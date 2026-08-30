"""Displacement (institutioneller Impuls) als Ereignis-Serie.

Anders als bei FVG, Struktur und Niveau gibt es hier **keine** eigene
Rechenlogik: ``common/market_primitives.py::detect_displacements`` ist bereits
ein einzelner Vorwaertsdurchlauf, O(n), schnell genug fuer die volle Historie
(~0,5 s auf 500k Kerzen). Eine serientaugliche Neufassung waere nur eine
zweite Definition desselben Musters - genau das, was Invariante 1 verbietet.

Dieses Modul adaptiert die Funde an die :class:`Ereignis`-Abstraktion und
liefert die Spaltenfassung fuer die Pipeline.

DEFINITION (aus detect_displacements)
------------------------------------
Eine Kerze ist ein Displacement, wenn

1. ``|close - open| / (high - low) >= min_body_ratio``  (Koerperdominanz)
2. ``|close - open| >= min_body_atr x ATR``             (Groesse)
3. ``volume >= min_volume_ratio x Rolling-Mittel(volume, 20)``

PHASEN
------
Eine Displacement-Kerze ist an ihrem eigenen Schluss vollstaendig bekannt
(Koerper, Spanne, Volumen). Also ``entstehung = bestaetigung = verfuegbar =
bar_index`` - keine Verzoegerung, kein Lookahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.market_primitives import detect_displacements

#: Vorgaben aus detect_displacements, hier nur gespiegelt.
MIN_BODY_ATR = 1.0
MIN_BODY_RATIO = 0.60
MIN_VOLUME_RATIO = 1.0
VOLUME_FENSTER = 20


def displacement_serie(
    df: pd.DataFrame,
    *,
    min_body_atr: float = MIN_BODY_ATR,
    min_body_ratio: float = MIN_BODY_RATIO,
    min_volume_ratio: float = MIN_VOLUME_RATIO,
    volume_fenster: int = VOLUME_FENSTER,
    detect_timeframe: str = "1m",
) -> list[Ereignis]:
    """Alle Displacement-Kerzen der Reihe als Ereignisse."""
    funde = detect_displacements(
        df,
        min_body_atr=min_body_atr,
        min_body_ratio=min_body_ratio,
        min_volume_ratio=min_volume_ratio,
        volume_window=volume_fenster,
    )
    ereignisse: list[Ereignis] = []
    for d in funde:
        ereignisse.append(
            Ereignis(
                pattern_type="displacement",
                pattern_variant="bullish" if d.direction == "bullish" else "bearish",
                detect_timeframe=detect_timeframe,
                direction=1 if d.direction == "bullish" else -1,
                entstehung_idx=d.bar_index,
                bestaetigung_idx=d.bar_index,
                verfuegbar_idx=d.bar_index,
                merkmale={
                    "koerper_punkte": round(d.body_points, 4),
                    "spanne_punkte": round(d.range_points, 4),
                    "koerper_anteil": round(d.body_ratio, 3),
                    "koerper_atr": round(d.body_atr, 3) if d.body_atr is not None else None,
                    "relatives_volumen": (
                        round(d.relative_volume, 3) if d.relative_volume is not None else None
                    ),
                },
            )
        )
    return ereignisse


DISPLACEMENT_SPALTEN = (
    "displacement", "displacement_richtung", "displacement_koerper_atr",
    "displacement_rel_volumen",
)


def displacement_spalten(
    df: pd.DataFrame,
    *,
    min_body_atr: float = MIN_BODY_ATR,
    min_body_ratio: float = MIN_BODY_RATIO,
    min_volume_ratio: float = MIN_VOLUME_RATIO,
    volume_fenster: int = VOLUME_FENSTER,
) -> pd.DataFrame:
    """Displacement als Spalten - Flanke plus Kennzahlen fuer den Kontext
    anderer Ereignisse (Plan: ein CHoCH mit Displacement ist ein MSS)."""
    n = len(df)
    flanke = np.zeros(n, dtype=bool)
    richtung = np.zeros(n, dtype=np.int8)
    koerper_atr = np.full(n, np.nan)
    rel_vol = np.full(n, np.nan)
    for e in displacement_serie(
        df,
        min_body_atr=min_body_atr,
        min_body_ratio=min_body_ratio,
        min_volume_ratio=min_volume_ratio,
        volume_fenster=volume_fenster,
    ):
        i = e.verfuegbar_idx
        flanke[i] = True
        richtung[i] = e.direction
        if e.merkmale["koerper_atr"] is not None:
            koerper_atr[i] = e.merkmale["koerper_atr"]
        if e.merkmale["relatives_volumen"] is not None:
            rel_vol[i] = e.merkmale["relatives_volumen"]
    return pd.DataFrame(
        {
            "displacement": flanke,
            "displacement_richtung": richtung,
            "displacement_koerper_atr": koerper_atr,
            "displacement_rel_volumen": rel_vol,
        },
        index=df.index,
    )


__all__ = [
    "DISPLACEMENT_SPALTEN",
    "MIN_BODY_ATR",
    "MIN_BODY_RATIO",
    "MIN_VOLUME_RATIO",
    "VOLUME_FENSTER",
    "displacement_serie",
    "displacement_spalten",
]
