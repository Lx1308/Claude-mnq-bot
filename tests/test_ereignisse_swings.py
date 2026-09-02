"""Vektorisierte Swing-Serie - Gleichheit mit find_swing_points, kein Lookahead.

Die Ereignisdatenbank baut fast alle Strukturmuster auf Swings auf. Wenn diese
Serie von ``common/structure.py::find_swing_points`` abweicht, testet die
Datenbank ein anderes Marktbild als der Rest des Projekts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.ereignisse.swings import STANDARD_STRENGTH, swing_serie
from common.structure import find_swing_points


def _kurs(n: int = 3000, *, seed: int = 20260830) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    schritte = rng.normal(0.0, 4.0, n)
    for start in range(0, n, 250):
        schritte[start : start + 120] += rng.choice([-1.0, 1.0]) * 1.5
    preise = 20000.0 + np.cumsum(schritte)
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    spanne = np.abs(rng.normal(3.0, 1.0, n)) + 0.5
    return pd.DataFrame(
        {
            "open": preise,
            "high": preise + spanne,
            "low": preise - spanne,
            "close": preise + rng.normal(0.0, 0.5, n),
            "volume": rng.integers(100, 2000, n).astype(float),
        },
        index=index,
    )


@pytest.mark.parametrize("strength", [2, 3, 5])
def test_serie_findet_dieselben_swings_wie_find_swing_points(strength):
    df = _kurs()
    serie = swing_serie(df, strength=strength)

    punkte = find_swing_points(df, strength=strength)
    letzter = len(df) - 1
    erwartet_hoch = {
        letzter - p.bars_ago for p in punkte if p.kind == "high"
    }
    erwartet_tief = {
        letzter - p.bars_ago for p in punkte if p.kind == "low"
    }

    serie_hoch = set(serie.hoch_ursprung_idx[serie.hoch_bestaetigt].tolist())
    serie_tief = set(serie.tief_ursprung_idx[serie.tief_bestaetigt].tolist())

    assert serie_hoch == erwartet_hoch
    assert serie_tief == erwartet_tief


def test_swing_ist_erst_strength_kerzen_spaeter_bestaetigt():
    df = _kurs(500)
    serie = swing_serie(df, strength=STANDARD_STRENGTH)

    for i in np.nonzero(serie.hoch_bestaetigt)[0]:
        ursprung = serie.hoch_ursprung_idx[i]
        assert i - ursprung == STANDARD_STRENGTH
        assert serie.hoch_preis[i] == pytest.approx(df["high"].iloc[ursprung])


def test_kein_lookahead():
    """Reihe abschneiden, Swings neu rechnen - was frueher bestaetigt war,
    muss identisch bleiben."""
    df = _kurs()
    schnitt = 2000
    voll = swing_serie(df, strength=3)
    kurz = swing_serie(df.iloc[:schnitt], strength=3)

    np.testing.assert_array_equal(
        voll.hoch_bestaetigt[:schnitt], kurz.hoch_bestaetigt
    )
    np.testing.assert_array_equal(
        voll.tief_bestaetigt[:schnitt], kurz.tief_bestaetigt
    )
    np.testing.assert_array_equal(
        voll.hoch_ursprung_idx[:schnitt], kurz.hoch_ursprung_idx
    )


def test_letzte_swings_schreiben_vorwaerts_fort():
    df = _kurs(400)
    serie = swing_serie(df, strength=3)
    preis, ursprung = serie.letzte_swings("tief")

    # Nach dem ersten bestaetigten Tief darf keine Luecke mehr sein.
    erstes = np.nonzero(serie.tief_bestaetigt)[0]
    if len(erstes):
        i0 = int(erstes[0])
        assert np.isnan(preis[i0 - 1]) if i0 > 0 else True
        assert not np.isnan(preis[i0:]).any()
        # Der fortgeschriebene Wert ist der zuletzt bestaetigte.
        assert preis[-1] == serie.tief_preis[erstes[-1]]


def test_leere_und_kurze_reihen():
    df = _kurs(4)
    serie = swing_serie(df, strength=3)
    assert not serie.hoch_bestaetigt.any()
    assert not serie.tief_bestaetigt.any()


def test_plateau_gibt_genau_einen_punkt():
    """Streng groesser links, groesser-gleich rechts - bei einem Plateau
    genau ein gemeldeter Swing, nicht mehrere."""
    preise = [10, 11, 12, 20, 20, 20, 12, 11, 10, 9, 8]
    n = len(preise)
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise, "high": preise, "low": preise,
            "close": preise, "volume": [100.0] * n,
        },
        index=index,
    )
    serie = swing_serie(df, strength=2)
    assert int(serie.hoch_bestaetigt.sum()) == 1
