"""Die echte NinjaTrader-Historie als Backtest-Datenquelle.

WARUM DIESES MODUL DER WICHTIGSTE FEHLENDE BAUSTEIN WAR
-------------------------------------------------------
Bis zum 30.08.2026 kannte ``create_provider`` ausschliesslich ``"csv"``. In
``data/`` liegt als einzige CSV der **synthetische** ``DEMO_1m.csv`` - ein
Zufallspfad zum Ausprobieren der CLI. Jeder Forschungslauf des Projekts
musste deshalb entweder auf diesem Zufallspfad oder auf der
Dukascopy-Naeherung rechnen (Index-CFD statt MNQ-Futures, laut Invariante 11
"rein informativ").

Seit dem NT8-Import liegen 2,57 Mio **echte** MNQ-Minutenkerzen ab Mai 2019 in
``data/ntbridge.sqlite3`` - und die Engine kam nicht an sie heran. Das ist
MASTERPLAN Abschnitt X.1, dort schon als P0 eingestuft.

WAS HIER GELESEN WIRD - UND WAS NICHT
-------------------------------------
Gelesen wird **ausschliesslich die 1m-Reihe**. Groebere Timeframes werden
hier aus ihr aggregiert, obwohl in derselben Datei auch fertige 1h/4h/1d-
Zeilen liegen. Das ist Absicht:

* Die gespeicherten groben Zeilen (``source='resampled_1m'``) sind eine
  **Anzeigehilfe** fuer den Chart, nachgezogen von einer Hintergrundschleife
  im Serverprozess. Ob sie aktuell sind, haengt daran, ob diese Schleife lief.
  Ein Forschungsergebnis darf nicht davon abhaengen, ob die Oberflaeche
  gestartet war.
* Aggregiert wird mit ``common.timeframes.resample_ohlcv`` - derselben
  Funktion, die auch die Anzeige benutzt. Das Ergebnis ist also identisch,
  nur die Herkunft ist unabhaengig.
* 5m und 15m liegen ohnehin nicht vorberechnet vor.

DER ROLLSPRUNG - EIN STILLER FEHLER, DER HIER ABGEFANGEN WIRD
-------------------------------------------------------------
Die Reihe ist aus **30 Quartalskontrakten** zusammengesetzt (JUN19 bis SEP26).
An jeder der 29 Nahtstellen springt der Preis, weil ein anderer Kontrakt
uebernimmt - gemessen zwischen -0,55 % und +1,46 %.

Fuer den Backtest sieht so eine Naht aus wie eine Uebernacht-Kurslueke. Sie
ist aber keine: es hat sich nichts am Markt bewegt, nur der gehandelte
Kontrakt gewechselt. Eine Strategie auf Kurslueken saehe dort 29
Scheinsignale, und **an den Kursen selbst waere nichts zu sehen** - derselbe
Fehlertyp wie bei der Dukascopy-Beschriftung (Invariante 9).

Deshalb weist der Provider die Nahtstellen ueber
:attr:`NtBridgeDataProvider.rollgrenzen` aus. Wer Kurslueken untersucht,
schliesst sie aus; wer es nicht tut, hat es wenigstens gewusst. Die Kurse
selbst werden **nicht** rueckangepasst: eine Rueckanpassung veraendert
historische Preise und macht Niveau-Aussagen (Vortageshoch, VWAP-Abstand in
Punkten) unvergleichbar. Was hier steht, ist, was damals gehandelt wurde.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from backtest.data.base import BarRequest, DataProvider, DataProviderError
from common.sessions import SessionConfig
from common.timeframes import CANONICAL_TIMEFRAMES, resample_ohlcv

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Vorgabepfad der Kerzendatenbank - dieselbe Datei, in die der
#: ntbridge-Empfaenger schreibt und aus der die Oberflaeche liest.
STANDARD_DATENBANK = PROJECT_ROOT / "data" / "ntbridge.sqlite3"

#: Die Basisreihe. Alles Groebere wird daraus abgeleitet, nie umgekehrt.
BASIS_TIMEFRAME = "1m"

#: Minutenzahl -> kanonischer Timeframe-Name. Nur was ``resample_ohlcv``
#: auch kennt; eine Zahl ohne Entsprechung wird abgelehnt statt still auf den
#: naechstbesten Wert gerundet.
MINUTEN_ZU_TIMEFRAME: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    240: "4h",
    1440: "1d",
}

#: Ab welchem relativen Preissprung zwischen zwei aufeinanderfolgenden Kerzen
#: eine Kontraktnaht vermutet wird, wenn der Kontraktbestand nicht lesbar ist.
#: Die groesste gemessene echte MNQ-Rolle lag bei 1,46 %; normale
#: Uebernachtluecken bleiben klar darunter. Der Wert ist bewusst grosszuegig -
#: er dient der Kennzeichnung, nicht dem Verwerfen von Daten.
ROLLSPRUNG_VERDACHT_PROZENT = 0.9


def _als_utc(zeitpunkt) -> pd.Timestamp:
    """Zeitangabe -> UTC-Timestamp, egal ob mit oder ohne Zeitzone.

    ``pd.Timestamp(x, tz="UTC")`` wirft, wenn ``x`` schon eine Zone hat -
    und ``BarRequest`` bekommt beides, je nachdem ob die CLI oder ein
    Forschungsskript ruft.
    """
    marke = pd.Timestamp(zeitpunkt)
    return marke.tz_localize("UTC") if marke.tz is None else marke.tz_convert("UTC")


class NtBridgeDataProvider(DataProvider):
    """Liest die echte MNQ-Historie aus ``ntbridge.sqlite3``.

    Beispiel::

        provider = NtBridgeDataProvider()
        rahmen = provider.load(BarRequest("MNQ", interval_minutes=5))
        provider.rollgrenzen   # Zeitstempel der Kontraktnahtstellen
    """

    name = "ntbridge"

    def __init__(
        self,
        database: str | Path | None = None,
        *,
        session_cfg: SessionConfig | None = None,
    ) -> None:
        self._pfad = Path(database) if database else STANDARD_DATENBANK
        self._session_cfg = session_cfg or SessionConfig()
        #: Zeitstempel der Kerzen, die auf einen Kontraktwechsel folgen.
        #: Wird bei jedem :meth:`load` neu gesetzt.
        self.rollgrenzen: pd.DatetimeIndex = pd.DatetimeIndex([], tz="UTC")
        # Die 1m-Reihe einmal je Instrument und Zeitfenster halten. Sieben
        # Jahre zu lesen kostet gemessen ~20 s; ein Forschungslauf, der
        # mehrere Timeframes oder mehrere Strategien nacheinander rechnet,
        # zahlt das sonst jedes Mal neu. Der Cache haengt an der Instanz -
        # ein neuer Provider liest frisch, und niemand sieht versehentlich
        # veraltete Kerzen ueber Prozessgrenzen hinweg.
        self._basis_cache: dict[tuple, pd.DataFrame] = {}

    # -- Timeframe-Aufloesung ---------------------------------------------

    @staticmethod
    def timeframe_fuer(interval_minutes: int) -> str:
        """Minutenzahl -> Timeframe-Name, oder ein lauter Abbruch.

        Absichtlich ohne Rundung: eine 7-Minuten-Anfrage still auf 5 Minuten
        zu beantworten waere ein Ergebnis fuer eine Frage, die niemand
        gestellt hat.
        """
        tf = MINUTEN_ZU_TIMEFRAME.get(int(interval_minutes))
        if tf is None:
            moeglich = ", ".join(
                f"{m} ({t})" for m, t in sorted(MINUTEN_ZU_TIMEFRAME.items())
            )
            raise DataProviderError(
                f"Kein Timeframe fuer {interval_minutes} Minuten. "
                f"Moeglich: {moeglich}. Die Basisreihe ist 1m; alles Groebere "
                "wird daraus aggregiert, und dafuer muss die Zielgroesse "
                f"benannt sein (kanonisch: {', '.join(CANONICAL_TIMEFRAMES)})."
            )
        return tf

    # -- Lesen -------------------------------------------------------------

    def _lies_basisreihe(self, request: BarRequest) -> pd.DataFrame:
        """Die 1m-Kerzen des Instruments, aufsteigend, UTC-Index.

        Ohne ``row_factory`` und mit festem Zeitstempelformat: ueber
        ``sqlite3.Row`` dauerte das Lesen von 2,5 Mio Zeilen gemessen ~120 s,
        ueber Tupel ~20 s. ``pd.to_datetime`` ohne ``format=`` kostete noch
        einmal ~18 s.
        """
        if not self._pfad.exists():
            raise DataProviderError(
                f"Kerzendatenbank nicht gefunden: {self._pfad}\n"
                "Sie entsteht durch den ntbridge-Empfaenger und den "
                "NT8-Historienimport (docs/NT8_EXPORT_ANLEITUNG.md)."
            )

        spalten = ["ts_utc", "open", "high", "low", "close", "volume"]
        abfrage = (
            "SELECT ts_utc, open, high, low, close, volume FROM bars "
            "WHERE instrument = ? AND timeframe = ? ORDER BY ts_utc"
        )
        parameter: list = [request.symbol.upper(), BASIS_TIMEFRAME]

        # Zeitfilter schon in SQL: bei sieben Jahren Historie ist das der
        # Unterschied zwischen zwanzig Sekunden und einer halben.
        #
        # Der Vorlauf ist Absicht und wichtig: ein grober Timeframe braucht
        # die Minuten VOR dem Startzeitpunkt, sonst ist die erste Kerze aus
        # einem angeschnittenen Fenster gebildet und damit falsch. finalize()
        # schneidet danach exakt auf den angefragten Bereich.
        vorlauf = pd.Timedelta(minutes=int(request.interval_minutes) * 2 + 1440)
        if request.start is not None:
            abfrage = abfrage.replace("ORDER BY", "AND ts_utc >= ? ORDER BY")
            parameter.append((_als_utc(request.start) - vorlauf).isoformat())
        if request.end is not None:
            abfrage = abfrage.replace("ORDER BY", "AND ts_utc <= ? ORDER BY")
            parameter.append(_als_utc(request.end).isoformat())

        verbindung = sqlite3.connect(str(self._pfad))
        try:
            zeilen = verbindung.execute(abfrage, parameter).fetchall()
        finally:
            verbindung.close()

        if not zeilen:
            raise DataProviderError(
                f"Keine 1m-Kerzen fuer {request.symbol.upper()} in {self._pfad.name}. "
                "Vorhanden sind nur Instrumente, die ueber die Bridge oder den "
                "NT8-Import hereingekommen sind."
            )

        rahmen = pd.DataFrame(zeilen, columns=spalten)
        rahmen.index = pd.to_datetime(
            rahmen.pop("ts_utc"), utc=True, format="ISO8601"
        )
        rahmen.index.name = None
        return rahmen

    def _bestimme_rollgrenzen(self, basis: pd.DataFrame) -> pd.DatetimeIndex:
        """Zeitstempel der Kerzen, die auf einen Kontraktwechsel folgen.

        Bevorzugt aus NinjaTraders eigenem Kontraktbestand - der weiss
        genau, ab wann welcher Kontrakt Frontmonat war
        (``werkzeuge.nt8_import.rollplan_aus_nt8``). Fehlt der Ordner, wird
        auf einen Preissprung-Verdacht zurueckgefallen, und das steht dann
        auch im Log: ein Verdacht ist kein Bestand.
        """
        if basis.empty:
            return pd.DatetimeIndex([], tz="UTC")

        try:
            from werkzeuge.nt8_import import rollplan_aus_nt8

            wurzel = str(basis.attrs.get("instrument", "MNQ"))
            plan = rollplan_aus_nt8(wurzel)
        except Exception:  # noqa: BLE001 - Bestand ist eine Kuer, kein Muss
            plan = {}

        if plan:
            # Jeder Fensterbeginn ausser dem allerersten ist eine Naht.
            beginne = sorted(von for von, _ in plan.values())[1:]
            treffer = [
                basis.index[basis.index.searchsorted(zeitpunkt)]
                for zeitpunkt in beginne
                if basis.index.searchsorted(zeitpunkt) < len(basis.index)
            ]
            return pd.DatetimeIndex(sorted(set(treffer)), tz="UTC")

        schluss = basis["close"]
        sprung = (basis["open"] - schluss.shift(1)).abs() / schluss.shift(1) * 100.0
        verdacht = basis.index[sprung > ROLLSPRUNG_VERDACHT_PROZENT]
        log.warning(
            "Kontraktbestand nicht lesbar - %d Rollgrenzen nur aus dem "
            "Preissprung geschaetzt (> %.2f %%). Das ist ein Verdacht, "
            "kein Bestand.",
            len(verdacht),
            ROLLSPRUNG_VERDACHT_PROZENT,
        )
        return pd.DatetimeIndex(verdacht, tz="UTC")

    def load(self, request: BarRequest) -> pd.DataFrame:
        timeframe = self.timeframe_fuer(request.interval_minutes)

        schluessel = (
            request.symbol.upper(),
            None if request.start is None else _als_utc(request.start),
            None if request.end is None else _als_utc(request.end),
            int(request.interval_minutes),
        )
        basis = self._basis_cache.get(schluessel)
        if basis is None:
            basis = self._lies_basisreihe(request)
            self._basis_cache[schluessel] = basis
            log.info(
                "%d 1m-Kerzen fuer %s gelesen (%s bis %s).",
                len(basis),
                request.symbol.upper(),
                basis.index[0],
                basis.index[-1],
            )
        basis.attrs["instrument"] = request.symbol.upper()

        self.rollgrenzen = self._bestimme_rollgrenzen(basis)
        if len(self.rollgrenzen):
            log.info(
                "%d Kontraktnahtstellen im Zeitraum - siehe "
                "NtBridgeDataProvider.rollgrenzen. Der Preissprung dort ist "
                "ein Kontraktwechsel, keine Marktbewegung.",
                len(self.rollgrenzen),
            )

        if timeframe == BASIS_TIMEFRAME:
            rahmen = basis
        else:
            rahmen = resample_ohlcv(basis, timeframe, self._session_cfg)
            log.info(
                "Auf %s verdichtet: %d Kerzen.", timeframe, len(rahmen)
            )

        return self.finalize(rahmen, request)

    # -- Auskunft ----------------------------------------------------------

    def bestand(self) -> pd.DataFrame:
        """Was in der Datenbank liegt - je Instrument und Timeframe.

        Fuer die Frage "worauf kann ich ueberhaupt rechnen", bevor ein
        Forschungslauf startet.
        """
        if not self._pfad.exists():
            raise DataProviderError(f"Kerzendatenbank nicht gefunden: {self._pfad}")
        verbindung = sqlite3.connect(str(self._pfad))
        try:
            zeilen = verbindung.execute(
                "SELECT instrument, timeframe, COUNT(*) AS kerzen, "
                "MIN(ts_utc) AS von, MAX(ts_utc) AS bis, "
                "GROUP_CONCAT(DISTINCT source) AS quellen "
                "FROM bars GROUP BY instrument, timeframe "
                "ORDER BY instrument, kerzen DESC"
            ).fetchall()
        finally:
            verbindung.close()
        return pd.DataFrame(
            zeilen,
            columns=["instrument", "timeframe", "kerzen", "von", "bis", "quellen"],
        )
