"""SQLite-Speicher fuer protokollierte Trade-Ideen.

BEWUSST EINE EIGENE DATEI, GETRENNT VON DEN KERZEN
--------------------------------------------------
``data/ntbridge.sqlite3`` wird im laufenden Betrieb vom Empfaenger
beschrieben. Ideen dort mit hineinzuschreiben haette zwei Schreiber auf
derselben Datei bedeutet, ohne dafuer einen Gewinn zu bieten - die beiden
Datensaetze haben unterschiedliche Lebensdauern und werden getrennt
gesichert.

EINE DATENBANK FUER BEIDE PROFILE
---------------------------------
Es gibt bewusst **keine** getrennten Dateien fuer "demo" und "lucid".
Stattdessen traegt jede Idee ein ``profil``-Feld. Bei getrennten Dateien
liesse sich spaeter nicht mehr fragen, wie ein Setup unter dem jeweils
anderen Regelwerk abgeschnitten haette - und genau das ist die eigentliche
Zielfrage des Projekts.

IDEMPOTENZ
----------
Schluessel ist ``(instrument, setup, ts_utc)``. Laeuft die Protokollierung
zweimal ueber denselben Zeitraum, entstehen keine Duplikate. Das ist keine
Bequemlichkeit, sondern Voraussetzung: der Erkennungslauf wird regelmaessig
ueber ein ueberlappendes Fenster gefahren.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ideas.model import TradeIdee

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideen (
    instrument          TEXT    NOT NULL,
    setup               TEXT    NOT NULL,
    ts_utc              TEXT    NOT NULL,
    timeframe           TEXT    NOT NULL,
    richtung            TEXT    NOT NULL,

    entry               REAL    NOT NULL,
    stop                REAL    NOT NULL,
    ziel                REAL    NOT NULL,

    risiko_punkte       REAL    NOT NULL,
    chance_punkte       REAL    NOT NULL,
    crv                 REAL    NOT NULL,
    risiko_usd          REAL    NOT NULL,
    chance_usd          REAL    NOT NULL,
    crv_unter_schwelle  INTEGER NOT NULL,

    profil              TEXT    NOT NULL,
    gefiltert           INTEGER NOT NULL,
    filter_gruende      TEXT    NOT NULL,
    ungeprueft          TEXT    NOT NULL,

    snapshot            TEXT    NOT NULL,
    erzeugt_am_utc      TEXT    NOT NULL,

    PRIMARY KEY (instrument, setup, ts_utc)
);

CREATE INDEX IF NOT EXISTS idx_ideen_zeit
    ON ideen (instrument, ts_utc DESC);

CREATE INDEX IF NOT EXISTS idx_ideen_setup
    ON ideen (setup, profil);
"""


