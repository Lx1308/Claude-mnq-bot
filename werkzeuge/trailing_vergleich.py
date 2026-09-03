"""Festes Ziel gegen nachgezogenen Stop - bei identischen Einstiegen.

DIE THESE
---------
Laurin, 03.09.2026, zu einem FVG-Chart: *"wenn der bot zb bei dem ersten fvg
gekauft haette und dann erst mit zb einem trailing sl von 15 % oder so
verkauft haette waere das ein sehr profitabler trade gewesen."*

Der Einwand sitzt. Die Messung vom 02.09. hat 14 Mustertypen ueber 1,9 Mio
Ereignisse geprueft und nichts gefunden - aber sie hat **ausschliesslich mit
festen Zielen** gerechnet. Wenn der Einstieg brauchbar war und nur der
Ausstieg falsch, haette diese Messung das nicht sehen koennen.

Die Zahl, die dafuer spricht, stand schon in der Stufenmessung:

    MFE bis zum Ausstieg      0,79 R
    MFE ueber den Horizont    3,26 R

Die Bewegung war da. Ein festes Ziel sammelt sie nur nicht ein.

WAS HIER VERGLICHEN WIRD
------------------------
**Dieselben Ereignisse, derselbe Einstieg, derselbe Anfangsstop.** Nur der
Ausstieg unterscheidet sich:

    A   festes Ziel        (wie am 02.09.)
    B   nachgezogener Stop (Rueckgabe x Aktivierung, gerastert)

Damit ist der Vergleich sauber auf die Ausstiegsregel isoliert. Faellt B
besser aus, lag es nie am Einstieg.

DIE NULLLINIE BLEIBT
--------------------
Ein nachgezogener Stop hat keine feste Trefferquote und laesst sich nicht
mehr gegen `Risiko/(Risiko+Lohn)` halten. Stattdessen laeuft dieselbe
zeitversetzte Kontrolle mit wie in `w_stufenmessung`: derselbe Einstieg um
ein bis fuenf Handelstage verschoben, alles andere gleich. Was die Kontrolle
genauso gut kann, kommt nicht vom Muster.

AUFRUF
------
    .venv\\Scripts\\python.exe -m werkzeuge.trailing_vergleich
    .venv\\Scripts\\python.exe -m werkzeuge.trailing_vergleich --muster liquidity_sweep
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common.ereignisse.barrieren import NICHT_ERREICHT, erste_beruehrung
from common.indicators import atr as atr_indikator
from common.stops import PUFFER_PKT, letzte_tiefs, stop_unter_dem_tief
from common.trailing import AKTIVIERUNG_R, RUECKGABE
from werkzeuge.w_referenz import lade_kerzen

WURZEL = Path(__file__).resolve().parents[1]
EVENTDB = WURZEL / "data" / "eventdb.sqlite3"
ERGEBNIS = WURZEL / "data" / "trailing_vergleich.csv"

HORIZONT = 240
KOSTEN_PKT = 1.45
PUNKTWERT_USD = 2.0
MIND_RISIKO_PKT = 2.0
HANDELSTAG = 390
BLOCK = 20_000

#: Anfangsstop, als ATR-Vielfaches unter dem Einstieg. Der Vergleichsmassstab.
STOPS_ATR: tuple[float, ...] = (0.5, 1.0, 2.0)
#: Feste Ziele zum Vergleich, ebenfalls in ATR.
ZIELE_ATR: tuple[float, ...] = (0.5, 1.0, 2.0, 3.0)


def indexprobe(df: pd.DataFrame, con: sqlite3.Connection, muster: str) -> bool:
    """Zeigt ``verfuegbar_idx`` auf dieselbe Kerze wie ``verfuegbar_ts``?

    Ohne diese Probe waeren alle Zahlen Unsinn: die Indizes stammen aus der
    Kerzenreihe, die beim Erkennungslauf geladen war, und ob das dieselbe
    ist wie die hier geladene, ist eine Annahme.
    """
    proben = con.execute(
        "SELECT verfuegbar_idx, verfuegbar_ts FROM events "
        "WHERE pattern_type = ? LIMIT 500", (muster,)).fetchall()
    if not proben:
        return False
    treffer = sum(
        1 for i, roh in proben
        if 0 <= i < len(df)
        and abs((df.index[i] - pd.Timestamp(roh)).total_seconds()) < 1)
    quote = treffer / len(proben)
    print(f"  Indexprobe: {treffer}/{len(proben)} ({quote:.1%})")
    return quote > 0.99


def lade_ereignisse(con: sqlite3.Connection, muster: str,
                    richtung: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT verfuegbar_idx, pattern_hoehe_pkt, level_1, level_2 "
        "FROM events WHERE pattern_type = ? AND direction = ? "
        "AND datensatz_block = 'train'", con, params=(muster, richtung))


def _bloecke(anzahl: int):
    for start in range(0, anzahl, BLOCK):
        yield slice(start, min(start + BLOCK, anzahl))


def messe(df: pd.DataFrame, e: np.ndarray, entry: np.ndarray,
          risiko: np.ndarray, rng: np.random.Generator | None = None
          ) -> dict[tuple, np.ndarray]:
    """Fuer alle Trailing-Kombinationen die Punkte je Trade.

    Die teure Groesse - das laufende Gewinnhoch - haengt nur vom Einstieg ab
    und wird deshalb EINMAL je Block gerechnet und ueber alle
    Parameterkombinationen wiederverwendet.
    """
    hoch = df["high"].to_numpy(np.float32)
    tief = df["low"].to_numpy(np.float32)
    schluss = df["close"].to_numpy(np.float32)
    start_stop = entry - risiko

    ergebnis = {(r, a): np.empty(len(e)) for r in RUECKGABE
                for a in AKTIVIERUNG_R}
    spalten = np.arange(HORIZONT)

    for teil in _bloecke(len(e)):
        idx = e[teil][:, None] + spalten[None, :]
        h_block = hoch[idx]
        t_block = tief[idx]
        lauf = np.maximum.accumulate(h_block, axis=1)
        vorher = np.full_like(lauf, -np.inf)
        vorher[:, 1:] = lauf[:, :-1]
        gewinn = vorher - entry[teil][:, None]
        ende_kurs = schluss[e[teil] + HORIZONT - 1]
        zeilen = np.arange(t_block.shape[0])

        for rueck in RUECKGABE:
            nachgezogen = entry[teil][:, None] + (1.0 - rueck) * gewinn
            for akt_r in AKTIVIERUNG_R:
                schwelle = akt_r * risiko[teil][:, None]
                aktiv = gewinn >= schwelle
                stufe = np.where(
                    aktiv,
                    np.maximum(start_stop[teil][:, None], nachgezogen),
                    start_stop[teil][:, None])
                getroffen = t_block <= stufe
                hat = getroffen.any(axis=1)
                wann = np.where(hat, getroffen.argmax(axis=1), HORIZONT - 1)
                kurs = np.where(hat, stufe[zeilen, wann], ende_kurs)
                ergebnis[(rueck, akt_r)][teil] = kurs - entry[teil]
    return ergebnis


def festes_ziel(df: pd.DataFrame, e: np.ndarray, entry: np.ndarray,
                risiko: np.ndarray, a: np.ndarray) -> dict[float, np.ndarray]:
    """Punkte je Trade fuer die festen Ziele - die Rechnung vom 02.09."""
    schluss = df["close"].to_numpy(float)
    t_stop = erste_beruehrung(df, e, entry - risiko, HORIZONT, nach_oben=False)
    ergebnis = {}
    for z in ZIELE_ATR:
        lohn = z * a
        t_ziel = erste_beruehrung(df, e, entry + lohn, HORIZONT, nach_oben=True)
        offen = (t_stop == NICHT_ERREICHT) & (t_ziel == NICHT_ERREICHT)
        stop_zuerst = (~offen) & (t_stop <= t_ziel)
        ziel_zuerst = (~offen) & (t_ziel < t_stop)
        ergebnis[z] = np.where(
            ziel_zuerst, lohn,
            np.where(stop_zuerst, -risiko, schluss[e + HORIZONT - 1] - entry))
    return ergebnis


def _kennzahl(punkte: np.ndarray, risiko: np.ndarray) -> dict:
    r = (punkte - KOSTEN_PKT) / risiko
    usd = (punkte - KOSTEN_PKT) * PUNKTWERT_USD
    se = float(r.std(ddof=1) / np.sqrt(len(r))) if len(r) > 1 else np.nan
    return {
        "n": int(len(r)),
        "E_R_netto": round(float(r.mean()), 4),
        "stdfehler": round(se, 4),
        "t_wert": round(float(r.mean() / se), 2) if se and se > 0 else np.nan,
        "E_USD": round(float(usd.mean()), 3),
        "gewinnanteil": round(float((punkte > KOSTEN_PKT).mean()), 4),
        "median_R": round(float(np.median(r)), 4),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--muster", default="fair_value_gap")
    p.add_argument("--richtung", type=int, default=1, choices=(1, -1))
    p.add_argument("--stichprobe", type=int, default=0,
                   help="nur so viele Ereignisse (0 = alle)")
    args = p.parse_args(argv)

    print("Kerzen laden ...", flush=True)
    df = lade_kerzen()
    print(f"  {len(df):,} Kerzen")
    a_reihe = atr_indikator(df, period=14).to_numpy()

    con = sqlite3.connect(EVENTDB)
    if not indexprobe(df, con, args.muster):
        print("  -> Indizes passen NICHT. Abbruch, sonst waeren alle Zahlen "
              "Unsinn.")
        return 1

    tab = lade_ereignisse(con, args.muster, args.richtung)
    con.close()
    print(f"  {len(tab):,} {args.muster} "
          f"({'long' if args.richtung == 1 else 'short'}) im Training")

    idx = tab["verfuegbar_idx"].to_numpy(np.int64)
    e = idx + 1
    n = len(df)
    a = a_reihe[np.clip(idx, 0, n - 1)]
    brauchbar = (e >= 0) & (e + HORIZONT <= n) & np.isfinite(a) & (a >= 1.0)
    e, a = e[brauchbar], a[brauchbar]
    if args.stichprobe and len(e) > args.stichprobe:
        wahl = np.random.default_rng(7).choice(len(e), args.stichprobe,
                                               replace=False)
        e, a = e[np.sort(wahl)], a[np.sort(wahl)]
    entry = df["open"].to_numpy(float)[e]
    print(f"  {len(e):,} brauchbar, Median-ATR {np.median(a):.2f} Punkte")

    grenze = int(df.index.searchsorted(pd.Timestamp("2023-12-31 23:59:59",
                                                    tz="UTC"))) - HORIZONT
    rng = np.random.default_rng(20260903)
    zeilen: list[dict] = []
    t0 = time.time()

    # Zwei Stop-Familien nebeneinander: ATR-Vielfache als Massstab und
    # Laurins struktureller Stop unter dem letzten bestaetigten Tief.
    familien: list[tuple[str, np.ndarray, np.ndarray]] = [
        (f"atr_{s:.1f}", s * a, (s * a) >= MIND_RISIKO_PKT)
        for s in STOPS_ATR
    ]
    print("  letzte bestaetigte Tiefs suchen ...", flush=True)
    tiefs = letzte_tiefs(df)
    letztes = tiefs[e]
    for puffer in PUFFER_PKT:
        stop, gut = stop_unter_dem_tief(entry, letztes, puffer_pkt=puffer)
        familien.append((f"tief_minus_{puffer:.0f}", entry - stop, gut))
    print(f"  {len(familien)} Stop-Varianten "
          f"({time.time() - t0:.0f}s)", flush=True)

    for name, risiko, gut in familien:
        if gut.sum() < 1000:
            print(f"  {name}: nur {gut.sum()} brauchbar, uebersprungen")
            continue
        e_g, entry_g, risiko_g, a_g = e[gut], entry[gut], risiko[gut], a[gut]

        # Kontrolle: derselbe Einstieg, um 1-5 Handelstage verschoben.
        schritte = rng.integers(1, 6, len(e_g)) * HANDELSTAG
        v = np.clip(e_g + schritte * rng.choice([-1, 1], len(e_g)),
                    300, grenze)

        fest = festes_ziel(df, e_g, entry_g, risiko_g, a_g)
        for z, punkte in fest.items():
            zeilen.append({"ausstieg": "festes_ziel", "stop": name,
                           "risiko_median": round(float(np.median(risiko_g)), 2),
                           "parameter": f"ziel {z:.1f} ATR", "rueckgabe": None,
                           "aktivierung_r": None,
                           **_kennzahl(punkte, risiko_g)})

        trail = messe(df, e_g, entry_g, risiko_g)
        trail_v = messe(df, v, df["open"].to_numpy(float)[v], risiko_g)
        for (rueck, akt), punkte in trail.items():
            k = _kennzahl(punkte, risiko_g)
            kv = _kennzahl(trail_v[(rueck, akt)], risiko_g)
            zeilen.append({
                "ausstieg": "trailing", "stop": name,
                "risiko_median": round(float(np.median(risiko_g)), 2),
                "parameter": f"rueckgabe {rueck:.0%} / aktiv {akt:.2f} R",
                "rueckgabe": rueck, "aktivierung_r": akt, **k,
                "kontrolle_E_R": kv["E_R_netto"],
                "vorsprung_R": round(k["E_R_netto"] - kv["E_R_netto"], 4),
            })
        print(f"  {name}: n={int(gut.sum()):,} fertig "
              f"({time.time() - t0:.0f}s)", flush=True)

    ergebnis = pd.DataFrame(zeilen)
    ergebnis.insert(0, "muster", args.muster)
    ergebnis.insert(1, "richtung", args.richtung)
    ergebnis.to_csv(ERGEBNIS, index=False)
    _bericht(ergebnis, args.muster)
    print(f"\n{len(ergebnis)} Zeilen -> {ERGEBNIS}")
    return 0


def _bericht(e: pd.DataFrame, muster: str) -> None:
    print("\n" + "=" * 90)
    print(f"{muster.upper()}  -  FESTES ZIEL GEGEN NACHGEZOGENEN STOP")
    print("=" * 90)
    fest = e[e["ausstieg"] == "festes_ziel"]
    trail = e[e["ausstieg"] == "trailing"]
    print(f"  bestes festes Ziel : E[R] {fest['E_R_netto'].max():+.4f}   "
          f"({fest.loc[fest['E_R_netto'].idxmax(), 'parameter']}, "
          f"Stop {fest.loc[fest['E_R_netto'].idxmax(), 'stop']})")
    if trail.empty:
        return
    beste = trail.loc[trail["E_R_netto"].idxmax()]
    print(f"  bestes Trailing    : E[R] {beste['E_R_netto']:+.4f}   "
          f"({beste['parameter']}, Stop {beste['stop']})")
    print(f"                       t = {beste['t_wert']}, n = {beste['n']:,}, "
          f"E[$] {beste['E_USD']:+.3f}")
    print(f"                       Kontrolle {beste['kontrolle_E_R']:+.4f}, "
          f"Vorsprung {beste['vorsprung_R']:+.4f} R")
    print(f"\n  positive Zellen: festes Ziel "
          f"{(fest['E_R_netto'] > 0).sum()}/{len(fest)}, "
          f"Trailing {(trail['E_R_netto'] > 0).sum()}/{len(trail)}")

    print("\n  Trailing, beste fuenf nach E[R]:")
    spalten = ["stop", "risiko_median", "parameter", "n", "E_R_netto",
               "t_wert", "E_USD", "gewinnanteil", "kontrolle_E_R",
               "vorsprung_R"]
    print(trail.nlargest(8, "E_R_netto")[spalten].to_string(index=False))

    print("\n  Bester Trailing-Wert je Stop-Variante:")
    beste_je = trail.loc[trail.groupby("stop")["E_R_netto"].idxmax()]
    print(beste_je.sort_values("E_R_netto", ascending=False)[spalten]
          .to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
