"""Der Historien-Import und sein Kreuzvergleich.

Der Kreuzvergleich ist der eigentliche Gegenstand dieser Tests. Er existiert
wegen Invariante 9: eine um eine Minute verschobene oder in der falschen
Zeitzone gelesene Reihe sieht lueckenlos und plausibel aus, und an den Kursen
selbst ist nichts zu sehen. Bei den Dukascopy-Daten ist genau das passiert.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from werkzeuge.nt8_import import (
    MAX_ABWEICHUNG,
    MIN_UEBERLAPPUNG,
    kreuzvergleich,
    lies_export,
)


def _reihe(start: datetime, n: int, basis: float = 20000.0) -> pd.DataFrame:
    zeitpunkte = [start + timedelta(minutes=i) for i in range(n)]
    kurse = [basis + i * 0.25 for i in range(n)]
    return pd.DataFrame(
        {
            "open": kurse,
            "high": [k + 2 for k in kurse],
            "low": [k - 2 for k in kurse],
            "close": [k + 0.5 for k in kurse],
            "volume": [100.0] * n,
        },
        index=pd.DatetimeIndex(zeitpunkte, tz="UTC"),
    )


START = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)


# -- Einlesen ---------------------------------------------------------------

def test_semikolon_format_wird_gelesen(tmp_path):
    datei = tmp_path / "MNQ.txt"
    datei.write_text(
        "20260902 140000;20000.25;20005.00;19998.50;20003.75;1234\n"
        "20260902 140100;20003.75;20008.00;20002.00;20006.25;987\n",
        encoding="utf-8",
    )
    df = lies_export(datei, "UTC")

    assert len(df) == 2
    assert df["open"].iloc[0] == 20000.25
    assert df["volume"].iloc[1] == 987
    assert str(df.index.tz) == "UTC"


def test_komma_format_wird_auch_gelesen(tmp_path):
    """Das Trennzeichen ist im Exportdialog umstellbar."""
    datei = tmp_path / "MNQ.txt"
    datei.write_text("20260902 140000,20000.25,20005,19998.5,20003.75,1234\n", "utf-8")
    assert len(lies_export(datei, "UTC")) == 1


def test_zeitzone_wird_umgerechnet_und_nicht_geraten(tmp_path):
    """Eine falsch angenommene Zeitzone verschoebe die Reihe um Stunden -
    und die Kurse saehen weiter plausibel aus."""
    datei = tmp_path / "MNQ.txt"
    datei.write_text("20260902 100000;1;2;0;1;1\n", encoding="utf-8")

    newyork = lies_export(datei, "America/New_York")
    utc = lies_export(datei, "UTC")

    assert newyork.index[0] == pd.Timestamp("2026-09-02 14:00", tz="UTC")
    assert utc.index[0] == pd.Timestamp("2026-09-02 10:00", tz="UTC")


def test_unlesbare_zeilen_werden_uebersprungen_nicht_geraten(tmp_path):
    datei = tmp_path / "MNQ.txt"
    datei.write_text(
        "Kopfzeile ohne Zahlen\n"
        "20260902 140000;20000.25;20005.00;19998.50;20003.75;1234\n"
        "kaputt;;;\n",
        encoding="utf-8",
    )
    assert len(lies_export(datei, "UTC")) == 1


def test_datei_ohne_brauchbare_zeile_bricht_ab(tmp_path):
    datei = tmp_path / "leer.txt"
    datei.write_text("nur Text\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        lies_export(datei, "UTC")


# -- Kreuzvergleich ---------------------------------------------------------

def test_identische_reihen_bestehen():
    referenz = _reihe(START, 400)
    bestanden, meldungen = kreuzvergleich(referenz.copy(), referenz)
    assert bestanden, meldungen
    assert any("bestanden" in m for m in meldungen)


def test_zu_wenig_ueberlappung_besteht_nicht():
    """Zwei zufaellig passende Kerzen waeren kein Beleg."""
    referenz = _reihe(START, 400)
    winzig = referenz.iloc[:10]
    bestanden, meldungen = kreuzvergleich(winzig, referenz)

    assert not bestanden
    assert any(str(MIN_UEBERLAPPUNG) in m for m in meldungen)


def test_um_eine_minute_verschobene_reihe_wird_erkannt():
    """DER Test dieses Moduls.

    Eine um eine Minute verschobene Reihe hat plausible Kurse und einen
    lueckenlosen Index. Nur der Vergleich mit dem Versatz zeigt, dass die
    Beschriftung nicht stimmt - genau der Dukascopy-Fehler.
    """
    referenz = _reihe(START, 800)
    verschoben = referenz.copy()
    verschoben.index = verschoben.index + pd.Timedelta(minutes=1)

    bestanden, meldungen = kreuzvergleich(verschoben, referenz)
    assert not bestanden
    assert any("Invariante 9" in m or "verschoben" in m for m in meldungen)


def test_abweichende_kurse_brechen_ab():
    referenz = _reihe(START, 400)
    anders = referenz.copy()
    anders["close"] = anders["close"] + 5.0

    bestanden, meldungen = kreuzvergleich(anders, referenz)
    assert not bestanden
    assert any("ABBRUCH" in m for m in meldungen)


def test_rundungsreste_innerhalb_der_toleranz_bestehen():
    """Der Export rundet auf die Ticksize, die Datenbank haelt Fliesskomma."""
    referenz = _reihe(START, 400)
    gerundet = referenz.copy()
    gerundet["close"] = gerundet["close"] + MAX_ABWEICHUNG / 2

    bestanden, _ = kreuzvergleich(gerundet, referenz)
    assert bestanden


def test_falsche_zeitzone_faellt_durch():
    """Um Stunden verschoben gibt es gar keine Ueberlappung mehr."""
    referenz = _reihe(START, 400)
    falsch = referenz.copy()
    falsch.index = falsch.index + pd.Timedelta(hours=6)

    bestanden, _ = kreuzvergleich(falsch, referenz)
    assert not bestanden
