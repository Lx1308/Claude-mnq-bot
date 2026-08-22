"""SQLite-Ablage der Dukascopy-Naeherungsdaten - strikt getrennt vom Echtbestand.

WARUM EINE EIGENE DATEI
-----------------------
``data/ntbridge.sqlite3`` enthaelt **gemessene** MNQ-Futures-Kerzen aus
NinjaTrader. Was hier abgelegt wird, ist ein CFD auf den Nasdaq-100-Index -
eine Naeherung mit anderer Preisbildung und ohne echtes Handelsvolumen
(Begruendung ausfuehrlich in ``dukascopy.py``).

Beides in dieselbe Datei zu schreiben hiesse, dass spaeter niemand mehr
auseinanderhalten kann, worauf eine Auswertung beruht. Deshalb eine eigene
Datei, und darin eine Tabelle ``herkunft``, die die Einschraenkung
mitschreibt statt sie der Erinnerung zu ueberlassen.

Dieselbe Haltung wie ``naeherung: true`` beim Volume Profile und wie das
Delta, das null bleibt statt geschaetzt zu werden.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backtest.data.dukascopy import DukascopyInstrument

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    ts_utc  TEXT    NOT NULL PRIMARY KEY,
    open    REAL    NOT NULL,
    high    REAL    NOT NULL,
    low     REAL    NOT NULL,
    close   REAL    NOT NULL,
    volume  REAL    NOT NULL
);

-- Welche Stunden bereits geholt wurden. Ohne das muesste ein abgebrochener
-- Mehrjahres-Download von vorn beginnen; ausserdem ist "Stunde geholt, aber
-- leer" (Wochenende) nicht dasselbe wie "Stunde noch nicht geholt".
CREATE TABLE IF NOT EXISTS geholte_stunden (
    stunde_utc TEXT    NOT NULL PRIMARY KEY,
    kerzen     INTEGER NOT NULL
);

-- Die Einschraenkung wandert mit der Datei. Wer sie in zwei Jahren findet,
-- soll nicht raten muessen, was darin steht.
CREATE TABLE IF NOT EXISTS herkunft (
    schluessel TEXT NOT NULL PRIMARY KEY,
    wert       TEXT NOT NULL
);
"""

# Wird beim Anlegen in die Tabelle "herkunft" geschrieben.
WARNUNG = (
    "NAEHERUNG, KEINE MESSUNG. Diese Daten sind ein CFD auf den "
    "Nasdaq-100-Index, gestellt von der Dukascopy Bank - KEIN MNQ-Futures. "
    "Andere Preisbildung (ein Market Maker statt CME-Orderbuch), kein echtes "
    "Handelsvolumen (die Volumenspalte traegt Anbieter-Liquiditaet), keine "
    "Kontraktablaeufe, andere Sessionstruktur. Backtest-Ergebnisse auf diesen "
    "Daten sind REIN INFORMATIV und keine Grundlage fuer "
    "Strategieentscheidungen."
)


class DukascopyStore:
    """Kerzen und Fortschritt eines Dukascopy-Downloads."""

    def __init__(self, path: str | Path, instrument: DukascopyInstrument) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._instrument = instrument

        self._conn = sqlite3.connect(str(self._path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._schreibe_herkunft()
        self._conn.commit()

    def _schreibe_herkunft(self) -> None:
        eintraege = {
            "warnung": WARNUNG,
            "symbol": self._instrument.symbol,
            "beschreibung": self._instrument.beschreibung,
            "preis_faktor": str(self._instrument.preis_faktor),
            "ist_naeherung": "true",
            "quelle": "https://www.dukascopy.com/datafeed/",
            "kurs_definition": "Mitte aus Bid und Ask",
            "volumen_definition": (
                "Summe aus Bid- und Ask-Liquiditaet des Market Makers in "
                "Millionen Einheiten - KEIN gehandeltes Volumen"
            ),
            "angelegt_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._conn.executemany(
            "INSERT INTO herkunft (schluessel, wert) VALUES (?,?) "
            "ON CONFLICT(schluessel) DO UPDATE SET wert = excluded.wert",
            [(k, v) for k, v in eintraege.items() if k != "angelegt_utc"],
        )
        # Anlagezeitpunkt nur beim ersten Mal.
        self._conn.execute(
            "INSERT OR IGNORE INTO herkunft (schluessel, wert) VALUES (?,?)",
            ("angelegt_utc", eintraege["angelegt_utc"]),
        )

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DukascopyStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- Schreiben ---------------------------------------------------------

    def speichere_stunde(self, stunde_utc: datetime, kerzen: pd.DataFrame) -> int:
        """Legt die Kerzen einer Stunde ab und vermerkt sie als geholt.

        Auch eine **leere** Stunde wird vermerkt: sonst liefe ein
        Wiederaufnahme-Lauf jedes Wochenende erneut ins Leere.
        """
        marke = stunde_utc.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        zeilen = [
            (
                zeit.tz_convert("UTC").isoformat(),
                float(reihe["open"]), float(reihe["high"]),
                float(reihe["low"]), float(reihe["close"]), float(reihe["volume"]),
            )
            for zeit, reihe in kerzen.iterrows()
        ]
        if zeilen:
            self._conn.executemany(
                "INSERT INTO bars (ts_utc, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?) ON CONFLICT(ts_utc) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume",
                zeilen,
            )
        self._conn.execute(
            "INSERT INTO geholte_stunden (stunde_utc, kerzen) VALUES (?,?) "
            "ON CONFLICT(stunde_utc) DO UPDATE SET kerzen = excluded.kerzen",
            (marke.isoformat(), len(zeilen)),
        )
        self._conn.commit()
        return len(zeilen)

    # -- Lesen -------------------------------------------------------------

    def ist_geholt(self, stunde_utc: datetime) -> bool:
        marke = stunde_utc.astimezone(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        treffer = self._conn.execute(
            "SELECT 1 FROM geholte_stunden WHERE stunde_utc = ?", (marke.isoformat(),)
        ).fetchone()
        return treffer is not None

    def anzahl_kerzen(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM bars").fetchone()["n"])

    def anzahl_stunden(self) -> int:
        return int(
            self._conn.execute(
                "SELECT COUNT(*) AS n FROM geholte_stunden"
            ).fetchone()["n"]
        )

    def herkunft(self) -> dict[str, str]:
        return {
            zeile["schluessel"]: zeile["wert"]
            for zeile in self._conn.execute("SELECT * FROM herkunft")
        }

    def lade_frame(
        self, *, start: datetime | None = None, ende: datetime | None = None
    ) -> pd.DataFrame:
        """OHLCV im Projektschema - direkt backtestfaehig."""
        sql = "SELECT ts_utc, open, high, low, close, volume FROM bars"
        bedingungen, werte = [], []
        if start is not None:
            bedingungen.append("ts_utc >= ?")
            werte.append(start.astimezone(timezone.utc).isoformat())
        if ende is not None:
            bedingungen.append("ts_utc <= ?")
            werte.append(ende.astimezone(timezone.utc).isoformat())
        if bedingungen:
            sql += " WHERE " + " AND ".join(bedingungen)
        sql += " ORDER BY ts_utc ASC"

        frame = pd.read_sql_query(sql, self._conn, params=werte)
        if frame.empty:
            return pd.DataFrame(
                {n: pd.Series(dtype="float64")
                 for n in ("open", "high", "low", "close", "volume")},
                index=pd.DatetimeIndex([], tz="UTC"),
            )
        frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True, format="ISO8601")
        return frame.set_index("ts_utc").sort_index()


__all__ = ["SCHEMA", "WARNUNG", "DukascopyStore"]
