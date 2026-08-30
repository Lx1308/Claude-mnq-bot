"""Hoch und Tief der Handelsfenster Asia und London.

Ausdruecklich gewuenscht am 30.08.2026 ("da war zum Beispiel das London High,
da war das Asia High"). Der interessante Teil ist nicht das Maximum, sondern
die Frage, WELCHE Kerzen dazugehoeren - und die haengt an der Zeitzone.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from common.config import Config, SessionConfig
from common.indicators import compute_indicators
from common.instruments import get_instrument
from common.levels import compute_levels, session_extremes, session_mask
from common.sessions import SESSION_WINDOWS


def _rahmen(zeitpunkte: list[datetime], hochs: list[float]) -> pd.DataFrame:
    # utc=True: die Zeitpunkte tragen verschiedene Zeitzonen (Tokio, London,
    # New York). Ohne die Umrechnung auf UTC lehnt pandas den gemischten Index
    # ab - und genau dieses Gemisch ist hier der Punkt.
    index = pd.DatetimeIndex(pd.to_datetime(zeitpunkte, utc=True))
    return pd.DataFrame(
        {
            "open": hochs,
            "high": hochs,
            "low": [h - 1 for h in hochs],
            "close": hochs,
            "volume": [100.0] * len(hochs),
        },
        index=index,
    )


LONDON = next(w for w in SESSION_WINDOWS if w.name == "london")
ASIA = next(w for w in SESSION_WINDOWS if w.name == "asia")


def test_london_fenster_folgt_der_londoner_zeit_nicht_einer_et_spanne():
    """Der eigentliche Grund fuer die Zeitzonenrechnung.

    Europa und die USA stellen die Uhr an verschiedenen Terminen um. Ende
    Oktober 2026 hat London bereits Winterzeit, New York noch Sommerzeit -
    eine hart verdrahtete Spanne "London = 03:00-11:30 ET" liegt in dieser
    Woche eine Stunde daneben.
    """
    london = ZoneInfo("Europe/London")
    et = ZoneInfo("America/New_York")

    # 26.10.2026: London ist auf Winterzeit, New York noch nicht.
    oeffnung = datetime(2026, 10, 26, 8, 0, tzinfo=london)
    assert LONDON.contains(oeffnung)
    assert oeffnung.astimezone(et).hour == 4        # nicht 3

    # Im Sommer sind es dagegen 03:00 ET.
    sommer = datetime(2026, 6, 26, 8, 0, tzinfo=london)
    assert LONDON.contains(sommer)
    assert sommer.astimezone(et).hour == 3


def test_asia_fenster_liegt_in_tokioter_zeit():
    tokio = ZoneInfo("Asia/Tokyo")
    assert ASIA.contains(datetime(2026, 9, 2, 9, 0, tzinfo=tokio))
    assert ASIA.contains(datetime(2026, 9, 2, 17, 59, tzinfo=tokio))
    assert not ASIA.contains(datetime(2026, 9, 2, 18, 0, tzinfo=tokio))
    assert not ASIA.contains(datetime(2026, 9, 2, 8, 59, tzinfo=tokio))


def test_extremwerte_je_fenster_werden_getrennt_gerechnet():
    tokio = ZoneInfo("Asia/Tokyo")
    london = ZoneInfo("Europe/London")

    df = _rahmen(
        [
            # Bewusst ausserhalb der Ueberlappung gewaehlt - siehe
            # test_die_fenster_ueberlappen_sich_und_das_ist_richtig.
            datetime(2026, 9, 2, 10, 0, tzinfo=tokio),    # 01:00 UTC, nur Asia
            datetime(2026, 9, 2, 14, 0, tzinfo=tokio),    # 05:00 UTC, nur Asia
            datetime(2026, 9, 2, 12, 0, tzinfo=london),   # 11:00 UTC, nur London
            datetime(2026, 9, 2, 15, 0, tzinfo=london),   # 14:00 UTC, nur London
        ],
        [100.0, 120.0, 200.0, 180.0],
    )
    werte = session_extremes(df)

    assert werte["asia_high"] == 120.0
    assert werte["asia_low"] == 99.0
    assert werte["london_high"] == 200.0
    assert werte["london_low"] == 179.0


def test_die_fenster_ueberlappen_sich_und_das_ist_richtig():
    """Asia und London ueberlappen zwischen 07:00 und 09:00 UTC.

    Eine Kerze um 08:00 London (= 17:00 Tokio) gehoert zu BEIDEN Fenstern und
    zaehlt in beide Extremwerte. Das ist keine Unsauberkeit, sondern die
    Realitaet: der Markt laeuft in dieser Stunde tatsaechlich unter beiden
    Vorzeichen. Wer eine ueberschneidungsfreie Zuordnung braucht, nimmt
    ``primary_session`` - die entscheidet sich fuer eine.
    """
    tokio = ZoneInfo("Asia/Tokyo")
    london = ZoneInfo("Europe/London")

    ueberlappung = datetime(2026, 9, 2, 8, 30, tzinfo=london)
    assert LONDON.contains(ueberlappung)
    assert ASIA.contains(ueberlappung)
    assert ueberlappung.astimezone(tokio).hour == 16

    df = _rahmen([ueberlappung], [150.0])
    werte = session_extremes(df)
    assert werte["asia_high"] == 150.0
    assert werte["london_high"] == 150.0


def test_fehlendes_fenster_taucht_gar_nicht_auf():
    """Kein 0 und kein NaN - beides saehe aus wie ein gemessener Kurs."""
    tokio = ZoneInfo("Asia/Tokyo")
    df = _rahmen([datetime(2026, 9, 2, 10, 0, tzinfo=tokio)], [100.0])
    werte = session_extremes(df)

    assert "asia_high" in werte
    assert "london_high" not in werte
    assert "london_low" not in werte


def test_leerer_rahmen_liefert_leeres_ergebnis():
    leer = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    assert session_extremes(leer) == {}
    assert session_mask(leer, LONDON).empty


def test_compute_levels_liefert_asia_und_london(tmp_path):
    """Die Level muessen im normalen Level-Satz ankommen, nicht daneben.

    Sonst braeuchte die Oberflaeche einen zweiten Weg, sie zu holen - und
    zwei Wege zu denselben Zahlen laufen frueher oder spaeter auseinander.
    """
    tokio = ZoneInfo("Asia/Tokyo")
    london = ZoneInfo("Europe/London")
    et = ZoneInfo("America/New_York")

    zeitpunkte = [
        datetime(2026, 9, 2, 10, 0, tzinfo=tokio),     # 01:00 UTC, nur Asia
        datetime(2026, 9, 2, 12, 0, tzinfo=london),    # 11:00 UTC, nur London
        datetime(2026, 9, 2, 10, 30, tzinfo=et),       # RTH New York
    ]
    df = _rahmen(zeitpunkte, [100.0, 200.0, 150.0]).sort_index()

    cfg = Config.load("config.yaml")
    instrument = get_instrument("MNQ")
    vorbereitet = compute_indicators(df, cfg.indicators, cfg.market.session)
    satz = compute_levels(
        vorbereitet, instrument, atr_value=10.0, session_cfg=cfg.market.session
    )

    namen = {level.name for level in satz.levels}
    assert "asia_high" in namen
    assert "london_high" in namen


def test_session_level_stehen_auf_dem_laufenden_handelstag():
    """Die 18:00-ET-Regel gilt auch hier.

    ``compute_levels`` schneidet vorher auf den Handelstag zu; ``session_extremes``
    gruppiert bewusst nicht noch einmal selbst. Zwei Stellen, die entscheiden,
    welcher Tag gemeint ist, koennen auseinander laufen.
    """
    from common.sessions import session_date_for

    et = ZoneInfo("America/New_York")
    # Montag 19:30 ET gehoert bereits zum Handelstag Dienstag.
    montag_abend = datetime(2026, 8, 31, 19, 30, tzinfo=et)
    assert session_date_for(montag_abend, SessionConfig()).isoformat() == "2026-09-01"
