"""Bar-Beschaffung fuer den MCP-Server.

Die Schnittstelle :class:`BarSource` ist bewusst so geschnitten, dass ein
spaeterer lokaler Bar-Cache **ohne Umbau** dahinterpasst: er implementiert
dieselbe Methode, beantwortet Treffer aus der Datei und delegiert Fehltreffer
an :class:`TradovateBarSource`.

Warum ein Aufruf je Timeframe statt Hochsampeln aus 1m
------------------------------------------------------
Ein EMA200 auf dem Stundenchart braucht 200 Stundenkerzen, also 12.000
Minutenkerzen - deutlich mehr, als ``md/getChart`` in einer Antwort liefert.
Wer aus zu wenig 1m-Daten hochsampelt, bekommt eine EMA200, die auf halber
Strecke abbricht und trotzdem wie ein Wert aussieht. Deshalb holt jeder
Timeframe seine eigenen Bars mit eigener Warmlaufphase - alle ueber
**dieselbe** WebSocket-Verbindung.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

import pandas as pd

from common.config import Config
from common.instruments import Instrument, get_instrument
from common.logging_setup import log_event
from live_bot.market.candles import candles_from_tradovate_bars
from live_bot.tradovate.auth import TokenManager
from live_bot.tradovate.contracts import Contract, resolve_contract
from live_bot.tradovate.md_socket import MarketDataSocket
from live_bot.tradovate.rest import TradovateRestClient

log = logging.getLogger(__name__)

# Unterstuetzte Timeframes und ihre Laenge in Minuten. "1d" ist ein
# Sonderfall und wird von Tradovate als DailyBar geliefert.
TIMEFRAME_MINUTES: dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
DAILY = "1d"
ALL_TIMEFRAMES = (*TIMEFRAME_MINUTES, DAILY)

# Wie viele Bars je Timeframe geholt werden. Bemessen an EMA200 plus
# Swing-Lookback, bei 5m/15m zusaetzlich so, dass zwei Handelssessions
# hineinpassen (Voraussetzung fuer Vortageshoch/-tief).
DEFAULT_BAR_COUNTS: dict[str, int] = {
    "1m": 1500,
    "5m": 800,     # ~2.8 Sessions
    "15m": 500,    # ~5 Sessions
    "1h": 300,
    DAILY: 120,
}


class BarSourceError(RuntimeError):
    """Bars konnten nicht beschafft werden."""


@dataclass
class BarSet:
    """Bars eines Timeframes samt Herkunftsangaben."""

    timeframe: str
    frame: pd.DataFrame
    source: str
    contract: str
    requested_bars: int

    @property
    def bars_available(self) -> int:
        return len(self.frame)

    @property
    def newest(self) -> datetime | None:
        return self.frame.index[-1].to_pydatetime() if not self.frame.empty else None

    @property
    def oldest(self) -> datetime | None:
        return self.frame.index[0].to_pydatetime() if not self.frame.empty else None

    @property
    def has_flow(self) -> bool:
        """Liefert die Datenquelle Bid-/Ask-Volumen?

        Ueber die NinjaTrader-Bridge grundsaetzlich nein: dafuer braeuchte es
        das kostenpflichtige Add-on "Order Flow +". Das Feld bleibt deshalb
        dauerhaft False und das Delta im Snapshot null mit Begruendung.
        """
        if "bid_volume" not in self.frame.columns:
            return False
        return float(
            (self.frame["bid_volume"] + self.frame["ask_volume"]).sum()
        ) > 0.0

    @property
    def timeframe_minutes(self) -> int:
        """Laenge eines Bars in Minuten (Tageskerzen: Sessionlaenge 23 h)."""
        if self.timeframe == DAILY:
            return 23 * 60
        return TIMEFRAME_MINUTES.get(self.timeframe, 1)

    def age_seconds(self, now: datetime | None = None) -> float | None:
        if self.newest is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - self.newest).total_seconds()

    def is_stale(self, now: datetime | None = None, factor: float = 2.0) -> bool:
        """Ist der juengste Bar aelter als ``factor`` mal die Bar-Laenge?

        Bei laufender NinjaTrader-Instanz kommt jede Minute eine neue
        1m-Kerze. Bleibt sie deutlich laenger aus, ist mit hoher
        Wahrscheinlichkeit das Chart geschlossen oder die Plattform beendet -
        und der Snapshot beschreibt dann einen veralteten Markt, ohne dass
        man es sieht. Genau dafuer ist dieses Flag da.

        Achtung: ausserhalb der Handelszeiten ist "veraltet" normal. Der
        Snapshot weist deshalb zusaetzlich den Globex-Zustand aus.
        """
        age = self.age_seconds(now)
        if age is None:
            return True
        return age > factor * self.timeframe_minutes * 60.0


@dataclass
class LoadedBars:
    """Ergebnis eines Ladevorgangs ueber mehrere Timeframes."""

    symbol: str
    contract: Contract
    instrument: Instrument
    sets: dict[str, BarSet] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def __getitem__(self, timeframe: str) -> BarSet:
        return self.sets[timeframe]

    def get(self, timeframe: str) -> BarSet | None:
        return self.sets.get(timeframe)


class BarSource(Protocol):
    """Schnittstelle fuer Bar-Beschaffung.

    Ein spaeterer Cache implementiert genau diese Methode.
    """

    async def load(
        self,
        symbol: str,
        timeframes: list[str],
        *,
        bar_counts: dict[str, int] | None = None,
    ) -> LoadedBars:
        ...


class TradovateBarSource:
    """Holt Bars ueber ``md/getChart``.

    Der :class:`TokenManager` ist langlebig und wird ueber mehrere Anfragen
    wiederverwendet - jeder Aufruf einen neuen Login zu machen waere gegen
    Tradovates Drosselung.
    """

    name = "tradovate/md.getChart"

    def __init__(self, config: Config, tokens: TokenManager) -> None:
        self._config = config
        self._tokens = tokens
        self._contract_cache: dict[str, Contract] = {}

    async def resolve(self, symbol: str) -> tuple[Instrument, Contract]:
        """Loest Produkt-Root oder Kontraktnamen zum aktiven Kontrakt auf."""
        instrument = get_instrument(symbol)
        key = symbol.upper()

        cached = self._contract_cache.get(key)
        if cached is not None:
            return instrument, cached

        rest = TradovateRestClient(self._config.tradovate, self._tokens)
        looks_like_contract = (
            len(key) > len(instrument.root)
            and key[len(instrument.root):][:1].isalpha()
            and key[len(instrument.root) + 1:].isdigit()
        )
        contract = await resolve_contract(
            rest,
            product=instrument.root,
            override=key if looks_like_contract else None,
        )
        self._contract_cache[key] = contract
        return instrument, contract

    async def load(
        self,
        symbol: str,
        timeframes: list[str],
        *,
        bar_counts: dict[str, int] | None = None,
    ) -> LoadedBars:
        counts = {**DEFAULT_BAR_COUNTS, **(bar_counts or {})}
        instrument, contract = await self.resolve(symbol)

        result = LoadedBars(symbol=symbol.upper(), contract=contract, instrument=instrument)

        md_token = await self._tokens.get_md_access_token()
        socket = MarketDataSocket(
            self._config.tradovate.market_data_url,
            md_token,
            heartbeat_interval=self._config.tradovate.websocket.heartbeat_interval_seconds,
        )

        try:
            await socket.connect()
            for timeframe in timeframes:
                if timeframe not in ALL_TIMEFRAMES:
                    result.errors[timeframe] = f"Unbekannter Timeframe {timeframe!r}"
                    continue
                try:
                    result.sets[timeframe] = await self._load_one(
                        socket, contract.name, timeframe, counts[timeframe]
                    )
                except Exception as exc:  # noqa: BLE001 - ein TF darf den Rest nicht kippen
                    log_event(
                        log,
                        "mcp.bars.timeframe_failed",
                        f"Timeframe {timeframe} fuer {contract.name} fehlgeschlagen: {exc}",
                        level=logging.WARNING,
                        timeframe=timeframe,
                        error=str(exc),
                    )
                    result.errors[timeframe] = str(exc)
        finally:
            await socket.close()

        if not result.sets:
            raise BarSourceError(
                f"Keine Bars fuer {contract.name} erhalten. Fehler: {result.errors}"
            )
        return result

    async def _load_one(
        self, socket: MarketDataSocket, contract_name: str, timeframe: str, bars: int
    ) -> BarSet:
        if timeframe == DAILY:
            raw = await socket.fetch_history(
                contract_name, interval_minutes=1, bars=bars, chart_type="daily"
            )
            interval_minutes = 1440
        else:
            interval_minutes = TIMEFRAME_MINUTES[timeframe]
            raw = await socket.fetch_history(
                contract_name, interval_minutes=interval_minutes, bars=bars
            )

        candles = candles_from_tradovate_bars(raw, interval_minutes)
        # Die letzte Kerze laeuft noch - fuer eine Analyse unbrauchbar.
        candles = candles[:-1]
        if not candles:
            raise BarSourceError(f"Keine verwertbaren Bars fuer {timeframe}")

        frame = pd.DataFrame(
            [candle.as_row(include_flow=True) for candle in candles],
            index=pd.DatetimeIndex([candle.start for candle in candles], tz="UTC"),
        )
        return BarSet(
            timeframe=timeframe,
            frame=frame,
            source=self.name,
            contract=contract_name,
            requested_bars=bars,
        )


class NTBridgeBarSource:
    """Liest Kerzen aus dem SQLite-Speicher der NinjaScript-Bridge.

    Erfuellt dieselbe Schnittstelle wie :class:`TradovateBarSource`; fuer
    :mod:`mcp_server.snapshot` ist der Unterschied nicht sichtbar.

    Anders als bei Tradovate gibt es hier keine Kontraktaufloesung: welcher
    Kontrakt gehandelt wird, entscheidet der Chart in NinjaTrader. Die Bridge
    meldet den Namen mit (z.B. "MNQ 12-25"), er wird uebernommen und nicht
    nachgerechnet.
    """

    name = "ninjatrader"

    def __init__(self, store: "BarStoreProtocol", symbol_map: dict[str, str] | None = None) -> None:
        self._store = store
        # Interne Roots auf abweichende NinjaTrader-Namen abbilden, falls der
        # Broker andere Bezeichner verwendet.
        self._symbol_map = {
            key.upper(): value.upper() for key, value in (symbol_map or {}).items()
        }

    def _resolve_root(self, symbol: str) -> tuple[Instrument, str]:
        instrument = get_instrument(symbol)
        stored_root = self._symbol_map.get(instrument.root, instrument.root)
        return instrument, stored_root

    async def load(
        self,
        symbol: str,
        timeframes: list[str],
        *,
        bar_counts: dict[str, int] | None = None,
    ) -> LoadedBars:
        counts = {**DEFAULT_BAR_COUNTS, **(bar_counts or {})}
        instrument, stored_root = self._resolve_root(symbol)

        contract_name = None
        sets: dict[str, BarSet] = {}
        errors: dict[str, str] = {}

        for timeframe in timeframes:
            if timeframe not in ALL_TIMEFRAMES:
                errors[timeframe] = f"Unbekannter Timeframe {timeframe!r}"
                continue

            frame = self._store.load_frame(stored_root, timeframe, limit=counts[timeframe])
            if frame.empty:
                errors[timeframe] = (
                    f"Keine Kerzen fuer {stored_root}/{timeframe} im Speicher. "
                    "Laeuft in NinjaTrader ein Chart mit der ClaudeBridge fuer "
                    "dieses Instrument und diesen Timeframe?"
                )
                continue

            if contract_name is None:
                contract_name = self._store.nt_instrument(stored_root, timeframe)

            sets[timeframe] = BarSet(
                timeframe=timeframe,
                frame=frame,
                source=self.name,
                contract=contract_name or stored_root,
                requested_bars=counts[timeframe],
            )

        if not sets:
            raise BarSourceError(
                f"Keine Kerzen fuer {symbol} im Speicher. Details: {errors}"
            )

        return LoadedBars(
            symbol=instrument.root,
            contract=Contract(id=0, name=contract_name or stored_root, expiry=None),
            instrument=instrument,
            sets=sets,
            errors=errors,
        )


class BarStoreProtocol(Protocol):
    """Minimale Sicht auf den Speicher - haelt bars.py frei von ntbridge."""

    def load_frame(self, instrument: str, timeframe: str, limit: int | None = None) -> pd.DataFrame:
        ...

    def nt_instrument(self, instrument: str, timeframe: str) -> str | None:
        ...


__all__ = [
    "ALL_TIMEFRAMES",
    "DAILY",
    "DEFAULT_BAR_COUNTS",
    "TIMEFRAME_MINUTES",
    "BarSet",
    "BarSource",
    "BarSourceError",
    "BarStoreProtocol",
    "LoadedBars",
    "NTBridgeBarSource",
    "TradovateBarSource",
]
