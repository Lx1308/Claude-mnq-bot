"""Terminal-Zugang zu denselben Daten, die der MCP-Server liefert.

Zweck: den Snapshot einmal ohne Claude Desktop ausgeben und mit dem
TradingView-Chart abgleichen.

    python -m mcp_server.cli snapshot --symbol MNQ
    python -m mcp_server.cli snapshot --symbol MGC --timeframes 5m,15m --compact
    python -m mcp_server.cli levels --symbol MNQ

Hier ist ``print`` auf stdout unbedenklich - das ist ein eigener Prozess und
nicht der JSON-RPC-Kanal des MCP-Servers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from common.instruments import UnknownInstrument, get_instrument, known_roots
from mcp_server.bars import ALL_TIMEFRAMES, DAILY
from mcp_server.context import DEFAULT_CONFIG_PATH, DEFAULT_ENV_PATH, ServerContext
from mcp_server.snapshot import DEFAULT_BARS_IN_OUTPUT, build_snapshot_payload


async def _build(args: argparse.Namespace) -> dict[str, Any]:
    context = ServerContext(args.config, args.env_file)
    timeframes = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]
    for extra in ("1h", DAILY):
        if extra not in timeframes:
            timeframes.append(extra)

    unknown = [tf for tf in timeframes if tf not in ALL_TIMEFRAMES]
    if unknown:
        raise SystemExit(
            f"Unbekannte Timeframes: {', '.join(unknown)}. "
            f"Moeglich: {', '.join(ALL_TIMEFRAMES)}"
        )

    try:
        source = await context.bar_source()
        loaded = await source.load(args.symbol, timeframes)
        return build_snapshot_payload(
            loaded,
            context.config,
            timeframes=timeframes,
            include_bars=not args.no_bars,
            bars_in_output=args.bars,
        )
    finally:
        await context.aclose()


def _print_summary(payload: dict[str, Any]) -> None:
    """Kompakte Textausgabe zum Abgleich mit dem Chart."""
    instrument = payload["instrument"]
    session = payload["session"]
    levels = payload["levels"]

    print("=" * 78)
    print(f"{instrument['name']}  ({instrument['aktiver_kontrakt']})")
    print(
        f"Tick {instrument['tick_size_points']} = {instrument['tick_value_usd']} USD   |   "
        f"Punktwert {instrument['point_value_usd']} USD"
    )
    print("=" * 78)

    stamps = session["timestamp"]
    print(f"Zeit UTC : {stamps['utc']}")
    print(f"     ET  : {stamps['et']}")
    print(f"     CT  : {stamps['ct']}")
    print(
        f"Session  : {session['primary_session']}  (Globex {session['globex_state']})"
        f"   RTH: {'ja' if session['is_rth'] else 'nein'}"
    )
    if session["minutes_to_rth_close"] is not None:
        print(f"           noch {session['minutes_to_rth_close']:.0f} Min bis RTH-Schluss")
    elif session["minutes_to_rth_open"]:
        print(f"           noch {session['minutes_to_rth_open']:.0f} Min bis RTH-Eroeffnung")

    flags = [
        name for name, active in (
            ("Liquiditaetsfenster", session["is_liquid_window"]),
            ("duenne Mittagszone", session["is_thin_midday_window"]),
            ("erste Stunde nach Wartung", session["is_first_hour_after_maintenance"]),
        ) if active
    ]
    if flags:
        print(f"Flags    : {', '.join(flags)}")

    print(f"\nKurs     : {levels['current_price']}")
    print(f"Levels aus Timeframe {levels['berechnet_aus_timeframe']}:")
    for level in sorted(levels["levels"], key=lambda item: abs(item["distance_points"])):
        atr = f"{level['distance_atr']:+.2f} ATR" if level["distance_atr"] is not None else "   n/a"
        print(
            f"  {level['name']:<28} {level['price']:>12.2f}   "
            f"{level['distance_points']:>+9.2f} Pt  {atr:>10}"
        )

    if levels["gap"].get("available"):
        gap = levels["gap"]
        print(
            f"\nGap      : {gap['gap_points']:+.2f} Pt ({gap['direction']}), "
            f"{'geschlossen' if gap['filled'] else 'offen'}"
        )

    for timeframe, block in payload["timeframes"].items():
        momentum = block["momentum"]
        volatility = block["volatilitaet"]
        print(f"\n--- {timeframe} ({block['bars_verfuegbar']} Bars) ---")
        print(
            f"  RSI {momentum['rsi_14']['value']}   "
            f"ADX {momentum['adx_14']['adx']} ({momentum['adx_14']['regime']})   "
            f"MACD-Hist {momentum['macd_12_26_9']['histogramm']}   "
            f"Stoch {momentum['stochastik_14_3_3']['k']}"
        )
        print(
            f"  ATR {volatility['atr_14']['punkte']} Pt = "
            f"{volatility['atr_14']['ticks']} Ticks = "
            f"{volatility['atr_14']['usd_je_kontrakt']} USD   "
            f"Squeeze: {'ja' if volatility['bollinger_20_2']['squeeze'] else 'nein'}"
        )
        structure = block["struktur"]["marktstruktur"]
        print(f"  Struktur: {structure['trend']}", end="")
        if structure["break_of_structure"]["erkannt"]:
            print(f"   BOS {structure['break_of_structure']['richtung']}", end="")
        if structure["change_of_character"]["erkannt"]:
            print(f"   CHoCH {structure['change_of_character']['richtung']}", end="")
        print()

        divergence = momentum["rsi_14"]["divergenz"]
        if divergence["erkannt"]:
            print(f"  RSI-Divergenz: {divergence['art']}")

        for pattern in block["muster"][:3]:
            marker = " (schwach)" if pattern["schwaches_einzelsignal"] else ""
            print(f"  Muster: {pattern['name']} [{pattern['konfidenz']:.2f}]{marker}")

    print("\nHistorienabhaengige Kennzahlen:")
    for name, entry in payload["historienabhaengig"].items():
        if entry.get("available"):
            if name == "volume_profile":
                heute = entry.get("heute") or {}
                print(
                    f"  {name:<20} POC {heute.get('poc')}  "
                    f"VAH {heute.get('vah')}  VAL {heute.get('val')}  (Naeherung)"
                )
            else:
                print(f"  {name:<20} {entry.get('value')} {entry.get('unit', '')}")
        else:
            print(
                f"  {name:<20} noch nicht belastbar - "
                f"{entry.get('sessions_available')}/{entry.get('sessions_required')} Sessions"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp_server.cli",
        description="Snapshot im Terminal ausgeben - zum Abgleich mit dem Chart.",
    )
    parser.add_argument("command", choices=("snapshot", "levels"))
    parser.add_argument("--symbol", default="MNQ", help=f"z.B. {', '.join(known_roots())}")
    parser.add_argument("--timeframes", default="1m,5m,15m")
    parser.add_argument("--bars", type=int, default=DEFAULT_BARS_IN_OUTPUT)
    parser.add_argument("--no-bars", action="store_true", help="Rohkerzen weglassen")
    parser.add_argument("--json", action="store_true", help="Rohes JSON statt Textfassung")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    args = parser.parse_args(argv)

    try:
        get_instrument(args.symbol)
    except UnknownInstrument as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2

    try:
        payload = asyncio.run(_build(args))
    except Exception as exc:  # noqa: BLE001 - CLI soll nicht mit Traceback enden
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    if args.command == "levels":
        payload = {"instrument": payload["instrument"], "levels": payload["levels"]}

    if args.json or args.command == "levels":
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
