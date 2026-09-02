"""Ziel vor Stop - erste Beruehrung, nicht Zeit bis zum Extremum.

Der wichtigste Test ist ``test_ziel_zuerst_auch_wenn_das_maximum_spaeter_kommt``:
genau daran scheitert die Naeherung in ``backtest/conditional_outcomes.py``,
und der Fehler verzerrt die Trefferquote systematisch nach unten.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.barrieren import (
    NICHT_ERREICHT,
    barrieren_raster,
    erste_beruehrung,
    zufalls_nulllinie,
)
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _fest(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """OHLC von Hand, damit man das Ergebnis nachrechnen kann."""
    index = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    df = pd.DataFrame(
        {
            "open": [k[0] for k in kerzen],
            "high": [k[1] for k in kerzen],
            "low": [k[2] for k in kerzen],
            "close": [k[3] for k in kerzen],
            "volume": [500.0] * len(kerzen),
        },
        index=index,
    )
    df["atr"] = 10.0
    return df


def _rausch(n: int = 3000, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20000.0 + np.cumsum(rng.normal(0, 6, n))
    s = np.abs(rng.normal(4, 1.5, n)) + 0.5
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s, "close": p, "volume": 500.0},
        index=idx,
    )


# -- erste Beruehrung ------------------------------------------------------

def test_erste_beruehrung_ist_einsbasiert():
    df = _fest([(100, 105, 95, 100), (100, 120, 99, 118), (118, 125, 117, 124)])
    # Schwelle 110 nach oben, Einstieg bei Kerze 0: Kerze 1 (high 120) trifft.
    zeit = erste_beruehrung(df, np.array([0]), np.array([110.0]), 3,
                            nach_oben=True)
    assert zeit[0] == 2, "Kerze 1 ist der zweite Schritt im Fenster"


def test_beruehrung_in_der_einstiegskerze_zaehlt_als_eins():
    df = _fest([(100, 115, 95, 110), (110, 111, 109, 110)])
    zeit = erste_beruehrung(df, np.array([0]), np.array([110.0]), 2,
                            nach_oben=True)
    assert zeit[0] == 1


def test_nicht_erreicht_bleibt_offen():
    df = _fest([(100, 101, 99, 100)] * 5)
    zeit = erste_beruehrung(df, np.array([0]), np.array([200.0]), 5,
                            nach_oben=True)
    assert zeit[0] == NICHT_ERREICHT


def test_nach_unten_prueft_gegen_das_tief():
    df = _fest([(100, 101, 99, 100), (100, 101, 80, 85)])
    zeit = erste_beruehrung(df, np.array([0]), np.array([90.0]), 2,
                            nach_oben=False)
    assert zeit[0] == 2


# -- Der Fehler in der alten Naeherung ------------------------------------

def test_ziel_zuerst_auch_wenn_das_maximum_spaeter_kommt():
    """Der Kern.

    Ziel 1R wird in Kerze 1 erreicht, danach faellt der Kurs auf -2R und
    steigt spaeter auf +3R. Die Naeherung ueber ``time_to_mfe`` (Zeit bis zum
    MAXIMUM = spaet) gegen ``time_to_mae`` (frueh) bucht hier "Stop zuerst" -
    obwohl das Ziel laengst erreicht war.
    """
    atr = 10.0
    kerzen = [
        (100, 100, 100, 100),      # 0: Ereigniskerze
        (100, 112, 99, 110),       # 1: Einstieg 100, Ziel 1R=110 SOFORT erreicht
        (110, 111, 78, 80),        # 2: faellt auf -2R (Stop 1R=90 waere hier)
        (80, 135, 79, 132),        # 3: Maximum +3R - aber viel spaeter
    ]
    df = _fest(kerzen)
    df["atr"] = atr

    ergebnis = barrieren_raster(
        df, np.array([0]), np.array([1]), horizont=3,
        ziele=(1.0,), stops=(1.0,),
    )
    assert len(ergebnis) == 1
    e = ergebnis[0]
    assert e.ziel_zuerst == 1, (
        "Ziel wurde in Kerze 1 erreicht, Stop erst in Kerze 2 - "
        "das ist ein Gewinn"
    )
    assert e.stop_zuerst == 0


# -- Intrabar-Konvention --------------------------------------------------

def test_bei_gleichstand_gilt_der_stop():
    """Beruehrt eine Kerze Ziel UND Stop, ist aus OHLC nicht rekonstruierbar,
    was zuerst kam. Konvention wie in der Engine: der Stop (Invariante 4)."""
    kerzen = [
        (100, 100, 100, 100),
        (100, 115, 85, 100),       # eine Kerze, die 1R hoch UND 1R runter geht
    ]
    df = _fest(kerzen)
    ergebnis = barrieren_raster(
        df, np.array([0]), np.array([1]), horizont=1,
        ziele=(1.0,), stops=(1.0,),
    )[0]
    assert ergebnis.stop_zuerst == 1
    assert ergebnis.ziel_zuerst == 0
    assert ergebnis.ambig == 1
    assert ergebnis.ambig_anteil == 1.0


def test_ambig_anteil_wird_ausgewiesen():
    """Ist der Anteil hoch, haengt das Ergebnis an der Annahme - das muss
    sichtbar sein, nicht verschwiegen."""
    df = compute_indicators(_rausch(2000), Config.load(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "config.yaml"
    ).indicators, Config.load(
        __import__("pathlib").Path(__file__).resolve().parents[1] / "config.yaml"
    ).market.session)
    ergebnis = barrieren_raster(
        df, np.arange(100, 1500, 7), np.ones(200, dtype=int)[:len(np.arange(100, 1500, 7))],
        horizont=60, ziele=(0.5,), stops=(0.5,),
    )
    assert 0.0 <= ergebnis[0].ambig_anteil <= 1.0


# -- Short spiegelt sich ---------------------------------------------------

def test_short_spiegelt_die_richtung():
    kerzen = [
        (100, 100, 100, 100),
        (100, 101, 88, 90),        # faellt: fuer den Short ist das das ZIEL
    ]
    df = _fest(kerzen)
    long = barrieren_raster(df, np.array([0]), np.array([1]), horizont=1,
                            ziele=(1.0,), stops=(1.0,))[0]
    short = barrieren_raster(df, np.array([0]), np.array([-1]), horizont=1,
                             ziele=(1.0,), stops=(1.0,))[0]
    assert long.stop_zuerst == 1 and long.ziel_zuerst == 0
    assert short.ziel_zuerst == 1 and short.stop_zuerst == 0


# -- Erwartungswert --------------------------------------------------------

def test_erwartungswert_rechnet_ziel_und_stop_gegeneinander():
    from common.ereignisse.barrieren import Barriereergebnis

    # 60 Gewinne a 2R, 40 Verluste a 1R, keine Zeitablaeufe.
    e = Barriereergebnis(ziel_r=2.0, stop_r=1.0, horizont=60, n=100,
                         ziel_zuerst=60, stop_zuerst=40, keins=0, ambig=0)
    assert e.trefferquote == pytest.approx(0.6)
    assert e.erwartungswert_r() == pytest.approx((60 * 2 - 40 * 1) / 100)
    assert e.erwartungswert_r(kosten_r=0.2) == pytest.approx(0.8 - 0.2)


def test_zeitablauf_wird_mit_null_gewertet():
    """Vorsichtige Annahme: in Wahrheit steht dort irgendetwas zwischen Ziel
    und Stop. Die Zahl ist damit eine Untergrenze."""
    from common.ereignisse.barrieren import Barriereergebnis

    e = Barriereergebnis(ziel_r=1.0, stop_r=1.0, horizont=60, n=100,
                         ziel_zuerst=30, stop_zuerst=30, keins=40, ambig=0)
    assert e.trefferquote == pytest.approx(0.5), "Quote nur ueber Entschiedene"
    assert e.erwartungswert_r() == pytest.approx(0.0)


# -- Filter und Randfaelle -------------------------------------------------

def test_unvollstaendiges_fenster_wird_verworfen(config):
    df = compute_indicators(_rausch(200), config.indicators,
                            config.market.session)
    ergebnis = barrieren_raster(
        df, np.array([50, 195]), np.array([1, 1]), horizont=20,
        ziele=(1.0,), stops=(1.0,),
    )
    assert ergebnis[0].n == 1, "das Ereignis am Reihenende gehoert verworfen"


def test_winzige_atr_wird_verworfen():
    df = _fest([(100, 101, 99, 100)] * 50)
    df["atr"] = 0.01
    ergebnis = barrieren_raster(
        df, np.array([0, 10]), np.array([1, 1]), horizont=20,
        ziele=(1.0,), stops=(1.0,),
    )
    assert ergebnis == [], "ATR von 0,01 ist kein Marktzustand"


def test_raster_liefert_jede_kombination(config):
    df = compute_indicators(_rausch(3000), config.indicators,
                            config.market.session)
    idx = np.arange(100, 2000, 11)
    ergebnis = barrieren_raster(
        df, idx, np.ones(len(idx), dtype=int), horizont=60,
        ziele=(1.0, 2.0), stops=(1.0, 2.0),
    )
    assert len(ergebnis) == 4
    assert {(e.ziel_r, e.stop_r) for e in ergebnis} == {
        (1.0, 1.0), (1.0, 2.0), (2.0, 1.0), (2.0, 2.0)
    }


def test_weiteres_ziel_wird_seltener_zuerst_erreicht(config):
    """Plausibilitaet: ein Ziel weiter weg kann nicht haeufiger vor demselben
    Stop erreicht werden als ein naeheres."""
    df = compute_indicators(_rausch(4000), config.indicators,
                            config.market.session)
    idx = np.arange(100, 3000, 7)
    ergebnis = {
        (e.ziel_r, e.stop_r): e
        for e in barrieren_raster(
            df, idx, np.ones(len(idx), dtype=int), horizont=120,
            ziele=(0.5, 1.0, 2.0), stops=(1.0,),
        )
    }
    assert (ergebnis[(0.5, 1.0)].trefferquote
            >= ergebnis[(1.0, 1.0)].trefferquote
            >= ergebnis[(2.0, 1.0)].trefferquote)


def test_nulllinie_laeuft_und_liefert_dasselbe_raster(config):
    df = compute_indicators(_rausch(3000), config.indicators,
                            config.market.session)
    null = zufalls_nulllinie(df, 1, horizont=30, anzahl=500,
                             ziele=(1.0,), stops=(1.0,))
    assert len(null) == 1
    assert null[0].n > 0


def test_ungueltige_richtung_bricht_ab(config):
    df = compute_indicators(_rausch(500), config.indicators,
                            config.market.session)
    with pytest.raises(ValueError, match="richtung"):
        barrieren_raster(df, np.array([10]), np.array([0]), horizont=10)
