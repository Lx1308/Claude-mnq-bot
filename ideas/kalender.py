"""Blackout-Pruefung fuer die Ideen-Protokollierung.

WOZU DIESE SCHICHT UEBERHAUPT
-----------------------------
``CalendarService.event_risk(now=...)`` nimmt einen beliebigen Zeitpunkt
entgegen und beantwortet, ob er in einem Termin-Blackout liegt. Die
Terminliste dahinter stammt aber von Forex Factory und umfasst im
Wesentlichen die **laufende Woche**.

Fragt man diese Schnittstelle nach einem Zeitpunkt von vor drei Wochen,
findet sie dort keinen Termin und meldet ``blackout.aktiv = False``. Das
sieht aus wie "geprueft, alles frei", ist aber "der Kalender kennt diesen
Zeitraum gar nicht". Genau diese Verwechslung - Ausfall sieht aus wie
Entwarnung - hat das Projekt schon einmal getroffen (Bug-Lehre 6, damals
beim nicht erreichbaren Kalender).

Deshalb liegt hier eine **Abdeckungsgrenze** davor: Zeitpunkte ausserhalb
des Fensters werden mit ``None`` beantwortet. ``filters.filter_blackout``
macht daraus den dritten Ausgang "nicht pruefbar", und die Idee wird
protokolliert, ohne dass jemand sie faelschlich fuer geprueft haelt.

PRAKTISCHE FOLGE FUER DEN BETRIEB
---------------------------------
Ein Protokollierungslauf, der **zeitnah** ueber frische Kerzen laeuft,
bekommt eine echte Blackout-Antwort. Ein nachtraeglicher Lauf ueber alte
Historie bekommt "nicht pruefbar" - richtig so, aber ein Grund, den Lauf
regelmaessig laufen zu lassen statt einmal im Monat aufzuholen.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from common.logging_setup import log_event

log = logging.getLogger(__name__)


class Terminquelle(Protocol):
    """Was von ``CalendarService`` gebraucht wird - nicht mehr.

    Als Protokoll formuliert, damit ``ideas`` nicht hart an ``mcp_server``
    haengt. Verdrahtet wird die konkrete Klasse erst im Einstiegspunkt.
    """

    async def event_risk(
        self, *, now: datetime | None = ..., symbol: str | None = ...
    ) -> dict[str, Any]:
        ...


class KalenderBlackout:
    """Beantwortet "lag dieser Zeitpunkt in einem Termin-Blackout?".

    Rueckgabe ``True``/``False`` innerhalb der Abdeckung, sonst ``None``.
    """

    def __init__(
        self,
        quelle: Terminquelle,
        *,
        max_alter_tage: float,
        symbol: str | None = None,
        jetzt: datetime | None = None,
    ) -> None:
        self._quelle = quelle
        self._symbol = symbol
        self._jetzt = jetzt or datetime.now(timezone.utc)
        self._max_alter = timedelta(days=max_alter_tage)
        # Einmal gemeldet reicht - sonst flutet ein Nachhol-Lauf das Log.
        self._ausserhalb_gemeldet = False
        self._ausserhalb_gezaehlt = 0

    @property
    def ausserhalb_der_abdeckung(self) -> int:
        """Wie oft die Frage mangels Kalenderabdeckung offen blieb."""
        return self._ausserhalb_gezaehlt

    def deckt_ab(self, zeitpunkt: datetime) -> bool:
        """Kann der Kalender ueber diesen Zeitpunkt ueberhaupt Auskunft geben?

        Zukunft ist unproblematisch: dort stehen die Termine ja. Nur zu weit
        zurueckliegende Zeitpunkte fallen heraus.
        """
        return (self._jetzt - zeitpunkt) <= self._max_alter

    def __call__(self, zeitpunkt: datetime) -> bool | None:
        if not self.deckt_ab(zeitpunkt):
            self._ausserhalb_gezaehlt += 1
            if not self._ausserhalb_gemeldet:
                self._ausserhalb_gemeldet = True
                log_event(
                    log,
                    "ideen.blackout.ausserhalb_abdeckung",
                    "Kalender deckt diesen Zeitraum nicht ab - Blackout bleibt "
                    "ungeprueft statt als 'frei' zu gelten.",
                    level=logging.INFO,
                    aeltester_zeitpunkt=zeitpunkt.isoformat(),
                    max_alter_tage=self._max_alter.days,
                )
            return None

        ergebnis = asyncio.run(
            self._quelle.event_risk(now=zeitpunkt, symbol=self._symbol)
        )

        # Der Kalender selbst war nicht erreichbar. Auch das ist "nicht
        # pruefbar" und ausdruecklich nicht "keine Termine".
        if not ergebnis.get("calendar_available", False):
            return None

        blackout = ergebnis.get("blackout") or {}
        aktiv = blackout.get("aktiv")
        return None if aktiv is None else bool(aktiv)


__all__ = ["KalenderBlackout", "Terminquelle"]
