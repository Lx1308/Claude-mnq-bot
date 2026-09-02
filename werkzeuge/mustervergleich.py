"""Dieselbe Messung fuer alle elf Muster der Ereignisdatenbank.

DIE FRAGE
---------
Beim Doppelboden lag die Trefferquote in 1.728 Zellen exakt auf der
Geometrielinie:

    P(Ziel zuerst) = Risiko / (Risiko + Lohn)

Gilt das auch fuer Liquidity Sweep, Fair Value Gap, Order Block, Ausbruch,
Fehlausbruch, MSS, BOS, Equal Highs/Lows, Niveautest, Displacement und
Opening-Range-Bruch? Wenn ja, ist der Befund groesser als ein einzelnes
Muster: dann traegt reine Kursgeometrie auf MNQ-Minutenkerzen keine
Richtungsinformation.

WARUM HIER KEINE GEWUERFELTE REIHE MEHR LAEUFT
----------------------------------------------
Die Geometrielinie IST die Nulllinie. Beim W wurde sie gegen zwei
gespiegelte Kontrollreihen geprueft und traf deren Trefferquoten ebenso
genau wie die echten. Sie ist damit als Nullmodell belegt und spart den
teuren Neuaufbau der Erkenner auf gefaelschten Daten.

ZUERST DIE INDEXPROBE
---------------------
Die Datenbank speichert ``verfuegbar_idx`` als Position in der Kerzenreihe,
die beim Erkennungslauf geladen war. Ob das dieselbe Reihe ist wie die hier
zwischengespeicherte, ist eine ANNAHME - und sie wird geprueft, bevor
irgendetwas gerechnet wird. Stimmt sie nicht, sind alle Zahlen wertlos.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ABLAGE = Path(__file__).resolve().parents[1] / "data"
DB = Path(r"C:\Users\lm130\Desktop\Claude chart bot\data\eventdb.sqlite3")
RT_KOSTEN_PKT = 1.45
TRAIN_ENDE = np.datetime64("2023-12-31T23:59:59")
HORIZONT = 240
MIND_RISIKO_PKT = 2.0
BLOCK = 40_000

#: Stop und Ziel als ATR-Vielfache. Bewusst grob - gesucht wird nicht die
#: beste Zelle, sondern ob IRGENDWO etwas ueber der Geometrielinie liegt.
STOPS = (0.5, 1.0, 2.0)
ZIELE = (0.5, 1.0, 2.0, 3.0)


def lade_kerzen():
    d = np.load(ABLAGE / "rahmen_1m.npz")
    return (pd.DatetimeIndex(d["ts"]).tz_localize("UTC"),
            d["open"], d["high"], d["low"])


def indexprobe(ts, con) -> bool:
    """Zeigt verfuegbar_idx auf dieselbe Kerze wie verfuegbar_ts?"""
    proben = con.execute(
        "SELECT verfuegbar_idx, verfuegbar_ts FROM events "
        "WHERE event_id % 97 = 0 LIMIT 400"
    ).fetchall()
    if not proben:
        print("  ! keine Proben gezogen")
        return False
    treffer = 0
    for idx, roh in proben:
        if idx < 0 or idx >= len(ts):
            continue
        if abs((ts[idx] - pd.Timestamp(roh)).total_seconds()) < 1:
            treffer += 1
    quote = treffer / len(proben)
    print(f"  Indexprobe: {treffer}/{len(proben)} stimmen ueberein "
          f"({quote:.1%})")
    return quote > 0.99


def messe(o, h, l, idx, richtung, atr):
    """Trefferquote gegen Geometrie, ueber das ganze Raster."""
    ein = idx + 1
    gut = (ein > 0) & (ein < len(o) - HORIZONT) & np.isfinite(atr) & (atr >= 1.0)
    ein, richtung, atr = ein[gut], richtung[gut], atr[gut]
    if len(ein) < 500:
        return []

    preis = o[ein]
    zeilen = []
    for s in STOPS:
        for z in ZIELE:
            traf_ges = verlor_ges = offen_ges = 0
            r_summe = kosten_summe = geo_summe = 0.0
            for a in range(0, len(ein), BLOCK):
                e = ein[a:a + BLOCK]
                ri, at, pr = richtung[a:a + BLOCK], atr[a:a + BLOCK], preis[a:a + BLOCK]
                risiko, lohn = s * at, z * at
                ziel = pr + ri * lohn
                stop = pr - ri * risiko
                brauchbar = risiko >= MIND_RISIKO_PKT
                if not brauchbar.any():
                    continue
                e, ri, pr = e[brauchbar], ri[brauchbar], pr[brauchbar]
                ziel, stop = ziel[brauchbar], stop[brauchbar]
                risiko, lohn = risiko[brauchbar], lohn[brauchbar]

                f = e[:, None] + np.arange(HORIZONT, dtype=np.int64)[None, :]
                hoch = np.maximum.accumulate(h[f], axis=1)
                tief = np.minimum.accumulate(l[f], axis=1)
                # Long: Ziel oben, Stop unten. Short gespiegelt.
                lang = ri > 0
                t_ziel = np.where(
                    lang,
                    (hoch < ziel[:, None]).sum(1),
                    (tief > ziel[:, None]).sum(1))
                t_stop = np.where(
                    lang,
                    (tief > stop[:, None]).sum(1),
                    (hoch < stop[:, None]).sum(1))
                del f, hoch, tief

                traf = t_ziel < t_stop
                offen = (t_ziel >= HORIZONT) & (t_stop >= HORIZONT)
                verlor = ~traf & ~offen
                traf_ges += int(traf.sum())
                verlor_ges += int(verlor.sum())
                offen_ges += int(offen.sum())
                r_summe += float(np.where(traf, lohn / risiko,
                                          np.where(verlor, -1.0, 0.0)).sum())
                kosten_summe += float((RT_KOSTEN_PKT / risiko).sum())
                geo_summe += float((risiko / (risiko + lohn)).sum())

            n = traf_ges + verlor_ges + offen_ges
            ent = traf_ges + verlor_ges
            if ent < 500:
                continue
            zeilen.append({
                "stop_atr": s, "ziel_atr": z, "n": n, "entschieden": ent,
                "quote": traf_ges / ent, "geometrie": geo_summe / n,
                "offen": offen_ges / n,
                "er_netto": (r_summe - kosten_summe) / n,
                "kosten_r": kosten_summe / n,
            })
    return zeilen


def main():
    ts, o, h, l = lade_kerzen()
    print(f"{len(ts):,} Kerzen zwischengespeichert\n")
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    if not indexprobe(ts, con):
        print("  -> Indizes passen NICHT. Abbruch, sonst waeren alle Zahlen "
              "Unsinn.")
        return 1
    print("  -> passt\n")

    arten = [r[0] for r in con.execute(
        "SELECT DISTINCT pattern_type FROM events ORDER BY 1").fetchall()]

    alle = []
    for art in arten:
        for ri in (1, -1):
            t0 = time.perf_counter()
            df = pd.read_sql_query(
                "SELECT verfuegbar_idx, atr FROM events "
                "WHERE pattern_type = ? AND direction = ? "
                "AND verfuegbar_ts <= ?",
                con, params=(art, ri, "2023-12-31T23:59:59"))
            if len(df) < 500:
                continue
            idx = df.verfuegbar_idx.to_numpy(np.int64)
            atr = df.atr.to_numpy(float)
            for z in messe(o, h, l, idx, np.full(len(idx), ri), atr):
                z["muster"] = art
                z["richtung"] = ri
                alle.append(z)
            print(f"  {art:<20}{'long' if ri > 0 else 'short':<6}"
                  f"{len(df):>9,} Ereignisse "
                  f"[{time.perf_counter() - t0:.0f}s]", flush=True)

    con.close()
    tab = pd.DataFrame(alle)
    tab["ueber"] = tab.quote - tab.geometrie
    tab.to_pickle(ABLAGE / "alle_muster.pkl")
    print(f"\n{len(tab):,} Zellen gerechnet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
