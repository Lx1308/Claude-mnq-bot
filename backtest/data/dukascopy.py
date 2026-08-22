"""Dukascopy-Tickdaten als Backtest-Historie - AUSDRUECKLICH EINE NAEHERUNG.

WAS DIESE DATEN SIND UND WAS NICHT
----------------------------------
Dukascopy stellt seine Tickhistorie oeffentlich und ohne Konto bereit. Was
dort unter ``USATECHIDXUSD`` liegt, ist ein **CFD auf den Nasdaq-100-Index**,
gestellt vom Market Maker der Dukascopy Bank.

Es ist **kein** MNQ-Futures. Die Unterschiede sind nicht kosmetisch:

* **Andere Preisbildung.** Der Kurs stammt von einem einzelnen Market Maker,
  nicht aus dem CME-Orderbuch. Spreads, Slippage und Ausreisser folgen dessen
  Regeln, nicht denen der Boerse.
* **Kein echtes Handelsvolumen.** Die Volumenfelder tragen Dukascopys eigene
  Liquiditaet in Millionen Einheiten, nicht gehandelte Kontrakte. Alles, was
  auf Volumen beruht (relatives Volumen, Volume Profile, VWAP), ist damit
  etwas anderes als auf echten Futures-Daten.
* **Keine Kontraktablaeufe.** Ein Index-CFD rollt nicht. Echte MNQ-Historie
  hat vierteljaehrlich einen Rollover mit Preissprung; hier fehlt er.
* **Andere Sessionstruktur.** Der CFD handelt nach den Zeiten des Anbieters,
  nicht nach der CME-Globex-Session mit ihrer Wartungspause 16:00-17:00 CT.
  Das 18:00-ET-Rollover-Modell des Projekts passt hier nur naeherungsweise.

**Folge: Ergebnisse auf diesen Daten sind rein informativ.** Sie taugen dazu,
eine Strategie auf grobe Plausibilitaet und auf Programmierfehler abzuklopfen -
nicht als Grundlage fuer eine Entscheidung ueber echtes Geld. Das Projekt
verlangt das schon fuer den Backtest auf den eigenen NT8-Daten; hier gilt es
staerker.

Deshalb traegt jede erzeugte Datei eine Tabelle ``herkunft`` mit genau diesen
Angaben - dieselbe Haltung wie ``naeherung: true`` beim Volume Profile: eine
Naeherung wird gekennzeichnet, nicht stillschweigend als Messung ausgegeben.

WARUM NICHT ``duka``
--------------------
Das Paket ``duka`` laedt dieselben Dateien, setzt aber keinen
``User-Agent``-Header. Dukascopy beantwortet solche Anfragen seit geraumer
Zeit mit **HTTP 403** und einer Cloudflare-Seite - gemessen am 22.08.2026,
auch fuer ``EURUSD``, das es garantiert gibt. ``duka`` laeuft damit in seine
Wiederholungsschleife und bricht ab.

Der Download hier ist deshalb selbst gebaut: es sind rund 30 Zeilen, und das
Dekodieren wollten wir ohnehin unter Test haben.

DATEIFORMAT
-----------
Eine Datei je Stunde UTC, LZMA-komprimiert (``FORMAT_ALONE``). Darin Saetze zu
20 Byte, Big-Endian: Millisekunden seit Stundenbeginn (uint32), Ask und Bid als
Ganzzahl (uint32), Ask- und Bid-Volumen (float32).

Der Preisfaktor haengt am Instrument und ist **gemessen, nicht geraten**: fuer
``USATECHIDXUSD`` ergibt 29408411 / 1000 = 29408.41, was zum Nasdaq-Niveau
derselben Tage passt.

Der Monat in der URL ist **zero-based** (Januar = 00). Ein haeufiger Fehler,
der stillschweigend die Daten des Vormonats laedt.
"""

from __future__ import annotations

import lzma
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

URL = (
    "https://www.dukascopy.com/datafeed/{symbol}/{jahr}/{monat:02d}/{tag:02d}/"
    "{stunde:02d}h_ticks.bi5"
)

# Ohne diesen Header antwortet Dukascopy mit 403 (siehe Modul-Docstring).
BROWSER_HEADER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}

SATZ = struct.Struct(">IIIff")
SATZ_BYTES = SATZ.size  # 20


@dataclass(frozen=True)
class DukascopyInstrument:
    """Ein Dukascopy-Symbol samt seines gemessenen Preisfaktors."""

    symbol: str
    beschreibung: str
    preis_faktor: float

    @property
    def ist_naeherung(self) -> bool:
        """Immer True - es gibt hier kein Instrument, das ein Futures waere."""
        return True


