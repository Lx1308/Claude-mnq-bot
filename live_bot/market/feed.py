"""Selbstheilender Market-Data-Feed.

Verantwortlich fuer alles, was eine EINZELNE Verbindung nicht leisten kann:

  * Wiederverbinden mit exponentiellem Backoff
  * Neu-Abonnieren nach jedem Verbindungsaufbau
  * Nachladen der Historie nach einem Ausfall (schliesst die Datenluecke)
  * Erkennen "stiller" Verbindungen: kommt laenger als
    ``stale_data_timeout_seconds`` nichts an, wird aktiv neu verbunden.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

from common.config import TradovateConfig
from common.logging_setup import log_event
from live_bot.market.candles import Candle, Tick, candles_from_tradovate_bars, tick_from_quote
from live_bot.tradovate.auth import TokenManager
from live_bot.tradovate.md_socket import MarketDataSocket

log = logging.getLogger(__name__)

TickCallback = Callable[[Tick], Awaitable[None] | None]
HistoryCallback = Callable[[list[Candle]], Awaitable[None] | None]
StateCallback = Callable[[bool], Awaitable[None] | None]


class MarketDataFeed:
    def __init__(
        self,
        config: TradovateConfig,
        tokens: TokenManager,
        *,
        symbol: str,
        interval_minutes: int,
        warmup_bars: int,
        on_tick: TickCallback,
        on_history: HistoryCallback | None = None,
        on_connection_state: StateCallback | None = None,
    ) -> None:
        self._config = config
        self._tokens = tokens
        self._symbol = symbol
        self._interval_minutes = interval_minutes
        self._warmup_bars = warmup_bars
        self._on_tick = on_tick
        self._on_history = on_history
        self._on_connection_state = on_connection_state

        self._socket: MarketDataSocket | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def run(self, stop_event: asyncio.Event) -> None:
        """Laeuft, bis ``stop_event`` gesetzt wird. Faengt alle Fehler ab."""
        ws_cfg = self._config.websocket
        delay = ws_cfg.reconnect_initial_delay_seconds
        attempt = 0

        while not stop_event.is_set():
            attempt += 1
            try:
                await self._connect_once(stop_event)
                # Sauber beendet (z.B. Stop-Signal) -> Backoff zuruecksetzen.
                delay = ws_cfg.reconnect_initial_delay_seconds
                attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - der Feed darf nie sterben
                log_event(
                    log,
                    "feed.error",
                    f"Market-Data-Feed abgebrochen: {exc}",
                    level=logging.ERROR,
                    error=str(exc),
                    attempt=attempt,
                    exc_info=True,
                )
            finally:
                await self._teardown()

            if stop_event.is_set():
                break

            # Jitter verhindert, dass mehrere Instanzen synchron reconnecten.
            sleep_for = min(delay, ws_cfg.reconnect_max_delay_seconds)
            sleep_for *= 0.8 + 0.4 * random.random()
            log_event(
                log,
                "feed.reconnect_scheduled",
                f"Neuverbindung in {sleep_for:.1f}s (Versuch {attempt})",
                level=logging.WARNING,
                delay_seconds=round(sleep_for, 1),
                attempt=attempt,
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=sleep_for)
                break  # stop_event wurde waehrend des Wartens gesetzt
            except asyncio.TimeoutError:
                pass

            delay = min(
                delay * ws_cfg.reconnect_backoff_factor,
                ws_cfg.reconnect_max_delay_seconds,
            )

    # -- Intern ------------------------------------------------------------

    async def _connect_once(self, stop_event: asyncio.Event) -> None:
        md_token = await self._tokens.get_md_access_token()

        socket = MarketDataSocket(
            self._config.market_data_url,
            md_token,
            heartbeat_interval=self._config.websocket.heartbeat_interval_seconds,
            on_quote=self._handle_quote,
        )
        self._socket = socket

        await socket.connect()
        await self._set_connected(True)

        # Historie NACH dem Connect laden: fuellt beim Start die Indikatoren
        # und nach einem Ausfall die entstandene Luecke.
        if self._warmup_bars > 0 and self._on_history is not None:
            await self._load_history(socket)

        await socket.subscribe_quotes(self._symbol)

        await self._watch(socket, stop_event)

    async def _load_history(self, socket: MarketDataSocket) -> None:
        try:
            raw_bars = await socket.fetch_history(
                self._symbol,
                interval_minutes=self._interval_minutes,
                bars=self._warmup_bars,
            )
        except Exception as exc:  # noqa: BLE001 - ohne Historie laeuft der Bot weiter
            log_event(
                log,
                "feed.history_failed",
                f"Historie konnte nicht geladen werden ({exc}) - Indikatoren brauchen laenger",
                level=logging.WARNING,
                error=str(exc),
            )
            return

        candles = candles_from_tradovate_bars(raw_bars, self._interval_minutes)
        # Die letzte Kerze ist typischerweise noch nicht abgeschlossen.
        if candles:
            candles = candles[:-1]
        await self._invoke(self._on_history, candles)

    async def _watch(self, socket: MarketDataSocket, stop_event: asyncio.Event) -> None:
        """Ueberwacht die offene Verbindung auf Abbruch oder Datenstille."""
        stale_after = self._config.websocket.stale_data_timeout_seconds
        loop = asyncio.get_running_loop()

        while not stop_event.is_set():
            await asyncio.sleep(1.0)

            if not socket.connected:
                raise ConnectionError("Market-Data-Verbindung wurde geschlossen.")

            silent_for = loop.time() - socket.last_message_at
            if stale_after > 0 and silent_for > stale_after:
                raise ConnectionError(
                    f"Seit {silent_for:.0f}s keine Daten empfangen "
                    f"(Grenzwert {stale_after:.0f}s) - erzwinge Neuverbindung."
                )

    async def _teardown(self) -> None:
        await self._set_connected(False)
        if self._socket is not None:
            try:
                await self._socket.close()
            except Exception:  # noqa: BLE001
                pass
            self._socket = None

    async def _handle_quote(self, quote: dict[str, Any]) -> None:
        tick = tick_from_quote(quote)
        if tick is None:
            return
        await self._invoke(self._on_tick, tick)

    async def _set_connected(self, connected: bool) -> None:
        if connected == self._connected:
            return
        self._connected = connected
        await self._invoke(self._on_connection_state, connected)

    @staticmethod
    async def _invoke(callback: Any, *args: Any) -> None:
        if callback is None:
            return
        result = callback(*args)
        if asyncio.iscoroutine(result):
            await result
