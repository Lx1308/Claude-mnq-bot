"""Die Ereignisdatenbank: Schema, Schreibweg, Kontextanreicherung.

Etappe 2 aus ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``. Hier wird aus den
Ereignislisten der Erkenner eine abfragbare Wissensbasis.

VIER TABELLEN
-------------
``events``          ein Datensatz je erkanntem Muster
``outcomes``        Kursverlauf je Ereignis und Horizont   (Etappe 4)
``triggers``        Entry-Varianten je Ereignis            (Etappe 6)
``stop_szenarien``  Ereignis x Entry x Stop-Position       (Etappe 7)

Hier entsteht das Schema fuer alle vier und der Schreibweg fuer ``events``.

WARUM KERNSPALTEN + JSON
------------------------
Ein Doppelboden hat andere Rohmerkmale als ein Liquidity Sweep. Ein festes
Schema je Mustertyp waere entweder lueckenhaft oder aufgeblaeht (siehe
``basis.py``). Deshalb:

* die im Plan benannten **Kernmerkmale** (``level_1``, ``level_2``,
  ``level_neckline``, Groesse, Dauer) als echte Spalten - danach wird
  gefiltert und sortiert;
* alles Musterspezifische zusaetzlich als JSON in ``merkmale_json``.

Nichts geht verloren, und die haeufigen Abfragen bleiben schnell.

WAS BEIM SCHREIBEN DAZUKOMMT
----------------------------
Die Erkenner liefern nur Indizes und Rohmerkmale. Erst hier kommt der
**Kontext zum Verfuegbarkeitszeitpunkt** dazu: ATR, Regime, Session,
Wochentag, Abstand zu VWAP und Vortagesmarken, relatives Volumen,
Kontraktnaht, Datensatzblock. Das ist der eigentliche Wert der Datenbank -
ohne ihn liesse sich nicht fragen, ob ein Muster in ruhigen Phasen anders
laeuft als in bewegten.

**Jede Kontextspalte wird am ``verfuegbar_idx`` gelesen**, nie spaeter. Ein
Test prueft das, indem er die Reihe abschneidet und vergleicht.

CLUSTER (Plan Abschnitt 12.1)
-----------------------------
Ereignisse, die dicht beieinander in dieselbe Richtung feuern, beschreiben
oft **dieselbe** Marktbewegung aus verschiedenen Blickwinkeln. Sie bekommen
eine gemeinsame ``cluster_id``; in der Signifikanzpruefung zaehlt ein Cluster
als eine Beobachtung. Die Einzelzeilen bleiben erhalten - die Reduktion
passiert beim Auswerten, nicht beim Schreiben.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis

#: Innerhalb wie vieler 1m-Kerzen zwei gleichgerichtete Ereignisse als
#: derselbe Vorgang gelten. Drei: bei 1m-Handel ist das die Spanne, in der
#: ein Einstieg praktisch derselbe waere.
CLUSTER_FENSTER_BARS = 3

#: Feste Blockgrenzen (Plan Abschnitt 11, entschieden am 30.08.2026). Sie
#: wandern NICHT mit dem Datenbestand - sonst waere ein Ergebnis von heute
#: nicht mit einem von naechster Woche vergleichbar.
TRAINING_BIS = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")
VALIDATION_BIS = pd.Timestamp("2024-12-31 23:59:59", tz="UTC")


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id            TEXT PRIMARY KEY,
    pattern_type        TEXT NOT NULL,
    pattern_variant     TEXT NOT NULL,
    detect_timeframe    TEXT NOT NULL,
    direction           INTEGER NOT NULL,

    -- Die vier Phasen. NUR verfuegbar_* darf in eine Auswertung.
    entstehung_ts       TEXT NOT NULL,
    bestaetigung_ts     TEXT NOT NULL,
    verfuegbar_ts       TEXT NOT NULL,
    entstehung_idx      INTEGER NOT NULL,
    bestaetigung_idx    INTEGER NOT NULL,
    verfuegbar_idx      INTEGER NOT NULL,
    dauer_bars          INTEGER NOT NULL,

    -- Kernmerkmale (Plan Abschnitt 9). Musterspezifisches in merkmale_json.
    level_1             REAL,
    level_2             REAL,
    level_neckline      REAL,
    pattern_hoehe_pkt   REAL,
    pattern_hoehe_atr   REAL,

    -- Kontext zum Verfuegbarkeitszeitpunkt
    preis               REAL,
    atr                 REAL,
    vola_regime         TEXT,
    struktur_regime     TEXT,
    liquiditaet_regime  TEXT,
    session             TEXT,
    wochentag           INTEGER,
    minuten_seit_open   INTEGER,
    struktur_trend      INTEGER,
    abstand_vwap_atr    REAL,
    abstand_pdh_atr     REAL,
    abstand_pdl_atr     REAL,
    volumen_relativ     REAL,
    volumen_am_extremum_relativ REAL,

    -- Klumpen (Plan 12.1)
    cluster_id          TEXT,
    cluster_groesse     INTEGER,

    -- Herkunft
    instrument          TEXT NOT NULL,
    nahe_rollgrenze     INTEGER NOT NULL DEFAULT 0,
    datensatz_block     TEXT NOT NULL,
    lauf_id             TEXT NOT NULL,

    merkmale_json       TEXT NOT NULL
);

-- Rohzahlen des Kursverlaufs. Sie haengen NICHT von der
-- Klassifikationsschwelle ab - nur die Klasse tut das. Deshalb hier der
-- Schluessel (event_id, horizont_bars) und die Klassen in einer eigenen
-- Tabelle: die Rohzahlen dreimal zu speichern (fuer s = 0,25/0,5/1,0) waeren
-- 70 statt 23 Mio Zeilen fuer denselben Inhalt.
CREATE TABLE IF NOT EXISTS outcomes (
    event_id            TEXT NOT NULL,
    horizont_bars       INTEGER NOT NULL,
    entry_preis         REAL,
    atr_referenz        REAL,
    mfe_pkt             REAL,
    mfe_r               REAL,
    zeit_bis_mfe        INTEGER,
    mae_pkt             REAL,
    mae_r               REAL,
    zeit_bis_mae        INTEGER,
    end_pkt             REAL,
    end_r               REAL,
    end_prozent         REAL,

    PRIMARY KEY (event_id, horizont_bars),
    FOREIGN KEY (event_id) REFERENCES events (event_id)
);

-- Outcome-Klassen je Schwelle (Plan Abschnitt 6). Getrennt von den
-- Rohzahlen, weil sie von der Schwelle abhaengen und diese bewusst
-- variiert wird (0,25 / 0,5 / 1,0 x ATR), um zu zeigen, wie stark das
-- Ergebnis daran haengt.
--
-- klasse_stop_zuerst / klasse_ziel_zuerst: bei Intrabar-Ambiguitaet ist aus
-- OHLC nicht rekonstruierbar, was zuerst kam (Plan Abschnitt 9,
-- Gemini-Punkt B). Beide Annahmen werden gerechnet; liegen die Ergebnisse
-- weit auseinander, haengt die Aussage an der Annahme und gehoert so
-- gekennzeichnet.
CREATE TABLE IF NOT EXISTS outcome_klassen (
    event_id            TEXT NOT NULL,
    horizont_bars       INTEGER NOT NULL,
    schwelle_atr        REAL NOT NULL,
    klasse              TEXT,
    klasse_stop_zuerst  TEXT,
    klasse_ziel_zuerst  TEXT,
    intrabar_ambig      INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (event_id, horizont_bars, schwelle_atr),
    FOREIGN KEY (event_id) REFERENCES events (event_id)
);

CREATE TABLE IF NOT EXISTS triggers (
    event_id            TEXT NOT NULL,
    entry_type          TEXT NOT NULL,
    ausgeloest          INTEGER NOT NULL,
    trigger_ts          TEXT,
    trigger_idx         INTEGER,
    entry_preis         REAL,
    verzoegerung_bars   INTEGER,

    -- Orderart und gemessene Nichtfuellung (Plan Abschnitt 9, Gemini-Punkt A).
    -- Slippage steht bewusst NICHT hier: sie ist aus OHLCV nicht messbar und
    -- kommt in der Auswertung als benanntes Szenario dazu (Invariante 10/11).
    order_art           TEXT,
    limit_durchhandelt  INTEGER,
    nichtfuellung_grund TEXT,

    PRIMARY KEY (event_id, entry_type),
    FOREIGN KEY (event_id) REFERENCES events (event_id)
);

CREATE TABLE IF NOT EXISTS stop_szenarien (
    event_id            TEXT NOT NULL,
    entry_type          TEXT NOT NULL,
    stop_bezug          TEXT NOT NULL,
    stop_abstand_atr    REAL NOT NULL,
    stop_preis          REAL,
    getroffen           INTEGER NOT NULL,
    zeit_bis_stop       INTEGER,
    fall                TEXT,
    ziel_erreicht_trotz_stop INTEGER,
    r_ergebnis          REAL,

    PRIMARY KEY (event_id, entry_type, stop_bezug, stop_abstand_atr),
    FOREIGN KEY (event_id) REFERENCES events (event_id)
);

CREATE TABLE IF NOT EXISTS laeufe (
    lauf_id             TEXT PRIMARY KEY,
    gestartet_utc       TEXT NOT NULL,
    instrument          TEXT NOT NULL,
    kerzen              INTEGER NOT NULL,
    von_ts              TEXT,
    bis_ts              TEXT,
    erkenner            TEXT NOT NULL,
    ereignisse          INTEGER NOT NULL DEFAULT 0,
    notiz               TEXT
);
"""