NASDAQ_100_CFD = DukascopyInstrument(
    symbol="USATECHIDXUSD",
    beschreibung=(
        "CFD auf den Nasdaq-100-Index, gestellt von der Dukascopy Bank. "
        "KEIN MNQ-Futures: andere Preisbildung, kein echtes Handelsvolumen, "
        "keine Kontraktablaeufe, andere Sessionstruktur."
    ),
    preis_faktor=1000.0,
)

INSTRUMENTE: dict[str, DukascopyInstrument] = {
    "NAS100": NASDAQ_100_CFD,
}


class DukascopyFehler(RuntimeError):
    """Download oder Dekodierung fehlgeschlagen."""


# ---------------------------------------------------------------------------
# Dekodierung - der getestete Teil
# ---------------------------------------------------------------------------

def entpacke(rohdaten: bytes) -> bytes:
    """LZMA-Rohstrom einer bi5-Datei entpacken.

    Eine leere Datei ist **kein Fehler**: Dukascopy liefert fuer Stunden ohne
    Handel (Wochenende, Feiertag) eine Datei der Laenge 0. Das von einem
    echten Ausfall zu unterscheiden ist der Grund, warum hier nicht einfach
    eine Ausnahme fliegt.
    """
    if not rohdaten:
        return b""
    try:
        return lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(rohdaten)
    except lzma.LZMAError as fehler:
        raise DukascopyFehler(
            f"bi5-Datei nicht entpackbar ({fehler}). Kam statt der Datei eine "
            "HTML-Seite zurueck? Dukascopy antwortet ohne User-Agent mit 403."
        ) from fehler


