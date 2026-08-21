"""MCP-Server fuer Claude Desktop (stdio-Transport).

Zum stdout-Kanal
----------------
Der stdio-Transport des ``mcp``-Pakets sichert den JSON-RPC-Kanal bereits
selbst auf Dateideskriptor-Ebene: er dupliziert fd 1 auf einen privaten
Deskriptor fuer das Protokoll und biegt fd 1 selbst auf stderr um
(``_open_stdout_diversion`` -> ``os.dup(2)``). Ein verirrtes ``print()`` in
irgendeiner Abhaengigkeit landet damit automatisch auf stderr.

**Deshalb wird hier NICHT ``sys.stdout = sys.stderr`` gesetzt.** Das waere
sogar schaedlich: der Transport prueft ``stream.buffer.fileno() == 1``, um zu
entscheiden, ob er den Deskriptor beanspruchen darf. Zeigte ``sys.stdout``
auf stderr, schluege diese Pruefung fehl und das Protokoll wuerde auf
stderr geschrieben - der Kanal waere kaputt statt geschuetzt.

Was hier stattdessen gilt: Logging ausschliesslich in Dateien und auf
stderr, und aus diesem Modul heraus wird nichts importiert, was auf stdout
schreibt (``Notifier._emit_fallback``, ``backtest.cli``).

Kein Anthropic-Aufruf
---------------------
Der Server liefert ausschliesslich strukturiertes JSON. Es gibt hier keinen
``ClaudeCommentator`` und keinen ``_create()``-Aufruf - interpretiert wird
in der Claude-Desktop-Unterhaltung, nicht auf Kosten der API.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server import MCPServer

from common.instruments import UnknownInstrument, get_instrument, known_roots
from common.logging_setup import log_event
from mcp_server.bars import ALL_TIMEFRAMES, DAILY
from mcp_server.context import ServerContext
from mcp_server.snapshot import DEFAULT_BARS_IN_OUTPUT, build_snapshot_payload

log = logging.getLogger(__name__)

DEFAULT_TIMEFRAMES = ["1m", "5m", "15m"]
# 1h und Daily kommen als Kontext immer dazu.
CONTEXT_TIMEFRAMES = ["1h", DAILY]

server = MCPServer(
    name="claude-chart-bot",
    instructions=(
        "Liefert Marktdaten-Snapshots fuer CME-Futures aus NinjaTrader 8. "
        "Die Kerzen kommen ueber den lokalen ntbridge-Empfaenger in eine "
        "SQLite-Datei; der Server liest nur daraus. Laeuft der Empfaenger "
        "nicht oder ist in NinjaTrader kein Chart offen, sind die Daten "
        "veraltet - das steht dann im Block 'datenherkunft'. "
        "Alle Werte sind berechnete Kennzahlen mit Einheiten - der Server "
        "interpretiert nicht. Abstaende zu Preisniveaus stehen immer in "
        "Punkten UND in ATR-Vielfachen; nur letztere sind zwischen "
        "Instrumenten vergleichbar."
    ),
)

_context = ServerContext()


def _normalise_timeframes(requested: list[str] | None) -> list[str]:
    """Ergaenzt die Kontext-Timeframes und entfernt Unbekanntes."""
    chosen = list(requested) if requested else list(DEFAULT_TIMEFRAMES)
    for timeframe in CONTEXT_TIMEFRAMES:
        if timeframe not in chosen:
            chosen.append(timeframe)

    valid = [timeframe for timeframe in chosen if timeframe in ALL_TIMEFRAMES]
    if not valid:
        raise ValueError(
            f"Keine gueltigen Timeframes. Moeglich: {', '.join(ALL_TIMEFRAMES)}"
        )
    return valid


@server.tool(
    name="get_market_snapshot",
    title="Marktdaten-Snapshot",
    description=(
        "Vollstaendiger Datenstand zu einem Futures-Kontrakt: Kontraktdaten, "
        "Session-Lage, Preisniveaus (PDH/PDL, Overnight, Initial Balance, "
        "Opening Range, Gap), Marktstruktur mit BOS/CHoCH, Momentum "
        "(RSI mit Divergenz, MACD, Stochastik, EMA-Stack, ADX), Volatilitaet "
        "(ATR, Bollinger mit Squeeze), Volumen (VWAP mit Sigma-Baendern, "
        "kumulatives Delta) und erkannte Muster mit Konfidenz. "
        "Standardmaessig MNQ. Ein anderes Symbol ist nur abrufbar, wenn in "
        "NinjaTrader ein Chart mit der ClaudeBridge dafuer laeuft - es wird "
        "NICHT on-demand nachgeladen. Kumulatives Delta bleibt null: dafuer "
        "braeuchte es das kostenpflichtige NT8-Add-on 'Order Flow +'."
    ),
)
async def get_market_snapshot(
    symbol: str = "MNQ",
    timeframes: list[str] | None = None,
    include_bars: bool = True,
    bars_in_output: int = DEFAULT_BARS_IN_OUTPUT,
) -> dict[str, Any]:
    """Liefert den aktuellen Datenstand als strukturiertes JSON.

    Args:
        symbol: Produkt-Root (``MNQ``, ``MGC``) oder konkreter Kontrakt
            (``MNQZ5``). Der Frontmonat wird automatisch aufgeloest.
        timeframes: Gewuenschte Timeframes, Standard ``["1m","5m","15m"]``.
            ``1h`` und ``1d`` werden als Kontext immer ergaenzt.
        include_bars: Rohkerzen mitliefern. Abschalten spart Kontext.
        bars_in_output: Anzahl Rohkerzen je Timeframe.
    """
    try:
        instrument = get_instrument(symbol)
    except UnknownInstrument as exc:
        return {
            "fehler": str(exc),
            "bekannte_symbole": known_roots(),
        }

    selected = _normalise_timeframes(timeframes)
    source = await _context.bar_source()

    log_event(
        log,
        "mcp.snapshot.requested",
        f"Snapshot fuer {instrument.root} angefordert",
        symbol=instrument.root,
        timeframes=selected,
    )

    loaded = await source.load(symbol, selected)
    payload = build_snapshot_payload(
        loaded,
        _context.config,
        timeframes=selected,
        include_bars=include_bars,
        bars_in_output=bars_in_output,
    )

    log_event(
        log,
        "mcp.snapshot.delivered",
        f"Snapshot fuer {loaded.contract.name} geliefert",
        contract=loaded.contract.name,
        timeframes=list(payload["timeframes"]),
    )
    return payload


@server.tool(
    name="get_event_risk",
    title="Terminrisiko",
    description=(
        "Wirtschaftskalender fuer USD-Termine mit hoher Wirkung (FOMC, CPI, "
        "PPI, PCE, NFP, Jobless Claims, Retail Sales, ISM/PMI, Fed-Reden): "
        "Minuten bis zum naechsten Termin, Blackout-Flag um den Termin herum, "
        "Forecast und Previous, sowie - soweit verfuegbar - die bereits "
        "veroeffentlichten Werte des Tages. Ist der Kalender nicht erreichbar, "
        "wird calendar_available=false gemeldet und NICHT 'keine Termine'."
    ),
)
async def get_event_risk(symbol: str = "MNQ") -> dict[str, Any]:
    """Terminrisiko rund um den aktuellen Zeitpunkt.

    Args:
        symbol: Nur zur Kennzeichnung im Ergebnis - der Kalender ist
            makrooekonomisch und damit fuer MNQ und MGC derselbe.
    """
    config = _context.config
    if not config.event_risk.enabled:
        return {
            "calendar_available": False,
            "reason": "event_risk.enabled ist in der config.yaml auf false gesetzt.",
            "symbol": symbol,
        }

    result = await _context.calendar().event_risk(symbol=symbol)
    log_event(
        log,
        "mcp.event_risk.delivered",
        "Terminrisiko geliefert",
        symbol=symbol,
        available=result.get("calendar_available"),
        blackout=(result.get("blackout") or {}).get("aktiv"),
    )
    return result


@server.tool(
    name="list_instruments",
    title="Verfuegbare Instrumente",
    description="Registrierte Instrumente mit Ticksize, Punktwert und Handelszeiten.",
)
async def list_instruments() -> dict[str, Any]:
    """Kontraktspezifikationen aus dem Instrument-Register."""
    from common.instruments import all_instruments

    return {
        "instrumente": [
            instrument.describe_contract() for instrument in all_instruments()
        ],
        "hinweis": "Registrierte Kontraktspezifikationen - NICHT gleichbedeutend "
                   "mit verfuegbaren Daten. Abrufbar ist ein Instrument nur, "
                   "wenn in NinjaTrader ein Chart mit der ClaudeBridge dafuer "
                   "laeuft. Derzeit ist das MNQ. Welche Daten tatsaechlich "
                   "vorliegen, zeigt get_market_snapshot im Block "
                   "'datenherkunft'.",
    }


def main() -> None:
    """Startet den Server auf dem stdio-Transport."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