#: Die Spalten von ``events``, in der Reihenfolge, in der ``schreibe_events``
#: sie fuellt. Ausdruecklich benannt statt auf Positionen zu vertrauen -
#: siehe die Pruefung in ``schreibe_events``.
EVENT_SPALTEN: tuple[str, ...] = (
    "event_id", "pattern_type", "pattern_variant", "detect_timeframe",
    "direction",
    "entstehung_ts", "bestaetigung_ts", "verfuegbar_ts",
    "entstehung_idx", "bestaetigung_idx", "verfuegbar_idx", "dauer_bars",
    "level_1", "level_2", "level_neckline",
    "pattern_hoehe_pkt", "pattern_hoehe_atr",
    "preis", "atr",
    "vola_regime", "struktur_regime", "liquiditaet_regime",
    "session", "wochentag", "minuten_seit_open", "struktur_trend",
    "abstand_vwap_atr", "abstand_pdh_atr", "abstand_pdl_atr",
    "volumen_relativ", "volumen_am_extremum_relativ",
    "cluster_id", "cluster_groesse",
    "instrument", "nahe_rollgrenze", "datensatz_block", "lauf_id",
    "merkmale_json",
)


#: Die Sekundaerindizes von ``events``, getrennt vom Schema gehalten.
#:
#: WARUM GETRENNT: beim ersten Volllauf (31.08.2026) dauerte das Schreiben von
#: 2,59 Mio Zeilen **7.087 Sekunden** - 2,7 ms je Zeile, rund hundertmal
#: langsamer als SQLite kann. Ursache: jeder ``INSERT`` pflegt fuenf
#: Sekundaerindizes mit, und die Suche nach dem Primaerschluessel laeuft dabei
#: durch eine auf 622 MB angewachsene WAL-Datei. Indizes **nach** dem
#: Masseneinfuegen anzulegen ist der Standardweg; ``massenschreiben`` tut das.
INDIZES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_events_typ "
    "ON events (pattern_type, pattern_variant, detect_timeframe)",
    "CREATE INDEX IF NOT EXISTS idx_events_block "
    "ON events (datensatz_block, pattern_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_zeit ON events (verfuegbar_ts)",
    "CREATE INDEX IF NOT EXISTS idx_events_cluster ON events (cluster_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_regime "
    "ON events (vola_regime, struktur_regime, liquiditaet_regime)",
    "CREATE INDEX IF NOT EXISTS idx_outcomes_horizont "
    "ON outcomes (horizont_bars)",
    "CREATE INDEX IF NOT EXISTS idx_klassen_horizont "
    "ON outcome_klassen (horizont_bars, schwelle_atr)",
)

