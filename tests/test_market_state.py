"""Tests fuer das kanonische MarketState-Modell in common/market_state.py."""

from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from common.market_state import (
    MarketState,
    build_market_state,
)
from tests.conftest import make_ohlcv


def test_build_market_state_deterministic_and_lookahead_safe():
    # 2 Handelstage simulierte Minuten-Kerzen (z.B. 2000 Kerzen)
    start = pd.Timestamp("2026-08-24 14:00:00", tz="UTC")
    closes = np.linspace(100, 200, 2000)
    df_full = make_ohlcv(closes, start=start, spread=0.5)

    # Waehle Schnittpunkt T bei Kerze 1000
    t_cutoff = df_full.index[1000].to_pydatetime()

    # Baue MarketState mit vollem DataFrame
    state_1 = build_market_state(t_cutoff, df_full, symbol="MNQ")

    # Baue MarketState mit DataFrame, das strikt bei Kerze 1000 abgeschnitten ist
    df_truncated = df_full.iloc[:1001].copy()
    state_2 = build_market_state(t_cutoff, df_truncated, symbol="MNQ")

    # 1. Deterministische Reproduzierbarkeit
    assert state_1.current_price == pytest.approx(df_full["close"].iloc[1000])
    assert state_1.current_price == state_2.current_price
    assert state_1.timestamp_utc == t_cutoff
    assert state_2.timestamp_utc == t_cutoff

    # 2. Lookahead-Sicherheit: Feature-Vektoren muessen exakt identisch sein
    feat_1 = state_1.to_feature_vector()
    feat_2 = state_2.to_feature_vector()
    assert feat_1 == feat_2

    # 3. Struktur- und Timeframe-Pruefungen
    assert state_1.htf_1h is not None
    assert state_1.setup_5m is not None
    assert state_1.trigger_1m is not None
    assert state_1.liquidity is not None
    assert state_1.session is not None
    assert state_1.volatility is not None

    # 4. Serialisierbarkeit nach dict
    d = state_1.to_dict()
    assert isinstance(d, dict)
    assert d["instrument"] == "MNQ"
    assert d["aktueller_kurs"] == round(df_full["close"].iloc[1000], 4)
