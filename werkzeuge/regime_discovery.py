"""Discovery: unter welchen Marktbedingungen traegt ein Setup?

Beantwortet die Frage, die die erste Doppelboden-Messung offengelassen hat:
dieselbe Strategie war in-sample negativ und out-of-sample positiv. Liegt das
am Marktregime oder war es Zufall?

WAS DIESES SKRIPT IST - UND WAS NICHT
-------------------------------------
Es ist ein **Discovery**-Lauf (MASTERPLAN G): er erzeugt Hypothesen und
**keine** Aussage ueber Guete. Ein Fund hier ist ein Kandidat fuer die
Validierung, kein Befund.

Deshalb laeuft er ausschliesslich auf dem **Trainingsteil**.
``pruefe_nur_training`` bricht laut ab, sobald Daten jenseits der Grenze im
Datensatz liegen - der Out-of-Sample-Block ist einmalig und danach
verbraucht.

DIE HYPOTHESENZAHL GEHOERT IN DEN BERICHT
-----------------------------------------
Wer 40 Bedingungen prueft, findet bei alpha = 0,05 rund zwei "signifikante"
allein durch Zufall. Jeder Lauf schreibt deshalb mit, wie viele Hypothesen er
geprueft hat, und die Bonferroni-Schwelle wird dagegen gerechnet.

**Noch offen:** die Zaehlung ist laufintern. Ein laufuebergreifendes Budget
im Register (Laurins Entscheidung vom 30.08.2026) fehlt noch - bis dahin
darf aus mehreren Laeufen dieses Skripts keine Signifikanzaussage
zusammengesetzt werden.

Aufruf
------
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\regime_discovery.py
    .venv\\Scripts\\python.exe werkzeuge\\regime_discovery.py --strategie vwap_trend
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.data import BarRequest, create_provider  # noqa: E402
from backtest.engine import Backtester, CostModel  # noqa: E402
from backtest.kosten import profil_aus_config  # noqa: E402
from backtest.research import (  # noqa: E402
    Discoverylauf,
    faktor_tageszeit,
    faktor_wochentag,
    pruefe_faktor,
    pruefe_nur_training,
)
from backtest.splits import split_data  # noqa: E402
from backtest.strategies.library import build_strategy  # noqa: E402
from common.config import Config  # noqa: E402
from common.instruments import get_instrument  # noqa: E402
from common.regime import ACHSEN, regime_spalten, verteilung  # noqa: E402

#: Welche Setups gegen die Regime-Achsen gehalten werden. Die beiden
#: Doppelboden-Varianten sind der Anlass; vwap_trend laeuft als Massstab mit.
STANDARD_STRATEGIEN = (
    "doppelboden_bestaetigt",
    "doppelboden_nackenbruch",
    "vwap_trend",
)


def baue_faktor_regime(spalte: str):
    """Ordnet einen Trade der Regime-Auspraegung seiner Einstiegskerze zu.

    ``None``, wo das Regime unbestimmt ist (Fenstervorlauf) - solche Trades
    werden als "nicht zuordenbar" ausgewiesen, nicht stillschweigend einer
    Gruppe zugeschlagen.
    """

    def faktor(trade, rahmen: pd.DataFrame) -> str | None:
        if spalte not in rahmen.columns:
            return None
        marke = pd.Timestamp(trade.entry_time)
        if marke.tzinfo is None:
            marke = marke.tz_localize("UTC")
        if marke not in rahmen.index:
            return None
        wert = rahmen.loc[marke, spalte]
        if wert is None or (isinstance(wert, float) and pd.isna(wert)):
            return None
        return str(wert)

    return faktor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="regime_discovery",
        description="Einzelfaktor-Discovery gegen die Regime-Achsen.",
    )
    parser.add_argument("--symbol", default="MNQ")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument(
        "--strategie", action="append", dest="strategien",
        help="mehrfach moeglich; Vorgabe sind drei",
    )
    parser.add_argument(
        "--sessions", type=int, default=60,
        help="Fenstergroesse der Regime-Verteilung in Handelstagen",
    )
    parser.add_argument("--min-trades", type=int, default=20)
    args = parser.parse_args(argv)

    strategien = tuple(args.strategien or STANDARD_STRATEGIEN)
    config = Config.load(PROJECT_ROOT / "config.yaml")

    print("Lade die echte NT8-Historie ...")
    provider = create_provider("ntbridge", database=config.ntbridge.database)
    rohdaten = provider.load(
        BarRequest(args.symbol, interval_minutes=args.interval)
    )
    print(f"  {len(rohdaten)} Kerzen, {rohdaten.index[0]} bis {rohdaten.index[-1]}")
    if len(provider.rollgrenzen):
        print(
            f"  {len(provider.rollgrenzen)} Kontraktnahtstellen - der Preissprung "
            "dort ist ein Kontraktwechsel, keine Marktbewegung."
        )

    # NUR der Trainingsteil. Discovery darf den OOS-Block nicht sehen.
    split = split_data(rohdaten, config.backtest.split)
    training = split.in_sample
    print(
        f"\nTraining: {training.index[0]:%Y-%m-%d} bis {training.index[-1]:%Y-%m-%d} "
        f"({len(training)} Kerzen)"
    )
    print(
        f"Out-of-Sample ab {split.boundary:%Y-%m-%d} - wird hier NICHT angeruehrt."
    )

    # Denselben Weg wie die CLI: Profil aus der Config, daraus das
    # Kostenmodell. Der Bericht muss ausweisen, womit gerechnet wurde
    # (Invariante 10).
    profil = profil_aus_config(config.backtest)
    print(f"Kostenprofil: {profil.name}")
    backtester = Backtester(
        config.market,
        config.indicators,
        CostModel.aus_profil(
            profil,
            tick_size=config.market.tick_size,
            point_value=config.market.point_value,
        ),
    )

    print("\nIndikatoren und Muster rechnen ...")
    vorbereitet = backtester.prepare(training)
    pruefe_nur_training(vorbereitet, split.boundary)

    print("Regime-Achsen rechnen ...")
    regime = regime_spalten(
        vorbereitet,
        config.indicators,
        config.market.session,
        kerzen_minuten=args.interval,
        sessions=args.sessions,
    )
    for spalte in regime.columns:
        vorbereitet[spalte] = regime[spalte]

    print()
    print(verteilung(regime).bericht())

    faktoren = [
        (achse, baue_faktor_regime(achse)) for achse in ACHSEN
    ] + [
        ("tageszeit", faktor_tageszeit),
        ("wochentag", faktor_wochentag),
    ]

    punktwert = get_instrument(config.market.product).point_value
    lauf = Discoverylauf()

    for name in strategien:
        print(f"\n=== {name} ===")
        strategie = build_strategy(name)
        ergebnis = backtester.run(vorbereitet, strategie, already_prepared=True)
        print(f"{len(ergebnis.trades)} Trades im Trainingsteil")
        if not ergebnis.trades:
            print("  keine Trades - nichts zu zerlegen")
            continue
        for faktor_name, faktor in faktoren:
            lauf.ergebnisse.append(
                pruefe_faktor(
                    ergebnis, vorbereitet, faktor_name, faktor, punktwert=punktwert
                )
            )

    print("\n" + "=" * 72)
    print(lauf.bericht(min_trades=args.min_trades))
    print("\n" + "=" * 72)
    print(lauf.statistikbericht())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
