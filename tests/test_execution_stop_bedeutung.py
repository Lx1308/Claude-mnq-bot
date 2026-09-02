"""Stop als KURS oder als ABSTAND - die Verwechslung, die eine Order zerstoerte.

WAS AM 02.09.2026 PASSIERTE
---------------------------
Das Order-Panel schickt "SL 20 / TP 40" - gemeint sind Punkte Abstand. Der
Server reichte diese Zahlen unter ``stop_loss_price`` bzw.
``take_profit_price`` an NinjaTrader weiter, wo sie als KURSE gelesen wurden.
NinjaTrader legte daraufhin ein Verkaufslimit bei Kurs 40 an. Bei einem Markt
von 29430 war das sofort ausfuehrbar: die Position wurde eine Sekunde nach dem
Einstieg wieder geschlossen, mit einem Punkt Verlust. Der Stop bei Kurs 20
haette nie ausgeloest - die Position war die ganze Zeit ungeschuetzt.

Derselbe Irrtum verdarb die Buchung: ``abs(29430,25 - 20)`` ergab ein Risiko
von 29410 Punkten, und das R-Vielfache war um Faktor 1470 zu klein.

Der Bot war davon NICHT betroffen - er liefert aus der Ideen-Tabelle echte
Kurse (entry 29130,75, stop 29173,40). Beide Bedeutungen sind also
berechtigt; sie duerfen sich nur nicht dieselbe Spalte teilen.
"""

from __future__ import annotations

import pytest

from execution.buchung import baue_trade
from execution.store import ExecutionStore, Order


@pytest.fixture()
def store(tmp_path):
    s = ExecutionStore(tmp_path / "execution.sqlite3")
    yield s
    s.close()


# -- Die Trennung der beiden Bedeutungen -----------------------------------

def test_panel_order_speichert_abstaende_nicht_kurse(store):
    """Genau der Fall vom 02.09.2026: das Panel schickt 20 und 40."""
    order = Order(instrument="MNQ", richtung="long", art="MARKET", menge=1,
                  quelle="ui", stop_loss_punkte=20.0, take_profit_punkte=40.0)
    gespeichert = store.lege_order_an(order, "o-1")
    assert gespeichert["stop_loss_punkte"] == 20.0
    assert gespeichert["take_profit_punkte"] == 40.0
    assert gespeichert["stop_loss"] is None, (
        "20 ist ein Abstand und darf nicht als Kurs gespeichert werden - "
        "genau daraus wurde ein Verkaufslimit bei Kurs 40"
    )
    assert gespeichert["take_profit"] is None


def test_bot_order_speichert_kurse_nicht_abstaende(store):
    """Der Bot liefert aus der Ideen-Tabelle absolute Kurse."""
    order = Order(instrument="MNQ", richtung="short", art="MARKET", menge=1,
                  quelle="bot", stop_loss=29173.40, take_profit=29073.88)
    gespeichert = store.lege_order_an(order, "o-2")
    assert gespeichert["stop_loss"] == pytest.approx(29173.40)
    assert gespeichert["stop_loss_punkte"] is None


def test_beides_gleichzeitig_wird_abgelehnt():
    """Zwei Wahrheiten darueber, wo der Stop liegt, sind eine zu viel."""
    with pytest.raises(ValueError, match="stop_loss"):
        Order(instrument="MNQ", richtung="long", art="MARKET", menge=1,
              stop_loss=29410.25, stop_loss_punkte=20.0)
    with pytest.raises(ValueError, match="take_profit"):
        Order(instrument="MNQ", richtung="long", art="MARKET", menge=1,
              take_profit=29470.25, take_profit_punkte=40.0)


def test_negativer_abstand_wird_abgelehnt():
    with pytest.raises(ValueError, match="Abstand"):
        Order(instrument="MNQ", richtung="long", art="MARKET", menge=1,
              stop_loss_punkte=-20.0)


