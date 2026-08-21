"""Tests des Wirtschaftskalenders (Tool 2) - ohne Netzzugriff."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from mcp_server.calendar_provider import (
    CalendarProviderError,
    CalendarService,
    CalendarSettings,
    EconomicEvent,
    ForexFactoryProvider,
    FredProvider,
    TtlCache,
)

UTC = timezone.utc
NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)


def event(
    title: str,
    minutes_from_now: float,
    *,
    impact: str = "High",
    country: str = "USD",
    forecast: str | None = "2.1%",
    previous: str | None = "2.0%",
) -> EconomicEvent:
    return EconomicEvent(
        title=title,
        country=country,
        timestamp=NOW + timedelta(minutes=minutes_from_now),
        impact=impact,
        forecast=forecast,
        previous=previous,
    )


class FakeSchedule:
    """Terminliste ohne Netz."""

    name = "fake"

    def __init__(self, events: list[EconomicEvent] | None = None, fail: bool = False) -> None:
        self._events = events or []
        self._fail = fail
        self.calls = 0

    async def fetch_events(self) -> list[EconomicEvent]:
        self.calls += 1
        if self._fail:
            raise CalendarProviderError("Feed nicht erreichbar (Test)")
        return list(self._events)


class FakeFred(FredProvider):
    def __init__(self, values: dict[str, tuple[str, str]] | None = None) -> None:
        super().__init__(api_key="test-key")
        self._values = values or {}
        self.calls = 0

    async def latest_observation(self, series_id: str):
        self.calls += 1
        return self._values.get(series_id)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fail-safe - der wichtigste Test
# ---------------------------------------------------------------------------

def test_nicht_erreichbarer_kalender_meldet_niemals_keine_termine():
    """Die gefaehrlichste moegliche Falschaussage kurz vor einem FOMC."""
    service = CalendarService(FakeSchedule(fail=True))
    result = run(service.event_risk(now=NOW, symbol="MNQ"))

    assert result["calendar_available"] is False
    assert "reason" in result
    assert "kommende_termine" not in result
    assert "naechster_termin" not in result
    assert "unbekanntes Terminrisiko" in result["hinweis"]


def test_erreichbarer_kalender_liefert_verfuegbar_true():
    service = CalendarService(FakeSchedule([event("CPI m/m", 120)]))
    result = run(service.event_risk(now=NOW))
    assert result["calendar_available"] is True


# ---------------------------------------------------------------------------
# Blackout
# ---------------------------------------------------------------------------

def test_blackout_greift_vor_dem_termin():
    service = CalendarService(FakeSchedule([event("FOMC Statement", 10)]))
    result = run(service.event_risk(now=NOW))

    assert result["blackout"]["aktiv"] is True
    assert result["blackout"]["ausgeloest_durch"]["titel"] == "FOMC Statement"


def test_blackout_greift_nach_dem_termin():
    service = CalendarService(FakeSchedule([event("CPI m/m", -8)]))
    result = run(service.event_risk(now=NOW))
    assert result["blackout"]["aktiv"] is True


def test_kein_blackout_ausserhalb_des_fensters():
    service = CalendarService(FakeSchedule([event("CPI m/m", 45)]))
    result = run(service.event_risk(now=NOW))
    assert result["blackout"]["aktiv"] is False
    assert result["blackout"]["ausgeloest_durch"] is None


def test_blackout_fenster_ist_konfigurierbar():
    settings = CalendarSettings(blackout_minutes_before=60, blackout_minutes_after=60)
    service = CalendarService(FakeSchedule([event("NFP", 45)]), settings=settings)
    result = run(service.event_risk(now=NOW))

    assert result["blackout"]["aktiv"] is True
    assert result["blackout"]["fenster_minuten_vor"] == 60


# ---------------------------------------------------------------------------
# Filterung
# ---------------------------------------------------------------------------

def test_nur_hochwirksame_usd_termine_werden_beruecksichtigt():
    events = [
        event("CPI m/m", 30),                              # USD/High -> relevant
        event("SPPI y/y", 20, impact="Low", country="JPY"),
        event("Retail Sales", 25, impact="Medium"),
    ]
    service = CalendarService(FakeSchedule(events))
    result = run(service.event_risk(now=NOW))

    titel = [entry["titel"] for entry in result["kommende_termine"]]
    assert titel == ["CPI m/m"]


def test_naechster_termin_ist_der_zeitlich_naechste():
    events = [event("NFP", 180), event("CPI m/m", 30), event("PPI m/m", 90)]
    service = CalendarService(FakeSchedule(events))
    result = run(service.event_risk(now=NOW))

    assert result["naechster_termin"]["titel"] == "CPI m/m"
    assert result["minuten_bis_naechstem_termin"] == pytest.approx(30.0)


def test_bereits_gelaufene_termine_landen_nicht_bei_den_kommenden():
    events = [event("CPI m/m", -120), event("NFP", 240)]
    service = CalendarService(FakeSchedule(events))
    result = run(service.event_risk(now=NOW))

    assert [e["titel"] for e in result["kommende_termine"]] == ["NFP"]
    assert [e["titel"] for e in result["heute_veroeffentlicht"]] == ["CPI m/m"]


def test_ohne_kommende_termine_ist_naechster_termin_none():
    service = CalendarService(FakeSchedule([event("CPI m/m", -300)]))
    result = run(service.event_risk(now=NOW))

    assert result["naechster_termin"] is None
    assert result["minuten_bis_naechstem_termin"] is None
    assert result["calendar_available"] is True   # nicht dasselbe wie "nicht erreichbar"


# ---------------------------------------------------------------------------
# Actuals aus FRED
# ---------------------------------------------------------------------------

def test_actual_wird_aus_fred_ergaenzt():
    fred = FakeFred({"CPIAUCSL": ("312.5", "2026-07-01")})
    service = CalendarService(FakeSchedule([event("CPI m/m", -60)]), fred=fred)
    result = run(service.event_risk(now=NOW))

    veroeffentlicht = result["heute_veroeffentlicht"][0]
    assert veroeffentlicht["actual"] == "312.5"
    assert veroeffentlicht["actual_quelle"] == "FRED:CPIAUCSL"
    assert "verzoegert" in veroeffentlicht["actual_hinweis"]


def test_ism_bleibt_ohne_actual_mit_begruendung():
    """Fuer ISM gibt es keine brauchbare Gratisquelle - also null, nicht geraten."""
    fred = FakeFred({"CPIAUCSL": ("312.5", "2026-07-01")})
    service = CalendarService(FakeSchedule([event("ISM Manufacturing PMI", -60)]), fred=fred)
    result = run(service.event_risk(now=NOW))

    veroeffentlicht = result["heute_veroeffentlicht"][0]
    assert veroeffentlicht["actual"] is None
    assert "keine brauchbare Gratisquelle" in veroeffentlicht["actual_hinweis"]


def test_fed_rede_bleibt_ohne_actual():
    service = CalendarService(
        FakeSchedule([event("Fed Chair Powell Speaks", -30)]), fred=FakeFred()
    )
    result = run(service.event_risk(now=NOW))
    assert result["heute_veroeffentlicht"][0]["actual"] is None


def test_ohne_fred_key_wird_das_ausgewiesen():
    service = CalendarService(
        FakeSchedule([event("CPI m/m", -60)]), fred=FredProvider(api_key=None)
    )
    result = run(service.event_risk(now=NOW))

    assert result["quelle_actuals"] is None
    assert "FRED_API_KEY" in result["heute_veroeffentlicht"][0]["actual_hinweis"]


def test_zukuenftige_termine_bekommen_keinen_actual():
    fred = FakeFred({"CPIAUCSL": ("312.5", "2026-07-01")})
    service = CalendarService(FakeSchedule([event("CPI m/m", 60)]), fred=fred)
    result = run(service.event_risk(now=NOW))

    assert result["kommende_termine"][0]["actual"] is None
    assert fred.calls == 0   # gar nicht erst abgefragt


def test_fred_zuordnung_trifft_die_kuratierten_reihen():
    fred = FredProvider(api_key="x")

    assert fred.series_for("CPI m/m")[0] == "CPIAUCSL"
    assert fred.series_for("Core CPI m/m")[0] == "CPILFESL"
    assert fred.series_for("Non-Farm Employment Change")[0] == "PAYEMS"
    assert fred.series_for("Unemployment Claims")[0] == "ICSA"
    assert fred.series_for("Irgendein Termin") is None


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def test_terminliste_wird_gecacht():
    schedule = FakeSchedule([event("CPI m/m", 60)])
    service = CalendarService(schedule)

    async def scenario():
        await service.event_risk(now=NOW)
        await service.event_risk(now=NOW)
        await service.event_risk(now=NOW)

    run(scenario())
    assert schedule.calls == 1, "Der Feed darf nicht bei jedem Aufruf geholt werden."


def test_ttl_cache_liefert_nach_ablauf_neu():
    cache = TtlCache()
    aufrufe = {"n": 0}

    async def factory():
        aufrufe["n"] += 1
        return aufrufe["n"]

    async def scenario():
        erst = await cache.get_or_set("k", 0.0, factory)
        zweit = await cache.get_or_set("k", 0.0, factory)
        return erst, zweit

    erst, zweit = run(scenario())
    assert erst == 1 and zweit == 2   # TTL 0 -> jedes Mal neu


# ---------------------------------------------------------------------------
# Forex-Factory-Parser
# ---------------------------------------------------------------------------

def test_forex_factory_parser_liest_die_realen_feldnamen():
    """Die Feldmenge wurde am 31.07.2026 am echten Feed geprueft."""
    provider = ForexFactoryProvider()
    timestamp = provider._parse_timestamp("2026-07-30T08:30:00-04:00")

    assert timestamp is not None
    assert timestamp.tzinfo is not None
    assert timestamp.hour == 12   # 08:30 EDT = 12:30 UTC
    assert timestamp.minute == 30


def test_forex_factory_parser_ignoriert_kaputte_zeitstempel():
    provider = ForexFactoryProvider()
    assert provider._parse_timestamp("kaputt") is None
    assert provider._parse_timestamp(None) is None


def test_leere_forecast_felder_werden_zu_none():
    from mcp_server.calendar_provider import _blank_to_none

    assert _blank_to_none("") is None
    assert _blank_to_none("   ") is None
    assert _blank_to_none(None) is None
    assert _blank_to_none("2.1%") == "2.1%"


# ---------------------------------------------------------------------------
# Ergebnisform
# ---------------------------------------------------------------------------

def test_ergebnis_enthaelt_quellenangaben():
    service = CalendarService(FakeSchedule([event("CPI m/m", 60)]), fred=FakeFred())
    result = run(service.event_risk(now=NOW, symbol="MGC"))

    assert result["symbol"] == "MGC"
    assert result["quelle_termine"] == "fake"
    assert result["quelle_actuals"] == "fred"
    assert "Forex Factory liefert keine Actual-Werte" in result["hinweis_actuals"]
    assert result["gefiltert_nach"]["waehrungen"] == ["USD"]
