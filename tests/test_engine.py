"""Tests der Backtest-Engine - vor allem: kein Look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import LONG, SHORT, Backtester, CostModel, ExitReason
from backtest.strategies.base import ColumnAbove, CrossesAbove, CrossesBelow, RuleStrategy
from tests.conftest import make_ohlcv


@pytest.fixture
def backtester(market_cfg, indicator_cfg) -> Backtester:
    costs = CostModel(
        commission_per_side=2.0,
        slippage_ticks_per_side=0.0,   # fuer exakte Preisvergleiche
        tick_size=0.25,
        point_value=20.0,
    )
    return Backtester(market_cfg, indicator_cfg, costs)


def simple_strategy(**overrides) -> RuleStrategy:
    defaults = dict(
        name="test",
        long_entry=CrossesAbove("close", 105.0),
        long_exit=CrossesBelow("close", 103.0),
        stop_loss_atr=None,
        take_profit_atr=None,
        max_bars_in_trade=None,
        close_at_session_end=False,
    )
    defaults.update(overrides)
    return RuleStrategy(**defaults)


# ---------------------------------------------------------------------------
# Ausfuehrungsmodell
# ---------------------------------------------------------------------------

def test_einstieg_erfolgt_zur_eroeffnung_der_folgekerze(backtester):
    # Kreuzung von 105 passiert auf Kerze 60; ausgefuehrt wird auf Kerze 61.
    closes = [100.0] * 60 + [106.0] + [107.0] * 5 + [102.0] * 5
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    result = backtester.run(frame, simple_strategy(), already_prepared=True)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.direction == LONG
    # Ausfuehrungskurs muss die Eroeffnung der FOLGEkerze sein.
    assert trade.entry_price == pytest.approx(frame["open"].iloc[61])
    assert trade.entry_time == frame.index[61].to_pydatetime()


def test_kein_lookahead_signal_der_letzten_kerze_wird_nicht_gehandelt(backtester):
    # Die Kreuzung passiert auf der allerletzten Kerze - es gibt keine
    # Folgekerze mehr, also darf kein Trade entstehen.
    closes = [100.0] * 80 + [106.0]
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    result = backtester.run(frame, simple_strategy(), already_prepared=True)
    assert result.trades == []


def test_ausstiegssignal_wird_ebenfalls_erst_naechste_kerze_ausgefuehrt(backtester):
    closes = [100.0] * 60 + [106.0, 107.0, 107.0, 102.0, 101.0, 101.0]
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    result = backtester.run(frame, simple_strategy(), already_prepared=True)

    assert len(result.trades) == 1
    trade = result.trades[0]
    # Kreuzung unter 103 auf Index 63 -> Ausstieg zur Eroeffnung von 64.
    assert trade.exit_price == pytest.approx(frame["open"].iloc[64])
    assert trade.exit_reason == ExitReason.SIGNAL


def test_stop_loss_greift_innerhalb_der_kerze(backtester, market_cfg, indicator_cfg):
    # Ruhiger Anstieg, dann Einstieg, dann harter Einbruch in einer Kerze.
    closes = list(np.linspace(100, 110, 70)) + [120.0] + [119.0] * 3 + [80.0] + [80.0] * 3
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    strategy = simple_strategy(
        long_entry=CrossesAbove("close", 115.0),
        long_exit=CrossesBelow("close", 1.0),   # feuert nie
        stop_loss_atr=1.0,
    )
    result = backtester.run(frame, strategy, already_prepared=True)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.STOP
    assert result.trades[0].pnl < 0


def test_take_profit_greift_innerhalb_der_kerze(backtester):
    closes = list(np.linspace(100, 110, 70)) + [120.0, 121.0, 200.0] + [200.0] * 3
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    strategy = simple_strategy(
        long_entry=CrossesAbove("close", 115.0),
        long_exit=CrossesBelow("close", 1.0),
        take_profit_atr=1.0,
    )
    result = backtester.run(frame, strategy, already_prepared=True)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.TARGET
    assert result.trades[0].pnl > 0


def test_stop_hat_vorrang_wenn_beides_in_derselben_kerze_liegt(backtester):
    # Die Ausbruchskerze deckt Stop UND Ziel ab -> pessimistisch: Stop.
    closes = list(np.linspace(100, 110, 70)) + [120.0] + [100.0] * 5
    frame = make_ohlcv(closes, spread=0.5)
    # Kerze nach dem Einstieg spannt eine sehr weite Range auf.
    frame.iloc[71, frame.columns.get_loc("high")] = 200.0
    frame.iloc[71, frame.columns.get_loc("low")] = 50.0
    prepared = backtester.prepare(frame)

    strategy = simple_strategy(
        long_entry=CrossesAbove("close", 115.0),
        long_exit=CrossesBelow("close", 1.0),
        stop_loss_atr=1.0,
        take_profit_atr=1.0,
    )
    result = backtester.run(prepared, strategy, already_prepared=True)

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.STOP


def test_zeitstop_schliesst_nach_n_kerzen(backtester):
    closes = [100.0] * 60 + [106.0] + [107.0] * 40
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    result = backtester.run(
        frame, simple_strategy(max_bars_in_trade=5), already_prepared=True
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == ExitReason.TIME
    assert result.trades[0].bars_held == 5


def test_immer_nur_eine_position_gleichzeitig(backtester):
    # Mehrfache Kreuzungen nach oben duerfen keine Positionen stapeln.
    closes = [100.0] * 55 + [106.0, 104.0, 106.0, 104.0, 106.0] * 5
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    strategy = simple_strategy(long_exit=CrossesBelow("close", 105.0))
    result = backtester.run(frame, strategy, already_prepared=True)

    for earlier, later in zip(result.trades, result.trades[1:]):
        assert earlier.exit_time <= later.entry_time


def test_sessionende_schliesst_offene_position(backtester):
    # Kerzen ueber den Sessionwechsel (18:00 ET = 23:00 UTC im Winter) hinweg.
    closes = [100.0] * 60 + [106.0] + [107.0] * 60
    frame = make_ohlcv(closes, start="2025-01-02 22:00", freq="1min", spread=0.5)
    prepared = backtester.prepare(frame)

    strategy = simple_strategy(close_at_session_end=True)
    result = backtester.run(prepared, strategy, already_prepared=True)

    assert result.trades, "Es sollte mindestens ein Trade entstehen."
    assert result.trades[0].exit_reason in (
        ExitReason.SESSION_END,
        ExitReason.END_OF_DATA,
    )


def test_short_trade_verdient_bei_fallenden_kursen(backtester):
    closes = [100.0] * 60 + [94.0] + [93.0] * 10
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))

    strategy = RuleStrategy(
        name="short_test",
        short_entry=CrossesBelow("close", 95.0),
        short_exit=ColumnAbove("close", 1000.0),   # feuert nie
        close_at_session_end=False,
    )
    result = backtester.run(frame, strategy, already_prepared=True)

    assert len(result.trades) == 1
    assert result.trades[0].direction == SHORT
    assert result.trades[0].pnl > 0


# ---------------------------------------------------------------------------
# Kosten
# ---------------------------------------------------------------------------

def test_kosten_reduzieren_das_ergebnis(market_cfg, indicator_cfg):
    closes = [100.0] * 60 + [106.0] + [107.0] * 5 + [102.0] * 5
    frame = make_ohlcv(closes, spread=0.5)

    ohne = Backtester(
        market_cfg, indicator_cfg,
        CostModel(commission_per_side=0.0, slippage_ticks_per_side=0.0,
                  tick_size=0.25, point_value=20.0),
    )
    mit = Backtester(
        market_cfg, indicator_cfg,
        CostModel(commission_per_side=5.0, slippage_ticks_per_side=2.0,
                  tick_size=0.25, point_value=20.0),
    )

    strategy = simple_strategy()
    pnl_ohne = sum(trade.pnl for trade in ohne.run(frame, strategy).trades)
    pnl_mit = sum(trade.pnl for trade in mit.run(frame, strategy).trades)

    assert pnl_mit < pnl_ohne


def test_equity_kurve_hat_die_laenge_der_daten(backtester):
    closes = [100.0] * 60 + [106.0] + [107.0] * 20
    frame = backtester.prepare(make_ohlcv(closes, spread=0.5))
    result = backtester.run(frame, simple_strategy(), already_prepared=True)

    assert len(result.equity) == len(frame)
    assert isinstance(result.equity.index, pd.DatetimeIndex)


def test_engine_verlangt_mindestens_zwei_kerzen(backtester):
    frame = backtester.prepare(make_ohlcv([100.0] * 60))
    with pytest.raises(ValueError, match="mindestens zwei"):
        backtester.run(frame.iloc[:1], simple_strategy(), already_prepared=True)