_INDEXNAMEN = ("idx_events_typ", "idx_events_block", "idx_events_zeit",
               "idx_events_cluster", "idx_events_regime",
               "idx_outcomes_horizont", "idx_klassen_horizont")


def oeffne(pfad: str | Path, *, mit_indizes: bool = True) -> sqlite3.Connection:
    """Verbindung mit Schema, WAL und vernuenftigen Schreibeinstellungen.

    ``mit_indizes=False`` laesst die Sekundaerindizes weg - fuer einen
    Massenlauf, der sie danach ueber ``lege_indizes_an`` erzeugt.
    """
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(pfad))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    if mit_indizes:
        lege_indizes_an(conn)
    conn.commit()
    return conn


def lege_indizes_an(conn: sqlite3.Connection) -> None:
    """Die Sekundaerindizes erzeugen (idempotent)."""
    for befehl in INDIZES:
        conn.execute(befehl)
    conn.commit()


def loesche_indizes(conn: sqlite3.Connection) -> None:
    """Die Sekundaerindizes verwerfen - vor einem Masseneinfuegen.

    Der Primaerschluessel bleibt; ohne ihn koennte ``INSERT OR REPLACE``
    Doppelte nicht erkennen.
    """
    for name in _INDEXNAMEN:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()


def datensatz_block(zeitpunkt: pd.Timestamp) -> str:
    """``train`` | ``validation`` | ``oos`` nach den festen Grenzen."""
    if zeitpunkt <= TRAINING_BIS:
        return "train"
    if zeitpunkt <= VALIDATION_BIS:
        return "validation"
    return "oos"


