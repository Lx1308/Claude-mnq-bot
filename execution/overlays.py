"""Marktprimitive fuer die Oberflaeche aufbereiten.

Warum ein Adapter und keine zweite Erkennung
--------------------------------------------
Die Oberflaeche darf die Erkennungslogik nicht noch einmal implementieren.
Erkannt wird ausschliesslich in ``common/market_primitives.py`` und
``common/structure.py`` - hier werden die Ergebnisse nur in die Formen
gebracht, die ``ui/frontend/src/api/types.ts`` beschreibt.

Vorher lieferten ``/api/overlays``, ``/api/analysis`` und ``/api/strategy``
leere Listen. Die Erkennung existierte die ganze Zeit; sie war nur nirgends
angeschlossen. Deshalb blieb der Chart nackt, obwohl die Haken gesetzt waren.

Zeitstempel: ``event_time`` oder ``availability_time``?
------------------------------------------------------
Beides steht in den Primitiven, und der Unterschied ist wichtig.

* ``event_time`` ist die Kerze, auf der das Muster **liegt**. Das ist, was ein
  Mensch im Chart sieht, und deshalb wird hier damit gezeichnet.
* ``availability_time`` ist der Zeitpunkt, ab dem das Muster **bekannt** war -
  ein Swing-Hoch mit Staerke 3 steht erst drei Kerzen spaeter fest.

Fuer die **Anzeige** ist ``event_time`` richtig. Fuer jede **Auswertung** ist
ausschliesslich ``availability_time`` zulaessig, sonst entsteht Lookahead.
Diese Datei zeichnet; sie wertet nichts aus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from common.config import Config
from common.instruments import Instrument
from common.market_primitives import (
    detect_displacements,
    detect_equal_highs_lows,
    detect_fair_value_gaps,
    detect_liquidity_sweeps,
    detect_structure_breaks,
)
from common.structure import assess_trend, classify_market_structure, find_swing_points

__all__ = ["baue_overlays", "baue_analyse", "MAX_PRIMITIVE"]

#: Obergrenze je Art. Ein Chart mit 400 Fair-Value-Gaps ist unlesbar, und die
#: Uebertragung waechst mit jeder Kerze. Genommen werden die juengsten.
MAX_PRIMITIVE = 60


def _ns(zeitpunkt: Any) -> int:
    """Zeitstempel in Nanosekunden - die Einheit, die das Frontend erwartet."""
    if zeitpunkt is None:
        return 0
    if isinstance(zeitpunkt, str):
        zeitpunkt = datetime.fromisoformat(zeitpunkt)
    if isinstance(zeitpunkt, pd.Timestamp):
        zeitpunkt = zeitpunkt.to_pydatetime()
    try:
        return int(zeitpunkt.timestamp() * 1_000_000_000)
    except (AttributeError, ValueError, OSError):
        return 0


def _index_von(df: pd.DataFrame, zeitpunkt: Any) -> int:
    """Position einer Kerze im Rahmen, oder -1.

    Das Frontend rechnet an einigen Stellen mit Indizes statt Zeitstempeln.
    ``-1`` heisst ausdruecklich "nicht im uebertragenen Ausschnitt" und nicht
    "erste Kerze" - deshalb kein 0 als Ersatzwert.
    """
    if zeitpunkt is None:
        return -1
    try:
        return int(df.index.get_loc(pd.Timestamp(zeitpunkt)))
    except (KeyError, TypeError, ValueError):
        return -1


def _richtung(wert: Any) -> str:
    """``Direction`` der Primitive auf 'bullish'/'bearish' abbilden."""
    text = str(getattr(wert, "value", wert)).lower()
    if text in ("bullish", "up", "long", "aufwaerts"):
        return "bullish"
    if text in ("bearish", "down", "short", "abwaerts"):
        return "bearish"
    return text


def baue_overlays(
    df: pd.DataFrame,
    instrument: Instrument,
    config: Config,
    *,
    symbol: str,
    timeframe: str,
    level: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Alles, was der Chart einzeichnet - aus einem vorbereiteten Rahmen.

    ``df`` muss die Indikatorspalten tragen (mindestens ``atr``), weil die
    Erkennung Groessen in ATR-Vielfachen misst. Ohne ATR waere ein
    "grosser" Gap nur eine Punktzahl - und die ist zwischen einem ruhigen und
    einem hektischen Tag nicht vergleichbar.
    """
    leer = {
        "symbol": symbol, "timeframe": timeframe, "swings": [], "fvgs": [],
        "pools": [], "sweeps": [], "structure_events": [], "displacements": [],
    }
    if df.empty:
        return leer

    atr_serie = df["atr"] if "atr" in df.columns else None
    staerke = config.analyse.swing_strength
    rueckblick = config.analyse.swing_lookback

    swings = find_swing_points(df, strength=staerke, lookback=rueckblick)
    fvgs = detect_fair_value_gaps(
        df, tick_size=instrument.tick_size, atr_series=atr_serie
    )
    displacements = detect_displacements(df, atr_series=atr_serie)
    # Liefert ZWEI Listen (gleiche Hochs, gleiche Tiefs) und nimmt einen
    # einzelnen ATR-Wert, keine Serie - anders als die uebrigen Erkenner.
    gleiche_hochs, gleiche_tiefs = detect_equal_highs_lows(
        df, swings=swings, strength=staerke, lookback=rueckblick,
        tick_size=instrument.tick_size,
        atr_value=float(atr_serie.iloc[-1]) if atr_serie is not None
        and not pd.isna(atr_serie.iloc[-1]) else None,
    )
    gleiche = list(gleiche_hochs) + list(gleiche_tiefs)
    brueche = detect_structure_breaks(
        df, swings=swings, strength=staerke, lookback=rueckblick,
        displacements=displacements, fvgs=fvgs,
    )
    sweeps = detect_liquidity_sweeps(
        df,
        levels=[(name, preis) for name, preis in (level or {}).items()] or None,
        tick_size=instrument.tick_size,
        atr_series=atr_serie,
    )

    # -- Swings ------------------------------------------------------------
    swing_json = [
        {
            "index": _index_von(df, s.timestamp),
            "ts": _ns(s.timestamp),
            "price": float(s.price),
            "type": "swing_high" if str(getattr(s.kind, "value", s.kind)).lower().startswith("high") else "swing_low",
            "strength": staerke,
            # Bestaetigt ist ein Swing erst, wenn `strength` Kerzen ohne
            # neues Extrem vergangen sind - genau der Lookahead-Abstand.
            "confirmed_at_index": _index_von(df, s.timestamp) + staerke,
        }
        for s in swings[-MAX_PRIMITIVE:]
    ]

    # -- Fair Value Gaps ---------------------------------------------------
    #
    # Nicht einfach die juengsten: ein noch OFFENER Gap von gestern ist fuer
    # eine Entscheidung wichtiger als ein geschlossener von vor zehn Minuten.
    # Offene zuerst, danach mit den juengsten geschlossenen auffuellen.
    offen = [g for g in fvgs if not g.is_mitigated][-MAX_PRIMITIVE:]
    geschlossen = [g for g in fvgs if g.is_mitigated][-(MAX_PRIMITIVE - len(offen)):]
    auswahl = sorted(offen + geschlossen, key=lambda g: g.event_time)

    fvg_json = []
    for nummer, gap in enumerate(auswahl):
        fvg_json.append({
            "id": nummer,
            "direction": _richtung(gap.kind),
            "created_index": _index_von(df, gap.event_time),
            "created_ts": _ns(gap.event_time),
            "bottom": float(gap.bottom),
            "top": float(gap.top),
            "size_ticks": float(gap.size_ticks),
            "state": "mitigated" if gap.is_mitigated else (
                "touched" if gap.fill_ratio and gap.fill_ratio > 0 else "open"
            ),
            "max_fill": float(gap.fill_ratio or 0.0),
            "touched_index": None,
            "mitigated_index": _index_von(df, gap.mitigation_time)
            if gap.is_mitigated else None,
            "closed_ts": _ns(gap.mitigation_time) if gap.is_mitigated else None,
        })

    # -- Liquiditaetszonen -------------------------------------------------
    #
    # Zwei Quellen: gleiche Hochs/Tiefs (EQH/EQL) und die benannten
    # Tagesniveaus (PDH/PDL, Asia, London ...). Beide sind Orte, an denen
    # Stops liegen - genau das, was Laurin sehen wollte.
    pools: list[dict[str, Any]] = []
    # Auch hier: unberuehrte Zonen zuerst - dort liegen die Stops noch.
    gleiche = sorted(gleiche, key=lambda g: (g.is_swept, -_ns(g.event_time)))
    for nummer, gleich in enumerate(gleiche[:MAX_PRIMITIVE]):
        oben = str(getattr(gleich.kind, "value", gleich.kind)).lower() == "high"
        pools.append({
            "id": nummer,
            "price": float(gleich.price_level),
            "side": "buy_side" if oben else "sell_side",
            "kind": "equal",
            "label": f"EQ{'H' if oben else 'L'}",
            "strength": len(gleich.swings),
            "state": "swept" if gleich.is_swept else "untapped",
            "created_ts": _ns(gleich.event_time),
            "tapped_index": _index_von(df, gleich.swept_time) if gleich.is_swept else None,
        })

    versatz = len(pools)
    for nummer, (name, preis) in enumerate((level or {}).items()):
        oben = name.endswith("_high")
        pools.append({
            "id": versatz + nummer,
            "price": float(preis),
            "side": "buy_side" if oben else "sell_side",
            "kind": "session" if name.split("_")[0] in ("asia", "london", "overnight")
                    else "prior_day",
            "label": name,
            "strength": 1,
            "state": "untapped",
            "created_ts": _ns(df.index[0]),
            "tapped_index": None,
        })

    # -- Sweeps ------------------------------------------------------------
    sweep_json = [
        {
            "pool_id": -1,     # nicht auf einen Pool oben abgebildet
            "pool_kind": "session" if s.level_name.split("_")[0] in
                         ("asia", "london", "overnight") else "prior_day",
            "pool_price": float(s.level_price),
            "side": "buy_side" if _richtung(s.direction) == "bearish" else "sell_side",
            "direction": _richtung(s.direction),
            "penetration_ts": _ns(s.event_time),
            "reclaim_ts": _ns(s.confirmation_time),
            "depth_ticks": float(s.sweep_depth_ticks),
            "bars_to_reclaim": int(s.reclaim_bars_taken or 0),
        }
        for s in sweeps[-MAX_PRIMITIVE:]
    ]

    # -- Strukturbrueche ---------------------------------------------------
    struktur_json = []
    for bruch in brueche[-MAX_PRIMITIVE:]:
        art = str(getattr(bruch.break_type, "value", bruch.break_type)).lower()
        richtung = _richtung(bruch.direction)
        kurz = "mss" if "mss" in art or "choch" in art else "bos"
        struktur_json.append({
            "index": _index_von(df, bruch.event_time),
            "ts": _ns(bruch.event_time),
            "type": f"{kurz}_{richtung}",
            "broken_price": float(bruch.broken_level),
            "break_price": float(bruch.swing_point.price),
            "previous_state": "range",
            "new_state": "bullish" if richtung == "bullish" else "bearish",
        })

    # -- Displacements -----------------------------------------------------
    displacement_json = [
        {
            "index": _index_von(df, d.bar_time),
            "ts": _ns(d.bar_time),
            "direction": _richtung(d.direction),
            "range": float(d.range_points),
            "body_ratio": float(d.body_ratio),
            "range_atr_mult": float(d.body_atr),
            "volume_ratio": None if d.relative_volume is None else float(d.relative_volume),
            "volume_confirmed": bool(d.relative_volume and d.relative_volume > 1.0),
            "strength": float(d.body_atr),
        }
        for d in displacements[-MAX_PRIMITIVE:]
    ]

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "swings": swing_json,
        "fvgs": fvg_json,
        "pools": pools,
        "sweeps": sweep_json,
        "structure_events": struktur_json,
        "displacements": displacement_json,
    }