def test_alte_datenbank_bekommt_die_spalten_nachgereicht(tmp_path):
    """``CREATE TABLE IF NOT EXISTS`` ergaenzt eine bestehende Tabelle nicht."""
    import sqlite3

    pfad = tmp_path / "alt.sqlite3"
    con = sqlite3.connect(pfad)
    con.executescript(
        "CREATE TABLE orders (order_id TEXT PRIMARY KEY, erstellt_utc TEXT, "
        "zuletzt_utc TEXT, quelle TEXT, konto TEXT, instrument TEXT, "
        "richtung TEXT, art TEXT, menge INTEGER, limit_preis REAL, "
        "stop_preis REAL, stop_loss REAL, take_profit REAL, status TEXT, "
        "nt_zustand TEXT, fehler TEXT, idee_id TEXT, hypothese TEXT, "
        "begruendung TEXT);"
    )
    con.commit()
    con.close()

    store = ExecutionStore(pfad)
    try:
        order = Order(instrument="MNQ", richtung="long", art="MARKET", menge=1,
                      stop_loss_punkte=20.0)
        assert store.lege_order_an(order, "o-3")["stop_loss_punkte"] == 20.0
    finally:
        store.close()


# -- Das R-Vielfaches ------------------------------------------------------

def _fuellungen(einstieg: float, ausstieg: float):
    return (
        {"preis": einstieg, "ts_utc": "2026-09-02T17:17:22+00:00",
         "menge": 1, "kommission": 0.0, "rolle": "entry"},
        {"preis": ausstieg, "ts_utc": "2026-09-02T17:17:40+00:00",
         "menge": 1, "kommission": 0.0, "rolle": "stop"},
    )


def test_r_vielfaches_aus_dem_abstand():
    """Der konkrete Fall: 1 Punkt Verlust bei 20 Punkten Stop sind -0,05 R."""
    ein, aus = _fuellungen(29430.25, 29429.25)
    trade = baue_trade(
        order={"order_id": "o", "instrument": "MNQ", "richtung": "long",
               "menge": 1, "stop_loss": None, "stop_loss_punkte": 20.0},
        einstieg=ein, ausstieg=aus, point_value=2.0)
    assert trade["punkte_brutto"] == pytest.approx(-1.0)
    assert trade["pnl_usd"] == pytest.approx(-2.0)
    assert trade["r_vielfaches"] == pytest.approx(-0.05), (
        "gebucht wurde -0,000034 - die 20 war als Kurs gelesen worden"
    )


def test_r_vielfaches_aus_dem_kurs():
    """Der Bot-Weg bleibt unveraendert: Stop ist ein Kurs."""
    ein, aus = _fuellungen(29430.25, 29429.25)
    trade = baue_trade(
        order={"order_id": "o", "instrument": "MNQ", "richtung": "long",
               "menge": 1, "stop_loss": 29410.25, "stop_loss_punkte": None},
        einstieg=ein, ausstieg=aus, point_value=2.0)
    assert trade["r_vielfaches"] == pytest.approx(-0.05)


def test_beide_wege_ergeben_dasselbe_r():
    """20 Punkte Abstand und der passende Kurs muessen gleich rechnen."""
    ein, aus = _fuellungen(29430.25, 29410.25)
    basis = {"order_id": "o", "instrument": "MNQ", "richtung": "long", "menge": 1}
    per_abstand = baue_trade(
        order={**basis, "stop_loss_punkte": 20.0}, einstieg=ein, ausstieg=aus,
        point_value=2.0)
    per_kurs = baue_trade(
        order={**basis, "stop_loss": 29410.25}, einstieg=ein, ausstieg=aus,
        point_value=2.0)
    assert per_abstand["r_vielfaches"] == pytest.approx(-1.0)
    assert per_kurs["r_vielfaches"] == pytest.approx(per_abstand["r_vielfaches"])


def test_ohne_stop_kein_r():
    """Ohne Stop gibt es kein R - eine ersatzweise Bezugsgroesse waere erfunden."""
    ein, aus = _fuellungen(29430.25, 29429.25)
    trade = baue_trade(
        order={"order_id": "o", "instrument": "MNQ", "richtung": "long",
               "menge": 1},
        einstieg=ein, ausstieg=aus, point_value=2.0)
    assert trade["r_vielfaches"] is None