def dekodiere_ticks(
    entpackt: bytes,
    stunde_utc: datetime,
    preis_faktor: float,
) -> pd.DataFrame:
    """Entpackte bi5-Bytes in einen Tick-Frame.

    Rueckgabe: Spalten ``ask``, ``bid``, ``ask_volume``, ``bid_volume`` mit
    UTC-Index. Bei leerer Eingabe ein leerer Frame mit demselben Schema -
    nicht ``None``, damit die Aufrufer nicht jedes Mal unterscheiden muessen.
    """
    if stunde_utc.tzinfo is None:
        raise ValueError("stunde_utc muss zeitzonenbehaftet sein.")
    if preis_faktor <= 0:
        raise ValueError("preis_faktor muss > 0 sein.")

    leer = pd.DataFrame(
        {
            "ask": pd.Series(dtype="float64"),
            "bid": pd.Series(dtype="float64"),
            "ask_volume": pd.Series(dtype="float64"),
            "bid_volume": pd.Series(dtype="float64"),
        },
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    if not entpackt:
        return leer

    if len(entpackt) % SATZ_BYTES:
        raise DukascopyFehler(
            f"Entpackte Laenge {len(entpackt)} ist kein Vielfaches von "
            f"{SATZ_BYTES}. Die Datei ist unvollstaendig oder kein bi5."
        )

    anzahl = len(entpackt) // SATZ_BYTES
    werte = [SATZ.unpack_from(entpackt, i * SATZ_BYTES) for i in range(anzahl)]
    versatz_ms, ask, bid, ask_vol, bid_vol = (np.array(spalte) for spalte in zip(*werte))

    basis = stunde_utc.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    index = pd.DatetimeIndex(
        [basis + timedelta(milliseconds=int(ms)) for ms in versatz_ms], tz="UTC"
    )

    return pd.DataFrame(
        {
            "ask": ask.astype("float64") / preis_faktor,
            "bid": bid.astype("float64") / preis_faktor,
            "ask_volume": ask_vol.astype("float64"),
            "bid_volume": bid_vol.astype("float64"),
        },
        index=index,
    )


def ticks_zu_minuten(ticks: pd.DataFrame) -> pd.DataFrame:
    """Verdichtet Ticks zu Ein-Minuten-Kerzen im Projektschema.

    Der Kurs ist die **Mitte** aus Bid und Ask. Ein Backtest, der auf dem Ask
    kaufte und auf dem Bid verkaufte, wuerde den Spread doppelt zahlen - das
    Kostenmodell des Projekts rechnet Slippage und Kommission ohnehin separat
    (``CostModel``), und beides zusammen waere eine Doppelbelastung.

    ``volume`` ist die Summe aus Bid- und Ask-Volumen. **Das ist kein
    gehandeltes Volumen**, sondern die Liquiditaet des Market Makers in
    Millionen Einheiten. Die Spalte existiert, weil das Projektschema sie
    verlangt; sie traegt aber keine Aussage ueber Marktaktivitaet.

    Minuten ohne Tick entstehen nicht als Zeile - genau wie NinjaTrader
    ohne Handel keine Kerze erzeugt. Eine Kerze zu erfinden hiesse, Handel
    zu behaupten, den es nicht gab.

    BESCHRIFTUNG MIT DER SCHLUSSZEIT - nicht der Anfangszeit
    --------------------------------------------------------
    Eine Kerze, die die Ticks von 14:00:00 bis 14:00:59 enthaelt, traegt den
    Zeitstempel **14:01**. So macht es NinjaTrader, und so liegen die Kerzen
    in ``data/ntbridge.sqlite3``.

    ``resample`` beschriftet standardmaessig mit dem **Anfang** des Fensters.
    Das ergibt einen Versatz von genau einer Minute - unauffaellig, weil die
    Kurse plausibel bleiben und die Reihe lueckenlos aussieht.

    Gemessen am 22.08.2026 gegen echte MNQ-Kerzen desselben Tages: mit
    Anfangs-Beschriftung korrelieren die Minutenaenderungen beider Reihen mit
    **r = -0.06**, also gar nicht; mit Schluss-Beschriftung mit **r = +0.95**.
    Beide Reihen bewegen sich um 5,3 Punkte je Minute - ohne diesen Abgleich
    haette nichts auf den Fehler hingedeutet.
    """
    if ticks.empty:
        return pd.DataFrame(
            {name: pd.Series(dtype="float64")
             for name in ("open", "high", "low", "close", "volume")},
            index=pd.DatetimeIndex([], tz="UTC"),
        )

    mitte = (ticks["ask"] + ticks["bid"]) / 2.0
    volumen = ticks["ask_volume"] + ticks["bid_volume"]

    # closed="left", label="right": das Fenster [14:00, 14:01) traegt den
    # Stempel 14:01 - die Konvention von NinjaTrader und damit des Projekts.
    takt = dict(rule="1min", closed="left", label="right")
    gruppen = mitte.resample(**takt)
    frame = pd.DataFrame(
        {
            "open": gruppen.first(),
            "high": gruppen.max(),
            "low": gruppen.min(),
            "close": gruppen.last(),
            "volume": volumen.resample(**takt).sum(),
        }
    )
    # resample fuellt Luecken mit NaN auf - die werden entfernt, nicht gefuellt.
    return frame.dropna(subset=["open", "high", "low", "close"])


# ---------------------------------------------------------------------------
# Download - nicht unter Test (Netz)
# ---------------------------------------------------------------------------

def stunden_url(instrument: DukascopyInstrument, stunde_utc: datetime) -> str:
    """Baut die URL. Achtung: der Monat ist zero-based."""
    moment = stunde_utc.astimezone(timezone.utc)
    return URL.format(
        symbol=instrument.symbol,
        jahr=moment.year,
        monat=moment.month - 1,
        tag=moment.day,
        stunde=moment.hour,
    )


def lade_stunde(
    instrument: DukascopyInstrument,
    stunde_utc: datetime,
    *,
    session=None,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """Laedt und dekodiert eine Stunde. Leerer Frame, wenn es nichts gab."""
    import requests

    holen = session.get if session is not None else requests.get
    url = stunden_url(instrument, stunde_utc)
    antwort = holen(url, headers=BROWSER_HEADER, timeout=timeout)

    if antwort.status_code == 404:
        # Stunde existiert nicht (ausserhalb der Historie) - kein Fehler.
        return ticks_zu_minuten(dekodiere_ticks(b"", stunde_utc, instrument.preis_faktor))
    if antwort.status_code != 200:
        raise DukascopyFehler(
            f"HTTP {antwort.status_code} fuer {url}. Bei 403 fehlt der "
            "User-Agent-Header."
        )

    ticks = dekodiere_ticks(
        entpacke(antwort.content), stunde_utc, instrument.preis_faktor
    )
    return ticks_zu_minuten(ticks)


__all__ = [
    "BROWSER_HEADER",
    "INSTRUMENTE",
    "NASDAQ_100_CFD",
    "URL",
    "DukascopyFehler",
    "DukascopyInstrument",
    "dekodiere_ticks",
    "entpacke",
    "lade_stunde",
    "stunden_url",
    "ticks_zu_minuten",
]
