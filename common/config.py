"""Laden und Validieren von config.yaml + .env.

Grundregel: Schwellenwerte und Verhalten kommen aus der YAML, Secrets
ausschliesslich aus Umgebungsvariablen. Nichts davon steht im Code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Any, Mapping

import yaml

try:  # python-dotenv ist optional zur Laufzeit (z.B. in CI ohne .env)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(RuntimeError):
    """Konfiguration ist unvollstaendig oder widerspruechlich."""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Fehlender Konfigurationsschluessel '{key}' unter '{where}'.")
    return mapping[key]


def _parse_hhmm(value: str, where: str) -> dtime:
    try:
        hour_str, minute_str = value.split(":")
        return dtime(int(hour_str), int(minute_str))
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"'{where}' muss im Format HH:MM stehen, war: {value!r}") from exc


# ---------------------------------------------------------------------------
# Secrets (.env)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Secrets:
    tradovate_username: str
    tradovate_password: str
    tradovate_cid: str
    tradovate_secret: str
    tradovate_device_id: str
    tradovate_app_id: str
    tradovate_app_version: str
    anthropic_api_key: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    tradovate_env_override: str | None
    fred_api_key: str | None = None

    @staticmethod
    def load(dotenv_path: str | os.PathLike[str] | None = ".env") -> "Secrets":
        if dotenv_path is not None and Path(dotenv_path).exists():
            load_dotenv(dotenv_path, override=False)

        def opt(name: str) -> str | None:
            value = os.environ.get(name, "").strip()
            return value or None

        return Secrets(
            tradovate_username=opt("TRADOVATE_USERNAME") or "",
            tradovate_password=opt("TRADOVATE_PASSWORD") or "",
            tradovate_cid=opt("TRADOVATE_CID") or "",
            tradovate_secret=opt("TRADOVATE_SECRET") or "",
            tradovate_device_id=opt("TRADOVATE_DEVICE_ID") or "",
            tradovate_app_id=opt("TRADOVATE_APP_ID") or "ClaudeChartBot",
            tradovate_app_version=opt("TRADOVATE_APP_VERSION") or "1.0.0",
            anthropic_api_key=opt("ANTHROPIC_API_KEY"),
            telegram_bot_token=opt("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=opt("TELEGRAM_CHAT_ID"),
            tradovate_env_override=(opt("TRADOVATE_ENV") or "").lower() or None,
            fred_api_key=opt("FRED_API_KEY"),
        )

    def require_tradovate(self) -> None:
        """Wirft, wenn Pflichtfelder fuer die Tradovate-Auth fehlen."""
        missing = [
            name
            for name, value in (
                ("TRADOVATE_USERNAME", self.tradovate_username),
                ("TRADOVATE_PASSWORD", self.tradovate_password),
                ("TRADOVATE_CID", self.tradovate_cid),
                ("TRADOVATE_SECRET", self.tradovate_secret),
                ("TRADOVATE_DEVICE_ID", self.tradovate_device_id),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Folgende Umgebungsvariablen fehlen (siehe .env.example): "
                + ", ".join(missing)
            )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


# ---------------------------------------------------------------------------
# Konfigurations-Sektionen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WebsocketConfig:
    heartbeat_interval_seconds: float = 2.5
    reconnect_initial_delay_seconds: float = 2.0
    reconnect_max_delay_seconds: float = 120.0
    reconnect_backoff_factor: float = 2.0
    stale_data_timeout_seconds: float = 90.0


@dataclass(frozen=True)
class TradovateConfig:
    environment: str = "demo"
    allow_live_environment: bool = False
    token_refresh_margin_seconds: int = 300
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    websocket: WebsocketConfig = field(default_factory=WebsocketConfig)

    @property
    def rest_base_url(self) -> str:
        host = "live" if self.environment == "live" else "demo"
        return f"https://{host}.tradovateapi.com/v1"

    @property
    def market_data_url(self) -> str:
        host = "md" if self.environment == "live" else "md-demo"
        return f"wss://{host}.tradovateapi.com/v1/websocket"


@dataclass(frozen=True)
class SessionConfig:
    timezone: str = "America/New_York"
    start_time: dtime = dtime(18, 0)
    end_time: dtime = dtime(17, 0)


@dataclass(frozen=True)
class MarketConfig:
    product: str = "NQ"
    contract_override: str | None = None
    candle_interval_minutes: int = 1
    candle_buffer_size: int = 500
    warmup_bars: int = 300
    tick_size: float = 0.25
    point_value: float = 20.0
    session: SessionConfig = field(default_factory=SessionConfig)

    # CME-Globex laeuft 18:00 ET bis 17:00 ET mit einer Stunde Pause = 23h.
    SESSION_MINUTES = 23 * 60

    @property
    def bars_per_session(self) -> int:
        """Wie viele Kerzen eine volle Handelssession umfasst."""
        return max(1, self.SESSION_MINUTES // self.candle_interval_minutes)

    @property
    def bars_for_previous_session(self) -> int:
        """Puffergroesse, ab der Vortageshoch/-tief zuverlaessig vorliegen.

        Es braucht die KOMPLETTE Vorsession plus die laufende Session - erst
        dann kennt ``previous_session_levels`` beide Handelstage. Ist der
        Puffer kleiner, bleiben die Vortagesmarken NaN und die zugehoerigen
        Alarme koennen niemals ausloesen. Genau so ein stiller Ausfall soll
        beim Start auffallen, nicht nach Wochen ohne Alarm.
        """
        return 2 * self.bars_per_session


@dataclass(frozen=True)
class FlagConfig:
    impulse_lookback: int = 20
    impulse_min_atr: float = 2.5
    consolidation_lookback: int = 10
    consolidation_max_atr: float = 1.2
    breakout_buffer_atr: float = 0.1


@dataclass(frozen=True)
class IndicatorConfig:
    rsi_period: int = 14
    sma_fast: int = 20
    sma_slow: int = 50
    atr_period: int = 14
    flag: FlagConfig = field(default_factory=FlagConfig)

    @property
    def min_bars_required(self) -> int:
        """Wie viele Kerzen mindestens im Puffer sein muessen."""
        return max(
            self.rsi_period + 1,
            self.sma_slow,
            self.atr_period + 1,
            self.flag.impulse_lookback + self.flag.consolidation_lookback + 1,
        )


@dataclass(frozen=True)
class ConditionConfig:
    enabled: bool = True
    cooldown_minutes: int | None = None
    level: float | None = None
    buffer_ticks: float = 0.0


@dataclass(frozen=True)
class AlertConfig:
    default_cooldown_minutes: int = 30
    max_alerts_per_session: int = 20
    conditions: dict[str, ConditionConfig] = field(default_factory=dict)

    def for_condition(self, name: str) -> ConditionConfig:
        return self.conditions.get(name, ConditionConfig(enabled=False))

    def cooldown_for(self, name: str) -> int:
        cfg = self.for_condition(name)
        return cfg.cooldown_minutes if cfg.cooldown_minutes is not None else self.default_cooldown_minutes


@dataclass(frozen=True)
class ClaudeConfig:
    model: str = "claude-sonnet-5"
    max_tokens: int = 1200
    timeout_seconds: float = 45.0
    max_retries: int = 2
    effort: str = "low"
    # Der On-Demand-Bericht braucht mehr Raum als ein Alarm-Kommentar.
    report_max_tokens: int = 4000
    report_effort: str = "medium"


@dataclass(frozen=True)
class NtBridgeConfig:
    """Empfaenger fuer Kerzen aus NinjaTrader 8."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8787
    database: str = "data/ntbridge.sqlite3"
    # Juengster Bar aelter als factor * Bar-Laenge -> Snapshot markiert veraltet.
    stale_factor: float = 2.0
    # NinjaTrader-Name -> internes Root, falls der Broker abweichend benennt.
    symbol_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EventRiskConfig:
    """Wirtschaftskalender (MCP-Tool ``get_event_risk``)."""

    enabled: bool = True
    currencies: tuple[str, ...] = ("USD",)
    impacts: tuple[str, ...] = ("High",)
    blackout_minutes_before: float = 15.0
    blackout_minutes_after: float = 15.0
    schedule_cache_minutes: float = 30.0
    actual_cache_hours: float = 6.0
    upcoming_limit: int = 8
    forex_factory_url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


