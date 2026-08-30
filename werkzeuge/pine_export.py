"""Eine lokale Strategie als Pine-Skript fuer TradingView-Deep-Backtesting.

Wozu
----
Laurin holt sich ein TradingView-Premium-Abo, um die lokal gefundenen
Hypothesen ueber rund 2 Mio. Kerzen nachrechnen zu lassen - deutlich mehr
Historie, als hier vorliegt. Damit dieser Vergleich etwas bedeutet, muss das
Pine-Skript **dieselbe Strategie** sein und nicht eine aehnliche.

Was die Uebereinstimmung sichert
--------------------------------
1. Die Bedingungen kommen aus ``Rule.nach_pine`` und stehen damit direkt neben
   ``Rule.evaluate``. Wer die eine aendert, sieht die andere.
2. Das **Ausfuehrungsmodell** wird nachgebaut: ausgewertet wird auf dem
   Schlusskurs, ausgefuehrt zur Eroeffnung der Folgekerze
   (``process_orders_on_close = false`` ist Pines Vorgabe und entspricht genau
   dem). Stop und Ziel liegen in ATR-Vielfachen des EINSTIEGSBALKENS, wie in
   ``backtest/engine.py``.
3. Bei gleichzeitigem Treffer von Stop und Ziel in derselben Kerze gilt der
   **Stop** - Pine macht das ueber ``strategy.exit`` genauso, weil aus OHLC
   nicht rekonstruierbar ist, was zuerst kam.
4. Kosten werden aus dem benannten Kostenprofil uebernommen, nicht geraten.

Was NICHT uebersetzt wird
-------------------------
Regeln, die an selbst gerechneten Spalten haengen (Flaggen-Ausbruch, Initial
Balance), werden **abgelehnt** statt genaehert. Eine genaeherte Pine-Fassung
saehe aus wie dieselbe Strategie und waere keine - und der Vergleich mit dem
lokalen Lauf haette dann keine Aussage mehr.

Aufruf
------
    .venv\\Scripts\\python.exe werkzeuge\\pine_export.py --liste
    .venv\\Scripts\\python.exe werkzeuge\\pine_export.py vwap_reversion
    .venv\\Scripts\\python.exe werkzeuge\\pine_export.py vwap_reversion -o mein.pine
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.strategies.base import NichtUebersetzbar, RuleStrategy  # noqa: E402
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy  # noqa: E402
from common.config import Config  # noqa: E402
from common.instruments import get_instrument  # noqa: E402

#: Unsere Spaltennamen -> Pine-Bezeichner. Die zugehoerigen Definitionen
#: stehen in KOPF_INDIKATOREN; beides muss zusammenpassen.
#:
#: Was hier NICHT steht, ist nicht uebersetzbar - und dann bricht der Export
#: ab. Das ist Absicht: eine fehlende Zeile hier waere sonst eine stille
#: Naeherung.
SPALTEN_NACH_PINE: dict[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "atr": "atrWert",
    "rsi": "rsiWert",
    "sma_fast": "smaFast",
    "sma_slow": "smaSlow",
    "vwap": "vwapWert",
    "prev_session_high": "pdh",
    "prev_session_low": "pdl",
    "prev_session_close": "pdc",
}

KOPF_INDIKATOREN = """// --- Indikatoren, identisch zu common/indicators.py -----------------------
atrWert  = ta.atr(atrPeriode)
rsiWert  = ta.rsi(close, rsiPeriode)
smaFast  = ta.sma(close, smaFastPeriode)
smaSlow  = ta.sma(close, smaSlowPeriode)

// Session-VWAP. Setzt mit dem CME-Handelstag zurueck (18:00 ET), NICHT um
// Mitternacht - sonst waere es ein anderer VWAP als der lokale.
istNeuerHandelstag = ta.change(time("D", "1800-1700", "America/New_York")) != 0
vwapWert = ta.vwap(hlc3, istNeuerHandelstag)

