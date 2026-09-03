"""Referenzsatz aufbauen: Bilder, die Laurin beurteilt, statt Rueckfragen.

DAS PROBLEM
-----------
Die Schwellen in ``common/muster_w.py`` sind aus ZWEI Beispielen kalibriert.
Damit kann niemand pruefen, ob ein Kandidat richtig ist - es wird jedes Mal
Laurin gefragt, und jede Antwort gilt nur fuer dieses eine Bild. Vier Anlaeufe
sind so gescheitert.

Hier entsteht stattdessen ein beschrifteter Satz: 150 Kandidaten und 100
Zufallsfenster, alle gleich gerendert, in gemischter Reihenfolge. Danach ist
jede Schwelle messbar - Falsch-Positiv- und Falsch-Negativ-Rate statt Meinung.

WARUM AUCH ZUFALLSFENSTER
-------------------------
Ohne Negativbeispiele misst der Sweep nur die Trefferquote INNERHALB der
Kandidaten. Die Frage "wie viel Rauschen laesst diese Schwelle durch" waere
gar nicht stellbar - und genau daran ist der Erkenner bisher gescheitert.

WO DAS BILD ENDET - UND WARUM DER ERSTE ANLAUF FALSCH WAR
---------------------------------------------------------
Die Bilder endeten zuerst am ZWEITEN TIEF. Der Gedanke war, den Nachlauf zu
verdecken, damit Laurin nicht Gewinner beschriftet statt Formen. Das hat
genau das abgeschnitten, was ein W zum W macht.

Er hat nach vierzig Bildern gesagt: *"keins war annaehernd ein W ... man kann
ein W erst dann bestimmen, indem die Bottom Line bestaetigt wurde, da das
zweite Tief auf der Hoehe des ersten Tiefs wieder umgekehrt ist und dann nach
oben gestiegen ist."*

Er hat recht. Ein W ist Tief - Hoch - Tief - **HOCH**. Ein Bild, das am
zweiten Tief endet, zeigt Tief - Hoch - Tief, und das sieht nie aus wie ein W.
Alle vierzig Urteile lauteten "nein", und das war die richtige Antwort auf
das falsche Bild.

Die Bilder reichen deshalb jetzt bis zur **Bestaetigung** - dem fruehesten
Zeitpunkt, an dem gehandelt werden koennte. Das ist kein Nachlauf: die
Bestaetigung gehoert zum Muster und ist zum Entscheidungszeitpunkt bekannt.
Verdeckt bleibt nur, was DANACH passiert - der Ausgang.

Aus demselben Grund fehlen weiterhin Datum und Kursniveau: mit beidem liesse
sich der Chart nachschlagen und der Ausgang doch sehen.

WARUM MAN DIE BEIDEN KLASSEN NICHT UNTERSCHEIDEN KANN
-----------------------------------------------------
Die drei Marker werden fuer BEIDE Klassen nach derselben rein geometrischen
Regel gesetzt (hoechstes Hoch, tiefstes Tief davor, tiefstes Tief danach) -
nicht aus den Feldern des Erkenners. Bei einem Kandidaten liefert diese Regel
fast immer dieselben drei Punkte; ein Unterschied im Bild entsteht dadurch
nicht.

AUFRUF
------
    .venv\\Scripts\\python.exe -m werkzeuge.w_referenz
    .venv\\Scripts\\python.exe -m werkzeuge.w_referenz --kandidaten 150 --zufall 100

Danach ``werkzeuge/w_referenz_server.py`` starten und die Seite oeffnen.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from common.config import DoppelbodenConfig
from common.indicators import atr as atr_indikator
from common.muster_w import finde_w
from common.w_schablone import glaette

WURZEL = Path(__file__).resolve().parents[1]
KERZEN_DB = WURZEL / "data" / "ntbridge.sqlite3"
REFERENZ_DB = WURZEL / "data" / "w_referenz.sqlite3"
BILDER = WURZEL / "data" / "w_referenz_bilder"
#: Die Urteile als Text. Die SQLite-Datei ist gitignoriert (``*.sqlite3``),
#: und die Bilder sind aus der Kerzenhistorie jederzeit neu zu erzeugen -
#: Laurins Urteile sind es NICHT. Sie sind die einzige nicht reproduzierbare
#: Groesse im ganzen Vorgang und gehoeren deshalb in die Versionierung.
URTEILE_CSV = WURZEL / "data" / "w_referenz_urteile.csv"

MUSTERART = "doppelboden"
#: Kerzen vor dem ersten Tief, damit die Formation im Zusammenhang steht.
#:
#: Die Aufgabe nannte 40 fest. Fest ist hier falsch: bei einer 10-Kerzen-
#: Formation fuellt der Vorlauf vier Fuenftel des Bildes, und beurteilt wird
#: dann der Vorlauf statt der Form. Der Vorlauf richtet sich deshalb nach der
#: Dauer - fuer BEIDE Klassen nach derselben Regel, die Zufallsfenster ziehen
#: ihre Laengen ohnehin aus der Kandidatenverteilung.
VORLAUF_MIN = 15
VORLAUF_MAX = 60
VORLAUF_ANTEIL = 0.8


def vorlauf(dauer: int) -> int:
    return int(max(VORLAUF_MIN, min(VORLAUF_MAX, dauer * VORLAUF_ANTEIL)))

#: BEWUSST WEIT. Der Referenzsatz soll den Grenzbereich abdecken, nicht nur
#: das, was die aktuelle Definition ohnehin durchlaesst - sonst misst der
#: Sweep spaeter nur sich selbst.
WEIT = DoppelbodenConfig(
    max_unter=0.35,
    max_ueber=0.25,
    min_hoehe_atr=1.0,
    min_dauer=10,
    max_dauer=200,
    min_linker_arm=0.3,
    max_formfehler=None,
)


# -- Daten -----------------------------------------------------------------

def lade_kerzen() -> pd.DataFrame:
    """Alle MNQ-Minutenkerzen, Export und Live zusammen, ohne Doppelte."""
    con = sqlite3.connect(KERZEN_DB)
    try:
        df = pd.read_sql_query(
            "SELECT ts_utc, open, high, low, close, volume FROM bars "
            "WHERE instrument = 'MNQ' AND timeframe = '1m' "
            "ORDER BY ts_utc",
            con,
        )
    finally:
        con.close()
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    # Export und Live ueberlappen; der Export gilt, weil er vollstaendig ist.
    df = df.drop_duplicates(subset="ts_utc", keep="first").set_index("ts_utc")
    return df


def _monatsbloecke(df: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Kalendermonate als (Anfang, Ende).

    Die Zeitzone wird vor ``to_period`` abgestreift und danach wieder
    angesetzt - ``to_period`` wuerde sie sonst stillschweigend verlieren und
    dabei warnen.
    """
    monate = sorted(set(df.index.tz_convert("UTC").tz_localize(None)
                        .to_period("M")))
    return [(m.start_time.tz_localize("UTC"), m.end_time.tz_localize("UTC"))
            for m in monate]


