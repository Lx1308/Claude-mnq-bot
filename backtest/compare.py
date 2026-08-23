"""Vergleich mehrerer Strategien / Parametervarianten.

Liefert:
  * eine Tabelle mit allen Kennzahlen (Konsole + CSV)
  * einen Equity-Chart als PNG
  * Trade-Listen je Strategie als CSV

In-Sample und Out-of-Sample werden IMMER getrennt ausgewiesen. Eine
Strategie, die in-sample glaenzt und out-of-sample zusammenbricht, faellt
in der Tabelle sofort auf.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import pandas as pd

from backtest.engine import BacktestResult, Backtester
from backtest.metrics import Metrics, compute_metrics, format_metrics
from backtest.splits import DataSplit, assert_in_sample_only
from backtest.strategies.base import RuleStrategy
from backtest.strategies.library import build_strategy

log = logging.getLogger(__name__)

IN_SAMPLE = "in-sample"
OUT_OF_SAMPLE = "out-of-sample"


@dataclass
class StrategyRun:
    strategy: RuleStrategy
    in_sample: BacktestResult
    out_of_sample: BacktestResult
    in_sample_metrics: Metrics
    out_of_sample_metrics: Metrics

    @property
    def robustness(self) -> float | None:
        """Verhaeltnis Ø-Trade OOS zu Ø-Trade IS.

        Werte nahe 1 bedeuten: die Strategie verhaelt sich out-of-sample
        aehnlich wie in-sample. Deutlich unter 1 ist ein Overfitting-Verdacht.

        NUR BEI POSITIVEM IN-SAMPLE-ERGEBNIS
        ------------------------------------
        Ist der Ø-Trade in-sample negativ, dreht der Quotient sein Vorzeichen
        um und behauptet das Gegenteil dessen, was passiert ist. Am
        23.08.2026 gemessen an ``prev_day_breakout``: Ø-Trade -4.40 USD
        in-sample, -9.02 USD out-of-sample -- der Verlust hat sich also gut
        verdoppelt, der Quotient stand bei 2.05 und der Report schrieb
        "stabil" daneben.

        Es gibt an einer Strategie, die schon in-sample verliert, auch nichts
        zu bestaetigen: Robustheit ist die Frage, ob ein *gefundener* Vorteil
        ausserhalb der Suchdaten Bestand hat. Ohne Vorteil ist die Frage
        gegenstandslos, und die ehrliche Antwort ist ``None``.
        """
        if self.in_sample_metrics.avg_trade <= 0:
            return None
        return self.out_of_sample_metrics.avg_trade / self.in_sample_metrics.avg_trade


def prepare_split(
    backtester: Backtester, split: DataSplit
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Berechnet Indikatoren EINMAL ueber die Gesamthistorie und teilt danach.

    Wichtig: Wuerde man den Out-of-Sample-Teil isoliert vorbereiten, haetten
    dessen erste ~50 Kerzen keine gueltigen SMA(50)-Werte und die Strategie
    wuerde dort stumm bleiben - ein stiller Fehler, der den OOS-Zeitraum
    kuerzt. Da alle Indikatoren rueckwaertsgerichtet sind (rolling/ewm),
    entsteht durch die gemeinsame Berechnung kein Blick in die Zukunft.
    """
    full = pd.concat([split.in_sample, split.out_of_sample])
    prepared = backtester.prepare(full)
    return (
        prepared[prepared.index < split.boundary],
        prepared[prepared.index >= split.boundary],
    )


def run_on_split(
    backtester: Backtester,
    split: DataSplit,
    strategy: RuleStrategy,
    prepared: tuple[pd.DataFrame, pd.DataFrame] | None = None,
) -> StrategyRun:
    """Fuehrt eine Strategie getrennt auf beiden Zeitraeumen aus."""
    prepared_is, prepared_oos = prepared or prepare_split(backtester, split)

    result_is = backtester.run(prepared_is, strategy, label=IN_SAMPLE, already_prepared=True)
    result_oos = backtester.run(prepared_oos, strategy, label=OUT_OF_SAMPLE, already_prepared=True)

    return StrategyRun(
        strategy=strategy,
        in_sample=result_is,
        out_of_sample=result_oos,
        in_sample_metrics=compute_metrics(result_is),
        out_of_sample_metrics=compute_metrics(result_oos),
    )


