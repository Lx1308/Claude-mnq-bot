"""Tradovate Market-Data-WebSocket (eine einzelne Verbindung).

Das Tradovate-Protokoll ist SockJS-aehnlich und textbasiert:

  Server -> Client
    ``o``          Verbindung geoeffnet
    ``h``          Heartbeat
    ``a[...]``     JSON-Array mit Antworten und Events
    ``c[...]``     Verbindung wird geschlossen

  Client -> Server
    ``<endpoint>\\n<id>\\n<query>\\n<body>``   Request
    ``[]``                                    Heartbeat (alle ~2.5s Pflicht)

Antworten haben die Form ``{"i": <request-id>, "s": <status>, "d": <payload>}``,
Events die Form ``{"e": "md"|"chart"|..., "d": {...}}``.

Diese Klasse kapselt genau EINE Verbindung. Die Wiederverbindungslogik
liegt bewusst eine Ebene hoeher in :mod:`live_bot.market.feed`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from common.logging_setup import log_event

log = logging.getLogger(__name__)

QuoteHandler = Callable[[dict[str, Any]], Awaitable[None] | None]

DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_HISTORY_TIMEOUT = 60.0


class MarketDataError(RuntimeError):
    """Fehler auf der Market-Data-Verbindung."""


class MarketDataSocket:
    """Eine offene Market-Data-Verbindung zu Tradovate."""

    def __init__(
        self,
        url: str,
        md_access_token: str,
        *,
        heartbeat_interval: float = 2.5,
        on_quote: QuoteHandler | None = None,
    ) -> None:
        self._url = url
        self._token = md_access_token
        self._heartbeat_interval = heartbeat_interval
        self._on_quote = on_quote

        self._ws: websockets.WebSocketClientProtocol | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Chart-Historie: bars je Chart-ID puffern, bis "end of history".
        self._chart_bars: dict[int, list[dict[str, Any]]] = {}
        self._chart_complete: dict[int, asyncio.Event] = {}

        self._closed = asyncio.Event()
        self._last_message_at: float = 0.0

    # -- Lifecycle ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._closed.is_set()

    @property
    def last_message_at(self) -> float:
        """Monotone Zeit der letzten empfangenen Nachricht (fuer Stale-Erkennung)."""
        return self._last_message_at

    async def connect(self) -> None:
        """Verbindet, wartet auf das Open-Frame und authorisiert."""
        self._closed.clear()
        self._ws = await websockets.connect(
            self._url,
            open_timeout=20,
            close_timeout=5,
            ping_interval=None,   # Tradovate nutzt eigenen Heartbeat
            max_size=8 * 1024 * 1024,
        )
        self._last_message_at = asyncio.get_running_loop().time()

        opening = await asyncio.wait_for(self._ws.recv(), timeout=20)
        if not str(opening).startswith("o"):
            raise MarketDataError(f"Unerwartetes erstes Frame: {opening!r}")

        self._reader_task = asyncio.create_task(self._read_loop(), name="md-reader")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="md-heartbeat")

        await self._authorize()
        log_event(log, "md.connected", "Market-Data-Verbindung aufgebaut", url=self._url)

    async def close(self) -> None:
        self._closed.set()
        for task in (self._heartbeat_task, self._reader_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        self._heartbeat_task = None
        self._reader_task = None

        for future in self._pending.values():
            if not future.done():
                future.set_exception(MarketDataError("Verbindung geschlossen."))
        self._pending.clear()

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 - beim Schliessen egal
                pass
            self._ws = None

    async def _authorize(self) -> None:
        response = await self._send_request("authorize", body=self._token, raw_body=True)
        log_event(log, "md.authorized", "Market-Data-Token akzeptiert", status=response.get("s"))

    # -- Requests ----------------------------------------------------------

    async def request(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
        *,
        query: str = "",
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> Any:
        """Sendet einen Request und liefert dessen ``d``-Payload."""
        response = await self._send_request(endpoint, body=body, query=query, timeout=timeout)
        return response.get("d")

    async def _send_request(
        self,
        endpoint: str,
        body: Any = None,
        *,
        query: str = "",
        raw_body: bool = False,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        if self._ws is None:
            raise MarketDataError("Nicht verbunden.")

        self._request_id += 1
        request_id = self._request_id

        if body is None:
            body_text = ""
        elif raw_body:
            body_text = str(body)
        else:
            body_text = json.dumps(body)

        frame = f"{endpoint}\n{request_id}\n{query}\n{body_text}"

        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._ws.send(frame)
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise MarketDataError(f"Timeout bei Request {endpoint!r}") from exc
        finally:
            self._pending.pop(request_id, None)

        status = response.get("s")
        if status is not None and int(status) >= 400:
            raise MarketDataError(
                f"Request {endpoint!r} abgelehnt (Status {status}): {response.get('d')}"
            )
        return response

    # -- Subscriptions -----------------------------------------------------

    async def subscribe_quotes(self, symbol: str) -> None:
        await self.request("md/subscribeQuote", {"symbol": symbol})
        log_event(log, "md.subscribed", f"Quotes abonniert: {symbol}", symbol=symbol)

    async def unsubscribe_quotes(self, symbol: str) -> None:
        await self.request("md/unsubscribeQuote", {"symbol": symbol})

    async def fetch_history(
        self,
        symbol: str,
        *,
        interval_minutes: int,
        bars: int,
        chart_type: str = "minute",
        timeout: float = DEFAULT_HISTORY_TIMEOUT,
    ) -> list[dict[str, Any]]:
        """Laedt historische Bars ueber ``md/getChart``.

        ``chart_type`` ist ``"minute"`` (Standard) oder ``"daily"``.
        Bei Tageskerzen ignoriert Tradovate ``interval_minutes``.

        Liefert Rohbars von Tradovate (Normalisierung in
        :mod:`live_bot.market.candles`).
        """
        if chart_type == "daily":
            underlying_type, element_size = "DailyBar", 1
        else:
            underlying_type, element_size = "MinuteBar", interval_minutes

        payload = await self.request(
            "md/getChart",
            {
                "symbol": symbol,
                "chartDescription": {
                    "underlyingType": underlying_type,
                    "elementSize": element_size,
                    "elementSizeUnit": "UnderlyingUnits",
                    "withHistogram": False,
                },
                "timeRange": {"asMuchAsElements": bars},
            },
        )

        chart_ids = self._extract_chart_ids(payload)
        if not chart_ids:
            raise MarketDataError(f"md/getChart lieferte keine Chart-ID: {payload!r}")

        for chart_id in chart_ids:
            self._chart_bars.setdefault(chart_id, [])
            self._chart_complete.setdefault(chart_id, asyncio.Event())

        waiters = [
            asyncio.create_task(self._chart_complete[cid].wait()) for cid in chart_ids
        ]
        try:
            await asyncio.wait_for(
                asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            log_event(
                log,
                "md.history.timeout",
                "Timeout beim Laden der Historie - verwende, was bereits angekommen ist",
                level=logging.WARNING,
                symbol=symbol,
                received=sum(len(self._chart_bars.get(cid, [])) for cid in chart_ids),
            )
        finally:
            # Haengende Warte-Tasks abraeumen, sonst laufen sie bis zum
            # Verbindungsende weiter.
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            await asyncio.gather(*waiters, return_exceptions=True)

            for chart_id in chart_ids:
                try:
                    await self.request(
                        "md/cancelChart", {"subscriptionId": chart_id}, timeout=10
                    )
                except Exception as exc:  # noqa: BLE001 - Aufraeumen darf nicht abbrechen
                    log.debug("md/cancelChart fuer %s fehlgeschlagen: %s", chart_id, exc)

        collected: list[dict[str, Any]] = []
        for chart_id in chart_ids:
            collected.extend(self._chart_bars.pop(chart_id, []))
            self._chart_complete.pop(chart_id, None)

        log_event(
            log,
            "md.history.loaded",
            f"{len(collected)} historische Bars fuer {symbol} geladen",
            symbol=symbol,
            bars=len(collected),
        )
        return collected

    @staticmethod
    def _extract_chart_ids(payload: Any) -> list[int]:
        if not isinstance(payload, dict):
            return []
        ids: list[int] = []
        for key in ("historicalId", "realtimeId", "subscriptionId", "id"):
            value = payload.get(key)
            if isinstance(value, int) and value not in ids:
                ids.append(value)
        return ids

    # -- Interne Schleifen -------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        try:
            while not self._closed.is_set() and self._ws is not None:
                await asyncio.sleep(self._heartbeat_interval)
                if self._ws is None or self._closed.is_set():
                    return
                await self._ws.send("[]")
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            self._closed.set()
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "md.heartbeat.error",
                f"Heartbeat fehlgeschlagen: {exc}",
                level=logging.WARNING,
                error=str(exc),
            )
            self._closed.set()

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                self._last_message_at = asyncio.get_running_loop().time()
                await self._handle_frame(str(raw))
        except asyncio.CancelledError:
            raise
        except ConnectionClosed as exc:
            log_event(
                log,
                "md.disconnected",
                f"Market-Data-Verbindung geschlossen: {exc}",
                level=logging.WARNING,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "md.read_error",
                f"Fehler in der Leseschleife: {exc}",
                level=logging.ERROR,
                error=str(exc),
                exc_info=True,
            )
        finally:
            self._closed.set()
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(MarketDataError("Verbindung verloren."))
            self._pending.clear()

    async def _handle_frame(self, raw: str) -> None:
        if not raw:
            return
        kind, payload = raw[0], raw[1:]

        if kind == "h":
            return
        if kind == "o":
            return
        if kind == "c":
            log_event(
                log,
                "md.close_frame",
                "Server hat die Verbindung beendet",
                level=logging.WARNING,
                payload=payload[:200],
            )
            self._closed.set()
            return
        if kind != "a":
            return

        try:
            messages = json.loads(payload)
        except json.JSONDecodeError:
            log.debug("Nicht parsebares Frame ignoriert: %r", raw[:200])
            return

        if not isinstance(messages, list):
            messages = [messages]

        for message in messages:
            if not isinstance(message, dict):
                continue
            await self._dispatch(message)

    async def _dispatch(self, message: dict[str, Any]) -> None:
        request_id = message.get("i")
        if request_id is not None:
            future = self._pending.get(int(request_id))
            if future is not None and not future.done():
                future.set_result(message)
            return

        event = message.get("e")
        data = message.get("d") or {}

        if event == "md":
            for quote in data.get("quotes", []) or []:
                await self._emit_quote(quote)
        elif event == "chart":
            self._collect_chart(data)
        elif event == "shutdown":
            log_event(
                log,
                "md.shutdown",
                "Server kuendigt Shutdown an - Verbindung wird neu aufgebaut",
                level=logging.WARNING,
            )
            self._closed.set()

    async def _emit_quote(self, quote: dict[str, Any]) -> None:
        if self._on_quote is None:
            return
        try:
            result = self._on_quote(quote)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:  # noqa: BLE001 - Handlerfehler darf den Feed nicht killen
            log_event(
                log,
                "md.quote_handler_error",
                f"Quote-Handler warf eine Exception: {exc}",
                level=logging.ERROR,
                error=str(exc),
                exc_info=True,
            )

    def _collect_chart(self, data: dict[str, Any]) -> None:
        for chart in data.get("charts", []) or []:
            chart_id = chart.get("id")
            if not isinstance(chart_id, int):
                continue
            buffer = self._chart_bars.setdefault(chart_id, [])
            buffer.extend(chart.get("bars", []) or [])
            if chart.get("eoh"):
                self._chart_complete.setdefault(chart_id, asyncio.Event()).set()
