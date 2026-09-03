"""Die Stufenmessung - Buchhaltung und Konventionen.

Die Leiter selbst ist in ``test_muster_w_stufen`` geprueft. Hier geht es um
das, was danach kommt: welcher Ausgang gebucht wird, wie Kosten und
R-Vielfache entstehen, und dass die Geometrielinie richtig gerechnet wird.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from werkzeuge import w_stufenmessung as M


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    index = pd.date_range("2022-03-01 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    return pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": [500.0] * len(kerzen)}, index=index)


def _fall(kerzen, n_kopien=40, tief2=100.0, hoch=200.0):
    """Dieselbe Kursbewegung n-mal, damit die Mindestgroesse erreicht wird."""
    voll = kerzen + [(kerzen[-1][3],) * 4] * (M.HORIZONT + 2)
    df = _rahmen(voll)
    tab = pd.DataFrame({
        "tief2": np.full(n_kopien, tief2), "hoch": np.full(n_kopien, hoch),
        "hoehe": np.full(n_kopien, hoch - tief2),
        "formfehler": np.linspace(0.05, 0.30, n_kopien),
    })
    einstieg = np.zeros(n_kopien, dtype=np.int64)
    return df, tab, einstieg


def _messe(df, tab, einstieg, stops, ziele):
    n = len(df)
    roll_hoch = pd.Series(df["high"]).rolling(M.HORIZONT).max().shift(
        -(M.HORIZONT - 1)).to_numpy()
    roll_tief = pd.Series(df["low"]).rolling(M.HORIZONT).min().shift(
        -(M.HORIZONT - 1)).to_numpy()
    schluss = np.full(n, np.nan)
    schluss[: n - M.HORIZONT + 1] = df["close"].to_numpy()[M.HORIZONT - 1:]
    return M.messe_stufe(df, tab, einstieg, stops, ziele,
                         roll_hoch, roll_tief, schluss, "probe")


# -- Buchhaltung -----------------------------------------------------------

def test_ziel_zuerst_wird_als_gewinn_gebucht():
    """Einstieg 100, Ziel 120, Stop 90 - der Kurs geht direkt auf 120."""
    df, tab, e = _fall([(100, 121, 99, 120)])
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    z = _messe(df, tab, e, stops, ziele)
    alle = z[z["gruppe"] == "alle"].iloc[0]
    assert alle["ziel_zuerst"] == len(tab)
    assert alle["stop_zuerst"] == 0
    assert alle["trefferquote"] == 1.0
    # 20 Punkte Lohn minus 1,45 Kosten auf 10 Punkte Risiko.
    assert alle["E_R_netto"] == pytest.approx((20 - M.KOSTEN_PKT) / 10, abs=1e-4)
    assert alle["E_USD_netto"] == pytest.approx((20 - M.KOSTEN_PKT) * 2.0, abs=0.01)


def test_stop_zuerst_wird_als_verlust_gebucht():
    df, tab, e = _fall([(100, 101, 89, 90)])
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["stop_zuerst"] == len(tab)
    assert alle["E_R_netto"] == pytest.approx((-10 - M.KOSTEN_PKT) / 10, abs=1e-4)


def test_beides_in_derselben_kerze_zaehlt_als_stop():
    """Invariante 4: aus OHLC ist nicht rekonstruierbar, was zuerst kam."""
    df, tab, e = _fall([(100, 125, 85, 110)])
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["stop_zuerst"] == len(tab)
    assert alle["ziel_zuerst"] == 0
    assert alle["ambig_anteil"] == 1.0, (
        "der Anteil muss ausgewiesen werden - haengt das Ergebnis daran, "
        "haengt es an einer Annahme"
    )


def test_zeitablauf_wird_zum_schlusskurs_gebucht():
    """Weder Ziel noch Stop: die Position wird am Horizontende bewertet.

    Nicht mit 0 R - das waere eine Erfindung. Der Schlusskurs ist das, was
    tatsaechlich dastand.
    """
    df, tab, e = _fall([(100, 105, 95, 104)])
    stops = {"fest": np.full(len(tab), 50.0)}
    ziele = {"fest": np.full(len(tab), 500.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["zeitablauf"] == len(tab)
    assert alle["entschieden"] == 0


# -- Grenzen des Rasters ---------------------------------------------------

def test_ziel_unter_dem_einstieg_wird_verworfen():
    """Bei spaeten Stufen liegt die Nackenlinie unter dem Einstieg.

    Solche Zellen werden weggelassen und nicht als Short umgedeutet.
    """
    df, tab, e = _fall([(150, 151, 149, 150)])
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"drunter": np.full(len(tab), 120.0)}   # unter dem Einstieg 150
    assert _messe(df, tab, e, stops, ziele).empty


def test_zu_kleines_risiko_wird_verworfen():
    """Ein Stop von einem halben Punkt ist bei MNQ kein Stop."""
    df, tab, e = _fall([(100, 101, 99, 100)])
    stops = {"eng": np.full(len(tab), 99.5)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    assert _messe(df, tab, e, stops, ziele).empty


def test_kleine_gruppen_werden_nicht_ausgewiesen():
    df, tab, e = _fall([(100, 121, 99, 120)], n_kopien=20)
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    assert _messe(df, tab, e, stops, ziele).empty


# -- Die Geometrielinie ----------------------------------------------------

def test_geometrie_ist_risiko_durch_risiko_plus_lohn():
    """Und zwar ueber die ENTSCHIEDENEN Faelle - dieselbe Teilmenge wie die
    Trefferquote. Wer im Horizont nicht entscheidet, ist kein Zufallsauszug."""
    df, tab, e = _fall([(100, 131, 99, 130)])
    stops = {"fest": np.full(len(tab), 90.0)}     # Risiko 10
    ziele = {"fest": np.full(len(tab), 130.0)}    # Lohn 30
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["geometrie"] == pytest.approx(10 / 40)
    assert alle["crv"] == pytest.approx(3.0)


def test_geometrie_bleibt_leer_ohne_entschiedene_faelle():
    """Lieber kein Wert als einer aus einer anderen Teilmenge."""
    df, tab, e = _fall([(100, 105, 95, 104)])
    stops = {"fest": np.full(len(tab), 50.0)}
    ziele = {"fest": np.full(len(tab), 500.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["entschieden"] == 0
    assert np.isnan(alle["geometrie"])


# -- Die Preisniveaus ------------------------------------------------------

def test_stops_liegen_unter_dem_boden_ziele_unter_der_nackenlinie():
    tab = pd.DataFrame({"tief2": [100.0], "hoch": [200.0], "hoehe": [100.0]})
    stops, ziele = M._preisniveaus(tab)
    assert stops["anteil_0.10"][0] == pytest.approx(90.0)
    assert stops["punkte_10"][0] == pytest.approx(90.0)
    assert all(kurs[0] < 100.0 for kurs in stops.values()), (
        "Laurins Bedingung: der Stop gehoert UNTER das Tief"
    )
    assert ziele["anteil_+0.15"][0] == pytest.approx(185.0)
    assert ziele["anteil_+0.00"][0] == pytest.approx(200.0)
    # Das klassische Messziel: eine Musterhoehe ueber die Nackenlinie.
    assert ziele["anteil_-1.00"][0] == pytest.approx(300.0)


# -- Auslenkung bis zum Ausstieg -------------------------------------------

def test_mfe_wird_nur_bis_zum_ausstieg_gemessen():
    """Die Bewegung NACH dem Stop gehoert nicht in die MFE.

    Hier wird in Kerze 1 ausgestoppt und der Kurs steigt danach auf 300.
    Wuerde ueber den ganzen Horizont gemessen, saehe der Trade aus, als
    haette er 20 R im Plus gestanden.
    """
    kerzen = [(100, 101, 89, 90), (90, 300, 89, 299)]
    df, tab, e = _fall(kerzen)
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 150.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["mfe_R_bis_ausstieg"] == pytest.approx(0.1, abs=0.01)
    assert alle["mfe_R_horizont"] > 15, (
        "der Horizontwert soll die spaetere Bewegung sehr wohl zeigen"
    )
    assert alle["hochgelaufen_dann_gestoppt"] == 0.0


def test_hochgelaufen_dann_gestoppt_erkennt_den_fall():
    """Erst ein halbes R ins Plus, dann ausgestoppt."""
    kerzen = [(100, 106, 99, 105), (105, 106, 89, 90)]
    df, tab, e = _fall(kerzen)
    stops = {"fest": np.full(len(tab), 90.0)}     # Risiko 10, halbes R = 105
    ziele = {"fest": np.full(len(tab), 150.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["stop_zuerst"] == len(tab)
    assert alle["hochgelaufen_dann_gestoppt"] == 1.0


# -- Kennzahlen aus Laurins Liste ------------------------------------------

def test_abstaende_und_restpotential_stehen_in_der_zeile():
    df, tab, e = _fall([(120, 121, 119, 120)])    # Einstieg bei 120
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 200.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["ueber_boden_pkt"] == pytest.approx(20.0)
    assert alle["ueber_boden_anteil"] == pytest.approx(0.20)
    assert alle["rest_pkt"] == pytest.approx(80.0)
    assert alle["rest_anteil"] == pytest.approx(0.80)


def test_zeit_bis_ziel_und_stop_stehen_getrennt():
    df, tab, e = _fall([(100, 101, 99, 100), (100, 101, 99, 100),
                        (100, 125, 99, 124)])
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert alle["zeit_bis_ziel"] == pytest.approx(3.0)
    assert np.isnan(alle["zeit_bis_stop"])


def test_t_wert_wird_ausgewiesen():
    """Ohne Streuung ist ein E[R] nahe null nicht von null zu unterscheiden."""
    rng = np.random.default_rng(3)
    kerzen = [(100, 101, 99, 100)]
    df, tab, e = _fall(kerzen, n_kopien=200)
    # Kurse so, dass es Gewinner und Verlierer gibt.
    stops = {"fest": np.full(len(tab), 90.0)}
    ziele = {"fest": np.full(len(tab), 120.0)}
    alle = _messe(df, tab, e, stops, ziele)
    alle = alle[alle["gruppe"] == "alle"].iloc[0]
    assert "E_R_stdfehler" in alle.index
    assert "t_wert" in alle.index
