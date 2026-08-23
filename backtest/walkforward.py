"""Walk-Forward: dieselbe Strategie ueber viele aufeinanderfolgende Zeitfenster.

Ein einzelner In-/Out-of-Sample-Schnitt beantwortet nur die Frage, ob eine
Strategie in *einer* spaeteren Marktphase noch funktioniert hat. Ein Ergebnis
aus einem Schnitt ist deshalb kaum von Zufall zu unterscheiden. Walk-Forward
wiederholt den Test rollierend ueber die gesamte Historie und macht die
eigentlich interessante Groesse sichtbar: **wie viele** Fenster positiv waren,
nicht nur die Summe ueber alles.

Was dieses Modul ausdruecklich NICHT tut
----------------------------------------
Es sucht **keine Parameter** im Trainingsfenster. Die Strategie laeuft mit
festen Parametern durch alle Fenster. Damit ist das hier streng genommen kein
Walk-Forward *mit Optimierung*, sondern ein abschnittsweiser
Out-of-Sample-Lauf - und genau so wird es auch beschriftet
(:data:`MODUS_FESTE_PARAMETER`).

Das Trainingsfenster dient in dieser Fassung als **Vorlauf**, nicht als
Suchraum: es wird nicht ausgewertet und geht in keine Kennzahl ein. Eine
Fassung mit Parametersuche je Fenster waere die naechste Stufe; sie ist eine
Research-Entscheidung und steht im Masterplan, nicht hier.

Der Grund fuer die Unterscheidung ist Invariante 10: eine Auswertung, die
aussieht wie ein Walk-Forward, aber keine Optimierung enthaelt, waere eine
Schaetzung im Gewand einer Messung.

Lookahead
---------
Die Fenster entstehen ueber :func:`backtest.splits.walk_forward_windows` und
sind chronologisch: das Testfenster liegt immer **hinter** seinem
Trainingsfenster. Innerhalb eines Fensters gilt unveraendert das
Ausfuehrungsmodell der Engine (Regel auf dem Schlusskurs, Ausfuehrung zur
Eroeffnung der Folgekerze).

Die Indikatoren werden **einmal ueber die Gesamthistorie** gerechnet und erst
danach geschnitten - dieselbe Begruendung wie bei
:func:`backtest.compare.prepare_split`: ein isoliert vorbereitetes Fenster
haette in seinen ersten Kerzen keinen gueltigen SMA(50), und die Strategie
bliebe dort stumm. Da alle Indikatoren rueckwaertsgerichtet sind, entsteht
dabei kein Blick in die Zukunft.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from backtest.engine import BacktestResult, Backtester
from backtest.metrics import Metrics, compute_metrics
from backtest.splits import walk_forward_windows
from backtest.strategies.base import RuleStrategy

log = logging.getLogger(__name__)

MODUS_FESTE_PARAMETER = "feste Parameter (keine Suche im Trainingsfenster)"


class WalkForwardError(RuntimeError):
    """Der Lauf laesst sich mit den angegebenen Fenstergroessen nicht rechnen."""


@dataclass(frozen=True)
class FensterErgebnis:
    """Ein einzelnes Testfenster mit seinen Kennzahlen."""

    nummer: int
    train_von: pd.Timestamp
    train_bis: pd.Timestamp
    test_von: pd.Timestamp
    test_bis: pd.Timestamp
    metriken: Metrics
    ergebnis: BacktestResult

    def zeile(self) -> dict[str, Any]:
        """Kompakte Zeile fuer die Uebersichtstabelle."""
        return {
            "Fenster": self.nummer,
            "Test von": self.test_von.strftime("%Y-%m-%d"),
            "Test bis": self.test_bis.strftime("%Y-%m-%d"),
            "Trades": self.metriken.trades,
            "Trefferquote %": round(self.metriken.win_rate * 100, 1),
            "Netto USD": round(self.metriken.total_pnl, 2),
            "O Trade USD": round(self.metriken.avg_trade, 2),
            "Max DD USD": round(self.metriken.max_drawdown, 2),
        }


@dataclass(frozen=True)
class WalkForwardBericht:
    """Alle Fenster eines Laufs plus die Kennzahlen ueber sie hinweg."""

    strategie: str
    modus: str
    train_bars: int
    test_bars: int
    step_bars: int
    fenster: list[FensterErgebnis]

    # -- Kennzahlen ueber die Fenster ------------------------------------

    @property
    def fenster_ueberlappen(self) -> bool:
        """Ueberschneiden sich aufeinanderfolgende Testfenster?

        Bei ``step_bars < test_bars`` taucht dieselbe Kerze in mehreren
        Testfenstern auf. Summierte Groessen (Trades, Netto-P&L) zaehlen sie
        dann mehrfach.
        """
        return self.step_bars < self.test_bars

    @property
    def anzahl_fenster(self) -> int:
        return len(self.fenster)

    @property
    def anteil_positiver_fenster(self) -> float | None:
        """Anteil der Testfenster mit positiver Netto-P&L.

        Das ist die aussagekraeftigste Groesse eines Walk-Forward-Laufs.
        Eine Strategie, die insgesamt im Plus steht, aber nur in zwei von
        zwanzig Fenstern verdient hat, lebt von einer einzelnen Marktphase.

        ``None``, solange es keine Fenster gibt - nicht 0.0, denn "kein
        Fenster war positiv" und "es gab keine Fenster" sind verschiedene
        Aussagen.
        """
        if not self.fenster:
            return None
        positive = sum(1 for f in self.fenster if f.metriken.total_pnl > 0)
        return positive / len(self.fenster)

    @property
    def fenster_mit_trades(self) -> int:
        return sum(1 for f in self.fenster if f.metriken.trades > 0)

    @property
    def summe_trades(self) -> int | None:
        """Trades ueber alle Testfenster - ``None`` bei Ueberlappung."""
        if self.fenster_ueberlappen:
            return None
        return sum(f.metriken.trades for f in self.fenster)

    @property
    def summe_netto(self) -> float | None:
        """Netto-P&L ueber alle Testfenster in USD - ``None`` bei Ueberlappung.

        Bei ueberlappenden Fenstern waere die Summe schlicht falsch: dieselbe
        Kerze und damit derselbe Trade steckt in mehreren Fenstern. Lieber
        keine Zahl als eine zu grosse.
        """
        if self.fenster_ueberlappen:
            return None
        return sum(f.metriken.total_pnl for f in self.fenster)

    def tabelle(self) -> pd.DataFrame:
        return pd.DataFrame([f.zeile() for f in self.fenster])


def lauf(
    backtester: Backtester,
    data: pd.DataFrame,
    strategy: RuleStrategy,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    already_prepared: bool = False,
) -> WalkForwardBericht:
    """Rechnet die Strategie ueber alle rollierenden Testfenster.

    ``data`` ist die **Gesamthistorie**; die Indikatoren werden hier einmal
    darueber berechnet (ausser ``already_prepared``) und erst danach in
    Fenster geschnitten.
    """
    if train_bars < 1 or test_bars < 1:
        raise WalkForwardError("train_bars und test_bars muessen mindestens 1 sein.")
    if step_bars is not None and step_bars < 1:
        raise WalkForwardError("step_bars muss mindestens 1 sein.")

    vorbereitet = data if already_prepared else backtester.prepare(data)
    schritt = step_bars or test_bars

    if train_bars + test_bars > len(vorbereitet):
        # Abbrechen statt eine leere Fensterliste zurueckzugeben: null Fenster
        # liest sich wie "die Strategie hat nichts gefunden" statt wie "die
        # Historie ist fuer diese Fenstergroessen zu kurz".
        raise WalkForwardError(
            f"Historie zu kurz: {len(vorbereitet)} Kerzen, benoetigt werden "
            f"mindestens train_bars + test_bars = {train_bars + test_bars}."
        )

    fenster = walk_forward_windows(
        vorbereitet, train_bars=train_bars, test_bars=test_bars, step_bars=schritt
    )

    ergebnisse: list[FensterErgebnis] = []
    for nummer, (train, test) in enumerate(fenster, start=1):
        ergebnis = backtester.run(
            test, strategy, label=f"walk-forward Fenster {nummer}", already_prepared=True
        )
        ergebnisse.append(
            FensterErgebnis(
                nummer=nummer,
                train_von=train.index[0],
                train_bis=train.index[-1],
                test_von=test.index[0],
                test_bis=test.index[-1],
                metriken=compute_metrics(ergebnis),
                ergebnis=ergebnis,
            )
        )

    bericht = WalkForwardBericht(
        strategie=strategy.name,
        modus=MODUS_FESTE_PARAMETER,
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=schritt,
        fenster=ergebnisse,
    )
    log.info(
        "Walk-Forward '%s': %d Fenster, %d davon mit Trades",
        strategy.name,
        bericht.anzahl_fenster,
        bericht.fenster_mit_trades,
    )
    return bericht


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def bericht_text(bericht: WalkForwardBericht) -> str:
    """Der Bericht als Text - benennt auch, was NICHT gerechnet wurde."""
    from backtest.compare import render_table

    zeilen: list[str] = []
    zeilen.append(f"Walk-Forward: {bericht.strategie}")
    zeilen.append(f"  Modus            : {bericht.modus}")
    zeilen.append(
        f"  Fenster          : {bericht.train_bars} Trainingskerzen (nur Vorlauf), "
        f"{bericht.test_bars} Testkerzen, Schritt {bericht.step_bars}"
    )
    zeilen.append(f"  Testfenster      : {bericht.anzahl_fenster}")
    zeilen.append("")
    zeilen.append(render_table(bericht.tabelle()))
    zeilen.append("")

    anteil = bericht.anteil_positiver_fenster
    if anteil is None:
        zeilen.append("  Kein Testfenster - kein Ergebnis.")
        return "\n".join(zeilen)

    zeilen.append(
        f"  Positive Fenster : {anteil * 100:.0f} % "
        f"({sum(1 for f in bericht.fenster if f.metriken.total_pnl > 0)} von "
        f"{bericht.anzahl_fenster})"
    )
    zeilen.append(f"  Fenster m. Trades: {bericht.fenster_mit_trades}")

    if bericht.fenster_ueberlappen:
        # Nicht weglassen, sondern hinschreiben: eine fehlende Summenzeile
        # haelt man fuer einen Darstellungsfehler statt fuer eine Aussage.
        zeilen.append(
            "  Summe ueber alle : nicht ausgewiesen - die Testfenster ueberlappen "
            f"(Schritt {bericht.step_bars} < Testlaenge {bericht.test_bars}), "
            "dieselben Trades kaemen mehrfach vor."
        )
    else:
        zeilen.append(f"  Trades gesamt    : {bericht.summe_trades}")
        zeilen.append(f"  Netto gesamt USD : {bericht.summe_netto:.2f}")

    zeilen.append("")
    zeilen.append(
        "  Hinweis: im Trainingsfenster wurde nichts gesucht. Der Lauf zeigt, "
        "wie stabil\n  feste Parameter ueber die Zeit sind - er bestaetigt keine "
        "Parameterwahl."
    )
    return "\n".join(zeilen)


def export_walkforward(bericht: WalkForwardBericht, output_dir: str | Path) -> dict[str, Path]:
    """Schreibt die Fenstertabelle und die Trade-Listen je Fenster."""
    verzeichnis = Path(output_dir)
    verzeichnis.mkdir(parents=True, exist_ok=True)
    geschrieben: dict[str, Path] = {}

    name = _dateiname(bericht.strategie)
    tabelle_pfad = verzeichnis / f"walkforward_{name}.csv"
    bericht.tabelle().to_csv(tabelle_pfad, index=False)
    geschrieben["tabelle"] = tabelle_pfad

    for f in bericht.fenster:
        trades = f.ergebnis.trades_dataframe()
        if trades.empty:
            continue
        pfad = verzeichnis / f"walkforward_{name}_fenster{f.nummer:03d}.csv"
        trades.to_csv(pfad, index=False)
        geschrieben[f"fenster{f.nummer:03d}"] = pfad

    return geschrieben


def _dateiname(name: str) -> str:
    return "".join(z if z.isalnum() or z in "-_" else "_" for z in name)


def pruefe_chronologie(fenster: Sequence[tuple[pd.DataFrame, pd.DataFrame]]) -> None:
    """Wirft, wenn ein Testfenster nicht hinter seinem Trainingsfenster liegt.

    Das ist ein Lookahead-Test, kein Formtest: waere die Reihenfolge vertauscht,
    liefe die Auswertung auf Daten, die zum Zeitpunkt der Entscheidung noch
    nicht existierten.
    """
    for nummer, (train, test) in enumerate(fenster, start=1):
        if train.empty or test.empty:
            raise WalkForwardError(f"Fenster {nummer} hat einen leeren Teil.")
        if test.index[0] <= train.index[-1]:
            raise WalkForwardError(
                f"Fenster {nummer}: das Testfenster beginnt {test.index[0]}, "
                f"das Trainingsfenster endet aber erst {train.index[-1]}."
            )
