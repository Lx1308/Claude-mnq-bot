"""Tests der Makro-Vintage-Infrastruktur - ohne Netzzugriff.

Deckt genau die drei Zusicherungen ab, die MASTERPLAN.md Abschnitt T fuer
Makrodaten verlangt: Lookahead, Revision, Timezone. Dazu die Fail-safe-
Pflicht (analog Wirtschaftskalender) und den abgeschalteten
Calendar-Provider.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
import yaml

from common.config import Config, ConfigError
from macro.model import MacroObservation
from macro.pipeline import aktualisiere
from macro.provider import (
    ALFRED_REALTIME_END,
    ALFRED_REALTIME_START,
    FredAlfredProvider,
    MacroProviderError,
    create_economic_calendar_provider,
)
from macro.store import MacroStore

UTC = timezone.utc


def obs(
    *,
    source_event_id: str = "CPIAUCSL:2026-07-01",
    beobachtungszeitraum: datetime = datetime(2026, 7, 1, tzinfo=UTC),
    verfuegbar_ab: datetime = datetime(2026, 8, 12, tzinfo=UTC),
    revision: int = 0,
    actual: str = "320.5",
) -> MacroObservation:
    return MacroObservation(
        source="fred_alfred",
        source_event_id=source_event_id,
        event_name="VPI (Index)",
        event_type="macro_release",
        beobachtungszeitraum_utc=beobachtungszeitraum,
        available_at_utc=verfuegbar_ab,
        released_at_utc=verfuegbar_ab,
        revision=revision,
        revision_at_utc=verfuegbar_ab,
        actual=actual,
    )


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Timezone - naive Zeitstempel werden ueberall abgelehnt
# ---------------------------------------------------------------------------

def test_naiver_zeitstempel_in_macro_observation_wird_abgelehnt():
    with pytest.raises(ValueError, match="zeitzonenbewusst"):
        MacroObservation(
            source="x", source_event_id="y", event_name="z", event_type="macro_release",
            beobachtungszeitraum_utc=datetime(2026, 1, 1),  # naiv
            available_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            released_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            revision=0,
            revision_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
            actual="1",
        )


def test_naiver_zeitstempel_bei_stand_zum_zeitpunkt_wird_abgelehnt(tmp_path):
    store = MacroStore(tmp_path / "macro.sqlite3")
    with pytest.raises(ValueError, match="zeitzonenbewusst"):
        store.stand_zum_zeitpunkt("fred_alfred", "x", datetime(2026, 1, 1))
    store.close()


# ---------------------------------------------------------------------------
# Lookahead - der wichtigste Test
# ---------------------------------------------------------------------------

def test_wert_ist_vor_available_at_nicht_sichtbar(tmp_path):
    store = MacroStore(tmp_path / "macro.sqlite3")
    store.speichere([obs(verfuegbar_ab=datetime(2026, 8, 12, tzinfo=UTC))])

    # Eine Sekunde vor der Veroeffentlichung: nicht sichtbar.
    vorher = store.stand_zum_zeitpunkt(
        "fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 8, 11, 23, 59, 59, tzinfo=UTC)
    )
    assert vorher is None

    # Zum Veroeffentlichungszeitpunkt selbst: sichtbar (available_at_utc <=).
    danach = store.stand_zum_zeitpunkt(
        "fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 8, 12, tzinfo=UTC)
    )
    assert danach is not None
    assert danach["actual"] == "320.5"
    store.close()


# ---------------------------------------------------------------------------
# Revision - alte Vintages bleiben unveraendert stehen
# ---------------------------------------------------------------------------

def test_revisionen_werden_nie_ueberschrieben_sondern_versioniert(tmp_path):
    store = MacroStore(tmp_path / "macro.sqlite3")
    erstveroeffentlichung = obs(verfuegbar_ab=datetime(2026, 8, 12, tzinfo=UTC), revision=0, actual="320.5")
    revision_1 = obs(verfuegbar_ab=datetime(2026, 9, 12, tzinfo=UTC), revision=1, actual="320.7")

    store.speichere([erstveroeffentlichung, revision_1])

    # Ein Backtest, der zum 20.08. rechnet, sieht weiterhin die Erstveroeffentlichung -
    # auch NACHDEM die Revision laengst in der Datenbank liegt.
    zum_20_08 = store.stand_zum_zeitpunkt(
        "fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 8, 20, tzinfo=UTC)
    )
    assert zum_20_08["actual"] == "320.5"

    zum_01_10 = store.stand_zum_zeitpunkt(
        "fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 10, 1, tzinfo=UTC)
    )
    assert zum_01_10["actual"] == "320.7"

    alle = store.alle_vintages("fred_alfred", "CPIAUCSL:2026-07-01")
    assert [z["actual"] for z in alle] == ["320.5", "320.7"]
    store.close()


def test_erneutes_speichern_derselben_vintages_erzeugt_keine_duplikate(tmp_path):
    """Idempotenz: ein wiederholter Pipeline-Lauf ueber dieselbe ALFRED-Antwort
    darf die Datenbank nicht wachsen lassen."""
    store = MacroStore(tmp_path / "macro.sqlite3")
    eintraege = [obs(), obs(verfuegbar_ab=datetime(2026, 9, 12, tzinfo=UTC), revision=1, actual="320.7")]

    erster_lauf = store.speichere(eintraege)
    zweiter_lauf = store.speichere(eintraege)

    assert erster_lauf == 2
    assert zweiter_lauf == 0
    assert store.gesamt() == 2
    store.close()


# ---------------------------------------------------------------------------
# Fail-safe - Providerausfall darf niemals wie "keine Revision" aussehen
# ---------------------------------------------------------------------------

def test_fehlender_api_key_bricht_laut_ab_statt_leere_liste_zu_liefern():
    provider = FredAlfredProvider(api_key=None)
    with pytest.raises(MacroProviderError, match="FRED_API_KEY"):
        run(provider.hole_vintages("CPIAUCSL"))


def test_netzwerkfehler_wird_zu_macro_provider_error():
    def kaputter_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("kein Netz (Test)")

    provider = FredAlfredProvider(
        api_key="test-key", transport=httpx.MockTransport(kaputter_handler)
    )
    with pytest.raises(MacroProviderError, match="fehlgeschlagen"):
        run(provider.hole_vintages("CPIAUCSL"))


# ---------------------------------------------------------------------------
# ALFRED-Antwort korrekt in Vintages uebersetzt
# ---------------------------------------------------------------------------

def test_alfred_antwort_wird_korrekt_in_vintages_uebersetzt():
    """Reale ALFRED-Antwortform (gekuerzt): drei Vintages, davon einer mit
    Punkt-Platzhalter (= noch kein Wert), der uebersprungen werden muss."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["realtime_start"] == ALFRED_REALTIME_START
        assert request.url.params["realtime_end"] == ALFRED_REALTIME_END
        return httpx.Response(
            200,
            json={
                "observations": [
                    {"realtime_start": "2026-08-12", "realtime_end": "2026-09-11",
                     "date": "2026-07-01", "value": "320.5"},
                    {"realtime_start": "2026-09-12", "realtime_end": "9999-12-31",
                     "date": "2026-07-01", "value": "320.7"},
                    {"realtime_start": "2026-09-12", "realtime_end": "9999-12-31",
                     "date": "2026-08-01", "value": "."},
                ]
            },
        )

    provider = FredAlfredProvider(api_key="test-key", transport=httpx.MockTransport(handler))
    vintages = run(provider.hole_vintages("CPIAUCSL"))

    assert len(vintages) == 2  # der "."-Platzhalter wurde uebersprungen
    assert vintages[0].revision == 0
    assert vintages[0].actual == "320.5"
    assert vintages[0].available_at_utc == datetime(2026, 8, 12, tzinfo=UTC)
    assert vintages[1].revision == 1
    assert vintages[1].actual == "320.7"
    assert vintages[0].source_event_id == vintages[1].source_event_id == "CPIAUCSL:2026-07-01"
    assert vintages[0].scheduled_at_utc is None  # FRED kennt keine Vorankuendigung


