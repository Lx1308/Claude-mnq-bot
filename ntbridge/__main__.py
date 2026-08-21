"""Startet den Empfaenger fuer NinjaTrader-Kerzen.

    python -m ntbridge

Laeuft dauerhaft. Beenden mit Strg+C.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from common.config import Config, ConfigError
from common.logging_setup import log_event, setup_logging
from ntbridge.receiver import make_server
from ntbridge.store import BarStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

log = logging.getLogger("ntbridge")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ntbridge",
        description="Empfaengt Kerzen aus NinjaTrader 8 und legt sie in SQLite ab.",
    )
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config.yaml"))
    parser.add_argument("--port", type=int, help="Ueberschreibt ntbridge.port")
    parser.add_argument("--database", help="Ueberschreibt ntbridge.database")
    args = parser.parse_args(argv)

    try:
        config = Config.load(args.config)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    # Logverzeichnis absolut, damit es unabhaengig vom Arbeitsverzeichnis
    # immer im Projekt landet.
    logging_cfg = replace(
        config.logging,
        directory=str(PROJECT_ROOT / config.logging.directory),
        text_file="ntbridge.log",
        json_file="ntbridge_events.jsonl",
    )
    setup_logging(logging_cfg, logger_name="ntbridge")

    if not config.ntbridge.enabled:
        print("ntbridge.enabled ist false - nichts zu tun.", file=sys.stderr)
        return 2

    database = Path(args.database or config.ntbridge.database)
    if not database.is_absolute():
        database = PROJECT_ROOT / database

    port = args.port or config.ntbridge.port
    host = config.ntbridge.host

    # Startpruefung: nur lokal binden. Eine versehentliche 0.0.0.0-Bindung
    # wuerde den Endpunkt im ganzen Netz oeffnen.
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"ntbridge.host ist '{host}'. Der Empfaenger darf ausschliesslich "
            "lokal gebunden werden - bitte auf 127.0.0.1 setzen.",
            file=sys.stderr,
        )
        return 2

    store = BarStore(database)

    try:
        server, state = make_server(
            store,
            host=host,
            port=port,
            symbol_map=config.ntbridge.symbol_map,
        )
    except OSError as exc:
        print(
            f"Port {port} konnte nicht belegt werden: {exc}\n"
            "Laeuft bereits ein zweiter Empfaenger?",
            file=sys.stderr,
        )
        store.close()
        return 3

    coverage = store.coverage()
    log_event(
        log,
        "ntbridge.started",
        f"Empfaenger laeuft auf http://{host}:{port}",
        host=host,
        port=port,
        database=str(database),
        bars_in_db=store.total_bars(),
        series=len(coverage),
    )

    # Diese Zeilen gehen bewusst auf stdout: das hier ist ein eigener Prozess
    # und nicht der JSON-RPC-Kanal des MCP-Servers.
    print(f"Empfaenger laeuft auf http://{host}:{port}")
    print(f"  Datenbank : {database}")
    print(f"  Kerzen    : {store.total_bars()}")
    if coverage:
        for entry in coverage:
            print(
                f"    {entry['instrument']:<6} {entry['timeframe']:<4} "
                f"{entry['bars']:>7} Bars, juengster {entry['juengster_bar_utc']}"
            )
    else:
        print("    (noch keine Daten - NinjaTrader mit ClaudeBridge starten)")
    print(f"\n  Status pruefen: http://{host}:{port}/status")
    print("  Beenden mit Strg+C\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeende...")
    finally:
        server.shutdown()
        server.server_close()
        log_event(
            log,
            "ntbridge.stopped",
            "Empfaenger beendet",
            kerzen_angenommen=state.accepted,
            kerzen_abgelehnt=state.rejected,
        )
        store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
