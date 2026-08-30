"""Fair Value Gap (Imbalance) als Serie ueber die ganze Historie.

``common/market_primitives.py::detect_fair_value_gaps`` verfolgt fuer JEDES
erkannte Gap die Mitigation in einer Schleife bis ans Reihenende -
O(Gaps x n). Auf 2,5 Mio Kerzen mit einigen zehntausend Gaps ist das nicht
rechenbar. Hier: die Gap-Erkennung vektorisiert, die Mitigation in einem
begrenzten Fenster.

DEFINITION (identisch zu detect_fair_value_gaps)
-----------------------------------------------
Drei Kerzen ``i-2, i-1, i``:

* **bullish**: ``low[i] > high[i-2]``   -> ungedeckte Spanne ``[high[i-2], low[i]]``
* **bearish**: ``high[i] < low[i-2]``   -> ungedeckte Spanne ``[high[i], low[i-2]]``

Filter: Spanne >= ``min_gap_ticks`` Ticks, und (falls ``min_gap_atr > 0``)
Spanne >= ``min_gap_atr`` x ATR am Bestaetigungsindex.

PHASEN
------
* ``entstehung_idx``  = ``i-1`` (die Impulskerze, die das Loch reisst)
* ``bestaetigung_idx``= ``i``   (die dritte Kerze schliesst das Muster ab)
* ``verfuegbar_idx``  = ``i``   (ihr Schluss steht fest)

MITIGATION - begrenztes Fenster, bewusst anders als der punktuelle Erkenner
--------------------------------------------------------------------------
Der punktuelle Erkenner sucht die Mitigation bis ans Reihenende - fuer die
Anzeige ("ist dieses alte FVG noch offen?"). Fuer die Forschung zaehlt nur,
ob das Gap **zeitnah** wieder angelaufen wurde; alles danach ist Sache der
Outcome-Messung. Deshalb ``mitigation_fenster`` Kerzen (Vorgabe 240 = 4 h,
der laengste Nicht-Session-Horizont im Plan). Ein Test haelt fest, dass
serielle und punktuelle Fassung **innerhalb dieses Fensters** dasselbe
Mitigation-Urteil faellen.

KEIN LOOKAHEAD
--------------
Das Gap ist am Schluss von Kerze ``i`` bekannt. Die Mitigation-Merkmale
stehen ebenfalls am ``verfuegbar_idx`` - sie beschreiben, was in den
folgenden Kerzen geschah, und werden erst beim Erreichen des Fensterendes
(bzw. der Mitigation) endgueltig. Fuer die Auswertung heisst das: die
Mitigation-Felder eines Gaps, dessen Fenster noch nicht abgelaufen ist,
sind unvollstaendig - genau wie beim Outcome. Der Lookahead-Test schneidet
die Reihe und prueft, dass die frueh verfuegbaren Gaps identisch bleiben.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.indicators import validate_ohlcv

#: Mindestgroesse in Ticks - wie beim punktuellen Erkenner.
MIN_GAP_TICKS = 1.0

#: Wie viele Kerzen nach der Bestaetigung die Mitigation noch verfolgt wird.
MITIGATION_FENSTER = 240


def fvg_serie(
    df: pd.DataFrame,
    *,
    tick_size: float = 0.25,
    min_gap_ticks: float = MIN_GAP_TICKS,
    min_gap_atr: float = 0.0,
    detect_timeframe: str = "1m",
    mitigation_fenster: int = MITIGATION_FENSTER,
) -> list[Ereignis]:
    """Alle Fair Value Gaps der Reihe, aufsteigend nach ``verfuegbar_idx``.

    Erwartet einen mit ``compute_indicators`` vorbereiteten Rahmen, wenn
    ``min_gap_atr > 0`` (dann wird die ``atr``-Spalte gebraucht).
    """
    validate_ohlcv(df)
    n = len(df)
    if n < 3:
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)

    atr = None
    if "atr" in df.columns:
        atr = df["atr"].to_numpy(dtype=float)
    if min_gap_atr > 0 and atr is None:
        raise ValueError(
            "fvg_serie mit min_gap_atr > 0 braucht die atr-Spalte des "
            "vorbereiteten Rahmens."
        )

    # --- Gap-Erkennung, vektorisiert -------------------------------------
    i = np.arange(2, n)
    hoch_vor2 = highs[:-2]
    tief_vor2 = lows[:-2]
    bull = lows[2:] > hoch_vor2
    bear = highs[2:] < tief_vor2

    ereignisse: list[Ereignis] = []

    for maske, richtung, name in ((bull, 1, "bullish"), (bear, -1, "bearish")):
        for pos in np.nonzero(maske)[0]:
            idx = int(i[pos])
            if richtung == 1:
                oben = float(lows[idx])
                unten = float(highs[idx - 2])
            else:
                oben = float(tief_vor2[pos])
                unten = float(highs[idx])
            spanne = oben - unten
            if spanne <= 0:
                continue
            spanne_ticks = spanne / tick_size
            if spanne_ticks < min_gap_ticks:
                continue
            a = float(atr[idx]) if atr is not None and np.isfinite(atr[idx]) else None
            spanne_atr = (spanne / a) if (a and a > 0) else None
            if min_gap_atr > 0 and (spanne_atr is None or spanne_atr < min_gap_atr):
                continue

            mitig = _mitigation(
                highs, lows, idx, oben, unten, spanne, richtung,
                fenster=mitigation_fenster, n=n,
            )

            ereignisse.append(
                Ereignis(
                    pattern_type="fair_value_gap",
                    pattern_variant=name,
                    detect_timeframe=detect_timeframe,
                    direction=richtung,
                    entstehung_idx=idx - 1,
                    bestaetigung_idx=idx,
                    verfuegbar_idx=idx,
                    merkmale={
                        "level_1": round(unten, 4),
                        "level_2": round(oben, 4),
                        "fvg_top": round(oben, 4),
                        "fvg_bottom": round(unten, 4),
                        "fvg_mittelpunkt_ce": round((oben + unten) / 2.0, 4),
                        "spanne_punkte": round(spanne, 4),
                        "spanne_ticks": round(spanne_ticks, 2),
                        "spanne_atr": round(spanne_atr, 3) if spanne_atr is not None else None,
                        "mitigiert": mitig["mitigiert"],
                        "kerzen_bis_mitigation": mitig["kerzen_bis_mitigation"],
                        "fuellgrad": round(mitig["fuellgrad"], 3),
                        "mitigation_fenster": int(mitigation_fenster),
                    },
                )
            )

    ereignisse.sort(key=lambda e: (e.verfuegbar_idx, -e.direction))
    return ereignisse


def _mitigation(
    highs: np.ndarray,
    lows: np.ndarray,
    idx: int,
    oben: float,
    unten: float,
    spanne: float,
    richtung: int,
    *,
    fenster: int,
    n: int,
) -> dict:
    """Erste Rueckkehr ins Gap innerhalb des Fensters + maximaler Fuellgrad.

    Mitigation wie beim punktuellen Erkenner: der Kurs erreicht das
    50%-Niveau des Gaps. Fuellgrad = tiefste Durchdringung / Gap-Groesse,
    auf ``[0, 1]`` begrenzt.
    """
    ende = min(idx + fenster, n - 1)
    if ende <= idx:
        return {"mitigiert": False, "kerzen_bis_mitigation": None, "fuellgrad": 0.0}

    halb = spanne * 0.5
    if richtung == 1:
        # bullish: Gap = [unten, oben] = [high[i-2], low[i]]. Durchdringung
        # von oben: low[j] faellt unter low[i] (= oben).
        folge_low = lows[idx + 1 : ende + 1]
        pen = oben - folge_low
        schwelle = folge_low <= unten + halb
    else:
        folge_high = highs[idx + 1 : ende + 1]
        pen = folge_high - unten  # unten = high[i]
        schwelle = folge_high >= oben - halb

    pen_positiv = pen[pen > 0]
    fuellgrad = float(np.clip(pen_positiv.max() / spanne, 0.0, 1.0)) if pen_positiv.size else 0.0

    treffer = np.nonzero(schwelle)[0]
    if treffer.size:
        return {
            "mitigiert": True,
            "kerzen_bis_mitigation": int(treffer[0]) + 1,
            "fuellgrad": fuellgrad,
        }
    return {"mitigiert": False, "kerzen_bis_mitigation": None, "fuellgrad": fuellgrad}


def fvg_spalten(
    df: pd.DataFrame,
    *,
    tick_size: float = 0.25,
    min_gap_ticks: float = MIN_GAP_TICKS,
    min_gap_atr: float = 0.0,
) -> pd.DataFrame:
    """Die FVG-Serie als Spalten - auf dem Verfuegbarkeitszeitpunkt.

    ``fvg_bull`` / ``fvg_bear`` sind Flanken (nur an der Bestaetigungskerze
    True), ``fvg_bull_top`` etc. tragen die Gap-Grenzen fuer eine
    Stop-Referenz.
    """
    n = len(df)
    spalten = {
        "fvg_bull": np.zeros(n, dtype=bool),
        "fvg_bull_top": np.full(n, np.nan),
        "fvg_bull_bottom": np.full(n, np.nan),
        "fvg_bear": np.zeros(n, dtype=bool),
        "fvg_bear_top": np.full(n, np.nan),
        "fvg_bear_bottom": np.full(n, np.nan),
    }
    for e in fvg_serie(
        df, tick_size=tick_size, min_gap_ticks=min_gap_ticks, min_gap_atr=min_gap_atr
    ):
        i = e.verfuegbar_idx
        p = "fvg_bull" if e.direction == 1 else "fvg_bear"
        spalten[p][i] = True
        spalten[f"{p}_top"][i] = e.merkmale["fvg_top"]
        spalten[f"{p}_bottom"][i] = e.merkmale["fvg_bottom"]
    return pd.DataFrame(spalten, index=df.index)


FVG_SPALTEN = (
    "fvg_bull", "fvg_bull_top", "fvg_bull_bottom",
    "fvg_bear", "fvg_bear_top", "fvg_bear_bottom",
)


__all__ = [
    "FVG_SPALTEN",
    "MIN_GAP_TICKS",
    "MITIGATION_FENSTER",
    "fvg_serie",
    "fvg_spalten",
]
