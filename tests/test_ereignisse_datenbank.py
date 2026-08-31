"""Die Ereignisdatenbank: Schema, Schreibweg, Kontext, Cluster.

Der wichtigste Test ist hier ``test_kontext_wird_am_verfuegbarkeitszeitpunkt
_gelesen``: die Erkenner sind lookahead-sicher, aber wenn der Schreibweg den
Kontext eine Kerze zu spaet liest, ist die ganze Datenbank wertlos - und
nichts an den Zahlen verriete es.
"""

from __future__ import annotations

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.basis import Ereignis
from common.ereignisse.datenbank import (
    CLUSTER_FENSTER_BARS,
    datensatz_block,
    notiere_lauf,
    oeffne,
    schreibe_events,
    vergib_cluster,
    zaehle,
)
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


@pytest.fixture()
def conn(tmp_path):
    verbindung = oeffne(tmp_path / "eventdb.sqlite3")
    yield verbindung
    verbindung.close()


def _rahmen(config, n: int = 600, start: str = "2022-06-01 14:00") -> pd.DataFrame:
    rng = np.random.default_rng(5)
    preise = 20000.0 + np.cumsum(rng.normal(0, 5, n))
    index = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise, "high": preise + 4, "low": preise - 4,
            "close": preise, "volume": rng.integers(200, 2000, n).astype(float),
        },
        index=index,
    )
    return compute_indicators(df, config.indicators, config.market.session)


def _ereignis(idx: int, *, richtung: int = 1, typ: str = "test_muster") -> Ereignis:
    return Ereignis(
        pattern_type=typ,
        pattern_variant="A",
        detect_timeframe="1m",
        direction=richtung,
        entstehung_idx=max(0, idx - 5),
        bestaetigung_idx=idx,
        verfuegbar_idx=idx,
        merkmale={"level_1": 100.0, "level_2": 110.0, "eigenes_feld": "x"},
    )


# -- Schema -----------------------------------------------------------------

def test_schema_legt_alle_tabellen_an(conn):
    namen = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "events", "outcomes", "outcome_klassen", "triggers",
        "stop_szenarien", "laeufe",
    } <= namen


def test_outcomes_haengen_nicht_an_der_schwelle(conn):
    """Rohzahlen und Klassen sind getrennt: MFE/MAE haengen nicht von der
    Klassifikationsschwelle ab, nur die Klasse tut das. Beides in einer
    Tabelle waeren 70 statt 23 Mio Zeilen fuer denselben Inhalt."""
    outcome_spalten = {b[1] for b in conn.execute("PRAGMA table_info(outcomes)")}
    klassen_spalten = {
        b[1] for b in conn.execute("PRAGMA table_info(outcome_klassen)")
    }
    assert "schwelle_atr" not in outcome_spalten
    assert "schwelle_atr" in klassen_spalten
    assert "mfe_pkt" in outcome_spalten
    assert "klasse" in klassen_spalten


def test_outcomes_werden_geschrieben(conn, config):
    from common.ereignisse.datenbank import schreibe_outcomes
    from common.ereignisse.outcomes import alle_horizonte

    df = _rahmen(config, n=2000)
    idx = np.array([100, 300, 500])
    richtung = np.array([1, -1, 1])
    ereignisse = [_ereignis(int(i), richtung=int(r)) for i, r in zip(idx, richtung)]
    schreibe_events(conn, ereignisse, df, lauf_id="L1")
    ids = [r[0] for r in conn.execute(
        "SELECT event_id FROM events ORDER BY event_id"
    )]

    ergebnis = alle_horizonte(df, idx, richtung, horizonte=(5, 20))
    n = schreibe_outcomes(conn, ids, ergebnis)
    assert n == 6, "3 Ereignisse x 2 Horizonte"

    zeile = conn.execute(
        "SELECT horizont_bars, mfe_pkt, mae_pkt, end_pkt, mfe_r, atr_referenz "
        "FROM outcomes WHERE event_id = ? AND horizont_bars = 5", (ids[0],)
    ).fetchone()
    assert zeile[0] == 5
    assert zeile[1] >= 0 and zeile[2] >= 0, "Exkursionen sind nie negativ"
    assert zeile[5] is not None, "ATR-Bezug fehlt"


