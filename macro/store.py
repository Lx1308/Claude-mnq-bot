"""SQLite-Speicher fuer Makro-Beobachtungen - eigene Datei, siehe unten warum.

EIGENE DATENBANK
-----------------
Weder ``ntbridge.sqlite3`` (wird vom Empfaenger im laufenden Betrieb
beschrieben) noch ``ideas.sqlite3`` (eigene Lebensdauer, eigener Zweck) sind
der richtige Ort. Makrodaten sind eine dritte, eigenstaendige Datenart -
"getrennte Dateien je Datenart", MASTERPLAN.md Abschnitt L.

REVISIONEN WERDEN NIE UEBERSCHRIEBEN
--------------------------------------
``speichere()`` fuegt neue Vintages hinzu, aendert aber NIE eine bestehende
Zeile. Ein Backtest, der zum Zeitpunkt T gerechnet wurde, muss auch nach
zehn weiteren Revisionen derselben Reihe exakt denselben Wert liefern, wenn
er erneut gegen dieselbe Datenbank laeuft - genau das macht Makrodaten fuer
Research ueberhaupt erst benutzbar (Masterplan K: "Ohne Vintage-Modellierung
ist jede Makro-Research wertlos").

DER LOOKAHEAD-SICHERE LESEPFAD IST DIE EIGENTLICHE FUNKTION DIESES MODULS
-----------------------------------------------------------------------------
``stand_zum_zeitpunkt()`` ist der einzige Weg, wie Research an einen
Makrowert kommen soll. Ein direktes ``SELECT actual FROM ... WHERE
beobachtungszeitraum_utc = X`` waere fast immer falsch - es liefert die
NEUESTE Revision, nicht die zum jeweiligen Analysezeitpunkt bekannte.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from macro.model import MacroObservation

SCHEMA = """
CREATE TABLE IF NOT EXISTS economic_events (
    event_id                   INTEGER PRIMARY KEY AUTOINCREMENT,

    source                     TEXT    NOT NULL,
    source_event_id            TEXT    NOT NULL,
    event_name                 TEXT    NOT NULL,
    event_type                 TEXT    NOT NULL,

    beobachtungszeitraum_utc   TEXT    NOT NULL,
    scheduled_at_utc           TEXT,
    released_at_utc            TEXT    NOT NULL,
    available_at_utc           TEXT    NOT NULL,
    revision                   INTEGER NOT NULL,
    revision_at_utc            TEXT    NOT NULL,

    actual                     TEXT    NOT NULL,
    forecast                   TEXT,
    previous                   TEXT,

    country                    TEXT    NOT NULL DEFAULT 'US',
    currency                   TEXT    NOT NULL DEFAULT 'USD',
    category                   TEXT,
    importance                 TEXT,
    status                     TEXT    NOT NULL DEFAULT 'released',
    source_url                 TEXT,

    created_at_utc              TEXT    NOT NULL
);

-- Ein Vintage ist unveraenderlich und genau einmal vorhanden. Erneutes
-- Einspielen derselben ALFRED-Antwort darf keine Duplikate erzeugen, siehe
-- ON CONFLICT DO NOTHING in speichere().
CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_events_vintage
    ON economic_events (source, source_event_id, available_at_utc);

-- Der lookahead-sichere Lesepfad: "juengster Vintage <= T fuer diese Reihe".
CREATE INDEX IF NOT EXISTS idx_economic_events_zeitreise
    ON economic_events (source, source_event_id, available_at_utc);