def _blockspalte(index: pd.DatetimeIndex) -> np.ndarray:
    """Vektorisiert - bei 2,5 Mio Kerzen ist eine Schleife spuerbar."""
    werte = np.full(len(index), "oos", dtype=object)
    werte[index <= VALIDATION_BIS] = "validation"
    werte[index <= TRAINING_BIS] = "train"
    return werte


def vergib_cluster(
    ereignisse: Sequence[Ereignis], *, fenster: int = CLUSTER_FENSTER_BARS
) -> dict[int, tuple[str, int]]:
    """Gleichzeitige gleichgerichtete Ereignisse bekommen dieselbe Cluster-ID.

    Rueckgabe ``{position_in_der_liste: (cluster_id, cluster_groesse)}``.

    Zwei Ereignisse gehoeren zusammen, wenn ihre ``verfuegbar_idx`` hoechstens
    ``fenster`` Kerzen **vom ersten Ereignis des Clusters** entfernt liegen und
    die Richtung gleich ist.

    Warum das noetig ist: um 15:35 koennen ein Doppelboden, eine Flagge und
    ein Sweep denselben Einstiegspreis in dieselbe Richtung ergeben. Als drei
    Zeilen gezaehlt verdreifachen sie die Stichprobe, ohne dass es drei
    unabhaengige Beobachtungen waeren (Plan 12.1).

    **Festes Fenster, keine transitive Kette.** Eine Kette (A-B, B-C, also
    A-B-C) klingt zunaechst richtiger, laeuft auf 1m-Daten mit sieben
    Erkennern aber davon: gemessen entstanden so Cluster aus 58 Ereignissen
    ueber mehrere Minuten. Das waeren keine gleichzeitigen Signale mehr,
    sondern eine ganze Bewegung - und sie auf **eine** Beobachtung zu
    reduzieren wuerde die Stichprobe zu stark schrumpfen. Das feste Fenster
    fasst nur das zusammen, was tatsaechlich zeitgleich ist.
    """
    zuordnung: dict[int, tuple[str, int]] = {}
    if not ereignisse:
        return zuordnung

    for richtung in (1, -1):
        gleich = [
            (i, e.verfuegbar_idx)
            for i, e in enumerate(ereignisse)
            if e.direction == richtung
        ]
        gleich.sort(key=lambda paar: paar[1])

        gruppe: list[int] = []
        anker = None
        for pos, idx in gleich:
            if anker is not None and idx - anker > fenster:
                _schreibe_cluster(zuordnung, gruppe, ereignisse, richtung)
                gruppe = []
                anker = None
            if anker is None:
                anker = idx
            gruppe.append(pos)
        _schreibe_cluster(zuordnung, gruppe, ereignisse, richtung)

    return zuordnung


def _schreibe_cluster(
    zuordnung: dict[int, tuple[str, int]],
    gruppe: list[int],
    ereignisse: Sequence[Ereignis],
    richtung: int,
) -> None:
    if not gruppe:
        return
    anker = ereignisse[gruppe[0]].verfuegbar_idx
    cid = f"C{richtung:+d}-{anker:09d}"
    for pos in gruppe:
        zuordnung[pos] = (cid, len(gruppe))


