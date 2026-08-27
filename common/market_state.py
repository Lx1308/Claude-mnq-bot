"""Kanonisches, deterministisches MarketState-Modell.

Ein MarketState repraesentiert den vollstaendigen, mathematisch definierten
Zustand des Marktes zu einem exakten historischen Zeitpunkt T, basierend
AUSSCHLIESSLICH auf Informationen, die zum Zeitpunkt T verfuegbar waren.

Keine Heuristiken wie "sieht bullisch aus", sondern:
- Multi-Timeframe Marktstruktur (4h, 1h, 15m, 5m, 1m)
- Liquiditaets-Niveaus & Sweeps (PDH/PDL, ONH/ONL, PWH/PWL, EQH/EQL)
- Ineffizienzen (aktive FVGs, Displacement)
- Volatilitaets- & Kompressions-Regime
- Session- & Opening-Range-Kontext
- Session-VWAP & Relativvolumen
- Makro-/Event-Status & Blackout-Fenster
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.config import IndicatorConfig, SessionConfig
from common.indicators import compute_indicators
from common.instruments import Instrument, get_instrument
from common.levels import LevelSet, compute_levels, overnight_mask, rth_mask
from common.market_primitives import (
    Displacement,
    EqualLevel,
    FairValueGap,
    LiquiditySweep,
    StructureBreak,
    detect_displacements,
    detect_equal_highs_lows,
    detect_fair_value_gaps,
    detect_liquidity_sweeps,
    detect_structure_breaks,
)
from common.patterns import detect_double_top_bottom, detect_flag, detect_triangle
from common.sessions import (
    SESSION_WINDOWS,
    SessionWindow,
    market_timezone,
    session_date_for,
    session_dates,
)
from common.structure import (
    MarketStructure,
    RsiDivergence,
    TrendAssessment,
    assess_trend,
    classify_market_structure,
    detect_rsi_divergence,
    find_swing_points,
    support_resistance_zones,
)
from common.timeframes import CANONICAL_TIMEFRAMES, normalize_timeframe, resample_ohlcv


@dataclass(frozen=True)
class TimeframeState:
    """Zustand einer einzelnen Zeitebene zum Zeitpunkt T."""

    timeframe: str
    close_price: float
    atr: float | None
    trend_direction: str                 # "aufwaerts" | "abwaerts" | "seitwaerts" | "unklar"
    structure_trend: str                 # "uptrend" | "downtrend" | "range_expanding" | "range_contracting" | "unklar"
    above_sma50: bool | None
    above_vwap: bool | None
    active_fvg_count: int
    recent_displacement: bool
    recent_sweep: bool
    rsi: float | None
    adx: float | None
    last_swing_high: float | None
    last_swing_low: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LiquidityContext:
    """Liquiditaets-Umfeld und Schluesselniveaus relativ zum Kurs."""

    current_price: float

    # Distanzen in Punkten (positiv = Niveau liegt ueber Kurs)
    dist_pdh_pts: float | None
    dist_pdl_pts: float | None
    dist_onh_pts: float | None
    dist_onl_pts: float | None
    dist_pwh_pts: float | None
    dist_pwl_pts: float | None
    dist_ib_high_pts: float | None
    dist_ib_low_pts: float | None

    # Distanzen in ATR
    dist_pdh_atr: float | None
    dist_pdl_atr: float | None
    dist_onh_atr: float | None
    dist_onl_atr: float | None
    dist_pwh_atr: float | None
    dist_pwl_atr: float | None

    # Equal Highs / Lows (Liquiditaetspools)
    active_eqh_count: int
    active_eql_count: int
    nearest_eqh_pts: float | None
    nearest_eql_pts: float | None

    # Juengste Sweeps
    recent_bsl_sweep: bool
    recent_ssl_sweep: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VolatilityRegime:
    """Volatilitaets- und Kompressionszustand."""

    atr_5m: float | None
    atr_1h: float | None
    atr_percentile_20d: float | None
    regime: Literal["low_volatility", "normal_volatility", "high_volatility"]
    is_compressed: bool                  # Inside Bar / BB Squeeze / verengte Range
    is_expanding: bool                   # Range Expansion / Momentum Ausbruch

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SessionContext:
    """Session- und Tagesverlaufskontext."""

    trading_day: str
    active_window: str                   # "asia" | "london" | "new_york" | "overnight"
    is_rth: bool
    minutes_into_session: int
    initial_balance_complete: bool
    opening_range_5m_breakout: str | None # "up" | "down" | None
    opening_range_15m_breakout: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MacroContext:
    """Makro-, Termin- und Event-Umfeld."""

    blackout_active: bool
    minutes_to_next_event: int | None
    next_event_name: str | None
    next_event_importance: str | None
    macro_regime: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketState:
    """Der vollstaendige, unveränderliche Marktzustand zum Zeitpunkt T."""

    timestamp_utc: datetime
    instrument: str
    current_price: float

    session: SessionContext
    volatility: VolatilityRegime
    liquidity: LiquidityContext
    macro: MacroContext

    # Multi-Timeframe Zustaende
    htf_4h: TimeframeState | None
    htf_1h: TimeframeState | None
    setup_15m: TimeframeState | None
    setup_5m: TimeframeState | None
    trigger_1m: TimeframeState | None

    # Signifikante Muster zum Zeitpunkt T
    detected_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zeitpunkt_utc": self.timestamp_utc.isoformat(),
            "instrument": self.instrument,
            "aktueller_kurs": round(self.current_price, 4),
            "session": self.session.to_dict(),
            "volatilitaet": self.volatility.to_dict(),
            "liquiditaet": self.liquidity.to_dict(),
            "makro": self.macro.to_dict(),
            "4h": self.htf_4h.to_dict() if self.htf_4h else None,
            "1h": self.htf_1h.to_dict() if self.htf_1h else None,
            "15m": self.setup_15m.to_dict() if self.setup_15m else None,
            "5m": self.setup_5m.to_dict() if self.setup_5m else None,
            "1m": self.trigger_1m.to_dict() if self.trigger_1m else None,
            "muster": self.detected_patterns,
        }

    def to_feature_vector(self) -> dict[str, float | int | bool]:
        """Flacher numerischer/boolscher Vektor fuer Machine Learning & empirische Tabellen."""
        vec: dict[str, float | int | bool] = {
            "price": self.current_price,
            "is_rth": self.session.is_rth,
            "minutes_into_session": self.session.minutes_into_session,
            "ib_complete": self.session.initial_balance_complete,
            "vol_regime_high": self.volatility.regime == "high_volatility",
            "vol_regime_low": self.volatility.regime == "low_volatility",
            "is_compressed": self.volatility.is_compressed,
            "is_expanding": self.volatility.is_expanding,
            "blackout_active": self.macro.blackout_active,
            "dist_pdh_pts": self.liquidity.dist_pdh_pts or 0.0,
            "dist_pdl_pts": self.liquidity.dist_pdl_pts or 0.0,
            "dist_onh_pts": self.liquidity.dist_onh_pts or 0.0,
            "dist_onl_pts": self.liquidity.dist_onl_pts or 0.0,
            "dist_pdh_atr": self.liquidity.dist_pdh_atr or 0.0,
            "dist_pdl_atr": self.liquidity.dist_pdl_atr or 0.0,
            "active_eqh": self.liquidity.active_eqh_count,
            "active_eql": self.liquidity.active_eql_count,
            "recent_bsl_sweep": self.liquidity.recent_bsl_sweep,
            "recent_ssl_sweep": self.liquidity.recent_ssl_sweep,
        }

        for tf_name, tf_state in (
            ("4h", self.htf_4h),
            ("1h", self.htf_1h),
            ("15m", self.setup_15m),
            ("5m", self.setup_5m),
            ("1m", self.trigger_1m),
        ):
            if tf_state is not None:
                vec[f"{tf_name}_uptrend"] = tf_state.structure_trend == "uptrend"
                vec[f"{tf_name}_downtrend"] = tf_state.structure_trend == "downtrend"
                vec[f"{tf_name}_above_sma50"] = bool(tf_state.above_sma50)
                vec[f"{tf_name}_above_vwap"] = bool(tf_state.above_vwap)
                vec[f"{tf_name}_fvg_count"] = tf_state.active_fvg_count
                vec[f"{tf_name}_displacement"] = tf_state.recent_displacement
                vec[f"{tf_name}_sweep"] = tf_state.recent_sweep
                vec[f"{tf_name}_rsi"] = tf_state.rsi or 50.0
                vec[f"{tf_name}_adx"] = tf_state.adx or 0.0

        return vec


# ===========================================================================
# Builder: Erzeugt den MarketState fuer einen konkreten Zeitpunkt T
# ===========================================================================

def build_market_state(
    timestamp_utc: datetime,
    bars_1m: pd.DataFrame,
    *,
    symbol: str = "MNQ",
    session_cfg: SessionConfig | None = None,
    indicator_cfg: IndicatorConfig | None = None,
    bars_by_tf: dict[str, pd.DataFrame] | None = None,
) -> MarketState:
    """Baut den unveränderlichen MarketState zum Zeitpunkt T ohne Lookahead."""
    instrument = get_instrument(symbol)
    cfg = session_cfg or SessionConfig(timezone=instrument.timezone)
    ind_cfg = indicator_cfg or IndicatorConfig()

    # 1. Daten bis exakt T schneiden (Lookahead-Schutz)
    cutoff = pd.Timestamp(timestamp_utc)
    df_1m_historical = bars_1m[bars_1m.index <= cutoff]
    if df_1m_historical.empty:
        raise ValueError(f"Keine Kerzen vor oder an {timestamp_utc} verfuegbar.")

    current_price = float(df_1m_historical["close"].iloc[-1])

    # 2. Timeframe-Frames vorbereiten (aus gegebenen Frames oder resampled aus 1m)
    tf_frames: dict[str, pd.DataFrame] = {}
    for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
        if bars_by_tf and tf in bars_by_tf:
            src = bars_by_tf[tf]
            tf_frames[tf] = src[src.index <= cutoff]
        else:
            tf_frames[tf] = resample_ohlcv(df_1m_historical, tf, cfg)

    # 3. Indikatoren auf allen Timeframes berechnen
    enriched: dict[str, pd.DataFrame] = {}
    for tf, frame in tf_frames.items():
        if not frame.empty and len(frame) >= 2:
            enriched[tf] = compute_indicators(frame, ind_cfg, cfg)
        else:
            enriched[tf] = frame

    # 4. Timeframe-Zustaende aufbauen
    def _build_tf_state(tf_name: str) -> TimeframeState | None:
        fr = enriched.get(tf_name)
        if fr is None or fr.empty or len(fr) < 3:
            return None

        last_row = fr.iloc[-1]
        c = float(last_row["close"])
        atr_val = float(last_row["atr"]) if "atr" in fr.columns and not math.isnan(last_row["atr"]) else None
        sma50 = float(last_row["sma_slow"]) if "sma_slow" in fr.columns and not math.isnan(last_row["sma_slow"]) else None
        vwap_val = float(last_row["vwap"]) if "vwap" in fr.columns and not math.isnan(last_row["vwap"]) else None
        rsi_val = float(last_row["rsi"]) if "rsi" in fr.columns and not math.isnan(last_row["rsi"]) else None
        adx_val = float(last_row["adx"]) if "adx" in fr.columns and not math.isnan(last_row["adx"]) else None

        trend_ass = assess_trend(fr, atr_value=atr_val)
        m_struct = classify_market_structure(fr)
        fvgs = detect_fair_value_gaps(fr, tick_size=instrument.tick_size)
        active_fvgs = [f for f in fvgs if not f.is_mitigated]
        disps = detect_displacements(fr, min_body_atr=1.0)
        recent_disp = len(disps) > 0 and (len(fr) - 1 - disps[-1].bar_index) <= 3

        return TimeframeState(
            timeframe=tf_name,
            close_price=c,
            atr=atr_val,
            trend_direction=trend_ass.direction,
            structure_trend=m_struct.trend,
            above_sma50=(c > sma50) if sma50 is not None else None,
            above_vwap=(c > vwap_val) if vwap_val is not None else None,
            active_fvg_count=len(active_fvgs),
            recent_displacement=recent_disp,
            recent_sweep=m_struct.break_of_structure or m_struct.change_of_character,
            rsi=rsi_val,
            adx=adx_val,
            last_swing_high=m_struct.last_swing_high,
            last_swing_low=m_struct.last_swing_low,
        )

    state_4h = _build_tf_state("4h")
    state_1h = _build_tf_state("1h")
    state_15m = _build_tf_state("15m")
    state_5m = _build_tf_state("5m")
    state_1m = _build_tf_state("1m")

    # 5. Levels & Liquiditaets-Umfeld
    level_set = compute_levels(df_1m_historical, instrument, session_cfg=cfg)
    atr_ref = level_set.atr_value or (state_5m.atr if state_5m else 5.0)

    def _dist_pts(lvl_name: str) -> float | None:
        lvl = level_set.by_name(lvl_name)
        return (lvl.price - current_price) if lvl else None

    def _dist_atr(pts: float | None) -> float | None:
        return (pts / atr_ref) if (pts is not None and atr_ref and atr_ref > 0) else None

    dist_pdh = _dist_pts("prev_day_high")
    dist_pdl = _dist_pts("prev_day_low")
    dist_onh = _dist_pts("overnight_high")
    dist_onl = _dist_pts("overnight_low")
    dist_ib_h = _dist_pts("initial_balance_high")
    dist_ib_l = _dist_pts("initial_balance_low")

    # Equal Highs / Lows & Sweeps auf 5m
    fr_5m = enriched.get("5m", df_1m_historical)
    swings_5m = find_swing_points(fr_5m, strength=2)
    eq_highs, eq_lows = detect_equal_highs_lows(fr_5m, swings=swings_5m, tick_size=instrument.tick_size)
    active_eqh = [e for e in eq_highs if not e.is_swept]
    active_eql = [e for e in eq_lows if not e.is_swept]

    key_levels_to_check: list[tuple[str, float]] = []
    if level_set.by_name("prev_day_high"):
        key_levels_to_check.append(("PDH", level_set.by_name("prev_day_high").price))
    if level_set.by_name("prev_day_low"):
        key_levels_to_check.append(("PDL", level_set.by_name("prev_day_low").price))
    if level_set.by_name("overnight_high"):
        key_levels_to_check.append(("ONH", level_set.by_name("overnight_high").price))
    if level_set.by_name("overnight_low"):
        key_levels_to_check.append(("ONL", level_set.by_name("overnight_low").price))

    sweeps = detect_liquidity_sweeps(fr_5m, levels=key_levels_to_check, tick_size=instrument.tick_size)
    recent_sweeps = [s for s in sweeps if (cutoff - pd.Timestamp(s.confirmation_time)).total_seconds() <= 3600]
    has_bsl_sweep = any(s.direction == "bearish" for s in recent_sweeps)
    has_ssl_sweep = any(s.direction == "bullish" for s in recent_sweeps)

    liq_context = LiquidityContext(
        current_price=current_price,
        dist_pdh_pts=dist_pdh,
        dist_pdl_pts=dist_pdl,
        dist_onh_pts=dist_onh,
        dist_onl_pts=dist_onl,
        dist_pwh_pts=None,
        dist_pwl_pts=None,
        dist_ib_high_pts=dist_ib_h,
        dist_ib_low_pts=dist_ib_l,
        dist_pdh_atr=_dist_atr(dist_pdh),
        dist_pdl_atr=_dist_atr(dist_pdl),
        dist_onh_atr=_dist_atr(dist_onh),
        dist_onl_atr=_dist_atr(dist_onl),
        dist_pwh_atr=None,
        dist_pwl_atr=None,
        active_eqh_count=len(active_eqh),
        active_eql_count=len(active_eql),
        nearest_eqh_pts=(active_eqh[0].price_level - current_price) if active_eqh else None,
        nearest_eql_pts=(active_eql[0].price_level - current_price) if active_eql else None,
        recent_bsl_sweep=has_bsl_sweep,
        recent_ssl_sweep=has_ssl_sweep,
    )

    # 6. Session-Kontext
    s_day = session_date_for(cutoff.to_pydatetime(), cfg)
    active_win = "overnight"
    for w in SESSION_WINDOWS:
        if w.contains(cutoff.to_pydatetime()):
            active_win = w.name
            break

    tz = market_timezone(cfg)
    local_cutoff = cutoff.tz_convert(tz)
    s_start_minutes = cfg.start_time.hour * 60 + cfg.start_time.minute
    current_minutes = local_cutoff.hour * 60 + local_cutoff.minute
    minutes_into_s = (current_minutes - s_start_minutes) % 1440

    is_rth_now = bool(instrument.rth_start <= local_cutoff.time() < instrument.rth_end)

    or5_break = None
    if "5m" in level_set.opening_ranges:
        or5 = level_set.opening_ranges["5m"]
        if or5.get("complete"):
            if current_price > or5["high"]:
                or5_break = "up"
            elif current_price < or5["low"]:
                or5_break = "down"

    or15_break = None
    if "15m" in level_set.opening_ranges:
        or15 = level_set.opening_ranges["15m"]
        if or15.get("complete"):
            if current_price > or15["high"]:
                or15_break = "up"
            elif current_price < or15["low"]:
                or15_break = "down"

    sess_context = SessionContext(
        trading_day=s_day.isoformat(),
        active_window=active_win,
        is_rth=is_rth_now,
        minutes_into_session=minutes_into_s,
        initial_balance_complete=level_set.initial_balance_complete,
        opening_range_5m_breakout=or5_break,
        opening_range_15m_breakout=or15_break,
    )

    # 7. Volatilitaets-Regime
    atr_5 = state_5m.atr if state_5m else None
    atr_1 = state_1h.atr if state_1h else None
    vol_regime: Literal["low_volatility", "normal_volatility", "high_volatility"] = "normal_volatility"
    if atr_5 is not None:
        if atr_5 < 3.0:
            vol_regime = "low_volatility"
        elif atr_5 > 10.0:
            vol_regime = "high_volatility"

    # Kompressions-Erkennung (z.B. Flagge oder verengte Bollinger-Baender)
    is_comp = False
    if "bb_squeeze" in fr_5m.columns:
        is_comp = bool(fr_5m["bb_squeeze"].iloc[-1])

    is_exp = False
    if state_5m and state_5m.recent_displacement:
        is_exp = True

    vol_context = VolatilityRegime(
        atr_5m=atr_5,
        atr_1h=atr_1,
        atr_percentile_20d=None,
        regime=vol_regime,
        is_compressed=is_comp,
        is_expanding=is_exp,
    )

    # 8. Makro & Events (Default sicher)
    macro_context = MacroContext(
        blackout_active=False,
        minutes_to_next_event=None,
        next_event_name=None,
        next_event_importance=None,
        macro_regime=None,
    )

    # 9. Chartmuster zum Zeitpunkt T
    detected_patterns: list[str] = []
    p_flag = detect_flag(fr_5m)
    if p_flag:
        detected_patterns.append(p_flag.name)
    p_tri = detect_triangle(fr_5m)
    if p_tri:
        detected_patterns.append(p_tri.name)
    p_dtb = detect_double_top_bottom(fr_5m)
    if p_dtb:
        detected_patterns.append(p_dtb.name)

    return MarketState(
        timestamp_utc=cutoff.to_pydatetime(),
        instrument=symbol,
        current_price=current_price,
        session=sess_context,
        volatility=vol_context,
        liquidity=liq_context,
        macro=macro_context,
        htf_4h=state_4h,
        htf_1h=state_1h,
        setup_15m=state_15m,
        setup_5m=state_5m,
        trigger_1m=state_1m,
        detected_patterns=detected_patterns,
    )
