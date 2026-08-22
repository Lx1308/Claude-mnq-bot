"""Datenmodell der Ideen-Protokollierung (Etappe C).

ZWEI GETRENNTE LOGS, NIE VERMISCHT
----------------------------------
``TradeIdee`` (Tabelle ``ideen``) haelt feste, regelbasierte Setups fest und
ist die Grundlage der spaeteren Erwartungswert-Rechnung.

``Beobachtung`` (Tabelle ``observations``) ist das Exploration-Log: freie
Notizen ohne feste Regel, die **nie** in ``evaluate_past_ideas`` einfliessen.
Die Trennung ist zwingend, weil eine LLM-Einschaetzung nicht reproduzierbar
ist - zwei Aufrufe mit gleichen Daten koennen abweichen. Als Ideenquelle fuer
kuenftige feste Setups ist sie trotzdem wertvoll, deshalb wird sie
protokolliert statt verworfen.

WARUM MANUELL-ASSISTIERTE IDEEN TROTZDEM INS HAUPT-LOG GEHOEREN
---------------------------------------------------------------
``quelle`` unterscheidet ``regel`` von ``manuell_assistiert``. Beide stehen
in derselben Tabelle und laufen beide durch die Auswertung. Der Unterschied
zur abgelehnten LLM-Protokollierung liegt nicht darin, *wer* die Idee
ausgeloest hat, sondern darin, dass hier feste, protokollierte Werte
vorliegen (Einstieg, Stop, Ziel, Zeitpunkt) statt einer nachtraeglichen
freien Einschaetzung. Die Reproduzierbarkeit bleibt damit erfuellt.

NACHSPIELBAR, NICHT NUR ERGEBNISORIENTIERT
------------------------------------------
Bewusst **kein** Ergebnisfeld (Gewinn/Verlust). Das Ergebnis entsteht erst
durch ``evaluate_past_ideas`` unter einem bestimmten Regelwerk. Stuende es
hier, gaebe es zwei Wahrheiten, je nachdem wann man hinschaut.

Damit die Auswertung den Trade wirklich nachspielen kann, werden neben den
Eckdaten die **Bemessungsgrundlagen** mitgeschrieben: ``atr_referenz``,
``stop_atr`` und ``ziel_atr``. Der Grund steht bei ``entry``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Herkunft einer Idee. Beide landen im selben Log, damit sich spaeter
# auswerten laesst, ob assistierte Entscheidungen anders abschneiden als
# rein regelbasierte.
QUELLE_REGEL = "regel"
QUELLE_MANUELL = "manuell_assistiert"
ALLE_QUELLEN: tuple[str, ...] = (QUELLE_REGEL, QUELLE_MANUELL)

RICHTUNG_LONG = "long"
RICHTUNG_SHORT = "short"
ALLE_RICHTUNGEN: tuple[str, ...] = (RICHTUNG_LONG, RICHTUNG_SHORT)


class UngueltigeIdee(ValueError):
    """Die Idee ist in sich nicht schluessig und wird nicht gespeichert."""


@dataclass(frozen=True)
class TradeIdee:
    """Eine protokollierte Idee des Haupt-Logs.

    ``erstellt_utc`` ist der **Schlusszeitpunkt der Signalkerze**, nicht der
    Zeitpunkt des Datenbankschreibens. Nur so ist die Idee spaeter gegen die
    Kerzen in ``ntbridge.sqlite3`` nachvollziehbar.
    """

    instrument: str
    setup: str
    richtung: str
    timeframe: str
    erstellt_utc: datetime

    # ``entry`` ist der SCHLUSSKURS der Signalkerze - eine Referenz, keine
    # Fill-Annahme. Die Backtest-Engine fuellt zur Eroeffnung der Folgekerze,
    # und genauso rechnet die Auswertung. Weil der tatsaechliche Fill damit
    # vom hier gespeicherten Wert abweicht, werden zusaetzlich
    # ``atr_referenz``, ``stop_atr`` und ``ziel_atr`` mitgeschrieben: daraus
    # laesst sich Stop und Ziel relativ zum echten Fill exakt neu bilden.
    # Ohne diese drei Felder waere das R-Vielfache nicht rekonstruierbar.
    entry: float
    stop: float
    ziel: float
    crv: float
    unter_crv_schwelle: bool

    atr_referenz: float
    stop_atr: float
    ziel_atr: float

    quelle: str
    profil: str

    # Von mindestens einem Filter abgelehnt. Die Idee wird trotzdem
    # gespeichert - sonst liesse sich weder pruefen, ob ein Filter zu scharf
    # steht, noch die Frage beantworten, wie viele Ideen ein Regelwerk
    # verhindert haette.
    gefiltert: bool = False
    filter_gruende: tuple[str, ...] = ()
    # Filter, die ihre Frage nicht beantworten konnten (dritter Ausgang).
    ungeprueft: tuple[str, ...] = ()
    # Werte der Filter zum Signalzeitpunkt, fuer spaetere Nachvollziehbarkeit.
    filter_context: dict[str, Any] = field(default_factory=dict)

    # Freitext. Wird ausdruecklich nie fuer die Auswertung genutzt.
    notiz: str | None = None

    def __post_init__(self) -> None:
        if self.richtung not in ALLE_RICHTUNGEN:
            raise UngueltigeIdee(
                f"richtung muss {' oder '.join(ALLE_RICHTUNGEN)} sein, war {self.richtung!r}."
            )
        if self.quelle not in ALLE_QUELLEN:
            raise UngueltigeIdee(
                f"quelle muss {' oder '.join(ALLE_QUELLEN)} sein, war {self.quelle!r}."
            )
        if self.erstellt_utc.tzinfo is None:
            raise UngueltigeIdee(
                "erstellt_utc muss zeitzonenbehaftet sein. Ein naiver Zeitstempel "
                "waere spaeter nicht eindeutig gegen die Kerzen zuzuordnen."
            )
        # Stop auf der falschen Seite waere keine Idee, sondern ein Rechenfehler.
        # Lieber hier abbrechen als eine unsinnige Zeile in die Statistik lassen.
        if self.richtung == RICHTUNG_LONG and not self.stop < self.entry < self.ziel:
            raise UngueltigeIdee(
                f"Long-Idee braucht stop < entry < ziel, war "
                f"{self.stop} / {self.entry} / {self.ziel}."
            )
        if self.richtung == RICHTUNG_SHORT and not self.ziel < self.entry < self.stop:
            raise UngueltigeIdee(
                f"Short-Idee braucht ziel < entry < stop, war "
                f"{self.ziel} / {self.entry} / {self.stop}."
            )

    @property
    def risiko_punkte(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def chance_punkte(self) -> float:
        return abs(self.ziel - self.entry)

    def filter_context_json(self) -> str:
        return json.dumps(
            self.filter_context, ensure_ascii=False, sort_keys=True, default=str
        )


@dataclass(frozen=True)
class Beobachtung:
    """Ein Eintrag des Exploration-Logs.

    Bewusst schlanker als :class:`TradeIdee`: hier steht keine Regel
    dahinter, die geprueft werden muesste. Entsprechend gibt es weder
    Einstieg noch Stop noch CRV - eine Beobachtung ist kein Trade.
    """

    instrument: str
    beschreibung: str
    erstellt_utc: datetime
    chart_kontext: dict[str, Any] = field(default_factory=dict)
    # Verweis auf einen Setup-Schluessel, falls aus der Beobachtung spaeter
    # ein festes Setup wurde. Bis dahin None.
    wurde_festes_setup: str | None = None

    def __post_init__(self) -> None:
        if self.erstellt_utc.tzinfo is None:
            raise UngueltigeIdee("erstellt_utc muss zeitzonenbehaftet sein.")
        if not self.beschreibung.strip():
            raise UngueltigeIdee(
                "Eine Beobachtung ohne Beschreibung traegt keine Information."
            )

    def chart_kontext_json(self) -> str:
        return json.dumps(
            self.chart_kontext, ensure_ascii=False, sort_keys=True, default=str
        )


def berechne_crv(entry: float, stop: float, ziel: float) -> float:
    """Chance-Risiko-Verhaeltnis aus den drei Marken.

    Rueckgabe 0.0 bei verschwindendem Risiko - ein unendliches CRV waere
    kein Erkenntnisgewinn, sondern ein Hinweis auf kaputte Eingangsdaten.
    """
    risiko = abs(entry - stop)
    if risiko <= 0.0:
        return 0.0
    return abs(ziel - entry) / risiko


def jetzt_utc() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "ALLE_QUELLEN",
    "ALLE_RICHTUNGEN",
    "QUELLE_MANUELL",
    "QUELLE_REGEL",
    "RICHTUNG_LONG",
    "RICHTUNG_SHORT",
    "Beobachtung",
    "TradeIdee",
    "UngueltigeIdee",
    "berechne_crv",
    "jetzt_utc",
]
