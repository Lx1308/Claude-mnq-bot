"""Duenner, authentifizierter Wrapper um die Tradovate-REST-API.

Kuemmert sich um:
  * Authorization-Header aus dem :class:`TokenManager`
  * einmaliges Neu-Authentifizieren bei HTTP 401
  * Retries mit exponentiellem Backoff bei Netz-/5xx-Fehlern
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from common.config import TradovateConfig
from common.logging_setup import log_event
from live_bot.tradovate.auth import TokenManager

log = logging.getLogger(__name__)


class TradovateApiError(RuntimeError):
    """Die API hat einen fachlichen Fehler zurueckgegeben."""


class TradovateRestClient:
    def __init__(self, config: TradovateConfig, tokens: TokenManager) -> None:
        self._config = config
        self._tokens = tokens

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            token = await self._tokens.get_access_token()
            try:
                response = await self._tokens.http.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except Exception as exc:  # noqa: BLE001 - Netzfehler: wiederholen
                last_error = exc
                await self._backoff(attempt, path, exc)
                continue

            if response.status_code == 401:
                # Token serverseitig ungueltig - einmal neu holen und erneut versuchen.
                log_event(
                    log,
                    "tradovate.rest.unauthorized",
                    f"401 bei {path} - erneuere Token",
                    level=logging.WARNING,
                    path=path,
                )
                self._tokens.invalidate()
                last_error = TradovateApiError(f"401 Unauthorized bei {path}")
                continue

            if 400 <= response.status_code < 500:
                raise TradovateApiError(
                    f"{method} {path} -> {response.status_code}: {response.text[:300]}"
                )

            if response.status_code >= 500:
                last_error = TradovateApiError(
                    f"{method} {path} -> {response.status_code}"
                )
                await self._backoff(attempt, path, last_error)
                continue

            if not response.content:
                return None
            return response.json()

        raise TradovateApiError(f"{method} {path} endgueltig fehlgeschlagen: {last_error}")

    async def _backoff(self, attempt: int, path: str, error: Exception) -> None:
        delay = min(2.0 ** attempt, 30.0)
        log_event(
            log,
            "tradovate.rest.retry",
            f"REST-Aufruf {path} fehlgeschlagen ({error}), Wiederholung in {delay:.0f}s",
            level=logging.WARNING,
            path=path,
            attempt=attempt,
            error=str(error),
        )
        await asyncio.sleep(delay)