-- Provenienz je Quelle - wandert mit der Datei, analog
-- backtest/data/dukascopy_store.py::herkunft.
CREATE TABLE IF NOT EXISTS herkunft (
    quelle          TEXT    PRIMARY KEY,
    beschreibung    TEXT    NOT NULL,
    zuletzt_geholt_utc TEXT
);
"""


class MacroStore:
    """Persistenz der Makro-Beobachtungen."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.executescript(SCHEMA)
            self._connection.commit()

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "MacroStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- Schreiben -----------------------------------------------------

    def speichere(self, beobachtungen: Iterable[MacroObservation]) -> int:
        """Legt neue Vintages ab. Rueckgabe: Anzahl **neu** gespeicherter Zeilen.

        Bestehende Vintages werden NIE aktualisiert - siehe Moduldocstring.
        ``ON CONFLICT DO NOTHING`` statt ``DO UPDATE`` ist hier bewusst
        gewaehlt, anders als bei ``ideas/store.py``: dort sollen sich
        Kerngroessen bei Ueberlappung noch aendern duerfen, hier NIE.
        """
        eintraege = list(beobachtungen)
        if not eintraege:
            return 0

        jetzt = datetime.now(timezone.utc).isoformat()
        zeilen = [
            (
                b.source,
                b.source_event_id,
                b.event_name,
                b.event_type,
                b.beobachtungszeitraum_utc.astimezone(timezone.utc).isoformat(),
                b.scheduled_at_utc.astimezone(timezone.utc).isoformat() if b.scheduled_at_utc else None,
                b.released_at_utc.astimezone(timezone.utc).isoformat(),
                b.available_at_utc.astimezone(timezone.utc).isoformat(),
                int(b.revision),
                b.revision_at_utc.astimezone(timezone.utc).isoformat(),
                b.actual,
                b.forecast,
                b.previous,
                b.country,
                b.currency,
                b.category,
                b.importance,
                b.status,
                b.source_url,
                jetzt,
            )
            for b in eintraege
        ]

        with self._lock:
            vorher = self._anzahl_ohne_lock()
            self._connection.executemany(
                """
                INSERT INTO economic_events (
                    source, source_event_id, event_name, event_type,
                    beobachtungszeitraum_utc, scheduled_at_utc, released_at_utc,
                    available_at_utc, revision, revision_at_utc,
                    actual, forecast, previous,
                    country, currency, category, importance, status, source_url,
                    created_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT (source, source_event_id, available_at_utc) DO NOTHING
                """,
                zeilen,
            )
            self._connection.commit()
            return self._anzahl_ohne_lock() - vorher

    def setze_herkunft(self, quelle: str, beschreibung: str) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO herkunft (quelle, beschreibung, zuletzt_geholt_utc)
                VALUES (?, ?, ?)
                ON CONFLICT (quelle) DO UPDATE SET
                    beschreibung = excluded.beschreibung,
                    zuletzt_geholt_utc = excluded.zuletzt_geholt_utc
                """,
                (quelle, beschreibung, datetime.now(timezone.utc).isoformat()),
            )
            self._connection.commit()

    # -- Lesen: der lookahead-sichere Pfad ------------------------------

    def stand_zum_zeitpunkt(
        self, source: str, source_event_id: str, zeitpunkt: datetime
    ) -> dict[str, Any] | None:
        """Der Wert, wie er zu ``zeitpunkt`` bekannt war - oder ``None``.

        ``None`` heisst: entweder gibt es diese Reihe nicht, oder sie war zu
        ``zeitpunkt`` noch nicht veroeffentlicht. Beides wird bewusst NICHT
        unterschieden (waere eine Vermutung ueber die Zukunft der Reihe) -
        der Aufrufer behandelt beides gleich: kein Wert verfuegbar.
        """
        if zeitpunkt.tzinfo is None:
            raise ValueError(
                "stand_zum_zeitpunkt() braucht einen zeitzonenbewussten "
                f"Zeitpunkt, bekam einen naiven: {zeitpunkt!r}"
            )
        grenze = zeitpunkt.astimezone(timezone.utc).isoformat()

        with self._lock:
            zeile = self._connection.execute(
                """
                SELECT * FROM economic_events
                WHERE source = ? AND source_event_id = ? AND available_at_utc <= ?
                ORDER BY available_at_utc DESC
                LIMIT 1
                """,
                (source, source_event_id, grenze),
            ).fetchone()
        return dict(zeile) if zeile is not None else None

    def alle_vintages(self, source: str, source_event_id: str) -> list[dict[str, Any]]:
        """Alle Revisionen einer Reihe, chronologisch - fuer Inspektion und Tests."""
        with self._lock:
            zeilen = self._connection.execute(
                """
                SELECT * FROM economic_events
                WHERE source = ? AND source_event_id = ?
                ORDER BY available_at_utc ASC
                """,
                (source, source_event_id),
            ).fetchall()
        return [dict(z) for z in zeilen]

    def _anzahl_ohne_lock(self) -> int:
        cursor = self._connection.execute("SELECT COUNT(*) AS n FROM economic_events")
        return int(cursor.fetchone()["n"])

    def gesamt(self) -> int:
        with self._lock:
            return self._anzahl_ohne_lock()


__all__ = ["SCHEMA", "MacroStore"]
