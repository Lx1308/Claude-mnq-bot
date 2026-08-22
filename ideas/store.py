"""SQLite-Speicher fuer Ideen und Beobachtungen.

EIGENE DATEI, GETRENNT VON DEN KERZEN
-------------------------------------
``data/ntbridge.sqlite3`` wird im laufenden Betrieb vom Empfaenger
beschrieben. Ideen dort hineinzuschreiben haette zwei Schreiber auf derselben
Datei bedeutet, ohne Gewinn - die beiden Datensaetze haben unterschiedliche
Lebensdauern und werden getrennt gesichert.

EINE DATENBANK, ZWEI TABELLEN, EINE RICHTUNG
--------------------------------------------
``ideen`` und ``observations`` liegen in derselben Datei, sind aber strikt
getrennt: :meth:`IdeenStore.lade_fuer_auswertung` ist der einzige Weg, auf
dem Etappe D an Daten kommt, und er liest ausschliesslich ``ideen``. Ein Test
sichert zu, dass diese Methode das Wort ``observations`` nicht einmal
erwaehnt. Ohne diese Sperre schliche sich ueber eine Abkuerzung genau das
nicht-reproduzierbare LLM-Rauschen in die Erwartungswert-Statistik, das die
Trennung verhindern soll.

EINE DATENBANK FUER ALLE PROFILE
--------------------------------
Es gibt bewusst **keine** getrennten Dateien je Kontoumgebung. Jede Idee
traegt ein ``profil``-Feld. Bei getrennten Dateien liesse sich spaeter nicht
mehr fragen, wie ein Setup unter dem jeweils anderen Regelwerk abgeschnitten
haette - und genau das ist die Zielfrage des Projekts.

IDEMPOTENZ TROTZ AUTOINCREMENT-SCHLUESSEL
-----------------------------------------
``idea_id`` ist der Primaerschluessel, taugt aber nicht zur Duplikaterkennung:
derselbe Lauf zweimal ausgefuehrt vergaebe zwei verschiedene ids fuer
dieselbe Idee. Der Erkennungslauf laeuft regelmaessig ueber ein
ueberlappendes Fenster, deshalb liegt zusaetzlich ein UNIQUE-Index auf
(instrument, setup, richtung, timeframe, erstellt_utc, quelle).

``quelle`` gehoert in diesen Schluessel: eine manuell-assistierte Idee darf
zur selben Kerze existieren wie eine regelbasierte, ohne sie zu ueberschreiben.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ideas.model import Beobachtung, TradeIdee

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideen (
    idea_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    erstellt_utc        TEXT    NOT NULL,
    instrument          TEXT    NOT NULL,
    setup               TEXT    NOT NULL,
    richtung            TEXT    NOT NULL,
    timeframe           TEXT    NOT NULL,

    entry               REAL    NOT NULL,
    stop                REAL    NOT NULL,
    ziel                REAL    NOT NULL,
    crv                 REAL    NOT NULL,
    unter_crv_schwelle  INTEGER NOT NULL,

    -- Bemessungsgrundlagen, damit die Auswertung Stop und Ziel relativ zum
    -- tatsaechlichen Fill (Eroeffnung der Folgekerze) neu bilden kann.
    atr_referenz        REAL    NOT NULL,
    stop_atr            REAL    NOT NULL,
    ziel_atr            REAL    NOT NULL,

    quelle              TEXT    NOT NULL,
    profil              TEXT    NOT NULL,

    gefiltert           INTEGER NOT NULL,
    filter_gruende      TEXT    NOT NULL,
    ungeprueft          TEXT    NOT NULL,
    filter_context      TEXT    NOT NULL,

    notiz               TEXT,
    gespeichert_am_utc  TEXT    NOT NULL
);

-- Idempotenz ueberlappender Laeufe, siehe Modul-Docstring.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ideen_eindeutig
    ON ideen (instrument, setup, richtung, timeframe, erstellt_utc, quelle);

CREATE INDEX IF NOT EXISTS idx_ideen_zeit
    ON ideen (instrument, erstellt_utc DESC);

CREATE INDEX IF NOT EXISTS idx_ideen_kategorie
    ON ideen (setup, richtung, profil);

CREATE TABLE IF NOT EXISTS observations (
    observation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    erstellt_utc        TEXT    NOT NULL,
    instrument          TEXT    NOT NULL,
    beschreibung        TEXT    NOT NULL,
    chart_kontext       TEXT    NOT NULL,
    -- Verweis auf einen Setup-Schluessel, falls daraus ein festes Setup wurde.
    wurde_festes_setup  TEXT,
    gespeichert_am_utc  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_observations_zeit
    ON observations (instrument, erstellt_utc DESC);
"""


