"""Filter, die eine erkannte Idee als nicht handelbar markieren.

DREI AUSGAENGE, NICHT ZWEI
--------------------------
Ein Filter kann eine Idee durchlassen, sie ablehnen - oder feststellen,
dass er sie **nicht pruefen konnte**. Der dritte Fall ist der wichtige.

Beispiel Blackout-Fenster: Ist der Wirtschaftskalender nicht erreichbar,
waeren beide naheliegenden Antworten falsch.

- "keine Termine, also durch" waere eine **Freigabe aus einem Ausfall
  heraus**. Genau dieser Fehler ist im Projekt schon einmal aufgetreten
  (Bug-Lehre 6) und hat zur Regel gefuehrt: ein Ausfall darf nie wie
  Entwarnung aussehen.
- "nicht pruefbar, also ablehnen" waere ebenso falsch: dann wuerde ein
  Netzproblem den kompletten Datensatz vernichten, auf dem die spaetere
  Auswertung beruht.

Deshalb wird die Idee protokolliert, **nicht** als gefiltert markiert, aber
mit einem ungepruefte-Vermerk versehen. Etappe D kann dann entscheiden, ob
sie solche Ideen mitzaehlt. Die Information geht nicht verloren, und
niemand haelt sie faelschlich fuer geprueft.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol

import pandas as pd

from common.config import IdeenFilterConfig
from common.instruments import Instrument
from common.sessions import is_liquid_window, is_thin_window
from ideas.setups import ART_FORTSETZUNG, ART_REVERSION


@dataclass(frozen=True)
class Filterergebnis:
    """Ausgang einer einzelnen Filterpruefung."""

    abgelehnt: bool = False
    grund: str | None = None
    ungeprueft: str | None = None

    @staticmethod
    def durch() -> "Filterergebnis":
        return Filterergebnis()

    @staticmethod
    def ablehnen(grund: str) -> "Filterergebnis":
        return Filterergebnis(abgelehnt=True, grund=grund)

    @staticmethod
    def nicht_pruefbar(grund: str) -> "Filterergebnis":
        return Filterergebnis(ungeprueft=grund)


class BlackoutPruefer(Protocol):
    """Beantwortet: liegt dieser Zeitpunkt in einem Termin-Blackout?

    Rueckgabe ``True``/``False``. Wirft oder gibt ``None`` zurueck, wenn die
    Frage nicht beantwortbar ist - dann greift der ungeprueft-Pfad.
    """

    def __call__(self, zeitpunkt: datetime) -> bool | None: ...


def _zahl(wert: Any) -> float | None:
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) or math.isinf(zahl) else zahl


# ---------------------------------------------------------------------------
#  1  ADX-Regime
# ---------------------------------------------------------------------------

def filter_adx(
    art: str, jetzt: pd.Series, cfg: IdeenFilterConfig
) -> Filterergebnis:
    """Fortsetzungs-Setups brauchen Trend, Reversion braucht Range.

    Ein Vortagesbruch in einer flachen Range ist meistens ein Fehlausbruch;
    eine VWAP-Reversion in einem starken Trend laeuft dem Zug hinterher.
    Der ADX trennt beides grob, aber reproduzierbar.
    """
    if not cfg.adx_aktiv:
        return Filterergebnis.durch()

    adx = _zahl(jetzt.get("adx"))
    if adx is None:
        # Am Anfang der Historie ist der ADX noch nicht eingeschwungen.
        # Nicht ablehnen, aber auch nicht als geprueft ausgeben.
        return Filterergebnis.nicht_pruefbar("adx_noch_nicht_belastbar")

    if art == ART_FORTSETZUNG and adx < cfg.adx_trend_min:
        return Filterergebnis.ablehnen(
            f"adx_zu_niedrig_fuer_fortsetzung ({adx:.1f} < {cfg.adx_trend_min:.1f})"
        )
    if art == ART_REVERSION and adx > cfg.adx_range_max:
        return Filterergebnis.ablehnen(
            f"adx_zu_hoch_fuer_reversion ({adx:.1f} > {cfg.adx_range_max:.1f})"
        )
    return Filterergebnis.durch()


# ---------------------------------------------------------------------------
#  2  Liquiditaetszone
# ---------------------------------------------------------------------------

def filter_liquiditaet(
    zeitpunkt: datetime, instrument: Instrument, cfg: IdeenFilterConfig
) -> Filterergebnis:
    """Nur in den liquiden Phasen protokollieren.

    Ausserhalb sind Spreads breiter und Ausbrueche haeufiger unecht. Die
    Fensterdefinition liegt in ``common.sessions`` und rechnet in
    Boersenzeit - damit laeuft die Sommerzeit automatisch mit.
    """
    if not cfg.liquiditaet_aktiv:
        return Filterergebnis.durch()
    if is_liquid_window(zeitpunkt, instrument):
        return Filterergebnis.durch()
    return Filterergebnis.ablehnen("ausserhalb_liquider_phase")


# ---------------------------------------------------------------------------
#  3  Duennzone
# ---------------------------------------------------------------------------

def filter_duennzone(
    zeitpunkt: datetime, instrument: Instrument, cfg: IdeenFilterConfig
) -> Filterergebnis:
    """Duenne Mittagszone blockiert.

    Getrennt vom Liquiditaetsfilter, obwohl beide verwandt sind: die
    Mittagsflaute ist ein eigenes Phaenomen mit eigener Fensterdefinition,
    und in der Auswertung soll unterscheidbar bleiben, welcher der beiden
    Gruende gegriffen hat.
    """
    if not cfg.duennzone_aktiv:
        return Filterergebnis.durch()
    if is_thin_window(zeitpunkt, instrument):
        return Filterergebnis.ablehnen("duenne_mittagszone")
    return Filterergebnis.durch()


# ---------------------------------------------------------------------------
#  4  Blackout um Wirtschaftstermine
# ---------------------------------------------------------------------------

def filter_blackout(
    zeitpunkt: datetime,
    cfg: IdeenFilterConfig,
    pruefer: BlackoutPruefer | Callable[[datetime], bool | None] | None,
) -> Filterergebnis:
    """Termin-Blackout - mit dem dritten Ausgang.

    Siehe Modul-Docstring: ohne erreichbaren Kalender wird weder
    durchgewinkt noch abgelehnt, sondern als ungeprueft vermerkt.
    """
    if not cfg.blackout_aktiv:
        return Filterergebnis.durch()
    if pruefer is None:
        return Filterergebnis.nicht_pruefbar("blackout_nicht_pruefbar_kein_kalender")

    try:
        im_blackout = pruefer(zeitpunkt)
    except Exception as fehler:  # noqa: BLE001 - jeder Fehler ist "nicht pruefbar"
        return Filterergebnis.nicht_pruefbar(
            f"blackout_nicht_pruefbar ({type(fehler).__name__})"
        )

    if im_blackout is None:
        return Filterergebnis.nicht_pruefbar("blackout_nicht_pruefbar_keine_antwort")
    if im_blackout:
        return Filterergebnis.ablehnen("termin_blackout")
    return Filterergebnis.durch()


# ---------------------------------------------------------------------------
#  Alle Filter zusammen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Filterbilanz:
    """Gesamtergebnis aller Filter fuer eine Idee."""

    abgelehnt: bool
    gruende: tuple[str, ...]
    ungeprueft: tuple[str, ...]


def pruefe_alle(
    art: str,
    jetzt: pd.Series,
    zeitpunkt: datetime,
    instrument: Instrument,
    cfg: IdeenFilterConfig,
    blackout_pruefer: BlackoutPruefer | Callable[[datetime], bool | None] | None = None,
) -> Filterbilanz:
    """Alle vier Filter anwenden.

    Es wird ausdruecklich **nicht** beim ersten Treffer abgebrochen: fuer die
    spaetere Auswertung ist interessant, ob eine Idee an einem oder an vier
    Filtern gescheitert waere.
    """
    ergebnisse = (
        filter_adx(art, jetzt, cfg),
        filter_liquiditaet(zeitpunkt, instrument, cfg),
        filter_duennzone(zeitpunkt, instrument, cfg),
        filter_blackout(zeitpunkt, cfg, blackout_pruefer),
    )

    gruende = tuple(e.grund for e in ergebnisse if e.abgelehnt and e.grund)
    ungeprueft = tuple(e.ungeprueft for e in ergebnisse if e.ungeprueft)
    return Filterbilanz(
        abgelehnt=any(e.abgelehnt for e in ergebnisse),
        gruende=gruende,
        ungeprueft=ungeprueft,
    )


__all__ = [
    "BlackoutPruefer",
    "Filterbilanz",
    "Filterergebnis",
    "filter_adx",
    "filter_blackout",
    "filter_duennzone",
    "filter_liquiditaet",
    "pruefe_alle",
]
