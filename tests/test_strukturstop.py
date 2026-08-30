"""Strukturelle Stops - wohin der Stop chartlich gehoert.

Laurins Frage vom 30.08.2026: nicht "50 oder 100 Dollar", sondern wo der Stop
strukturell sitzen muss. Ein Stop unter dem letzten Tief hat eine Begruendung,
1,5 x ATR hat keine.

Drei Dinge werden hier abgesichert, und jedes einzelne waere als Fehler
unauffaellig:

1. **Kein Lookahead.** Ein Stop auf einem Tief, das beim Einstieg noch nicht
   bestaetigt war, sieht im Backtest besser aus - er liegt zufaellig immer
   knapp unter dem tatsaechlichen Tief.
2. **Die Short-Seite.** Ein Short-Stop gehoert ueber ein HOCH. Mit derselben
   Spalte fuer beide Richtungen waere die halbe Strategie falsch abgesichert.
3. **Der Rueckfall wird gezaehlt.** Griff das Niveau nur bei einem Zehntel der
   Trades, misst man ueberwiegend den ATR-Rueckfall und nennt es "Stop am
   letzten Tief".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.engine import LONG, SHORT, Backtester, CostModel, ExitReason
from backtest.strategies.base import ColumnAbove, CrossesAbove, RuleStrategy
from backtest.strategies.library import (
    STOP_VARIANTEN,
    build_strategy,
    mit_stop_variante,
    stop_spalten_fuer,
)
from common.strukturniveaus import STRUKTUR_SPALTEN, strukturniveau_spalten


@pytest.fixture
def backtester(market_cfg, indicator_cfg) -> Backtester:
    return Backtester(
        market_cfg,
        indicator_cfg,
        CostModel(commission_per_side=0.0, slippage_ticks_per_side=0.0,
                  tick_size=0.25, point_value=2.0),
    )


def _zickzack(n: int = 900, *, drift: float = -3.0) -> pd.DataFrame:
    """Kursverlauf mit klaren, wiederkehrenden Swing-Punkten.

    ``drift`` negativ: die Grundtendenz faellt, damit Long-Einstiege auch
    tatsaechlich ausgestoppt werden. Mit steigender Tendenz lief die
    Zickzack-Reihe nie unter das letzte Tief, und der Test war leer gruen.
    """
    preise: list[float] = []
    for k in range(n // 20 + 1):
        basis = 20000.0 + k * drift
        preise += [
            basis, basis + 12, basis + 24, basis + 30, basis + 34,
            basis + 30, basis + 18, basis + 6, basis - 6, basis - 12,
            basis - 8, basis + 4, basis + 16, basis + 26, basis + 32,
            basis + 28, basis + 14, basis + 2, basis - 10, basis - 14,
        ]
    preise = preise[:n]
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": [p + 3.0 for p in preise],
            "low": [p - 3.0 for p in preise],
            "close": preise,
            "volume": [900.0] * n,
        },
        index=index,
    )


# -- Die Niveauserie --------------------------------------------------------

def test_alle_strukturspalten_entstehen():
    niveaus = strukturniveau_spalten(_zickzack())
    assert list(niveaus.columns) == list(STRUKTUR_SPALTEN)


def test_niveaus_sind_nicht_dauerhaft_leer():
    """Vorhandene, aber immer leere Spalten waeren ein stiller Ausfall."""
    niveaus = strukturniveau_spalten(_zickzack())
    for spalte in STRUKTUR_SPALTEN:
        assert niveaus[spalte].notna().any(), f"{spalte} ist durchgehend leer"


def test_vorletztes_niveau_liegt_hinter_dem_letzten():
    """Sonst waeren die beiden Varianten dasselbe."""
    niveaus = strukturniveau_spalten(_zickzack())
    beide = niveaus[["letztes_swing_tief", "vorletztes_swing_tief"]].dropna()
    assert len(beide) > 50
    assert (beide["letztes_swing_tief"] != beide["vorletztes_swing_tief"]).any()


def test_kein_lookahead_in_den_niveaus():
    """DER Test dieses Moduls.

    Ein Stop auf einem Tief, das beim Einstieg noch nicht bestaetigt war,
    sieht im Backtest besser aus - er liegt zufaellig immer knapp unter dem
    tatsaechlichen Tief. Hier wird die Reihe abgeschnitten und geprueft, dass
    sich an den frueheren Werten nichts aendert.
    """
    daten = _zickzack()
    schnitt = 600
    voll = strukturniveau_spalten(daten)
    kurz = strukturniveau_spalten(daten.iloc[:schnitt])

    for spalte in STRUKTUR_SPALTEN:
        pd.testing.assert_series_equal(
            voll[spalte].iloc[:schnitt], kurz[spalte], check_names=False
        )


def test_niveau_ist_erst_nach_bestaetigung_da():
    """Ein Swing-Tief ist an seiner eigenen Kerze nicht erkennbar."""
    from common.strukturniveaus import STANDARD_STRENGTH
    from common.structure import find_swing_points

    daten = _zickzack(300)
    niveaus = strukturniveau_spalten(daten)
    punkte = [p for p in find_swing_points(daten, strength=STANDARD_STRENGTH)
              if p.kind == "low"]
    assert punkte

    letzter = len(daten) - 1
    erstes_tief_index = min(letzter - p.bars_ago for p in punkte)
    # Vor der Bestaetigung darf kein Niveau stehen.
    assert niveaus["letztes_swing_tief"].iloc[erstes_tief_index] != niveaus[
        "letztes_swing_tief"
    ].iloc[erstes_tief_index + STANDARD_STRENGTH] or pd.isna(
        niveaus["letztes_swing_tief"].iloc[erstes_tief_index]
    )


# -- Die Varianten ----------------------------------------------------------

def test_jede_variante_hat_eine_short_entsprechung():
    """Ein Short-Stop gehoert ueber ein HOCH, nicht unter ein Tief."""
    for variante in STOP_VARIANTEN:
        lang, kurz = stop_spalten_fuer(variante)
        if lang is None:
            assert kurz is None
            continue
        assert kurz is not None, f"{variante} hat keine Short-Spalte"
        assert "tief" in lang or "low" in lang
        assert "hoch" in kurz or "high" in kurz


def test_unbekannte_variante_bricht_ab():
    with pytest.raises(KeyError, match="mondphase"):
        stop_spalten_fuer("mondphase")


def test_varianten_unterscheiden_sich_nur_im_stop():
    """Der ganze Punkt: ein einziger Unterschied."""
    basis = build_strategy("doppelboden_bestaetigt")
    a = mit_stop_variante(basis, "letztes_swing")
    b = mit_stop_variante(basis, "vortag")

    assert a.stop_loss_spalte != b.stop_loss_spalte
    assert a.long_entry is b.long_entry
    assert a.take_profit_atr == b.take_profit_atr
    assert a.max_bars_in_trade == b.max_bars_in_trade


def test_strukturspalten_stehen_in_benoetigte_spalten():
    """Sonst faellt der Stop still auf ATR zurueck, statt dass es auffaellt."""
    s = mit_stop_variante(build_strategy("doppelboden_bestaetigt"), "letztes_swing")
    assert "letztes_swing_tief" in s.benoetigte_spalten()
    assert "letztes_swing_hoch" in s.benoetigte_spalten()


# -- Die Engine -------------------------------------------------------------

def _long_strategie(**overrides) -> RuleStrategy:
    vorgabe = dict(
        name="test",
        long_entry=CrossesAbove("close", "sma_fast"),
        long_exit=None,
        stop_loss_atr=1.5,
        take_profit_atr=None,
        max_bars_in_trade=None,
        close_at_session_end=False,
    )
    vorgabe.update(overrides)
    return RuleStrategy(**vorgabe)


def test_stop_sitzt_auf_dem_niveau_minus_puffer(backtester):
    daten = backtester.prepare(_zickzack())
    strategie = _long_strategie(
        stop_loss_spalte="letztes_swing_tief",
        stop_loss_puffer_ticks=4.0,
    )
    ergebnis = backtester.run(daten, strategie, already_prepared=True)
    assert ergebnis.trades

    gestoppte = [t for t in ergebnis.trades if t.exit_reason == ExitReason.STOP]
    assert gestoppte, "Kein einziger Trade wurde ausgestoppt"

    # Der Stop muss unter dem Niveau der Entscheidungskerze liegen.
    for trade in gestoppte[:20]:
        einstieg = daten.index.get_loc(pd.Timestamp(trade.entry_time))
        niveau = daten["letztes_swing_tief"].iloc[einstieg - 1]
        if pd.isna(niveau):
            continue
        assert trade.exit_price <= niveau + 0.01


def test_rueckfall_wird_gezaehlt(backtester):
    """Ohne diese Zahl liesse sich eine Stop-Variante nicht beurteilen."""
    daten = backtester.prepare(_zickzack())
    strategie = _long_strategie(stop_loss_spalte="letztes_swing_tief")
    ergebnis = backtester.run(daten, strategie, already_prepared=True)

    assert ergebnis.strukturstops + ergebnis.stop_rueckfaelle == len(ergebnis.trades)
    assert ergebnis.strukturstop_anteil is not None
    assert 0.0 <= ergebnis.strukturstop_anteil <= 1.0


def test_ohne_strukturspalte_bleibt_alles_beim_alten(backtester):
    """Die ATR-Variante muss exakt das Bisherige tun - sie ist die Nulllinie."""
    daten = backtester.prepare(_zickzack())
    alt = backtester.run(daten, _long_strategie(), already_prepared=True)
    neu = backtester.run(
        daten, _long_strategie(stop_loss_spalte=None), already_prepared=True
    )

    assert len(alt.trades) == len(neu.trades)
    for a, b in zip(alt.trades, neu.trades):
        assert a.exit_price == pytest.approx(b.exit_price)
        assert a.pnl == pytest.approx(b.pnl)
    assert neu.strukturstops == 0


def test_stop_auf_der_falschen_seite_faellt_zurueck(backtester):
    """Liegt das Niveau beim Einstieg schon jenseits des Kurses, waere es kein
    Stop, sondern ein sofortiger Ausstieg."""
    daten = backtester.prepare(_zickzack())
    # Ein Niveau WEIT ueber dem Kurs - als Long-Stop unbrauchbar.
    daten = daten.copy()
    daten["kaputtes_niveau"] = daten["close"] + 500.0

    strategie = _long_strategie(stop_loss_spalte="kaputtes_niveau")
    ergebnis = backtester.run(daten, strategie, already_prepared=True)

    assert ergebnis.strukturstops == 0
    assert ergebnis.stop_rueckfaelle == len(ergebnis.trades)
    # Und kein Trade darf sofort am Einstieg ausgestoppt worden sein.
    sofort = [t for t in ergebnis.trades
              if t.exit_reason == ExitReason.STOP and t.bars_held == 0]
    assert not sofort
