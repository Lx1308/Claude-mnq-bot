"""Tests fuer Instrument-Register und Session-Klassifikation.

Schwerpunkt: die beiden Stellen, an denen falsche Annahmen still zu falschen
Zahlen fuehren - Verfallsregeln je Instrument und Sommerzeit-Uebergaenge.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from common.instruments import (
    MGC,
    MNQ,
    UnknownInstrument,
    get_instrument,
    known_roots,
    third_friday,
    third_last_business_day,
)
from common.sessions import (
    active_sessions,
    format_timestamps,
    globex_state,
    is_liquid_window,
    is_rth,
    is_thin_window,
    minutes_until_rth_close,
    minutes_until_rth_open,
    primary_session,
    session_context,
)

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def et(year, month, day, hour, minute=0) -> datetime:
    """Zeitpunkt in New Yorker Boersenzeit."""
    return datetime(year, month, day, hour, minute, tzinfo=ET)


# ---------------------------------------------------------------------------
# Kontraktspezifikation
# ---------------------------------------------------------------------------

def test_mnq_tickwert_stimmt():
    # 0.25 Indexpunkte x 2 USD/Punkt = 0.50 USD je Tick
    assert MNQ.tick_size == 0.25
    assert MNQ.point_value == 2.0
    assert MNQ.tick_value == pytest.approx(0.50)
    assert MNQ.points_to_usd(10) == pytest.approx(20.0)
    assert MNQ.points_to_ticks(1.0) == pytest.approx(4.0)


def test_mgc_tickwert_stimmt():
    # 0.10 USD/oz x 10 Unzen = 1.00 USD je Tick; 1.00-USD-Move = 10 USD
    assert MGC.tick_size == pytest.approx(0.10)
    assert MGC.point_value == 10.0
    assert MGC.tick_value == pytest.approx(1.00)
    assert MGC.points_to_usd(1.0) == pytest.approx(10.0)


def test_round_to_tick_trifft_das_handelbare_raster():
    assert MNQ.round_to_tick(21345.31) == pytest.approx(21345.25)
    assert MNQ.round_to_tick(21345.40) == pytest.approx(21345.50)
    assert MGC.round_to_tick(2412.37) == pytest.approx(2412.40)


# ---------------------------------------------------------------------------
# Verfallsregeln - hier lag der Fehler der bisherigen Implementierung
# ---------------------------------------------------------------------------

def test_third_friday_ist_korrekt():
    # Dezember 2025: 1.12. ist ein Montag -> Freitage am 5., 12., 19.
    assert third_friday(2025, 12) == date(2025, 12, 19)
    # Maerz 2026: 1.3. ist ein Sonntag -> Freitage am 6., 13., 20.
    assert third_friday(2026, 3) == date(2026, 3, 20)


def test_third_last_business_day_ist_korrekt():
    # Dezember 2025 endet Mi 31.12. -> Geschaeftstage rueckwaerts: 31., 30., 29.
    assert third_last_business_day(2025, 12) == date(2025, 12, 29)
    # August 2025 endet So 31.8. -> letzte Geschaeftstage: 29. (Fr), 28., 27.
    assert third_last_business_day(2025, 8) == date(2025, 8, 27)


def test_mgc_und_mnq_verfallen_nach_unterschiedlichen_regeln():
    """Der Kern des Problems: eine Regel fuer beide waere falsch."""
    mnq_expiry = MNQ.expiry_for(2025, 12)
    mgc_expiry = MGC.expiry_for(2025, 12)

    assert mnq_expiry == date(2025, 12, 19)     # 3. Freitag
    assert mgc_expiry == date(2025, 12, 29)     # drittletzter Geschaeftstag
    assert mgc_expiry != mnq_expiry


def test_kontraktmonate_unterscheiden_sich():
    assert MNQ.contract_months == ("H", "M", "U", "Z")           # quartalsweise
    assert MGC.contract_months == ("G", "J", "M", "Q", "V", "Z")  # zweimonatlich


# ---------------------------------------------------------------------------
# Symbolaufloesung
# ---------------------------------------------------------------------------

def test_get_instrument_akzeptiert_root_und_kontrakt():
    assert get_instrument("MNQ") is MNQ
    assert get_instrument("MNQZ5") is MNQ
    assert get_instrument("mnqz25") is MNQ
    assert get_instrument("MGCG6") is MGC


def test_get_instrument_verwechselt_keine_praefixe():
    """"MNQ" darf nicht als "MN" plus Monatscode gelesen werden."""
    assert get_instrument("MNQ").root == "MNQ"
    assert get_instrument("MES").root == "MES"
    assert get_instrument("ES").root == "ES"


def test_unbekanntes_symbol_wirft_mit_hinweis():
    with pytest.raises(UnknownInstrument, match="Bekannt"):
        get_instrument("XYZ")


def test_register_kennt_die_gehandelten_instrumente():
    roots = known_roots()
    assert "MNQ" in roots and "MGC" in roots


# ---------------------------------------------------------------------------
# Globex-Rahmen
# ---------------------------------------------------------------------------

def test_globex_wartungspause_wird_erkannt():
    # 16:30 CT = 17:30 ET, mitten in der taeglichen Pause
    assert globex_state(et(2026, 3, 10, 17, 30)) == "maintenance"
    # 18:30 ET = 17:30 CT, wieder offen
    assert globex_state(et(2026, 3, 10, 18, 30)) == "open"


def test_globex_wochenende_wird_erkannt():
    # Freitag nach 16:00 CT (17:00 ET)
    assert globex_state(et(2026, 3, 13, 18, 0)) == "weekend"
    # Samstag
    assert globex_state(et(2026, 3, 14, 12, 0)) == "weekend"
    # Sonntag vor 17:00 CT (18:00 ET)
    assert globex_state(et(2026, 3, 15, 16, 0)) == "weekend"
    # Sonntag nach der Eroeffnung
    assert globex_state(et(2026, 3, 15, 19, 0)) == "open"


def test_am_wochenende_laeuft_keine_session():
    assert active_sessions(et(2026, 3, 14, 12, 0)) == []
    assert primary_session(et(2026, 3, 14, 12, 0)) == "closed"


# ---------------------------------------------------------------------------
# Session-Klassifikation und Sommerzeit
# ---------------------------------------------------------------------------

def test_new_york_session_zur_rth_zeit():
    moment = et(2026, 6, 10, 10, 30)
    assert "new_york" in active_sessions(moment)
    assert primary_session(moment) == "new_york"


def test_new_york_schlaegt_london_bei_ueberlappung():
    """Beide laufen um 10:00 ET - relevant ist New York."""
    moment = et(2026, 6, 10, 10, 0)
    running = active_sessions(moment)
    assert "london" in running and "new_york" in running
    assert primary_session(moment) == "new_york"


def test_london_session_vor_der_us_eroeffnung():
    moment = et(2026, 6, 10, 5, 0)   # 10:00 London
    assert "london" in active_sessions(moment)
    assert primary_session(moment) == "london"


def test_asien_session_am_abend_et():
    moment = et(2026, 6, 9, 21, 0)   # 10:00 Tokio am Folgetag
    assert "asia" in active_sessions(moment)


def test_dst_versatz_zwischen_us_und_uk_wird_korrekt_behandelt():
    """Der eigentliche Sommerzeit-Fallstrick.

    Die USA stellen am 8. Maerz 2026 um, Grossbritannien erst am 29. Maerz.
    In diesen drei Wochen liegt London aus US-Sicht eine Stunde anders.
    Ein fest verdrahtetes "London = 03:00 ET" waere hier falsch.
    """
    # 20. Maerz 2026: USA in EDT (UTC-4), UK noch in GMT (UTC+0).
    # London 08:00 GMT entspricht 04:00 ET.
    vor_umstellung = et(2026, 3, 20, 4, 0)
    assert "london" in active_sessions(vor_umstellung)
    assert "london" not in active_sessions(et(2026, 3, 20, 2, 30))

    # 10. April 2026: beide in Sommerzeit, London 08:00 BST = 03:00 ET.
    nach_umstellung = et(2026, 4, 10, 3, 0)
    assert "london" in active_sessions(nach_umstellung)


def test_session_zuordnung_ueber_den_us_dst_wechsel():
    """Der Handelstag-Rollover muss auch am Umstellungstag bei 18:00 ET liegen."""
    from common.config import SessionConfig
    from common.sessions import session_date_for

    config = SessionConfig()
    # 8. Maerz 2026 ist der US-Umstellungstag (2->3 Uhr).
    vor_rollover = et(2026, 3, 9, 17, 30)
    nach_rollover = et(2026, 3, 9, 18, 30)

    assert session_date_for(vor_rollover, config) == date(2026, 3, 9)
    assert session_date_for(nach_rollover, config) == date(2026, 3, 10)


# ---------------------------------------------------------------------------
# RTH und Liquiditaetsfenster je Instrument
# ---------------------------------------------------------------------------

def test_rth_fenster_unterscheiden_sich_je_instrument():
    # 14:00 ET: MNQ handelt noch regulaer, MGC ist bereits ausserhalb.
    moment = et(2026, 6, 10, 14, 0)
    assert is_rth(moment, MNQ) is True
    assert is_rth(moment, MGC) is False

    # 09:00 ET: MGC laeuft (ab 08:20), MNQ noch nicht (ab 09:30).
    frueh = et(2026, 6, 10, 9, 0)
    assert is_rth(frueh, MGC) is True
    assert is_rth(frueh, MNQ) is False


def test_duenne_mittagszone_wird_markiert():
    assert is_thin_window(et(2026, 6, 10, 13, 0), MNQ) is True
    assert is_thin_window(et(2026, 6, 10, 10, 0), MNQ) is False


def test_minuten_bis_rth_open_und_close():
    # 09:00 ET, MNQ oeffnet 09:30 -> 30 Minuten
    assert minutes_until_rth_open(et(2026, 6, 10, 9, 0), MNQ) == pytest.approx(30.0)
    # Waehrend RTH ist der Abstand null
    assert minutes_until_rth_open(et(2026, 6, 10, 10, 0), MNQ) == 0.0
    # 16:00 ET, MNQ schliesst 16:15 -> 15 Minuten
    assert minutes_until_rth_close(et(2026, 6, 10, 16, 0), MNQ) == pytest.approx(15.0)
    # Ausserhalb RTH gibt es keinen Schlussabstand
    assert minutes_until_rth_close(et(2026, 6, 10, 20, 0), MNQ) is None


def test_liquiditaetsfenster_endet_vor_dem_rth_schluss_bei_mnq():
    # MNQ: RTH bis 16:15, belastbare Liquiditaet bis 16:00
    assert is_liquid_window(et(2026, 6, 10, 15, 30), MNQ) is True
    assert is_liquid_window(et(2026, 6, 10, 16, 5), MNQ) is False
    assert is_rth(et(2026, 6, 10, 16, 5), MNQ) is True


# ---------------------------------------------------------------------------
# Ausgabeformat
# ---------------------------------------------------------------------------

def test_zeitstempel_werden_in_utc_et_und_ct_geliefert():
    stamps = format_timestamps(et(2026, 6, 10, 10, 0))

    assert stamps["utc"].endswith("+00:00")
    assert "-04:00" in stamps["et"]    # EDT
    assert "-05:00" in stamps["ct"]    # CDT
    assert "14:00" in stamps["utc"]


def test_session_context_liefert_alle_felder():
    context = session_context(et(2026, 6, 10, 10, 0), MNQ)

    for key in (
        "timestamp", "globex_state", "globex_frame", "primary_session",
        "active_sessions", "trading_day", "is_rth", "is_liquid_window",
        "is_thin_midday_window", "minutes_to_rth_open", "minutes_to_rth_close",
        "minutes_to_globex_close",
    ):
        assert key in context, f"Feld {key} fehlt"

    assert context["globex_state"] == "open"
    assert context["is_rth"] is True
    assert context["primary_session"] == "new_york"
