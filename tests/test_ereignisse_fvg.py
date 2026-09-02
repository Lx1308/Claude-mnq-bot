"""Fair Value Gap als Serie - Gleichheit mit detect_fair_value_gaps, kein
Lookahead.

Der punktuelle Erkenner verfolgt die Mitigation bis ans Reihenende
(O(Gaps x n)). Die Serie tut es in einem begrenzten Fenster. Diese Tests
sichern: dieselbe Gap-Menge, dasselbe Mitigation-Urteil innerhalb des
Fensters, keine Zukunftsinformation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.fvg import fvg_serie, fvg_spalten
from common.indicators import compute_indicators
from common.market_primitives import detect_fair_value_gaps


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _kurs(preise: list[float], spannen: list[float] | None = None) -> pd.DataFrame:
    n = len(preise)
    spannen = spannen or [1.0] * n
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": [p + s for p, s in zip(preise, spannen)],
            "low": [p - s for p, s in zip(preise, spannen)],
            "close": preise,
            "volume": [500.0] * n,
        },
        index=index,
    )


def test_bullish_gap_wird_erkannt():
    # Kerze 2 springt klar ueber das Hoch von Kerze 0.
    preise = [100.0, 101.0, 120.0, 121.0, 122.0]
    df = _kurs(preise)
    ev = fvg_serie(df, tick_size=0.25)
    bull = [e for e in ev if e.direction == 1]
    assert bull, "kein bullisher FVG erkannt"
    e = bull[0]
    assert e.entstehung_idx == 1 and e.bestaetigung_idx == 2 and e.verfuegbar_idx == 2
    assert e.merkmale["fvg_bottom"] == pytest.approx(101.0)  # high[0] = 100 + 1
    assert e.merkmale["fvg_top"] == pytest.approx(119.0)     # low[2]  = 120 - 1


def test_zu_kleines_gap_faellt_raus():
    # high[0]=100,05, low[2]=100,27 -> Luecke 0,22 Punkte < 1 Tick (0,25).
    preise = [100.0, 100.1, 100.32, 100.4, 100.5]
    df = _kurs(preise, spannen=[0.05] * 5)
    ev = fvg_serie(df, tick_size=0.25, min_gap_ticks=1.0)
    assert not [e for e in ev if e.direction == 1]


def test_serie_gleicht_dem_punktuellen_erkenner(config):
    """Dieselbe Gap-Menge, und innerhalb des Fensters dasselbe
    Mitigation-Urteil."""
    rng = np.random.default_rng(20260831)
    n = 3000
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 8.0, n))
    spannen = np.abs(rng.normal(3.0, 1.2, n)) + 0.3
    df = compute_indicators(
        _kurs(list(preise), list(spannen)), config.indicators, config.market.session
    )

    fenster = 240
    serie = fvg_serie(df, tick_size=0.25, mitigation_fenster=fenster)
    punktuell = detect_fair_value_gaps(df, tick_size=0.25)

    # gleiche Gap-Menge (art, Bestaetigungsindex, Grenzen)
    serie_key = sorted(
        (e.direction, e.bestaetigung_idx,
         round(e.merkmale["fvg_top"], 4), round(e.merkmale["fvg_bottom"], 4))
        for e in serie
    )
    punkt_key = sorted(
        (1 if g.kind == "bullish" else -1, g.bar_index,
         round(g.top, 4), round(g.bottom, 4))
        for g in punktuell
    )
    assert serie_key == punkt_key
    assert len(serie) >= 20

    # Mitigation innerhalb des Fensters: beide muessen sich einig sein.
    punkt_nach_index = {g.bar_index: g for g in punktuell}
    for e in serie:
        g = punkt_nach_index[e.bestaetigung_idx]
        punkt_mit_im_fenster = False
        if g.is_mitigated and g.mitigation_time is not None:
            j = df.index.get_loc(pd.Timestamp(g.mitigation_time))
            punkt_mit_im_fenster = (j - g.bar_index) <= fenster
        assert e.merkmale["mitigiert"] == punkt_mit_im_fenster, (
            f"Gap @ {e.bestaetigung_idx}: Serie sagt "
            f"mitigiert={e.merkmale['mitigiert']}, punktuell (im Fenster) "
            f"{punkt_mit_im_fenster}"
        )


def test_kein_lookahead(config):
    rng = np.random.default_rng(7)
    n = 4000
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 7.0, n))
    spannen = np.abs(rng.normal(3.0, 1.0, n)) + 0.3
    df = compute_indicators(
        _kurs(list(preise), list(spannen)), config.indicators, config.market.session
    )

    schnitt = 2500
    voll = fvg_serie(df, mitigation_fenster=60)
    kurz = fvg_serie(df.iloc[:schnitt], mitigation_fenster=60)

    # Ein Gap, dessen Mitigationsfenster ganz vor dem Schnitt liegt, muss in
    # beiden Laeufen identisch sein - Merkmale eingeschlossen.
    def fruehe(ev):
        return [
            (e.direction, e.bestaetigung_idx, e.merkmale["mitigiert"],
             e.merkmale["kerzen_bis_mitigation"], round(e.merkmale["fuellgrad"], 3))
            for e in ev if e.verfuegbar_idx + 60 < schnitt
        ]

    assert fruehe(voll) == fruehe(kurz)


def test_spalten_haben_richtige_form(config):
    df = compute_indicators(
        _kurs([100.0, 101.0, 120.0, 121.0, 119.0, 90.0, 89.0]),
        config.indicators, config.market.session,
    )
    spalten = fvg_spalten(df)
    assert len(spalten) == len(df)
    assert list(spalten.columns) == [
        "fvg_bull", "fvg_bull_top", "fvg_bull_bottom",
        "fvg_bear", "fvg_bear_top", "fvg_bear_bottom",
    ]
    assert bool(spalten["fvg_bull"].any())


def test_ohne_atr_bricht_es_ab_bei_atr_filter():
    df = _kurs([100.0, 101.0, 120.0, 121.0])
    with pytest.raises(ValueError, match="atr"):
        fvg_serie(df, min_gap_atr=0.5)