# ---------------------------------------------------------------------------
# Pipeline: eine fehlschlagende Reihe darf den Lauf nicht abbrechen
# ---------------------------------------------------------------------------

class _FakeProvider:
    """Erfuellt die von aktualisiere() gebrauchte Schnittstelle, ohne Netz."""

    name = "fred_alfred"

    def __init__(self, ergebnisse: dict[str, list[MacroObservation] | Exception]) -> None:
        self._ergebnisse = ergebnisse

    async def hole_vintages(self, series_id: str) -> list[MacroObservation]:
        ergebnis = self._ergebnisse[series_id]
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis


def test_pipeline_isoliert_fehler_je_reihe(tmp_path):
    store = MacroStore(tmp_path / "macro.sqlite3")
    provider = _FakeProvider(
        {
            "CPIAUCSL": [obs()],
            "PAYEMS": MacroProviderError("ALFRED down (Test)"),
        }
    )

    ergebnis = aktualisiere(
        store, provider, serien={"CPIAUCSL": "VPI", "PAYEMS": "Payrolls"}
    )

    assert ergebnis["CPIAUCSL"] == 1
    assert ergebnis["PAYEMS"] == -1  # -1 = Fehler, nicht "0 neue"
    assert store.gesamt() == 1
    store.close()


def test_pipeline_traegt_kuratierte_wichtigkeit_in_gespeicherte_zeilen_ein(tmp_path):
    store = MacroStore(tmp_path / "macro.sqlite3")
    provider = _FakeProvider({"CPIAUCSL": [obs()], "RSAFS": [obs(source_event_id="RSAFS:2026-07-01")]})

    aktualisiere(
        store,
        provider,
        serien={"CPIAUCSL": "VPI", "RSAFS": "Einzelhandel"},
        wichtigkeit={"CPIAUCSL": "High", "RSAFS": "Medium"},
    )

    cpi = store.stand_zum_zeitpunkt("fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 8, 20, tzinfo=UTC))
    rsafs = store.stand_zum_zeitpunkt("fred_alfred", "RSAFS:2026-07-01", datetime(2026, 8, 20, tzinfo=UTC))
    assert cpi["importance"] == "High"
    assert rsafs["importance"] == "Medium"
    store.close()


def test_pipeline_laesst_importance_leer_ohne_eintrag_in_wichtigkeit(tmp_path):
    """Eine Reihe ohne Eintrag in macro.wichtigkeit wird nicht geraten -
    importance bleibt None, nicht z.B. stillschweigend 'Medium'."""
    store = MacroStore(tmp_path / "macro.sqlite3")
    provider = _FakeProvider({"CPIAUCSL": [obs()]})

    aktualisiere(store, provider, serien={"CPIAUCSL": "VPI"}, wichtigkeit={})

    zeile = store.stand_zum_zeitpunkt("fred_alfred", "CPIAUCSL:2026-07-01", datetime(2026, 8, 20, tzinfo=UTC))
    assert zeile["importance"] is None
    store.close()


# ---------------------------------------------------------------------------
# Economic-Calendar-Provider: Schnittstelle vorhanden, nichts angeschaltet
# ---------------------------------------------------------------------------

def test_calendar_provider_ist_ohne_env_var_deaktiviert(monkeypatch):
    monkeypatch.delenv("ECONOMIC_CALENDAR_PROVIDER", raising=False)
    assert create_economic_calendar_provider() is None


def test_calendar_provider_bricht_bei_unbekanntem_wert_laut_ab(monkeypatch):
    monkeypatch.setenv("ECONOMIC_CALENDAR_PROVIDER", "trading_economics")
    with pytest.raises(MacroProviderError, match="kein Kalenderanbieter implementiert"):
        create_economic_calendar_provider()


# ---------------------------------------------------------------------------
# Config: die kuratierte Wichtigkeit ist keine freie Zeichenkette
# ---------------------------------------------------------------------------

def test_config_bricht_bei_unbekannter_wichtigkeitsstufe_ab():
    with open("config.yaml", encoding="utf-8") as handle:
        daten = yaml.safe_load(handle)
    daten["macro"]["wichtigkeit"] = {"CPIAUCSL": "Hoch"}  # nicht "High"

    with pytest.raises(ConfigError, match="wichtigkeit"):
        Config.from_dict(daten)


def test_config_akzeptiert_die_vorgabe_aus_config_yaml():
    cfg = Config.load("config.yaml")
    assert cfg.macro.wichtigkeit["CPIAUCSL"] == "High"
    assert set(cfg.macro.wichtigkeit.values()) <= {"High", "Medium", "Low"}
