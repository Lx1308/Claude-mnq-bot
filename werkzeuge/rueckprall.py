"""Traegt das W etwas - oder reicht "ein Tief, das gehalten hat"?

DIE FRAGE
---------
Die Stufenmessung vom 03.09.2026 (`docs/W_STUFENMESSUNG_2026-09-03.md`) fand
zwei Dinge, die zusammen einen Verdacht ergeben:

  1. Der Vorsprung gegenueber einer gematchten Kontrolle waechst mit der
     BESTAETIGUNG - null bei der ersten Sprosse, +1,2 Prozentpunkte bei 85 %
     der Strecke.
  2. Die W-FORM traegt nichts bei. Nach Formfehler-Vierteln kein Gefaelle in
     die erwartete Richtung.

Wenn die Form nichts beitraegt und nur die Bestaetigung zaehlt, dann ist das
W moeglicherweise Dekoration. Das eigentliche Signal hiesse dann schlicht:
**ein Tief hat gehalten, und der Kurs ist davon weggelaufen.**

Das ist entscheidbar - und es waere ein wichtiger Unterschied. Ein
Rueckprall-Signal tritt viel haeufiger auf als ein W, ist einfacher zu
definieren und hat damit mehr statistische Kraft, um zu finden, WO der
Vorteil sitzt.

DER AUFBAU
----------
Beide Gruppen sind dieselbe Art Objekt: **bestaetigte Swingtiefs** (Fraktale
mit Staerke 6). Das ist wichtig - das zweite Tief eines W ist selbst kein
Fraktal, sondern das laufende Minimum des Ruecklaufs, und ein Vergleich
ueber verschiedene Objektarten haette gemessen, was ein Fraktal von einem
laufenden Minimum unterscheidet, nicht was ein W ausmacht.

    Gruppe W        - Swingtiefs, die (auf +/-3 Kerzen) das zweite Tief eines
                      W-Kandidaten sind
    Gruppe generisch- alle uebrigen Swingtiefs

Beide bekommen dieselbe Leiter in ATR-Vielfachen ueber dem Tief, denselben
Stop unter dem Tief, dieselben Ziele, denselben Horizont - und jede ihre
eigene zeitversetzte Kontrolle. Verglichen wird nicht die Trefferquote
(die haengt an der Geometrie), sondern der **Vorsprung vor der jeweils
eigenen Kontrolle**.

Sind die beiden Vorspruenge gleich, traegt das W nichts ueber "ein Tief, das
gehalten hat" hinaus.

KEIN LOOKAHEAD
--------------
Ein Swingtief mit Staerke 6 ist erst 6 Kerzen spaeter bekannt. Die Leiter
sucht deshalb ab ``tief_idx + 6``, fuer BEIDE Gruppen gleich. Gehandelt wird
zur Eroeffnung der Folgekerze.

AUFRUF
------
    .venv\\Scripts\\python.exe -m werkzeuge.rueckprall
"""

from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import pandas as pd

from common.ereignisse.barrieren import NICHT_ERREICHT, erste_beruehrung
from common.indicators import atr as atr_indikator
from common.structure import find_swing_points
from werkzeuge import w_stufenmessung as M
from werkzeuge.w_referenz import lade_kerzen

#: Wie ein Swingtief bestaetigt wird - dieselbe Staerke wie im W-Erkenner.
STAERKE = 6

#: Sprossen der Leiter, in ATR ueber dem Tief. ATR statt Musterhoehe, weil
#: ein generisches Swingtief keine Nackenlinie hat - und beide Gruppen
#: denselben Massstab brauchen.
SPROSSEN: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)

#: Stop unter dem Tief, Ziel ueber dem Einstieg - beides in ATR.
STOPS: tuple[float, ...] = (0.25, 0.5, 1.0)
ZIELE: tuple[float, ...] = (1.0, 2.0, 3.0)

#: Ein Swingtief gilt als W-Tief, wenn es so nah an einem zweiten Boden liegt.
NAEHE = 3

BLOCK_KERZEN = 200_000


