"""Order Block als Serie - die letzte Gegenkerze vor dem Impuls.

Der wichtigste Test ist der Lookahead-Test: die OB-Kerze ist zu ihrer eigenen
Zeit eine gewoehnliche Gegenkerze. Erst das Displacement danach macht sie zum
Order Block.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.orderblocks import (
    orderblock_ereignisse,
    orderblock_spalten,
)
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _rahmen(kerzen: list[tuple[float, float, float, float, float]], config):
    """Kerzen als (open, high, low, close, volume)."""
    n = len(kerzen)
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [k[0] for k in kerzen],
            "high": [k[1] for k in kerzen],
            "low": [k[2] for k in kerzen],
            "close": [k[3] for k in kerzen],
            "volume": [k[4] for k in kerzen],
        },
        index=index,
    )
    return compute_indicators(df, config.indicators, config.market.session)


def _ruhig(n: int, preis: float = 100.0):
    """Ruhige Kerzen mit abwechselnder Richtung und normalem Volumen."""
    aus = []
    for i in range(n):
        o = preis + (0.1 if i % 2 else -0.1)
        c = preis - (0.1 if i % 2 else -0.1)
        aus.append((o, preis + 0.6, preis - 0.6, c, 500.0))
    return aus


def test_bullischer_orderblock_ist_die_letzte_baerische_kerze(config):
    kerzen = _ruhig(60)
    # Eine klare Gegenkerze (baerisch), dann ein bullischer Impuls.
    ob = (101.0, 101.2, 99.0, 99.2, 600.0)     # close < open
    impuls = (99.3, 112.0, 99.2, 111.5, 4000.0)
    kerzen += [ob, impuls]
    kerzen += _ruhig(10, 111.0)

    ereignisse = orderblock_ereignisse(_rahmen(kerzen, config))
    bull = [e for e in ereignisse if e.direction == 1]
    assert bull, "kein bullischer Order Block erkannt"
    e = bull[0]
    ob_idx = len(kerzen) - 12
    assert e.entstehung_idx == ob_idx
    assert e.bestaetigung_idx == ob_idx + 1 == e.verfuegbar_idx
    assert e.merkmale["ob_zone_oben"] == pytest.approx(101.2)
    assert e.merkmale["ob_zone_unten"] == pytest.approx(99.0)
    # Beim Long ist die Unterkante die Kante, an der ein Ruecklauf ansetzt.
    assert e.merkmale["level_neckline"] == pytest.approx(99.0)
    assert e.merkmale["abstand_zum_impuls_bars"] == 1


def test_ohne_gegenkerze_kein_orderblock(config):
    """Ein Impuls aus lauter gleichgerichteten Kerzen hat keinen Order Block -
    ihn trotzdem irgendwo zu verankern waere geraten."""
    kerzen = _ruhig(60)
    # Zehn bullische Kerzen in Folge, dann der Impuls: keine baerische Kerze
    # im Suchfenster.
    p = 100.0
    for _ in range(12):
        kerzen.append((p, p + 0.7, p - 0.2, p + 0.5, 500.0))
        p += 0.5
    kerzen.append((p, p + 13.0, p - 0.1, p + 12.5, 4000.0))
    kerzen += _ruhig(10, p + 12.0)

    bull = [e for e in orderblock_ereignisse(_rahmen(kerzen, config))
            if e.direction == 1]
    assert not bull, f"Order Block ohne Gegenkerze erfunden: {bull}"


def test_baerischer_orderblock_ist_die_letzte_bullische_kerze(config):
    kerzen = _ruhig(60)
    ob = (99.0, 101.2, 98.8, 101.0, 600.0)     # close > open
    impuls = (100.9, 101.0, 88.0, 88.5, 4000.0)
    kerzen += [ob, impuls]
    kerzen += _ruhig(10, 89.0)

    bear = [e for e in orderblock_ereignisse(_rahmen(kerzen, config))
            if e.direction == -1]
    assert bear, "kein baerischer Order Block erkannt"
    e = bear[0]
    # Beim Short ist die Oberkante die Kante.
    assert e.merkmale["level_neckline"] == pytest.approx(101.2)


def test_phasenordnung_ob_liegt_vor_dem_impuls(config):
    rng = np.random.default_rng(9)
    n = 3000
    basis = 20000.0 + np.cumsum(rng.normal(0, 8, n))
    schluss = basis + rng.normal(0, 3, n)
    stoss = rng.choice(np.arange(50, n), size=n // 70, replace=False)
    schluss[stoss] = basis[stoss] + rng.choice([-1, 1], size=stoss.size) * 50.0
    vol = rng.integers(200, 1500, n).astype(float)
    vol[stoss] *= 4
    kerzen = [
        (float(basis[i]), float(max(basis[i], schluss[i]) + 3),
         float(min(basis[i], schluss[i]) - 3), float(schluss[i]), float(vol[i]))
        for i in range(n)
    ]

    ereignisse = orderblock_ereignisse(_rahmen(kerzen, config))
    assert ereignisse
    for e in ereignisse:
        assert e.entstehung_idx < e.bestaetigung_idx == e.verfuegbar_idx
        assert e.merkmale["abstand_zum_impuls_bars"] >= 1


def test_kein_lookahead(config):
    """Die OB-Kerze ist zu ihrer eigenen Zeit eine gewoehnliche Gegenkerze."""
    rng = np.random.default_rng(31)
    n = 4000
    basis = 20000.0 + np.cumsum(rng.normal(0, 8, n))
    schluss = basis + rng.normal(0, 3, n)
    stoss = rng.choice(np.arange(50, n), size=n // 70, replace=False)
    schluss[stoss] = basis[stoss] + rng.choice([-1, 1], size=stoss.size) * 50.0
    vol = rng.integers(200, 1500, n).astype(float)
    vol[stoss] *= 4
    kerzen = [
        (float(basis[i]), float(max(basis[i], schluss[i]) + 3),
         float(min(basis[i], schluss[i]) - 3), float(schluss[i]), float(vol[i]))
        for i in range(n)
    ]
    df = _rahmen(kerzen, config)

    schnitt = 2500
    voll = orderblock_ereignisse(df)
    kurz = orderblock_ereignisse(df.iloc[:schnitt])

    def frueh(ev):
        return [
            (e.direction, e.entstehung_idx, e.verfuegbar_idx,
             e.merkmale["ob_zone_oben"], e.merkmale["ob_zone_unten"])
            for e in ev if e.verfuegbar_idx < schnitt
        ]

    assert frueh(voll) == frueh(kurz)


def test_spalten_form(config):
    kerzen = _ruhig(60)
    kerzen += [(101.0, 101.2, 99.0, 99.2, 600.0),
               (99.3, 112.0, 99.2, 111.5, 4000.0)]
    kerzen += _ruhig(20, 111.0)

    spalten = orderblock_spalten(_rahmen(kerzen, config))
    assert len(spalten) == len(kerzen)
    assert list(spalten.columns) == [
        "ob_bull", "ob_bull_oben", "ob_bull_unten",
        "ob_bear", "ob_bear_oben", "ob_bear_unten",
    ]
    treffer = np.nonzero(spalten["ob_bull"].to_numpy())[0]
    assert len(treffer)
    i = int(treffer[0])
    # Zone wird fortgeschrieben, aber nicht rueckwirkend gesetzt.
    assert np.isnan(spalten["ob_bull_oben"].iloc[i - 1])
    assert spalten["ob_bull_oben"].iloc[i:].notna().all()


def test_ohne_atr_bricht_es_ab():
    df = pd.DataFrame(
        {"open": [1.0, 2, 3], "high": [1.0, 2, 3], "low": [1.0, 2, 3],
         "close": [1.0, 2, 3], "volume": [1.0, 1, 1]},
        index=pd.date_range("2026-01-05", periods=3, freq="1min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="atr"):
        orderblock_ereignisse(df)
