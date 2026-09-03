"""Ausstieg ueber einen nachgezogenen Stop - ohne festes Ziel.

DIE IDEE, UND WOHER SIE KOMMT
-----------------------------
Laurin, 03.09.2026: *"Kein Ziel sondern nur trailing SL, denke das klappt
wesentlich besser weil die Logik dahinter einfacher is. Da koennte man ja
auch herausfinden welcher Prozentsatz sinnvoll ist, sodass eine kleine
Gegenkorrektur das nicht ausloest aber ein echter Einbruch da rein geht."*

Die Stufenmessung vom selben Tag hatte dafuer die Zahl geliefert, ohne dass
sie damals jemandem aufgefallen waere:

    MFE bis zum Ausstieg      0,79 R
    MFE ueber den Horizont    3,26 R

Die Bewegung WAR da - im Schnitt ueber drei R. Ein festes Ziel sammelt sie
nur nicht ein: liegt es nah, ist man mit einem R draussen, waehrend der Kurs
weiterlaeuft; liegt es weit, wird es nie erreicht. Ein nachgezogener Stop
laesst laufen und nimmt, was kommt.

ZWEI GROESSEN, NICHT EINE
-------------------------
Ein reiner Prozentsatz vom Gewinnhoch hat frueh ein Problem: steht der Trade
zwei Punkte im Plus, sind 20 % davon 0,4 Punkte - das loest der naechste Tick
aus. Deshalb braucht es beides:

    aktivierung   ab welchem Gewinn der Stop ueberhaupt nachgezogen wird
    rueckgabe     wie viel vom Gewinnhoch wieder abgegeben werden darf

Genau Laurins Frage in zwei Zahlen: die Aktivierung sorgt dafuer, dass eine
kleine Gegenkorrektur gar nicht erst in Reichweite kommt, die Rueckgabe
entscheidet, ab wann ein Rutsch ein echter Einbruch ist. Beide werden
gerastert, keine wird gesetzt.

WAS DER STOP TUT
----------------
Er geht nur nach oben, nie nach unten. Solange der Gewinn unter der
Aktivierung liegt, gilt der urspruengliche Stop unter dem zweiten Tief;
darueber gilt der hoehere von beiden.

DIE KONVENTIONEN
----------------
* Der Stop einer Kerze steht auf dem Gewinnhoch der Kerzen **davor**, nicht
  einschliesslich der laufenden. Genau so arbeitet eine echte Stop-Order: sie
  liegt auf einem Niveau, das aus abgeschlossenen Kerzen stammt.

  Das ist nicht nur realistischer, es ist auch die pessimistische Seite - und
  ich hatte es zuerst falsch herum. Nimmt man das Hoch der laufenden Kerze
  mit, steht der Stop hoeher, und eine Kerze, die von 100 auf 140 und zurueck
  auf 89 geht, wuerde als Ausstieg bei 132 gebucht statt beim echten Stop.
  Das ist ein Gewinn, den es nie gab.
* Gefuellt wird **auf dem Stopkurs**. Faellt eine Kerze mit einer Luecke
  darunter, waere die echte Fuellung schlechter; wie oft das vorkommt, wird
  als ``luecke_anteil`` ausgewiesen statt versteckt.
* Wer im Horizont nicht ausgestoppt wird, wird zum **Schlusskurs** der
  letzten Kerze bewertet - nicht mit null, das waere eine Erfindung.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv

#: Wie viel vom Gewinnhoch wieder abgegeben werden darf. Laurins 20 % sind
#: einer von sechs Werten, kein Vorgabewert.
RUECKGABE: tuple[float, ...] = (0.10, 0.20, 0.30, 0.40, 0.50, 0.65)

#: Ab welchem Gewinn der Stop nachgezogen wird, als Vielfaches des Risikos.
#: 0.0 heisst "sofort" - fuer den Vergleich mit drin, obwohl es der Wert ist,
#: bei dem jede Gegenkorrektur ausloest.
AKTIVIERUNG_R: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0, 1.5)

BLOCK = 20_000


@dataclass(frozen=True)
class Ausstieg:
    """Ergebnis je Trade. Alle Arrays haben die Laenge der Ereignisliste."""

    #: Kerze des Ausstiegs, relativ zum Einstieg (0 = Einstiegskerze).
    kerze: np.ndarray
    #: Kurs, zu dem gefuellt wurde.
    preis: np.ndarray
    #: 0 = urspruenglicher Stop, 1 = nachgezogener Stop, 2 = Zeitablauf.
    grund: np.ndarray
    #: Gewinnhoch bis zum Ausstieg, in Punkten.
    spitze: np.ndarray
    #: Anteil der Ausstiege, bei denen die Kerze unter dem Stop EROEFFNETE -
    #: dort waere die echte Fuellung schlechter als gebucht.
    luecke_anteil: float

    STOP, TRAILING, ZEIT = 0, 1, 2

    def punkte(self, einstiegskurs: np.ndarray) -> np.ndarray:
        return self.preis - einstiegskurs


def trailing_ausstieg(
    df: pd.DataFrame,
    einstieg_idx: np.ndarray,
    einstiegskurs: np.ndarray,
    start_stop: np.ndarray,
    *,
    rueckgabe: float,
    aktivierung_pkt: np.ndarray,
    horizont: int,
) -> Ausstieg:
    """Wann und wo ein Long mit nachgezogenem Stop herauskommt.

    ``start_stop`` ist der urspruengliche Stop (unter dem zweiten Tief),
    ``aktivierung_pkt`` der Gewinn in Punkten, ab dem nachgezogen wird.
    Beide je Trade.
    """
    validate_ohlcv(df)
    if not 0.0 < rueckgabe < 1.0:
        raise ValueError("rueckgabe ist ein Anteil des Gewinnhochs, 0 < x < 1.")
    if horizont < 1:
        raise ValueError("horizont muss mindestens 1 sein.")
    e = np.asarray(einstieg_idx, dtype=np.int64)
    n = len(df)
    if np.any(e < 0) or np.any(e + horizont > n):
        raise ValueError("Einstiegsindizes liegen ausserhalb der Reihe.")
    if not (len(e) == len(einstiegskurs) == len(start_stop)
            == len(aktivierung_pkt)):
        raise ValueError("Alle Eingabefelder muessen gleich lang sein.")
    if np.any(start_stop >= einstiegskurs):
        raise ValueError(
            "Der Stop muss UNTER dem Einstieg liegen - sonst ist es keiner."
        )

    # float32 ist fuer MNQ-Kurse exakt (Vielfache von 0,25 unter 65.000).
    hoch = df["high"].to_numpy(np.float32)
    tief = df["low"].to_numpy(np.float32)
    offen = df["open"].to_numpy(np.float32)
    schluss = df["close"].to_numpy(np.float32)

    kerze = np.full(len(e), horizont - 1, dtype=np.int32)
    preis = np.empty(len(e), dtype=float)
    grund = np.full(len(e), Ausstieg.ZEIT, dtype=np.int8)
    spitze = np.zeros(len(e), dtype=float)
    luecke = np.zeros(len(e), dtype=bool)

    spalten = np.arange(horizont)
    for start in range(0, len(e), BLOCK):
        teil = slice(start, start + BLOCK)
        idx = e[teil][:, None] + spalten[None, :]
        h_block = hoch[idx]
        t_block = tief[idx]

        # Gewinnhoch der Kerzen DAVOR. In der Einstiegskerze gibt es noch
        # keins, dort gilt allein der urspruengliche Stop.
        lauf_hoch = np.maximum.accumulate(h_block, axis=1)
        vorher = np.full_like(lauf_hoch, -np.inf)
        vorher[:, 1:] = lauf_hoch[:, :-1]
        gewinn = vorher - einstiegskurs[teil][:, None]

        aktiv = gewinn >= aktivierung_pkt[teil][:, None]
        nachgezogen = (einstiegskurs[teil][:, None]
                       + (1.0 - rueckgabe) * gewinn)
        stufe = np.where(aktiv,
                         np.maximum(start_stop[teil][:, None], nachgezogen),
                         start_stop[teil][:, None])

        getroffen = t_block <= stufe
        hat = getroffen.any(axis=1)
        wann = np.where(hat, getroffen.argmax(axis=1), horizont - 1)

        zeilen = np.arange(len(wann))
        stop_kurs = stufe[zeilen, wann]
        # Zeitablauf: Schlusskurs der letzten Kerze.
        schluss_kurs = schluss[e[teil] + horizont - 1]

        kerze[teil] = wann
        preis[teil] = np.where(hat, stop_kurs, schluss_kurs)
        grund[teil] = np.where(
            ~hat, Ausstieg.ZEIT,
            np.where(aktiv[zeilen, wann], Ausstieg.TRAILING, Ausstieg.STOP))
        spitze[teil] = np.maximum(gewinn[zeilen, wann], 0.0)
        luecke[teil] = hat & (offen[e[teil] + wann] < stop_kurs)

    return Ausstieg(kerze=kerze, preis=preis, grund=grund, spitze=spitze,
                    luecke_anteil=float(luecke.mean()) if len(e) else 0.0)


__all__ = ["Ausstieg", "trailing_ausstieg", "RUECKGABE", "AKTIVIERUNG_R"]
