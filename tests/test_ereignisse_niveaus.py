"""Niveau-Interaktion: Test, n-ter Test, Ausbruch, Fehlausbruch, Retest.

Laurins Kerninteresse. Die Tests sichern die objektive, reproduzierbare
Erkennung ab - und dass kein Ereignis Zukunftsinformation nutzt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.niveaus import niveau_ereignisse
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


SESSION = 1440  # ganzer Kalendertag; PDH ist dann ab dem naechsten 18:00 ET live


def _rahmen(preise: list[float], config) -> pd.DataFrame:
    n = len(preise)
    # Start um 23:00 UTC = 18:00 ET, direkt an einem Sessionwechsel.
    index = pd.date_range("2026-01-05 23:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise,
            "high": [p + 2.0 for p in preise],
            "low": [p - 2.0 for p in preise],
            "close": preise,
            "volume": [500.0] * n,
        },
        index=index,
    )
    return compute_indicators(df, config.indicators, config.market.session)


def _vortag(hoch: float, tief: float) -> list[float]:
    """Ein voller Handelstag, der ein bekanntes Hoch und Tief hinterlaesst."""
    mitte = (hoch + tief) / 2
    viertel = SESSION // 4
    return (
        list(np.linspace(mitte, hoch, viertel))
        + list(np.linspace(hoch, tief, viertel))
        + list(np.linspace(tief, hoch, viertel))
        + list(np.linspace(hoch, mitte, SESSION - 3 * viertel))
    )


def test_mehrfacher_test_wird_hochgezaehlt(config):
    marke = 19960.0
    # Das Vortagestief liegt bei marke - 2 (low = Preis - 2). Der Kurs muss es
    # also mit dem Umkehrpunkt genau treffen. Halbwellen unter RETEST_FENSTER
    # (60), damit die Testfolge nicht zwischendrin zuruckgesetzt wird.
    boden = marke - 2.0
    tag2 = []
    for _ in range(4):
        tag2 += list(np.linspace(boden + 30, boden, 25))
        tag2 += list(np.linspace(boden, boden + 30, 25))
    df = _rahmen(_vortag(20050.0, marke) + tag2, config)

    ereignisse = niveau_ereignisse(df)
    tests = [
        e for e in ereignisse
        if e.pattern_type == "niveau_test" and e.pattern_variant == "pdl"
    ]
    assert tests, "Kein Test des Vortagestiefs erkannt"
    assert max(e.merkmale["test_nummer"] for e in tests) >= 2


def test_ausbruch_und_retest(config):
    pdh = 20080.0
    tag2 = (
        list(np.linspace(20010, pdh + 30, 150))     # Ausbruch nach oben
        + list(np.linspace(pdh + 30, pdh + 1, 80))  # Retest von oben
        + list(np.linspace(pdh + 1, pdh + 60, 150)) # Fortsetzung
    )
    df = _rahmen(_vortag(pdh, 19950.0) + tag2, config)

    ereignisse = niveau_ereignisse(df)
    typen = {(e.pattern_type, e.pattern_variant) for e in ereignisse}
    assert ("ausbruch", "pdh") in typen
    assert ("ausbruch_retest", "pdh") in typen


def test_fehlausbruch_dreht_die_richtung(config):
    pdh = 20080.0
    tag2 = (
        list(np.linspace(20010, pdh + 15, 40))       # kurzer Ausbruch
        + list(np.linspace(pdh + 15, pdh - 40, 30))  # faellt klar zurueck
    )
    df = _rahmen(_vortag(pdh, 19950.0) + tag2, config)

    ereignisse = niveau_ereignisse(df)
    fehl = [e for e in ereignisse if e.pattern_type == "fehlausbruch"]
    assert fehl, "Kein Fehlausbruch erkannt"
    assert fehl[0].direction == -1


def test_jedes_ereignis_haelt_die_phasenordnung(config):
    rng = np.random.default_rng(7)
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, 3000)))
    df = _rahmen(preise, config)
    ereignisse = niveau_ereignisse(df)
    assert ereignisse
    for e in ereignisse:
        assert e.entstehung_idx <= e.bestaetigung_idx <= e.verfuegbar_idx


def test_kein_lookahead(config):
    rng = np.random.default_rng(11)
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, 4000)))
    df = _rahmen(preise, config)

    schnitt = 2500
    voll = niveau_ereignisse(df)
    kurz = niveau_ereignisse(df.iloc[:schnitt])

    voll_frueh = [
        (e.pattern_type, e.pattern_variant, e.entstehung_idx, e.verfuegbar_idx)
        for e in voll if e.verfuegbar_idx < schnitt
    ]
    kurz_liste = [
        (e.pattern_type, e.pattern_variant, e.entstehung_idx, e.verfuegbar_idx)
        for e in kurz
    ]
    assert voll_frueh == kurz_liste


def test_ohne_atr_bricht_es_ab(config):
    df = pd.DataFrame(
        {
            "open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3],
            "close": [1, 2, 3], "volume": [1, 1, 1],
        },
        index=pd.date_range("2026-01-05", periods=3, freq="1min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="atr"):
        niveau_ereignisse(df)
