"""Tool 1: ``get_market_snapshot``.

Setzt vollstaendig auf den bestehenden Bausteinen auf:

* Indikatoren -> :func:`common.indicators.compute_extended_indicators`
* Levels      -> :func:`common.levels.compute_levels`
* Struktur    -> :mod:`common.structure`
* Muster      -> :mod:`common.patterns`
* Session     -> :func:`common.sessions.session_context`
* Kontrakt    -> :mod:`common.instruments`

Kein Anthropic-Aufruf, keine Prosa - nur Zahlen mit Einheiten. Die
Interpretation passiert in der Claude-Desktop-Unterhaltung.

Zu den Levels: Vortageshoch/-tief brauchen die **vollstaendige** vorherige
Handelssession im Fenster - nicht nur irgendeinen Bar aus ihr. Der
1m-Timeframe schafft das mit den geladenen Bars nicht, der 5m- oder
15m-Timeframe schon. Deshalb wird der Levelblock EINMAL aus dem feinsten
Timeframe berechnet, der die Vorsession wirklich komplett enthaelt
(:func:`_vorsession_vollstaendig`), und der verwendete Timeframe im Ergebnis
ausgewiesen. Sonst haette derselbe PDH je nach Chart einen anderen Wert -
was schlicht falsch waere.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from common.config import Config
from common.indicators import (
    compute_extended_indicators,
    session_cumulative_delta,
)
from common.instruments import Instrument
from common.levels import LevelSet, compute_levels, history_dependent_metrics
from common.patterns import detect_all_patterns
from common.sessions import session_bounds, session_context, session_dates
from common.structure import (
    assess_trend,
    classify_market_structure,
    detect_rsi_divergence,
    find_swing_points,
    support_resistance_zones,
)
from common.config import SessionConfig
from mcp_server.bars import DAILY, BarSet, LoadedBars

# Wie viele Rohkerzen je Timeframe mitgeliefert werden. Bewusst knapp:
# der volle Satz waere 30-60 KB JSON je Aufruf und wuerde in jeder
# Claude-Desktop-Unterhaltung spuerbar Kontext kosten.
# Definiert in bars.py, damit server.py sie ohne pandas erreicht.
from mcp_server.bars import DEFAULT_BARS_IN_OUTPUT  # noqa: E402


def _clean(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _round(value: Any, digits: int = 2) -> float | None:
    cleaned = _clean(value)
    return round(cleaned, digits) if cleaned is not None else None


def _bar_abstand(frame: pd.DataFrame) -> timedelta:
    """Typischer zeitlicher Abstand zwischen zwei Bars des Frames."""
    if len(frame.index) < 2:
        return timedelta(0)
    abstaende = pd.Series(frame.index).diff().dropna()
    if abstaende.empty:
        return timedelta(0)
    return abstaende.median().to_pytimedelta()


def _vorsession_vollstaendig(frame: pd.DataFrame, session_cfg: SessionConfig) -> bool:
    """Enthaelt der Frame die **komplette** vorherige Handelssession?

    WARUM NICHT EINFACH ZWEI SESSIONS ZAEHLEN
    -----------------------------------------
    Die fruehere Fassung pruefte ``len(set(session_dates(...))) >= 2`` - also
    die Anzahl verschiedener Session-*Daten*. Das war falsch, und zwar auf
    die teuerste Art: lautlos.

    Ein auf 1500 Bars gedeckelter 1-Minuten-Frame umfasst rund 25 Stunden.
    Er beruehrt damit zwei Session-Daten, enthaelt die aeltere aber nur zu
    einem Bruchteil. Die alte Pruefung sagte trotzdem "ja", ``compute_levels``
    berechnete das Vortageshoch aus einem **angeschnittenen** Tag, und der
    Snapshot wies das Ergebnis auch noch als geprueft aus.

    Gemessen an echten MNQ-Daten (21.08.2026): der gedeckelte Frame lieferte
    ein Vortageshoch von 29686.75, die vollstaendige Session 29688.50. Hier
    waren es 1,75 Punkte. Der Fehler ist aber **nicht nach oben begrenzt** -
    faellt das echte Hoch frueh in der Session, liegt der Wert beliebig weit
    daneben. Genau die Fehlerklasse aus Bug-Lehre 1.

    DIE PRUEFUNG
    ------------
    Die vorherige Session ist die zweitjuengste im Frame. Sie gilt als
    vollstaendig, wenn der Frame mindestens einen Bar **an ihrem Beginn**
    enthaelt. Das faengt beides ab: einen zu kurzen Frame und ein Loch in
    den Daten am Sessionanfang.

    Die Toleranz von zwei Bar-Abstaenden ist noetig, weil ein Bar den
    Schluss seines Intervalls traegt: der erste 1-Minuten-Bar einer um 22:00
    beginnenden Session steht auf 22:01. Faellt die Pruefung im Zweifel
    negativ aus, waehlt der Aufrufer einen groberen, weiter zurueckreichenden
    Timeframe - der Irrtum geht also in Richtung Korrektheit, nicht in
    Richtung falscher Zahl.
    """
    if frame.empty:
        return False

    tage = sorted(set(session_dates(frame.index, session_cfg).values))
    if len(tage) < 2:
        return False

    vorsession_start, _ = session_bounds(tage[-2], session_cfg)
    toleranz = 2 * _bar_abstand(frame)

    beginn_abgedeckt = (frame.index >= vorsession_start) & (
        frame.index <= vorsession_start + toleranz
    )
    return bool(beginn_abgedeckt.any())


# ---------------------------------------------------------------------------
# Bloecke je Timeframe
# ---------------------------------------------------------------------------

def _momentum_block(enriched: pd.DataFrame, instrument: Instrument) -> dict[str, Any]:
    last = enriched.iloc[-1]
    divergence = detect_rsi_divergence(enriched)

    return {
        "rsi_14": {
            "value": _round(last.get("rsi"), 1),
            "unit": "index_0_100",
            "divergenz": divergence.to_dict(),
        },
        "macd_12_26_9": {
            "linie": _round(last.get("macd_line"), 4),
            "signal": _round(last.get("macd_signal"), 4),
            "histogramm": _round(last.get("macd_hist"), 4),
            "unit": "punkte",
        },
        "stochastik_14_3_3": {
            "k": _round(last.get("stoch_k"), 1),
            "d": _round(last.get("stoch_d"), 1),
            "unit": "index_0_100",
        },
        "ema": {
            "ema_9": _round(last.get("ema_9")),
            "ema_21": _round(last.get("ema_21")),
            "ema_50": _round(last.get("ema_50")),
            "ema_200": _round(last.get("ema_200")),
            "unit": "preis",
            "gestapelt_bullisch": bool(last.get("ema_stacked_bullish", False)),
            "gestapelt_baerisch": bool(last.get("ema_stacked_bearish", False)),
            "hinweis": "Staffelung ist ein Form-, kein Staerkesignal - ADX daneben lesen.",
        },
        "adx_14": {
            "adx": _round(last.get("adx"), 1),
            "plus_di": _round(last.get("plus_di"), 1),
            "minus_di": _round(last.get("minus_di"), 1),
            "unit": "index_0_100",
            "regime": _adx_regime(_clean(last.get("adx"))),
        },
    }


def _adx_regime(adx_value: float | None) -> str | None:
    """Grobe Einordnung - die Schwellen 20/25 sind Konvention, kein Gesetz."""
    if adx_value is None:
        return None
    if adx_value < 20:
        return "chop"
    if adx_value < 25:
        return "uebergang"
    return "trend"


def _volatility_block(enriched: pd.DataFrame, instrument: Instrument) -> dict[str, Any]:
    last = enriched.iloc[-1]
    atr_value = _clean(last.get("atr"))

    return {
        "atr_14": {
            "punkte": _round(atr_value),
            "ticks": _round(atr_value / instrument.tick_size, 1) if atr_value else None,
            "usd_je_kontrakt": _round(instrument.points_to_usd(atr_value)) if atr_value else None,
        },
        "bollinger_20_2": {
            "oben": _round(last.get("bb_upper")),
            "mitte": _round(last.get("bb_middle")),
            "unten": _round(last.get("bb_lower")),
            "bandbreite": _round(last.get("bb_bandwidth"), 4),
            "squeeze": bool(last.get("bb_squeeze", False)),
            "squeeze_definition": "Bollinger-Band innerhalb Keltner (EMA20 +/- 1.5 ATR)",
            "unit": "preis",
        },
    }


def _volume_block(
    enriched: pd.DataFrame, bar_set: BarSet, session_cfg: SessionConfig
) -> dict[str, Any]:
    last = enriched.iloc[-1]
    vwap = _clean(last.get("vwap"))

    # VWAP-Baender aus der Standardabweichung der Schlusskurse um den VWAP
    # innerhalb der laufenden Session.
    bands: dict[str, Any] = {"sigma1_oben": None, "sigma1_unten": None,
                             "sigma2_oben": None, "sigma2_unten": None}
    sessions = session_dates(enriched.index, session_cfg)
    current_session = enriched[sessions.values == sessions.iloc[-1]]
    if vwap is not None and len(current_session) >= 2:
        deviation = float((current_session["close"] - current_session["vwap"]).std(ddof=0))
        if deviation > 0:
            bands = {
                "sigma1_oben": round(vwap + deviation, 2),
                "sigma1_unten": round(vwap - deviation, 2),
                "sigma2_oben": round(vwap + 2 * deviation, 2),
                "sigma2_unten": round(vwap - 2 * deviation, 2),
                "sigma_punkte": round(deviation, 2),
            }

    delta_series = session_cumulative_delta(enriched, session_cfg)
    if delta_series is None:
        delta_block: dict[str, Any] = {
            "kumulativ": None,
            "letzte_kerze": None,
            "verfuegbar": False,
            "reason": "NinjaTrader liefert Bid-/Ask-Volumen je Kerze nur mit dem "
                      "kostenpflichtigen Add-on 'Order Flow +'. Das ist nicht "
                      "lizenziert, deshalb bleibt das Delta dauerhaft null. "
                      "Es wird bewusst nichts aus Auf-/Abwaertskerzen geschaetzt - "
                      "eine Schaetzung saehe aus wie eine Messung und waere keine.",
        }
    else:
        bar_delta = float(enriched["ask_volume"].iloc[-1] - enriched["bid_volume"].iloc[-1])
        delta_block = {
            "kumulativ": round(float(delta_series.iloc[-1]), 0),
            "letzte_kerze": round(bar_delta, 0),
            "verfuegbar": True,
            "unit": "kontrakte",
            "hinweis": "Setzt zu jedem Sessionbeginn zurueck.",
        }

    return {
        "session_vwap": {"value": _round(vwap), "unit": "preis", **bands},
        "volumen_letzte_kerze": _round(last.get("volume"), 0),
        "kumulatives_delta": delta_block,
    }


def _structure_block(enriched: pd.DataFrame, instrument: Instrument, config: Config) -> dict[str, Any]:
    analyse = config.analyse
    atr_value = _clean(enriched["atr"].iloc[-1]) if "atr" in enriched.columns else None

    structure = classify_market_structure(
        enriched, strength=analyse.swing_strength, lookback=analyse.swing_lookback
    )
    supports, resistances = support_resistance_zones(
        enriched,
        atr_value=atr_value,
        strength=analyse.swing_strength,
        lookback=analyse.swing_lookback,
        max_zones=analyse.max_zones,
        merge_atr=analyse.zone_merge_atr,
    )
    trend = assess_trend(
        enriched,
        atr_value=atr_value,
        slope_lookback=analyse.trend_slope_lookback,
        flat_threshold_atr=analyse.trend_flat_threshold_atr,
    )
    swings = find_swing_points(
        enriched, strength=analyse.swing_strength, lookback=analyse.swing_lookback
    )[:6]

    return {
        "marktstruktur": structure.to_dict(),
        "trend": trend.to_dict(),
        "letzte_swings": [swing.to_dict() for swing in swings],
        "zonen": {
            "unterstuetzungen": [zone.to_dict() for zone in supports],
            "widerstaende": [zone.to_dict() for zone in resistances],
        },
    }


def _bars_block(enriched: pd.DataFrame, count: int) -> list[dict[str, Any]]:
    tail = enriched.iloc[-count:]
    rows: list[dict[str, Any]] = []
    for timestamp, row in tail.iterrows():
        entry = {
            "t": timestamp.isoformat(),
            "o": _round(row["open"]),
            "h": _round(row["high"]),
            "l": _round(row["low"]),
            "c": _round(row["close"]),
            "v": _round(row["volume"], 0),
        }
        if "bid_volume" in tail.columns and float(row["bid_volume"] + row["ask_volume"]) > 0:
            entry["delta"] = _round(row["ask_volume"] - row["bid_volume"], 0)
        rows.append(entry)
    return rows


# ---------------------------------------------------------------------------
# Gesamtaufbau
# ---------------------------------------------------------------------------

def build_snapshot_payload(
    loaded: LoadedBars,
    config: Config,
    *,
    timeframes: list[str],
    include_bars: bool = True,
    bars_in_output: int = DEFAULT_BARS_IN_OUTPUT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Baut das vollstaendige Snapshot-JSON."""
    now = now or datetime.now(timezone.utc)
    instrument = loaded.instrument
    session_cfg = SessionConfig(timezone=instrument.timezone)

    enriched_by_tf: dict[str, pd.DataFrame] = {}
    for timeframe in timeframes:
        bar_set = loaded.get(timeframe)
        if bar_set is None:
            continue
        enriched_by_tf[timeframe] = compute_extended_indicators(
            bar_set.frame, config.indicators, session_cfg
        )

    if not enriched_by_tf:
        raise ValueError("Kein Timeframe konnte ausgewertet werden.")

    # --- Levels einmalig aus dem besten Timeframe -------------------------
    level_set, level_timeframe = _choose_level_frame(enriched_by_tf, session_cfg, instrument)

    # Fuer die historienabhaengigen Kennzahlen zaehlt nicht die Aufloesung,
    # sondern die Anzahl abgedeckter Handelssessions. Der Level-Frame ist
    # bewusst der feinste - hier wollen wir den weitreichendsten.
    _history_frame = _choose_history_frame(enriched_by_tf, session_cfg)

    # Kein "or" auf DataFrames: das ruft __bool__ auf und wirft bei pandas.
    reference = enriched_by_tf.get("5m")
    if reference is None:
        reference = next(iter(enriched_by_tf.values()))
    latest_timestamp = reference.index[-1].to_pydatetime()

    payload: dict[str, Any] = {
        "meta": {
            "erzeugt_utc": now.isoformat(),
            "server": "claude-chart-bot mcp_server",
            "hinweis": "Reine Kennzahlen. Interpretation erfolgt in der Unterhaltung, "
                       "nicht im Server.",
        },
        "instrument": {
            **instrument.describe_contract(),
            "aktiver_kontrakt": loaded.contract.name,
            "kontrakt_verfall": (
                loaded.contract.expiry.isoformat() if loaded.contract.expiry else None
            ),
        },
        "session": session_context(latest_timestamp, instrument),
        "datenherkunft": _provenance_block(loaded, timeframes, session_cfg, now),
        "levels": {
            **level_set.to_dict(),
            "berechnet_aus_timeframe": level_timeframe,
            "hinweis": "Levels sind timeframeunabhaengig und werden einmal aus dem "
                       "feinsten Timeframe berechnet, der die vorherige Session "
                       "vollstaendig enthaelt.",
        },
        # Kennzahlen, die mehrere Handelssessions Historie brauchen. Sie
        # fuellen sich im laufenden Betrieb von selbst, weil der
        # NinjaTrader-Speicher mit jeder Session waechst. Bis dahin steht
        # dort null MIT Angabe, was noch fehlt.
        "historienabhaengig": history_dependent_metrics(
            _history_frame, instrument, session_cfg,
            atr_series=_history_frame["atr"] if "atr" in _history_frame.columns else None,
            daily_frame=enriched_by_tf.get(DAILY),
        ),
        "timeframes": {},
    }

    for timeframe, enriched in enriched_by_tf.items():
        bar_set = loaded[timeframe]
        last = enriched.iloc[-1]
        atr_value = _clean(last.get("atr"))

        block: dict[str, Any] = {
            "bars_verfuegbar": len(enriched),
            "letzte_kerze": {
                "zeit_utc": enriched.index[-1].isoformat(),
                "open": _round(last["open"]),
                "high": _round(last["high"]),
                "low": _round(last["low"]),
                "close": _round(last["close"]),
                "volumen": _round(last["volume"], 0),
            },
            "momentum": _momentum_block(enriched, instrument),
            "volatilitaet": _volatility_block(enriched, instrument),
            "volumen": _volume_block(enriched, bar_set, session_cfg),
            "struktur": _structure_block(enriched, instrument, config),
            "muster": [
                pattern.to_dict()
                for pattern in detect_all_patterns(
                    enriched,
                    instrument=instrument,
                    levels=level_set.levels,
                    atr_value=atr_value,
                    strength=config.analyse.swing_strength,
                    lookback=config.analyse.swing_lookback,
                )
            ],
        }

        if include_bars:
            block["letzte_bars"] = _bars_block(enriched, bars_in_output)

        payload["timeframes"][timeframe] = block

    return payload


