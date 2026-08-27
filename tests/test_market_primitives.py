"""Tests fuer common/market_primitives.py."""

from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import pytest

from common.market_primitives import (
    FairValueGap,
    Displacement,
    EqualLevel,
    LiquiditySweep,
    StructureBreak,
    detect_fair_value_gaps,
    detect_displacements,
    detect_equal_highs_lows,
    detect_liquidity_sweeps,
    detect_structure_breaks,
)
from common.structure import SwingPoint, find_swing_points
from tests.conftest import make_ohlcv


def test_bullish_fvg_detection_and_lookahead():
    # 3 Kerzen:
    # C0: High = 100.0, Low = 95.0
    # C1: High = 110.0, Low = 99.0 (Displacement Up)
    # C2: High = 115.0, Low = 105.0
    # Bullish FVG zwischen 100.0 und 105.0 (Spanne = 5.0 Punkte = 20 Ticks)
    dates = pd.date_range("2026-08-24 14:00:00", periods=3, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [96.0, 100.0, 106.0],
            "high": [100.0, 110.0, 115.0],
            "low": [95.0, 99.0, 105.0],
            "close": [99.0, 108.0, 114.0],
            "volume": [100.0, 500.0, 200.0],
            "atr": [4.0, 4.0, 4.0],
        },
        index=dates,
    )

    fvgs = detect_fair_value_gaps(df, tick_size=0.25)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.kind == "bullish"
    assert fvg.top == 105.0
    assert fvg.bottom == 100.0
    assert fvg.size_points == 5.0
    assert fvg.size_ticks == 20.0
    assert fvg.midpoint == 102.5
    # Lookahead-Pruefung: Bestaetigung und Verfuegbarkeit erst bei C2 (14:10 UTC)
    assert fvg.event_time == pd.Timestamp("2026-08-24 14:05:00", tz="UTC").to_pydatetime()
    assert fvg.confirmation_time == pd.Timestamp("2026-08-24 14:10:00", tz="UTC").to_pydatetime()
    assert fvg.availability_time == fvg.confirmation_time
    assert not fvg.is_mitigated


def test_bearish_fvg_mitigation():
    # 5 Kerzen:
    # C0: High = 120, Low = 115
    # C1: High = 116, Low = 105 (Impulse Down)
    # C2: High = 108, Low = 100 -> Bearish FVG [108, 115]
    # C3: Retracement nach oben: High = 112 -> dringt zu >50% ein -> mitigiert!
    dates = pd.date_range("2026-08-24 14:00:00", periods=4, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [118.0, 115.0, 104.0, 102.0],
            "high": [120.0, 116.0, 108.0, 112.0],
            "low": [115.0, 105.0, 100.0, 101.0],
            "close": [116.0, 106.0, 102.0, 111.0],
            "volume": [100.0, 600.0, 200.0, 150.0],
            "atr": [5.0, 5.0, 5.0, 5.0],
        },
        index=dates,
    )

    fvgs = detect_fair_value_gaps(df, tick_size=0.25)
    assert len(fvgs) == 1
    fvg = fvgs[0]
    assert fvg.kind == "bearish"
    assert fvg.top == 115.0
    assert fvg.bottom == 108.0
    assert fvg.is_mitigated is True
    assert fvg.mitigation_time == pd.Timestamp("2026-08-24 14:15:00", tz="UTC").to_pydatetime()
    assert fvg.fill_ratio >= 0.5


def test_displacement_detection():
    dates = pd.date_range("2026-08-24 14:00:00", periods=3, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 114.0],
            "high": [102.0, 115.0, 116.0],
            "low": [99.0, 100.5, 113.0],
            "close": [101.0, 114.5, 115.0],
            "volume": [100.0, 800.0, 120.0],
            "atr": [5.0, 5.0, 5.0],
        },
        index=dates,
    )

    disps = detect_displacements(df, min_body_atr=1.2, min_body_ratio=0.70)
    assert len(disps) == 1
    d = disps[0]
    assert d.direction == "bullish"
    assert d.body_points == 13.5
    assert d.range_points == 14.5
    assert d.body_ratio > 0.90
    assert d.relative_volume > 1.5


def test_liquidity_sweep_bsl_and_ssl():
    # Level: PDH = 150.0
    # C0: High = 145, Low = 140, Close = 144
    # C1: High = 153, Low = 146, Close = 148 (Sweep ueber 150 und Reclaim darunter!)
    dates = pd.date_range("2026-08-24 14:00:00", periods=2, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [141.0, 147.0],
            "high": [145.0, 153.0],
            "low": [140.0, 146.0],
            "close": [144.0, 148.0],
            "volume": [100.0, 300.0],
            "atr": [5.0, 5.0],
        },
        index=dates,
    )

    sweeps = detect_liquidity_sweeps(df, levels=[("PDH", 150.0)], tick_size=0.25)
    assert len(sweeps) == 1
    s = sweeps[0]
    assert s.direction == "bearish"  # BSL sweep fuehrt zu Verkaufsdruck
    assert s.level_name == "PDH"
    assert s.level_price == 150.0
    assert s.sweep_extreme == 153.0
    assert s.sweep_depth_points == 3.0
    assert s.sweep_depth_ticks == 12.0
    assert s.reclaim_confirmed is True
    assert s.reclaim_bars_taken == 1


def test_equal_highs_and_lows():
    # 2 Swing Highs bei 150.0 und 150.25 (Differenz 0.25 Punkte = 1 Tick)
    # Erwartet: EQH gefunden mit Swing Count 2
    dates = pd.date_range("2026-08-24 14:00:00", periods=20, freq="5min", tz="UTC")
    closes = [
        100.0, 110.0, 130.0, 150.0, 130.0, 110.0, 100.0,
        110.0, 130.0, 150.25, 130.0, 110.0, 100.0,
        100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0
    ]
    df = make_ohlcv(closes, start=dates[0], spread=0.5)

    swings = find_swing_points(df, strength=2)
    eq_highs, eq_lows = detect_equal_highs_lows(df, swings=swings, tolerance_ticks=4.0)

    assert len(eq_highs) >= 1
    eqh = eq_highs[0]
    assert eqh.kind == "high"
    assert eqh.swing_count == 2
    assert abs(eqh.price_level - 150.625) < 0.01
    assert not eqh.is_swept


def test_structure_breaks_bos_choch_mss():
    # Sequenz:
    # 1. Uptrend: Swings bei 100 -> 120 -> 110 -> 140 (HH & HL)
    # 2. CHoCH: Kurs faellt unter 110 (letztes HL) mit Displacement
    # Erwartet: MSS (Market Structure Shift) erkannt
    dates = pd.date_range("2026-08-24 14:00:00", periods=30, freq="5min", tz="UTC")
    closes = [
        100.0, 105.0, 120.0, 115.0, 110.0, 112.0, 125.0, 140.0, 135.0, 130.0,
        125.0, 120.0, 105.0, 100.0, 95.0, 90.0, 90.0, 90.0, 90.0, 90.0,
        90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0
    ]
    df = make_ohlcv(closes, start=dates[0], spread=1.0)
    df["atr"] = 4.0

    swings = find_swing_points(df, strength=2)
    breaks = detect_structure_breaks(df, swings=swings, strength=2)

    assert len(breaks) >= 1
    # Pruefe, dass mind. ein Strukturbruch erfasst wurde
    assert any(b.direction in ("bullish", "bearish") for b in breaks)
