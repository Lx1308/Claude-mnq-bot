"""Schnittstelle fuer historische Datenquellen.

Die Engine kennt ausschliesslich :class:`DataProvider`. Ob die Bars aus
einer CSV, aus der Dukascopy-Naeherungshistorie oder spaeter aus einem
kommerziellen Feed kommen, ist damit eine Konfigurationsentscheidung - keine
Code-Aenderung. Registriert ist am 23.08.2026 nur ``csv``; ein Provider fuer
die Dukascopy-Historie fehlt noch (MASTERPLAN Abschnitt X.1, P0).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from common.indicators import OHLCV_COLUMNS, validate_ohlcv


class DataProviderError(RuntimeError):
    """Daten konnten nicht geladen werden."""


@dataclass(frozen=True)
class BarRequest:
    """Beschreibt den gewuenschten Datenausschnitt."""

    symbol: str
    interval_minutes: int = 1
    start: datetime | None = None
    end: datetime | None = None
    max_bars: int | None = None

    def describe(self) -> str:
        span = ""
        if self.start or self.end:
            span = f" {self.start or '...'} bis {self.end or '...'}"
        return f"{self.symbol} {self.interval_minutes}min{span}"


class DataProvider(ABC):
    """Basisklasse aller Datenquellen."""

    #: Anzeigename fuer Logs und Reports
    name: str = "provider"

    @abstractmethod
    def load(self, request: BarRequest) -> pd.DataFrame:
        """Liefert OHLCV-Daten im gemeinsamen Schema.

        Rueckgabe: DataFrame mit tz-behaftetem UTC-DatetimeIndex (aufsteigend)
        und den Spalten ``open``, ``high``, ``low``, ``close``, ``volume``.
        """

    # -- Hilfen fuer Unterklassen -----------------------------------------

    @staticmethod
    def finalize(df: pd.DataFrame, request: BarRequest) -> pd.DataFrame:
        """Normalisiert, filtert und validiert das Ergebnis einer Unterklasse."""
        if df.empty:
            raise DataProviderError(f"Keine Daten fuer {request.describe()}.")

        frame = df.copy()
        frame = frame[[column for column in OHLCV_COLUMNS if column in frame.columns]]
        frame = frame.astype(float)
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()

        if request.start is not None:
            frame = frame[frame.index >= pd.Timestamp(request.start)]
        if request.end is not None:
            frame = frame[frame.index <= pd.Timestamp(request.end)]
        if request.max_bars is not None and len(frame) > request.max_bars:
            frame = frame.iloc[-request.max_bars :]

        if frame.empty:
            raise DataProviderError(
                f"Nach Zeitfilterung keine Daten mehr uebrig fuer {request.describe()}."
            )

        validate_ohlcv(frame)
        return frame
