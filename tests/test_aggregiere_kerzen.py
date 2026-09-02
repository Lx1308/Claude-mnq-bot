"""Vorberechnung der groben Timeframes aus 1m.

Seit dem NT8-Import liegen ~2,5 Mio MNQ-Minutenkerzen vor, aber nur als 1m.
werkzeuge/aggregiere_kerzen.py leitet 1h/4h/1d daraus ab und speichert sie,
damit der Chart die volle Historie zeigen kann, ohne bei jeder Anfrage alles
neu zu aggregieren. Dieselbe Resampling-Regel wie im Backtest (Invariante 1).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ntbridge.store import BarStore
from werkzeuge.aggregiere_kerzen import aggregiere

UTC = timezone.utc


def _fuelle_1m(store: BarStore, start: datetime, minuten: int, basis: float = 20000.0) -> None:
    """Ein einfacher Sägezahn - Hauptsache gueltige, aufsteigende Kerzen."""
    saetze = []
    for i in range(minuten):
        ts = start + timedelta(minutes=i)
        preis = basis + (i % 120) * 0.25
        saetze.append({
            "instrument": "MNQ",
            "timeframe": "1m",
            "timestampUtc": ts.isoformat(),
            "open": preis,
            "high": preis + 1.0,
            "low": preis - 1.0,
            "close": preis + 0.5,
            "volume": 100.0,
            "source": "nt8_export",
        })
    res = store.ingest(saetze, known_timeframes={"1m"}, symbol_map={})
    assert res.accepted == minuten


@pytest.fixture
def db(tmp_path):
    pfad = tmp_path / "bars.sqlite3"
    store = BarStore(pfad)
    # Vier Handelstage, damit sich Tageskerzen bilden.
    _fuelle_1m(store, datetime(2024, 3, 4, 0, 0, tzinfo=UTC), 4 * 24 * 60)
    store.close()
    return pfad


def test_grobe_timeframes_werden_geschrieben(db):
    ergebnis = aggregiere(db, symbol="MNQ", voll=True)

    assert set(ergebnis) == {"1h", "4h", "1d"}
    assert all(anzahl > 0 for anzahl in ergebnis.values())

    store = BarStore(db)
    try:
        for tf in ("1h", "4h", "1d"):
            df = store.load_frame("MNQ", tf)
            assert not df.empty, tf
        tages = store.load_frame("MNQ", "1d")
        # Vier Kalendertage 1m-Daten - der CME-Handelstag beginnt 18:00 ET am
        # Vortag, also ergeben sich vier bis fuenf Tagesbuckets.
        assert 3 <= len(tages) <= 6
    finally:
        store.close()


def test_abgeleitete_zeilen_sind_als_solche_gekennzeichnet(db):
    aggregiere(db, symbol="MNQ", voll=True)

    store = BarStore(db)
    try:
        conn = store._connection
        quellen = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT source FROM bars WHERE instrument='MNQ' "
                "AND timeframe IN ('1h','4h','1d')"
            )
        }
        assert quellen == {"resampled_1m"}
    finally:
        store.close()


def test_einminuten_reihe_bleibt_unangetastet(db):
    store = BarStore(db)
    try:
        vorher = len(store.load_frame("MNQ", "1m"))
    finally:
        store.close()

    aggregiere(db, symbol="MNQ", voll=True)

    store = BarStore(db)
    try:
        nachher = store.load_frame("MNQ", "1m")
        assert len(nachher) == vorher
        # nichts davon traegt die abgeleitete Quelle
        conn = store._connection
        row = conn.execute(
            "SELECT COUNT(*) FROM bars WHERE instrument='MNQ' AND timeframe='1m' "
            "AND source='resampled_1m'"
        ).fetchone()
        assert row[0] == 0
    finally:
        store.close()


def test_tageskerze_deckt_sich_mit_manueller_aggregation(db):
    aggregiere(db, symbol="MNQ", voll=True)

    store = BarStore(db)
    try:
        eins = store.load_frame("MNQ", "1m")
        tag = store.load_frame("MNQ", "1d")
    finally:
        store.close()

    # Das Gesamt-High/Low der Tagesreihe muss dem der Minutenreihe entsprechen
    # (Buckets luecken- und ueberschneidungsfrei), und jeder Tages-Close muss
    # ein echter Minuten-Close aus dem Bestand sein.
    assert tag["high"].max() == pytest.approx(eins["high"].max())
    assert tag["low"].min() == pytest.approx(eins["low"].min())
    echte_closes = set(round(float(c), 4) for c in eins["close"])
    for c in tag["close"]:
        assert round(float(c), 4) in echte_closes


def test_inkrementell_zieht_neue_buckets_nach(db):
    aggregiere(db, symbol="MNQ", voll=True)

    store = BarStore(db)
    try:
        vor_1h = len(store.load_frame("MNQ", "1h"))
        letzte_1m = store.load_frame("MNQ", "1m").index[-1]
        _fuelle_1m(store, letzte_1m + timedelta(minutes=1), 6 * 60, basis=20500.0)
    finally:
        store.close()

    ergebnis = aggregiere(db, symbol="MNQ", voll=False)
    assert ergebnis["1h"] > 0

    store = BarStore(db)
    try:
        nach_1h = len(store.load_frame("MNQ", "1h"))
    finally:
        store.close()
    assert nach_1h > vor_1h
