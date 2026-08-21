"""Einstiegspunkt des Live-Alert-Bots.

    python -m live_bot.main --config config.yaml

Der Bot liest ausschliesslich Marktdaten, berechnet Indikatoren, prueft
Alarm-Bedingungen und verschickt Benachrichtigungen. Er platziert
**keine Orders** - es gibt in diesem Projekt bewusst keinen einzigen
Aufruf eines Order-Endpunkts.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone

import pandas as pd

from common.config import Config, ConfigError, Secrets
from common.logging_setup import log_event, setup_logging
from live_bot.ai.claude_client import ClaudeCommentator
from live_bot.alerts.conditions import Alert, ConditionEvaluator
from live_bot.alerts.cooldown import CooldownTracker
from live_bot.market.candles import Candle, CandleAggregator, Tick
from live_bot.market.feed import MarketDataFeed
from live_bot.market.state import MarketSnapshot, MarketState
from live_bot.notify.notifier import Notifier, format_alert_message
from live_bot.notify.telegram_commands import TelegramCommandListener
from live_bot.on_demand_report import OnDemandReportService
from live_bot.tradovate.auth import TokenManager
from live_bot.tradovate.contracts import resolve_contract
from live_bot.tradovate.rest import TradovateRestClient

log = logging.getLogger("live_bot")

# Wie oft geprueft wird, ob die laufende Kerze abgelaufen ist (Sekunden).
CANDLE_TICKER_INTERVAL = 5.0


class LiveBot:
    def __init__(self, config: Config, secrets: Secrets, symbol: str) -> None:
        self._config = config
        self._secrets = secrets
        self._symbol = symbol

        self._aggregator = CandleAggregator(config.market.candle_interval_minutes)
        self._state = MarketState(symbol, config.market, config.indicators)
        self._evaluator = ConditionEvaluator(config.alerts, config.market)
        self._cooldowns = CooldownTracker(config.alerts)
        self._claude = ClaudeCommentator(config.claude, secrets.anthropic_api_key)
        self._notifier = Notifier(
            config.notify, secrets.telegram_bot_token, secrets.telegram_chat_id
        )
        self._stop_event = asyncio.Event()
        # Serialisiert die Verarbeitung: Ticks und der Kerzen-Ticker koennen
        # sonst gleichzeitig dieselbe Kerze schliessen wollen.
        self._lock = asyncio.Lock()

    # -- Lifecycle ---------------------------------------------------------

    async def run(self) -> int:
        async with TokenManager(self._config.tradovate, self._secrets) as tokens:
            async with self._notifier:
                feed = MarketDataFeed(
                    self._config.tradovate,
                    tokens,
                    symbol=self._symbol,
                    interval_minutes=self._config.market.candle_interval_minutes,
                    warmup_bars=self._config.market.warmup_bars,
                    on_tick=self._on_tick,
                    on_history=self._on_history,
                    on_connection_state=self._on_connection_state,
                )

                tasks = [
                    asyncio.create_task(feed.run(self._stop_event), name="feed"),
                    asyncio.create_task(self._candle_ticker(), name="candle-ticker"),
                ]

                listener = self._build_command_listener(tokens)
                if listener is not None:
                    tasks.append(
                        asyncio.create_task(
                            listener.run(self._stop_event), name="telegram-commands"
                        )
                    )

                log_event(
                    log,
                    "bot.started",
                    f"Bot laeuft: {self._symbol} @ {self._config.market.candle_interval_minutes}min "
                    f"({self._config.tradovate.environment.upper()})",
                    symbol=self._symbol,
                    environment=self._config.tradovate.environment,
                    interval_minutes=self._config.market.candle_interval_minutes,
                    claude_enabled=self._claude.enabled,
                    on_demand_enabled=listener is not None,
                )

                try:
                    await self._stop_event.wait()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await self._claude.aclose()

        log_event(log, "bot.stopped", "Bot beendet")
        return 0

    def request_stop(self) -> None:
        self._stop_event.set()

    # -- On-Demand-Bericht (/analyse) --------------------------------------

    def _build_command_listener(self, tokens: TokenManager) -> TelegramCommandListener | None:
        """Baut den Telegram-Befehlsempfaenger, wenn die Voraussetzungen stimmen."""
        if not self._config.on_demand.enabled:
            return None

        if not self._secrets.telegram_configured:
            log_event(
                log,
                "bot.on_demand_disabled",
                "/analyse ist nicht verfuegbar: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID fehlen. "
                "Der automatische Alarm laeuft davon unabhaengig weiter.",
                level=logging.WARNING,
            )
            return None

        service = OnDemandReportService(
            self._config,
            self._secrets,
            claude=self._claude,
            notifier=self._notifier,
            tokens=tokens,
            live_state_provider=self._live_state_snapshot,
        )
        return TelegramCommandListener(
            self._secrets.telegram_bot_token or "",
            self._secrets.telegram_chat_id or "",
            on_command=service.handle_command,
            long_poll_timeout=self._config.on_demand.long_poll_timeout_seconds,
            retry_delay=self._config.on_demand.poll_retry_delay_seconds,
        )

    async def _live_state_snapshot(self) -> tuple[str, pd.DataFrame] | None:
        """Kopiert den Kerzenpuffer unter dem Lock.

        Nur das Kopieren laeuft unter dem Lock - die anschliessende Analyse und
        der Claude-Aufruf (mehrere Sekunden) nicht. Sonst wuerde ein Bericht
        die Tick-Verarbeitung blockieren.
        """
        async with self._lock:
            if self._state.bar_count == 0:
                return None
            return self._state.symbol, self._state.dataframe()

    # -- Feed-Callbacks ----------------------------------------------------

    async def _on_connection_state(self, connected: bool) -> None:
        if connected:
            log_event(log, "bot.feed_up", "Marktdatenverbindung steht")
        else:
            log_event(
                log,
                "bot.feed_down",
                "Marktdatenverbindung unterbrochen",
                level=logging.WARNING,
            )
            # Nach einem Ausfall ist die laufende Kerze unvollstaendig.
            self._aggregator.reset()

    async def _on_history(self, candles: list[Candle]) -> None:
        async with self._lock:
            self._state.seed(candles)

    async def _on_tick(self, tick: Tick) -> None:
        async with self._lock:
            finished = self._aggregator.add_tick(tick.timestamp, tick.price, tick.size)
            if finished is not None:
                await self._handle_closed_candle(finished)

    async def _candle_ticker(self) -> None:
        """Schliesst Kerzen auch dann, wenn gerade keine Ticks kommen."""
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(CANDLE_TICKER_INTERVAL)
                async with self._lock:
                    finished = self._aggregator.close_expired(datetime.now(timezone.utc))
                    if finished is not None:
                        await self._handle_closed_candle(finished)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Ticker darf den Bot nicht killen
            log_event(
                log,
                "bot.ticker_error",
                f"Kerzen-Ticker abgebrochen: {exc}",
                level=logging.ERROR,
                error=str(exc),
                exc_info=True,
            )

    # -- Kernlogik ---------------------------------------------------------

    async def _handle_closed_candle(self, candle: Candle) -> None:
        snapshot = self._state.on_candle_closed(candle)
        if snapshot is None:
            return

        log_event(
            log,
            "candle.closed",
            f"Kerze {snapshot.timestamp:%H:%M} geschlossen @ {snapshot.close:.2f}",
            level=logging.DEBUG,
            timestamp=snapshot.timestamp.isoformat(),
            close=snapshot.close,
            volume=snapshot.volume,
            bars=snapshot.bars_available,
        )

        if not self._state.warm:
            return

        alerts = self._evaluator.evaluate(self._state.previous, snapshot)
        for alert in alerts:
            await self._process_alert(alert, snapshot)

    async def _process_alert(self, alert: Alert, snapshot: MarketSnapshot) -> None:
        now = datetime.now(timezone.utc)
        if not self._cooldowns.allows(alert.condition, now, snapshot.session_date):
            return
        self._cooldowns.record(alert.condition, now, snapshot.session_date)

        log_event(
            log,
            "alert.triggered",
            alert.headline,
            level=logging.WARNING,
            condition=alert.condition,
            direction=alert.direction,
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp.isoformat(),
            close=snapshot.close,
            rsi=snapshot.rsi,
            vwap=snapshot.vwap,
            details=alert.details,
        )

        comment = None
        if self._claude.enabled:
            comment = await self._claude.comment(snapshot, alert)

        message = format_alert_message(alert, snapshot, comment)
        result = await self._notifier.send(
            message,
            context={"condition": alert.condition, "symbol": snapshot.symbol},
        )

        log_event(
            log,
            "alert.delivered",
            f"Alarm '{alert.condition}' zugestellt via {result.delivered_via}",
            condition=alert.condition,
            channel=result.delivered_via,
            delivery_error=result.error,
            claude_ok=(comment.succeeded if comment else None),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="live_bot",
        description="Tradovate-Marktbeobachtung mit Claude-Kommentar und Telegram-Alarmen "
        "(read-only, keine Orderausfuehrung).",
    )
    parser.add_argument("--config", default="config.yaml", help="Pfad zur config.yaml")
    parser.add_argument("--env-file", default=".env", help="Pfad zur .env")
    parser.add_argument(
        "--environment",
        choices=("demo", "live"),
        help="Ueberschreibt tradovate.environment aus config.yaml und .env",
    )
    parser.add_argument(
        "--i-know-this-is-live",
        action="store_true",
        help="Pflichtbestaetigung fuer die Live-Umgebung (zusaetzlich zu "
        "allow_live_environment: true in der config.yaml)",
    )
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Sendet eine Testnachricht ueber den Benachrichtigungsweg und beendet sich",
    )
    return parser.parse_args(argv)


def resolve_environment(config: Config, secrets: Secrets, args: argparse.Namespace) -> Config:
    """CLI schlaegt .env, .env schlaegt config.yaml."""
    environment = args.environment or secrets.tradovate_env_override or config.tradovate.environment
    resolved = config.with_environment(environment)

    if resolved.tradovate.environment == "live":
        if not resolved.tradovate.allow_live_environment:
            raise ConfigError(
                "Live-Umgebung angefordert, aber tradovate.allow_live_environment ist false. "
                "Bitte erst gegen die Demo-Umgebung testen."
            )
        if not args.i_know_this_is_live:
            raise ConfigError(
                "Live-Umgebung angefordert. Zur Bestaetigung zusaetzlich "
                "--i-know-this-is-live angeben."
            )
    return resolved


async def send_test_notification(config: Config, secrets: Secrets) -> int:
    async with Notifier(
        config.notify, secrets.telegram_bot_token, secrets.telegram_chat_id
    ) as notifier:
        result = await notifier.send(
            "Testnachricht vom Claude Chart Bot.\n"
            "Wenn du das hier liest, funktioniert der Benachrichtigungsweg.\n\n"
            "Hinweis: Dies ist keine Anlageberatung.",
            context={"condition": "test"},
        )
    print(f"Zugestellt via: {result.delivered_via}")
    return 0


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    secrets = Secrets.load(args.env_file)
    setup_logging(config.logging, logger_name="live_bot")

    if args.test_notification:
        return await send_test_notification(config, secrets)

    try:
        config = resolve_environment(config, secrets, args)
        secrets.require_tradovate()
    except ConfigError as exc:
        log_event(log, "bot.config_error", str(exc), level=logging.ERROR)
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    if config.tradovate.environment == "live":
        log_event(
            log,
            "bot.live_environment",
            "ACHTUNG: Bot laeuft gegen die LIVE-Umgebung von Tradovate "
            "(nur lesend, keine Orders).",
            level=logging.WARNING,
        )

    # Kontrakt aufloesen, bevor der Feed startet.
    async with TokenManager(config.tradovate, secrets) as tokens:
        rest = TradovateRestClient(config.tradovate, tokens)
        try:
            contract = await resolve_contract(
                rest, config.market.product, config.market.contract_override
            )
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "bot.contract_error",
                f"Kontrakt konnte nicht aufgeloest werden: {exc}",
                level=logging.ERROR,
                error=str(exc),
            )
            print(f"Kontrakt konnte nicht aufgeloest werden: {exc}", file=sys.stderr)
            return 3

    bot = LiveBot(config, secrets, contract.name)

    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, bot.request_stop)
        except NotImplementedError:
            # Windows unterstuetzt add_signal_handler nicht - dort greift
            # der KeyboardInterrupt-Handler in main().
            pass

    return await bot.run()


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