class IdeenStore:
    """Persistenz der protokollierten Ideen."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # check_same_thread=False analog zum Kerzenspeicher: die
        # Serialisierung uebernimmt self._lock.
        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

        with self._lock:
            # WAL: ein Schreiber (Protokollierung) und mehrere Leser
            # (Auswertung, spaeter das MCP-Werkzeug) parallel.
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

    def __enter__(self) -> "IdeenStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- Schreiben ---------------------------------------------------------

    def speichere(self, ideen: Iterable[TradeIdee]) -> int:
        """Legt Ideen ab. Rueckgabe: Anzahl **neu** hinzugekommener Zeilen.

        Bereits vorhandene Schluessel werden aktualisiert statt dupliziert.
        Die Rueckgabe zaehlt bewusst nur die neuen - sonst saehe ein
        wiederholter Lauf ueber denselben Zeitraum wie ein Erfolg aus.
        """
        eintraege: list[TradeIdee] = list(ideen)
        if not eintraege:
            return 0

        jetzt = datetime.now(timezone.utc).isoformat()
        zeilen = [
            (
                idee.instrument,
                idee.setup,
                idee.ts_utc.astimezone(timezone.utc).isoformat(),
                idee.timeframe,
                idee.richtung,
                float(idee.entry),
                float(idee.stop),
                float(idee.ziel),
                float(idee.risiko_punkte),
                float(idee.chance_punkte),
                float(idee.crv),
                float(idee.risiko_usd),
                float(idee.chance_usd),
                int(idee.crv_unter_schwelle),
                idee.profil,
                int(idee.gefiltert),
                json.dumps(list(idee.filter_gruende), ensure_ascii=False),
                json.dumps(list(idee.snapshot.get("ungeprueft", [])), ensure_ascii=False),
                idee.snapshot_json(),
                jetzt,
            )
            for idee in eintraege
        ]

        with self._lock:
            vorher = self._gesamt_ohne_lock()
            self._connection.executemany(
                """
                INSERT INTO ideen (
                    instrument, setup, ts_utc, timeframe, richtung,
                    entry, stop, ziel,
                    risiko_punkte, chance_punkte, crv, risiko_usd, chance_usd,
                    crv_unter_schwelle, profil, gefiltert, filter_gruende,
                    ungeprueft, snapshot, erzeugt_am_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(instrument, setup, ts_utc) DO UPDATE SET
                    timeframe          = excluded.timeframe,
                    richtung           = excluded.richtung,
                    entry              = excluded.entry,
                    stop               = excluded.stop,
                    ziel               = excluded.ziel,
                    risiko_punkte      = excluded.risiko_punkte,
                    chance_punkte      = excluded.chance_punkte,
                    crv                = excluded.crv,
                    risiko_usd         = excluded.risiko_usd,
                    chance_usd         = excluded.chance_usd,
                    crv_unter_schwelle = excluded.crv_unter_schwelle,
                    profil             = excluded.profil,
                    gefiltert          = excluded.gefiltert,
                    filter_gruende     = excluded.filter_gruende,
                    ungeprueft         = excluded.ungeprueft,
                    snapshot           = excluded.snapshot
                """,
                zeilen,
            )
            self._connection.commit()
            return self._gesamt_ohne_lock() - vorher

    # -- Lesen -------------------------------------------------------------

    def _gesamt_ohne_lock(self) -> int:
        cursor = self._connection.execute("SELECT COUNT(*) AS n FROM ideen")
        return int(cursor.fetchone()["n"])

    def gesamt(self) -> int:
        with self._lock:
            return self._gesamt_ohne_lock()

    def lade(
        self,
        *,
        instrument: str | None = None,
        profil: str | None = None,
        nur_ungefiltert: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Ideen als Dicts, juengste zuerst."""
        bedingungen: list[str] = []
        werte: list[Any] = []
        if instrument:
            bedingungen.append("instrument = ?")
            werte.append(instrument.upper())
        if profil:
            bedingungen.append("profil = ?")
            werte.append(profil.lower())
        if nur_ungefiltert:
            bedingungen.append("gefiltert = 0")

        sql = "SELECT * FROM ideen"
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        sql += " ORDER BY ts_utc DESC"
        if limit is not None:
            sql += " LIMIT ?"
            werte.append(int(limit))

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()

        ergebnis: list[dict[str, Any]] = []
        for zeile in zeilen:
            datensatz = dict(zeile)
            datensatz["filter_gruende"] = json.loads(datensatz["filter_gruende"])
            datensatz["ungeprueft"] = json.loads(datensatz["ungeprueft"])
            datensatz["snapshot"] = json.loads(datensatz["snapshot"])
            datensatz["crv_unter_schwelle"] = bool(datensatz["crv_unter_schwelle"])
            datensatz["gefiltert"] = bool(datensatz["gefiltert"])
            ergebnis.append(datensatz)
        return ergebnis

    def anzahl_je_setup(self, *, profil: str | None = None) -> dict[str, dict[str, int]]:
        """Wie viele Ideen je Setup - getrennt nach gefiltert/ungefiltert.

        Grundlage fuer die Schwelle "unter N Ideen gilt als zu wenig Daten"
        in Etappe D.
        """
        sql = (
            "SELECT setup, gefiltert, COUNT(*) AS n FROM ideen "
            + ("WHERE profil = ? " if profil else "")
            + "GROUP BY setup, gefiltert"
        )
        werte = [profil.lower()] if profil else []

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()

        ergebnis: dict[str, dict[str, int]] = {}
        for zeile in zeilen:
            eintrag = ergebnis.setdefault(zeile["setup"], {"gesamt": 0, "handelbar": 0, "gefiltert": 0})
            anzahl = int(zeile["n"])
            eintrag["gesamt"] += anzahl
            if int(zeile["gefiltert"]):
                eintrag["gefiltert"] += anzahl
            else:
                eintrag["handelbar"] += anzahl
        return ergebnis

    def letzter_zeitpunkt(self, instrument: str) -> datetime | None:
        """Juengster protokollierter Zeitpunkt - erlaubt ueberlappende Laeufe."""
        with self._lock:
            zeile = self._connection.execute(
                "SELECT MAX(ts_utc) AS neueste FROM ideen WHERE instrument = ?",
                (instrument.upper(),),
            ).fetchone()
        if zeile is None or zeile["neueste"] is None:
            return None
        return datetime.fromisoformat(zeile["neueste"])


__all__ = ["SCHEMA", "IdeenStore"]
