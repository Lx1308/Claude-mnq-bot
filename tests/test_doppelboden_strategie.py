"""Das "W" als Strategie - und der Schutz gegen den stillen Ausfall.

``ib_breakout`` war jahrelang tot: die Strategie verlangte ``ib_high``/
``ib_low``, ``compute_indicators`` erzeugte diese Spalten nicht, und ueber
zehn Jahre Kursverlauf kam kein einziger Trade zustande. Null Trades liest
sich wie "die Idee hat nicht gegriffen" - deshalb pruefen diese Tests
ausdruecklich, dass die Musterspalten im vorbereiteten Rahmen ankommen und
dass die Strategien darauf feuern.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.engine import Backtester, CostModel
from backtest.strategies.base import BarContext, IstGesetzt, NichtUebersetzbar
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
from common.muster_serie import DOPPELMUSTER_SPALTEN


@pytest.fixture
def backtester(market_cfg, indicator_cfg) -> Backtester:
    return Backtester(
        market_cfg,
        indicator_cfg,
        CostModel(commission_per_side=0.95, slippage_ticks_per_side=1.0,
                  tick_size=0.25, point_value=2.0),
    )


def _kursverlauf_mit_w(n_wiederholungen: int = 12) -> pd.DataFrame:
    """Mehrere W-Formationen hintereinander, RTH-Zeiten, genug Vorlauf.

    Die Indikatoren brauchen Anlauf (SMA 50, ATR), deshalb ein ruhiger
    Vorlauf vor dem ersten Muster.
    """
    preise: list[float] = []
    # Vorlauf: leichtes Rauschen um 20000, damit ATR und SMA definiert sind.
    for i in range(300):
        preise.append(20000.0 + (i % 7) * 4.0 - 12.0)

    for k in range(n_wiederholungen):
        basis = 20000.0 + k * 5.0
        preise += [
            basis, basis - 20, basis - 40, basis - 60,
            basis - 80,                       # erstes Tief
            basis - 55, basis - 25, basis + 5, basis + 25,
            basis + 35,                       # Zwischenhoch
            basis + 5, basis - 25, basis - 55, basis - 70,
            basis - 78,                       # zweites Tief
            basis - 50, basis - 15, basis + 20, basis + 45,
            basis + 55, basis + 40, basis + 20, basis, basis - 10,
        ]

    index = pd.date_range(
        "2026-01-05 14:30", periods=len(preise), freq="5min", tz="UTC"
    )
    return pd.DataFrame(
        {
            "open": preise,
            "high": [p + 6.0 for p in preise],
            "low": [p - 6.0 for p in preise],
            "close": preise,
            "volume": [1000.0] * len(preise),
        },
        index=index,
    )


# -- Die Regel --------------------------------------------------------------

def test_istgesetzt_feuert_nur_auf_wahr():
    reihe = pd.Series({"w_erkannt": 1.0, "andere": 0.0})
    vorher = pd.Series({"w_erkannt": 0.0, "andere": 0.0})
    ctx = BarContext(
        timestamp=pd.Timestamp("2026-01-05 14:30", tz="UTC"),
        row=reihe, previous=vorher, position=0, bars_in_trade=0,
    )
    assert IstGesetzt("w_erkannt").evaluate(ctx)
    assert not IstGesetzt("andere").evaluate(ctx)


def test_istgesetzt_meldet_seine_spalte():
    """Ohne das faellt die Strategie still aus, statt abzubrechen."""
    assert IstGesetzt("w_nackenbruch").benoetigte_spalten() == {"w_nackenbruch"}


def test_istgesetzt_verweigert_die_pine_uebersetzung():
    """Lieber ehrlich ablehnen als naehern - eine genaeherte Pine-Fassung
    waere genau die Art Zahl, die aussieht wie eine Messung."""
    with pytest.raises(NichtUebersetzbar):
        IstGesetzt("w_erkannt").nach_pine({})


def test_unbekannte_spalte_feuert_nie():
    reihe = pd.Series({"close": 100.0})
    ctx = BarContext(
        timestamp=pd.Timestamp("2026-01-05 14:30", tz="UTC"),
        row=reihe, previous=reihe, position=0, bars_in_trade=0,
    )
    assert not IstGesetzt("gibtsnicht").evaluate(ctx)


# -- Die Strategien ---------------------------------------------------------

def test_beide_varianten_sind_registriert():
    assert "doppelboden_bestaetigt" in STRATEGY_LIBRARY
    assert "doppelboden_nackenbruch" in STRATEGY_LIBRARY


def test_die_varianten_unterscheiden_sich_nur_im_einstieg():
    """Der ganze Punkt des Vergleichs: dieselbe Mustererkennung, ein
    einziger Unterschied."""
    frueh = build_strategy("doppelboden_bestaetigt")
    spaet = build_strategy("doppelboden_nackenbruch")

    assert "w_erkannt" in frueh.benoetigte_spalten()
    assert "w_nackenbruch" in spaet.benoetigte_spalten()
    assert "w_nackenbruch" not in frueh.benoetigte_spalten()
    assert "w_erkannt" not in spaet.benoetigte_spalten()
    # Gleiches Risikoprofil, sonst vergleicht man zwei Dinge auf einmal.
    assert frueh.stop_loss_atr == spaet.stop_loss_atr
    assert frueh.take_profit_atr == spaet.take_profit_atr


# -- Die Verdrahtung: kommen die Spalten im Backtest an? --------------------

def test_prepare_liefert_die_musterspalten(backtester):
    """DER Test gegen den stillen Ausfall.

    Fehlt eine Spalte, liest die Regel NaN, feuert nie und liefert null
    Trades ohne Fehlermeldung - was sich liest wie "hat nicht gegriffen".
    """
    vorbereitet = backtester.prepare(_kursverlauf_mit_w())

    for spalte in DOPPELMUSTER_SPALTEN:
        assert spalte in vorbereitet.columns, f"{spalte} fehlt im Rahmen"


def test_die_musterspalten_sind_nicht_dauerhaft_leer(backtester):
    """Vorhandene, aber immer leere Spalten waeren derselbe stille Ausfall."""
    vorbereitet = backtester.prepare(_kursverlauf_mit_w())

    assert bool(vorbereitet["w_erkannt"].any()), "Kein einziges W erkannt"


def test_beide_strategien_finden_trades(backtester):
    """Ohne diesen Test waere ein toter Einstieg nicht von einer
    wirkungslosen Idee zu unterscheiden."""
    daten = _kursverlauf_mit_w()

    for name in ("doppelboden_bestaetigt", "doppelboden_nackenbruch"):
        ergebnis = backtester.run(daten, build_strategy(name))
        assert ergebnis.trades, f"{name} hat keinen einzigen Trade erzeugt"


def test_fehlende_musterspalte_bricht_ab_statt_still_zu_scheitern(backtester):
    """Der Schutzriegel aus Backtester.run - hier fuer die Musterspalten."""
    vorbereitet = backtester.prepare(_kursverlauf_mit_w())
    ohne = vorbereitet.drop(columns=["w_erkannt"])

    with pytest.raises(Exception) as fehler:
        backtester.run(ohne, build_strategy("doppelboden_bestaetigt"), already_prepared=True)
    assert "w_erkannt" in str(fehler.value)