# -- Kandidaten ------------------------------------------------------------

def sammle_kandidaten(df: pd.DataFrame) -> pd.DataFrame:
    """Alle W-Kandidaten der Historie, monatsweise gerechnet.

    Jeder Monat bekommt einen Vorlauf von ``max_dauer`` Kerzen (fuer den
    linken Arm und die ATR) und einen Nachlauf derselben Laenge (damit ein
    Muster ueber den Monatswechsel hinweg nicht abgeschnitten wird). Gezaehlt
    werden nur Funde, deren erstes Tief IM Monat liegt - sonst kaeme jeder
    Fund an der Naht zweimal vor.
    """
    puffer = WEIT.max_dauer + 20
    zeilen: list[dict] = []
    bloecke = _monatsbloecke(df)
    for nr, (anfang, ende) in enumerate(bloecke, 1):
        kern = df.index.searchsorted(anfang), df.index.searchsorted(ende)
        von = max(0, kern[0] - puffer)
        bis = min(len(df), kern[1] + puffer)
        if bis - von < 2 * puffer:
            continue
        block = df.iloc[von:bis]
        a = atr_indikator(block, period=14).to_numpy()
        try:
            funde = finde_w(block, a, cfg=WEIT)
        except ValueError as fehler:      # z.B. Luecke im Block
            print(f"  [{nr}/{len(bloecke)}] {anfang:%Y-%m} uebersprungen: {fehler}")
            continue
        im_kern = 0
        for f in funde:
            global_erst = von + f.erst_idx
            if not (kern[0] <= global_erst < kern[1]):
                continue
            im_kern += 1
            zeilen.append({
                "erst_idx": global_erst,
                "hoch_idx": von + f.hoch_idx,
                "zweit_idx": von + f.zweit_idx,
                "bestaetigt_idx": von + f.bestaetigt_idx,
                "hoehe": f.hoehe,
                "dauer": f.dauer,
                "versatz": f.versatz,
                "linker_arm": f.linker_arm,
                "formfehler": f.formfehler,
                "gipfellage": f.gipfellage,
                "atr": f.atr,
                "monat": f"{anfang:%Y-%m}",
            })
        print(f"  [{nr}/{len(bloecke)}] {anfang:%Y-%m}: {im_kern} Kandidaten",
              flush=True)
    return pd.DataFrame(zeilen)


