"""Tests fuer das Forschungsregister backtest/research_register.py."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pandas as pd
import pytest

from backtest.research_register import ResearchRegister, hash_dataframe


def test_research_register_workflow(tmp_path):
    db_file = tmp_path / "test_register.sqlite3"
    register = ResearchRegister(db_file)

    hyp_id = register.next_hypothesis_id()
    assert hyp_id == "HYP-000001"

    entry = register.register(
        title="Bullish MSS nach SSL Sweep",
        description="Hypothese: 5m Bullish MSS nach Sell-Side Sweep uebertrifft Baseline",
        verdict="CONFIRMED",
        timeframe="5m",
        dataset_name="dukascopy_nas100",
        dataset_hash="a1b2c3d4e5f60718",
        git_commit="9a6e68c",
        config_hash="cfg_hash_12345",
        sample_size_train=145,
        sample_size_val=48,
        p_value_raw=0.00012,
        p_value_corrected=0.00132,
        bonferroni_passed=True,
        conditions={"mss": True, "sweep": "SSL", "htf": "uptrend"},
        metrics={"win_rate": 0.62, "sharpe": 1.85, "expectancy_r": 0.42},
        notes="Signifikanter Edge auch nach Kosten.",
    )

    assert entry.hypothesis_id == "HYP-000001"
    assert register.count() == 1

    # Abrufen und Pruefen
    loaded = register.get("HYP-000001")
    assert loaded is not None
    assert loaded.title == "Bullish MSS nach SSL Sweep"
    assert loaded.verdict == "CONFIRMED"
    assert loaded.bonferroni_passed is True
    assert loaded.conditions["mss"] is True
    assert loaded.metrics["sharpe"] == 1.85


def test_hash_dataframe_consistency():
    dates = pd.date_range("2026-08-24 14:00:00", periods=5, freq="1min", tz="UTC")
    df1 = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates)
    df2 = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates)
    df3 = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 105.0]}, index=dates)

    h1 = hash_dataframe(df1)
    h2 = hash_dataframe(df2)
    h3 = hash_dataframe(df3)

    assert h1 == h2
    assert h1 != h3
