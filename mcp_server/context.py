"""Langlebiger Zustand des MCP-Servers.

Der Server laeuft als Dauerprozess unter Claude Desktop. Der Kerzenspeicher
wird deshalb **einmal** beim ersten Werkzeugaufruf geoeffnet und danach
wiederverwendet, statt je Aufruf eine neue SQLite-Verbindung aufzubauen.

Es gibt hier **keinen Broker-Login und keine Zugangsdaten**. Die Kerzen
liefert NinjaTrader ueber den ntbridge-Empfaenger in eine SQLite-Datei; der
Server liest ausschliesslich daraus.

Warum der Zustand einmal aufgebaut und dann gehalten wird: Das Oeffnen
der SQLite-Datei und der Aufbau der BarSource kosten je Aufruf spuerbar
Zeit, und der MCP-Server startet ohnehin schon langsam (rund 7,5 Sekunden,
fast ausschliesslich Imports).

Die urspruengliche Begruendung war eine andere - hier stand bis zum
21.08.2026 ein Tradovate-Login, das wegen der Drosselung dort nicht je
Aufruf passieren durfte. Diese Datenquelle ist verworfen und der Code
entfernt; die Entscheidung, den Zustand zu halten, traegt aber weiterhin.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from common.config import Config, Secrets
from common.logging_setup import log_event, setup_logging
from mcp_server.bars import NTBridgeBarSource
from mcp_server.calendar_provider import (
    CalendarService,
    CalendarSettings,
    ForexFactoryProvider,
    FredProvider,
)

log = logging.getLogger(__name__)

# Pfade absolut aufloesen: Claude Desktop startet den Server mit einem
# unbekannten Arbeitsverzeichnis.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class ServerContext:
    """Haelt Konfiguration, Kerzenspeicher und Kalenderdienst."""

    def __init__(
        self,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        env_path: Path | str = DEFAULT_ENV_PATH,
    ) -> None:
        self._config_path = Path(config_path)
        self._env_path = Path(env_path)
        self._config: Config | None = None
        self._secrets: Secrets | None = None
        self._store: Any = None
        self._source: NTBridgeBarSource | None = None
        self._calendar: CalendarService | None = None
        self._lock = asyncio.Lock()
        self._logging_ready = False

    # -- Konfiguration -----------------------------------------------------

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = Config.load(self._config_path)
            self._setup_logging(self._config)
        return self._config

    @property
    def secrets(self) -> Secrets:
        if self._secrets is None:
            self._secrets = Secrets.load(self._env_path)
        return self._secrets

    def _setup_logging(self, config: Config) -> None:
        if self._logging_ready:
            return
        from dataclasses import replace

        # Logverzeichnis absolut, sonst landet es im Arbeitsverzeichnis von
        # Claude Desktop. Der Konsolen-Handler schreibt auf stderr - das ist
        # der einzige Kanal, der neben dem JSON-RPC-Protokoll frei ist.
        logging_cfg = replace(
            config.logging,
            directory=str(PROJECT_ROOT / config.logging.directory),
            text_file="mcp_server.log",
            json_file="mcp_events.jsonl",
        )
        setup_logging(logging_cfg, logger_name="mcp_server")
        self._logging_ready = True

    # -- Datenquelle -------------------------------------------------------

    async def bar_source(self) -> NTBridgeBarSource:
        """Liefert die Bar-Quelle und oeffnet den Speicher beim ersten Aufruf.

        Die Daten kommen aus dem SQLite-Speicher, den der Empfaenger
        (``python -m ntbridge``) mit den Kerzen aus NinjaTrader fuellt. Es
        gibt hier keinen Broker-Login und keine Zugangsdaten - der MCP-Server
        liest nur.
        """
        async with self._lock:
            if self._source is None:
                from ntbridge.store import BarStore

                config = self.config
                database = Path(config.ntbridge.database)
                if not database.is_absolute():
                    database = PROJECT_ROOT / database

                if not database.exists():
                    raise FileNotFoundError(
                        f"Kerzendatenbank nicht gefunden: {database}\n"
                        "Bitte zuerst den Empfaenger starten (python -m ntbridge) "
                        "und in NinjaTrader ein Chart mit der ClaudeBridge oeffnen."
                    )

                self._store = BarStore(database)
                self._source = NTBridgeBarSource(self._store, config.ntbridge.symbol_map)

                log_event(
                    log,
                    "mcp.context.ready",
                    f"Kerzenspeicher geoeffnet: {database}",
                    database=str(database),
                    bars=self._store.total_bars(),
                )
            return self._source

    # -- Wirtschaftskalender ----------------------------------------------

    def calendar(self) -> CalendarService:
        """Kalenderdienst - unabhaengig vom Kerzenspeicher."""
        if self._calendar is None:
            config, secrets = self.config, self.secrets
            settings = CalendarSettings(
                currencies=tuple(config.event_risk.currencies),
                impacts=tuple(config.event_risk.impacts),
                blackout_minutes_before=config.event_risk.blackout_minutes_before,
                blackout_minutes_after=config.event_risk.blackout_minutes_after,
                schedule_cache_seconds=config.event_risk.schedule_cache_minutes * 60.0,
                actual_cache_seconds=config.event_risk.actual_cache_hours * 3600.0,
                upcoming_limit=config.event_risk.upcoming_limit,
            )
            self._calendar = CalendarService(
                ForexFactoryProvider(config.event_risk.forex_factory_url),
                FredProvider(secrets.fred_api_key),
                settings,
            )
        return self._calendar

    async def aclose(self) -> None:
        if self._store is not None:
            self._store.close()
            self._store = None
        self._source = None


__all__ = ["DEFAULT_CONFIG_PATH", "DEFAULT_ENV_PATH", "PROJECT_ROOT", "ServerContext"]
