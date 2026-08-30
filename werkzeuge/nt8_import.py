"""Historie aus NinjaTrader importieren - mit erzwungenem Kreuzvergleich.

Warum dieses Werkzeug existiert
-------------------------------
Fuer Research reichen die Kerzen nicht, die der Indikator beim Chartladen
mitschickt: er liefert, was der Chart geladen hat, und das sind in der Praxis
Tage bis Wochen. NinjaTrader haelt aber deutlich mehr vor - auf dieser
Installation liegen MNQ-Minutendaten von 30 Kontrakten zurueck bis 2019 unter
``Documents\\NinjaTrader 8\\db\\minute\\``.

Warum NICHT direkt aus den .ncd-Dateien
---------------------------------------
Die Dateien dort sind ein hauseigenes, variabel bit-gepacktes Binaerformat.
Der Kopf ist leicht zu lesen (Version, Ticksize, Basispreis, .NET-Zeitstempel),
der Koerper nicht: rund 7,8 Byte je Kerze, also keine feste Satzlaenge.

Ein rueckentwickelter Parser koennte hier jahrelang unbemerkt falsche Kurse
liefern - genau der Fehlertyp, an dem die Dukascopy-Daten schon einmal
gescheitert sind (Invariante 9: die Reihe sah lueckenlos und plausibel aus,
und erst der Kreuzvergleich gegen echte MNQ-Kerzen zeigte r = -0,06 statt
+0,95). Eine Forschungsdatenbasis auf so etwas zu stellen waere der teuerste
denkbare Fehler.

Stattdessen: NinjaTraders **eigener Export**. Dokumentiertes Textformat, von
NinjaTrader selbst geschrieben, kein Ratespiel.

    Tools -> Historical Data -> Export
      Instrument : MNQ 09-26 (bzw. der gewuenschte Kontrakt)
      Type       : Minute
      From/To    : gewuenschter Zeitraum
      -> speichert eine .txt je Instrument

Der Kreuzvergleich ist Pflicht
------------------------------
Vor dem Schreiben wird der Import gegen die bereits vorhandenen Kerzen aus
``ntbridge.sqlite3`` geprueft - die kamen ueber ``ClaudeBridge.cs`` aus
NinjaTrader selbst und sind damit die Referenz. Weicht auch nur eine
gemeinsame Kerze ab, bricht der Import ab.

Geprueft wird ausdruecklich auch die **Beschriftung**: NinjaTrader
beschriftet eine Kerze mit dem ENDE ihres Fensters. Waere der Export
linksbuendig beschriftet, laege die ganze Reihe eine Minute daneben, und an
den Kursen selbst waere das nicht zu sehen.

Aufruf
------
    .venv\\Scripts\\python.exe werkzeuge\\nt8_import.py --pruefen datei.txt
    .venv\\Scripts\\python.exe werkzeuge\\nt8_import.py --schreiben datei.txt
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.config import Config  # noqa: E402
from ntbridge.store import BarStore  # noqa: E402

#: Wie viele Kerzen mindestens uebereinstimmen muessen, damit der
#: Kreuzvergleich als aussagekraeftig gilt. Zwei zufaellig passende Kerzen
#: waeren kein Beleg.
MIN_UEBERLAPPUNG = 200

#: Groesste zulaessige Abweichung eines Kurses. Nicht 0: der Export rundet
#: auf die Ticksize, die Datenbank haelt Fliesskomma. Ein Achtel Tick ist
#: kleiner als jede echte Preisbewegung und groesser als jeder Rundungsrest.
MAX_ABWEICHUNG = 0.03


def lies_export(pfad: Path, zeitzone: str) -> pd.DataFrame:
    """NinjaTraders Exportformat lesen.

    Erwartet wird je Zeile ``yyyyMMdd HHmmss;open;high;low;close;volume``.
    Semikolon ist NinjaTraders Vorgabe; Komma wird ebenfalls akzeptiert, weil
    das Trennzeichen im Exportdialog umstellbar ist.

    Die Zeitstempel des Exports sind **ohne Zeitzone**. Welche gemeint ist,
    haengt an NinjaTraders Einstellung; deshalb ist sie hier ein Pflichtargument
    und wird nicht geraten. Eine falsch angenommene Zeitzone verschoebe die
    ganze Reihe um Stunden - und die Kurse saehen weiter plausibel aus.
    """
    zeilen = pfad.read_text(encoding="utf-8", errors="replace").splitlines()
    saetze: list[tuple] = []
    fehlerhaft = 0

    for zeile in zeilen:
        zeile = zeile.strip()
        if not zeile:
            continue
        teile = zeile.split(";") if ";" in zeile else zeile.split(",")
        if len(teile) < 6:
            fehlerhaft += 1
            continue
        try:
            zeitpunkt = datetime.strptime(teile[0].strip(), "%Y%m%d %H%M%S")
            saetze.append((
                zeitpunkt,
                float(teile[1]), float(teile[2]), float(teile[3]),
                float(teile[4]), float(teile[5]),
            ))
        except ValueError:
            fehlerhaft += 1

    if fehlerhaft:
        print(f"  {fehlerhaft} unlesbare Zeilen uebersprungen.", file=sys.stderr)
    if not saetze:
        raise SystemExit(
            f"Keine lesbaren Kerzen in {pfad}. Erwartet wird "
            "'yyyyMMdd HHmmss;open;high;low;close;volume'."
        )

    df = pd.DataFrame(
        saetze, columns=["ts", "open", "high", "low", "close", "volume"]
    )
    index = pd.DatetimeIndex(df.pop("ts")).tz_localize(ZoneInfo(zeitzone))
    df.index = index.tz_convert("UTC")
    return df.sort_index()


def kreuzvergleich(
    neu: pd.DataFrame, referenz: pd.DataFrame
) -> tuple[bool, list[str]]:
    """Stimmen die gemeinsamen Kerzen ueberein?

    Liefert (bestanden, Meldungen). Bestanden ist der Vergleich nur, wenn
    genug gemeinsame Zeitstempel existieren UND alle vier Kurse je Kerze
    innerhalb der Toleranz liegen.
    """
    meldungen: list[str] = []
    gemeinsam = neu.index.intersection(referenz.index)

    if len(gemeinsam) < MIN_UEBERLAPPUNG:
        meldungen.append(
            f"Nur {len(gemeinsam)} gemeinsame Kerzen (noetig: {MIN_UEBERLAPPUNG}). "
            "Der Vergleich waere nicht aussagekraeftig."
        )
        # Der haeufigste Grund fuer null Ueberlappung ist eine um eine Minute
        # verschobene Beschriftung. Das ausdruecklich pruefen, statt den
        # Nutzer raten zu lassen.
        for versatz in (-1, 1):
            verschoben = neu.copy()
            verschoben.index = verschoben.index + pd.Timedelta(minutes=versatz)
            treffer = verschoben.index.intersection(referenz.index)
            if len(treffer) > len(gemeinsam):
                meldungen.append(
                    f"HINWEIS: um {versatz:+d} Minute verschoben gaebe es "
                    f"{len(treffer)} statt {len(gemeinsam)} Treffer. Der Export "
                    "ist dann anders beschriftet als die Datenbank - "
                    "NinjaTrader beschriftet eine Kerze mit dem ENDE ihres "
                    "Fensters (Invariante 9)."
                )
        return False, meldungen

    a = neu.loc[gemeinsam].sort_index()
    b = referenz.loc[gemeinsam].sort_index()
    abweichungen: dict[str, float] = {}
    for spalte in ("open", "high", "low", "close"):
        groesste = float((a[spalte] - b[spalte]).abs().max())
        abweichungen[spalte] = groesste

    schlimmste = max(abweichungen.values())
    meldungen.append(f"{len(gemeinsam)} gemeinsame Kerzen geprueft.")
    meldungen.append(
        "  groesste Abweichung: "
        + ", ".join(f"{s} {w:.4f}" for s, w in abweichungen.items())
    )

    # Der Versatzvergleich kommt VOR dem Toleranzurteil, weil er die
    # aussagekraeftigere Diagnose liefert. "Die Kurse weichen ab" laesst offen,
    # ob es der falsche Kontrakt, die falsche Zeitzone oder eine verschobene
    # Beschriftung ist; "um eine Minute verschoben passt es besser" sagt genau,
    # was zu tun ist.
    #
    # Und er ist auch dann noetig, wenn die Kurse innerhalb der Toleranz
    # liegen: in einem ruhigen Markt aehneln sich benachbarte Minuten so sehr,
    # dass eine verschobene Reihe durchrutschen wuerde.
    for versatz in (-1, 1):
        verschoben = neu.copy()
        verschoben.index = verschoben.index + pd.Timedelta(minutes=versatz)
        treffer = verschoben.index.intersection(referenz.index)
        if len(treffer) < MIN_UEBERLAPPUNG:
            continue
        va = verschoben.loc[treffer].sort_index()
        vb = referenz.loc[treffer].sort_index()
        versatz_fehler = float((va["close"] - vb["close"]).abs().max())
        if versatz_fehler < schlimmste:
            meldungen.append(
                f"ABBRUCH: um {versatz:+d} Minute verschoben passt der Export "
                f"BESSER ({versatz_fehler:.4f} statt {schlimmste:.4f}). Die "
                "Beschriftung stimmt nicht - NinjaTrader beschriftet eine "
                "Kerze mit dem ENDE ihres Fensters (Invariante 9)."
            )
            return False, meldungen

    if schlimmste > MAX_ABWEICHUNG:
        meldungen.append(
            f"ABBRUCH: {schlimmste:.4f} Punkte Abweichung ueberschreiten die "
            f"Toleranz von {MAX_ABWEICHUNG}. Ein Zeitversatz wurde geprueft und "
            "ausgeschlossen - es bleibt ein anderer Kontrakt, eine andere "
            "Zeitzone oder ein anderer Datentyp (Last/Bid/Ask)."
        )
        return False, meldungen

    meldungen.append("Kreuzvergleich bestanden.")
    return True, meldungen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nt8_import",
        description="Importiert einen NinjaTrader-Historienexport nach Pruefung.",
    )
    parser.add_argument("datei", type=Path)
    parser.add_argument("--symbol", default="MNQ")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument(
        "--zeitzone",
        default="America/New_York",
        help="Zeitzone der Zeitstempel im Export. NinjaTrader exportiert in "
             "seiner Anzeigezeitzone - im Zweifel im Exportdialog nachsehen.",
    )
    parser.add_argument(
        "--schreiben",
        action="store_true",
        help="Nach bestandener Pruefung tatsaechlich schreiben. Ohne diesen "
             "Schalter wird nur geprueft und berichtet.",
    )
    parser.add_argument("--database", default=None)
    args = parser.parse_args(argv)

    if not args.datei.exists():
        print(f"Datei nicht gefunden: {args.datei}", file=sys.stderr)
        return 2

    config = Config.load(PROJECT_ROOT / "config.yaml")
    datenbank = Path(args.database or config.ntbridge.database)
    if not datenbank.is_absolute():
        datenbank = PROJECT_ROOT / datenbank

    print(f"Lese {args.datei} ...")
    neu = lies_export(args.datei, args.zeitzone)
    print(f"  {len(neu)} Kerzen, {neu.index[0]} bis {neu.index[-1]}")

    speicher = BarStore(datenbank)
    try:
        referenz = speicher.load_frame(args.symbol, args.timeframe)
        print(f"  Referenz in der Datenbank: {len(referenz)} Kerzen")

        if referenz.empty:
            print(
                "\nABBRUCH: keine Referenzkerzen in der Datenbank.\n"
                "Ohne Kreuzvergleich wird nicht importiert - eine um eine "
                "Minute verschobene oder in der falschen Zeitzone gelesene "
                "Reihe saehe lueckenlos und plausibel aus. Starte zuerst die "
                "Bridge und lass NinjaTrader ein paar hundert Kerzen liefern.",
                file=sys.stderr,
            )
            return 3

        bestanden, meldungen = kreuzvergleich(neu, referenz)
        print()
        for meldung in meldungen:
            print(" ", meldung)

        if not bestanden:
            print("\nEs wurde nichts geschrieben.", file=sys.stderr)
            return 3

        if not args.schreiben:
            neue_kerzen = len(neu.index.difference(referenz.index))
            print(
                f"\nPruefung bestanden. {neue_kerzen} Kerzen waeren neu.\n"
                "Zum Schreiben mit --schreiben erneut aufrufen."
            )
            return 0

        saetze = [
            {
                "timestampUtc": zeitpunkt.isoformat(),
                "instrument": args.symbol,
                "timeframe": args.timeframe,
                "open": float(zeile["open"]), "high": float(zeile["high"]),
                "low": float(zeile["low"]), "close": float(zeile["close"]),
                "volume": float(zeile["volume"]),
                "source": "nt8_export",
            }
            for zeitpunkt, zeile in neu.iterrows()
        ]
        ergebnis = speicher.ingest(
            saetze,
            known_timeframes={args.timeframe},
            symbol_map={},
        )
        print(
            f"\nGeschrieben: {ergebnis.accepted} angenommen, "
            f"{ergebnis.rejected} abgelehnt."
        )
        if ergebnis.reasons:
            for grund, anzahl in ergebnis.reasons.items():
                print(f"  {grund}: {anzahl}")
        return 0
    finally:
        speicher.close()


if __name__ == "__main__":
    raise SystemExit(main())