def test_ungueltige_outcomes_werden_nicht_geschrieben(conn, config):
    """Eine Zeile voller NULL saehe aus wie eine Messung, die zufaellig
    nichts ergab. Sie fehlt lieber."""
    from common.ereignisse.datenbank import schreibe_outcomes
    from common.ereignisse.outcomes import alle_horizonte

    df = _rahmen(config, n=300)
    # 295 + 1 Einstieg + 20 Horizont passt nicht mehr in 300 Kerzen.
    idx = np.array([100, 295])
    richtung = np.array([1, 1])
    ereignisse = [_ereignis(int(i)) for i in idx]
    schreibe_events(conn, ereignisse, df, lauf_id="L1")
    ids = [r[0] for r in conn.execute(
        "SELECT event_id FROM events ORDER BY event_id"
    )]

    n = schreibe_outcomes(conn, ids, alle_horizonte(df, idx, richtung,
                                                   horizonte=(20,)))
    assert n == 1, "das unvollstaendige Fenster wurde geschrieben"
    (geschrieben,) = conn.execute(
        "SELECT event_id FROM outcomes"
    ).fetchone()
    assert geschrieben == ids[0]


def test_outcome_reihenfolge_wird_geprueft(conn, config):
    """Passen event_ids und Outcomes nicht zusammen, landen Ergebnisse beim
    falschen Ereignis - und man saehe es keiner Zeile an."""
    from common.ereignisse.datenbank import schreibe_outcomes
    from common.ereignisse.outcomes import alle_horizonte

    df = _rahmen(config, n=1000)
    idx = np.array([100, 300])
    ergebnis = alle_horizonte(df, idx, np.array([1, 1]), horizonte=(5,))
    with pytest.raises(ValueError, match="Reihenfolge"):
        schreibe_outcomes(conn, ["nur-eine-id"], ergebnis)


def test_event_spalten_stimmen_mit_dem_schema_ueberein(conn):
    """Laufen die beiden auseinander, schreibt der Schreibweg still in die
    falsche Spalte - eine zu wenig meldet SQLite, ein vertauschtes Paar
    gleicher Typen nicht."""
    from common.ereignisse.datenbank import EVENT_SPALTEN

    im_schema = [
        b[1] for b in conn.execute("PRAGMA table_info(events)")
    ]
    assert list(EVENT_SPALTEN) == im_schema


# -- Vektorisierte Zeitfelder ----------------------------------------------

def test_iso_strings_sind_zeichengleich_mit_isoformat():
    """Der schnelle Weg muss AUF DAS ZEICHEN dasselbe liefern wie
    ``Timestamp.isoformat()``.

    Weicht das Format ab, sind die Zeilen eines Laufs nicht mehr mit denen
    eines frueheren vergleichbar - und man saehe es keiner einzelnen Zeile an.
    """
    from common.ereignisse.datenbank import _iso_strings

    for start, freq, n in (
        ("2019-05-06 00:01", "1min", 500),
        ("2026-08-28 21:00", "1h", 100),
        ("2020-03-08 06:00", "1min", 300),   # US-Zeitumstellung
        ("2020-11-01 05:00", "1min", 300),
    ):
        index = pd.date_range(start, periods=n, freq=freq, tz="UTC")
        schnell = _iso_strings(index)
        langsam = [t.isoformat() for t in index]
        assert schnell == langsam, f"Format weicht ab bei {start}/{freq}"


def test_iso_strings_faellt_bei_bruchteilsekunden_zurueck():
    """Mit Mikrosekunden greift der schnelle Weg nicht - dann muss der
    langsame, aber immer richtige einspringen."""
    from common.ereignisse.datenbank import _iso_strings

    index = pd.DatetimeIndex(
        ["2026-01-05T09:00:00.123456+00:00", "2026-01-05T09:01:00.500000+00:00"]
    )
    assert _iso_strings(index) == [t.isoformat() for t in index]


def test_minuten_seit_open_serie_gleicht_der_einzelrechnung():
    """Vektorisiert muss dasselbe herauskommen wie je Zeitstempel - inklusive
    Sommerzeit, wo 13:30 UTC mal 09:30 ET ist und mal 08:30."""
    from zoneinfo import ZoneInfo

    from common.ereignisse.datenbank import _minuten_seit_open_serie

    for start in ("2026-08-03 12:00", "2026-01-05 12:00"):   # Sommer / Winter
        index = pd.date_range(start, periods=240, freq="1min", tz="UTC")
        serie = _minuten_seit_open_serie(index)
        for k, t in enumerate(index):
            lokal = t.tz_convert(ZoneInfo("America/New_York"))
            erwartet = (lokal.hour * 60 + lokal.minute) - (9 * 60 + 30)
            assert int(serie[k]) == erwartet


