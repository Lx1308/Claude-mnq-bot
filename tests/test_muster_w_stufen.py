"""Die Bestaetigungsleiter - vor allem: kein Lookahead, kein Zaehlen von
gruenen Kerzen, und der Bruch beendet das Muster.

Die Leiter ist der Kern von Laurins Auftrag vom 03.09.2026: nicht EINEN
Einstieg festlegen, sondern mehrere messen und die Daten entscheiden lassen.
Diese Tests halten fest, dass die Sprossen bedeuten, was sie behaupten.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.muster_w_stufen import (
    Leiter,
    struktur_stufen,
    weg_stufen,
)


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    index = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    return pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": [500.0] * len(kerzen)}, index=index)


def _treppe(schritte: list[float], start: float = 100.0) -> pd.DataFrame:
    """Kerzen, deren Hoch genau die vorgegebenen Werte annimmt."""
    kerzen = []
    kurs = start
    for ziel in schritte:
        kerzen.append((kurs, max(kurs, ziel), min(kurs, ziel), ziel))
        kurs = ziel
    return _rahmen(kerzen)


# -- Weg-Stufen ------------------------------------------------------------

def test_sprossen_liegen_auf_den_richtigen_kursen():
    """Tief2 100, Nackenlinie 200: die 25-%-Sprosse liegt bei 125."""
    df = _treppe([100, 110, 120, 126, 140, 160, 200, 205])
    leiter = weg_stufen(df, np.array([0]), np.array([100.0]),
                        np.array([200.0]), stufen=(0.25, 0.50, 1.00),
                        horizont=10)
    # Kerze 3 hat das Hoch 126 -> erste Beruehrung von 125
    assert leiter.erreicht[0, 0] == 3
    assert leiter.erreicht[0, 1] == 5      # Hoch 160 >= 150
    assert leiter.erreicht[0, 2] == 6      # Hoch 200 >= 200
    # Einstieg immer zur Eroeffnung der Folgekerze.
    assert (leiter.einstieg[0] == leiter.erreicht[0] + 1).all()


def test_hoehere_sprossen_liegen_nie_frueher():
    """Sonst waere die Leiter keine Leiter."""
    rng = np.random.default_rng(4)
    p = 100 + np.cumsum(rng.normal(0, 1.0, 3000))
    df = _rahmen([(x, x + 1.5, x - 1.5, x) for x in p])
    n = 200
    start = rng.integers(10, 2500, n)
    tief2 = np.array([df["low"].to_numpy()[s] - 2.0 for s in start])
    hals = tief2 + 20.0
    leiter = weg_stufen(df, start, tief2, hals, horizont=300)
    for k in range(leiter.erreicht.shape[1] - 1):
        frueh, spaet = leiter.erreicht[:, k], leiter.erreicht[:, k + 1]
        beide = (frueh >= 0) & (spaet >= 0)
        assert (frueh[beide] <= spaet[beide]).all()


def test_bruch_unter_den_zweiten_boden_beendet_die_leiter():
    """Laurins Punkt: nach dem Durchbruch ist es kein W mehr.

    Der Kurs faellt erst unter 100 und steigt DANACH auf 190. Keine Sprosse
    darf zaehlen - wer dort einstiege, handelte einen Abwaertsausbruch.
    """
    df = _treppe([100, 110, 95, 120, 150, 190])
    leiter = weg_stufen(df, np.array([0]), np.array([100.0]),
                        np.array([200.0]), stufen=(0.25, 0.50),
                        horizont=10)
    assert (leiter.erreicht[0] == -1).all()
    assert leiter.bruch[0] == 2


def test_sprosse_vor_dem_bruch_zaehlt_weiter():
    df = _treppe([100, 130, 95, 190])
    leiter = weg_stufen(df, np.array([0]), np.array([100.0]),
                        np.array([200.0]), stufen=(0.25, 0.50),
                        horizont=10)
    assert leiter.erreicht[0, 0] == 1      # 130 >= 125, vor dem Bruch
    assert leiter.erreicht[0, 1] == -1     # 150 erst nach dem Bruch
    assert leiter.bruch[0] == 2


def test_gleichzeitiger_bruch_und_sprosse_zaehlt_als_bruch():
    """Intrabar-Konvention wie in der Engine: der Stop gilt."""
    df = _rahmen([(100, 100, 100, 100), (100, 190, 95, 120)])
    leiter = weg_stufen(df, np.array([0]), np.array([100.0]),
                        np.array([200.0]), stufen=(0.25,), horizont=5)
    assert leiter.erreicht[0, 0] == -1
    assert leiter.bruch[0] == 1


def test_quote_faellt_mit_der_sprossenhoehe():
    rng = np.random.default_rng(7)
    p = 100 + np.cumsum(rng.normal(0, 1.0, 5000))
    df = _rahmen([(x, x + 1.5, x - 1.5, x) for x in p])
    start = rng.integers(10, 4000, 400)
    tief2 = np.array([df["low"].to_numpy()[s] - 3.0 for s in start])
    leiter = weg_stufen(df, start, tief2, tief2 + 25.0, horizont=200)
    q = leiter.quote()
    assert (np.diff(q) <= 1e-12).all(), "hoehere Sprossen muessen seltener sein"
    assert q[0] > q[-1]


# -- Struktur-Stufen -------------------------------------------------------

def test_durchlaufende_rally_ist_nicht_vier_bestaetigungen():
    """Ohne Korrektur gibt es keinen zweiten Schenkel.

    Genau das meint Laurin mit 'nicht einfach gruene Kerzen zaehlen': eine
    Bewegung ohne Ruecksetzer ist EINE Bewegung, auch wenn sie aus zwanzig
    gruenen Kerzen besteht.
    """
    df = _treppe([100 + 5 * i for i in range(20)])
    leiter = struktur_stufen(df, np.array([0]), np.array([100.0]),
                             np.array([200.0]), zickzack_anteil=0.10,
                             max_stufen=4, horizont=25)
    assert leiter.erreicht[0, 0] >= 0
    assert (leiter.erreicht[0, 1:] == -1).all()


def test_zwei_schenkel_mit_korrektur_dazwischen():
    # hoch auf 115, zurueck auf 100 (Korrektur 15 = 15 % der Hoehe 100),
    # dann weiter auf 140.
    df = _treppe([100, 108, 115, 108, 100, 112, 125, 140])
    leiter = struktur_stufen(df, np.array([0]), np.array([100.0]),
                             np.array([200.0]), zickzack_anteil=0.10,
                             max_stufen=4, horizont=20)
    assert leiter.erreicht[0, 0] == 2      # 115 - 100 = 15 >= 10
    assert leiter.erreicht[0, 1] > leiter.erreicht[0, 0]
    assert leiter.erreicht[0, 2] == -1


def test_zu_kleine_bewegung_ist_kein_schenkel():
    df = _treppe([100, 104, 101, 105, 102, 106])
    leiter = struktur_stufen(df, np.array([0]), np.array([100.0]),
                             np.array([200.0]), zickzack_anteil=0.10,
                             max_stufen=4, horizont=20)
    assert (leiter.erreicht[0] == -1).all(), (
        "kein Schenkel erreicht die Mindestbewegung von 10 Punkten"
    )


def test_groessere_mindestbewegung_liefert_weniger_stufen():
    rng = np.random.default_rng(11)
    p = 100 + np.cumsum(rng.normal(0.02, 1.0, 4000))
    df = _rahmen([(x, x + 1.2, x - 1.2, x) for x in p])
    start = rng.integers(10, 3000, 200)
    tief2 = np.array([df["low"].to_numpy()[s] - 3.0 for s in start])
    hals = tief2 + 30.0
    fein = struktur_stufen(df, start, tief2, hals, zickzack_anteil=0.10,
                           horizont=250)
    grob = struktur_stufen(df, start, tief2, hals, zickzack_anteil=0.30,
                           horizont=250)
    assert (grob.erreicht >= 0).sum() < (fein.erreicht >= 0).sum()


def test_struktur_bruch_beendet_ebenfalls():
    df = _treppe([100, 115, 95, 130, 160])
    leiter = struktur_stufen(df, np.array([0]), np.array([100.0]),
                             np.array([200.0]), zickzack_anteil=0.10,
                             max_stufen=4, horizont=20)
    assert leiter.bruch[0] == 2
    assert leiter.erreicht[0, 0] == 1      # der Schenkel VOR dem Bruch zaehlt
    assert (leiter.erreicht[0, 1:] == -1).all()


# -- Kein Lookahead --------------------------------------------------------

def test_kein_lookahead_bei_abgeschnittener_reihe():
    """Was die halbe Reihe liefert, muss die ganze identisch liefern.

    Die Sprossen duerfen nur von Kerzen bis zu ihrem eigenen Zeitpunkt
    abhaengen - nie davon, wie es danach weiterging.
    """
    rng = np.random.default_rng(21)
    p = 100 + np.cumsum(rng.normal(0, 1.0, 6000))
    df = _rahmen([(x, x + 1.5, x - 1.5, x) for x in p])
    schnitt = 3000
    kurz = df.iloc[:schnitt]

    start = np.arange(200, 2500, 37)
    tief2 = df["low"].to_numpy()[start] - 2.0
    hals = tief2 + 20.0
    horizont = 200

    voll = weg_stufen(df, start, tief2, hals, horizont=horizont)
    teil = weg_stufen(kurz, start, tief2, hals, horizont=horizont)

    # Nur Muster mit vollem Fenster in der kurzen Reihe vergleichen.
    passt = start + horizont < schnitt
    assert passt.sum() > 50
    assert (voll.erreicht[passt] == teil.erreicht[passt]).all()
    assert (voll.bruch[passt] == teil.bruch[passt]).all()

    s_voll = struktur_stufen(df, start, tief2, hals, zickzack_anteil=0.15,
                             horizont=horizont)
    s_teil = struktur_stufen(kurz, start, tief2, hals, zickzack_anteil=0.15,
                             horizont=horizont)
    assert (s_voll.erreicht[passt] == s_teil.erreicht[passt]).all()


# -- Randfaelle ------------------------------------------------------------

def test_nackenlinie_unter_dem_boden_bricht_ab():
    df = _treppe([100, 110])
    with pytest.raises(ValueError, match="Nackenlinie"):
        weg_stufen(df, np.array([0]), np.array([100.0]), np.array([90.0]),
                   horizont=5)


def test_unsortierte_stufen_brechen_ab():
    df = _treppe([100, 110])
    with pytest.raises(ValueError, match="aufsteigend"):
        weg_stufen(df, np.array([0]), np.array([100.0]), np.array([200.0]),
                   stufen=(0.5, 0.25), horizont=5)


def test_leiter_prueft_ihre_form():
    with pytest.raises(ValueError, match="Spalten"):
        Leiter(stufen=(0.1, 0.2), erreicht=np.zeros((3, 1), dtype=np.int64),
               einstieg=np.zeros((3, 1), dtype=np.int64),
               bruch=np.zeros(3, dtype=np.int64))
