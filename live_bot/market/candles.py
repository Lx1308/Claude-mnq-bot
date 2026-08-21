"""Aggregation von Tick-/Quote-Daten zu Kerzen und rollierender Puffer."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import pandas as pd

from common.sessions import floor_to_interval

log = logging.getLogger(__name__)


@dataclass
class Candle:
    """Eine OHLCV-Kerze. ``start`` ist der Beginn des Intervalls (UTC).

    ``bid_volume``/``ask_volume`` sind optional und stammen aus den
    Tradovate-Chart-Bars (``bidVolume``/``offerVolume``). Sie erlauben die
    Berechnung des Volumen-Deltas. Ob dein Datenabo sie liefert, zeigt
    :attr:`has_flow` - geschaetzt wird nichts.
    """

    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    bid_volume: float = 0.0
    ask_volume: float = 0.0

    def update(self, price: float, size: float = 0.0) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size

    @property
    def has_flow(self) -> bool:
        """True, wenn Bid-/Ask-Volumen tatsaechlich geliefert wurde."""
        return (self.bid_volume + self.ask_volume) > 0.0

    @property
    def delta(self) -> float | None:
        """Volumen-Delta (am Brief gehandelt minus am Geld gehandelt)."""
        return (self.ask_volume - self.bid_volume) if self.has_flow else None

    def as_row(self, *, include_flow: bool = False) -> dict[str, Any]:
        """Zeile fuer den DataFrame-Export.

        ``include_flow`` ist bewusst standardmaessig aus: Backtest-Engine
        und Live-Alarme arbeiten auf dem reinen OHLCV-Schema, und zusaetzliche
        Spalten dort einzuschleusen waere eine stille Schema-Aenderung.
        """
        row = {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
        if include_flow:
            row["bid_volume"] = self.bid_volume
            row["ask_volume"] = self.ask_volume
        return row


class CandleAggregator:
    """Baut aus einzelnen Trades/Ticks Kerzen fester Laenge.

    Wichtig: Eine Kerze wird erst geschlossen, wenn ein Tick im NAECHSTEN
    Intervall eintrifft - oder wenn :meth:`close_expired` sie aktiv schliesst.
    Letzteres verhindert, dass in ruhigen Phasen (kein Handel) Alarme
    minutenlang haengen bleiben.
    """

    def __init__(self, interval_minutes: int) -> None:
        if interval_minutes <= 0:
            raise ValueError("interval_minutes muss > 0 sein.")
        self._interval = timedelta(minutes=interval_minutes)
        self._interval_minutes = interval_minutes
        self._current: Candle | None = None

    @property
    def current(self) -> Candle | None:
        return self._current

    def add_tick(self, timestamp: datetime, price: float, size: float = 0.0) -> Candle | None:
        """Verarbeitet einen Tick. Gibt die abgeschlossene Kerze zurueck, falls eine endet."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        bucket = floor_to_interval(timestamp.astimezone(timezone.utc), self._interval_minutes)

        if self._current is None:
            self._current = Candle(bucket, price, price, price, price, size)
            return None

        if bucket == self._current.start:
            self._current.update(price, size)
            return None

        if bucket < self._current.start:
            # Verspaeteter Tick aus einem bereits geschlossenen Intervall.
            log.debug("Verspaeteten Tick verworfen: %s < %s", bucket, self._current.start)
            return None

        finished = self._current
        self._current = Candle(bucket, price, price, price, price, size)
        return finished

    def close_expired(self, now: datetime) -> Candle | None:
        """Schliesst die laufende Kerze, wenn ihr Intervall vorbei ist."""
        if self._current is None:
            return None
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if now.astimezone(timezone.utc) < self._current.start + self._interval:
            return None
        finished = self._current
        self._current = None
        return finished

    def reset(self) -> None:
        self._current = None


