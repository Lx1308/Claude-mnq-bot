"""Tests fuer Empfaenger, Speicher und NTBridgeBarSource."""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from common.instruments import MGC, MNQ
from mcp_server.bars import DAILY, BarSourceError, NTBridgeBarSource
from ntbridge.receiver import make_server
from ntbridge.store import BarRejected, BarStore, validate_bar

UTC = timezone.utc
KNOWN = {"1m", "5m", "15m", "1h", "1d"}
NOW = datetime(2026, 7, 31, 15, 0, tzinfo=UTC)


def payload(**overrides):
    base = {
        "instrument": "MNQ",
        "ntInstrument": "MNQ 09-26",
        "timeframe": "1m",
        "timestampUtc": "2026-07-31T14:30:00Z",
        "timestampLocal": "2026-07-31T10:30:00",
        "timeZoneId": "US Eastern Standard Time",
        "open": 21000.25,
        "high": 21010.50,
        "low": 20995.00,
        "close": 21005.75,
        "volume": 1234,
        "bidVolume": None,
        "askVolume": None,
        "source": "ninjatrader",
    }
    base.update(overrides)
    return base


@pytest.fixture
def store(tmp_path) -> BarStore:
    instance = BarStore(tmp_path / "bars.sqlite3")
    yield instance
    instance.close()


# ---------------------------------------------------------------------------
# Validierung - unplausible Kerzen werden abgelehnt, nicht gespeichert
# ---------------------------------------------------------------------------

def test_gueltige_kerze_wird_angenommen():
    record = validate_bar(payload(), known_timeframes=KNOWN, now=NOW)

    assert record.instrument == "MNQ"
    assert record.timeframe == "1m"
    assert record.close == pytest.approx(21005.75)
    assert record.nt_instrument == "MNQ 09-26"


def test_high_kleiner_als_low_wird_abgelehnt():
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(high=20990.0, low=21010.0), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "high_kleiner_low"


def test_widerspruechliches_ohlc_wird_abgelehnt():
    """High muss mindestens so hoch sein wie Open und Close."""
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(high=21000.0, close=21050.0), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "ohlc_widerspruechlich"


def test_negatives_volumen_wird_abgelehnt():
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(volume=-5), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "volumen_ungueltig"


def test_zeitstempel_in_der_zukunft_wird_abgelehnt():
    """Haeufigste Ursache: falsche Zeitzone in NinjaTrader."""
    future = (NOW + timedelta(hours=2)).isoformat()
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(timestampUtc=future), known_timeframes=KNOWN, now=NOW)

    assert exc.value.reason == "zeitstempel_in_zukunft"
    assert "Zeitzone" in exc.value.detail


def test_geringe_uhrabweichung_wird_toleriert():
    knapp = (NOW + timedelta(minutes=2)).isoformat()
    record = validate_bar(payload(timestampUtc=knapp), known_timeframes=KNOWN, now=NOW)
    assert record is not None


def test_unbekannter_timeframe_wird_abgelehnt():
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(timeframe="3m"), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "timeframe_unbekannt"


def test_unlesbarer_zeitstempel_wird_abgelehnt():
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(timestampUtc="kaputt"), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "zeitstempel_unlesbar"


def test_nicht_numerischer_preis_wird_abgelehnt():
    with pytest.raises(BarRejected) as exc:
        validate_bar(payload(close="21.005,75"), known_timeframes=KNOWN, now=NOW)
    assert exc.value.reason == "preis_ungueltig"


def test_symbolzuordnung_wird_angewandt():
    record = validate_bar(
        payload(instrument="MNQ1!"),
        known_timeframes=KNOWN,
        symbol_map={"MNQ1!": "MNQ"},
        now=NOW,
    )
    assert record.instrument == "MNQ"


# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------

def test_kerzen_werden_gespeichert_und_gelesen(store):
    result = store.ingest([payload()], known_timeframes=KNOWN, now=NOW)

    assert result.accepted == 1
    assert result.rejected == 0

    frame = store.load_frame("MNQ", "1m")
    assert len(frame) == 1
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert str(frame.index.tz) == "UTC"


def test_dieselbe_kerze_zweimal_erzeugt_keine_duplikate(store):
    """NinjaTrader schickt beim Neustart die Historie erneut."""
    store.ingest([payload()], known_timeframes=KNOWN, now=NOW)
    store.ingest([payload()], known_timeframes=KNOWN, now=NOW)

    assert len(store.load_frame("MNQ", "1m")) == 1
    assert store.total_bars() == 1


