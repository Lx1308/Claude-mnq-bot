"""Order Block als Serie - die letzte Gegenkerze vor dem Impuls.

ICT/SMC-Definition: Bevor der Markt kraeftig in eine Richtung laeuft, gibt es
oft eine letzte Kerze in die **Gegen**richtung. Die Lesart dahinter: dort hat
jemand Grosses die Gegenseite eingesammelt, bevor er den Markt bewegte. Kommt
der Kurs spaeter an diese Zone zurueck, soll sie halten.

**Ob sie das haeufiger haelt, als der Zufall erwarten laesst, ist die Frage
dieser Untersuchung und wird hier nicht behauptet.** Der Erkenner markiert
die Zone; ob sie traegt, entscheidet die Outcome-Messung.

DEFINITION
----------
Ein Displacement bei ``d`` (aus ``displacement.py``, dieselbe Definition wie
``market_primitives.detect_displacements``):

* **Bullish Order Block**: die juengste Kerze ``b < d`` mit ``close < open``
  innerhalb von ``max_abstand`` Kerzen vor ``d``.
* **Bearish Order Block**: die juengste Kerze ``b < d`` mit ``close > open``.

Die **Zone** ist die volle Spanne dieser Kerze (``low..high``); der Koerper
(``open..close``) wird als engere Variante mitgefuehrt. Welche der beiden
besser traegt, ist messbar und wird nicht vorentschieden - deshalb stehen
beide in den Merkmalen.

Findet sich innerhalb des Fensters keine Gegenkerze, entsteht **kein**
Ereignis. Ein Impuls aus einer Reihe gleichgerichteter Kerzen heraus hat
keinen Order Block; ihn trotzdem irgendwo zu verankern waere geraten.

PHASEN
------
* ``entstehung_idx``  = die Order-Block-Kerze (dort liegt die Zone)
* ``bestaetigung_idx``= die Displacement-Kerze
* ``verfuegbar_idx``  = die Displacement-Kerze

Der entscheidende Punkt: **die OB-Kerze allein ist kein Signal.** Zum Zeitpunkt
``b`` ist sie eine gewoehnliche Gegenkerze - erst das Displacement danach macht
sie zum Order Block. Wer die Zone ab ``b`` handelt, benutzt Wissen aus der
Zukunft.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.ereignisse.displacement import (
    MIN_BODY_ATR,
    MIN_BODY_RATIO,
    MIN_VOLUME_RATIO,
    displacement_serie,
)
from common.indicators import validate_ohlcv

#: Wie viele Kerzen vor dem Displacement nach der Gegenkerze gesucht wird.
#: Zehn: was weiter zurueckliegt, hat mit diesem Impuls nichts mehr zu tun.
MAX_ABSTAND = 10


def orderblock_ereignisse(
    df: pd.DataFrame,
    *,
    detect_timeframe: str = "1m",
    max_abstand: int = MAX_ABSTAND,
    min_body_atr: float = MIN_BODY_ATR,
    min_body_ratio: float = MIN_BODY_RATIO,
    min_volume_ratio: float = MIN_VOLUME_RATIO,
) -> list[Ereignis]:
    """Order Blocks als Ereignisse, verankert auf dem Displacement.

    Erwartet einen mit ``compute_indicators`` vorbereiteten Rahmen.
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError("orderblock_ereignisse braucht die atr-Spalte.")

    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)

    ereignisse: list[Ereignis] = []
    for disp in displacement_serie(
        df,
        min_body_atr=min_body_atr,
        min_body_ratio=min_body_ratio,
        min_volume_ratio=min_volume_ratio,
    ):
        d = disp.verfuegbar_idx
        richtung = disp.direction
        a = atr[d]
        if not (np.isfinite(a) and a > 0):
            continue

        # Rueckwaerts die juengste Gegenkerze suchen.
        anfang = max(0, d - max_abstand)
        b = -1
        for k in range(d - 1, anfang - 1, -1):
            gegen = (
                closes[k] < opens[k] if richtung == 1 else closes[k] > opens[k]
            )
            if gegen:
                b = k
                break
        if b < 0:
            continue

        zone_oben = float(highs[b])
        zone_unten = float(lows[b])
        koerper_oben = float(max(opens[b], closes[b]))
        koerper_unten = float(min(opens[b], closes[b]))

        ereignisse.append(
            Ereignis(
                pattern_type="order_block",
                pattern_variant="bullish" if richtung == 1 else "bearish",
                detect_timeframe=detect_timeframe,
                direction=richtung,
                entstehung_idx=b,
                bestaetigung_idx=d,
                verfuegbar_idx=d,
                merkmale={
                    # Volle Spanne der OB-Kerze - die weite Variante.
                    "level_1": round(zone_unten, 4),
                    "level_2": round(zone_oben, 4),
                    "ob_zone_oben": round(zone_oben, 4),
                    "ob_zone_unten": round(zone_unten, 4),
                    # Koerper - die enge Variante. Welche traegt, ist messbar.
                    "ob_koerper_oben": round(koerper_oben, 4),
                    "ob_koerper_unten": round(koerper_unten, 4),
                    # Die Kante, an der ein Ruecklauf typischerweise ansetzt.
                    "level_neckline": round(
                        zone_oben if richtung == -1 else zone_unten, 4
                    ),
                    "ob_hoehe_punkte": round(zone_oben - zone_unten, 4),
                    "ob_hoehe_atr": round((zone_oben - zone_unten) / float(a), 3),
                    "abstand_zum_impuls_bars": int(d - b),
                    "impuls_koerper_atr": disp.merkmale["koerper_atr"],
                    "impuls_rel_volumen": disp.merkmale["relatives_volumen"],
                },
            )
        )

    ereignisse.sort(key=lambda e: (e.verfuegbar_idx, -e.direction))
    return ereignisse


