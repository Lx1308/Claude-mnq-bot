"""Auswertung der Alarm-Bedingungen.

Alle Bedingungen sind *Flankenerkennungen*: sie vergleichen den Snapshot der
gerade geschlossenen Kerze mit dem der vorherigen. Damit feuert eine
Bedingung genau beim Uebergang und nicht dauerhaft, solange ein Zustand
anhaelt. Das Rate-Limiting (:mod:`live_bot.alerts.cooldown`) kommt als
zweite Bremse obendrauf.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from common.config import AlertConfig, MarketConfig
from live_bot.market.state import MarketSnapshot

# Bedingungs-Schluessel - muessen zu den Namen in der config.yaml passen.
PREV_DAY_HIGH_CROSS = "prev_day_high_cross"
PREV_DAY_LOW_CROSS = "prev_day_low_cross"
RSI_EXIT_OVERBOUGHT = "rsi_exit_overbought"
RSI_EXIT_OVERSOLD = "rsi_exit_oversold"
FLAG_BREAKOUT = "flag_breakout"

ALL_CONDITIONS = (
    PREV_DAY_HIGH_CROSS,
    PREV_DAY_LOW_CROSS,
    RSI_EXIT_OVERBOUGHT,
    RSI_EXIT_OVERSOLD,
    FLAG_BREAKOUT,
)


@dataclass(frozen=True)
class Alert:
    """Ein ausgeloestes Ereignis - noch ohne Claude-Kommentar."""

    condition: str
    headline: str
    direction: str  # "up" | "down" | "neutral"
    details: dict[str, Any] = field(default_factory=dict)


class ConditionEvaluator:
    """Prueft alle aktivierten Bedingungen fuer eine geschlossene Kerze."""

    def __init__(self, alert_cfg: AlertConfig, market_cfg: MarketConfig) -> None:
        self._alerts = alert_cfg
        self._market = market_cfg
        self._checks: dict[str, Callable[[MarketSnapshot, MarketSnapshot], Alert | None]] = {
            PREV_DAY_HIGH_CROSS: self._check_prev_day_high,
            PREV_DAY_LOW_CROSS: self._check_prev_day_low,
            RSI_EXIT_OVERBOUGHT: self._check_rsi_overbought_exit,
            RSI_EXIT_OVERSOLD: self._check_rsi_oversold_exit,
            FLAG_BREAKOUT: self._check_flag_breakout,
        }

    def evaluate(
        self, previous: MarketSnapshot | None, current: MarketSnapshot
    ) -> list[Alert]:
        """Liefert alle Bedingungen, die mit dieser Kerze ausgeloest haben."""
        if previous is None or not current.indicators_ready:
            return []

        triggered: list[Alert] = []
        for name, check in self._checks.items():
            if not self._alerts.for_condition(name).enabled:
                continue
            alert = check(previous, current)
            if alert is not None:
                triggered.append(alert)
        return triggered

    # -- Einzelne Bedingungen ----------------------------------------------

    def _buffer(self, condition: str) -> float:
        """Puffer in Preispunkten, damit Tick-Rauschen keinen Alarm ausloest."""
        return self._alerts.for_condition(condition).buffer_ticks * self._market.tick_size

    def _check_prev_day_high(
        self, previous: MarketSnapshot, current: MarketSnapshot
    ) -> Alert | None:
        level = current.prev_session_high
        if level is None or previous.prev_session_high is None:
            return None

        buffer = self._buffer(PREV_DAY_HIGH_CROSS)
        crossed = previous.close <= level and current.close > level + buffer
        if not crossed:
            return None

        return Alert(
            condition=PREV_DAY_HIGH_CROSS,
            headline=f"{current.symbol}: Vortageshoch {level:.2f} von unten gekreuzt",
            direction="up",
            details={
                "level_name": "Vortageshoch",
                "level": round(level, 4),
                "previous_close": round(previous.close, 4),
                "close": round(current.close, 4),
                "buffer_points": round(buffer, 4),
                "distance_points": round(current.close - level, 4),
            },
        )

    def _check_prev_day_low(
        self, previous: MarketSnapshot, current: MarketSnapshot
    ) -> Alert | None:
        level = current.prev_session_low
        if level is None or previous.prev_session_low is None:
            return None

        buffer = self._buffer(PREV_DAY_LOW_CROSS)
        crossed = previous.close >= level and current.close < level - buffer
        if not crossed:
            return None

        return Alert(
            condition=PREV_DAY_LOW_CROSS,
            headline=f"{current.symbol}: Vortagestief {level:.2f} von oben gekreuzt",
            direction="down",
            details={
                "level_name": "Vortagestief",
                "level": round(level, 4),
                "previous_close": round(previous.close, 4),
                "close": round(current.close, 4),
                "buffer_points": round(buffer, 4),
                "distance_points": round(current.close - level, 4),
            },
        )

    def _check_rsi_overbought_exit(
        self, previous: MarketSnapshot, current: MarketSnapshot
    ) -> Alert | None:
        level = self._alerts.for_condition(RSI_EXIT_OVERBOUGHT).level
        if level is None or previous.rsi is None or current.rsi is None:
            return None
        if not (previous.rsi >= level and current.rsi < level):
            return None

        return Alert(
            condition=RSI_EXIT_OVERBOUGHT,
            headline=f"{current.symbol}: RSI verlaesst ueberkaufte Zone ({previous.rsi:.1f} -> {current.rsi:.1f})",
            direction="down",
            details={
                "threshold": level,
                "rsi_previous": round(previous.rsi, 2),
                "rsi_current": round(current.rsi, 2),
                "close": round(current.close, 4),
            },
        )

    def _check_rsi_oversold_exit(
        self, previous: MarketSnapshot, current: MarketSnapshot
    ) -> Alert | None:
        level = self._alerts.for_condition(RSI_EXIT_OVERSOLD).level
        if level is None or previous.rsi is None or current.rsi is None:
            return None
        if not (previous.rsi <= level and current.rsi > level):
            return None

        return Alert(
            condition=RSI_EXIT_OVERSOLD,
            headline=f"{current.symbol}: RSI verlaesst ueberverkaufte Zone ({previous.rsi:.1f} -> {current.rsi:.1f})",
            direction="up",
            details={
                "threshold": level,
                "rsi_previous": round(previous.rsi, 2),
                "rsi_current": round(current.rsi, 2),
                "close": round(current.close, 4),
            },
        )

    def _check_flag_breakout(
        self, previous: MarketSnapshot, current: MarketSnapshot
    ) -> Alert | None:
        if current.flag_breakout_up and not previous.flag_breakout_up:
            direction, label = "up", "nach oben"
            boundary = current.flag_range_high
        elif current.flag_breakout_down and not previous.flag_breakout_down:
            direction, label = "down", "nach unten"
            boundary = current.flag_range_low
        else:
            return None

        return Alert(
            condition=FLAG_BREAKOUT,
            headline=f"{current.symbol}: moeglicher Flaggen-Ausbruch {label}",
            direction=direction,
            details={
                "range_high": round(current.flag_range_high, 4) if current.flag_range_high else None,
                "range_low": round(current.flag_range_low, 4) if current.flag_range_low else None,
                "breakout_level": round(boundary, 4) if boundary else None,
                "close": round(current.close, 4),
                "atr": round(current.atr, 4) if current.atr else None,
                "impulse_direction": current.flag_direction,
                "note": (
                    "Heuristik: kraeftiger Impuls, danach enge Range, jetzt Schlusskurs "
                    "ausserhalb der Range. Kein bestaetigtes Chartmuster."
                ),
            },
        )
