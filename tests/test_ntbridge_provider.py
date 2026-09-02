"""Die echte NT8-Historie als Backtest-Datenquelle.

Bis zum 30.08.2026 kannte ``create_provider`` nur ``"csv"``, und in ``data/``
liegt als einzige CSV ein synthetischer Zufallspfad. Jeder Forschungslauf des
Projekts rechnete deshalb entweder darauf oder auf der Dukascopy-Naeherung.
Diese Tests sichern den Weg zu den echten Kerzen ab - und die Kennzeichnung
der Kontraktnahtstellen, die sonst als Kursluecken durchgingen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from backtest.data import PROVIDER, BarRequest, DataProviderError, create_provider
from backtest.data.ntbridge_provider import NtBridgeDataProvider
from ntbridge.store import BarStore

UTC = timezone.utc
START = datetime(2026, 3, 2, 0, 0, tzinfo=UTC)


def _schreibe_1m(pfad, minuten: int, *, instrument: str = "MNQ", basis: float = 20000.0):
    store = BarStore(pfad)
    try:
        saetze = []
        for i in range(minuten):
            ts = START + timedelta(minutes=i)
            preis = basis + (i % 60) * 0.25
            saetze.append({
                "instrument": instrument,
                "timeframe": "1m",
                "timestampUtc": ts.isoformat(),
                "open": preis,
                "high": preis + 1.0,
                "low": preis - 1.0,
                "close": preis + 0.5,
                "volume": 100.0,
                "source": "nt8_export",
            })
        ergebnis = store.ingest(saetze, known_timeframes={"1m"}, symbol_map={})
        assert ergebnis.accepted == minuten
    finally:
        store.close()


@pytest.fixture
def db(tmp_path):
    pfad = tmp_path / "bars.sqlite3"
    _schreibe_1m(pfad, 3 * 24 * 60)
    return pfad


# -- Registrierung ----------------------------------------------------------

def test_provider_ist_registriert():
    """DER Test dieses Moduls.

    Ohne diese Registrierung kommt die Engine an die einzige echte Historie
    des Projekts nicht heran - MASTERPLAN X.1, dort als P0 gefuehrt.
    """
    assert "ntbridge" in PROVIDER
    assert isinstance(create_provider("ntbridge"), NtBridgeDataProvider)


def test_unbekannte_quelle_nennt_die_verfuegbaren():
    with pytest.raises(DataProviderError) as fehler:
        create_provider("databento")
    assert "ntbridge" in str(fehler.value)
    assert "csv" in str(fehler.value)


# -- Lesen ------------------------------------------------------------------

def test_einminutenreihe_kommt_unveraendert(db):
    provider = NtBridgeDataProvider(db)
    rahmen = provider.load(BarRequest("MNQ", interval_minutes=1))

    assert len(rahmen) == 3 * 24 * 60
    assert list(rahmen.columns) == ["open", "high", "low", "close", "volume"]
    assert str(rahmen.index.tz) == "UTC"
    assert rahmen.index.is_monotonic_increasing


def test_grobe_timeframes_werden_aus_1m_aggregiert(db):
    """Nicht aus den gespeicherten Aggregaten.

    Die sind eine Anzeigehilfe, nachgezogen von einer Schleife im
    Serverprozess. Ein Forschungsergebnis darf nicht davon abhaengen, ob die
    Oberflaeche lief.
    """
    provider = NtBridgeDataProvider(db)
    fuenf = provider.load(BarRequest("MNQ", interval_minutes=5))
    eins = provider.load(BarRequest("MNQ", interval_minutes=1))

    assert len(fuenf) == pytest.approx(len(eins) / 5, rel=0.05)
    # Extrema muessen erhalten bleiben - sonst stimmt die Aggregation nicht.
    assert fuenf["high"].max() == pytest.approx(eins["high"].max())
    assert fuenf["low"].min() == pytest.approx(eins["low"].min())


def test_gespeicherte_aggregate_werden_ignoriert(db):
    """Auch wenn absichtlich falsche 5m-Zeilen in der Datenbank liegen."""
    store = BarStore(db)
    try:
        store.ingest(
            [{
                "instrument": "MNQ",
                "timeframe": "5m",
                "timestampUtc": (START + timedelta(minutes=5)).isoformat(),
                "open": 99999.0, "high": 99999.0, "low": 99999.0,
                "close": 99999.0, "volume": 1.0,
                "source": "kaputt",
            }],
            known_timeframes={"5m"}, symbol_map={},
        )
    finally:
        store.close()

    rahmen = NtBridgeDataProvider(db).load(BarRequest("MNQ", interval_minutes=5))
    assert rahmen["high"].max() < 50000.0, "Der Provider hat gespeicherte 5m-Zeilen gelesen"


def test_unbekannte_kerzenlaenge_bricht_ab_statt_zu_runden(db):
    """Eine 7-Minuten-Anfrage still mit 5 Minuten zu beantworten waere ein
    Ergebnis fuer eine Frage, die niemand gestellt hat."""
    provider = NtBridgeDataProvider(db)
    with pytest.raises(DataProviderError) as fehler:
        provider.load(BarRequest("MNQ", interval_minutes=7))
    assert "7" in str(fehler.value)


def test_fehlende_datenbank_erklaert_woher_sie_kommt(tmp_path):
    provider = NtBridgeDataProvider(tmp_path / "gibtsnicht.sqlite3")
    with pytest.raises(DataProviderError) as fehler:
        provider.load(BarRequest("MNQ"))
    assert "NT8_EXPORT_ANLEITUNG" in str(fehler.value)


def test_unbekanntes_instrument_bricht_ab(db):
    provider = NtBridgeDataProvider(db)
    with pytest.raises(DataProviderError):
        provider.load(BarRequest("ES", interval_minutes=1))


def test_zeitfilter_wirkt_schon_in_sql(db):
    """Bei sieben Jahren Historie ist das der Unterschied zwischen zwanzig
    Sekunden und einer halben."""
    provider = NtBridgeDataProvider(db)
    ab = START + timedelta(days=1)
    rahmen = provider.load(
        BarRequest("MNQ", interval_minutes=1, start=ab)
    )
    assert rahmen.index[0] >= pd.Timestamp(ab)
    assert len(rahmen) < 3 * 24 * 60


# -- Rollgrenzen ------------------------------------------------------------

def test_rollgrenzen_aus_dem_preissprung_wenn_kein_bestand(db, monkeypatch):
    """Ohne NT8-Kontraktordner bleibt nur der Preissprung-Verdacht.

    Die Naht ist fuer den Backtest von einer Uebernachtluecke nicht zu
    unterscheiden - und an den Kursen selbst ist nichts zu sehen. Genau
    deshalb wird sie ausgewiesen.
    """
    from backtest.data import ntbridge_provider as modul

    # Einen Kontraktwechsel nachbauen: ab der Haelfte ein anderes Kursniveau.
    store = BarStore(db)
    try:
        weiter = START + timedelta(days=3)
        saetze = []
        for i in range(600):
            ts = weiter + timedelta(minutes=i)
            preis = 20400.0 + (i % 60) * 0.25   # +2 % Sprung
            saetze.append({
                "instrument": "MNQ", "timeframe": "1m",
                "timestampUtc": ts.isoformat(),
                "open": preis, "high": preis + 1.0, "low": preis - 1.0,
                "close": preis + 0.5, "volume": 100.0, "source": "nt8_export",
            })
        store.ingest(saetze, known_timeframes={"1m"}, symbol_map={})
    finally:
        store.close()

    # Kontraktbestand unlesbar machen -> Rueckfall auf den Preissprung.
    monkeypatch.setattr(modul, "ROLLSPRUNG_VERDACHT_PROZENT", 0.9)
    import werkzeuge.nt8_import as nt8
    monkeypatch.setattr(nt8, "rollplan_aus_nt8", lambda *a, **k: {})

    provider = NtBridgeDataProvider(db)
    provider.load(BarRequest("MNQ", interval_minutes=1))

    assert len(provider.rollgrenzen) >= 1
    assert str(provider.rollgrenzen.tz) == "UTC"


def test_ohne_sprung_keine_rollgrenzen(db, monkeypatch):
    import werkzeuge.nt8_import as nt8
    monkeypatch.setattr(nt8, "rollplan_aus_nt8", lambda *a, **k: {})

    provider = NtBridgeDataProvider(db)
    provider.load(BarRequest("MNQ", interval_minutes=1))
    assert len(provider.rollgrenzen) == 0


def test_bestand_zeigt_was_da_ist(db):
    bestand = NtBridgeDataProvider(db).bestand()
    zeile = bestand[bestand["timeframe"] == "1m"].iloc[0]
    assert zeile["instrument"] == "MNQ"
    assert zeile["kerzen"] == 3 * 24 * 60
    assert "nt8_export" in zeile["quellen"]
