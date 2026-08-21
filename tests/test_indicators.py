"""Tests der Indikator-Berechnungen."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import FlagConfig
from common.indicators import (
    atr,
    compute_indicators,
    flag_signals,
    previous_session_levels,
    rsi,
    session_vwap,
    sma,
    validate_ohlcv,
)
from common.sessions import session_date_for, session_dates
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------

def test_sma_ist_gleitender_mittelwert():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(series, 3)
    assert np.isnan(result.iloc[0]) and np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_rsi_bei_ausschliesslich_steigenden_kursen_ist_100():
    closes = pd.Series(np.arange(100, 140, dtype=float))
    result = rsi(closes, 14)
    assert result.dropna().iloc[-1] == pytest.approx(100.0)


def test_rsi_bei_ausschliesslich_fallenden_kursen_ist_0():
    closes = pd.Series(np.arange(140, 100, -1, dtype=float))
    result = rsi(closes, 14)
    assert result.dropna().iloc[-1] == pytest.approx(0.0)


def test_rsi_bleibt_im_gueltigen_band():
    rng = np.random.default_rng(42)
    closes = pd.Series(20000 + np.cumsum(rng.normal(0, 5, 500)))
    result = rsi(closes, 14).dropna()
    assert len(result) > 400
    assert result.between(0, 100).all()


def test_rsi_warmlaufphase_ist_nan():
    closes = pd.Series(np.arange(100, 120, dtype=float))
    result = rsi(closes, 14)
    # Die ersten 14 Werte koennen noch keinen belastbaren RSI liefern.
    assert result.iloc[:14].isna().all()


def test_atr_ist_positiv_und_glatt():
    frame = make_ohlcv(np.linspace(100, 120, 60), spread=2.0)
    result = atr(frame, 14).dropna()
    assert (result > 0).all()
    # Bei konstantem Spread und gleichmaessigem Anstieg pendelt sich ATR ein.
    assert result.iloc[-1] == pytest.approx(result.iloc[-2], rel=0.2)


def test_validate_ohlcv_meldet_fehlende_spalten():
    frame = make_ohlcv([1.0, 2.0]).drop(columns=["volume"])
    with pytest.raises(ValueError, match="volume"):
        validate_ohlcv(frame)


def test_validate_ohlcv_verlangt_zeitzone():
    frame = make_ohlcv([1.0, 2.0])
    frame.index = frame.index.tz_localize(None)
    with pytest.raises(ValueError, match="zeitzonenbehaftet"):
        validate_ohlcv(frame)


# ---------------------------------------------------------------------------
# Session-Logik
# ---------------------------------------------------------------------------

def test_session_date_rollt_ab_18_uhr_et_auf_den_folgetag(session_cfg):
    # 22:00 UTC = 17:00 ET (Winterzeit) -> noch derselbe Handelstag
    before = pd.Timestamp("2025-01-02 22:00", tz="UTC").to_pydatetime()
    # 23:30 UTC = 18:30 ET -> naechster Handelstag
    after = pd.Timestamp("2025-01-02 23:30", tz="UTC").to_pydatetime()

    assert session_date_for(before, session_cfg).isoformat() == "2025-01-02"
    assert session_date_for(after, session_cfg).isoformat() == "2025-01-03"


def test_session_dates_vektorisiert_stimmt_mit_einzelwerten_ueberein(session_cfg):
    index = pd.date_range("2025-01-02 12:00", periods=48, freq="1h", tz="UTC")
    vectorized = session_dates(index, session_cfg)
    for timestamp in index:
        assert vectorized[timestamp] == session_date_for(timestamp.to_pydatetime(), session_cfg)


def test_session_vwap_setzt_zum_sessionbeginn_zurueck(session_cfg):
    # 20:00-22:00 UTC = 15:00-17:00 ET -> Handelstag 2025-01-02
    # ab 23:00 UTC   = 18:00 ET       -> Handelstag 2025-01-03
    index = pd.date_range("2025-01-02 20:00", periods=8, freq="1h", tz="UTC")
    closes = [100.0] * 3 + [200.0] * 5
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [10.0] * 8,
        },
        index=index,
    )

    vwap = session_vwap(frame, session_cfg)
    sessions = session_dates(index, session_cfg)

    # Die Testdaten muessen den Sessionwechsel wirklich treffen.
    wechsel = int(np.argmax(sessions.values != sessions.values[0]))
    assert wechsel == 3

    # Innerhalb einer Session bleibt der VWAP beim konstanten Kurs.
    assert vwap.iloc[0] == pytest.approx(100.0)
    # Nach dem Sessionwechsel darf der alte Kurs nicht mehr nachwirken.
    assert vwap.iloc[wechsel] == pytest.approx(200.0)
    assert vwap.iloc[-1] == pytest.approx(200.0)


def test_previous_session_levels_nutzen_die_vorsession(session_cfg):
    index = pd.date_range("2025-01-02 20:00", periods=8, freq="1h", tz="UTC")
    highs = [110.0] * 3 + [220.0] * 5
    lows = [90.0] * 3 + [180.0] * 5
    frame = pd.DataFrame(
        {
            "open": [100.0] * 8,
            "high": highs,
            "low": lows,
            "close": [100.0] * 3 + [200.0] * 5,
            "volume": [1.0] * 8,
        },
        index=index,
    )

    levels = previous_session_levels(frame, session_cfg)
    # Erste Session hat keine Vorsession.
    assert pd.isna(levels["prev_session_high"].iloc[0])
    # Zweite Session sieht Hoch/Tief der ersten.
    assert levels["prev_session_high"].iloc[-1] == pytest.approx(110.0)
    assert levels["prev_session_low"].iloc[-1] == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Flaggen-Heuristik
# ---------------------------------------------------------------------------

def test_flag_breakout_wird_nach_impuls_und_enger_range_erkannt():
    # Aufbau: ruhig -> starker Impuls -> enge Range -> Ausbruch nach oben.
    # Die Konsolidierung muss direkt am Impulsende (130) ansetzen, sonst
    # spannt die Uebergangskerze die Range zu weit auf.
    closes = (
        [100.0 + 0.1 * i for i in range(30)]         # ruhiger Vorlauf
        + [103.0 + 3.0 * i for i in range(10)]       # Impuls, endet bei 130
        + [130.2, 130.0, 130.3, 129.9, 130.1]        # enge Konsolidierung
        + [140.0]                                    # Ausbruch
    )
    frame = make_ohlcv(closes, spread=0.3)
    atr_series = atr(frame, 14)

    config = FlagConfig(
        impulse_lookback=10,
        impulse_min_atr=2.0,
        consolidation_lookback=5,
        consolidation_max_atr=2.0,
        breakout_buffer_atr=0.0,
    )
    signals = flag_signals(frame, atr_series, config)

    assert bool(signals["flag_breakout_up"].iloc[-1]) is True
    assert bool(signals["flag_breakout_down"].iloc[-1]) is False


def test_flag_meldet_keinen_ausbruch_bei_reinem_seitwaerts():
    # Deterministische Saegezahn-Bewegung ohne Nettorichtung: der Impuls ueber
    # das Lookback-Fenster ist per Konstruktion ~0 und kann die Schwelle
    # (2.5 x ATR) nie erreichen.
    closes = [100.0 + (0.5 if i % 2 else -0.5) for i in range(200)]
    frame = make_ohlcv(closes, spread=0.2)
    signals = flag_signals(frame, atr(frame, 14), FlagConfig())

    assert not signals["flag_breakout_up"].any()
    assert not signals["flag_breakout_down"].any()


# ---------------------------------------------------------------------------
# Gesamtberechnung
# ---------------------------------------------------------------------------

def test_compute_indicators_liefert_alle_spalten(indicator_cfg, session_cfg):
    frame = make_ohlcv(np.linspace(20000, 20200, 300))
    result = compute_indicators(frame, indicator_cfg, session_cfg)

    for column in (
        "rsi", "sma_fast", "sma_slow", "atr", "vwap",
        "prev_session_high", "prev_session_low", "prev_session_close",
        "flag_breakout_up", "flag_breakout_down", "session_date",
    ):
        assert column in result.columns, f"Spalte {column} fehlt"

    # Eingabe darf nicht veraendert werden.
    assert "rsi" not in frame.columns
    assert len(result) == len(frame)
