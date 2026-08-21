"""SQLite-Speicher fuer Kerzen aus der NinjaScript-Bridge.

Entwurfsentscheidungen
----------------------
* **Schluessel ist (instrument, timeframe, timestamp).** Dieselbe Kerze darf
  beliebig oft ankommen - beim Neustart von NinjaTrader wird die Historie
  erneut geschickt. Ein ``INSERT ... ON CONFLICT DO UPDATE`` ueberschreibt
  idempotent, statt Duplikate anzuhaeufen.

* **WAL-Modus.** Empfaenger und MCP-Server sind getrennte Prozesse: der eine
  schreibt, der andere liest. Ohne WAL wuerden sich beide gegenseitig
  blockieren.

* **Unplausible Kerzen werden abgelehnt, nicht gespeichert.** Und zwar mit
  Zaehler je Grund, damit man am ``/status``-Endpunkt sieht, ob etwas
  systematisch schieflaeuft - statt es erst Wochen spaeter in den Zahlen zu
  bemerken.

* **Kein Bid-/Ask-Volumen.** NinjaTrader liefert es ohne das kostenpflichtige
  Add-on "Order Flow +" nicht. Es gibt hier deshalb keine Spalten dafuer und
  im Snapshot bleibt das Delta ``null`` mit Begruendung - eine Schaetzung aus
  Auf- und Abwaertskerzen saehe aus wie eine Messung und waere keine.
"""

from __future__ import annotations

import logging
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from common.logging_setup import log_event

log = logging.getLogger(__name__)

# Kerzen, deren Schlusszeit weiter als das in der Zukunft liegt, sind
# unplausibel. Toleranz fuer Uhrabweichungen zwischen NT8 und diesem Rechner.
FUTURE_TOLERANCE = timedelta(minutes=5)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    instrument    TEXT NOT NULL,
    timeframe     TEXT NOT NULL,
    ts_utc        TEXT NOT NULL,
    open          REAL NOT NULL,
    high          REAL NOT NULL,
    low           REAL NOT NULL,
    close         REAL NOT NULL,
    volume        REAL NOT NULL,
    nt_instrument TEXT,
    source        TEXT,
    received_utc  TEXT NOT NULL,
    PRIMARY KEY (instrument, timeframe, ts_utc)
);

CREATE INDEX IF NOT EXISTS idx_bars_lookup
    ON bars (instrument, timeframe, ts_utc DESC);
"""


class BarRejected(ValueError):
    """Eine Kerze hat die Plausibilitaetspruefung nicht bestanden."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class BarRecord:
    """Eine validierte Kerze."""

    instrument: str
    timeframe: str
    timestamp: datetime          # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    nt_instrument: str | None = None
    source: str = "ninjatrader"


@dataclass
class IngestResult:
    """Ergebnis eines Schreibvorgangs."""

    accepted: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    instruments: set[str] = field(default_factory=set)

    def add_rejection(self, reason: str) -> None:
        self.rejected += 1
        self.reasons[reason] = self.reasons.get(reason, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "angenommen": self.accepted,
            "abgelehnt": self.rejected,
            "gruende": dict(self.reasons),
            "instrumente": sorted(self.instruments),
        }


# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------

def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(number) or math.isinf(number)) else number


