"""Der nachgezogene Stop - Buchhaltung und Konventionen.

Laurins Vorgabe vom 03.09.2026: kein festes Ziel, nur ein Trailing-Stop, und
der Prozentsatz soll so gefunden werden, dass *"eine kleine Gegenkorrektur
das nicht ausloest aber ein echter Einbruch da rein geht"*.

Diese Tests halten fest, dass der Stop tut, was er verspricht: nur nach oben,
erst ab der Aktivierung, und pessimistisch dort, wo die Kerze beides zulaesst.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.trailing import Ausstieg, trailing_ausstieg


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                        tz="UTC")
    return pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": 500.0}, index=idx)


def _lauf(kerzen, *, einstieg=0, kurs=100.0, stop=90.0, rueckgabe=0.2,
          aktivierung=0.0, horizont=None):
    df = _rahmen(kerzen)
    h = horizont if horizont is not None else len(kerzen) - einstieg
    return trailing_ausstieg(
        df, np.array([einstieg]), np.array([kurs]), np.array([stop]),
        rueckgabe=rueckgabe, aktivierung_pkt=np.array([aktivierung]),
        horizont=h)


# -- Der Stop geht nur nach oben -------------------------------------------

def test_ohne_gewinn_gilt_der_urspruengliche_stop():
    """Faellt der Kurs sofort, ist der Ausstieg der Startstop."""
    a = _lauf([(100, 100.5, 89, 90), (90, 91, 88, 89)])
    assert a.grund[0] == Ausstieg.STOP
    assert a.preis[0] == pytest.approx(90.0)
    assert a.kerze[0] == 0


def test_der_nachgezogene_stop_steigt_mit_dem_gewinnhoch():
    """Gewinnhoch 40, Rueckgabe 20 % -> Stop bei 100 + 32 = 132."""
    kerzen = [(100, 140, 99, 138),      # Gewinnhoch 40
              (138, 139, 131, 132)]     # faellt auf 131 -> unter 132
    a = _lauf(kerzen, rueckgabe=0.2)
    assert a.grund[0] == Ausstieg.TRAILING
    assert a.preis[0] == pytest.approx(132.0)
    assert a.spitze[0] == pytest.approx(40.0)


def test_der_stop_faellt_nie_zurueck():
    """Nach einem Hoch von 40 darf ein spaeteres Hoch von 10 nicht
    dazu fuehren, dass der Stop wieder sinkt."""
    kerzen = [(100, 140, 99, 138),      # Hoch 140 -> Stop 132
              (138, 139, 133, 134),     # haelt knapp
              (134, 135, 131, 132)]     # jetzt drunter
    a = _lauf(kerzen, rueckgabe=0.2)
    assert a.kerze[0] == 2
    assert a.preis[0] == pytest.approx(132.0)


def test_kleine_gegenkorrektur_loest_nicht_aus():
    """Genau Laurins Bedingung: 10 % Ruecksetzer bei 20 % Rueckgabe."""
    kerzen = [(100, 140, 99, 138),      # Gewinnhoch 40, Stop bei 132
              (138, 139, 136, 137),     # nur bis 136 zurueck
              (137, 160, 136, 158),     # weiter hoch, Stop jetzt 148
              (158, 159, 150, 152)]     # 150 haelt ueber 148
    a = _lauf(kerzen, rueckgabe=0.2)
    assert a.grund[0] == Ausstieg.ZEIT, "kein Ruecksetzer war tief genug"


def test_echter_einbruch_loest_aus():
    kerzen = [(100, 160, 99, 158),      # Gewinnhoch 60, Stop bei 148
              (158, 159, 140, 142)]     # bricht durch
    a = _lauf(kerzen, rueckgabe=0.2)
    assert a.grund[0] == Ausstieg.TRAILING
    assert a.preis[0] == pytest.approx(148.0)


# -- Die Aktivierung -------------------------------------------------------

def test_unter_der_aktivierung_zieht_nichts_nach():
    """Bei 8 Punkten Gewinn und Aktivierung 20 gilt weiter der Startstop."""
    kerzen = [(100, 108, 99, 107),      # Gewinnhoch nur 8
              (107, 108, 100, 101),     # faellt zurueck, aber ueber 90
              (101, 102, 89, 90)]       # erst hier der Startstop
    a = _lauf(kerzen, rueckgabe=0.2, aktivierung=20.0)
    assert a.grund[0] == Ausstieg.STOP
    assert a.kerze[0] == 2


def test_die_aktivierung_verhindert_den_fruehen_rauswurf():
    """Ohne Aktivierung wirft ein Mini-Gewinn sofort raus, mit nicht.

    Das ist der Fall, den Laurin meint: zwei Punkte im Plus, 20 % davon sind
    0,4 Punkte - das loest der naechste Tick aus.
    """
    kerzen = [(100, 102, 99.5, 101),    # Gewinnhoch 2 -> Stop 101.6
              (101, 101.5, 101.0, 101.2),
              (101.2, 130, 101, 128)]   # danach laeuft es
    ohne = _lauf(kerzen, rueckgabe=0.2, aktivierung=0.0)
    mit = _lauf(kerzen, rueckgabe=0.2, aktivierung=10.0)
    assert ohne.grund[0] == Ausstieg.TRAILING and ohne.kerze[0] <= 1
    assert mit.grund[0] != Ausstieg.TRAILING or mit.kerze[0] > 1


# -- Konventionen ----------------------------------------------------------

def test_zeitablauf_wird_zum_schlusskurs_gebucht():
    kerzen = [(100, 105, 99, 104)] * 4
    a = _lauf(kerzen, rueckgabe=0.5, aktivierung=100.0)
    assert a.grund[0] == Ausstieg.ZEIT
    assert a.preis[0] == pytest.approx(104.0)


def test_der_stop_kennt_nur_die_kerzen_davor():
    """Eine Kerze kann ihren eigenen Trailing-Stop nicht ausloesen.

    Die Kerze geht von 100 auf 140 und faellt auf 89. Wuerde ihr eigenes
    Hoch den Stop setzen, saehe das nach einem Ausstieg bei 132 aus - einem
    Gewinn, den es nie gab. Richtig ist der urspruengliche Stop bei 90.
    """
    a = _lauf([(100, 140, 89, 91), (91, 92, 88, 89)], rueckgabe=0.2)
    assert a.grund[0] == Ausstieg.STOP
    assert a.preis[0] == pytest.approx(90.0)
    assert a.kerze[0] == 0


def test_luecken_werden_ausgewiesen_statt_versteckt():
    """Eroeffnet die Kerze unter dem Stop, waere die echte Fuellung
    schlechter als gebucht. Das muss sichtbar sein."""
    kerzen = [(100, 140, 139, 139),     # Gewinnhoch 40 -> Stop 132
              (120, 121, 119, 120)]     # eroeffnet mit Luecke bei 120
    a = _lauf(kerzen, rueckgabe=0.2)
    assert a.grund[0] == Ausstieg.TRAILING
    assert a.preis[0] == pytest.approx(132.0)
    assert a.luecke_anteil == 1.0


def test_groessere_rueckgabe_haelt_laenger():
    rng = np.random.default_rng(3)
    p = 100 + np.cumsum(rng.normal(0.02, 1.0, 3000))
    df = _rahmen([(x, x + 1.2, x - 1.2, x) for x in p])
    e = np.arange(100, 2500, 20)
    kurs = df["open"].to_numpy()[e]
    stop = kurs - 8.0
    akt = np.full(len(e), 2.0)
    kurz = trailing_ausstieg(df, e, kurs, stop, rueckgabe=0.10,
                             aktivierung_pkt=akt, horizont=200)
    lang = trailing_ausstieg(df, e, kurs, stop, rueckgabe=0.50,
                             aktivierung_pkt=akt, horizont=200)
    assert lang.kerze.mean() > kurz.kerze.mean()


# -- Randfaelle ------------------------------------------------------------

def test_stop_ueber_dem_einstieg_bricht_ab():
    df = _rahmen([(100, 101, 99, 100)] * 10)
    with pytest.raises(ValueError, match="UNTER dem Einstieg"):
        trailing_ausstieg(df, np.array([0]), np.array([100.0]),
                          np.array([101.0]), rueckgabe=0.2,
                          aktivierung_pkt=np.array([0.0]), horizont=5)


def test_unsinnige_rueckgabe_bricht_ab():
    df = _rahmen([(100, 101, 99, 100)] * 10)
    for wert in (0.0, 1.0, 1.5):
        with pytest.raises(ValueError, match="rueckgabe"):
            trailing_ausstieg(df, np.array([0]), np.array([100.0]),
                              np.array([90.0]), rueckgabe=wert,
                              aktivierung_pkt=np.array([0.0]), horizont=5)


def test_fenster_ausserhalb_der_reihe_bricht_ab():
    df = _rahmen([(100, 101, 99, 100)] * 10)
    with pytest.raises(ValueError, match="ausserhalb"):
        trailing_ausstieg(df, np.array([8]), np.array([100.0]),
                          np.array([90.0]), rueckgabe=0.2,
                          aktivierung_pkt=np.array([0.0]), horizont=5)
