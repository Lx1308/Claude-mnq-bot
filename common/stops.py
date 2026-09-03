"""Der Anfangsstop unter dem letzten Tief - Laurins Regel.

WOHER
-----
Laurin, 03.09.2026, an einem FVG-Chart: *"das SL immer unter das letzte Tief
legen und zudem ca 15 Punkte Abstand lassen. Haette es hier bei 29260 gelegt,
aber max 100 Punkte SL-Abstand."*

Drei Dinge stecken darin, und alle drei sind besser als ein ATR-Vielfaches:

1. **Der Stop haengt an der Struktur**, nicht an der Volatilitaet. Unter dem
   letzten Tief liegt der Punkt, an dem die Annahme widerlegt ist - ein ATR
   unter dem Einstieg liegt irgendwo.
2. **Ein Puffer darunter.** Genau auf dem Tief wird man von jedem Docht
   erwischt, der das Tief noch einmal testet.
3. **Eine Obergrenze.** Liegt das letzte Tief weit weg, waere das Risiko
   sonst unbegrenzt; ein Trade mit 300 Punkten Risiko ist keiner mehr.

Alle drei Zahlen sind Beispiele und werden gerastert, nicht gesetzt.

WAS "DAS LETZTE TIEF" HEISST
----------------------------
Das letzte **bestaetigte** Swingtief vor dem Einstieg. Bestaetigt heisst: es
war das tiefste seines Fensters, und das Fenster ist abgeschlossen - ein Tief
von vor drei Kerzen ist bei Staerke 6 noch keins, weil es noch tiefer werden
kann. Ohne diese Verzoegerung waere Zukunftswissen im Spiel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.structure import find_swing_points

#: Puffer unter dem letzten Tief, in Punkten. Laurins 15 sind einer davon.
PUFFER_PKT: tuple[float, ...] = (5.0, 10.0, 15.0, 20.0, 30.0)

#: Groesster zugelassener Abstand zwischen Einstieg und Stop, in Punkten.
MAX_ABSTAND_PKT = 100.0

#: Kleinster sinnvoller Abstand. Darunter ist es kein Stop, sondern Spread.
MIN_ABSTAND_PKT = 2.0

STAERKE = 6
BLOCK_KERZEN = 200_000


def letzte_tiefs(df: pd.DataFrame, *, staerke: int = STAERKE) -> np.ndarray:
    """Fuer jede Kerze das letzte BESTAETIGTE Swingtief davor.

    Rueckgabe: Array der Laenge ``len(df)`` mit dem Kurs des jeweils letzten
    bestaetigten Tiefs, ``NaN`` wo es noch keins gibt.

    Ein Tief bei Index ``i`` ist erst ab ``i + staerke`` bekannt - vorher
    kann es noch tiefer werden. Genau diese Verzoegerung ist der Unterschied
    zwischen einer Regel und Zukunftswissen.
    """
    tief = df["low"].to_numpy(float)
    ergebnis = np.full(len(df), np.nan)

    gefunden: dict[int, float] = {}
    for start in range(0, len(df), BLOCK_KERZEN):
        ende = min(start + BLOCK_KERZEN + staerke, len(df))
        block = df.iloc[start:ende]
        if len(block) < 4 * staerke:
            continue
        letzter = len(block) - 1
        for punkt in find_swing_points(block, strength=staerke):
            if punkt.kind == "low":
                gefunden[start + (letzter - punkt.bars_ago)] = punkt.price

    if not gefunden:
        return ergebnis
    idx = np.array(sorted(gefunden), dtype=np.int64)
    kurs = np.array([gefunden[i] for i in idx], dtype=float)
    # Ab wann bekannt: staerke Kerzen nach dem Tief.
    bekannt = idx + staerke
    gueltig = bekannt < len(df)
    ergebnis[bekannt[gueltig]] = kurs[gueltig]
    # Nach vorn fortschreiben: bis zum naechsten Tief gilt dieses.
    fehlt = np.isnan(ergebnis)
    stelle = np.where(~fehlt, np.arange(len(df)), 0)
    np.maximum.accumulate(stelle, out=stelle)
    ergebnis = np.where(np.arange(len(df)) >= bekannt.min(),
                        ergebnis[stelle], np.nan)
    return ergebnis


def stop_unter_dem_tief(
    einstiegskurs: np.ndarray,
    letztes_tief: np.ndarray,
    *,
    puffer_pkt: float,
    max_abstand: float = MAX_ABSTAND_PKT,
    min_abstand: float = MIN_ABSTAND_PKT,
) -> tuple[np.ndarray, np.ndarray]:
    """Stopkurs und Maske der brauchbaren Trades.

    Der Stop liegt ``puffer_pkt`` unter dem letzten bestaetigten Tief. Liegt
    er weiter als ``max_abstand`` vom Einstieg weg, faellt der Trade heraus -
    er wird NICHT auf die Obergrenze gekuerzt.

    Das ist der Unterschied zwischen einer Regel und einer Verlegenheit: ein
    gekuerzter Stop haengt nicht mehr an der Struktur und misst etwas
    anderes als das, was er zu messen vorgibt.
    """
    if puffer_pkt < 0:
        raise ValueError("Der Puffer gehoert UNTER das Tief, also >= 0.")
    if max_abstand <= min_abstand:
        raise ValueError("max_abstand muss groesser als min_abstand sein.")

    stop = letztes_tief - puffer_pkt
    abstand = einstiegskurs - stop
    brauchbar = (
        np.isfinite(stop)
        & (abstand >= min_abstand)
        & (abstand <= max_abstand)
    )
    return stop, brauchbar


__all__ = ["letzte_tiefs", "stop_unter_dem_tief", "PUFFER_PKT",
           "MAX_ABSTAND_PKT", "MIN_ABSTAND_PKT"]
