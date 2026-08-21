"""Tests der Mustererkennung."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.indicators import compute_indicators
from common.instruments import MNQ
from common.levels import make_level
from common.patterns import (
    detect_all_patterns,
    detect_candle_patterns_at_levels,
    detect_double_top_bottom,
    detect_flag,
    detect_range_compression,
    detect_triangle,
)
from tests.conftest import make_ohlcv
from tests.test_levels_structure import zigzag


# ---------------------------------------------------------------------------
# Dreieck
# ---------------------------------------------------------------------------

def test_symmetrisches_dreieck_wird_erkannt():
    # Fallende Hochs (21200 -> 21140), steigende Tiefs (21000 -> 21060)
    frame = zigzag([21100, 21200, 21000, 21140, 21060, 21100], bars_per_leg=10)
    pattern = detect_triangle(frame, strength=2, lookback=100, atr_value=5.0)

    assert pattern is not None
    assert pattern.name == "Symmetrisches Dreieck"
    assert pattern.direction == "neutral"
    assert pattern.evidence["spanne_neu_punkte"] < pattern.evidence["spanne_alt_punkte"]
    assert pattern.evidence["verengung_prozent"] > 0


def test_aufsteigendes_dreieck_ist_bullisch():
    # Flache Hochs (21200 / 21200), steigende Tiefs (21000 -> 21100)
    frame = zigzag([21100, 21200, 21000, 21200, 21100, 21180], bars_per_leg=10)
    pattern = detect_triangle(frame, strength=2, lookback=100, atr_value=20.0)

    assert pattern is not None
    assert pattern.name == "Aufsteigendes Dreieck"
    assert pattern.direction == "bullish"


def test_dreieck_meldet_nichts_bei_gleichfoermiger_bewegung():
    frame = make_ohlcv(np.linspace(21000, 21300, 200), spread=1.0)
    assert detect_triangle(frame, strength=3, atr_value=5.0) is None


def test_dreieck_konfidenz_steigt_mit_der_verengung():
    schwach = zigzag([21100, 21200, 21000, 21180, 21020, 21150], bars_per_leg=10)
    stark = zigzag([21100, 21200, 21000, 21120, 21080, 21100], bars_per_leg=10)

    schwach_pattern = detect_triangle(schwach, strength=2, atr_value=5.0)
    stark_pattern = detect_triangle(stark, strength=2, atr_value=5.0)

    assert schwach_pattern is not None and stark_pattern is not None
    assert stark_pattern.confidence > schwach_pattern.confidence


# ---------------------------------------------------------------------------
# Doppeltop / Doppelboden
# ---------------------------------------------------------------------------

def test_doppeltop_wird_erkannt():
    # Zwei Hochs bei 21200 / 21205, dazwischen ein Tief bei 21100
    frame = zigzag([21000, 21200, 21100, 21205, 21120], bars_per_leg=12)
    pattern = detect_double_top_bottom(frame, strength=2, lookback=120, atr_value=20.0)

    assert pattern is not None
    assert pattern.name == "Doppeltop"
    assert pattern.direction == "bearish"
    assert pattern.evidence["abstand_der_spitzen_punkte"] == pytest.approx(5.0, abs=1.5)
    assert pattern.evidence["nackenlinie"] == pytest.approx(21100.0, abs=2.0)


def test_doppelboden_wird_erkannt():
    frame = zigzag([21200, 21000, 21100, 21005, 21080], bars_per_leg=12)
    pattern = detect_double_top_bottom(frame, strength=2, lookback=120, atr_value=20.0)

    assert pattern is not None
    assert pattern.name == "Doppelboden"
    assert pattern.direction == "bullish"


def test_kein_doppeltop_wenn_die_spitzen_zu_weit_auseinanderliegen():
    # Zweites Hoch 80 Punkte hoeher - bei ATR 20 sind das 4 ATR
    frame = zigzag([21000, 21200, 21100, 21280, 21150], bars_per_leg=12)
    assert detect_double_top_bottom(frame, strength=2, atr_value=20.0) is None


def test_kein_doppeltop_bei_zu_flachem_zwischental():
    # Zwischental nur 10 Punkte tief, bei ATR 20 also 0.5 ATR
    frame = zigzag([21150, 21200, 21190, 21200, 21180], bars_per_leg=12)
    assert detect_double_top_bottom(frame, strength=2, atr_value=20.0) is None


def test_doppeltop_braucht_atr_als_massstab():
    frame = zigzag([21000, 21200, 21100, 21205, 21120], bars_per_leg=12)
    assert detect_double_top_bottom(frame, strength=2, atr_value=None) is None


# ---------------------------------------------------------------------------
# Range-Kompression
# ---------------------------------------------------------------------------

def test_range_kompression_wird_erkannt():
    rng = np.random.default_rng(12)
    weit = 21000 + np.cumsum(rng.normal(0, 5, 100))
    eng = np.full(20, weit[-1]) + rng.normal(0, 0.3, 20)
    frame = make_ohlcv(np.concatenate([weit, eng]), spread=0.3)

    pattern = detect_range_compression(frame, atr_value=5.0)

    assert pattern is not None
    assert pattern.direction == "neutral"
    assert pattern.evidence["verhaeltnis"] < 0.6
    assert "Ausbruchsrichtung" in pattern.note


def test_zufallspfad_ohne_kompression_schlaegt_nicht_an():
    """Regressionstest gegen den Wurzel-n-Fehler.

    Ein Vergleich von 20-Bar-Spanne gegen 60-Bar-Spanne wuerde hier
    anschlagen, weil die Spanne eines Zufallspfads mit der Wurzel der
    Fensterlaenge waechst - sqrt(20/60) = 0.58 liegt bereits unter der
    Schwelle von 0.6, ganz ohne echte Verengung.
    """
    for seed in (13, 21, 34, 55, 89):
        rng = np.random.default_rng(seed)
        frame = make_ohlcv(21000 + np.cumsum(rng.normal(0, 5, 200)), spread=1.0)
        pattern = detect_range_compression(frame, atr_value=5.0)
        assert pattern is None, f"Falscher Treffer bei Seed {seed}"


def test_kompression_vergleicht_gleich_lange_fenster():
    rng = np.random.default_rng(12)
    weit = 21000 + np.cumsum(rng.normal(0, 5, 100))
    eng = np.full(20, weit[-1]) + rng.normal(0, 0.3, 20)
    frame = make_ohlcv(np.concatenate([weit, eng]), spread=0.3)

    pattern = detect_range_compression(frame, recent_bars=20, reference_bars=60, atr_value=5.0)

    assert pattern.evidence["fensterlaenge_kerzen"] == 20
    assert pattern.evidence["vergleichsfenster_anzahl"] > 1


def test_kompression_braucht_genug_historie():
    frame = make_ohlcv(np.linspace(21000, 21010, 30), spread=0.5)
    assert detect_range_compression(frame) is None


# ---------------------------------------------------------------------------
# Flagge
# ---------------------------------------------------------------------------

def test_flagge_wird_aus_den_indikatorspalten_gelesen(indicator_cfg, session_cfg):
    closes = (
        [100.0 + 0.1 * i for i in range(30)]
        + [103.0 + 3.0 * i for i in range(10)]
        + [130.2, 130.0, 130.3, 129.9, 130.1]
        + [140.0]
    )
    frame = compute_indicators(make_ohlcv(closes, spread=0.3), indicator_cfg, session_cfg)

    pattern = detect_flag(frame)

    assert pattern is not None
    assert pattern.direction == "bullish"
    assert pattern.evidence["ausbruch"] is True
    assert "Heuristik" in pattern.note


def test_flagge_meldet_nichts_ohne_indikatorspalten():
    frame = make_ohlcv([100.0] * 50, spread=0.5)
    assert detect_flag(frame) is None


# ---------------------------------------------------------------------------
# Kerzenmuster - nur an Levels
# ---------------------------------------------------------------------------

def bullish_engulfing_frame(level_price: float = 21000.0):
    """Kleine Abwaertskerze, danach grosse Aufwaertskerze, die sie umschliesst."""
    index = pd.date_range("2025-06-10 14:30", periods=2, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [21005.0, 20995.0],
            "high": [21006.0, 21012.0],
            "low": [20999.0, 20994.0],
            "close": [21000.0, 21010.0],
            "volume": [100.0, 300.0],
        },
        index=index,
    )


def test_engulfing_wird_an_einem_level_gemeldet():
    frame = bullish_engulfing_frame()
    level = make_level("prev_day_high", 21008.0, 21010.0, MNQ, atr_value=20.0)

    patterns = detect_candle_patterns_at_levels(frame, [level], MNQ, atr_value=20.0)

    assert len(patterns) == 1
    assert patterns[0].name == "Engulfing"
    assert patterns[0].direction == "bullish"
    assert patterns[0].weak_signal is True
    assert patterns[0].evidence["level_name"] == "prev_day_high"


def test_engulfing_ohne_level_in_der_naehe_wird_nicht_gemeldet():
    """Der Kern der Regel: isolierte Kerzenmuster sind Rauschen."""
    frame = bullish_engulfing_frame()
    weit_entfernt = make_level("prev_day_high", 21500.0, 21010.0, MNQ, atr_value=20.0)

    assert detect_candle_patterns_at_levels(frame, [weit_entfernt], MNQ, atr_value=20.0) == []


def test_pin_bar_mit_langem_docht_unten_ist_bullisch():
    index = pd.date_range("2025-06-10 14:30", periods=2, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [21000.0, 21002.0],
            "high": [21003.0, 21004.0],
            "low": [20998.0, 20980.0],     # langer Docht nach unten
            "close": [21002.0, 21003.0],   # kleiner Koerper oben
            "volume": [100.0, 200.0],
        },
        index=index,
    )
    level = make_level("day_low", 20982.0, 21003.0, MNQ, atr_value=60.0)

    patterns = detect_candle_patterns_at_levels(frame, [level], MNQ, atr_value=60.0)

    assert any("Docht unten" in pattern.name for pattern in patterns)
    assert all(pattern.weak_signal for pattern in patterns)


def test_kerzenmuster_ohne_atr_werden_nicht_gemeldet():
    frame = bullish_engulfing_frame()
    level = make_level("prev_day_high", 21008.0, 21010.0, MNQ, atr_value=None)
    assert detect_candle_patterns_at_levels(frame, [level], MNQ, atr_value=None) == []


# ---------------------------------------------------------------------------
# Sammelaufruf
# ---------------------------------------------------------------------------

def test_detect_all_sortiert_nach_konfidenz(indicator_cfg, session_cfg):
    frame = compute_indicators(
        zigzag([21000, 21200, 21100, 21205, 21120], bars_per_leg=12),
        indicator_cfg,
        session_cfg,
    )
    patterns = detect_all_patterns(frame, instrument=MNQ, atr_value=20.0, strength=2)

    konfidenzen = [pattern.confidence for pattern in patterns]
    assert konfidenzen == sorted(konfidenzen, reverse=True)


def test_jedes_muster_traegt_seine_rohzahlen(indicator_cfg, session_cfg):
    """Ohne Herleitung ist ein Muster in Claude Desktop nicht nachpruefbar."""
    frame = compute_indicators(
        zigzag([21000, 21200, 21100, 21205, 21120], bars_per_leg=12),
        indicator_cfg,
        session_cfg,
    )
    patterns = detect_all_patterns(frame, instrument=MNQ, atr_value=20.0, strength=2)

    assert patterns, "Die Testdaten sollten mindestens ein Muster liefern."
    for pattern in patterns:
        rendered = pattern.to_dict()
        assert rendered["herleitung"], f"{pattern.name} ohne Herleitung"
        assert 0.0 <= rendered["konfidenz"] <= 1.0


def test_konfidenz_bleibt_im_gueltigen_band():
    frame = zigzag([21000, 21200, 21100, 21201, 21120], bars_per_leg=12)
    pattern = detect_double_top_bottom(frame, strength=2, atr_value=20.0)

    assert pattern is not None
    assert 0.0 <= pattern.confidence <= 1.0