def _choose_level_frame(
    enriched_by_tf: dict[str, pd.DataFrame],
    session_cfg: SessionConfig,
    instrument: Instrument,
) -> tuple[LevelSet, str]:
    """Waehlt den feinsten Timeframe, der die Vorsession VOLLSTAENDIG enthaelt."""
    preference = ["1m", "5m", "15m", "1h", DAILY]

    for timeframe in preference:
        frame = enriched_by_tf.get(timeframe)
        if frame is None or frame.empty:
            continue
        if _vorsession_vollstaendig(frame, session_cfg):
            return compute_levels(frame, instrument, session_cfg=session_cfg), timeframe

    # Kein Timeframe enthaelt die Vorsession vollstaendig - dann den feinsten
    # nehmen; die Vortagesmarken sind dann entsprechend gekennzeichnet.
    for timeframe in preference:
        frame = enriched_by_tf.get(timeframe)
        if frame is not None and not frame.empty:
            return compute_levels(frame, instrument, session_cfg=session_cfg), timeframe

    raise ValueError("Keine Bars zur Levelberechnung vorhanden.")


def _choose_history_frame(
    enriched_by_tf: dict[str, pd.DataFrame], session_cfg: SessionConfig
) -> pd.DataFrame:
    """Intraday-Frame mit der groessten Sessionabdeckung.

    Relatives Volumen und ATR-Perzentil vergleichen dieselbe Tageszeit ueber
    viele Sessions - dafuer zaehlt Reichweite, nicht Aufloesung. Tageskerzen
    scheiden aus, weil sie keine Uhrzeit innerhalb der Session kennen.
    """
    best: pd.DataFrame | None = None
    best_sessions = -1

    for timeframe, frame in enriched_by_tf.items():
        if timeframe == DAILY or frame.empty:
            continue
        sessions = len(set(session_dates(frame.index, session_cfg).values))
        if sessions > best_sessions:
            best, best_sessions = frame, sessions

    if best is None:
        best = next(iter(enriched_by_tf.values()))
    return best