def swingtiefs(df: pd.DataFrame) -> np.ndarray:
    """Alle bestaetigten Swingtiefs der Reihe, als Indizes.

    Blockweise, weil ``find_swing_points`` ueber 2,6 Mio Kerzen sonst zu viel
    Speicher braucht. Die Bloecke ueberlappen um ``STAERKE``, damit an den
    Naehten nichts verlorengeht.
    """
    gefunden: set[int] = set()
    for start in range(0, len(df), BLOCK_KERZEN):
        ende = min(start + BLOCK_KERZEN + STAERKE, len(df))
        block = df.iloc[start:ende]
        if len(block) < 4 * STAERKE:
            continue
        # find_swing_points liefert bars_ago vom ENDE des Blocks aus und
        # sortiert AUFSTEIGEND danach - die Indizes kommen also absteigend.
        # Eine Monotonie-Annahme an dieser Stelle wirft alles bis auf den
        # letzten Fund weg.
        letzter_idx = len(block) - 1
        for punkt in find_swing_points(block, strength=STAERKE):
            if punkt.kind == "low":
                gefunden.add(start + (letzter_idx - punkt.bars_ago))
    return np.array(sorted(gefunden), dtype=np.int64)


def teile_auf(tiefs: np.ndarray, w_zweit: np.ndarray,
              w_bestaetigt: np.ndarray | None = None
              ) -> tuple[np.ndarray, np.ndarray]:
    """Maske: welches Swingtief gehoert zu einem W - und welches ist verwendbar?

    Zurueck kommt ``(ist_w, verwendbar)``.

    ZUM ZWEITEN RUECKGABEWERT - DER LOOKAHEAD-FRAGE
    Das Etikett "W" stammt aus der Kandidatentabelle, und ein W ist erst an
    seinem ``bestaetigt_idx`` bekannt. Die Leiter startet aber bei
    ``tief_idx + STAERKE``, wenn das Swingtief bestaetigt ist. Wo das W
    SPAETER bestaetigt wird als der Swing, waere das Etikett benutzt worden,
    bevor es existierte.

    Nachgemessen betrifft das 1,0 % der Kandidaten (Median 1 Kerze, P99 sechs
    Kerzen). Der Anteil ist zu klein, um ein Ergebnis zu erzeugen - aber ein
    Leck, das man wegargumentiert, bleibt ein Leck. Diese Faelle fliegen
    deshalb raus, und beide Gruppen starten unveraendert bei
    ``tief_idx + STAERKE``. Das haelt den Vergleich symmetrisch.
    """
    verwendbar = np.ones(len(tiefs), dtype=bool)
    if len(w_zweit) == 0:
        return np.zeros(len(tiefs), dtype=bool), verwendbar

    ordnung = np.argsort(w_zweit)
    sortiert = w_zweit[ordnung]
    bestaetigt = (w_bestaetigt[ordnung] if w_bestaetigt is not None
                  else sortiert)
    pos = np.searchsorted(sortiert, tiefs)

    ist_w = np.zeros(len(tiefs), dtype=bool)
    zu_spaet = np.zeros(len(tiefs), dtype=bool)
    for versatz in (-1, 0):
        nachbar = np.clip(pos + versatz, 0, len(sortiert) - 1)
        treffer = np.abs(sortiert[nachbar] - tiefs) <= NAEHE
        ist_w |= treffer
        zu_spaet |= treffer & (bestaetigt[nachbar] > tiefs + STAERKE)
    return ist_w, ~zu_spaet


def leiter(df: pd.DataFrame, tief_idx: np.ndarray, tief_kurs: np.ndarray,
           a: np.ndarray, horizont: int) -> dict[float, np.ndarray]:
    """Wann jedes Tief welche Sprosse erreicht - vor dem Bruch.

    Rueckgabe je Sprosse: der Einstiegsindex, ``-1`` wo nicht erreicht.
    """
    start = tief_idx + STAERKE          # frueher ist das Tief nicht bekannt
    bruch = erste_beruehrung(df, start, tief_kurs - 1e-9, horizont,
                             nach_oben=False)
    ergebnis: dict[float, np.ndarray] = {}
    for r in SPROSSEN:
        zeit = erste_beruehrung(df, start, tief_kurs + r * a, horizont,
                                nach_oben=True)
        gut = (zeit != NICHT_ERREICHT) & (zeit < bruch)
        einstieg = np.full(len(tief_idx), -1, dtype=np.int64)
        einstieg[gut] = start[gut] + zeit[gut]      # +1-1: naechste Kerze
        einstieg[einstieg >= len(df)] = -1
        ergebnis[r] = einstieg
    return ergebnis