ORDERBLOCK_SPALTEN = (
    "ob_bull", "ob_bull_oben", "ob_bull_unten",
    "ob_bear", "ob_bear_oben", "ob_bear_unten",
)


def orderblock_spalten(
    df: pd.DataFrame, *, max_abstand: int = MAX_ABSTAND, **schwellen
) -> pd.DataFrame:
    """Order Blocks als Spalten.

    Die Zonengrenzen werden **fortgeschrieben**: eine Zone bleibt als
    Referenz stehen, bis eine neue derselben Richtung sie ersetzt. Ob sie
    noch gilt (also noch nicht durchhandelt wurde), beantwortet die
    Outcome-Messung, nicht diese Spalte.
    """
    n = len(df)
    spalten = {
        "ob_bull": np.zeros(n, dtype=bool),
        "ob_bull_oben": np.full(n, np.nan),
        "ob_bull_unten": np.full(n, np.nan),
        "ob_bear": np.zeros(n, dtype=bool),
        "ob_bear_oben": np.full(n, np.nan),
        "ob_bear_unten": np.full(n, np.nan),
    }
    for e in orderblock_ereignisse(df, max_abstand=max_abstand, **schwellen):
        i = e.verfuegbar_idx
        p = "ob_bull" if e.direction == 1 else "ob_bear"
        spalten[p][i] = True
        spalten[f"{p}_oben"][i] = e.merkmale["ob_zone_oben"]
        spalten[f"{p}_unten"][i] = e.merkmale["ob_zone_unten"]

    rahmen = pd.DataFrame(spalten, index=df.index)
    for p in ("ob_bull", "ob_bear"):
        rahmen[f"{p}_oben"] = rahmen[f"{p}_oben"].ffill()
        rahmen[f"{p}_unten"] = rahmen[f"{p}_unten"].ffill()
    return rahmen[list(ORDERBLOCK_SPALTEN)]


__all__ = [
    "MAX_ABSTAND",
    "ORDERBLOCK_SPALTEN",
    "orderblock_ereignisse",
    "orderblock_spalten",
]
