"""Tests des Marktkalender-Wrappers.

Bewusst gegen die ECHTE pandas_market_calendars-Bibliothek getestet, nicht
gegen ein Fake - der ganze Zweck dieses Moduls ist, korrekt an eine externe
Feiertagsquelle anzudocken. Ein Fake wuerde genau die Frage nicht pruefen,
die zaehlt: stimmt der Kalendername ueberhaupt.
"""

from __future__ import annotations

import datetime

import pytest

from common.marktkalender import Marktkalender, MarktkalenderFehler


@pytest.fixture(scope="module")
def kalender() -> Marktkalender:
    return Marktkalender()


def test_weihnachten_ist_kein_handelstag(kalender):
    assert kalender.ist_handelstag(datetime.date(2026, 12, 25)) is False


def test_neujahr_ist_kein_handelstag(kalender):
    assert kalender.ist_handelstag(datetime.date(2026, 1, 1)) is False


def test_normaler_wochentag_ist_handelstag(kalender):
    # 2026-08-24 ist ein Montag ohne bekannten CME-Feiertag.
    assert kalender.ist_handelstag(datetime.date(2026, 8, 24)) is True


def test_wochenende_ist_kein_handelstag(kalender):
    # 2026-08-22 ist ein Samstag.
    assert kalender.ist_handelstag(datetime.date(2026, 8, 22)) is False


def test_heiligabend_ist_fruehschluss(kalender):
    assert kalender.ist_fruehschluss(datetime.date(2026, 12, 24)) is True


def test_normaler_handelstag_ist_kein_fruehschluss(kalender):
    assert kalender.ist_fruehschluss(datetime.date(2026, 8, 24)) is False


def test_kein_fruehschluss_an_einem_nicht_handelstag(kalender):
    """Ein arbeitsfreier Tag ist kein 'Fruehschluss' - die Frage ergibt
    dort keinen Sinn und muss False liefern, nicht werfen oder raten."""
    assert kalender.ist_fruehschluss(datetime.date(2026, 12, 25)) is False


def test_naechster_handelstag_ueberspringt_feiertag(kalender):
    naechster = kalender.naechster_handelstag(datetime.date(2026, 12, 25))
    assert naechster == datetime.date(2026, 12, 28)


def test_naechster_handelstag_an_einem_handelstag_ist_derselbe_tag(kalender):
    heute = datetime.date(2026, 8, 24)
    assert kalender.naechster_handelstag(heute) == heute


def test_handelstage_zwischen_zaehlt_feiertage_nicht_mit(kalender):
    tage = kalender.handelstage_zwischen(
        datetime.date(2026, 12, 23), datetime.date(2026, 12, 28)
    )
    assert datetime.date(2026, 12, 25) not in tage
    assert datetime.date(2026, 12, 24) in tage
    assert datetime.date(2026, 12, 28) in tage


def test_unbekannter_kalendername_bricht_beim_aufbau_ab():
    with pytest.raises(MarktkalenderFehler, match="nicht bekannt"):
        Marktkalender(name="DOES_NOT_EXIST_XYZ")