@dataclass(frozen=True)
class OnDemandConfig:
    enabled: bool = True
    long_poll_timeout_seconds: float = 25.0
    poll_retry_delay_seconds: float = 5.0
    cooldown_seconds: float = 60.0
    max_reports_per_day: int = 50
    allow_symbol_override: bool = True
    history_bars: int = 400
    swing_strength: int = 3
    swing_lookback: int = 120
    max_zones: int = 3
    zone_merge_atr: float = 0.5
    trend_slope_lookback: int = 10
    trend_flat_threshold_atr: float = 0.02


@dataclass(frozen=True)
class NotifyConfig:
    telegram_enabled: bool = True
    telegram_timeout_seconds: float = 15.0


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    directory: str = "logs"
    text_file: str = "bot.log"
    json_file: str = "events.jsonl"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    console: bool = True


@dataclass(frozen=True)
class SplitConfig:
    mode: str = "fraction"
    in_sample_fraction: float = 0.7
    split_date: str | None = None


@dataclass(frozen=True)
class BacktestConfig:
    provider: str = "csv"
    csv_directory: str = "data"
    output_directory: str = "backtest_results"
    commission_per_side: float = 2.50
    slippage_ticks_per_side: float = 1.0
    split: SplitConfig = field(default_factory=SplitConfig)


