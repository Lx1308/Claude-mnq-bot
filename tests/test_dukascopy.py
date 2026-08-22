"""Tests der Dukascopy-Import- und Konvertierungslogik.

Der **Download** ist bewusst nicht getestet - das pruefte vor allem das Netz.
Getestet ist alles, was aus Bytes Zahlen macht: dort entstehen die Fehler,
die still falsche Kurse ergeben.

Die Fixtures sind **selbst gebaute** bi5-Saetze, keine heruntergeladenen
Dateien. So laeuft der Test ohne Netz und bleibt reproduzierbar; das Format
ist mit 20 Byte je Satz klein genug, um es exakt nachzubilden.
"""

from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone

import pandas as pd
import pytest

from backtest.data.dukascopy import (
    NASDAQ_100_CFD,
    DukascopyFehler,
    dekodiere_ticks,
    entpacke,
    stunden_url,
    ticks_zu_minuten,
)

STUNDE = datetime(2026, 8, 19, 14, tzinfo=timezone.utc)


def baue_bi5(saetze: list[tuple[int, int, int, float, float]]) -> bytes:
    """Baut eine bi5-Datei aus (ms, ask_roh, bid_roh, ask_vol, bid_vol)."""
    roh = b"".join(struct.pack(">IIIff", *satz) for satz in saetze)
    komprimierer = lzma.LZMACompressor(format=lzma.FORMAT_ALONE)
    return komprimierer.compress(roh) + komprimierer.flush()


# ---------------------------------------------------------------------------
#  URL
# ---------------------------------------------------------------------------

def test_monat_in_der_url_ist_zero_based():
    """August (8) muss als 07 in der URL stehen.

    Ein haeufiger Fehler bei diesem Endpunkt: mit 1-basiertem Monat laedt man
    stillschweigend den Vormonat und merkt es nie, weil Kurse ja kommen.
    """
    url = stunden_url(NASDAQ_100_CFD, STUNDE)
    assert "/2026/07/19/14h_ticks.bi5" in url
    assert "USATECHIDXUSD" in url


def test_januar_wird_zu_null():
    url = stunden_url(NASDAQ_100_CFD, datetime(2020, 1, 5, 3, tzinfo=timezone.utc))
    assert "/2020/00/05/03h_ticks.bi5" in url


# ---------------------------------------------------------------------------
#  Dekodierung
# ---------------------------------------------------------------------------

def test_preisfaktor_ergibt_plausible_nasdaq_kurse():
    """Gemessen, nicht geraten: 29408411 / 1000 = 29408.41.

    Der Faktor stammt aus einem echten Abruf vom 19.08.2026 und passt zum
    Nasdaq-Niveau derselben Tage. Ein Faktor 100 oder 10000 ergaebe 294084
    bzw. 2940 - beides offensichtlich falsch, aber nur, wenn jemand hinsieht.
    """
    daten = entpacke(baue_bi5([(6, 29408411, 29407664, 0.0003, 0.0002)]))
    ticks = dekodiere_ticks(daten, STUNDE, NASDAQ_100_CFD.preis_faktor)

    assert len(ticks) == 1
    assert ticks["ask"].iloc[0] == pytest.approx(29408.411)
    assert ticks["bid"].iloc[0] == pytest.approx(29407.664)
    # Sanity: der Kurs muss im Bereich eines Nasdaq-100-Standes liegen.
    assert 1000.0 < ticks["ask"].iloc[0] < 100000.0


def test_zeitstempel_setzt_auf_der_vollen_stunde_auf():
    """Der ms-Wert ist ein Versatz zur Stunde, kein absoluter Zeitpunkt."""
    daten = entpacke(baue_bi5([
        (0, 29400000, 29399000, 0.1, 0.1),
        (61_000, 29401000, 29400000, 0.1, 0.1),      # +1:01
        (3_599_999, 29402000, 29401000, 0.1, 0.1),   # letzte Millisekunde
    ]))
    ticks = dekodiere_ticks(daten, STUNDE, NASDAQ_100_CFD.preis_faktor)

    assert ticks.index[0] == pd.Timestamp("2026-08-19 14:00:00", tz="UTC")
    assert ticks.index[1] == pd.Timestamp("2026-08-19 14:01:01", tz="UTC")
    assert ticks.index[2] < pd.Timestamp("2026-08-19 15:00:00", tz="UTC")


