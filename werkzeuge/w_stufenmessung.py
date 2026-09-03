"""Was passiert nach dem zweiten Boden - je Bestaetigungsstufe gemessen.

DIE FRAGE, WOERTLICH
--------------------
Laurin, 03.09.2026: *"Je frueher ich einsteige, desto mehr Gewinnpotential ist
noch vorhanden, aber desto weniger Bestaetigung habe ich. Je spaeter ich
einsteige, desto mehr Bestaetigung, aber desto schlechter wird mein
verbleibendes Chance-/Risiko-Verhaeltnis. Ich moechte, dass die historischen
Daten zeigen, wo dieser optimale Punkt liegt."*

Hier wird deshalb NICHTS festgelegt. Gemessen wird ein Raster:

    Bestaetigungsstufe  x  struktureller Stop  x  strukturelles Ziel

und zwar fuer jedes historische W einzeln, mit dem tatsaechlichen weiteren
Kursverlauf.

WAS "STRUKTURELL" HEISST
------------------------
Stop und Ziel haengen an den Linien des Musters, nicht an einem ATR-Vielfachen:

    Stop  =  zweiter Boden  MINUS  Abstand
    Ziel  =  Nackenlinie    MINUS  Abstand

Der Abstand wird in ZWEI Waehrungen gerastert - als Anteil der Musterhoehe
und in absoluten Punkten. Welche der beiden traegt, ist selbst ein Ergebnis:
wenn der beste Anteil ueber alle Groessenklassen derselbe ist, skaliert das
Muster; wenn die beste Punktzahl derselbe ist, skaliert es nicht.

DIE NULLLINIE
-------------
`P(Ziel zuerst) = Risiko / (Risiko + Lohn)` - die Geometrielinie aus
`docs/MUSTERBEFUND_2026-09-02.md`. Ueber 14 Mustertypen und 1,9 Mio
Ereignisse lag jede gemessene Trefferquote darauf, maximale Abweichung
0,75 Prozentpunkte. Jede Zelle wird deshalb gegen ihre eigene geometrische
Erwartung ausgewiesen, nicht gegen 50 %.

Ein Ergebnis, das deutlich davon abweicht, ist ZUERST als Messfehler zu
behandeln und gegenzupruefen - nicht als Fund zu melden.

DIE FORMSCHWELLE IST KEINE VORAUSSETZUNG
----------------------------------------
Ab welchem Formfehler eine Form kein W mehr ist, ist noch nicht kalibriert -
der Referenzsatz wartet auf Laurins Urteile. Statt einen Schnitt zu raten,
wird der Formfehler als DIMENSION gefuehrt: die Ergebnisse stehen je
Formfehler-Viertel. Traegt die W-Form Information, muss sich das als Gefaelle
ueber die Viertel zeigen. Tut es das nicht, ist auch das eine Antwort - und
Laurins spaetere Urteile machen die Messung nicht ungueltig, sie sagen nur,
welches Viertel "echte Ws" sind.

AUFRUF
------
    .venv\\Scripts\\python.exe -m werkzeuge.w_stufenmessung
    .venv\\Scripts\\python.exe -m werkzeuge.w_stufenmessung --neu   # Cache verwerfen
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common.ereignisse.barrieren import NICHT_ERREICHT, erste_beruehrung
from common.ereignisse.outcomes import vorwaertsfenster
from common.indicators import atr as atr_indikator
from common.muster_w import finde_w
from common.muster_w_stufen import WEG_STUFEN, struktur_stufen, weg_stufen
from werkzeuge.w_referenz import WEIT, lade_kerzen

WURZEL = Path(__file__).resolve().parents[1]
ABLAGE = WURZEL / "data"
CACHE = ABLAGE / "w_kandidaten.npz"
ERGEBNIS = ABLAGE / "w_stufenmessung.csv"

#: Trainingsfenster. 2024 ist Validation, ab 2025 Out-of-Sample - beides
#: bleibt hier unberuehrt (Invariante 5).
TRAIN_ENDE = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")

#: Kerzen nach dem Einstieg, in denen sich entscheidet.
HORIZONT = 240

#: Round Turn in Punkten: 0,95 USD Kommission je Seite = 0,475 Punkte, plus
#: ein Tick Slippage je Seite = 0,25 Punkte. Belegtes Profil
#: `private_ninjatrader` aus `backtest/kosten.py`.
KOSTEN_PKT = 1.45

#: MNQ: 2 USD je Punkt. Nicht 20 - das ist der grosse NQ.
PUNKTWERT_USD = 2.0

#: Unter diesem Risiko wird das R-Vielfache zur Willkuer: ein Stop von einem
#: halben Punkt ist bei MNQ kein Stop, sondern Rauschen im Spread.
MIND_RISIKO_PKT = 2.0

#: Stop-Abstaende UNTER dem zweiten Boden, als Anteil der Musterhoehe.
STOP_ANTEILE: tuple[float, ...] = (0.02, 0.05, 0.10, 0.20, 0.35)
#: ... und in absoluten Punkten. Laurins Beispiel "10-15 Punkte unter das
#: Tief" liegt in diesem Raster, ist aber nur einer von sieben Werten.
STOP_PUNKTE: tuple[float, ...] = (2.0, 5.0, 10.0, 20.0)

#: Ziel-Abstaende, als Anteil der Musterhoehe von der Nackenlinie aus.
#: Positiv = davor (der Kurs muss die Linie nicht erreichen), 0 = auf der
#: Linie, negativ = darueber hinaus. -1,0 ist das klassische Messziel.
ZIEL_ANTEILE: tuple[float, ...] = (0.30, 0.15, 0.05, 0.0, -0.25, -0.50, -1.00)

BLOCK = 20_000


# -- Kandidaten ------------------------------------------------------------

def sammle(df: pd.DataFrame) -> pd.DataFrame:
    """Alle W-Kandidaten mit ihren Kennzahlen, monatsweise gerechnet.

    Weite Schwellen (``WEIT``): der Formfehler entscheidet spaeter, nicht
    hier. Insbesondere darf das zweite Tief das erste deutlich
    unterschreiten - Laurins eigenes W tut das, und ein Liquidity Sweep
    zerstoert ein W nicht.
    """
    puffer = WEIT.max_dauer + 20
    monate = sorted(set(df.index.tz_convert("UTC").tz_localize(None)
                        .to_period("M")))
    zeilen: list[dict] = []
    for nr, m in enumerate(monate, 1):
        anfang = m.start_time.tz_localize("UTC")
        ende = m.end_time.tz_localize("UTC")
        k0, k1 = df.index.searchsorted(anfang), df.index.searchsorted(ende)
        von, bis = max(0, k0 - puffer), min(len(df), k1 + puffer)
        if bis - von < 2 * puffer:
            continue
        block = df.iloc[von:bis]
        a = atr_indikator(block, period=14).to_numpy()
        for f in finde_w(block, a, cfg=WEIT):
            if not (k0 <= von + f.erst_idx < k1):
                continue
            zeilen.append({
                "erst_idx": von + f.erst_idx,
                "zweit_idx": von + f.zweit_idx,
                "bestaetigt_idx": von + f.bestaetigt_idx,
                "tief1": f.tief1, "tief2": f.tief2, "hoch": f.hoch,
                "hoehe": f.hoehe, "dauer": f.dauer,
                "formfehler": f.formfehler, "gipfellage": f.gipfellage,
                "linker_arm": f.linker_arm, "atr": f.atr,
                "zweites_tiefer": float(f.zweites_tiefer),
            })
        if nr % 12 == 0:
            print(f"  {nr}/{len(monate)} Monate, {len(zeilen):,} Kandidaten",
                  flush=True)
    return pd.DataFrame(zeilen)


def lade_kandidaten(df: pd.DataFrame, neu: bool) -> pd.DataFrame:
    if CACHE.exists() and not neu:
        d = np.load(CACHE)
        tab = pd.DataFrame({k: d[k] for k in d.files})
        print(f"  {len(tab):,} Kandidaten aus dem Zwischenspeicher")
        return tab
    print("Kandidaten sammeln (einige Minuten) ...", flush=True)
    t0 = time.time()
    tab = sammle(df)
    np.savez_compressed(CACHE, **{c: tab[c].to_numpy() for c in tab.columns})
    print(f"  {len(tab):,} Kandidaten in {time.time() - t0:.0f}s")
    return tab


# -- Die Messung -----------------------------------------------------------

def _preisniveaus(tab: pd.DataFrame) -> tuple[dict, dict]:
    """Stop- und Zielkurse je Kandidat, benannt.

    Beides haengt AM MUSTER, nicht am Einstieg - deshalb einmal gerechnet
    und ueber alle Stufen wiederverwendet.
    """
    tief2 = tab["tief2"].to_numpy()
    hoch = tab["hoch"].to_numpy()
    hoehe = tab["hoehe"].to_numpy()
    stops = {f"anteil_{s:.2f}": tief2 - s * hoehe for s in STOP_ANTEILE}
    stops.update({f"punkte_{p:.0f}": tief2 - p for p in STOP_PUNKTE})
    ziele = {f"anteil_{z:+.2f}": hoch - z * hoehe for z in ZIEL_ANTEILE}
    return stops, ziele


def _laufende_extrema(df, e):
    """Laufendes Hoch und Tief AB dem Einstieg, Kerze fuer Kerze.

    Ergebnis ist ``(anzahl, HORIZONT)``: an Position ``k`` steht das
    Extremum ueber die Kerzen ``e .. e+k``. Damit laesst sich die groesste
    Auslenkung BIS ZUM AUSSTIEG ablesen statt bis zum Ende des Horizonts.

    Das ist kein Detail. Ueber den ganzen Horizont gerechnet enthaelt die
    MFE auch die Bewegung NACH dem Stop - eine Position, die in Kerze 3
    ausgestoppt wurde und danach vier Stunden steigt, saehe aus, als waere
    sie weit im Gewinn gewesen. Genau die Kennzahl, mit der Laurin wissen
    will, wie oft "der Markt zunaechst steigt und anschliessend trotzdem
    einbricht", waere damit unbrauchbar.
    """
    # float32 ist hier EXAKT: MNQ-Kurse sind Vielfache von 0,25 und liegen
    # unter 65.000, also ganze Zahlen unter 262.144 nach Multiplikation mit
    # vier - weit innerhalb der 24 Mantissenbits. Es halbiert den Speicher
    # der beiden grossen Matrizen (bei 90.000 Mustern rund 170 statt 340 MB).
    h = df["high"].to_numpy(np.float32)
    l = df["low"].to_numpy(np.float32)
    lauf_h = np.empty((len(e), HORIZONT), dtype=np.float32)
    lauf_l = np.empty((len(e), HORIZONT), dtype=np.float32)
    spalten = np.arange(HORIZONT)[None, :]
    for start in range(0, len(e), BLOCK):
        teil = e[start:start + BLOCK]
        idx = teil[:, None] + spalten
        np.maximum.accumulate(h[idx], axis=1,
                              out=lauf_h[start:start + len(teil)])
        np.minimum.accumulate(l[idx], axis=1,
                              out=lauf_l[start:start + len(teil)])
    return lauf_h, lauf_l


def messe_stufe(df, tab, einstieg, stops, ziele, roll_hoch, roll_tief,
                schluss_h, stufenname):
    """Alle Stop/Ziel-Kombinationen fuer EINEN Einstiegszeitpunkt.

    ``einstieg`` ist der Index der Einstiegskerze je Kandidat, ``-1`` wo die
    Stufe nicht erreicht wurde. Gehandelt wird zur EROEFFNUNG dieser Kerze -
    die Stufe selbst wurde eine Kerze vorher erreicht.
    """
    n = len(df)
    opens = df["open"].to_numpy(float)
    brauchbar = (einstieg >= 0) & (einstieg + HORIZONT <= n)
    if brauchbar.sum() < 30:
        return pd.DataFrame()

    e = einstieg[brauchbar]
    entry = opens[e]
    hoehe = tab["hoehe"].to_numpy()[brauchbar]
    formfehler = tab["formfehler"].to_numpy()[brauchbar]
    jahr = df.index.year.to_numpy()[e]

    # Was ueber den GANZEN Horizont erreichbar gewesen waere - Laurins
    # "maximal erreichbares R". Nicht dasselbe wie die Auslenkung bis zum
    # Ausstieg, und deshalb getrennt ausgewiesen.
    mfe_horizont = roll_hoch[e] - entry
    ende_pkt = schluss_h[e] - entry

    # Laurins Liste: Abstand zum zweiten Boden und verbleibendes Potential.
    # Beides in Punkten UND als Anteil der Musterhoehe, weil vorher nicht
    # entschieden ist, welche der beiden Waehrungen traegt.
    tief2 = tab["tief2"].to_numpy()[brauchbar]
    hals = tab["hoch"].to_numpy()[brauchbar]
    ueber_boden = entry - tief2
    rest_pkt = hals - entry

    lauf_h, lauf_l = _laufende_extrema(df, e)

    # Die teure Rechnung: erste Beruehrung je Niveau, einmal je Stufe.
    stop_zeit = {name: erste_beruehrung(df, e, kurs[brauchbar], HORIZONT,
                                        nach_oben=False)
                 for name, kurs in stops.items()}
    ziel_zeit = {name: erste_beruehrung(df, e, kurs[brauchbar], HORIZONT,
                                        nach_oben=True)
                 for name, kurs in ziele.items()}

    zeilen = []
    zeile_idx = np.arange(len(e))
    for s_name, s_kurs in stops.items():
        risiko = entry - s_kurs[brauchbar]
        for z_name, z_kurs in ziele.items():
            lohn = z_kurs[brauchbar] - entry
            # Ein Ziel unter dem Einstieg ist kein Ziel, ein Stop darueber
            # kein Stop. Beides kommt bei spaeten Stufen vor und wird
            # verworfen statt umgedeutet.
            gueltig = (risiko >= MIND_RISIKO_PKT) & (lohn > 0)
            if gueltig.sum() < 30:
                continue
            ts, tz = stop_zeit[s_name], ziel_zeit[z_name]
            # Ausstiegskerze: die fruehere der beiden Beruehrungen, sonst
            # das Ende des Horizonts.
            aus = np.minimum(np.minimum(ts, tz), HORIZONT) - 1
            mfe_aus = lauf_h[zeile_idx, aus] - entry
            mae_aus = entry - lauf_l[zeile_idx, aus]
            zeilen.extend(_zelle(
                stufenname, s_name, z_name, gueltig, risiko, lohn, ts, tz,
                mfe_aus, mae_aus, mfe_horizont, ende_pkt, hoehe, formfehler,
                jahr, ueber_boden, rest_pkt))
    return pd.DataFrame(zeilen)


def _zelle(stufe, s_name, z_name, gueltig, risiko, lohn, t_stop, t_ziel,
           mfe_aus, mae_aus, mfe_horizont, ende_pkt, hoehe, formfehler, jahr,
           ueber_boden, rest_pkt):
    """Eine Zelle - insgesamt, je Formfehler-Viertel und je Jahr.

    Die Jahresgruppen sind Laurins Robustheitsfrage: ein Ergebnis, das nur
    aus einem einzigen Jahr stammt, ist keine Aussage ueber den Markt,
    sondern ueber dieses Jahr.
    """
    ergebnisse = []
    schranken = np.quantile(formfehler[gueltig], [0.25, 0.50, 0.75])
    gruppen = [("alle", gueltig)]
    for nr, (unten, oben) in enumerate(
            zip([-np.inf, *schranken], [*schranken, np.inf]), 1):
        gruppen.append((f"formviertel_{nr}",
                        gueltig & (formfehler >= unten) & (formfehler < oben)))
    for j in np.unique(jahr[gueltig]):
        gruppen.append((f"jahr_{j}", gueltig & (jahr == j)))

    for gname, maske in gruppen:
        if maske.sum() < 30:
            continue
        r = risiko[maske]
        w = lohn[maske]
        ts, tz = t_stop[maske], t_ziel[maske]

        offen = (ts == NICHT_ERREICHT) & (tz == NICHT_ERREICHT)
        # Gleichstand = beide in derselben Kerze: der Stop gilt (Invariante 4).
        gleich = (~offen) & (ts == tz)
        stop_zuerst = (~offen) & (ts <= tz)
        ziel_zuerst = (~offen) & (tz < ts)

        punkte = np.where(ziel_zuerst, w,
                          np.where(stop_zuerst, -r, ende_pkt[maske]))
        r_netto = (punkte - KOSTEN_PKT) / r
        usd = (punkte - KOSTEN_PKT) * PUNKTWERT_USD

        # Zeit bis zum Ausgang, getrennt - nur ueber die Faelle, in denen er
        # eintrat. Ueber alle gemittelt waere es die Zeit bis "irgendwas".
        zeit_ziel = (float(np.median(tz[ziel_zuerst])) if ziel_zuerst.any()
                     else np.nan)
        zeit_stop = (float(np.median(ts[stop_zuerst])) if stop_zuerst.any()
                     else np.nan)

        entschieden = int(stop_zuerst.sum() + ziel_zuerst.sum())
        quote = ziel_zuerst.sum() / entschieden if entschieden else np.nan
        # Die Geometrie ueber DIESELBE Teilmenge wie die Trefferquote, also
        # ohne die Faelle, die im Horizont nicht entschieden haben.
        #
        # Ueber alle gerechnet waeren die beiden Zahlen nicht vergleichbar:
        # wer nicht entscheidet, ist kein Zufallsauszug, sondern hat
        # systematisch weitere Barrieren im Verhaeltnis zur Volatilitaet.
        # Der Fehler machte die Abweichung bei den spaeten Sprossen um rund
        # 0,7 Prozentpunkte zu gross.
        ent_maske = stop_zuerst | ziel_zuerst
        geo = (float(np.mean(r[ent_maske] / (r[ent_maske] + w[ent_maske])))
               if entschieden else np.nan)

        # "Erst gestiegen, dann doch eingebrochen": ausgestoppt, obwohl der
        # Kurs VOR dem Ausstieg mindestens ein halbes R im Plus stand.
        gelaufen = stop_zuerst & (mfe_aus[maske] >= 0.5 * r)

        ergebnisse.append({
            "stufe": stufe, "stop": s_name, "ziel": z_name, "gruppe": gname,
            "n": int(maske.sum()),
            "entschieden": entschieden,
            "ziel_zuerst": int(ziel_zuerst.sum()),
            "stop_zuerst": int(stop_zuerst.sum()),
            "zeitablauf": int(offen.sum()),
            "ambig_anteil": (round(float(gleich.sum() / entschieden), 4)
                             if entschieden else np.nan),
            "trefferquote": round(float(quote), 4),
            "geometrie": round(geo, 4),
            "abweichung_pp": (round(float(quote - geo) * 100, 2)
                              if entschieden else np.nan),
            "risiko_pkt": round(float(np.median(r)), 2),
            "lohn_pkt": round(float(np.median(w)), 2),
            "crv": round(float(np.median(w / r)), 2),
            "E_R_netto": round(float(r_netto.mean()), 4),
            # Streuung des Mittelwerts. Ohne sie ist ein E[R] von +0,01 bei
            # n = 200 nicht von null zu unterscheiden - und genau solche
            # Zellen sind es, die als "Fund" durchgehen.
            "E_R_stdfehler": round(float(r_netto.std(ddof=1) / np.sqrt(len(r_netto))), 4),
            "t_wert": round(float(r_netto.mean() /
                                  (r_netto.std(ddof=1) / np.sqrt(len(r_netto)))), 2)
                      if r_netto.std(ddof=1) > 0 else np.nan,
            "median_R_netto": round(float(np.median(r_netto)), 4),
            "E_USD_netto": round(float(usd.mean()), 2),
            "median_USD": round(float(np.median(usd)), 2),
            "mfe_R_bis_ausstieg": round(float(np.median(mfe_aus[maske] / r)), 2),
            "mae_R_bis_ausstieg": round(float(np.median(mae_aus[maske] / r)), 2),
            "mfe_R_horizont": round(float(np.median(mfe_horizont[maske] / r)), 2),
            "hochgelaufen_dann_gestoppt": round(float(gelaufen.mean()), 3),
            "zeit_bis_ziel": round(zeit_ziel, 1) if zeit_ziel == zeit_ziel else np.nan,
            "zeit_bis_stop": round(zeit_stop, 1) if zeit_stop == zeit_stop else np.nan,
            "ueber_boden_pkt": round(float(np.median(ueber_boden[maske])), 2),
            "ueber_boden_anteil": round(
                float(np.median(ueber_boden[maske] / hoehe[maske])), 3),
            "rest_pkt": round(float(np.median(rest_pkt[maske])), 2),
            "rest_anteil": round(
                float(np.median(rest_pkt[maske] / hoehe[maske])), 3),
            "hoehe_median": round(float(np.median(hoehe[maske])), 1),
            "formfehler_median": round(float(np.median(formfehler[maske])), 3),
            "jahre": int(len(np.unique(jahr[maske]))),
        })
    return ergebnisse


#: Minuten einer US-Kernsession. Der versetzte Placebo verschiebt um ganze
#: Handelstage, damit Tageszeit und Regime erhalten bleiben.
HANDELSTAG_MINUTEN = 390


def placebo(df, e, risiko, lohn, rng, wiederholungen=3, versetzt=True):
    """Dieselben Abstaende, dieselbe Richtung - aber ein anderer Einstieg.

    DIE FRAGE, DIE DAMIT BEANTWORTET WIRD
    Eine Trefferquote ueber der Geometrielinie hat zwei moegliche Ursachen,
    und in der Tabelle sehen sie gleich aus:

      1. Nach einem bestaetigten W steigt der Kurs oefter - das waere ein Fund.
      2. MNQ ist im Trainingszeitraum von rund 7.000 auf 16.000 gestiegen.
         JEDER Long schlaegt die Geometrielinie, ganz ohne Muster.

    Der Placebo trennt beides: gleiche Risiko- und Lohnabstaende in Punkten,
    gleiche Richtung, gleicher Zeitraum - nur der Einstieg sitzt woanders.

    ZWEI VARIANTEN, UND DIE ZWEITE IST DIE SCHAERFERE
    ``versetzt=False`` zieht gleichverteilt aus dem Training. Das misst die
    Drift sauber, hat aber einen Haken: ein zufaelliger Punkt aus sieben
    Jahren sitzt im Mittel in einer RUHIGEREN Phase als ein W - Muster
    haeufen sich, wo sich der Kurs bewegt. Dieselbe Punktzahl Abstand ist
    dort relativ weiter weg, und der Vergleich misst dann Volatilitaet.

    ``versetzt=True`` (Vorgabe) verschiebt stattdessen um ein bis fuenf
    ganze Handelstage in zufaelliger Richtung. Regime, Tageszeit und
    Volatilitaet bleiben damit erhalten - nachgemessen liegt die Median-ATR
    am versetzten Punkt bei 4,2 gegen 4,0 am Muster, also sogar leicht
    GEGEN das Muster -, die Ausrichtung auf die Formation ist zerstoert.

    Zurueck kommt die Liste der Abweichungen (Prozentpunkte) je Wiederholung.
    """
    opens = df["open"].to_numpy(float)
    grenze = len(df) - HORIZONT - 1
    ergebnis = []
    for _ in range(wiederholungen):
        if versetzt:
            schritte = rng.integers(1, 6, len(e)) * HANDELSTAG_MINUTEN
            z = np.clip(e + schritte * rng.choice([-1, 1], len(e)), 300, grenze)
        else:
            z = rng.integers(300, grenze, len(e))
        entry = opens[z]
        ts = erste_beruehrung(df, z, entry - risiko, HORIZONT, nach_oben=False)
        tz = erste_beruehrung(df, z, entry + lohn, HORIZONT, nach_oben=True)
        offen = (ts == NICHT_ERREICHT) & (tz == NICHT_ERREICHT)
        ziel_zuerst = (~offen) & (tz < ts)
        ent = ~offen
        if ent.sum() < 30:
            continue
        quote = ziel_zuerst[ent].sum() / ent.sum()
        geo = float(np.mean(risiko[ent] / (risiko[ent] + lohn[ent])))
        ergebnis.append((quote - geo) * 100)
    return ergebnis


# -- Ablauf ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--neu", action="store_true",
                   help="Kandidaten neu sammeln statt aus dem Cache")
    args = p.parse_args(argv)

    print("Kerzen laden ...", flush=True)
    df = lade_kerzen()
    print(f"  {len(df):,} Kerzen {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")

    tab = lade_kandidaten(df, args.neu)

    # Nur Training. Geschnitten wird am BESTAETIGUNGSZEITPUNKT - dort faellt
    # die Entscheidung, nicht beim ersten Tief.
    zeit = df.index[tab["bestaetigt_idx"].to_numpy().astype(int)]
    tab = tab[zeit <= TRAIN_ENDE].reset_index(drop=True)
    print(f"  {len(tab):,} davon im Training (bis {TRAIN_ENDE:%Y-%m-%d})")
    if tab.empty:
        print("Keine Kandidaten im Training - Abbruch.")
        return 1

    start = tab["bestaetigt_idx"].to_numpy().astype(np.int64)
    tief2 = tab["tief2"].to_numpy()
    hals = tab["hoch"].to_numpy()

    print("Vorwaertsfenster ...", flush=True)
    vf = vorwaertsfenster(df, HORIZONT, mit_zeiten=False)
    roll_hoch, roll_tief, schluss_h = vf.hoch, vf.tief, vf.schluss

    print("Bestaetigungsleitern ...", flush=True)
    weg = weg_stufen(df, start, tief2, hals, horizont=HORIZONT)
    quote = weg.quote()
    print("  Weg-Stufen (Anteil der Strecke zur Nackenlinie):")
    for anteil, q in zip(WEG_STUFEN, quote):
        print(f"    {anteil:5.0%}  von {len(tab):,} Mustern erreicht: {q:6.1%}")
    gebrochen = (weg.bruch >= 0).mean()
    print(f"  unter den zweiten Boden gefallen: {gebrochen:.1%}")

    struktur = {a: struktur_stufen(df, start, tief2, hals,
                                   zickzack_anteil=a, horizont=HORIZONT)
                for a in (0.10, 0.20)}
    for a, leiter in struktur.items():
        q = leiter.quote()
        print(f"  Struktur-Stufen bei {a:.0%} Mindestbewegung: "
              + "  ".join(f"{i + 1}:{v:.0%}" for i, v in enumerate(q)))

    stops, ziele = _preisniveaus(tab)
    print(f"\nRaster: {len(WEG_STUFEN)} Weg-Stufen + "
          f"{sum(l.erreicht.shape[1] for l in struktur.values())} Struktur-Stufen "
          f"x {len(stops)} Stops x {len(ziele)} Ziele", flush=True)

    teile: list[pd.DataFrame] = []
    aufgaben = [(f"weg_{a:.2f}", weg.einstieg[:, k])
                for k, a in enumerate(WEG_STUFEN)]
    for a, leiter in struktur.items():
        aufgaben += [(f"struktur{a:.0%}_{k + 1}", leiter.einstieg[:, k])
                     for k in range(leiter.erreicht.shape[1])]

    t0 = time.time()
    for nr, (name, einstieg) in enumerate(aufgaben, 1):
        teil = messe_stufe(df, tab, einstieg, stops, ziele,
                           roll_hoch, roll_tief, schluss_h, name)
        teile.append(teil)
        print(f"  [{nr}/{len(aufgaben)}] {name}: {len(teil)} Zellen "
              f"({time.time() - t0:.0f}s)", flush=True)

    ergebnis = pd.concat([t for t in teile if not t.empty], ignore_index=True)
    ergebnis.to_csv(ERGEBNIS, index=False)
    print(f"\n{len(ergebnis):,} Zellen -> {ERGEBNIS}")

    _bericht(ergebnis)
    _placebo_bericht(df, tab, ergebnis, dict(aufgaben), stops, ziele)
    return 0


def _placebo_bericht(df, tab, ergebnis, aufgaben, stops, ziele):
    """Muster gegen Kontrolle, gemittelt ueber ALLE Zellen einer Stufe.

    Bewusst nicht ueber die beste Zelle: die ist auf den Daten ausgesucht,
    und der Vergleich fiele dadurch zugunsten des Musters aus.
    """
    print("\n" + "=" * 78)
    print("PLACEBO: DIESELBEN ABSTAENDE, ANDERER EINSTIEG")
    print("=" * 78)
    print("  Was die Kontrolle genauso gut kann, kommt nicht vom Muster.")
    print("  Kontrolle = derselbe Einstieg, um 1-5 Handelstage verschoben.")
    print("  Gemittelt ueber alle Zellen der Stufe, nichts ausgewaehlt.\n")
    opens = df["open"].to_numpy(float)
    n = len(df)
    rng = np.random.default_rng(20260903)
    print(f"  {'Stufe':<16} {'Zellen':>7} {'Muster':>9} {'Kontrolle':>10} "
          f"{'Vorsprung':>10}")
    for stufe, einstieg in aufgaben.items():
        ok = (einstieg >= 0) & (einstieg + HORIZONT <= n)
        if ok.sum() < 200:
            continue
        e = einstieg[ok]
        entry = opens[e]
        echt, kontrolle = [], []
        for s_name, s_kurs in stops.items():
            r = entry - s_kurs[ok]
            for z_name, z_kurs in ziele.items():
                w = z_kurs[ok] - entry
                gut = (r >= MIND_RISIKO_PKT) & (w > 0)
                if gut.sum() < 200:
                    continue
                eigen = _abweichung(df, e[gut], r[gut], w[gut])
                kontr = placebo(df, e[gut], r[gut], w[gut], rng,
                                wiederholungen=1)
                if np.isfinite(eigen) and kontr:
                    echt.append(eigen)
                    kontrolle.append(kontr[0])
        if not echt:
            continue
        m, k = float(np.mean(echt)), float(np.mean(kontrolle))
        print(f"  {stufe:<16} {len(echt):>7} {m:>+8.2f}  {k:>+9.2f}  "
              f"{m - k:>+9.2f} pp")


def _abweichung(df, e, risiko, lohn):
    """Trefferquote minus Geometrielinie, in Prozentpunkten."""
    entry = df["open"].to_numpy(float)[e]
    ts = erste_beruehrung(df, e, entry - risiko, HORIZONT, nach_oben=False)
    tz = erste_beruehrung(df, e, entry + lohn, HORIZONT, nach_oben=True)
    offen = (ts == NICHT_ERREICHT) & (tz == NICHT_ERREICHT)
    ent = ~offen
    if ent.sum() < 100:
        return np.nan
    quote = ((~offen) & (tz < ts))[ent].sum() / ent.sum()
    geo = float(np.mean(risiko[ent] / (risiko[ent] + lohn[ent])))
    return (quote - geo) * 100


def _bericht(e: pd.DataFrame) -> None:
    """Das Wesentliche im Terminal - der Rest steht im CSV."""
    alle = e[e["gruppe"] == "alle"]
    print("\n" + "=" * 78)
    print("DIE GEOMETRIELINIE ALS LUEGENDETEKTOR")
    print("=" * 78)
    ab = alle["abweichung_pp"].dropna()
    print(f"  {len(ab):,} Zellen, Abweichung von Risiko/(Risiko+Lohn):")
    print(f"    Median {ab.median():+.2f} pp   "
          f"5 % {ab.quantile(0.05):+.2f}   95 % {ab.quantile(0.95):+.2f}   "
          f"max |{ab.abs().max():.2f}|")

    print("\n" + "=" * 78)
    print("ERWARTUNGSWERT NACH KOSTEN, JE BESTAETIGUNGSSTUFE")
    print("=" * 78)
    print(f"  {'Stufe':<16} {'Zellen':>7} {'n_max':>8} {'bestes E[R]':>12} "
          f"{'bestes E[$]':>12} {'positiv':>8}")
    for stufe, g in alle.groupby("stufe", sort=False):
        beste = g.loc[g["E_R_netto"].idxmax()]
        print(f"  {stufe:<16} {len(g):>7} {g['n'].max():>8,} "
              f"{beste['E_R_netto']:>+12.4f} {beste['E_USD_netto']:>+12.2f} "
              f"{(g['E_R_netto'] > 0).sum():>8}")

    positiv = alle[alle["E_R_netto"] > 0].sort_values("E_R_netto",
                                                      ascending=False)
    print("\n" + "=" * 78)
    print(f"ZELLEN MIT POSITIVEM ERWARTUNGSWERT NACH KOSTEN: {len(positiv)} "
          f"von {len(alle)}")
    print("=" * 78)
    if positiv.empty:
        print("  Keine. Das ist der Befund, nicht ein Fehler.")
    else:
        spalten = ["stufe", "stop", "ziel", "n", "trefferquote", "geometrie",
                   "abweichung_pp", "crv", "E_R_netto", "t_wert",
                   "E_USD_netto", "jahre"]
        print(positiv[spalten].head(25).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
