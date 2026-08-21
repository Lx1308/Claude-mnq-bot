"""CSV-Datenquelle.

Erwartet eine Datei ``<verzeichnis>/<SYMBOL>_<INTERVALL>m.csv``, z.B.
``data/NQZ5_1m.csv``. Alternativ kann ein expliziter Pfad uebergeben werden.

Akzeptierte Spaltennamen (Gross-/Kleinschreibung egal):

    Zeit    : timestamp | time | datetime | date
    Preise  : open, high, low, close   (auch o/h/l/c)
    Volumen : volume | vol   (optional, fehlt es, wird 0 angenommen)

Zeitstempel ohne Zeitzone werden als UTC interpretiert - das ist die
Konvention des gesamten Projekts.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backtest.data.base import BarRequest, DataProvider, DataProviderError

log = logging.getLogger(__name__)

TIME_COLUMNS = ("timestamp", "time", "datetime", "date", "ts")
COLUMN_ALIASES = {
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
    "vol": "volume",
    "last": "close",
}


class CsvDataProvider(DataProvider):
    name = "csv"

    def __init__(self, directory: str | Path = "data", path: str | Path | None = None) -> None:
        self._directory = Path(directory)
        self._explicit_path = Path(path) if path else None

    def resolve_path(self, request: BarRequest) -> Path:
        if self._explicit_path is not None:
            return self._explicit_path
        return self._directory / f"{request.symbol.upper()}_{request.interval_minutes}m.csv"

    def load(self, request: BarRequest) -> pd.DataFrame:
        path = self.resolve_path(request)
        if not path.exists():
            raise DataProviderError(
                f"CSV-Datei nicht gefunden: {path.resolve()}\n"
                f"Tipp: mit 'python -m backtest.cli fetch --symbol {request.symbol}' "
                f"Historie von Tradovate herunterladen."
            )

        raw = pd.read_csv(path)
        raw.columns = [str(column).strip().lower() for column in raw.columns]
        raw = raw.rename(columns=COLUMN_ALIASES)

        time_column = next((column for column in TIME_COLUMNS if column in raw.columns), None)
        if time_column is None:
            raise DataProviderError(
                f"{path.name}: keine Zeitspalte gefunden "
                f"(erwartet eine von {', '.join(TIME_COLUMNS)})."
            )

        timestamps = pd.to_datetime(raw[time_column], utc=True, errors="coerce")
        if timestamps.isna().any():
            bad = int(timestamps.isna().sum())
            log.warning("%s: %d Zeilen mit unlesbarem Zeitstempel verworfen.", path.name, bad)
            raw = raw[timestamps.notna()]
            timestamps = timestamps[timestamps.notna()]

        frame = raw.set_index(pd.DatetimeIndex(timestamps))
        if "volume" not in frame.columns:
            frame["volume"] = 0.0

        missing = [column for column in ("open", "high", "low", "close") if column not in frame.columns]
        if missing:
            raise DataProviderError(f"{path.name}: fehlende Spalten {', '.join(missing)}.")

        log.info("%d Zeilen aus %s geladen.", len(frame), path.name)
        return self.finalize(frame, request)

    @staticmethod
    def write(df: pd.DataFrame, path: str | Path) -> Path:
        """Schreibt ein OHLCV-DataFrame im erwarteten Format."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        output = df.copy()
        output.index.name = "timestamp"
        output.to_csv(target)
        return target
