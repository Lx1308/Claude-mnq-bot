"""Equal Highs / Equal Lows als Serie.

Der Liquiditaetspool: zwei oder mehr Swings auf praktisch demselben Preis.
Die Tests sichern die Toleranzregel, das Hochzaehlen und die Abgrenzung zum
Doppeltop ab.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.eqhl import eqhl_ereignisse, eqhl_spalten
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


def _kurs(preise: list[float], config) -> pd.DataFrame:
    n = len(preise)
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise,
            "high": [p + 1.0 for p in preise],
            "low": [p - 1.0 for p in preise],
            "close": preise,
            "volume": [500.0] * n,
        },
        index=index,
    )
    return compute_indicators(df, config.indicators, config.market.session)


def _welle(basis: float, spitze: float, laenge: int = 14) -> list[float]:
    """Eine Auf-Ab-Welle mit klarem Hoch in der Mitte."""
    halb = laenge // 2
    return (
        list(np.linspace(basis, spitze, halb))
        + list(np.linspace(spitze - 1, basis, laenge - halb))
    )


def test_zwei_gleiche_hochs_werden_erkannt(config):
    preise = [100.0] * 20
    preise += _welle(100.0, 140.0)
    preise += _welle(100.0, 140.2)     # zweites Hoch, 0,2 Punkte daneben
    preise += [100.0] * 20

    ereignisse = eqhl_ereignisse(_kurs(preise, config))
    eqh = [e for e in ereignisse if e.pattern_type == "equal_highs"]
    assert eqh, "zwei praktisch gleiche Hochs wurden nicht erkannt"
    assert eqh[0].merkmale["anzahl_swings"] == 2
    assert eqh[0].direction == -1, "Liquiditaet oben -> Abholung nach oben"
    assert eqh[0].merkmale["streuung_punkte"] < 1.0


def test_der_dritte_gleiche_swing_zaehlt_hoch(config):
    """Der dritte gleiche Hochpunkt ist ein anderer Zustand als der zweite -
    wer nur den Cluster am Ende meldet, kann das nicht auseinanderhalten."""
    preise = [100.0] * 20
    for spitze in (140.0, 140.2, 139.9):
        preise += _welle(100.0, spitze)
    preise += [100.0] * 20

    eqh = [
        e for e in eqhl_ereignisse(_kurs(preise, config))
        if e.pattern_type == "equal_highs"
    ]
    anzahlen = [e.merkmale["anzahl_swings"] for e in eqh]
    assert 2 in anzahlen and 3 in anzahlen, f"Zaehlung falsch: {anzahlen}"
    assert [e.pattern_variant for e in eqh][:2] == ["n2", "n3"]


def test_zu_weit_auseinander_ist_kein_paar(config):
    """Hochs mit deutlichem Abstand sind kein Pool - sonst waere jeder
    Doppelgipfel einer."""
    preise = [100.0] * 20
    preise += _welle(100.0, 140.0)
    preise += _welle(100.0, 175.0)     # 35 Punkte hoeher
    preise += [100.0] * 20

    eqh = [
        e for e in eqhl_ereignisse(_kurs(preise, config))
        if e.pattern_type == "equal_highs"
    ]
    assert not eqh, f"zu weit entfernte Hochs als gleich gewertet: {eqh}"


def test_gleiche_tiefs_werden_als_eql_erkannt(config):
    preise = [200.0] * 20
    for tief in (160.0, 160.2):
        halb = 7
        preise += list(np.linspace(200.0, tief, halb))
        preise += list(np.linspace(tief + 1, 200.0, halb))
    preise += [200.0] * 20

    eql = [
        e for e in eqhl_ereignisse(_kurs(preise, config))
        if e.pattern_type == "equal_lows"
    ]
    assert eql, "gleiche Tiefs nicht erkannt"
    assert eql[0].direction == 1


def test_phasenordnung(config):
    rng = np.random.default_rng(4)
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, 3000)))
    ereignisse = eqhl_ereignisse(_kurs(preise, config))
    assert ereignisse
    for e in ereignisse:
        assert e.entstehung_idx <= e.bestaetigung_idx == e.verfuegbar_idx
        # Der erste Swing des Clusters liegt vor dem juengsten.
        assert e.merkmale["spanne_bars"] >= 0


def test_kein_lookahead(config):
    rng = np.random.default_rng(23)
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, 4000)))
    df = _kurs(preise, config)

    schnitt = 2500
    voll = eqhl_ereignisse(df)
    kurz = eqhl_ereignisse(df.iloc[:schnitt])

    def frueh(ev):
        return [
            (e.pattern_type, e.pattern_variant, e.entstehung_idx,
             e.verfuegbar_idx, e.merkmale["level_neckline"])
            for e in ev if e.verfuegbar_idx < schnitt
        ]

    assert frueh(voll) == frueh(kurz)


def test_cluster_verfaellt_nach_dem_lookback(config):
    """Zwei gleiche Hochs zwei Handelstage auseinander sind kein Pool."""
    preise = [100.0] * 20
    preise += _welle(100.0, 140.0)
    preise += [100.0] * 300              # lange Pause, weit ueber lookback=120
    preise += _welle(100.0, 140.1)
    preise += [100.0] * 20

    eqh = [
        e for e in eqhl_ereignisse(_kurs(preise, config), lookback=120)
        if e.pattern_type == "equal_highs"
    ]
    assert not eqh, "Cluster ueberdauerte das Lookback-Fenster"


def test_spalten_schreiben_das_niveau_fort(config):
    preise = [100.0] * 20
    preise += _welle(100.0, 140.0)
    preise += _welle(100.0, 140.2)
    preise += [100.0] * 40

    spalten = eqhl_spalten(_kurs(preise, config))
    assert len(spalten) == len(preise)
    assert list(spalten.columns) == [
        "eqh", "eqh_niveau", "eqh_anzahl", "eql", "eql_niveau", "eql_anzahl",
    ]
    treffer = np.nonzero(spalten["eqh"].to_numpy())[0]
    assert len(treffer)
    i = int(treffer[0])
    # Vor dem ersten Pool ist nichts bekannt, danach steht das Niveau.
    assert np.isnan(spalten["eqh_niveau"].iloc[i - 1])
    assert spalten["eqh_niveau"].iloc[i:].notna().all()


def test_ohne_atr_bricht_es_ab():
    df = pd.DataFrame(
        {"open": [1.0, 2, 3], "high": [1.0, 2, 3], "low": [1.0, 2, 3],
         "close": [1.0, 2, 3], "volume": [1.0, 1, 1]},
        index=pd.date_range("2026-01-05", periods=3, freq="1min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="atr"):
        eqhl_ereignisse(df)
