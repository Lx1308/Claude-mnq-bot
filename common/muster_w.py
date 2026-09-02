"""Das W ueber seine FORM erkennen - nach Laurins eigener Definition.

STAND: WARTET AUF LAURINS BESTAETIGUNG
--------------------------------------
Dieses Modul ist noch nicht freigegeben. Es ersetzt ``muster_handelbar``,
sobald Laurin bestaetigt hat, dass die gefundenen Formen Ws sind. Bis dahin
wird darauf NICHT gemessen - der Fehler vom 02.09.2026 war, zu messen, bevor
die Definition stand.

WAS AN DEN VORGAENGERN FALSCH WAR
---------------------------------
``muster_serie`` und ``muster_handelbar`` verlangen beide keinen Formtest.
``muster_handelbar`` etwa nur: ein bestaetigtes Tief, irgendwann danach ein
Hoch, ein Ruecklauf auf Tiefniveau. Zwischen den Tiefs durfte alles
passieren - eine 300 Kerzen lange Seitwaertsphase mit zufaelligem Hoch zaehlte
genauso wie ein sauberes W. Laurins Urteil ueber die Beispiele: "das sind
alle keine Ws."

SEINE DEFINITION
----------------
"Es heisst W, weil wenn man eine Durchschnittslinie durchlegen wuerde, es
aussieht wie ein W."

Der Formtest laeuft deshalb auf der GEGLAETTETEN Linie, nicht auf den
Rohkursen. Das ist keine Feinheit: sein erstes Beispiel steigt von 29290 auf
29330, faellt auf 29300 zurueck, laeuft seitwaerts und geht erst dann auf
29360. Roh gerechnet waere das ein Rueckschlag von 75 % des Aufschenkels -
jeder strenge Formtest auf Rohkursen haette sein eigenes W verworfen.

SEINE BEIDEN BEISPIELE, NACHGEMESSEN
------------------------------------
                          W 1 (01.09.)      W 2 (02.09., 09:38-09:56)
    Hoehe                 ~70 Punkte        101,75 Punkte
    Dauer                 ~105 Kerzen        18 Kerzen
    Tiefs auseinander     ~0                 19,50 Pkt = 19 % der Hoehe
    zweites Tief          gleich             TIEFER als das erste
    Schenkelverhaeltnis   2,15               2,60

Daraus folgen drei Regeln, die keiner der Vorgaenger hatte:

1. Das zweite Tief darf das erste UNTERSCHREITEN. Genau das ist die starke
   Variante - das erste Tief wird abgeraeumt, und DANN dreht es. Beide
   Vorgaenger hielten so etwas fuer ein kaputtes Muster und brachen ab.
2. Die Dauer reicht von rund 15 bis rund 200 Kerzen. Eine Swing-Staerke von
   30 kann ein 18-Kerzen-W gar nicht sehen; gefiltert wird ueber die HOEHE,
   nicht ueber die Staerke.
3. Die Schenkel duerfen deutlich ungleich sein - bei beiden Beispielen ist
   der eine mehr als doppelt so lang wie der andere.

LOOKAHEAD
---------
Jede Pruefung benutzt ausschliesslich Kerzen bis zum Ruecklauf. Das erste
Tief traegt seine Bestaetigungsverzoegerung von ``strength`` Kerzen, das Hoch
ist das LAUFENDE Maximum bis zu diesem Moment - nicht das spaetere Hoch des
ganzen Fensters. An genau dieser Stelle ist die erste Fassung des
Vorgaengers durch die Abschneide-Probe gefallen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv
from common.structure import find_swing_points

#: Vorgaben, aus Laurins beiden Beispielen kalibriert.
STANDARD_STRENGTH = 6
STANDARD_MAX_UEBER = 0.15      # zweites Tief hoechstens so viel HOEHER
STANDARD_MAX_UNTER = 0.30      # ... und hoechstens so viel TIEFER
STANDARD_MAX_RUECKSCHLAG = 0.25
STANDARD_GLAETTUNG = 0.12      # Fenster der Durchschnittslinie, Anteil der Dauer
STANDARD_MIN_DAUER = 12
STANDARD_MAX_DAUER = 200
STANDARD_MAX_SCHENKEL = 3.0
STANDARD_MIN_HOEHE_ATR = 2.0
STANDARD_MIN_ARM = 0.5


@dataclass(frozen=True)
class WMuster:
    """Ein Doppelboden mit dem Zeitpunkt, an dem er handelbar wird."""

    erst_idx: int
    hoch_idx: int
    zweit_idx: int
    einstieg_idx: int
    tief1: float
    tief2: float
    hoch: float
    linker_arm: float      #: Abverkauf vor dem ersten Tief, in Musterhoehen
    sauber_auf: float      #: Rueckschlag im GEGLAETTETEN Aufschenkel
    sauber_ab: float       #: Erholung im GEGLAETTETEN Abschenkel
    atr: float

    @property
    def tief(self) -> float:
        """Die untere W-Linie - das tiefere der beiden Tiefs."""
        return min(self.tief1, self.tief2)

    @property
    def hoehe(self) -> float:
        return self.hoch - self.tief

    @property
    def dauer(self) -> int:
        return self.zweit_idx - self.erst_idx

    @property
    def versatz(self) -> float:
        """Abstand der beiden Tiefs in Punkten."""
        return abs(self.tief2 - self.tief1)

    @property
    def zweites_tiefer(self) -> bool:
        """Wurde das erste Tief abgeraeumt? Die starke Variante."""
        return self.tief2 < self.tief1

    def stop(self, anteil: float) -> float:
        """Stop ``anteil`` der Musterhoehe UNTER der unteren Linie."""
        if anteil <= 0:
            raise ValueError(
                "Der Stop gehoert unter das Tief; ein Anteil <= 0 laege im "
                "Muster, wo es noch gar nicht gebrochen ist."
            )
        return self.tief - anteil * self.hoehe

    def ziel(self, anteil: float) -> float:
        """Ziel ``anteil`` der Musterhoehe vor der oberen Linie.

        Negativer ``anteil`` geht darueber hinaus; ``-1.0`` ist das
        klassische Messziel.
        """
        return self.hoch - anteil * self.hoehe


def finde_w(
    df: pd.DataFrame,
    atr: np.ndarray | pd.Series,
    *,
    strength: int = STANDARD_STRENGTH,
    max_ueber_anteil: float = STANDARD_MAX_UEBER,
    max_unter_anteil: float = STANDARD_MAX_UNTER,
    max_rueckschlag: float = STANDARD_MAX_RUECKSCHLAG,
    glaettung: float = STANDARD_GLAETTUNG,
    min_dauer: int = STANDARD_MIN_DAUER,
    max_dauer: int = STANDARD_MAX_DAUER,
    max_schenkel_verhaeltnis: float = STANDARD_MAX_SCHENKEL,
    min_hoehe_atr: float = STANDARD_MIN_HOEHE_ATR,
    min_linker_arm: float = STANDARD_MIN_ARM,
    n_gruen: int = 1,
    max_warten: int = 20,
) -> list[WMuster]:
    """Alle W-Formen der Reihe, in zeitlicher Ordnung.

    Alle Toleranzen sind Anteile der Musterhoehe, nicht Punktzahlen - ein
    20-Punkte-W und ein 100-Punkte-W bekommen dieselbe Regel.
    """
    validate_ohlcv(df)
    if strength < 1:
        raise ValueError("strength muss mindestens 1 sein.")

    atr_werte = np.asarray(atr, dtype=float)
    if len(atr_werte) != len(df):
        raise ValueError(
            f"atr hat {len(atr_werte)} Werte, der Rahmen {len(df)} Kerzen."
        )

    o = df["open"].to_numpy(float)
    h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float)
    c = df["close"].to_numpy(float)
    n = len(df)
    ist_gruen = c > o

    punkte = find_swing_points(df, strength=strength)
    letzter = n - 1
    tiefs = sorted(
        ((letzter - p.bars_ago, p.price) for p in punkte if p.kind == "low"),
        key=lambda t: t[0],
    )

    funde: list[WMuster] = []
    for erst_idx, tief1 in tiefs:
        bekannt = erst_idx + strength
        if bekannt >= n - 2 or erst_idx < 120:
            continue
        ende = min(erst_idx + max_dauer, n - 1)

        # Laufendes Hoch und Ruecklauf in EINEM Vorwaertslauf.
        hoch, hoch_idx, zweit_idx = -np.inf, -1, -1
        for j in range(erst_idx + 1, ende + 1):
            if h[j] > hoch:
                hoch, hoch_idx = h[j], j
            if j < bekannt or hoch_idx < 0 or j - erst_idx < min_dauer:
                continue
            hoehe_j = hoch - tief1
            if hoehe_j <= 0:
                continue
            a_j = atr_werte[j]
            if not np.isfinite(a_j) or a_j <= 0 or hoehe_j < min_hoehe_atr * a_j:
                continue
            # Das zweite Tief DARF das erste unterschreiten - siehe Docstring.
            if l[j] < tief1 - max_unter_anteil * hoehe_j:
                break
            if j > hoch_idx and l[j] <= tief1 + max_ueber_anteil * hoehe_j:
                zweit_idx = j
                break
        if zweit_idx < 0 or hoch_idx <= erst_idx:
            continue

        hoch = float(hoch)
        tief2 = float(l[zweit_idx])
        tief = min(tief1, tief2)
        hoehe = hoch - tief
        if hoehe <= 0:
            continue

        auf = hoch_idx - erst_idx
        ab = zweit_idx - hoch_idx
        if auf < 3 or ab < 3:
            continue
        if max(auf, ab) / min(auf, ab) > max_schenkel_verhaeltnis:
            continue

        # Formtest auf der Durchschnittslinie - Laurins eigenes Kriterium.
        fenster = max(3, int((zweit_idx - erst_idx) * glaettung))
        seg = c[erst_idx:zweit_idx + 1]
        if len(seg) <= fenster:
            continue
        glatt = np.convolve(seg, np.ones(fenster) / fenster, mode="valid")
        if len(glatt) < 6:
            continue
        gipfel = int(np.argmax(glatt))
        # Der Gipfel muss ZWISCHEN den Tiefs liegen, sonst ist es eine Flanke.
        if not (0.1 * len(glatt) < gipfel < 0.9 * len(glatt)):
            continue
        auf_g, ab_g = glatt[:gipfel + 1], glatt[gipfel:]
        spanne_auf = float(auf_g.max() - auf_g.min())
        spanne_ab = float(ab_g.max() - ab_g.min())
        if spanne_auf <= 0 or spanne_ab <= 0:
            continue
        s_auf = float(np.max(np.maximum.accumulate(auf_g) - auf_g)) / spanne_auf
        s_ab = float(np.max(ab_g - np.minimum.accumulate(ab_g))) / spanne_ab
        if s_auf > max_rueckschlag or s_ab > max_rueckschlag:
            continue

        # Linker Arm: ohne Abverkauf davor kehrt eine Umkehrformation nichts um.
        vor = h[max(0, erst_idx - 120):erst_idx + 1]
        arm = (float(vor.max()) - tief1) / hoehe
        if arm < min_linker_arm:
            continue

        folge, einstieg = 0, -1
        for j in range(zweit_idx, min(zweit_idx + max_warten, n - 2) + 1):
            if l[j] < tief - max_unter_anteil * hoehe:
                break
            folge = folge + 1 if ist_gruen[j] else 0
            if folge >= n_gruen:
                einstieg = j + 1
                break
        if einstieg < 0 or einstieg >= n:
            continue
        a_e = atr_werte[einstieg]
        if not np.isfinite(a_e) or a_e <= 0:
            continue

        funde.append(WMuster(
            erst_idx=erst_idx, hoch_idx=hoch_idx, zweit_idx=zweit_idx,
            einstieg_idx=einstieg, tief1=float(tief1), tief2=tief2,
            hoch=hoch, linker_arm=arm, sauber_auf=s_auf, sauber_ab=s_ab,
            atr=float(a_e),
        ))

    funde.sort(key=lambda f: f.einstieg_idx)
    return funde


__all__ = ["WMuster", "finde_w"] + [
    n for n in dir() if n.startswith("STANDARD_")
]
