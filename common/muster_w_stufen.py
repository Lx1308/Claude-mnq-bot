"""Die Bestaetigungsleiter nach dem zweiten Boden.

DIE FRAGE
---------
Nach dem zweiten Boden eines W steigt der Kurs - oder er bricht durch. Frueh
einsteigen heisst viel Restpotential bei wenig Bestaetigung; spaet einsteigen
heisst umgekehrt. Wo dazwischen der wirtschaftlich beste Punkt liegt, ist
eine EMPIRISCHE Frage, keine Entwurfsentscheidung.

Dieses Modul legt deshalb keine Bestaetigung fest. Es baut eine **Leiter**:
mehrere Einstiegszeitpunkte je Muster, jeder einzeln messbar. Welche Sprosse
die beste ist, sagen die Daten.

ZWEI LEITERN, WEIL ES ZWEI FRAGEN SIND
--------------------------------------
**Weg-Stufen** (``weg_stufen``) - der Kurs hat einen Anteil x der Strecke vom
zweiten Boden zur Nackenlinie zurueckgelegt. Parameterfrei und genau die
Achse, um die es wirtschaftlich geht: was schon gelaufen ist, ist als Gewinn
nicht mehr zu holen.

**Struktur-Stufen** (``struktur_stufen``) - die s-te abgeschlossene
Aufwaertsbewegung im Sinne eines Zickzacks. Naeher an dem, was ein Mensch
"erste, zweite, dritte Bestaetigung" nennt, aber mit einem Parameter (der
Mindestbewegung) behaftet, der mitgemessen und nicht gesetzt wird.

Beide werden ausgewertet. Wenn sie dasselbe sagen, ist der Befund robuster;
wenn nicht, ist der Unterschied selbst das Ergebnis.

WAS EINE SPROSSE UNGUELTIG MACHT
--------------------------------
Faellt der Kurs unter den zweiten Boden, ist die untere W-Linie gebrochen.
Alle Sprossen, die danach erreicht wuerden, zaehlen nicht mehr - wer dort
einstiege, handelte kein W mehr, sondern einen Abwaertsausbruch. Der
Erkenner meldet in dem Fall spaeter ohnehin einen neuen Kandidaten mit
tieferem zweitem Boden; der bekommt seine eigene Leiter.

Das ist Laurins Punkt vom 03.09.2026 woertlich: *"Wenn der Kurs nach einem
vermeintlichen zweiten Boden noch deutlich weiter faellt, darf die vorherige
Kerze nicht einfach rueckwirkend als endgueltiger zweiter Boden behandelt
werden."*

KEIN LOOKAHEAD
--------------
Jede Sprosse liegt bei oder nach ``bestaetigt_idx`` des Musters. Zu diesem
Zeitpunkt sind zweiter Boden (laufendes Minimum), Nackenlinie (laufendes
Maximum vor dem Ruecklauf) und ATR bekannt - der Erkenner hat sie mit genau
diesen Kerzen gebildet. Die Sprossenhoehen folgen daraus, nicht aus dem
spaeteren Verlauf. Gehandelt wird zur Eroeffnung der FOLGEKERZE.

Die Zukunft wird ausschliesslich zum Messen des Ausgangs benutzt, nie zum
Bestimmen des Einstiegs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.ereignisse.barrieren import NICHT_ERREICHT, erste_beruehrung

#: Anteile der Strecke vom zweiten Boden zur Nackenlinie.
#:
#: Die unterste Sprosse liegt bei 15 % und damit auf der Bestaetigung, die
#: der Erkenner ohnehin verlangt (``patterns.doppelboden.bestaetigung_anteil``).
#: Frueher waere nicht handelbar: dort steht der zweite Boden noch nicht fest.
#: Die oberste liegt AUF der Nackenlinie - der klassische Ausbruchseinstieg,
#: der damit im selben Raster mitgemessen wird.
WEG_STUFEN: tuple[float, ...] = (0.15, 0.25, 0.35, 0.45, 0.55, 0.70, 0.85, 1.00)

#: Mindestbewegung eines Zickzack-Schenkels, Anteil der Musterhoehe. Zwei
#: Werte, damit sichtbar wird, ob das Ergebnis daran haengt.
ZICKZACK_ANTEILE: tuple[float, ...] = (0.10, 0.20)

#: Hoechste Struktur-Stufe, die gezaehlt wird.
MAX_STRUKTUR_STUFEN = 6


@dataclass(frozen=True)
class Leiter:
    """Erreichte Sprossen je Muster.

    ``erreicht`` ist ``(anzahl_muster, anzahl_stufen)`` und enthaelt den
    Index der Kerze, in der die Sprosse erreicht wurde, sonst ``-1``.
    ``einstieg`` ist ``erreicht + 1`` (Eroeffnung der Folgekerze), ebenfalls
    ``-1`` wo die Sprosse ausfiel.
    """

    stufen: tuple[float, ...]
    erreicht: np.ndarray            # int64, -1 = nicht erreicht
    einstieg: np.ndarray            # int64, -1 = nicht erreicht
    bruch: np.ndarray               # int64, Kerze des Bruchs unter tief2, -1 = keiner

    def __post_init__(self) -> None:
        if self.erreicht.shape != self.einstieg.shape:
            raise ValueError("erreicht und einstieg muessen gleich geformt sein.")
        if self.erreicht.shape[1] != len(self.stufen):
            raise ValueError(
                f"{self.erreicht.shape[1]} Spalten fuer {len(self.stufen)} Stufen."
            )

    @property
    def anzahl(self) -> int:
        return self.erreicht.shape[0]

    def quote(self) -> np.ndarray:
        """Anteil der Muster, die jede Sprosse erreicht haben."""
        if self.anzahl == 0:
            return np.zeros(len(self.stufen))
        return (self.erreicht >= 0).mean(axis=0)


def weg_stufen(
    df: pd.DataFrame,
    start_idx: np.ndarray,
    tief2: np.ndarray,
    nackenlinie: np.ndarray,
    *,
    stufen: tuple[float, ...] = WEG_STUFEN,
    horizont: int,
) -> Leiter:
    """Wann jedes Muster welchen Anteil der Strecke zurueckgelegt hat.

    ``start_idx`` ist die Kerze, ab der gesucht wird - der
    Bestaetigungsindex des Erkenners. ``tief2`` und ``nackenlinie`` sind die
    beiden Preisniveaus des Musters.

    Eine Sprosse gilt als erreicht, wenn das HOCH einer Kerze das Niveau
    beruehrt, und nur solange der Kurs nicht vorher unter ``tief2``
    gefallen ist.
    """
    start_idx = np.asarray(start_idx, dtype=np.int64)
    tief2 = np.asarray(tief2, dtype=float)
    nackenlinie = np.asarray(nackenlinie, dtype=float)
    if not (len(start_idx) == len(tief2) == len(nackenlinie)):
        raise ValueError("start_idx, tief2 und nackenlinie muessen gleich lang sein.")
    if any(not 0.0 < s <= 1.5 for s in stufen):
        raise ValueError("Stufen sind Anteile der Strecke, 0 < x <= 1.5.")
    if list(stufen) != sorted(stufen):
        raise ValueError("Stufen muessen aufsteigend sein.")

    hoehe = nackenlinie - tief2
    if np.any(hoehe <= 0):
        raise ValueError("Nackenlinie muss ueber dem zweiten Boden liegen.")

    # Der Bruch unter den zweiten Boden beendet das Muster. Strikt kleiner:
    # ein Retest auf demselben Kurs ist noch kein Bruch.
    bruch_zeit = erste_beruehrung(
        df, start_idx, tief2 - 1e-9, horizont, nach_oben=False)

    erreicht = np.full((len(start_idx), len(stufen)), -1, dtype=np.int64)
    for k, anteil in enumerate(stufen):
        zeit = erste_beruehrung(
            df, start_idx, tief2 + anteil * hoehe, horizont, nach_oben=True)
        gueltig = (zeit != NICHT_ERREICHT) & (zeit < bruch_zeit)
        erreicht[gueltig, k] = start_idx[gueltig] + zeit[gueltig] - 1

    einstieg = np.where(erreicht >= 0, erreicht + 1, -1)
    # Ein Einstieg jenseits der Reihe ist keiner.
    einstieg = np.where(einstieg >= len(df), -1, einstieg)
    erreicht = np.where(einstieg < 0, -1, erreicht)

    bruch = np.where(bruch_zeit == NICHT_ERREICHT, -1,
                     start_idx + bruch_zeit - 1)
    return Leiter(stufen=stufen, erreicht=erreicht, einstieg=einstieg,
                  bruch=bruch)


def struktur_stufen(
    df: pd.DataFrame,
    start_idx: np.ndarray,
    tief2: np.ndarray,
    nackenlinie: np.ndarray,
    *,
    zickzack_anteil: float,
    max_stufen: int = MAX_STRUKTUR_STUFEN,
    horizont: int,
) -> Leiter:
    """Wann jedes Muster die s-te abgeschlossene Aufwaertsbewegung hatte.

    Ein Zickzack mit Mindestbewegung ``zickzack_anteil`` der Musterhoehe:
    Ein Schenkel nach oben gilt als abgeschlossen, sobald der Kurs vom
    letzten Zwischentief um mindestens diesen Anteil gestiegen ist UND das
    Hoch des vorigen Schenkels ueberschritten hat. Der naechste Schenkel
    beginnt erst nach einer echten KORREKTUR - der Kurs muss um dieselbe
    Mindestbewegung vom erreichten Hoch zurueckkommen.

    Ohne diese Korrekturbedingung wuerde eine durchlaufende Rally jede
    Kerze als eigene "Bestaetigung" zaehlen, und die Leiter waere nur eine
    umstaendliche Schreibweise fuer ``weg_stufen``.

    Das ist Laurins "erste, zweite, dritte bestaetigende Aufwaertsbewegung" -
    ausdruecklich NICHT "gruene Kerzen zaehlen": eine einzelne gruene Kerze
    schliesst keinen Schenkel ab, und drei kleine Kerzen hintereinander
    ebensowenig, wenn sie zusammen unter der Mindestbewegung bleiben.

    Anders als ``weg_stufen`` laesst sich das nicht als Preisschwelle
    ausdruecken - der Zustand haengt vom Pfad ab. Deshalb eine Schleife je
    Muster; sie laeuft nur ueber den Horizont und bricht beim Bruch ab.
    """
    start_idx = np.asarray(start_idx, dtype=np.int64)
    tief2 = np.asarray(tief2, dtype=float)
    nackenlinie = np.asarray(nackenlinie, dtype=float)
    if not 0.0 < zickzack_anteil < 1.0:
        raise ValueError("zickzack_anteil ist ein Anteil der Musterhoehe.")
    if max_stufen < 1:
        raise ValueError("max_stufen muss mindestens 1 sein.")

    h = df["high"].to_numpy(dtype=float)
    l = df["low"].to_numpy(dtype=float)
    n = len(df)
    hoehe = nackenlinie - tief2

    erreicht = np.full((len(start_idx), max_stufen), -1, dtype=np.int64)
    bruch = np.full(len(start_idx), -1, dtype=np.int64)

    for i in range(len(start_idx)):
        s0 = int(start_idx[i])
        mindest = zickzack_anteil * hoehe[i]
        if mindest <= 0:
            continue
        tief_marke = tief2[i]          # Tief, von dem der laufende Schenkel zaehlt
        letztes_hoch = -np.inf         # Hoch des zuletzt abgeschlossenen Schenkels
        lauf_hoch = -np.inf            # Hoch des laufenden Schenkels
        gipfel = -np.inf               # hoechster Punkt seit dem Schenkelende
        seit_gipfel_tief = np.inf      # tiefster Punkt SEIT diesem Gipfel
        steigend = True
        stufe = 0
        for j in range(s0, min(s0 + horizont, n)):
            if l[j] < tief2[i]:
                bruch[i] = j
                break
            if steigend:
                if h[j] > lauf_hoch:
                    lauf_hoch = h[j]
                # Schenkel abgeschlossen: weit genug ueber dem Ausgangstief
                # UND ueber dem Hoch des vorigen Schenkels.
                if (lauf_hoch - tief_marke >= mindest
                        and lauf_hoch > letztes_hoch):
                    erreicht[i, stufe] = j
                    stufe += 1
                    if stufe >= max_stufen:
                        break
                    steigend = False
                    gipfel = lauf_hoch
                    seit_gipfel_tief = l[j]
                elif l[j] < tief_marke:
                    tief_marke = l[j]
            else:
                # Korrektur. Gemessen wird der Rueckgang vom laufenden
                # GIPFEL - steigt der Kurs weiter, wandert der Gipfel mit und
                # die Zaehlung beginnt von vorn.
                #
                # Ohne das Zuruecksetzen zaehlte eine durchlaufende Rally
                # jeden weiteren Anstieg als "Korrektur" und damit als
                # naechste Bestaetigung: der Abstand zwischen mitwanderndem
                # Gipfel und stehengebliebenem Tief wuchs von selbst ueber
                # die Mindestbewegung.
                if h[j] > gipfel:
                    gipfel = h[j]
                    seit_gipfel_tief = l[j]
                elif l[j] < seit_gipfel_tief:
                    seit_gipfel_tief = l[j]
                if gipfel - seit_gipfel_tief >= mindest:
                    letztes_hoch = gipfel
                    tief_marke = seit_gipfel_tief
                    lauf_hoch = -np.inf
                    steigend = True

    einstieg = np.where(erreicht >= 0, erreicht + 1, -1)
    einstieg = np.where(einstieg >= n, -1, einstieg)
    erreicht = np.where(einstieg < 0, -1, erreicht)
    return Leiter(stufen=tuple(range(1, max_stufen + 1)),
                  erreicht=erreicht, einstieg=einstieg, bruch=bruch)


__all__ = ["Leiter", "weg_stufen", "struktur_stufen",
           "WEG_STUFEN", "ZICKZACK_ANTEILE", "MAX_STRUKTUR_STUFEN"]