@dataclass(frozen=True)
class Kontextquellen:
    """Welche Spalten des vorbereiteten Rahmens als Kontext gelesen werden.

    Fehlt eine, bleibt das Feld ``None`` - **nicht** geschaetzt (Invariante
    11). Eine fehlende Regime-Angabe ist eine ehrliche Luecke; eine geratene
    waere eine Falschaussage mit Autoritaet.
    """

    atr: str = "atr"
    vwap: str = "vwap"
    pdh: str = "prev_session_high"
    pdl: str = "prev_session_low"
    vola_regime: str = "vola_regime"
    struktur_regime: str = "struktur_regime"
    liquiditaet_regime: str = "liquiditaet_regime"
    struktur_trend: str = "struktur_trend"
    volumen_relativ: str = "volumen_relativ"


def _spalte(df: pd.DataFrame, name: str) -> np.ndarray | None:
    if name not in df.columns:
        return None
    return df[name].to_numpy()


def _wert(arr: np.ndarray | None, i: int) -> Any:
    """Ein Wert oder ``None`` - NaN wird zu None, nicht zu 0."""
    if arr is None:
        return None
    v = arr[i]
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (bool, np.bool_)):
        return int(v)
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _abstand_atr(preis: float, niveau: Any, atr: Any) -> float | None:
    if niveau is None or atr is None or not atr:
        return None
    return round((preis - float(niveau)) / float(atr), 4)


