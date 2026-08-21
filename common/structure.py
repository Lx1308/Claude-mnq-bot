"""Marktstruktur: Swing-Punkte, Unterstuetzungs-/Widerstandszonen, Trend.

Bewusst getrennt von :mod:`common.indicators`:

* ``compute_indicators`` laeuft bei JEDER geschlossenen Kerze und bei jeder
  einzelnen Backtest-Kerze. Was dort hineinwandert, kostet in einem
  Backtest ueber 300.000 Bars sofort spuerbar Zeit.
* Die Funktionen hier werden punktuell aufgerufen - beim On-Demand-Bericht
  einmal pro Anfrage. Sie arbeiten auf demselben DataFrame-Schema und sind
  damit fuer Strategien jederzeit nachnutzbar.

Alle Funktionen sind rein rueckwaertsgerichtet: sie schauen ausschliesslich
auf abgeschlossene Kerzen bis zum uebergebenen Ende.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import pandas as pd

from common.indicators import validate_ohlcv

SwingKind = Literal["high", "low"]
ZoneKind = Literal["support", "resistance"]


# ---------------------------------------------------------------------------
# Swing-Punkte
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SwingPoint:
    """Ein lokales Extrem im Kursverlauf."""

    timestamp: datetime
    price: float
    kind: SwingKind
    bars_ago: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "zeitpunkt": self.timestamp.isoformat(),
            "preis": round(self.price, 2),
            "art": "Hoch" if self.kind == "high" else "Tief",
            "kerzen_her": self.bars_ago,
        }


def find_swing_points(
    df: pd.DataFrame,
    *,
    strength: int = 3,
    lookback: int | None = None,
) -> list[SwingPoint]:
    """Findet lokale Hoch- und Tiefpunkte (Fraktale).

    Eine Kerze gilt als Swing-Hoch, wenn ihr High das hoechste im Fenster
    ``[i-strength, i+strength]`` ist. Die letzten ``strength`` Kerzen koennen
    per Definition noch kein bestaetigtes Extrem sein - ob sie eines werden,
    entscheidet sich erst in der Zukunft. Genau deshalb werden sie hier
    ausgelassen statt geraten.

    ``strength`` steuert die Empfindlichkeit: kleine Werte liefern viele
    kleine Zwischenhochs, grosse Werte nur die markanten Wendepunkte.
    """
    validate_ohlcv(df)
    if strength < 1:
        raise ValueError("strength muss mindestens 1 sein.")

    window = df if lookback is None else df.iloc[-lookback:]
    if len(window) < 2 * strength + 1:
        return []

    highs = window["high"].to_numpy(dtype=float)
    lows = window["low"].to_numpy(dtype=float)
    timestamps = window.index
    last_index = len(window) - 1

    points: list[SwingPoint] = []
    for i in range(strength, len(window) - strength):
        left = slice(i - strength, i)
        right = slice(i + 1, i + strength + 1)

        # Streng groesser nach links, groesser-gleich nach rechts: bei
        # Plateaus wird so genau ein Punkt gemeldet statt mehrerer.
        if highs[i] > highs[left].max() and highs[i] >= highs[right].max():
            points.append(
                SwingPoint(
                    timestamp=timestamps[i].to_pydatetime(),
                    price=float(highs[i]),
                    kind="high",
                    bars_ago=last_index - i,
                )
            )
        if lows[i] < lows[left].min() and lows[i] <= lows[right].min():
            points.append(
                SwingPoint(
                    timestamp=timestamps[i].to_pydatetime(),
                    price=float(lows[i]),
                    kind="low",
                    bars_ago=last_index - i,
                )
            )

    points.sort(key=lambda point: point.bars_ago)
    return points


# ---------------------------------------------------------------------------
# Unterstuetzungs- / Widerstandszonen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Zone:
    """Eine Preiszone, die mehrfach als Wendepunkt gedient hat."""

    kind: ZoneKind
    price: float
    lower: float
    upper: float
    touches: int
    bars_since_last_touch: int
    distance_points: float
    distance_atr: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preis": round(self.price, 2),
            "von": round(self.lower, 2),
            "bis": round(self.upper, 2),
            "beruehrungen": self.touches,
            "kerzen_seit_letzter_beruehrung": self.bars_since_last_touch,
            "abstand_punkte": round(self.distance_points, 2),
            "abstand_in_atr": round(self.distance_atr, 2) if self.distance_atr is not None else None,
        }


def support_resistance_zones(
    df: pd.DataFrame,
    *,
    atr_value: float | None,
    strength: int = 3,
    lookback: int = 120,
    max_zones: int = 3,
    merge_atr: float = 0.5,
) -> tuple[list[Zone], list[Zone]]:
    """Leitet die naechstgelegenen Zonen aus den juengsten Swing-Punkten ab.

    Rueckgabe: ``(unterstuetzungen, widerstaende)``, jeweils nach Abstand zum
    aktuellen Kurs sortiert (naechste zuerst).

    Die Einordnung erfolgt bewusst ueber die **Lage zum aktuellen Kurs**, nicht
    ueber die Art des Swings: ein durchbrochenes Swing-Hoch unterhalb des
    Kurses wirkt in der Praxis als Unterstuetzung, nicht mehr als Widerstand.

    Punkte, die naeher als ``merge_atr * ATR`` beieinanderliegen, werden zu
    einer Zone zusammengefasst. Mehrfachberuehrungen sind damit sichtbar -
    eine dreimal getestete Marke ist etwas anderes als ein einmaliges Extrem.
    """
    points = find_swing_points(df, strength=strength, lookback=lookback)
    if not points:
        return [], []

    current_price = float(df["close"].iloc[-1])
    # Ohne belastbaren ATR auf eine Toleranz relativ zum Kurs ausweichen.
    tolerance = (
        merge_atr * atr_value
        if atr_value is not None and atr_value > 0
        else abs(current_price) * 0.0005
    )

    below = [point for point in points if point.price < current_price]
    above = [point for point in points if point.price > current_price]

    supports = _cluster(below, tolerance, "support", current_price, atr_value)
    resistances = _cluster(above, tolerance, "resistance", current_price, atr_value)

    supports.sort(key=lambda zone: zone.distance_points)
    resistances.sort(key=lambda zone: zone.distance_points)
    return supports[:max_zones], resistances[:max_zones]


def _cluster(
    points: list[SwingPoint],
    tolerance: float,
    kind: ZoneKind,
    current_price: float,
    atr_value: float | None,
) -> list[Zone]:
    """Fasst nahe beieinanderliegende Swing-Punkte zu Zonen zusammen."""
    if not points:
        return []

    ordered = sorted(points, key=lambda point: point.price)
    clusters: list[list[SwingPoint]] = [[ordered[0]]]
    for point in ordered[1:]:
        if abs(point.price - clusters[-1][-1].price) <= tolerance:
            clusters[-1].append(point)
        else:
            clusters.append([point])

    zones: list[Zone] = []
    for cluster in clusters:
        prices = [point.price for point in cluster]
        centre = sum(prices) / len(prices)
        distance = abs(centre - current_price)
        zones.append(
            Zone(
                kind=kind,
                price=centre,
                lower=min(prices),
                upper=max(prices),
                touches=len(cluster),
                bars_since_last_touch=min(point.bars_ago for point in cluster),
                distance_points=distance,
                distance_atr=(
                    distance / atr_value if atr_value is not None and atr_value > 0 else None
                ),
            )
        )
    return zones


# ---------------------------------------------------------------------------
# Trend-Einschaetzung
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TrendAssessment:
    """Grobe Trendlage aus SMA-Position und SMA-Steigung."""

    direction: Literal["aufwaerts", "abwaerts", "seitwaerts", "unklar"]
    above_sma_slow: bool | None
    sma_fast_slope_per_bar: float | None
    sma_fast_slope_in_atr: float | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "richtung": self.direction,
            "ueber_sma50": self.above_sma_slow,
            "sma20_steigung_pro_kerze": (
                round(self.sma_fast_slope_per_bar, 4)
                if self.sma_fast_slope_per_bar is not None
                else None
            ),
            "sma20_steigung_in_atr_pro_kerze": (
                round(self.sma_fast_slope_in_atr, 4)
                if self.sma_fast_slope_in_atr is not None
                else None
            ),
            "beschreibung": self.description,
        }


def assess_trend(
    df: pd.DataFrame,
    *,
    atr_value: float | None,
    slope_lookback: int = 10,
    flat_threshold_atr: float = 0.02,
) -> TrendAssessment:
    """Trend aus Lage zur SMA(50) und Steigung der SMA(20).

    Die Steigung wird in ATR pro Kerze normiert - sonst waere ein Schwellwert
    fuer NQ (Punkte im Zehnerbereich) und ES (Punkte im Einerbereich) nicht
    derselbe. ``flat_threshold_atr`` ist die Grenze, unterhalb derer die
    Steigung als flach gilt.

    Erwartet die Spalten ``sma_fast``, ``sma_slow`` aus
    :func:`common.indicators.compute_indicators`.
    """
    if "sma_fast" not in df.columns or "sma_slow" not in df.columns:
        raise ValueError(
            "assess_trend erwartet ein bereits mit compute_indicators angereichertes DataFrame."
        )

    close = float(df["close"].iloc[-1])
    sma_fast = df["sma_fast"]
    sma_slow_value = df["sma_slow"].iloc[-1]

    above_slow: bool | None = None
    if sma_slow_value is not None and not _is_nan(sma_slow_value):
        above_slow = close > float(sma_slow_value)

    slope: float | None = None
    if len(sma_fast) > slope_lookback:
        recent = sma_fast.iloc[-1]
        earlier = sma_fast.iloc[-1 - slope_lookback]
        if not _is_nan(recent) and not _is_nan(earlier):
            slope = (float(recent) - float(earlier)) / slope_lookback

    slope_atr: float | None = None
    if slope is not None and atr_value is not None and atr_value > 0:
        slope_atr = slope / atr_value

    if above_slow is None or slope_atr is None:
        return TrendAssessment(
            direction="unklar",
            above_sma_slow=above_slow,
            sma_fast_slope_per_bar=slope,
            sma_fast_slope_in_atr=slope_atr,
            description="Zu wenige Kerzen fuer eine belastbare Trendaussage.",
        )

    rising = slope_atr > flat_threshold_atr
    falling = slope_atr < -flat_threshold_atr

    if above_slow and rising:
        direction = "aufwaerts"
        description = "Kurs ueber SMA50, SMA20 steigend - Aufwaertsstruktur."
    elif not above_slow and falling:
        direction = "abwaerts"
        description = "Kurs unter SMA50, SMA20 fallend - Abwaertsstruktur."
    elif not rising and not falling:
        direction = "seitwaerts"
        description = (
            "SMA20 nahezu flach - Seitwaertsphase, Ausbruchsrichtung offen."
        )
    else:
        direction = "seitwaerts"
        side = "ueber" if above_slow else "unter"
        moving = "steigend" if rising else "fallend"
        description = (
            f"Gemischtes Bild: Kurs {side} SMA50, SMA20 aber {moving} - "
            "moegliche Trendwende oder Korrektur im uebergeordneten Trend."
        )

    return TrendAssessment(
        direction=direction,
        above_sma_slow=above_slow,
        sma_fast_slope_per_bar=slope,
        sma_fast_slope_in_atr=slope_atr,
        description=description,
    )


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


# ---------------------------------------------------------------------------
# Marktstruktur: HH/HL vs. LH/LL, Break of Structure, Change of Character
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabelledSwing:
    """Ein Swing mit seiner Einordnung relativ zum vorherigen gleicher Art."""

    timestamp: datetime
    price: float
    kind: SwingKind
    label: str          # "HH" | "LH" | "HL" | "LL" | "first"
    bars_ago: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "zeitpunkt": self.timestamp.isoformat(),
            "preis": round(self.price, 4),
            "art": "Hoch" if self.kind == "high" else "Tief",
            "label": self.label,
            "kerzen_her": self.bars_ago,
        }


@dataclass(frozen=True)
class MarketStructure:
    """Strukturelle Einordnung des Kursverlaufs."""

    trend: Literal["uptrend", "downtrend", "range_expanding", "range_contracting", "unklar"]
    labelled_swings: list[LabelledSwing]
    last_swing_high: float | None
    last_swing_low: float | None
    break_of_structure: bool
    bos_direction: Literal["up", "down"] | None
    bos_level: float | None
    change_of_character: bool
    choch_direction: Literal["up", "down"] | None
    choch_level: float | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trend": self.trend,
            "letzte_swings": [swing.to_dict() for swing in self.labelled_swings],
            "letztes_swing_hoch": round(self.last_swing_high, 4) if self.last_swing_high else None,
            "letztes_swing_tief": round(self.last_swing_low, 4) if self.last_swing_low else None,
            "break_of_structure": {
                "erkannt": self.break_of_structure,
                "richtung": self.bos_direction,
                "niveau": round(self.bos_level, 4) if self.bos_level else None,
            },
            "change_of_character": {
                "erkannt": self.change_of_character,
                "richtung": self.choch_direction,
                "niveau": round(self.choch_level, 4) if self.choch_level else None,
            },
            "beschreibung": self.description,
        }


def _label_swings(swings: list[SwingPoint]) -> list[LabelledSwing]:
    """Vergibt HH/LH/HL/LL durch Vergleich mit dem vorherigen Swing gleicher Art."""
    chronological = sorted(swings, key=lambda point: point.bars_ago, reverse=True)

    labelled: list[LabelledSwing] = []
    last_high: float | None = None
    last_low: float | None = None

    for point in chronological:
        if point.kind == "high":
            if last_high is None:
                label = "first"
            else:
                label = "HH" if point.price > last_high else "LH"
            last_high = point.price
        else:
            if last_low is None:
                label = "first"
            else:
                label = "HL" if point.price > last_low else "LL"
            last_low = point.price

        labelled.append(
            LabelledSwing(
                timestamp=point.timestamp,
                price=point.price,
                kind=point.kind,
                label=label,
                bars_ago=point.bars_ago,
            )
        )
    return labelled


def classify_market_structure(
    df: pd.DataFrame,
    *,
    strength: int = 3,
    lookback: int = 120,
    max_swings: int = 8,
) -> MarketStructure:
    """Leitet Trendstruktur, Break of Structure und CHoCH aus den Swings ab.

    Abgrenzung der beiden Ereignisse - sie werden haeufig verwechselt:

    * **Break of Structure (BOS)** ist eine *Fortsetzung*: im Aufwaertstrend
      wird das letzte Swing-Hoch ueberschritten.
    * **Change of Character (CHoCH)** ist der erste Bruch *gegen* die
      laufende Struktur: im Aufwaertstrend faellt der Kurs unter das letzte
      hoehere Tief. Das ist das fruehere und riskantere Signal.

    Ohne erkennbaren Trend gibt es per Definition kein CHoCH - nur einen
    Range-Ausbruch, der hier als BOS mit entsprechendem Hinweis gemeldet wird.
    """
    swings = find_swing_points(df, strength=strength, lookback=lookback)
    if len(swings) < 2:
        return MarketStructure(
            trend="unklar",
            labelled_swings=[],
            last_swing_high=None,
            last_swing_low=None,
            break_of_structure=False,
            bos_direction=None,
            bos_level=None,
            change_of_character=False,
            choch_direction=None,
            choch_level=None,
            description="Zu wenige bestaetigte Swings fuer eine Strukturaussage.",
        )

    labelled = _label_swings(swings)
    recent = labelled[-max_swings:]

    highs = [swing for swing in labelled if swing.kind == "high"]
    lows = [swing for swing in labelled if swing.kind == "low"]
    last_high = highs[-1].price if highs else None
    last_low = lows[-1].price if lows else None

    high_label = highs[-1].label if highs else "first"
    low_label = lows[-1].label if lows else "first"

    if high_label == "HH" and low_label == "HL":
        trend = "uptrend"
        description = "Hoehere Hochs und hoehere Tiefs - intakte Aufwaertsstruktur."
    elif high_label == "LH" and low_label == "LL":
        trend = "downtrend"
        description = "Tiefere Hochs und tiefere Tiefs - intakte Abwaertsstruktur."
    elif high_label == "HH" and low_label == "LL":
        trend = "range_expanding"
        description = "Hoehere Hochs bei tieferen Tiefs - sich weitende Spanne."
    elif high_label == "LH" and low_label == "HL":
        trend = "range_contracting"
        description = "Tiefere Hochs bei hoeheren Tiefs - Kompression, Ausbruch offen."
    else:
        trend = "unklar"
        description = "Struktur noch nicht eindeutig (zu wenige Vergleichspunkte)."

    close = float(df["close"].iloc[-1])

    bos = False
    bos_direction: str | None = None
    bos_level: float | None = None
    choch = False
    choch_direction: str | None = None
    choch_level: float | None = None

    broke_high = last_high is not None and close > last_high
    broke_low = last_low is not None and close < last_low

    if trend == "uptrend":
        if broke_high:
            bos, bos_direction, bos_level = True, "up", last_high
            description += " Letztes Swing-Hoch ueberschritten (BOS)."
        elif broke_low:
            choch, choch_direction, choch_level = True, "down", last_low
            description += " Letztes hoeheres Tief unterschritten (CHoCH)."
    elif trend == "downtrend":
        if broke_low:
            bos, bos_direction, bos_level = True, "down", last_low
            description += " Letztes Swing-Tief unterschritten (BOS)."
        elif broke_high:
            choch, choch_direction, choch_level = True, "up", last_high
            description += " Letztes tieferes Hoch ueberschritten (CHoCH)."
    else:
        if broke_high:
            bos, bos_direction, bos_level = True, "up", last_high
            description += " Ausbruch ueber das letzte Swing-Hoch (Range-Ausbruch, kein Trend-BOS)."
        elif broke_low:
            bos, bos_direction, bos_level = True, "down", last_low
            description += " Ausbruch unter das letzte Swing-Tief (Range-Ausbruch, kein Trend-BOS)."

    return MarketStructure(
        trend=trend,
        labelled_swings=recent,
        last_swing_high=last_high,
        last_swing_low=last_low,
        break_of_structure=bos,
        bos_direction=bos_direction,
        bos_level=bos_level,
        change_of_character=choch,
        choch_direction=choch_direction,
        choch_level=choch_level,
        description=description,
    )


# ---------------------------------------------------------------------------
# RSI-Divergenz
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RsiDivergence:
    """Divergenz zwischen Kursverlauf und RSI an den letzten Swings."""

    detected: bool
    kind: Literal["bullish", "bearish"] | None
    price_first: float | None
    price_second: float | None
    rsi_first: float | None
    rsi_second: float | None
    bars_between: int | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "erkannt": self.detected,
            "art": self.kind,
            "kurs_erster_swing": round(self.price_first, 4) if self.price_first else None,
            "kurs_zweiter_swing": round(self.price_second, 4) if self.price_second else None,
            "rsi_erster_swing": round(self.rsi_first, 1) if self.rsi_first is not None else None,
            "rsi_zweiter_swing": round(self.rsi_second, 1) if self.rsi_second is not None else None,
            "kerzen_zwischen_swings": self.bars_between,
            "beschreibung": self.description,
        }


def detect_rsi_divergence(
    df: pd.DataFrame,
    *,
    strength: int = 3,
    lookback: int = 120,
    rsi_column: str = "rsi",
    min_rsi_gap: float = 2.0,
) -> RsiDivergence:
    """Vergleicht die letzten beiden gleichartigen Swings mit dem RSI.

    * **Baerische Divergenz**: Kurs macht ein hoeheres Hoch, der RSI nicht.
    * **Bullische Divergenz**: Kurs macht ein tieferes Tief, der RSI nicht.

    ``min_rsi_gap`` verhindert, dass Rundungsrauschen im RSI als Divergenz
    durchgeht. Eine Divergenz ist ein Hinweis auf nachlassende Dynamik,
    kein Umkehrsignal - entsprechend wird sie hier auch nur beschrieben.
    """
    if rsi_column not in df.columns:
        raise ValueError(
            f"detect_rsi_divergence erwartet die Spalte {rsi_column!r} "
            "(compute_indicators aufrufen)."
        )

    swings = find_swing_points(df, strength=strength, lookback=lookback)
    rsi_series = df[rsi_column]

    def rsi_at(timestamp: datetime) -> float | None:
        try:
            value = rsi_series.loc[pd.Timestamp(timestamp)]
        except KeyError:
            return None
        return None if _is_nan(value) else float(value)

    for kind, comparator in (("high", "bearish"), ("low", "bullish")):
        same_kind = sorted(
            [swing for swing in swings if swing.kind == kind],
            key=lambda point: point.bars_ago,
        )
        if len(same_kind) < 2:
            continue

        second, first = same_kind[0], same_kind[1]   # neuester, davorliegender
        rsi_first, rsi_second = rsi_at(first.timestamp), rsi_at(second.timestamp)
        if rsi_first is None or rsi_second is None:
            continue

        price_diverges = (
            second.price > first.price if kind == "high" else second.price < first.price
        )
        rsi_diverges = (
            rsi_second < rsi_first - min_rsi_gap
            if kind == "high"
            else rsi_second > rsi_first + min_rsi_gap
        )

        if price_diverges and rsi_diverges:
            richtung = "hoeheres Hoch" if kind == "high" else "tieferes Tief"
            return RsiDivergence(
                detected=True,
                kind=comparator,
                price_first=first.price,
                price_second=second.price,
                rsi_first=rsi_first,
                rsi_second=rsi_second,
                bars_between=first.bars_ago - second.bars_ago,
                description=(
                    f"{comparator.capitalize()}e Divergenz: Kurs bildet ein {richtung} "
                    f"({first.price:.2f} -> {second.price:.2f}), der RSI folgt nicht "
                    f"({rsi_first:.1f} -> {rsi_second:.1f}). Hinweis auf nachlassende "
                    "Dynamik, kein Umkehrsignal."
                ),
            )

    return RsiDivergence(
        detected=False,
        kind=None,
        price_first=None,
        price_second=None,
        rsi_first=None,
        rsi_second=None,
        bars_between=None,
        description="Keine Divergenz an den letzten Swings.",
    )


__all__ = [
    "LabelledSwing",
    "MarketStructure",
    "RsiDivergence",
    "SwingPoint",
    "TrendAssessment",
    "Zone",
    "assess_trend",
    "classify_market_structure",
    "detect_rsi_divergence",
    "find_swing_points",
    "support_resistance_zones",
]
