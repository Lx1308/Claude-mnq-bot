"""Equal Highs / Equal Lows als Serie - der Liquiditaetspool.

ICT/SMC-Kern und die Vorstufe zum Sweep: zwei oder mehr Swings auf praktisch
demselben Preis. Unter einer Reihe gleicher Tiefs liegen die Stops der
Kaeufer, ueber gleichen Hochs die der Verkaeufer. Ein Markt, der solche
Marken stehen laesst, holt sie oft ab - **ob er das haeufiger tut, als der
Zufall erwarten laesst, ist genau die Frage dieser Untersuchung** und wird
hier nicht behauptet.

ABGRENZUNG ZUM DOPPELTOP
------------------------
Beide bestehen aus zwei aehnlichen Swings. Der Unterschied liegt in dem, was
dazwischen passiert:

* **Doppeltop/-boden** (``muster_serie.py``): verlangt ein Zwischental von
  mindestens 1,0 x ATR. Es ist eine **Umkehrformation**.
* **Equal Highs/Lows** (hier): stellt keine Anforderung an das Dazwischen.
  Es ist ein **Liquiditaetspool** - eine Marke, an der Orders vermutet werden.

Ein enges Doppeltop mit tiefem Zwischental ist beides. Die beiden Erkenner
melden dann zwei Zeilen; welche Sicht traegt, ist eine Messfrage (siehe
``basis.Ereignis.key`` und Plan Abschnitt 12.1).

DEFINITION (aus ``market_primitives.detect_equal_highs_lows``)
-------------------------------------------------------------
Zwei bestaetigte Swings gleicher Art gelten als "gleich", wenn ihr
Preisabstand unter der Toleranz liegt:

    toleranz = max(toleranz_ticks x tick_size, toleranz_atr x ATR)

Der punktuelle Erkenner clustert ueber ein Lookback-Fenster und mittelt die
Preise. Hier wird **jede neue Bestaetigung, die zu einem laufenden Cluster
passt, als eigenes Ereignis gemeldet** - mit ``anzahl_swings`` als Merkmal.
Grund: der dritte gleiche Hochpunkt ist ein anderer Zustand als der zweite,
und wer nur den Cluster am Ende meldet, kann das nicht auseinanderhalten.
Genau dieselbe Logik wie beim n-ten Test eines Niveaus (``niveaus.py``).

KEIN LOOKAHEAD
--------------
Ein Cluster waechst nur nach vorn. Das Ereignis steht auf der Bestaetigung
des **juengsten** beteiligten Swings (``p + strength``); der Mittelpreis
rechnet ausschliesslich aus den bis dahin bekannten Swings.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.ereignisse.swings import STANDARD_STRENGTH, SwingSerie, swing_serie
from common.indicators import validate_ohlcv

#: Toleranz in Ticks - wie im punktuellen Erkenner.
TOLERANZ_TICKS = 4.0

#: Toleranz in ATR. Es gilt die groessere der beiden - in ruhigen Phasen
#: dominiert die Tickgrenze, in bewegten die ATR-Grenze.
TOLERANZ_ATR = 0.20

#: Wie weit zurueck ein Cluster reichen darf. Liegen die gleichen Hochs zwei
#: Handelstage auseinander, ist der Zusammenhang nicht mehr plausibel.
LOOKBACK = 120

#: Wie viele gleiche Swings hoechstens in einem Cluster gefuehrt werden. Nur
#: eine Obergrenze fuer die Merkmale, keine inhaltliche Schwelle.
MAX_CLUSTER = 8


def _eq_fuer_art(
    serie: SwingSerie,
    atr: np.ndarray,
    *,
    art: str,
    tick_size: float,
    toleranz_ticks: float,
    toleranz_atr: float,
    lookback: int,
    detect_timeframe: str,
) -> list[Ereignis]:
    """Ein Vorwaertsdurchlauf ueber die bestaetigten Swings einer Art."""
    if art == "hoch":
        bestaetigt = serie.hoch_bestaetigt
        preise = serie.hoch_preis
        ursprung = serie.hoch_ursprung_idx
        richtung = -1        # gleiche Hochs -> Liquiditaet oben, Abholung nach oben
        name = "equal_highs"
    else:
        bestaetigt = serie.tief_bestaetigt
        preise = serie.tief_preis
        ursprung = serie.tief_ursprung_idx
        richtung = 1
        name = "equal_lows"

    idx = np.nonzero(bestaetigt)[0]
    ereignisse: list[Ereignis] = []

    # Laufender Cluster: die Bestaetigungsindizes und Preise der zuletzt
    # gesehenen gleichen Swings. Faellt ein neuer Swing aus der Toleranz oder
    # aus dem Lookback, beginnt ein neuer Cluster.
    cluster_idx: list[int] = []
    cluster_preis: list[float] = []

    for i in idx:
        i = int(i)
        p = float(preise[i])
        a = atr[i]
        if not (np.isfinite(p) and np.isfinite(a) and a > 0):
            cluster_idx, cluster_preis = [i], [p]
            continue

        toleranz = max(toleranz_ticks * tick_size, toleranz_atr * float(a))

        # Zu alte Mitglieder verfallen - gemessen am Ursprung, nicht an der
        # Bestaetigung: die Marke liegt dort, wo das Extrem war.
        while cluster_idx and (
            int(ursprung[i]) - int(ursprung[cluster_idx[0]]) > lookback
        ):
            cluster_idx.pop(0)
            cluster_preis.pop(0)

        passt = bool(cluster_preis) and all(
            abs(p - q) <= toleranz for q in cluster_preis
        )
        if not passt:
            cluster_idx, cluster_preis = [i], [p]
            continue

        cluster_idx.append(i)
        cluster_preis.append(p)
        if len(cluster_idx) > MAX_CLUSTER:
            cluster_idx.pop(0)
            cluster_preis.pop(0)

        mittel = float(np.mean(cluster_preis))
        streuung = float(np.max(cluster_preis) - np.min(cluster_preis))
        erster = int(ursprung[cluster_idx[0]])

        ereignisse.append(
            Ereignis(
                pattern_type=name,
                pattern_variant=f"n{len(cluster_idx)}",
                detect_timeframe=detect_timeframe,
                direction=richtung,
                entstehung_idx=erster,
                bestaetigung_idx=i,
                verfuegbar_idx=i,
                merkmale={
                    "level_1": round(float(cluster_preis[0]), 4),
                    "level_2": round(p, 4),
                    "level_neckline": round(mittel, 4),
                    "anzahl_swings": len(cluster_idx),
                    "streuung_punkte": round(streuung, 4),
                    "streuung_atr": round(streuung / float(a), 4),
                    "toleranz_punkte": round(toleranz, 4),
                    "spanne_bars": int(ursprung[i]) - erster,
                },
            )
        )

    return ereignisse


def eqhl_ereignisse(
    df: pd.DataFrame,
    *,
    detect_timeframe: str = "1m",
    strength: int = STANDARD_STRENGTH,
    tick_size: float = 0.25,
    toleranz_ticks: float = TOLERANZ_TICKS,
    toleranz_atr: float = TOLERANZ_ATR,
    lookback: int = LOOKBACK,
    serie: SwingSerie | None = None,
) -> list[Ereignis]:
    """Equal Highs und Equal Lows als Ereignisse.

    Erwartet einen mit ``compute_indicators`` vorbereiteten Rahmen (``atr``).
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError("eqhl_ereignisse braucht die atr-Spalte.")

    if serie is None:
        serie = swing_serie(df, strength=strength)
    atr = df["atr"].to_numpy(dtype=float)

    ereignisse: list[Ereignis] = []
    for art in ("hoch", "tief"):
        ereignisse.extend(
            _eq_fuer_art(
                serie, atr, art=art, tick_size=tick_size,
                toleranz_ticks=toleranz_ticks, toleranz_atr=toleranz_atr,
                lookback=lookback, detect_timeframe=detect_timeframe,
            )
        )
    ereignisse.sort(key=lambda e: (e.verfuegbar_idx, -e.direction))
    return ereignisse


