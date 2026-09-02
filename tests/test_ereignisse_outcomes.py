"""Outcomes: MFE, MAE, Endergebnis je Horizont.

Der wichtigste Test ist die Gleichheit mit ``compute_path_excursions``: die
vektorisierte Fassung muss dieselbe Definition rechnen, sonst misst die
Ereignisdatenbank etwas anderes als der Rest des Projekts (Invariante 1).

Der zweitwichtigste ist ``test_unvollstaendiges_fenster_wird_verworfen``: ein
gekuerztes Fenster sieht aus wie ein vollstaendiges und verzerrt die
Statistik zum Reihenende hin.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.excursions import compute_path_excursions
from common.config import Config
from common.ereignisse.outcomes import (
    HORIZONTE,
    alle_horizonte,
    berechne_outcomes,
    vorwaertsfenster,
)
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _kurs(n: int = 2000, *, seed: int = 31) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 6.0, n))
    spanne = np.abs(rng.normal(4.0, 1.5, n)) + 0.5
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": preise + spanne,
            "low": preise - spanne,
            "close": preise + rng.normal(0.0, 1.0, n),
            "volume": rng.integers(100, 2000, n).astype(float),
        },
        index=index,
    )


def _fest(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """OHLC von Hand - fuer Faelle, die man nachrechnen koennen muss."""
    index = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    return pd.DataFrame(
        {
            "open": [k[0] for k in kerzen],
            "high": [k[1] for k in kerzen],
            "low": [k[2] for k in kerzen],
            "close": [k[3] for k in kerzen],
            "volume": [500.0] * len(kerzen),
        },
        index=index,
    )


# -- Vorwaertsfenster -------------------------------------------------------

def test_vorwaertsfenster_rechnet_von_der_position_an():
    df = _fest([
        (10, 12, 9, 11),     # 0
        (11, 15, 10, 14),    # 1
        (14, 14, 8, 9),      # 2
        (9, 20, 9, 19),      # 3
        (19, 19, 18, 18),    # 4
    ])
    f = vorwaertsfenster(df, 3)
    # Fenster ab 0: Kerzen 0,1,2 -> Hoch 15, Tief 8, Schluss von Kerze 2 = 9
    assert f.hoch[0] == 15.0
    assert f.tief[0] == 8.0
    assert f.schluss[0] == 9.0
    # Fenster ab 2: Kerzen 2,3,4 -> Hoch 20, Tief 8, Schluss 18
    assert f.hoch[2] == 20.0
    assert f.tief[2] == 8.0
    assert f.schluss[2] == 18.0
    # Ab Position 3 passt das 3er-Fenster nicht mehr.
    assert np.isnan(f.hoch[3])
    assert f.bis_hoch[3] == -1


def test_zeit_bis_extremum_ist_einsbasiert_und_nimmt_das_erste():
    df = _fest([
        (10, 20, 9, 19),     # 0: Hoch gleich in der ersten Kerze
        (19, 20, 18, 19),    # 1: gleiches Hoch, spaeter -> zaehlt nicht
        (19, 15, 5, 6),      # 2: Tief
    ])
    f = vorwaertsfenster(df, 3)
    assert f.bis_hoch[0] == 1, "erstes Auftreten des Maximums zaehlt"
    assert f.bis_tief[0] == 3


def test_fenster_ohne_zeiten_laesst_sie_leer():
    df = _kurs(200)
    f = vorwaertsfenster(df, 10, mit_zeiten=False)
    assert np.isfinite(f.hoch[0])
    assert (f.bis_hoch == -1).all()


def test_horizont_null_bricht_ab():
    with pytest.raises(ValueError, match="mindestens 1"):
        vorwaertsfenster(_kurs(100), 0)


# -- Gleichheit mit dem bestehenden Erkenner -------------------------------

@pytest.mark.parametrize("richtung_wert", [1, -1])
@pytest.mark.parametrize("horizont", [1, 5, 20, 60])
def test_gleich_mit_compute_path_excursions(config, horizont, richtung_wert):
    """Dieselbe Definition wie ``backtest/excursions.py`` - sonst misst die
    Ereignisdatenbank etwas anderes als der Rest des Projekts."""
    df = compute_indicators(_kurs(1200), config.indicators,
                            config.market.session)
    idx = np.arange(50, 1000, 7)

    alt = compute_path_excursions(
        df, list(idx), direction=richtung_wert, horizon_bars=horizont
    )
    neu = berechne_outcomes(
        df, idx, np.full(len(idx), richtung_wert), horizont
    )

    # compute_path_excursions ueberspringt nur Einstiege jenseits der Reihe
    # und KUERZT das Fenster am Ende; hier werden nur die vollstaendigen
    # verglichen.
    for k, alt_e in enumerate(alt):
        if alt_e.horizon_bars != horizont:
            continue           # dort hat die alte Fassung gekuerzt
        assert neu.gueltig[k], f"Ereignis {k} faelschlich verworfen"
        assert neu.entry_preis[k] == pytest.approx(alt_e.entry_price)
        assert neu.mfe_pkt[k] == pytest.approx(alt_e.mfe_points, abs=1e-9)
        assert neu.mae_pkt[k] == pytest.approx(alt_e.mae_points, abs=1e-9)
        assert neu.end_pkt[k] == pytest.approx(alt_e.final_points, abs=1e-9)
        assert neu.zeit_bis_mfe[k] == alt_e.time_to_mfe_bars
        assert neu.zeit_bis_mae[k] == alt_e.time_to_mae_bars


def test_r_bleibt_leer_ohne_atr_statt_auf_fuenf_zu_raten():
    """``compute_path_excursions`` setzt bei fehlendem ATR ersatzweise 5.0
    ein - eine erfundene Zahl, die aussieht wie eine Messung. Fuer eine
    Wissensbasis ist das der schwerste Fehler (Invariante 11)."""
    df = _kurs(300)              # ohne compute_indicators -> keine atr-Spalte
    assert "atr" not in df.columns

    o = berechne_outcomes(df, np.array([50, 100]), np.array([1, 1]), 10)
    assert np.isfinite(o.mfe_pkt).all(), "Punkte muessen trotzdem da sein"
    assert np.isnan(o.mfe_r).all()
    assert np.isnan(o.mae_r).all()
    assert np.isnan(o.end_r).all()


# -- Ausfuehrungsmodell -----------------------------------------------------

def test_einstieg_ist_die_eroeffnung_der_folgekerze(config):
    """Der Schlusskurs der Ereigniskerze ist nicht handelbar (Invariante 4)."""
    df = compute_indicators(_kurs(500), config.indicators,
                            config.market.session)
    o = berechne_outcomes(df, np.array([100]), np.array([1]), 10)
    assert o.entry_preis[0] == pytest.approx(float(df["open"].iloc[101]))


def test_atr_bezug_steht_auf_der_ereigniskerze(config):
    """Der ATR ist das, was zum Entscheidungszeitpunkt bekannt war - nicht
    der der Einstiegskerze."""
    df = compute_indicators(_kurs(500), config.indicators,
                            config.market.session)
    o = berechne_outcomes(df, np.array([100]), np.array([1]), 10)
    assert o.atr_referenz[0] == pytest.approx(float(df["atr"].iloc[100]))


def test_unvollstaendiges_fenster_wird_verworfen(config):
    """Kuerzen waere schlimmer als verwerfen: ein gekuerztes Fenster sieht aus
    wie ein vollstaendiges und verzerrt die Statistik zum Reihenende hin."""
    df = compute_indicators(_kurs(200), config.indicators,
                            config.market.session)
    # 198 + 1 (Einstieg) + 20 (Horizont) > 200
    o = berechne_outcomes(df, np.array([100, 198]), np.array([1, 1]), 20)
    assert o.gueltig[0]
    assert not o.gueltig[1]
    assert np.isnan(o.mfe_pkt[1])
    assert o.zeit_bis_mfe[1] == -1


# -- Richtung und Vorzeichen ------------------------------------------------

def test_long_und_short_spiegeln_sich():
    df = _fest([
        (100, 100, 100, 100),   # 0: Ereigniskerze
        (100, 110, 95, 105),    # 1: Einstieg zu 100
        (105, 120, 100, 118),   # 2
        (118, 119, 90, 92),     # 3
    ])
    long = berechne_outcomes(df, np.array([0]), np.array([1]), 3)
    short = berechne_outcomes(df, np.array([0]), np.array([-1]), 3)

    # Einstieg 100, Fenster = Kerzen 1..3: Hoch 120, Tief 90, Schluss 92
    assert long.mfe_pkt[0] == pytest.approx(20.0)
    assert long.mae_pkt[0] == pytest.approx(10.0)
    assert long.end_pkt[0] == pytest.approx(-8.0)

    assert short.mfe_pkt[0] == pytest.approx(10.0)
    assert short.mae_pkt[0] == pytest.approx(20.0)
    assert short.end_pkt[0] == pytest.approx(8.0)


def test_exkursionen_sind_nie_negativ():
    """Eine Bewegung, die nie ueber den Einstieg lief, hat MFE 0 - nicht
    'minus drei'."""
    df = _fest([
        (100, 100, 100, 100),
        (100, 100, 90, 91),     # Einstieg 100, geht nur runter
        (91, 92, 85, 86),
    ])
    o = berechne_outcomes(df, np.array([0]), np.array([1]), 2)
    assert o.mfe_pkt[0] == 0.0
    assert o.mae_pkt[0] == pytest.approx(15.0)
    assert o.end_pkt[0] == pytest.approx(-14.0)


def test_ungueltige_richtung_bricht_ab():
    df = _kurs(100)
    with pytest.raises(ValueError, match="richtung"):
        berechne_outcomes(df, np.array([10]), np.array([0]), 5)


def test_ungleiche_laengen_brechen_ab():
    df = _kurs(100)
    with pytest.raises(ValueError, match="gleich lang"):
        berechne_outcomes(df, np.array([10, 20]), np.array([1]), 5)


def test_fenster_mit_falschem_horizont_bricht_ab(config):
    df = compute_indicators(_kurs(300), config.indicators,
                            config.market.session)
    f = vorwaertsfenster(df, 10)
    with pytest.raises(ValueError, match="Horizont"):
        berechne_outcomes(df, np.array([50]), np.array([1]), 20, fenster=f)


# -- Prozent und alle Horizonte --------------------------------------------

def test_end_prozent_bezieht_sich_auf_den_einstieg():
    df = _fest([
        (100, 100, 100, 100),
        (100, 110, 100, 105),
        (105, 110, 100, 110),
    ])
    o = berechne_outcomes(df, np.array([0]), np.array([1]), 2)
    assert o.end_pkt[0] == pytest.approx(10.0)
    assert o.end_prozent[0] == pytest.approx(10.0)


def test_alle_horizonte_liefert_jeden(config):
    df = compute_indicators(_kurs(1500), config.indicators,
                            config.market.session)
    idx = np.arange(100, 800, 13)
    richtung = np.where(np.arange(len(idx)) % 2 == 0, 1, -1)

    ergebnis = alle_horizonte(df, idx, richtung, mit_zeiten=False)
    assert set(ergebnis) == set(HORIZONTE)
    for h, o in ergebnis.items():
        assert o.horizont == h
        assert len(o) == len(idx)

    # Ein laengerer Horizont kann die guenstige Exkursion nur vergroessern.
    kurz = ergebnis[5]
    lang = ergebnis[60]
    beide = kurz.gueltig & lang.gueltig
    assert beide.any()
    assert (lang.mfe_pkt[beide] >= kurz.mfe_pkt[beide] - 1e-9).all()
    assert (lang.mae_pkt[beide] >= kurz.mae_pkt[beide] - 1e-9).all()