def schreibe_events(
    conn: sqlite3.Connection,
    ereignisse: Sequence[Ereignis],
    rahmen: pd.DataFrame,
    *,
    lauf_id: str,
    instrument: str = "MNQ",
    rollgrenzen: Iterable[pd.Timestamp] = (),
    rollgrenze_bars: int = 30,
    quellen: Kontextquellen | None = None,
    stapel: int = 20_000,
) -> int:
    """Ereignisse mit ihrem Kontext in ``events`` schreiben.

    ``rahmen`` ist der vorbereitete 1m-Rahmen, auf dessen Indizes die
    Ereignisse verankert sind. ``rollgrenzen`` sind die Kontraktnahtstellen
    aus ``NtBridgeDataProvider.rollgrenzen``; Ereignisse innerhalb von
    ``rollgrenze_bars`` davon werden markiert (**nicht** verworfen - Plan
    Entscheidung 4).

    Rueckgabe: Zahl der geschriebenen Zeilen.
    """
    if not ereignisse:
        return 0
    quellen = quellen or Kontextquellen()

    index = rahmen.index
    n = len(rahmen)
    for e in ereignisse:
        if not (0 <= e.entstehung_idx <= e.verfuegbar_idx < n):
            raise ValueError(
                f"Ereignis {e.pattern_type} liegt ausserhalb des Rahmens "
                f"(0..{n - 1}): {e.entstehung_idx}..{e.verfuegbar_idx}"
            )

    schluss = rahmen["close"].to_numpy(dtype=float)
    atr = _spalte(rahmen, quellen.atr)
    vwap = _spalte(rahmen, quellen.vwap)
    pdh = _spalte(rahmen, quellen.pdh)
    pdl = _spalte(rahmen, quellen.pdl)
    vola = _spalte(rahmen, quellen.vola_regime)
    struktur = _spalte(rahmen, quellen.struktur_regime)
    liquiditaet = _spalte(rahmen, quellen.liquiditaet_regime)
    trend = _spalte(rahmen, quellen.struktur_trend)
    vol_rel = _spalte(rahmen, quellen.volumen_relativ)

    bloecke = _blockspalte(index)
    wochentage = index.dayofweek.to_numpy()
    naht = _rollnaehe(index, rollgrenzen, rollgrenze_bars)
    cluster = vergib_cluster(ereignisse)

    # Alles, was nur vom Zeitstempel abhaengt, EINMAL vektorisiert statt je
    # Ereignis. Gemessen am 31.08.2026: die drei ``index[i].isoformat()`` und
    # die beiden Zeitzonenumrechnungen je Zeile machten 24 von 36 Sekunden
    # aus - bei 2,59 Mio Ereignissen also Stunden.
    iso = _iso_strings(index)
    minuten_open = _minuten_seit_open_serie(index)
    sessions = _session_serie(index)

    zeilen = []
    for pos, e in enumerate(ereignisse):
        i = e.verfuegbar_idx
        a = _wert(atr, i)
        preis = float(schluss[i])
        cid, cgroesse = cluster.get(pos, (None, None))
        m = e.merkmale

        hoehe = m.get("pattern_hoehe_pkt")
        if hoehe is None and m.get("level_1") is not None and m.get("level_2") is not None:
            hoehe = abs(float(m["level_2"]) - float(m["level_1"]))

        zeilen.append((
            f"{lauf_id}-{pos:09d}",
            e.pattern_type, e.pattern_variant, e.detect_timeframe, e.direction,
            iso[e.entstehung_idx],
            iso[e.bestaetigung_idx],
            iso[i],
            e.entstehung_idx, e.bestaetigung_idx, i, e.dauer_bars,
            m.get("level_1"), m.get("level_2"), m.get("level_neckline"),
            round(hoehe, 4) if hoehe is not None else None,
            round(hoehe / a, 4) if (hoehe is not None and a) else None,
            preis, a,
            _wert(vola, i), _wert(struktur, i), _wert(liquiditaet, i),
            sessions[i],
            int(wochentage[i]),
            int(minuten_open[i]),
            _wert(trend, i),
            _abstand_atr(preis, _wert(vwap, i), a),
            _abstand_atr(preis, _wert(pdh, i), a),
            _abstand_atr(preis, _wert(pdl, i), a),
            _wert(vol_rel, i),
            m.get("volumen_am_extremum_relativ"),
            cid, cgroesse,
            instrument, int(naht[i]), str(bloecke[i]), lauf_id,
            json.dumps(m, separators=(",", ":"), default=str),
        ))

    # Spalten ausdruecklich benennen statt auf die Reihenfolge zu vertrauen:
    # ein "?" zu wenig ergibt sonst eine Fehlermeldung ueber Spaltenzahlen,
    # ein VERTAUSCHTES Paar gleicher Typen dagegen gar keine - und dann
    # stuende der Kontext still in der falschen Spalte.
    frage = (
        f"INSERT OR REPLACE INTO events ({','.join(EVENT_SPALTEN)}) VALUES ("
        + ",".join("?" * len(EVENT_SPALTEN))
        + ")"
    )
    if zeilen and len(zeilen[0]) != len(EVENT_SPALTEN):
        raise AssertionError(
            f"{len(zeilen[0])} Werte je Zeile, aber {len(EVENT_SPALTEN)} "
            "Spalten benannt - EVENT_SPALTEN und der Zeilenaufbau sind "
            "auseinandergelaufen."
        )
    geschrieben = 0
    for start in range(0, len(zeilen), stapel):
        teil = zeilen[start : start + stapel]
        conn.executemany(frage, teil)
        geschrieben += len(teil)
        # Je Stapel abschliessen und die WAL zurueckschneiden. Ohne das
        # waechst sie ungebremst (gemessen 622 MB), und die
        # Primaerschluesselpruefung jedes weiteren INSERT muss sich durch sie
        # hindurcharbeiten - das Schreiben wird mit jeder Zeile langsamer.
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    conn.commit()
    return geschrieben


