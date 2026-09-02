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


def test_wenige_ausreisser_bestehen_und_werden_benannt():
    """Eine LUECKE in einer Quelle ist keine KORRUPTION.

    Am 30.08.2026 lagen beim ersten echten Import (MNQ 09-26) 99,31 % der
    gemeinsamen Kerzen bittgenau; die 0,69 % Rest waren ein Tag, den
    NinjaTrader lokal nie voll geladen hatte, plus Tick-Rauschen an der
    Minutengrenze zwischen Live- und Historienkerzen.
    """
    referenz = _reihe(START, 400)
    mit_luecke = referenz.copy()
    # 2 von 400 Kerzen (0,5 %) grob daneben - unter der 1-%-Schwelle.
    mit_luecke.iloc[10, mit_luecke.columns.get_loc("close")] += 30.0
    mit_luecke.iloc[20, mit_luecke.columns.get_loc("close")] += 30.0

    bestanden, meldungen = kreuzvergleich(mit_luecke, referenz)
    assert bestanden, meldungen
    assert any("2 Kerzen ausserhalb der Toleranz" in m for m in meldungen)
    assert any("bestanden" in m for m in meldungen)


def test_zu_viele_ausreisser_brechen_ab():
    """Ueber der Schwelle ist es kein Rauschen mehr, sondern ein Fehler."""
    referenz = _reihe(START, 400)
    kaputt = referenz.copy()
    idx = kaputt.columns.get_loc("close")
    for i in range(40):  # 10 % daneben
        kaputt.iloc[i * 10, idx] += 30.0

    bestanden, meldungen = kreuzvergleich(kaputt, referenz)
    assert not bestanden
    assert any("ABBRUCH" in m and "%" in m for m in meldungen)


def test_ein_einzelner_ausreisser_kippt_den_versatztest_nicht():
    """Der Versatztest misst am Anteil, nicht am schlechtesten Balken - sonst
    koennte eine einzelne krasse Kerze einen Beschriftungs-Fehlalarm ausloesen.
    """
    referenz = _reihe(START, 400)
    fast_gleich = referenz.copy()
    fast_gleich.iloc[5, fast_gleich.columns.get_loc("high")] += 500.0

    bestanden, meldungen = kreuzvergleich(fast_gleich, referenz)
    assert bestanden, meldungen
    assert not any("Beschriftung" in m for m in meldungen)


# -- Kontraktrollen ---------------------------------------------------------

def test_kontrakt_wird_aus_dem_dateinamen_gelesen():
    """NinjaTrader benennt die Exportdatei nach dem Kontrakt.

    Ihn von Hand nachtragen zu muessen waere eine Fehlerquelle - und ein
    falsch zugeordneter Kontrakt schoebe die Kerzen in das Zeitfenster eines
    anderen.
    """
    from werkzeuge.nt8_import import kontrakt_aus_name

    assert kontrakt_aus_name("MNQ SEP19.Last.txt") == ("MNQ", 2019, 9)
    assert kontrakt_aus_name("MNQ_DEC21_minute.txt") == ("MNQ", 2021, 12)
    assert kontrakt_aus_name("mnq-jun26.txt") == ("MNQ", 2026, 6)
    assert kontrakt_aus_name("irgendwas.csv") is None


def test_kontrakt_auch_in_numerischer_schreibweise():
    """Der Exportdialog auf Laurins Installation schreibt "MNQ 09-26.Last.txt",
    nicht "MNQ SEP26" - und die db\\minute-Ordner heissen ebenso.
    """
    from werkzeuge.nt8_import import kontrakt_aus_name

    assert kontrakt_aus_name("MNQ 09-26.Last.txt") == ("MNQ", 2026, 9)
    assert kontrakt_aus_name("MNQ 12-19.Last.txt") == ("MNQ", 2019, 12)
    assert kontrakt_aus_name("MNQ_03-20_minute.txt") == ("MNQ", 2020, 3)
    # 13 ist kein Monat - lieber None als ein stiller Fehlgriff.
    assert kontrakt_aus_name("MNQ 13-20.txt") is None


def test_rollplan_schluessel_passt_zu_kontrakt_aus_name(tmp_path):
    """main() schlaegt das Rollfenster mit (jahr, monat) nach - dem Paar, das
    kontrakt_aus_name liefert. Frueher stand dort das Dreitupel
    (wurzel, jahr, monat), das nie traf: der Import fiel still auf die
    gerechnete Acht-Tage-Formel zurueck, obwohl der Bestand vorlag.
    """
    from werkzeuge.nt8_import import kontrakt_aus_name, rollplan_aus_nt8

    ordner = tmp_path / "MNQ 09-26"
    ordner.mkdir()
    (ordner / "20260612.Last.ncd").write_bytes(b"x" * 5000)
    plan = rollplan_aus_nt8("MNQ", db_pfad=tmp_path)

    wurzel, jahr, monat = kontrakt_aus_name("MNQ 09-26.Last.txt")
    assert (jahr, monat) in plan
    assert (wurzel, jahr, monat) not in plan


