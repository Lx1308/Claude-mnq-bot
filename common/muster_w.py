"""Das W ueber seine FORM erkennen - nach Laurins eigener Definition.

STAND: WARTET AUF LAURINS BESTAETIGUNG
--------------------------------------
Dieses Modul ist nicht freigegeben. Es wird erst gemessen, wenn Laurin die
Definition gegen den Referenzsatz (``werkzeuge/w_referenz.py``) bestaetigt
hat. Der Fehler vom 02.09.2026 war, dreimal vor der Definition zu messen.

SEINE DEFINITION
----------------
"Es heisst W, weil wenn man eine Durchschnittslinie durchlegen wuerde, es
aussieht wie ein W." Und dazu: "am einfachsten ist, wenn man ein W drueberlegt
und das ca. passt."

Beides zusammen ist der Formtest: die Kurslinie wird geglaettet und gegen eine
W-Schablone gelegt (``common/w_schablone.py``). Er laeuft auf der GEGLAETTETEN
Linie, nicht auf den Rohkursen - sein erstes Beispiel steigt von 29290 auf
29330, faellt auf 29300 zurueck, laeuft seitwaerts und geht erst dann auf
29360. Roh gerechnet waere das ein Rueckschlag von 75 % des Aufschenkels;
jeder strenge Formtest auf Rohkursen haette sein eigenes W verworfen.

SEINE BEIDEN BEISPIELE, NACHGEMESSEN
------------------------------------
                          W 1 (01.09.)      W 2 (02.09., 09:38-09:56 ET)
    Hoehe                 ~70 Punkte        101,75 Punkte
    Dauer                 ~105 Kerzen        18 Kerzen
    Tiefs auseinander     ~0                 19,50 Pkt
    zweites Tief          gleich             TIEFER als das erste
    Schenkelverhaeltnis   2,15               2,60

Daraus folgen drei Regeln, die die Vorgaenger nicht hatten:

1. Das zweite Tief darf das erste UNTERSCHREITEN. Genau das ist die starke
   Variante - das erste Tief wird abgeraeumt, und DANN dreht es.
2. Die Dauer reicht von rund 15 bis rund 200 Kerzen. Eine Swing-Staerke von
   30 kann ein 18-Kerzen-W gar nicht sehen; gefiltert wird ueber die HOEHE,
   nicht ueber die Staerke.
3. Die Schenkel duerfen deutlich ungleich sein. Eine eigene Schwelle dafuer
   gibt es nicht mehr - die Schablone verschiebt ihren Gipfel selbst.

DAS ZWEITE TIEF - DER FEHLER VOM 02.09.2026
-------------------------------------------
Die Vorgaengerfassung brach bei der ERSTEN Kerze ab, die in das Tiefband
zurueckkam. Bei Laurins eigenem W lieferte das die 09:50 bei 29.041,75 statt
der 09:56 bei 29.017,25 - sechs Kerzen zu frueh und 24 Punkte zu hoch.

Hier laeuft die Schleife weiter, bis die Umkehr BESTAETIGT ist: der
Schlusskurs steigt um ``bestaetigung_anteil`` der Musterhoehe ueber das
laufende Minimum. Als zweites Tief gilt dann das MINIMUM dieses Abschnitts,
nicht der erste Treffer.

Und - wichtiger - es wird nicht mehr abgebrochen: macht der Kurs danach ein
neues, tieferes Minimum und dreht wieder, entsteht ein ZWEITER Kandidat zum
selben ersten Tief. Welcher davon die W-Form trifft, entscheidet der
Formfehler und nicht die Reihenfolge.

LOOKAHEAD
---------
Jede Pruefung eines Kandidaten benutzt ausschliesslich Kerzen bis zu seinem
Bestaetigungsindex. Das erste Tief traegt seine Verzoegerung von ``strength``
Kerzen, das Hoch ist das LAUFENDE Maximum - nicht das spaetere Hoch des ganzen
Fensters. An genau dieser Stelle ist die erste Fassung des Vorgaengers durch
die Abschneide-Probe gefallen; ``test_kein_lookahead_bei_abgeschnittener_reihe``
haelt sie fest.

Der Bestaetigungszeitpunkt liegt spaeter als der erste Ruecklauf. Das ist der
Preis dafuer, das richtige Tief zu treffen, und darf nicht wegoptimiert
werden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.config import DoppelbodenConfig
from common.indicators import validate_ohlcv
from common.structure import find_swing_points
from common.w_schablone import formfehler as _formfehler
from common.w_schablone import glaette

#: Voreinstellung. Die verbindlichen Werte stehen in ``config.yaml`` unter
#: ``patterns.doppelboden``; hier steht nur, was ohne Config gilt.
STANDARD = DoppelbodenConfig()


@dataclass(frozen=True)
class WMuster:
    """Eine W-Form mit dem Zeitpunkt, an dem sie bestaetigt ist."""

    erst_idx: int
    hoch_idx: int
    zweit_idx: int
    #: Letzte Kerze, die zur Erkennung benutzt wurde.
    bestaetigt_idx: int
    #: Frueheste zulaessige Ausfuehrung: Eroeffnung der Folgekerze.
    einstieg_idx: int
    tief1: float
    tief2: float
    hoch: float
    linker_arm: float      #: Abverkauf vor dem ersten Tief, in Musterhoehen
    formfehler: float      #: Abstand zur W-Schablone, 0 = deckungsgleich
    gipfellage: float      #: Position des Schablonengipfels, Anteil der Dauer
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

    @property
    def verzoegerung(self) -> int:
        """Kerzen zwischen dem zweiten Tief und seiner Bestaetigung."""
        return self.bestaetigt_idx - self.zweit_idx

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
    cfg: DoppelbodenConfig | None = None,
) -> list[WMuster]:
    """Alle W-Formen der Reihe, nach Bestaetigungszeitpunkt geordnet.

    Zu einem ersten Tief koennen MEHRERE Kandidaten entstehen - siehe
    Modul-Docstring. Aussortiert wird ueber den Formfehler, entweder hier
    (wenn ``cfg.max_formfehler`` gesetzt ist) oder spaeter beim Auswerten.

    Alle Toleranzen sind Anteile der Musterhoehe, keine Punktzahlen - ein
    20-Punkte-W und ein 100-Punkte-W bekommen dieselbe Regel.
    """
    validate_ohlcv(df)
    k = cfg or STANDARD

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

    punkte = find_swing_points(df, strength=k.strength)
    letzter = n - 1
    tiefs = sorted(
        ((letzter - p.bars_ago, p.price) for p in punkte if p.kind == "low"),
        key=lambda t: t[0],
    )

    funde: list[WMuster] = []
    for erst_idx, tief1 in tiefs:
        # Vor dem ersten Tief muss genug Reihe fuer den linken Arm liegen.
        if erst_idx < k.max_dauer:
            continue
        if erst_idx + k.strength >= n - 2:
            continue
        funde.extend(
            _kandidaten_zum_tief(o, h, l, c, atr_werte, n, erst_idx,
                                 float(tief1), k)
        )

    if k.max_formfehler is not None:
        funde = [f for f in funde if f.formfehler <= k.max_formfehler]
    funde.sort(key=lambda f: (f.bestaetigt_idx, f.erst_idx))
    return funde


def _kandidaten_zum_tief(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    atr_werte: np.ndarray,
    n: int,
    erst_idx: int,
    tief1: float,
    k: DoppelbodenConfig,
) -> list[WMuster]:
    """Alle W-Kandidaten, die auf EIN erstes Tief folgen.

    Ein Vorwaertslauf. ``hoch`` ist das laufende Maximum, ``min2`` das
    laufende Minimum des Ruecklaufs. Jedes Mal, wenn der Kurs sich von
    ``min2`` weit genug erholt, entsteht ein Kandidat; faellt er danach
    tiefer, gilt das neue Minimum und es kann ein weiterer entstehen.
    """
    bekannt = erst_idx + k.strength
    ende = min(erst_idx + k.max_dauer, n - 2)

    # Linker Arm: der Abverkauf VOR dem ersten Tief. Eine Umkehrformation
    # ohne etwas zum Umkehren ist keine.
    vor_hoch = float(h[max(0, erst_idx - k.max_dauer):erst_idx + 1].max())

    hoch, hoch_idx = -np.inf, -1
    nackenlinie = np.inf    # Hoch zu Beginn des Ruecklaufs, dann eingefroren
    min2, min2_idx = np.inf, -1
    auf_seit_min = 0        # Aufwaertskerzen seit dem laufenden Minimum
    offen = False           # Ruecklauf hat begonnen
    gemeldet = -1           # Index des zuletzt gemeldeten zweiten Tiefs
    kandidaten: list[WMuster] = []

    for j in range(erst_idx + 1, ende + 1):
        if h[j] > hoch:
            hoch, hoch_idx = h[j], j
        if j < bekannt or hoch_idx <= erst_idx:
            continue

        # Das Band immer aus (Hoch - erstes Tief). Wuerde es das laufende
        # Minimum enthalten, zoege ein langsames Abrutschen das Band mit sich
        # nach unten und erlaubte sich damit selbst.
        spanne = hoch - tief1
        if spanne <= 0:
            continue

        # Gerissen: das Tief taugt nicht mehr als untere Linie.
        if l[j] < tief1 - k.max_unter * spanne:
            break

        if j - erst_idx < k.min_dauer:
            continue

        # Ueber die Nackenlinie hinaus - die Formation ist abgeschlossen,
        # alles Weitere ist eine andere Struktur.
        #
        # Verglichen wird gegen das EINGEFRORENE Hoch vom Beginn des
        # Ruecklaufs, nicht gegen das laufende: ``hoch`` wird oben in
        # derselben Kerze mitgezogen, und weil ein Schlusskurs nie ueber dem
        # eigenen Hoch liegt, konnte diese Bedingung nie zutreffen. Der
        # Zweig war toter Code.
        if offen and c[j] > nackenlinie:
            break

        if j > hoch_idx and l[j] <= tief1 + k.max_ueber * spanne:
            if not offen:
                nackenlinie = hoch
            offen = True
            if l[j] < min2:
                min2, min2_idx = l[j], j
                auf_seit_min = 0        # neues Tief, Zaehlung von vorn

        if not offen or min2_idx < 0 or j <= min2_idx or min2_idx == gemeldet:
            continue

        if c[j] > o[j]:
            auf_seit_min += 1

        # Bestaetigung braucht ZWEIERLEI: genug Aufwaertskerzen und genug
        # Weg. Die Kerzenbedingung ist Laurins Regel vom 03.09.2026 - eine
        # einzelne gruene Kerze kann noch zum Abverkauf gehoeren, erst die
        # zweite zeigt, dass die untere Linie gehalten hat.
        if auf_seit_min < k.min_aufwaerts_kerzen:
            continue
        if c[j] - min2 < k.bestaetigung_anteil * spanne:
            continue

        gemeldet = min2_idx
        muster = _baue(c, atr_werte, n, erst_idx, tief1, hoch_idx,
                       float(hoch), min2_idx, float(min2), j, vor_hoch, k)
        if muster is not None:
            kandidaten.append(muster)
            if len(kandidaten) >= k.max_kandidaten:
                break

    return kandidaten


def _baue(
    c: np.ndarray,
    atr_werte: np.ndarray,
    n: int,
    erst_idx: int,
    tief1: float,
    hoch_idx: int,
    hoch: float,
    zweit_idx: int,
    tief2: float,
    bestaetigt_idx: int,
    vor_hoch: float,
    k: DoppelbodenConfig,
) -> WMuster | None:
    """Ein Kandidat, wenn er Hoehe, Arm und Glaettung uebersteht.

    Alles hier benutzt ausschliesslich Kerzen bis ``bestaetigt_idx``.
    """
    tief = min(tief1, tief2)
    hoehe = hoch - tief
    if hoehe <= 0:
        return None

    a = atr_werte[bestaetigt_idx]
    if not np.isfinite(a) or a <= 0 or hoehe < k.min_hoehe_atr * a:
        return None

    arm = (vor_hoch - tief1) / hoehe
    if arm < k.min_linker_arm:
        return None

    einstieg = bestaetigt_idx + 1
    if einstieg >= n:
        return None

    try:
        linie = glaette(c[erst_idx:zweit_idx + 1], k.glaettung)
    except ValueError:
        return None
    if len(linie) < 5:
        return None
    fehler, gipfel = _formfehler(linie)
    if not np.isfinite(fehler):
        return None

    return WMuster(
        erst_idx=erst_idx, hoch_idx=hoch_idx, zweit_idx=zweit_idx,
        bestaetigt_idx=bestaetigt_idx, einstieg_idx=einstieg,
        tief1=tief1, tief2=tief2, hoch=hoch, linker_arm=arm,
        formfehler=fehler, gipfellage=gipfel, atr=float(a),
    )


def bester_je_tief(funde: list[WMuster]) -> list[WMuster]:
    """Je erstem Tief nur der Kandidat mit dem kleinsten Formfehler.

    NUR FUER DIE AUSWERTUNG, NICHT FUER DEN LIVE-BOT. Die Auswahl vergleicht
    Kandidaten, die zu verschiedenen Zeitpunkten bestaetigt wurden - wer um
    09:51 handeln will, kann nicht wissen, dass der Kandidat von 09:57 besser
    zur Schablone passt. Live ist der richtige Weg eine Schranke
    (``patterns.doppelboden.max_formfehler``) und der ERSTE Kandidat, der sie
    unterschreitet.
    """
    beste: dict[int, WMuster] = {}
    for f in funde:
        vorher = beste.get(f.erst_idx)
        if vorher is None or f.formfehler < vorher.formfehler:
            beste[f.erst_idx] = f
    return sorted(beste.values(), key=lambda f: f.bestaetigt_idx)


__all__ = ["WMuster", "finde_w", "bester_je_tief", "STANDARD"]
