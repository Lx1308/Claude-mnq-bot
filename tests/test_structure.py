"""Tests der Marktstruktur-Analyse: Swings, Zonen, Trend."""

from __future__ import annotations

import numpy as np
import pytest

from common.indicators import atr, compute_indicators
from common.structure import (
    assess_trend,
    find_swing_points,
    support_resistance_zones,
)
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Swing-Punkte
# ---------------------------------------------------------------------------

def test_swing_hoch_und_tief_werden_gefunden():
    # Dreieck hoch, Dreieck runter: genau ein Hoch bei 110, ein Tief bei 90.
    closes = [100, 103, 106, 110, 106, 103, 100, 96, 93, 90, 93, 96, 100, 103, 106]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    points = find_swing_points(frame, strength=3)
    highs = [point for point in points if point.kind == "high"]
    lows = [point for point in points if point.kind == "low"]

    assert len(highs) == 1
    assert len(lows) == 1
    assert highs[0].price == pytest.approx(110.0)
    assert lows[0].price == pytest.approx(90.0)


def test_letzte_kerzen_koennen_noch_kein_swing_sein():
    """Ein Extrem ganz am rechten Rand ist noch nicht bestaetigt."""
    closes = [100, 101, 102, 103, 104, 105, 106]   # monoton steigend
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    points = find_swing_points(frame, strength=3)
    # Das hoechste High liegt auf der letzten Kerze - die kann per Definition
    # kein bestaetigtes Swing-Hoch sein.
    assert all(point.bars_ago >= 3 for point in points)


def test_zu_kurze_historie_liefert_keine_swings():
    frame = make_ohlcv([100.0, 101.0, 102.0], spread=0.0)
    assert find_swing_points(frame, strength=3) == []


def test_bars_ago_zaehlt_ab_der_letzten_kerze():
    closes = [100, 103, 106, 110, 106, 103, 100, 100, 100, 100]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    points = find_swing_points(frame, strength=3)
    high = next(point for point in points if point.kind == "high")

    # Das Hoch liegt auf Index 3, die letzte Kerze ist Index 9.
    assert high.bars_ago == 6


def test_strength_steuert_die_empfindlichkeit():
    rng = np.random.default_rng(11)
    closes = 100 + np.cumsum(rng.normal(0, 1.0, 300))
    frame = make_ohlcv(closes, spread=0.2)

    fein = find_swing_points(frame, strength=2)
    grob = find_swing_points(frame, strength=8)

    assert len(fein) > len(grob)


# ---------------------------------------------------------------------------
# Zonen
# ---------------------------------------------------------------------------

def test_zonen_werden_nach_lage_zum_kurs_eingeordnet():
    # Kurs endet in der Mitte zwischen einem Hoch (110) und einem Tief (90).
    closes = [100, 103, 106, 110, 106, 103, 100, 96, 93, 90, 93, 96, 100, 100, 100]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    supports, resistances = support_resistance_zones(
        frame, atr_value=1.0, strength=3, lookback=50, max_zones=3, merge_atr=0.5
    )

    assert len(resistances) == 1
    assert resistances[0].price == pytest.approx(110.0)
    assert len(supports) == 1
    assert supports[0].price == pytest.approx(90.0)


def test_nahe_swings_werden_zu_einer_zone_mit_mehreren_beruehrungen():
    # Zwei Hochs bei 110.0 und 110.4 - innerhalb von 0.5 * ATR(2.0) = 1.0
    closes = [
        100, 104, 107, 110.0, 107, 104, 101,
        104, 107, 110.4, 107, 104, 101, 101, 101,
    ]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    _, resistances = support_resistance_zones(
        frame, atr_value=2.0, strength=3, lookback=50, max_zones=3, merge_atr=0.5
    )

    assert len(resistances) == 1
    assert resistances[0].touches == 2
    assert resistances[0].lower == pytest.approx(110.0)
    assert resistances[0].upper == pytest.approx(110.4)


def test_weit_entfernte_swings_bleiben_getrennte_zonen():
    closes = [
        100, 104, 107, 110, 107, 104, 101,
        104, 107, 130, 107, 104, 101, 101, 101,
    ]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    _, resistances = support_resistance_zones(
        frame, atr_value=1.0, strength=3, lookback=50, max_zones=3, merge_atr=0.5
    )

    assert len(resistances) == 2
    # Naechstgelegene Zone zuerst.
    assert resistances[0].price < resistances[1].price
    assert resistances[0].distance_points < resistances[1].distance_points


