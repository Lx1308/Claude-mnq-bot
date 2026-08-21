"""Tradovate als historische Datenquelle.

Nutzt denselben Market-Data-WebSocket wie der Live-Bot (``md/getChart``).
Die Klasse ist bewusst synchron nach aussen - die Engine soll nichts von
asyncio wissen muessen -, intern laeuft ein kurzlebiger Event-Loop.

Grenzen (bitte vor der Nutzung lesen)
-------------------------------------
* Tradovate liefert pro Anfrage eine begrenzte Anzahl Bars. Fuer laengere
  Zeitraeume wird in Bloecken rueckwaerts geladen und zusammengesetzt.
* Wie weit die Historie zurueckreicht, haengt am Datenabo. Fuer mehrere
  Jahre Minutendaten ist ein spezialisierter Anbieter die bessere Wahl -
  genau dafuer ist die Provider-Schnittstelle austauschbar.
* Fuer wiederholte Backtests einmal per ``backtest.cli fetch`` in eine CSV
  ziehen und danach den CSV-Provider nutzen. Das ist schneller und schont
  das API-Kontingent.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import pandas as pd

from backtest.data.base import BarRequest, DataProvider, DataProviderError
from common.config import Config, Secrets
from live_bot.market.candles import candles_from_tradovate_bars
from live_bot.tradovate.auth import TokenManager
from live_bot.tradovate.md_socket import MarketDataSocket

log = logging.getLogger(__name__)

# Tradovate deckelt die Bars pro getChart-Aufruf; konservativ gewaehlt.
MAX_BARS_PER_REQUEST = 5000


class TradovateDataProvider(DataProvider):
    name = "tradovate"

    def __init__(self, config: Config, secrets: Secrets | None = None) -> None:
        self._config = config
        self._secrets = secrets or Secrets.load()

    def load(self, request: BarRequest) -> pd.DataFrame:
        try:
            frame = asyncio.run(self._load_async(request))
        except RuntimeError as exc:
            if "asyncio.run() cannot be called" in str(exc):
                raise DataProviderError(
                    "TradovateDataProvider.load() kann nicht aus einem laufenden Event-Loop "
                    "heraus aufgerufen werden. Bitte '_load_async' direkt awaiten."
                ) from exc
            raise
        return self.finalize(frame, request)

    async def _load_async(self, request: BarRequest) -> pd.DataFrame:
        self._secrets.require_tradovate()

        wanted = request.max_bars or self._estimate_bars(request)
        collected: list[dict] = []

        async with TokenManager(self._config.tradovate, self._secrets) as tokens:
            md_token = await tokens.get_md_access_token()
            socket = MarketDataSocket(
                self._config.tradovate.market_data_url,
                md_token,
                heartbeat_interval=self._config.tradovate.websocket.heartbeat_interval_seconds,
            )
            await socket.connect()
            try:
                remaining = wanted
                while remaining > 0:
                    chunk_size = min(remaining, MAX_BARS_PER_REQUEST)
                    bars = await socket.fetch_history(
                        request.symbol,
                        interval_minutes=request.interval_minutes,
                        bars=chunk_size,
                    )
                    if not bars:
                        break
                    collected.extend(bars)
                    # Tradovate liefert ab dem aktuellen Rand rueckwaerts; ohne
                    # Cursor-Unterstuetzung bringt ein weiterer Block nichts.
                    if len(bars) < chunk_size:
                        break
                    remaining -= len(bars)
                    break
            finally:
                await socket.close()

        if not collected:
            raise DataProviderError(f"Tradovate lieferte keine Bars fuer {request.describe()}.")

        candles = candles_from_tradovate_bars(collected, request.interval_minutes)
        if not candles:
            raise DataProviderError("Tradovate-Bars liessen sich nicht normalisieren.")

        index = pd.DatetimeIndex([candle.start for candle in candles], tz="UTC")
        frame = pd.DataFrame(
            [
                {
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in candles
            ],
            index=index,
        )
        log.info("%d Bars von Tradovate geladen (%s).", len(frame), request.describe())
        return frame

    @staticmethod
    def _estimate_bars(request: BarRequest) -> int:
        """Schaetzt die noetige Bar-Anzahl aus dem Zeitfenster."""
        if request.start is None:
            return MAX_BARS_PER_REQUEST
        end = request.end or datetime.now(timezone.utc)
        minutes = max((end - request.start).total_seconds() / 60.0, 0.0)
        # ~23 Handelsstunden pro Tag bei Index-Futures -> ca. 96% der Kalenderzeit.
        estimated = int(minutes / request.interval_minutes * 0.96) + 100
        return max(estimated, 100)
