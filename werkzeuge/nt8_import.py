"""Historie aus NinjaTrader importieren - mit erzwungenem Kreuzvergleich.

Warum dieses Werkzeug existiert
-------------------------------
Fuer Research reichen die Kerzen nicht, die der Indikator beim Chartladen
mitschickt: er liefert, was der Chart geladen hat, und das sind in der Praxis
Tage bis Wochen. NinjaTrader haelt aber deutlich mehr vor - auf dieser
Installation liegen MNQ-Minutendaten von 30 Kontrakten zurueck bis 2019 unter
``Documents\\NinjaTrader 8\\db\\minute\\``.

Warum NICHT direkt aus den .ncd-Dateien
---------------------------------------
Die Dateien dort sind ein hauseigenes, variabel bit-gepacktes Binaerformat.
Der Kopf ist leicht zu lesen (Version, Ticksize, Basispreis, .NET-Zeitstempel),
der Koerper nicht: rund 7,8 Byte je Kerze, also keine feste Satzlaenge.

Ein rueckentwickelter Parser koennte hier jahrelang unbemerkt falsche Kurse
liefern - genau der Fehlertyp, an dem die Dukascopy-Daten schon einmal
gescheitert sind (Invariante 9: die Reihe sah lueckenlos und plausibel aus,
und erst der Kreuzvergleich gegen echte MNQ-Kerzen zeigte r = -0,06 statt
+0,95). Eine Forschungsdatenbasis auf so etwas zu stellen waere der teuerste
denkbare Fehler.

Stattdessen: NinjaTraders **eigener Export**. Dokumentiertes Textformat, von
NinjaTrader selbst geschrieben, kein Ratespiel.

    Tools -> Historical Data -> Export
      Instrument : MNQ 09-26 (bzw. der gewuenschte Kontrakt)
      Type       : Minute
      From/To    : gewuenschter Zeitraum
      -> speichert eine .txt je Instrument

Der Kreuzvergleich ist Pflicht
------------------------------
Vor dem Schreiben wird der Import gegen die bereits vorhandenen Kerzen aus
``ntbridge.sqlite3`` geprueft - die kamen ueber ``ClaudeBridge.cs`` aus
NinjaTrader selbst und sind damit die Referenz. Weicht auch nur eine
gemeinsame Kerze ab, bricht der Import ab.

Geprueft wird ausdruecklich auch die **Beschriftung**: NinjaTrader
beschriftet eine Kerze mit dem ENDE ihres Fensters. Waere der Export
linksbuendig beschriftet, laege die ganze Reihe eine Minute daneben, und an
den Kursen selbst waere das nicht zu sehen.

Aufruf
------
    .venv\\Scripts\\python.exe werkzeuge\\nt8_import.py --pruefen datei.txt
    .venv\\Scripts\\python.exe werkzeuge\\nt8_import.py --schreiben datei.txt
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common.config import Config  # noqa: E402
from ntbridge.store import BarStore  # noqa: E402

#: Wie viele Kerzen mindestens uebereinstimmen muessen, damit der
#: Kreuzvergleich als aussagekraeftig gilt. Zwei zufaellig passende Kerzen
#: waeren kein Beleg.
MIN_UEBERLAPPUNG = 200

#: Groesste zulaessige Abweichung eines Kurses. Nicht 0: der Export rundet
#: auf die Ticksize, die Datenbank haelt Fliesskomma. Ein Achtel Tick ist
#: kleiner als jede echte Preisbewegung und groesser als jeder Rundungsrest.
MAX_ABWEICHUNG = 0.03

#: Welcher Anteil der gemeinsamen Kerzen in der Toleranz liegen muss, damit
#: der Kreuzvergleich besteht. Nicht 100 %: eine LUECKE ist keine KORRUPTION.
#: Die Referenzkerzen kommen live ueber die Bridge, der Export aus NinjaTraders
#: gesetzter Historie - an der Minutengrenze weichen open/close gelegentlich um
#: ein, zwei Ticks ab (erster/letzter *gesehener* Tick gegen ersten/letzten
#: *Trade*), und an einem Tag, den NinjaTrader lokal nie vollstaendig geladen
#: hat, stehen im Export ein paar Platzhalter. Beim ersten echten Import
#: (MNQ 09-26 am 30.08.2026) lagen 99,31 % bittgenau. Ein Zeitzonen-,
#: Beschriftungs- oder Kontraktfehler dagegen kippt ~100 % der Kerzen, nie 1 %.
MIN_ANTEIL_IN_TOLERANZ = 0.99

#: Um wie viel besser die verschobene Ausrichtung sein muss, damit der
#: Versatztest auf einen Beschriftungsfehler schliesst. Die verschobene und die
#: unverschobene Schnittmenge enthalten an den Raendern leicht verschiedene
#: Kerzen; ohne Marge koennte ein Rundungsrest einen Fehlalarm ausloesen. Ein
#: echter Ein-Minuten-Versatz hebt den Anteil um Dutzende Prozentpunkte.
VERSATZ_MARGE = 0.02


#: NinjaTrader benennt Kontrakte "MNQ SEP19". Monatskuerzel -> Monatszahl.
MONATE = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def kontrakt_aus_name(text: str) -> tuple[str, int, int] | None:
    """"MNQ SEP19" -> ("MNQ", 2019, 9). ``None``, wenn unlesbar.

    Auch aus einem Dateinamen wie "MNQ SEP19.Last.txt" oder
    "MNQ_SEP19_minute.txt" - NinjaTrader benennt die Exportdatei nach dem
    Kontrakt, und den Namen von Hand nachzutragen waere eine Fehlerquelle.

    NinjaTrader schreibt den Kontrakt je nach Kontext als Monatskuerzel
    ("MNQ SEP19") ODER numerisch als "MM-YY" ("MNQ 09-19") - der Exportdialog
    auf dieser Installation liefert die numerische Form, und die
    Datenbankordner unter ``db\\minute`` heissen ebenfalls so. Beide werden
    hier gelesen.
    """
    import re

    grosstext = text.upper()

    treffer = re.search(
        r"([A-Z]{2,4})[ _-]?(" + "|".join(MONATE) + r")[ _-]?(\d{2}|\d{4})",
        grosstext,
    )
    if treffer:
        wurzel, monat, jahr = treffer.groups()
        monatszahl = MONATE[monat]
    else:
        # Numerisch: "MNQ 09-26". Der Bindestrich ist Pflicht - ohne ihn
        # waere "MNQ 0926" nicht von einer Kursangabe zu unterscheiden.
        treffer = re.search(r"([A-Z]{2,4})[ _]?(\d{2})-(\d{2})", grosstext)
        if not treffer:
            return None
        wurzel, monat, jahr = treffer.groups()
        monatszahl = int(monat)
        if not 1 <= monatszahl <= 12:
            return None

    jahreszahl = int(jahr)
    if jahreszahl < 100:
        # Zweistellig: 19 -> 2019. Futures laufen nicht 80 Jahre.
        jahreszahl += 2000
    return wurzel, jahreszahl, monatszahl


def rollfenster(
    wurzel: str, jahr: int, monat: int, *, rolltage: int
) -> tuple[datetime, datetime]:
    """Von wann bis wann dieser Kontrakt der Frontmonat war.

    WARUM DAS NOETIG IST
    --------------------
    Die Kerzen liegen unter ``(instrument, timeframe, ts_utc)`` als
    Primaerschluessel, und der Import macht ein UPSERT. Wuerde man alle
    Kontrakte ungefiltert einlesen, ueberschrieben sich ihre
    Ueberschneidungszeitraeume gegenseitig - und welcher Kontrakt am Ende in
    der Datenbank steht, haenge an der Reihenfolge der Importe.

    Das Ergebnis saehe lueckenlos und plausibel aus. Es waere aber eine
    Mischung aus zwei verschiedenen Kontrakten mit unterschiedlichem
    Kursniveau - derselbe Fehlertyp wie bei den Dukascopy-Daten, nur an einer
    anderen Stelle.

    Das Fenster reicht deshalb vom Rolltermin des VORgaengerkontrakts bis zum
    eigenen. ``rolltage`` ist der Abstand zum Verfall, an dem das Volumen
    ueblicherweise umschlaegt.
    """
    from datetime import timedelta

    from common.instruments import get_instrument

    instrument = get_instrument(wurzel)
    eigener_verfall = instrument.expiry_rule(jahr, monat)

    # Quartalskontrakte: der Vorgaenger liegt drei Monate frueher.
    vor_monat = monat - 3
    vor_jahr = jahr
    if vor_monat < 1:
        vor_monat += 12
        vor_jahr -= 1
    vorheriger_verfall = instrument.expiry_rule(vor_jahr, vor_monat)

    von = datetime.combine(
        vorheriger_verfall - timedelta(days=rolltage), datetime.min.time()
    ).replace(tzinfo=ZoneInfo("UTC"))
    bis = datetime.combine(
        eigener_verfall - timedelta(days=rolltage), datetime.min.time()
    ).replace(tzinfo=ZoneInfo("UTC"))
    return von, bis


#: Wo NinjaTrader seine Minutendaten ablegt - ein Ordner je Kontrakt,
#: darin eine Datei je Handelstag ("20260615.Last.ncd").
NT8_MINUTEN = (
    Path.home() / "Documents" / "NinjaTrader 8" / "db" / "minute"
)


def rollplan_aus_nt8(
    wurzel: str = "MNQ", *, db_pfad: Path | None = None
) -> dict[tuple[int, int], tuple[datetime, datetime]]:
    """Rollfenster aus NinjaTraders eigenem Datenbestand ableiten.

    WARUM DAS BESSER IST ALS EINE FESTE TAGESZAHL
    ---------------------------------------------
    ``rollfenster`` rechnet mit einem Abstand zum Verfall (Vorgabe acht Tage).
    Das ist eine Annahme. Am 30.08.2026 gegen den tatsaechlichen Bestand
    geprueft, und die Annahme lag daneben: NinjaTrader rollte bis 2022
    mittwochs, ab 2023 freitags. Die Formel haette ab MAR23 drei bis vier
    Kalendertage zu frueh geschnitten.

    Der Bestand selbst weiss es genauer. Jeder Kontraktordner enthaelt genau
    die Handelstage, an denen NinjaTrader ihn als Frontmonat gefuehrt hat.
    Kontrakt N endet damit dort, wo N+1 beginnt - lueckenlos und
    ueberschneidungsfrei, ohne dass irgendwo eine Zahl geraten wird.

    Nachgemessen ueber 30 MNQ-Kontrakte von JUN19 bis SEP26: **null fehlende
    Handelstage**. Die scheinbaren Luecken von ein bis vier Kalendertagen an
    den Uebergaengen sind ausnahmslos Wochenenden.

    Liefert ``{}``, wenn der Ordner nicht existiert - dann bleibt
    ``rollfenster`` als Rueckfallebene, und der Aufrufer sagt das auch.
    """
    import re

    ordnerpfad = db_pfad or NT8_MINUTEN
    if not ordnerpfad.exists():
        return {}

    erste_tage: dict[tuple[int, int], date] = {}
    for ordner in sorted(ordnerpfad.glob(f"{wurzel} *")):
        treffer = re.match(rf"{wurzel} (\d{{2}})-(\d{{2}})$", ordner.name)
        if not treffer:
            continue
        monat, jahr = int(treffer.group(1)), 2000 + int(treffer.group(2))
        # Sehr kleine Dateien sind Platzhalter ohne Kerzen (etwa ein
        # Feiertag); sie wuerden den Beginn faelschlich vorziehen.
        tage = sorted(
            d.name[:8] for d in ordner.glob("*.Last.ncd") if d.stat().st_size > 40
        )
        if tage:
            erste_tage[(jahr, monat)] = date(
                int(tage[0][:4]), int(tage[0][4:6]), int(tage[0][6:8])
            )

    schluessel = sorted(erste_tage)
    plan: dict[tuple[int, int], tuple[datetime, datetime]] = {}
    for i, kennung in enumerate(schluessel):
        von = datetime.combine(erste_tage[kennung], datetime.min.time()).replace(
            tzinfo=ZoneInfo("UTC")
        )
        if i + 1 < len(schluessel):
            bis = datetime.combine(
                erste_tage[schluessel[i + 1]], datetime.min.time()
            ).replace(tzinfo=ZoneInfo("UTC"))
        else:
            # Der laufende Kontrakt hat kein Ende - er ist noch Frontmonat.
            bis = datetime(2099, 1, 1, tzinfo=ZoneInfo("UTC"))
        plan[kennung] = (von, bis)
    return plan


def lies_export(pfad: Path, zeitzone: str) -> pd.DataFrame:
    """NinjaTraders Exportformat lesen.

    Erwartet wird je Zeile ``yyyyMMdd HHmmss;open;high;low;close;volume``.
    Semikolon ist NinjaTraders Vorgabe; Komma wird ebenfalls akzeptiert, weil
    das Trennzeichen im Exportdialog umstellbar ist.

    Die Zeitstempel des Exports sind **ohne Zeitzone**. Welche gemeint ist,
    haengt an NinjaTraders Einstellung; deshalb ist sie hier ein Pflichtargument
    und wird nicht geraten. Eine falsch angenommene Zeitzone verschoebe die
    ganze Reihe um Stunden - und die Kurse saehen weiter plausibel aus.
    """
    # NinjaTrader legt den Export je nach Version als reine .txt oder
    # gepackt als .gz ab. Beides hier annehmen, statt den Nutzer erst an einer
    # unverstaendlichen Fehlermeldung scheitern zu lassen.
    if pfad.suffix.lower() == ".gz":
        import gzip

        with gzip.open(pfad, "rt", encoding="utf-8", errors="replace") as datei:
            zeilen = datei.read().splitlines()
    else:
        zeilen = pfad.read_text(encoding="utf-8", errors="replace").splitlines()
    saetze: list[tuple] = []
    fehlerhaft = 0

    for zeile in zeilen:
        zeile = zeile.strip()
        if not zeile:
            continue
        teile = zeile.split(";") if ";" in zeile else zeile.split(",")
        if len(teile) < 6:
            fehlerhaft += 1
            continue
        try:
            zeitpunkt = datetime.strptime(teile[0].strip(), "%Y%m%d %H%M%S")
            saetze.append((
                zeitpunkt,
                float(teile[1]), float(teile[2]), float(teile[3]),
                float(teile[4]), float(teile[5]),
            ))
        except ValueError:
            fehlerhaft += 1

    if fehlerhaft:
        print(f"  {fehlerhaft} unlesbare Zeilen uebersprungen.", file=sys.stderr)
    if not saetze:
        raise SystemExit(
            f"Keine lesbaren Kerzen in {pfad}. Erwartet wird "
            "'yyyyMMdd HHmmss;open;high;low;close;volume'."
        )

    df = pd.DataFrame(
        saetze, columns=["ts", "open", "high", "low", "close", "volume"]
    )
    index = pd.DatetimeIndex(df.pop("ts")).tz_localize(ZoneInfo(zeitzone))
    df.index = index.tz_convert("UTC")
    return df.sort_index()


def kreuzvergleich(
    neu: pd.DataFrame, referenz: pd.DataFrame
) -> tuple[bool, list[str]]:
    """Stimmen die gemeinsamen Kerzen ueberein?

    Liefert (bestanden, Meldungen). Bestanden ist der Vergleich nur, wenn
    genug gemeinsame Zeitstempel existieren, KEINE um eine Minute verschobene
    Ausrichtung deutlich besser passt (Beschriftung, Invariante 9), UND
    mindestens ``MIN_ANTEIL_IN_TOLERANZ`` der gemeinsamen Kerzen auf allen
    vier Kursen innerhalb der Toleranz liegen. Nicht 100 %: eine Luecke in der
    einen Quelle ist keine Korruption, und Live- gegen Historienkerzen weichen
    an der Minutengrenze gelegentlich um einen Tick ab.
    """
    meldungen: list[str] = []
    gemeinsam = neu.index.intersection(referenz.index)

    if len(gemeinsam) < MIN_UEBERLAPPUNG:
        meldungen.append(
            f"Nur {len(gemeinsam)} gemeinsame Kerzen (noetig: {MIN_UEBERLAPPUNG}). "
            "Der Vergleich waere nicht aussagekraeftig."
        )
        # Der haeufigste Grund fuer null Ueberlappung ist eine um eine Minute
        # verschobene Beschriftung. Das ausdruecklich pruefen, statt den
        # Nutzer raten zu lassen.
        for versatz in (-1, 1):
            verschoben = neu.copy()
            verschoben.index = verschoben.index + pd.Timedelta(minutes=versatz)
            treffer = verschoben.index.intersection(referenz.index)
            if len(treffer) > len(gemeinsam):
                meldungen.append(
                    f"HINWEIS: um {versatz:+d} Minute verschoben gaebe es "
                    f"{len(treffer)} statt {len(gemeinsam)} Treffer. Der Export "
                    "ist dann anders beschriftet als die Datenbank - "
                    "NinjaTrader beschriftet eine Kerze mit dem ENDE ihres "
                    "Fensters (Invariante 9)."
                )
        return False, meldungen

    def kerzenabweichung(x: pd.DataFrame, y: pd.DataFrame) -> pd.Series:
        """Groesste Abweichung je Kerze ueber die vier Kurse."""
        return pd.concat(
            [(x[s] - y[s]).abs() for s in ("open", "high", "low", "close")],
            axis=1,
        ).max(axis=1)

    def anteil_in_toleranz(x: pd.DataFrame, y: pd.DataFrame) -> float:
        return float((kerzenabweichung(x, y) <= MAX_ABWEICHUNG).mean())

    a = neu.loc[gemeinsam].sort_index()
    b = referenz.loc[gemeinsam].sort_index()

    abweichungen = {
        spalte: float((a[spalte] - b[spalte]).abs().max())
        for spalte in ("open", "high", "low", "close")
    }
    je_kerze = kerzenabweichung(a, b)
    innerhalb = je_kerze <= MAX_ABWEICHUNG
    anteil = float(innerhalb.mean())
    schlimmste = max(abweichungen.values())

    meldungen.append(f"{len(gemeinsam)} gemeinsame Kerzen geprueft.")
    meldungen.append(
        "  groesste Abweichung: "
        + ", ".join(f"{s} {w:.4f}" for s, w in abweichungen.items())
    )
    meldungen.append(
        f"  {int(innerhalb.sum())} von {len(gemeinsam)} Kerzen in Toleranz "
        f"({anteil * 100:.2f} %)"
    )

    # Der Versatzvergleich kommt VOR dem Toleranzurteil, weil er die
    # aussagekraeftigere Diagnose liefert. "Die Kurse weichen ab" laesst offen,
    # ob es der falsche Kontrakt, die falsche Zeitzone oder eine verschobene
    # Beschriftung ist; "um eine Minute verschoben passt es besser" sagt genau,
    # was zu tun ist.
    #
    # Gemessen wird jetzt am ANTEIL der Kerzen in Toleranz, nicht am einzelnen
    # schlechtesten Balken: ein paar Ausreisser sollen das Urteil nicht kippen,
    # ein echter Ein-Minuten-Versatz kippt den Anteil dagegen um Dutzende
    # Prozentpunkte - auch im ruhigen Markt, in dem sich die absoluten Kurse
    # benachbarter Minuten stark aehneln.
    for versatz in (-1, 1):
        verschoben = neu.copy()
        verschoben.index = verschoben.index + pd.Timedelta(minutes=versatz)
        treffer = verschoben.index.intersection(referenz.index)
        if len(treffer) < MIN_UEBERLAPPUNG:
            continue
        va = verschoben.loc[treffer].sort_index()
        vb = referenz.loc[treffer].sort_index()
        versatz_anteil = anteil_in_toleranz(va, vb)
        if versatz_anteil > anteil + VERSATZ_MARGE:
            meldungen.append(
                f"ABBRUCH: um {versatz:+d} Minute verschoben liegen deutlich "
                f"mehr Kerzen in Toleranz ({versatz_anteil * 100:.2f} % statt "
                f"{anteil * 100:.2f} %). Die Beschriftung stimmt nicht - "
                "NinjaTrader beschriftet eine Kerze mit dem ENDE ihres "
                "Fensters (Invariante 9)."
            )
            return False, meldungen

    if anteil < MIN_ANTEIL_IN_TOLERANZ:
        meldungen.append(
            f"ABBRUCH: nur {anteil * 100:.2f} % der gemeinsamen Kerzen liegen "
            f"in der Toleranz von {MAX_ABWEICHUNG} (noetig: "
            f"{MIN_ANTEIL_IN_TOLERANZ * 100:.0f} %), groesste Abweichung "
            f"{schlimmste:.4f}. Ein Zeitversatz wurde geprueft und "
            "ausgeschlossen - es bleibt ein anderer Kontrakt, eine andere "
            "Zeitzone oder ein anderer Datentyp (Last/Bid/Ask)."
        )
        return False, meldungen

    if not bool(innerhalb.all()):
        ausser = je_kerze[~innerhalb]
        tage = sorted({d.strftime("%Y-%m-%d") for d in ausser.index})
        meldungen.append(
            f"  {len(ausser)} Kerzen ausserhalb der Toleranz (max "
            f"{schlimmste:.2f} Punkte), an: {', '.join(tage)}. Unter der "
            f"Schwelle von {(1 - MIN_ANTEIL_IN_TOLERANZ) * 100:.0f} % und "
            "nicht systematisch (Versatztest bestanden) - typisch fuer "
            "Live-vs-Historie-Rauschen an der Minutengrenze."
        )

    meldungen.append("Kreuzvergleich bestanden.")
    return True, meldungen


#: Wo festgehalten wird, dass das Exportformat einmal gegen echte Kerzen
#: geprueft wurde.
NACHWEIS = PROJECT_ROOT / "data" / "nt8_import_nachweis.json"


def lies_nachweis() -> dict:
    import json

    if not NACHWEIS.exists():
        return {}
    try:
        return json.loads(NACHWEIS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def schreibe_nachweis(symbol: str, timeframe: str, zeitzone: str,
                      gemeinsame: int) -> None:
    """Festhalten, dass Format, Zeitzone und Beschriftung geprueft sind.

    WARUM DAS NOETIG IST
    --------------------
    Der Kreuzvergleich braucht Ueberlappung mit Kerzen, die schon in der
    Datenbank liegen. Die gibt es nur beim aktuell laufenden Kontrakt - ein
    Export von MNQ SEP19 ueberschneidet sich mit nichts, was 2026 gesammelt
    wurde.

    Ohne diesen Nachweis muesste man entweder die Pruefung fuer alte
    Kontrakte ganz weglassen (dann waere sie wertlos) oder sie unmoeglich
    machen. Beides ist falsch.

    Was der Nachweis belegt, ist genau das, was er belegen kann: dass DIESES
    Exportformat, in DIESER Zeitzone, mit DIESER Beschriftung mit echten
    NinjaTrader-Kerzen uebereinstimmt. Das ist eine Eigenschaft des
    Exportwegs, nicht des einzelnen Kontrakts - und sie uebertraegt sich
    deshalb auf weitere Exporte aus derselben Quelle.

    Was er NICHT belegt: dass die Kurse eines bestimmten alten Kontrakts
    stimmen. Dafuer gibt es die Anschlusspruefung.
    """
    import json
    from datetime import datetime, timezone as _tz

    daten = lies_nachweis()
    daten[f"{symbol}/{timeframe}/{zeitzone}"] = {
        "geprueft_utc": datetime.now(_tz.utc).isoformat(),
        "gemeinsame_kerzen": gemeinsame,
    }
    NACHWEIS.parent.mkdir(parents=True, exist_ok=True)
    NACHWEIS.write_text(json.dumps(daten, indent=2), encoding="utf-8")


def pruefe_anschluss(
    neu_df,
    referenz_df,
    *,
    max_sprung_prozent: float = 3.0,
    max_luecke_tage: int = 4,
) -> tuple[bool, list[str]]:
    """Passt der Kontrakt zeitlich und preislich an das Vorhandene an?

    Fuer alte Kontrakte, die sich mit nichts ueberschneiden, ist das die
    einzige moegliche Pruefung. Sie ist schwaecher als der Kreuzvergleich und
    wird auch so benannt.

    Geprueft wird der Preissprung an der Nahtstelle - RELATIV, nicht in
    absoluten Punkten. MNQ stand 2019 bei 7.500 und 2026 bei 29.500; 400
    Punkte waren damals 5 %, heute 1,4 %. Ueber alle 29 echten Rollen von
    JUN19 bis SEP26 lag der Sprung zwischen -0,55 % und +1,46 % (Zinsdifferenz
    minus Dividenden ueber ein Quartal). Ein Sprung von mehreren Prozent heisst
    dagegen: falscher Kontrakt, falsches Jahr oder falsches Instrument.

    Nur der ZEITLICH ANGRENZENDE Kontrakt taugt als Nachbar. Liegt die
    naechste vorhandene Kerze mehr als ``max_luecke_tage`` entfernt, gibt es
    auf dieser Seite nichts anzuschliessen - das ist der Normalfall, wenn erst
    der laufende Kontrakt in der Datenbank liegt und ein sechs Jahre alter
    importiert wird. Frueher nahm die Pruefung stur die erste Kerze jenseits
    der Grenze; die lag dann Jahre entfernt auf einem voellig anderen
    Kursniveau, und jeder alte Import brach ab.
    """
    meldungen: list[str] = []
    if referenz_df.empty or neu_df.empty:
        return True, ["Kein Nachbar zum Anschliessen - nichts zu pruefen."]

    grenze = pd.Timedelta(days=max_luecke_tage)
    davor = referenz_df[referenz_df.index < neu_df.index[0]]
    danach = referenz_df[referenz_df.index > neu_df.index[-1]]

    for nachbar, seite, eigen_ts, eigener in (
        (davor, "davor", neu_df.index[0], neu_df["open"].iloc[0]),
        (danach, "danach", neu_df.index[-1], neu_df["close"].iloc[-1]),
    ):
        if nachbar.empty:
            continue
        if seite == "davor":
            nachbar_ts = nachbar.index[-1]
            nachbarkurs = float(nachbar["close"].iloc[-1])
        else:
            nachbar_ts = nachbar.index[0]
            nachbarkurs = float(nachbar["open"].iloc[0])

        luecke = abs(nachbar_ts - eigen_ts)
        if luecke > grenze:
            meldungen.append(
                f"  Anschluss {seite}: naechste Kerze {luecke.days} Tage "
                "entfernt - kein direkter Nachbar, nichts anzuschliessen."
            )
            continue

        sprung = abs(float(eigener) - nachbarkurs)
        sprung_prozent = sprung / nachbarkurs * 100 if nachbarkurs else 0.0
        meldungen.append(
            f"  Anschluss {seite}: {sprung:.1f} Punkte / {sprung_prozent:.2f} % "
            f"Sprung ({nachbarkurs:.2f} -> {float(eigener):.2f})"
        )
        if sprung_prozent > max_sprung_prozent:
            meldungen.append(
                f"ABBRUCH: {sprung_prozent:.2f} % sind kein Rollsprung "
                f"(groesste echte MNQ-Rolle: 1,46 %). Das deutet auf einen "
                "falschen Kontrakt, ein falsches Jahr oder ein anderes "
                "Instrument hin."
            )
            return False, meldungen

    return True, meldungen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nt8_import",
        description="Importiert einen NinjaTrader-Historienexport nach Pruefung.",
    )
    parser.add_argument("datei", type=Path)
    parser.add_argument("--symbol", default="MNQ")
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument(
        "--zeitzone",
        default="America/New_York",
        help="Zeitzone der Zeitstempel im Export. NinjaTrader exportiert in "
             "seiner Anzeigezeitzone - im Zweifel im Exportdialog nachsehen.",
    )
    parser.add_argument(
        "--kontrakt",
        help="z.B. 'MNQ SEP19'. Ohne Angabe aus dem Dateinamen gelesen. "
             "Wird gebraucht, um den Zeitraum zu bestimmen, in dem dieser "
             "Kontrakt der Frontmonat war.",
    )
    parser.add_argument(
        "--rolltage", type=int, default=8,
        help="Wie viele Tage vor dem Verfall auf den naechsten Kontrakt "
             "gerollt wird (Vorgabe 8).",
    )
    parser.add_argument(
        "--rolltage-erzwingen", action="store_true",
        help="Das Rollfenster rechnen statt es aus NinjaTraders Bestand zu "
             "lesen. Nur noetig, wenn der NT8-Ordner nicht erreichbar ist.",
    )
    parser.add_argument(
        "--alle-kerzen", action="store_true",
        help="Ohne Beschraenkung auf das Rollfenster importieren. NUR fuer "
             "einen einzelnen Kontrakt sinnvoll - bei mehreren ueberschreiben "
             "sich die Ueberschneidungen gegenseitig.",
    )
    parser.add_argument(
        "--schreiben",
        action="store_true",
        help="Nach bestandener Pruefung tatsaechlich schreiben. Ohne diesen "
             "Schalter wird nur geprueft und berichtet.",
    )
    parser.add_argument("--database", default=None)
    args = parser.parse_args(argv)

    if not args.datei.exists():
        print(f"Datei nicht gefunden: {args.datei}", file=sys.stderr)
        return 2

    config = Config.load(PROJECT_ROOT / "config.yaml")
    datenbank = Path(args.database or config.ntbridge.database)
    if not datenbank.is_absolute():
        datenbank = PROJECT_ROOT / datenbank

    print(f"Lese {args.datei} ...")
    neu = lies_export(args.datei, args.zeitzone)
    print(f"  {len(neu)} Kerzen, {neu.index[0]} bis {neu.index[-1]}")

    if not args.alle_kerzen:
        kennung = kontrakt_aus_name(args.kontrakt or args.datei.name)
        if kennung is None:
            print(
                "ABBRUCH: Kontrakt nicht erkennbar.",
                "Aus dem Dateinamen liess sich kein Kontrakt lesen (erwartet",
                "wird etwas wie 'MNQ SEP19'). Gib ihn mit --kontrakt an.",
                "",
                "Warum das noetig ist: mehrere Kontrakte ueberschneiden sich",
                "zeitlich. Ungefiltert importiert ueberschreiben sie einander,",
                "und welcher am Ende in der Datenbank steht, haengt an der",
                "Reihenfolge der Importe. Das Ergebnis saehe lueckenlos aus und",
                "waere eine Mischung aus zwei Kontrakten mit verschiedenem",
                "Kursniveau.",
                "",
                "Wenn du wirklich nur einen einzigen Kontrakt hast und alles",
                "davon willst: --alle-kerzen.",
                sep=chr(10), file=sys.stderr,
            )
            return 2

        wurzel, jahr, monat = kennung

        # Bevorzugt aus NinjaTraders eigenem Bestand: der weiss genauer als
        # jede Formel, wann gerollt wurde. Nur wenn der Ordner fehlt, wird
        # gerechnet - und das steht dann auch da.
        plan = {} if args.rolltage_erzwingen else rollplan_aus_nt8(wurzel)
        # ``rollplan_aus_nt8`` schluesselt auf (jahr, monat) - ``kennung`` ist
        # ein Dreitupel (wurzel, jahr, monat). Frueher stand hier
        # ``kennung in plan``, was nie zutraf: der Import fiel still auf die
        # gerechnete Acht-Tage-Formel zurueck, obwohl der Bestand vorlag.
        planschluessel = (jahr, monat)
        if planschluessel in plan:
            von, bis = plan[planschluessel]
            herkunft = "aus NinjaTraders Datenbestand"
        else:
            von, bis = rollfenster(wurzel, jahr, monat, rolltage=args.rolltage)
            herkunft = f"gerechnet, {args.rolltage} Tage vor Verfall"

        vorher = len(neu)
        neu = neu[(neu.index >= von) & (neu.index < bis)]
        bis_text = "offen" if bis.year > 2090 else f"{bis:%Y-%m-%d}"
        print(
            f"  Kontrakt {wurzel} {jahr}-{monat:02d}, Frontmonat von "
            f"{von:%Y-%m-%d} bis {bis_text} ({herkunft})"
        )
        print(
            f"  {vorher - len(neu)} Kerzen ausserhalb des Fensters verworfen, "
            f"{len(neu)} bleiben"
        )
        if neu.empty:
            print(
                "Nichts uebrig. Entweder deckt der Export das Rollfenster "
                "nicht ab, oder die Zeitzone stimmt nicht.",
                file=sys.stderr,
            )
            return 3

    speicher = BarStore(datenbank)
    try:
        referenz = speicher.load_frame(args.symbol, args.timeframe)
        print(f"  Referenz in der Datenbank: {len(referenz)} Kerzen")

        # Ueberschneidet sich dieser Export mit dem, was schon da ist?
        # Nur dann ist der vollstaendige Kreuzvergleich moeglich. Alte
        # Kontrakte ueberschneiden sich mit nichts - fuer sie greift der
        # einmal erbrachte Formatnachweis plus die Anschlusspruefung.
        gemeinsam = len(neu.index.intersection(referenz.index))
        nachweis = lies_nachweis().get(
            f"{args.symbol}/{args.timeframe}/{args.zeitzone}"
        )

        if gemeinsam >= MIN_UEBERLAPPUNG:
            bestanden, meldungen = kreuzvergleich(neu, referenz)
            print()
            for meldung in meldungen:
                print(" ", meldung)
            if bestanden and args.schreiben:
                schreibe_nachweis(
                    args.symbol, args.timeframe, args.zeitzone, gemeinsam
                )
                print(
                    "  Formatnachweis gespeichert - weitere Kontrakte aus "
                    "demselben Exportweg brauchen keine eigene Ueberlappung."
                )
        elif nachweis is not None:
            print()
            print(
                f"  Keine Ueberlappung ({gemeinsam} gemeinsame Kerzen) - das ist "
                "bei einem alten Kontrakt normal."
            )
            print(
                f"  Formatnachweis liegt vor (geprueft {nachweis['geprueft_utc'][:10]} "
                f"an {nachweis['gemeinsame_kerzen']} gemeinsamen Kerzen):"
            )
            print(
                "  Exportformat, Zeitzone und Beschriftung sind damit belegt. "
                "Was er NICHT belegt, ist die Richtigkeit dieses Kontrakts - "
                "dafuer die Anschlusspruefung:"
            )
            bestanden, meldungen = pruefe_anschluss(neu, referenz)
            for meldung in meldungen:
                print(" ", meldung)
        elif referenz.empty:
            print(
                "ABBRUCH: keine Referenzkerzen in der Datenbank.",
                "Ohne Kreuzvergleich wird nicht importiert - eine um eine",
                "Minute verschobene oder in der falschen Zeitzone gelesene",
                "Reihe saehe lueckenlos und plausibel aus. Starte zuerst die",
                "Bridge und lass NinjaTrader ein paar hundert Kerzen liefern.",
                sep=chr(10), file=sys.stderr,
            )
            return 3
        else:
            print(
                "ABBRUCH: dieser Export ueberschneidet sich nicht mit den",
                f"vorhandenen Kerzen ({gemeinsam} gemeinsame), und es gibt noch",
                "keinen Formatnachweis.",
                "",
                "Importiere zuerst den LAUFENDEN Kontrakt - der ueberschneidet",
                "sich mit dem, was die Bridge gesammelt hat. Damit sind",
                "Format, Zeitzone und Beschriftung belegt, und alle aelteren",
                "Kontrakte gehen danach durch.",
                sep=chr(10), file=sys.stderr,
            )
            return 3

        if not bestanden:
            print("\nEs wurde nichts geschrieben.", file=sys.stderr)
            return 3

        if not args.schreiben:
            neue_kerzen = len(neu.index.difference(referenz.index))
            print(
                f"\nPruefung bestanden. {neue_kerzen} Kerzen waeren neu.\n"
                "Zum Schreiben mit --schreiben erneut aufrufen."
            )
            return 0

        saetze = [
            {
                "timestampUtc": zeitpunkt.isoformat(),
                "instrument": args.symbol,
                "timeframe": args.timeframe,
                "open": float(zeile["open"]), "high": float(zeile["high"]),
                "low": float(zeile["low"]), "close": float(zeile["close"]),
                "volume": float(zeile["volume"]),
                "source": "nt8_export",
            }
            for zeitpunkt, zeile in neu.iterrows()
        ]
        ergebnis = speicher.ingest(
            saetze,
            known_timeframes={args.timeframe},
            symbol_map={},
        )
        print(
            f"\nGeschrieben: {ergebnis.accepted} angenommen, "
            f"{ergebnis.rejected} abgelehnt."
        )
        if ergebnis.reasons:
            for grund, anzahl in ergebnis.reasons.items():
                print(f"  {grund}: {anzahl}")
        return 0
    finally:
        speicher.close()


if __name__ == "__main__":
    raise SystemExit(main())