// Vortageswerte. request.security mit lookahead_off: ohne das liefe der
// Vortageswert dem Kurs voraus und das Ergebnis waere wertlos.
pdh = request.security(syminfo.tickerid, "D", high[1], lookahead=barmerge.lookahead_off)
pdl = request.security(syminfo.tickerid, "D", low[1],  lookahead=barmerge.lookahead_off)
pdc = request.security(syminfo.tickerid, "D", close[1], lookahead=barmerge.lookahead_off)
"""


def _pine_zahl(wert) -> str:
    return "na" if wert is None else repr(float(wert))


def baue_pine(
    strategie: RuleStrategy,
    *,
    config: Config,
    kommission_je_seite: float,
    slippage_ticks: float,
) -> str:
    """Ein vollstaendiges Pine-v6-Skript - oder ``NichtUebersetzbar``."""
    instrument = get_instrument(config.market.product)

    bedingungen: dict[str, str] = {}
    for feld in ("long_entry", "long_exit", "short_entry", "short_exit"):
        regel = getattr(strategie, feld)
        bedingungen[feld] = (
            regel.nach_pine(SPALTEN_NACH_PINE) if regel is not None else "false"
        )

    erzeugt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parameter = "\n".join(
        f"//   {name} = {wert}" for name, wert in sorted(strategie.params.items())
    )

    return f'''// @version=6
// ===========================================================================
//  {strategie.name} - erzeugt aus dem lokalen Projekt am {erzeugt}
// ===========================================================================
//
//  NICHT VON HAND AENDERN. Erzeugt von werkzeuge/pine_export.py aus
//  backtest/strategies/library.py::{strategie.name}. Wer hier etwas aendert,
//  vergleicht anschliessend zwei verschiedene Strategien.
//
//  Parameter des lokalen Laufs:
{parameter or "//   (keine)"}
//
//  AUSFUEHRUNGSMODELL - muss zu backtest/engine.py passen:
//    * Regeln werden auf dem SCHLUSS einer Kerze ausgewertet.
//    * Ausgefuehrt wird zur EROEFFNUNG der Folgekerze
//      (process_orders_on_close = false, Pines Vorgabe).
//    * Stop und Ziel in ATR-Vielfachen des EINSTIEGSBALKENS.
//    * Treffen Stop und Ziel in derselben Kerze, gilt der STOP - aus OHLC
//      ist nicht rekonstruierbar, was zuerst kam.
//    * Hoechstens eine Position gleichzeitig.
//
//  KOSTEN: {kommission_je_seite:.2f} USD je Seite, {slippage_ticks} Tick(s)
//  Slippage je Seite. Aus dem benannten Kostenprofil des Projekts, nicht
//  geraten.
//
//  VERGLEICH: Ergebnis in TradingView ueber "List of Trades" als CSV
//  exportieren und mit werkzeuge/tv_import.py gegen den lokalen Lauf halten.
// ===========================================================================

strategy("{strategie.name}",
     overlay              = true,
     initial_capital      = 10000,
     default_qty_type     = strategy.fixed,
     default_qty_value    = 1,
     pyramiding           = 0,
     calc_on_every_tick   = false,
     process_orders_on_close = false,
     commission_type      = strategy.commission.cash_per_contract,
     commission_value     = {kommission_je_seite:.4f},
     slippage             = {int(slippage_ticks)})

// --- Parameter (Werte des lokalen Laufs) ----------------------------------
atrPeriode      = input.int({config.indicators.atr_period}, "ATR-Periode")
rsiPeriode      = input.int({config.indicators.rsi_period}, "RSI-Periode")
smaFastPeriode  = input.int({config.indicators.sma_fast}, "SMA schnell")
smaSlowPeriode  = input.int({config.indicators.sma_slow}, "SMA langsam")
stopAtr         = input.float({_pine_zahl(strategie.stop_loss_atr)}, "Stop in ATR")
zielAtr         = input.float({_pine_zahl(strategie.take_profit_atr)}, "Ziel in ATR")
maxKerzen       = input.int({strategie.max_bars_in_trade or 0}, "Zwangsausstieg nach N Kerzen (0 = aus)")

{KOPF_INDIKATOREN}
// --- Bedingungen, uebersetzt aus den Regel-Objekten ------------------------
longEinstieg  = {bedingungen["long_entry"]}
longAusstieg  = {bedingungen["long_exit"]}
shortEinstieg = {bedingungen["short_entry"]}
shortAusstieg = {bedingungen["short_exit"]}

// --- Ausfuehrung -----------------------------------------------------------
// Der ATR des EINSTIEGSBALKENS wird festgehalten. Wuerde der Stop bei jeder
// Kerze mit dem aktuellen ATR neu gerechnet, waende er sich mit der
// Volatilitaet - das waere ein nachziehender Stop und eine andere Strategie.
var float einstiegsAtr = na

if strategy.position_size == 0
    einstiegsAtr := atrWert

if longEinstieg and strategy.position_size == 0
    strategy.entry("Long", strategy.long)

if shortEinstieg and strategy.position_size == 0
    strategy.entry("Short", strategy.short)

if strategy.position_size > 0
    stopPreis = na(stopAtr) ? na : strategy.position_avg_price - stopAtr * einstiegsAtr
    zielPreis = na(zielAtr) ? na : strategy.position_avg_price + zielAtr * einstiegsAtr
    strategy.exit("Long-Aus", from_entry = "Long", stop = stopPreis, limit = zielPreis)
    if longAusstieg
        strategy.close("Long", comment = "Regelausstieg")

if strategy.position_size < 0
    stopPreis = na(stopAtr) ? na : strategy.position_avg_price + stopAtr * einstiegsAtr
    zielPreis = na(zielAtr) ? na : strategy.position_avg_price - zielAtr * einstiegsAtr
    strategy.exit("Short-Aus", from_entry = "Short", stop = stopPreis, limit = zielPreis)
    if shortAusstieg
        strategy.close("Short", comment = "Regelausstieg")

// Zeitstop
if maxKerzen > 0 and strategy.position_size != 0
    if bar_index - strategy.opentrades.entry_bar_index(0) >= maxKerzen
        strategy.close_all(comment = "Zeitstop")

// Sessionende: alle Positionen schliessen. Entspricht
// close_at_session_end = {strategie.close_at_session_end} im lokalen Lauf.
istSessionEnde = ta.change(time("D", "1800-1700", "America/New_York")) != 0
if istSessionEnde and strategy.position_size != 0
    strategy.close_all(comment = "Sessionende")

// --- Anzeige ---------------------------------------------------------------
plot(vwapWert, "VWAP", color.new(color.orange, 0))
plot(smaSlow, "SMA langsam", color.new(color.blue, 0))
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pine_export",
        description="Erzeugt ein Pine-Skript aus einer Strategie der Bibliothek.",
    )
    parser.add_argument("strategie", nargs="?")
    parser.add_argument("--liste", action="store_true",
                        help="Zeigt, welche Strategien uebersetzbar sind.")
    parser.add_argument("-o", "--ausgabe", type=Path)
    parser.add_argument("--kostenprofil", default=None)
    args = parser.parse_args(argv)

    config = Config.load(PROJECT_ROOT / "config.yaml")

    if args.liste or not args.strategie:
        from backtest.kosten import profil_aus_config

        profil = profil_aus_config(config.backtest, args.kostenprofil)
        print("Strategie                 Pine-Export")
        print("-" * 60)
        for name in sorted(STRATEGY_LIBRARY):
            try:
                baue_pine(
                    build_strategy(name), config=config,
                    kommission_je_seite=profil.summe_je_seite,
                    slippage_ticks=profil.slippage_ticks_je_seite,
                )
                print(f"{name:<25} moeglich")
            except NichtUebersetzbar as grund:
                print(f"{name:<25} NEIN - {grund}")
        return 0

    if args.strategie not in STRATEGY_LIBRARY:
        print(
            f"Unbekannte Strategie {args.strategie!r}. Bekannt: "
            + ", ".join(sorted(STRATEGY_LIBRARY)),
            file=sys.stderr,
        )
        return 2

    from backtest.kosten import profil_aus_config

    profil = profil_aus_config(config.backtest, args.kostenprofil)
    try:
        skript = baue_pine(
            build_strategy(args.strategie), config=config,
            kommission_je_seite=profil.summe_je_seite,
            slippage_ticks=profil.slippage_ticks_je_seite,
        )
    except NichtUebersetzbar as grund:
        print(f"Nicht uebersetzbar: {grund}", file=sys.stderr)
        print(
            "\nEine genaeherte Pine-Fassung waere schlimmer als keine - der "
            "Vergleich mit dem lokalen Lauf haette dann keine Aussage.",
            file=sys.stderr,
        )
        return 3

    ziel = args.ausgabe or (
        PROJECT_ROOT / "backtest_results" / f"{args.strategie}.pine"
    )
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(skript, encoding="utf-8")
    print(f"Geschrieben: {ziel}")
    print(f"  Kostenprofil: {profil.name} ({profil.summe_je_seite:.2f} USD je Seite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