class IdeenStore:
    """Persistenz der protokollierten Ideen und Beobachtungen."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # check_same_thread=False analog zum Kerzenspeicher; die
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

    # -- Ideen schreiben ---------------------------------------------------

    def speichere(self, ideen: Iterable[TradeIdee]) -> int:
        """Legt Ideen ab. Rueckgabe: Anzahl **neu** hinzugekommener Zeilen.

        Bereits vorhandene Kombinationen werden aktualisiert statt
        dupliziert. Die Rueckgabe zaehlt bewusst nur die neuen - sonst saehe
        ein wiederholter Lauf ueber denselben Zeitraum wie ein Erfolg aus.
        """
        eintraege = list(ideen)
        if not eintraege:
            return 0

        jetzt = datetime.now(timezone.utc).isoformat()
        zeilen = [
            (
                idee.erstellt_utc.astimezone(timezone.utc).isoformat(),
                idee.instrument.upper(),
                idee.setup,
                idee.richtung,
                idee.timeframe,
                float(idee.entry),
                float(idee.stop),
                float(idee.ziel),
                float(idee.crv),
                int(idee.unter_crv_schwelle),
                float(idee.atr_referenz),
                float(idee.stop_atr),
                float(idee.ziel_atr),
                idee.quelle,
                idee.profil,
                int(idee.gefiltert),
                json.dumps(list(idee.filter_gruende), ensure_ascii=False),
                json.dumps(list(idee.ungeprueft), ensure_ascii=False),
                idee.filter_context_json(),
                idee.notiz,
                jetzt,
            )
            for idee in eintraege
        ]

        with self._lock:
            vorher = self._anzahl_ohne_lock("ideen")
            self._connection.executemany(
                """
                INSERT INTO ideen (
                    erstellt_utc, instrument, setup, richtung, timeframe,
                    entry, stop, ziel, crv, unter_crv_schwelle,
                    atr_referenz, stop_atr, ziel_atr,
                    quelle, profil,
                    gefiltert, filter_gruende, ungeprueft, filter_context,
                    notiz, gespeichert_am_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT (instrument, setup, richtung, timeframe, erstellt_utc, quelle)
                DO UPDATE SET
                    entry              = excluded.entry,
                    stop               = excluded.stop,
                    ziel               = excluded.ziel,
                    crv                = excluded.crv,
                    unter_crv_schwelle = excluded.unter_crv_schwelle,
                    atr_referenz       = excluded.atr_referenz,
                    stop_atr           = excluded.stop_atr,
                    ziel_atr           = excluded.ziel_atr,
                    profil             = excluded.profil,
                    gefiltert          = excluded.gefiltert,
                    filter_gruende     = excluded.filter_gruende,
                    ungeprueft         = excluded.ungeprueft,
                    filter_context     = excluded.filter_context,
                    notiz              = COALESCE(excluded.notiz, ideen.notiz)
                """,
                zeilen,
            )
            self._connection.commit()
            return self._anzahl_ohne_lock("ideen") - vorher

    # -- Ideen lesen -------------------------------------------------------

    def lade_fuer_auswertung(
        self,
        *,
        instrument: str | None = None,
        profil: str | None = None,
        quelle: str | None = None,
        nur_ungefiltert: bool = True,
    ) -> list[dict[str, Any]]:
        """Datenquelle fuer Etappe D. Liest AUSSCHLIESSLICH das Haupt-Log.

        Das Exploration-Log wird hier bewusst nicht angefasst und darf es
        auch nie: es ist per Definition nicht reproduzierbar und haette in
        einer Erwartungswert-Rechnung nichts verloren. Ein Test prueft, dass
        der Quelltext dieser Methode die andere Tabelle nicht nennt.

        ``profil`` ist ein **optionaler** Filter. Ohne Angabe kommen alle
        Ideen unabhaengig von ihrer Kontoumgebung - nur so laesst sich
        fragen, welche Setups auch unter Prop-Firm-Regeln tragen.

        ``nur_ungefiltert`` ist standardmaessig True: gefilterte Ideen sind
        gespeichert, gehoeren aber nicht ungefragt in eine Auswertung, denn
        sie waeren gar nicht gehandelt worden.
        """
        bedingungen: list[str] = []
        werte: list[Any] = []
        if instrument:
            bedingungen.append("instrument = ?")
            werte.append(instrument.upper())
        if profil:
            bedingungen.append("profil = ?")
            werte.append(profil.lower())
        if quelle:
            bedingungen.append("quelle = ?")
            werte.append(quelle)
        if nur_ungefiltert:
            bedingungen.append("gefiltert = 0")

        sql = "SELECT * FROM ideen"
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        sql += " ORDER BY erstellt_utc ASC"

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()
        return [self._idee_aus_zeile(zeile) for zeile in zeilen]

    def lade(
        self,
        *,
        instrument: str | None = None,
        setup: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Ideen zur Ansicht, juengste zuerst - inklusive gefilterter."""
        bedingungen: list[str] = []
        werte: list[Any] = []
        if instrument:
            bedingungen.append("instrument = ?")
            werte.append(instrument.upper())
        if setup:
            bedingungen.append("setup = ?")
            werte.append(setup)

        sql = "SELECT * FROM ideen"
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        sql += " ORDER BY erstellt_utc DESC"
        if limit is not None:
            sql += " LIMIT ?"
            werte.append(int(limit))

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()
        return [self._idee_aus_zeile(zeile) for zeile in zeilen]

    @staticmethod
    def _idee_aus_zeile(zeile: sqlite3.Row) -> dict[str, Any]:
        datensatz = dict(zeile)
        datensatz["filter_gruende"] = json.loads(datensatz["filter_gruende"])
        datensatz["ungeprueft"] = json.loads(datensatz["ungeprueft"])
        datensatz["filter_context"] = json.loads(datensatz["filter_context"])
        datensatz["unter_crv_schwelle"] = bool(datensatz["unter_crv_schwelle"])
        datensatz["gefiltert"] = bool(datensatz["gefiltert"])
        return datensatz

    def anzahl_je_kategorie(self, *, profil: str | None = None) -> dict[str, dict[str, int]]:
        """Ideen je Setup UND Richtung - die Kategorie der Auswertung.

        Grundlage fuer die Schwelle "unter N Ideen gilt als zu wenig Daten".
        Gezaehlt wird nach ``setup/richtung``, weil genau das die Kategorie
        ist, ueber die Etappe D eine Aussage treffen soll.
        """
        sql = (
            "SELECT setup, richtung, gefiltert, COUNT(*) AS n FROM ideen "
            + ("WHERE profil = ? " if profil else "")
            + "GROUP BY setup, richtung, gefiltert"
        )
        werte = [profil.lower()] if profil else []

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()

        ergebnis: dict[str, dict[str, int]] = {}
        for zeile in zeilen:
            schluessel = f"{zeile['setup']}/{zeile['richtung']}"
            eintrag = ergebnis.setdefault(
                schluessel, {"gesamt": 0, "handelbar": 0, "gefiltert": 0}
            )
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
                "SELECT MAX(erstellt_utc) AS neueste FROM ideen WHERE instrument = ?",
                (instrument.upper(),),
            ).fetchone()
        if zeile is None or zeile["neueste"] is None:
            return None
        return datetime.fromisoformat(zeile["neueste"])

    # -- Exploration-Log ---------------------------------------------------

    def speichere_beobachtung(self, beobachtung: Beobachtung) -> int:
        """Legt einen Eintrag im Exploration-Log ab, Rueckgabe: observation_id.

        Bewusst ohne Idempotenz-Schluessel: zwei gleichlautende Beobachtungen
        zu verschiedenen Zeitpunkten sind zwei Beobachtungen. Eine
        Zusammenfuehrung waere hier eine Behauptung, keine Messung.
        """
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO observations (
                    erstellt_utc, instrument, beschreibung, chart_kontext,
                    wurde_festes_setup, gespeichert_am_utc
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    beobachtung.erstellt_utc.astimezone(timezone.utc).isoformat(),
                    beobachtung.instrument.upper(),
                    beobachtung.beschreibung,
                    beobachtung.chart_kontext_json(),
                    beobachtung.wurde_festes_setup,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._connection.commit()
            return int(cursor.lastrowid)

    def lade_beobachtungen(
        self, *, instrument: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Beobachtungen zur Ansicht, juengste zuerst."""
        sql = "SELECT * FROM observations"
        werte: list[Any] = []
        if instrument:
            sql += " WHERE instrument = ?"
            werte.append(instrument.upper())
        sql += " ORDER BY erstellt_utc DESC"
        if limit is not None:
            sql += " LIMIT ?"
            werte.append(int(limit))

        with self._lock:
            zeilen = self._connection.execute(sql, werte).fetchall()

        ergebnis = []
        for zeile in zeilen:
            datensatz = dict(zeile)
            datensatz["chart_kontext"] = json.loads(datensatz["chart_kontext"])
            ergebnis.append(datensatz)
        return ergebnis

    # -- Gemeinsam ---------------------------------------------------------

    def _anzahl_ohne_lock(self, tabelle: str) -> int:
        cursor = self._connection.execute(f"SELECT COUNT(*) AS n FROM {tabelle}")
        return int(cursor.fetchone()["n"])

    def gesamt(self) -> int:
        with self._lock:
            return self._anzahl_ohne_lock("ideen")

    def gesamt_beobachtungen(self) -> int:
        with self._lock:
            return self._anzahl_ohne_lock("observations")


__all__ = ["SCHEMA", "IdeenStore"]