def test_max_zones_begrenzt_das_ergebnis():
    rng = np.random.default_rng(5)
    closes = 100 + np.cumsum(rng.normal(0, 1.5, 400))
    frame = make_ohlcv(closes, spread=0.3)

    supports, resistances = support_resistance_zones(
        frame, atr_value=2.0, strength=2, lookback=300, max_zones=2, merge_atr=0.5
    )

    assert len(supports) <= 2
    assert len(resistances) <= 2


def test_zonen_ohne_atr_funktionieren_trotzdem():
    closes = [100, 103, 106, 110, 106, 103, 100, 100, 100, 100]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    _, resistances = support_resistance_zones(
        frame, atr_value=None, strength=3, lookback=50, max_zones=3, merge_atr=0.5
    )

    assert len(resistances) == 1
    assert resistances[0].distance_atr is None


def test_abstand_in_atr_wird_berechnet():
    closes = [100, 103, 106, 110, 106, 103, 100, 100, 100, 100]
    frame = make_ohlcv([float(c) for c in closes], spread=0.0)

    _, resistances = support_resistance_zones(
        frame, atr_value=2.0, strength=3, lookback=50, max_zones=3, merge_atr=0.1
    )

    zone = resistances[0]
    assert zone.distance_points == pytest.approx(10.0)
    assert zone.distance_atr == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def test_trend_erkennt_aufwaertsbewegung(indicator_cfg, session_cfg):
    frame = make_ohlcv(np.linspace(20000, 20400, 300), spread=1.0)
    enriched = compute_indicators(frame, indicator_cfg, session_cfg)

    trend = assess_trend(enriched, atr_value=float(enriched["atr"].iloc[-1]))

    assert trend.direction == "aufwaerts"
    assert trend.above_sma_slow is True
    assert trend.sma_fast_slope_per_bar > 0


def test_trend_erkennt_abwaertsbewegung(indicator_cfg, session_cfg):
    frame = make_ohlcv(np.linspace(20400, 20000, 300), spread=1.0)
    enriched = compute_indicators(frame, indicator_cfg, session_cfg)

    trend = assess_trend(enriched, atr_value=float(enriched["atr"].iloc[-1]))

    assert trend.direction == "abwaerts"
    assert trend.above_sma_slow is False
    assert trend.sma_fast_slope_per_bar < 0


def test_trend_erkennt_seitwaerts(indicator_cfg, session_cfg):
    closes = [20000.0 + (2.0 if i % 2 else -2.0) for i in range(300)]
    frame = make_ohlcv(closes, spread=1.0)
    enriched = compute_indicators(frame, indicator_cfg, session_cfg)

    trend = assess_trend(enriched, atr_value=float(enriched["atr"].iloc[-1]))

    assert trend.direction == "seitwaerts"


def test_trend_ist_unklar_bei_zu_wenigen_kerzen(indicator_cfg, session_cfg):
    frame = make_ohlcv(np.linspace(20000, 20010, 30), spread=1.0)
    enriched = compute_indicators(frame, indicator_cfg, session_cfg)

    trend = assess_trend(enriched, atr_value=None)

    assert trend.direction == "unklar"
    assert "Zu wenige Kerzen" in trend.description


def test_trend_verlangt_angereichertes_dataframe():
    frame = make_ohlcv([100.0] * 60)
    with pytest.raises(ValueError, match="compute_indicators"):
        assess_trend(frame, atr_value=1.0)


def test_steigung_wird_in_atr_normiert(indicator_cfg, session_cfg):
    """Dieselbe Bewegung muss bei doppeltem ATR die halbe normierte Steigung ergeben."""
    frame = make_ohlcv(np.linspace(20000, 20400, 300), spread=1.0)
    enriched = compute_indicators(frame, indicator_cfg, session_cfg)

    schmal = assess_trend(enriched, atr_value=1.0)
    breit = assess_trend(enriched, atr_value=2.0)

    assert schmal.sma_fast_slope_per_bar == pytest.approx(breit.sma_fast_slope_per_bar)
    assert schmal.sma_fast_slope_in_atr == pytest.approx(
        2 * breit.sma_fast_slope_in_atr
    )
