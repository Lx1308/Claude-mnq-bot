"""Tests der Kennzahlen und der In-Sample/Out-of-Sample-Trennung."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from backtest.engine import LONG, SHORT, BacktestResult, Trade
from backtest.metrics import compute_metrics, max_consecutive_losses, max_drawdown
from backtest.splits import (
    OutOfSampleViolation,
    assert_in_sample_only,
    assert_validation_only,
    split_data,
    split_data_three_way,
    walk_forward_windows,
)
from common.config import SplitConfig
from tests.conftest import make_ohlcv


def make_trade(pnl: float, *, index: int = 0, bars: int = 10) -> Trade:
    base = datetime(2025, 1, 2, 15, 0, tzinfo=timezone.utc)
    return Trade(
        direction=LONG if pnl >= 0 else SHORT,
        entry_time=base,
        entry_price=100.0,
        exit_time=base,
        exit_price=100.0 + pnl,
        bars_held=bars,
        exit_reason="signal",
        gross_points=pnl,
        commission=0.0,
        pnl=pnl,
    )


def make_result(pnls: list[float]) -> BacktestResult:
    index = pd.date_range("2025-01-02", periods=max(len(pnls), 2), freq="1D", tz="UTC")
    equity = pd.Series(
        # dtype ausdruecklich: bei leerer Liste waere die Reihe sonst object-dtype,
        # und ffill auf object-dtype ist in pandas abgekuendigt (FutureWarning).
        pd.Series(pnls, dtype="float64").cumsum().reindex(range(len(index))).ffill().fillna(0.0).values,
        index=index,
    )
    return BacktestResult(
        strategy_name="test",
        strategy_description="test",
        trades=[make_trade(pnl, index=i) for i, pnl in enumerate(pnls)],
        equity=equity,
        bars=len(index),
        label="test",
    )


# ---------------------------------------------------------------------------
# Kennzahlen
# ---------------------------------------------------------------------------

def test_trefferquote_und_profitfaktor():
    metrics = compute_metrics(make_result([100.0, -50.0, 100.0, -50.0]))

    assert metrics.trades == 4
    assert metrics.wins == 2
    assert metrics.losses == 2
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.profit_factor == pytest.approx(2.0)   # 200 / 100
    assert metrics.total_pnl == pytest.approx(100.0)
    assert metrics.avg_win == pytest.approx(100.0)
    assert metrics.avg_loss == pytest.approx(-50.0)


def test_profitfaktor_ist_unendlich_ohne_verluste():
    metrics = compute_metrics(make_result([10.0, 20.0, 30.0]))
    assert math.isinf(metrics.profit_factor)


def test_profitfaktor_ist_null_ohne_trades():
    metrics = compute_metrics(make_result([]))
    assert metrics.profit_factor == 0.0
    assert metrics.trades == 0
    assert metrics.win_rate == 0.0


def test_max_drawdown_findet_den_groessten_rueckgang():
    equity = pd.Series(
        [0.0, 100.0, 250.0, 120.0, 180.0, 60.0, 300.0],
        index=pd.date_range("2025-01-02", periods=7, freq="1D", tz="UTC"),
    )
    absolute, relative = max_drawdown(equity)

    # Hoch 250 -> Tief 60 = 190
    assert absolute == pytest.approx(190.0)
    assert relative == pytest.approx(190.0 / 250.0)


def test_max_drawdown_bei_leerer_kurve():
    absolute, relative = max_drawdown(pd.Series(dtype=float))
    assert absolute == 0.0
    assert relative is None


def test_laengste_verluststraehne():
    assert max_consecutive_losses([1.0, -1.0, -1.0, -1.0, 1.0, -1.0]) == 3
    assert max_consecutive_losses([1.0, 2.0]) == 0
    assert max_consecutive_losses([]) == 0


def test_sharpe_ist_none_bei_zu_wenigen_handelstagen():
    metrics = compute_metrics(make_result([100.0]))
    assert metrics.sharpe_pnl is None


def test_sharpe_auf_kapital_wird_nur_mit_kapitalangabe_berechnet():
    result = make_result([100.0, -40.0, 60.0, -20.0, 80.0])
    ohne = compute_metrics(result)
    mit = compute_metrics(result, initial_capital=50_000.0)

    assert ohne.sharpe_on_capital is None
    assert mit.sharpe_on_capital is not None


# ---------------------------------------------------------------------------
# In-Sample / Out-of-Sample
# ---------------------------------------------------------------------------

def test_split_nach_anteil_teilt_chronologisch():
    frame = make_ohlcv(list(range(100)))
    split = split_data(frame, SplitConfig(mode="fraction", in_sample_fraction=0.7))

    assert len(split.in_sample) == 70
    assert len(split.out_of_sample) == 30
    # Keine Ueberschneidung, keine Luecke.
    assert split.in_sample.index.max() < split.out_of_sample.index.min()
    assert len(split.in_sample) + len(split.out_of_sample) == len(frame)


def test_split_nach_datum():
    frame = make_ohlcv(list(range(200)), start="2025-01-02 00:00", freq="1h")
    boundary = frame.index[120].isoformat()
    split = split_data(frame, SplitConfig(mode="date", split_date=boundary))

    assert split.out_of_sample.index[0] == frame.index[120]
    assert len(split.in_sample) == 120


def test_split_wirft_bei_leerem_teil():
    frame = make_ohlcv(list(range(10)))
    with pytest.raises(ValueError, match="leeren Teil"):
        split_data(frame, SplitConfig(mode="date", split_date="2099-01-01"))


def test_optimierung_auf_out_of_sample_wird_verhindert():
    frame = make_ohlcv(list(range(100)))
    split = split_data(frame, SplitConfig(mode="fraction", in_sample_fraction=0.7))

    # Der In-Sample-Teil ist erlaubt ...
    assert_in_sample_only(split.in_sample, split)

    # ... der volle Datensatz nicht.
    with pytest.raises(OutOfSampleViolation, match="Out-of-Sample"):
        assert_in_sample_only(frame, split)


# ---------------------------------------------------------------------------
# Dreiwege-Split: Training / Validation / Out-of-Sample
# ---------------------------------------------------------------------------

def test_dreiwege_split_teilt_chronologisch_ohne_ueberlappung():
    frame = make_ohlcv(list(range(100)))
    split = split_data_three_way(
        frame, SplitConfig(mode="fraction", in_sample_fraction=0.7, validation_fraction=0.5)
    )

    assert len(split.train) == 70
    # Rest sind 30 Kerzen, davon die Haelfte Validation, die Haelfte OOS.
    assert len(split.validation) == 15
    assert len(split.out_of_sample) == 15
    assert len(split.train) + len(split.validation) + len(split.out_of_sample) == len(frame)
    assert split.train.index.max() < split.validation.index.min()
    assert split.validation.index.max() < split.out_of_sample.index.min()


def test_dreiwege_split_traingrenze_ist_dieselbe_wie_beim_zweiwege_split():
    """Die Dreiteilung darf die bereits von Discovery verbrauchte Grenze nicht verschieben."""
    frame = make_ohlcv(list(range(200)))
    cfg = SplitConfig(mode="fraction", in_sample_fraction=0.7, validation_fraction=0.5)

    zweiwege = split_data(frame, cfg)
    dreiwege = split_data_three_way(frame, cfg)

    assert dreiwege.validation_boundary == zweiwege.boundary
    assert len(dreiwege.train) == len(zweiwege.in_sample)


def test_dreiwege_split_wirft_bei_ungueltigem_validation_anteil():
    frame = make_ohlcv(list(range(100)))
    with pytest.raises(ValueError, match="validation_fraction"):
        split_data_three_way(
            frame, SplitConfig(mode="fraction", in_sample_fraction=0.7, validation_fraction=0.0)
        )
    with pytest.raises(ValueError, match="validation_fraction"):
        split_data_three_way(
            frame, SplitConfig(mode="fraction", in_sample_fraction=0.7, validation_fraction=1.0)
        )


def test_dreiwege_split_unterstuetzt_kein_datum():
    frame = make_ohlcv(list(range(100)))
    with pytest.raises(ValueError, match="mode='fraction'"):
        split_data_three_way(
            frame, SplitConfig(mode="date", split_date="2025-01-01", validation_fraction=0.5)
        )


def test_validation_auf_out_of_sample_wird_verhindert():
    frame = make_ohlcv(list(range(100)))
    split = split_data_three_way(
        frame, SplitConfig(mode="fraction", in_sample_fraction=0.7, validation_fraction=0.5)
    )

    # Training und Validation gemeinsam sind erlaubt - Indikatoren brauchen
    # den Trainingsvorlauf (Invariante 5).
    training_und_validation = frame.loc[: split.validation.index[-1]]
    assert_validation_only(training_und_validation, split)

    # Der volle Datensatz reicht in den Out-of-Sample-Teil hinein.
    with pytest.raises(OutOfSampleViolation, match="Out-of-Sample"):
        assert_validation_only(frame, split)


def test_ideas_bars_muessen_zwei_sessions_abdecken():
    """Regressionstest fuer einen stillen Ausfall - umgezogen, nicht entfernt.

    Mit zu wenig Kerzen bleiben prev_session_high/-low dauerhaft NaN, und das
    Setup pdh_pdl_bruch loest NIE aus - ohne jede Fehlermeldung.

    Bis zum 22.08.2026 haftete diese Zusicherung an
    ``market.candle_buffer_size`` und den Vortages-Alarmen des Live-Bots. Der
    Alarmpfad ist entfernt, die Gefahr nicht: sie ist mit der
    Ideen-Protokollierung nach ``ideas.bars`` umgezogen.
    """
    from dataclasses import replace

    from common.config import Config, ConfigError

    basis = Config.load("config.yaml")

    # 5m-Kerzen: eine 23-Stunden-Session hat 276, zwei also 552.
    zu_wenig = replace(basis, ideas=replace(basis.ideas, timeframe="5m", bars=300))
    with pytest.raises(ConfigError, match="Vortageshoch"):
        zu_wenig.validate()

    # Gegenprobe: knapp darueber muss durchgehen. Ohne sie bliebe der Test
    # auch dann gruen, wenn validate() aus einem anderen Grund immer wuerfe.
    genug = replace(basis, ideas=replace(basis.ideas, timeframe="5m", bars=600))
    genug.validate()


def test_ideas_bars_pruefung_skaliert_mit_dem_timeframe():
    """Auf 15m reichen weniger Kerzen als auf 5m - die Pruefung muss das kennen."""
    from dataclasses import replace

    from common.config import Config, ConfigError

    basis = Config.load("config.yaml")

    # 15m: zwei Sessions = 2 * 92 = 184. 300 reicht hier also, auf 5m nicht.
    auf_15m = replace(basis, ideas=replace(basis.ideas, timeframe="15m", bars=300))
    auf_15m.validate()

    auf_5m = replace(basis, ideas=replace(basis.ideas, timeframe="5m", bars=300))
    with pytest.raises(ConfigError):
        auf_5m.validate()


def test_bars_per_session_skaliert_mit_dem_kerzenintervall(market_cfg):
    from dataclasses import replace

    minuetlich = replace(market_cfg, candle_interval_minutes=1)
    fuenf_minuten = replace(market_cfg, candle_interval_minutes=5)

    assert minuetlich.bars_per_session == 23 * 60
    assert fuenf_minuten.bars_per_session == 23 * 60 // 5
    assert minuetlich.bars_for_previous_session == 2 * minuetlich.bars_per_session


def test_robustheit_ist_ohne_positiven_in_sample_vorteil_keine_zahl():
    """Der Befund vom 23.08.2026: der Quotient log, wenn beide Seiten negativ sind.

    prev_day_breakout auf zehn Jahren Naeherungshistorie: Durchschnittstrade -4.40 USD
    in-sample, -9.02 USD out-of-sample. Der Verlust hat sich mehr als
    verdoppelt, der Quotient stand bei 2.05 und der Report nannte das
    "stabil".
    """
    from backtest.compare import StrategyRun
    from backtest.strategies.base import RuleStrategy

    schlechter_is = make_result([-10.0, -10.0, 5.0])
    noch_schlechter_oos = make_result([-30.0, -30.0, 5.0])

    run = StrategyRun(
        strategy=RuleStrategy(name="test"),
        in_sample=schlechter_is,
        out_of_sample=noch_schlechter_oos,
        in_sample_metrics=compute_metrics(schlechter_is),
        out_of_sample_metrics=compute_metrics(noch_schlechter_oos),
    )

    assert run.in_sample_metrics.avg_trade < 0
    assert run.out_of_sample_metrics.avg_trade < run.in_sample_metrics.avg_trade
    assert run.robustness is None


def test_robustheit_wird_bei_positivem_in_sample_ergebnis_berechnet():
    from backtest.compare import StrategyRun
    from backtest.strategies.base import RuleStrategy

    gut_is = make_result([30.0, -10.0, 10.0])           # Durchschnitt +10
    halb_so_gut_oos = make_result([15.0, -10.0, 10.0])  # Durchschnitt +5

    run = StrategyRun(
        strategy=RuleStrategy(name="test"),
        in_sample=gut_is,
        out_of_sample=halb_so_gut_oos,
        in_sample_metrics=compute_metrics(gut_is),
        out_of_sample_metrics=compute_metrics(halb_so_gut_oos),
    )

    assert run.robustness == pytest.approx(0.5)


def test_walk_forward_fenster_ueberlappen_nicht_zwischen_train_und_test():
    frame = make_ohlcv(list(range(1000)))
    windows = walk_forward_windows(frame, train_bars=200, test_bars=100)

    assert len(windows) > 1
    for train, test in windows:
        assert len(train) == 200
        assert len(test) == 100
        assert train.index.max() < test.index.min()
