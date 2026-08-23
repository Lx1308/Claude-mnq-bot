"""Tests der benannten Handelskostenprofile.

Der Schwerpunkt liegt auf den Zusicherungen, die still brechen koennten:
dass ein Profil NUR die Kosten aendert, dass eine Annahme als solche
gekennzeichnet bleibt, und dass eine Aufschluesselung nicht erfunden wird.
"""

from __future__ import annotations

import pytest

from backtest.engine import CostModel
from backtest.kosten import (
    LUCID,
    PAUSCHALE_BIS_23_08_2026,
    PRIVATE_NINJATRADER,
    PROFILE,
    Kostenprofil,
    UnbekanntesKostenprofil,
    aus_konfiguration,
    hole_profil,
    profil_aus_config,
)


# ---------------------------------------------------------------------------
#  Die mitgelieferten Profile
# ---------------------------------------------------------------------------

def test_beide_geforderten_profile_existieren():
    """Der Auftrag verlangt mindestens diese zwei benannten Profile."""
    assert "private_ninjatrader" in PROFILE
    assert "lucid" in PROFILE


def test_private_ninjatrader_traegt_die_zahlen_von_laurin():
    assert PRIVATE_NINJATRADER.summe_je_seite == pytest.approx(0.95)
    assert PRIVATE_NINJATRADER.round_turn == pytest.approx(1.90)


def test_lucid_ist_als_annahme_gekennzeichnet():
    """Der Wert ist nicht gegen eine Abrechnung geprueft.

    Ihn als Tatsache auszugeben waere genau die Sorte Zahl, die aussieht wie
    eine Messung und keine ist - das verbietet dieses Projekt ausdruecklich.
    """
    assert LUCID.summe_je_seite == pytest.approx(0.50)
    assert LUCID.round_turn == pytest.approx(1.00)
    assert LUCID.ist_annahme is True
    assert "nicht verifiziert" in LUCID.quelle.lower()


def test_private_ninjatrader_ist_belegt_und_nicht_annahme():
    """Unterscheidung muss sichtbar sein, sonst ist sie wertlos."""
    assert PRIVATE_NINJATRADER.ist_annahme is False
    assert LUCID.ist_annahme is True


def test_altpauschale_bleibt_zum_nachrechnen_erhalten():
    """Ohne sie liessen sich die Ergebnisse der Basisvermessung nicht pruefen."""
    assert PAUSCHALE_BIS_23_08_2026.summe_je_seite == pytest.approx(2.50)
    assert PAUSCHALE_BIS_23_08_2026.ist_annahme is True


# ---------------------------------------------------------------------------
#  Trennung der Kostenarten
# ---------------------------------------------------------------------------

def test_slippage_ist_kein_bestandteil_der_gebuehr():
    """Slippage ist Ausfuehrungsqualitaet, keine Gebuehr.

    Sie steckt im Fuellkurs, nicht im abgezogenen Betrag. Waere sie Teil der
    Kommission, verschoebe sich die Round-Turn-Summe und man haette den
    Spread doppelt belastet.
    """
    modell = CostModel.aus_profil(
        PRIVATE_NINJATRADER, tick_size=0.25, point_value=2.0
    )
    # Round Turn = 2 x 0.95, ohne jeden Slippage-Anteil.
    assert modell.round_turn_commission == pytest.approx(1.90)
    # Slippage getrennt, in Punkten.
    assert modell.slippage_points == pytest.approx(0.25)


def test_aufschluesselung_wird_nicht_erfunden():
    """Ist die Aufteilung unbekannt, bleiben die Posten None.

    Erfundene Einzelposten, die zufaellig richtig aufsummieren, saehen aus wie
    eine Recherche - eine ehrliche Luecke ist besser.
    """
    assert PRIVATE_NINJATRADER.aufschluesselung_bekannt is False
    assert PRIVATE_NINJATRADER.broker_kommission_je_seite is None
    assert PRIVATE_NINJATRADER.boerse_je_seite is None

    bericht = PRIVATE_NINJATRADER.to_dict()
    assert bericht["aufschluesselung"] is None
    assert "Nicht aufgeschluesselt" in bericht["aufschluesselung_hinweis"]


def test_angegebene_aufschluesselung_muss_zur_summe_passen():
    """Eine Aufteilung, die etwas anderes ergibt, waere schlimmer als keine."""
    with pytest.raises(ValueError, match="Einzelposten"):
        Kostenprofil(
            name="kaputt",
            beschreibung="",
            summe_je_seite=0.95,
            slippage_ticks_je_seite=1.0,
            quelle="Test",
            ist_annahme=True,
            broker_kommission_je_seite=0.35,
            boerse_je_seite=0.10,   # Summe 0.45, verrechnet werden 0.95
        )


