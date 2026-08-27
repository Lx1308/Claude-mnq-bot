"""Bar-Beschaffung fuer den MCP-Server.

Einzige Quelle ist :class:`NTBridgeBarSource`. Sie liest die Kerzen aus der
SQLite-Datei, die der ntbridge-Empfaenger mit den Daten aus NinjaTrader
fuellt. **Kein Netzaufruf, kein Login, keine Zugangsdaten.**

Historie: Hier stand bis 21.08.2026 zusaetzlich eine ``TradovateBarSource``,
die Bars ueber ``md/getChart`` holte. Tradovate wurde als Datenquelle
verworfen (Live-Konto mit Mindesteinlage plus kostenpflichtiges API-Add-on
erforderlich) und die Klasse entfernt. Sie hatte einen Nebeneffekt, der
teurer war als ihr Nutzen: ueber sie zog dieses Modul fuenf ``live_bot``-
Module in den Importpfad des MCP-Servers, obwohl er sie nie brauchte. Jede
Abhaengigkeit, die dort hinzugekommen waere, haette den Server beim Start
mitreissen koennen.

Die Schnittstelle :class:`BarSource` ist geblieben. Sie hat sich beim
Wechsel bewaehrt: beide Quellen erfuellten dasselbe ``load()``-Protokoll,
weshalb ``snapshot.py`` strukturell unveraendert blieb.

Warum ein Satz Bars je Timeframe statt Hochsampeln aus 1m
---------------------------------------------------------
Ein EMA200 auf dem Stundenchart braucht 200 Stundenkerzen, also 12.000
Minutenkerzen. Wer aus zu wenig 1m-Daten hochsampelt, bekommt eine EMA200,
die auf halber Strecke abbricht und trotzdem wie ein Wert aussieht. Deshalb
liefert NinjaTrader jeden Timeframe als eigene Datenserie, und jeder bringt
seine eigene Warmlaufphase mit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

# pandas wird hier NUR in Typannotationen gebraucht. Dank
# ``from __future__ import annotations`` sind die Zeichenketten und loesen
# keinen Import aus.
#
# Warum das zaehlt: der MCP-Server startet bei JEDEM Client neu. Auf kaltem
# Dateisystem-Cache war pandas mit rund 18 von 30 Sekunden der groesste
# Einzelposten des Startvorgangs - gebraucht wird es aber erst beim ersten
# Werkzeugaufruf, nicht fuer den Handshake.
#
# Warm gemessen faellt das kaum ins Gewicht (0,8 s). Der eigentliche
# Zeitfresser ist dann die Bibliothek ``mcp.server`` selbst, die ihren
# Client-Code mitlaedt - daran laesst sich von hier aus nichts aendern.
if TYPE_CHECKING:  # pragma: no cover - nur fuer Typpruefer
    import pandas as pd

from common.config import Config
from common.instruments import Instrument, get_instrument
from common.logging_setup import log_event
from common.contracts import Contract

log = logging.getLogger(__name__)

# Unterstuetzte Timeframes und ihre Laenge in Minuten. "1d" ist ein
# Sonderfall: NinjaTrader liefert Tageskerzen ueber BarsPeriodType.Day,
# also gemaess Handelszeiten-Vorlage des Kontrakts - nicht als 1440 Minuten.
TIMEFRAME_MINUTES: dict[str, int] = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
DAILY = "1d"
ALL_TIMEFRAMES = (*TIMEFRAME_MINUTES, DAILY)

# Wie viele Bars je Timeframe geholt werden. Bemessen an EMA200 plus
# Swing-Lookback, bei 5m/15m zusaetzlich so, dass zwei Handelssessions
# hineinpassen (Voraussetzung fuer Vortageshoch/-tief).
# Wie viele Kerzen der Snapshot ausgibt. Steht hier und nicht in
# snapshot.py, weil server.py sie als Vorgabewert einer Signatur braucht -
# und ein Import von snapshot.py zoege pandas in den Startvorgang.
DEFAULT_BARS_IN_OUTPUT = 20

DEFAULT_BAR_COUNTS: dict[str, int] = {
    "1m": 1500,
    "5m": 800,     # ~2.8 Sessions
    "15m": 500,    # ~5 Sessions
    "1h": 300,
    "4h": 200,
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


class NTBridgeBarSource:
    """Liest Kerzen aus dem SQLite-Speicher der NinjaScript-Bridge.

    Erfuellt das :class:`BarSource`-Protokoll; fuer
    :mod:`mcp_server.snapshot` ist die Herkunft der Kerzen nicht sichtbar.

    Es gibt hier keine Kontraktaufloesung ueber einen Broker: welcher
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
    "DEFAULT_BARS_IN_OUTPUT",
    "DAILY",
    "DEFAULT_BAR_COUNTS",
    "TIMEFRAME_MINUTES",
    "BarSet",
    "BarSource",
    "BarSourceError",
    "BarStoreProtocol",
    "LoadedBars",
    "NTBridgeBarSource",
]
