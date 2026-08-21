"""On-Demand-Marktbericht ueber den Telegram-Befehl ``/analyse``.

Unabhaengig vom automatischen Alert-System: der Bericht laesst sich jederzeit
anfordern, auch wenn keine einzige Alarm-Bedingung erfuellt ist.

Wiederverwendung statt Duplikat
-------------------------------
Der Bericht rechnet nichts neu, was es schon gibt:

* Indikatoren        -> :func:`common.indicators.compute_indicators`
  (dieselbe Funktion wie Live-Bot und Backtest)
* Snapshot           -> :func:`live_bot.market.state.build_snapshot`
* Struktur/Zonen     -> :mod:`common.structure`
* Claude-Aufruf      -> :class:`live_bot.ai.claude_client.ClaudeCommentator`
  (derselbe Client, dieselben Timeouts und Retries, nur anderer Prompt)
* Zustellung         -> :class:`live_bot.notify.notifier.Notifier`

Datenherkunft
-------------
* Symbol == laufend beobachteter Kontrakt -> direkt aus dem Live-Puffer,
  ohne einen einzigen Netzwerkaufruf.
* Anderes Symbol -> Frontmonat aufloesen und Historie ueber ``md/getChart``
  nachladen. Kostet ein paar Sekunden, laeuft danach durch dieselbe Pipeline.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

import pandas as pd

from common.config import Config, Secrets
from common.indicators import compute_indicators
from common.logging_setup import log_event
from common.structure import (
    SwingPoint,
    TrendAssessment,
    Zone,
    assess_trend,
    find_swing_points,
    support_resistance_zones,
)
from live_bot.ai.claude_client import ClaudeComment, ClaudeCommentator
from live_bot.market.candles import candles_from_tradovate_bars
from live_bot.market.state import MarketSnapshot, build_snapshot
from live_bot.notify.notifier import Notifier
from live_bot.notify.telegram_commands import Command
from live_bot.tradovate.auth import TokenManager
from live_bot.tradovate.contracts import resolve_contract
from live_bot.tradovate.md_socket import MarketDataSocket
from live_bot.tradovate.rest import TradovateRestClient

log = logging.getLogger(__name__)

COMMAND_NAME = "analyse"
HELP_TEXT = (
    "Verfuegbare Befehle:\n"
    "/analyse            - Marktbericht zum laufenden Symbol\n"
    "/analyse NQ         - Marktbericht zu einem anderen Produkt\n"
    "/analyse NQZ5       - Marktbericht zu einem konkreten Kontrakt"
)

# Der Live-Puffer wird unter dem Lock des Bots kopiert und hier ausgewertet.
LiveStateProvider = Callable[[], Awaitable["tuple[str, pd.DataFrame] | None"]]


@dataclass(frozen=True)
class ReportData:
    """Alles, was fuer einen Bericht zusammengetragen wurde."""

    symbol: str
    source: str            # "live-puffer" | "historie"
    snapshot: MarketSnapshot
    trend: TrendAssessment
    supports: list[Zone]
    resistances: list[Zone]
    swings: list[SwingPoint]
    session_high: float | None
    session_low: float | None
    bars_used: int


class ReportUnavailable(RuntimeError):
    """Der Bericht konnte nicht erstellt werden - Text ist nutzerlesbar."""


# ---------------------------------------------------------------------------
# Rate-Limiting
# ---------------------------------------------------------------------------

class ReportRateLimiter:
    """Eigene Bremse fuer On-Demand-Berichte.

    Bewusst getrennt vom Alarm-Cooldown: sonst wuerde ein Schwung
    ``/analyse``-Anfragen das Tageskontingent der automatischen Alarme
    aufbrauchen - oder umgekehrt.
    """

    def __init__(self, cooldown_seconds: float, max_per_day: int) -> None:
        self._cooldown = cooldown_seconds
        self._max_per_day = max_per_day
        self._last_at: float | None = None
        self._day: date | None = None
        self._count = 0

    def _roll_day(self, now: datetime) -> None:
        """Setzt den Zaehler zum Tageswechsel zurueck.

        Wird von ``check`` UND ``record`` aufgerufen: haenge der Tageswechsel
        nur an ``check``, koennte ein ``record`` vor dem ersten ``check`` den
        Zaehler wieder verlieren.
        """
        today = now.date()
        if self._day != today:
            self._day = today
            self._count = 0

    def check(self, now: datetime | None = None) -> str | None:
        """Gibt ``None`` zurueck, wenn erlaubt - sonst den Ablehnungstext."""
        now = now or datetime.now(timezone.utc)
        self._roll_day(now)

        if self._max_per_day > 0 and self._count >= self._max_per_day:
            return (
                f"Tageslimit erreicht ({self._max_per_day} Berichte). "
                "Morgen wieder verfuegbar - oder das Limit in der config.yaml "
                "unter on_demand.max_reports_per_day anheben."
            )

        if self._last_at is not None:
            elapsed = time.monotonic() - self._last_at
            if elapsed < self._cooldown:
                return (
                    f"Bitte noch {self._cooldown - elapsed:.0f}s warten - "
                    "jeder Bericht kostet einen Claude-Aufruf."
                )
        return None

    def record(self, now: datetime | None = None) -> None:
        self._roll_day(now or datetime.now(timezone.utc))
        self._last_at = time.monotonic()
        self._count += 1


# ---------------------------------------------------------------------------
# Dienst
# ---------------------------------------------------------------------------

class OnDemandReportService:
    def __init__(
        self,
        config: Config,
        secrets: Secrets,
        *,
        claude: ClaudeCommentator,
        notifier: Notifier,
        live_state_provider: LiveStateProvider,
        # Optional: nur noetig, um Historie fuer ein NICHT gestreamtes Symbol
        # nachzuladen. Ohne Tradovate-Zugang funktioniert der Bericht zum
        # laufenden Kontrakt trotzdem.
        tokens: TokenManager | None = None,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._claude = claude
        self._notifier = notifier
        self._tokens = tokens
        self._live_state = live_state_provider
        self._limiter = ReportRateLimiter(
            config.on_demand.cooldown_seconds, config.on_demand.max_reports_per_day
        )

    # -- Befehlseinstieg ---------------------------------------------------

    async def handle_command(self, command: Command) -> None:
        """Verarbeitet einen eingegangenen Telegram-Befehl."""
        if command.name in {"help", "start", "hilfe"}:
            await self._notifier.send(HELP_TEXT, context={"command": command.name})
            return

        if command.name != COMMAND_NAME:
            await self._notifier.send(
                f"Unbekannter Befehl /{command.name}.\n\n{HELP_TEXT}",
                context={"command": command.name},
            )
            return

        rejection = self._limiter.check()
        if rejection is not None:
            log_event(
                log,
                "report.rate_limited",
                f"On-Demand-Bericht abgelehnt: {rejection}",
                level=logging.WARNING,
                command=command.raw_text,
            )
            await self._notifier.send(rejection, context={"command": command.name})
            return

        requested = command.first_arg
        started = time.monotonic()

        try:
            data = await self.collect(requested)
        except ReportUnavailable as exc:
            await self._notifier.send(str(exc), context={"command": command.name})
            return
        except Exception as exc:  # noqa: BLE001 - der Bot laeuft weiter
            log_event(
                log,
                "report.failed",
                f"Bericht konnte nicht erstellt werden: {exc}",
                level=logging.ERROR,
                error=str(exc),
                exc_info=True,
            )
            await self._notifier.send(
                f"Bericht fehlgeschlagen: {exc}", context={"command": command.name}
            )
            return

        # Erst hier zaehlen: an einer Datenpanne soll das Kontingent nicht haengen.
        self._limiter.record()

        payload = build_report_payload(data, self._config)
        log_event(
            log,
            "report.requested",
            f"On-Demand-Bericht fuer {data.symbol} angefordert",
            symbol=data.symbol,
            source=data.source,
            bars=data.bars_used,
            close=data.snapshot.close,
            trend=data.trend.direction,
            supports=[zone.price for zone in data.supports],
            resistances=[zone.price for zone in data.resistances],
        )

        comment = await self._claude.report(payload, symbol=data.symbol)
        message = format_report_message(data, comment)
        result = await self._notifier.send_long(
            message, context={"command": command.name, "symbol": data.symbol}
        )

        log_event(
            log,
            "report.delivered",
            f"Bericht fuer {data.symbol} zugestellt via {result.delivered_via}",
            symbol=data.symbol,
            channel=result.delivered_via,
            claude_ok=comment.succeeded,
            duration_seconds=round(time.monotonic() - started, 1),
        )

    # -- Datenbeschaffung --------------------------------------------------

    async def collect(self, requested_symbol: str | None) -> ReportData:
        """Traegt alle Kennzahlen fuer den Bericht zusammen."""
        symbol, frame, source = await self._resolve_frame(requested_symbol)

        minimum = max(
            self._config.indicators.min_bars_required,
            2 * self._config.on_demand.swing_strength + 1,
        )
        if len(frame) < minimum:
            raise ReportUnavailable(
                f"Zu wenige Kerzen fuer {symbol}: {len(frame)} vorhanden, "
                f"{minimum} noetig. Der Bot braucht nach dem Start ein paar "
                "Minuten, bis die Indikatoren belastbar sind."
            )

        enriched = compute_indicators(
            frame, self._config.indicators, self._config.market.session
        )
        snapshot = build_snapshot(
            symbol,
            self._config.market,
            enriched.iloc[-1],
            enriched.index[-1],
            len(enriched),
        )

        on_demand = self._config.on_demand
        supports, resistances = support_resistance_zones(
            enriched,
            atr_value=snapshot.atr,
            strength=on_demand.swing_strength,
            lookback=on_demand.swing_lookback,
            max_zones=on_demand.max_zones,
            merge_atr=on_demand.zone_merge_atr,
        )
        trend = assess_trend(
            enriched,
            atr_value=snapshot.atr,
            slope_lookback=on_demand.trend_slope_lookback,
            flat_threshold_atr=on_demand.trend_flat_threshold_atr,
        )
        swings = find_swing_points(
            enriched, strength=on_demand.swing_strength, lookback=on_demand.swing_lookback
        )[:4]

        session_high, session_low = _current_session_range(enriched, snapshot.session_date)

        return ReportData(
            symbol=symbol,
            source=source,
            snapshot=snapshot,
            trend=trend,
            supports=supports,
            resistances=resistances,
            swings=swings,
            session_high=session_high,
            session_low=session_low,
            bars_used=len(enriched),
        )

    async def _resolve_frame(
        self, requested_symbol: str | None
    ) -> tuple[str, pd.DataFrame, str]:
        """Liefert (Symbol, OHLCV-Frame, Quelle)."""
        live = await self._live_state()
        live_symbol = live[0] if live else None

        wanted = (requested_symbol or "").strip().upper() or None

        # Kein Symbol angegeben, oder es passt zum laufenden Kontrakt
        # (auch "NQ" trifft "NQZ5") -> Live-Puffer verwenden.
        if live is not None and (
            wanted is None
            or wanted == live_symbol
            or (live_symbol or "").startswith(wanted)
        ):
            return live_symbol or "", live[1], "live-puffer"

        if wanted is None:
            raise ReportUnavailable(
                "Der Live-Puffer ist noch leer und es wurde kein Symbol angegeben. "
                "Bitte kurz warten oder ein Symbol nennen, z.B. /analyse NQ"
            )

        if not self._config.on_demand.allow_symbol_override:
            raise ReportUnavailable(
                f"Abweichende Symbole sind deaktiviert (on_demand.allow_symbol_override). "
                f"Der Bot beobachtet gerade {live_symbol}."
            )

        frame = await self._fetch_history(wanted)
        return frame.attrs.get("symbol", wanted), frame, "historie"

    async def _fetch_history(self, requested: str) -> pd.DataFrame:
        """Laedt Historie fuer ein Symbol, das der Bot nicht streamt."""
        if self._tokens is None:
            raise ReportUnavailable(
                "Fuer ein abweichendes Symbol wird ein Tradovate-Zugang benoetigt, "
                "der hier nicht verfuegbar ist."
            )
        rest = TradovateRestClient(self._config.tradovate, self._tokens)

        # "NQ" -> Frontmonat aufloesen; "NQZ5" wird direkt uebernommen.
        looks_like_contract = len(requested) > 3 and requested[-1].isdigit()
        try:
            contract = await resolve_contract(
                rest,
                product=requested[:2] if looks_like_contract else requested,
                override=requested if looks_like_contract else None,
            )
        except Exception as exc:  # noqa: BLE001
            raise ReportUnavailable(
                f"Symbol {requested} konnte nicht aufgeloest werden: {exc}"
            ) from exc

        md_token = await self._tokens.get_md_access_token()
        socket = MarketDataSocket(
            self._config.tradovate.market_data_url,
            md_token,
            heartbeat_interval=self._config.tradovate.websocket.heartbeat_interval_seconds,
        )

        try:
            await socket.connect()
            raw_bars = await socket.fetch_history(
                contract.name,
                interval_minutes=self._config.market.candle_interval_minutes,
                bars=self._config.on_demand.history_bars,
            )
        except Exception as exc:  # noqa: BLE001
            raise ReportUnavailable(
                f"Historie fuer {contract.name} konnte nicht geladen werden: {exc}"
            ) from exc
        finally:
            await socket.close()

        candles = candles_from_tradovate_bars(
            raw_bars, self._config.market.candle_interval_minutes
        )
        # Die letzte Kerze laeuft noch - fuer eine Analyse nicht verwendbar.
        candles = candles[:-1]
        if not candles:
            raise ReportUnavailable(f"Keine verwertbaren Kerzen fuer {contract.name} erhalten.")

        frame = pd.DataFrame(
            [candle.as_row() for candle in candles],
            index=pd.DatetimeIndex([candle.start for candle in candles], tz="UTC"),
        )
        frame.attrs["symbol"] = contract.name
        return frame


# ---------------------------------------------------------------------------
# Payload und Nachricht
# ---------------------------------------------------------------------------

def _current_session_range(
    enriched: pd.DataFrame, session_day: date | None
) -> tuple[float | None, float | None]:
    """Hoch und Tief der laufenden Session bis zur letzten Kerze."""
    if session_day is None or "session_date" not in enriched.columns:
        return None, None
    mask = enriched["session_date"] == session_day
    if not mask.any():
        return None, None
    return float(enriched.loc[mask, "high"].max()), float(enriched.loc[mask, "low"].min())


def build_report_payload(data: ReportData, config: Config) -> dict[str, Any]:
    """Baut das Kennzahlen-Objekt fuer Claude.

    Wie beim Alarm gilt: nur berechnete Groessen, keine Rohdaten, keine
    Kerzenlisten, keine Bilder. Alles an einer Stelle, damit im Test und im
    Log nachvollziehbar ist, was das Haus verlaesst.
    """
    snapshot = data.snapshot

    def rounded(value: float | None, digits: int = 2) -> float | None:
        return round(value, digits) if value is not None else None

    atr = snapshot.atr
    session_range = (
        data.session_high - data.session_low
        if data.session_high is not None and data.session_low is not None
        else None
    )
    position_in_range = None
    if session_range and session_range > 0 and data.session_low is not None:
        position_in_range = round(
            (snapshot.close - data.session_low) / session_range * 100.0, 1
        )

    return {
        "instrument": snapshot.symbol,
        "kerzenintervall_minuten": snapshot.interval_minutes,
        "zeitpunkt_utc": snapshot.timestamp.isoformat(),
        "handelstag": snapshot.session_date.isoformat() if snapshot.session_date else None,
        "datenquelle": data.source,
        "kerzen_im_fenster": data.bars_used,
        "kontrakt": {
            "tick_size": config.market.tick_size,
            "punktwert_usd": config.market.point_value,
        },
        "kerze": {
            "open": rounded(snapshot.open),
            "high": rounded(snapshot.high),
            "low": rounded(snapshot.low),
            "close": rounded(snapshot.close),
            "volumen": rounded(snapshot.volume, 0),
        },
        "indikatoren": {
            "rsi_14": rounded(snapshot.rsi, 1),
            "sma_20": rounded(snapshot.sma_fast),
            "sma_50": rounded(snapshot.sma_slow),
            "vwap_session": rounded(snapshot.vwap),
            "atr": rounded(atr),
            "abstand_close_zu_vwap": (
                rounded(snapshot.close - snapshot.vwap) if snapshot.vwap is not None else None
            ),
            "abstand_close_zu_vwap_in_atr": (
                rounded((snapshot.close - snapshot.vwap) / atr)
                if snapshot.vwap is not None and atr
                else None
            ),
            "close_ueber_sma20": (
                None if snapshot.sma_fast is None else snapshot.close > snapshot.sma_fast
            ),
            "sma20_ueber_sma50": (
                None
                if snapshot.sma_fast is None or snapshot.sma_slow is None
                else snapshot.sma_fast > snapshot.sma_slow
            ),
        },
        "trend": data.trend.to_dict(),
        "tagesspanne": {
            "hoch": rounded(data.session_high),
            "tief": rounded(data.session_low),
            "spanne_punkte": rounded(session_range),
            "spanne_in_atr": rounded(session_range / atr) if session_range and atr else None,
            "position_im_range_prozent": position_in_range,
        },
        "vortagesmarken": {
            "hoch": rounded(snapshot.prev_session_high),
            "tief": rounded(snapshot.prev_session_low),
            "schluss": rounded(snapshot.prev_session_close),
        },
        "konsolidierung": {
            "in_konsolidierung": snapshot.flag_in_consolidation,
            "impulsrichtung": snapshot.flag_direction,
            "range_hoch": rounded(snapshot.flag_range_high),
            "range_tief": rounded(snapshot.flag_range_low),
            "ausbruch_oben": snapshot.flag_breakout_up,
            "ausbruch_unten": snapshot.flag_breakout_down,
        },
        "zonen": {
            "unterstuetzungen": [zone.to_dict() for zone in data.supports],
            "widerstaende": [zone.to_dict() for zone in data.resistances],
        },
        "letzte_swing_punkte": [point.to_dict() for point in data.swings],
    }


def format_report_message(data: ReportData, comment: ClaudeComment) -> str:
    """Baut die Telegram-Nachricht: kompakter Zahlenkopf plus Claude-Text."""
    snapshot = data.snapshot
    lines = [
        f"MARKTBERICHT {snapshot.symbol}  ({snapshot.interval_minutes}min)",
        f"Stand: {snapshot.timestamp:%Y-%m-%d %H:%M} UTC   Close: {snapshot.close:.2f}",
    ]

    indicators = []
    if snapshot.rsi is not None:
        indicators.append(f"RSI {snapshot.rsi:.1f}")
    if snapshot.atr is not None:
        indicators.append(f"ATR {snapshot.atr:.2f}")
    if snapshot.vwap is not None:
        indicators.append(f"VWAP {snapshot.vwap:.2f}")
    if snapshot.sma_fast is not None:
        indicators.append(f"SMA20 {snapshot.sma_fast:.2f}")
    if snapshot.sma_slow is not None:
        indicators.append(f"SMA50 {snapshot.sma_slow:.2f}")
    if indicators:
        lines.append("  |  ".join(indicators))

    lines.append(f"Trend: {data.trend.direction}")

    if data.resistances:
        rendered = "  ".join(
            f"{zone.price:.2f}({zone.touches}x)" for zone in data.resistances
        )
        lines.append(f"Widerstand: {rendered}")
    if data.supports:
        rendered = "  ".join(
            f"{zone.price:.2f}({zone.touches}x)" for zone in data.supports
        )
        lines.append(f"Unterstuetzung: {rendered}")

    if snapshot.prev_session_high is not None and snapshot.prev_session_low is not None:
        lines.append(
            f"Vortag: {snapshot.prev_session_low:.2f} - {snapshot.prev_session_high:.2f}"
        )

    if data.source == "historie":
        lines.append("(Daten nachgeladen, nicht aus dem laufenden Stream)")

    lines.append("")
    if comment.succeeded and comment.text:
        lines.append(comment.text)
    else:
        lines.append(
            f"Claude-Analyse nicht verfuegbar: {comment.error}\n"
            "Die Kennzahlen oben stammen direkt aus der Pipeline und sind gueltig."
        )

    return "\n".join(lines)
