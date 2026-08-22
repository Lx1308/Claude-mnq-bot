"""Signalerkennung der Ideen-Protokollierung.

Hier steht **keine** Signal-Logik. Dieses Modul laeuft ueber die Kerzen und
fragt die Regel-Objekte der Backtest-Strategien, ob ihre Einstiegsbedingung
erfuellt ist. Die Bedingung selbst lebt ausschliesslich in
``backtest/strategies/`` - eine zweite Fassung hier haette bedeutet, dass der
Backtest etwas anderes prueft als das, was protokolliert wird.

WAS "KEINE ZWEITE FASSUNG" KONKRET HEISST
-----------------------------------------
Ausgewertet wird ueber denselben :class:`BarContext`, den auch
``backtest.engine`` benutzt: nur die aktuelle und die vorherige Zeile. Damit
ist Lookahead strukturell ausgeschlossen, nicht bloss durch Sorgfalt
vermieden.

Stop und Ziel entstehen aus ``stop_loss_atr``/``take_profit_atr`` derselben
:class:`RuleStrategy` und demselben ATR-Bezug wie in der Engine.

UNTERSCHIED ZUM BACKTEST - BEWUSST
----------------------------------
Die Engine kennt eine Position und ignoriert Einstiegssignale, solange sie
im Markt ist. Die Protokollierung fuehrt **keine** Position: jedes erfuellte
Signal wird festgehalten, auch wenn kurz zuvor schon eines feuerte. Das ist
richtig so - protokolliert wird die Haeufigkeit einer Bedingung, nicht eine
Handelsfolge. Eine Positionslogik wuerde Ideen verschlucken, die fuer die
Statistik gerade interessant sind.

Aus demselben Grund steht ``position=0`` und ``bars_in_trade=0`` im Kontext:
Regeln, die eine offene Position voraussetzen (etwa ``MinBarsInTrade``),
gehoeren in Ausstiegsbedingungen und nicht in Einstiegsbedingungen. Faende
sich eine solche Regel je in einem Einstieg, wuerde sie hier dauerhaft
False liefern - deshalb der ausdrueckliche Hinweis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtest.strategies.base import BarContext, RuleStrategy
from common.config import IdeasConfig
from ideas.model import RICHTUNG_LONG, RICHTUNG_SHORT, berechne_crv
from ideas.setups import SETUP_BIBLIOTHEK, SetupDefinition


class FehlendeSpalte(KeyError):
    """Dem DataFrame fehlt eine Spalte, die ein Setup zwingend braucht."""


@dataclass(frozen=True)
class Rohsignal:
    """Ein erkanntes Signal - noch ohne Filterpruefung und Profil."""

    setup: str
    art: str
    richtung: str
    zeitpunkt: pd.Timestamp
    zeile: pd.Series

    entry: float
    stop: float
    ziel: float
    crv: float
    atr_referenz: float
    stop_atr: float
    ziel_atr: float


@dataclass
class Erkennungsbericht:
    """Was der Lauf getan hat - inklusive dessen, was er NICHT tun konnte.

    ``ohne_atr`` zaehlt Signale, die erkannt wurden, aber mangels gueltigem
    ATR keinen Stop und kein Ziel bekommen konnten. Diese Zahl wird bewusst
    ausgewiesen statt verschwiegen: waere sie hoch, hiesse das, dass die
    Historie zu kurz fuer den ATR-Vorlauf ist - und ein leeres Ergebnis
    saehe faelschlich nach "keine Signale" aus.
    """

    gepruefte_kerzen: int = 0
    signale: int = 0
    ohne_atr: int = 0
    je_setup: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gepruefte_kerzen": self.gepruefte_kerzen,
            "signale": self.signale,
            "ohne_atr": self.ohne_atr,
            "je_setup": dict(self.je_setup),
        }


def _gueltig(wert: Any) -> float | None:
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) or math.isinf(zahl) else zahl


def aktive_setups(cfg: IdeasConfig) -> list[tuple[SetupDefinition, RuleStrategy]]:
    """Alle eingeschalteten Familien samt gebauter Strategie."""
    ergebnis: list[tuple[SetupDefinition, RuleStrategy]] = []
    for schluessel, definition in SETUP_BIBLIOTHEK.items():
        parameter = cfg.setup_parameter(schluessel)
        if not parameter.aktiv:
            continue
        ergebnis.append((definition, definition.baue(parameter)))
    return ergebnis


def pruefe_spalten(df: pd.DataFrame, definitionen: list[SetupDefinition]) -> None:
    """Wirft, wenn eine Spalte fehlt, die ein aktives Setup braucht.

    Absichtlich laut. Fehlte etwa ``ib_high``, wuerde die IB-Regel ueber
    ihren NaN-Schutz einfach nie ausloesen - ohne Fehlermeldung, ohne leere
    Tabelle, ohne irgendein Anzeichen. Genau diese Klasse stiller Ausfaelle
    hat das Projekt bereits einmal Wochen gekostet (Vortagesmarken bei zu
    kleinem Kerzenpuffer).
    """
    benoetigt: dict[str, list[str]] = {}
    for definition in definitionen:
        for spalte in definition.benoetigte_spalten:
            if spalte not in df.columns:
                benoetigt.setdefault(spalte, []).append(definition.schluessel)

    if benoetigt:
        details = "; ".join(
            f"{spalte} (gebraucht von {', '.join(setups)})"
            for spalte, setups in sorted(benoetigt.items())
        )
        raise FehlendeSpalte(
            "Dem DataFrame fehlen Spalten fuer die Ideen-Erkennung: "
            + details
            + ". Wurde ideas.pipeline.vorbereiten() aufgerufen?"
        )


def _signal_aus_kontext(
    definition: SetupDefinition,
    strategie: RuleStrategy,
    ctx: BarContext,
    richtung: str,
    bericht: Erkennungsbericht,
) -> Rohsignal | None:
    """Bildet Einstieg, Stop und Ziel - mit derselben ATR-Bedeutung wie die Engine."""
    entry = _gueltig(ctx.row.get("close"))
    atr_ref = _gueltig(ctx.row.get("atr"))
    if entry is None:
        return None
    if atr_ref is None or atr_ref <= 0:
        bericht.ohne_atr += 1
        return None

    stop_atr = strategie.stop_loss_atr
    ziel_atr = strategie.take_profit_atr
    if not stop_atr or not ziel_atr:
        # Ohne beide Groessen gaebe es kein CRV, und ohne CRV waere die Idee
        # in der spaeteren Auswertung nicht vergleichbar.
        bericht.ohne_atr += 1
        return None

    vorzeichen = 1.0 if richtung == RICHTUNG_LONG else -1.0
    stop = entry - vorzeichen * stop_atr * atr_ref
    ziel = entry + vorzeichen * ziel_atr * atr_ref

    return Rohsignal(
        setup=definition.schluessel,
        art=definition.art,
        richtung=richtung,
        zeitpunkt=ctx.timestamp,
        zeile=ctx.row,
        entry=entry,
        stop=stop,
        ziel=ziel,
        crv=berechne_crv(entry, stop, ziel),
        atr_referenz=atr_ref,
        stop_atr=float(stop_atr),
        ziel_atr=float(ziel_atr),
    )


def erkenne(
    df: pd.DataFrame,
    cfg: IdeasConfig,
    *,
    ab_zeitpunkt: pd.Timestamp | None = None,
) -> tuple[list[Rohsignal], Erkennungsbericht]:
    """Laeuft ueber die Kerzen und sammelt alle erfuellten Einstiegssignale.

    ``ab_zeitpunkt`` begrenzt die *Ausgabe*, nicht die Berechnung: die
    Indikatoren sind bereits gerechnet, und die Vorkerze wird fuer jede
    Flanke gebraucht. Ein ueberlappender Lauf liefert deshalb dieselben
    Signale wie ein durchgehender.
    """
    paare = aktive_setups(cfg)
    bericht = Erkennungsbericht()
    if not paare or df.empty:
        return [], bericht

    pruefe_spalten(df, [definition for definition, _ in paare])

    signale: list[Rohsignal] = []

    # Ab 1, weil jede Flanke eine Vorkerze braucht.
    for i in range(1, len(df)):
        zeitpunkt = df.index[i]
        if ab_zeitpunkt is not None and zeitpunkt < ab_zeitpunkt:
            continue

        bericht.gepruefte_kerzen += 1
        zeile = df.iloc[i]
        vorherige = df.iloc[i - 1]

        ctx = BarContext(
            row=zeile,
            previous=vorherige,
            timestamp=zeitpunkt,
            position=0,
            bars_in_trade=0,
        )

        for definition, strategie in paare:
            for regel, richtung in (
                (strategie.long_entry, RICHTUNG_LONG),
                (strategie.short_entry, RICHTUNG_SHORT),
            ):
                if regel is None or not regel.evaluate(ctx):
                    continue
                signal = _signal_aus_kontext(definition, strategie, ctx, richtung, bericht)
                if signal is None:
                    continue
                signale.append(signal)
                bericht.signale += 1
                schluessel = f"{definition.schluessel}/{richtung}"
                bericht.je_setup[schluessel] = bericht.je_setup.get(schluessel, 0) + 1

    return signale, bericht


__all__ = [
    "Erkennungsbericht",
    "FehlendeSpalte",
    "Rohsignal",
    "aktive_setups",
    "erkenne",
    "pruefe_spalten",
]