def test_rollfenster_schliessen_luecken_und_ueberlappungsfrei_aneinander_an():
    """DER Punkt der ganzen Uebung.

    Die Kerzen liegen unter (instrument, timeframe, ts_utc) als
    Primaerschluessel, und der Import macht ein UPSERT. Ueberlappen sich zwei
    Kontraktfenster, ueberschreiben sie einander - und welcher Kontrakt am
    Ende in der Datenbank steht, haengt an der Reihenfolge der Importe.
    """
    from werkzeuge.nt8_import import rollfenster

    quartale = [(2026, 3), (2026, 6), (2026, 9), (2026, 12)]
    fenster = [rollfenster("MNQ", j, m, rolltage=8) for j, m in quartale]

    for (_, ende), (start, _) in zip(fenster, fenster[1:]):
        assert ende == start, "Fenster muessen luecken- und ueberlappungsfrei sein"


def test_rolltage_verschieben_das_fenster():
    from werkzeuge.nt8_import import rollfenster

    frueh = rollfenster("MNQ", 2026, 9, rolltage=15)
    spaet = rollfenster("MNQ", 2026, 9, rolltage=1)
    assert frueh[1] < spaet[1]


def test_fenster_endet_vor_dem_verfall():
    """Am Verfallstag selbst handelt niemand mehr den auslaufenden Kontrakt."""
    from datetime import date

    from common.instruments import get_instrument
    from werkzeuge.nt8_import import rollfenster

    verfall = get_instrument("MNQ").expiry_rule(2026, 9)
    _, bis = rollfenster("MNQ", 2026, 9, rolltage=8)
    assert bis.date() < verfall
    assert (verfall - bis.date()).days == 8


def test_gepackter_export_wird_gelesen(tmp_path):
    """NinjaTrader legt den Export je nach Version gepackt ab."""
    import gzip

    datei = tmp_path / "MNQ SEP19.txt.gz"
    with gzip.open(datei, "wt", encoding="utf-8") as f:
        f.write("20260902 140000;20000.25;20005.00;19998.50;20003.75;1234\n")

    df = lies_export(datei, "UTC")
    assert len(df) == 1
    assert df["close"].iloc[0] == 20003.75


# -- Formatnachweis und Anschlusspruefung -----------------------------------

def test_anschlusspruefung_akzeptiert_einen_rollsprung():
    """Ein Rollsprung bei MNQ liegt bei Dutzenden bis wenigen Hundert
    Punkten - Zinsdifferenz und Dividenden ueber ein Quartal."""
    from werkzeuge.nt8_import import pruefe_anschluss

    alt = _reihe(START, 300, basis=20000.0)
    neu = _reihe(START + timedelta(minutes=400), 300, basis=20180.0)

    bestanden, meldungen = pruefe_anschluss(neu, alt)
    assert bestanden, meldungen


def test_anschlusspruefung_erkennt_den_falschen_kontrakt():
    """Mehrere Tausend Punkte Sprung heisst: falsches Jahr oder falsches
    Instrument."""
    from werkzeuge.nt8_import import pruefe_anschluss

    alt = _reihe(START, 300, basis=20000.0)
    neu = _reihe(START + timedelta(minutes=400), 300, basis=8000.0)

    bestanden, meldungen = pruefe_anschluss(neu, alt)
    assert not bestanden
    assert any("kein Rollsprung" in m for m in meldungen)


def test_ohne_nachbarn_gibt_es_nichts_anzuschliessen():
    from werkzeuge.nt8_import import pruefe_anschluss

    leer = _reihe(START, 0)
    bestanden, _ = pruefe_anschluss(_reihe(START, 10), leer)
    assert bestanden


def test_anschluss_ist_relativ_nicht_in_absoluten_punkten():
    """MNQ stand 2019 bei 7.500 und 2026 bei 29.500 - 300 Punkte waren damals
    4 %, heute 1 %. Eine feste Punktgrenze schnitt die alten Kontrakte weg.
    """
    from werkzeuge.nt8_import import pruefe_anschluss

    # 1,4 % Sprung auf hohem Niveau: die groesste echte MNQ-Rolle. Muss durch.
    alt = _reihe(START, 300, basis=29000.0)
    neu = _reihe(START + timedelta(minutes=400), 300, basis=29406.0)  # +1,4 %
    bestanden, meldungen = pruefe_anschluss(neu, alt)
    assert bestanden, meldungen

    # 4 % Sprung: kein Rollsprung mehr, egal auf welchem Niveau.
    zu_weit = _reihe(START + timedelta(minutes=400), 300, basis=30200.0)
    bestanden, meldungen = pruefe_anschluss(zu_weit, alt)
    assert not bestanden
    assert any("kein Rollsprung" in m for m in meldungen)