def massenschreiben(
    conn: sqlite3.Connection,
    ereignisse: Sequence[Ereignis],
    rahmen: pd.DataFrame,
    **kwargs: Any,
) -> int:
    """``schreibe_events`` fuer grosse Mengen: Indizes weg, schreiben, Indizes
    neu.

    Beim ersten Volllauf ueber die 1m-Historie (2,59 Mio Ereignisse) brauchte
    das Schreiben MIT stehenden Indizes 7.087 Sekunden. Fuenf Sekundaerindizes
    bei jeder einzelnen Zeile zu pflegen ist der teuerste Teil daran; sie am
    Stueck aufzubauen ist um Groessenordnungen billiger.

    Fuer kleine Mengen ist ``schreibe_events`` richtig - dort waere das
    Neuaufbauen der Indizes teurer als das Pflegen.
    """
    loesche_indizes(conn)
    try:
        return schreibe_events(conn, ereignisse, rahmen, **kwargs)
    finally:
        lege_indizes_an(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()


def _rollnaehe(
    index: pd.DatetimeIndex,
    rollgrenzen: Iterable[pd.Timestamp],
    bars: int,
) -> np.ndarray:
    """Bool-Array: liegt diese Kerze nahe einer Kontraktnaht?

    Der Preissprung an der Naht ist ein Artefakt der Verkettung, kein
    Marktereignis - fuer Gap- und Ausbruchsmuster ein Scheinsignal (Plan
    Abschnitt 2). Markiert, nicht verworfen (Entscheidung 4).
    """
    naht = np.zeros(len(index), dtype=bool)
    for grenze in rollgrenzen:
        pos = int(index.searchsorted(pd.Timestamp(grenze)))
        naht[max(0, pos - bars) : min(len(index), pos + bars + 1)] = True
    return naht


def _iso_strings(index: pd.DatetimeIndex) -> list[str]:
    """ISO-Zeitstempel fuer den ganzen Index, in einem Zug.

    ``index[i].isoformat()`` je Ereignis kostet bei Millionen Zeilen Stunden -
    jeder Zugriff baut ein ``Timestamp``-Objekt. ``strftime`` arbeitet auf dem
    ganzen Index.

    Nur fuer UTC-Indizes ohne Bruchteilsekunden; sonst faellt die Funktion auf
    den langsamen, aber immer richtigen Weg zurueck. Das Format muss auf den
    Zeichen genau dem entsprechen, was ``Timestamp.isoformat()`` liefert -
    sonst laesst sich ein spaeterer Lauf nicht mit einem frueheren vergleichen.
    """
    ganze_sekunden = bool((index.microsecond == 0).all()) and bool(
        (index.nanosecond == 0).all()
    )
    if ganze_sekunden and str(index.tz) == "UTC":
        return [s + "+00:00" for s in index.strftime("%Y-%m-%dT%H:%M:%S")]
    return [t.isoformat() for t in index]


def _minuten_seit_open_serie(index: pd.DatetimeIndex) -> np.ndarray:
    """Minuten seit der RTH-Eroeffnung (09:30 ET) fuer den ganzen Index.

    Negativ davor. Eine Zeitzonenumrechnung fuer alles statt einer je Zeile.
    """
    from zoneinfo import ZoneInfo

    lokal = index.tz_convert(ZoneInfo("America/New_York"))
    return (
        lokal.hour.to_numpy() * 60 + lokal.minute.to_numpy()
    ) - (9 * 60 + 30)


def _session_serie(index: pd.DatetimeIndex) -> list[str]:
    """Sessionname je Kerze - ueber einen Nachschlagecache.

    ``primary_session`` haengt ausschliesslich an Wochentag und Uhrzeit (in
    CT). Es gibt also hoechstens 7 x 1440 verschiedene Antworten. Statt die
    Funktion millionenfach zu rufen, wird sie je Kombination **einmal**
    gefragt.

    Bewusst dieselbe Funktion und keine vektorisierte Neufassung: eine zweite
    Sessionlogik waere derselbe Fehler wie eine zweite Indikatorrechnung
    (Invariante 1).
    """
    from common.sessions import primary_session

    schluessel = (
        index.dayofweek.to_numpy() * 1440
        + index.hour.to_numpy() * 60
        + index.minute.to_numpy()
    )
    cache: dict[int, str] = {}
    namen: list[str] = []
    for k, zeitpunkt in zip(schluessel, index):
        name = cache.get(int(k))
        if name is None:
            name = primary_session(zeitpunkt.to_pydatetime())
            cache[int(k)] = name
        namen.append(name)
    return namen


#: Die Spalten von ``outcomes``, in Schreibreihenfolge.
OUTCOME_SPALTEN: tuple[str, ...] = (
    "event_id", "horizont_bars", "entry_preis", "atr_referenz",
    "mfe_pkt", "mfe_r", "zeit_bis_mfe",
    "mae_pkt", "mae_r", "zeit_bis_mae",
    "end_pkt", "end_r", "end_prozent",
)


def schreibe_outcomes(
    conn: sqlite3.Connection,
    event_ids: Sequence[str],
    outcomes_je_horizont: dict[int, Any],
    *,
    stapel: int = 50_000,
) -> int:
    """Outcome-Rohzahlen schreiben - alle Horizonte auf einmal.

    ``event_ids`` sind die ``event_id``-Werte in **derselben Reihenfolge**,
    in der die Ereignisse an ``berechne_outcomes`` gegeben wurden.
    ``outcomes_je_horizont`` ist das Ergebnis von
    ``common.ereignisse.outcomes.alle_horizonte``.

    **Ungueltige Zeilen werden nicht geschrieben.** Ein Ereignis, dessen
    Fenster nicht vollstaendig in die Reihe passt, hat fuer diesen Horizont
    kein Ergebnis - und eine Zeile voller NULL saehe aus wie eine Messung,
    die zufaellig nichts ergab (Invariante 11). Es fehlt lieber.
    """
    frage = (
        f"INSERT OR REPLACE INTO outcomes ({','.join(OUTCOME_SPALTEN)}) "
        "VALUES (" + ",".join("?" * len(OUTCOME_SPALTEN)) + ")"
    )
    geschrieben = 0

    for horizont, o in sorted(outcomes_je_horizont.items()):
        if len(o) != len(event_ids):
            raise ValueError(
                f"Horizont {horizont}: {len(o)} Outcomes, aber "
                f"{len(event_ids)} event_ids - die Reihenfolge stimmt nicht."
            )
        gueltig = np.nonzero(o.gueltig)[0]
        if not len(gueltig):
            continue

        zeilen = [
            (
                event_ids[k], horizont,
                _f(o.entry_preis[k]), _f(o.atr_referenz[k]),
                _f(o.mfe_pkt[k]), _f(o.mfe_r[k]), int(o.zeit_bis_mfe[k]),
                _f(o.mae_pkt[k]), _f(o.mae_r[k]), int(o.zeit_bis_mae[k]),
                _f(o.end_pkt[k]), _f(o.end_r[k]), _f(o.end_prozent[k]),
            )
            for k in gueltig
        ]
        for start in range(0, len(zeilen), stapel):
            conn.executemany(frage, zeilen[start : start + stapel])
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            geschrieben += len(zeilen[start : start + stapel])

    conn.commit()
    return geschrieben


def _f(wert: Any) -> float | None:
    """NaN wird zu ``None`` - SQLite kennt kein NaN, und ``NULL`` ist die
    ehrliche Antwort auf 'nicht berechenbar'."""
    if wert is None:
        return None
    w = float(wert)
    return None if not np.isfinite(w) else w


def notiere_lauf(
    conn: sqlite3.Connection,
    *,
    lauf_id: str,
    instrument: str,
    rahmen: pd.DataFrame,
    erkenner: Sequence[str],
    ereignisse: int,
    notiz: str = "",
) -> None:
    """Herkunftseintrag - welcher Lauf hat diese Zeilen erzeugt.

    Ohne den liesse sich spaeter nicht sagen, aus welchem Datenstand und mit
    welchen Erkennern eine Zahl stammt.
    """
    conn.execute(
        "INSERT OR REPLACE INTO laeufe VALUES (?,?,?,?,?,?,?,?,?)",
        (
            lauf_id,
            pd.Timestamp.now("UTC").isoformat(),
            instrument,
            len(rahmen),
            rahmen.index[0].isoformat() if len(rahmen) else None,
            rahmen.index[-1].isoformat() if len(rahmen) else None,
            ",".join(erkenner),
            ereignisse,
            notiz,
        ),
    )
    conn.commit()


def zaehle(conn: sqlite3.Connection) -> pd.DataFrame:
    """Ereignisse je Typ, Variante und Datensatzblock - der schnelle
    Ueberblick ueber das, was in der Datenbank steht."""
    return pd.read_sql_query(
        "SELECT pattern_type, pattern_variant, detect_timeframe, "
        "datensatz_block, COUNT(*) AS n "
        "FROM events GROUP BY 1,2,3,4 ORDER BY n DESC",
        conn,
    )


__all__ = [
    "CLUSTER_FENSTER_BARS",
    "EVENT_SPALTEN",
    "INDIZES",
    "OUTCOME_SPALTEN",
    "Kontextquellen",
    "SCHEMA",
    "TRAINING_BIS",
    "VALIDATION_BIS",
    "datensatz_block",
    "lege_indizes_an",
    "loesche_indizes",
    "massenschreiben",
    "notiere_lauf",
    "oeffne",
    "schreibe_events",
    "schreibe_outcomes",
    "vergib_cluster",
    "zaehle",
]
