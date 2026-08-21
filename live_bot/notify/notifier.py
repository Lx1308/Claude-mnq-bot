"""Alarm-Zustellung: Telegram mit garantiertem Konsolen-/Log-Fallback.

Leitgedanke: Ein Alarm darf NIE verloren gehen. Ist Telegram nicht
konfiguriert oder schlaegt der Versand fehl, landet die Nachricht in jedem
Fall im Log und auf der Konsole.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from common.config import NotifyConfig
from common.logging_setup import log_event
from live_bot.ai.claude_client import ClaudeComment
from live_bot.alerts.conditions import Alert
from live_bot.market.state import MarketSnapshot

log = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Puffer fuer den "(1/2)"-Praefix bei aufgeteilten Nachrichten.
TELEGRAM_SAFE_CHUNK_LENGTH = 3900


def split_message(text: str, limit: int = TELEGRAM_SAFE_CHUNK_LENGTH) -> list[str]:
    """Zerlegt einen langen Text in telegramtaugliche Stuecke.

    Bevorzugt Absatzgrenzen, dann Zeilengrenzen. Nur wenn ein einzelner
    Absatz laenger als das Limit ist, wird hart geschnitten - besser ein
    unschoener Umbruch als eine abgeschnittene Nachricht.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > limit:
            # An der letzten Zeilengrenze innerhalb des Limits trennen.
            cut = paragraph.rfind("\n", 0, limit)
            if cut <= 0:
                cut = limit
            chunks.append(paragraph[:cut].rstrip())
            paragraph = paragraph[cut:].lstrip()
        current = paragraph

    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


@dataclass(frozen=True)
class DeliveryResult:
    delivered_via: str  # "telegram" | "console"
    error: str | None = None


def format_alert_message(
    alert: Alert, snapshot: MarketSnapshot, comment: ClaudeComment | None
) -> str:
    """Baut die Textnachricht (bewusst reiner Text, kein Markdown/HTML).

    Markdown wuerde bei Symbolen wie ``_`` oder ``*`` in Telegram zu
    Parse-Fehlern fuehren - reiner Text ist hier robuster als huebsch.
    """
    lines: list[str] = [
        f"[{alert.direction.upper()}] {alert.headline}",
        f"Zeit (UTC): {snapshot.timestamp:%Y-%m-%d %H:%M}",
        f"Close: {snapshot.close:.2f}   Volumen: {snapshot.volume:.0f}",
    ]

    indicator_bits: list[str] = []
    if snapshot.rsi is not None:
        indicator_bits.append(f"RSI(14) {snapshot.rsi:.1f}")
    if snapshot.sma_fast is not None:
        indicator_bits.append(f"SMA20 {snapshot.sma_fast:.2f}")
    if snapshot.sma_slow is not None:
        indicator_bits.append(f"SMA50 {snapshot.sma_slow:.2f}")
    if snapshot.vwap is not None:
        indicator_bits.append(f"VWAP {snapshot.vwap:.2f}")
    if snapshot.atr is not None:
        indicator_bits.append(f"ATR {snapshot.atr:.2f}")
    if indicator_bits:
        lines.append("  |  ".join(indicator_bits))

    if snapshot.prev_session_high is not None and snapshot.prev_session_low is not None:
        lines.append(
            f"Vortag: Hoch {snapshot.prev_session_high:.2f} / "
            f"Tief {snapshot.prev_session_low:.2f}"
        )

    if comment is not None and comment.succeeded and comment.text:
        lines.append("")
        lines.append(comment.text)
    elif comment is not None and not comment.succeeded:
        lines.append("")
        lines.append(f"(Claude-Kommentar nicht verfuegbar: {comment.error})")

    message = "\n".join(lines)
    if len(message) > TELEGRAM_MAX_MESSAGE_LENGTH:
        message = message[: TELEGRAM_MAX_MESSAGE_LENGTH - 20].rstrip() + "\n[gekuerzt]"
    return message


class Notifier:
    def __init__(
        self,
        config: NotifyConfig,
        bot_token: str | None,
        chat_id: str | None,
    ) -> None:
        self._config = config
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client: httpx.AsyncClient | None = None

        self._telegram_ready = bool(config.telegram_enabled and bot_token and chat_id)
        if config.telegram_enabled and not self._telegram_ready:
            log_event(
                log,
                "notify.telegram_unconfigured",
                "Telegram ist aktiviert, aber TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID fehlen "
                "- Alarme gehen auf Konsole und ins Log",
                level=logging.WARNING,
            )

    async def __aenter__(self) -> "Notifier":
        if self._telegram_ready:
            self._client = httpx.AsyncClient(timeout=self._config.telegram_timeout_seconds)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_long(
        self, message: str, *, context: dict[str, object] | None = None
    ) -> DeliveryResult:
        """Versendet auch Texte ueber dem Telegram-Limit, aufgeteilt in Teile.

        Fuer den On-Demand-Bericht wichtig: der ist deutlich laenger als ein
        Alarm und wuerde sonst am Limit abgeschnitten.
        """
        chunks = split_message(message)
        if len(chunks) == 1:
            return await self.send(chunks[0], context=context)

        result = DeliveryResult(delivered_via="console")
        for number, chunk in enumerate(chunks, start=1):
            result = await self.send(
                f"({number}/{len(chunks)})\n{chunk}", context=context
            )
        return result

    async def send(self, message: str, *, context: dict[str, object] | None = None) -> DeliveryResult:
        """Versendet eine Nachricht. Faellt bei jedem Fehler auf Log/Konsole zurueck."""
        context = context or {}

        if self._telegram_ready and self._client is not None:
            try:
                response = await self._client.post(
                    f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": message,
                        "disable_web_page_preview": True,
                    },
                )
                response.raise_for_status()
                body = response.json()
                if not body.get("ok", False):
                    raise RuntimeError(f"Telegram-API meldet Fehler: {body}")

                log_event(
                    log,
                    "notify.telegram.sent",
                    "Alarm per Telegram zugestellt",
                    **context,
                )
                return DeliveryResult(delivered_via="telegram")

            except Exception as exc:  # noqa: BLE001 - Fallback ist der Sinn der Sache
                log_event(
                    log,
                    "notify.telegram.failed",
                    f"Telegram-Versand fehlgeschlagen ({exc}) - Fallback auf Konsole",
                    level=logging.ERROR,
                    error=str(exc),
                    **context,
                )
                self._emit_fallback(message, context)
                return DeliveryResult(delivered_via="console", error=str(exc))

        self._emit_fallback(message, context)
        return DeliveryResult(delivered_via="console")

    @staticmethod
    def _emit_fallback(message: str, context: dict[str, object]) -> None:
        # Bewusst zusaetzlich print(): das Log kann auf WARNING stehen, der
        # Alarm soll trotzdem im Terminal sichtbar sein.
        print("\n" + "=" * 72)
        print(message)
        print("=" * 72 + "\n", flush=True)
        # Feldname bewusst nicht "message": das ist der Positionsparameter
        # von log_event und wuerde kollidieren.
        log_event(
            log,
            "notify.console",
            "Alarm auf Konsole ausgegeben",
            alert_text=message,
            **context,
        )