@dataclass(frozen=True)
class Config:
    tradovate: TradovateConfig
    market: MarketConfig
    indicators: IndicatorConfig
    # Alles ab hier hat brauchbare Defaults - so laesst sich ein Config-Objekt
    # in Tests und Skripten aufbauen, ohne jede Sektion auszubuchstabieren.
    alerts: AlertConfig = field(default_factory=AlertConfig)
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    on_demand: OnDemandConfig = field(default_factory=OnDemandConfig)
    event_risk: EventRiskConfig = field(default_factory=EventRiskConfig)
    ntbridge: NtBridgeConfig = field(default_factory=NtBridgeConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- Laden -------------------------------------------------------------

    @staticmethod
    def load(path: str | os.PathLike[str] = DEFAULT_CONFIG_PATH) -> "Config":
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(f"Konfigurationsdatei nicht gefunden: {config_path.resolve()}")
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ConfigError("config.yaml muss ein Mapping auf oberster Ebene sein.")
        return Config.from_dict(data)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Config":
        tv = dict(_require(data, "tradovate", "root"))
        ws = dict(tv.pop("websocket", {}) or {})
        tradovate = TradovateConfig(
            environment=str(tv.get("environment", "demo")).lower(),
            allow_live_environment=bool(tv.get("allow_live_environment", False)),
            token_refresh_margin_seconds=int(tv.get("token_refresh_margin_seconds", 300)),
            request_timeout_seconds=float(tv.get("request_timeout_seconds", 20)),
            max_retries=int(tv.get("max_retries", 3)),
            websocket=WebsocketConfig(
                heartbeat_interval_seconds=float(ws.get("heartbeat_interval_seconds", 2.5)),
                reconnect_initial_delay_seconds=float(ws.get("reconnect_initial_delay_seconds", 2)),
                reconnect_max_delay_seconds=float(ws.get("reconnect_max_delay_seconds", 120)),
                reconnect_backoff_factor=float(ws.get("reconnect_backoff_factor", 2.0)),
                stale_data_timeout_seconds=float(ws.get("stale_data_timeout_seconds", 90)),
            ),
        )

        mk = dict(_require(data, "market", "root"))
        sess = dict(mk.pop("session", {}) or {})
        market = MarketConfig(
            product=str(mk.get("product", "NQ")).upper(),
            contract_override=(mk.get("contract_override") or None),
            candle_interval_minutes=int(mk.get("candle_interval_minutes", 1)),
            candle_buffer_size=int(mk.get("candle_buffer_size", 500)),
            warmup_bars=int(mk.get("warmup_bars", 300)),
            tick_size=float(mk.get("tick_size", 0.25)),
            point_value=float(mk.get("point_value", 20.0)),
            session=SessionConfig(
                timezone=str(sess.get("timezone", "America/New_York")),
                start_time=_parse_hhmm(str(sess.get("start_time", "18:00")), "market.session.start_time"),
                end_time=_parse_hhmm(str(sess.get("end_time", "17:00")), "market.session.end_time"),
            ),
        )

        ind = dict(data.get("indicators", {}) or {})
        flag = dict(ind.pop("flag", {}) or {})
        indicators = IndicatorConfig(
            rsi_period=int(ind.get("rsi_period", 14)),
            sma_fast=int(ind.get("sma_fast", 20)),
            sma_slow=int(ind.get("sma_slow", 50)),
            atr_period=int(ind.get("atr_period", 14)),
            flag=FlagConfig(
                impulse_lookback=int(flag.get("impulse_lookback", 20)),
                impulse_min_atr=float(flag.get("impulse_min_atr", 2.5)),
                consolidation_lookback=int(flag.get("consolidation_lookback", 10)),
                consolidation_max_atr=float(flag.get("consolidation_max_atr", 1.2)),
                breakout_buffer_atr=float(flag.get("breakout_buffer_atr", 0.1)),
            ),
        )

        al = dict(data.get("alerts", {}) or {})
        conditions = {
            name: ConditionConfig(
                enabled=bool(spec.get("enabled", True)),
                cooldown_minutes=(int(spec["cooldown_minutes"]) if spec.get("cooldown_minutes") is not None else None),
                level=(float(spec["level"]) if spec.get("level") is not None else None),
                buffer_ticks=float(spec.get("buffer_ticks", 0.0)),
            )
            for name, spec in (al.get("conditions", {}) or {}).items()
        }
        alerts = AlertConfig(
            default_cooldown_minutes=int(al.get("default_cooldown_minutes", 30)),
            max_alerts_per_session=int(al.get("max_alerts_per_session", 20)),
            conditions=conditions,
        )

        cl = dict(data.get("claude", {}) or {})
        claude = ClaudeConfig(
            model=str(cl.get("model", "claude-sonnet-5")),
            max_tokens=int(cl.get("max_tokens", 1200)),
            timeout_seconds=float(cl.get("timeout_seconds", 45)),
            max_retries=int(cl.get("max_retries", 2)),
            effort=str(cl.get("effort", "low")).lower(),
            report_max_tokens=int(cl.get("report_max_tokens", 4000)),
            report_effort=str(cl.get("report_effort", "medium")).lower(),
        )

        od = dict(data.get("on_demand", {}) or {})
        on_demand = OnDemandConfig(
            enabled=bool(od.get("enabled", True)),
            long_poll_timeout_seconds=float(od.get("long_poll_timeout_seconds", 25)),
            poll_retry_delay_seconds=float(od.get("poll_retry_delay_seconds", 5)),
            cooldown_seconds=float(od.get("cooldown_seconds", 60)),
            max_reports_per_day=int(od.get("max_reports_per_day", 50)),
            allow_symbol_override=bool(od.get("allow_symbol_override", True)),
            history_bars=int(od.get("history_bars", 400)),
            swing_strength=int(od.get("swing_strength", 3)),
            swing_lookback=int(od.get("swing_lookback", 120)),
            max_zones=int(od.get("max_zones", 3)),
            zone_merge_atr=float(od.get("zone_merge_atr", 0.5)),
            trend_slope_lookback=int(od.get("trend_slope_lookback", 10)),
            trend_flat_threshold_atr=float(od.get("trend_flat_threshold_atr", 0.02)),
        )

        er = dict(data.get("event_risk", {}) or {})
        event_risk = EventRiskConfig(
            enabled=bool(er.get("enabled", True)),
            currencies=tuple(er.get("currencies", ["USD"])),
            impacts=tuple(er.get("impacts", ["High"])),
            blackout_minutes_before=float(er.get("blackout_minutes_before", 15)),
            blackout_minutes_after=float(er.get("blackout_minutes_after", 15)),
            schedule_cache_minutes=float(er.get("schedule_cache_minutes", 30)),
            actual_cache_hours=float(er.get("actual_cache_hours", 6)),
            upcoming_limit=int(er.get("upcoming_limit", 8)),
            forex_factory_url=str(
                er.get(
                    "forex_factory_url",
                    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                )
            ),
        )

        nb = dict(data.get("ntbridge", {}) or {})
        ntbridge = NtBridgeConfig(
            enabled=bool(nb.get("enabled", True)),
            host=str(nb.get("host", "127.0.0.1")),
            port=int(nb.get("port", 8787)),
            database=str(nb.get("database", "data/ntbridge.sqlite3")),
            stale_factor=float(nb.get("stale_factor", 2.0)),
            symbol_map={
                str(key).upper(): str(value).upper()
                for key, value in (nb.get("symbol_map", {}) or {}).items()
            },
        )

        nt = dict(data.get("notify", {}) or {})
        notify = NotifyConfig(
            telegram_enabled=bool(nt.get("telegram_enabled", True)),
            telegram_timeout_seconds=float(nt.get("telegram_timeout_seconds", 15)),
        )

        lg = dict(data.get("logging", {}) or {})
        logging_cfg = LoggingConfig(
            level=str(lg.get("level", "INFO")).upper(),
            directory=str(lg.get("directory", "logs")),
            text_file=str(lg.get("text_file", "bot.log")),
            json_file=str(lg.get("json_file", "events.jsonl")),
            max_bytes=int(lg.get("max_bytes", 10 * 1024 * 1024)),
            backup_count=int(lg.get("backup_count", 5)),
            console=bool(lg.get("console", True)),
        )

        bt = dict(data.get("backtest", {}) or {})
        split = dict(bt.get("split", {}) or {})
        backtest = BacktestConfig(
            provider=str(bt.get("provider", "csv")).lower(),
            csv_directory=str((bt.get("csv", {}) or {}).get("directory", "data")),
            output_directory=str(bt.get("output_directory", "backtest_results")),
            commission_per_side=float(bt.get("commission_per_side", 2.50)),
            slippage_ticks_per_side=float(bt.get("slippage_ticks_per_side", 1.0)),
            split=SplitConfig(
                mode=str(split.get("mode", "fraction")).lower(),
                in_sample_fraction=float(split.get("in_sample_fraction", 0.7)),
                split_date=(split.get("split_date") or None),
            ),
        )

        cfg = Config(
            tradovate=tradovate,
            market=market,
            indicators=indicators,
            alerts=alerts,
            claude=claude,
            on_demand=on_demand,
            event_risk=event_risk,
            ntbridge=ntbridge,
            notify=notify,
            logging=logging_cfg,
            backtest=backtest,
            raw=dict(data),
        )
        cfg.validate()
        return cfg

    # -- Validierung -------------------------------------------------------

    def validate(self) -> None:
        if self.tradovate.environment not in {"demo", "live"}:
            raise ConfigError("tradovate.environment muss 'demo' oder 'live' sein.")
        if self.market.candle_interval_minutes <= 0:
            raise ConfigError("market.candle_interval_minutes muss > 0 sein.")
        if self.market.tick_size <= 0:
            raise ConfigError("market.tick_size muss > 0 sein.")
        if self.market.point_value <= 0:
            raise ConfigError("market.point_value muss > 0 sein.")
        needed = self.indicators.min_bars_required
        if self.market.candle_buffer_size < needed:
            raise ConfigError(
                f"market.candle_buffer_size ({self.market.candle_buffer_size}) ist kleiner als "
                f"der Bedarf der Indikatoren ({needed})."
            )
        # Kontraktspezifikation gegen das Instrument-Register pruefen.
        # Ein "product: MNQ" mit den Punktwerten von NQ wuerde jede
        # USD-Angabe um den Faktor 10 verfaelschen - lautlos.
        from common.instruments import UnknownInstrument, get_instrument

        try:
            instrument = get_instrument(self.market.product)
        except UnknownInstrument:
            instrument = None

        if instrument is not None:
            if abs(self.market.tick_size - instrument.tick_size) > 1e-9:
                raise ConfigError(
                    f"market.tick_size ({self.market.tick_size}) passt nicht zu "
                    f"{instrument.root} im Instrument-Register ({instrument.tick_size})."
                )
            if abs(self.market.point_value - instrument.point_value) > 1e-9:
                raise ConfigError(
                    f"market.point_value ({self.market.point_value}) passt nicht zu "
                    f"{instrument.root} im Instrument-Register ({instrument.point_value}). "
                    f"Ein Tick ist bei {instrument.root} {instrument.tick_value:.2f} USD wert."
                )

        # Vortagesmarken brauchen einen Puffer ueber zwei Sessions. Nur
        # pruefen, wenn die davon abhaengigen Alarme ueberhaupt aktiv sind.
        prev_day_conditions = [
            name
            for name in ("prev_day_high_cross", "prev_day_low_cross")
            if self.alerts.for_condition(name).enabled
        ]
        needed_for_prev_day = self.market.bars_for_previous_session
        if prev_day_conditions and self.market.candle_buffer_size < needed_for_prev_day:
            raise ConfigError(
                f"market.candle_buffer_size ({self.market.candle_buffer_size}) reicht nicht fuer "
                f"Vortageshoch/-tief: bei {self.market.candle_interval_minutes}-Minuten-Kerzen "
                f"werden {needed_for_prev_day} Kerzen benoetigt (Vorsession + laufende Session). "
                f"Sonst bleiben die Vortagesmarken leer und die Alarme "
                f"{', '.join(prev_day_conditions)} loesen nie aus. "
                "Entweder candle_buffer_size erhoehen oder diese Bedingungen abschalten."
            )
        if prev_day_conditions and self.market.warmup_bars < needed_for_prev_day:
            raise ConfigError(
                f"market.warmup_bars ({self.market.warmup_bars}) reicht nicht fuer "
                f"Vortageshoch/-tief: {needed_for_prev_day} Kerzen werden beim Start geladen "
                "muessen, sonst dauert es bis zum naechsten Handelstag, bis die Alarme "
                f"{', '.join(prev_day_conditions)} funktionieren."
            )

        swing_window = 2 * self.on_demand.swing_strength + 1
        if self.on_demand.swing_lookback < swing_window:
            raise ConfigError(
                f"on_demand.swing_lookback ({self.on_demand.swing_lookback}) muss mindestens "
                f"2*swing_strength+1 = {swing_window} betragen, sonst kann kein Swing "
                "bestaetigt werden."
            )
        if self.market.candle_buffer_size < self.on_demand.swing_lookback:
            raise ConfigError(
                f"market.candle_buffer_size ({self.market.candle_buffer_size}) ist kleiner als "
                f"on_demand.swing_lookback ({self.on_demand.swing_lookback}) - die Zonen "
                "wuerden auf weniger Kerzen beruhen als konfiguriert."
            )
        if not 0.0 < self.backtest.split.in_sample_fraction < 1.0:
            raise ConfigError("backtest.split.in_sample_fraction muss zwischen 0 und 1 liegen.")
        if self.backtest.split.mode not in {"fraction", "date"}:
            raise ConfigError("backtest.split.mode muss 'fraction' oder 'date' sein.")
        if self.backtest.split.mode == "date" and not self.backtest.split.split_date:
            raise ConfigError("backtest.split.mode='date' erfordert backtest.split.split_date.")

    def with_environment(self, environment: str) -> "Config":
        """Kopie mit ueberschriebener Tradovate-Umgebung (z.B. aus .env oder CLI)."""
        env = environment.lower()
        if env == self.tradovate.environment:
            return self
        from dataclasses import replace

        return replace(self, tradovate=replace(self.tradovate, environment=env))
