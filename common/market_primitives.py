"""Kanonische Marktprimitive fuer quantitative Research- und Analyse-Pipelines.

Jedes Primitiv besitzt:
1. Eine exakte mathematische Definition ohne subjektive Begriffe.
2. Klare Trennung der Zeitstempel:
   - ``event_time``: Wann die Preisaktion physisch stattfand.
   - ``confirmation_time``: Wann die Bedingung mathematisch bestaetigt war.
   - ``availability_time``: Wann die Information fruehestens fuer ein
     deterministisches Signal / einen Backtest verfuegbar war (i.d.R. Kerzenschluss).
3. Vollstaendige quantitative Attribute (Punkte, Ticks, ATR-Vielfache, Verhaeltnisse).
4. Striktes Lookahead-Schutzverhalten.

Unterstuetzte Primitive:
- Fair Value Gap (FVG) / Imbalance (Bullisch / Baerisch, Mitigation, Rebalancing)
- Displacement (Impuls-Kerzen mit Koerper-/ATR-Dominanz und Volumen)
- Equal Highs (EQH) / Equal Lows (EQL) / Liquidity Pools
- Liquidity Sweeps (BSL / SSL) & Stop-Run / Reclaim-Events
- Market Structure Shift (MSS) vs. Break of Structure (BOS) vs. Change of Character (CHoCH)
- Geometrische Pattern-Messungen (W / M, V-Reversal, Kompression / Expansion)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Sequence

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv
from common.levels import Level, LevelSet
from common.structure import SwingPoint, find_swing_points

Direction = Literal["bullish", "bearish"]
StructureBreakType = Literal["BOS", "CHoCH", "MSS"]


def _clean_float(val: Any) -> float:
    try:
        f = float(val)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return 0.0


# ===========================================================================
# 1. Fair Value Gap (FVG) / Imbalance
# ===========================================================================

@dataclass(frozen=True)
class FairValueGap:
    """Ein 3-Kerzen Fair Value Gap (Imbalance).

    Mathematische Definition:
    - Bullish FVG: Low[i] > High[i-2]. Ungedeckte Spanne: [High[i-2], Low[i]].
    - Bearish FVG: High[i] < Low[i-2]. Ungedeckte Spanne: [High[i], Low[i-2]].
    """

    kind: Direction
    top: float
    bottom: float
    size_points: float
    size_ticks: float
    size_atr: float | None

    # Zeitstempel
    event_time: datetime         # Zeitpunkt der Impulskerze (i-1)
    confirmation_time: datetime  # Schlusszeitpunkt der 3. Kerze (i)
    availability_time: datetime  # Fruehestens bekannt (Schluss i / Open i+1)
    bar_index: int               # Index der Bestaetigungskerze

    # Mitigation / Rebalancing
    is_mitigated: bool = False
    mitigation_time: datetime | None = None
    fill_ratio: float = 0.0      # 0.0 (unberuehrt) bis 1.0 (vollstaendig gefuellt)

    @property
    def midpoint(self) -> float:
        """Consequent Encroachment (50%-Niveau des FVG)."""
        return (self.top + self.bottom) / 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "art": self.kind,
            "top": round(self.top, 4),
            "bottom": round(self.bottom, 4),
            "mittelpunkt_ce": round(self.midpoint, 4),
            "spanne_punkte": round(self.size_points, 4),
            "spanne_ticks": round(self.size_ticks, 1),
            "spanne_in_atr": round(self.size_atr, 2) if self.size_atr is not None else None,
            "event_zeit_utc": self.event_time.isoformat(),
            "bestaetigt_am_utc": self.confirmation_time.isoformat(),
            "verfuegbar_ab_utc": self.availability_time.isoformat(),
            "mitigiert": self.is_mitigated,
            "mitigation_zeit_utc": self.mitigation_time.isoformat() if self.mitigation_time else None,
            "fuellgrad": round(self.fill_ratio, 2),
        }


def detect_fair_value_gaps(
    df: pd.DataFrame,
    *,
    tick_size: float = 0.25,
    min_gap_ticks: float = 1.0,
    min_gap_atr: float = 0.0,
    atr_series: pd.Series | None = None,
) -> list[FairValueGap]:
    """Erkennt alle FVGs in einem OHLCV-DataFrame und verfolgt deren Mitigation.

    Lookahead-Schutz:
    Jedes FVG wird erst bei Kerze i bestaetigt und darf fruehestens ab Kerze i+1
    gehandelt werden.
    """
    validate_ohlcv(df)
    if len(df) < 3:
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    timestamps = df.index

    atrs = None
    if atr_series is not None:
        atrs = atr_series.to_numpy(dtype=float)
    elif "atr" in df.columns:
        atrs = df["atr"].to_numpy(dtype=float)

    gaps: list[FairValueGap] = []
    n = len(df)

    for i in range(2, n):
        c0_high = highs[i - 2]
        c0_low = lows[i - 2]
        c1_time = timestamps[i - 1].to_pydatetime()
        c2_high = highs[i]
        c2_low = lows[i]
        c2_time = timestamps[i].to_pydatetime()

        current_atr = float(atrs[i]) if (atrs is not None and not math.isnan(atrs[i])) else None

        # Bullish FVG: Low[i] > High[i-2]
        if c2_low > c0_high:
            gap_size = c2_low - c0_high
            gap_ticks = gap_size / tick_size
            gap_atr = (gap_size / current_atr) if (current_atr and current_atr > 0) else None

            if gap_ticks >= min_gap_ticks and (gap_atr is None or gap_atr >= min_gap_atr):
                # Mitigation in Folgekerzen pruefen
                is_mit = False
                mit_time = None
                max_penetration = 0.0

                for j in range(i + 1, n):
                    pen = c2_low - lows[j]
                    if pen > 0:
                        max_penetration = max(max_penetration, pen)
                        if not is_mit and lows[j] <= c0_high + (gap_size * 0.5):
                            is_mit = True
                            mit_time = timestamps[j].to_pydatetime()

                fill_ratio = min(1.0, max(0.0, max_penetration / gap_size)) if gap_size > 0 else 1.0

                gaps.append(
                    FairValueGap(
                        kind="bullish",
                        top=float(c2_low),
                        bottom=float(c0_high),
                        size_points=float(gap_size),
                        size_ticks=float(gap_ticks),
                        size_atr=gap_atr,
                        event_time=c1_time,
                        confirmation_time=c2_time,
                        availability_time=c2_time,
                        bar_index=i,
                        is_mitigated=is_mit,
                        mitigation_time=mit_time,
                        fill_ratio=fill_ratio,
                    )
                )

        # Bearish FVG: High[i] < Low[i-2]
        elif c2_high < c0_low:
            gap_size = c0_low - c2_high
            gap_ticks = gap_size / tick_size
            gap_atr = (gap_size / current_atr) if (current_atr and current_atr > 0) else None

            if gap_ticks >= min_gap_ticks and (gap_atr is None or gap_atr >= min_gap_atr):
                is_mit = False
                mit_time = None
                max_penetration = 0.0

                for j in range(i + 1, n):
                    pen = highs[j] - c2_high
                    if pen > 0:
                        max_penetration = max(max_penetration, pen)
                        if not is_mit and highs[j] >= c2_high + (gap_size * 0.5):
                            is_mit = True
                            mit_time = timestamps[j].to_pydatetime()

                fill_ratio = min(1.0, max(0.0, max_penetration / gap_size)) if gap_size > 0 else 1.0

                gaps.append(
                    FairValueGap(
                        kind="bearish",
                        top=float(c0_low),
                        bottom=float(c2_high),
                        size_points=float(gap_size),
                        size_ticks=float(gap_ticks),
                        size_atr=gap_atr,
                        event_time=c1_time,
                        confirmation_time=c2_time,
                        availability_time=c2_time,
                        bar_index=i,
                        is_mitigated=is_mit,
                        mitigation_time=mit_time,
                        fill_ratio=fill_ratio,
                    )
                )

    return gaps


# ===========================================================================
# 2. Displacement (Impuls-Kerze mit Volumen- und Koerper-Dominanz)
# ===========================================================================

@dataclass(frozen=True)
class Displacement:
    """Eine Displacement-Kerze (starker institutioneller Impuls).

    Mathematische Kriterien:
    1. Koerpergroesse abs(Close - Open) >= min_body_atr * ATR
    2. Body-to-Range-Ratio abs(Close - Open) / (High - Low) >= min_body_ratio (z.B. 0.60)
    3. Volumen >= min_volume_ratio * Rolling-Volume (optional)
    """

    direction: Direction
    bar_time: datetime
    confirmation_time: datetime
    availability_time: datetime
    bar_index: int

    body_points: float
    range_points: float
    body_ratio: float
    body_atr: float | None
    volume: float
    relative_volume: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "richtung": self.direction,
            "zeitpunkt_utc": self.bar_time.isoformat(),
            "bestaetigt_am_utc": self.confirmation_time.isoformat(),
            "verfuegbar_ab_utc": self.availability_time.isoformat(),
            "koerper_punkte": round(self.body_points, 4),
            "spanne_punkte": round(self.range_points, 4),
            "koerper_anteil": round(self.body_ratio, 2),
            "koerper_in_atr": round(self.body_atr, 2) if self.body_atr is not None else None,
            "relatives_volumen": round(self.relative_volume, 2) if self.relative_volume is not None else None,
        }


def detect_displacements(
    df: pd.DataFrame,
    *,
    min_body_atr: float = 1.0,
    min_body_ratio: float = 0.60,
    min_volume_ratio: float = 1.0,
    atr_series: pd.Series | None = None,
    volume_window: int = 20,
) -> list[Displacement]:
    """Erkennt Displacement-Bars."""
    validate_ohlcv(df)
    if len(df) < 2:
        return []

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    volumes = df["volume"].to_numpy(dtype=float)
    timestamps = df.index

    atrs = None
    if atr_series is not None:
        atrs = atr_series.to_numpy(dtype=float)
    elif "atr" in df.columns:
        atrs = df["atr"].to_numpy(dtype=float)

    # Rolling Mean Volume fuer Relativvolumen
    vol_series = pd.Series(volumes, index=timestamps)
    mean_vols = vol_series.rolling(volume_window, min_periods=1).mean().to_numpy(dtype=float)

    displacements: list[Displacement] = []

    for i in range(len(df)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        body = abs(c - o)
        tot_range = h - l

        if tot_range <= 0.0:
            continue

        body_ratio = body / tot_range
        if body_ratio < min_body_ratio:
            continue

        current_atr = float(atrs[i]) if (atrs is not None and not math.isnan(atrs[i])) else None
        body_atr = (body / current_atr) if (current_atr and current_atr > 0) else None

        if body_atr is not None and body_atr < min_body_atr:
            continue

        m_vol = mean_vols[i]
        rel_vol = (volumes[i] / m_vol) if (m_vol > 0) else 1.0
        if rel_vol < min_volume_ratio:
            continue

        direction: Direction = "bullish" if c > o else "bearish"
        t = timestamps[i].to_pydatetime()

        displacements.append(
            Displacement(
                direction=direction,
                bar_time=t,
                confirmation_time=t,
                availability_time=t,
                bar_index=i,
                body_points=float(body),
                range_points=float(tot_range),
                body_ratio=float(body_ratio),
                body_atr=body_atr,
                volume=float(volumes[i]),
                relative_volume=float(rel_vol),
            )
        )

    return displacements


# ===========================================================================
# 3. Equal Highs (EQH) / Equal Lows (EQL) / Liquidity Pools
# ===========================================================================

@dataclass(frozen=True)
class EqualLevel:
    """Zwei oder mehr Swings auf nahezu identischem Niveau (Liquiditaetspool)."""

    kind: Literal["high", "low"]  # EQH = "high", EQL = "low"
    price_level: float
    swings: list[SwingPoint]
    tolerance_points: float
    tolerance_ticks: float
    tolerance_atr: float | None

    event_time: datetime          # Zeitpunkt des juengsten beteiligten Swings
    confirmation_time: datetime   # Bestaetigung des juengsten Swings
    availability_time: datetime

    is_swept: bool = False
    swept_time: datetime | None = None

    @property
    def swing_count(self) -> int:
        return len(self.swings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "art": "EQH" if self.kind == "high" else "EQL",
            "preisniveau": round(self.price_level, 4),
            "anzahl_swings": self.swing_count,
            "toleranz_punkte": round(self.tolerance_points, 4),
            "toleranz_ticks": round(self.tolerance_ticks, 1),
            "toleranz_in_atr": round(self.tolerance_atr, 2) if self.tolerance_atr is not None else None,
            "event_zeit_utc": self.event_time.isoformat(),
            "bestaetigt_am_utc": self.confirmation_time.isoformat(),
            "verfuegbar_ab_utc": self.availability_time.isoformat(),
            "wurde_gesweept": self.is_swept,
            "sweep_zeit_utc": self.swept_time.isoformat() if self.swept_time else None,
        }


def detect_equal_highs_lows(
    df: pd.DataFrame,
    *,
    swings: list[SwingPoint] | None = None,
    strength: int = 3,
    lookback: int = 120,
    tick_size: float = 0.25,
    tolerance_ticks: float = 4.0,
    tolerance_atr: float = 0.20,
    atr_value: float | None = None,
) -> tuple[list[EqualLevel], list[EqualLevel]]:
    """Findet EQH (Equal Highs) und EQL (Equal Lows) aus den Swing-Punkten."""
    validate_ohlcv(df)
    if swings is None:
        swings = find_swing_points(df, strength=strength, lookback=lookback)

    if not swings:
        return [], []

    high_swings = [s for s in swings if s.kind == "high"]
    low_swings = [s for s in swings if s.kind == "low"]

    current_price = float(df["close"].iloc[-1])
    if atr_value is None and "atr" in df.columns:
        atr_value = _clean_float(df["atr"].iloc[-1])

    tol_pts = max(
        tolerance_ticks * tick_size,
        (tolerance_atr * atr_value) if (atr_value and atr_value > 0) else 0.0,
    )

    timestamps = df.index
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)

    def _cluster_equal(pts: list[SwingPoint], kind: Literal["high", "low"]) -> list[EqualLevel]:
        if len(pts) < 2:
            return []
        # Sortiere chronologisch (aelteste zuerst)
        chrono = sorted(pts, key=lambda p: p.bars_ago, reverse=True)
        clusters: list[list[SwingPoint]] = []

        for p in chrono:
            assigned = False
            for c in clusters:
                avg_price = sum(x.price for x in c) / len(c)
                if abs(p.price - avg_price) <= tol_pts:
                    c.append(p)
                    assigned = True
                    break
            if not assigned:
                clusters.append([p])

        equal_levels: list[EqualLevel] = []
        for c in clusters:
            if len(c) < 2:
                continue
            avg_lvl = sum(x.price for x in c) / len(c)
            latest_swing = c[-1]

            # Bestaetigungszeitpunkt des juengsten Swings ist latest_swing.bars_ago - strength
            conf_idx = max(0, len(df) - 1 - latest_swing.bars_ago + strength)
            conf_idx = min(len(df) - 1, conf_idx)
            conf_time = timestamps[conf_idx].to_pydatetime()

            # Sweep-Pruefung nach dem Bestaetigungszeitpunkt
            swept = False
            swept_t = None
            for j in range(conf_idx, len(df)):
                if kind == "high" and highs[j] > avg_lvl:
                    swept = True
                    swept_t = timestamps[j].to_pydatetime()
                    break
                elif kind == "low" and lows[j] < avg_lvl:
                    swept = True
                    swept_t = timestamps[j].to_pydatetime()
                    break

            equal_levels.append(
                EqualLevel(
                    kind=kind,
                    price_level=avg_lvl,
                    swings=c,
                    tolerance_points=tol_pts,
                    tolerance_ticks=tol_pts / tick_size,
                    tolerance_atr=(tol_pts / atr_value) if (atr_value and atr_value > 0) else None,
                    event_time=latest_swing.timestamp,
                    confirmation_time=conf_time,
                    availability_time=conf_time,
                    is_swept=swept,
                    swept_time=swept_t,
                )
            )
        return equal_levels

    eq_highs = _cluster_equal(high_swings, "high")
    eq_lows = _cluster_equal(low_swings, "low")
    return eq_highs, eq_lows


# ===========================================================================
# 4. Liquidity Sweeps & Stop-Runs / Reclaims
# ===========================================================================

@dataclass(frozen=True)
class LiquiditySweep:
    """Ein Liquiditaets-Sweep (Buy-Side / Sell-Side) mit Reclaim-Verhalten.

    Definition:
    - BSL-Sweep (Baerisch): Kurs bricht ueber ein Niveau (High > Level),
      schliesst aber wieder darunter (Close < Level) oder reclaimt innerhalb
      von N Kerzen.
    - SSL-Sweep (Bullisch): Kurs bricht unter ein Niveau (Low < Level),
      schliesst aber wieder darueber (Close > Level) oder reclaimt innerhalb
      von N Kerzen.
    """

    direction: Direction          # "bullish" (SSL sweep) | "bearish" (BSL sweep)
    level_name: str               # z.B. "PDH", "PDL", "ONH", "ONL", "EQH", "EQL", "SwingHigh", "SwingLow"
    level_price: float
    sweep_extreme: float          # Hoechst-/Tiefstkurs des Sweeps

    sweep_depth_points: float
    sweep_depth_ticks: float
    sweep_depth_atr: float | None

    event_time: datetime          # Zeitpunkt der Sweep-Kerze
    confirmation_time: datetime   # Zeitpunkt der Reclaim-Bestaetigung
    availability_time: datetime

    reclaim_confirmed: bool = True
    reclaim_bars_taken: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "richtung": self.direction,
            "niveau_name": self.level_name,
            "niveau_preis": round(self.level_price, 4),
            "sweep_extremum": round(self.sweep_extreme, 4),
            "sweep_tiefe_punkte": round(self.sweep_depth_points, 4),
            "sweep_tiefe_ticks": round(self.sweep_depth_ticks, 1),
            "sweep_tiefe_in_atr": round(self.sweep_depth_atr, 2) if self.sweep_depth_atr is not None else None,
            "sweep_zeit_utc": self.event_time.isoformat(),
            "reclaim_bestaetigt_am_utc": self.confirmation_time.isoformat(),
            "verfuegbar_ab_utc": self.availability_time.isoformat(),
            "reclaim_erfolgt": self.reclaim_confirmed,
            "kerzen_bis_reclaim": self.reclaim_bars_taken,
        }


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    *,
    levels: list[tuple[str, float]] | None = None,
    tick_size: float = 0.25,
    max_reclaim_bars: int = 3,
    atr_series: pd.Series | None = None,
) -> list[LiquiditySweep]:
    """Erkennt Buy-Side und Sell-Side Liquidity Sweeps ueber gegebene Schluesselniveaus."""
    validate_ohlcv(df)
    if not levels or len(df) < 2:
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    timestamps = df.index

    atrs = None
    if atr_series is not None:
        atrs = atr_series.to_numpy(dtype=float)
    elif "atr" in df.columns:
        atrs = df["atr"].to_numpy(dtype=float)

    sweeps: list[LiquiditySweep] = []
    n = len(df)

    for lvl_name, lvl_price in levels:
        if lvl_price <= 0:
            continue

        for i in range(1, n):
            c_high = highs[i]
            c_low = lows[i]
            c_close = closes[i]
            c_time = timestamps[i].to_pydatetime()

            curr_atr = float(atrs[i]) if (atrs is not None and not math.isnan(atrs[i])) else None

            # Buy-Side Liquidity Sweep (BSL): High > Level
            if c_high > lvl_price and highs[i - 1] <= lvl_price:
                # Reclaim sofort in derselben Kerze:
                if c_close < lvl_price:
                    depth = c_high - lvl_price
                    sweeps.append(
                        LiquiditySweep(
                            direction="bearish",
                            level_name=lvl_name,
                            level_price=lvl_price,
                            sweep_extreme=c_high,
                            sweep_depth_points=depth,
                            sweep_depth_ticks=depth / tick_size,
                            sweep_depth_atr=(depth / curr_atr) if curr_atr else None,
                            event_time=c_time,
                            confirmation_time=c_time,
                            availability_time=c_time,
                            reclaim_confirmed=True,
                            reclaim_bars_taken=1,
                        )
                    )
                else:
                    # Pruefe Reclaim in den naechsten max_reclaim_bars
                    for k in range(1, min(max_reclaim_bars + 1, n - i)):
                        if closes[i + k] < lvl_price:
                            max_h = float(np.max(highs[i : i + k + 1]))
                            depth = max_h - lvl_price
                            reclaim_time = timestamps[i + k].to_pydatetime()
                            sweeps.append(
                                LiquiditySweep(
                                    direction="bearish",
                                    level_name=lvl_name,
                                    level_price=lvl_price,
                                    sweep_extreme=max_h,
                                    sweep_depth_points=depth,
                                    sweep_depth_ticks=depth / tick_size,
                                    sweep_depth_atr=(depth / curr_atr) if curr_atr else None,
                                    event_time=c_time,
                                    confirmation_time=reclaim_time,
                                    availability_time=reclaim_time,
                                    reclaim_confirmed=True,
                                    reclaim_bars_taken=k + 1,
                                )
                            )
                            break

            # Sell-Side Liquidity Sweep (SSL): Low < Level
            if c_low < lvl_price and lows[i - 1] >= lvl_price:
                if c_close > lvl_price:
                    depth = lvl_price - c_low
                    sweeps.append(
                        LiquiditySweep(
                            direction="bullish",
                            level_name=lvl_name,
                            level_price=lvl_price,
                            sweep_extreme=c_low,
                            sweep_depth_points=depth,
                            sweep_depth_ticks=depth / tick_size,
                            sweep_depth_atr=(depth / curr_atr) if curr_atr else None,
                            event_time=c_time,
                            confirmation_time=c_time,
                            availability_time=c_time,
                            reclaim_confirmed=True,
                            reclaim_bars_taken=1,
                        )
                    )
                else:
                    for k in range(1, min(max_reclaim_bars + 1, n - i)):
                        if closes[i + k] > lvl_price:
                            min_l = float(np.min(lows[i : i + k + 1]))
                            depth = lvl_price - min_l
                            reclaim_time = timestamps[i + k].to_pydatetime()
                            sweeps.append(
                                LiquiditySweep(
                                    direction="bullish",
                                    level_name=lvl_name,
                                    level_price=lvl_price,
                                    sweep_extreme=min_l,
                                    sweep_depth_points=depth,
                                    sweep_depth_ticks=depth / tick_size,
                                    sweep_depth_atr=(depth / curr_atr) if curr_atr else None,
                                    event_time=c_time,
                                    confirmation_time=reclaim_time,
                                    availability_time=reclaim_time,
                                    reclaim_confirmed=True,
                                    reclaim_bars_taken=k + 1,
                                )
                            )
                            break

    sweeps.sort(key=lambda s: s.confirmation_time)
    return sweeps


# ===========================================================================
# 5. Market Structure Shift (MSS) vs. BOS vs. CHoCH
# ===========================================================================

@dataclass(frozen=True)
class StructureBreak:
    """Strukturbruch-Ereignis (BOS, CHoCH oder MSS).

    Abgrenzung:
    - BOS (Break of Structure): Trend-Fortsetzung (z.B. neues HH im Uptrend).
    - CHoCH (Change of Character): Erster Gegenstruktur-Bruch (z.B. HL unterschritten).
    - MSS (Market Structure Shift): CHoCH MIT Displacement und FVG-Bestaetigung
      (institutioneller Trendwechsel).
    """

    break_type: StructureBreakType
    direction: Direction
    broken_level: float
    swing_point: SwingPoint

    event_time: datetime         # Wann der Bruch stattfand
    confirmation_time: datetime  # Wann der Bruch bestaetigt war (Bar Close)
    availability_time: datetime

    displacement_present: bool = False
    fvg_present: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "typ": self.break_type,
            "richtung": self.direction,
            "gebrochenes_niveau": round(self.broken_level, 4),
            "swing_zeit_utc": self.swing_point.timestamp.isoformat(),
            "bruch_zeit_utc": self.event_time.isoformat(),
            "bestaetigt_am_utc": self.confirmation_time.isoformat(),
            "verfuegbar_ab_utc": self.availability_time.isoformat(),
            "mit_displacement": self.displacement_present,
            "mit_fvg": self.fvg_present,
        }


def detect_structure_breaks(
    df: pd.DataFrame,
    *,
    swings: list[SwingPoint] | None = None,
    strength: int = 3,
    lookback: int = 120,
    displacements: list[Displacement] | None = None,
    fvgs: list[FairValueGap] | None = None,
) -> list[StructureBreak]:
    """Erkennt alle BOS, CHoCH und MSS Ereignisse chronologisch."""
    validate_ohlcv(df)
    if swings is None:
        swings = find_swing_points(df, strength=strength, lookback=lookback)

    if len(swings) < 2:
        return []

    if displacements is None:
        displacements = detect_displacements(df)
    if fvgs is None:
        fvgs = detect_fair_value_gaps(df)

    disp_times = {d.confirmation_time: d for d in displacements}
    fvg_times = {f.confirmation_time: f for f in fvgs}

    closes = df["close"].to_numpy(dtype=float)
    timestamps = df.index
    n = len(df)

    breaks: list[StructureBreak] = []

    # Sortiere Swings chronologisch
    chrono_swings = sorted(swings, key=lambda s: s.bars_ago, reverse=True)

    for idx, sp in enumerate(chrono_swings):
        # Bestaetigungspunkt des Swings im df
        sp_bar_idx = len(df) - 1 - sp.bars_ago
        conf_idx = min(n - 1, sp_bar_idx + strength)

        for i in range(conf_idx + 1, n):
            c_close = closes[i]
            c_time = timestamps[i].to_pydatetime()

            # Bruch nach oben (Swing High gebrochen)
            if sp.kind == "high" and c_close > sp.price:
                # Pruefe ob vorheriger Trend downtrend war -> CHoCH/MSS, sonst BOS
                has_disp = c_time in disp_times and disp_times[c_time].direction == "bullish"
                has_fvg = c_time in fvg_times and fvg_times[c_time].kind == "bullish"

                # Klassifikation
                b_type: StructureBreakType = "BOS"
                if idx > 0 and chrono_swings[idx - 1].kind == "high" and sp.price < chrono_swings[idx - 1].price:
                    # LH wurde gebrochen -> Gegenstruktur
                    b_type = "MSS" if (has_disp or has_fvg) else "CHoCH"

                breaks.append(
                    StructureBreak(
                        break_type=b_type,
                        direction="bullish",
                        broken_level=sp.price,
                        swing_point=sp,
                        event_time=c_time,
                        confirmation_time=c_time,
                        availability_time=c_time,
                        displacement_present=has_disp,
                        fvg_present=has_fvg,
                    )
                )
                break  # Dieser Swing wurde einmal gebrochen

            # Bruch nach unten (Swing Low gebrochen)
            elif sp.kind == "low" and c_close < sp.price:
                has_disp = c_time in disp_times and disp_times[c_time].direction == "bearish"
                has_fvg = c_time in fvg_times and fvg_times[c_time].kind == "bearish"

                b_type: StructureBreakType = "BOS"
                if idx > 0 and chrono_swings[idx - 1].kind == "low" and sp.price > chrono_swings[idx - 1].price:
                    # HL wurde gebrochen -> Gegenstruktur
                    b_type = "MSS" if (has_disp or has_fvg) else "CHoCH"

                breaks.append(
                    StructureBreak(
                        break_type=b_type,
                        direction="bearish",
                        broken_level=sp.price,
                        swing_point=sp,
                        event_time=c_time,
                        confirmation_time=c_time,
                        availability_time=c_time,
                        displacement_present=has_disp,
                        fvg_present=has_fvg,
                    )
                )
                break

    breaks.sort(key=lambda b: b.confirmation_time)
    return breaks
