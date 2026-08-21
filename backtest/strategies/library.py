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
    FlagBreakout,
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


STRATEGY_LIBRARY: dict[str, Callable[..., RuleStrategy]] = {
    "prev_day_breakout": prev_day_breakout,
    "rsi_mean_reversion": rsi_mean_reversion,
    "flag_breakout": flag_breakout,
    "vwap_trend": vwap_trend,
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
