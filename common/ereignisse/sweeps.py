"""Liquidity Sweep (Stop-Run mit Reclaim) als Serie.

Laurins Kerninteresse aus dem einen erfolgreichen Trade vom 30.08.2026: das
Ziel lag "knapp unter dem letzten Liquiditaets-Spike". Der Sweep ist das
Muster dahinter - der Kurs holt die Stops jenseits einer Marke ab und dreht
sofort um.

ABGRENZUNG ZU ``niveaus.py`` - drei verschiedene Dinge
-----------------------------------------------------
An derselben Marke koennen drei Muster entstehen, und sie sind **nicht**
dasselbe:

* ``niveau_test``  - beruehrt, geht nicht durch (weder Docht noch Schluss)
* ``ausbruch`` / ``fehlausbruch`` - der **Schluss** ging durch; beim
  Fehlausbruch kam der Kurs danach zurueck
* ``liquidity_sweep`` (hier) - der **Docht** ging durch, der Schluss aber
  nicht (oder nur ganz kurz). Genau das ist die Stop-Abholung: der Markt
  greift die Orders jenseits ab, ohne das Niveau anzunehmen.

Der Sweep ist der feinste der drei: er verlangt keinen Schluss jenseits.

**Sie ueberlappen bewusst.** Ein Fehlausbruch, der innerhalb von
``max_reclaim_bars`` zurueckkommt, ist zugleich ein Sweep und erscheint in
beiden Tabellen - als zwei Zeilen, nicht als eine. Das ist Absicht (siehe
``basis.Ereignis.key``): jede Sicht bleibt eigenstaendig auswertbar, und
welche traegt, ist eine Messfrage. Damit die doppelte Sicht die
Stichprobengroesse nicht aufblaeht, fasst die Auswertung gleichzeitige
Ereignisse ueber ``cluster_id`` zusammen (Plan Abschnitt 12.1).

DEFINITION (aus ``market_primitives.detect_liquidity_sweeps``)
-------------------------------------------------------------
Sell-Side-Sweep (bullisch gedeutet), Niveau ``L``:

1. ``low[i] < L``  und ``low[i-1] >= L``   - Erstdurchstich nach unten
2. Reclaim: ``close[i] > L`` (sofort) **oder** ``close[i+k] > L`` fuer ein
   ``k <= max_reclaim_bars``
3. Sweep-Tiefe = ``L - min(low[i..i+k])``

Buy-Side-Sweep spiegelbildlich. Ohne Reclaim innerhalb des Fensters ist es
**kein** Sweep, sondern ein Ausbruch - und wird hier nicht gemeldet.

WAS "LIQUIDITAET" HIER HEISST - UND WAS NICHT
--------------------------------------------
Ein Preisniveau, an dem Stops **vermutet** werden. Kein Orderbuch, keine
Order-Tiefe, kein Delta (Plan Abschnitt 2). Als einzigen messbaren Ersatz
traegt jedes Sweep-Ereignis das **relative Volumen an der Sweep-Kerze**
(``volumen_am_extremum_relativ``, Plan Abschnitt 16 D): ein Sweep mit dem
Vierfachen des ueblichen Volumens ist strukturell etwas anderes als einer
bei duennem Handel. Das ist eine Messung am Umsatz, keine Aussage ueber die
Order-Tiefe.

PHASEN
------
* ``entstehung_idx``  = Sweep-Kerze (der Durchstich)
* ``bestaetigung_idx``= Reclaim-Kerze
* ``verfuegbar_idx``  = Reclaim-Kerze (ihr Schluss steht fest)

Der Sweep allein ist kein Ereignis - erst der Reclaim macht ihn zu einem.
Wer auf dem Durchstich handelt, weiss noch nicht, ob es einer wird.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.ereignisse.niveaus import niveau_serien
from common.ereignisse.swings import STANDARD_STRENGTH
from common.indicators import validate_ohlcv

#: Wie viele Kerzen der Reclaim spaetestens braucht. Drei wie im punktuellen
#: Erkenner: was fuenf Minuten braucht, um zurueckzukommen, ist keine
#: Stop-Abholung mehr, sondern eine normale Bewegung.
MAX_RECLAIM_BARS = 3

#: Mindesttiefe des Durchstichs in ATR. Ohne die zaehlt jeder Tick jenseits
#: der Marke als Sweep - bei 2,5 Mio Kerzen waeren das Millionen Ereignisse,
#: die ueberwiegend Rauschen sind.
MIN_TIEFE_ATR = 0.05

#: Fenster fuer das relative Volumen (gleitender Median). Median statt
#: Mittelwert: eine einzelne Ausbruchskerze soll den Bezugswert nicht
#: mitziehen.
VOLUMEN_FENSTER = 60


def _relatives_volumen(volumen: np.ndarray, fenster: int) -> np.ndarray:
    """Volumen im Verhaeltnis zum gleitenden Median der letzten ``fenster``
    Kerzen - **einschliesslich** der aktuellen.

    Rueckwaertsgerichtet: der Median steht am selben Index zur Verfuegung wie
    der Wert, den er einordnet. Kein Lookahead.
    """
    reihe = pd.Series(volumen)
    median = reihe.rolling(fenster, min_periods=max(5, fenster // 4)).median()
    verhaeltnis = reihe / median.replace(0.0, np.nan)
    return verhaeltnis.to_numpy(dtype=float)


def _sweeps_an_niveau(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr: np.ndarray,
    rel_volumen: np.ndarray,
    niveau: np.ndarray,
    *,
    niveau_name: str,
    detect_timeframe: str,
    max_reclaim_bars: int,
    min_tiefe_atr: float,
    tick_size: float,
) -> list[Ereignis]:
    """Ein Niveau, ein Vorwaertsdurchlauf."""
    n = len(closes)
    ereignisse: list[Ereignis] = []

    # Bis wohin die Reclaim-Suche eines frueheren Sweeps schon gelaufen ist -
    # verhindert, dass derselbe Durchstich mehrfach gemeldet wird, wenn der
    # Kurs mehrere Kerzen jenseits bleibt.
    naechster_frei_oben = 0
    naechster_frei_unten = 0

    for i in range(1, n):
        L = niveau[i]
        a = atr[i]
        if not (np.isfinite(L) and np.isfinite(a) and a > 0):
            continue
        mindest = min_tiefe_atr * a

        # --- Buy-Side: Docht ueber das Niveau, Schluss zurueck darunter ---
        if i >= naechster_frei_oben and highs[i] > L and highs[i - 1] <= L:
            treffer = _reclaim(
                closes, highs, i, L, max_reclaim_bars, n, richtung=-1
            )
            if treffer is not None:
                k, extremum = treffer
                tiefe = extremum - L
                if tiefe >= mindest:
                    ereignisse.append(
                        _ereignis(
                            richtung=-1, niveau_name=niveau_name,
                            detect_timeframe=detect_timeframe,
                            sweep_idx=i, reclaim_idx=i + k, niveau=L,
                            extremum=extremum, tiefe=tiefe, atr=a,
                            tick_size=tick_size,
                            rel_volumen=rel_volumen[i],
                        )
                    )
                    naechster_frei_oben = i + k + 1

        # --- Sell-Side: Docht unter das Niveau, Schluss zurueck darueber ---
        if i >= naechster_frei_unten and lows[i] < L and lows[i - 1] >= L:
            treffer = _reclaim(
                closes, lows, i, L, max_reclaim_bars, n, richtung=1
            )
            if treffer is not None:
                k, extremum = treffer
                tiefe = L - extremum
                if tiefe >= mindest:
                    ereignisse.append(
                        _ereignis(
                            richtung=1, niveau_name=niveau_name,
                            detect_timeframe=detect_timeframe,
                            sweep_idx=i, reclaim_idx=i + k, niveau=L,
                            extremum=extremum, tiefe=tiefe, atr=a,
                            tick_size=tick_size,
                            rel_volumen=rel_volumen[i],
                        )
                    )
                    naechster_frei_unten = i + k + 1

    return ereignisse


def _reclaim(
    closes: np.ndarray,
    extrema: np.ndarray,
    i: int,
    L: float,
    max_reclaim_bars: int,
    n: int,
    *,
    richtung: int,
) -> tuple[int, float] | None:
    """Kam der Kurs innerhalb des Fensters zurueck?

    Rueckgabe ``(k, extremum)``: ``k`` Kerzen nach dem Durchstich schloss der
    Kurs wieder diesseits; ``extremum`` ist das aeusserste Hoch/Tief des
    Durchstichs. ``None``, wenn kein Reclaim - dann ist es ein Ausbruch und
    gehoert nicht hierher.
    """
    ende = min(i + max_reclaim_bars, n - 1)
    for k in range(0, ende - i + 1):
        zurueck = (
            closes[i + k] > L if richtung == 1 else closes[i + k] < L
        )
        if zurueck:
            fenster = extrema[i : i + k + 1]
            extremum = float(fenster.min() if richtung == 1 else fenster.max())
            return k, extremum
    return None


def _ereignis(
    *,
    richtung: int,
    niveau_name: str,
    detect_timeframe: str,
    sweep_idx: int,
    reclaim_idx: int,
    niveau: float,
    extremum: float,
    tiefe: float,
    atr: float,
    tick_size: float,
    rel_volumen: float,
) -> Ereignis:
    return Ereignis(
        pattern_type="liquidity_sweep",
        pattern_variant=niveau_name,
        detect_timeframe=detect_timeframe,
        direction=richtung,
        entstehung_idx=sweep_idx,
        bestaetigung_idx=reclaim_idx,
        verfuegbar_idx=reclaim_idx,
        merkmale={
            "level_1": round(float(niveau), 4),
            "level_neckline": round(float(niveau), 4),
            "sweep_extremum": round(float(extremum), 4),
            "sweep_tiefe_punkte": round(float(tiefe), 4),
            "sweep_tiefe_ticks": round(float(tiefe / tick_size), 2),
            "sweep_tiefe_atr": round(float(tiefe / atr), 3),
            "kerzen_bis_reclaim": int(reclaim_idx - sweep_idx + 1),
            # Der einzige messbare Ersatz fuers fehlende Orderbuch (Plan 16 D).
            # Eine Messung am Umsatz, KEINE Aussage ueber die Order-Tiefe.
            "volumen_am_extremum_relativ": (
                round(float(rel_volumen), 3) if np.isfinite(rel_volumen) else None
            ),
        },
    )


def sweep_ereignisse(
    df: pd.DataFrame,
    *,
    detect_timeframe: str = "1m",
    strength: int = STANDARD_STRENGTH,
    max_reclaim_bars: int = MAX_RECLAIM_BARS,
    min_tiefe_atr: float = MIN_TIEFE_ATR,
    tick_size: float = 0.25,
    volumen_fenster: int = VOLUMEN_FENSTER,
) -> list[Ereignis]:
    """Alle Liquidity Sweeps ueber alle Niveauquellen.

    Erwartet den Output von ``Backtester.prepare`` (braucht ``atr``, und fuer
    die Vortages-/IB-Marken deren Spalten).
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError("sweep_ereignisse braucht die atr-Spalte.")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    rel_vol = _relatives_volumen(
        df["volume"].to_numpy(dtype=float), volumen_fenster
    )

    ereignisse: list[Ereignis] = []
    for name, niveau in niveau_serien(df, strength=strength):
        ereignisse.extend(
            _sweeps_an_niveau(
                highs, lows, closes, atr, rel_vol, niveau,
                niveau_name=name,
                detect_timeframe=detect_timeframe,
                max_reclaim_bars=max_reclaim_bars,
                min_tiefe_atr=min_tiefe_atr,
                tick_size=tick_size,
            )
        )
    ereignisse.sort(key=lambda e: (e.verfuegbar_idx, -e.direction))
    return ereignisse