def compare(
    backtester: Backtester,
    split: DataSplit,
    strategies: Sequence[RuleStrategy],
) -> tuple[list[StrategyRun], pd.DataFrame]:
    """Vergleicht mehrere Strategien und liefert Laeufe plus Tabelle."""
    runs: list[StrategyRun] = []
    rows: list[dict[str, Any]] = []

    # Indikatoren einmal berechnen und fuer alle Strategien wiederverwenden.
    prepared = prepare_split(backtester, split)

    for strategy in strategies:
        try:
            run = run_on_split(backtester, split, strategy, prepared=prepared)
        except Exception as exc:  # noqa: BLE001 - eine kaputte Variante darf den Rest nicht stoppen
            log.error("Strategie '%s' fehlgeschlagen: %s", strategy.name, exc, exc_info=True)
            continue
        runs.append(run)
        rows.append(run.in_sample_metrics.to_row())
        row_oos = run.out_of_sample_metrics.to_row()
        row_oos["Robustheit OOS/IS"] = (
            round(run.robustness, 2) if run.robustness is not None else None
        )
        rows.append(row_oos)

    table = pd.DataFrame(rows)
    return runs, table


def render_table(table: pd.DataFrame) -> str:
    """Tabelle als Text - nutzt tabulate, faellt sonst auf pandas zurueck."""
    if table.empty:
        return "(keine Ergebnisse)"
    try:
        from tabulate import tabulate

        return tabulate(table, headers="keys", tablefmt="github", showindex=False)
    except ImportError:
        return table.to_string(index=False)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(
    runs: Sequence[StrategyRun],
    table: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Schreibt Tabelle, Trade-Listen und Equity-Chart in ein Verzeichnis."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    table_path = directory / "vergleich.csv"
    table.to_csv(table_path, index=False)
    written["table"] = table_path

    for run in runs:
        safe_name = _safe_filename(run.strategy.name)
        for label, result in ((IN_SAMPLE, run.in_sample), (OUT_OF_SAMPLE, run.out_of_sample)):
            trades = result.trades_dataframe()
            if trades.empty:
                continue
            path = directory / f"trades_{safe_name}_{label}.csv"
            trades.to_csv(path, index=False)
            written[f"trades_{safe_name}_{label}"] = path

    chart = export_equity_chart(runs, directory / "equity.png")
    if chart is not None:
        written["chart"] = chart

    return written


def export_equity_chart(runs: Sequence[StrategyRun], path: str | Path) -> Path | None:
    """Zeichnet die Equity-Kurven aller Strategien (IS und OOS untereinander)."""
    if not runs:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")  # kein GUI noetig
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib nicht installiert - Equity-Chart wird uebersprungen.")
        return None

    figure, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=False)

    for axis, label, attribute in (
        (axes[0], "In-Sample", "in_sample"),
        (axes[1], "Out-of-Sample", "out_of_sample"),
    ):
        for run in runs:
            result: BacktestResult = getattr(run, attribute)
            if result.equity.empty:
                continue
            axis.plot(result.equity.index, result.equity.values, label=run.strategy.name, linewidth=1.2)
        axis.set_title(f"Equity-Kurve - {label}")
        axis.set_ylabel("Kumulierte P&L (USD)")
        axis.axhline(0.0, color="black", linewidth=0.8, linestyle="--")
        axis.grid(True, alpha=0.3)
        axis.legend(fontsize=8, loc="best")

    figure.tight_layout()
    target = Path(path)
    figure.savefig(target, dpi=120)
    plt.close(figure)
    return target


def _safe_filename(name: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in name)


# ---------------------------------------------------------------------------
# Parametersuche (ausschliesslich In-Sample)
# ---------------------------------------------------------------------------

def parameter_grid(grid: dict[str, Iterable[Any]]) -> list[dict[str, Any]]:
    """Kartesisches Produkt eines Parameterrasters."""
    keys = list(grid)
    combinations = itertools.product(*(list(grid[key]) for key in keys))
    return [dict(zip(keys, values)) for values in combinations]


