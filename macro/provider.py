"""Anbieter fuer Makro-Vintages (FRED/ALFRED) und die kuenftige Kalender-Anbindung.

WARUM NICHT ``mcp_server/calendar_provider.py::FredProvider`` WIEDERVERWENDET
--------------------------------------------------------------------------------
Jene Klasse holt bewusst nur die JUENGSTE Beobachtung (``latest_observation``,
ein Live-Blick fuer den heutigen Snapshot). ALFRED-Vintages brauchen die
VOLLSTAENDIGE Revisionshistorie einer Reihe - ein anderer API-Aufruf
(``realtime_start``/``realtime_end`` als Spanne statt als "heute"), ein
anderer Ruecksprungtyp (mehrere Zeilen statt eine). Eine gemeinsame Basis
haette mehr Kopplung erzeugt als sie erspart.

DIE KURATIERTE SERIENLISTE IST BEWUSST DUPLIZIERT, NICHT IMPORTIERT
------------------------------------------------------------------------
Dieselben acht FRED-Reihen stehen bereits in
``mcp_server/calendar_provider.py::FRED_SERIES_BY_KEYWORD`` (dort als
Text-Zuordnung fuer Forex-Factory-Titel). Ein Import von hier nach dort
wuerde die Research-Schicht von der Live-MCP-Schicht abhaengig machen -
die falsche Richtung (Masterplan D: "Jede Schicht darf nur nach unten
greifen"). Die kleine Dopplung ist der Preis fuer saubere Schichtung.

FEHLSCHLAG DARF NIEMALS WIE "KEINE REVISION" AUSSEHEN
----------------------------------------------------------
Analog zu ``CalendarProviderError`` in ``mcp_server/calendar_provider.py``:
ein nicht erreichbares ALFRED liefert eine leere Liste zurueckzugeben waere
so gefaehrlich wie beim Wirtschaftskalender - der Aufrufer wuerde "keine
neuen Daten" nicht von "Netzwerk kaputt" unterscheiden koennen.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

from common.logging_setup import log_event
from macro.model import MacroObservation

log = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
# FRED-Sentinel fuer "alle jemals gueltigen Vintages", siehe FRED-API-Doku
# zu realtime_start/realtime_end.
ALFRED_REALTIME_START = "1776-07-04"
ALFRED_REALTIME_END = "9999-12-31"

# Dieselben acht Reihen wie in mcp_server/calendar_provider.py -
# absichtlich dupliziert, siehe Moduldocstring.
STANDARD_SERIEN: dict[str, str] = {
    "CPIAUCSL": "VPI (Index)",
    "CPILFESL": "Kern-VPI (Index)",
    "PPIACO": "EPI (Index)",
    "PPILFE": "Kern-EPI (Index)",
    "PCEPILFE": "Kern-PCE (Index)",
    "PAYEMS": "Beschaeftigte ausserhalb der Landwirtschaft",
    "ICSA": "Erstantraege Arbeitslosenhilfe",
    "RSAFS": "Einzelhandelsumsaetze",
}


class MacroProviderError(RuntimeError):
    """Der Anbieter konnte nicht abgefragt werden - NICHT mit "keine Revisionen" verwechseln."""


def _parse_fred_datum(text: str) -> datetime:
    """FRED liefert Daten als 'YYYY-MM-DD', immer in US-Boersenzeit gemeint,
    hier aber als UTC-Mitternacht abgelegt - fuer eine tagesgenaue Reihe ist
    das die einzige verlustfreie Wahl ohne eine Zeitzone zu erfinden, die
    FRED nicht mitliefert."""
    jahr, monat, tag = (int(teil) for teil in text.split("-"))
    return datetime(jahr, monat, tag, tzinfo=timezone.utc)


class FredAlfredProvider:
    """Holt die vollstaendige Vintage-Historie kuratierter FRED-Reihen."""

    name = "fred_alfred"

    def __init__(
        self,
        api_key: str | None,
        timeout: float = 30.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        # Nur fuer Tests: httpx.MockTransport ersetzt die echte Verbindung,
        # ohne die Anfrage-/Antwortlogik unten zu duplizieren. Unveraendert
        # None im Betrieb - httpx waehlt dann den echten Transport.
        self._transport = transport

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def hole_vintages(self, series_id: str) -> list[MacroObservation]:
        """Alle Vintages einer Reihe, chronologisch nach ``available_at_utc``.

        ``revision`` wird hier aus der Position in der (von FRED bereits
        chronologisch sortierten) Antwort abgeleitet - keine Datenbankabfrage
        noetig, da jede Antwort bei 0 beginnt und lueckenlos zaehlt.
        """
        if not self._api_key:
            raise MacroProviderError(
                "FRED_API_KEY fehlt - ALFRED-Vintages koennen ohne Schluessel "
                "nicht abgefragt werden."
            )
        name = STANDARD_SERIEN.get(series_id, series_id)
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "realtime_start": ALFRED_REALTIME_START,
            "realtime_end": ALFRED_REALTIME_END,
            "sort_order": "asc",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(FRED_BASE_URL, params=params)
                response.raise_for_status()
                rohdaten = response.json().get("observations", [])
        except Exception as exc:  # noqa: BLE001
            raise MacroProviderError(
                f"ALFRED-Abfrage fuer {series_id} fehlgeschlagen: {exc}"
            ) from exc

        beobachtungen: list[MacroObservation] = []
        revision = 0
        for eintrag in rohdaten:
            wert = str(eintrag.get("value", "")).strip()
            if not wert or wert == ".":
                continue
            try:
                verfuegbar_ab = _parse_fred_datum(str(eintrag["realtime_start"]))
                periode = _parse_fred_datum(str(eintrag["date"]))
            except (KeyError, ValueError) as exc:
                log_event(
                    log,
                    "macro.fred.zeile_uebersprungen",
                    f"Unlesbare ALFRED-Zeile fuer {series_id} uebersprungen: {exc}",
                    level=logging.WARNING,
                    series=series_id,
                )
                continue

            beobachtungen.append(
                MacroObservation(
                    source=self.name,
                    source_event_id=f"{series_id}:{eintrag['date']}",
                    event_name=name,
                    event_type="macro_release",
                    beobachtungszeitraum_utc=periode,
                    available_at_utc=verfuegbar_ab,
                    released_at_utc=verfuegbar_ab,
                    revision=revision,
                    revision_at_utc=verfuegbar_ab,
                    actual=wert,
                    source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                )
            )
            revision += 1
        return beobachtungen


# ---------------------------------------------------------------------------
# Kalender-Anbieter-Abstraktion - Schnittstelle vorhanden, NICHTS angeschaltet
# ---------------------------------------------------------------------------

class EconomicCalendarProvider(Protocol):
    """Kuenftige Schnittstelle fuer einen kostenpflichtigen Kalenderanbieter
    (z.B. Trading Economics) - bewusst noch OHNE Implementierung.

    Grund: die Recherche zu Trading Economics nennt kein verifiziertes
    Preismodell und keinen belegten Point-in-Time-Endpunkt (nur Vermutungen:
    "vermutlich mehrere hundert $/Monat", keine Quellenlinks). Das
    widerspraeche der Kein-Erfinden-Regel und dem Kostenbewusstsein des
    Projekts - eine Implementierung folgt erst nach Verifikation.
    """

    name: str

    async def fetch_events(
        self, *, von: datetime, bis: datetime
    ) -> list[MacroObservation]:
        ...


def create_economic_calendar_provider() -> "EconomicCalendarProvider | None":
    """Liest ``ECONOMIC_CALENDAR_PROVIDER`` aus der Umgebung.

    Liefert ``None``, solange kein Wert gesetzt ist - das ist der
    Normalfall, bis ein Anbieter verifiziert und angebunden ist. Ein
    gesetzter, aber unbekannter Wert bricht laut ab statt still `None` zu
    liefern (Invariante 12: abbrechende Startpruefung statt stiller
    Fehlfunktion) - ein Tippfehler in der Env-Variable soll auffallen,
    nicht kommentarlos "kein Kalender" bedeuten.
    """
    wert = os.environ.get("ECONOMIC_CALENDAR_PROVIDER", "").strip().lower()
    if not wert:
        return None
    raise MacroProviderError(
        f"ECONOMIC_CALENDAR_PROVIDER={wert!r} ist gesetzt, aber es ist noch "
        "kein Kalenderanbieter implementiert (siehe Moduldocstring von "
        "EconomicCalendarProvider). Variable entfernen oder Anbieter zuerst "
        "verifizieren und anbinden."
    )


__all__ = [
    "ALFRED_REALTIME_END",
    "ALFRED_REALTIME_START",
    "STANDARD_SERIEN",
    "EconomicCalendarProvider",
    "FredAlfredProvider",
    "MacroProviderError",
    "create_economic_calendar_provider",
]
