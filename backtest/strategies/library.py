"""Fertige Strategien als Bausteine - alle rein aus Regel-Objekten gebaut.

Jede Fabrikfunktion nimmt nur Parameter entgegen und liefert eine
:class:`RuleStrategy`. Parametervarianten sind damit reine Daten und
lassen sich ohne Code-Aenderung vergleichen:

    build_strategy("prev_day_breakout", rsi_max=65, stop_loss_atr=1.5)
"""

from __future__ import annotations

from datetime import time as dtime
from typing import Any, Callable

from backtest.strategies.base import (
    ColumnAbove,
    ColumnBelow,
    CrossesAbove,
    CrossesBelow,
    DeviationReentry,
    FlagBreakout,
    IstGesetzt,
    RuleStrategy,
    SessionTimeWindow,
)


def prev_day_breakout(
    *,
    rsi_max: float = 70.0,
    rsi_min: float = 30.0,
    buffer_points: float = 1.0,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 120,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Ausbruch ueber das Vortageshoch (bzw. unter das Vortagestief).

    Der RSI-Filter soll verhindern, dass in eine bereits ueberdehnte
    Bewegung hinein eingestiegen wird.
    """
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = (
        CrossesAbove("close", "prev_session_high", buffer=buffer_points)
        & ColumnBelow("rsi", rsi_max)
        & window
    )
    long_exit = CrossesBelow("close", "vwap")

    short_entry = None
    short_exit = None
    if trade_short:
        short_entry = (
            CrossesBelow("close", "prev_session_low", buffer=buffer_points)
            & ColumnAbove("rsi", rsi_min)
            & window
        )
        short_exit = CrossesAbove("close", "vwap")

    return RuleStrategy(
        name="prev_day_breakout",
        long_entry=long_entry,
        long_exit=long_exit,
        short_entry=short_entry,
        short_exit=short_exit,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "rsi_max": rsi_max,
            "rsi_min": rsi_min,
            "buffer_points": buffer_points,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def rsi_mean_reversion(
    *,
    oversold: float = 30.0,
    overbought: float = 70.0,
    exit_level: float = 50.0,
    stop_loss_atr: float | None = 2.0,
    take_profit_atr: float | None = None,
    max_bars_in_trade: int | None = 60,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Rueckkehr zur Mitte: Einstieg beim Verlassen der Extremzone."""
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = CrossesAbove("rsi", oversold) & window
    long_exit = CrossesAbove("rsi", exit_level)

    short_entry = None
    short_exit = None
    if trade_short:
        short_entry = CrossesBelow("rsi", overbought) & window
        short_exit = CrossesBelow("rsi", exit_level)

    return RuleStrategy(
        name="rsi_mean_reversion",
        long_entry=long_entry,
        long_exit=long_exit,
        short_entry=short_entry,
        short_exit=short_exit,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "oversold": oversold,
            "overbought": overbought,
            "exit_level": exit_level,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def flag_breakout(
    *,
    require_trend: bool = True,
    stop_loss_atr: float | None = 1.2,
    take_profit_atr: float | None = 2.5,
    max_bars_in_trade: int | None = 90,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Ausbruch aus der Konsolidierung, optional mit SMA-Trendfilter."""
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = FlagBreakout("up") & window
    short_entry = FlagBreakout("down") & window
    if require_trend:
        long_entry = long_entry & ColumnAbove("sma_fast", "sma_slow")
        short_entry = short_entry & ColumnBelow("sma_fast", "sma_slow")

    return RuleStrategy(
        name="flag_breakout",
        long_entry=long_entry,
        long_exit=CrossesBelow("close", "sma_fast"),
        short_entry=short_entry if trade_short else None,
        short_exit=CrossesAbove("close", "sma_fast") if trade_short else None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "require_trend": require_trend,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def vwap_trend(
    *,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 120,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Trendfolge: VWAP-Kreuzung in Richtung der SMA-Struktur."""
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    return RuleStrategy(
        name="vwap_trend",
        long_entry=CrossesAbove("close", "vwap") & ColumnAbove("sma_fast", "sma_slow") & window,
        long_exit=CrossesBelow("close", "vwap"),
        short_entry=(
            CrossesBelow("close", "vwap") & ColumnBelow("sma_fast", "sma_slow") & window
            if trade_short
            else None
        ),
        short_exit=CrossesAbove("close", "vwap") if trade_short else None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def ib_breakout(
    *,
    buffer_points: float = 1.0,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 120,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Bruch der Initial Balance (erste RTH-Stunde) nach oben bzw. unten.

    Braucht die Spalten ``ib_high``/``ib_low`` aus
    ``common.levels.initial_balance_per_session``. Die sind waehrend des
    laufenden IB-Fensters NaN; damit kann diese Strategie konstruktions-
    bedingt nicht ausloesen, bevor die Initial Balance ueberhaupt feststeht.

    Die Kreuzungsregeln verwerfen NaN, also entsteht auch auf der ersten
    Kerze nach Fensterende kein Scheinsignal aus dem Uebergang NaN -> Wert.
    """
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = CrossesAbove("close", "ib_high", buffer=buffer_points) & window
    short_entry = CrossesBelow("close", "ib_low", buffer=buffer_points) & window

    return RuleStrategy(
        name="ib_breakout",
        long_entry=long_entry,
        long_exit=CrossesBelow("close", "vwap"),
        short_entry=short_entry if trade_short else None,
        short_exit=CrossesAbove("close", "vwap") if trade_short else None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "buffer_points": buffer_points,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def vwap_reversion(
    *,
    deviation_atr: float = 1.5,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 2.0,
    max_bars_in_trade: int | None = 60,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Rueckkehr zum VWAP nach weiter Abweichung.

    Ausdruecklich NICHT dasselbe wie :func:`vwap_trend`: dort ist die
    VWAP-Kreuzung in Trendrichtung das Signal, hier die Umkehr aus einer
    Uebertreibung zurueck zum Anker. Beide Setups nutzen dieselbe
    VWAP-Spalte, meinen aber gegenlaeufige Marktzustaende.

    Das Signal ist der **Uebertritt** zurueck ins Band, nicht der Zustand
    "unterwegs zurueck": sonst feuerte es auf jeder Kerze der Rueckkehr
    erneut und dieselbe Bewegung stuende vielfach in der Statistik. Siehe
    :class:`DeviationReentry`.
    """
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = DeviationReentry("close", "vwap", deviation_atr, "below") & window
    short_entry = DeviationReentry("close", "vwap", deviation_atr, "above") & window

    return RuleStrategy(
        name="vwap_reversion",
        long_entry=long_entry,
        long_exit=ColumnAbove("close", "vwap"),
        short_entry=short_entry if trade_short else None,
        short_exit=ColumnBelow("close", "vwap") if trade_short else None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "deviation_atr": deviation_atr,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )



def power_hour_vwap(
    *,
    deviation_atr: float = 2.0,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 60,
    trade_short: bool = True,
    session_start: str = "15:00",
    session_end: str = "15:55",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )
    long_entry = DeviationReentry("close", "vwap", deviation_atr, "below") & window
    short_entry = DeviationReentry("close", "vwap", deviation_atr, "above") & window

    return RuleStrategy(
        name="power_hour_vwap",
        long_entry=long_entry,
        long_exit=ColumnAbove("close", "vwap"),
        short_entry=short_entry if trade_short else None,
        short_exit=ColumnBelow("close", "vwap") if trade_short else None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "deviation_atr": deviation_atr,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )

def doppelboden_bestaetigt(
    *,
    min_konfidenz: float = 0.0,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 60,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Das "W": Einstieg, sobald das zweite Tief bestaetigt ist.

    **Der frueheste ehrlich handelbare Zeitpunkt.** Nicht "am zweiten Tief" -
    ein Swing-Tief ist an seiner eigenen Kerze nicht erkennbar, es wird erst
    ``strength`` Kerzen spaeter bestaetigt (siehe
    ``common/muster_serie.py``). Ein Backtest, der am Tief selbst einsteigt,
    handelt mit Wissen aus der Zukunft.

    Das ist die fruehe, guenstige, unbestaetigte Variante. Die Gegenprobe ist
    :func:`doppelboden_nackenbruch` - dort wird auf die Bestaetigung durch
    den Nackenlinienbruch gewartet, zu einem schlechteren Kurs. Welche der
    beiden traegt, ist eine Messfrage.

    Das Doppeltop ist die Short-Entsprechung, gleiche Logik gespiegelt.
    """
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = IstGesetzt("w_erkannt") & window
    short_entry = IstGesetzt("m_erkannt") & window
    if min_konfidenz > 0:
        long_entry = long_entry & ColumnAbove("w_konfidenz", min_konfidenz)
        short_entry = short_entry & ColumnAbove("m_konfidenz", min_konfidenz)

    return RuleStrategy(
        name="doppelboden_bestaetigt",
        long_entry=long_entry,
        # Ausstieg ueber die Risikoparameter (Stop/Ziel/Zeit). Eine eigene
        # Ausstiegsregel waere eine zweite Hypothese im selben Test - Ein-
        # und Ausstieg werden getrennt untersucht (MASTERPLAN G).
        long_exit=None,
        short_entry=short_entry if trade_short else None,
        short_exit=None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "min_konfidenz": min_konfidenz,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


def doppelboden_nackenbruch(
    *,
    min_konfidenz: float = 0.0,
    stop_loss_atr: float | None = 1.5,
    take_profit_atr: float | None = 3.0,
    max_bars_in_trade: int | None = 60,
    trade_short: bool = True,
    session_start: str = "09:30",
    session_end: str = "15:45",
    timezone: str = "America/New_York",
) -> RuleStrategy:
    """Das "W", aber erst beim Bruch der Nackenlinie.

    Die klassische Lehrbuchvariante - ``detect_double_top_bottom`` sagt es
    selbst: "Bestaetigt gilt das Muster erst mit Schlusskurs jenseits der
    Nackenlinie."

    Spaeter als :func:`doppelboden_bestaetigt` und damit zu einem
    schlechteren Kurs, dafuer mit Bestaetigung. Die beiden gegeneinander zu
    rechnen ist der eigentliche Punkt: dieselbe Mustererkennung, ein
    einziger Unterschied im Einstieg.
    """
    window = SessionTimeWindow(
        _parse_time(session_start), _parse_time(session_end), timezone
    )

    long_entry = IstGesetzt("w_nackenbruch") & window
    short_entry = IstGesetzt("m_nackenbruch") & window
    if min_konfidenz > 0:
        long_entry = long_entry & ColumnAbove("w_konfidenz", min_konfidenz)
        short_entry = short_entry & ColumnAbove("m_konfidenz", min_konfidenz)

    return RuleStrategy(
        name="doppelboden_nackenbruch",
        long_entry=long_entry,
        long_exit=None,
        short_entry=short_entry if trade_short else None,
        short_exit=None,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        max_bars_in_trade=max_bars_in_trade,
        params={
            "min_konfidenz": min_konfidenz,
            "stop_loss_atr": stop_loss_atr,
            "take_profit_atr": take_profit_atr,
            "max_bars_in_trade": max_bars_in_trade,
            "trade_short": trade_short,
        },
    )


STRATEGY_LIBRARY: dict[str, Callable[..., RuleStrategy]] = {
    'power_hour_vwap': power_hour_vwap,
    "prev_day_breakout": prev_day_breakout,
    "rsi_mean_reversion": rsi_mean_reversion,
    "flag_breakout": flag_breakout,
    "vwap_trend": vwap_trend,
    "ib_breakout": ib_breakout,
    "vwap_reversion": vwap_reversion,
    "doppelboden_bestaetigt": doppelboden_bestaetigt,
    "doppelboden_nackenbruch": doppelboden_nackenbruch,
}


def build_strategy(name: str, **params: Any) -> RuleStrategy:
    """Erzeugt eine Strategie aus der Bibliothek."""
    factory = STRATEGY_LIBRARY.get(name)
    if factory is None:
        raise KeyError(
            f"Unbekannte Strategie {name!r}. Verfuegbar: {', '.join(sorted(STRATEGY_LIBRARY))}"
        )
    strategy = factory(**params)
    if params:
        # Variantenname macht Vergleichstabellen lesbar.
        suffix = ",".join(f"{key}={value}" for key, value in sorted(params.items()))
        object.__setattr__(strategy, "name", f"{name}[{suffix}]")
    return strategy


def _parse_time(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))