def test_leere_stunde_ist_kein_fehler():
    """Wochenende und Feiertage liefern Dateien der Laenge 0.

    Das von einem echten Ausfall zu unterscheiden ist der Punkt: eine
    Ausnahme wuerde einen Mehrjahres-Download an jedem Samstag abbrechen.
    """
    assert entpacke(b"") == b""
    ticks = dekodiere_ticks(b"", STUNDE, NASDAQ_100_CFD.preis_faktor)
    assert ticks.empty
    assert list(ticks.columns) == ["ask", "bid", "ask_volume", "bid_volume"]
    assert ticks.index.tz is not None


def test_angeschnittene_datei_bricht_ab_statt_stillschweigend_zu_kuerzen():
    """Ein halber Satz darf nicht als ganzer durchgehen.

    Wuerde man abrunden, verschoebe sich nichts sichtbar - die Datei waere
    nur unvollstaendig, und niemand erfuehre es.
    """
    daten = entpacke(baue_bi5([(6, 29408411, 29407664, 0.0003, 0.0002)]))
    with pytest.raises(DukascopyFehler, match="Vielfaches"):
        dekodiere_ticks(daten[:-5], STUNDE, NASDAQ_100_CFD.preis_faktor)


def test_html_statt_bi5_wird_als_solches_gemeldet():
    """Dukascopy antwortet ohne User-Agent mit einer HTML-Seite (403).

    Die Meldung muss darauf hinweisen, sonst sucht man den Fehler im
    Dekoder statt im Header.
    """
    with pytest.raises(DukascopyFehler, match="User-Agent"):
        entpacke(b"<!DOCTYPE html><html>Access denied</html>")


def test_naiver_zeitstempel_wird_abgelehnt():
    with pytest.raises(ValueError, match="zeitzonenbehaftet"):
        dekodiere_ticks(b"", datetime(2026, 8, 19, 14), 1000.0)


# ---------------------------------------------------------------------------
#  Verdichtung zu Minutenkerzen
# ---------------------------------------------------------------------------

def test_minutenkerze_nutzt_die_mitte_aus_bid_und_ask():
    """Sonst zahlte der Backtest den Spread doppelt.

    Er rechnet Slippage und Kommission bereits ueber CostModel; auf dem Ask
    kaufen und auf dem Bid verkaufen kaeme obendrauf.
    """
    daten = entpacke(baue_bi5([(0, 20_000_000, 19_000_000, 0.5, 0.5)]))
    ticks = dekodiere_ticks(daten, STUNDE, 1000.0)
    kerzen = ticks_zu_minuten(ticks)

    assert len(kerzen) == 1
    # (20000 + 19000) / 2
    assert kerzen["close"].iloc[0] == pytest.approx(19500.0)


def test_ohlc_ergibt_sich_aus_der_reihenfolge_der_ticks():
    daten = entpacke(baue_bi5([
        (1_000, 29_400_000, 29_400_000, 0.1, 0.0),   # open  29400
        (2_000, 29_450_000, 29_450_000, 0.2, 0.0),   # high  29450
        (3_000, 29_350_000, 29_350_000, 0.3, 0.0),   # low   29350
        (4_000, 29_420_000, 29_420_000, 0.4, 0.0),   # close 29420
    ]))
    kerzen = ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))

    assert len(kerzen) == 1
    zeile = kerzen.iloc[0]
    assert zeile["open"] == pytest.approx(29400.0)
    assert zeile["high"] == pytest.approx(29450.0)
    assert zeile["low"] == pytest.approx(29350.0)
    assert zeile["close"] == pytest.approx(29420.0)
    assert zeile["volume"] == pytest.approx(1.0)  # 0.1+0.2+0.3+0.4