def _parse_timestamp(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def validate_bar(
    payload: dict[str, Any],
    *,
    known_timeframes: set[str],
    symbol_map: dict[str, str] | None = None,
    now: datetime | None = None,
) -> BarRecord:
    """Prueft eine eingegangene Kerze. Wirft :class:`BarRejected` bei Verstoss.

    Die Pruefungen sind bewusst hart: eine unplausible Kerze stillschweigend
    zu speichern, verfaelscht spaeter jede Kennzahl, die darauf aufbaut - und
    faellt niemandem auf.
    """
    now = now or datetime.now(timezone.utc)
    symbol_map = symbol_map or {}

    raw_instrument = str(payload.get("instrument", "")).strip().upper()
    if not raw_instrument:
        raise BarRejected("instrument_fehlt")
    instrument = symbol_map.get(raw_instrument, raw_instrument)

    timeframe = str(payload.get("timeframe", "")).strip().lower()
    if timeframe not in known_timeframes:
        raise BarRejected(
            "timeframe_unbekannt",
            f"{timeframe!r} (bekannt: {', '.join(sorted(known_timeframes))})",
        )

    timestamp = _parse_timestamp(payload.get("timestampUtc"))
    if timestamp is None:
        raise BarRejected("zeitstempel_unlesbar", str(payload.get("timestampUtc")))

    if timestamp > now + FUTURE_TOLERANCE:
        # Haeufigste Ursache: in NinjaTrader ist eine andere Zeitzone
        # eingestellt als in Windows. Die Kerze abzulehnen ist richtig -
        # gespeichert wuerde sie jede Sessionzuordnung verschieben.
        raise BarRejected(
            "zeitstempel_in_zukunft",
            f"{timestamp.isoformat()} liegt {(timestamp - now).total_seconds() / 3600:.1f} h "
            f"vor der aktuellen Zeit. Pruefe die Zeitzone in NinjaTrader "
            f"(Parameter 'Zeitzone (optional)' der ClaudeBridge).",
        )

    values: dict[str, float] = {}
    for key in ("open", "high", "low", "close"):
        number = _finite(payload.get(key))
        if number is None:
            raise BarRejected("preis_ungueltig", f"{key}={payload.get(key)!r}")
        values[key] = number

    volume = _finite(payload.get("volume"))
    if volume is None or volume < 0:
        raise BarRejected("volumen_ungueltig", f"volume={payload.get('volume')!r}")

    if values["high"] < values["low"]:
        raise BarRejected(
            "high_kleiner_low", f"high={values['high']} low={values['low']}"
        )

    highest_body = max(values["open"], values["close"])
    lowest_body = min(values["open"], values["close"])
    if values["high"] < highest_body or values["low"] > lowest_body:
        raise BarRejected(
            "ohlc_widerspruechlich",
            f"O={values['open']} H={values['high']} L={values['low']} C={values['close']}",
        )

    return BarRecord(
        instrument=instrument,
        timeframe=timeframe,
        timestamp=timestamp,
        open=values["open"],
        high=values["high"],
        low=values["low"],
        close=values["close"],
        volume=volume,
        nt_instrument=(str(payload.get("ntInstrument")).strip() or None)
        if payload.get("ntInstrument") else None,
        source=str(payload.get("source", "ninjatrader")),
    )


# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------

class BarStore:
    """Kerzenspeicher. Neustartfest, idempotent, von mehreren Prozessen lesbar."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # check_same_thread=False, weil der HTTP-Server mehrere Threads nutzt.
        # Die Serialisierung uebernimmt self._lock.
        self._connection = sqlite3.connect(str(self._path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

        with self._lock:
            # WAL: erlaubt einen Schreiber und mehrere Leser gleichzeitig.
            # Ohne das wuerden Empfaenger und MCP-Server einander blockieren.
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

    # -- Schreiben ---------------------------------------------------------

    def upsert(self, records: Iterable[BarRecord]) -> int:
        """Schreibt Kerzen. Bereits vorhandene werden ueberschrieben."""
        rows = [
            (
                record.instrument,
                record.timeframe,
                record.timestamp.isoformat(),
                record.open,
                record.high,
                record.low,
                record.close,
                record.volume,
                record.nt_instrument,
                record.source,
                datetime.now(timezone.utc).isoformat(),
            )
            for record in records
        ]
        if not rows:
            return 0

        with self._lock:
            self._connection.executemany(
                """
                INSERT INTO bars (instrument, timeframe, ts_utc, open, high, low,
                                  close, volume, nt_instrument, source, received_utc)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument, timeframe, ts_utc) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    nt_instrument = excluded.nt_instrument,
                    source = excluded.source,
                    received_utc = excluded.received_utc
                """,
                rows,
            )
            self._connection.commit()
        return len(rows)

    def ingest(
        self,
        payloads: Iterable[dict[str, Any]],
        *,
        known_timeframes: set[str],
        symbol_map: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> IngestResult:
        """Validiert und schreibt in einem Schritt."""
        result = IngestResult()
        accepted: list[BarRecord] = []

        for payload in payloads:
            try:
                record = validate_bar(
                    payload,
                    known_timeframes=known_timeframes,
                    symbol_map=symbol_map,
                    now=now,
                )
            except BarRejected as exc:
                result.add_rejection(exc.reason)
                log_event(
                    log,
                    "ntbridge.bar_rejected",
                    f"Kerze abgelehnt ({exc.reason}): {exc.detail}",
                    level=logging.WARNING,
                    reason=exc.reason,
                    detail=exc.detail,
                )
                continue

            accepted.append(record)
            result.instruments.add(f"{record.instrument}/{record.timeframe}")

        result.accepted = self.upsert(accepted)
        return result

    # -- Lesen -------------------------------------------------------------

    def load_frame(
        self, instrument: str, timeframe: str, limit: int | None = None
    ) -> pd.DataFrame:
        """OHLCV-DataFrame im Projektschema (UTC-Index, aufsteigend)."""
        query = (
            "SELECT ts_utc, open, high, low, close, volume FROM bars "
            "WHERE instrument = ? AND timeframe = ? ORDER BY ts_utc DESC"
        )
        params: list[Any] = [instrument.upper(), timeframe.lower()]
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        with self._lock:
            rows = self._connection.execute(query, params).fetchall()

        columns = ["open", "high", "low", "close", "volume"]
        if not rows:
            return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC"))

        rows = list(reversed(rows))   # wieder aufsteigend
        index = pd.DatetimeIndex(
            [datetime.fromisoformat(row["ts_utc"]) for row in rows], tz="UTC"
        )
        return pd.DataFrame(
            [[row[column] for column in columns] for row in rows],
            columns=columns,
            index=index,
        )

    def latest_timestamp(self, instrument: str, timeframe: str) -> datetime | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT MAX(ts_utc) AS newest FROM bars "
                "WHERE instrument = ? AND timeframe = ?",
                (instrument.upper(), timeframe.lower()),
            ).fetchone()
        if row is None or row["newest"] is None:
            return None
        return datetime.fromisoformat(row["newest"])

    def nt_instrument(self, instrument: str, timeframe: str) -> str | None:
        """Zuletzt gemeldeter NinjaTrader-Kontraktname, z.B. 'MNQ 12-25'."""
        with self._lock:
            row = self._connection.execute(
                "SELECT nt_instrument FROM bars "
                "WHERE instrument = ? AND timeframe = ? AND nt_instrument IS NOT NULL "
                "ORDER BY ts_utc DESC LIMIT 1",
                (instrument.upper(), timeframe.lower()),
            ).fetchone()
        return row["nt_instrument"] if row else None

    def coverage(self) -> list[dict[str, Any]]:
        """Uebersicht je (Instrument, Timeframe) - Grundlage fuer /status."""
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT instrument, timeframe, COUNT(*) AS bars,
                       MIN(ts_utc) AS oldest, MAX(ts_utc) AS newest
                FROM bars GROUP BY instrument, timeframe
                ORDER BY instrument, timeframe
                """
            ).fetchall()

        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for row in rows:
            newest = datetime.fromisoformat(row["newest"])
            result.append(
                {
                    "instrument": row["instrument"],
                    "timeframe": row["timeframe"],
                    "bars": row["bars"],
                    "aeltester_bar_utc": row["oldest"],
                    "juengster_bar_utc": row["newest"],
                    "alter_sekunden": round((now - newest).total_seconds(), 1),
                }
            )
        return result

    def total_bars(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS n FROM bars").fetchone()
        return int(row["n"])


__all__ = [
    "FUTURE_TOLERANCE",
    "BarRecord",
    "BarRejected",
    "BarStore",
    "IngestResult",
    "validate_bar",
]
