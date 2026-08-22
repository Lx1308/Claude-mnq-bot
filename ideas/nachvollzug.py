"""Prueft, ob eine protokollierte Idee aus den Kerzen nachvollziehbar ist.

WOZU
----
Spezifikation Abschnitt 1 verlangt "nachspielbar, nicht nur
ergebnisorientiert": das Log haelt nur die Eckdaten, der Kursverlauf wird bei
der Auswertung aus ``ntbridge.sqlite3`` rekonstruiert. Diese Zusage ist wenig
wert, solange sie niemand prueft - eine Idee mit falschem Zeitstempel oder
einem Stop, der nicht zu ihrem ATR passt, faellt sonst erst in Etappe D auf,
wenn die Statistik schon darauf beruht.

Dieses Modul rechnet eine gespeicherte Idee gegen die Kerzen zurueck und
meldet **jede** Abweichung einzeln, statt nur "passt" oder "passt nicht".

WAS GEPRUEFT WIRD
-----------------
1. Zur ``erstellt_utc`` existiert ueberhaupt eine Kerze.
2. ``entry`` ist der Schlusskurs jener Kerze.
3. ``atr_referenz`` ist der ATR jener Kerze.
4. ``stop`` und ``ziel`` ergeben sich aus ``entry`` und den ATR-Faktoren.
5. Die Einstiegsregel des Setups war auf jener Kerze tatsaechlich erfuellt.

Punkt 5 ist der eigentliche Kern: die ersten vier pruefen Arithmetik, der
fuenfte prueft, dass die Idee ueberhaupt aus einer erfuellten Bedingung
stammt. Ohne ihn koennte eine frei erfundene Zeile alle anderen Pruefungen
bestehen.

WARUM TOLERANZEN
----------------
Die Kerzen laufen ueber SQLite (REAL) und pandas; Gleitkomma-Rundung macht
exakte Gleichheit unsinnig. Die Toleranz ist als Bruchteil eines Ticks
gewaehlt - grob genug fuer Rundung, fein genug, um einen echten Fehler
(falsche Kerze, falscher Faktor) sicher zu treffen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from backtest.strategies.base import BarContext
from common.config import Config
from ideas.model import RICHTUNG_LONG
from ideas.setups import hole_setup

# Ein Zehntel Tick. Bei MNQ sind das 0,025 Punkte - Rundungsfehler liegen
# um Groessenordnungen darunter, ein falscher ATR-Faktor darueber.
TOLERANZ_ANTEIL_TICK = 0.1


@dataclass
class Nachvollzug:
    """Ergebnis der Rueckrechnung einer Idee."""

    nachvollziehbar: bool
    kerze_gefunden: bool = False
    signal_bestaetigt: bool = False
    abweichungen: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nachvollziehbar": self.nachvollziehbar,
            "kerze_gefunden": self.kerze_gefunden,
            "signal_bestaetigt": self.signal_bestaetigt,
            "abweichungen": list(self.abweichungen),
        }


def _weicht_ab(ist: float, soll: float, toleranz: float) -> bool:
    if ist is None or soll is None:
        return True
    if math.isnan(ist) or math.isnan(soll):
        return True
    return abs(ist - soll) > toleranz


def pruefe_idee(
    idee: dict[str, Any],
    vorbereitet: pd.DataFrame,
    cfg: Config,
) -> Nachvollzug:
    """Rechnet eine gespeicherte Idee gegen die vorbereiteten Kerzen zurueck.

    ``vorbereitet`` ist ein Frame aus ``ideas.pipeline.vorbereiten`` - also mit
    denselben Indikatorspalten, die bei der Erkennung galten. Wer einen
    anders vorbereiteten Frame uebergibt, prueft etwas anderes.
    """
    ergebnis = Nachvollzug(nachvollziehbar=False)
    toleranz = cfg.market.tick_size * TOLERANZ_ANTEIL_TICK

    zeitpunkt = idee["erstellt_utc"]
    if isinstance(zeitpunkt, str):
        zeitpunkt = datetime.fromisoformat(zeitpunkt)
    marke = pd.Timestamp(zeitpunkt)
    if marke.tzinfo is None:
        marke = marke.tz_localize("UTC")

    if marke not in vorbereitet.index:
        ergebnis.abweichungen.append(
            f"Zu {marke.isoformat()} gibt es keine Kerze. Fehlt die Historie, "
            "oder stimmt der Zeitstempel nicht?"
        )
        return ergebnis

    ergebnis.kerze_gefunden = True
    zeile = vorbereitet.loc[marke]

    # -- 1. Einstieg ist der Schlusskurs jener Kerze ------------------------
    schluss = float(zeile["close"])
    if _weicht_ab(float(idee["entry"]), schluss, toleranz):
        ergebnis.abweichungen.append(
            f"entry {idee['entry']} passt nicht zum Schlusskurs {schluss} "
            f"der Kerze (Toleranz {toleranz})."
        )

    # -- 2. ATR-Bezug ------------------------------------------------------
    atr = float(zeile["atr"]) if "atr" in zeile else float("nan")
    if _weicht_ab(float(idee["atr_referenz"]), atr, toleranz):
        ergebnis.abweichungen.append(
            f"atr_referenz {idee['atr_referenz']} passt nicht zum ATR {atr} "
            "der Kerze. Wurde mit anderen Indikator-Parametern gerechnet?"
        )

    # -- 3. Stop und Ziel aus Einstieg und Faktoren ------------------------
    vorzeichen = 1.0 if idee["richtung"] == RICHTUNG_LONG else -1.0
    stop_soll = float(idee["entry"]) - vorzeichen * float(idee["stop_atr"]) * float(
        idee["atr_referenz"]
    )
    ziel_soll = float(idee["entry"]) + vorzeichen * float(idee["ziel_atr"]) * float(
        idee["atr_referenz"]
    )
    if _weicht_ab(float(idee["stop"]), stop_soll, toleranz):
        ergebnis.abweichungen.append(
            f"stop {idee['stop']} laesst sich nicht aus entry und stop_atr "
            f"bilden (erwartet {stop_soll:.4f})."
        )
    if _weicht_ab(float(idee["ziel"]), ziel_soll, toleranz):
        ergebnis.abweichungen.append(
            f"ziel {idee['ziel']} laesst sich nicht aus entry und ziel_atr "
            f"bilden (erwartet {ziel_soll:.4f})."
        )

    # -- 4. War die Einstiegsbedingung wirklich erfuellt? -------------------
    # Der eigentliche Kern: ohne diese Pruefung bestuende eine frei erfundene
    # Zeile alle vorherigen.
    position = vorbereitet.index.get_loc(marke)
    if position == 0:
        ergebnis.abweichungen.append(
            "Die Kerze ist die erste im Frame - ohne Vorkerze laesst sich "
            "keine Flanke pruefen. Mehr Historie laden."
        )
    else:
        try:
            definition = hole_setup(idee["setup"])
        except KeyError:
            ergebnis.abweichungen.append(
                f"Setup {idee['setup']!r} steht nicht in der Bibliothek."
            )
        else:
            strategie = definition.baue(cfg.ideas.setup_parameter(idee["setup"]))
            regel = (
                strategie.long_entry
                if idee["richtung"] == RICHTUNG_LONG
                else strategie.short_entry
            )
            ctx = BarContext(
                row=zeile,
                previous=vorbereitet.iloc[position - 1],
                timestamp=marke,
                position=0,
                bars_in_trade=0,
            )
            if regel is not None and regel.evaluate(ctx):
                ergebnis.signal_bestaetigt = True
            else:
                ergebnis.abweichungen.append(
                    f"Die Einstiegsregel von {idee['setup']}/{idee['richtung']} "
                    "war auf dieser Kerze NICHT erfuellt. Wurden die "
                    "Setup-Parameter seit der Protokollierung geaendert?"
                )

    ergebnis.nachvollziehbar = not ergebnis.abweichungen
    return ergebnis


def pruefe_alle(
    ideen: list[dict[str, Any]],
    vorbereitet: pd.DataFrame,
    cfg: Config,
) -> tuple[int, list[tuple[dict[str, Any], Nachvollzug]]]:
    """Alle Ideen pruefen. Rueckgabe: (Anzahl gut, Liste der Beanstandungen).

    Die Beanstandungen werden vollstaendig zurueckgegeben, nicht nur gezaehlt -
    eine Zahl allein sagt nicht, ob ein systematischer Fehler vorliegt oder
    ein Einzelfall.
    """
    beanstandet: list[tuple[dict[str, Any], Nachvollzug]] = []
    gut = 0
    for idee in ideen:
        ergebnis = pruefe_idee(idee, vorbereitet, cfg)
        if ergebnis.nachvollziehbar:
            gut += 1
        else:
            beanstandet.append((idee, ergebnis))
    return gut, beanstandet


__all__ = ["TOLERANZ_ANTEIL_TICK", "Nachvollzug", "pruefe_alle", "pruefe_idee"]
