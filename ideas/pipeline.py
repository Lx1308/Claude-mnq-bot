"""Ablauf der Ideen-Protokollierung: Kerzen rein, Ideen raus.

REIHENFOLGE UND IHR GRUND
-------------------------
1. ``vorbereiten`` rechnet die Indikatoren - ueber ``compute_extended_indicators``,
   weil der ADX-Filter den ADX braucht, und ergaenzt die Initial Balance je
   Session. Die Basisrechnung ist dieselbe wie im Backtest und im Live-Bot.
2. ``erkenne`` fragt die Regel-Objekte der Backtest-Strategien.
3. ``pruefe_alle`` bewertet jedes Signal mit den vier Filtern.
4. Alles wird gespeichert - auch das Abgelehnte.

WARUM AUCH ABGELEHNTE IDEEN GESPEICHERT WERDEN
----------------------------------------------
Ohne sie liesse sich spaeter weder pruefen, ob ein Filter zu scharf steht,
noch die Frage beantworten, wie viele Ideen ein Regelwerk verhindert haette.
Stilles Verwerfen ist in diesem Projekt unzulaessig - eine weggelassene Zeile
sieht hinterher aus wie eine, die es nie gab.

WARUM DIE INDIKATOREN UEBER DIE GESAMTE HISTORIE GERECHNET WERDEN
-----------------------------------------------------------------
``ab_zeitpunkt`` begrenzt nur, welche Signale ausgegeben werden - gerechnet
wird immer ueber alle geladenen Kerzen. Schnitte man den Rahmen vorher zu,
haetten die ersten Kerzen keinen gueltigen ATR und keinen SMA, und das Setup
bliebe dort stumm. Genau dieser Fehler ist im Projekt schon einmal
aufgetreten (isoliert vorbereiteter Out-of-Sample-Block).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from common.config import Config
from common.indicators import compute_extended_indicators
from common.instruments import Instrument, get_instrument
from common.levels import initial_balance_per_session
from common.logging_setup import log_event
from ideas.erkennung import Erkennungsbericht, Rohsignal, erkenne
from ideas.filters import BlackoutPruefer, pruefe_alle
from ideas.model import QUELLE_REGEL, TradeIdee, UngueltigeIdee
from ideas.setups import pruefe_konfiguration
from ideas.store import IdeenStore

log = logging.getLogger(__name__)


def vorbereiten(
    df: pd.DataFrame,
    instrument: Instrument,
    cfg: Config,
) -> pd.DataFrame:
    """Haengt alle Spalten an, die die aktiven Setups und Filter brauchen.

    ``compute_extended_indicators`` statt ``compute_indicators``, weil der
    ADX-Filter den ADX braucht. Das ist hier vertretbar: die Protokollierung
    laeuft einmal je Kerzenschluss, nicht 300.000-mal wie ein Backtest.

    Die Initial Balance kommt aus ``common.levels`` und nicht aus einer
    eigenen Rechnung - dieselbe Konstante, dieselbe RTH-Maske, derselbe
    Lookahead-Schutz.
    """
    angereichert = compute_extended_indicators(
        df, cfg.indicators, cfg.market.session
    )
    ib = initial_balance_per_session(angereichert, instrument, cfg.market.session)
    for spalte in ib.columns:
        angereichert[spalte] = ib[spalte]
    return angereichert


@dataclass
class Protokollbericht:
    """Ergebnis eines Protokollierungslaufs."""

    instrument: str
    timeframe: str
    erkennung: Erkennungsbericht
    erzeugt: int = 0
    gefiltert: int = 0
    neu_gespeichert: int = 0
    verworfen: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "erkennung": self.erkennung.to_dict(),
            "erzeugt": self.erzeugt,
            "gefiltert": self.gefiltert,
            "neu_gespeichert": self.neu_gespeichert,
            "verworfen": list(self.verworfen),
        }


def baue_idee(
    signal: Rohsignal,
    instrument: Instrument,
    timeframe: str,
    cfg: Config,
    *,
    blackout_pruefer: BlackoutPruefer | Callable | None = None,
    quelle: str = QUELLE_REGEL,
    notiz: str | None = None,
) -> TradeIdee:
    """Aus einem Rohsignal plus Filterbilanz eine speicherbare Idee bilden."""
    zeitpunkt = signal.zeitpunkt.to_pydatetime()
    bilanz = pruefe_alle(
        signal.art,
        signal.zeile,
        zeitpunkt,
        instrument,
        cfg.ideas.filter,
        blackout_pruefer,
    )

    kontext = dict(bilanz.kontext)
    kontext["gefiltert"] = bilanz.abgelehnt
    if bilanz.gruende:
        kontext["gruende"] = list(bilanz.gruende)
    if bilanz.ungeprueft:
        kontext["ungeprueft"] = list(bilanz.ungeprueft)

    return TradeIdee(
        instrument=instrument.root,
        setup=signal.setup,
        richtung=signal.richtung,
        timeframe=timeframe,
        erstellt_utc=zeitpunkt,
        entry=signal.entry,
        stop=signal.stop,
        ziel=signal.ziel,
        crv=signal.crv,
        unter_crv_schwelle=signal.crv < cfg.ideas.crv_schwelle,
        atr_referenz=signal.atr_referenz,
        stop_atr=signal.stop_atr,
        ziel_atr=signal.ziel_atr,
        quelle=quelle,
        profil=cfg.ideas.profil,
        gefiltert=bilanz.abgelehnt,
        filter_gruende=bilanz.gruende,
        ungeprueft=bilanz.ungeprueft,
        filter_context=kontext,
        notiz=notiz,
    )


def protokolliere(
    df: pd.DataFrame,
    symbol: str,
    cfg: Config,
    store: IdeenStore,
    *,
    bereits_vorbereitet: bool = False,
    blackout_pruefer: BlackoutPruefer | Callable | None = None,
    ab_zeitpunkt: pd.Timestamp | None = None,
) -> Protokollbericht:
    """Ein vollstaendiger Lauf: erkennen, filtern, speichern.

    ``ab_zeitpunkt`` erlaubt ueberlappende Laeufe, ohne dass Duplikate
    entstehen - der UNIQUE-Index im Speicher faengt Wiederholungen ohnehin
    ab, aber die Begrenzung spart die Filterarbeit.
    """
    # Vor jeder Arbeit: eine Konfiguration, die nie ausloesen kann, soll
    # abbrechen statt still ein leeres Ergebnis zu liefern.
    pruefe_konfiguration(cfg.ideas)

    instrument = get_instrument(symbol)
    timeframe = cfg.ideas.timeframe

    daten = df if bereits_vorbereitet else vorbereiten(df, instrument, cfg)
    signale, erkennungsbericht = erkenne(daten, cfg.ideas, ab_zeitpunkt=ab_zeitpunkt)

    bericht = Protokollbericht(
        instrument=instrument.root,
        timeframe=timeframe,
        erkennung=erkennungsbericht,
    )

    ideen: list[TradeIdee] = []
    for signal in signale:
        try:
            idee = baue_idee(
                signal,
                instrument,
                timeframe,
                cfg,
                blackout_pruefer=blackout_pruefer,
            )
        except UngueltigeIdee as fehler:
            # Nicht stillschweigend ueberspringen: eine unschluessige Idee
            # ist ein Hinweis auf kaputte Eingangsdaten, kein Rauschen.
            bericht.verworfen.append(f"{signal.setup}/{signal.richtung}: {fehler}")
            log_event(
                log,
                "ideen.verworfen",
                "Idee war nicht schluessig und wurde nicht gespeichert.",
                level=logging.WARNING,
                setup=signal.setup,
                richtung=signal.richtung,
                zeitpunkt=str(signal.zeitpunkt),
                grund=str(fehler),
            )
            continue

        if idee.gefiltert:
            bericht.gefiltert += 1
            if not cfg.ideas.speichere_gefilterte:
                continue
        ideen.append(idee)

    bericht.erzeugt = len(ideen)
    bericht.neu_gespeichert = store.speichere(ideen)

    log_event(
        log,
        "ideen.lauf",
        "Ideen-Protokollierung abgeschlossen.",
        **bericht.to_dict(),
    )
    return bericht


__all__ = [
    "Protokollbericht",
    "baue_idee",
    "protokolliere",
    "vorbereiten",
]
