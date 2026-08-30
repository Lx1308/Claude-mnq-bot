"""Displacement als Ereignis-Serie - Adapter auf detect_displacements.

Keine eigene Definition, deshalb kein Gleichheitstest gegen eine zweite
Rechnung noetig - wohl aber: der Adapter verliert nichts, die Phasen stimmen,
und kein Lookahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.displacement import displacement_serie, displacement_spalten
from common.indicators import compute_indicators
from common.market_primitives import detect_displacements


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _kurs(n: int = 3000, *, seed: int = 20260831) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 9.0, n))
    # ab und zu ein kraeftiger Impuls mit Volumen
    schluss = preise + rng.normal(0.0, 3.0, n)
    idx = rng.choice(np.arange(50, n), size=n // 60, replace=False)
    schluss[idx] = preise[idx] + rng.choice([-1, 1], size=idx.size) * 45.0
    spanne = np.abs(rng.normal(3.0, 1.0, n)) + 0.5
    vol = rng.integers(200, 1500, n).astype(float)
    vol[idx] *= 4.0
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": np.maximum(preise, schluss) + spanne,
            "low": np.minimum(preise, schluss) - spanne,
            "close": schluss,
            "volume": vol,
        },
        index=index,
    )


def test_adapter_verliert_keinen_fund(config):
    df = compute_indicators(_kurs(), config.indicators, config.market.session)
    funde = detect_displacements(df)
    ereignisse = displacement_serie(df)

    assert len(ereignisse) == len(funde)
    assert [e.verfuegbar_idx for e in ereignisse] == [d.bar_index for d in funde]
    for e, d in zip(ereignisse, funde):
        assert e.direction == (1 if d.direction == "bullish" else -1)
        assert e.merkmale["koerper_punkte"] == pytest.approx(round(d.body_points, 4))


def test_phasen_fallen_auf_die_kerze_selbst(config):
    df = compute_indicators(_kurs(), config.indicators, config.market.session)
    for e in displacement_serie(df):
        assert e.entstehung_idx == e.bestaetigung_idx == e.verfuegbar_idx


def test_kein_lookahead(config):
    df = compute_indicators(_kurs(4000), config.indicators, config.market.session)
    schnitt = 2500
    voll = displacement_serie(df)
    kurz = displacement_serie(df.iloc[:schnitt])

    def frueh(ev):
        return [
            (e.direction, e.verfuegbar_idx, e.merkmale["koerper_atr"],
             e.merkmale["relatives_volumen"])
            for e in ev if e.verfuegbar_idx < schnitt
        ]

    assert frueh(voll) == frueh(kurz)


def test_spalten_form(config):
    df = compute_indicators(_kurs(500), config.indicators, config.market.session)
    spalten = displacement_spalten(df)
    assert len(spalten) == len(df)
    assert list(spalten.columns) == [
        "displacement", "displacement_richtung",
        "displacement_koerper_atr", "displacement_rel_volumen",
    ]
    # Richtung nur dort gesetzt, wo auch die Flanke steht.
    gesetzt = spalten["displacement_richtung"] != 0
    assert (gesetzt == spalten["displacement"]).all()