def messe(df: pd.DataFrame, einstieg: np.ndarray, tief_kurs: np.ndarray,
          a: np.ndarray, rng: np.random.Generator,
          horizont: int) -> list[dict]:
    """Alle Stop/Ziel-Kombinationen fuer eine Sprosse einer Gruppe."""
    n = len(df)
    opens = df["open"].to_numpy(float)
    ok = (einstieg >= 0) & (einstieg + horizont <= n)
    if ok.sum() < 500:
        return []
    e = einstieg[ok]
    entry = opens[e]
    tief = tief_kurs[ok]
    atr = a[ok]

    zeilen = []
    for s in STOPS:
        risiko = entry - (tief - s * atr)
        for z in ZIELE:
            lohn = z * atr
            gut = (risiko >= M.MIND_RISIKO_PKT) & (lohn > 0)
            if gut.sum() < 500:
                continue
            eigen = M._abweichung(df, e[gut], risiko[gut], lohn[gut])
            kontrolle = M.placebo(df, e[gut], risiko[gut], lohn[gut], rng,
                                  wiederholungen=2)
            if not np.isfinite(eigen) or not kontrolle:
                continue
            zeilen.append({
                "stop_atr": s, "ziel_atr": z, "n": int(gut.sum()),
                "abweichung": eigen,
                "kontrolle": float(np.mean(kontrolle)),
                "vorsprung": eigen - float(np.mean(kontrolle)),
                "crv": float(np.median(lohn[gut] / risiko[gut])),
                "risiko_pkt": float(np.median(risiko[gut])),
            })
    return zeilen


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--horizont", type=int, default=M.HORIZONT)
    args = p.parse_args(argv)

    print("Kerzen laden ...", flush=True)
    df = lade_kerzen()
    grenze = int(df.index.searchsorted(M.TRAIN_ENDE))
    print(f"  {len(df):,} Kerzen, davon {grenze:,} im Training")

    print("ATR ...", flush=True)
    a_reihe = atr_indikator(df, period=14).to_numpy()

    print("Swingtiefs suchen ...", flush=True)
    t0 = time.time()
    alle = swingtiefs(df)
    alle = alle[(alle > 300) & (alle + STAERKE + args.horizont < grenze)]
    print(f"  {len(alle):,} bestaetigte Tiefs im Training "
          f"({time.time() - t0:.0f}s)")

    d = np.load(M.CACHE)
    w_zweit = d["zweit_idx"].astype(np.int64)
    w_best = d["bestaetigt_idx"].astype(np.int64)
    ist_w, verwendbar = teile_auf(alle, w_zweit, w_best)
    print(f"  davon aus einem W: {ist_w.sum():,} "
          f"({ist_w.mean():.1%}), generisch: {(~ist_w).sum():,}")
    print(f"  wegen spaeter W-Bestaetigung verworfen: "
          f"{(~verwendbar).sum():,} ({(~verwendbar).mean():.1%})")
    alle, ist_w = alle[verwendbar], ist_w[verwendbar]

    tief_kurs = df["low"].to_numpy(float)[alle]
    a = a_reihe[alle + STAERKE]
    brauchbar = np.isfinite(a) & (a > 0.5)
    alle, ist_w = alle[brauchbar], ist_w[brauchbar]
    tief_kurs, a = tief_kurs[brauchbar], a[brauchbar]
    print(f"  mit brauchbarer ATR: {len(alle):,}")

    print("Leitern ...", flush=True)
    leitern = leiter(df, alle, tief_kurs, a, args.horizont)
    for r, ein in leitern.items():
        q_w = (ein[ist_w] >= 0).mean()
        q_g = (ein[~ist_w] >= 0).mean()
        print(f"  {r:.1f} ATR ueber dem Tief erreicht:  "
              f"W {q_w:6.1%}   generisch {q_g:6.1%}")

    rng = np.random.default_rng(20260903)
    print("\n" + "=" * 84)
    print("VORSPRUNG VOR DER EIGENEN KONTROLLE, JE GRUPPE")
    print("=" * 84)
    print("  Prozentpunkte Trefferquote gegenueber der Geometrielinie,")
    print("  gemittelt ueber 9 Stop/Ziel-Kombinationen.\n")
    print(f"  {'Sprosse':<10} {'n (W)':>9} {'W':>9} "
          f"{'n (gen.)':>10} {'generisch':>11} {'Differenz':>11}")

    zeilen = []
    for r in SPROSSEN:
        ein = leitern[r]
        w = messe(df, np.where(ist_w, ein, -1), tief_kurs, a, rng,
                  args.horizont)
        g = messe(df, np.where(~ist_w, ein, -1), tief_kurs, a, rng,
                  args.horizont)
        if not w or not g:
            continue
        vw = float(np.mean([x["vorsprung"] for x in w]))
        vg = float(np.mean([x["vorsprung"] for x in g]))
        nw = max(x["n"] for x in w)
        ng = max(x["n"] for x in g)
        print(f"  {r:<10.1f} {nw:>9,} {vw:>+8.2f}  {ng:>10,} "
              f"{vg:>+10.2f}  {vw - vg:>+10.2f}")
        for x in w:
            zeilen.append({"gruppe": "W", "sprosse_atr": r, **x})
        for x in g:
            zeilen.append({"gruppe": "generisch", "sprosse_atr": r, **x})

    tabelle = pd.DataFrame(zeilen)
    ziel = M.ABLAGE / "rueckprall.csv"
    tabelle.to_csv(ziel, index=False)
    print(f"\n{len(tabelle):,} Zeilen -> {ziel}")

    print("\n" + "=" * 84)
    print("SIND DIE GRUPPEN VERGLEICHBAR?")
    print("=" * 84)
    print(f"  {'':<12} {'ATR Median':>12} {'Tiefkurs':>12}")
    for name, maske in (("W", ist_w), ("generisch", ~ist_w)):
        print(f"  {name:<12} {np.median(a[maske]):>12.2f} "
              f"{np.median(tief_kurs[maske]):>12.0f}")

    _permutation(df, leitern, ist_w, tief_kurs, a, args.horizont)
    return 0


