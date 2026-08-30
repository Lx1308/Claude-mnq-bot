"""Die Sicherungen des Watchdogs.

Ein Watchdog, der Code aendern darf, ist ein Werkzeug mit scharfer Kante. Die
Tests hier pruefen nicht, dass er arbeitet - sie pruefen, dass er in den
Faellen, in denen er NICHT arbeiten darf, auch wirklich stillhaelt.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from werkzeuge import watchdog


@pytest.fixture()
def umgebung(tmp_path, monkeypatch):
    """Watchdog auf ein temporaeres Verzeichnis umbiegen."""
    monkeypatch.setattr(watchdog, "ZUSTAND", tmp_path / "watchdog.json")
    monkeypatch.setattr(watchdog, "SPERRE", tmp_path / "watchdog.lock")
    monkeypatch.setattr(watchdog, "NOTAUS", tmp_path / "watchdog.stop")
    monkeypatch.setattr(watchdog, "PROTOKOLL", tmp_path / "watchdog.log")
    monkeypatch.setattr(watchdog, "AUFTRAG", tmp_path / "auftrag.md")
    # Vorgabe: nichts laeuft, Kontingent frei. Einzelne Tests drehen das um.
    monkeypatch.setattr(watchdog, "claude_laeuft_bereits", lambda: (False, "frei"))
    monkeypatch.setattr(watchdog, "kontingent_verfuegbar", lambda: (True, "frei"))
    return tmp_path


# -- Notaus -----------------------------------------------------------------

def test_notaus_verhindert_jeden_lauf(umgebung):
    """Eine Datei, die Laurin von Hand anlegen kann, ohne etwas zu bedienen."""
    watchdog.NOTAUS.write_text("angehalten", encoding="utf-8")
    ergebnis = watchdog.lauf_ausfuehren()

    assert not ergebnis["getan"]
    assert "Notaus" in ergebnis["grund"]


def test_notaus_setzen_und_loesen(umgebung):
    assert watchdog.main(["stopp"]) == 0
    assert watchdog.NOTAUS.exists()
    assert watchdog.main(["weiter"]) == 0
    assert not watchdog.NOTAUS.exists()


# -- Parallelitaet ----------------------------------------------------------

def test_laufende_sitzung_verhindert_den_start(umgebung, monkeypatch):
    """Der wichtigste Riegel.

    Wuerde der Watchdog in eine offene Sitzung hineinstarten, arbeiteten zwei
    Instanzen an denselben Dateien, und die spaetere ueberschriebe die
    Aenderungen der frueheren - ohne dass es jemand merkt.
    """
    monkeypatch.setattr(
        watchdog, "claude_laeuft_bereits", lambda: (True, "2 Sitzungen laufen")
    )
    ergebnis = watchdog.lauf_ausfuehren()

    assert not ergebnis["getan"]
    assert "Sitzungen" in ergebnis["grund"]


def test_bei_fehlgeschlagener_prozesspruefung_wird_nicht_gestartet(monkeypatch):
    """Im Zweifel nicht starten.

    Ein ausgefallener Lauf kostet eine Stunde, zwei gleichzeitige koennen
    einen Arbeitstag kosten.
    """
    def kaputt(*args, **kwargs):
        raise OSError("tasklist nicht verfuegbar")

    monkeypatch.setattr(watchdog.subprocess, "run", kaputt)
    laeuft, grund = watchdog.claude_laeuft_bereits()

    assert laeuft is True
    assert "kein Start" in grund


# -- Sperre -----------------------------------------------------------------

def test_sperre_wird_genommen_und_freigegeben(umgebung):
    assert watchdog.sperre_nehmen()
    assert watchdog.SPERRE.exists()
    watchdog.sperre_freigeben()
    assert not watchdog.SPERRE.exists()


def test_sperre_eines_lebenden_prozesses_blockiert(umgebung, monkeypatch):
    watchdog.SPERRE.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    monkeypatch.setattr(watchdog, "_prozess_laeuft", lambda pid: True)

    assert not watchdog.sperre_nehmen()


def test_verwaiste_sperre_wird_uebernommen(umgebung, monkeypatch):
    """Sonst blockierte ein Absturz den Watchdog fuer immer."""
    watchdog.SPERRE.write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    monkeypatch.setattr(watchdog, "_prozess_laeuft", lambda pid: False)

    assert watchdog.sperre_nehmen()
    assert json.loads(watchdog.SPERRE.read_text())["pid"] != 4242


def test_unlesbare_sperre_blockiert_nicht_dauerhaft(umgebung, monkeypatch):
    watchdog.SPERRE.write_text("kein JSON", encoding="utf-8")
    monkeypatch.setattr(watchdog, "_prozess_laeuft", lambda pid: False)
    assert watchdog.sperre_nehmen()


# -- Tageslimit -------------------------------------------------------------

def test_tageslimit_stoppt_den_watchdog(umgebung):
    """Riegel gegen eine kaputte Abbruchbedingung."""
    watchdog.schreibe_zustand({
        "laeufe": {date.today().isoformat(): watchdog.MAX_LAEUFE_JE_TAG},
    })
    ergebnis = watchdog.lauf_ausfuehren()

    assert not ergebnis["getan"]
    assert "Tageslimit" in ergebnis["grund"]


def test_laeufe_eines_anderen_tages_zaehlen_nicht_mit(umgebung):
    watchdog.schreibe_zustand({"laeufe": {"2020-01-01": 99}})
    ergebnis = watchdog.lauf_ausfuehren(trocken=True)

    assert "Tageslimit" not in ergebnis["grund"]


# -- Kontingent -------------------------------------------------------------

def test_erschoepftes_kontingent_wird_vermerkt_statt_gestartet(umgebung, monkeypatch):
    monkeypatch.setattr(
        watchdog, "kontingent_verfuegbar",
        lambda: (False, "Kontingent erschoepft (usage limit)"),
    )
    ergebnis = watchdog.lauf_ausfuehren()

    assert not ergebnis["getan"]
    assert "erschoepft" in ergebnis["grund"]
    # Der Grund muss im Zustand landen, sonst weiss der naechste Lauf nichts.
    assert "erschoepft" in watchdog.lies_zustand()["letztes_ergebnis"]


# -- Zustand ----------------------------------------------------------------

def test_zustand_ueberlebt_und_wird_atomar_geschrieben(umgebung):
    watchdog.schreibe_zustand({"laeufe": {"2026-08-30": 3}, "letzter_lauf": "x"})
    assert watchdog.lies_zustand()["laeufe"]["2026-08-30"] == 3
    # Keine halbe Datei zurueckgelassen
    assert not (umgebung / "watchdog.json.tmp").exists()


def test_kaputter_zustand_legt_den_watchdog_nicht_lahm(umgebung):
    watchdog.ZUSTAND.parent.mkdir(parents=True, exist_ok=True)
    watchdog.ZUSTAND.write_text("{kaputt", encoding="utf-8")

    zustand = watchdog.lies_zustand()
    assert zustand["laeufe"] == {}


# -- Auftrag ----------------------------------------------------------------

def test_auftragsdatei_hat_vorrang_vor_dem_vorgabetext(umgebung):
    watchdog.AUFTRAG.write_text("Mach genau dies.", encoding="utf-8")
    assert watchdog.auftrag_lesen() == "Mach genau dies."


def test_ohne_auftragsdatei_gibt_es_einen_vorgabetext(umgebung):
    text = watchdog.auftrag_lesen()
    assert "PUSHE NICHTS" in text


def test_der_vorgabeauftrag_verbietet_den_push(umgebung):
    """Laurins ausdrueckliche Ansage vom 29.08.2026."""
    assert "PUSHE NICHTS" in watchdog.auftrag_lesen()


def test_echte_auftragsdatei_im_projekt_verbietet_den_push():
    """Auch die mitgelieferte Datei, nicht nur der Vorgabetext."""
    from pathlib import Path

    datei = Path(__file__).resolve().parents[1] / "WATCHDOG_AUFTRAG.md"
    assert datei.exists()
    inhalt = datei.read_text(encoding="utf-8")
    assert "Pushe NICHTS" in inhalt or "PUSHE NICHTS" in inhalt