def test_anschluss_ueberspringt_den_zeitlich_fernen_nachbarn():
    """Liegt erst der laufende Kontrakt in der Datenbank und wird ein sechs
    Jahre alter importiert, ist die naechste Kerze Jahre entfernt auf einem
    ganz anderen Kursniveau - das ist kein Anschlussfehler, das ist kein
    Nachbar. Frueher brach hier jeder Alt-Import ab.
    """
    from werkzeuge.nt8_import import pruefe_anschluss

    alt_2019 = _reihe(START, 300, basis=7500.0)
    laufend_2026 = _reihe(START + timedelta(days=2000), 300, basis=29500.0)

    bestanden, meldungen = pruefe_anschluss(alt_2019, laufend_2026)
    assert bestanden, meldungen
    assert any("kein direkter Nachbar" in m for m in meldungen)


def test_nachweis_wird_geschrieben_und_gelesen(tmp_path, monkeypatch):
    """Der Nachweis belegt den EXPORTWEG, nicht den einzelnen Kontrakt.

    Ohne ihn koennte kein alter Kontrakt importiert werden - alte Kontrakte
    ueberschneiden sich mit nichts, was 2026 gesammelt wurde.
    """
    from werkzeuge import nt8_import

    monkeypatch.setattr(nt8_import, "NACHWEIS", tmp_path / "nachweis.json")
    assert nt8_import.lies_nachweis() == {}

    nt8_import.schreibe_nachweis("MNQ", "1m", "America/New_York", 4321)
    daten = nt8_import.lies_nachweis()

    assert "MNQ/1m/America/New_York" in daten
    assert daten["MNQ/1m/America/New_York"]["gemeinsame_kerzen"] == 4321


def test_nachweis_gilt_je_zeitzone_getrennt(tmp_path, monkeypatch):
    """Eine andere Zeitzone ist ein anderer Exportweg - und der Nachweis
    darf sich nicht auf sie uebertragen."""
    from werkzeuge import nt8_import

    monkeypatch.setattr(nt8_import, "NACHWEIS", tmp_path / "nachweis.json")
    nt8_import.schreibe_nachweis("MNQ", "1m", "America/New_York", 500)
    daten = nt8_import.lies_nachweis()

    assert "MNQ/1m/UTC" not in daten


def test_kaputter_nachweis_wird_wie_keiner_behandelt(tmp_path, monkeypatch):
    from werkzeuge import nt8_import

    pfad = tmp_path / "nachweis.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    monkeypatch.setattr(nt8_import, "NACHWEIS", pfad)

    assert nt8_import.lies_nachweis() == {}


def test_rollplan_aus_dem_bestand_ist_lueckenlos_und_ueberschneidungsfrei(tmp_path):
    """Der Bestand weiss genauer als jede Formel, wann gerollt wurde.

    Am 30.08.2026 gegen die echten Daten geprueft: NinjaTrader rollte bis 2022
    mittwochs, ab 2023 freitags. Die Acht-Tage-Formel haette ab MAR23 drei bis
    vier Kalendertage zu frueh geschnitten.
    """
    from werkzeuge.nt8_import import rollplan_aus_nt8

    # Zwei Kontrakte mit je zwei Handelstagen nachbauen.
    for ordner, tage in (
        ("MNQ 06-26", ("20260315", "20260316")),
        ("MNQ 09-26", ("20260612", "20260613")),
    ):
        ziel = tmp_path / ordner
        ziel.mkdir()
        for tag in tage:
            (ziel / f"{tag}.Last.ncd").write_bytes(b"x" * 100)

    plan = rollplan_aus_nt8("MNQ", db_pfad=tmp_path)

    assert set(plan) == {(2026, 6), (2026, 9)}
    # Der aeltere endet genau dort, wo der neuere beginnt.
    assert plan[(2026, 6)][1] == plan[(2026, 9)][0]
    # Der laufende Kontrakt hat kein Ende.
    assert plan[(2026, 9)][1].year > 2090


def test_platzhalterdateien_ziehen_den_beginn_nicht_vor(tmp_path):
    """Sehr kleine Dateien sind Tage ohne Kerzen - etwa ein Feiertag."""
    from werkzeuge.nt8_import import rollplan_aus_nt8

    ordner = tmp_path / "MNQ 09-26"
    ordner.mkdir()
    (ordner / "20260601.Last.ncd").write_bytes(b"x" * 20)    # Platzhalter
    (ordner / "20260612.Last.ncd").write_bytes(b"x" * 5000)  # echte Kerzen

    plan = rollplan_aus_nt8("MNQ", db_pfad=tmp_path)
    assert plan[(2026, 9)][0].strftime("%Y-%m-%d") == "2026-06-12"


def test_ohne_nt8_ordner_bleibt_der_plan_leer(tmp_path):
    """Dann greift die gerechnete Rueckfallebene - und der Import sagt das."""
    from werkzeuge.nt8_import import rollplan_aus_nt8

    assert rollplan_aus_nt8("MNQ", db_pfad=tmp_path / "gibtsnicht") == {}