def optimize_in_sample(
    backtester: Backtester,
    split: DataSplit,
    strategy_name: str,
    grid: dict[str, Iterable[Any]],
    *,
    objective: Callable[[Metrics], float] | None = None,
    min_trades: int = 20,
) -> pd.DataFrame:
    """Sucht Parameter - garantiert nur auf dem In-Sample-Zeitraum.

    Der Out-of-Sample-Teil wird hier bewusst nicht einmal angefasst; der
    Aufruf von :func:`assert_in_sample_only` macht einen Fehlgriff zu einem
    lauten Fehler statt zu einem stillen Ergebnis.
    """
    assert_in_sample_only(split.in_sample, split, context="Parametersuche")

    objective = objective or (lambda metrics: metrics.total_pnl)
    # Nur der In-Sample-Teil des vorbereiteten Datensatzes - der zweite Teil
    # wird hier nicht einmal ausgepackt.
    prepared, _ = prepare_split(backtester, split)

    rows: list[dict[str, Any]] = []
    for params in parameter_grid(grid):
        strategy = build_strategy(strategy_name, **params)
        try:
            result = backtester.run(prepared, strategy, label=IN_SAMPLE, already_prepared=True)
        except Exception as exc:  # noqa: BLE001
            log.error("Variante %s fehlgeschlagen: %s", params, exc)
            continue
        metrics = compute_metrics(result)
        rows.append(
            {
                **params,
                "Trades": metrics.trades,
                "Trefferquote %": round(metrics.win_rate * 100, 1),
                "Profit-Faktor": metrics.profit_factor,
                "Netto USD": round(metrics.total_pnl, 2),
                "Max DD USD": round(metrics.max_drawdown, 2),
                "Ziel": round(objective(metrics), 4),
                "genug_trades": metrics.trades >= min_trades,
            }
        )

    table = pd.DataFrame(rows)
    if table.empty:
        return table

    # Varianten mit zu wenigen Trades nach hinten - sie sind Zufallsprodukte.
    table = table.sort_values(["genug_trades", "Ziel"], ascending=[False, False]).reset_index(drop=True)
    log.info(
        "Parametersuche abgeschlossen: %d Varianten, beste Zielgroesse %.4f",
        len(table),
        float(table.iloc[0]["Ziel"]),
    )
    return table


def kostenzeile(kosten: dict) -> str:
    """Womit gerechnet wurde - gehoert an den Anfang jedes Berichts.

    Dieselbe Strategie ist unter 0,50 und unter 2,50 USD je Seite ein voellig
    anderes Geschaeft. Ein Ergebnis ohne diese Angabe laesst sich nicht
    einordnen, und genau das war bis zum 23.08.2026 der Fall.
    """
    if not kosten:
        return "Kostenprofil          : nicht ausgewiesen"

    art = "ANNAHME, nicht verifiziert" if kosten.get("ist_annahme") else "belegt"
    zeilen = [
        f"Kostenprofil          : {kosten.get('name')}  [{art}]",
        f"  je Seite            : {kosten.get('je_seite_usd')} USD"
        f"   (Round Turn {kosten.get('round_turn_usd')} USD)",
        f"  Slippage            : {kosten.get('slippage_ticks_je_seite')} Ticks je Seite"
        "  (KEINE Gebuehr - Ausfuehrungsqualitaet)",
        f"  Quelle              : {kosten.get('quelle')}",
    ]
    hinweis = kosten.get("aufschluesselung_hinweis")
    if hinweis:
        zeilen.append(f"  Aufschluesselung    : {hinweis}")
    else:
        a = kosten.get("aufschluesselung") or {}
        zeilen.append(
            f"  Aufschluesselung    : Broker {a.get('broker_kommission')}, "
            f"Boerse {a.get('boerse')}, Clearing {a.get('clearing')}, "
            f"NFA {a.get('nfa')}"
        )
    return "\n".join(zeilen)


def print_report(runs: Sequence[StrategyRun], table: pd.DataFrame) -> None:
    print()
    kosten = next(
        (r.in_sample.kosten for r in runs if getattr(r, "in_sample", None) is not None),
        {},
    )
    print(kostenzeile(kosten))
    print()
    print(render_table(table))
    print()
    for run in runs:
        print(run.strategy.describe())
        print(format_metrics(run.in_sample_metrics))
        print(format_metrics(run.out_of_sample_metrics))
        if run.robustness is not None:
            verdict = (
                "stabil" if run.robustness >= 0.5
                else "auffaellig schwaecher out-of-sample (Overfitting-Verdacht)"
            )
            print(f"  Robustheit OOS/IS     : {run.robustness:.2f}  -> {verdict}")
        elif run.in_sample_metrics.trades and run.in_sample_metrics.avg_trade <= 0:
            # Nicht stillschweigend weglassen: das Fehlen der Zeile wuerde man
            # fuer einen Darstellungsfehler halten statt fuer eine Aussage.
            print(
                "  Robustheit OOS/IS     : nicht aussagekraeftig "
                "(schon in-sample kein positiver Ø-Trade)"
            )
        print()