def test_session_serie_gleicht_primary_session():
    """Der Cache darf das Urteil nicht veraendern - nur die Zahl der
    Aufrufe."""
    from common.ereignisse.datenbank import _session_serie
    from common.sessions import primary_session

    index = pd.date_range("2026-08-03 00:00", periods=2000, freq="7min", tz="UTC")
    serie = _session_serie(index)
    for k, t in enumerate(index):
        assert serie[k] == primary_session(t.to_pydatetime())


def test_indizes_werden_angelegt(conn):
    namen = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_%'"
        )
    }
    assert "idx_events_typ" in namen
    assert "idx_events_regime" in namen


def test_massenschreiben_baut_die_indizes_wieder_auf(tmp_path, config):
    """Fuer den Volllauf werden die Indizes verworfen und danach neu gebaut.

    Mit stehenden Indizes brauchte das Schreiben von 2,59 Mio Zeilen 7.087
    Sekunden - fuenf Sekundaerindizes bei jeder Zeile zu pflegen ist der
    teuerste Teil daran. Danach muessen sie aber wieder da sein, sonst ist
    jede Abfrage der Datenbank ein voller Tabellendurchlauf.
    """
    from common.ereignisse.datenbank import massenschreiben

    verbindung = oeffne(tmp_path / "massen.sqlite3", mit_indizes=False)
    try:
        vorher = {
            r[0] for r in verbindung.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name LIKE 'idx_%'"
            )
        }
        assert not vorher, "mit_indizes=False hat trotzdem Indizes angelegt"

        df = _rahmen(config)
        n = massenschreiben(
            verbindung, [_ereignis(100), _ereignis(200)], df, lauf_id="L1"
        )
        assert n == 2

        nachher = {
            r[0] for r in verbindung.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name LIKE 'idx_%'"
            )
        }
        assert "idx_events_typ" in nachher
        assert "idx_events_regime" in nachher
        assert "idx_outcomes_horizont" in nachher
        # Und die Daten sind da.
        (anzahl,) = verbindung.execute("SELECT COUNT(*) FROM events").fetchone()
        assert anzahl == 2
    finally:
        verbindung.close()


def test_schema_ist_idempotent(tmp_path):
    pfad = tmp_path / "db.sqlite3"
    a = oeffne(pfad)
    a.close()
    b = oeffne(pfad)   # zweimal oeffnen darf nicht scheitern
    b.close()


# -- Datensatzblock ---------------------------------------------------------

def test_blockgrenzen_sind_fest():
    """Sie duerfen NICHT mit dem Datenbestand wandern - sonst ist ein
    Ergebnis von heute nicht mit einem von naechster Woche vergleichbar."""
    assert datensatz_block(pd.Timestamp("2019-06-01", tz="UTC")) == "train"
    assert datensatz_block(pd.Timestamp("2023-12-31 12:00", tz="UTC")) == "train"
    assert datensatz_block(pd.Timestamp("2024-01-01", tz="UTC")) == "validation"
    assert datensatz_block(pd.Timestamp("2024-12-31 12:00", tz="UTC")) == "validation"
    assert datensatz_block(pd.Timestamp("2025-01-01", tz="UTC")) == "oos"
    assert datensatz_block(pd.Timestamp("2026-08-31", tz="UTC")) == "oos"


def test_block_landet_in_der_zeile(conn, config):
    df = _rahmen(config, start="2022-06-01 14:00")
    schreibe_events(conn, [_ereignis(100)], df, lauf_id="L1")
    (block,) = conn.execute("SELECT datensatz_block FROM events").fetchone()
    assert block == "train"

    df2 = _rahmen(config, start="2025-06-01 14:00")
    schreibe_events(conn, [_ereignis(100)], df2, lauf_id="L2")
    bloecke = {r[0] for r in conn.execute("SELECT datensatz_block FROM events")}
    assert bloecke == {"train", "oos"}


# -- Cluster ----------------------------------------------------------------

def test_gleichzeitige_gleichgerichtete_ereignisse_teilen_ein_cluster():
    """Um 15:35 koennen Doppelboden, Flagge und Sweep denselben Einstieg in
    dieselbe Richtung ergeben - drei Zeilen, aber keine drei unabhaengigen
    Beobachtungen (Plan 12.1)."""
    ereignisse = [
        _ereignis(100, typ="doppelboden"),
        _ereignis(101, typ="flagge"),
        _ereignis(102, typ="sweep"),
    ]
    zuordnung = vergib_cluster(ereignisse)
    ids = {zuordnung[i][0] for i in range(3)}
    assert len(ids) == 1, "drei gleichzeitige Signale, aber nicht ein Cluster"
    assert all(zuordnung[i][1] == 3 for i in range(3))


