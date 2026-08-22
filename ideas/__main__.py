"""Fuehrt einen Protokollierungslauf der Ideen-Erkennung aus.

    python -m ideas                 # ein Lauf ueber die juengsten Kerzen
    python -m ideas --probelauf     # rechnen, aber nichts schreiben
    python -m ideas --kein-kalender # ohne Blackout-Abfrage (kein Netz)

Laeuft **einmal** durch und beendet sich. Fuer den Dauerbetrieb gehoert er
in die Windows-Aufgabenplanung - genauso wie ``pruefe_datenluecken.py``.

WARUM EIN EINZELLAUF UND KEIN DAUERPROZESS
------------------------------------------
Ein dauerhaft laufender Prozess muesste den Kerzenspeicher pollen und haette
seinen eigenen Zustand, seine eigenen Absturzszenarien und sein eigenes
Neustartproblem. Ein Einzellauf ist zustandslos: er liest, was da ist,
schreibt was fehlt, und ist fertig. Der Speicher ist idempotent, ein Lauf
zu viel schadet also nicht.

WARUM REGELMAESSIG UND NICHT GESAMMELT
--------------------------------------
Der Blackout-Filter kann nur ueber die letzten Tage Auskunft geben (siehe
``ideas/kalender.py``). Wer einmal im Monat aufholt, bekommt fuer fast alle
Ideen "Blackout nicht pruefbar" - protokolliert, aber weniger wert. Der
Lauf sollte deshalb mindestens taeglich laufen.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from common.config import Config, ConfigError
from common.logging_setup import log_event, setup_logging
from ideas.kalender import KalenderBlackout
from ideas.pipeline import protokolliere
from ideas.setups import pruefe_konfiguration
from ideas.store import IdeenStore
from ntbridge.store import BarStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

log = logging.getLogger("ideas")


def _baue_blackout_pruefer(config: Config, symbol: str):
    """Verdrahtet den Wirtschaftskalender - nur hier, nicht im Paket.

    ``ideas`` haengt bewusst nicht an ``mcp_server``: die Blackout-Schicht
    kennt nur ein Protokoll. Die konkrete Klasse kommt erst an dieser
    Kante dazu, damit die beiden Oberschichten nicht verwachsen.
    """
    from mcp_server.calendar_provider import (
        CalendarService,
        CalendarSettings,
        ForexFactoryProvider,
        FredProvider,
    )
    from common.config import Secrets

    try:
        secrets = Secrets.load(str(PROJECT_ROOT / ".env"))
        fred_key = secrets.fred_api_key
    except Exception:
        # Ohne .env laeuft der Kalender trotzdem: Forex Factory braucht
        # keinen Schluessel. Nur die Actual-Werte fehlen, und die sind
        # fuer die Blackout-Frage ohne Belang.
        fred_key = ""

    einstellungen = CalendarSettings(
        currencies=tuple(config.event_risk.currencies),
        impacts=tuple(config.event_risk.impacts),
        blackout_minutes_before=config.event_risk.blackout_minutes_before,
        blackout_minutes_after=config.event_risk.blackout_minutes_after,
        schedule_cache_seconds=config.event_risk.schedule_cache_minutes * 60.0,
        actual_cache_seconds=config.event_risk.actual_cache_hours * 3600.0,
        upcoming_limit=config.event_risk.upcoming_limit,
    )
    dienst = CalendarService(
        ForexFactoryProvider(config.event_risk.forex_factory_url),
        FredProvider(fred_key),
        einstellungen,
    )
    return KalenderBlackout(
        dienst,
        max_alter_tage=config.ideas.filter.blackout_max_alter_tage,
        symbol=symbol,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ideas",
        description="Protokolliert regelbasierte Trade-Ideen aus den gesammelten Kerzen.",
    )
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config.yaml"))
    parser.add_argument(
        "--symbol",
        help="Nur dieses Instrument (Vorgabe: alle aus ideas.instrumente)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        help="Wie viele Kerzen geladen werden (Vorgabe: ideas.bars)",
    )
    parser.add_argument(
        "--probelauf",
        action="store_true",
        help="Rechnen und berichten, aber nichts in die Datenbank schreiben.",
    )
    parser.add_argument(
        "--kein-kalender",
        action="store_true",
        help=(
            "Ohne Blackout-Abfrage laufen. Die Ideen werden dann als "
            "'Blackout nicht pruefbar' vermerkt - nicht als 'kein Blackout'."
        ),
    )
    args = parser.parse_args(argv)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    # Eigene Logdateien, damit ein Protokollierungslauf nicht im Rauschen
    # des Empfaengers untergeht. Verzeichnis absolut, sonst landet es je
    # nach Arbeitsverzeichnis woanders - die Aufgabenplanung startet ohne
    # definiertes cwd.
    logging_cfg = replace(
        config.logging,
        directory=str(PROJECT_ROOT / config.logging.directory),
        text_file="ideas.log",
        json_file="ideas_events.jsonl",
    )
    setup_logging(logging_cfg, logger_name="ideas")

    if not config.ideas.enabled:
        print("ideas.enabled ist false - nichts zu tun.", file=sys.stderr)
        return 2

    try:
        pruefe_konfiguration(config.ideas)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    datenbank = PROJECT_ROOT / config.ntbridge.database
    if not datenbank.exists():
        print(
            f"Kerzenspeicher nicht gefunden: {datenbank}\n"
            "Laeuft der Empfaenger (python -m ntbridge)?",
            file=sys.stderr,
        )
        return 2

    symbole = [args.symbol.upper()] if args.symbol else list(config.ideas.instrumente)
    anzahl_bars = args.bars if args.bars is not None else config.ideas.bars
    timeframe = config.ideas.timeframe

    bar_store = BarStore(str(datenbank))
    ideen_store = IdeenStore(str(PROJECT_ROOT / config.ideas.datenbank))

    fehler = 0
    try:
        for symbol in symbole:
            rahmen = bar_store.load_frame(symbol, timeframe, limit=anzahl_bars)
            if rahmen.empty:
                print(
                    f"{symbol}/{timeframe}: keine Kerzen im Speicher - uebersprungen.",
                    file=sys.stderr,
                )
                fehler += 1
                continue

            pruefer = None
            if not args.kein_kalender and config.ideas.filter.blackout_aktiv:
                pruefer = _baue_blackout_pruefer(config, symbol)

            bericht = protokolliere(
                rahmen,
                symbol,
                config,
                ideen_store,
                blackout_pruefer=pruefer,
                # Beim Probelauf wird derselbe Weg gerechnet, nur nicht
                # geschrieben - sonst prueft der Probelauf etwas anderes
                # als der echte Lauf.
                nur_rechnen=args.probelauf,
            )
            _berichte(bericht, rahmen, symbol, timeframe, pruefer, args.probelauf)
    finally:
        bar_store.close()
        ideen_store.close()

    return 1 if fehler else 0


def _berichte(bericht, rahmen, symbol, timeframe, pruefer, probelauf: bool) -> None:
    """Menschenlesbare Zusammenfassung auf die Konsole."""
    print("=" * 70)
    print(f"Ideen-Protokollierung  {symbol} / {timeframe}")
    print("=" * 70)
    if probelauf:
        print("PROBELAUF - es wurde nichts geschrieben.")
    print(f"Kerzen geladen     : {len(rahmen)}")
    print(f"  von              : {rahmen.index[0]}")
    print(f"  bis              : {rahmen.index[-1]}")
    print(f"Gepruefte Kerzen   : {bericht.erkennung.gepruefte_kerzen}")
    print(f"Signale erkannt    : {bericht.erkennung.signale}")

    if bericht.erkennung.ohne_atr:
        print(
            f"  davon ohne ATR   : {bericht.erkennung.ohne_atr} "
            "(kein Stop/Ziel bildbar - zu wenig Vorlauf?)"
        )

    for schluessel, anzahl in sorted(bericht.erkennung.je_setup.items()):
        print(f"    {schluessel:<32} {anzahl}")

    print(f"Ideen gebildet     : {bericht.erzeugt}")
    print(f"  davon gefiltert  : {bericht.gefiltert}")
    print(f"Neu gespeichert    : {bericht.neu_gespeichert}")

    if pruefer is not None and pruefer.ausserhalb_der_abdeckung:
        print(
            f"Blackout ungeprueft: {pruefer.ausserhalb_der_abdeckung} "
            "(Kalender deckt den Zeitraum nicht ab)"
        )
        print("  -> Lauf haeufiger ausfuehren, dann greift die Pruefung.")

    if bericht.verworfen:
        print(f"Verworfen          : {len(bericht.verworfen)}")
        for eintrag in bericht.verworfen[:5]:
            print(f"    {eintrag}")

    print()


if __name__ == "__main__":
    sys.exit(main())