def ziehe_gestreut(kandidaten: pd.DataFrame, anzahl: int,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Gleichmaessig ueber die Monate ziehen, nicht ueber die Gesamtmenge.

    Eine einfache Zufallsziehung wuerde die Monate bevorzugen, in denen der
    Erkenner viel findet - und das sind die volatilen. Der Referenzsatz waere
    dann eine Aussage ueber 2020 und 2022, nicht ueber die Historie.
    """
    monate = sorted(kandidaten["monat"].unique())
    je_monat = max(1, anzahl // len(monate))
    teile = []
    for monat in monate:
        gruppe = kandidaten[kandidaten["monat"] == monat]
        n = min(len(gruppe), je_monat)
        teile.append(gruppe.sample(n=n, random_state=int(rng.integers(1 << 31))))
    gezogen = pd.concat(teile)
    if len(gezogen) > anzahl:
        gezogen = gezogen.sample(n=anzahl,
                                 random_state=int(rng.integers(1 << 31)))
    elif len(gezogen) < anzahl:
        rest = kandidaten.drop(index=gezogen.index)
        fehlt = min(anzahl - len(gezogen), len(rest))
        if fehlt:
            gezogen = pd.concat([
                gezogen,
                rest.sample(n=fehlt, random_state=int(rng.integers(1 << 31))),
            ])
    return gezogen.sort_values("erst_idx").reset_index(drop=True)


# -- Zufallsfenster --------------------------------------------------------

def ziehe_zufallsfenster(df: pd.DataFrame, alle: pd.DataFrame,
                         gezogen: pd.DataFrame, anzahl: int,
                         rng: np.random.Generator) -> pd.DataFrame:
    """Fenster mit derselben Laengenverteilung, die KEIN Kandidat sind.

    Zwei Dinge, die beim ersten Anlauf schieflagen und deshalb hier stehen:

    **Die Laengen kommen aus den GEZOGENEN 150**, nicht aus allen 162.000.
    Verglichen werden die 150 mit den 100 - wenn deren Verteilungen
    auseinandergehen, sind die Klassen an der Breite des Bildes erkennbar,
    und der Referenzsatz misst die Bildbreite statt die Form.

    **"Kein Kandidat" heisst nicht "beruehrt keinen Kandidaten".** Mit den
    weiten Schwellen ueberdecken die Kandidaten **78 %** der Reihe; ein
    100-Kerzen-Fenster ohne jede Ueberlappung gibt es praktisch nicht, und
    der erste Anlauf hat deshalb stillschweigend nur kurze Fenster gezogen
    (Mittel 22,9 gegen 46,8 Kerzen). Verworfen wird ein Fenster deshalb erst,
    wenn ein EINZELNER Kandidat mehr als ``MAX_UEBERLAPPUNG`` davon abdeckt -
    dann waere es im Wesentlichen dieser Kandidat.

    **Die Laenge wird VORGEGEBEN und dann platziert**, nicht gewuerfelt und
    dann geprueft. Der zweite Anlauf hat das falsch herum gemacht und kippte
    dadurch ins Gegenteil (66,7 gegen 46,8 Kerzen): ein kurzes Fenster liegt
    viel oefter ganz in einem Kandidaten als ein langes und faellt haeufiger
    durch, sodass die angenommenen Fenster zu lang ausfielen. Mit fester
    Zielaenge stimmt die Verteilung per Konstruktion.
    """
    erst = np.sort(alle["erst_idx"].to_numpy())
    ordnung = np.argsort(alle["erst_idx"].to_numpy())
    zweit = alle["zweit_idx"].to_numpy()[ordnung]

    laengen = gezogen["dauer"].to_numpy()
    ziele = rng.choice(laengen, size=anzahl, replace=len(laengen) < anzahl)
    # Kandidatenbilder reichen bis zur Bestaetigung, also einige Kerzen ueber
    # das zweite Tief hinaus. Die Zufallsfenster bekommen denselben Zuschlag
    # aus derselben Verteilung - sonst waeren die Klassen an der Bildbreite
    # zu unterscheiden.
    zuschlaege = rng.choice(
        (gezogen["bestaetigt_idx"] - gezogen["zweit_idx"]).to_numpy(),
        size=anzahl, replace=True)
    rand = WEIT.max_dauer + VORLAUF_MAX + 20
    belegt = np.zeros(len(df), dtype=bool)      # nur gegen Doppelziehung
    zeilen: list[dict] = []
    gescheitert = 0

    for dauer, zuschlag in zip(ziele, zuschlaege):
        dauer = int(dauer) + int(zuschlag)
        vor = vorlauf(dauer)
        for _ in range(VERSUCHE_JE_FENSTER):
            start = int(rng.integers(rand, len(df) - rand))
            ende = start + dauer
            if belegt[start - vor:ende + 1].any():
                continue
            if _deckt_sich_mit_kandidat(erst, zweit, start, ende):
                continue
            # Zeitliche Luecke im Fenster (Boersenpause, Wochenende) waere
            # kein Chartausschnitt, sondern eine Naht.
            spanne = df.index[ende] - df.index[start - vor]
            if spanne > pd.Timedelta(minutes=(dauer + vor) * 3):
                continue
            belegt[start - vor:ende + 1] = True
            zeilen.append({"erst_idx": start, "zweit_idx": ende,
                           "dauer": dauer})
            break
        else:
            gescheitert += 1
    if gescheitert:
        print(f"  ! {gescheitert} von {anzahl} Laengen nicht platzierbar")
    return pd.DataFrame(zeilen)


#: Platzierungsversuche je vorgegebener Laenge.
VERSUCHE_JE_FENSTER = 3000


#: Ab welchem Anteil ein Zufallsfenster im Wesentlichen ein Kandidat ist.
MAX_UEBERLAPPUNG = 0.5


def _deckt_sich_mit_kandidat(erst: np.ndarray, zweit: np.ndarray,
                             start: int, ende: int) -> bool:
    """Deckt ein EINZELNER Kandidat mehr als die Haelfte des Fensters ab?"""
    laenge = ende - start
    if laenge <= 0:
        return True
    # Nur Kandidaten, die vor dem Fensterende beginnen; die frueheren koennen
    # nicht mehr als max_dauer zurueckreichen.
    links = int(np.searchsorted(erst, start - WEIT.max_dauer, side="left"))
    rechts = int(np.searchsorted(erst, ende, side="right"))
    if rechts <= links:
        return False
    ueber = (np.minimum(zweit[links:rechts], ende)
             - np.maximum(erst[links:rechts], start))
    return bool((ueber > MAX_UEBERLAPPUNG * laenge).any())


# -- Marker ----------------------------------------------------------------

def marker(df: pd.DataFrame, start: int, ende: int) -> tuple[int, int, int]:
    """Die drei Punkte, rein geometrisch - fuer BEIDE Klassen dieselbe Regel.

    Hoechstes Hoch im Fenster, tiefstes Tief davor, tiefstes Tief danach.
    Wuerde man bei Kandidaten stattdessen die Felder des Erkenners nehmen,
    waeren die beiden Klassen am Bild unterscheidbar.
    """
    h = df["high"].to_numpy(float)[start:ende + 1]
    l = df["low"].to_numpy(float)[start:ende + 1]
    hoch = int(np.argmax(h))
    if hoch == 0:
        hoch = 1
    if hoch >= len(h) - 1:
        hoch = len(h) - 2
    # Das Fenster reicht ueber den zweiten Boden hinaus bis zur Bestaetigung;
    # das tiefste Tief NACH dem Hoch ist damit weiterhin genau dieser Boden.
    tief1 = int(np.argmin(l[:hoch + 1]))
    tief2 = hoch + int(np.argmin(l[hoch:]))
    return start + tief1, start + hoch, start + tief2


# -- Bild ------------------------------------------------------------------

def zeichne(df: pd.DataFrame, start: int, ende: int, ziel: Path) -> None:
    """Ein Fenster als PNG. Kein Datum, kein Kursniveau, kein Nachlauf."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    von = max(0, start - vorlauf(ende - start))
    o = df["open"].to_numpy(float)[von:ende + 1]
    h = df["high"].to_numpy(float)[von:ende + 1]
    l = df["low"].to_numpy(float)[von:ende + 1]
    c = df["close"].to_numpy(float)[von:ende + 1]
    x = np.arange(len(o))
    basis = float(l.min())

    fig, ax = plt.subplots(figsize=(11.0, 5.0), dpi=100)
    ax.set_facecolor("#14161a")
    fig.patch.set_facecolor("#14161a")

    # Vorlauf abheben, damit klar ist, wo die Formation beginnt.
    grenze = start - von
    ax.axvspan(-0.5, grenze - 0.5, color="#ffffff", alpha=0.05, lw=0)
    ax.axvline(grenze - 0.5, color="#3a414d", lw=1.0, ls=(0, (4, 4)))

    for i in x:
        farbe = "#26a96a" if c[i] >= o[i] else "#d1465a"
        ax.vlines(i, l[i] - basis, h[i] - basis, color=farbe, lw=0.8)
        unten, oben = sorted((o[i] - basis, c[i] - basis))
        ax.add_patch(plt.Rectangle((i - 0.32, unten), 0.64,
                                   max(oben - unten, 0.02),
                                   facecolor=farbe, edgecolor=farbe, lw=0.4))

    # Die Durchschnittslinie - Laurins eigenes Kriterium.
    fenster = max(3, int(len(c) * 0.08))
    if len(c) > fenster:
        linie = glaette(c, 0.08)
        versatz = (len(c) - len(linie)) // 2
        ax.plot(x[versatz:versatz + len(linie)], linie - basis,
                color="#e8c547", lw=1.6, alpha=0.9)

    t1, hi, t2 = marker(df, start, ende)
    # Versatz relativ zur Bildspanne - eine feste Punktzahl waere bei einem
    # 8-Punkte-Muster riesig und bei einem 140-Punkte-Muster unsichtbar.
    abstand = max(float(h.max() - l.min()), 1e-6) * 0.045
    for idx, form, farbe in ((t1, "^", "#5aa9e6"), (hi, "v", "#e8c547"),
                             (t2, "^", "#5aa9e6")):
        stelle = idx - von
        wert = (l[stelle] if form == "^" else h[stelle]) - basis
        ax.plot(stelle, wert + (-abstand if form == "^" else abstand), form,
                color=farbe, markersize=9, alpha=0.95)

    ax.set_xlim(-1, len(o))
    ax.set_ylabel("Punkte ueber dem Tief", color="#8b93a0", fontsize=9)
    ax.set_xlabel("Kerzen (1 Minute)", color="#8b93a0", fontsize=9)
    ax.tick_params(colors="#8b93a0", labelsize=8)
    for rand in ax.spines.values():
        rand.set_color("#2a2f38")
    ax.grid(color="#2a2f38", lw=0.5, alpha=0.5)
    fig.tight_layout()
    fig.savefig(ziel, facecolor=fig.get_facecolor())
    plt.close(fig)


# -- Ablage ----------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS fenster (
    fenster_id     INTEGER PRIMARY KEY,
    musterart      TEXT NOT NULL,
    art            TEXT NOT NULL,
    fenster_start  TEXT NOT NULL,
    fenster_ende   TEXT NOT NULL,
    dauer          INTEGER NOT NULL,
    hoehe          REAL,
    versatz        REAL,
    linker_arm     REAL,
    formfehler     REAL,
    gipfellage     REAL,
    atr            REAL,
    bild           TEXT NOT NULL,
    reihenfolge    INTEGER NOT NULL,
    UNIQUE (musterart, fenster_start, fenster_ende)
);

