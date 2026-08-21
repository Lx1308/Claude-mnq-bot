"""Instrument-Register: Kontraktspezifikation als Daten, nicht als Code.

Warum eigenes Modul
-------------------
``MarketConfig`` in :mod:`common.config` beschreibt genau EIN Instrument -
das reicht fuer den Live-Bot, der einen Kontrakt streamt. Der MCP-Server
beantwortet dagegen Fragen zu mehreren Instrumenten in derselben Sitzung
(MNQ und MGC) und braucht dafuer Ticksize, Punktwert, Handelszeiten und
Verfallsregel je Symbol.

Die Verfallsregel ist dabei kein Detail
---------------------------------------
:func:`live_bot.tradovate.contracts.third_friday` gilt fuer die Index-
Futures (MNQ/MES: Quartalsmonate H/M/U/Z, letzter Handelstag 3. Freitag).
Fuer COMEX-Gold ist sie **falsch**: MGC notiert G/J/M/Q/V/Z und der letzte
Handelstag ist der drittletzte Geschaeftstag des Liefermonats. Wer die
Index-Regel darauf anwendet, rollt rund zwei Wochen zu frueh - deshalb
haengt die Regel hier am Instrument und nicht im Aufloesungscode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time as dtime, timedelta
from enum import Enum
from typing import Callable

# CME-Monatscodes (identisch zu live_bot.tradovate.contracts.MONTH_CODES,
# hier nochmals als Umkehrabbildung fuer die Kontraktlisten)
MONTH_CODE_BY_NUMBER = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
MONTH_NUMBER_BY_CODE = {code: number for number, code in MONTH_CODE_BY_NUMBER.items()}

QUARTERLY = ("H", "M", "U", "Z")
GOLD_MONTHS = ("G", "J", "M", "Q", "V", "Z")


class AssetClass(str, Enum):
    EQUITY_INDEX = "equity_index"
    METAL = "metal"
    RATE = "rate"
    FX = "fx"
    VOLATILITY = "volatility"


# ---------------------------------------------------------------------------
# Verfallsregeln
# ---------------------------------------------------------------------------

def third_friday(year: int, month: int) -> date:
    """3. Freitag eines Monats - letzter Handelstag der US-Index-Futures."""
    first = date(year, month, 1)
    days_until_friday = (4 - first.weekday()) % 7   # Montag=0 ... Freitag=4
    return first + timedelta(days=days_until_friday + 14)


def third_last_business_day(year: int, month: int) -> date:
    """Drittletzter Geschaeftstag eines Monats - letzter Handelstag COMEX-Gold.

    Beruecksichtigt nur Wochenenden, keine Boersenfeiertage. Die Abweichung
    betraegt hoechstens einen Tag und wird vom Roll-Puffer
    (:data:`Instrument.roll_buffer_days`) aufgefangen. Eine echte
    Feiertagsliste waere pflegebeduerftig, ohne die Rollentscheidung
    praktisch zu veraendern.
    """
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    business_days_found = 0
    cursor = last_day
    while True:
        if cursor.weekday() < 5:   # Montag bis Freitag
            business_days_found += 1
            if business_days_found == 3:
                return cursor
        cursor -= timedelta(days=1)


ExpiryRule = Callable[[int, int], date]


# ---------------------------------------------------------------------------
# Instrument
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Instrument:
    """Vollstaendige Spezifikation eines handelbaren Kontrakts.

    Alle Uhrzeiten in Boersenzeit des Instruments (``timezone``), damit die
    Sommerzeit-Umstellung automatisch mitlaeuft.
    """

    root: str                     # "MNQ"
    name: str                     # "Micro E-mini Nasdaq-100"
    exchange: str                 # "CME" | "COMEX"
    asset_class: AssetClass

    tick_size: float              # kleinste Preisbewegung, in Preiseinheiten
    point_value: float            # USD je voller Preiseinheit (1.00 Punkt / 1.00 USD/oz)
    currency: str = "USD"

    contract_months: tuple[str, ...] = QUARTERLY
    expiry_rule: ExpiryRule = third_friday
    roll_buffer_days: int = 3     # so viele Tage vor Verfall auf den naechsten Kontrakt

    timezone: str = "America/New_York"
    rth_start: dtime = dtime(9, 30)
    rth_end: dtime = dtime(16, 15)

    # Fenster mit belastbarer Liquiditaet - ausserhalb sind Spreads breiter
    # und Levels weniger aussagekraeftig.
    liquid_start: dtime = dtime(9, 30)
    liquid_end: dtime = dtime(16, 0)

    # Duenne Mittagszone, in der Ausbrueche haeufiger scheitern.
    thin_start: dtime = dtime(12, 0)
    thin_end: dtime = dtime(14, 0)

    aliases: tuple[str, ...] = field(default_factory=tuple)

    # -- abgeleitete Groessen ---------------------------------------------

    @property
    def tick_value(self) -> float:
        """USD je Tick."""
        return self.tick_size * self.point_value

    def points_to_usd(self, points: float) -> float:
        return points * self.point_value

    def usd_to_points(self, usd: float) -> float:
        return usd / self.point_value

    def points_to_ticks(self, points: float) -> float:
        return points / self.tick_size

    def ticks_to_points(self, ticks: float) -> float:
        return ticks * self.tick_size

    def round_to_tick(self, price: float) -> float:
        """Rundet einen Preis auf ein handelbares Tick-Raster."""
        return round(round(price / self.tick_size) * self.tick_size, 10)

    def expiry_for(self, year: int, month: int) -> date:
        return self.expiry_rule(year, month)

    def describe_contract(self) -> dict[str, object]:
        """Kontraktspezifikation fuer die Snapshot-Ausgabe (mit Einheiten)."""
        return {
            "root": self.root,
            "name": self.name,
            "exchange": self.exchange,
            "tick_size_points": self.tick_size,
            "tick_value_usd": round(self.tick_value, 4),
            "point_value_usd": self.point_value,
            "currency": self.currency,
            "contract_months": list(self.contract_months),
            "rth_start_local": self.rth_start.strftime("%H:%M"),
            "rth_end_local": self.rth_end.strftime("%H:%M"),
            "timezone": self.timezone,
        }


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

_INSTRUMENTS: dict[str, Instrument] = {}


def register(instrument: Instrument) -> Instrument:
    _INSTRUMENTS[instrument.root.upper()] = instrument
    for alias in instrument.aliases:
        _INSTRUMENTS[alias.upper()] = instrument
    return instrument


# --- Aktiv gehandelt --------------------------------------------------------

MNQ = register(
    Instrument(
        root="MNQ",
        name="Micro E-mini Nasdaq-100",
        exchange="CME",
        asset_class=AssetClass.EQUITY_INDEX,
        tick_size=0.25,          # Indexpunkte
        point_value=2.0,         # USD je Indexpunkt -> Tick = 0.50 USD
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_start=dtime(9, 30),
        rth_end=dtime(16, 15),
        liquid_start=dtime(9, 30),
        liquid_end=dtime(16, 0),
        thin_start=dtime(12, 0),
        thin_end=dtime(14, 0),
    )
)

MGC = register(
    Instrument(
        root="MGC",
        name="Micro Gold",
        exchange="COMEX",
        asset_class=AssetClass.METAL,
        tick_size=0.10,          # USD je Feinunze
        point_value=10.0,        # 10 Unzen -> 1.00 USD Move = 10 USD, Tick = 1.00 USD
        contract_months=GOLD_MONTHS,
        expiry_rule=third_last_business_day,
        rth_start=dtime(8, 20),
        rth_end=dtime(13, 30),
        liquid_start=dtime(8, 20),
        liquid_end=dtime(13, 30),
        thin_start=dtime(12, 0),
        thin_end=dtime(14, 0),
    )
)

# --- Kontext / Cross-Market -------------------------------------------------

MES = register(
    Instrument(
        root="MES",
        name="Micro E-mini S&P 500",
        exchange="CME",
        asset_class=AssetClass.EQUITY_INDEX,
        tick_size=0.25,
        point_value=5.0,
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_end=dtime(16, 15),
    )
)

ES = register(
    Instrument(
        root="ES",
        name="E-mini S&P 500",
        exchange="CME",
        asset_class=AssetClass.EQUITY_INDEX,
        tick_size=0.25,
        point_value=50.0,
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_end=dtime(16, 15),
    )
)

NQ = register(
    Instrument(
        root="NQ",
        name="E-mini Nasdaq-100",
        exchange="CME",
        asset_class=AssetClass.EQUITY_INDEX,
        tick_size=0.25,
        point_value=20.0,
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_end=dtime(16, 15),
    )
)

SIL = register(
    Instrument(
        root="SIL",
        name="Micro Silver",
        exchange="COMEX",
        asset_class=AssetClass.METAL,
        tick_size=0.005,
        point_value=1000.0,      # 1000 Unzen
        contract_months=("H", "K", "N", "U", "Z"),
        expiry_rule=third_last_business_day,
        rth_start=dtime(8, 25),
        rth_end=dtime(13, 25),
    )
)

ZN = register(
    Instrument(
        root="ZN",
        name="10-Year T-Note (Zinsproxy)",
        exchange="CBOT",
        asset_class=AssetClass.RATE,
        tick_size=1.0 / 64.0,
        point_value=1000.0,
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_start=dtime(8, 20),
        rth_end=dtime(15, 0),
    )
)

M6E = register(
    Instrument(
        root="M6E",
        name="Micro EUR/USD (Dollarproxy)",
        exchange="CME",
        asset_class=AssetClass.FX,
        tick_size=0.0001,
        point_value=12500.0,
        contract_months=QUARTERLY,
        expiry_rule=third_friday,
        rth_start=dtime(8, 20),
        rth_end=dtime(15, 0),
        aliases=("6E",),
    )
)


class UnknownInstrument(KeyError):
    """Symbol ist im Register nicht hinterlegt."""


def get_instrument(symbol: str) -> Instrument:
    """Loest ein Symbol auf - akzeptiert Root ("MNQ") und Kontrakt ("MNQZ5").

    Die laengsten Roots werden zuerst geprueft, damit "MNQ" nicht faelschlich
    als "MN" + Monatscode gelesen wird.
    """
    key = (symbol or "").strip().upper()
    if not key:
        raise UnknownInstrument("Leeres Symbol.")
    if key in _INSTRUMENTS:
        return _INSTRUMENTS[key]

    for root in sorted(_INSTRUMENTS, key=len, reverse=True):
        if not key.startswith(root):
            continue
        suffix = key[len(root):]
        # Rest muss wie ein Kontraktsuffix aussehen: Monatscode + 1-2 Ziffern
        if len(suffix) in (2, 3) and suffix[0] in MONTH_NUMBER_BY_CODE and suffix[1:].isdigit():
            return _INSTRUMENTS[root]

    raise UnknownInstrument(
        f"Unbekanntes Symbol {symbol!r}. Bekannt: {', '.join(sorted(known_roots()))}"
    )


def known_roots() -> list[str]:
    """Alle registrierten Roots (ohne Aliase)."""
    return sorted({instrument.root for instrument in _INSTRUMENTS.values()})


def all_instruments() -> list[Instrument]:
    return sorted({instrument.root: instrument for instrument in _INSTRUMENTS.values()}.values(),
                  key=lambda item: item.root)


__all__ = [
    "AssetClass",
    "GOLD_MONTHS",
    "Instrument",
    "MGC",
    "MNQ",
    "QUARTERLY",
    "UnknownInstrument",
    "all_instruments",
    "get_instrument",
    "known_roots",
    "register",
    "third_friday",
    "third_last_business_day",
]
