"""Validation der ``vwap_trend``/RSI-Terzil-Hypothese aus dem Discovery-Lauf.

WOZU
----
``docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`` nannte ``vwap_trend`` nach
RSI-Terzil als den "belastbarsten Einzelfund": 1435 Trades, beide Randgruppen
positiv (niedrig +1,217 / hoch +2,671 Punkte je Trade), die Mitte tief negativ
(-3,199), t=-4,74. Ausdruecklich als HYPOTHESE fuer die Validierung markiert,
kein Befund (Masterplan G: Discovery -> Validation -> Confirmation).

WARUM DIESER BLOCK UND KEIN ANDERER
------------------------------------
Der einzige bisher unberuehrte Datenblock ist der Out-of-Sample-Teil (letzte
30 % von ``data/DUKA_5m.csv``) - und der ist einmalig, siehe
``backtest/research.py::pruefe_nur_training``. Ihn fuer eine erste Validierung
zu verbrauchen waere Verschwendung, wenn die Hypothese schon vorher scheitert.

Deshalb wird der bestehende Trainingsteil (die ersten 70 % - unveraendert
gegenueber dem Discovery-Lauf, damit die Out-of-Sample-Grenze exakt gleich
bleibt) intern noch einmal geschnitten:

    0 % ----------- 50 % ----------- 70 % ------------------- 100 %
    "Sub-Training"   |  VALIDATION   |         OUT-OF-SAMPLE
    (im Discovery-    |  (dieser      |         (weiterhin unberuehrt,
     Lauf mitgepoolt) |   Lauf)       |          einmalig fuer Confirmation)

**Einschraenkung, offen ausgewiesen statt verschwiegen:** Die
Validierungsspanne (50-70 %) war Teil des 70-%-Blocks, den der Discovery-Lauf
gepoolt ausgewertet hat - sie ist also nicht im strengen Sinn nie gesehen
worden. Sie ist aber ein chronologisch abgegrenztes Fenster, auf dem noch nie
eine EIGENE Gruppenkennzahl berechnet wurde, und die Hypothese wird
eingefroren aus dem Discovery-Lauf uebernommen (dieselben RSI-Terzilgrenzen,
45,902 / 56,596 - NICHT auf dem Validierungsblock neu bestimmt). Eine neu
bestimmte Grenze wuerde die Hypothese neu anpassen statt sie zu pruefen.
Diese Teilueberlappung ist eine Naeherung an eine echte Validierung, keine
vollstaendig blinde - siehe CODE_CHAT_KONTEXT.md fuer die Einordnung.

Indikatoren werden ueber die vollen 70 % gerechnet (wie im Discovery-Lauf,
Invariante 5 - ein isoliert vorbereiteter Block haette am Anfang keinen
gueltigen SMA(50)) und danach erst auf den Validierungsblock geschnitten.

Aufruf (braucht PYTHONPATH, da ausserhalb der CLI):
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\validation_vwap_trend_rsi.py
"""

import pandas as pd

from backtest.engine import Backtester, CostModel
from backtest.kosten import profil_aus_config
from backtest.research import (
    Discoverylauf,
    baue_faktor_perzentil,
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

schnitt_oos = int(len(roh) * 0.7)   # identisch zum Discovery-Lauf, OOS unveraendert
schnitt_validation = int(len(roh) * 0.5)

training = roh.iloc[:schnitt_oos]
trainingsende = training.index[-1]
print(f"Trainingsteil (wie im Discovery-Lauf): {len(training)} Kerzen, "
      f"{training.index[0]:%Y-%m-%d} bis {trainingsende:%Y-%m-%d}")
print(f"Kostenprofil: {profil.zeile()}")

instrument = get_instrument(cfg.market.product)
vorbereitet = vorbereiten(training, instrument, cfg)
pruefe_nur_training(vorbereitet, trainingsende)  # OOS-Grenze weiterhin respektiert

validation = vorbereitet.iloc[schnitt_validation:]
print(f"Validierungsblock (50-70 % der Gesamthistorie): {len(validation)} Kerzen, "
      f"{validation.index[0]:%Y-%m-%d} bis {validation.index[-1]:%Y-%m-%d}")
print()

# Eingefrorene Terzilgrenzen aus dem Discovery-Lauf vom 24.08.2026 -
# ABSICHTLICH NICHT auf dem Validierungsblock neu bestimmt.
GRENZEN_DISCOVERY = [45.902, 56.596]
NAMEN = ["1 niedrig", "2 mittel", "3 hoch"]
faktor_rsi_terzil = baue_faktor_perzentil("rsi", GRENZEN_DISCOVERY, NAMEN)

ergebnis = bt.run(validation, build_strategy("vwap_trend"), already_prepared=True)
print(f"vwap_trend im Validierungsblock: {len(ergebnis.trades)} Trades "
      f"(Discovery-Lauf zum Vergleich: 3248 Trades im gesamten 70-%-Trainingsteil, "
      f"davon 1435 in der RSI-Terzil-Mittelgruppe)")
print()

lauf = Discoverylauf()
lauf.ergebnisse.append(
    pruefe_faktor(ergebnis, validation, "RSI-Terzil (eingefrorene Discovery-Grenzen)",
                  faktor_rsi_terzil, punktwert=cfg.market.point_value)
)

print("=" * 78)
print(lauf.bericht())
print("=" * 78)
print(lauf.statistikbericht())
print()
print("Zum Vergleich, Discovery-Lauf 24.08.2026 (ganzer 70-%-Trainingsteil, gepoolt):")
print("  1 niedrig     brutto +1.217 Pkt (Trade-Zahl im Bericht nicht einzeln genannt)")
print("  2 mittel      1435 Trades   brutto -3.199 Pkt   t=-4.74  (der gemeldete Fund)")
print("  3 hoch        brutto +2.671 Pkt (Trade-Zahl im Bericht nicht einzeln genannt)")
