"""Laedt Dukascopy-Historie als Ein-Minuten-Kerzen in eine eigene SQLite-Datei.

    .venv\\Scripts\\python.exe lade_dukascopy.py --jahre 10
    .venv\\Scripts\\python.exe lade_dukascopy.py --von 2024-01-01 --bis 2024-02-01
    .venv\\Scripts\\python.exe lade_dukascopy.py --jahre 10 --parallel 16

NAEHERUNG, KEINE MESSUNG
------------------------
Was hier geladen wird, ist ein **CFD auf den Nasdaq-100-Index** von der
Dukascopy Bank - kein MNQ-Futures. Andere Preisbildung, kein echtes
Handelsvolumen, keine Kontraktablaeufe, andere Sessionstruktur. Ergebnisse
eines Backtests auf diesen Daten sind **rein informativ**. Ausfuehrlich in
``backtest/data/dukascopy.py``; die Warnung steht ausserdem in der erzeugten
Datei selbst (Tabelle ``herkunft``).

DAUER - vorher lesen
--------------------
Eine Stunde Historie sind rund 30.000 Ticks. Zehn Jahre haben etwa 87.600
Stunden. Seriell gemessen: rund 6 Sekunden je Stunde, also ueber **fuenf
Tage** am Stueck. Deshalb laeuft der Download parallel und ist
**wiederaufnehmbar**: bereits geholte Stunden stehen in der Datenbank und
werden uebersprungen. Ein Abbruch mit Strg+C kostet nichts als die gerade
laufenden Anfragen.

Mit ``--parallel 12`` sind es erfahrungsgemaess wenige Stunden. Hoehere Werte
sind nicht unbedingt schneller - Dukascopy antwortet dann mit HTTP 503.
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from backtest.data.dukascopy import (
    INSTRUMENTE,
    DukascopyFehler,
    dekodiere_ticks,
    entpacke,
    stunden_url,
    ticks_zu_minuten,
)
from backtest.data.dukascopy import BROWSER_HEADER
from backtest.data.dukascopy_store import DukascopyStore

PROJEKT = Path(__file__).resolve().parent
VORGABE_DATENBANK = PROJEKT / "data" / "dukascopy_nas100_1m.sqlite3"


def stunden(von: datetime, bis: datetime):
    moment = von.replace(minute=0, second=0, microsecond=0)
    while moment < bis:
        yield moment
        moment += timedelta(hours=1)


# Dukascopy drosselt bei zu vielen Anfragen mit HTTP 503. Das ist
# voruebergehend und kein Grund, die Stunde als fehlerhaft abzuschreiben -
# bei 87.600 Stunden trifft es sonst zwangslaeufig einen erheblichen Teil.
VERSUCHE = 4
WARTE_GRUNDWERT = 2.0


def hole_eine(session: requests.Session, instrument, stunde: datetime):
    """Eine Stunde holen. Gibt (stunde, kerzen, fehler) zurueck."""
    letzter_fehler = "unbekannt"

    for versuch in range(VERSUCHE):
        try:
            antwort = session.get(
                stunden_url(instrument, stunde), headers=BROWSER_HEADER, timeout=30
            )
            if antwort.status_code == 404:
                # Stunde ausserhalb der Historie - kein Fehler, kein Neuversuch.
                return stunde, ticks_zu_minuten(
                    dekodiere_ticks(b"", stunde, instrument.preis_faktor)
                ), None
            if antwort.status_code == 200:
                ticks = dekodiere_ticks(
                    entpacke(antwort.content), stunde, instrument.preis_faktor
                )
                return stunde, ticks_zu_minuten(ticks), None

            letzter_fehler = f"HTTP {antwort.status_code}"
            if antwort.status_code not in (429, 500, 502, 503, 504):
                return stunde, None, letzter_fehler  # dauerhaft, nicht wiederholen
        except (requests.RequestException, DukascopyFehler) as fehler:
            letzter_fehler = str(fehler)

        if versuch < VERSUCHE - 1:
            # Exponentiell warten, damit die Drosselung sich loesen kann.
            time.sleep(WARTE_GRUNDWERT * (2 ** versuch))

    return stunde, None, f"{letzter_fehler} (nach {VERSUCHE} Versuchen)"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="lade_dukascopy",
        description="Laedt Dukascopy-Naeherungshistorie (Nasdaq-100-CFD) als 1m-Kerzen.",
    )
    p.add_argument("--instrument", default="NAS100", choices=sorted(INSTRUMENTE))
    p.add_argument("--jahre", type=float, help="Die letzten N Jahre (statt --von/--bis)")
    p.add_argument("--von", help="Startdatum JJJJ-MM-TT")
    p.add_argument("--bis", help="Enddatum JJJJ-MM-TT (exklusiv)")
    p.add_argument("--parallel", type=int, default=12)
    p.add_argument("--db", default=str(VORGABE_DATENBANK))
    args = p.parse_args(argv)

    instrument = INSTRUMENTE[args.instrument]
    jetzt = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    if args.von:
        von = datetime.fromisoformat(args.von).replace(tzinfo=timezone.utc)
        bis = (
            datetime.fromisoformat(args.bis).replace(tzinfo=timezone.utc)
            if args.bis else jetzt
        )
    elif args.jahre:
        von, bis = jetzt - timedelta(days=365.25 * args.jahre), jetzt
    else:
        print("Bitte --jahre oder --von angeben.", file=sys.stderr)
        return 2

    print("=" * 72)
    print("Dukascopy-Download - NAEHERUNG, kein MNQ-Futures")
    print("=" * 72)
    print(f"Instrument : {instrument.symbol}  ({args.instrument})")
    print(f"Zeitraum   : {von:%Y-%m-%d} bis {bis:%Y-%m-%d}")
    print(f"Datenbank  : {args.db}")
    print()
    print(instrument.beschreibung)
    print()

    with DukascopyStore(args.db, instrument) as store:
        offen = [s for s in stunden(von, bis) if not store.ist_geholt(s)]
        gesamt = len(offen)
        if not gesamt:
            print("Alle Stunden im Zeitraum sind bereits geholt.")
            print(f"Bestand: {store.anzahl_kerzen()} Kerzen.")
            return 0

        print(f"Offen: {gesamt} Stunden (bereits geholt: {store.anzahl_stunden()})")
        print(f"Parallel: {args.parallel}. Abbruch mit Strg+C ist gefahrlos -")
        print("der naechste Lauf setzt an derselben Stelle fort.")
        print()

        start = time.time()
        fertig = kerzen_gesamt = fehler = 0
        session = requests.Session()

        try:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                auftraege = {
                    pool.submit(hole_eine, session, instrument, s): s for s in offen
                }
                for zukunft in as_completed(auftraege):
                    stunde, kerzen, problem = zukunft.result()
                    fertig += 1
                    if problem:
                        fehler += 1
                        if fehler <= 5:
                            print(f"  FEHLER {stunde:%Y-%m-%d %Hh}: {problem}")
                    else:
                        kerzen_gesamt += store.speichere_stunde(stunde, kerzen)

                    if fertig % 200 == 0 or fertig == gesamt:
                        dauer = time.time() - start
                        rest = (gesamt - fertig) * dauer / max(fertig, 1)
                        print(
                            f"  {fertig}/{gesamt} Stunden, {kerzen_gesamt} Kerzen, "
                            f"{fehler} Fehler, noch ~{rest/60:.0f} min"
                        )
        except KeyboardInterrupt:
            print("\nAbgebrochen. Der Fortschritt ist gespeichert.")

        print()
        print("=" * 72)
        print(f"Kerzen in der Datenbank : {store.anzahl_kerzen()}")
        print(f"Geholte Stunden         : {store.anzahl_stunden()}")
        print(f"Fehler                  : {fehler}")
        if fehler:
            print("Fehlerhafte Stunden sind NICHT als geholt vermerkt -")
            print("ein erneuter Lauf holt genau sie nach.")
        print()
        print("ERINNERUNG: Naeherungsdaten. Backtests darauf sind rein informativ.")

    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
