"""Marktstruktur als Serie: HH/HL/LH/LL, Strukturbruch (BOS), Charakterwechsel
(CHoCH).

``common/market_primitives.py::detect_structure_breaks`` durchsucht fuer JEDEN
Swing die gesamte Restreihe nach dem Bruch - O(Swings x n). Bei ~250.000
Swings auf 2,5 Mio Kerzen ist das nicht rechenbar. Hier ein einziger
Vorwaertsdurchlauf, O(n).

DEFINITIONEN (Standard-TA / SMC, siehe Plan)
-------------------------------------------
* Swing-Hoch hoeher als das vorige Swing-Hoch  -> Higher High (HH)
* Swing-Hoch tiefer                             -> Lower High (LH)
* Swing-Tief hoeher als das vorige Swing-Tief   -> Higher Low (HL)
* Swing-Tief tiefer                             -> Lower Low (LL)
* Aufwaertsstruktur: zuletzt HH und HL
* Abwaertsstruktur:  zuletzt LH und LL

* **BOS bullish**: in Aufwaertsstruktur schliesst der Kurs ueber dem zuletzt
  bestaetigten Swing-Hoch -> Fortsetzung.
* **CHoCH bullish**: in Abwaertsstruktur schliesst der Kurs ueber dem zuletzt
  bestaetigten Swing-Hoch -> erster Gegenstruktur-Bruch.
* Spiegelbildlich fuer die Baisse.

MSS (Market Structure Shift = CHoCH mit Displacement/FVG) wird hier NICHT
klassifiziert - das braucht die anderen Erkenner und passiert erst in der
Pipeline.

KEIN LOOKAHEAD
--------------
Ein Swing ist erst ``strength`` Kerzen nach seinem Extremum bekannt
(``swing_serie``). Der Bruch wird auf dem **Schlusskurs** der Bruchkerze
erkannt; verfuegbar ist er ab derselben Kerze (der Schluss steht fest). Der
Einstieg waere die Folgekerze - das ist Sache der Trigger-Tabelle, nicht
dieses Moduls.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.ereignisse.swings import STANDARD_STRENGTH, SwingSerie, swing_serie
from common.indicators import validate_ohlcv

#: Ab wann ein Bruch als "sauber" gilt: der Schluss muss das Niveau um
#: mindestens so viel ueberschreiten. In ATR, damit es ueber die Historie
#: vergleichbar bleibt. Null waere jeder Tick ein Bruch.
MIN_BRUCH_ATR = 0.05


def _struktur_labels(serie: SwingSerie) -> dict[str, np.ndarray]:
    """HH/HL/LH/LL je bestaetigtem Swing, plus die laufende Trendlage.

    Rueckgabe-Arrays, alle Laenge n:
      hh, hl, lh, ll     bool - an der Bestaetigungskerze des jeweiligen Swings
      trend              int[n] - +1 Aufwaerts, -1 Abwaerts, 0 unklar
                         (vorwaerts fortgeschrieben)
    """
    n = len(serie)
    hh = np.zeros(n, dtype=bool)
    hl = np.zeros(n, dtype=bool)
    lh = np.zeros(n, dtype=bool)
    ll = np.zeros(n, dtype=bool)
    trend = np.zeros(n, dtype=np.int8)

    letztes_hoch = np.nan
    letztes_tief = np.nan
    hoch_ist_hh: bool | None = None
    tief_ist_hl: bool | None = None
    aktueller_trend = 0

    for i in range(n):
        if serie.hoch_bestaetigt[i]:
            preis = serie.hoch_preis[i]
            if not np.isnan(letztes_hoch):
                if preis > letztes_hoch:
                    hh[i] = True
                    hoch_ist_hh = True
                else:
                    lh[i] = True
                    hoch_ist_hh = False
            letztes_hoch = preis
        if serie.tief_bestaetigt[i]:
            preis = serie.tief_preis[i]
            if not np.isnan(letztes_tief):
                if preis > letztes_tief:
                    hl[i] = True
                    tief_ist_hl = True
                else:
                    ll[i] = True
                    tief_ist_hl = False
            letztes_tief = preis

        if hoch_ist_hh is True and tief_ist_hl is True:
            aktueller_trend = 1
        elif hoch_ist_hh is False and tief_ist_hl is False:
            aktueller_trend = -1
        trend[i] = aktueller_trend

    return {"hh": hh, "hl": hl, "lh": lh, "ll": ll, "trend": trend}


def struktur_ereignisse(
    df: pd.DataFrame,
    *,
    strength: int = STANDARD_STRENGTH,
    serie: SwingSerie | None = None,
    detect_timeframe: str = "1m",
    min_bruch_atr: float = MIN_BRUCH_ATR,
) -> list[Ereignis]:
    """BOS- und CHoCH-Ereignisse in einem Vorwaertsdurchlauf.

    Erwartet einen mit ``compute_indicators`` vorbereiteten Rahmen (braucht
    ``atr``).
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError("struktur_ereignisse braucht die atr-Spalte.")

    if serie is None:
        serie = swing_serie(df, strength=strength)
    labels = _struktur_labels(serie)
    trend = labels["trend"]

    closes = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    n = len(df)

    hoch_preis, hoch_ursprung = serie.letzte_swings("hoch")
    tief_preis, tief_ursprung = serie.letzte_swings("tief")

    ereignisse: list[Ereignis] = []
    zuletzt_gebrochen_hoch = -1
    zuletzt_gebrochen_tief = -1

    for i in range(1, n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        puffer = min_bruch_atr * a

        # Bruch nach oben: Schluss ueber dem aktiven Swing-Hoch.
        h = hoch_preis[i]
        if np.isfinite(h) and closes[i] > h + puffer:
            ursprung = int(hoch_ursprung[i])
            if ursprung != zuletzt_gebrochen_hoch:
                zuletzt_gebrochen_hoch = ursprung
                typ = "bos" if trend[i] >= 0 else "choch"
                ereignisse.append(
                    Ereignis(
                        pattern_type=f"{typ}_bullish",
                        pattern_variant="close",
                        detect_timeframe=detect_timeframe,
                        direction=1,
                        entstehung_idx=ursprung,
                        bestaetigung_idx=min(ursprung + strength, i),
                        verfuegbar_idx=i,
                        merkmale={
                            "level_1": round(float(h), 4),
                            "level_neckline": round(float(h), 4),
                            "bruch_atr": round(float((closes[i] - h) / a), 3),
                            "trend_vor_bruch": int(trend[i]),
                            "swing_alter_bars": int(i - ursprung),
                        },
                    )
                )

        # Bruch nach unten.
        t = tief_preis[i]
        if np.isfinite(t) and closes[i] < t - puffer:
            ursprung = int(tief_ursprung[i])
            if ursprung != zuletzt_gebrochen_tief:
                zuletzt_gebrochen_tief = ursprung
                typ = "bos" if trend[i] <= 0 else "choch"
                ereignisse.append(
                    Ereignis(
                        pattern_type=f"{typ}_bearish",
                        pattern_variant="close",
                        detect_timeframe=detect_timeframe,
                        direction=-1,
                        entstehung_idx=ursprung,
                        bestaetigung_idx=min(ursprung + strength, i),
                        verfuegbar_idx=i,
                        merkmale={
                            "level_1": round(float(t), 4),
                            "level_neckline": round(float(t), 4),
                            "bruch_atr": round(float((t - closes[i]) / a), 3),
                            "trend_vor_bruch": int(trend[i]),
                            "swing_alter_bars": int(i - ursprung),
                        },
                    )
                )

    return ereignisse


def struktur_spalten(
    df: pd.DataFrame, *, strength: int = STANDARD_STRENGTH
) -> pd.DataFrame:
    """HH/HL/LH/LL und die laufende Trendlage als Spalten - fuer den Kontext
    anderer Ereignisse (``trend_context`` im Plan).
    """
    serie = swing_serie(df, strength=strength)
    labels = _struktur_labels(serie)
    return pd.DataFrame(
        {
            "struktur_hh": labels["hh"],
            "struktur_hl": labels["hl"],
            "struktur_lh": labels["lh"],
            "struktur_ll": labels["ll"],
            "struktur_trend": labels["trend"],
        },
        index=df.index,
    )


__all__ = [
    "MIN_BRUCH_ATR",
    "struktur_ereignisse",
    "struktur_spalten",
]
