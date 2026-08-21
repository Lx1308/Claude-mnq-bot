"""Marktzustand: Kerzenpuffer + berechnete Indikatoren als Momentaufnahme.

Die Indikatoren werden bei jeder abgeschlossenen Kerze neu berechnet -
mit exakt derselben Funktion, die auch der Backtest benutzt
(:func:`common.indicators.compute_indicators`).
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from common.config import IndicatorConfig, MarketConfig
from common.indicators import compute_indicators
from live_bot.market.candles import Candle, CandleBuffer

log = logging.getLogger(__name__)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


@dataclass(frozen=True)
class MarketSnapshot:
    """Alle Kennzahlen zum Abschluss einer Kerze.

    Genau dieses Objekt (und nur dieses) wird spaeter an Claude geschickt -
    also ausschliesslich berechnete Kennzahlen, keine Rohdaten.
    """

    symbol: str
    timestamp: datetime
    interval_minutes: int
    bars_available: int

    open: float
    high: float
    low: float
    close: float
    volume: float

    rsi: float | None
    sma_fast: float | None
    sma_slow: float | None
    vwap: float | None
    atr: float | None

    session_date: date | None
    prev_session_high: float | None
    prev_session_low: float | None
    prev_session_close: float | None

    flag_direction: int
    flag_in_consolidation: bool
    flag_breakout_up: bool
    flag_breakout_down: bool
    flag_range_high: float | None
    flag_range_low: float | None

    @property
    def indicators_ready(self) -> bool:
        """True, sobald die langsamsten Indikatoren belastbare Werte liefern."""
        return None not in (self.rsi, self.sma_slow, self.atr)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["session_date"] = self.session_date.isoformat() if self.session_date else None
        return data


def build_snapshot(
    symbol: str,
    market_cfg: MarketConfig,
    row: pd.Series,
    timestamp: pd.Timestamp,
    bars_available: int,
) -> MarketSnapshot:
    """Baut einen Snapshot aus einer angereicherten Indikator-Zeile.

    Modulweite Funktion (statt Methode), damit auch Pfade ohne laufenden
    :class:`MarketState` sie nutzen koennen - etwa der On-Demand-Bericht fuer
    ein Symbol, das der Bot gerade gar nicht streamt.
    """
    session_value = row.get("session_date")
    session_day: date | None
    if isinstance(session_value, date):
        session_day = session_value
    elif session_value is None or (isinstance(session_value, float) and math.isnan(session_value)):
        session_day = None
    else:
        try:
            session_day = pd.Timestamp(session_value).date()
        except (TypeError, ValueError):
            session_day = None

    return MarketSnapshot(
        symbol=symbol,
        timestamp=timestamp.to_pydatetime(),
        interval_minutes=market_cfg.candle_interval_minutes,
        bars_available=bars_available,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
        rsi=_float_or_none(row.get("rsi")),
        sma_fast=_float_or_none(row.get("sma_fast")),
        sma_slow=_float_or_none(row.get("sma_slow")),
        vwap=_float_or_none(row.get("vwap")),
        atr=_float_or_none(row.get("atr")),
        session_date=session_day,
        prev_session_high=_float_or_none(row.get("prev_session_high")),
        prev_session_low=_float_or_none(row.get("prev_session_low")),
        prev_session_close=_float_or_none(row.get("prev_session_close")),
        flag_direction=int(row.get("flag_direction", 0) or 0),
        flag_in_consolidation=bool(row.get("flag_in_consolidation", False)),
        flag_breakout_up=bool(row.get("flag_breakout_up", False)),
        flag_breakout_down=bool(row.get("flag_breakout_down", False)),
        flag_range_high=_float_or_none(row.get("flag_range_high")),
        flag_range_low=_float_or_none(row.get("flag_range_low")),
    )


class MarketState:
    """Haelt den rollierenden Kerzenpuffer und leitet Snapshots daraus ab."""

    def __init__(
        self,
        symbol: str,
        market_cfg: MarketConfig,
        indicator_cfg: IndicatorConfig,
    ) -> None:
        self._symbol = symbol
        self._market_cfg = market_cfg
        self._indicator_cfg = indicator_cfg
        self._buffer = CandleBuffer(market_cfg.candle_buffer_size)
        self._previous: MarketSnapshot | None = None
        self._current: MarketSnapshot | None = None

    # -- Zustand -----------------------------------------------------------

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def bar_count(self) -> int:
        return len(self._buffer)

    @property
    def current(self) -> MarketSnapshot | None:
        return self._current

    @property
    def previous(self) -> MarketSnapshot | None:
        return self._previous

    @property
    def warm(self) -> bool:
        """True, wenn genug Kerzen fuer alle Indikatoren vorliegen."""
        return len(self._buffer) >= self._indicator_cfg.min_bars_required

    def dataframe(self) -> pd.DataFrame:
        return self._buffer.to_dataframe()

    # -- Aktualisierung ----------------------------------------------------

    def seed(self, candles: list[Candle]) -> None:
        """Fuellt den Puffer mit historischen Kerzen (Start oder nach Reconnect)."""
        if not candles:
            return
        self._buffer.extend(candles)
        log.info(
            "Kerzenpuffer auf %d Kerzen aufgefuellt (Symbol %s).",
            len(self._buffer),
            self._symbol,
        )
        self._recompute()

    def on_candle_closed(self, candle: Candle) -> MarketSnapshot | None:
        """Nimmt eine abgeschlossene Kerze auf und liefert den neuen Snapshot."""
        self._buffer.append(candle)
        return self._recompute()

    def _recompute(self) -> MarketSnapshot | None:
        frame = self._buffer.to_dataframe()
        if frame.empty:
            return None

        try:
            enriched = compute_indicators(
                frame, self._indicator_cfg, self._market_cfg.session
            )
        except Exception as exc:  # noqa: BLE001 - Rechenfehler darf den Bot nicht stoppen
            log.error("Indikatorberechnung fehlgeschlagen: %s", exc, exc_info=True)
            return None

        snapshot = build_snapshot(
            self._symbol,
            self._market_cfg,
            enriched.iloc[-1],
            enriched.index[-1],
            len(frame),
        )
        # Nur echte Fortschritte als "vorherigen" Snapshot merken; ein reines
        # Neuberechnen (z.B. nach Historien-Nachladen) darf keine Kreuzung
        # vortaeuschen.
        if self._current is not None and self._current.timestamp != snapshot.timestamp:
            self._previous = self._current
        self._current = snapshot
        return snapshot
