"""Liquidity Sweep als Serie - Definition, Abgrenzung, kein Lookahead.

Laurins Kerninteresse: der Stop-Run, der sofort zurueckdreht. Die Tests
sichern vor allem die **Abgrenzung** ab: ein Durchstich ohne Reclaim ist kein
Sweep, und ein Sweep ist nicht dasselbe wie ein Fehlausbruch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.config import Config
from common.ereignisse.sweeps import (
    MAX_RECLAIM_BARS,
    sweep_ereignisse,
    sweep_spalten,
)
from common.indicators import compute_indicators


@pytest.fixture(scope="module")
def config():
    from pathlib import Path

    return Config.load(Path(__file__).resolve().parents[1] / "config.yaml")


SESSION = 1440


def _rahmen(preise, config, *, dochte=None, volumen=None) -> pd.DataFrame:
    """OHLCV mit steuerbaren Dochten - fuer einen Sweep ist genau der Docht
    das Muster."""
    n = len(preise)
    dochte = dochte if dochte is not None else [(0.0, 0.0)] * n
    volumen = volumen if volumen is not None else [500.0] * n
    index = pd.date_range("2026-01-05 23:00", periods=n, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise,
            "high": [p + max(0.5, d[0]) for p, d in zip(preise, dochte)],
            "low": [p - max(0.5, d[1]) for p, d in zip(preise, dochte)],
            "close": preise,
            "volume": volumen,
        },
        index=index,
    )
    return compute_indicators(df, config.indicators, config.market.session)


def _vortag(hoch: float, tief: float) -> list[float]:
    mitte = (hoch + tief) / 2
    v = SESSION // 4
    return (
        list(np.linspace(mitte, hoch, v))
        + list(np.linspace(hoch, tief, v))
        + list(np.linspace(tief, hoch, v))
        + list(np.linspace(hoch, mitte, SESSION - 3 * v))
    )


def test_sweep_unter_das_vortagestief_mit_sofortigem_reclaim(config):
    """Der Lehrbuchfall: Docht durch die Marke, Schluss zurueck darueber."""
    tief = 19950.0
    tag2 = list(np.linspace(20000, tief + 6, 60))       # Anlauf von oben
    sweep_i = len(tag2)
    tag2 += [tief + 5.0]                                 # Sweep-Kerze
    tag2 += list(np.linspace(tief + 8, tief + 60, 60))   # Erholung

    dochte = [(0.0, 0.0)] * len(tag2)
    dochte[sweep_i] = (0.0, 30.0)   # Docht 30 Punkte nach unten, weit unter PDL
    volumen = [500.0] * len(tag2)
    volumen[sweep_i] = 4000.0        # dicker Umsatz auf der Sweep-Kerze

    vor = _vortag(20050.0, tief)
    df = _rahmen(
        vor + tag2, config,
        dochte=[(0.0, 0.0)] * len(vor) + dochte,
        volumen=[500.0] * len(vor) + volumen,
    )

    ereignisse = sweep_ereignisse(df)
    pdl = [e for e in ereignisse if e.pattern_variant == "pdl"]
    assert pdl, "kein Sweep des Vortagestiefs erkannt"
    e = pdl[0]
    assert e.direction == 1, "Sell-Side-Sweep wird bullisch gedeutet"
    assert e.merkmale["kerzen_bis_reclaim"] == 1, "Reclaim in derselben Kerze"
    assert e.merkmale["sweep_tiefe_punkte"] > 0
    # Der Orderbuch-Ersatz muss den dicken Umsatz sehen.
    assert e.merkmale["volumen_am_extremum_relativ"] > 3.0


def test_durchstich_ohne_reclaim_ist_kein_sweep(config):
    """Ohne Rueckkehr ist es ein Ausbruch - und gehoert nach niveaus.py,
    nicht hierher. Sonst zaehlte jeder Ausbruch doppelt."""
    tief = 19950.0
    tag2 = list(np.linspace(20000, tief + 5, 60))
    tag2 += list(np.linspace(tief - 5, tief - 120, 60))  # bricht durch, bleibt

    df = _rahmen(_vortag(20050.0, tief) + tag2, config)
    ereignisse = sweep_ereignisse(df)
    pdl = [e for e in ereignisse if e.pattern_variant == "pdl"]
    assert not pdl, f"Ausbruch faelschlich als Sweep gezaehlt: {pdl}"


def test_reclaim_zu_spaet_zaehlt_nicht(config):
    """Was laenger als max_reclaim_bars braucht, ist keine Stop-Abholung
    mehr, sondern eine normale Bewegung."""
    tief = 19950.0
    anlauf = list(np.linspace(20000, tief + 5, 60))
    # Deutlich mehr Kerzen unterhalb als das Reclaim-Fenster erlaubt.
    unten = [tief - 10.0] * (MAX_RECLAIM_BARS + 8)
    zurueck = list(np.linspace(tief + 2, tief + 50, 40))
    df = _rahmen(_vortag(20050.0, tief) + anlauf + unten + zurueck, config)

    pdl = [e for e in sweep_ereignisse(df) if e.pattern_variant == "pdl"]
    assert not pdl, "Reclaim ausserhalb des Fensters wurde gezaehlt"


def test_zu_flacher_durchstich_faellt_raus(config):
    """Ein Tick jenseits der Marke ist Rauschen, kein Sweep."""
    tief = 19950.0
    tag2 = list(np.linspace(20000, tief + 6, 60))
    sweep_i = len(tag2)
    tag2 += [tief + 5.0]
    tag2 += list(np.linspace(tief + 8, tief + 40, 40))
    dochte = [(0.0, 0.0)] * len(tag2)
    dochte[sweep_i] = (0.0, 5.2)   # gerade eben unter die Marke

    vor = _vortag(20050.0, tief)
    df = _rahmen(
        vor + tag2, config, dochte=[(0.0, 0.0)] * len(vor) + dochte
    )
    # Mit hoher Mindesttiefe darf nichts uebrigbleiben.
    streng = [
        e for e in sweep_ereignisse(df, min_tiefe_atr=2.0)
        if e.pattern_variant == "pdl"
    ]
    assert not streng


def test_phasenordnung_sweep_vor_reclaim(config):
    rng = np.random.default_rng(3)
    n = 3000
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, n)))
    spannen = [(float(abs(x)), float(abs(y))) for x, y in
               zip(rng.normal(3, 1, n), rng.normal(3, 1, n))]
    df = _rahmen(preise, config, dochte=spannen)

    ereignisse = sweep_ereignisse(df)
    assert ereignisse, "auf einer Zufallsreihe muss es Sweeps geben"
    for e in ereignisse:
        assert e.entstehung_idx <= e.bestaetigung_idx == e.verfuegbar_idx
        assert e.verfuegbar_idx - e.entstehung_idx <= MAX_RECLAIM_BARS


def test_kein_lookahead(config):
    rng = np.random.default_rng(17)
    n = 4000
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, n)))
    spannen = [(float(abs(x)), float(abs(y))) for x, y in
               zip(rng.normal(3, 1, n), rng.normal(3, 1, n))]
    df = _rahmen(preise, config, dochte=spannen)

    schnitt = 2500
    voll = sweep_ereignisse(df)
    kurz = sweep_ereignisse(df.iloc[:schnitt])

    def frueh(ev):
        return [
            (e.pattern_variant, e.direction, e.entstehung_idx, e.verfuegbar_idx,
             e.merkmale["sweep_tiefe_atr"])
            for e in ev if e.verfuegbar_idx < schnitt
        ]

    assert frueh(voll) == frueh(kurz)


def test_relatives_volumen_ist_rueckwaertsgerichtet(config):
    """Der Bezugsmedian darf nur aus der Vergangenheit stammen - sonst wuesste
    die Sweep-Kerze, wie ruhig es danach wird."""
    from common.ereignisse.sweeps import _relatives_volumen

    vol = np.concatenate([np.full(200, 500.0), np.full(200, 5000.0)])
    rel = _relatives_volumen(vol, 60)
    # Direkt beim Sprung ist der Median noch der alte -> hohes Verhaeltnis.
    assert rel[200] > 5.0
    # Weit nach dem Sprung hat sich der Median angepasst -> wieder ~1.
    assert rel[-1] == pytest.approx(1.0, abs=0.2)
    # Vor dem Sprung darf nichts vom Sprung zu sehen sein.
    assert rel[199] == pytest.approx(1.0, abs=0.2)


def test_spalten_form(config):
    rng = np.random.default_rng(5)
    n = 2000
    preise = list(20000.0 + np.cumsum(rng.normal(0, 6, n)))
    spannen = [(float(abs(x)), float(abs(y))) for x, y in
               zip(rng.normal(3, 1, n), rng.normal(3, 1, n))]
    df = _rahmen(preise, config, dochte=spannen)

    spalten = sweep_spalten(df)
    assert len(spalten) == len(df)
    assert list(spalten.columns) == [
        "sweep_bull", "sweep_bear", "sweep_niveau", "sweep_tiefe_atr",
        "sweep_rel_volumen",
    ]
    # Nie beides auf derselben Kerze.
    assert not (spalten["sweep_bull"] & spalten["sweep_bear"]).any()
    # Wo eine Flanke steht, steht auch das Niveau.
    flanke = spalten["sweep_bull"] | spalten["sweep_bear"]
    assert spalten.loc[flanke, "sweep_niveau"].notna().all()


def test_ohne_atr_bricht_es_ab(config):
    df = pd.DataFrame(
        {"open": [1.0, 2, 3], "high": [1.0, 2, 3], "low": [1.0, 2, 3],
         "close": [1.0, 2, 3], "volume": [1.0, 1, 1]},
        index=pd.date_range("2026-01-05", periods=3, freq="1min", tz="UTC"),
    )
    with pytest.raises(ValueError, match="atr"):
        sweep_ereignisse(df)