EQHL_SPALTEN = (
    "eqh", "eqh_niveau", "eqh_anzahl",
    "eql", "eql_niveau", "eql_anzahl",
)


def eqhl_spalten(
    df: pd.DataFrame,
    *,
    strength: int = STANDARD_STRENGTH,
    **schwellen,
) -> pd.DataFrame:
    """Equal Highs/Lows als Spalten.

    ``eqh_niveau`` wird **fortgeschrieben**: der Pool bleibt bestehen, bis ein
    neuer ihn ersetzt. So laesst er sich als Ziel- oder Stopreferenz benutzen,
    ohne dass der Aufrufer selbst nachhalten muss.
    """
    n = len(df)
    spalten = {
        "eqh": np.zeros(n, dtype=bool),
        "eqh_niveau": np.full(n, np.nan),
        "eqh_anzahl": np.zeros(n, dtype=np.int16),
        "eql": np.zeros(n, dtype=bool),
        "eql_niveau": np.full(n, np.nan),
        "eql_anzahl": np.zeros(n, dtype=np.int16),
    }
    for e in eqhl_ereignisse(df, strength=strength, **schwellen):
        i = e.verfuegbar_idx
        p = "eqh" if e.pattern_type == "equal_highs" else "eql"
        spalten[p][i] = True
        spalten[f"{p}_niveau"][i] = e.merkmale["level_neckline"]
        spalten[f"{p}_anzahl"][i] = e.merkmale["anzahl_swings"]

    rahmen = pd.DataFrame(spalten, index=df.index)
    for p in ("eqh", "eql"):
        rahmen[f"{p}_niveau"] = rahmen[f"{p}_niveau"].ffill()
    return rahmen[list(EQHL_SPALTEN)]


__all__ = [
    "EQHL_SPALTEN",
    "LOOKBACK",
    "MAX_CLUSTER",
    "TOLERANZ_ATR",
    "TOLERANZ_TICKS",
    "eqhl_ereignisse",
    "eqhl_spalten",
]
