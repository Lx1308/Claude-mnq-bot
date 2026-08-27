"""Tests fuer backtest/excursions.py und backtest/conditional_outcomes.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.conditional_outcomes import analyze_conditional_outcomes
from backtest.excursions import compute_path_excursions
from tests.conftest import make_ohlcv


def test_path_excursions_long_and_short():
    # 20 Kerzen, Einstieg bei Kerze 5
    dates = pd.date_range("2026-08-24 14:00:00", periods=20, freq="5min", tz="UTC")
    closes = [100.0] * 5 + [105.0, 110.0, 115.0, 95.0, 90.0] + [100.0] * 10
    df = make_ohlcv(closes, start=dates[0], spread=1.0)
    df["atr"] = 5.0

    # Long Exkursion ab Kerze 5 (Ausfuehrung auf Kerze 6 Open)
    long_exc = compute_path_excursions(df, entry_indices=[5], direction=1, horizon_bars=5)
    assert len(long_exc) == 1
    e_long = long_exc[0]
    assert e_long.direction == 1
    assert e_long.entry_price == df["open"].iloc[6]
    # Maximum High in den 5 Kerzen nach Einstieg
    assert e_long.mfe_points >= 4.0
    assert e_long.mae_points >= 9.0

    # Short Exkursion
    short_exc = compute_path_excursions(df, entry_indices=[5], direction=-1, horizon_bars=5)
    assert len(short_exc) == 1
    e_short = short_exc[0]
    assert e_short.direction == -1
    assert e_short.mfe_points == e_long.mae_points


def test_conditional_outcomes_analysis():
    # 100 Kerzen mit simuliertem Trend-Verhalten
    dates = pd.date_range("2026-08-24 14:00:00", periods=100, freq="5min", tz="UTC")
    closes = np.linspace(100, 200, 100)
    df = make_ohlcv(closes, start=dates[0], spread=0.5)
    df["atr"] = 5.0

    # Bedingung: jede 5. Kerze
    cond_mask = np.zeros(100, dtype=bool)
    cond_mask[::5] = True

    report = analyze_conditional_outcomes(
        df,
        cond_mask,
        condition_name="Aufwaertstrend_Test",
        direction=1,
        horizon_bars=10,
        target_r_grid=(1.0, 2.0),
        stop_r_grid=(1.0, 2.0),
    )

    assert report.sample_size > 0
    assert report.unconditional_sample_size > report.sample_size
    assert report.mean_return_pts > 0.0
    assert len(report.target_stop_grid) == 4
    # Serialisierung testen
    d = report.to_dict()
    assert d["bedingung"] == "Aufwaertstrend_Test"
    assert "target_stop_matrix" in d