def test_verschiedene_richtungen_sind_verschiedene_cluster():
    ereignisse = [_ereignis(100, richtung=1), _ereignis(100, richtung=-1)]
    zuordnung = vergib_cluster(ereignisse)
    assert zuordnung[0][0] != zuordnung[1][0]


def test_weit_auseinander_ist_kein_cluster():
    weit = CLUSTER_FENSTER_BARS + 5
    ereignisse = [_ereignis(100), _ereignis(100 + weit)]
    zuordnung = vergib_cluster(ereignisse)
    assert zuordnung[0][0] != zuordnung[1][0]
    assert zuordnung[0][1] == 1 and zuordnung[1][1] == 1


def test_cluster_laeuft_nicht_als_kette_davon():
    """Festes Fenster ab dem ersten Ereignis, KEINE transitive Kette.

    Eine Kette (A-B, B-C, also A-B-C) klingt richtiger, laeuft auf 1m-Daten
    mit sieben Erkennern aber davon - gemessen entstanden Cluster aus 58
    Ereignissen ueber mehrere Minuten. Das waeren keine gleichzeitigen
    Signale mehr, sondern eine ganze Bewegung.
    """
    schritt = CLUSTER_FENSTER_BARS
    ereignisse = [_ereignis(100 + k * schritt) for k in range(10)]
    zuordnung = vergib_cluster(ereignisse)

    ids = {zuordnung[i][0] for i in range(10)}
    assert len(ids) > 1, "die Kette hat alles zu einem Cluster verschmolzen"
    # Kein Cluster darf laenger sein als das Fenster erlaubt.
    for i in range(10):
        assert zuordnung[i][1] <= CLUSTER_FENSTER_BARS + 1


def test_cluster_groesse_ist_durch_das_fenster_begrenzt():
    """Auf einer dichten Ereignisfolge - eine Kette wuerde hier alles
    zusammenziehen."""
    ereignisse = [_ereignis(100 + k) for k in range(60)]
    zuordnung = vergib_cluster(ereignisse)
    groessen = {zuordnung[i][1] for i in range(60)}
    assert max(groessen) <= CLUSTER_FENSTER_BARS + 1, (
        f"Cluster zu gross: {max(groessen)}"
    )


# -- Schreibweg und Kontext -------------------------------------------------

def test_ereignis_landet_vollstaendig_in_der_tabelle(conn, config):
    df = _rahmen(config)
    n = schreibe_events(conn, [_ereignis(200)], df, lauf_id="L1")
    assert n == 1

    zeile = conn.execute("SELECT * FROM events").fetchone()
    spalten = [b[0] for b in conn.execute("SELECT * FROM events").description]
    daten = dict(zip(spalten, zeile))

    assert daten["pattern_type"] == "test_muster"
    assert daten["direction"] == 1
    assert daten["verfuegbar_idx"] == 200
    assert daten["verfuegbar_ts"] == df.index[200].isoformat()
    assert daten["level_1"] == 100.0
    assert daten["pattern_hoehe_pkt"] == 10.0
    assert daten["preis"] == pytest.approx(float(df["close"].iloc[200]))
    assert daten["atr"] == pytest.approx(float(df["atr"].iloc[200]))
    assert daten["instrument"] == "MNQ"
    # Musterspezifisches geht nicht verloren.
    assert json.loads(daten["merkmale_json"])["eigenes_feld"] == "x"


def test_kontext_wird_am_verfuegbarkeitszeitpunkt_gelesen(conn, config):
    """Der wichtigste Test dieser Datei.

    Die Erkenner sind lookahead-sicher. Liest der Schreibweg den Kontext eine
    Kerze zu spaet, ist die ganze Datenbank wertlos - und nichts an den Zahlen
    verriete es. Geprueft, indem die Reihe hinter dem Ereignis abgeschnitten
    wird: der Kontext muss identisch bleiben.
    """
    df = _rahmen(config, n=600)
    idx = 300
    voll = oeffne(":memory:")
    kurz = oeffne(":memory:")
    try:
        schreibe_events(conn=voll, ereignisse=[_ereignis(idx)],
                        rahmen=df, lauf_id="L")
        schreibe_events(conn=kurz, ereignisse=[_ereignis(idx)],
                        rahmen=df.iloc[: idx + 1], lauf_id="L")
        felder = (
            "preis, atr, abstand_vwap_atr, abstand_pdh_atr, abstand_pdl_atr, "
            "vola_regime, struktur_regime, session, wochentag, "
            "minuten_seit_open, volumen_relativ"
        )
        a = voll.execute(f"SELECT {felder} FROM events").fetchone()
        b = kurz.execute(f"SELECT {felder} FROM events").fetchone()
        assert a == b, "Kontext haengt von Kerzen NACH dem Ereignis ab"
    finally:
        voll.close()
        kurz.close()


