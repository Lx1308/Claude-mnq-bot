"""Strukturniveaus als Serie - wohin ein Stop chartlich gehoert.

WOZU
----
Laurins Frage vom 30.08.2026, und sie ist die bessere: **nicht** "50 oder 100
Dollar Stop", sondern "wo muss der Stop *chartlich* hin, damit er plausibel
ist". Ein Stop unterhalb des letzten Tiefs hat eine Begruendung - dort ist der
Halt weg, der die Bewegung getragen hat. Ein Stop bei 1,5 x ATR hat keine; er
ist strukturell blind und sitzt mal mitten in einer Zone, mal weit dahinter.

Die Vermutung dahinter ist ernst zu nehmen: es kann sein, dass unsere Setups
gar keine schlechte Einstiegskante haben, sondern nur eine Stop-Platzierung,
die sie systematisch ausknockt. Ein- und Ausstieg gehoeren getrennt untersucht
(MASTERPLAN G) - passiert ist das bisher nie.

WAS HIER ENTSTEHT
-----------------
Je Kerze das **zuletzt bestaetigte** Strukturniveau:

* ``letztes_swing_tief`` / ``letztes_swing_hoch``
* ``vorletztes_swing_tief`` / ``vorletztes_swing_hoch`` - fuer einen weiter
  entfernten Stop, der nicht am erstbesten Rauschen haengt

Vortagesmarken (``prev_session_low``/``prev_session_high``) liefert
``common.indicators.compute_indicators`` bereits; sie werden hier nicht
verdoppelt.

DER LOOKAHEAD, DER VERHINDERT WIRD
----------------------------------
Dieselbe Falle wie bei der Musterserie: ein Swing-Tief ist an seiner eigenen
Kerze nicht erkennbar. ``find_swing_points`` laesst die letzten ``strength``
Kerzen aus, weil sich "erst in der Zukunft entscheidet", ob sie ein Extrem
werden.

Ein Stop, der auf ein Tief gesetzt wird, das zum Einstiegszeitpunkt noch gar
nicht bestaetigt war, ist Wissen aus der Zukunft - und er sieht im Backtest
besser aus, weil er zufaellig immer knapp unter dem tatsaechlichen Tief liegt.
Deshalb steht ein Swing-Niveau hier erst ``strength`` Kerzen nach seinem
Extrem zur Verfuegung.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv
from common.structure import find_swing_points

#: Wie bei der Musterserie - Vorgabe aus ``detect_double_top_bottom``.
STANDARD_STRENGTH = 3

#: Die Spalten, die :func:`strukturniveau_spalten` erzeugt.
STRUKTUR_SPALTEN = (
    "letztes_swing_tief",
    "letztes_swing_hoch",
    "vorletztes_swing_tief",
    "vorletztes_swing_hoch",
)


def _niveau_serie(
    laenge: int,
    indizes: list[int],
    preise: list[float],
    *,
    strength: int,
    rang: int,
) -> np.ndarray:
    """Das ``rang``-letzte bestaetigte Niveau je Kerze, vorwaerts fortgeschrieben.

    ``rang=0`` ist das juengste bestaetigte Extrem, ``rang=1`` das davor.
    Bekannt wird ein Extrem bei ``index + strength``.
    """
    werte = np.full(laenge, np.nan)
    bisher: list[float] = []

    # Verfuegbarkeitszeitpunkt -> Preis, in zeitlicher Reihenfolge.
    verfuegbar = sorted(
        ((idx + strength, preis) for idx, preis in zip(indizes, preise)),
        key=lambda paar: paar[0],
    )

    naechster = 0
    for i in range(laenge):
        while naechster < len(verfuegbar) and verfuegbar[naechster][0] <= i:
            bisher.append(verfuegbar[naechster][1])
            naechster += 1
        if len(bisher) > rang:
            werte[i] = bisher[-1 - rang]
    return werte


def strukturniveau_spalten(
    df: pd.DataFrame, *, strength: int = STANDARD_STRENGTH
) -> pd.DataFrame:
    """Die zuletzt bestaetigten Swing-Niveaus je Kerze.

    Die Swing-Punkte werden **einmal** ueber die ganze Reihe gesucht - aus
    O(n x lookback) wird O(n), wie bei der Musterserie.
    """
    validate_ohlcv(df)
    leer = pd.DataFrame(
        {name: np.full(len(df), np.nan) for name in STRUKTUR_SPALTEN},
        index=df.index,
    )
    if len(df) < 2 * strength + 2:
        return leer

    punkte = find_swing_points(df, strength=strength)
    if not punkte:
        return leer

    letzter = len(df) - 1
    tiefs_idx, tiefs_preis, hochs_idx, hochs_preis = [], [], [], []
    for punkt in punkte:
        index = letzter - punkt.bars_ago
        if punkt.kind == "low":
            tiefs_idx.append(index)
            tiefs_preis.append(float(punkt.price))
        else:
            hochs_idx.append(index)
            hochs_preis.append(float(punkt.price))

    n = len(df)
    return pd.DataFrame(
        {
            "letztes_swing_tief": _niveau_serie(
                n, tiefs_idx, tiefs_preis, strength=strength, rang=0
            ),
            "letztes_swing_hoch": _niveau_serie(
                n, hochs_idx, hochs_preis, strength=strength, rang=0
            ),
            "vorletztes_swing_tief": _niveau_serie(
                n, tiefs_idx, tiefs_preis, strength=strength, rang=1
            ),
            "vorletztes_swing_hoch": _niveau_serie(
                n, hochs_idx, hochs_preis, strength=strength, rang=1
            ),
        },
        index=df.index,
    )


__all__ = [
    "STANDARD_STRENGTH",
    "STRUKTUR_SPALTEN",
    "strukturniveau_spalten",
]