def test_stimmige_aufschluesselung_wird_angenommen():
    """Gegenprobe: passt die Summe, geht es durch."""
    profil = Kostenprofil(
        name="stimmig",
        beschreibung="",
        summe_je_seite=0.95,
        slippage_ticks_je_seite=1.0,
        quelle="Test",
        ist_annahme=True,
        broker_kommission_je_seite=0.35,
        boerse_je_seite=0.37,
        clearing_je_seite=0.21,
        nfa_je_seite=0.02,
    )
    assert profil.aufschluesselung_bekannt is True
    assert profil.to_dict()["aufschluesselung"]["broker_kommission"] == 0.35


def test_profil_ohne_quellenangabe_wird_abgelehnt():
    """Woher die Zahl stammt, gehoert zum Wert.

    Genau diese Angabe fehlte der Altpauschale von 2,50 - deshalb liess sich
    Jahre spaeter nicht mehr feststellen, ob sie je gestimmt hat.
    """
    with pytest.raises(ValueError, match="Quellenangabe"):
        Kostenprofil(
            name="ohne_quelle",
            beschreibung="",
            summe_je_seite=1.0,
            slippage_ticks_je_seite=1.0,
            quelle="   ",
            ist_annahme=True,
        )


# ---------------------------------------------------------------------------
#  Auswahl und Konfiguration
# ---------------------------------------------------------------------------

def test_unbekanntes_profil_bricht_ab_und_nennt_die_verfuegbaren():
    with pytest.raises(UnbekanntesKostenprofil, match="Verfuegbar"):
        hole_profil("gibt_es_nicht")


def test_profil_aus_der_konfiguration_gewinnt_gegen_den_code():
    """Die config.yaml ist massgeblich, nicht die Vorgabe im Code."""
    class FakeCfg:
        kostenprofil = "private_ninjatrader"
        kostenprofile = {
            "private_ninjatrader": {
                "summe_je_seite": 1.23,
                "slippage_ticks_je_seite": 2.0,
                "quelle": "Test",
                "ist_annahme": True,
            }
        }

    profil = profil_aus_config(FakeCfg())
    assert profil.summe_je_seite == pytest.approx(1.23)


def test_name_ueberschreibt_die_konfiguration():
    """Dasselbe Setup unter einem zweiten Profil, ohne die Config zu aendern."""
    class FakeCfg:
        kostenprofil = "private_ninjatrader"
        kostenprofile = {}

    assert profil_aus_config(FakeCfg(), "lucid").name == "lucid"


def test_konfiguration_ohne_betrag_bricht_ab():
    """Ohne Summe laesst sich nichts rechnen - keine stille Vorgabe."""
    with pytest.raises(ValueError, match="summe_je_seite"):
        aus_konfiguration("leer", {"quelle": "Test"})


# ---------------------------------------------------------------------------
#  Das Profil aendert NUR die Kosten
# ---------------------------------------------------------------------------

def test_profilwechsel_aendert_die_kosten_und_sonst_nichts():
    """Die tragende Zusicherung des Auftrags.

    Dasselbe Setup muss unter beiden Profilen rechenbar sein, ohne die
    Strategie- oder Research-Logik anzufassen. Waere dafuer eine Aenderung
    noetig, verglichen zwei Laeufe zwei verschiedene Strategien.
    """
    a = CostModel.aus_profil(PRIVATE_NINJATRADER, tick_size=0.25, point_value=2.0)
    b = CostModel.aus_profil(LUCID, tick_size=0.25, point_value=2.0)

    # Was sich unterscheiden MUSS:
    assert a.round_turn_commission != b.round_turn_commission
    # Was gleich bleiben MUSS - sonst waere es ein anderer Markt:
    assert a.tick_size == b.tick_size
    assert a.point_value == b.point_value
    assert a.contracts == b.contracts
    assert a.slippage_points == b.slippage_points


def test_kostenmodell_weist_seine_herkunft_aus():
    """Ohne diese Angabe laesst sich ein Ergebnis nicht einordnen."""
    modell = CostModel.aus_profil(LUCID, tick_size=0.25, point_value=2.0)
    herkunft = modell.herkunft()

    assert herkunft["name"] == "lucid"
    assert herkunft["ist_annahme"] is True
    assert herkunft["round_turn_usd"] == pytest.approx(1.00)
    assert herkunft["quelle"]


def test_kostenmodell_ohne_profil_meldet_das_ehrlich():
    """Direkt gesetzte Werte sind eine Annahme ohne Herkunft - und sagen das."""
    modell = CostModel(commission_per_side=3.0, tick_size=0.25, point_value=2.0)
    herkunft = modell.herkunft()

    assert herkunft["name"] == "unbenannt"
    assert herkunft["ist_annahme"] is True
    assert "keine Herkunft" in herkunft["quelle"]
