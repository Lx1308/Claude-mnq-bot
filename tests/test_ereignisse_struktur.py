"""Marktstruktur als Serie: HH/HL/LH/LL, BOS, CHoCH.

Der punktuelle Erkenner in market_primitives.py durchsucht je Swing die
Restreihe - O(Swings x n), auf 2,5 Mio Kerzen nicht rechenbar. Diese Tests
sichern die serientaugliche Fassung ab: richtige Klassifikation, kein
Lookahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.basis import LookaheadVerletzung
from common.ereignisse.struktur import struktur_ereignisse, struktur_spalten
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _kurs(preise: list[float]) -> pd.DataFrame:
    n = len(preise)
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": [p + 1.0 for p in preise],
            "low": [p - 1.0 for p in preise],
            "close": preise,
            "volume": [500.0] * n,
        },
        index=index,
    )


def _trend_hoch(wiederholungen: int = 8) -> list[float]:
    """Sauberer Aufwaertstrend: jede Welle hoeher als die vorige."""
    preise: list[float] = [100.0] * 40
    hoch = 100.0
    for k in range(wiederholungen):
        hoch += 30.0
        tief = hoch - 15.0
        preise += [hoch - 20, hoch - 10, hoch, hoch - 5, hoch - 12, tief, tief + 8]
    preise += [preise[-1]] * 20
    return preise


def test_aufwaertstrend_wird_erkannt(config):
    df = compute_indicators(_kurs(_trend_hoch()), config.indicators, config.market.session)
    spalten = struktur_spalten(df)
    # Am Ende der Reihe muss die Struktur aufwaerts stehen.
    assert spalten["struktur_trend"].iloc[-1] == 1
    assert bool(spalten["struktur_hh"].any())
    assert bool(spalten["struktur_hl"].any())


def test_bos_im_trend_choch_gegen_den_trend(config):
    # Aufwaerts, dann ein tiefer Bruch -> CHoCH bearish.
    preise = _trend_hoch(6)
    letztes_tief = min(preise[-30:])
    preise += [letztes_tief - 40] * 10   # klarer Bruch nach unten
    df = compute_indicators(_kurs(preise), config.indicators, config.market.session)

    ereignisse = struktur_ereignisse(df)
    typen = {e.pattern_type for e in ereignisse}
    assert "bos_bullish" in typen, "Kein BOS im Aufwaertstrend"
    assert "choch_bearish" in typen, "Kein CHoCH beim Bruch gegen den Trend"


def test_jedes_ereignis_haelt_die_phasenordnung(config):
    df = compute_indicators(_kurs(_trend_hoch(10)), config.indicators, config.market.session)
    ereignisse = struktur_ereignisse(df)
    assert ereignisse
    for e in ereignisse:
        assert e.entstehung_idx <= e.bestaetigung_idx <= e.verfuegbar_idx


def test_derselbe_swing_wird_nur_einmal_gebrochen(config):
    """Sonst feuert der Bruch auf jeder Kerze der Bewegung erneut."""
    preise = _trend_hoch(4)
    # Lange Seitwaerts ueber dem letzten Swing-Hoch - darf nicht dauerfeuern.
    preise += [max(preise) + 5] * 60
    df = compute_indicators(_kurs(preise), config.indicators, config.market.session)

    ereignisse = struktur_ereignisse(df)
    bullish = [e for e in ereignisse if e.direction == 1]
    ursprünge = [e.entstehung_idx for e in bullish]
    assert len(ursprünge) == len(set(ursprünge)), "Ein Swing mehrfach gebrochen"


def test_kein_lookahead(config):
    rng = np.random.default_rng(42)
    n = 4000
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 5.0, n))
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    df = compute_indicators(
        pd.DataFrame(
            {
                "open": preise, "high": preise + 4, "low": preise - 4,
                "close": preise, "volume": 800.0,
            },
            index=idx,
        ),
        config.indicators, config.market.session,
    )

    schnitt = 2500
    voll = struktur_ereignisse(df)
    kurz = struktur_ereignisse(df.iloc[:schnitt])

    voll_frueh = [
        (e.pattern_type, e.entstehung_idx, e.verfuegbar_idx)
        for e in voll if e.verfuegbar_idx < schnitt
    ]
    kurz_liste = [
        (e.pattern_type, e.entstehung_idx, e.verfuegbar_idx) for e in kurz
    ]
    assert voll_frueh == kurz_liste


def test_struktur_spalten_haben_richtige_laenge(config):
    df = compute_indicators(_kurs(_trend_hoch()), config.indicators, config.market.session)
    spalten = struktur_spalten(df)
    assert len(spalten) == len(df)
    assert set(spalten.columns) == {
        "struktur_hh", "struktur_hl", "struktur_lh", "struktur_ll", "struktur_trend",
    }


def test_ohne_atr_bricht_es_ab(config):
    df = _kurs(_trend_hoch(3))
    with pytest.raises(ValueError, match="atr"):
        struktur_ereignisse(df)
