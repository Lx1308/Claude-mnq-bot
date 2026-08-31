"""Grundraten: die fuenf statistischen Fallen.

Diese Tests sichern nicht Rechenwege ab, sondern **Ehrlichkeit**: dass keine
Zahl ohne Nulllinie steht, dass Ueberschneidung die Signifikanz nicht
aufblaeht, dass zu kleine Stichproben gar nicht erst behauptet werden - und
dass ein einzelner winziger ATR-Wert nicht das ganze Ergebnis kippt (die
fuenfte Falle, am 31.08.2026 im ersten Volllauf gefunden).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.ereignisse.grundraten import (
    ATR_UNTERGRENZE,
    BELASTBAR_AB,
    MIN_N,
    WINSOR_R,
    bonferroni_schwelle,
    grundrate_aus_rahmen,
    grundratentabelle,
    ueberschneidungsfrei,
    wilson_intervall,
    zwei_anteile_p,
)


def _daten(
    n: int, *, end_r: np.ndarray | None = None, idx: np.ndarray | None = None,
    richtung: int = 1, cluster: np.ndarray | None = None,
    typ: str = "muster_a", atr: np.ndarray | float = 10.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    if end_r is None:
        end_r = rng.normal(0.0, 1.0, n)
    if idx is None:
        idx = np.arange(n) * 500
    if cluster is None:
        cluster = np.array([f"C{i}" for i in range(n)])
    atr_arr = np.full(n, atr, dtype=float) if np.isscalar(atr) else np.asarray(atr, float)
    return pd.DataFrame({
        "pattern_type": typ,
        "direction": richtung,
        "verfuegbar_idx": idx,
        "cluster_id": cluster,
        "nahe_rollgrenze": 0,
        "atr_referenz": atr_arr,
        "end_r": end_r,
        # end_pkt konsistent zum Vorzeichen von end_r
        "end_pkt": end_r * atr_arr,
        "mfe_r": np.abs(end_r) + 0.5,
        "mae_r": np.abs(end_r) + 0.3,
    })


# -- Wilson -----------------------------------------------------------------

def test_wilson_bleibt_im_einheitsintervall():
    for treffer, gesamt in ((0, 10), (10, 10), (1, 3), (49, 50)):
        u, o = wilson_intervall(treffer, gesamt)
        assert 0.0 <= u <= o <= 1.0, f"{treffer}/{gesamt} -> [{u}, {o}]"


def test_wilson_wird_mit_mehr_daten_enger():
    schmal = wilson_intervall(500, 1000)
    breit = wilson_intervall(5, 10)
    assert (schmal[1] - schmal[0]) < (breit[1] - breit[0])


def test_wilson_ohne_daten_ist_nan():
    u, o = wilson_intervall(0, 0)
    assert np.isnan(u) and np.isnan(o)


# -- Zwei-Anteile-Test ----------------------------------------------------

def test_zwei_anteile_p_erkennt_gleichheit():
    _, p = zwei_anteile_p(500, 1000, 505, 1000)
    assert p > 0.5


def test_zwei_anteile_p_erkennt_unterschied():
    _, p = zwei_anteile_p(600, 1000, 500, 1000)
    assert p < 1e-4


def test_zwei_anteile_p_ohne_daten():
    assert zwei_anteile_p(0, 0, 5, 10) == (0.0, 1.0)


# -- Ueberschneidungsfreiheit --------------------------------------------

def test_ueberschneidungsfrei_haelt_den_abstand_ein():
    idx = np.array([0, 5, 10, 100, 105, 200])
    gewaehlt = idx[ueberschneidungsfrei(idx, horizont=60)]
    assert list(gewaehlt) == [0, 100, 200]
    assert np.all(np.diff(gewaehlt) >= 60)


def test_ueberschneidungsfrei_nimmt_bei_horizont_eins_alles():
    assert ueberschneidungsfrei(np.arange(20), horizont=1).all()


def test_ueberschneidungsfrei_bei_leerer_eingabe():
    assert len(ueberschneidungsfrei(np.array([], dtype=np.int64), 10)) == 0


def test_ueberschneidung_blaeht_die_signifikanz_auf():
    """Dicht liegende Ereignisse teilen sich ihr Fenster. Als unabhaengig
    gezaehlt wird die Statistik zu gross."""
    n, horizont = 800, 60
    rng = np.random.default_rng(3)
    werte = rng.normal(0.0, 1.0, n)
    vorz = np.where(np.arange(n) % 100 < 58, 1.0, -1.0)   # 58 % positiv, geklumpt
    dicht = _daten(n, end_r=werte, idx=np.arange(n))
    dicht["end_pkt"] = vorz
    basis = _daten(n, end_r=rng.normal(0.0, 1.0, n), idx=np.arange(n) * 1000)
    basis["end_pkt"] = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)   # 50 %

    rate = grundrate_aus_rahmen(dicht, basis, name="dicht", horizont=horizont)
    assert rate is not None
    assert rate.n_unabhaengig < n / 10
    # Der ueberschneidende p-Wert ist kleiner (optimistischer) als der ehrliche.
    assert rate.anteil_p_wert > rate.anteil_p_wert_ueberschneidend


# -- Nulllinie ----------------------------------------------------------

def test_anteil_kante_ist_der_ueberschuss_ueber_die_nulllinie():
    muster = _daten(400, end_r=np.full(400, 0.5))    # 100 % positiv
    basis = _daten(400, end_r=np.concatenate([np.full(240, 0.1), np.full(160, -0.1)]))
    rate = grundrate_aus_rahmen(muster, basis, name="m", horizont=10)
    assert rate.anteil_positiv == pytest.approx(1.0)
    assert rate.basis_anteil_positiv == pytest.approx(0.6)
    assert rate.anteil_kante == pytest.approx(0.4)


def test_ohne_kante_kein_signifikanter_befund():
    """Ein Muster, das genau die Grundrate liefert, darf nicht als Fund
    dastehen - auch nicht bei riesiger Stichprobe."""
    rng = np.random.default_rng(11)
    vorz = rng.choice([1.0, -1.0], 6000, p=[0.53, 0.47])
    muster = _daten(6000, idx=np.arange(6000) * 100)
    muster["end_pkt"] = vorz
    basis = _daten(6000, idx=np.arange(6000) * 100)
    basis["end_pkt"] = rng.choice([1.0, -1.0], 6000, p=[0.53, 0.47])

    rate = grundrate_aus_rahmen(muster, basis, name="m", horizont=10)
    assert abs(rate.anteil_kante) < 0.02
    assert rate.anteil_p_wert > 0.1, "gleiche Verteilung, trotzdem signifikant"


# -- Die fuenfte Falle: winzige ATR ------------------------------------

def test_winzige_atr_wird_verworfen():
    """Ein 14-Kerzen-ATR von 0,003 Punkten ist kein Marktzustand, sondern
    eingefrorene Kurse - solche Ereignisse gehoeren nicht in die Statistik."""
    atr = np.concatenate([np.full(180, 8.0), np.full(20, 0.01)])
    daten = _daten(200, atr=atr)
    basis = _daten(500)
    rate = grundrate_aus_rahmen(daten, basis, name="m", horizont=10)
    assert rate.n == 180
    assert rate.n_verworfen_atr == 20
    assert ATR_UNTERGRENZE == 1.0


def test_anteil_kante_ist_gegen_atr_muell_immun():
    """Der Kern der fuenften Falle nachgestellt: 9 % der Ereignisse haben eine
    Mini-ATR und eine normale Bewegung dagegen. E[R] wird zertruemmert, der
    Trefferanteil bleibt unberuehrt - weil er die ATR gar nicht benutzt.
    """
    n = 1000
    rng = np.random.default_rng(5)
    end_pkt = rng.normal(0.0, 30.0, n)              # Bewegung in Punkten
    atr = np.full(n, 8.0)
    muell = slice(0, 90)
    atr[muell] = 0.02                               # Mini-ATR
    end_pkt[muell] = -150.0                         # klar dagegen
    end_r = end_pkt / atr

    daten = _daten(n, end_r=end_r, atr=atr, idx=np.arange(n) * 200)
    daten["end_pkt"] = end_pkt
    basis = _daten(n, end_r=rng.normal(0, 3, n), idx=np.arange(n) * 200)
    basis["end_pkt"] = rng.normal(0, 30, n)

    rate = grundrate_aus_rahmen(daten, basis, name="m", horizont=10)
    # Die Mini-ATR-Zeilen sind raus.
    assert rate.n == n - 90
    # E[R] roh waere jenseits von -10; nach Saeuberung + Winsor ist es zahm.
    assert abs(rate.mittel_r) < WINSOR_R
    # Der Trefferanteil sitzt auf ~50 %, keine kuenstliche Kante.
    assert abs(rate.anteil_kante) < 0.05


def test_schwere_raender_werden_benannt():
    end_r = np.concatenate([np.full(280, 0.1), np.full(20, -40.0)])
    daten = _daten(300, end_r=end_r, atr=8.0)
    basis = _daten(1000)
    rate = grundrate_aus_rahmen(daten, basis, name="m", horizont=10)
    assert "schwere Raender" in rate.hinweis or "auseinander" in rate.hinweis


# -- Stichprobengroesse -----------------------------------------------

def test_zu_kleine_stichprobe_wird_gar_nicht_ausgewiesen():
    assert grundrate_aus_rahmen(_daten(MIN_N - 1), _daten(500),
                                name="m", horizont=10) is None


def test_kleine_stichprobe_traegt_einen_vorbehalt():
    rate = grundrate_aus_rahmen(_daten(BELASTBAR_AB - 50), _daten(2000),
                                name="m", horizont=10)
    assert rate is not None
    assert "zu klein" in rate.hinweis


def test_zeilen_ohne_outcome_zaehlen_nicht_mit():
    daten = _daten(100)
    daten.loc[daten.index[:60], "end_r"] = np.nan
    rate = grundrate_aus_rahmen(daten, _daten(500), name="m", horizont=10)
    assert rate is not None
    assert rate.n == 40


# -- Klumpen ----------------------------------------------------------

def test_cluster_werden_gezaehlt():
    cluster = np.repeat([f"C{i}" for i in range(50)], 4)
    rate = grundrate_aus_rahmen(_daten(200, cluster=cluster), _daten(500),
                                name="m", horizont=10)
    assert rate.n == 200
    assert rate.n_cluster == 50


# -- Tabelle --------------------------------------------------------

def test_tabelle_trennt_die_richtungen():
    long = _daten(300, richtung=1, typ="a")
    short = _daten(300, richtung=-1, typ="a")
    short["verfuegbar_idx"] = short["verfuegbar_idx"] + 7
    tabelle = grundratentabelle(pd.concat([long, short], ignore_index=True),
                                horizont=10)
    assert set(tabelle["muster"]) == {"a [long]", "a [short]"}


def test_tabelle_nulllinie_ohne_die_eigene_gruppe():
    """Ein grosses, schiefes Muster darf die Nulllinie nicht in seine eigene
    Richtung ziehen - es steht sonst teilweise gegen sich selbst."""
    rng = np.random.default_rng(1)
    # Ein grosses Muster, das fast immer verliert.
    gross = _daten(4000, typ="gross", idx=np.arange(4000) * 50)
    gross["end_pkt"] = np.where(np.arange(4000) % 100 < 20, 1.0, -1.0)   # 20 %
    # Ein kleines, neutrales Muster.
    klein = _daten(400, typ="klein", idx=np.arange(400) * 900)
    klein["end_pkt"] = rng.choice([1.0, -1.0], 400)                     # ~50 %

    tabelle = grundratentabelle(pd.concat([gross, klein], ignore_index=True),
                                horizont=10)
    zeile_klein = tabelle[tabelle["muster"].str.startswith("klein")].iloc[0]
    # Die Nulllinie fuer "klein" ist "gross" (20 % positiv). "klein" bei ~50 %
    # hat also eine deutliche positive Kante - nicht null.
    assert zeile_klein["basis_anteil_positiv"] < 0.3
    assert zeile_klein["anteil_kante"] > 0.15


def test_tabelle_gibt_alle_gruppen_aus():
    teile = []
    for k in range(5):
        t = _daten(100, typ=f"muster_{k}")
        t["verfuegbar_idx"] = t["verfuegbar_idx"] + k
        teile.append(t)
    tabelle = grundratentabelle(pd.concat(teile, ignore_index=True), horizont=10)
    assert len(tabelle) == 5


def test_tabelle_ist_nach_dem_anteilsueberschuss_sortiert():
    stark = _daten(400, typ="stark")
    stark["end_pkt"] = 1.0                       # 100 % positiv
    mittel = _daten(400, typ="mittel")
    mittel["end_pkt"] = np.where(np.arange(400) % 4 == 0, 1.0, -1.0)   # 25 %
    mittel["verfuegbar_idx"] = mittel["verfuegbar_idx"] + 3
    tabelle = grundratentabelle(pd.concat([stark, mittel], ignore_index=True),
                                horizont=10)
    assert abs(tabelle.iloc[0]["anteil_kante"]) >= abs(tabelle.iloc[1]["anteil_kante"])


def test_tabelle_verwirft_atr_muell_einmal_fuer_alle():
    atr = np.concatenate([np.full(360, 8.0), np.full(40, 0.01)])
    daten = _daten(400, atr=atr, typ="a")
    tabelle = grundratentabelle(daten, horizont=10)
    assert tabelle.attrs.get("verworfen_atr_gesamt") == 40


def test_leere_daten_geben_leere_tabelle():
    assert grundratentabelle(_daten(0), horizont=10).empty


# -- Mehrfachtests ------------------------------------------------

def test_bonferroni_wird_mit_mehr_vergleichen_strenger():
    assert bonferroni_schwelle(1) == pytest.approx(0.05)
    assert bonferroni_schwelle(100) == pytest.approx(0.0005)
    assert bonferroni_schwelle(0) == pytest.approx(0.05)


def test_lade_fuer_auswertung_lehnt_unbekannten_block_ab():
    from common.ereignisse.grundraten import lade_fuer_auswertung

    with pytest.raises(ValueError, match="Unbekannter Block"):
        lade_fuer_auswertung(None, horizont=10, block="alles_bitte")