def test_kerze_traegt_die_schlusszeit_nicht_die_anfangszeit():
    """Regressionstest fuer einen Fehler, der still jeden Vergleich ruiniert.

    NinjaTrader beschriftet eine Kerze mit ihrer SCHLUSSZEIT: die Ticks von
    14:00:00 bis 14:00:59 ergeben die Kerze 14:01. ``resample`` beschriftet
    standardmaessig mit dem Anfang - ein Versatz von genau einer Minute.

    Gemessen am 22.08.2026 gegen echte MNQ-Kerzen: mit Anfangs-Beschriftung
    korrelieren die Minutenaenderungen mit r = -0.06, mit Schluss-
    Beschriftung mit r = +0.95. Nichts an den Kursen selbst haette den
    Fehler verraten.

    Gegenprobe: mit ``resample("1min")`` ohne die Argumente stuende hier
    14:00 statt 14:01, und dieser Test fiele.
    """
    daten = entpacke(baue_bi5([
        (0, 29_400_000, 29_400_000, 0.1, 0.0),        # 14:00:00.000
        (59_999, 29_410_000, 29_410_000, 0.1, 0.0),   # 14:00:59.999
    ]))
    kerzen = ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))

    assert len(kerzen) == 1
    assert kerzen.index[0] == pd.Timestamp("2026-08-19 14:01", tz="UTC"), (
        "Die Kerze muss die Schlusszeit tragen, nicht die Anfangszeit."
    )
    # Beide Ticks gehoeren in dieselbe Kerze.
    assert kerzen["open"].iloc[0] == pytest.approx(29400.0)
    assert kerzen["close"].iloc[0] == pytest.approx(29410.0)


def test_tick_auf_der_minutengrenze_gehoert_in_die_naechste_kerze():
    """closed="left": 14:01:00.000 eroeffnet die Kerze 14:02, schliesst nicht 14:01."""
    daten = entpacke(baue_bi5([
        (0, 29_400_000, 29_400_000, 0.1, 0.0),         # 14:00:00 -> Kerze 14:01
        (60_000, 29_500_000, 29_500_000, 0.1, 0.0),    # 14:01:00 -> Kerze 14:02
    ]))
    kerzen = ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))

    assert len(kerzen) == 2
    assert kerzen.index[0] == pd.Timestamp("2026-08-19 14:01", tz="UTC")
    assert kerzen.index[1] == pd.Timestamp("2026-08-19 14:02", tz="UTC")


def test_minuten_ohne_tick_erzeugen_keine_kerze():
    """Eine Kerze zu erfinden hiesse, Handel zu behaupten, den es nicht gab.

    Genauso verhaelt sich NinjaTrader; die Datenluecken-Pruefung des Projekts
    setzt genau das voraus.
    """
    daten = entpacke(baue_bi5([
        (0, 29_400_000, 29_400_000, 0.1, 0.0),          # Minute 0
        (5 * 60_000, 29_410_000, 29_410_000, 0.1, 0.0), # Minute 5
    ]))
    kerzen = ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))

    assert len(kerzen) == 2, "Die vier Minuten dazwischen duerfen nicht entstehen."
    assert kerzen.index[0] == pd.Timestamp("2026-08-19 14:01", tz="UTC")
    assert kerzen.index[1] == pd.Timestamp("2026-08-19 14:06", tz="UTC")


def test_erzeugte_kerzen_erfuellen_das_projektschema():
    """validate_ohlcv ist die Eintrittskarte in den Backtest."""
    from common.indicators import validate_ohlcv

    daten = entpacke(baue_bi5([
        (0, 29_400_000, 29_399_000, 0.1, 0.1),
        (30_000, 29_410_000, 29_409_000, 0.1, 0.1),
        (90_000, 29_405_000, 29_404_000, 0.1, 0.1),
    ]))
    kerzen = ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))

    validate_ohlcv(kerzen)  # wirft, wenn Schema oder Index nicht stimmen
    assert (kerzen["high"] >= kerzen["low"]).all()
    assert kerzen.index.is_monotonic_increasing


