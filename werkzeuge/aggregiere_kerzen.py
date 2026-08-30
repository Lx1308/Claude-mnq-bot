"""Groebere Timeframes aus 1m vorberechnen und in die Kerzendatenbank schreiben.

Warum dieses Werkzeug existiert
------------------------------
Seit dem NT8-Import (30.08.2026) liegen rund 2,5 Mio MNQ-Minutenkerzen ab 2019
in ``data/ntbridge.sqlite3`` - aber **nur als 1m**. Die groeberen Timeframes
hatten dort nur die paar tausend Kerzen, die die Bridge nebenbei mitgeschickt
hat (Wochen, nicht Jahre).

Der Chart soll 2019 bis heute zeigen. 2,5 Mio Minutenkerzen bei jeder
Chart-Anfrage neu zu aggregieren dauert gemessen rund zwanzig Sekunden - einmal
gerechnet und als eigene ``timeframe``-Zeilen gespeichert ist es ein
Millisekunden-Query mit ``LIMIT``.

Wie
---
``common/timeframes.resample_ohlcv`` - **dieselbe** Regel wie im Backtest
(``closed="left"``, ``label="right"``, 18:00-ET-Handelstag). Keine zweite
Rechenlogik (Invariante 1 gilt auch hier).

Die abgeleiteten Zeilen tragen ``source="resampled_1m"``. Sie sind kein
zweiter Messwert, sondern eine Ableitung aus 1m - und werden so gekennzeichnet,
damit sie nie mit echten Kerzen verwechselt werden (Invariante 11). Beim Lauf
werden bestehende Nicht-1m-Zeilen des Symbols ersetzt, damit jede Reihe
durchgaengig aus derselben Quelle stammt.

Aufruf
------
    .venv\\Scripts\\python.exe -m werkzeuge.aggregiere_kerzen            # inkrementell
    .venv\\Scripts\\python.exe -m werkzeuge.aggregiere_kerzen --voll     # von vorn
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.config import Config  # noqa: E402
from common.timeframes import resample_ohlcv  # noqa: E402
from ntbridge.store import BarStore  # noqa: E402

#: Welche Timeframes vorberechnet und gespeichert werden.
#:
#: Die groben - fuer sie zeigt der Chart die volle Historie 2019 bis heute,
#: und das laesst sich nicht bei jeder Anfrage neu rechnen (2,5 Mio 1m-Kerzen
#: zu aggregieren dauert ~20 s). 1h/4h/1d zusammen sind rund 60.000 Zeilen -
#: guenstig zu speichern. Die feinen Ebenen (5m/15m) zeigt die Oberflaeche nur
#: als begrenztes Fenster; das aggregiert der Server bei Bedarf direkt aus 1m.
#: 1m selbst ist die Quelle und wird nie ueberschrieben.
ZIEL_TIMEFRAMES: tuple[str, ...] = ("1h", "4h", "1d")

#: Wie weit vor dem letzten gespeicherten Bucket neu gerechnet wird. Der
#: juengste Bucket war beim letzten Lauf womoeglich noch unvollstaendig; er
#: muss mit den seither hereingekommenen 1m-Kerzen neu gebildet werden. Ein
#: Handelstag Rueckgriff deckt auch die 1d-Kerze sicher ab.
NEUBERECHNUNG_AB_TAGEN = 2


def _lies_1m(db_pfad: Path, symbol: str, *, ab_iso: str | None) -> pd.DataFrame:
    """1m-Kerzen als OHLCV-Frame (UTC-Index, aufsteigend).

    Eigene Verbindung **ohne** ``row_factory``: ueber 2,5 Mio
    ``sqlite3.Row``-Objekte zu bauen dauert zwei Minuten, ueber Tupel rund
    zwanzig Sekunden.
    """
    query = (
        "SELECT ts_utc, open, high, low, close, volume FROM bars "
        "WHERE instrument = ? AND timeframe = '1m'"
    )
    params: list = [symbol.upper()]
    if ab_iso is not None:
        query += " AND ts_utc >= ?"
        params.append(ab_iso)
    query += " ORDER BY ts_utc"

    conn = sqlite3.connect(str(db_pfad))
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], tz="UTC"),
        )
    df = pd.DataFrame(rows, columns=["ts_utc", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts_utc"), utc=True, format="ISO8601")
    return df


def _letzter_bucket(conn: sqlite3.Connection, symbol: str, timeframe: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(ts_utc) FROM bars WHERE instrument = ? AND timeframe = ? "
        "AND source = 'resampled_1m'",
        (symbol.upper(), timeframe),
    ).fetchone()
    wert = row[0] if row else None
    # row_factory kann sqlite3.Row sein - dann ist row[0] der Wert, sonst auch.
    return wert if wert else None


def aggregiere(
    db_pfad: Path,
    *,
    symbol: str = "MNQ",
    voll: bool = False,
    timeframes: tuple[str, ...] = ZIEL_TIMEFRAMES,
    config: Config | None = None,
) -> dict[str, int]:
    """Leitet die groeberen Timeframes aus 1m ab und schreibt sie.

    Rueckgabe: ``{timeframe: geschriebene_kerzen}``.
    """
    cfg = config or Config.load(PROJECT_ROOT / "config.yaml")
    session_cfg = cfg.market.session
    ergebnis: dict[str, int] = {}

    speicher = BarStore(db_pfad)
    try:
        conn = speicher._connection
        # Der ntbridge-Empfaenger schreibt 1m in dieselbe Datei. WAL laesst
        # das nebeneinander laufen; nur der kurze Moment, in dem beide
        # schreiben wollen, braucht Geduld statt eines sofortigen "locked".
        conn.execute("PRAGMA busy_timeout=10000")

        for tf in timeframes:
            ab_iso: str | None = None
            if not voll:
                letzter = _letzter_bucket(conn, symbol, tf)
                if letzter is not None:
                    ab_iso = (
                        pd.Timestamp(letzter, tz="UTC")
                        - pd.Timedelta(days=NEUBERECHNUNG_AB_TAGEN)
                    ).isoformat()

            roh = _lies_1m(db_pfad, symbol, ab_iso=ab_iso)
            if roh.empty:
                ergebnis[tf] = 0
                continue

            grob = resample_ohlcv(roh, tf, session_cfg)
            if grob.empty:
                ergebnis[tf] = 0
                continue

            with speicher._lock:
                if voll:
                    conn.execute(
                        "DELETE FROM bars WHERE instrument = ? AND timeframe = ?",
                        (symbol.upper(), tf),
                    )
                else:
                    conn.execute(
                        "DELETE FROM bars WHERE instrument = ? AND timeframe = ? "
                        "AND ts_utc >= ?",
                        (symbol.upper(), tf, grob.index[0].isoformat()),
                    )
                conn.commit()

            saetze = [
                {
                    "timestampUtc": ts.isoformat(),
                    "instrument": symbol.upper(),
                    "timeframe": tf,
                    "open": float(zeile["open"]),
                    "high": float(zeile["high"]),
                    "low": float(zeile["low"]),
                    "close": float(zeile["close"]),
                    "volume": float(zeile["volume"]),
                    "source": "resampled_1m",
                }
                for ts, zeile in grob.iterrows()
            ]
            res = speicher.ingest(saetze, known_timeframes={tf}, symbol_map={})
            ergebnis[tf] = res.accepted
    finally:
        speicher.close()

    return ergebnis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aggregiere_kerzen",
        description="Leitet 5m/15m/1h/4h/1d aus den 1m-Kerzen ab.",
    )
    parser.add_argument("--symbol", default="MNQ")
    parser.add_argument(
        "--voll",
        action="store_true",
        help="Alle Nicht-1m-Zeilen des Symbols verwerfen und komplett neu "
        "aggregieren. Ohne den Schalter werden nur die juengsten Buckets "
        "nachgezogen.",
    )
    parser.add_argument("--database", default=None)
    args = parser.parse_args(argv)

    config = Config.load(PROJECT_ROOT / "config.yaml")
    datenbank = Path(args.database or config.ntbridge.database)
    if not datenbank.is_absolute():
        datenbank = PROJECT_ROOT / datenbank

    modus = "vollstaendig" if args.voll else "inkrementell"
    print(f"Aggregiere {args.symbol} ({modus}) in {datenbank} ...")
    ergebnis = aggregiere(
        datenbank, symbol=args.symbol, voll=args.voll, config=config
    )
    for tf, anzahl in ergebnis.items():
        print(f"  {tf}: {anzahl} Kerzen geschrieben")
    print("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
