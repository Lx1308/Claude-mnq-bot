"""Tradovate-Authentifizierung inklusive Token-Refresh.

Tradovate-Tokens laufen typischerweise nach ~80 Minuten ab. Der
:class:`TokenManager` erneuert sie proaktiv (Standard: 5 Minuten vor Ablauf)
ueber ``/auth/renewaccesstoken`` und faellt auf einen kompletten
Neu-Login zurueck, falls das Erneuern scheitert.

Zusaetzlich wird Tradovates "Penalty"-Mechanismus behandelt: Bei zu vielen
Login-Versuchen antwortet die API mit ``p-ticket``/``p-time`` statt einem
Token. Dann muss ``p-time`` Sekunden gewartet und der Request mit dem Ticket
wiederholt werden.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from common.config import Secrets, TradovateConfig
from common.logging_setup import log_event

log = logging.getLogger(__name__)


class TradovateAuthError(RuntimeError):
    """Authentifizierung ist endgueltig fehlgeschlagen."""


@dataclass(frozen=True)
class AccessTokens:
    """Ein Paar aus Trading- und Market-Data-Token."""

    access_token: str
    md_access_token: str
    expires_at: datetime
    user_id: int | None = None

    def expired(self, margin_seconds: float = 0.0) -> bool:
        return datetime.now(timezone.utc) >= (self.expires_at - timedelta(seconds=margin_seconds))


def _parse_expiration(raw: str | None) -> datetime:
    """Tradovate liefert ISO-8601 mit 'Z'. Fallback: 60 Minuten ab jetzt."""
    if not raw:
        return datetime.now(timezone.utc) + timedelta(minutes=60)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc) + timedelta(minutes=60)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TokenManager:
    """Haelt gueltige Tradovate-Tokens vor und erneuert sie bei Bedarf."""

    # Tradovate erzwingt Wartezeiten bei zu haeufigen Logins; darueber hinaus
    # wird nicht mehr gewartet, sondern hart abgebrochen.
    MAX_PENALTY_WAIT_SECONDS = 120.0
    MAX_PENALTY_RETRIES = 3

    def __init__(
        self,
        config: TradovateConfig,
        secrets: Secrets,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        secrets.require_tradovate()
        self._config = config
        self._secrets = secrets
        self._client = client
        self._owns_client = client is None
        self._tokens: AccessTokens | None = None
        self._lock = asyncio.Lock()

    # -- Lifecycle ---------------------------------------------------------

    async def start(self) -> "TokenManager":
        """Legt den HTTP-Client an. Mehrfachaufrufe sind unschaedlich.

        Fuer langlebige Prozesse (MCP-Server), die keinen ``async with``-Block
        um ihre gesamte Laufzeit legen koennen.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._config.rest_base_url,
                timeout=self._config.request_timeout_seconds,
            )
        return self

    async def __aenter__(self) -> "TokenManager":
        return await self.start()

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("TokenManager muss als async context manager benutzt werden.")
        return self._client

    # -- Oeffentliche API --------------------------------------------------

    async def get_tokens(self) -> AccessTokens:
        """Liefert gueltige Tokens und erneuert sie bei Bedarf."""
        async with self._lock:
            margin = self._config.token_refresh_margin_seconds
            if self._tokens is None:
                self._tokens = await self._login()
            elif self._tokens.expired(margin):
                self._tokens = await self._renew_or_relogin()
            return self._tokens

    async def get_access_token(self) -> str:
        return (await self.get_tokens()).access_token

    async def get_md_access_token(self) -> str:
        return (await self.get_tokens()).md_access_token

    def invalidate(self) -> None:
        """Erzwingt beim naechsten Zugriff einen frischen Login."""
        self._tokens = None

    # -- Intern ------------------------------------------------------------

    async def _login(self) -> AccessTokens:
        payload = {
            "name": self._secrets.tradovate_username,
            "password": self._secrets.tradovate_password,
            "appId": self._secrets.tradovate_app_id,
            "appVersion": self._secrets.tradovate_app_version,
            "cid": self._secrets.tradovate_cid,
            "sec": self._secrets.tradovate_secret,
            "deviceId": self._secrets.tradovate_device_id,
        }

        for attempt in range(1, self.MAX_PENALTY_RETRIES + 1):
            data = await self._post_json("/auth/accesstokenrequest", payload)

            if data.get("errorText"):
                raise TradovateAuthError(f"Tradovate-Login abgelehnt: {data['errorText']}")

            if data.get("p-captcha"):
                raise TradovateAuthError(
                    "Tradovate verlangt ein Captcha. Bitte einmal manuell im Browser "
                    "einloggen und danach den Bot erneut starten."
                )

            ticket = data.get("p-ticket")
            if ticket:
                wait_seconds = float(data.get("p-time", 5))
                if wait_seconds > self.MAX_PENALTY_WAIT_SECONDS:
                    raise TradovateAuthError(
                        f"Tradovate verlangt {wait_seconds:.0f}s Wartezeit vor dem naechsten "
                        "Login-Versuch. Das ist zu lang - bitte spaeter erneut starten."
                    )
                log_event(
                    log,
                    "tradovate.auth.penalty",
                    f"Tradovate-Login gedrosselt, warte {wait_seconds:.0f}s "
                    f"(Versuch {attempt}/{self.MAX_PENALTY_RETRIES})",
                    level=logging.WARNING,
                    wait_seconds=wait_seconds,
                    attempt=attempt,
                )
                await asyncio.sleep(wait_seconds)
                payload = {**payload, "p-ticket": ticket}
                continue

            tokens = self._tokens_from_response(data)
            log_event(
                log,
                "tradovate.auth.login",
                "Tradovate-Login erfolgreich",
                environment=self._config.environment,
                expires_at=tokens.expires_at.isoformat(),
                user_id=tokens.user_id,
            )
            return tokens

        raise TradovateAuthError(
            "Tradovate-Login nach mehreren gedrosselten Versuchen nicht erfolgreich."
        )

    async def _renew_or_relogin(self) -> AccessTokens:
        assert self._tokens is not None
        try:
            response = await self.http.get(
                "/auth/renewaccesstoken",
                headers={"Authorization": f"Bearer {self._tokens.access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            if data.get("errorText") or not data.get("accessToken"):
                raise TradovateAuthError(data.get("errorText", "Kein accessToken in der Antwort."))
            tokens = self._tokens_from_response(data)
            log_event(
                log,
                "tradovate.auth.renewed",
                "Tradovate-Token erneuert",
                expires_at=tokens.expires_at.isoformat(),
            )
            return tokens
        except Exception as exc:  # noqa: BLE001 - jeder Fehler fuehrt zum Re-Login
            log_event(
                log,
                "tradovate.auth.renew_failed",
                f"Token-Erneuerung fehlgeschlagen ({exc}) - versuche vollstaendigen Login",
                level=logging.WARNING,
                error=str(exc),
            )
            return await self._login()

    def _tokens_from_response(self, data: dict) -> AccessTokens:
        access_token = data.get("accessToken")
        if not access_token:
            raise TradovateAuthError(f"Antwort ohne accessToken: {data}")
        return AccessTokens(
            access_token=access_token,
            # Wenn Market-Data nicht freigeschaltet ist, fehlt mdAccessToken.
            md_access_token=data.get("mdAccessToken") or access_token,
            expires_at=_parse_expiration(data.get("expirationTime")),
            user_id=data.get("userId"),
        )

    async def _post_json(self, path: str, payload: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                response = await self.http.post(path, json=payload)
                # 4xx sind fachliche Fehler und werden nicht wiederholt.
                if 400 <= response.status_code < 500:
                    raise TradovateAuthError(
                        f"Tradovate antwortete mit {response.status_code}: {response.text[:300]}"
                    )
                response.raise_for_status()
                return response.json()
            except TradovateAuthError:
                raise
            except Exception as exc:  # noqa: BLE001 - Netzfehler: wiederholen
                last_error = exc
                delay = min(2.0 ** attempt, 30.0)
                log_event(
                    log,
                    "tradovate.auth.retry",
                    f"Auth-Request fehlgeschlagen ({exc}), Wiederholung in {delay:.0f}s",
                    level=logging.WARNING,
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(delay)
        raise TradovateAuthError(f"Auth-Request endgueltig fehlgeschlagen: {last_error}")
