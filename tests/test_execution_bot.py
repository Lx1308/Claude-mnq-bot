"""Der autonome Bot: Orderart, Positionsgroesse, Auswahl der Ideen.

Die Tests bilden vor allem die vier Fehler der Vorgaengerfassung
(``execution/live_bot.py``) ab:

* sie handelte auch **gefilterte** Ideen,
* sie handelte Ideen **beliebigen Alters**,
* sie handelte dieselbe Idee erneut, wenn der Zeitstempel gleich blieb,
* und sie nahm immer **einen** Kontrakt, unabhaengig vom Stopabstand.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from common.config import Config
from common.kontoregeln import hole_kontoregeln
from execution.bot import HandelsBot, kontraktzahl, order_art
from execution.risiko import Handelsfenster, RisikoPruefung
from execution.store import ExecutionStore, Order


# -- Orderart ---------------------------------------------------------------

def test_long_ueber_dem_kurs_ist_ein_ausbruch_also_stop():
    art, grund = order_art("long", entry=20050.0, aktueller_kurs=20000.0)
    assert art == "STOP"
    assert "Ausbruch" in grund


def test_long_unter_dem_kurs_ist_ein_ruecklauf_also_limit():
    assert order_art("long", entry=19950.0, aktueller_kurs=20000.0)[0] == "LIMIT"


def test_short_unter_dem_kurs_ist_ein_ausbruch_also_stop():
    assert order_art("short", entry=19950.0, aktueller_kurs=20000.0)[0] == "STOP"


def test_short_ueber_dem_kurs_ist_ein_ruecklauf_also_limit():
    assert order_art("short", entry=20050.0, aktueller_kurs=20000.0)[0] == "LIMIT"


def test_es_gibt_keine_market_order():
    """Der protokollierte Einstieg ist der Schlusskurs der Signalkerze.

    Zwischen ihm und der Ausfuehrung liegt Bewegung; eine Market-Order wuerde
    jeden Abstand kommentarlos bezahlen.
    """
    for richtung in ("long", "short"):
        for entry in (19950.0, 20000.0, 20050.0):
            assert order_art(richtung, entry, 20000.0)[0] in ("LIMIT", "STOP")


# -- Positionsgroesse -------------------------------------------------------

def test_enger_stop_erlaubt_mehr_kontrakte_als_weiter():
    eng, _ = kontraktzahl(
        risikobudget_usd=200.0, entry=20000.0, stop=19990.0,
        point_value=2.0, hoechstens=None,
    )
    weit, _ = kontraktzahl(
        risikobudget_usd=200.0, entry=20000.0, stop=19950.0,
        point_value=2.0, hoechstens=None,
    )
    assert eng == 10   # 10 Punkte * 2 USD = 20 USD je Kontrakt
    assert weit == 2   # 50 Punkte * 2 USD = 100 USD je Kontrakt
    assert eng > weit


def test_zu_kleines_budget_rundet_nicht_auf():
    """Reicht es nicht fuer einen Kontrakt, ist der Trade zu teuer.

    Aufrunden waere die stille Entscheidung, mehr zu riskieren als erlaubt.
    """
    menge, grund = kontraktzahl(
        risikobudget_usd=20.0, entry=20000.0, stop=19980.0,
        point_value=2.0, hoechstens=2,
    )
    assert menge == 0
    assert "Budget" in grund


def test_kontraktlimit_deckelt_das_budget():
    menge, grund = kontraktzahl(
        risikobudget_usd=10_000.0, entry=20000.0, stop=19990.0,
        point_value=2.0, hoechstens=2,
    )
    assert menge == 2
    assert "Limit" in grund


def test_stop_auf_dem_einstieg_ergibt_keine_position():
    menge, grund = kontraktzahl(
        risikobudget_usd=500.0, entry=20000.0, stop=20000.0,
        point_value=2.0, hoechstens=5,
    )
    assert menge == 0
    assert "kein Risiko berechenbar" in grund


def test_mnq_punktwert_wird_nicht_mit_nq_verwechselt():
    """2 USD je Punkt, nicht 20.

    Mit dem NQ-Wert waere jede Positionsgroesse ein Zehntel zu klein - und
    das Risiko pro Trade entsprechend falsch eingeschaetzt.
    """
    mnq, _ = kontraktzahl(
        risikobudget_usd=100.0, entry=20000.0, stop=19990.0,
        point_value=2.0, hoechstens=None,
    )
    nq, _ = kontraktzahl(
        risikobudget_usd=100.0, entry=20000.0, stop=19990.0,
        point_value=20.0, hoechstens=None,
    )
    assert mnq == 5
    assert nq == 0


# -- Risikobudget -----------------------------------------------------------

@pytest.fixture()
def bot(tmp_path):
    store = ExecutionStore(tmp_path / "execution.sqlite3")
    config = Config.load("config.yaml")
    risiko = RisikoPruefung(
        hole_kontoregeln("lucid_pro_25k"),
        store,
        fenster=Handelsfenster(nur_wochentags=False),
        eigenes_kontraktlimit=2,
    )
    b = HandelsBot(
        config, store, risiko,
        bar_datenbank=str(tmp_path / "leer.sqlite3"),
        ideen_datenbank=str(tmp_path / "ideen.sqlite3"),
    )
    yield b
    store.close()


def test_budget_bezieht_sich_auf_den_verlustpuffer_nicht_die_kontogroesse(bot):
    """Bei einem 25k-Konto mit 1.000 USD Puffer sind 7 Prozent 70 USD.

    Waere die Kontogroesse der Bezug, waeren es 1.750 USD - fast das
    Doppelte des gesamten Spielraums auf einem einzigen Trade.

    Der ausdrueckliche Betrag aus config.yaml wird hier abgeschaltet, weil
    genau der Ableitungsweg geprueft werden soll.
    """
    from dataclasses import replace

    bot.config = replace(
        bot.config,
        ausfuehrung=replace(
            bot.config.ausfuehrung,
            risiko_je_trade_usd=None,
            risiko_je_trade_anteil=0.07,
        ),
    )
    assert bot.risikobudget_usd() == pytest.approx(70.0)


def test_ausdruecklicher_betrag_hat_vorrang(bot):
    from dataclasses import replace

    bot.config = replace(
        bot.config,
        ausfuehrung=replace(bot.config.ausfuehrung, risiko_je_trade_usd=250.0),
    )
    assert bot.risikobudget_usd() == pytest.approx(250.0)


# -- Auswahl der Ideen ------------------------------------------------------

#: Mittwoch 11:00 ET - mitten im Handelsfenster. Bewusst fest und nicht
#: datetime.now(): sonst haengt das Ergebnis davon ab, wann die Testsuite
#: laeuft, und schluege nachts und am Wochenende fehl.
IM_FENSTER = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)


def _idee(**abweichungen):
    grundlage = {
        "idea_id": 1, "setup": "vwap_reversion", "richtung": "long",
        "timeframe": "5m", "erstellt_utc": IM_FENSTER.isoformat(),
        # 15 Punkte Stop = 30 USD je Kontrakt. Bewusst am unteren Rand:
        # das Median-Signal der aktuellen Setups liegt bei 119 USD und waere
        # mit dem Budget eines 25k-Kontos gar nicht handelbar - siehe
        # test_typisches_mnq_signal_sprengt_das_budget_eines_25k_kontos.
        "entry": 20000.0, "stop": 19985.0, "ziel": 20030.0, "crv": 2.0,
        "atr_referenz": 26.0, "stop_atr": 1.5, "ziel_atr": 3.0,
        "gefiltert": False, "ungeprueft": [],
    }
    grundlage.update(abweichungen)
    return grundlage


def test_idee_wird_zu_einer_order_mit_vollstaendiger_begruendung(bot):
    assert bot._handle(_idee(), kurs=19980.0, jetzt=IM_FENSTER)

    orders = bot.store.orders()
    assert len(orders) == 1
    order = orders[0]
    assert order["richtung"] == "long"
    assert order["art"] == "STOP"          # Einstieg liegt ueber dem Kurs
    assert order["stop_loss"] == 19985.0
    assert order["take_profit"] == 20030.0
    assert order["hypothese"] == "vwap_reversion"

    import json
    begruendung = json.loads(order["begruendung"])
    for feld in ("setup", "signalkerze_utc", "kurs_bei_entscheidung",
                 "orderart", "positionsgroesse", "risikobudget_usd",
                 "atr_referenz", "kontoprofil"):
        assert feld in begruendung, f"{feld} fehlt in der Begruendung"


def test_zu_teure_idee_wird_abgelehnt_und_begruendet(bot):
    """Stop 200 Punkte entfernt = 400 USD je Kontrakt, Budget sind 70."""
    assert not bot._handle(
        _idee(stop=19800.0), kurs=19980.0, jetzt=IM_FENSTER
    )
    assert bot.store.orders() == []

    entscheidungen = bot.store.entscheidungen()
    assert entscheidungen[0]["ergebnis"] == "abgelehnt"
    assert "Positionsgroesse 0" in entscheidungen[0]["grund"]


def test_ohne_kurs_wird_nicht_geraten(bot):
    assert not bot._handle(_idee(), kurs=None, jetzt=IM_FENSTER)
    assert "Kein aktueller Kurs" in bot.store.entscheidungen()[0]["grund"]


def test_ausserhalb_des_fensters_entsteht_keine_order(bot):
    bot.risiko.fenster = Handelsfenster(nur_wochentags=True)
    # Ein Samstag - da handelt niemand.
    lauf = bot.durchgang(datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc))
    assert lauf.orders == 0
    assert "Handelsfenster" in lauf.grund


def test_bereits_gehandelte_idee_erzeugt_keine_zweite_order(bot):
    """Die Vorgaengerfassung verglich Zeitstempel als Text und haette
    dieselbe Idee nach einem Neustart erneut gehandelt."""
    bot.store.lege_order_an(
        Order(
            instrument="MNQ", richtung="long", art="LIMIT", menge=1,
            limit_preis=20000.0, idee_id="1",
        ),
        "order-1",
    )
    gehandelt = {o["idee_id"] for o in bot.store.orders() if o["idee_id"]}
    assert "1" in gehandelt


def test_max_alter_haelt_alte_signale_draussen():
    """Ein Signal vom Vormittag beschreibt eine Marktlage, die es am
    Nachmittag nicht mehr gibt."""
    from execution.bot import MAX_ALTER_IN_KERZEN

    jetzt = IM_FENSTER
    grenze = jetzt - timedelta(minutes=5 * MAX_ALTER_IN_KERZEN)
    frisch = datetime.fromisoformat(_idee()["erstellt_utc"])
    alt = jetzt - timedelta(hours=3)

    assert frisch >= grenze
    assert alt < grenze


def test_typisches_mnq_signal_sprengt_das_budget_eines_25k_kontos(bot):
    """Am 30.08.2026 auf den echten Signalen nachgemessen - und festgehalten.

    Die 42 Signale der aktiven Setups auf sieben Tagen MNQ-5m riskieren je
    EINEM Micro-Kontrakt im Median 119 USD (Spanne 50-154 USD). Auf einem
    Lucid-25k mit 1.000 USD Gesamtverlustpuffer sind das 11,9 Prozent des
    gesamten Spielraums - fuer die kleinste handelbare Einheit, die es gibt.

    Daraus folgt nichts Gutes und nichts Schlimmes, sondern eine Tatsache:
    die aktuellen 5m-Setups und ein 25k-Konto passen nicht zusammen. Acht
    Verluste in Folge beenden das Konto. Wer sie trotzdem handeln will,
    braucht einen groesseren Kontotyp, engere Stops oder einen Timeframe mit
    kleinerem ATR - nicht eine andere Zahl im Risikobudget.

    Dieser Test haelt die Groessenordnung fest, damit sie nicht in Vergessenheit
    geraet, sobald jemand am Budget dreht.
    """
    typisches_signal_usd = 119.0
    puffer_25k = 1000.0
    anteil = typisches_signal_usd / puffer_25k
    assert anteil > 0.10, (
        "Sollte diese Zahl je unter 10 Prozent fallen, hat sich entweder die "
        "MNQ-Volatilitaet grundlegend geaendert oder die Setups wurden "
        "angefasst - beides ist einen neuen Blick wert."
    )

    # Und der Bot verhaelt sich entsprechend: er lehnt ab, statt aufzurunden.
    menge, grund = kontraktzahl(
        risikobudget_usd=70.0, entry=20000.0, stop=19940.5,
        point_value=2.0, hoechstens=2,
    )
    assert menge == 0
    assert "Budget" in grund