class CandleBuffer:
    """Rollierender Puffer geschlossener Kerzen mit DataFrame-Export."""

    def __init__(self, max_size: int) -> None:
        if max_size <= 0:
            raise ValueError("max_size muss > 0 sein.")
        self._candles: deque[Candle] = deque(maxlen=max_size)

    def __len__(self) -> int:
        return len(self._candles)

    @property
    def last(self) -> Candle | None:
        return self._candles[-1] if self._candles else None

    def append(self, candle: Candle) -> None:
        """Fuegt eine Kerze an. Doppelte Zeitstempel ueberschreiben den Eintrag."""
        if self._candles and candle.start == self._candles[-1].start:
            self._candles[-1] = candle
            return
        if self._candles and candle.start < self._candles[-1].start:
            log.debug("Kerze ausser der Reihe verworfen: %s", candle.start)
            return
        self._candles.append(candle)

    def extend(self, candles: Iterable[Candle]) -> None:
        for candle in sorted(candles, key=lambda item: item.start):
            self.append(candle)

    @property
    def has_flow(self) -> bool:
        """True, wenn mindestens eine Kerze Bid-/Ask-Volumen traegt."""
        return any(candle.has_flow for candle in self._candles)

    def to_dataframe(self, *, include_flow: bool = False) -> pd.DataFrame:
        """OHLCV-DataFrame im gemeinsamen Schema (UTC-Index, sortiert)."""
        columns = ["open", "high", "low", "close", "volume"]
        if include_flow:
            columns += ["bid_volume", "ask_volume"]

        if not self._candles:
            return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC"))

        index = pd.DatetimeIndex([candle.start for candle in self._candles], tz="UTC")
        return pd.DataFrame(
            [candle.as_row(include_flow=include_flow) for candle in self._candles],
            index=index,
        )


# ---------------------------------------------------------------------------
# Normalisierung von Tradovate-Rohdaten
# ---------------------------------------------------------------------------

def parse_tradovate_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def candle_from_tradovate_bar(bar: dict[str, Any], interval_minutes: int) -> Candle | None:
    """Wandelt einen Tradovate-Chart-Bar in eine :class:`Candle`."""
    timestamp = parse_tradovate_timestamp(bar.get("timestamp"))
    if timestamp is None:
        return None
    try:
        open_ = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
    except (KeyError, TypeError, ValueError):
        return None

    volume = float(bar.get("upVolume", 0) or 0) + float(bar.get("downVolume", 0) or 0)
    if volume == 0.0:
        # Manche Feeds liefern nur Tickzahlen statt Volumen.
        volume = float(bar.get("upTicks", 0) or 0) + float(bar.get("downTicks", 0) or 0)

    # Bid-/Ask-Volumen ist abo-abhaengig. Fehlt es, bleiben die Felder null
    # und has_flow meldet False - der Snapshot liefert dann kein geschaetztes
    # Delta, sondern gar keines.
    bid_volume = float(bar.get("bidVolume", 0) or 0)
    ask_volume = float(bar.get("offerVolume", 0) or 0)

    return Candle(
        start=floor_to_interval(timestamp, interval_minutes),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        bid_volume=bid_volume,
        ask_volume=ask_volume,
    )


def candles_from_tradovate_bars(
    bars: Iterable[dict[str, Any]], interval_minutes: int
) -> list[Candle]:
    """Normalisiert eine Liste Tradovate-Bars, verwirft unbrauchbare Eintraege."""
    result: list[Candle] = []
    for bar in bars:
        candle = candle_from_tradovate_bar(bar, interval_minutes)
        if candle is not None:
            result.append(candle)
    result.sort(key=lambda candle: candle.start)
    return result


@dataclass(frozen=True)
class Tick:
    """Ein aus einem Quote abgeleiteter Preispunkt."""

    timestamp: datetime
    price: float
    size: float


def tick_from_quote(quote: dict[str, Any]) -> Tick | None:
    """Extrahiert einen handelbaren Preis aus einem Tradovate-Quote.

    Bevorzugt echte Trades. Gibt es keinen Trade-Eintrag (haeufig ausserhalb
    aktiver Phasen), wird der Mittelkurs aus Bid/Ask mit Volumen 0 benutzt -
    so bleiben Kerzen luekenlos, ohne das Volumen zu verfaelschen.
    """
    timestamp = parse_tradovate_timestamp(quote.get("timestamp"))
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    entries = quote.get("entries") or {}

    trade = entries.get("Trade") or {}
    price = trade.get("price")
    if price is not None:
        return Tick(timestamp, float(price), float(trade.get("size", 0) or 0))

    bid = (entries.get("Bid") or {}).get("price")
    offer = (entries.get("Offer") or {}).get("price")
    if bid is not None and offer is not None:
        return Tick(timestamp, (float(bid) + float(offer)) / 2.0, 0.0)
    if bid is not None:
        return Tick(timestamp, float(bid), 0.0)
    if offer is not None:
        return Tick(timestamp, float(offer), 0.0)

    return None
