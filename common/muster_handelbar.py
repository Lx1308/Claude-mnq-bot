"""Umkehrmuster, wie sie LIVE handelbar sind - nicht wie sie im Rueckblick
aussehen.

WARUM ES DIESES MODUL GIBT
--------------------------
``common/muster_serie.py`` verlangt, dass BEIDE Extrema eines Doppelbodens
bestaetigte Swingpunkte sind. Ein Swingtief mit Staerke ``s`` gilt aber erst
``s`` Kerzen spaeter als bestaetigt. Bei den Staerken, die Muster in
handelbarer Groesse finden (20 bis 45 auf Minutenkerzen), heisst das: das
zweite Tief ist erst 20 bis 45 Kerzen spaeter bekannt. Ein Einstieg an der
ersten gruenen Kerze nach dem Tief - der Punkt, an dem ein Mensch tatsaechlich
kauft - waere damit unmoeglich.

Die Messung vom 02.09.2026 hat gezeigt, was daraus folgt: der Einstieg landete
im Median bei 69 % der Strecke vom Tief zur Nackenlinie, mit 3,2 Punkten Rest
zum Ziel gegen 11,7 Punkte Risiko. Das ist kein Trade, den jemand eingehen
wuerde, und jede Messung daran misst eine Strohpuppe.

WAS HIER ANDERS IST
-------------------
Live sieht ein Trader das hier:

    1. Ein Tief, das laengst bestaetigt ist          -> die untere Linie
    2. Ein Hoch darueber                             -> die obere Linie
    3. Der Kurs faellt an die untere Linie zurueck   -> das zweite Tief
    4. Gruene Kerzen                                 -> der Ausloeser

Nur Schritt 1 braucht Bestaetigung, und die liegt in der Vergangenheit. Die
Schritte 2 bis 4 sind im Moment ihres Eintretens sichtbar. Damit liegt der
Einstieg dort, wo er in der Praxis liegt: im Median bei 21 % der Musterhoehe.

DER LOOKAHEAD, DER HIER LAUERT
------------------------------
Die Nackenlinie muss das **laufende** Hoch bis zum Ruecklauf sein, nicht das
Hoch ueber das ganze Suchfenster. Die erste Fassung nahm Letzteres und fiel
deshalb durch die Abschneide-Probe (2.459 Abweichungen von 8.540). Wer hier
etwas aendert, laesst ``test_muster_handelbar.py`` laufen - der Test schneidet
die Reihe in der Mitte durch und verlangt identische Funde.

ALLES IN PROZENT DER MUSTERHOEHE
--------------------------------
Ein Stop "15 Punkte unter dem Tief" bedeutet bei einem 70-Punkte-Muster etwas
anderes als bei einem 20-Punkte-Muster. Massstab ist deshalb ueberall die
Hoehe ``H = Nackenlinie - Tief``. Dieses Modul liefert die Linien; wer daraus
Stop und Ziel setzt, rechnet in Anteilen von ``H``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv
from common.structure import find_swing_points

#: Vorgaben. Die Staerke steuert die Groessenordnung: 20 findet auf
#: Minutenkerzen Muster von rund 37 Punkten Hoehe, 45 solche von rund 51.
STANDARD_STRENGTH = 30
STANDARD_MAX_DAUER = 600
STANDARD_MIN_HOEHE_ATR = 2.0
STANDARD_RUECKLAUF_TOLERANZ = 0.15
STANDARD_UNTERSCHREITEN = 0.10
STANDARD_MAX_WARTEN = 30


@dataclass(frozen=True)
class HandelbaresMuster:
    """Ein Doppelboden mit dem Zeitpunkt, an dem er handelbar wird."""

    erst_idx: int          #: Kerze des ersten (bestaetigten) Tiefs
    hoch_idx: int          #: Kerze des Zwischenhochs
    zweit_idx: int         #: Kerze, die an die untere Linie zurueckkam
    einstieg_idx: int      #: die EROEFFNUNG dieser Kerze ist der Einstieg
    tief: float            #: untere Linie - Preis des ersten Tiefs
    zweites_tief: float    #: tatsaechlich erreichtes Tief beim Ruecklauf
    nackenlinie: float     #: obere Linie - laufendes Hoch bis zum Ruecklauf
    atr: float             #: ATR am Einstieg
    gruen: int             #: wie viele gruene Kerzen abgewartet wurden

    @property
    def hoehe(self) -> float:
        """Musterhoehe - der Massstab fuer Stop und Ziel."""
        return self.nackenlinie - self.tief

    @property
    def dauer_bars(self) -> int:
        """Kerzen zwischen den beiden Tiefs."""
        return self.zweit_idx - self.erst_idx

    def stop(self, anteil: float) -> float:
        """Stop ``anteil`` der Musterhoehe UNTER dem Tief.

        ``anteil`` muss positiv sein: ein Stop im Muster waere charttechnisch
        sinnlos - er laege dort, wo das Muster noch intakt ist.
        """
        if anteil <= 0:
            raise ValueError(
                "Der Stop gehoert unter das Tief; ein Anteil <= 0 laege im "
                "Muster, wo es noch gar nicht gebrochen ist."
            )
        return self.tief - anteil * self.hoehe

    def ziel(self, anteil: float) -> float:
        """Ziel ``anteil`` der Musterhoehe vor der Nackenlinie.

        Positiver ``anteil`` bleibt davor (Laurins Vorgehen: etwas Sicherheit
        lassen), negativer geht darueber hinaus - das klassische Messziel ist
        ``anteil = -1.0``.
        """
        return self.nackenlinie - anteil * self.hoehe


def finde_handelbare_doppelboeden(
    df: pd.DataFrame,
    atr: np.ndarray | pd.Series,
    *,
    strength: int = STANDARD_STRENGTH,
    n_gruen: int = 1,
    max_dauer: int = STANDARD_MAX_DAUER,
    min_hoehe_atr: float = STANDARD_MIN_HOEHE_ATR,
    ruecklauf_toleranz: float = STANDARD_RUECKLAUF_TOLERANZ,
    unterschreiten_erlaubt: float = STANDARD_UNTERSCHREITEN,
    max_warten_gruen: int = STANDARD_MAX_WARTEN,
) -> list[HandelbaresMuster]:
    """Alle live handelbaren Doppelboeden der Reihe, in zeitlicher Ordnung.

    ``ruecklauf_toleranz`` und ``unterschreiten_erlaubt`` sind Anteile der
    Musterhoehe: wie nah der Kurs an die untere Linie zurueck muss, damit es
    als zweites Tief zaehlt, und wie weit er darunter darf, bevor das Muster
    als gebrochen gilt.
    """
    validate_ohlcv(df)
    if strength < 1:
        raise ValueError("strength muss mindestens 1 sein.")
    if n_gruen < 0:
        raise ValueError("n_gruen darf nicht negativ sein.")

    atr_werte = np.asarray(atr, dtype=float)
    if len(atr_werte) != len(df):
        raise ValueError(
            f"atr hat {len(atr_werte)} Werte, der Rahmen {len(df)} Kerzen."
        )

    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    n = len(df)
    ist_gruen = c > o

    punkte = find_swing_points(df, strength=strength)
    letzter = n - 1
    tiefs = sorted(
        ((letzter - p.bars_ago, p.price) for p in punkte if p.kind == "low"),
        key=lambda t: t[0],
    )

    funde: list[HandelbaresMuster] = []
    for erst_idx, tief in tiefs:
        # Ab hier ist das erste Tief bestaetigt - vorher weiss niemand, dass
        # es eines ist.
        bekannt = erst_idx + strength
        if bekannt >= n - 2:
            continue
        ende = min(erst_idx + max_dauer, n - 1)
        if ende - bekannt < 3:
            continue

        # Hoch und Ruecklauf in EINEM Vorwaertslauf. Die Nackenlinie ist das
        # laufende Hoch bis zu diesem Moment - nicht das spaetere Hoch des
        # ganzen Fensters. Genau daran haengt die Lookahead-Freiheit.
        nacken, hoch_idx, zweit_idx = -np.inf, -1, -1
        for j in range(erst_idx + 1, ende + 1):
            if h[j] > nacken:
                nacken, hoch_idx = h[j], j
            if j < bekannt or hoch_idx < 0:
                continue
            hoehe = nacken - tief
            if hoehe <= 0:
                continue
            a_j = atr_werte[j]
            if not np.isfinite(a_j) or a_j <= 0 or hoehe < min_hoehe_atr * a_j:
                continue                      # noch zu flach fuer ein Muster
            if l[j] < tief - unterschreiten_erlaubt * hoehe:
                break                         # untere Linie gebrochen
            if j > hoch_idx and l[j] <= tief + ruecklauf_toleranz * hoehe:
                zweit_idx = j
                break
        if zweit_idx < 0 or hoch_idx < 0:
            continue

        nacken = float(nacken)
        untergrenze = tief - unterschreiten_erlaubt * (nacken - tief)

        # Die gruenen Kerzen als Ausloeser.
        folge, einstieg = 0, -1
        grenze = min(zweit_idx + max_warten_gruen, n - 2)
        for j in range(zweit_idx, grenze + 1):
            if l[j] < untergrenze:
                break                         # zwischendurch doch gebrochen
            folge = folge + 1 if ist_gruen[j] else 0
            if folge >= n_gruen:
                einstieg = j + 1
                break
        if einstieg < 0 or einstieg >= n:
            continue

        a_e = atr_werte[einstieg]
        if not np.isfinite(a_e) or a_e <= 0:
            continue

        funde.append(
            HandelbaresMuster(
                erst_idx=erst_idx,
                hoch_idx=hoch_idx,
                zweit_idx=zweit_idx,
                einstieg_idx=einstieg,
                tief=float(tief),
                zweites_tief=float(l[zweit_idx]),
                nackenlinie=nacken,
                atr=float(a_e),
                gruen=n_gruen,
            )
        )

    funde.sort(key=lambda f: f.einstieg_idx)
    return funde


__all__ = [
    "HandelbaresMuster",
    "STANDARD_MAX_DAUER",
    "STANDARD_MAX_WARTEN",
    "STANDARD_MIN_HOEHE_ATR",
    "STANDARD_RUECKLAUF_TOLERANZ",
    "STANDARD_STRENGTH",
    "STANDARD_UNTERSCHREITEN",
    "finde_handelbare_doppelboeden",
]