-- Das Urteil kennt die Klasse NICHT. Es haengt am Zeitfenster, damit sich
-- aus dieser Tabelle nicht zurueckrechnen laesst, was ein Kandidat war.
CREATE TABLE IF NOT EXISTS urteile (
    musterart      TEXT NOT NULL,
    fenster_start  TEXT NOT NULL,
    fenster_ende   TEXT NOT NULL,
    urteil         TEXT NOT NULL CHECK (urteil IN ('ja', 'nein', 'unklar')),
    ts             TEXT NOT NULL,
    PRIMARY KEY (musterart, fenster_start, fenster_ende)
);
"""


def schreibe_urteile_csv() -> int:
    """Die Urteilstabelle als CSV. Gibt die Zeilenzahl zurueck."""
    if not REFERENZ_DB.exists():
        return 0
    con = sqlite3.connect(REFERENZ_DB)
    try:
        zeilen = con.execute(
            "SELECT musterart, fenster_start, fenster_ende, urteil, ts "
            "FROM urteile ORDER BY musterart, fenster_start").fetchall()
    except sqlite3.OperationalError:      # Tabelle noch nicht angelegt
        return 0
    finally:
        con.close()
    with URTEILE_CSV.open("w", encoding="utf-8", newline="") as datei:
        schreiber = csv.writer(datei)
        schreiber.writerow(
            ["musterart", "fenster_start", "fenster_ende", "urteil", "ts"])
        schreiber.writerows(zeilen)
    return len(zeilen)


def lies_urteile_csv() -> int:
    """Urteile aus dem CSV zurueck in die Datenbank. Gibt die Zahl zurueck.

    Fuer den Fall, dass die SQLite-Datei verlorengeht - sie ist gitignoriert.
    Bestehende Urteile werden ueberschrieben, die Fenstertabelle nicht
    angetastet.
    """
    if not URTEILE_CSV.exists():
        return 0
    con = oeffne_db()
    n = 0
    with con:
        with URTEILE_CSV.open("r", encoding="utf-8", newline="") as datei:
            for zeile in csv.DictReader(datei):
                con.execute(
                    "INSERT OR REPLACE INTO urteile (musterart, fenster_start,"
                    " fenster_ende, urteil, ts) VALUES (?,?,?,?,?)",
                    (zeile["musterart"], zeile["fenster_start"],
                     zeile["fenster_ende"], zeile["urteil"], zeile["ts"]))
                n += 1
    con.close()
    return n


def oeffne_db() -> sqlite3.Connection:
    con = sqlite3.connect(REFERENZ_DB)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# -- Ablauf ----------------------------------------------------------------

def baue(anzahl_kandidaten: int, anzahl_zufall: int, seed: int) -> int:
    rng = np.random.default_rng(seed)
    BILDER.mkdir(parents=True, exist_ok=True)

    print("Kerzen laden ...", flush=True)
    df = lade_kerzen()
    print(f"  {len(df):,} Kerzen {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")

    print("Kandidaten sammeln (dauert einige Minuten) ...", flush=True)
    t0 = time.time()
    alle = sammle_kandidaten(df)
    if alle.empty:
        print("Keine Kandidaten gefunden - Abbruch.")
        return 1
    print(f"  {len(alle):,} Kandidaten in {time.time() - t0:.0f}s, "
          f"{alle['monat'].nunique()} Monate")

    kandidaten = ziehe_gestreut(alle, anzahl_kandidaten, rng)
    zufall = ziehe_zufallsfenster(df, alle, kandidaten, anzahl_zufall, rng)
    print(f"  gezogen: {len(kandidaten)} Kandidaten, {len(zufall)} Zufallsfenster")

    # Gemischte Reihenfolge. Ohne sie stuende die Klasse in der Reihenfolge.
    eintraege: list[dict] = []
    for _, k in kandidaten.iterrows():
        # Bis zur BESTAETIGUNG, nicht bis zum zweiten Tief - siehe Docstring.
        eintraege.append({
            "art": "kandidat",
            "start": int(k["erst_idx"]), "ende": int(k["bestaetigt_idx"]),
            "dauer": int(k["dauer"]), "hoehe": float(k["hoehe"]),
            "versatz": float(k["versatz"]), "linker_arm": float(k["linker_arm"]),
            "formfehler": float(k["formfehler"]),
            "gipfellage": float(k["gipfellage"]), "atr": float(k["atr"]),
        })
    for _, z in zufall.iterrows():
        eintraege.append({
            "art": "zufall",
            "start": int(z["erst_idx"]), "ende": int(z["zweit_idx"]),
            "dauer": int(z["dauer"]), "hoehe": None, "versatz": None,
            "linker_arm": None, "formfehler": None, "gipfellage": None,
            "atr": None,
        })
    rng.shuffle(eintraege)

    print(f"{len(eintraege)} Bilder zeichnen ...", flush=True)
    con = oeffne_db()
    with con:
        con.execute("DELETE FROM fenster WHERE musterart = ?", (MUSTERART,))
        for nr, e in enumerate(eintraege, 1):
            name = f"{MUSTERART}_{nr:04d}.png"
            zeichne(df, e["start"], e["ende"], BILDER / name)
            con.execute(
                "INSERT OR REPLACE INTO fenster (musterart, art, fenster_start,"
                " fenster_ende, dauer, hoehe, versatz, linker_arm, formfehler,"
                " gipfellage, atr, bild, reihenfolge)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (MUSTERART, e["art"], df.index[e["start"]].isoformat(),
                 df.index[e["ende"]].isoformat(), e["dauer"], e["hoehe"],
                 e["versatz"], e["linker_arm"], e["formfehler"],
                 e["gipfellage"], e["atr"], name, nr),
            )
            if nr % 25 == 0:
                print(f"  {nr}/{len(eintraege)}", flush=True)
    offen = con.execute(
        "SELECT COUNT(*) FROM fenster f WHERE f.musterart = ? AND NOT EXISTS "
        "(SELECT 1 FROM urteile u WHERE u.musterart = f.musterart "
        " AND u.fenster_start = f.fenster_start "
        " AND u.fenster_ende = f.fenster_ende)", (MUSTERART,)).fetchone()[0]
    con.close()

    print(f"\nFertig. {len(eintraege)} Fenster, davon {offen} unbeurteilt.")
    print(f"Bilder:   {BILDER}")
    print(f"Ablage:   {REFERENZ_DB}")
    print("\nJetzt die Seite starten:")
    print(r"  .venv\Scripts\python.exe -m werkzeuge.w_referenz_server")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kandidaten", type=int, default=150)
    p.add_argument("--zufall", type=int, default=100)
    p.add_argument("--seed", type=int, default=20260903)
    p.add_argument("--export", action="store_true",
                   help="nur die Urteile nach CSV schreiben, nichts neu bauen")
    p.add_argument("--import-urteile", action="store_true",
                   help="Urteile aus dem CSV in die Datenbank zuruecklesen")
    args = p.parse_args(argv)
    if args.export:
        print(f"{schreibe_urteile_csv()} Urteile nach {URTEILE_CSV}")
        return 0
    if args.import_urteile:
        print(f"{lies_urteile_csv()} Urteile aus {URTEILE_CSV} gelesen")
        return 0
    return baue(args.kandidaten, args.zufall, args.seed)


if __name__ == "__main__":
    sys.exit(main())
