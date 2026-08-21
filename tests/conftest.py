"""Gemeinsame Test-Fixtures."""

from __future__ import annotations

import sys
from datetime import time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Projektwurzel importierbar machen, ohne Installation als Paket.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import FlagConfig, IndicatorConfig, MarketConfig, SessionConfig  # noqa: E402


@pytest.fixture
def session_cfg() -> SessionConfig:
    return SessionConfig(
        timezone="America/New_York",
        start_time=dtime(18, 0),
        end_time=dtime(17, 0),
    )


@pytest.fixture
def indicator_cfg() -> IndicatorConfig:
    return IndicatorConfig(
        rsi_period=14,
        sma_fast=20,
        sma_slow=50,
        atr_period=14,
        flag=FlagConfig(
            impulse_lookback=10,
            impulse_min_atr=2.0,
            consolidation_lookback=5,
            consolidation_max_atr=1.0,
            breakout_buffer_atr=0.0,
        ),
    )


@pytest.fixture
def market_cfg(session_cfg: SessionConfig) -> MarketConfig:
    return MarketConfig(
        product="NQ",
        candle_interval_minutes=1,
        candle_buffer_size=1000,
        warmup_bars=0,
        tick_size=0.25,
        point_value=20.0,
        session=session_cfg,
    )


def make_ohlcv(
    closes: list[float] | np.ndarray,
    *,
    start: str = "2025-01-02 14:30",
    freq: str = "1min",
    volume: float = 100.0,
    spread: float = 1.0,
) -> pd.DataFrame:
    """Baut ein OHLCV-DataFrame aus einer Schlusskursreihe.

    High/Low werden symmetrisch um den Schlusskurs gesetzt, damit Stops und
    Ziele in Tests deterministisch ausloesen.
    """
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range(start=start, periods=len(closes), freq=freq, tz="UTC")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + spread,
            "low": np.minimum(opens, closes) - spread,
            "close": closes,
            "volume": np.full(len(closes), volume, dtype=float),
        },
        index=index,
    )