def baue_analyse(
    rahmen_je_timeframe: dict[str, pd.DataFrame],
    config: Config,
    *,
    symbol: str,
) -> dict[str, Any]:
    """Trend und Struktur je Zeitebene - die Grundlage des Bias-Panels.

    Bewusst ueber ``assess_trend``/``classify_market_structure`` aus
    ``common/structure.py``, also dieselbe Bewertung, die auch der
    ``/analyse``-Bericht des MCP-Servers benutzt. Eine eigene Trendformel fuer
    die Oberflaeche waere eine zweite Wahrheit ueber denselben Markt.
    """
    je_timeframe: dict[str, Any] = {}
    bewertungen: list[float] = []
    gruende: list[str] = []
    letzter_kurs = 0.0
    letzter_ts = 0

    for timeframe, df in rahmen_je_timeframe.items():
        if df is None or df.empty:
            continue
        atr = float(df["atr"].iloc[-1]) if "atr" in df.columns else None
        trend = assess_trend(
            df,
            atr_value=atr,
            slope_lookback=config.analyse.trend_slope_lookback,
            flat_threshold_atr=config.analyse.trend_flat_threshold_atr,
        )
        struktur = classify_market_structure(
            df,
            strength=config.analyse.swing_strength,
            lookback=config.analyse.swing_lookback,
        )
        letzter_kurs = float(df["close"].iloc[-1])
        letzter_ts = _ns(df.index[-1])

        punktzahl = {"aufwaerts": 1.0, "abwaerts": -1.0}.get(trend.direction, 0.0)
        bewertungen.append(punktzahl)
        gruende.append(f"{timeframe}: {trend.direction} ({struktur.trend})")

        je_timeframe[timeframe] = {
            "timeframe": timeframe,
            "score": punktzahl,
            "structure_score": punktzahl,
            "fvg_score": 0.0,
            "liquidity_score": 0.0,
            "structure_state": (
                "bullish" if punktzahl > 0 else "bearish" if punktzahl < 0 else "range"
            ),
            "active_bullish_fvgs": 0,
            "active_bearish_fvgs": 0,
            "nearest_buy_side": None,
            "nearest_sell_side": None,
            "trend": trend.direction,
            "struktur": struktur.trend,
            "atr": atr,
            "close": letzter_kurs,
        }

    mittel = sum(bewertungen) / len(bewertungen) if bewertungen else 0.0
    return {
        "symbol": symbol,
        "last_ts": letzter_ts,
        "session": "",
        "bias": {
            "bias": "bullish" if mittel > 0.25 else "bearish" if mittel < -0.25 else "neutral",
            "score": mittel,
            "per_timeframe": list(je_timeframe.values()),
            "reasons": gruende,
        },
        "timeframes": je_timeframe,
    }