def test_fehlende_kontextspalte_bleibt_none_statt_geraten(conn, config):
    """Invariante 11: eine fehlende Regime-Angabe ist eine ehrliche Luecke;
    eine geratene waere eine Falschaussage mit Autoritaet."""
    df = _rahmen(config)
    assert "vola_regime" not in df.columns   # bewusst nicht angereichert
    schreibe_events(conn, [_ereignis(200)], df, lauf_id="L1")
    (vola,) = conn.execute("SELECT vola_regime FROM events").fetchone()
    assert vola is None


def test_ereignis_ausserhalb_des_rahmens_bricht_ab(conn, config):
    df = _rahmen(config, n=100)
    with pytest.raises(ValueError, match="ausserhalb"):
        schreibe_events(conn, [_ereignis(500)], df, lauf_id="L1")


def test_rollgrenze_wird_markiert_nicht_verworfen(conn, config):
    """Plan Entscheidung 4: markieren, nicht generell ausschliessen."""
    df = _rahmen(config, n=600)
    naht = df.index[300]
    schreibe_events(
        conn, [_ereignis(300), _ereignis(50)], df,
        lauf_id="L1", rollgrenzen=[naht], rollgrenze_bars=10,
    )
    zeilen = dict(
        conn.execute("SELECT verfuegbar_idx, nahe_rollgrenze FROM events")
    )
    assert zeilen[300] == 1
    assert zeilen[50] == 0
    assert len(zeilen) == 2, "Ereignis an der Naht wurde verworfen"


def test_wiederholtes_schreiben_verdoppelt_nicht(conn, config):
    df = _rahmen(config)
    schreibe_events(conn, [_ereignis(200)], df, lauf_id="L1")
    schreibe_events(conn, [_ereignis(200)], df, lauf_id="L1")
    (n,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    assert n == 1


def test_verschiedene_laeufe_bleiben_nebeneinander(conn, config):
    df = _rahmen(config)
    schreibe_events(conn, [_ereignis(200)], df, lauf_id="L1")
    schreibe_events(conn, [_ereignis(200)], df, lauf_id="L2")
    (n,) = conn.execute("SELECT COUNT(*) FROM events").fetchone()
    assert n == 2


def test_lauf_wird_protokolliert(conn, config):
    df = _rahmen(config)
    notiere_lauf(
        conn, lauf_id="L1", instrument="MNQ", rahmen=df,
        erkenner=["fvg", "sweeps"], ereignisse=7, notiz="Test",
    )
    zeile = conn.execute("SELECT * FROM laeufe").fetchone()
    assert zeile[0] == "L1"
    assert zeile[3] == len(df)
    assert "fvg" in zeile[6]


def test_zaehle_gibt_den_ueberblick(conn, config):
    df = _rahmen(config)
    schreibe_events(
        conn,
        [_ereignis(100, typ="a"), _ereignis(200, typ="a"), _ereignis(300, typ="b")],
        df, lauf_id="L1",
    )
    uebersicht = zaehle(conn)
    assert set(uebersicht["pattern_type"]) == {"a", "b"}
    assert int(uebersicht.loc[uebersicht["pattern_type"] == "a", "n"].iloc[0]) == 2


def test_leere_liste_schreibt_nichts(conn, config):
    assert schreibe_events(conn, [], _rahmen(config), lauf_id="L1") == 0


def test_echte_erkenner_lassen_sich_schreiben(conn, config):
    """Der Durchstich: echte Ereignisse aus einem echten Erkenner."""
    from common.ereignisse.fvg import fvg_serie

    df = _rahmen(config, n=2000)
    ereignisse = fvg_serie(df)
    assert ereignisse, "der Erkenner muss auf diesen Daten etwas finden"

    n = schreibe_events(conn, ereignisse, df, lauf_id="ECHT")
    assert n == len(ereignisse)

    # Die Kernmerkmale des FVG muessen in den Spalten stehen.
    zeile = conn.execute(
        "SELECT level_1, level_2, pattern_hoehe_pkt, merkmale_json "
        "FROM events LIMIT 1"
    ).fetchone()
    assert zeile[0] is not None and zeile[1] is not None
    assert zeile[2] == pytest.approx(abs(zeile[1] - zeile[0]))
    assert "spanne_ticks" in json.loads(zeile[3])
