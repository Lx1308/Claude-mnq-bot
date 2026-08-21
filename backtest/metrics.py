"""Kennzahlen zur Bewertung eines Backtests.

Zur Sharpe Ratio bei Intraday-Futures
-------------------------------------
Die klassische Sharpe Ratio setzt eine Rendite auf eingesetztes Kapital
voraus. Bei Futures ist das eingesetzte Kapital eine Margin-Entscheidung
und keine Eigenschaft der Strategie - dieselben Trades ergeben je nach
Kontogroesse voellig verschiedene "Renditen".

Deshalb werden hier zwei Varianten ausgewiesen:

``sharpe_pnl``
    Auf **taegliche P&L in USD** gerechnet: ``mean / std * sqrt(252)``.
    Kapitalunabhaengig und damit fuer den Vergleich von Strategien
    untereinander die ehrlichere Zahl.

``sharpe_on_capital``
    Nur gefuellt, wenn ein ``initial_capital`` angegeben wird. Dann wird
    die uebliche Formel auf Tagesrenditen angewandt.

Beide sind bei wenigen Trades wenig aussagekraeftig. ``trades``,
``profit_factor`` und ``max_drawdown`` sind bei Intraday-Futures in aller
Regel die belastbareren Groessen.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult

TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class Metrics:
    strategy: str
    label: str

    trades: int
    wins: int
    losses: int
    win_rate: float

    total_pnl: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    avg_trade: float
    largest_win: float
    largest_loss: float

    max_drawdown: float
    max_drawdown_pct: float | None
    max_consecutive_losses: int

    avg_bars_held: float
    exposure_pct: float

    sharpe_pnl: float | None
    sharpe_on_capital: float | None
    trading_days: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_row(self) -> dict[str, Any]:
        """Kompakte Zeile fuer die Vergleichstabelle."""
        return {
            "Strategie": self.strategy,
            "Zeitraum": self.label,
            "Trades": self.trades,
            "Trefferquote %": round(self.win_rate * 100, 1),
            "Profit-Faktor": _round_or_inf(self.profit_factor),
            "Netto USD": round(self.total_pnl, 2),
            "Ø Trade USD": round(self.avg_trade, 2),
            "Ø Gewinn USD": round(self.avg_win, 2),
            "Ø Verlust USD": round(self.avg_loss, 2),
            "Max DD USD": round(self.max_drawdown, 2),
            "Sharpe (P&L)": round(self.sharpe_pnl, 2) if self.sharpe_pnl is not None else None,
            "Ø Kerzen": round(self.avg_bars_held, 1),
        }


def _round_or_inf(value: float) -> float | str:
    if math.isinf(value):
        return "inf"
    return round(value, 2)


def max_drawdown(equity: pd.Series) -> tuple[float, float | None]:
    """Groesster Rueckgang der Equity-Kurve (absolut in USD).

    Der prozentuale Wert wird nur bezogen auf den bisherigen Hoechststand
    berechnet und ist ``None``, solange die Kurve noch nie positiv war -
    sonst waere er durch Division durch ~0 sinnlos.
    """
    if equity.empty:
        return 0.0, None
    running_peak = equity.cummax()
    drawdown = equity - running_peak
    worst = float(drawdown.min())

    peak_at_worst = float(running_peak.loc[drawdown.idxmin()])
    percentage = abs(worst) / peak_at_worst if peak_at_worst > 0 else None
    return abs(worst), percentage


def max_consecutive_losses(pnls: list[float]) -> int:
    longest = current = 0
    for pnl in pnls:
        if pnl <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def daily_pnl(equity: pd.Series) -> pd.Series:
    """Taegliche Veraenderung der Equity-Kurve.

    Tage ohne Kursdaten (Wochenenden, Feiertage) fallen heraus - sie sind
    keine Handelstage und wuerden die Standardabweichung kuenstlich
    druecken. Handelstage mit P&L von null bleiben dagegen drin: ein Tag
    ohne Trade ist ein echtes Ergebnis, kein fehlender Wert.
    """
    if equity.empty:
        return pd.Series(dtype=float)
    daily = equity.resample("1D").last().dropna()
    return daily.diff().dropna()


def compute_metrics(
    result: BacktestResult, *, initial_capital: float | None = None
) -> Metrics:
    pnls = [trade.pnl for trade in result.trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl <= 0]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = math.inf
    else:
        profit_factor = 0.0

    drawdown_abs, drawdown_pct = max_drawdown(result.equity)

    bars_in_trades = sum(trade.bars_held for trade in result.trades)
    exposure = (bars_in_trades / result.bars * 100.0) if result.bars else 0.0

    changes = daily_pnl(result.equity)
    sharpe_pnl: float | None = None
    if len(changes) >= 2 and float(changes.std(ddof=1)) > 0:
        sharpe_pnl = float(
            changes.mean() / changes.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
        )

    sharpe_capital: float | None = None
    if initial_capital and initial_capital > 0 and len(changes) >= 2:
        returns = changes / initial_capital
        if float(returns.std(ddof=1)) > 0:
            sharpe_capital = float(
                returns.mean() / returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)
            )

    win_rate = (len(wins) / len(pnls)) if pnls else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0

    return Metrics(
        strategy=result.strategy_name,
        label=result.label,
        trades=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        total_pnl=float(sum(pnls)),
        profit_factor=profit_factor,
        expectancy=(win_rate * avg_win + (1 - win_rate) * avg_loss) if pnls else 0.0,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_trade=float(np.mean(pnls)) if pnls else 0.0,
        largest_win=max(wins) if wins else 0.0,
        largest_loss=min(losses) if losses else 0.0,
        max_drawdown=drawdown_abs,
        max_drawdown_pct=drawdown_pct,
        max_consecutive_losses=max_consecutive_losses(pnls),
        avg_bars_held=(bars_in_trades / len(pnls)) if pnls else 0.0,
        exposure_pct=exposure,
        sharpe_pnl=sharpe_pnl,
        sharpe_on_capital=sharpe_capital,
        trading_days=len(changes),
    )


def format_metrics(metrics: Metrics) -> str:
    """Ausfuehrliche, menschenlesbare Darstellung einer einzelnen Auswertung."""
    lines = [
        f"--- {metrics.strategy} ({metrics.label or 'gesamt'}) ---",
        f"  Trades                : {metrics.trades} "
        f"({metrics.wins} Gewinner / {metrics.losses} Verlierer)",
        f"  Trefferquote          : {metrics.win_rate * 100:.1f} %",
        f"  Profit-Faktor         : {_round_or_inf(metrics.profit_factor)}",
        f"  Netto-P&L             : {metrics.total_pnl:,.2f} USD",
        f"  Ø Gewinn / Ø Verlust  : {metrics.avg_win:,.2f} / {metrics.avg_loss:,.2f} USD",
        f"  Ø pro Trade           : {metrics.avg_trade:,.2f} USD",
        f"  Erwartungswert        : {metrics.expectancy:,.2f} USD",
        f"  Groesster Gewinn/Verl.: {metrics.largest_win:,.2f} / {metrics.largest_loss:,.2f} USD",
        f"  Max. Drawdown         : {metrics.max_drawdown:,.2f} USD"
        + (f" ({metrics.max_drawdown_pct * 100:.1f} % vom Hoch)" if metrics.max_drawdown_pct else ""),
        f"  Max. Verluststraehne  : {metrics.max_consecutive_losses}",
        f"  Ø Haltedauer          : {metrics.avg_bars_held:.1f} Kerzen",
        f"  Marktexposition       : {metrics.exposure_pct:.1f} % der Kerzen",
        f"  Sharpe (P&L, {metrics.trading_days} Tage): "
        + (f"{metrics.sharpe_pnl:.2f}" if metrics.sharpe_pnl is not None else "n/a"),
    ]
    if metrics.sharpe_on_capital is not None:
        lines.append(f"  Sharpe (auf Kapital)  : {metrics.sharpe_on_capital:.2f}")
    if metrics.trades < 30:
        lines.append(
            "  ! Wenige Trades - Kennzahlen sind statistisch kaum belastbar."
        )
    return "\n".join(lines)
