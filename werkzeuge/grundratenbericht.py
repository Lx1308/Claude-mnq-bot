"""Grundratenbericht aus der Ereignisdatenbank.

Etappe 8 aus ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``. Beantwortet Laurins
Ausgangsfrage: welche Situationen treten auf, und wie entwickeln sie sich -
**gegen die bedingungslose Nulllinie**.

    .venv\\Scripts\\python.exe -m werkzeuge.grundratenbericht
    .venv\\Scripts\\python.exe -m werkzeuge.grundratenbericht --horizont 60
    .venv\\Scripts\\python.exe -m werkzeuge.grundratenbericht --nach regime
    .venv\\Scripts\\python.exe -m werkzeuge.grundratenbericht --block validation

**Vorgabe ist ``--block train``.** Validation und OOS werden nicht beilaeufig
mitgelesen; wer sie sehen will, muss es hinschreiben (Plan Abschnitt 11).

WAS DER BERICHT NICHT SAGT
--------------------------
Keine Kosten, keine Slippage, keine Stops - das sind Rohverlaeufe. Bei einer
Friktion von rund 1,45 Punkten je Trade ist ein E[R] von 0,02 kein
Handelssignal. Und: **alle** gemessenen Muster stehen in der Tabelle. Wer
eines herausgreift, hat eine Auswahl getroffen; die Bonferroni-Schwelle unter
der Tabelle sagt, ab welchem p-Wert das noch zaehlt.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.ereignisse.grundraten import (  # noqa: E402
    bonferroni_schwelle,
    grundratentabelle,
    lade_fuer_auswertung,
)

DATENBANK = "data/eventdb.sqlite3"

#: Die Gruppierungen, die sich sinnvoll fragen lassen.
GRUPPIERUNGEN: dict[str, tuple[str, ...]] = {
    "muster": ("pattern_type",),
    "variante": ("pattern_type", "pattern_variant"),
    "regime": ("pattern_type", "vola_regime"),
    "session": ("pattern_type", "session"),
    "struktur": ("pattern_type", "struktur_regime"),
}


def _spalten_fuer(gruppierung: tuple[str, ...]) -> tuple[str, ...]:
    """Welche Zusatzspalten aus ``events`` geladen werden muessen."""
    schon_da = {
        "pattern_type", "pattern_variant", "direction", "vola_regime",
        "struktur_regime", "liquiditaet_regime", "session",
    }
    return tuple(s for s in gruppierung if s not in schon_da)


def bericht(
    conn: sqlite3.Connection,
    *,
    horizont: int,
    block: str,
    nach: str,
    min_n: int,
    ohne_rollnaht: bool,
) -> pd.DataFrame:
    gruppierung = GRUPPIERUNGEN[nach]
    daten = lade_fuer_auswertung(
        conn, horizont=horizont, block=block,
        zusatzspalten=_spalten_fuer(gruppierung),
    )
    if daten.empty:
        return daten

    if ohne_rollnaht:
        vorher = len(daten)
        daten = daten[daten["nahe_rollgrenze"] == 0]
        print(
            f"  Kontraktnaehte ausgeschlossen: {vorher - len(daten):,} von "
            f"{vorher:,} Ereignissen"
        )

    tabelle = grundratentabelle(daten, horizont=horizont, gruppierung=gruppierung)
    if tabelle.empty:
        return tabelle
    gefiltert = tabelle[tabelle["n"] >= min_n].reset_index(drop=True)
    gefiltert.attrs.update(tabelle.attrs)   # .attrs ueberlebt das Filtern nicht
    return gefiltert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="grundratenbericht",
        description="Grundraten je Muster aus der Ereignisdatenbank.",
    )
    parser.add_argument("--datenbank", default=DATENBANK)
    parser.add_argument("--horizont", type=int, default=60,
                        help="Horizont in Kerzen (Vorgabe 60 = eine Stunde)")
    parser.add_argument(
        "--block", default="train", choices=("train", "validation", "oos", "alle"),
        help="Datensatzblock. Vorgabe train - Validation und OOS werden "
             "nicht beilaeufig mitgelesen.",
    )
    parser.add_argument("--nach", default="muster", choices=tuple(GRUPPIERUNGEN))
    parser.add_argument("--min-n", type=int, default=200,
                        help="Zeilen mit weniger Faellen weglassen "
                             "(Vorgabe 200 = Schwelle fuer Belastbarkeit)")
    parser.add_argument(
        "--mit-rollnaht", action="store_true",
        help="Ereignisse nahe einer Kontraktnaht MITzaehlen. Vorgabe ist, "
             "sie auszuschliessen - der Preissprung dort ist ein Artefakt "
             "der Verkettung, kein Marktereignis.",
    )
    parser.add_argument("--csv", default=None, help="Tabelle zusaetzlich hier ablegen")
    args = parser.parse_args(argv)

    pfad = Path(args.datenbank)
    if not pfad.is_absolute():
        pfad = PROJECT_ROOT / pfad
    if not pfad.exists():
        print(f"Keine Ereignisdatenbank unter {pfad}.")
        print("Erst 'python -m werkzeuge.ereignisse_erkennen' laufen lassen.")
        return 1

    print(f"Grundraten, Horizont {args.horizont} Kerzen, Block '{args.block}', "
          f"gruppiert nach {args.nach}")
    conn = sqlite3.connect(str(pfad))
    try:
        tabelle = bericht(
            conn,
            horizont=args.horizont,
            block=args.block,
            nach=args.nach,
            min_n=args.min_n,
            ohne_rollnaht=not args.mit_rollnaht,
        )
    finally:
        conn.close()

    if tabelle.empty:
        print("\nKeine Zeile erreicht die Mindestgroesse - nichts zu berichten.")
        return 0

    verworfen = tabelle.attrs.get("verworfen_atr_gesamt", 0)
    if verworfen:
        print(f"  ATR-Artefakte verworfen: {verworfen:,} Ereignisse "
              "(atr_referenz < 1 Punkt - eingefrorene Kurse, kein Marktzustand)")

    anzeige = tabelle[[
        "muster", "n", "n_unabhaengig", "anteil_positiv", "basis_anteil_positiv",
        "anteil_kante", "anteil_p", "median_R", "E[R]", "mae_R_median",
    ]].copy()
    pd.set_option("display.width", 240)
    pd.set_option("display.max_rows", 200)
    print()
    print(anzeige.to_string(index=False))
    print(
        "\nMASSGEBLICH ist anteil_kante (Ueberschuss im Trefferanteil ueber "
        "die Nulllinie) mit anteil_p (ueberschneidungsfreier Zwei-Anteile-"
        "Test). E[R]/median_R stehen daneben - der Mittelwert von R ist gegen "
        "einzelne winzige ATR-Werte empfindlich, der Anteil nicht."
    )

    schwelle = bonferroni_schwelle(len(tabelle))
    treffer = tabelle[tabelle["anteil_p"] < schwelle]
    print(
        f"\n{len(tabelle)} Vergleiche. Bonferroni-Schwelle: anteil_p < {schwelle:.6f}"
    )
    if treffer.empty:
        print("Keine Zeile haelt der Mehrfachtestkorrektur stand.")
        print(
            "Das ist ein Ergebnis, kein Fehlschlag: es heisst, dass sich in "
            "diesen Rohverlaeufen kein Muster vom Zufall abhebt - genau das,\n"
            "was die Falsifikationsliteratur (Mesfin 2026) erwarten laesst."
        )
    else:
        print(f"{len(treffer)} Zeile(n) unter der Schwelle:")
        print(treffer[[
            "muster", "n_unabhaengig", "anteil_kante", "anteil_p", "hinweis",
        ]].to_string(index=False))
        print(
            "\nVORBEHALT: Trainingsmenge, ohne Kosten. Ein anteil_kante von "
            "0,01 heisst 1 Prozentpunkt mehr Treffer als die Nulllinie - bei "
            "rund 1,45 Punkten Friktion je Trade ist das kein Handelssignal.\n"
            "Der naechste Schritt ist Validation, nicht der Bot."
        )

    if args.csv:
        ziel = Path(args.csv)
        if not ziel.is_absolute():
            ziel = PROJECT_ROOT / ziel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        tabelle.to_csv(ziel, index=False)
        print(f"\nTabelle abgelegt: {ziel}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
