"""Tests fuer common/timeframes.py."""

from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from common.config import SessionConfig
from common.timeframes import (
    CANONICAL_TIMEFRAMES,
    TimeframeSpec,
    normalize_timeframe,
    resample_ohlcv,
)
from tests.conftest import make_ohlcv


def test_timeframe_spec_normalization():
    assert normalize_timeframe("1m") == "1m"
    assert normalize_timeframe("5m") == "5m"
    assert normalize_timeframe("15m") == "15m"
    assert normalize_timeframe("60m") == "1h"
    assert normalize_timeframe("1h") == "1h"
    assert normalize_timeframe("240m") == "4h"
    assert normalize_timeframe("4h") == "4h"
    assert normalize_timeframe("1d") == "1d"
    assert normalize_timeframe("daily") == "1d"


def test_resample_5m_timestamp_convention():
    # 5 1-Minuten-Kerzen von 14:00 bis 14:04 (UTC)
    # Erwarteter Zeitstempel der 5m-Kerze: 14:05:00
    dates = pd.date_range("2026-08-24 14:00:00", periods=5, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [105.0, 106.0, 107.0, 108.0, 109.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [101.0, 102.0, 103.0, 104.0, 108.5],
            "volume": [10.0, 20.0, 30.0, 40.0, 50.0],
        },
        index=dates,
    )
    res_5m = resample_ohlcv(df, "5m")
    assert len(res_5m) == 1
    assert res_5m.index[0] == pd.Timestamp("2026-08-24 14:05:00", tz="UTC")
    assert res_5m["open"].iloc[0] == 100.0
    assert res_5m["high"].iloc[0] == 109.0
    assert res_5m["low"].iloc[0] == 99.0
    assert res_5m["close"].iloc[0] == 108.5
    assert res_5m["volume"].iloc[0] == 150.0


def test_resample_4h_globex_alignment():
    # 18:00 ET entspricht im Sommer (EDT) 22:00 UTC
    dates = pd.date_range("2026-08-24 22:00:00", periods=240, freq="1min", tz="UTC")
    closes = np.linspace(100, 150, 240)
    df = make_ohlcv(closes, start=dates[0])

    res_4h = resample_ohlcv(df, "4h")
    assert len(res_4h) == 1
    # 4h-Kerze von 22:00 UTC bis 02:00 UTC naechster Tag -> Label 02:00 UTC
    assert res_4h.index[0] == pd.Timestamp("2026-08-25 02:00:00", tz="UTC")


def test_resample_daily_globex_session():
    # Eine volle Globex-Session: 18:00 ET bis 17:00 ET Folge-Tag (23h)
    dates = pd.date_range("2026-08-24 22:00:00", periods=23 * 60, freq="1min", tz="UTC")
    closes = np.linspace(200, 250, 23 * 60)
    df = make_ohlcv(closes, start=dates[0])

    res_daily = resample_ohlcv(df, "1d")
    assert len(res_daily) == 1
    # Das Sessionende ist 17:00 ET = 21:00 UTC
    assert res_daily.index[0] == pd.Timestamp("2026-08-25 21:00:00", tz="UTC")
    assert res_daily["open"].iloc[0] == pytest.approx(df["open"].iloc[0])
    assert res_daily["close"].iloc[0] == pytest.approx(df["close"].iloc[-1])
