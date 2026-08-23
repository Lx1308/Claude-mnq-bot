"""Einmaliger CSV-Auszug aus der Dukascopy-Naeherungshistorie.

Was das ist -- und was es nicht ist
-----------------------------------
Das ist **kein DataProvider**. Ein richtiger Dukascopy-Provider (Registrierung
in ``backtest/data/__init__.py``, Sessionfilter, Herkunftswarnung im Report)
steht als P0-Punkt im Masterplan und ist Laurins Entscheidung, nicht die eines
unbeaufsichtigten Laufs. Dieses Skript ist das Gegenteil davon: ein Werkzeug
fuer einen einzelnen, informativen Probelauf, das eine CSV nach ``/tmp``
schreibt und danach vergessen werden darf.

Warum ueberhaupt
----------------
``CsvDataProvider`` liest CSV, die Naeherungshistorie liegt in SQLite. Ohne
Bruecke laesst sich die Strategiebibliothek auf zehn Jahren Kursverlauf
ueberhaupt nicht vermessen -- und ohne Vermessung bleibt "wie schlaegt sich
das Regelwerk eigentlich" eine unbeantwortete Frage.

Die Warnung reist mit
---------------------
Die Tabelle ``herkunft`` der Quelldatei sagt unmissverstaendlich: CFD auf den
Nasdaq-100-Index, kein MNQ-Futures, kein gehandeltes Volumen. Das Skript
schreibt diese Warnung als Kommentarzeilen in eine Begleitdatei neben die CSV
(nicht in die CSV selbst -- ``pd.read_csv`` stolperte darueber). Ergebnisse auf
diesen Daten sind **rein informativ** (Invariante 10).

Aufruf::

    python3 werkzeuge/python_linux.py werkzeuge/dukascopy_export.py \\
        --minuten 5 --ziel /tmp/DUKA_5m.csv

Kerzenbeschriftung
------------------
Die Quelle traegt bereits die **Schlusszeit** je Kerze (Invariante 9): die
erste Kerze der Historie heisst 06:01, nicht 06:00. Beim Zusammenfassen auf
groebere Kerzen wird deshalb erst auf Startzeit zurueckgerechnet, dann
gruppiert und am Ende wieder auf die Schlusszeit gesetzt. Wer das ueberspringt,
verschiebt die ganze Reihe um ein Kerzenfenster, und **an den Kursen sieht man
das nicht** -- genau der Fehler, der bei dieser Quelle schon einmal passiert
ist.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

PROJEKTWURZEL = Path(__file__).resolve().parents[1]
QUELLE = PROJEKTWURZEL / "data" / "dukascopy_nas100_1m.sqlite3"


def lade(quelle: Path, von: str | None, bis: str | None) -> pd.DataFrame:
    """Liest die Minutenkerzen schreibgeschuetzt aus der SQLite-Datei."""
    if not quelle.exists():
        raise SystemExit("Quelldatei nicht gefunden: %s" % quelle)

    # immutable=1: der Downloader kann parallel laufen, gelesen wird nur.
    verbindung = sqlite3.connect("file:%s?mode=ro&immutable=1" % quelle, uri=True)
    try:
        bedingungen, werte = [], []
        if von:
            bedingungen.append("ts_utc >= ?")
            werte.append(von)
        if bis:
            bedingungen.append("ts_utc <= ?")
            werte.append(bis)
        wo = (" where " + " and ".join(bedingungen)) if bedingungen else ""
        frame = pd.read_sql_query(
            "select ts_utc, open, high, low, close, volume from bars%s order by ts_utc" % wo,
            verbindung,
            params=werte,
        )
        herkunft = dict(verbindung.execute("select schluessel, wert from herkunft"))
    finally:
        verbindung.close()

    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("ts_utc"), utc=True))
    frame.attrs["herkunft"] = herkunft
    return frame


def verdichten(minuten: pd.DataFrame, fenster: int) -> pd.DataFrame:
    """Fasst Minutenkerzen zu groeberen Kerzen zusammen -- schlusszeitbeschriftet."""
    if fenster == 1:
        return minuten

    # Auf Startzeit zurueck, gruppieren, wieder auf Schlusszeit. Siehe Docstring.
    versetzt = minuten.copy()
    versetzt.index = versetzt.index - pd.Timedelta(minutes=1)
    grob = versetzt.resample("%dmin" % fenster, closed="left", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    grob = grob.dropna(subset=["open", "high", "low", "close"])
    grob.index = grob.index + pd.Timedelta(minutes=fenster)
    grob.index.name = "timestamp"
    return grob


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--quelle",
        default=str(QUELLE),
        help="SQLite-Quelldatei. Ueber einen Netz- oder FUSE-Mount ist ein "
             "voller Tabellendurchlauf zaeh; dann vorher lokal kopieren.",
    )
    parser.add_argument("--minuten", type=int, default=5, help="Kerzenlaenge (Standard 5)")
    parser.add_argument("--ziel", default="/tmp/DUKA_5m.csv", help="Zieldatei")
    parser.add_argument("--von", default=None, help="ISO-Zeitstempel, inklusive")
    parser.add_argument("--bis", default=None, help="ISO-Zeitstempel, inklusive")
    args = parser.parse_args(argv)

    minuten = lade(Path(args.quelle), args.von, args.bis)
    print("%d Minutenkerzen gelesen (%s bis %s)"
          % (len(minuten), minuten.index[0], minuten.index[-1]), file=sys.stderr)

    grob = verdichten(minuten, args.minuten)
    grob.index.name = "timestamp"
    ziel = Path(args.ziel)
    grob.to_csv(ziel)
    print("%d Kerzen a %d Minuten -> %s" % (len(grob), args.minuten, ziel), file=sys.stderr)

    begleit = ziel.with_suffix(ziel.suffix + ".HERKUNFT.txt")
    zeilen = ["Herkunft der Datei %s" % ziel.name, ""]
    for schluessel, wert in sorted(minuten.attrs["herkunft"].items()):
        zeilen.append("%s: %s" % (schluessel, wert))
    zeilen.append("")
    zeilen.append("Kerzenlaenge: %d Minuten, Beschriftung = Schlusszeit." % args.minuten)
    begleit.write_text("\n".join(zeilen), encoding="utf-8")
    print("Herkunftsvermerk -> %s" % begleit, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
