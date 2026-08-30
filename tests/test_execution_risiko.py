"""Kontoregeln, Ausfuehrungsspeicher und Risikopruefung.

Die Tests hier sichern vor allem die Faelle ab, an denen die drei
Vorgaengerimplementierungen gescheitert sind: ein Limit, das nie ausloest,
weil der Zustand nie aktualisiert wird; ein Abholvorgang, der Orders
verschwinden laesst; ein nachziehender Drawdown, der auf dem falschen
Hoechststand rechnet.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.kontoregeln import (
    DrawdownArt,
    FREI,
    aus_konfiguration,
    bekannte_kontoprofile,
    hole_kontoregeln,
)
from execution.risiko import Handelsfenster, RisikoPruefung
from execution.store import ExecutionStore, Order, OrderStatus


@pytest.fixture()
def store(tmp_path):
    speicher = ExecutionStore(tmp_path / "execution.sqlite3")
    yield speicher
    speicher.close()


def _order(**abweichungen) -> Order:
    grundlage = dict(
        instrument="MNQ", richtung="long", art="LIMIT", menge=1,
        limit_preis=20000.0, stop_loss=19980.0, take_profit=20040.0,
    )
    grundlage.update(abweichungen)
    return Order(**grundlage)


def _trade(store: ExecutionStore, pnl: float, tag: str, trade_id: str) -> None:
    store.schreibe_trade({
        "trade_id": trade_id, "order_id": "o-" + trade_id, "instrument": "MNQ",
        "richtung": "long", "menge": 1, "einstieg_utc": f"{tag}T14:00:00+00:00",
        "einstiegskurs": 20000.0, "ausstieg_utc": f"{tag}T14:30:00+00:00",
        "ausstiegskurs": 20000.0 + pnl / 2, "grund_ausstieg": "target",
        "punkte_brutto": pnl / 2, "kommission": 1.9, "pnl_usd": pnl,
        "r_vielfaches": None, "mae_punkte": None, "mfe_punkte": None,
        "session_datum": tag, "idee_id": None, "hypothese": None,
    })


# -- Kontoregeln ------------------------------------------------------------

def test_jedes_lucid_profil_ist_als_annahme_gekennzeichnet():
    """Solange die Zahlen nicht aus Lucids eigenen Bedingungen stammen, darf
    kein Bericht behaupten, ein Lauf habe 'die Lucid-Regeln' eingehalten."""
    for name in bekannte_kontoprofile():
        regeln = hole_kontoregeln(name)
        if regeln.anbieter == "lucid":
            assert regeln.ist_annahme, f"{name} muesste als Annahme markiert sein"
            assert "403" in regeln.quelle or "NICHT" in regeln.quelle


def test_freies_konto_hat_keine_grenzen_aber_ist_keine_annahme():
    assert FREI.max_verlust_usd is None
    assert FREI.tagesverlust_usd is None
    assert FREI.drawdown_art == DrawdownArt.KEINER
    assert not FREI.ist_annahme


def test_nur_das_25k_konto_hat_kein_tagesverlustlimit():
    assert hole_kontoregeln("lucid_pro_25k").tagesverlust_usd is None
    for groesse in ("50k", "100k", "150k"):
        assert hole_kontoregeln(f"lucid_pro_{groesse}").tagesverlust_usd is not None


def test_kein_300k_konto_im_register():
    """Beide Quellen kennen als groesste Stufe 150k.

    Lieber eine fehlende Stufe als eine erfundene: ein Profil mit geratenen
    Grenzen wuerde im Protokoll aussehen wie ein gemessenes.
    """
    assert not any("300k" in name for name in bekannte_kontoprofile())


def test_unbekanntes_profil_nennt_die_auswahl():
    with pytest.raises(KeyError) as fehler:
        hole_kontoregeln("lucid_pro_300k")
    assert "lucid_pro_25k" in str(fehler.value)


def test_ueberschreiben_ohne_quelle_wird_abgelehnt():
    """Eine geaenderte Zahl ohne Herkunft ist im Protokoll wertlos."""
    with pytest.raises(ValueError, match="quelle"):
        aus_konfiguration("lucid_pro_25k", {"max_verlust_usd": 1500.0})


def test_ueberschreiben_mit_quelle_geht_durch():
    regeln = aus_konfiguration(
        "lucid_pro_25k",
        {"max_verlust_usd": 1500.0, "quelle": "Dashboard, 30.08.2026",
         "ist_annahme": False},
    )
    assert regeln.max_verlust_usd == 1500.0
    assert not regeln.ist_annahme


def test_unbekanntes_feld_im_kontoprofil_bricht_ab():
    with pytest.raises(ValueError, match="Unbekannte Felder"):
        aus_konfiguration("frei", {"max_dd": 1000, "quelle": "x"})


# -- Speicher ---------------------------------------------------------------

def test_abholen_setzt_status_statt_zu_loeschen(store):
    """Der Kern des alten Fehlers: die Liste wurde beim Lesen geleert.

    Ein zweiter Abholer bekam dann nichts - und die Order war weg, ohne je
    bei NinjaTrader angekommen zu sein.
    """
    store.lege_order_an(_order(), "order-1")

    erste = store.zu_senden()
    assert [o["order_id"] for o in erste] == ["order-1"]

    zweite = store.zu_senden()
    assert zweite == [], "dieselbe Order darf nicht zweimal rausgehen"

    assert store.order("order-1")["status"] == OrderStatus.GESENDET


def test_order_ueberlebt_einen_neustart(tmp_path):
    pfad = tmp_path / "execution.sqlite3"
    erster = ExecutionStore(pfad)
    erster.lege_order_an(_order(), "order-1")
    erster.close()

    zweiter = ExecutionStore(pfad)
    try:
        assert zweiter.order("order-1")["status"] == OrderStatus.ANGELEGT
    finally:
        zweiter.close()


def test_doppelte_fuellung_wird_nicht_zweimal_gezaehlt(store):
    """NinjaTrader wiederholt Ereignisse nach einem Verbindungsabriss."""
    store.lege_order_an(_order(), "order-1")
    ersteinmal = store.erfasse_fill(
        exec_id="x-1", order_id="order-1", rolle="entry",
        ts_utc="2026-08-31T14:00:00+00:00", menge=1, preis=20000.0,
    )
    nochmal = store.erfasse_fill(
        exec_id="x-1", order_id="order-1", rolle="entry",
        ts_utc="2026-08-31T14:00:00+00:00", menge=1, preis=20000.0,
    )
    assert ersteinmal is True
    assert nochmal is False
    assert len(store.fills("order-1")) == 1


def test_richtung_wird_nicht_geraten():
    """Eine unlesbare Richtung ist ein Fehler, kein Standardwert."""
    with pytest.raises(ValueError, match="richtung"):
        _order(richtung="BUY_MAYBE")


def test_limit_order_ohne_preis_wird_abgelehnt():
    with pytest.raises(ValueError, match="limit_preis"):
        _order(art="LIMIT", limit_preis=None)


def test_abgelehnte_entscheidung_wird_auch_protokolliert(store):
    """Ohne die Ablehnungen laesst sich spaeter nicht unterscheiden, ob ein
    Filter zu scharf stand oder ob es kein Signal gab."""
    store.protokolliere_entscheidung(
        instrument="MNQ", ergebnis="abgelehnt",
        grund="Tagesverlustlimit erreicht",
    )
    eintraege = store.entscheidungen()
    assert len(eintraege) == 1
    assert eintraege[0]["ergebnis"] == "abgelehnt"


# -- Risiko -----------------------------------------------------------------

def _pruefung(store, profil="lucid_pro_50k", **kwargs) -> RisikoPruefung:
    return RisikoPruefung(hole_kontoregeln(profil), store, **kwargs)


MITTWOCH_MITTAG = datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc)   # 11:00 ET
MITTWOCH_NACHT = datetime(2026, 9, 2, 3, 0, tzinfo=timezone.utc)     # 23:00 ET (Vortag)
SAMSTAG = datetime(2026, 9, 5, 15, 0, tzinfo=timezone.utc)


def test_ausserhalb_des_fensters_wird_abgelehnt(store):
    urteil = _pruefung(store).pruefe(menge=1, zeitpunkt=MITTWOCH_NACHT)
    assert not urteil.erlaubt
    assert "Handelsfenster" in urteil.grund


def test_am_wochenende_wird_abgelehnt(store):
    urteil = _pruefung(store).pruefe(menge=1, zeitpunkt=SAMSTAG)
    assert not urteil.erlaubt


def test_innerhalb_des_fensters_geht_durch(store):
    urteil = _pruefung(store).pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert urteil.erlaubt, urteil.grund
    assert urteil.menge == 1


def test_tagesverlustlimit_greift_und_nutzt_echte_trades(store):
    """Genau das, was die drei Vorgaenger nicht konnten: der Zustand kommt
    aus tatsaechlichen Fuellungen, nicht aus einer Variablen, die niemand
    fortschreibt."""
    pruefung = _pruefung(store)
    tag = pruefung.session_datum(MITTWOCH_MITTAG)
    _trade(store, -1300.0, tag, "t1")     # Limit des 50k-Kontos: 1200

    urteil = pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert not urteil.erlaubt
    assert "Tagesverlustlimit" in urteil.grund


def test_verlust_eines_anderen_handelstages_sperrt_heute_nicht(store):
    pruefung = _pruefung(store)
    _trade(store, -1300.0, "2026-09-01", "t1")

    urteil = pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert urteil.erlaubt, urteil.grund


def test_25k_konto_hat_kein_tageslimit_aber_die_gesamtgrenze(store):
    pruefung = _pruefung(store, "lucid_pro_25k")
    tag = pruefung.session_datum(MITTWOCH_MITTAG)
    _trade(store, -900.0, tag, "t1")
    assert pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG).erlaubt

    _trade(store, -200.0, tag, "t2")      # zusammen -1100, Grenze liegt bei -1000
    urteil = pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert not urteil.erlaubt
    assert "Gesamtverlustgrenze" in urteil.grund


def test_eod_trailing_zieht_erst_mit_dem_tagesschluss_nach(store):
    """Der nachziehende Verlust rechnet auf dem SCHLUSSSTAND, nicht auf dem
    hoechsten Stand waehrend des Tages. Solange kein Handelstag abgeschlossen
    ist, steht die Grenze auf ihrem Startwert."""
    pruefung = _pruefung(store, "lucid_pro_50k")
    assert pruefung.max_verlust_grenze() == pytest.approx(48_000.0)

    store.schreibe_tagesabschluss("2026-09-01", 51_000.0, 1_000.0, 3)
    assert pruefung.max_verlust_grenze() == pytest.approx(49_000.0)


def test_trailing_friert_ueber_der_initialen_trail_grenze_ein(store):
    """Ab Startbalance + max_verlust steht die Grenze dauerhaft auf der
    Startbalance und zieht nicht weiter mit."""
    pruefung = _pruefung(store, "lucid_pro_50k")
    store.schreibe_tagesabschluss("2026-09-01", 52_500.0, 2_500.0, 5)
    assert pruefung.max_verlust_grenze() == pytest.approx(50_000.0)

    store.schreibe_tagesabschluss("2026-09-02", 60_000.0, 7_500.0, 5)
    assert pruefung.max_verlust_grenze() == pytest.approx(50_000.0)


def test_menge_wird_auf_das_limit_gekuerzt_statt_abgelehnt(store):
    pruefung = _pruefung(store, "lucid_pro_25k", eigenes_kontraktlimit=2)
    urteil = pruefung.pruefe(menge=5, zeitpunkt=MITTWOCH_MITTAG)
    assert urteil.erlaubt
    assert urteil.menge == 2
    assert "gekuerzt" in urteil.grund


def test_das_kleinere_von_anbieter_und_eigenem_limit_gilt(store):
    assert _pruefung(store, "lucid_pro_150k", eigenes_kontraktlimit=3).max_kontrakte() == 3
    assert _pruefung(store, "lucid_pro_25k", eigenes_kontraktlimit=50).max_kontrakte() == 20
    assert _pruefung(store, "frei", eigenes_kontraktlimit=4).max_kontrakte() == 4


def test_offene_orders_zaehlen_gegen_das_kontraktlimit(store):
    pruefung = _pruefung(store, "lucid_pro_25k", eigenes_kontraktlimit=2)
    store.lege_order_an(_order(menge=2), "order-1")

    urteil = pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert not urteil.erlaubt
    assert "Kontraktlimit" in urteil.grund


def test_ausstieg_wird_nie_blockiert(store):
    """Wenn ein Limit gerissen ist, will man raus - nicht festsitzen."""
    pruefung = _pruefung(store, "lucid_pro_50k")
    tag = pruefung.session_datum(MITTWOCH_MITTAG)
    _trade(store, -5000.0, tag, "t1")

    urteil = pruefung.pruefe(
        menge=1, zeitpunkt=MITTWOCH_NACHT, ist_einstieg=False
    )
    assert urteil.erlaubt


def test_freies_konto_kennt_keine_verlustgrenzen(store):
    pruefung = _pruefung(store, "frei")
    _trade(store, -50_000.0, pruefung.session_datum(MITTWOCH_MITTAG), "t1")
    urteil = pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG)
    assert urteil.erlaubt, urteil.grund
    assert pruefung.max_verlust_grenze() is None


def test_kennzahlen_melden_ob_die_regeln_eine_annahme_sind(store):
    kennzahlen = _pruefung(store, "lucid_pro_50k").kennzahlen(MITTWOCH_MITTAG)
    assert kennzahlen["regeln_sind_annahme"] is True
    assert kennzahlen["kontoprofil"] == "lucid_pro_50k"
    # MNQ ist ein Micro-Kontrakt: 4 Mini entsprechen 40 Micro.
    assert kennzahlen["max_kontrakte"] == 40


def test_konsistenzkennzahl_wird_berichtet_aber_blockiert_nicht(store):
    """Die Konsistenzregel greift bei Lucid erst beim Auszahlungsantrag.
    Eine Order zu blockieren, weil der Tag zu gut laeuft, waere eine Regel,
    die es nicht gibt."""
    pruefung = _pruefung(store, "lucid_pro_50k")
    _trade(store, 900.0, "2026-09-01", "t1")
    _trade(store, 100.0, "2026-09-02", "t2")

    kennzahlen = pruefung.kennzahlen(MITTWOCH_MITTAG)
    assert kennzahlen["konsistenz_ist"] == pytest.approx(0.9)
    assert kennzahlen["konsistenz_grenze"] == pytest.approx(0.4)
    assert pruefung.pruefe(menge=1, zeitpunkt=MITTWOCH_MITTAG).erlaubt


def test_handelsfenster_deckt_london_und_us_ab():
    fenster = Handelsfenster()
    # 03:00 ET = London-Eroeffnung, 15:59 ET = kurz vor US-Schluss
    assert fenster.ist_offen(datetime(2026, 9, 2, 7, 0, tzinfo=timezone.utc))
    assert fenster.ist_offen(datetime(2026, 9, 2, 19, 58, tzinfo=timezone.utc))
    assert not fenster.ist_offen(datetime(2026, 9, 2, 20, 5, tzinfo=timezone.utc))