def test_erneutes_senden_ueberschreibt_den_wert(store):
    store.ingest([payload(close=21005.75)], known_timeframes=KNOWN, now=NOW)
    store.ingest([payload(close=21099.00, high=21099.00)], known_timeframes=KNOWN, now=NOW)

    frame = store.load_frame("MNQ", "1m")
    assert len(frame) == 1
    assert frame["close"].iloc[0] == pytest.approx(21099.00)


def test_instrumente_und_timeframes_werden_getrennt_gehalten(store):
    store.ingest(
        [
            payload(instrument="MNQ", timeframe="1m"),
            payload(instrument="MNQ", timeframe="5m"),
            payload(instrument="MGC", timeframe="1m", open=2400.0, high=2401.0,
                    low=2399.0, close=2400.5),
        ],
        known_timeframes=KNOWN,
        now=NOW,
    )

    assert len(store.load_frame("MNQ", "1m")) == 1
    assert len(store.load_frame("MNQ", "5m")) == 1
    assert len(store.load_frame("MGC", "1m")) == 1
    assert len(store.load_frame("MGC", "5m")) == 0


def test_ablehnungsgruende_werden_gezaehlt(store):
    result = store.ingest(
        [payload(), payload(volume=-1), payload(high=1.0, low=2.0)],
        known_timeframes=KNOWN,
        now=NOW,
    )

    assert result.accepted == 1
    assert result.rejected == 2
    assert result.reasons["volumen_ungueltig"] == 1
    assert result.reasons["high_kleiner_low"] == 1


def test_speicher_ueberlebt_neustart(tmp_path):
    path = tmp_path / "bars.sqlite3"

    first = BarStore(path)
    first.ingest([payload()], known_timeframes=KNOWN, now=NOW)
    first.close()

    second = BarStore(path)
    try:
        assert second.total_bars() == 1
        assert len(second.load_frame("MNQ", "1m")) == 1
    finally:
        second.close()


def test_load_frame_liefert_aufsteigend_sortiert(store):
    bars = [
        payload(timestampUtc=f"2026-07-31T14:{minute:02d}:00Z")
        for minute in (35, 31, 33, 30)
    ]
    store.ingest(bars, known_timeframes=KNOWN, now=NOW)

    frame = store.load_frame("MNQ", "1m")
    assert frame.index.is_monotonic_increasing
    assert len(frame) == 4


def test_limit_liefert_die_juengsten_kerzen(store):
    bars = [
        payload(timestampUtc=f"2026-07-31T14:{minute:02d}:00Z")
        for minute in range(20, 40)
    ]
    store.ingest(bars, known_timeframes=KNOWN, now=NOW)

    frame = store.load_frame("MNQ", "1m", limit=5)
    assert len(frame) == 5
    assert frame.index[-1].minute == 39


def test_coverage_meldet_alter_und_umfang(store):
    store.ingest([payload()], known_timeframes=KNOWN, now=NOW)
    coverage = store.coverage()

    assert len(coverage) == 1
    entry = coverage[0]
    assert entry["instrument"] == "MNQ"
    assert entry["timeframe"] == "1m"
    assert entry["bars"] == 1
    assert entry["alter_sekunden"] > 0


# ---------------------------------------------------------------------------
# HTTP-Empfaenger
# ---------------------------------------------------------------------------

