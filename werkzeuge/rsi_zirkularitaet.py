"""Zirkularitaetspruefung: RSI-Terzil-Treffer von ``rsi_mean_reversion``.

WOZU
----
``docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`` fand vier signifikante Gruppen
bei ``rsi_mean_reversion`` (RSI-Terzil mittel/hoch, Stochastik-Terzil
mittel/hoch), markierte sie aber als "vermutlich zirkulaer": die Strategie
steigt selbst genau dann ein, wenn RSI die 30 von unten bzw. die 70 von oben
kreuzt (``backtest/strategies/library.py:105-112``). Der RSI-Faktor aus
``backtest/research.py`` liest den RSI-Wert der EINSTIEGSKERZE (Eroeffnung der
Folgekerze, Invariante 4) - nicht den der SIGNALKERZE, auf deren Schlusskurs
die Regel tatsaechlich ausgewertet wurde.

Dieses Skript rechnet den RSI-Terzil-Faktor ein zweites Mal, diesmal mit dem
RSI-Wert der Signalkerze (Position entry_index - 1 im selben vorbereiteten
Rahmen - siehe ``backtest/engine.py:310-329``: das Signal wird auf Zeile i-1
gesetzt, ausgefuehrt auf Zeile i). Bleiben die Terzil-Gruppen unter diesem
naeheren Blick auf die eigene Einstiegsregel weiterhin signifikant getrennt,
ist der Fund weniger trivial als vermutet. Verschwindet die Trennung fast
vollstaendig, bestaetigt das die Zirkularitaetsvermutung.

NUR auf dem Trainingsteil (70 Prozent), dieselbe Aufteilung wie beim
Discovery-Lauf. Der Out-of-Sample-Block bleibt unberuehrt.

Aufruf (braucht PYTHONPATH, da ausserhalb der CLI):
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\rsi_zirkularitaet.py
"""

import math

import numpy as np
import pandas as pd

from backtest.engine import Backtester, CostModel, Trade
from backtest.kosten import profil_aus_config
from backtest.research import (
    Discoverylauf,
    baue_faktor_perzentil,
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

instrument = get_instrument(cfg.market.product)
vorbereitet = vorbereiten(training, instrument, cfg)
pruefe_nur_training(vorbereitet, trainingsende)

grenzen = perzentilgrenzen(vorbereitet, "rsi", [33.0, 67.0])
print(f"RSI-Terzilgrenzen (gemessen, wie im Discovery-Lauf): {grenzen[0]:.3f} / {grenzen[1]:.3f}")
print()

ergebnis = bt.run(vorbereitet, build_strategy("rsi_mean_reversion"), already_prepared=True)
print(f"rsi_mean_reversion: {len(ergebnis.trades)} Trades im Training")
print()


def baue_faktor_signalkerze(spalte: str, grenzen_liste, namen) -> "callable":
    """Wie ``baue_faktor_perzentil``, liest aber die Zeile VOR dem Einstieg.

    Die Signalkerze ist die Zeile, auf deren Schlusskurs die Einstiegsregel
    tatsaechlich feuerte (``backtest/engine.py``: Signal auf Zeile i-1,
    Ausfuehrung auf Zeile i). Kein Blick nach vorn - im Gegenteil, ein Blick
    eine Kerze weiter zurueck als der bisherige Faktor.
    """
    positionen = {ts: i for i, ts in enumerate(vorbereitet.index)}

    def faktor(trade: Trade, rahmen: pd.DataFrame) -> "str | None":
        marke = pd.Timestamp(trade.entry_time)
        if marke.tzinfo is None:
            marke = marke.tz_localize("UTC")
        pos = positionen.get(marke)
        if pos is None or pos == 0:
            return None
        wert = rahmen[spalte].iloc[pos - 1]
        try:
            zahl = float(wert)
        except (TypeError, ValueError):
            return None
        if math.isnan(zahl):
            return None
        for i, grenze in enumerate(grenzen_liste):
            if zahl <= grenze:
                return namen[i]
        return namen[-1]

    return faktor


namen = ["1 niedrig", "2 mittel", "3 hoch"]
faktor_einstiegskerze = baue_faktor_perzentil("rsi", grenzen, namen)
faktor_signalkerze = baue_faktor_signalkerze("rsi", grenzen, namen)

lauf = Discoverylauf()
lauf.ergebnisse.append(
    pruefe_faktor(ergebnis, vorbereitet, "RSI-Terzil (Einstiegskerze, wie im Discovery-Lauf)",
                  faktor_einstiegskerze, punktwert=cfg.market.point_value)
)
lauf.ergebnisse.append(
    pruefe_faktor(ergebnis, vorbereitet, "RSI-Terzil (Signalkerze, tatsaechliche Regelauswertung)",
                  faktor_signalkerze, punktwert=cfg.market.point_value)
)

print("=" * 78)
print(lauf.bericht())
print("=" * 78)
print(lauf.statistikbericht())
