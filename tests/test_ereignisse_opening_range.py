"""Opening Range je Handelstag - Lookahead ist hier die ganze Frage.

Eine Kerze um 09:38 darf das 15-Minuten-Hoch nicht kennen, das erst um 09:45
feststeht. Wuerde man den Tageswert auf alle Kerzen verteilen, waere jede
darauf gebaute Auswertung wertlos - und nichts an den Kursen verriete es.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.opening_range import (
    OR_FENSTER,
    opening_range_spalten,
    or_spaltennamen,
)
from common.instruments import get_instrument


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


@pytest.fixture(scope="module")
def instrument(config):
    return get_instrument(config.market.product)


def _tag(preise: list[float], start: str = "2026-08-03 13:30") -> pd.DataFrame:
    """Minutenkerzen ab RTH-Eroeffnung (09:30 ET = 13:30 UTC im Sommer)."""
    n = len(preise)
    index = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {
            "open": preise,
            "high": [p + 1.0 for p in preise],
            "low": [p - 1.0 for p in preise],
            "close": preise,
            "volume": [500.0] * n,
        },
        index=index,
    )


def test_spaltensatz_ist_vollstaendig(config, instrument):
    df = _tag([100.0] * 120)
    spalten = opening_range_spalten(df, instrument, config.market.session)
    assert list(spalten.columns) == list(or_spaltennamen())
    assert len(spalten) == len(df)


def test_or_bleibt_nan_solange_das_fenster_laeuft(config, instrument):
    """Der eigentliche Lookahead-Schutz."""
    # 60 Minuten, das Hoch faellt spaet in die 15-Minuten-Phase.
    preise = [100.0] * 60
    preise[12] = 130.0          # Minute 12: hoechster Punkt der OR15
    df = _tag(preise)
    spalten = opening_range_spalten(df, instrument, config.market.session)

    h15 = spalten["or15_high"]
    # Minuten 0..14 liegen IM Fenster - dort darf nichts stehen.
    assert h15.iloc[:15].isna().all(), "OR15 war vor Fensterende bekannt"
    # Ab Minute 15 steht sie.
    assert h15.iloc[15:].notna().all()
    assert h15.iloc[15] == pytest.approx(131.0)   # 130 + 1 (high)


def test_kuerzeres_fenster_ist_frueher_da(config, instrument):
    df = _tag([100.0] * 60)
    spalten = opening_range_spalten(df, instrument, config.market.session)
    assert spalten["or5_high"].iloc[:5].isna().all()
    assert spalten["or5_high"].iloc[5:].notna().all()
    assert spalten["or30_high"].iloc[:30].isna().all()
    assert spalten["or30_high"].iloc[30:].notna().all()


def test_or5_ist_enger_oder_gleich_or30(config, instrument):
    """Ein laengeres Fenster kann die Range nur weiten, nie verengen."""
    rng = np.random.default_rng(11)
    preise = list(100.0 + np.cumsum(rng.normal(0, 1.5, 90)))
    df = _tag(preise)
    spalten = opening_range_spalten(df, instrument, config.market.session)

    ab = 30  # ab hier stehen alle drei
    assert (spalten["or5_high"].iloc[ab:] <= spalten["or30_high"].iloc[ab:] + 1e-9).all()
    assert (spalten["or5_low"].iloc[ab:] >= spalten["or30_low"].iloc[ab:] - 1e-9).all()


def test_ausserhalb_rth_bleibt_leer(config, instrument):
    """Nachts gibt es keine Opening Range."""
    df = _tag([100.0] * 60, start="2026-08-04 02:00")  # 22:00 ET am Vortag
    spalten = opening_range_spalten(df, instrument, config.market.session)
    assert spalten["or15_high"].isna().all()


def test_kein_lookahead_beim_abschneiden(config, instrument):
    """Reihe abschneiden, neu rechnen - was frueher feststand, bleibt."""
    rng = np.random.default_rng(19)
    preise = list(100.0 + np.cumsum(rng.normal(0, 1.5, 240)))
    df = _tag(preise)

    schnitt = 100
    voll = opening_range_spalten(df, instrument, config.market.session)
    kurz = opening_range_spalten(
        df.iloc[:schnitt], instrument, config.market.session
    )
    for spalte in or_spaltennamen():
        pd.testing.assert_series_equal(
            voll[spalte].iloc[:schnitt], kurz[spalte], check_names=False
        )


def test_leerer_rahmen(config, instrument):
    df = _tag([]).iloc[0:0]
    spalten = opening_range_spalten(df, instrument, config.market.session)
    assert list(spalten.columns) == list(or_spaltennamen())
    assert spalten.empty


def test_prepare_haengt_die_or_spalten_an(config):
    """Die Erkenner finden die OR nur, wenn prepare sie liefert."""
    from backtest.engine import Backtester

    rng = np.random.default_rng(2)
    preise = list(20000.0 + np.cumsum(rng.normal(0, 5, 600)))
    df = _tag(preise)
    bt = Backtester(config.market, config.indicators)
    vorbereitet = bt.prepare(df)
    for spalte in or_spaltennamen():
        assert spalte in vorbereitet.columns


def test_or_ist_eine_niveauquelle_der_erkenner():
    """Kein eigener Erkenner: Test/Ausbruch/Sweep an der OR kommen aus
    niveaus.py und sweeps.py."""
    from common.ereignisse.niveaus import NIVEAU_QUELLEN

    namen = {spalte for spalte, _ in NIVEAU_QUELLEN}
    for minuten in OR_FENSTER:
        assert f"or{minuten}_high" in namen
        assert f"or{minuten}_low" in namen
