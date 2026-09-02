"""Der Orderweg von der Oberflaeche bis zum gebuchten Trade.

Diese Tests bilden den Weg nach, den eine Order tatsaechlich nimmt:

    Oberflaeche -> POST /api/order/submit
                -> GET  /api/orders/pending   (holt die Bridge ab)
                -> POST /api/orders/update    (NinjaTrader meldet den Zustand)
                -> POST /api/orders/fill      (Einstieg)
                -> POST /api/orders/fill      (Stop oder Ziel)
                -> Trade im Speicher, Risikozustand aktualisiert

Genau an dieser Kette scheiterte die Vorgaengerfassung an drei Stellen: das
Abholen loeschte die Order, das Fuellungsmodell passte nicht zu dem, was das
AddOn schickt, und der Fill-Endpunkt tat ohnehin nichts.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import execution.server as server
from common.kontoregeln import hole_kontoregeln
from execution.risiko import Handelsfenster, RisikoPruefung
from execution.store import ExecutionStore, OrderStatus


def _nanos(minute: int = 0) -> int:
    """Zeitstempel auf dem AKTUELLEN Handelstag, in Epoch-Nanosekunden.

    Bewusst nicht auf einem festen Datum: das Tagesverlustlimit rechnet auf
    dem laufenden CME-Handelstag, und eine Fuellung von vorgestern zaehlt zu
    Recht nicht dagegen.
    """
    jetzt = datetime.now(timezone.utc)
    return int((jetzt.timestamp() + minute * 60) * 1e9)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Server mit eigenem Speicher und dauerhaft offenem Handelsfenster.

    Das Fenster wird hier bewusst aufgemacht: ob es greift, pruefen die Tests
    in ``test_execution_risiko.py`` gezielt. Wuerde es hier mitwirken, waeren
    alle Tests vom Wochentag der Ausfuehrung abhaengig.
    """
    store = ExecutionStore(tmp_path / "execution.sqlite3")
    risiko = RisikoPruefung(
        hole_kontoregeln("lucid_pro_50k"),
        store,
        fenster=Handelsfenster(nur_wochentags=False),
        eigenes_kontraktlimit=2,
    )
    monkeypatch.setattr(server, "STORE", store)
    monkeypatch.setattr(server, "RISIKO", risiko)
    monkeypatch.setattr(
        risiko.fenster.__class__, "ist_offen", lambda self, zeitpunkt: True
    )
    with TestClient(server.app) as c:
        yield c
    store.close()


def _order(client, **abweichungen):
    nutzlast = {
        "symbol": "MNQ", "side": "LONG", "qty": 1, "kind": "LIMIT",
        "price": 20000.0, "stop_loss": 19980.0, "take_profit": 20040.0,
        "grund": "Test",
    }
    nutzlast.update(abweichungen)
    return client.post("/api/order/submit", json=nutzlast)


# -- Orderaufgabe -----------------------------------------------------------

def test_order_wird_angenommen_und_persistiert(client):
    antwort = _order(client)
    assert antwort.status_code == 200, antwort.text
    order_id = antwort.json()["order_id"]

    gespeichert = server.STORE.order(order_id)
    assert gespeichert["status"] == OrderStatus.ANGELEGT
    assert gespeichert["richtung"] == "long"
    assert gespeichert["stop_loss"] == 19980.0


def test_short_wird_als_short_gespeichert(client):
    """Der Kern des invertierten Richtungsfehlers - hier festgenagelt."""
    order_id = _order(client, side="SHORT").json()["order_id"]
    assert server.STORE.order(order_id)["richtung"] == "short"


def test_buy_und_sell_werden_ebenfalls_richtig_zugeordnet(client):
    assert server.STORE.order(_order(client, side="BUY").json()["order_id"])["richtung"] == "long"
    assert server.STORE.order(_order(client, side="SELL").json()["order_id"])["richtung"] == "short"


def test_unlesbare_richtung_wird_abgelehnt_statt_geraten(client):
    antwort = _order(client, side="vielleicht_long")
    assert antwort.status_code == 400
    assert "Unlesbare Richtung" in antwort.json()["detail"]


def test_limit_order_ohne_preis_wird_abgelehnt(client):
    antwort = _order(client, kind="LIMIT", price=None)
    assert antwort.status_code == 400