@pytest.fixture
def running_server(store):
    server, state = make_server(store, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    yield f"http://127.0.0.1:{port}", state
    server.shutdown()
    server.server_close()


def post(url: str, document: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url + "/bars",
        data=json.dumps(document).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_empfaenger_nimmt_kerzen_an(running_server, store):
    url, state = running_server

    status, body = post(url, {"bars": [payload()]})

    assert status == 200
    assert body["angenommen"] == 1
    assert store.total_bars() == 1
    assert state.accepted == 1


def test_empfaenger_nimmt_ein_ganzes_paket_an(running_server, store):
    url, _ = running_server
    bars = [
        payload(timestampUtc=f"2026-07-31T14:{minute:02d}:00Z")
        for minute in range(10, 40)
    ]

    status, body = post(url, {"bars": bars})

    assert status == 200
    assert body["angenommen"] == 30
    assert store.total_bars() == 30


def test_empfaenger_meldet_abgelehnte_kerzen(running_server):
    url, _ = running_server
    status, body = post(url, {"bars": [payload(), payload(volume=-1)]})

    assert status == 200
    assert body["angenommen"] == 1
    assert body["abgelehnt"] == 1
    assert "volumen_ungueltig" in body["gruende"]


def test_empfaenger_lehnt_kaputtes_json_ab(running_server):
    url, _ = running_server
    request = urllib.request.Request(
        url + "/bars",
        data=b"{kein json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=5)
        pytest.fail("Haette 400 liefern muessen")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400


def test_empfaenger_lehnt_falschen_pfad_ab(running_server):
    url, _ = running_server
    status, _ = post(url.replace("/bars", "") + "/falsch", {"bars": []})
    assert status == 404


def test_status_endpunkt_zeigt_abdeckung(running_server, store):
    url, _ = running_server
    post(url, {"bars": [payload()]})

    with urllib.request.urlopen(url + "/status", timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))

    assert body["status"] == "ok"
    assert body["kerzen_gesamt"] == 1
    assert body["abdeckung"][0]["instrument"] == "MNQ"
    assert body["empfaenger"]["kerzen_angenommen"] == 1


def test_status_ohne_daten_weist_darauf_hin(running_server):
    url, _ = running_server
    with urllib.request.urlopen(url + "/status", timeout=5) as response:
        body = json.loads(response.read().decode("utf-8"))

    assert body["abdeckung"] == []
    assert "NinjaTrader" in body["hinweis"]


# ---------------------------------------------------------------------------
# NTBridgeBarSource
# ---------------------------------------------------------------------------

def fill(store: BarStore, instrument: str, timeframe: str, count: int, minutes: int):
    start = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    bars = []
    for index in range(count):
        stamp = start + timedelta(minutes=index * minutes)
        price = 21000.0 + index * 0.25
        bars.append(
            payload(
                instrument=instrument,
                timeframe=timeframe,
                timestampUtc=stamp.isoformat().replace("+00:00", "Z"),
                open=price, high=price + 2, low=price - 2, close=price + 1,
            )
        )
    store.ingest(bars, known_timeframes=KNOWN, now=datetime.now(UTC))


def test_barsource_liest_aus_dem_speicher(store):
    fill(store, "MNQ", "5m", 100, 5)
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", ["5m"]))

    assert loaded.instrument is MNQ
    assert loaded.sets["5m"].bars_available == 100
    assert loaded.sets["5m"].source == "ninjatrader"
    assert loaded.contract.name == "MNQ 09-26"


def test_barsource_meldet_fehlende_timeframes_einzeln(store):
    fill(store, "MNQ", "5m", 50, 5)
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", ["5m", "15m"]))

    assert "5m" in loaded.sets
    assert "15m" not in loaded.sets
    assert "ClaudeBridge" in loaded.errors["15m"]


def test_barsource_wirft_wenn_gar_nichts_da_ist(store):
    source = NTBridgeBarSource(store)
    with pytest.raises(BarSourceError, match="Keine Kerzen"):
        asyncio.run(source.load("MNQ", ["1m"]))


def test_barsource_beachtet_die_symbolzuordnung(store):
    fill(store, "MNQ", "1m", 10, 1)
    source = NTBridgeBarSource(store, symbol_map={"MGC": "MNQ"})

    loaded = asyncio.run(source.load("MGC", ["1m"]))
    assert loaded.sets["1m"].bars_available == 10


def test_veraltet_flag_schlaegt_an(store):
    """Der juengste Bar ist Stunden alt - NinjaTrader laeuft vermutlich nicht."""
    fill(store, "MNQ", "1m", 10, 1)
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", ["1m"]))
    assert loaded.sets["1m"].is_stale(datetime.now(UTC)) is True


def test_frischer_bar_gilt_nicht_als_veraltet(store):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    store.ingest(
        [payload(timestampUtc=now.isoformat().replace("+00:00", "Z"))],
        known_timeframes=KNOWN,
        now=now + timedelta(seconds=1),
    )
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", ["1m"]))
    assert loaded.sets["1m"].is_stale(now + timedelta(seconds=30)) is False


def test_timeframe_minuten_werden_korrekt_abgeleitet(store):
    fill(store, "MNQ", "1d", 30, 1440)
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", [DAILY]))
    # Tageskerzen: 23 Stunden Sessionlaenge, nicht 24
    assert loaded.sets[DAILY].timeframe_minutes == 23 * 60


def test_kein_delta_ohne_order_flow(store):
    """Ohne Order Flow + gibt es kein Bid-/Ask-Volumen - und keine Schaetzung."""
    fill(store, "MNQ", "1m", 20, 1)
    source = NTBridgeBarSource(store)

    loaded = asyncio.run(source.load("MNQ", ["1m"]))
    assert loaded.sets["1m"].has_flow is False
    assert "bid_volume" not in loaded.sets["1m"].frame.columns