def _permutation(df, leitern, ist_w, tief_kurs, a, horizont,
                 durchgaenge: int = 3) -> None:
    """Die Etiketten wuerfeln - der entscheidende Test.

    Wenn der Unterschied zwischen den Gruppen auch dann bestehen bleibt, wenn
    "W" rein zufaellig auf dieselbe Anzahl Tiefe verteilt wird, misst er
    nicht das W, sondern irgendetwas an der Aufteilung selbst.

    Der echte Unterschied muss deutlich ueber dem liegen, was hier
    herauskommt.
    """
    print("\n" + "=" * 84)
    print("ETIKETTEN-PERMUTATION: 'W' ZUFAELLIG VERTEILT")
    print("=" * 84)
    print("  Was der Zufall genauso gut kann, kommt nicht vom Muster.\n")
    rng = np.random.default_rng(777)
    anteil = float(ist_w.mean())
    print(f"  {'Sprosse':<10} {'echt':>9}  {'gewuerfelt (3 Durchgaenge)':>34}")
    for r in SPROSSEN:
        ein = leitern[r]
        w = messe(df, np.where(ist_w, ein, -1), tief_kurs, a,
                  np.random.default_rng(1), horizont)
        g = messe(df, np.where(~ist_w, ein, -1), tief_kurs, a,
                  np.random.default_rng(2), horizont)
        if not w or not g:
            continue
        echt = (float(np.mean([x["vorsprung"] for x in w]))
                - float(np.mean([x["vorsprung"] for x in g])))
        zufall = []
        for _ in range(durchgaenge):
            marke = rng.random(len(ist_w)) < anteil
            wz = messe(df, np.where(marke, ein, -1), tief_kurs, a,
                       np.random.default_rng(1), horizont)
            gz = messe(df, np.where(~marke, ein, -1), tief_kurs, a,
                       np.random.default_rng(2), horizont)
            if wz and gz:
                zufall.append(float(np.mean([x["vorsprung"] for x in wz]))
                              - float(np.mean([x["vorsprung"] for x in gz])))
        print(f"  {r:<10.1f} {echt:>+8.2f}  "
              + "  ".join(f"{v:+7.2f}" for v in zufall))


if __name__ == "__main__":
    sys.exit(main())
