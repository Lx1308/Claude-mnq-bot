"""Grundraten: wie oft kam eine Lage vor, und wie ging sie aus?

LAURINS FRAGE, 30.08.2026
-------------------------
"Wie oft ist ein Liquidity Sweep vorgekommen? Wie oft ist der Kurs danach in
die Gegenrichtung bis zur oberen Kante gelaufen, wie oft ist er zurueckgefallen?
Dass man die Daten mit einem prozentualen Erwartungswert versieht und sich die
Zahlen anschaut."

Das ist die richtige Frage, und es ist ausdruecklich **nicht** dasselbe wie
"tausend Varianten testen und die beste nehmen".

DER UNTERSCHIED, AN DEM ALLES HAENGT
------------------------------------
Die Multiple-Testing-Falle schnappt beim **Auswaehlen** zu, nicht beim Messen.

* 1.000 Varianten rechnen und die beste melden -> das ist der eine von 1.000
  Muenzwerfern, der zehnmal Kopf geworfen hat.
* 1.000 Lagen vermessen und **alle 1.000 Ergebnisse hinschreiben** -> das ist
  eine Grundratentabelle. Sie ist ehrlich, weil nichts ausgewaehlt wurde.

Dieses Skript macht Zweiteres. Es waehlt nichts aus, es rangiert nichts nach
Guete, es empfiehlt nichts. Es zaehlt.

Das Budget gehoert an den Schritt DANACH - wenn aus dieser Tabelle eine
Hypothese herausgegriffen und gehandelt werden soll.

WAS GEMESSEN WIRD
-----------------
Ueber ``backtest/conditional_outcomes.py`` (war bis heute nur in seinen
eigenen Tests benutzt):

* Wie viele Faelle gab es ueberhaupt?
* Wie lief der Kurs danach - im Mittel, im Median, in R (ATR-Vielfachen)?
* **Gegen die bedingungslose Nulllinie**: derselbe Zeitraum ohne Bedingung.
  Ohne diesen Vergleich weiss man nicht, ob "+0,3 R nach dem Signal" etwas
  bedeutet oder ob der Markt in dieser Zeit ohnehin +0,3 R gelaufen ist.
* Ziel-gegen-Stop-Matrix: wie oft wurde 1R/2R/3R erreicht, bevor 1R/1,5R/2R
  Verlust eintrat - **ohne** willkuerliche Ausstiegsregel.

Aufruf
------
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\grundraten.py
    .venv\\Scripts\\python.exe werkzeuge\\grundraten.py --horizont 40 --json bericht.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.conditional_outcomes import (  # noqa: E402
    ConditionalOutcomeReport,
    analyze_conditional_outcomes,
)
from backtest.data import BarRequest, create_provider  # noqa: E402
from backtest.engine import Backtester, CostModel  # noqa: E402
from backtest.kosten import profil_aus_config  # noqa: E402
from backtest.splits import split_data  # noqa: E402
from common.config import Config  # noqa: E402
from common.regime import ACHSEN, regime_spalten  # noqa: E402


def sammle_bedingungen(rahmen: pd.DataFrame) -> list[tuple[str, pd.Series, int]]:
    """(Name, Maske, Richtung) fuer jede Lage, die vermessen wird.

    ``Richtung`` ist +1, wenn die Lage aufwaerts gedeutet wird, -1 abwaerts.
    Sie legt fest, in welche Richtung R gerechnet wird - eine baerische Lage
    mit -0,3 R waere sonst als "schlecht" ausgewiesen, obwohl sie genau das
    tat, was sie sollte.

    **Die Liste ist vollstaendig und wird vollstaendig berichtet.** Hier wird
    nichts vorsortiert; sonst waere die Auswahl schon getroffen, bevor die
    Zahlen da sind.
    """
    bedingungen: list[tuple[str, pd.Series, int]] = []

    def dazu(name: str, maske, richtung: int) -> None:
        reihe = pd.Series(np.asarray(maske, dtype=bool), index=rahmen.index)
        if int(reihe.sum()) >= 30:
            bedingungen.append((name, reihe, richtung))

    # -- Muster ------------------------------------------------------------
    for spalte, richtung, beschreibung in (
        ("w_erkannt", 1, "Doppelboden bestaetigt"),
        ("w_nackenbruch", 1, "Doppelboden, Nackenlinie gebrochen"),
        ("m_erkannt", -1, "Doppeltop bestaetigt"),
        ("m_nackenbruch", -1, "Doppeltop, Nackenlinie gebrochen"),
        ("flag_breakout_up", 1, "Flaggenausbruch aufwaerts"),
        ("flag_breakout_down", -1, "Flaggenausbruch abwaerts"),
    ):
        if spalte in rahmen.columns:
            dazu(f"{spalte} ({beschreibung})", rahmen[spalte].fillna(False), richtung)

    # -- Regime, beide Richtungen -----------------------------------------
    # Ein Regime ist keine Richtungsaussage; es wird deshalb in beide
    # Richtungen vermessen. Das verdoppelt die Zeilen und ist richtig so -
    # "in hoher Volatilitaet laeuft der Markt aufwaerts" und "abwaerts" sind
    # zwei verschiedene Behauptungen.
    for achse, auspraegungen in ACHSEN.items():
        if achse not in rahmen.columns:
            continue
        for auspraegung in auspraegungen:
            maske = rahmen[achse] == auspraegung
            for richtung, zeichen in ((1, "long"), (-1, "short")):
                dazu(f"{achse}={auspraegung} ({zeichen})", maske, richtung)

    # -- Muster im Regime --------------------------------------------------
    # Nur die naheliegende Kreuzung, nicht das volle Produkt: 6 Muster x 9
    # Regimeauspraegungen x 2 Richtungen waeren 108 Zeilen, und die meisten
    # haetten zu wenige Faelle.
    if "w_erkannt" in rahmen.columns and "struktur_regime" in rahmen.columns:
        for auspraegung in ACHSEN["struktur_regime"]:
            dazu(
                f"w_erkannt & struktur={auspraegung}",
                rahmen["w_erkannt"].fillna(False) & (rahmen["struktur_regime"] == auspraegung),
                1,
            )
    if "w_erkannt" in rahmen.columns and "liquiditaet_regime" in rahmen.columns:
        for auspraegung in ACHSEN["liquiditaet_regime"]:
            dazu(
                f"w_erkannt & liquiditaet={auspraegung}",
                rahmen["w_erkannt"].fillna(False) & (rahmen["liquiditaet_regime"] == auspraegung),
                1,
            )

    return bedingungen


def zeile(bericht: ConditionalOutcomeReport) -> str:
    kante = bericht.edge_r
    return (
        f"  {bericht.condition_name:<44} "
        f"n={bericht.sample_size:>6}  "
        f"E[R]={bericht.mean_return_r:>+6.3f}  "
        f"Basis={bericht.baseline_mean_r:>+6.3f}  "
        f"Kante={kante:>+6.3f}  "
        f"p={bericht.p_value:<8.5f}"
    )


def ziel_stop_zeilen(bericht: ConditionalOutcomeReport, top: int = 3) -> list[str]:
    """Die Ziel-Stop-Kombinationen mit der hoechsten Trefferquote.

    Ausdruecklich KEINE Empfehlung - eine hohe Trefferquote bei 1R Ziel und
    2R Stop ist ein Verlustgeschaeft. Die Zeile zeigt Trefferquote UND
    Verhaeltnis, damit man das sieht.
    """
    zeilen = []
    for ergebnis in bericht.target_stop_grid[:top]:
        erwartung = (
            ergebnis.win_rate * ergebnis.target_r
            - (1 - ergebnis.win_rate) * ergebnis.stop_r
        )
        zeilen.append(
            f"      Ziel {ergebnis.target_r:.1f}R / Stop {ergebnis.stop_r:.1f}R: "
            f"{ergebnis.win_rate:>5.1%} Treffer  "
            f"({ergebnis.target_hits}/{ergebnis.stop_hits}/{ergebnis.neither_hits} "
            f"Ziel/Stop/Zeitablauf)  E={erwartung:>+5.2f}R"
        )
    return zeilen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="grundraten",
        description="Wie oft kam eine Lage vor, und wie ging sie aus?",
    )
    parser.add_argument("--symbol", default="MNQ")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument(
        "--horizont", type=int, default=24,
        help="Wie viele Kerzen nach dem Ereignis betrachtet werden (24 x 5m = 2 h)",
    )
    parser.add_argument(
        "--alles", action="store_true",
        help="Auch den Out-of-Sample-Block einbeziehen. Vorgabe ist nur "
             "Training - eine Grundratentabelle waehlt zwar nichts aus, aber "
             "wer sie liest, tut es.",
    )
    parser.add_argument("--json", help="Bericht zusaetzlich als JSON ablegen")
    args = parser.parse_args(argv)

    config = Config.load(PROJECT_ROOT / "config.yaml")

    print("Lade die echte NT8-Historie ...")
    provider = create_provider("ntbridge", database=config.ntbridge.database)
    rohdaten = provider.load(BarRequest(args.symbol, interval_minutes=args.interval))
    print(f"  {len(rohdaten)} Kerzen, {rohdaten.index[0]} bis {rohdaten.index[-1]}")

    if not args.alles:
        split = split_data(rohdaten, config.backtest.split)
        rohdaten = split.in_sample
        print(
            f"  Nur Trainingsteil: {rohdaten.index[0]:%Y-%m-%d} bis "
            f"{rohdaten.index[-1]:%Y-%m-%d} ({len(rohdaten)} Kerzen)"
        )

    profil = profil_aus_config(config.backtest)
    backtester = Backtester(
        config.market,
        config.indicators,
        CostModel.aus_profil(
            profil,
            tick_size=config.market.tick_size,
            point_value=config.market.point_value,
        ),
    )

    print("Indikatoren, Muster und Strukturniveaus rechnen ...")
    rahmen = backtester.prepare(rohdaten)

    print("Regime-Achsen rechnen ...")
    regime = regime_spalten(
        rahmen, config.indicators, config.market.session,
        kerzen_minuten=args.interval,
    )
    for spalte in regime.columns:
        rahmen[spalte] = regime[spalte]

    bedingungen = sammle_bedingungen(rahmen)
    print(f"\n{len(bedingungen)} Lagen mit mindestens 30 Faellen.\n")
    print(f"Horizont: {args.horizont} Kerzen "
          f"({args.horizont * args.interval} Minuten)")
    print("R = Vielfaches der ATR zum Ereigniszeitpunkt.")
    print("'Basis' ist derselbe Zeitraum OHNE Bedingung - ohne diesen "
          "Vergleich sagt E[R] nichts.\n")
    print("=" * 100)

    berichte: list[ConditionalOutcomeReport] = []
    for name, maske, richtung in bedingungen:
        try:
            bericht = analyze_conditional_outcomes(
                rahmen,
                maske,
                condition_name=name,
                direction=richtung,
                horizon_bars=args.horizont,
                atr_series=rahmen.get("atr"),
            )
        except ValueError as fehler:
            print(f"  {name:<44} uebersprungen: {fehler}")
            continue
        berichte.append(bericht)
        print(zeile(bericht))

    # Ziel-Stop-Matrix nur fuer die Lagen mit den meisten Faellen - sonst
    # wird der Bericht unlesbar. Das ist eine Anzeigeentscheidung, keine
    # Auswahl: die Zahlen aller Lagen stehen im JSON.
    print("\n" + "=" * 100)
    print("Ziel-gegen-Stop, fuer die zehn haeufigsten Lagen:\n")
    for bericht in sorted(berichte, key=lambda b: -b.sample_size)[:10]:
        print(f"  {bericht.condition_name}  (n={bericht.sample_size})")
        for z in ziel_stop_zeilen(bericht):
            print(z)
        print()

    print("=" * 100)
    print(
        f"{len(berichte)} Lagen vermessen. Hier wurde NICHTS ausgewaehlt und "
        "nichts empfohlen.\n"
        "Wer aus dieser Tabelle eine Hypothese herausgreift, trifft damit eine "
        f"Auswahl aus {len(berichte)} - und ab da gilt die "
        "Mehrfachtestkorrektur."
    )

    if args.json:
        pfad = Path(args.json)
        pfad.write_text(
            json.dumps(
                {
                    "symbol": args.symbol,
                    "interval_minutes": args.interval,
                    "horizont_kerzen": args.horizont,
                    "nur_training": not args.alles,
                    "kostenprofil": profil.name,
                    "lagen": [b.to_dict() for b in berichte],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nJSON abgelegt: {pfad}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