SWEEP_SPALTEN = (
    "sweep_bull", "sweep_bear", "sweep_niveau", "sweep_tiefe_atr",
    "sweep_rel_volumen",
)


def sweep_spalten(
    df: pd.DataFrame,
    *,
    strength: int = STANDARD_STRENGTH,
    max_reclaim_bars: int = MAX_RECLAIM_BARS,
    min_tiefe_atr: float = MIN_TIEFE_ATR,
) -> pd.DataFrame:
    """Sweeps als Spalten - Flanken auf dem Reclaim, plus das gesweepte
    Niveau als Stop-Referenz.

    Steht mehr als ein Sweep auf derselben Kerze (mehrere Niveaus dicht
    beieinander), gewinnt der **tiefste** - er beschreibt die Bewegung.
    """
    n = len(df)
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)
    niveau = np.full(n, np.nan)
    tiefe = np.full(n, np.nan)
    rel_vol = np.full(n, np.nan)

    for e in sweep_ereignisse(
        df, strength=strength, max_reclaim_bars=max_reclaim_bars,
        min_tiefe_atr=min_tiefe_atr,
    ):
        i = e.verfuegbar_idx
        t = e.merkmale["sweep_tiefe_atr"]
        if np.isfinite(tiefe[i]) and tiefe[i] >= t:
            continue
        if e.direction == 1:
            bull[i] = True
            bear[i] = False
        else:
            bear[i] = True
            bull[i] = False
        niveau[i] = e.merkmale["level_1"]
        tiefe[i] = t
        v = e.merkmale["volumen_am_extremum_relativ"]
        rel_vol[i] = v if v is not None else np.nan

    return pd.DataFrame(
        {
            "sweep_bull": bull,
            "sweep_bear": bear,
            "sweep_niveau": niveau,
            "sweep_tiefe_atr": tiefe,
            "sweep_rel_volumen": rel_vol,
        },
        index=df.index,
    )


__all__ = [
    "MAX_RECLAIM_BARS",
    "MIN_TIEFE_ATR",
    "SWEEP_SPALTEN",
    "VOLUMEN_FENSTER",
    "sweep_ereignisse",
    "sweep_spalten",
]