def _provenance_block(
    loaded: LoadedBars,
    timeframes: list[str],
    session_cfg: SessionConfig,
    now: datetime,
) -> dict[str, Any]:
    """Woher die Daten stammen und wie frisch sie sind."""
    per_timeframe: dict[str, Any] = {}
    for timeframe in timeframes:
        bar_set = loaded.get(timeframe)
        if bar_set is None:
            per_timeframe[timeframe] = {
                "verfuegbar": False,
                "fehler": loaded.errors.get(timeframe, "nicht geladen"),
            }
            continue
        per_timeframe[timeframe] = {
            "verfuegbar": True,
            "quelle": bar_set.source,
            "bars_angefordert": bar_set.requested_bars,
            "bars_erhalten": bar_set.bars_available,
            "aeltester_bar_utc": bar_set.oldest.isoformat() if bar_set.oldest else None,
            "juengster_bar_utc": bar_set.newest.isoformat() if bar_set.newest else None,
            "alter_juengster_bar_sekunden": _round(bar_set.age_seconds(now), 0),
            "vorsession_vollstaendig": _vorsession_vollstaendig(bar_set.frame, session_cfg),
            "bid_ask_volumen_vorhanden": bar_set.has_flow,
            # Deutliches Flag: laenger als zwei Bar-Laengen kein neuer Bar.
            # Waehrend der Handelszeit heisst das fast immer, dass in
            # NinjaTrader kein Chart mehr laeuft.
            "veraltet": bar_set.is_stale(now),
            "veraltet_hinweis": (
                "Juengster Bar aelter als zwei Bar-Laengen. Innerhalb der "
                "Handelszeit deutet das darauf hin, dass NinjaTrader nicht "
                "laeuft oder das Chart geschlossen wurde. Ausserhalb der "
                "Handelszeit ist es normal - siehe session.globex_state."
                if bar_set.is_stale(now) else None
            ),
        }

    return {
        "kontrakt": loaded.contract.name,
        "je_timeframe": per_timeframe,
        "hinweis": "Die jeweils laufende (unfertige) Kerze ist bewusst nicht enthalten.",
    }


__all__ = ["DEFAULT_BARS_IN_OUTPUT", "build_snapshot_payload"]
