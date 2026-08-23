"""Einzelfaktor-Research: unter welchen Bedingungen traegt ein Setup?

WOZU
----
Die Basisvermessung vom 23.08.2026 zeigte, dass alle vier Setup-Familien
ueber die Gesamthistorie negativ sind - brutto, also nicht bloss von Gebuehren
aufgefressen. Ueber alles gemittelt heisst aber nicht ueberall.

Ein Setup, das im Trend traegt und in der Range verliert, sieht gemittelt aus
wie "kein Erwartungswert". Genau die Setups, die sich lohnen wuerden, sind so
unsichtbar. Dieses Modul teilt die Trades nach einer **vorab benannten**
Bedingung und rechnet je Gruppe.

WARUM EINZELFAKTOR ZUERST
-------------------------
Erst "traegt Bedingung X allein", dann Zweifaktor, dann Mehrfaktor
(``MASTERPLAN.md`` G). Wer sofort kombiniert, findet Kombinationen, die auf
den Trainingsdaten passen und sonst nirgends.

DAS MULTIPLE-TESTING-PROBLEM IST DER KERN
-----------------------------------------
Wer 40 Bedingungen prueft, findet bei alpha = 0,05 rund zwei "signifikante"
allein durch Zufall. Deshalb schreibt **jeder** Lauf mit, wie viele Hypothesen
er geprueft hat. Ohne diese Zahl ist jede Aussage ueber Signifikanz wertlos -
und die Zahl gehoert in den Bericht, nicht in eine Fussnote.

Ein Ergebnis dieses Moduls ist eine **Hypothese fuer die Validierung**, kein
Befund. Die Bestaetigung braucht den Validation-Block, und erst danach
einmalig den OOS-Block.

KEINE OOS-BERUEHRUNG
--------------------
Discovery laeuft ausschliesslich auf dem Trainingsteil. ``pruefe_nur_training``
bricht ab, sobald Daten jenseits der Grenze im Datensatz liegen - dieselbe
Haltung wie ``assert_in_sample_only`` bei der Parametersuche.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult, Trade

#: Unterhalb dieser Trade-Zahl wird KEINE Kennzahl ausgegeben, sondern
#: "zu wenig Daten". Laurins eigene Schwelle; sie steht hier als Vorgabe und
#: ist je Aufruf ueberschreibbar.
MIN_TRADES_JE_GRUPPE = 20


class OutOfSampleBeruehrung(RuntimeError):
    """Discovery hat Daten jenseits der Trainingsgrenze gesehen."""


def pruefe_nur_training(rahmen: pd.DataFrame, trainingsende: pd.Timestamp) -> None:
    """Bricht ab, wenn der Datensatz ueber das Trainingsende hinausreicht.

    Absichtlich laut. Ein Discovery-Lauf, der versehentlich OOS-Daten sieht,
    verbrennt den einzigen unabhaengigen Block - und man merkt es nicht, weil
    das Ergebnis dann nur besser aussieht.
    """
    if rahmen.empty:
        return
    letzter = rahmen.index[-1]
    if letzter > trainingsende:
        raise OutOfSampleBeruehrung(
            f"Der Datensatz reicht bis {letzter}, das Training endet aber "
            f"{trainingsende}. Discovery darf den Out-of-Sample-Block nicht "
            "sehen - er ist einmalig und danach verbraucht."
        )


@dataclass(frozen=True)
class Gruppenergebnis:
    """Kennzahlen einer Auspraegung des geprueften Faktors."""

    auspraegung: str
    trades: int
    treffer: int

    #: Brutto in Punkten je Trade - die Kante VOR Kosten. Die aussagekraeftigste
    #: Groesse fuer Research: Kosten sind eine Konstante, die Kante nicht.
    brutto_punkte_je_trade: float
    #: Netto in USD je Trade, also nach dem verwendeten Kostenprofil.
    netto_usd_je_trade: float
    brutto_punkte_gesamt: float
    netto_usd_gesamt: float

    @property
    def trefferquote(self) -> float:
        return self.treffer / self.trades if self.trades else 0.0

    @property
    def genug_daten(self) -> bool:
        return self.trades >= MIN_TRADES_JE_GRUPPE

    def zeile(self, min_trades: int = MIN_TRADES_JE_GRUPPE) -> str:
        if self.trades < min_trades:
            return (
                f"  {self.auspraegung:<22} {self.trades:>5} Trades  "
                f"-> zu wenig Daten (Schwelle {min_trades})"
            )
        return (
            f"  {self.auspraegung:<22} {self.trades:>5} Trades  "
            f"{self.trefferquote:>6.1%}  "
            f"brutto {self.brutto_punkte_je_trade:>+7.3f} Pkt  "
            f"netto {self.netto_usd_je_trade:>+8.2f} USD"
        )


@dataclass
class Faktorergebnis:
    """Ergebnis der Pruefung EINES Faktors ueber alle seine Auspraegungen."""

    faktor: str
    strategie: str
    gruppen: list[Gruppenergebnis] = field(default_factory=list)
    #: Trades, die keiner Auspraegung zugeordnet werden konnten. Werden
    #: ausgewiesen statt verschwiegen - eine hohe Zahl heisst, dass der
    #: Faktor fuer viele Trades gar nicht definiert war.
    nicht_zuordenbar: int = 0

    @property
    def auswertbare_gruppen(self) -> list[Gruppenergebnis]:
        return [g for g in self.gruppen if g.genug_daten]

    @property
    def spannweite_brutto(self) -> float | None:
        """Abstand zwischen bester und schlechtester auswertbarer Gruppe.

        Das ist die eigentliche Research-Frage: **unterscheidet** der Faktor?
        Ein Faktor, dessen Gruppen alle gleich abschneiden, trennt nichts -
        egal wie gut oder schlecht das Niveau ist.
        """
        werte = [g.brutto_punkte_je_trade for g in self.auswertbare_gruppen]
        return max(werte) - min(werte) if len(werte) >= 2 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "faktor": self.faktor,
            "strategie": self.strategie,
            "gruppen": [
                {
                    "auspraegung": g.auspraegung,
                    "trades": g.trades,
                    "trefferquote": round(g.trefferquote, 4),
                    "brutto_punkte_je_trade": round(g.brutto_punkte_je_trade, 4),
                    "netto_usd_je_trade": round(g.netto_usd_je_trade, 2),
                    "genug_daten": g.genug_daten,
                }
                for g in self.gruppen
            ],
            "nicht_zuordenbar": self.nicht_zuordenbar,
            "spannweite_brutto": (
                round(self.spannweite_brutto, 4)
                if self.spannweite_brutto is not None
                else None
            ),
        }


@dataclass
class Discoverylauf:
    """Ein vollstaendiger Discovery-Durchgang samt Hypothesen-Buchfuehrung."""

    ergebnisse: list[Faktorergebnis] = field(default_factory=list)

    @property
    def gepruefte_hypothesen(self) -> int:
        """Jede Auspraegung mit genug Daten ist eine gepruefte Hypothese.

        Diese Zahl gehoert in jeden Bericht. Bei 40 Hypothesen und alpha = 0,05
        sind zwei "signifikante" Funde der Erwartungswert, nicht ein Ergebnis.
        """
        return sum(len(e.auswertbare_gruppen) for e in self.ergebnisse)

    def bericht(self, min_trades: int = MIN_TRADES_JE_GRUPPE) -> str:
        zeilen: list[str] = []
        for erg in self.ergebnisse:
            zeilen.append(f"{erg.strategie} nach {erg.faktor}:")
            for gruppe in erg.gruppen:
                zeilen.append(gruppe.zeile(min_trades))
            if erg.nicht_zuordenbar:
                zeilen.append(
                    f"  {'(nicht zuordenbar)':<22} {erg.nicht_zuordenbar:>5} Trades"
                )
            spanne = erg.spannweite_brutto
            if spanne is not None:
                zeilen.append(f"  -> Spannweite brutto: {spanne:.3f} Punkte")
            else:
                zeilen.append(
                    "  -> keine Spannweite (unter zwei auswertbaren Gruppen)"
                )
            zeilen.append("")

        zeilen.append(f"Geprüfte Hypothesen in diesem Lauf: {self.gepruefte_hypothesen}")
        zeilen.append(
            "Bei alpha = 0,05 sind davon rund "
            f"{self.gepruefte_hypothesen * 0.05:.1f} Zufallstreffer zu erwarten. "
            "Ein Fund ist eine Hypothese fuer die Validierung, kein Befund."
        )
        return "\n".join(zeilen)


# ---------------------------------------------------------------------------
#  Faktoren - jede Funktion ordnet einem Trade eine Auspraegung zu
# ---------------------------------------------------------------------------
#
# Signatur: (trade, vorbereiteter_rahmen) -> str | None
# ``None`` heisst "fuer diesen Trade nicht bestimmbar" und wird als
# nicht zuordenbar ausgewiesen, nicht stillschweigend einer Gruppe zugeschlagen.

FaktorFunktion = Callable[[Trade, pd.DataFrame], "str | None"]


def _wert_bei_einstieg(rahmen: pd.DataFrame, trade: Trade, spalte: str) -> float | None:
    """Spaltenwert auf der Einstiegskerze - kein Blick nach vorn."""
    if spalte not in rahmen.columns:
        return None
    marke = pd.Timestamp(trade.entry_time)
    if marke.tzinfo is None:
        marke = marke.tz_localize("UTC")
    if marke not in rahmen.index:
        return None
    wert = rahmen.loc[marke, spalte]
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) else zahl


def faktor_tageszeit(trade: Trade, rahmen: pd.DataFrame) -> str | None:
    """Stunde des Einstiegs in Boersenzeit (New York).

    Der am besten belegte Faktor der Recherche: Intraday-Momentum ist an die
    erste und letzte halbe Stunde gebunden, und die Overnight-Phase verhaelt
    sich nachweislich anders als die Kernzeit.
    """
    marke = pd.Timestamp(trade.entry_time)
    if marke.tzinfo is None:
        marke = marke.tz_localize("UTC")
    stunde = marke.tz_convert("America/New_York").hour
    if 9 <= stunde < 11:
        return "1 Eroeffnung 09-11"
    if 11 <= stunde < 14:
        return "2 Mittag 11-14"
    if 14 <= stunde < 16:
        return "3 Schluss 14-16"
    return "4 ausserhalb RTH"


def faktor_wochentag(trade: Trade, rahmen: pd.DataFrame) -> str | None:
    marke = pd.Timestamp(trade.entry_time)
    if marke.tzinfo is None:
        marke = marke.tz_localize("UTC")
    namen = ["1 Mo", "2 Di", "3 Mi", "4 Do", "5 Fr", "6 Sa", "7 So"]
    return namen[marke.tz_convert("America/New_York").weekday()]


def baue_faktor_perzentil(
    spalte: str, grenzen: Sequence[float], namen: Sequence[str]
) -> FaktorFunktion:
    """Faktor aus Perzentilgrenzen einer Spalte.

    Die Grenzen werden **aus der Verteilung** abgeleitet und dem Aufrufer
    uebergeben, nicht hier gesetzt. Nach dem ``consolidation_max_atr``-Fund
    (Schwelle 1,2 war auf keiner Zeitebene erreichbar) ist eine geratene
    Grenze ein konkreter Verdacht, kein allgemeiner Vorbehalt.
    """
    if len(namen) != len(grenzen) + 1:
        raise ValueError("Es braucht genau eine Bezeichnung mehr als Grenzen.")

    def faktor(trade: Trade, rahmen: pd.DataFrame) -> str | None:
        wert = _wert_bei_einstieg(rahmen, trade, spalte)
        if wert is None:
            return None
        for i, grenze in enumerate(grenzen):
            if wert <= grenze:
                return namen[i]
        return namen[-1]

    return faktor


def perzentilgrenzen(
    rahmen: pd.DataFrame, spalte: str, perzentile: Sequence[float]
) -> list[float]:
    """Grenzen aus der tatsaechlichen Verteilung - nicht geraten."""
    reihe = rahmen[spalte].dropna()
    if reihe.empty:
        raise ValueError(f"Spalte {spalte!r} enthaelt keine gueltigen Werte.")
    return [float(np.percentile(reihe, p)) for p in perzentile]


# ---------------------------------------------------------------------------
#  Auswertung
# ---------------------------------------------------------------------------

def pruefe_faktor(
    ergebnis: BacktestResult,
    rahmen: pd.DataFrame,
    faktor_name: str,
    faktor: FaktorFunktion,
    *,
    punktwert: float,
) -> Faktorergebnis:
    """Teilt die Trades eines Laufs nach einem Faktor und rechnet je Gruppe."""
    eimer: dict[str, list[Trade]] = {}
    offen = 0

    for trade in ergebnis.trades:
        auspraegung = faktor(trade, rahmen)
        if auspraegung is None:
            offen += 1
            continue
        eimer.setdefault(auspraegung, []).append(trade)

    gruppen: list[Gruppenergebnis] = []
    for auspraegung in sorted(eimer):
        trades = eimer[auspraegung]
        brutto = sum(t.gross_points for t in trades)
        netto = sum(t.pnl for t in trades)
        gruppen.append(
            Gruppenergebnis(
                auspraegung=auspraegung,
                trades=len(trades),
                treffer=sum(1 for t in trades if t.pnl > 0),
                brutto_punkte_je_trade=brutto / len(trades),
                netto_usd_je_trade=netto / len(trades),
                brutto_punkte_gesamt=brutto,
                netto_usd_gesamt=netto,
            )
        )

    return Faktorergebnis(
        faktor=faktor_name,
        strategie=ergebnis.strategy_name,
        gruppen=gruppen,
        nicht_zuordenbar=offen,
    )


__all__ = [
    "MIN_TRADES_JE_GRUPPE",
    "Discoverylauf",
    "Faktorergebnis",
    "Gruppenergebnis",
    "OutOfSampleBeruehrung",
    "baue_faktor_perzentil",
    "faktor_tageszeit",
    "faktor_wochentag",
    "perzentilgrenzen",
    "pruefe_faktor",
    "pruefe_nur_training",
]
