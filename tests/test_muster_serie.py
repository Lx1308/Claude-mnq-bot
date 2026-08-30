"""Chartmuster als Serie - und der Beweis, dass es dasselbe Muster ist.

Zwei Dinge werden hier abgesichert, und beide sind Invarianten dieses
Projekts:

1. **Kein Lookahead.** Ein Swing-Tief ist an seiner eigenen Kerze nicht
   erkennbar; bekannt wird es erst ``strength`` Kerzen spaeter. Wer im
   Backtest "am zweiten Tief" einsteigt, handelt mit Wissen aus der Zukunft.
2. **Keine zweite Musterdefinition.** Die Serie muss zum selben Urteil kommen
   wie ``detect_double_top_bottom`` - sonst testet der Backtest ein anderes
   Muster als das, was die Oberflaeche zeigt (Invariante 1, uebertragen auf
   Muster).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.muster_serie import (
    STANDARD_LOOKBACK,
    STANDARD_MAX_SPITZENABSTAND_ATR,
    STANDARD_MIN_TALTIEFE_ATR,
    STANDARD_STRENGTH,
    doppelmuster_spalten,
    finde_doppelmuster,
)
from common.patterns import detect_double_top_bottom


def _reihe(preise: list[float], *, atr: float = 10.0) -> tuple[pd.DataFrame, pd.Series]:
    """OHLCV aus einer Schlusskursfolge; High/Low knapp darum."""
    n = len(preise)
    index = pd.date_range("2026-01-05 14:00", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise,
            "high": [p + 0.5 for p in preise],
            "low": [p - 0.5 for p in preise],
            "close": preise,
            "volume": [100.0] * n,
        },
        index=index,
    )
    return df, pd.Series([atr] * n, index=index)


def _w_verlauf() -> tuple[pd.DataFrame, pd.Series]:
    """Ein sauberes W: Tief, Erholung, zweites Tief auf gleicher Hoehe, Anstieg.

    Die Taltiefe muss mindestens 1 x ATR betragen, der Spitzenabstand
    hoechstens 0,5 x ATR - mit ATR 10 also >= 10 Punkte Erholung und <= 5
    Punkte Unterschied zwischen den beiden Tiefs.
    """
    preise = (
        [100.0, 98.0, 96.0, 94.0]      # Abstieg
        + [90.0]                        # erstes Tief
        + [94.0, 99.0, 104.0, 106.0]    # Erholung, ~16 Punkte ueber dem Tief
        + [107.0]                       # Zwischenhoch
        + [104.0, 99.0, 94.0, 92.0]     # Rueckgang
        + [90.5]                        # zweites Tief, 0,5 Punkte daneben
        + [93.0, 97.0, 102.0, 106.0]    # Ausbruch ueber die Nackenlinie
        + [110.0, 112.0]
    )
    return _reihe(preise)


# -- Erkennung --------------------------------------------------------------

def test_w_wird_gefunden():
    df, atr = _w_verlauf()
    funde = finde_doppelmuster(df, atr=atr)

    boeden = [f for f in funde if f.art == "Doppelboden"]
    assert boeden, "Das W wurde nicht erkannt"
    fund = boeden[0]
    assert fund.richtung == "bullish"
    # Swing-Tiefs kommen aus 'low' (= close - 0,5), das Zwischenhoch aus 'high'.
    assert fund.zweite_spitze == pytest.approx(90.0)
    assert fund.erste_spitze == pytest.approx(89.5)
    assert fund.nackenlinie == pytest.approx(107.5)


def test_muster_ist_erst_strength_kerzen_spaeter_bekannt():
    """DER Test dieses Moduls.

    Das zweite Tief liegt bei Kerze i, bestaetigt ist es erst bei i+strength.
    Wer die Erkennung auf i setzt, baut Lookahead ein - und das Ergebnis
    sieht hervorragend aus, ohne dass an den Kursen etwas verdaechtig waere.
    """
    df, atr = _w_verlauf()
    fund = [f for f in finde_doppelmuster(df, atr=atr) if f.art == "Doppelboden"][0]

    assert fund.verfuegbar_index == fund.event_index + STANDARD_STRENGTH


def test_spalten_stehen_auf_der_verfuegbarkeit_nicht_auf_dem_tief():
    df, atr = _w_verlauf()
    fund = [f for f in finde_doppelmuster(df, atr=atr) if f.art == "Doppelboden"][0]
    spalten = doppelmuster_spalten(df, atr=atr)

    assert bool(spalten["w_erkannt"].iloc[fund.verfuegbar_index])
    assert not bool(spalten["w_erkannt"].iloc[fund.event_index])
    # Die Ereigniszeit bleibt nachvollziehbar - fuer die Anzeige.
    assert spalten["w_event_ts"].iloc[fund.verfuegbar_index] == df.index.asi8[
        fund.event_index
    ]


def test_zu_flaches_zwischenhoch_ist_kein_w():
    """Sonst waere jede Seitwaertsbewegung an einem Level ein Doppelboden."""
    preise = (
        [100.0, 97.0, 94.0]
        + [90.0]
        + [91.0, 92.0, 93.0]     # nur 3 Punkte Erholung, ATR ist 10
        + [92.0, 91.0]
        + [90.2]
        + [92.0, 95.0, 98.0, 101.0]
    )
    df, atr = _reihe(preise)
    boeden = [f for f in finde_doppelmuster(df, atr=atr) if f.art == "Doppelboden"]
    assert not boeden


def test_zu_weit_auseinanderliegende_tiefs_sind_kein_w():
    preise = (
        [110.0, 104.0, 98.0]
        + [90.0]
        + [96.0, 102.0, 108.0]
        + [104.0, 98.0]
        + [78.0]                  # 12 Punkte tiefer, Schwelle ist 0,5 x ATR = 5
        + [86.0, 94.0, 102.0, 108.0]
    )
    df, atr = _reihe(preise)
    boeden = [f for f in finde_doppelmuster(df, atr=atr) if f.art == "Doppelboden"]
    assert not boeden


def test_ohne_atr_bricht_es_ab_statt_zu_raten():
    df, _ = _w_verlauf()
    with pytest.raises(ValueError, match="ATR"):
        finde_doppelmuster(df.drop(columns=[], errors="ignore"), atr=None)


def test_leere_und_kurze_reihen_liefern_nichts():
    df, atr = _reihe([100.0, 101.0, 102.0])
    assert finde_doppelmuster(df, atr=atr) == []


# -- Nackenbruch ------------------------------------------------------------

def test_nackenbruch_ist_eine_flanke_kein_zustand():
    """Eine Zustandsabfrage feuerte auf jeder Kerze der Bewegung erneut und
    zaehlte dieselbe Bewegung vielfach (CLAUDE.md, Erweiterungspunkte)."""
    df, atr = _w_verlauf()
    spalten = doppelmuster_spalten(df, atr=atr)

    assert int(spalten["w_nackenbruch"].sum()) == 1


def test_nackenbruch_liegt_nach_der_erkennung():
    df, atr = _w_verlauf()
    spalten = doppelmuster_spalten(df, atr=atr)

    erkannt = np.nonzero(spalten["w_erkannt"].to_numpy())[0]
    bruch = np.nonzero(spalten["w_nackenbruch"].to_numpy())[0]
    assert len(erkannt) and len(bruch)
    assert bruch[0] >= erkannt[0]


def test_ohne_bruch_im_fenster_kein_signal():
    """Laeuft der Kurs nach dem zweiten Tief nie ueber die Nackenlinie, gibt
    es kein Einstiegssignal - aber das Muster bleibt erkannt."""
    preise = (
        [110.0, 104.0, 98.0]
        + [90.0]
        + [96.0, 102.0, 107.0]
        + [102.0, 96.0]
        + [90.5]
        + [91.0, 91.5, 92.0, 91.0, 90.8, 91.2]   # dümpelt unter der Nackenlinie
    )
    df, atr = _reihe(preise)
    spalten = doppelmuster_spalten(df, atr=atr, gueltig_kerzen=4)

    assert bool(spalten["w_erkannt"].any())
    assert not bool(spalten["w_nackenbruch"].any())


# -- Gleichheit mit dem punktuellen Erkenner --------------------------------

def test_serie_und_punktueller_erkenner_urteilen_gleich():
    """Zwei Definitionen desselben Musters waeren derselbe Fehler wie zwei
    Indikator-Implementierungen.

    Geprueft wird ueber die ganze Reihe: an jeder Kerze muss die Serie
    dasselbe sagen wie ``detect_double_top_bottom`` auf den Daten bis dorthin.
    """
    df, atr = _w_verlauf()
    spalten = doppelmuster_spalten(df, atr=atr)
    atr_wert = float(atr.iloc[0])

    unterschiede = []
    for i in range(2 * STANDARD_STRENGTH + 2, len(df)):
        ausschnitt = df.iloc[: i + 1]
        punktuell = detect_double_top_bottom(ausschnitt, atr_value=atr_wert)
        punktuell_w = punktuell is not None and punktuell.name == "Doppelboden"

        # Die Serie meldet die Erkennung genau an der Kerze, an der sie
        # bekannt wird; der punktuelle Erkenner meldet sie ab dann bei jedem
        # Aufruf weiter, solange dieselben zwei Swings die juengsten sind.
        # Verglichen wird deshalb "seit der Erkennung schon einmal gemeldet".
        serie_w = bool(spalten["w_erkannt"].iloc[: i + 1].any())

        if punktuell_w and not serie_w:
            unterschiede.append(
                f"Kerze {i}: punktueller Erkenner findet ein W, die Serie nicht"
            )

    assert not unterschiede, "\n".join(unterschiede)


def test_serie_findet_kein_w_wo_der_punktuelle_keines_findet():
    """Die Gegenrichtung: keine Erfindung von Mustern."""
    # Reiner Aufwaertstrend - da gibt es kein Doppeltief.
    preise = [100.0 + i * 1.5 for i in range(40)]
    df, atr = _reihe(preise)

    spalten = doppelmuster_spalten(df, atr=atr)
    punktuell = detect_double_top_bottom(df, atr_value=10.0)

    assert not bool(spalten["w_erkannt"].any())
    assert punktuell is None or punktuell.name != "Doppelboden"


def test_spaltensatz_ist_vollstaendig():
    from common.muster_serie import DOPPELMUSTER_SPALTEN

    df, atr = _w_verlauf()
    spalten = doppelmuster_spalten(df, atr=atr)
    assert list(spalten.columns) == list(DOPPELMUSTER_SPALTEN)
    assert len(spalten) == len(df)


# -- Vektorisierung: Gleichheit mit der vollen Zwischenpunkt-Suche ---------

def _funde_mit_voller_suche(df, atr, *, strength=STANDARD_STRENGTH,
                            lookback=STANDARD_LOOKBACK):
    """Referenz: die alte O(Swings^2)-Fassung der Zwischenpunkt-Wahl.

    Baut die Musterfunde mit einer Komplettschleife ueber alle Gegen-Swings
    nach - genau so, wie es vor der searchsorted-Vektorisierung lief. Muss
    Fund fuer Fund dasselbe Ergebnis liefern.
    """
    from common.patterns import _clamp
    from common.structure import find_swing_points

    atr_werte = np.asarray(atr, dtype=float)
    punkte = find_swing_points(df, strength=strength)
    letzter = len(df) - 1
    geordnet = sorted(punkte, key=lambda p: letzter - p.bars_ago)
    indizes = [letzter - p.bars_ago for p in geordnet]

    raus = []
    for art, kind in (("Doppelboden", "low"), ("Doppeltop", "high")):
        gleiche = [(i, p) for i, p in zip(indizes, geordnet) if p.kind == kind]
        gegen = [(i, p) for i, p in zip(indizes, geordnet) if p.kind != kind]
        for k in range(1, len(gleiche)):
            erst_idx, erst = gleiche[k - 1]
            zweit_idx, zweit = gleiche[k]
            verfuegbar = zweit_idx + strength
            if verfuegbar > letzter or zweit_idx - erst_idx > lookback:
                continue
            a = atr_werte[verfuegbar]
            if not np.isfinite(a) or a <= 0:
                continue
            spitzenabstand = abs(zweit.price - erst.price)
            if spitzenabstand > STANDARD_MAX_SPITZENABSTAND_ATR * a:
                continue
            dazwischen = [(i, p) for i, p in gegen if erst_idx < i < zweit_idx]
            if not dazwischen:
                continue
            if kind == "low":
                _, tal = max(dazwischen, key=lambda paar: paar[1].price)
            else:
                _, tal = min(dazwischen, key=lambda paar: paar[1].price)
            taltiefe = abs(((erst.price + zweit.price) / 2.0) - tal.price)
            if taltiefe < STANDARD_MIN_TALTIEFE_ATR * a:
                continue
            raus.append((art, verfuegbar, round(tal.price, 6),
                         round(spitzenabstand, 6)))
    raus.sort(key=lambda t: t[1])
    return raus


def test_vektorisierte_zwischenpunkt_wahl_gleicht_der_vollen_suche():
    """searchsorted statt Komplettschleife - dasselbe Ergebnis, O(n) statt
    O(n^2). Lange, verrauschte Reihe, damit das Fenster zwischen zwei
    gleichartigen Swings mal keinen, mal einen, mal mehrere Gegen-Swings
    enthaelt.
    """
    from common.muster_serie import finde_doppelmuster

    rng = np.random.default_rng(20260831)
    n = 4000
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 6.0, n))
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    spanne = np.abs(rng.normal(4.0, 1.5, n)) + 0.5
    df = pd.DataFrame(
        {
            "open": preise,
            "high": preise + spanne,
            "low": preise - spanne,
            "close": preise + rng.normal(0.0, 0.5, n),
            "volume": rng.integers(100, 2000, n).astype(float),
        },
        index=index,
    )
    atr = pd.Series(np.full(n, 12.0), index=index)

    funde = finde_doppelmuster(df, atr=atr)
    gemessen = [
        (f.art, f.verfuegbar_index, round(f.nackenlinie, 6),
         round(f.spitzenabstand, 6))
        for f in funde
    ]
    assert gemessen == _funde_mit_voller_suche(df, atr)
    # Der Test taugt nur, wenn ueberhaupt Muster gefunden werden.
    assert len(funde) >= 5
