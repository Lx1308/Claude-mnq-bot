"""Grundraten: die vier statistischen Fallen.

Diese Tests sichern nicht Rechenwege ab, sondern **Ehrlichkeit**: dass keine
Zahl ohne Nulllinie steht, dass Ueberschneidung die Signifikanz nicht
aufblaeht, dass zu kleine Stichproben gar nicht erst behauptet werden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.ereignisse.grundraten import (
    BELASTBAR_AB,
    MIN_N,
    bonferroni_schwelle,
    grundrate_aus_rahmen,
    grundratentabelle,
    ueberschneidungsfrei,
    wilson_intervall,
)


def _daten(
    n: int, *, end_r: np.ndarray | None = None, idx: np.ndarray | None = None,
    richtung: int = 1, cluster: np.ndarray | None = None,
    typ: str = "muster_a",
) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    if end_r is None:
        end_r = rng.normal(0.0, 1.0, n)
    if idx is None:
        idx = np.arange(n) * 500
    if cluster is None:
        cluster = np.array([f"C{i}" for i in range(n)])
    return pd.DataFrame({
        "pattern_type": typ,
        "direction": richtung,
        "verfuegbar_idx": idx,
        "cluster_id": cluster,
        "end_r": end_r,
        "mfe_r": np.abs(end_r) + 0.5,
        "mae_r": np.abs(end_r) + 0.3,
    })


# -- Wilson -----------------------------------------------------------------

def test_wilson_bleibt_im_einheitsintervall():
    """Die Normalapproximation faellt bei kleinen n aus [0,1] heraus und
    behauptet dann Unsinn mit Nachkommastellen."""
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


# -- Ueberschneidungsfreiheit ----------------------------------------------

def test_ueberschneidungsfrei_haelt_den_abstand_ein():
    idx = np.array([0, 5, 10, 100, 105, 200])
    maske = ueberschneidungsfrei(idx, horizont=60)
    gewaehlt = idx[maske]
    assert list(gewaehlt) == [0, 100, 200]
    assert np.all(np.diff(gewaehlt) >= 60)


def test_ueberschneidungsfrei_nimmt_bei_horizont_eins_alles():
    idx = np.arange(20)
    assert ueberschneidungsfrei(idx, horizont=1).all()


def test_ueberschneidungsfrei_bei_leerer_eingabe():
    assert len(ueberschneidungsfrei(np.array([], dtype=np.int64), 10)) == 0


def test_ueberschneidung_blaeht_die_signifikanz_auf():
    """Der Kern: dicht liegende Ereignisse teilen sich ihr Fenster. Als
    unabhaengig gezaehlt wird die t-Statistik um rund sqrt(horizont) zu gross.
    """
    n, horizont = 600, 60
    rng = np.random.default_rng(3)
    # Ein schwacher echter Effekt, aber die Ereignisse liegen dicht.
    werte = rng.normal(0.05, 1.0, n)
    dicht = _daten(n, end_r=werte, idx=np.arange(n))       # 1 Kerze Abstand
    basis = _daten(n, end_r=rng.normal(0.0, 1.0, n), idx=np.arange(n) * 1000)

    rate = grundrate_aus_rahmen(dicht, basis, name="dicht", horizont=horizont)
    assert rate is not None
    assert rate.n == n
    assert rate.n_unabhaengig < n / 10, "kaum Ueberschneidung entfernt"
    # Der ueberschneidende t-Wert ist deutlich groesser als der ehrliche.
    assert abs(rate.t_ueberschneidend) > abs(rate.t_statistik)
    # Und der massgebliche p-Wert ist der ehrliche, also der groessere.
    assert rate.p_wert > rate.p_ueberschneidend


# -- Nulllinie --------------------------------------------------------------

def test_kante_ist_der_ueberschuss_ueber_die_nulllinie():
    """'In 62 % der Faelle ging es hoch' ist wertlos, wenn es ohne das Muster
    in 61 % der Faelle hochgeht."""
    muster = _daten(300, end_r=np.full(300, 0.5))
    basis = _daten(300, end_r=np.full(300, 0.4))

    rate = grundrate_aus_rahmen(muster, basis, name="m", horizont=10)
    assert rate.mittel_r == pytest.approx(0.5)
    assert rate.basis_mittel_r == pytest.approx(0.4)
    assert rate.kante_r == pytest.approx(0.1)


def test_ohne_kante_kein_signifikanter_befund():
    """Ein Muster, das genau die Grundrate liefert, darf nicht als Fund
    dastehen - auch nicht bei riesiger Stichprobe."""
    rng = np.random.default_rng(11)
    werte = rng.normal(0.3, 1.0, 5000)
    muster = _daten(5000, end_r=werte, idx=np.arange(5000) * 100)
    basis = _daten(5000, end_r=werte.copy(), idx=np.arange(5000) * 100)

    rate = grundrate_aus_rahmen(muster, basis, name="m", horizont=10)
    assert abs(rate.kante_r) < 1e-9
    assert rate.p_wert > 0.5, "identische Verteilung, trotzdem signifikant"


# -- Stichprobengroesse -----------------------------------------------------

def test_zu_kleine_stichprobe_wird_gar_nicht_ausgewiesen():
    """Plan Abschnitt 12: unter n=30 wird nichts behauptet."""
    klein = _daten(MIN_N - 1)
    basis = _daten(500)
    assert grundrate_aus_rahmen(klein, basis, name="m", horizont=10) is None


def test_kleine_stichprobe_traegt_einen_vorbehalt():
    mittel = _daten(BELASTBAR_AB - 50)
    basis = _daten(2000)
    rate = grundrate_aus_rahmen(mittel, basis, name="m", horizont=10)
    assert rate is not None
    assert "zu klein" in rate.hinweis


def test_wenige_unabhaengige_faelle_werden_benannt():
    """Grosse Stichprobe, aber alles dicht beieinander - der p-Wert taugt
    dann nichts, und das muss dastehen."""
    dicht = _daten(400, idx=np.arange(400))
    basis = _daten(2000, idx=np.arange(2000) * 500)
    rate = grundrate_aus_rahmen(dicht, basis, name="m", horizont=240)
    assert rate is not None
    assert "ueberschneidungsfreie" in rate.hinweis


def test_zeilen_ohne_outcome_zaehlen_nicht_mit():
    daten = _daten(100)
    daten.loc[daten.index[:60], "end_r"] = np.nan
    basis = _daten(500)
    rate = grundrate_aus_rahmen(daten, basis, name="m", horizont=10)
    assert rate is not None
    assert rate.n == 40


# -- Klumpen ----------------------------------------------------------------

def test_cluster_werden_gezaehlt():
    """Um 15:35 koennen sieben Erkenner dasselbe melden - das sind keine
    sieben Beobachtungen (Plan 12.1)."""
    cluster = np.repeat([f"C{i}" for i in range(50)], 4)   # je 4 im Klumpen
    daten = _daten(200, cluster=cluster)
    basis = _daten(500)
    rate = grundrate_aus_rahmen(daten, basis, name="m", horizont=10)
    assert rate.n == 200
    assert rate.n_cluster == 50


# -- Tabelle ----------------------------------------------------------------

def test_tabelle_trennt_die_richtungen():
    """Ein Muster, das nur Shorts erzeugt, waere gegen eine gemischte
    Nulllinie systematisch falsch bewertet."""
    long = _daten(300, richtung=1, typ="a")
    short = _daten(300, richtung=-1, typ="a")
    short["verfuegbar_idx"] = short["verfuegbar_idx"] + 7
    daten = pd.concat([long, short], ignore_index=True)

    tabelle = grundratentabelle(daten, horizont=10)
    assert len(tabelle) == 2
    assert set(tabelle["muster"]) == {"a [long]", "a [short]"}


def test_tabelle_gibt_alle_gruppen_aus():
    """Keine Auswahl im Bericht - wer eine trifft, muss sie zaehlen."""
    teile = []
    for k in range(5):
        t = _daten(100, typ=f"muster_{k}")
        t["verfuegbar_idx"] = t["verfuegbar_idx"] + k
        teile.append(t)
    tabelle = grundratentabelle(pd.concat(teile, ignore_index=True), horizont=10)
    assert len(tabelle) == 5


def test_tabelle_ist_nach_der_kante_sortiert():
    stark = _daten(300, end_r=np.full(300, 1.0), typ="stark")
    schwach = _daten(300, end_r=np.full(300, -1.0), typ="schwach")
    schwach["verfuegbar_idx"] = schwach["verfuegbar_idx"] + 3
    tabelle = grundratentabelle(
        pd.concat([stark, schwach], ignore_index=True), horizont=10
    )
    assert tabelle.iloc[0]["muster"].startswith("stark")


def test_leere_daten_geben_leere_tabelle():
    assert grundratentabelle(_daten(0), horizont=10).empty


# -- Mehrfachtests ----------------------------------------------------------

def test_bonferroni_wird_mit_mehr_vergleichen_strenger():
    """Wer 100 Muster misst und das beste nimmt, hat 100 Vergleiche
    angestellt - nicht einen."""
    assert bonferroni_schwelle(1) == pytest.approx(0.05)
    assert bonferroni_schwelle(100) == pytest.approx(0.0005)
    assert bonferroni_schwelle(0) == pytest.approx(0.05)


def test_lade_fuer_auswertung_lehnt_unbekannten_block_ab():
    from common.ereignisse.grundraten import lade_fuer_auswertung

    with pytest.raises(ValueError, match="Unbekannter Block"):
        lade_fuer_auswertung(None, horizont=10, block="alles_bitte")
