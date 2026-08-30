"""Autonomer Handel: von der erkannten Idee zur Order.

Warum der Bot IM Serverprozess laeuft
-------------------------------------
Die Vorgaengerfassung (``execution/live_bot.py``) war ein eigener Prozess, der
jede Minute ``python -m ideas`` als Unterprozess startete, das juengste
Ergebnis aus der Datenbank fischte und per HTTP eine Order schickte. Das hatte
vier Fehler, die sich gegenseitig verdeckten:

1. **Zwei Risikozustaende.** Bot und Server fuehrten jeder ihre eigenen
   Zahlen, keiner sah die Positionen des anderen. Genau dieses Split-Brain
   stand schon im Audit vom 28.08.2026.
2. **Gefilterte Ideen wurden gehandelt.** Es holte "die neueste Idee" ohne
   Ruecksicht auf ``gefiltert`` - eine wegen Wirtschaftskalender abgelehnte
   Idee waere gehandelt worden.
3. **Alter egal.** Eine Idee von vor drei Stunden war genauso gut wie eine
   von gerade eben.
4. ``capture_output=True`` verschluckte jeden Fehler der Erkennung.

Hier laeuft alles in einem Prozess, auf einem Speicher, mit einer
Risikopruefung.

Was der Bot NICHT selbst rechnet
--------------------------------
Er hat keine eigene Signal-Logik. Erkannt wird ueber ``ideas.pipeline`` und
damit ueber dieselben Regel-Objekte, die auch der Backtest auswertet
(Invariante 6). Ein zweiter Erkenner waere der sichere Weg, live etwas
anderes zu handeln als das, was gemessen wurde.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from common.config import Config
from common.instruments import get_instrument
from common.logging_setup import log_event
from execution.risiko import RisikoPruefung
from execution.store import ExecutionStore, Order

log = logging.getLogger("execution.bot")

#: Wie viele Vielfache der Kerzendauer eine Idee alt sein darf, bevor sie
#: nicht mehr gehandelt wird. Ein Signal vom Vormittag beschreibt eine
#: Marktlage, die es am Nachmittag nicht mehr gibt.
MAX_ALTER_IN_KERZEN = 2

_TIMEFRAME_MINUTEN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}


@dataclass
class Botlauf:
    """Ergebnis eines Durchgangs - fuer Log und Oberflaeche."""

    zeitpunkt: datetime
    geprueft: int = 0
    neue_ideen: int = 0
    orders: int = 0
    abgelehnt: int = 0
    grund: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "zeitpunkt": self.zeitpunkt.isoformat(),
            "geprueft": self.geprueft,
            "neue_ideen": self.neue_ideen,
            "orders": self.orders,
            "abgelehnt": self.abgelehnt,
            "grund": self.grund,
        }


def order_art(richtung: str, entry: float, aktueller_kurs: float) -> tuple[str, str]:
    """Limit oder Stop - und warum.

    Liegt der Einstieg fuer einen Long ueber dem aktuellen Kurs, ist es ein
    Ausbruch: eine **Stop**-Order, die erst ausloest, wenn der Markt dorthin
    laeuft. Liegt er darunter, ist es ein Ruecklauf: eine **Limit**-Order.
    Fuer Short spiegelverkehrt.

    Eine Market-Order kommt hier nicht vor. Der protokollierte ``entry`` ist
    der Schlusskurs der Signalkerze - zwischen ihm und der Ausfuehrung liegt
    Bewegung, und eine Market-Order wuerde jeden Abstand kommentarlos bezahlen.
    """
    if richtung == "long":
        if entry > aktueller_kurs:
            return "STOP", "Ausbruch ueber den aktuellen Kurs"
        return "LIMIT", "Ruecklauf auf den Einstieg"
    if entry < aktueller_kurs:
        return "STOP", "Ausbruch unter den aktuellen Kurs"
    return "LIMIT", "Ruecklauf auf den Einstieg"


def kontraktzahl(
    *,
    risikobudget_usd: float,
    entry: float,
    stop: float,
    point_value: float,
    hoechstens: int | None,
) -> tuple[int, str]:
    """Wie viele Kontrakte das Risikobudget hergibt.

    Der Abstand zum Stop bestimmt die Groesse, nicht umgekehrt. Ein enger
    Stop erlaubt mehr Kontrakte bei gleichem Risiko, ein weiter weniger -
    eine feste Kontraktzahl wuerde bedeuten, dass derselbe Bot je nach
    Volatilitaet das Zehnfache riskiert.

    Reicht das Budget nicht fuer einen einzigen Kontrakt, wird **nicht**
    aufgerundet: dann ist der Trade zu teuer, und das ist eine Antwort.
    """
    abstand = abs(entry - stop)
    if abstand <= 0:
        return 0, "Stop liegt auf dem Einstieg - kein Risiko berechenbar"

    risiko_je_kontrakt = abstand * point_value
    moeglich = int(risikobudget_usd // risiko_je_kontrakt)
    if moeglich < 1:
        return 0, (
            f"Ein Kontrakt riskiert {risiko_je_kontrakt:.2f} USD, Budget sind "
            f"{risikobudget_usd:.2f} USD"
        )
    if hoechstens is not None and moeglich > hoechstens:
        return hoechstens, (
            f"Budget erlaubt {moeglich}, Limit sind {hoechstens} Kontrakte"
        )
    return moeglich, (
        f"{moeglich} Kontrakte zu je {risiko_je_kontrakt:.2f} USD Risiko"
    )


class HandelsBot:
    """Erkennt Ideen und schickt daraus Orders - oder begruendet, warum nicht."""

    def __init__(
        self,
        config: Config,
        store: ExecutionStore,
        risiko: RisikoPruefung,
        *,
        bar_datenbank: str,
        ideen_datenbank: str,
    ) -> None:
        self.config = config
        self.store = store
        self.risiko = risiko
        self.bar_datenbank = bar_datenbank
        self.ideen_datenbank = ideen_datenbank
        self.instrument = get_instrument(config.market.product)
        self._stopp = threading.Event()
        self._faden: threading.Thread | None = None
        self.letzter_lauf: Botlauf | None = None

    # -- Risikobudget ------------------------------------------------------

    def risikobudget_usd(self) -> float:
        """Was ein einzelner Trade kosten darf.

        Vorgabe: ein Prozent der massgeblichen Bezugsgroesse. Bei einem
        Prop-Konto ist das der **Gesamtverlustpuffer** und nicht die
        Kontogroesse - bei einem 50k-Konto mit 2.000 USD Puffer sind ein
        Prozent von 50.000 (500 USD) ein Viertel des gesamten Spielraums,
        also offensichtlich falsch herum gedacht.
        """
        ausdruecklich = getattr(self.config.ausfuehrung, "risiko_je_trade_usd", None)
        if ausdruecklich:
            return float(ausdruecklich)

        regeln = self.risiko.regeln
        bezug = regeln.max_verlust_usd or self.risiko.startkapital_usd or 0.0
        anteil = getattr(self.config.ausfuehrung, "risiko_je_trade_anteil", 0.01)
        return max(0.0, bezug * float(anteil))

    # -- Ein Durchgang -----------------------------------------------------

    def durchgang(self, jetzt: datetime | None = None) -> Botlauf:
        jetzt = jetzt or datetime.now(timezone.utc)
        lauf = Botlauf(zeitpunkt=jetzt)

        if not self.risiko.fenster.ist_offen(jetzt):
            lauf.grund = (
                f"Ausserhalb des Handelsfensters "
                f"({self.risiko.fenster.beschreibung()})"
            )
            self.letzter_lauf = lauf
            return lauf

        ideen = self._neue_ideen(jetzt)
        lauf.neue_ideen = len(ideen)
        if not ideen:
            lauf.grund = "Kein handelbares Signal"
            self.store.protokolliere_entscheidung(
                instrument=self.instrument.root,
                ergebnis="kein_signal",
                grund=lauf.grund,
            )
            self.letzter_lauf = lauf
            return lauf

        kurs = self._letzter_kurs()
        for idee in ideen:
            lauf.geprueft += 1
            if self._handle(idee, kurs, jetzt):
                lauf.orders += 1
            else:
                lauf.abgelehnt += 1

        lauf.grund = f"{lauf.orders} Order(s) aus {lauf.neue_ideen} Ideen"
        self.letzter_lauf = lauf
        log_event(log, "bot.durchgang", lauf.grund, **lauf.to_dict())
        return lauf

    # -- Ideen -------------------------------------------------------------

    def _neue_ideen(self, jetzt: datetime) -> list[dict[str, Any]]:
        """Erkennung anstossen und nur das Handelbare zurueckgeben.

        Handelbar heisst: nicht gefiltert, nicht zu alt, und noch nicht
        gehandelt. Alle drei Bedingungen fehlten der Vorgaengerfassung.
        """
        from ideas.pipeline import protokolliere
        from ideas.store import IdeenStore
        from ntbridge.store import BarStore

        timeframe = self.config.ideas.timeframe
        minuten = _TIMEFRAME_MINUTEN.get(timeframe, 5)

        bars = BarStore(self.bar_datenbank)
        try:
            df = bars.load_frame(
                self.instrument.root, timeframe, limit=self.config.ideas.bars
            )
        finally:
            bars.close()

        if df.empty:
            return []

        with IdeenStore(self.ideen_datenbank) as ideen_store:
            protokolliere(df, self.instrument.root, self.config, ideen_store)

            grenze = jetzt - timedelta(minutes=minuten * MAX_ALTER_IN_KERZEN)
            frisch = ideen_store.lade(
                instrument=self.instrument.root, limit=50
            )

        gehandelt = {
            o["idee_id"] for o in self.store.orders(limit=500) if o["idee_id"]
        }

        handelbar = []
        for idee in frisch:
            if idee.get("gefiltert"):
                continue
            zeitpunkt = idee.get("erstellt_utc")
            if isinstance(zeitpunkt, str):
                zeitpunkt = datetime.fromisoformat(zeitpunkt)
            if zeitpunkt.tzinfo is None:
                zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
            if zeitpunkt < grenze:
                continue
            if str(idee.get("idea_id")) in gehandelt:
                continue
            handelbar.append(idee)
        return handelbar

    def _letzter_kurs(self) -> float | None:
        from ntbridge.store import BarStore

        bars = BarStore(self.bar_datenbank)
        try:
            df = bars.load_frame(self.instrument.root, "1m", limit=1)
        finally:
            bars.close()
        return None if df.empty else float(df["close"].iloc[-1])

    # -- Eine Idee zur Order machen ---------------------------------------

    def _handle(
        self, idee: dict[str, Any], kurs: float | None, jetzt: datetime
    ) -> bool:
        idee_id = str(idee.get("idea_id"))
        setup = idee.get("setup", "")
        richtung = str(idee.get("richtung", "")).lower()

        def ablehnen(grund: str) -> bool:
            self.store.protokolliere_entscheidung(
                instrument=self.instrument.root, ergebnis="abgelehnt", grund=grund,
                idee_id=idee_id, hypothese=setup, marktzustand=dict(idee),
            )
            log.info("Idee %s (%s) abgelehnt: %s", idee_id, setup, grund)
            return False

        if kurs is None:
            return ablehnen("Kein aktueller Kurs verfuegbar")

        entry = float(idee["entry"])
        stop = float(idee["stop"])
        ziel = float(idee["ziel"])

        menge, groessengrund = kontraktzahl(
            risikobudget_usd=self.risikobudget_usd(),
            entry=entry,
            stop=stop,
            point_value=self.instrument.point_value,
            hoechstens=self.risiko.max_kontrakte(),
        )
        if menge < 1:
            return ablehnen(f"Positionsgroesse 0: {groessengrund}")

        urteil = self.risiko.pruefe(menge=menge, zeitpunkt=jetzt)
        if not urteil.erlaubt:
            return ablehnen(urteil.grund)
        menge = urteil.menge

        art, artgrund = order_art(richtung, entry, kurs)

        order = Order(
            instrument=self.instrument.root,
            richtung=richtung,
            art=art,
            menge=menge,
            quelle="bot",
            konto=self.config.ausfuehrung.konto,
            limit_preis=entry if art == "LIMIT" else None,
            stop_preis=entry if art == "STOP" else None,
            stop_loss=stop,
            take_profit=ziel,
            idee_id=idee_id,
            hypothese=setup,
            begruendung={
                "setup": setup,
                "timeframe": idee.get("timeframe"),
                "signalkerze_utc": str(idee.get("erstellt_utc")),
                "kurs_bei_entscheidung": kurs,
                "orderart": artgrund,
                "positionsgroesse": groessengrund,
                "risikobudget_usd": self.risikobudget_usd(),
                "crv": idee.get("crv"),
                "atr_referenz": idee.get("atr_referenz"),
                "stop_atr": idee.get("stop_atr"),
                "ziel_atr": idee.get("ziel_atr"),
                "filter_ungeprueft": idee.get("ungeprueft"),
                "kontoprofil": self.risiko.regeln.name,
                "regeln_sind_annahme": self.risiko.regeln.ist_annahme,
            },
        )

        import uuid

        order_id = str(uuid.uuid4())
        self.store.lege_order_an(order, order_id)
        self.store.protokolliere_entscheidung(
            instrument=self.instrument.root, ergebnis="order",
            grund=f"{setup}/{richtung}: {artgrund}, {groessengrund}",
            order_id=order_id, idee_id=idee_id, hypothese=setup,
            marktzustand=urteil.kennzahlen,
        )
        log_event(
            log, "bot.order",
            f"Order aus {setup}/{richtung}: {art} {menge} @ {entry}",
            order_id=order_id, idee_id=idee_id, setup=setup, art=art,
            menge=menge, entry=entry, stop=stop, ziel=ziel,
        )
        return True

    # -- Dauerbetrieb ------------------------------------------------------

    def start(self) -> None:
        if self._faden is not None and self._faden.is_alive():
            return
        self._stopp.clear()
        self._faden = threading.Thread(target=self._schleife, daemon=True)
        self._faden.start()
        log.info(
            "Bot gestartet: %s, Takt %ds",
            self.risiko.fenster.beschreibung(), self.config.ausfuehrung.takt_sekunden,
        )

    def stop(self) -> None:
        self._stopp.set()

    @property
    def laeuft(self) -> bool:
        return self._faden is not None and self._faden.is_alive()

    def _schleife(self) -> None:
        takt = max(5, int(self.config.ausfuehrung.takt_sekunden))
        while not self._stopp.is_set():
            try:
                self.durchgang()
            except Exception as fehler:  # noqa: BLE001
                # Der Bot darf an einem einzelnen Durchgang nicht sterben -
                # sonst haette ein vorbeigehender Datenfehler zur Folge, dass
                # ab da niemand mehr handelt und es niemand merkt.
                log_event(
                    log, "bot.fehler", f"Durchgang fehlgeschlagen: {fehler}",
                    level=logging.ERROR, exc_info=True,
                )
            self._stopp.wait(takt)
