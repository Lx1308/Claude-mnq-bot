"""Tests des Walk-Forward-Laufs.

Der Schwerpunkt liegt auf zwei Dingen: die Fenster duerfen nicht in die
Zukunft greifen, und Summengroessen duerfen bei ueberlappenden Fenstern nicht
ausgewiesen werden.
"""

from __future__ import annotations

import numpy as np
import pytest

from backtest.engine import Backtester, CostModel
from backtest.splits import walk_forward_windows
from backtest.strategies.base import CrossesAbove, CrossesBelow, RuleStrategy
from backtest.walkforward import (
    MODUS_FESTE_PARAMETER,
    WalkForwardError,
    bericht_text,
    lauf,
    pruefe_chronologie,
)
from tests.conftest import make_ohlcv


@pytest.fixture
def backtester(market_cfg, indicator_cfg) -> Backtester:
    costs = CostModel(
        commission_per_side=2.0,
        slippage_ticks_per_side=0.0,
        tick_size=0.25,
        point_value=20.0,
    )
    return Backtester(market_cfg, indicator_cfg, costs)


def saegezahn(laenge: int) -> list[float]:
    """Regelmaessige Auf- und Abbewegung - loest die Testregel wiederholt aus."""
    return [100.0 + 8.0 * float(np.sin(i / 9.0)) for i in range(laenge)]


def mach_strategie() -> RuleStrategy:
    return RuleStrategy(
        name="wf_test",
        long_entry=CrossesAbove("close", 105.0),
        long_exit=CrossesBelow("close", 99.0),
        stop_loss_atr=None,
        take_profit_atr=None,
        max_bars_in_trade=None,
        close_at_session_end=False,
    )


# ---------------------------------------------------------------------------
# Lookahead
# ---------------------------------------------------------------------------

def test_kein_testfenster_liegt_vor_seinem_trainingsfenster():
    frame = make_ohlcv(list(range(1200)))
    fenster = walk_forward_windows(frame, train_bars=300, test_bars=150)

    assert len(fenster) > 1
    pruefe_chronologie(fenster)   # wirft, wenn die Reihenfolge kippt


def test_pruefe_chronologie_meldet_vertauschte_fenster():
    frame = make_ohlcv(list(range(400)))
    train = frame.iloc[200:300]
    test = frame.iloc[0:100]      # absichtlich davor

    with pytest.raises(WalkForwardError, match="Testfenster beginnt"):
        pruefe_chronologie([(train, test)])


def test_testfenster_ueberlappen_nicht_wenn_schritt_gleich_testlaenge():
    frame = make_ohlcv(list(range(1000)))
    fenster = walk_forward_windows(frame, train_bars=200, test_bars=100, step_bars=100)

    grenzen = [(test.index[0], test.index[-1]) for _, test in fenster]
    for (_, vorheriges_ende), (naechster_anfang, _) in zip(grenzen, grenzen[1:]):
        assert vorheriges_ende < naechster_anfang


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def test_lauf_erzeugt_ein_ergebnis_je_fenster(backtester):
    frame = make_ohlcv(saegezahn(1500))
    bericht = lauf(backtester, frame, mach_strategie(), train_bars=300, test_bars=200)

    erwartet = len(
        walk_forward_windows(backtester.prepare(frame), train_bars=300, test_bars=200)
    )
    assert bericht.anzahl_fenster == erwartet
    assert bericht.anzahl_fenster > 1
    assert [f.nummer for f in bericht.fenster] == list(range(1, erwartet + 1))
    for f in bericht.fenster:
        assert f.train_bis < f.test_von


def test_lauf_bricht_bei_zu_kurzer_historie_ab_statt_null_fenster_zu_liefern(backtester):
    # Null Fenster liest sich wie "die Strategie hat nichts gefunden" statt wie
    # "die Historie reicht fuer diese Fenstergroessen nicht".
    frame = make_ohlcv(saegezahn(300))

    with pytest.raises(WalkForwardError, match="Historie zu kurz"):
        lauf(backtester, frame, mach_strategie(), train_bars=500, test_bars=200)


def test_lauf_meldet_den_modus_ausdruecklich(backtester):
    frame = make_ohlcv(saegezahn(1200))
    bericht = lauf(backtester, frame, mach_strategie(), train_bars=300, test_bars=200)

    assert bericht.modus == MODUS_FESTE_PARAMETER
    assert "keine Suche" in bericht.modus


# ---------------------------------------------------------------------------
# Summen bei Ueberlappung
# ---------------------------------------------------------------------------

def test_summen_bleiben_leer_wenn_die_testfenster_ueberlappen(backtester):
    frame = make_ohlcv(saegezahn(1500))
    bericht = lauf(
        backtester, frame, mach_strategie(), train_bars=300, test_bars=200, step_bars=50
    )

    assert bericht.fenster_ueberlappen is True
    # Dieselbe Kerze steckt in mehreren Fenstern - eine Summe waere zu gross.
    assert bericht.summe_trades is None
    assert bericht.summe_netto is None
    assert "nicht ausgewiesen" in bericht_text(bericht)


def test_summen_werden_ohne_ueberlappung_ausgewiesen(backtester):
    frame = make_ohlcv(saegezahn(1500))
    bericht = lauf(backtester, frame, mach_strategie(), train_bars=300, test_bars=200)

    assert bericht.fenster_ueberlappen is False
    assert bericht.summe_trades == sum(f.metriken.trades for f in bericht.fenster)
    assert bericht.summe_netto == pytest.approx(
        sum(f.metriken.total_pnl for f in bericht.fenster)
    )


def test_anteil_positiver_fenster_ist_none_ohne_fenster(backtester):
    from backtest.walkforward import WalkForwardBericht

    leer = WalkForwardBericht(
        strategie="leer",
        modus=MODUS_FESTE_PARAMETER,
        train_bars=10,
        test_bars=10,
        step_bars=10,
        fenster=[],
    )
    # Nicht 0.0: "kein Fenster war positiv" und "es gab keine Fenster" sind
    # verschiedene Aussagen.
    assert leer.anteil_positiver_fenster is None


def test_anteil_positiver_fenster_zaehlt_richtig(backtester):
    frame = make_ohlcv(saegezahn(1500))
    bericht = lauf(backtester, frame, mach_strategie(), train_bars=300, test_bars=200)

    positive = sum(1 for f in bericht.fenster if f.metriken.total_pnl > 0)
    assert bericht.anteil_positiver_fenster == pytest.approx(
        positive / bericht.anzahl_fenster
    )
    assert 0.0 <= bericht.anteil_positiver_fenster <= 1.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_kennt_das_walkforward_kommando():
    from backtest.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "walkforward",
            "--symbol", "DEMO",
            "--strategy", "vwap_trend",
            "--train-bars", "500",
            "--test-bars", "100",
        ]
    )
    assert args.command == "walkforward"
    assert args.train_bars == 500
    assert args.test_bars == 100
    assert args.step_bars is None   # ohne Angabe gleich test_bars, siehe lauf()


def test_cli_verlangt_fenstergroessen_ausdruecklich():
    from backtest.cli import build_parser

    parser = build_parser()
    # Kein stiller Vorgabewert: eine Fensterwahl, die niemand getroffen hat,
    # waere ein Ergebnis ohne Urheber.
    with pytest.raises(SystemExit):
        parser.parse_args(["walkforward", "--symbol", "DEMO", "--strategy", "vwap_trend"])