def test_abgelehnte_order_landet_im_entscheidungsprotokoll(client):
    server.STORE.schreibe_trade({
        "trade_id": "t1", "order_id": "o1", "instrument": "MNQ", "richtung": "long",
        "menge": 1, "einstieg_utc": "2026-09-02T14:00:00+00:00", "einstiegskurs": 1.0,
        "ausstieg_utc": "2026-09-02T14:30:00+00:00", "ausstiegskurs": 1.0,
        "grund_ausstieg": "stop", "punkte_brutto": 0.0, "kommission": 0.0,
        "pnl_usd": -1300.0, "r_vielfaches": None, "mae_punkte": None,
        "mfe_punkte": None,
        "session_datum": server.RISIKO.session_datum(
            datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)
        ),
        "idee_id": None, "hypothese": None,
    })
    # Der Tag des Trades muss der aktuelle Handelstag sein, sonst greift das
    # Tageslimit nicht - deshalb hier ueber session_datum() bestimmt.
    heute = server.RISIKO.session_datum()
    server.STORE.schreibe_trade({
        "trade_id": "t2", "order_id": "o2", "instrument": "MNQ", "richtung": "long",
        "menge": 1, "einstieg_utc": f"{heute}T14:00:00+00:00", "einstiegskurs": 1.0,
        "ausstieg_utc": f"{heute}T14:30:00+00:00", "ausstiegskurs": 1.0,
        "grund_ausstieg": "stop", "punkte_brutto": 0.0, "kommission": 0.0,
        "pnl_usd": -1300.0, "r_vielfaches": None, "mae_punkte": None,
        "mfe_punkte": None, "session_datum": heute, "idee_id": None,
        "hypothese": None,
    })

    antwort = _order(client)
    assert antwort.status_code == 409
    protokoll = client.get("/api/entscheidungen").json()
    assert any(e["ergebnis"] == "abgelehnt" for e in protokoll)


def test_zu_grosse_menge_wird_gekuerzt_statt_abgelehnt(client):
    antwort = _order(client, qty=10)
    assert antwort.status_code == 200
    assert antwort.json()["menge"] == 2
    assert antwort.json()["gekuerzt"] is True


# -- Abholen ----------------------------------------------------------------

def test_abholen_liefert_die_order_genau_einmal(client):
    _order(client)

    erste = client.get("/api/orders/pending").json()
    assert len(erste) == 1
    assert erste[0]["direction"] == "long"
    assert erste[0]["order_type"] == "LIMIT"
    assert erste[0]["stop_loss_price"] == 19980.0

    zweite = client.get("/api/orders/pending").json()
    assert zweite == [], "eine zweite Abfrage darf dieselbe Order nicht nochmal liefern"


def test_abgeholte_order_bleibt_erhalten(client):
    """Vorher verschwand sie beim Abholen aus der Liste - samt jeder Spur."""
    order_id = _order(client).json()["order_id"]
    client.get("/api/orders/pending")
    assert server.STORE.order(order_id)["status"] == OrderStatus.GESENDET


# -- Rueckmeldungen aus NinjaTrader ----------------------------------------

def test_ablehnung_durch_ninjatrader_wird_sichtbar(client):
    """Laurins Frage vom 29.08.2026: kommt der Fehler in der App an?

    Ja - ueber den Order-Lebenslauf. Ohne diesen Weg stuende die Ablehnung
    ausschliesslich im NinjaTrader-Log.
    """
    order_id = _order(client).json()["order_id"]
    antwort = client.post("/api/orders/update", json={
        "order_key": order_id, "state": "Rejected",
        "error": "Market closed",
    })
    assert antwort.status_code == 200

    gespeichert = server.STORE.order(order_id)
    assert gespeichert["status"] == OrderStatus.ABGELEHNT
    assert gespeichert["fehler"] == "Market closed"


def test_unbekannter_zustand_aendert_den_status_nicht(client):
    order_id = _order(client).json()["order_id"]
    client.post("/api/orders/update", json={"order_key": order_id, "state": "Traeumend"})
    assert server.STORE.order(order_id)["status"] == OrderStatus.ANGELEGT


