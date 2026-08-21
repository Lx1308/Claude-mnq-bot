"""Datenmodell der Ideen-Protokollierung.

Eine *Trade-Idee* ist die regelbasierte Feststellung, dass zu einem
bestimmten Kerzenschluss eine Setup-Bedingung erfuellt war - zusammen mit
Einstieg, Stop, Ziel und CRV, wie sie sich **aus den Daten bis genau
diesem Zeitpunkt** ergeben.

Eine Idee ist ausdruecklich KEINE Order und keine Empfehlung. Sie wird
protokolliert, damit spaeter (Etappe D) ausgewertet werden kann, welche
Setups tatsaechlich einen Erwartungswert haben.

WARUM REGELBASIERT UND NICHT PER LLM
------------------------------------
Eine Regel ist auswertbar, nachjustierbar und spaeter automatisierbar.
Eine LLM-Einschaetzung ist nicht reproduzierbar - zwei Aufrufe mit
gleichen Daten koennen abweichen. Als Grundlage fuer "wird ueber die Zeit
besser" waere das unbrauchbar.

WARUM AUCH GEFILTERTE IDEEN GESPEICHERT WERDEN
----------------------------------------------
Wird eine Idee von einem Filter abgelehnt, verschwindet sie nicht - sie
wird mit ``gefiltert=True`` und den Ablehnungsgruenden abgelegt. Sonst
liesse sich spaeter weder pruefen, ob ein Filter zu scharf steht, noch die
Frage beantworten, wie viele Ideen ein Regelwerk verhindert haette.
Stilles Verwerfen ist in diesem Projekt generell unzulaessig.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
#  Setup-Namen
# ---------------------------------------------------------------------------
#  Als schlichte Zeichenketten und nicht als Enum: sie landen so wie sie
#  sind in der Datenbank und in der spaeteren Auswertung gruppiert danach.
#  Ein Enum brauchte an jeder Grenze eine Umwandlung, ohne Gewinn.

SETUP_PDH_BRUCH = "pdh_bruch"
SETUP_PDL_BRUCH = "pdl_bruch"
SETUP_VWAP_REVERSION = "vwap_reversion"
SETUP_IB_BRUCH_HOCH = "ib_bruch_hoch"
SETUP_IB_BRUCH_TIEF = "ib_bruch_tief"
SETUP_FLAGGE_HOCH = "flagge_ausbruch_hoch"
SETUP_FLAGGE_TIEF = "flagge_ausbruch_tief"

ALLE_SETUPS: tuple[str, ...] = (
    SETUP_PDH_BRUCH,
    SETUP_PDL_BRUCH,
    SETUP_VWAP_REVERSION,
    SETUP_IB_BRUCH_HOCH,
    SETUP_IB_BRUCH_TIEF,
    SETUP_FLAGGE_HOCH,
    SETUP_FLAGGE_TIEF,
)

# Setups, die auf Fortsetzung setzen (brauchen Trend), gegenueber solchen,
# die auf Rueckkehr setzen (brauchen Range). Der ADX-Filter wertet das aus.
SETUPS_FORTSETZUNG: frozenset[str] = frozenset(
    {
        SETUP_PDH_BRUCH,
        SETUP_PDL_BRUCH,
        SETUP_IB_BRUCH_HOCH,
        SETUP_IB_BRUCH_TIEF,
        SETUP_FLAGGE_HOCH,
        SETUP_FLAGGE_TIEF,
    }
)
SETUPS_REVERSION: frozenset[str] = frozenset({SETUP_VWAP_REVERSION})

RICHTUNG_LONG = "long"
RICHTUNG_SHORT = "short"


@dataclass(frozen=True)
class TradeIdee:
    """Eine protokollierte Idee.

    ``ts_utc`` ist der Schlusszeitpunkt der Kerze, auf der die Bedingung
    erfuellt war. Ausgefuehrt wuerde erst zur Eroeffnung der Folgekerze -
    genau wie im Backtest. Das ist der Grund, warum hier der Schlusskurs
    als ``entry`` steht und nicht ein spaeterer Preis: der Wert ist eine
    *Referenz*, keine Fill-Annahme. Die Auswertung in Etappe D setzt den
    tatsaechlichen Einstieg auf die Eroeffnung der naechsten Kerze.
    """

    instrument: str
    setup: str
    richtung: str
    ts_utc: datetime
    timeframe: str

    entry: float
    stop: float
    ziel: float

    risiko_punkte: float
    chance_punkte: float
    crv: float
    risiko_usd: float
    chance_usd: float

    # CRV unter der konfigurierten Schwelle. Die Idee wird trotzdem
    # protokolliert - nur eben markiert. Wegzulassen hiesse, den Datensatz
    # zugunsten der eigenen Erwartung zu beschneiden.
    crv_unter_schwelle: bool

    # Unter welchem Regelwerk die Idee entstanden ist ("demo"/"lucid").
    # EINE gemeinsame Datenbank mit diesem Feld - keine getrennten Logs.
    # Sonst liesse sich spaeter nicht mehr fragen, wie ein Setup unter dem
    # jeweils anderen Regelwerk abgeschnitten haette.
    profil: str

    # Von mindestens einem Filter abgelehnt.
    gefiltert: bool = False
    filter_gruende: tuple[str, ...] = ()

    # Kennzahlen zum Zeitpunkt der Erkennung. Die Auswertung darf
    # ausschliesslich hierauf zurueckgreifen und nicht auf spaetere Daten -
    # das ist der Lookahead-Schutz.
    snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def schluessel(self) -> tuple[str, str, str]:
        """Idempotenz-Schluessel: dieselbe Kerze ergibt dieselbe Idee."""
        return (self.instrument, self.setup, self.ts_utc.isoformat())

    def snapshot_json(self) -> str:
        return json.dumps(self.snapshot, ensure_ascii=False, sort_keys=True, default=str)


__all__ = [
    "ALLE_SETUPS",
    "RICHTUNG_LONG",
    "RICHTUNG_SHORT",
    "SETUPS_FORTSETZUNG",
    "SETUPS_REVERSION",
    "SETUP_FLAGGE_HOCH",
    "SETUP_FLAGGE_TIEF",
    "SETUP_IB_BRUCH_HOCH",
    "SETUP_IB_BRUCH_TIEF",
    "SETUP_PDH_BRUCH",
    "SETUP_PDL_BRUCH",
    "SETUP_VWAP_REVERSION",
    "TradeIdee",
]
