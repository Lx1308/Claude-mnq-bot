"""Der handelbare Doppelboden - vor allem: kein Lookahead.

Der wichtigste Test ist ``test_kein_lookahead_bei_abgeschnittener_reihe``.
Genau daran ist die erste Fassung gescheitert: sie nahm als Nackenlinie das
Hoch ueber das ganze Suchfenster statt das LAUFENDE Hoch bis zum Ruecklauf -
also auch Kerzen, die zum Einstiegszeitpunkt noch gar nicht existierten.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.indicators import atr as atr_indikator
from common.muster_handelbar import (
    HandelbaresMuster,
    finde_handelbare_doppelboeden,
)


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """OHLC von Hand, damit sich das Ergebnis nachrechnen laesst."""
    index = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    return pd.DataFrame(
        {
            "open": [k[0] for k in kerzen],
            "high": [k[1] for k in kerzen],
            "low": [k[2] for k in kerzen],
            "close": [k[3] for k in kerzen],
            "volume": [500.0] * len(kerzen),
        },
        index=index,
    )


def _rausch(n: int = 40_000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20_000.0 + np.cumsum(rng.normal(0, 4, n))
    s = np.abs(rng.normal(3, 1.2, n)) + 0.5
    richtung = rng.normal(0, 2, n)
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s, "close": p + richtung,
         "volume": 500.0},
        index=idx,
    ).assign(
        high=lambda d: d[["high", "open", "close"]].max(axis=1),
        low=lambda d: d[["low", "open", "close"]].min(axis=1),
    )


# -- Der Kern --------------------------------------------------------------

def test_kein_lookahead_bei_abgeschnittener_reihe():
    """Was auf der halben Reihe gefunden wird, muss auf der ganzen identisch
    herauskommen. Sonst ist Zukunftswissen im Spiel."""
    df = _rausch(40_000)
    a = atr_indikator(df, period=14).to_numpy()
    schnitt = len(df) // 2
    kurz = df.iloc[:schnitt]
    a_kurz = atr_indikator(kurz, period=14).to_numpy()

    voll = finde_handelbare_doppelboeden(df, a, strength=20)
    teil = finde_handelbare_doppelboeden(kurz, a_kurz, strength=20)

    # Nach dem ERSTEN TIEF schluesseln, nicht nach dem Einstieg: mehrere
    # Muster koennen denselben Einstiegsindex ergeben.
    voll_map = {f.erst_idx: f for f in voll}
    # Wer zu nah am Schnitt liegt, hatte in der kurzen Reihe schlicht weniger
    # Zukunft zum Suchen - das ist kein Lookahead.
    puffer = 600 + 30 + 20

    geprueft = 0
    for f in teil:
        if f.erst_idx > schnitt - puffer:
            continue
        geprueft += 1
        g = voll_map.get(f.erst_idx)
        assert g is not None, f"Fund bei {f.erst_idx} fehlt in der vollen Reihe"
        assert g.einstieg_idx == f.einstieg_idx
        assert g.tief == pytest.approx(f.tief)
        assert g.nackenlinie == pytest.approx(f.nackenlinie)
    assert geprueft > 50, "zu wenige Faelle geprueft, der Test traegt nicht"


def test_nackenlinie_ist_das_laufende_hoch_nicht_das_spaetere():
    """Ein Hoch NACH dem Ruecklauf darf die Nackenlinie nicht mehr anheben."""
    kerzen = [(100, 101, 99, 100)] * 25          # ruhiger Vorlauf
    kerzen += [(100, 100.5, 90, 91)]             # 25: das erste Tief
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]  # Anstieg
    kerzen += [(103, 104, 102, 103)] * 10        # Hoch bei 104
    kerzen += [(103, 103.5, 91, 92)]             # Ruecklauf ans Tief
    kerzen += [(92, 93, 91.5, 92.5)]             # gruene Kerze -> Einstieg
    kerzen += [(93, 130, 92, 129)]               # viel spaeteres Hoch: 130
    kerzen += [(129, 131, 128, 130)] * 20
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)

    funde = finde_handelbare_doppelboeden(
        df, a, strength=5, n_gruen=1, min_hoehe_atr=2.0)
    assert funde, "das Muster sollte gefunden werden"
    f = funde[0]
    assert f.nackenlinie < 110, (
        f"Nackenlinie {f.nackenlinie} enthaelt das spaetere Hoch von 130 - "
        "das ist Lookahead"
    )


def test_gebrochenes_tief_ergibt_kein_muster():
    kerzen = [(100, 101, 99, 100)] * 25
    kerzen += [(100, 100.5, 90, 91)]
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]
    kerzen += [(103, 104, 102, 103)] * 10
    kerzen += [(103, 103.5, 80, 81)]             # weit unter das Tief
    kerzen += [(81, 82, 80.5, 81.5)] * 25        # danach flach, kein neues Muster
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)
    funde = finde_handelbare_doppelboeden(df, a, strength=5, n_gruen=1)
    # Entscheidend ist, dass das TIEF BEI 90 nicht mehr als untere Linie
    # taugt - es wurde gerissen. Andere Muster weiter hinten in der Reihe
    # waeren erlaubt, nur dieses eine nicht.
    assert not [f for f in funde if abs(f.tief - 90.0) < 1e-9], (
        "das gerissene Tief darf keine untere Linie mehr sein"
    )


def test_flaches_muster_wird_verworfen():
    """Unter der Mindesthoehe in ATR ist es kein Muster, sondern Rauschen."""
    df = _rausch(20_000, seed=3)
    a = atr_indikator(df, period=14).to_numpy()
    viele = finde_handelbare_doppelboeden(df, a, strength=20, min_hoehe_atr=0.5)
    wenige = finde_handelbare_doppelboeden(df, a, strength=20, min_hoehe_atr=6.0)
    assert len(wenige) < len(viele)


# -- Die Geometrie des Musters --------------------------------------------

def test_stop_muss_unter_dem_tief_liegen():
    m = HandelbaresMuster(erst_idx=0, hoch_idx=5, zweit_idx=10,
                          einstieg_idx=11, tief=100.0, zweites_tief=100.5,
                          nackenlinie=170.0, atr=5.0, gruen=1)
    assert m.hoehe == pytest.approx(70.0)
    # Laurins Beispiel: 15 Punkte unter dem Tief sind 21 % der Hoehe.
    assert m.stop(15.0 / 70.0) == pytest.approx(85.0)
    with pytest.raises(ValueError, match="unter das Tief"):
        m.stop(0.0)
    with pytest.raises(ValueError, match="unter das Tief"):
        m.stop(-0.1)


def test_ziel_davor_und_als_messziel():
    m = HandelbaresMuster(erst_idx=0, hoch_idx=5, zweit_idx=10,
                          einstieg_idx=11, tief=100.0, zweites_tief=100.5,
                          nackenlinie=170.0, atr=5.0, gruen=1)
    # 10 Punkte VOR der Nackenlinie = 14 % der Hoehe.
    assert m.ziel(10.0 / 70.0) == pytest.approx(160.0)
    # Klassisches Messziel: eine Musterhoehe ueber die Nackenlinie hinaus.
    assert m.ziel(-1.0) == pytest.approx(240.0)


def test_dauer_ist_der_abstand_der_beiden_tiefs():
    m = HandelbaresMuster(erst_idx=100, hoch_idx=150, zweit_idx=205,
                          einstieg_idx=207, tief=1.0, zweites_tief=1.0,
                          nackenlinie=2.0, atr=0.1, gruen=1)
    assert m.dauer_bars == 105


# -- Randfaelle ------------------------------------------------------------

def test_mehr_gruene_kerzen_liefern_weniger_muster():
    df = _rausch(30_000, seed=7)
    a = atr_indikator(df, period=14).to_numpy()
    eins = finde_handelbare_doppelboeden(df, a, strength=20, n_gruen=1)
    drei = finde_handelbare_doppelboeden(df, a, strength=20, n_gruen=3)
    assert len(drei) < len(eins), (
        "wer laenger auf Bestaetigung wartet, verpasst Muster"
    )


def test_hoehere_staerke_liefert_groessere_muster():
    df = _rausch(40_000, seed=5)
    a = atr_indikator(df, period=14).to_numpy()
    klein = finde_handelbare_doppelboeden(df, a, strength=10)
    gross = finde_handelbare_doppelboeden(df, a, strength=40)
    assert len(gross) < len(klein)
    assert (np.median([f.hoehe for f in gross])
            > np.median([f.hoehe for f in klein]))


def test_atr_laenge_wird_geprueft():
    df = _rausch(2_000)
    with pytest.raises(ValueError, match="atr hat"):
        finde_handelbare_doppelboeden(df, np.ones(10))


def test_ungueltige_staerke_bricht_ab():
    df = _rausch(2_000)
    with pytest.raises(ValueError, match="strength"):
        finde_handelbare_doppelboeden(df, np.ones(len(df)), strength=0)