def test_fuellung_im_format_des_addons_wird_angenommen(client):
    """Das alte FillEvent verlangte {symbol, price, quantity}.

    Das AddOn schickt aber order_key/exec_id/role/ts/quantity/price/commission -
    jede Fuellung lief deshalb in einen 422 und wurde verworfen.
    """
    order_id = _order(client).json()["order_id"]
    antwort = client.post("/api/orders/fill", json={
        "type": "execution", "order_key": order_id, "role": "entry",
        "exec_id": "exec-1", "ts": _nanos(), "quantity": 1,
        "price": 20000.0, "commission": 0.95,
    })
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["status"] == "erfasst"


def test_doppelte_fuellung_wird_erkannt(client):
    order_id = _order(client).json()["order_id"]
    nutzlast = {
        "order_key": order_id, "role": "entry", "exec_id": "exec-1",
        "ts": _nanos(), "quantity": 1, "price": 20000.0, "commission": 0.95,
    }
    client.post("/api/orders/fill", json=nutzlast)
    zweite = client.post("/api/orders/fill", json=nutzlast)
    assert zweite.json()["status"] == "bekannt"


# -- Vollstaendiger Trade ---------------------------------------------------

def test_einstieg_und_ziel_ergeben_einen_gebuchten_trade(client):
    order_id = _order(client).json()["order_id"]
    client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "entry", "exec_id": "e-1",
        "ts": _nanos(0), "quantity": 1, "price": 20000.0, "commission": 0.95,
    })
    antwort = client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "target", "exec_id": "e-2",
        "ts": _nanos(minute=30), "quantity": 1, "price": 20040.0, "commission": 0.95,
    })

    assert antwort.json()["status"] == "trade"
    trades = client.get("/api/session/trades").json()
    assert len(trades) == 1
    trade = trades[0]

    # 40 Punkte * 2 USD (MNQ!) - 1,90 USD Kommission = 78,10
    assert trade["punkte_brutto"] == pytest.approx(40.0)
    assert trade["pnl_usd"] == pytest.approx(78.10)
    assert trade["grund_ausstieg"] == "target"
    # Stop lag 20 Punkte entfernt, Ziel 40 -> 2R
    assert trade["r_vielfaches"] == pytest.approx(2.0)


def test_short_trade_rechnet_mit_dem_richtigen_vorzeichen(client):
    order_id = _order(
        client, side="SHORT", price=20000.0, stop_loss=20020.0, take_profit=19960.0
    ).json()["order_id"]
    client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "entry", "exec_id": "e-1",
        "ts": _nanos(), "quantity": 1, "price": 20000.0,
    })
    client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "target", "exec_id": "e-2",
        "ts": _nanos(minute=30), "quantity": 1, "price": 19960.0,
    })
    trade = client.get("/api/session/trades").json()[0]
    assert trade["punkte_brutto"] == pytest.approx(40.0)
    assert trade["pnl_usd"] > 0


def test_stopfuellung_ergibt_einen_verlust_und_bewegt_das_risiko(client):
    """Der eigentliche Punkt: der Risikozustand folgt echten Fuellungen.

    In allen drei Vorgaengerfassungen blieb er unberuehrt, weil niemand ihn
    fortschrieb - die Limits konnten deshalb nie ausloesen.
    """
    vorher = client.get("/api/risiko").json()["realisiert_heute_usd"]

    order_id = _order(client).json()["order_id"]
    client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "entry", "exec_id": "e-1",
        "ts": _nanos(), "quantity": 1, "price": 20000.0,
    })
    client.post("/api/orders/fill", json={
        "order_key": order_id, "role": "stop", "exec_id": "e-2",
        "ts": _nanos(minute=10), "quantity": 1, "price": 19980.0,
    })

    nachher = client.get("/api/risiko").json()
    assert nachher["realisiert_heute_usd"] < vorher
    assert nachher["realisiert_heute_usd"] == pytest.approx(-40.0)


def test_risiko_endpunkt_weist_die_regeln_als_annahme_aus(client):
    antwort = client.get("/api/risiko").json()
    assert antwort["kontoprofil"] == "lucid_pro_50k"
    assert antwort["regeln_sind_annahme"] is True
    assert "ANNAHME" in antwort["regeln_zeile"]


# -- Marktzustand und Datenfrische ----------------------------------------

