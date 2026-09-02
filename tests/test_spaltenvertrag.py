"""Jede Strategie muss alle Spalten nennen, die sie liest.

WARUM DAS EIN EIGENER TEST IST
------------------------------
Die Engine reicht der Regelauswertung seit dem 30.08.2026 nur noch die
Spalten durch, die ``strategy.benoetigte_spalten()`` nennt - vorher war es
der ganze vorbereitete Rahmen. Das war der Engpass des Laufs: je Kerze zwei
pandas-Series ueber vierzig Spalten zu bauen kostet bei 519.000 Kerzen
Minuten.

Der Preis dafuer ist ein neues Risiko: eine Regel, die eine Spalte liest,
ohne sie zu deklarieren, funktionierte vorher zufaellig mit. Jetzt liest sie
NaN, feuert nie und liefert null Trades **ohne Fehlermeldung** - genau der
stille Ausfall, an dem ``ib_breakout`` jahrelang haengengeblieben ist.

Dieser Test schliesst die Luecke: fuer jede Strategie der Bibliothek muss der
Lauf auf dem beschnittenen Rahmen dieselben Trades liefern wie auf dem
vollen. Wo das nicht stimmt, fehlt eine Spalte in ``benoetigte_spalten()``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import Backtester, CostModel
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy


@pytest.fixture
def backtester(market_cfg, indicator_cfg) -> Backtester:
    return Backtester(
        market_cfg,
        indicator_cfg,
        CostModel(commission_per_side=0.95, slippage_ticks_per_side=1.0,
                  tick_size=0.25, point_value=2.0),
    )


@pytest.fixture(scope="module")
def bewegter_markt() -> pd.DataFrame:
    """Genug Bewegung, dass moeglichst viele Strategien ueberhaupt feuern.

    Ein Zufallspfad mit Trendphasen und Umkehrungen - nicht als Marktmodell,
    sondern damit die Regeln etwas zu tun bekommen. Fuer diesen Test zaehlt
    nur, dass beide Laeufe DASSELBE tun, nicht was.
    """
    rng = np.random.default_rng(20260830)
    n = 4000
    schritte = rng.normal(0.0, 6.0, n)
    # Ein paar Trendphasen aufpraegen.
    for start in range(0, n, 400):
        schritte[start : start + 200] += rng.choice([-1.2, 1.2])
    preise = 20000.0 + np.cumsum(schritte)

    index = pd.date_range("2026-01-05 09:00", periods=n, freq="5min", tz="UTC")
    spanne = np.abs(rng.normal(4.0, 1.5, n)) + 1.0
    return pd.DataFrame(
        {
            "open": preise,
            "high": preise + spanne,
            "low": preise - spanne,
            "close": preise + rng.normal(0.0, 1.0, n),
            "volume": rng.integers(200, 3000, n).astype(float),
        },
        index=index,
    )


@pytest.mark.parametrize("name", sorted(STRATEGY_LIBRARY))
def test_strategie_nennt_alle_spalten_die_sie_liest(name, backtester, bewegter_markt):
    """DER Test dieses Moduls.

    Gleiches Ergebnis auf dem beschnittenen wie auf dem vollen Rahmen -
    sonst liest die Strategie etwas, das sie nicht deklariert hat.
    """
    strategie = build_strategy(name)
    vorbereitet = backtester.prepare(bewegter_markt)

    voll = backtester.run(vorbereitet, strategie, already_prepared=True)

    # Nur die deklarierten Spalten plus das, was die Engine selbst braucht.
    pflicht = {"open", "high", "low", "close", "atr", "session_date"}
    behalten = sorted((strategie.benoetigte_spalten() | pflicht) & set(vorbereitet.columns))
    beschnitten = backtester.run(
        vorbereitet[behalten], strategie, already_prepared=True
    )

    assert len(beschnitten.trades) == len(voll.trades), (
        f"{name}: {len(voll.trades)} Trades auf dem vollen Rahmen, aber "
        f"{len(beschnitten.trades)} auf dem beschnittenen. Die Strategie liest "
        "eine Spalte, die sie in benoetigte_spalten() nicht nennt - damit "
        "faellt sie in der Engine still aus."
    )
    for a, b in zip(voll.trades, beschnitten.trades):
        assert a.entry_time == b.entry_time
        assert a.exit_time == b.exit_time
        assert a.pnl == pytest.approx(b.pnl)


def test_wenigstens_eine_strategie_feuert_ueberhaupt(backtester, bewegter_markt):
    """Sonst waere der Vertragstest oben leer und trotzdem gruen."""
    vorbereitet = backtester.prepare(bewegter_markt)
    gesamt = sum(
        len(backtester.run(vorbereitet, build_strategy(name), already_prepared=True).trades)
        for name in STRATEGY_LIBRARY
    )
    assert gesamt > 0, "Keine einzige Strategie hat auf den Testdaten gehandelt"
