"""Vollstaendiger Einzelfaktor-Discovery-Lauf: alle Indikatorspalten,
alle fuenf lauffaehigen Strategien.

Ergebnis dieses konkreten Laufs vom 24.08.2026 steht in
``docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`` - dieses Skript ist die
reproduzierbare Grundlage dafuer, nicht nur ein Einmal-Snippet.

News/Market Intelligence (Forex Factory, FRED, Cross-Asset) ist NICHT
enthalten - Begruendung in CODE_CHAT_KONTEXT.md Abschnitt 27 / 18.6 in
NORMALER_CHAT_KONTEXT.md.

``ib_breakout`` bleibt bewusst aussen vor: die Strategie lief zum Zeitpunkt
der Konzeption dieses Laufs noch nicht (fehlende ib_high/ib_low in
Backtester.prepare(), seit 24.08.2026 behoben). Sie absichtlich NICHT
nachtraeglich in denselben Lauf aufzunehmen, haette die Hypothesenzahl und
damit die Bonferroni-Schwelle nachtraeglich veraendert, ohne dass der Rest
des Laufs neu gerechnet wurde - ein sauberer Vergleich braucht einen eigenen
Lauf mit allen sechs Strategien von Anfang an.

NUR auf dem Trainingsteil (70 Prozent). Der Out-of-Sample-Block bleibt
unberuehrt (``pruefe_nur_training`` bricht sonst laut ab).

Aufruf (braucht PYTHONPATH, da ausserhalb der CLI):
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\discovery_indikatoren_voll.py
"""

import pandas as pd

from backtest.engine import Backtester, CostModel
from backtest.kosten import profil_aus_config
from backtest.research import (
    Discoverylauf,
    baue_faktor_bool,
    baue_faktor_kategorie,
    baue_faktor_perzentil,
    baue_faktor_relation,
    baue_faktor_vorzeichen,
    faktor_di_richtung,
    faktor_ema_stack,
    faktor_ib_lage,
    faktor_tageszeit,
    faktor_wochentag,
    perzentilgrenzen,
    pruefe_faktor,
    pruefe_nur_training,
)
from backtest.strategies.library import build_strategy
from common.config import Config
from common.instruments import get_instrument
from ideas.pipeline import vorbereiten

cfg = Config.load("config.yaml")
profil = profil_aus_config(cfg.backtest)
kosten = CostModel.aus_profil(
    profil, tick_size=cfg.market.tick_size, point_value=cfg.market.point_value
)
bt = Backtester(cfg.market, cfg.indicators, kosten)

roh = pd.read_csv("data/DUKA_5m.csv", parse_dates=["timestamp"], index_col="timestamp")
if roh.index.tz is None:
    roh.index = roh.index.tz_localize("UTC")

schnitt = int(len(roh) * 0.7)
training = roh.iloc[:schnitt]
trainingsende = training.index[-1]
print(f"Training: {len(training)} Kerzen, {training.index[0]:%Y-%m-%d} bis {trainingsende:%Y-%m-%d}")
print(f"Kostenprofil: {profil.zeile()}")
print()

# compute_indicators allein (Backtester.prepare()) liefert nur die
# Basisspalten. ADX, MACD, Stochastik, Bollinger, EMA-Stack und die
# Initial-Balance-Grenzen kommen aus ideas.pipeline.vorbereiten - derselben
# Funktion, die auch die Etappe-C-Protokollierung nutzt. Keine zweite
# Implementierung, nur hier fuer Research statt Protokollierung aufgerufen.
instrument = get_instrument(cfg.market.product)
vorbereitet = vorbereiten(training, instrument, cfg)
pruefe_nur_training(vorbereitet, trainingsende)

# Grenzen AUS DER VERTEILUNG, nicht geraten.
def terzil(spalte, namen=("1 niedrig", "2 mittel", "3 hoch")):
    grenzen = perzentilgrenzen(vorbereitet, spalte, [33.0, 67.0])
    print(f"  {spalte}: Terzilgrenzen (gemessen) {grenzen[0]:.3f} / {grenzen[1]:.3f}")
    return baue_faktor_perzentil(spalte, grenzen, list(namen))

print("Perzentilgrenzen (aus dem Trainingsteil):")
faktoren = [
    ("Tageszeit", faktor_tageszeit),
    ("Wochentag", faktor_wochentag),
    ("ATR-Terzil", terzil("atr", ("1 ruhig", "2 mittel", "3 bewegt"))),
    ("RSI-Terzil", terzil("rsi")),
    ("ADX-Terzil", terzil("adx", ("1 schwach", "2 mittel", "3 stark"))),
    ("Stochastik-Terzil", terzil("stoch_k")),
    ("Bollinger-Bandbreite-Terzil", terzil("bb_bandwidth", ("1 eng", "2 mittel", "3 weit"))),
    ("MACD-Histogramm-Vorzeichen", baue_faktor_vorzeichen("macd_hist")),
    ("DI-Richtung", faktor_di_richtung),
    ("EMA-Stack", faktor_ema_stack),
    ("Konsolidierung", baue_faktor_bool("flag_in_consolidation", ("1 ja", "2 nein"))),
    ("Range-Flag", baue_faktor_bool("flag_range", ("1 ja", "2 nein"))),
    ("Impuls-Flag", baue_faktor_bool("flag_impulse", ("1 ja", "2 nein"))),
    ("Breakout-Up-Flag", baue_faktor_bool("flag_breakout_up", ("1 ja", "2 nein"))),
    ("Breakout-Down-Flag", baue_faktor_bool("flag_breakout_down", ("1 ja", "2 nein"))),
    ("Bollinger-Squeeze", baue_faktor_bool("bb_squeeze", ("1 ja", "2 nein"))),
    ("Flag-Richtung", baue_faktor_kategorie("flag_direction", {1: "1 bullisch", -1: "2 baerisch", 0: "3 neutral"})),
    ("IB-Lage", faktor_ib_lage),
    ("VWAP-Lage", baue_faktor_relation("vwap", "VWAP")),
    ("Vortagesschluss-Lage", baue_faktor_relation("prev_session_close", "Vortagesschluss")),
]
print()

lauf = Discoverylauf()
strategien = ("prev_day_breakout", "vwap_reversion", "flag_breakout", "vwap_trend", "rsi_mean_reversion")
for name in strategien:
    ergebnis = bt.run(vorbereitet, build_strategy(name), already_prepared=True)
    print(f"{name}: {len(ergebnis.trades)} Trades im Training")
    for faktor_name, faktor in faktoren:
        lauf.ergebnisse.append(
            pruefe_faktor(ergebnis, vorbereitet, faktor_name, faktor,
                          punktwert=cfg.market.point_value)
        )

print()
print("=" * 78)
print(lauf.bericht())
print()
print("=" * 78)
print(lauf.statistikbericht())