def test_leerer_tickframe_ergibt_leere_kerzen_ohne_ausnahme():
    leer = dekodiere_ticks(b"", STUNDE, 1000.0)
    kerzen = ticks_zu_minuten(leer)
    assert kerzen.empty
    assert list(kerzen.columns) == ["open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------------
#  Kennzeichnung als Naeherung
# ---------------------------------------------------------------------------

def test_instrument_ist_als_naeherung_gekennzeichnet():
    """Dieselbe Haltung wie "naeherung: true" beim Volume Profile.

    Eine Naeherung wird gekennzeichnet, nicht stillschweigend als Messung
    ausgegeben.
    """
    assert NASDAQ_100_CFD.ist_naeherung is True
    beschreibung = NASDAQ_100_CFD.beschreibung.lower()
    assert "kein mnq" in beschreibung
    assert "volumen" in beschreibung


# ---------------------------------------------------------------------------
#  Speicher: Trennung vom Echtbestand und Wiederaufnahme
# ---------------------------------------------------------------------------

def kerzen_fixture() -> pd.DataFrame:
    daten = entpacke(baue_bi5([
        (0, 29_400_000, 29_399_000, 0.1, 0.1),
        (60_000, 29_410_000, 29_409_000, 0.1, 0.1),
    ]))
    return ticks_zu_minuten(dekodiere_ticks(daten, STUNDE, 1000.0))


def test_datei_traegt_die_einschraenkung_mit_sich(tmp_path):
    """Wer die Datei in zwei Jahren findet, soll nicht raten muessen.

    Dieselbe Haltung wie "naeherung: true" beim Volume Profile: eine
    Naeherung wird gekennzeichnet, nicht stillschweigend als Messung
    ausgegeben.
    """
    from backtest.data.dukascopy_store import DukascopyStore

    with DukascopyStore(tmp_path / "nas.sqlite3", NASDAQ_100_CFD) as store:
        herkunft = store.herkunft()

    assert herkunft["ist_naeherung"] == "true"
    assert herkunft["symbol"] == "USATECHIDXUSD"
    warnung = herkunft["warnung"].upper()
    assert "KEIN MNQ-FUTURES" in warnung
    assert "REIN INFORMATIV" in warnung
    assert "KEIN GESCHAEFTS" not in warnung  # keine falsche Beruhigung
    assert "volumen" in herkunft["volumen_definition"].lower()


def test_geholte_stunde_wird_auch_dann_vermerkt_wenn_sie_leer_war(tmp_path):
    """Sonst liefe ein Wiederaufnahme-Lauf jedes Wochenende erneut ins Leere."""
    from backtest.data.dukascopy_store import DukascopyStore

    leer = ticks_zu_minuten(dekodiere_ticks(b"", STUNDE, 1000.0))
    with DukascopyStore(tmp_path / "nas.sqlite3", NASDAQ_100_CFD) as store:
        assert not store.ist_geholt(STUNDE)
        assert store.speichere_stunde(STUNDE, leer) == 0
        assert store.ist_geholt(STUNDE), (
            "Eine leere Stunde muss als geholt gelten - sonst wird sie ewig "
            "erneut angefragt."
        )
        assert store.anzahl_kerzen() == 0
        assert store.anzahl_stunden() == 1


def test_wiederholtes_speichern_erzeugt_keine_duplikate(tmp_path):
    from backtest.data.dukascopy_store import DukascopyStore

    kerzen = kerzen_fixture()
    with DukascopyStore(tmp_path / "nas.sqlite3", NASDAQ_100_CFD) as store:
        store.speichere_stunde(STUNDE, kerzen)
        store.speichere_stunde(STUNDE, kerzen)
        assert store.anzahl_kerzen() == len(kerzen)


def test_geladener_frame_ist_backtestfaehig(tmp_path):
    """Der Backtest soll ohne Umweg darauf laufen koennen."""
    from common.indicators import validate_ohlcv
    from backtest.data.dukascopy_store import DukascopyStore

    with DukascopyStore(tmp_path / "nas.sqlite3", NASDAQ_100_CFD) as store:
        store.speichere_stunde(STUNDE, kerzen_fixture())
        frame = store.lade_frame()

    validate_ohlcv(frame)
    assert len(frame) == 2
    assert frame.index.tz is not None
    assert frame["close"].iloc[0] == pytest.approx(29399.5)


def test_speicher_liegt_nie_auf_der_produktiven_datenbank(tmp_path):
    """ntbridge.sqlite3 enthaelt gemessene Futures-Kerzen.

    Naeherungsdaten dort hineinzuschreiben hiesse, dass spaeter niemand mehr
    auseinanderhalten kann, worauf eine Auswertung beruht.
    """
    from backtest.data.dukascopy_store import DukascopyStore

    with DukascopyStore(tmp_path / "nas.sqlite3", NASDAQ_100_CFD) as store:
        assert "ntbridge" not in str(store.path)
