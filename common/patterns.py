"""Chart- und Kerzenmuster mit Konfidenz und nachvollziehbarer Herleitung.

Grundsatz: Jedes gemeldete Muster traegt die **Rohzahlen mit**, aus denen es
abgeleitet wurde. Ein "Doppeltop erkannt" ohne die beiden Hochs, ihren
Abstand und die Tiefe des Zwischentiefs ist eine Behauptung, keine Analyse -
und in Claude Desktop nicht nachpruefbar.

Die Konfidenz ist immer eine gerechnete Groesse aus diesen Rohzahlen, nie
ein geschaetzter Wert. Wie sie zustande kommt, steht bei jedem Detektor.

Kerzenmuster werden ausdruecklich nur an einem bekannten Level gemeldet und
dort als schwaches Einzelsignal markiert. Ein Engulfing mitten im Nirgendwo
ist Rauschen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from common.indicators import FlagColumns
from common.instruments import Instrument
from common.levels import Level
from common.structure import SwingPoint, find_swing_points

Direction = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class Pattern:
    """Ein erkanntes Muster samt Herleitung."""

    name: str
    kind: Literal["chart", "candle"]
    direction: Direction
    confidence: float                      # 0.0 - 1.0, gerechnet
    evidence: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    weak_signal: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "art": self.kind,
            "richtung": self.direction,
            "konfidenz": round(self.confidence, 2),
            "herleitung": self.evidence,
            "hinweis": self.note,
            "schwaches_einzelsignal": self.weak_signal,
        }


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Flagge / Wimpel
# ---------------------------------------------------------------------------

def detect_flag(df: pd.DataFrame) -> Pattern | None:
    """Liest die Flaggen-Heuristik aus :func:`common.indicators.flag_signals`.

    Kein eigener Algorithmus - die Spalten stammen aus ``compute_indicators``
    und sind damit identisch zu dem, was Live-Bot und Backtest sehen.

    Konfidenz: je enger die Konsolidierung relativ zum vorausgegangenen
    Impuls, desto sauberer die Flagge. 0.5 Grundwert, plus bis zu 0.5 aus
    dem Verhaeltnis Impulshoehe zu Rangebreite.
    """
    columns = FlagColumns()
    if columns.direction not in df.columns:
        return None

    last = df.iloc[-1]
    direction_value = int(last.get(columns.direction, 0) or 0)
    if direction_value == 0:
        return None

    range_width = last.get(columns.consolidation_range)
    impulse = last.get(columns.impulse)
    if _is_nan(range_width) or _is_nan(impulse) or float(range_width) <= 0:
        return None

    ratio = abs(float(impulse)) / float(range_width)
    confidence = _clamp(0.5 + 0.1 * (ratio - 2.0))

    broke_up = bool(last.get(columns.breakout_up, False))
    broke_down = bool(last.get(columns.breakout_down, False))
    in_consolidation = bool(last.get(columns.in_consolidation, False))

    if broke_up or broke_down:
        name = "Flaggen-Ausbruch"
        direction: Direction = "bullish" if broke_up else "bearish"
    elif in_consolidation:
        name = "Flagge in Konsolidierung"
        direction = "bullish" if direction_value > 0 else "bearish"
    else:
        return None

    return Pattern(
        name=name,
        kind="chart",
        direction=direction,
        confidence=confidence,
        evidence={
            "impuls_punkte": round(float(impulse), 4),
            "range_breite_punkte": round(float(range_width), 4),
            "verhaeltnis_impuls_zu_range": round(ratio, 2),
            "range_hoch": round(float(last.get(columns.consolidation_high)), 4)
            if not _is_nan(last.get(columns.consolidation_high)) else None,
            "range_tief": round(float(last.get(columns.consolidation_low)), 4)
            if not _is_nan(last.get(columns.consolidation_low)) else None,
            "ausbruch": broke_up or broke_down,
        },
        note="Heuristik aus Impuls + enger Range, kein bestaetigtes Chartmuster.",
    )


# ---------------------------------------------------------------------------
# Dreieck
# ---------------------------------------------------------------------------

def detect_triangle(
    df: pd.DataFrame,
    *,
    strength: int = 3,
    lookback: int = 120,
    atr_value: float | None = None,
    flat_tolerance_atr: float = 0.3,
) -> Pattern | None:
    """Erkennt symmetrische, aufsteigende und absteigende Dreiecke.

    Grundlage sind die letzten je zwei Swing-Hochs und -Tiefs:

    * fallende Hochs UND steigende Tiefs -> symmetrisches Dreieck
    * flache Hochs UND steigende Tiefs   -> aufsteigend (bullisch)
    * fallende Hochs UND flache Tiefs    -> absteigend (baerisch)

    "Flach" heisst: die beiden Punkte liegen weniger als
    ``flat_tolerance_atr`` ATR auseinander. Ohne ATR-Bezug waere die
    Schwelle zwischen MNQ und MGC nicht uebertragbar.

    Konfidenz: aus dem Grad der Verengung - wie stark die Spanne zwischen
    Hochs und Tiefs von der ersten zur zweiten Messung abgenommen hat.
    """
    swings = find_swing_points(df, strength=strength, lookback=lookback)
    highs = sorted([s for s in swings if s.kind == "high"], key=lambda s: s.bars_ago)
    lows = sorted([s for s in swings if s.kind == "low"], key=lambda s: s.bars_ago)

    if len(highs) < 2 or len(lows) < 2:
        return None

    new_high, old_high = highs[0], highs[1]
    new_low, old_low = lows[0], lows[1]

    tolerance = (atr_value or 0.0) * flat_tolerance_atr
    high_delta = new_high.price - old_high.price
    low_delta = new_low.price - old_low.price

    highs_falling = high_delta < -tolerance
    highs_flat = abs(high_delta) <= tolerance
    lows_rising = low_delta > tolerance
    lows_flat = abs(low_delta) <= tolerance

    if highs_falling and lows_rising:
        name, direction = "Symmetrisches Dreieck", "neutral"
    elif highs_flat and lows_rising:
        name, direction = "Aufsteigendes Dreieck", "bullish"
    elif highs_falling and lows_flat:
        name, direction = "Absteigendes Dreieck", "bearish"
    else:
        return None

    old_span = old_high.price - old_low.price
    new_span = new_high.price - new_low.price
    if old_span <= 0:
        return None

    contraction = 1.0 - (new_span / old_span)
    confidence = _clamp(contraction * 1.5)

    return Pattern(
        name=name,
        kind="chart",
        direction=direction,
        confidence=confidence,
        evidence={
            "hoch_alt": round(old_high.price, 4),
            "hoch_neu": round(new_high.price, 4),
            "tief_alt": round(old_low.price, 4),
            "tief_neu": round(new_low.price, 4),
            "spanne_alt_punkte": round(old_span, 4),
            "spanne_neu_punkte": round(new_span, 4),
            "verengung_prozent": round(contraction * 100, 1),
            "flach_toleranz_punkte": round(tolerance, 4),
        },
        note="Ausbruchsrichtung ist offen, bis der Kurs eine Begrenzung schliesst.",
    )


# ---------------------------------------------------------------------------
# Doppeltop / Doppelboden
# ---------------------------------------------------------------------------

def detect_double_top_bottom(
    df: pd.DataFrame,
    *,
    strength: int = 3,
    lookback: int = 120,
    atr_value: float | None = None,
    max_peak_distance_atr: float = 0.5,
    min_trough_depth_atr: float = 1.0,
) -> Pattern | None:
    """Zwei aehnlich hohe Extrema mit ausreichend tiefem Zwischental.

    Beide Bedingungen sind noetig: liegen die Spitzen zu weit auseinander,
    ist es kein Doppeltop; ist das Zwischental zu flach, ist es lediglich
    eine Seitwaertsbewegung an einem Level.

    Konfidenz: je naeher die beiden Spitzen beieinander und je tiefer das
    Zwischental, desto hoeher.
    """
    if not atr_value or atr_value <= 0:
        return None

    swings = find_swing_points(df, strength=strength, lookback=lookback)

    for kind, name, direction in (
        ("high", "Doppeltop", "bearish"),
        ("low", "Doppelboden", "bullish"),
    ):
        same = sorted([s for s in swings if s.kind == kind], key=lambda s: s.bars_ago)
        opposite = [s for s in swings if s.kind != kind]
        if len(same) < 2:
            continue

        second, first = same[0], same[1]
        peak_distance = abs(second.price - first.price)
        if peak_distance > max_peak_distance_atr * atr_value:
            continue

        # Zwischental muss zeitlich zwischen den beiden Spitzen liegen.
        between = [
            point for point in opposite
            if second.bars_ago < point.bars_ago < first.bars_ago
        ]
        if not between:
            continue

        trough = (
            min(between, key=lambda point: point.price)
            if kind == "high"
            else max(between, key=lambda point: point.price)
        )
        depth = abs(((first.price + second.price) / 2.0) - trough.price)
        if depth < min_trough_depth_atr * atr_value:
            continue

        closeness = 1.0 - (peak_distance / (max_peak_distance_atr * atr_value))
        depth_score = _clamp(depth / (2.0 * min_trough_depth_atr * atr_value))
        confidence = _clamp(0.4 * closeness + 0.6 * depth_score)

        return Pattern(
            name=name,
            kind="chart",
            direction=direction,
            confidence=confidence,
            evidence={
                "erste_spitze": round(first.price, 4),
                "zweite_spitze": round(second.price, 4),
                "abstand_der_spitzen_punkte": round(peak_distance, 4),
                "abstand_der_spitzen_atr": round(peak_distance / atr_value, 2),
                "zwischental": round(trough.price, 4),
                "tiefe_punkte": round(depth, 4),
                "tiefe_atr": round(depth / atr_value, 2),
                "kerzen_zwischen_den_spitzen": first.bars_ago - second.bars_ago,
                "nackenlinie": round(trough.price, 4),
            },
            note="Bestaetigt gilt das Muster erst mit Schlusskurs jenseits der Nackenlinie.",
        )

    return None


# ---------------------------------------------------------------------------
# Range-Kompression
# ---------------------------------------------------------------------------

def detect_range_compression(
    df: pd.DataFrame,
    *,
    recent_bars: int = 20,
    reference_bars: int = 60,
    atr_value: float | None = None,
    max_ratio: float = 0.6,
) -> Pattern | None:
    """Aktuelle Spanne deutlich enger als die ueblichen Spannen davor.

    Verglichen wird **gleich lang gegen gleich lang**: die Spanne der
    letzten ``recent_bars`` Kerzen gegen den Median der Spannen aller
    gleich langen Fenster im davorliegenden Referenzzeitraum.

    Warum nicht einfach "20-Bar-Spanne gegen 60-Bar-Spanne": die Spanne
    eines Zufallspfads waechst ungefaehr mit der Wurzel der Fensterlaenge.
    20 gegen 60 Kerzen ergaebe schon ohne jede Kompression ein Verhaeltnis
    um sqrt(20/60) = 0.58 - der Detektor wuerde auf praktisch jedem
    Kursverlauf anschlagen.

    Konfidenz: je staerker die Verengung, desto hoeher - linear von
    ``max_ratio`` (Konfidenz 0) bis Verhaeltnis 0 (Konfidenz 1).
    """
    needed = 2 * recent_bars + reference_bars
    if len(df) < needed:
        return None

    recent = df.iloc[-recent_bars:]
    recent_range = float(recent["high"].max() - recent["low"].min())

    rolling_range = (
        df["high"].rolling(recent_bars, min_periods=recent_bars).max()
        - df["low"].rolling(recent_bars, min_periods=recent_bars).min()
    )
    # Fenster, die keine der letzten recent_bars Kerzen enthalten.
    reference_slice = rolling_range.iloc[-(reference_bars + recent_bars):-recent_bars].dropna()
    if reference_slice.empty:
        return None

    typical_range = float(reference_slice.median())
    if typical_range <= 0:
        return None

    ratio = recent_range / typical_range
    if ratio > max_ratio:
        return None

    return Pattern(
        name="Range-Kompression",
        kind="chart",
        direction="neutral",
        confidence=_clamp(1.0 - ratio / max_ratio),
        evidence={
            "spanne_aktuell_punkte": round(recent_range, 4),
            "spanne_typisch_punkte": round(typical_range, 4),
            "verhaeltnis": round(ratio, 3),
            "fensterlaenge_kerzen": recent_bars,
            "referenzfenster_kerzen": reference_bars,
            "vergleichsfenster_anzahl": int(len(reference_slice)),
            "spanne_aktuell_atr": round(recent_range / atr_value, 2) if atr_value else None,
        },
        note="Vergleich gleich langer Fenster. Kompression sagt nichts ueber "
             "die Ausbruchsrichtung.",
    )


# ---------------------------------------------------------------------------
# Kerzenmuster - nur an Levels
# ---------------------------------------------------------------------------

def _candle_geometry(row: pd.Series) -> dict[str, float]:
    body = abs(float(row["close"]) - float(row["open"]))
    span = float(row["high"]) - float(row["low"])
    upper = float(row["high"]) - max(float(row["close"]), float(row["open"]))
    lower = min(float(row["close"]), float(row["open"])) - float(row["low"])
    return {"body": body, "span": span, "upper_wick": upper, "lower_wick": lower}


def detect_candle_patterns_at_levels(
    df: pd.DataFrame,
    levels: list[Level],
    instrument: Instrument,
    *,
    atr_value: float | None = None,
    max_distance_atr: float = 0.35,
) -> list[Pattern]:
    """Engulfing und Pin Bar - aber nur in unmittelbarer Naehe eines Levels.

    Ein isoliertes Kerzenmuster ist statistisch nahezu wertlos; erst der
    Ort macht es interessant. Alles hier Gemeldete traegt deshalb
    ``weak_signal=True`` - es ist ein Zusatzargument, kein Ausloeser.
    """
    if len(df) < 2 or not atr_value or atr_value <= 0:
        return []

    last, previous = df.iloc[-1], df.iloc[-2]
    close = float(last["close"])

    nearby = [
        level for level in levels
        if abs(level.price - close) <= max_distance_atr * atr_value
    ]
    if not nearby:
        return []

    nearest = min(nearby, key=lambda level: abs(level.price - close))
    geometry = _candle_geometry(last)
    previous_geometry = _candle_geometry(previous)
    patterns: list[Pattern] = []

    level_context = {
        "level_name": nearest.name,
        "level_preis": round(nearest.price, 4),
        "abstand_punkte": round(close - nearest.price, 4),
        "abstand_atr": round((close - nearest.price) / atr_value, 2),
    }

    # --- Engulfing ---
    last_bullish = float(last["close"]) > float(last["open"])
    previous_bullish = float(previous["close"]) > float(previous["open"])
    engulfs = (
        geometry["body"] > previous_geometry["body"]
        and min(float(last["open"]), float(last["close"]))
        <= min(float(previous["open"]), float(previous["close"]))
        and max(float(last["open"]), float(last["close"]))
        >= max(float(previous["open"]), float(previous["close"]))
    )
    if engulfs and last_bullish != previous_bullish and previous_geometry["body"] > 0:
        body_ratio = geometry["body"] / previous_geometry["body"]
        patterns.append(
            Pattern(
                name="Engulfing",
                kind="candle",
                direction="bullish" if last_bullish else "bearish",
                confidence=_clamp(0.3 + 0.15 * (body_ratio - 1.0)),
                evidence={
                    **level_context,
                    "koerper_aktuell_punkte": round(geometry["body"], 4),
                    "koerper_vorkerze_punkte": round(previous_geometry["body"], 4),
                    "koerper_verhaeltnis": round(body_ratio, 2),
                },
                note="Kerzenmuster an einem Level - nur als Zusatzargument brauchbar.",
                weak_signal=True,
            )
        )

    # --- Pin Bar ---
    if geometry["span"] > 0 and geometry["body"] > 0:
        upper_ratio = geometry["upper_wick"] / geometry["body"]
        lower_ratio = geometry["lower_wick"] / geometry["body"]

        if lower_ratio >= 2.0 and geometry["lower_wick"] / geometry["span"] >= 0.5:
            patterns.append(
                Pattern(
                    name="Pin Bar (langer Docht unten)",
                    kind="candle",
                    direction="bullish",
                    confidence=_clamp(0.25 + 0.1 * (lower_ratio - 2.0)),
                    evidence={
                        **level_context,
                        "docht_unten_punkte": round(geometry["lower_wick"], 4),
                        "koerper_punkte": round(geometry["body"], 4),
                        "verhaeltnis_docht_zu_koerper": round(lower_ratio, 2),
                    },
                    note="Kerzenmuster an einem Level - nur als Zusatzargument brauchbar.",
                    weak_signal=True,
                )
            )
        elif upper_ratio >= 2.0 and geometry["upper_wick"] / geometry["span"] >= 0.5:
            patterns.append(
                Pattern(
                    name="Pin Bar (langer Docht oben)",
                    kind="candle",
                    direction="bearish",
                    confidence=_clamp(0.25 + 0.1 * (upper_ratio - 2.0)),
                    evidence={
                        **level_context,
                        "docht_oben_punkte": round(geometry["upper_wick"], 4),
                        "koerper_punkte": round(geometry["body"], 4),
                        "verhaeltnis_docht_zu_koerper": round(upper_ratio, 2),
                    },
                    note="Kerzenmuster an einem Level - nur als Zusatzargument brauchbar.",
                    weak_signal=True,
                )
            )

    return patterns


# ---------------------------------------------------------------------------
# Sammelaufruf
# ---------------------------------------------------------------------------

def detect_all_patterns(
    df: pd.DataFrame,
    *,
    instrument: Instrument,
    levels: list[Level] | None = None,
    atr_value: float | None = None,
    strength: int = 3,
    lookback: int = 120,
) -> list[Pattern]:
    """Alle Detektoren in einem Durchlauf, nach Konfidenz sortiert."""
    if atr_value is None and "atr" in df.columns and not _is_nan(df["atr"].iloc[-1]):
        atr_value = float(df["atr"].iloc[-1])

    found: list[Pattern] = []
    for pattern in (
        detect_flag(df),
        detect_triangle(df, strength=strength, lookback=lookback, atr_value=atr_value),
        detect_double_top_bottom(df, strength=strength, lookback=lookback, atr_value=atr_value),
        detect_range_compression(df, atr_value=atr_value),
    ):
        if pattern is not None:
            found.append(pattern)

    if levels:
        found.extend(
            detect_candle_patterns_at_levels(
                df, levels, instrument, atr_value=atr_value
            )
        )

    return sorted(found, key=lambda item: item.confidence, reverse=True)


__all__ = [
    "Pattern",
    "detect_all_patterns",
    "detect_candle_patterns_at_levels",
    "detect_double_top_bottom",
    "detect_flag",
    "detect_range_compression",
    "detect_triangle",
]
