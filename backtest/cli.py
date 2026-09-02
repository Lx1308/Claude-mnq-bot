"""Kommandozeile des Backtesting-Frameworks.

    python -m backtest.cli list
    python -m backtest.cli run      --symbol NQZ5 --strategy prev_day_breakout
    python -m backtest.cli compare  --symbol NQZ5 --strategy prev_day_breakout --strategy vwap_trend
    python -m backtest.cli optimize --symbol NQZ5 --strategy prev_day_breakout --grid "rsi_max=60,65,70"
    python -m backtest.cli walkforward --symbol NQZ5 --strategy vwap_trend \
        --train-bars 5000 --test-bars 1000
    python -m backtest.cli fetch    --symbol NQZ5 --bars 5000
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from backtest.compare import (
    compare,
    export_results,
    optimize_in_sample,
    print_report,
    render_table,
    run_on_split,
)
from backtest.data import PROVIDER, BarRequest, create_provider
from backtest.data.csv_provider import CsvDataProvider
from backtest.engine import Backtester, CostModel
from backtest.kosten import PROFILE, profil_aus_config
from backtest.metrics import compute_metrics, format_metrics
from backtest.splits import split_data
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
from backtest.walkforward import bericht_text, export_walkforward
from backtest.walkforward import lauf as walkforward_lauf
from common.config import Config, ConfigError
from common.logging_setup import setup_logging

log = logging.getLogger("backtest")


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def coerce(value: str) -> Any:
    """Wandelt einen CLI-String in den plausibelsten Python-Typ."""
    lowered = value.strip().lower()
    if lowered in {"true", "ja", "yes"}:
        return True
    if lowered in {"false", "nein", "no"}:
        return False
    if lowered in {"none", "null", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_params(pairs: list[str] | None) -> dict[str, Any]:
    """``--param rsi_max=65`` -> ``{"rsi_max": 65}``"""
    result: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Parameter muss die Form key=value haben, war: {pair!r}")
        key, _, raw = pair.partition("=")
        result[key.strip()] = coerce(raw)
    return result


def parse_grid(specs: list[str] | None) -> dict[str, list[Any]]:
    """``--grid "rsi_max=60,65,70"`` -> ``{"rsi_max": [60, 65, 70]}``"""
    grid: dict[str, list[Any]] = {}
    for spec in specs or []:
        if "=" not in spec:
            raise SystemExit(f"Grid muss die Form key=v1,v2,v3 haben, war: {spec!r}")
        key, _, raw = spec.partition("=")
        grid[key.strip()] = [coerce(part) for part in raw.split(",")]
    return grid


def load_data(config: Config, args: argparse.Namespace) -> pd.DataFrame:
    """Laedt Historie ueber den konfigurierten Provider."""
    provider_name = args.provider or config.backtest.provider

    if provider_name == "csv":
        provider = create_provider("csv", directory=config.backtest.csv_directory, path=args.csv)
    elif provider_name == "ntbridge":
        # Die echte NT8-Historie. Der Pfad kommt aus der Config, damit
        # Forschung und Betrieb dieselbe Datei lesen.
        provider = create_provider("ntbridge", database=config.ntbridge.database)
    else:
        # create_provider wirft mit einer Liste der verfuegbaren Quellen,
        # statt still etwas anderes zu nehmen.
        provider = create_provider(provider_name)

    request = BarRequest(
        symbol=args.symbol,
        interval_minutes=args.interval or config.market.candle_interval_minutes,
        start=pd.Timestamp(args.start, tz="UTC").to_pydatetime() if args.start else None,
        end=pd.Timestamp(args.end, tz="UTC").to_pydatetime() if args.end else None,
        max_bars=args.max_bars,
    )
    log.info("Lade Daten via '%s': %s", provider.name, request.describe())
    return provider.load(request)


def make_backtester(config: Config, kostenprofil: str | None = None) -> Backtester:
    """Baut den Backtester mit dem konfigurierten oder verlangten Kostenprofil.

    ``kostenprofil`` erlaubt, dasselbe Setup unter einem zweiten Profil zu
    rechnen, ohne die Konfiguration zu aendern - genau dafuer sind die Profile
    da (siehe ``backtest/kosten.py``).
    """
    profil = profil_aus_config(config.backtest, kostenprofil)
    costs = CostModel.aus_profil(
        profil,
        tick_size=config.market.tick_size,
        point_value=config.market.point_value,
    )
    return Backtester(config.market, config.indicators, costs)


# ---------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------

def command_list(_config: Config, _args: argparse.Namespace) -> int:
    print("Verfuegbare Strategien:\n")
    for name, factory in sorted(STRATEGY_LIBRARY.items()):
        doc = (factory.__doc__ or "").strip().splitlines()
        headline = doc[0] if doc else ""
        print(f"  {name:<22} {headline}")
    print(
        "\nParameter setzen mit --param key=value (mehrfach moeglich),\n"
        "z.B.  --strategy prev_day_breakout --param rsi_max=65 --param stop_loss_atr=1.0"
    )
    return 0


def command_run(config: Config, args: argparse.Namespace) -> int:
    data = load_data(config, args)
    split = split_data(data, config.backtest.split)
    backtester = make_backtester(config, getattr(args, "kostenprofil", None))

    strategy = build_strategy(args.strategy, **parse_params(args.param))
    run = run_on_split(backtester, split, strategy)

    print()
    print(strategy.describe())
    print()
    print(split.describe())
    print()
    print(format_metrics(run.in_sample_metrics))
    print()
    print(format_metrics(run.out_of_sample_metrics))
    if run.robustness is not None:
        print(f"\n  Robustheit OOS/IS: {run.robustness:.2f}")

    if args.output:
        written = export_results([run], pd.DataFrame(
            [run.in_sample_metrics.to_row(), run.out_of_sample_metrics.to_row()]
        ), args.output)
        print(f"\nErgebnisse geschrieben nach: {Path(args.output).resolve()}")
        for key, path in written.items():
            print(f"  {key}: {path.name}")
    return 0


def command_compare(config: Config, args: argparse.Namespace) -> int:
    data = load_data(config, args)
    split = split_data(data, config.backtest.split)
    backtester = make_backtester(config, getattr(args, "kostenprofil", None))

    shared_params = parse_params(args.param)
    strategies = [build_strategy(name, **shared_params) for name in args.strategy]
    if not strategies:
        strategies = [build_strategy(name) for name in sorted(STRATEGY_LIBRARY)]

    runs, table = compare(backtester, split, strategies)
    if not runs:
        print("Keine Strategie lieferte ein Ergebnis.", file=sys.stderr)
        return 1

    print()
    print(split.describe())
    print_report(runs, table)

    output = args.output or config.backtest.output_directory
    written = export_results(runs, table, output)
    print(f"Ergebnisse geschrieben nach: {Path(output).resolve()}")
    for key, path in written.items():
        print(f"  {key}: {path.name}")
    return 0


def command_optimize(config: Config, args: argparse.Namespace) -> int:
    grid = parse_grid(args.grid)
    if not grid:
        print("Bitte mindestens ein --grid angeben, z.B. --grid \"rsi_max=60,65,70\"", file=sys.stderr)
        return 2

    data = load_data(config, args)
    split = split_data(data, config.backtest.split)
    backtester = make_backtester(config, getattr(args, "kostenprofil", None))

    objective_name = args.objective
    objectives = {
        "pnl": lambda metrics: metrics.total_pnl,
        "profit_factor": lambda metrics: (
            metrics.profit_factor if metrics.profit_factor != float("inf") else 0.0
        ),
        "sharpe": lambda metrics: metrics.sharpe_pnl or 0.0,
        "pnl_per_drawdown": lambda metrics: (
            metrics.total_pnl / metrics.max_drawdown if metrics.max_drawdown > 0 else 0.0
        ),
    }
    objective = objectives[objective_name]

    print()
    print(split.describe())
    print(f"\nParametersuche fuer '{args.strategy}' AUSSCHLIESSLICH auf In-Sample-Daten.")
    print(f"Zielgroesse: {objective_name}\n")

    table = optimize_in_sample(
        backtester, split, args.strategy, grid, objective=objective, min_trades=args.min_trades
    )
    if table.empty:
        print("Keine Variante lieferte ein Ergebnis.", file=sys.stderr)
        return 1

    print(render_table(table.head(args.top)))

    best = table.iloc[0]
    # .item() wandelt numpy-Skalare in native Python-Typen - sonst steht in
    # der Ausgabe "np.float64(2.0)" statt "2.0".
    best_params = {
        key: (best[key].item() if hasattr(best[key], "item") else best[key])
        for key in grid
    }
    print(f"\nBeste In-Sample-Variante: {best_params}")
    print("Diese Parameter jetzt EINMAL out-of-sample pruefen:\n")

    strategy = build_strategy(args.strategy, **best_params)
    run = run_on_split(backtester, split, strategy)
    print(format_metrics(run.out_of_sample_metrics))
    if run.robustness is not None:
        print(f"\n  Robustheit OOS/IS: {run.robustness:.2f}")
        if run.robustness < 0.5:
            print(
                "  ! Deutlicher Abfall out-of-sample. Die Parameter sind vermutlich "
                "auf den In-Sample-Zeitraum ueberangepasst."
            )

    if args.output:
        directory = Path(args.output)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"optimierung_{args.strategy}.csv"
        table.to_csv(path, index=False)
        print(f"\nVollstaendige Ergebnisliste: {path.resolve()}")
    return 0


def command_walkforward(config: Config, args: argparse.Namespace) -> int:
    """Rollierende Testfenster ueber die gesamte geladene Historie.

    Hier wird bewusst NICHT ueber ``split_data`` geschnitten: der Sinn des
    Laufs ist gerade, die gesamte Historie in viele Fenster zu zerlegen. Es
    findet auch keine Parametersuche statt - deshalb wird auch kein
    Out-of-Sample-Zeitraum verbraucht.
    """
    data = load_data(config, args)
    backtester = make_backtester(config, getattr(args, "kostenprofil", None))
    strategy = build_strategy(args.strategy, **parse_params(args.param))

    bericht = walkforward_lauf(
        backtester,
        data,
        strategy,
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
    )

    print()
    print(strategy.describe())
    print()
    print(bericht_text(bericht))

    if args.output:
        geschrieben = export_walkforward(bericht, args.output)
        print(f"\nErgebnisse geschrieben nach: {Path(args.output).resolve()}")
        for schluessel, pfad in geschrieben.items():
            print(f"  {schluessel}: {pfad.name}")
    return 0


# ---------------------------------------------------------------------------
# Argument-Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="backtest",
        description="Backtesting-Framework fuer regelbasierte Intraday-Futures-Strategien.",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--log-level", default="INFO")

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_data_args(target: argparse.ArgumentParser) -> None:
        target.add_argument("--symbol", required=True, help="z.B. NQZ5")
        target.add_argument("--interval", type=int, help="Kerzenlaenge in Minuten")
        # Nur registrierte Quellen anbieten. "tradovate" stand hier noch, nachdem
        # der Provider mit dem Legacy-Pfad entfallen war - die Option lief in
        # einen DataProviderError statt gar nicht erst waehlbar zu sein.
        target.add_argument(
            "--provider",
            choices=tuple(sorted(PROVIDER)),
            help="'ntbridge' = die echte NT8-Historie aus ntbridge.sqlite3, "
                 "'csv' = eine Datei aus data/",
        )
        target.add_argument("--csv", help="Expliziter Pfad zu einer CSV-Datei")
        target.add_argument("--start", help="ISO-Datum, z.B. 2025-01-01")
        target.add_argument("--end", help="ISO-Datum")
        target.add_argument("--max-bars", type=int)
        # Dasselbe Setup unter einem anderen Kostenprofil rechnen, ohne die
        # config.yaml anzufassen. Der Bericht weist aus, welches galt.
        target.add_argument(
            "--kostenprofil",
            choices=sorted(PROFILE),
            help="Ueberschreibt backtest.kostenprofil fuer diesen Lauf",
        )

    list_parser = subparsers.add_parser("list", help="Verfuegbare Strategien anzeigen")
    list_parser.set_defaults(handler=command_list)

    run_parser = subparsers.add_parser("run", help="Eine Strategie testen")
    add_data_args(run_parser)
    run_parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_LIBRARY))
    run_parser.add_argument("--param", action="append", help="key=value (mehrfach moeglich)")
    run_parser.add_argument("--output", help="Verzeichnis fuer CSV/Chart-Export")
    run_parser.set_defaults(handler=command_run)

    compare_parser = subparsers.add_parser("compare", help="Mehrere Strategien vergleichen")
    add_data_args(compare_parser)
    compare_parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        choices=sorted(STRATEGY_LIBRARY),
        help="mehrfach angeben; ohne Angabe werden alle verglichen",
    )
    compare_parser.add_argument("--param", action="append", help="key=value fuer alle Strategien")
    compare_parser.add_argument("--output", help="Zielverzeichnis")
    compare_parser.set_defaults(handler=command_compare)

    optimize_parser = subparsers.add_parser(
        "optimize", help="Parameter suchen (nur In-Sample) und einmal out-of-sample pruefen"
    )
    add_data_args(optimize_parser)
    optimize_parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_LIBRARY))
    optimize_parser.add_argument(
        "--grid", action="append", required=True, help='z.B. "rsi_max=60,65,70"'
    )
    optimize_parser.add_argument(
        "--objective",
        default="pnl_per_drawdown",
        choices=("pnl", "profit_factor", "sharpe", "pnl_per_drawdown"),
    )
    optimize_parser.add_argument("--min-trades", type=int, default=20)
    optimize_parser.add_argument("--top", type=int, default=15)
    optimize_parser.add_argument("--output", help="Zielverzeichnis")
    optimize_parser.set_defaults(handler=command_optimize)

    walkforward_parser = subparsers.add_parser(
        "walkforward",
        help="Rollierende Testfenster ueber die gesamte Historie (feste Parameter)",
        description=(
            "Rechnet eine Strategie mit FESTEN Parametern ueber viele "
            "aufeinanderfolgende Testfenster. Es wird im Trainingsfenster nichts "
            "gesucht - der Lauf zeigt, wie stabil eine Parameterwahl ueber die "
            "Zeit ist, und bestaetigt keine."
        ),
    )
    add_data_args(walkforward_parser)
    walkforward_parser.add_argument("--strategy", required=True, choices=sorted(STRATEGY_LIBRARY))
    walkforward_parser.add_argument("--param", action="append", help="key=value (mehrfach moeglich)")
    # Bewusst ohne Vorgabewert: die sinnvolle Fenstergroesse haengt an der
    # Kerzenlaenge und am Zeitraum. Ein stiller Vorgabewert liesse einen Lauf
    # entstehen, dessen Fensterwahl niemand bewusst getroffen hat.
    walkforward_parser.add_argument(
        "--train-bars", type=int, required=True, help="Kerzen Vorlauf je Fenster"
    )
    walkforward_parser.add_argument(
        "--test-bars", type=int, required=True, help="Kerzen Testfenster"
    )
    walkforward_parser.add_argument(
        "--step-bars",
        type=int,
        help="Versatz zwischen Fenstern; ohne Angabe gleich --test-bars (keine Ueberlappung)",
    )
    walkforward_parser.add_argument("--output", help="Zielverzeichnis fuer CSV-Export")
    walkforward_parser.set_defaults(handler=command_walkforward)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    logging_cfg = config.logging
    if args.log_level:
        from dataclasses import replace

        logging_cfg = replace(logging_cfg, level=args.log_level.upper())
    setup_logging(logging_cfg, logger_name="backtest")

    try:
        return int(args.handler(config, args))
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI soll nicht mit Traceback enden
        log.error("Befehl fehlgeschlagen: %s", exc, exc_info=True)
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
