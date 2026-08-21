"""Empfaengt Telegram-Befehle per Long-Polling.

Gegenstueck zum :class:`~live_bot.notify.notifier.Notifier`: der sendet,
dieser hoert zu. Bewusst ohne Webhook - ein Webhook braeuchte eine oeffentlich
erreichbare HTTPS-Adresse, Long-Polling laeuft hinter jedem Router.

Sicherheit
----------
Es werden ausschliesslich Nachrichten aus der konfigurierten
``TELEGRAM_CHAT_ID`` verarbeitet. Jeder, der den Bot-Namen kennt, kann ihm
schreiben - Nachrichten aus anderen Chats werden verworfen und protokolliert.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from common.logging_setup import log_event

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


@dataclass(frozen=True)
class Command:
    """Ein eingegangener Slash-Befehl."""

    name: str                       # ohne Schraegstrich, kleingeschrieben
    args: list[str] = field(default_factory=list)
    chat_id: str = ""
    raw_text: str = ""

    @property
    def first_arg(self) -> str | None:
        return self.args[0] if self.args else None


CommandHandler = Callable[[Command], Awaitable[None]]


def parse_command(text: str, chat_id: str) -> Command | None:
    """Zerlegt einen Nachrichtentext in einen Befehl.

    Beruecksichtigt die Telegram-Konvention ``/befehl@BotName`` (so werden
    Befehle in Gruppen adressiert).
    """
    stripped = (text or "").strip()
    if not stripped.startswith("/"):
        return None

    parts = stripped.split()
    name = parts[0][1:]
    if "@" in name:
        name = name.split("@", 1)[0]
    if not name:
        return None

    return Command(
        name=name.lower(),
        args=parts[1:],
        chat_id=chat_id,
        raw_text=stripped,
    )


class TelegramCommandListener:
    def __init__(
        self,
        bot_token: str,
        allowed_chat_id: str,
        *,
        on_command: CommandHandler,
        long_poll_timeout: float = 25.0,
        retry_delay: float = 5.0,
    ) -> None:
        self._token = bot_token
        self._allowed_chat_id = str(allowed_chat_id)
        self._on_command = on_command
        self._long_poll_timeout = long_poll_timeout
        self._retry_delay = retry_delay
        self._offset: int | None = None

    @property
    def _base_url(self) -> str:
        return f"{TELEGRAM_API}/bot{self._token}"

    async def run(self, stop_event: asyncio.Event) -> None:
        """Laeuft, bis ``stop_event`` gesetzt wird. Faengt alle Fehler ab."""
        # Lesetimeout muss ueber dem Long-Poll-Timeout liegen, sonst bricht
        # der Client genau die Verbindung ab, auf die er warten soll.
        timeout = httpx.Timeout(self._long_poll_timeout + 15.0, connect=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            await self._skip_backlog(client)

            log_event(
                log,
                "telegram.listener.started",
                "Telegram-Befehlsempfaenger aktiv (/analyse)",
                chat_id=self._allowed_chat_id,
            )

            while not stop_event.is_set():
                try:
                    updates = await self._fetch_updates(client)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - Empfaenger darf nie sterben
                    log_event(
                        log,
                        "telegram.listener.error",
                        f"getUpdates fehlgeschlagen ({exc}) - neuer Versuch in "
                        f"{self._retry_delay:.0f}s",
                        level=logging.WARNING,
                        error=str(exc),
                    )
                    await self._sleep_or_stop(stop_event, self._retry_delay)
                    continue

                for update in updates:
                    if stop_event.is_set():
                        break
                    await self._handle_update(update)

    async def _skip_backlog(self, client: httpx.AsyncClient) -> None:
        """Verwirft Nachrichten, die waehrend der Downtime aufgelaufen sind.

        Ohne diesen Schritt wuerde ein Neustart alle in der Zwischenzeit
        gesendeten ``/analyse``-Befehle auf einmal abarbeiten - inklusive
        der zugehoerigen Claude-Aufrufe.
        """
        try:
            response = await client.get(
                f"{self._base_url}/getUpdates",
                params={"timeout": 0, "offset": -1},
            )
            response.raise_for_status()
            results = response.json().get("result", []) or []
            if results:
                self._offset = int(results[-1]["update_id"]) + 1
                log_event(
                    log,
                    "telegram.listener.backlog_skipped",
                    f"{len(results)} aufgelaufene Nachricht(en) uebersprungen",
                    skipped=len(results),
                )
        except Exception as exc:  # noqa: BLE001 - nicht kritisch fuer den Start
            log_event(
                log,
                "telegram.listener.backlog_failed",
                f"Backlog konnte nicht uebersprungen werden: {exc}",
                level=logging.WARNING,
                error=str(exc),
            )

    async def _fetch_updates(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "timeout": int(self._long_poll_timeout),
            "allowed_updates": '["message"]',
        }
        if self._offset is not None:
            params["offset"] = self._offset

        response = await client.get(f"{self._base_url}/getUpdates", params=params)
        response.raise_for_status()
        body = response.json()
        if not body.get("ok", False):
            raise RuntimeError(f"Telegram-API meldet Fehler: {body}")
        return body.get("result", []) or []

    async def _handle_update(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            # Immer quittieren - auch verworfene Nachrichten, sonst kommen
            # sie bei jedem Poll erneut.
            self._offset = update_id + 1

        message = update.get("message") or {}
        chat_id = str((message.get("chat") or {}).get("id", ""))
        text = message.get("text") or ""

        if chat_id != self._allowed_chat_id:
            log_event(
                log,
                "telegram.listener.rejected",
                "Nachricht aus fremdem Chat verworfen",
                level=logging.WARNING,
                chat_id=chat_id,
                text_preview=text[:80],
            )
            return

        command = parse_command(text, chat_id)
        if command is None:
            return

        log_event(
            log,
            "telegram.command.received",
            f"Befehl empfangen: /{command.name}",
            command=command.name,
            args=command.args,
        )

        try:
            # Bewusst inline abgearbeitet: ein Bericht dauert einige Sekunden,
            # und waehrenddessen soll kein zweiter parallel laufen. Telegram
            # puffert die Nachrichten so lange serverseitig.
            await self._on_command(command)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Handlerfehler beendet den Empfaenger nicht
            log_event(
                log,
                "telegram.command.failed",
                f"Befehl /{command.name} fehlgeschlagen: {exc}",
                level=logging.ERROR,
                command=command.name,
                error=str(exc),
                exc_info=True,
            )

    @staticmethod
    async def _sleep_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass
