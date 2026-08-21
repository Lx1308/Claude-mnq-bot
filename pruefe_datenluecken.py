"""Prueft die ntbridge-Datenbank auf Luecken in der Kerzenabdeckung.

Zweck
-----
Die Statistik dieses Projekts haengt daran, dass ohne Unterbrechung Kerzen
gesammelt werden. Faellt der Empfaenger, NinjaTrader oder der Laptop aus,
entsteht eine Luecke - und zwar lautlos. Dieses Skript macht solche Luecken
sichtbar.

Betriebssicherheit
------------------
Die Datenbank wird ausschliesslich LESEND geoeffnet (mode=ro). Das Skript
kann waehrend des laufenden Empfaengers ausgefuehrt werden; SQLite im
WAL-Modus erlaubt einen Schreiber plus mehrere Leser.

Aufruf
------
    .venv\\Scripts\\python.exe pruefe_datenluecken.py
    .venv\\Scripts\\python.exe pruefe_datenluecken.py --tage 3
    .venv\\Scripts\\python.exe pruefe_datenluecken.py --db data\\ntbridge.sqlite3

Wichtige Einschraenkung, bewusst so gebaut
------------------------------------------
NinjaTrader erzeugt eine Minutenkerze nur dann, wenn in dieser Minute
tatsaechlich gehandelt wurde. In duennen Phasen (Asien-Session, kurz vor
der Wartungspause) fehlen daher einzelne Minuten voellig legitim. Solche
Mini-Luecken sind KEIN Datenverlust.

Das Skript trennt deshalb:
  - erwartete Nicht-Handelszeit (Wartungspause, Wochenende)  -> ignoriert
  - kleine Luecken unterhalb der Schwelle                     -> nur gezaehlt
  - grosse Luecken ab der Schwelle                            -> einzeln gemeldet

Die Schwelle ist ueber --schwelle einstellbar. Sie ist eine Heuristik und
wird als solche ausgewiesen - das Skript behauptet nicht, jede gemeldete
Luecke sei ein Ausfall.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    print("FEHLER: zoneinfo nicht verfuegbar. Python 3.9+ noetig.")
    sys.exit(1)

try:
    CT = ZoneInfo("America/Chicago")
except Exception as exc:  # tzdata fehlt (kommt auf Windows vor)
    print("FEHLER: Zeitzone 'America/Chicago' nicht ladbar: %s" % exc)
    print("Abhilfe: .venv\\Scripts\\python.exe -m pip install tzdata")
    print("Ohne korrekte Zeitzone waere jede Aussage ueber Session-Grenzen")
    print("geraten - das Skript bricht deshalb ab, statt zu schaetzen.")
    sys.exit(1)


# Timeframe-Bezeichnung -> Laenge in Minuten.
# Die Tageskerze wird mit 23*60 angesetzt, weil eine CME-Session 23 Stunden
# dauert (Wartungspause 16:00-17:00 CT). 24*60 waere falsch.
TIMEFRAME_MINUTEN = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "60m": 60,
    "4h": 240,
    "1d": 23 * 60,
}


def ist_handelsminute(zeitpunkt_utc: datetime) -> bool:
    """Liegt dieser Zeitpunkt innerhalb der CME-Globex-Handelszeit?

    Globex laeuft Sonntag 17:00 CT bis Freitag 16:00 CT, mit taeglicher
    Wartungspause 16:00-17:00 CT. Gerechnet wird in boersenlokaler Zeit,
    damit die Sommerzeitumstellung korrekt behandelt wird.
    """
    ct = zeitpunkt_utc.astimezone(CT)
    wochentag = ct.weekday()  # Montag=0 ... Sonntag=6
    minute_des_tages = ct.hour * 60 + ct.minute

    if wochentag == 5:  # Samstag: durchgehend geschlossen
        return False
    if wochentag == 6:  # Sonntag: Eroeffnung 17:00 CT
        return minute_des_tages >= 17 * 60
    if wochentag == 4:  # Freitag: Schluss 16:00 CT
        return minute_des_tages < 16 * 60
    # Montag bis Donnerstag: durchgehend ausser Wartungspause
    return not (16 * 60 <= minute_des_tages < 17 * 60)


def finde_kerzentabelle(conn: sqlite3.Connection) -> tuple[str, dict[str, str]]:
    """Sucht die Tabelle mit den Kerzen und ordnet die Spaltennamen zu.

    Der genaue Tabellen- und Spaltenname von ntbridge/store.py wird hier
    NICHT vorausgesetzt, sondern aus der Datenbank selbst ermittelt. So
    bricht das Skript nicht, wenn der Store umbenannt wird.
    """
    tabellen = [
        zeile[0]
        for zeile in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    ]

    for tabelle in tabellen:
        spalten = [zeile[1] for zeile in conn.execute(f"PRAGMA table_info('{tabelle}')")]
        klein = {s.lower(): s for s in spalten}

        instrument = klein.get("instrument") or klein.get("symbol")
        timeframe = klein.get("timeframe") or klein.get("tf")
        zeitstempel = (
            klein.get("ts_utc")
            or klein.get("timestamp_utc")
            or klein.get("timestamputc")
            or klein.get("ts")
        )

        if instrument and timeframe and zeitstempel:
            return tabelle, {
                "instrument": instrument,
                "timeframe": timeframe,
                "ts": zeitstempel,
            }

    raise SystemExit(
        "FEHLER: Keine Tabelle mit den Spalten instrument/timeframe/zeitstempel\n"
        "gefunden. Gefundene Tabellen: %s" % (", ".join(tabellen) or "(keine)")
    )


def lese_zeitstempel(conn, tabelle, spalten, instrument, timeframe, ab_utc):
    """Liest die Zeitstempel einer Serie aufsteigend als UTC-datetime."""
    sql = (
        f"SELECT {spalten['ts']} FROM {tabelle} "
        f"WHERE {spalten['instrument']} = ? AND {spalten['timeframe']} = ? "
        f"ORDER BY {spalten['ts']} ASC"
    )
    roh = [zeile[0] for zeile in conn.execute(sql, (instrument, timeframe))]

    zeitstempel = []
    for wert in roh:
        moment = _nach_utc(wert)
        if moment is None:
            continue
        if ab_utc is None or moment >= ab_utc:
            zeitstempel.append(moment)
    return zeitstempel


def _nach_utc(wert) -> datetime | None:
    """Wandelt einen gespeicherten Zeitstempel in ein UTC-datetime um.

    Akzeptiert ISO-Text und Unix-Sekunden bzw. -Millisekunden, weil das
    Speicherformat hier nicht vorausgesetzt werden soll.
    """
    if isinstance(wert, (int, float)):
        sekunden = float(wert)
        if sekunden > 1e11:  # offensichtlich Millisekunden
            sekunden /= 1000.0
        return datetime.fromtimestamp(sekunden, tz=timezone.utc)

    if isinstance(wert, str):
        text = wert.strip().replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc)

    return None


def zaehle_fehlende_kerzen(vorher: datetime, nachher: datetime, tf_minuten: int) -> int:
    """Zaehlt, wie viele Kerzen zwischen zwei Zeitstempeln fehlen.

    Gezaehlt werden nur Zeitpunkte, die tatsaechlich in der Handelszeit
    liegen. Wartungspause und Wochenende erzeugen so keine Falschmeldung.
    """
    schritt = timedelta(minutes=tf_minuten)
    fehlend = 0
    moment = vorher + schritt
    # Sicherheitsgrenze, damit ein monatelanger Ausfall keine Endlosschleife wird
    obergrenze = 200_000

    while moment < nachher and fehlend < obergrenze:
        if ist_handelsminute(moment):
            fehlend += 1
        moment += schritt

    return fehlend


def formatiere(moment: datetime) -> str:
    """Zeigt einen Zeitpunkt in UTC und boersenlokaler Zeit."""
    return "%s UTC (%s CT)" % (
        moment.strftime("%Y-%m-%d %H:%M"),
        moment.astimezone(CT).strftime("%a %H:%M"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prueft die ntbridge-Datenbank auf Luecken in der Kerzenabdeckung."
    )
    parser.add_argument(
        "--db",
        default="data/ntbridge.sqlite3",
        help="Pfad zur Datenbank (Standard: data/ntbridge.sqlite3)",
    )
    parser.add_argument(
        "--tage",
        type=float,
        default=7.0,
        help="Nur die letzten N Tage pruefen (Standard: 7, 0 = alles)",
    )
    parser.add_argument(
        "--schwelle",
        type=int,
        default=5,
        help=(
            "Ab wie vielen fehlenden Kerzen eine Luecke einzeln gemeldet wird "
            "(Standard: 5). Kleinere Luecken sind in duennen Phasen normal."
        ),
    )
    args = parser.parse_args()

    pfad = Path(args.db).resolve()
    if not pfad.exists():
        print("FEHLER: Datenbank nicht gefunden: %s" % pfad)
        print("Tipp: Skript aus dem Projektordner heraus aufrufen.")
        return 1

    try:
        conn = sqlite3.connect("file:%s?mode=ro" % pfad.as_posix(), uri=True)
    except sqlite3.OperationalError as exc:
        print("FEHLER: Datenbank nicht lesbar: %s" % exc)
        return 1

    jetzt = datetime.now(timezone.utc)
    ab_utc = None if args.tage <= 0 else jetzt - timedelta(days=args.tage)

    tabelle, spalten = finde_kerzentabelle(conn)

    serien = list(
        conn.execute(
            f"SELECT {spalten['instrument']}, {spalten['timeframe']}, COUNT(*) "
            f"FROM {tabelle} "
            f"GROUP BY {spalten['instrument']}, {spalten['timeframe']} "
            f"ORDER BY {spalten['instrument']}, {spalten['timeframe']}"
        )
    )

    print("=" * 74)
    print("Datenluecken-Pruefung")
    print("=" * 74)
    print("Datenbank : %s" % pfad)
    print("Tabelle   : %s" % tabelle)
    print("Geprueft  : %s" % ("gesamte Historie" if ab_utc is None
                              else "letzte %g Tage" % args.tage))
    print("Schwelle  : ab %d fehlenden Kerzen wird einzeln gemeldet" % args.schwelle)
    print("Jetzt     : %s" % formatiere(jetzt))
    print()

    if not serien:
        print("Es sind keine Kerzen in der Datenbank. Laeuft der Empfaenger,")
        print("und ist die ClaudeBridge an einem Chart aktiv?")
        return 1

    handel_offen = ist_handelsminute(jetzt)
    print("Markt gerade: %s" % ("offen" if handel_offen else "geschlossen"))
    print()

    gesamt_gross = 0
    gesamt_klein = 0
    warnungen = []

    for instrument, timeframe, anzahl in serien:
        tf_minuten = TIMEFRAME_MINUTEN.get(str(timeframe).lower())
        print("-" * 74)
        print("%s  %s   (%d Kerzen in der Datenbank)" % (instrument, timeframe, anzahl))

        if tf_minuten is None:
            print("  Timeframe unbekannt - uebersprungen. Bitte TIMEFRAME_MINUTEN")
            print("  im Skript ergaenzen, statt hier zu raten.")
            continue

        zeitstempel = lese_zeitstempel(
            conn, tabelle, spalten, instrument, timeframe, ab_utc
        )

        if len(zeitstempel) < 2:
            print("  Zu wenige Kerzen im Pruefzeitraum fuer eine Aussage.")
            continue

        print("  Zeitraum : %s" % formatiere(zeitstempel[0]))
        print("             bis %s" % formatiere(zeitstempel[-1]))

        # Wie alt ist die juengste Kerze, gemessen in Handelszeit?
        alter_minuten = (jetzt - zeitstempel[-1]).total_seconds() / 60.0
        if handel_offen and alter_minuten > max(3 * tf_minuten, 10):
            warnungen.append(
                "%s %s: juengste Kerze ist %.0f Minuten alt, obwohl der Markt "
                "offen ist." % (instrument, timeframe, alter_minuten)
            )
            print("  ACHTUNG: juengste Kerze %.0f Minuten alt bei offenem Markt."
                  % alter_minuten)

        gross = []
        klein = 0

        for vorher, nachher in zip(zeitstempel, zeitstempel[1:]):
            if (nachher - vorher) <= timedelta(minutes=tf_minuten):
                continue
            fehlend = zaehle_fehlende_kerzen(vorher, nachher, tf_minuten)
            if fehlend == 0:
                continue  # vollstaendig durch Pause/Wochenende erklaert
            if fehlend >= args.schwelle:
                gross.append((vorher, nachher, fehlend))
            else:
                klein += 1

        gesamt_gross += len(gross)
        gesamt_klein += klein

        if not gross:
            print("  Keine groessere Luecke gefunden.")
        else:
            print("  %d groessere Luecke(n):" % len(gross))
            for vorher, nachher, fehlend in gross[:20]:
                dauer = (nachher - vorher).total_seconds() / 60.0
                print("    %s -> fehlend %d Kerzen (%.0f Min Abstand)"
                      % (formatiere(vorher), fehlend, dauer))
            if len(gross) > 20:
                print("    ... und %d weitere (nicht angezeigt)" % (len(gross) - 20))

        if klein:
            print("  %d kleine Luecke(n) unter der Schwelle - in duennen Phasen"
                  % klein)
            print("  normal, da NinjaTrader ohne Handel keine Kerze erzeugt.")

    conn.close()

    print()
    print("=" * 74)
    print("ERGEBNIS")
    print("=" * 74)
    print("Groessere Luecken : %d" % gesamt_gross)
    print("Kleine Luecken    : %d (nur gezaehlt, kein Ausfall-Verdacht)"
          % gesamt_klein)

    for warnung in warnungen:
        print("WARNUNG: %s" % warnung)

    if gesamt_gross == 0 and not warnungen:
        print()
        print("Die Datensammlung war im Pruefzeitraum durchgehend.")
        return 0

    print()
    print("Groessere Luecken bedeuten nicht zwingend einen Defekt - moegliche")
    print("Ursachen sind Laptop im Energiesparmodus, beendeter Empfaenger,")
    print("Neustart von NinjaTrader oder ein Ausfall der Datenverbindung.")
    print("Die betroffenen Zeitraeume oben mit den Logs abgleichen.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
