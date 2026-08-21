"""Tests der erweiterten Indikatoren (MACD, Stochastik, ADX, Bollinger, EMA)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.indicators import (
    adx,
    bollinger,
    compute_extended_indicators,
    compute_indicators,
    ema,
    ema_stack,
    macd,
    stochastic,
)
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# EMA / MACD
# ---------------------------------------------------------------------------

def test_ema_reagiert_schneller_als_sma():
    from common.indicators import sma

    closes = pd.Series([100.0] * 30 + [120.0] * 10)
    schnell = ema(closes, 10).iloc[-1]
    langsam = sma(closes, 10).iloc[-1]

    # Nach 10 Kerzen auf neuem Niveau sind beide nah an 120; entscheidend ist
    # die Reaktion kurz nach dem Sprung.
    frueh_ema = ema(closes, 10).iloc[32]
    frueh_sma = sma(closes, 10).iloc[32]
    assert frueh_ema > frueh_sma
    assert schnell == pytest.approx(langsam, rel=0.05)


def test_macd_histogramm_ist_differenz_aus_linie_und_signal():
    closes = pd.Series(np.linspace(100, 140, 200))
    result = macd(closes)

    diff = result["macd_line"] - result["macd_signal"]
    pd.testing.assert_series_equal(
        result["macd_hist"].dropna(), diff.dropna(), check_names=False
    )


def test_macd_ist_positiv_im_aufwaertstrend():
    closes = pd.Series(np.linspace(100, 200, 300))
    result = macd(closes)
    assert result["macd_line"].iloc[-1] > 0
    assert result["macd_hist"].dropna().iloc[-1] == pytest.approx(
        result["macd_line"].iloc[-1] - result["macd_signal"].iloc[-1]
    )


# ---------------------------------------------------------------------------
# Stochastik
# ---------------------------------------------------------------------------

def test_stochastik_bleibt_zwischen_null_und_hundert():
    rng = np.random.default_rng(3)
    frame = make_ohlcv(100 + np.cumsum(rng.normal(0, 1, 300)), spread=0.5)
    result = stochastic(frame).dropna()

    assert result["stoch_k"].between(0, 100).all()
    assert result["stoch_d"].between(0, 100).all()


def test_stochastik_ist_hoch_am_oberen_rand_der_spanne():
    # Kurs steigt monoton -> Schluss liegt stets am Hoch der Spanne
    frame = make_ohlcv(np.linspace(100, 150, 100), spread=0.1)
    result = stochastic(frame).dropna()
    assert result["stoch_k"].iloc[-1] > 90


def test_stochastik_ist_niedrig_am_unteren_rand():
    frame = make_ohlcv(np.linspace(150, 100, 100), spread=0.1)
    result = stochastic(frame).dropna()
    assert result["stoch_k"].iloc[-1] < 10


# ---------------------------------------------------------------------------
# ADX - Trend gegen Chop
# ---------------------------------------------------------------------------

def test_adx_ist_hoch_im_klaren_trend():
    frame = make_ohlcv(np.linspace(20000, 20500, 300), spread=1.0)
    result = adx(frame, 14).dropna()

    assert result["adx"].iloc[-1] > 25
    assert result["plus_di"].iloc[-1] > result["minus_di"].iloc[-1]


def test_adx_ist_niedrig_im_seitwaertsmarkt():
    """Rauschen um einen festen Mittelwert - kein gerichteter Trend.

    Bewusst KEIN sauberer Saegezahn: dessen Hochs und Tiefs waeren in jeder
    Kerze identisch, +DM und -DM damit dauerhaft null. Der ADX antwortet
    darauf mit 100, was rechnerisch stimmt, aber nichts ueber Trendstaerke
    aussagt.
    """
    rng = np.random.default_rng(21)
    closes = 20000 + rng.normal(0, 8, 400)   # mittelwertstabil, kein Drift
    frame = make_ohlcv(closes, spread=1.5)
    result = adx(frame, 14).dropna()

    assert result["adx"].iloc[-1] < 25


def test_adx_erkennt_die_richtung_im_abwaertstrend():
    frame = make_ohlcv(np.linspace(20500, 20000, 300), spread=1.0)
    result = adx(frame, 14).dropna()

    assert result["minus_di"].iloc[-1] > result["plus_di"].iloc[-1]


def test_adx_bleibt_im_gueltigen_band():
    rng = np.random.default_rng(9)
    frame = make_ohlcv(20000 + np.cumsum(rng.normal(0, 3, 500)), spread=1.5)
    result = adx(frame, 14).dropna()

    assert result["adx"].between(0, 100).all()
    assert result["plus_di"].between(0, 100).all()


# ---------------------------------------------------------------------------
# Bollinger und Squeeze
# ---------------------------------------------------------------------------

def test_bollinger_baender_umschliessen_den_kurs():
    rng = np.random.default_rng(4)
    frame = make_ohlcv(100 + np.cumsum(rng.normal(0, 0.8, 300)), spread=0.3)
    result = bollinger(frame).dropna()

    assert (result["bb_upper"] >= result["bb_middle"]).all()
    assert (result["bb_middle"] >= result["bb_lower"]).all()


def test_squeeze_wird_bei_kompression_erkannt():
    """Erst volatil, dann sehr ruhig - die ruhige Phase muss Squeeze melden."""
    rng = np.random.default_rng(6)
    volatil = 100 + np.cumsum(rng.normal(0, 3.0, 200))
    ruhig = np.full(100, volatil[-1]) + rng.normal(0, 0.05, 100)
    frame = make_ohlcv(np.concatenate([volatil, ruhig]), spread=0.2)

    result = bollinger(frame)

    assert bool(result["bb_squeeze"].iloc[-1]) is True
    assert not bool(result["bb_squeeze"].iloc[190])


def test_squeeze_bleibt_bei_anhaltender_ruhe_erkannt():
    """Regressionstest gegen eine selbstbezuegliche Squeeze-Definition.

    Eine Perzentil-Definition ueber die letzten N Kerzen wuerde hier
    aufhoeren zu melden, sobald die ruhige Phase laenger als das Fenster
    ist - also genau dann, wenn die Kompression am ausgepraegtesten ist.
    """
    rng = np.random.default_rng(6)
    volatil = 100 + np.cumsum(rng.normal(0, 3.0, 100))
    sehr_lange_ruhe = np.full(400, volatil[-1]) + rng.normal(0, 0.05, 400)
    frame = make_ohlcv(np.concatenate([volatil, sehr_lange_ruhe]), spread=0.2)

    result = bollinger(frame)
    assert bool(result["bb_squeeze"].iloc[-1]) is True


def test_bandbreite_ist_bei_ruhe_kleiner_als_bei_volatilitaet():
    rng = np.random.default_rng(8)
    volatil = make_ohlcv(100 + np.cumsum(rng.normal(0, 3.0, 200)), spread=1.0)
    ruhig = make_ohlcv(100 + np.cumsum(rng.normal(0, 0.1, 200)), spread=0.05)

    breite_volatil = bollinger(volatil)["bb_bandwidth"].dropna().iloc[-1]
    breite_ruhig = bollinger(ruhig)["bb_bandwidth"].dropna().iloc[-1]

    assert breite_ruhig < breite_volatil


# ---------------------------------------------------------------------------
# EMA-Stack
# ---------------------------------------------------------------------------

def test_ema_stack_erkennt_bullische_staffelung():
    frame = make_ohlcv(np.linspace(20000, 21000, 400), spread=1.0)
    result = ema_stack(frame["close"])

    assert bool(result["ema_stacked_bullish"].iloc[-1]) is True
    assert bool(result["ema_stacked_bearish"].iloc[-1]) is False
    assert result["ema_9"].iloc[-1] > result["ema_200"].iloc[-1]


def test_ema_stack_erkennt_baerische_staffelung():
    frame = make_ohlcv(np.linspace(21000, 20000, 400), spread=1.0)
    result = ema_stack(frame["close"])

    assert bool(result["ema_stacked_bearish"].iloc[-1]) is True
    assert bool(result["ema_stacked_bullish"].iloc[-1]) is False


def test_ema_stack_bricht_waehrend_einer_trendwende_auf():
    """Waehrend der Wende ist weder die bullische noch die baerische Ordnung intakt.

    Bewusst keine Aussage ueber Rauschen: dort sind die EMAs zwar oft
    formal geordnet, liegen aber nur Cents auseinander. Die Staffelung ist
    ein Form-, kein Staerkesignal - fuer die Staerke steht der ADX daneben
    im Snapshot.
    """
    fallend = np.linspace(21000, 20000, 400)
    steigend = np.linspace(20000, 20600, 200)
    frame = make_ohlcv(np.concatenate([fallend, steigend]), spread=1.0)

    wende = ema_stack(frame["close"]).iloc[400:500]
    ungestaffelt = ~(wende["ema_stacked_bullish"] | wende["ema_stacked_bearish"])

    assert ungestaffelt.any(), "Waehrend der Wende muesste die Ordnung brechen."


def test_ema_stack_ist_im_trend_fast_durchgehend_gestaffelt():
    frame = make_ohlcv(np.linspace(20000, 22000, 800), spread=1.0)
    result = ema_stack(frame["close"]).iloc[300:]

    assert result["ema_stacked_bullish"].mean() > 0.9


def test_ema_stack_ist_ohne_genug_historie_false():
    frame = make_ohlcv(np.linspace(100, 110, 50), spread=0.5)
    result = ema_stack(frame["close"])
    # EMA200 kann bei 50 Kerzen nicht existieren -> keine Staffelung behauptet.
    assert not bool(result["ema_stacked_bullish"].iloc[-1])


# ---------------------------------------------------------------------------
# Gesamtberechnung
# ---------------------------------------------------------------------------

def test_compute_extended_baut_auf_der_basisfunktion_auf(indicator_cfg, session_cfg):
    frame = make_ohlcv(np.linspace(20000, 20400, 400), spread=1.0)

    basis = compute_indicators(frame, indicator_cfg, session_cfg)
    erweitert = compute_extended_indicators(frame, indicator_cfg, session_cfg)

    # Die gemeinsamen Spalten muessen identisch sein - keine zweite Rechenlogik.
    for column in ("rsi", "atr", "vwap", "sma_fast", "sma_slow", "prev_session_high"):
        pd.testing.assert_series_equal(
            basis[column], erweitert[column], check_names=False
        )

    for column in (
        "macd_line", "macd_signal", "macd_hist",
        "stoch_k", "stoch_d",
        "adx", "plus_di", "minus_di",
        "bb_upper", "bb_lower", "bb_squeeze",
        "ema_9", "ema_21", "ema_50", "ema_200", "ema_stacked_bullish",
    ):
        assert column in erweitert.columns, f"Spalte {column} fehlt"


def test_basisfunktion_bleibt_schlank(indicator_cfg, session_cfg):
    """compute_indicators darf die neuen Spalten NICHT enthalten.

    Sie laeuft im Backtest ueber hunderttausende Kerzen - alles, was dort
    ohne Not hineinwandert, kostet bei jeder Parametersuche Zeit.
    """
    frame = make_ohlcv(np.linspace(20000, 20100, 300), spread=1.0)
    basis = compute_indicators(frame, indicator_cfg, session_cfg)

    for column in ("macd_line", "adx", "bb_upper", "ema_200", "stoch_k"):
        assert column not in basis.columns
