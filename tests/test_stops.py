"""Der Stop unter dem letzten Tief - vor allem: kein Zukunftswissen.

Laurins Regel vom 03.09.2026: *"das SL immer unter das letzte Tief legen und
zudem ca 15 Punkte Abstand lassen ... aber max 100 Punkte SL-Abstand."*

Der kritische Teil ist die Verzoegerung. Ein Tief ist erst ``staerke`` Kerzen
spaeter bestaetigt; wer es frueher benutzt, benutzt die Zukunft.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.stops import (
    MAX_ABSTAND_PKT,
    STAERKE,
    letzte_tiefs,
    stop_unter_dem_tief,
)


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                        tz="UTC")
    return pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": 500.0}, index=idx)


def _rausch(n: int = 20_000, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20_000.0 + np.cumsum(rng.normal(0, 3, n))
    s = np.abs(rng.normal(2.5, 1.0, n)) + 0.5
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s,
         "close": p + rng.normal(0, 1.5, n), "volume": 500.0}, index=idx
    ).assign(
        high=lambda d: d[["high", "open", "close"]].max(axis=1),
        low=lambda d: d[["low", "open", "close"]].min(axis=1),
    )


# -- Kein Zukunftswissen ---------------------------------------------------

def test_ein_tief_gilt_erst_nach_seiner_bestaetigung():
    """Das Tief bei Index 20 darf erst ab Index 26 benutzt werden."""
    kerzen = [(100, 101, 99, 100)] * 20
    kerzen += [(100, 100.5, 90, 91)]          # Index 20: das Tief
    kerzen += [(91, 95, 90.5, 94)] * 20
    df = _rahmen(kerzen)
    tiefs = letzte_tiefs(df, staerke=STAERKE)
    assert np.isnan(tiefs[20]) or tiefs[20] != 90.0, (
        "das Tief darf in seiner eigenen Kerze noch nicht bekannt sein"
    )
    assert tiefs[20 + STAERKE] == pytest.approx(90.0)


def test_abschneiden_aendert_nichts_am_vergangenen():
    """Was auf der halben Reihe gilt, muss auf der ganzen identisch gelten."""
    df = _rausch(20_000)
    schnitt = 10_000
    voll = letzte_tiefs(df)
    kurz = letzte_tiefs(df.iloc[:schnitt])
    puffer = STAERKE + 2
    a, b = voll[:schnitt - puffer], kurz[:schnitt - puffer]
    beide = np.isfinite(a) & np.isfinite(b)
    assert beide.sum() > 5_000
    assert np.allclose(a[beide], b[beide])


def test_das_letzte_tief_wird_fortgeschrieben():
    """Zwischen zwei Tiefs gilt weiterhin das aeltere."""
    kerzen = [(100, 101, 99, 100)] * 20
    kerzen += [(100, 100.5, 90, 91)]
    kerzen += [(91, 95, 90.5, 94)] * 30
    df = _rahmen(kerzen)
    tiefs = letzte_tiefs(df)
    for i in range(20 + STAERKE, 45):
        assert tiefs[i] == pytest.approx(90.0)


def test_ein_neueres_tief_loest_das_aeltere_ab():
    kerzen = [(100, 101, 99, 100)] * 20
    kerzen += [(100, 100.5, 90, 91)]          # erstes Tief
    kerzen += [(91, 96, 90.5, 95)] * 20
    kerzen += [(95, 96, 85, 86)]              # zweites, tieferes
    kerzen += [(86, 92, 85.5, 91)] * 20
    df = _rahmen(kerzen)
    tiefs = letzte_tiefs(df)
    assert tiefs[35] == pytest.approx(90.0)
    assert tiefs[41 + STAERKE] == pytest.approx(85.0)


# -- Die Regel selbst ------------------------------------------------------

def test_der_stop_liegt_um_den_puffer_unter_dem_tief():
    """Laurins Beispiel: Tief 29.275, 15 Punkte Puffer -> 29.260."""
    stop, gut = stop_unter_dem_tief(
        np.array([29_310.0]), np.array([29_275.0]), puffer_pkt=15.0)
    assert stop[0] == pytest.approx(29_260.0)
    assert gut[0]


def test_zu_weiter_stop_faellt_heraus_statt_gekuerzt_zu_werden():
    """Ein gekuerzter Stop haengt nicht mehr an der Struktur.

    Er saehe aus wie die Regel, waere aber eine andere - und die Messung
    wuerde etwas anderes messen, als sie behauptet.
    """
    stop, gut = stop_unter_dem_tief(
        np.array([29_500.0]), np.array([29_300.0]), puffer_pkt=15.0)
    assert stop[0] == pytest.approx(29_285.0)
    assert not gut[0], "215 Punkte Abstand darf nicht durchgehen"
    assert MAX_ABSTAND_PKT == 100.0


def test_zu_enger_stop_faellt_heraus():
    stop, gut = stop_unter_dem_tief(
        np.array([100.0]), np.array([99.5]), puffer_pkt=0.0)
    assert not gut[0]


def test_ohne_bekanntes_tief_kein_trade():
    stop, gut = stop_unter_dem_tief(
        np.array([100.0]), np.array([np.nan]), puffer_pkt=15.0)
    assert not gut[0]


def test_groesserer_puffer_erhoeht_das_risiko():
    einstieg = np.full(5, 100.0)
    tief = np.full(5, 90.0)
    eng, _ = stop_unter_dem_tief(einstieg, tief, puffer_pkt=5.0)
    weit, _ = stop_unter_dem_tief(einstieg, tief, puffer_pkt=20.0)
    assert (einstieg - weit > einstieg - eng).all()


def test_negativer_puffer_bricht_ab():
    with pytest.raises(ValueError, match="UNTER das Tief"):
        stop_unter_dem_tief(np.array([100.0]), np.array([90.0]),
                            puffer_pkt=-1.0)