def test_marktzustand_kommt_aus_dem_kalender_nicht_aus_einer_konstanten(client):
    """``is_open`` stand fest auf ``True`` - eine Kopfzeile, die sonntags
    "MARKT OFFEN" meldet, ist eine Behauptung mit Autoritaet, keine Auskunft.

    Der Endpunkt fragt die Wanduhr, deshalb wird hier der **Vertrag** geprueft
    und daneben, dass die Quelle (``globex_state``) den Wochenendfall
    ueberhaupt kennt. Waere ``is_open`` weiterhin eine Konstante, faellt der
    zweite Teil nicht auf - der erste schon, sobald jemand den Endpunkt an
    einem Samstag aufruft.
    """
    from datetime import datetime, timezone as tz

    from common.sessions import globex_state

    antwort = client.get("/api/market?symbol=MNQ").json()
    assert isinstance(antwort["is_open"], bool)
    assert isinstance(antwort["is_rth"], bool)
    assert antwort["session"] in {
        "asia", "london", "new_york", "open", "maintenance", "closed",
    }
    # Der Endpunkt spiegelt genau diese Quelle.
    assert antwort["is_open"] == (globex_state(datetime.now(tz.utc)) == "open")
    # Und die Quelle kennt das Wochenende.
    assert globex_state(datetime(2026, 8, 29, 12, 0, tzinfo=tz.utc)) == "weekend"


def test_datenfrische_wird_ausgewiesen(client):
    """Ob Kerzen hereinkommen, sieht man sonst nur, indem man den Chart mit
    der Uhr vergleicht - ein stillstehender Chart sieht aus wie ein ruhiger
    Markt (Laurins Frage vom 31.08.2026)."""
    antwort = client.get("/api/market?symbol=MNQ").json()
    assert "letzte_kerze_ts" in antwort
    assert "datenalter_sekunden" in antwort
    assert "daten_frisch" in antwort
    assert isinstance(antwort["daten_frisch"], bool)
    if antwort["letzte_kerze_ts"]:
        # Nanosekunden, nicht Mikro- oder Millisekunden.
        assert len(str(antwort["letzte_kerze_ts"])) == 19
        assert antwort["datenalter_sekunden"] is not None
    else:
        assert antwort["datenalter_sekunden"] is None
        assert antwort["daten_frisch"] is False


def test_session_meldet_bot_und_datenstrom_getrennt(client):
    """Ein laufender Bot ohne Datenstrom ist kein Echtzeitbetrieb - und die
    Anzeige darf das nicht behaupten. ``active`` verlangt beides."""
    antwort = client.get("/api/session").json()
    assert antwort["active"] == (antwort["running"] and antwort["connected"])
    # Laeuft der Bot ohne Kerzen, muss die Ursache dastehen statt still zu
    # bleiben.
    if antwort["running"] and not antwort["connected"]:
        assert antwort["warnings"], "kein Hinweis auf den fehlenden Datenstrom"
        assert "ntbridge" in " ".join(antwort["warnings"])


# -- Chart-Kerzen: Zeitstempel-Einheit ------------------------------------

def test_bars_kommen_in_echten_nanosekunden():
    """pandas 3 parst ISO8601 als datetime64[us]. ``DatetimeIndex.asi8`` gab
    dann Mikrosekunden - das Frontend teilt durch 1e9 und landet im Januar
    1970 (der schwarze Chart, den Laurin am 31.08.2026 meldete).
    """
    import pandas as pd

    index = pd.to_datetime(
        pd.Series(["2026-08-30T13:00:00+00:00", "2026-08-30T13:01:00+00:00"]),
        utc=True,
        format="ISO8601",
    )
    rahmen = pd.DataFrame(
        {"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0],
         "close": [1.0, 2.0], "volume": [10.0, 20.0]},
        index=pd.DatetimeIndex(index),
    )

    bars = server._rahmen_zu_bars(rahmen)

    assert [b["ts"] for b in bars] == [1788094800_000_000_000, 1788094860_000_000_000]
    # Die Sekunden, die das Frontend daraus macht, muessen 2026 ergeben.
    zurueck = pd.Timestamp(bars[0]["ts"] // 1_000_000_000, unit="s", tz="UTC")
    assert zurueck.year == 2026
    # streng aufsteigend und je Minute verschieden (sonst wirft die Chart-Lib)
    assert bars[1]["ts"] - bars[0]["ts"] == 60_000_000_000
