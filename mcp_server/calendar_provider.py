"""Wirtschaftskalender hinter einem austauschbaren Interface.

Warum zwei Quellen
------------------
Geprueft am 31.07.2026: der Forex-Factory-Wochenfeed liefert genau
``title, country, date, impact, forecast, previous`` - **kein ``actual``**.
Er deckt damit Terminliste, Impact-Stufe, Minutengenauigkeit und Blackout
ab, aber nicht die veroeffentlichten Zahlen.

FRED liefert die tatsaechlichen Werte, dafuer nur fuer eine ueberschaubare
Menge offizieller Reihen und mit Verzoegerung nach der Veroeffentlichung.
Beides zusammen deckt die Anforderung ab; was keine Quelle hergibt (ISM,
Fed-Reden), bleibt ``null``.

Austauschbarkeit
----------------
Alles laeuft ueber :class:`CalendarProvider`. Ein anderer Anbieter
implementiert dieselbe Methode und wird in :class:`CalendarService`
eingehaengt - der Rest des Servers merkt nichts davon.

Fail-safe
---------
Ist eine Quelle nicht erreichbar, wird ``calendar_available: false``
gemeldet. **Niemals** "keine Termine" - das waere die gefaehrlichste
moegliche Falschaussage kurz vor einem FOMC.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import httpx

from common.logging_setup import log_event

log = logging.getLogger(__name__)

FOREX_FACTORY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Termine, die fuer MNQ und MGC tatsaechlich Bewegung machen. Die Zuordnung
# ist bewusst klein und handgepflegt - eine automatische Zuordnung waere
# ungenauer als gar keine.
FRED_SERIES_BY_KEYWORD: dict[str, tuple[str, str]] = {
    "core cpi": ("CPILFESL", "Kern-VPI (Index)"),
    "cpi": ("CPIAUCSL", "VPI (Index)"),
    "core ppi": ("PPILFE", "Kern-EPI (Index)"),
    "ppi": ("PPIACO", "EPI (Index)"),
    "core pce": ("PCEPILFE", "Kern-PCE (Index)"),
    "non-farm employment": ("PAYEMS", "Beschaeftigte ausserhalb der Landwirtschaft"),
    "unemployment claims": ("ICSA", "Erstantraege Arbeitslosenhilfe"),
    "retail sales": ("RSAFS", "Einzelhandelsumsaetze"),
}

# Termine ohne brauchbare Gratisquelle fuer den Actual-Wert.
NO_ACTUAL_SOURCE = ("ism", "pmi", "fed chair", "fomc member", "speaks", "testimony")


@dataclass
class EconomicEvent:
    """Ein Kalendereintrag."""

    title: str
    country: str
    timestamp: datetime          # immer UTC
    impact: str                  # "High" | "Medium" | "Low"
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    actual_source: str | None = None
    actual_note: str | None = None

    def minutes_from(self, now: datetime) -> float:
        return (self.timestamp - now).total_seconds() / 60.0

    def to_dict(self, now: datetime) -> dict[str, Any]:
        delta = self.minutes_from(now)
        return {
            "titel": self.title,
            "waehrung": self.country,
            "zeit_utc": self.timestamp.isoformat(),
            "impact": self.impact,
            "minuten_bis_termin": round(delta, 1),
            "bereits_veroeffentlicht": delta < 0,
            "forecast": self.forecast,
            "previous": self.previous,
            "actual": self.actual,
            "actual_quelle": self.actual_source,
            "actual_hinweis": self.actual_note,
        }


class CalendarProviderError(RuntimeError):
    """Der Anbieter konnte nicht abgefragt werden."""


class CalendarProvider(Protocol):
    """Schnittstelle fuer Kalenderanbieter."""

    name: str

    async def fetch_events(self) -> list[EconomicEvent]:
        ...


# ---------------------------------------------------------------------------
# TTL-Cache
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class TtlCache:
    """Minimaler In-Memory-Cache. Termine aendern sich nicht im Minutentakt."""

    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: str, ttl_seconds: float, factory) -> Any:
        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at > time.monotonic():
                return entry.value

        value = await factory()

        async with self._lock:
            self._entries[key] = _CacheEntry(
                value=value, expires_at=time.monotonic() + ttl_seconds
            )
        return value

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------------------
# Forex Factory - Terminliste
# ---------------------------------------------------------------------------

class ForexFactoryProvider:
    """Wochenkalender von Forex Factory.

    Inoffizieller Endpunkt ohne Zusicherung. Faellt er aus, meldet der
    Service ``calendar_available: false`` - genau dafuer ist das Feld da.
    """

    name = "forex_factory"

    def __init__(self, url: str = FOREX_FACTORY_URL, timeout: float = 15.0) -> None:
        self._url = url
        self._timeout = timeout

    async def fetch_events(self) -> list[EconomicEvent]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(self._url)
                response.raise_for_status()
                raw = response.json()
        except Exception as exc:  # noqa: BLE001
            raise CalendarProviderError(f"Forex Factory nicht erreichbar: {exc}") from exc

        events: list[EconomicEvent] = []
        for entry in raw if isinstance(raw, list) else []:
            timestamp = self._parse_timestamp(entry.get("date"))
            if timestamp is None:
                continue
            events.append(
                EconomicEvent(
                    title=str(entry.get("title", "")).strip(),
                    country=str(entry.get("country", "")).strip().upper(),
                    timestamp=timestamp,
                    impact=str(entry.get("impact", "")).strip() or "Unknown",
                    forecast=_blank_to_none(entry.get("forecast")),
                    previous=_blank_to_none(entry.get("previous")),
                )
            )
        events.sort(key=lambda event: event.timestamp)
        return events

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime | None:
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


def _blank_to_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


# ---------------------------------------------------------------------------
# FRED - veroeffentlichte Werte
# ---------------------------------------------------------------------------

class FredProvider:
    """Holt tatsaechliche Werte fuer eine kuratierte Menge Reihen.

    Wichtige Einschraenkung, die im Ergebnis auch so ausgewiesen wird: FRED
    uebernimmt eine Veroeffentlichung erst mit einiger Verzoegerung. Fuer
    einen Termin, der vor Minuten gelaufen ist, steht dort in aller Regel
    noch nichts. Der Wert taugt fuer die Einordnung des Tages, nicht fuer
    die Reaktion in der ersten Minute.
    """

    name = "fred"

    def __init__(self, api_key: str | None, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @staticmethod
    def series_for(title: str) -> tuple[str, str] | None:
        lowered = title.lower()
        for keyword, mapping in FRED_SERIES_BY_KEYWORD.items():
            if keyword in lowered:
                return mapping
        return None

    async def latest_observation(self, series_id: str) -> tuple[str, str] | None:
        """Liefert (Wert, Datum) der juengsten Beobachtung."""
        if not self._api_key:
            return None
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(FRED_BASE_URL, params=params)
                response.raise_for_status()
                observations = response.json().get("observations", [])
        except Exception as exc:  # noqa: BLE001 - fehlender Actual ist kein Beinbruch
            log_event(
                log,
                "calendar.fred.failed",
                f"FRED-Abfrage fuer {series_id} fehlgeschlagen: {exc}",
                level=logging.WARNING,
                series=series_id,
                error=str(exc),
            )
            return None

        if not observations:
            return None
        entry = observations[0]
        value = str(entry.get("value", "")).strip()
        if not value or value == ".":
            return None
        return value, str(entry.get("date", ""))

    async def fetch_events(self) -> list[EconomicEvent]:
        """FRED liefert keinen Terminkalender - nur Werte zu bekannten Reihen."""
        return []


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@dataclass
class CalendarSettings:
    currencies: tuple[str, ...] = ("USD",)
    impacts: tuple[str, ...] = ("High",)
    blackout_minutes_before: float = 15.0
    blackout_minutes_after: float = 15.0
    schedule_cache_seconds: float = 1800.0     # 30 Minuten
    actual_cache_seconds: float = 21600.0      # 6 Stunden
    upcoming_limit: int = 8


class CalendarService:
    """Verbindet Terminliste und Actuals, cached beides."""

    def __init__(
        self,
        schedule_provider: CalendarProvider,
        fred: FredProvider | None = None,
        settings: CalendarSettings | None = None,
    ) -> None:
        self._schedule = schedule_provider
        self._fred = fred
        self._settings = settings or CalendarSettings()
        self._cache = TtlCache()

    async def _events(self) -> list[EconomicEvent]:
        return await self._cache.get_or_set(
            f"schedule:{self._schedule.name}",
            self._settings.schedule_cache_seconds,
            self._schedule.fetch_events,
        )

    async def _enrich_with_actuals(
        self, events: list[EconomicEvent], now: datetime
    ) -> None:
        """Ergaenzt Actuals fuer bereits gelaufene Termine des Tages."""
        if self._fred is None or not self._fred.available:
            for event in events:
                if event.minutes_from(now) < 0:
                    event.actual_note = (
                        "Kein FRED_API_KEY gesetzt - Actual nicht abrufbar."
                    )
            return

        for event in events:
            if event.minutes_from(now) >= 0:
                continue

            if any(token in event.title.lower() for token in NO_ACTUAL_SOURCE):
                event.actual_note = (
                    "Fuer diesen Termin gibt es keine brauchbare Gratisquelle "
                    "fuer den Actual-Wert (z.B. ISM-Lizenz, Redebeitraege)."
                )
                continue

            mapping = self._fred.series_for(event.title)
            if mapping is None:
                event.actual_note = "Keine FRED-Reihe zugeordnet."
                continue

            series_id, description = mapping
            observation = await self._cache.get_or_set(
                f"fred:{series_id}",
                self._settings.actual_cache_seconds,
                lambda sid=series_id: self._fred.latest_observation(sid),
            )
            if observation is None:
                event.actual_note = f"FRED-Reihe {series_id} lieferte keinen Wert."
                continue

            value, as_of = observation
            event.actual = value
            event.actual_source = f"FRED:{series_id}"
            event.actual_note = (
                f"{description}, Stand {as_of}. FRED uebernimmt Veroeffentlichungen "
                "verzoegert - direkt nach dem Termin steht hier meist noch der "
                "Vorwert."
            )

    def _relevant(self, events: list[EconomicEvent]) -> list[EconomicEvent]:
        """Filtert und sortiert chronologisch.

        Die Sortierung gehoert hierher und nicht in den Anbieter: sonst
        haengt "naechster Termin" davon ab, ob eine fremde Quelle zufaellig
        sortiert liefert - ein Fehler, der erst beim Anbieterwechsel
        auffiele, und dann an der falschen Stelle.
        """
        currencies = {c.upper() for c in self._settings.currencies}
        impacts = {i.lower() for i in self._settings.impacts}
        filtered = [
            event for event in events
            if event.country in currencies and event.impact.lower() in impacts
        ]
        return sorted(filtered, key=lambda event: event.timestamp)

    async def event_risk(
        self, *, now: datetime | None = None, symbol: str | None = None
    ) -> dict[str, Any]:
        """Baut das Ergebnis fuer ``get_event_risk``."""
        now = now or datetime.now(timezone.utc)
        settings = self._settings

        try:
            all_events = await self._events()
        except CalendarProviderError as exc:
            log_event(
                log,
                "calendar.unavailable",
                f"Kalender nicht abrufbar: {exc}",
                level=logging.WARNING,
                error=str(exc),
            )
            return {
                "calendar_available": False,
                "reason": str(exc),
                "hinweis": (
                    "Es wird ausdruecklich NICHT 'keine Termine' gemeldet. "
                    "Behandle die Lage wie unbekanntes Terminrisiko."
                ),
                "symbol": symbol,
                "abgefragt_utc": now.isoformat(),
            }

        relevant = self._relevant(all_events)
        await self._enrich_with_actuals(
            [event for event in relevant if -1440 < event.minutes_from(now) < 0], now
        )

        upcoming = [event for event in relevant if event.minutes_from(now) >= 0]
        released_today = [
            event for event in relevant
            if -1440 < event.minutes_from(now) < 0
            and event.timestamp.date() == now.date()
        ]

        next_event = upcoming[0] if upcoming else None
        minutes_to_next = next_event.minutes_from(now) if next_event else None

        in_blackout = False
        blackout_trigger = None
        for event in relevant:
            delta = event.minutes_from(now)
            if -settings.blackout_minutes_after <= delta <= settings.blackout_minutes_before:
                in_blackout = True
                blackout_trigger = event
                break

        return {
            "calendar_available": True,
            "symbol": symbol,
            "abgefragt_utc": now.isoformat(),
            "quelle_termine": self._schedule.name,
            "quelle_actuals": (
                self._fred.name if self._fred and self._fred.available else None
            ),
            "gefiltert_nach": {
                "waehrungen": list(settings.currencies),
                "impact": list(settings.impacts),
            },
            "blackout": {
                "aktiv": in_blackout,
                "fenster_minuten_vor": settings.blackout_minutes_before,
                "fenster_minuten_nach": settings.blackout_minutes_after,
                "ausgeloest_durch": (
                    blackout_trigger.to_dict(now) if blackout_trigger else None
                ),
            },
            "naechster_termin": next_event.to_dict(now) if next_event else None,
            "minuten_bis_naechstem_termin": (
                round(minutes_to_next, 1) if minutes_to_next is not None else None
            ),
            "kommende_termine": [
                event.to_dict(now) for event in upcoming[: settings.upcoming_limit]
            ],
            "heute_veroeffentlicht": [event.to_dict(now) for event in released_today],
            "hinweis_actuals": (
                "Forex Factory liefert keine Actual-Werte. Sie stammen aus FRED "
                "und erscheinen dort erst mit Verzoegerung nach der "
                "Veroeffentlichung. ISM/PMI und Redebeitraege bleiben null."
            ),
        }


__all__ = [
    "FOREX_FACTORY_URL",
    "CalendarProvider",
    "CalendarProviderError",
    "CalendarService",
    "CalendarSettings",
    "EconomicEvent",
    "ForexFactoryProvider",
    "FredProvider",
    "TtlCache",
]
