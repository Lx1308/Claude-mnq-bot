"""Eine Handelsfolge gegen ein Kontoregelwerk durchspielen.

Die Frage
---------
Der Bot handelt auf einem freien Simulationskonto. Laurins Frage vom
30.08.2026: "dann kann man ja irgendwann auswerten, welche Hypothesen gut auf
einem funded acc funktioniert haetten und welche nicht."

Genau das macht dieses Modul - im Nachhinein, auf den tatsaechlich
protokollierten Trades, gegen jedes Kontoprofil aus ``common/kontoregeln.py``.

Warum das kein einfaches Aufsummieren ist
-----------------------------------------
Die naheliegende Rechnung waere: P&L addieren und nachsehen, ob die Summe
irgendwann unter die Verlustgrenze faellt. Sie waere aus drei Gruenden falsch:

1. **Die Positionsgroesse waere eine andere gewesen.** Ein 25k-Konto haette
   ein kleineres Risikobudget als das frei gesetzte - manche Trades gar nicht,
   andere mit weniger Kontrakten. Deshalb wird jeder Trade **neu
   dimensioniert** und seine P&L entsprechend skaliert.
2. **Ein gerissenes Tageslimit sperrt den Rest des Tages.** Danach folgende
   Trades haetten nicht stattgefunden - sie duerfen also auch nicht zaehlen,
   weder im Guten noch im Schlechten.
3. **Der nachziehende Verlust haengt am Pfad.** Faellt ein Trade weg,
   verschiebt sich jeder spaetere Kontostand und damit auch jede Grenze.

Deshalb wird chronologisch durchgespielt und nicht summiert.

Was diese Rechnung NICHT ist
----------------------------
Kein Beweis, sondern eine Nachrechnung unter ausdruecklichen Annahmen:

* **Gleicher Fuellkurs bei anderer Groesse.** Bei MNQ-Micros in dieser
  Groessenordnung vertretbar, aber es ist eine Annahme.
* **Gleiche Signalauswahl.** Der Bot hat unter dem freien Budget entschieden,
  welche Ideen er nimmt. Ein 25k-Bot haette moeglicherweise andere Ideen
  ueberhaupt erst geprueft, weil seine Kontraktgrenze frueher greift.
* **Keine Rueckkopplung auf das Verhalten.** Ein Mensch (oder ein besserer
  Bot) haette nach zwei Verlusttagen vielleicht anders gehandelt.

Jeder erzeugte Bericht traegt diese Einschraenkungen mit. Eine Zahl ohne sie
saehe aus wie eine Messung.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from common.kontoregeln import DrawdownArt, Kontoregeln

__all__ = [
    "TradeRueckblick",
    "Kontoverlauf",
    "spiele_durch",
    "vergleiche_kontoprofile",
    "EINSCHRAENKUNGEN",
]

#: Steht in jedem Bericht. Siehe Modul-Docstring.
EINSCHRAENKUNGEN: tuple[str, ...] = (
    "Gleicher Fuellkurs auch bei anderer Kontraktzahl angenommen.",
    "Gleiche Signalauswahl wie im tatsaechlichen Lauf angenommen - ein Bot "
    "mit kleinerem Budget haette moeglicherweise andere Ideen geprueft.",
    "Keine Rueckkopplung auf das Verhalten: niemand handelt nach zwei "
    "Verlusttagen genauso weiter wie vorher.",
)


@dataclass
class TradeRueckblick:
    """Ein Trade, wie er unter diesem Regelwerk verlaufen waere."""

    trade_id: str
    session_datum: str
    hypothese: str
    #: Kontrakte, die dieses Konto sich haette leisten koennen.
    kontrakte: int
    #: P&L nach Umrechnung auf diese Kontraktzahl.
    pnl_usd: float
    #: Kontostand nach diesem Trade.
    kontostand_usd: float
    #: ``gehandelt`` | ``zu_teuer`` | ``tag_gesperrt`` | ``konto_gerissen``
    ausgang: str
    grund: str = ""

    @property
    def gehandelt(self) -> bool:
        return self.ausgang == "gehandelt"


@dataclass
class Kontoverlauf:
    """Das Ergebnis eines Durchlaufs gegen ein Regelwerk."""

    regeln: Kontoregeln
    startkapital_usd: float
    trades: list[TradeRueckblick] = field(default_factory=list)

    endstand_usd: float = 0.0
    tiefster_stand_usd: float = 0.0
    gerissen_am: str | None = None
    gerissen_grund: str | None = None
    ziel_erreicht_am: str | None = None
    gesperrte_tage: list[str] = field(default_factory=list)

    # -- Kennzahlen --------------------------------------------------------

    @property
    def gehandelte(self) -> list[TradeRueckblick]:
        return [t for t in self.trades if t.gehandelt]

    @property
    def nicht_handelbar(self) -> int:
        return sum(1 for t in self.trades if t.ausgang == "zu_teuer")

    @property
    def uebersprungen(self) -> int:
        return sum(
            1 for t in self.trades
            if t.ausgang in ("tag_gesperrt", "konto_gerissen")
        )

    @property
    def netto_pnl_usd(self) -> float:
        return self.endstand_usd - self.startkapital_usd

    @property
    def ueberlebt(self) -> bool:
        return self.gerissen_am is None

    def pnl_je_tag(self) -> dict[str, float]:
        je_tag: dict[str, float] = {}
        for trade in self.gehandelte:
            je_tag[trade.session_datum] = (
                je_tag.get(trade.session_datum, 0.0) + trade.pnl_usd
            )
        return je_tag

    def konsistenz(self) -> float | None:
        """Groesster Gewinntag im Verhaeltnis zum Gesamtgewinn.

        ``None``, wenn es gar keinen Gewinn gibt - ein Anteil an null ist
        nicht definiert und nicht 0.
        """
        je_tag = self.pnl_je_tag()
        gewinn = sum(w for w in je_tag.values() if w > 0)
        if gewinn <= 0:
            return None
        return max(je_tag.values()) / gewinn

    def konsistenz_eingehalten(self) -> bool | None:
        grenze = self.regeln.konsistenz_anteil
        ist = self.konsistenz()
        if grenze is None or ist is None:
            return None
        return ist <= grenze

    def je_hypothese(self) -> dict[str, dict[str, Any]]:
        """Was jede Hypothese unter diesem Regelwerk beigetragen haette.

        Der eigentliche Zweck der ganzen Uebung: nicht "hat das Konto
        ueberlebt", sondern **welche Idee** es getragen oder gerissen haette.
        """
        ergebnis: dict[str, dict[str, Any]] = {}
        for trade in self.trades:
            eintrag = ergebnis.setdefault(
                trade.hypothese,
                {"gehandelt": 0, "zu_teuer": 0, "uebersprungen": 0,
                 "pnl_usd": 0.0, "gewinner": 0, "verlierer": 0},
            )
            if trade.ausgang == "gehandelt":
                eintrag["gehandelt"] += 1
                eintrag["pnl_usd"] += trade.pnl_usd
                if trade.pnl_usd > 0:
                    eintrag["gewinner"] += 1
                elif trade.pnl_usd < 0:
                    eintrag["verlierer"] += 1
            elif trade.ausgang == "zu_teuer":
                eintrag["zu_teuer"] += 1
            else:
                eintrag["uebersprungen"] += 1

        for eintrag in ergebnis.values():
            gesamt = eintrag["gewinner"] + eintrag["verlierer"]
            eintrag["trefferquote"] = (
                eintrag["gewinner"] / gesamt if gesamt else None
            )
        return ergebnis

    def zusammenfassung(self) -> dict[str, Any]:
        return {
            "kontoprofil": self.regeln.name,
            "regeln_sind_annahme": self.regeln.ist_annahme,
            "startkapital_usd": self.startkapital_usd,
            "endstand_usd": self.endstand_usd,
            "netto_pnl_usd": self.netto_pnl_usd,
            "tiefster_stand_usd": self.tiefster_stand_usd,
            "ueberlebt": self.ueberlebt,
            "gerissen_am": self.gerissen_am,
            "gerissen_grund": self.gerissen_grund,
            "ziel_erreicht_am": self.ziel_erreicht_am,
            "trades_gehandelt": len(self.gehandelte),
            "trades_zu_teuer": self.nicht_handelbar,
            "trades_uebersprungen": self.uebersprungen,
            "gesperrte_tage": list(self.gesperrte_tage),
            "handelstage": len(self.pnl_je_tag()),
            "konsistenz_ist": self.konsistenz(),
            "konsistenz_grenze": self.regeln.konsistenz_anteil,
            "konsistenz_eingehalten": self.konsistenz_eingehalten(),
            "einschraenkungen": list(EINSCHRAENKUNGEN),
        }


def _kontrakte_fuer(
    *,
    risiko_punkte: float,
    point_value: float,
    budget_usd: float,
    hoechstens: int | None,
) -> int:
    """Wie viele Kontrakte dieses Konto sich geleistet haette.

    Dieselbe Rechnung wie in ``execution.bot.kontraktzahl`` - bewusst
    nachgebildet und nicht importiert: dort haengt sie an einer laufenden
    Risikopruefung mit Speicher, hier soll sie eine reine Funktion auf Zahlen
    sein. Die Formel ist identisch, und ein Test haelt das fest.
    """
    if risiko_punkte <= 0 or point_value <= 0:
        return 0
    je_kontrakt = risiko_punkte * point_value
    moeglich = int(budget_usd // je_kontrakt)
    if moeglich < 1:
        return 0
    if hoechstens is not None:
        return min(moeglich, hoechstens)
    return moeglich


def spiele_durch(
    trades: Iterable[dict[str, Any]],
    regeln: Kontoregeln,
    *,
    point_value: float,
    startkapital_usd: float | None = None,
    risiko_anteil: float = 0.07,
    eigenes_kontraktlimit: int | None = None,
) -> Kontoverlauf:
    """Die Handelsfolge chronologisch gegen ein Regelwerk durchspielen.

    ``trades`` sind Datensaetze aus ``execution.store.trades()`` oder gleich
    aufgebaute. Gebraucht werden: ``session_datum``, ``einstiegskurs``,
    ``punkte_brutto``, ``kommission``, ``menge`` und - fuer die
    Neudimensionierung - der Stopabstand. Fehlt der, wird er aus
    ``r_vielfaches`` und ``punkte_brutto`` zurueckgerechnet; geht auch das
    nicht, gilt der Trade als nicht neu dimensionierbar und wird uebersprungen
    statt geraten.

    ``risiko_anteil`` bezieht sich auf den **Gesamtverlustpuffer** des Kontos,
    nicht auf die Kontogroesse - bei einem 50k-Konto mit 2.000 USD Puffer
    waeren ein Prozent von 50.000 ein Viertel des gesamten Spielraums.
    """
    start = startkapital_usd
    if start is None:
        start = regeln.kontogroesse_usd or 25_000.0

    bezug = regeln.max_verlust_usd or start
    budget = bezug * risiko_anteil

    grenzen = [w for w in (regeln.max_kontrakte_micro, eigenes_kontraktlimit)
               if w is not None]
    kontraktlimit = min(grenzen) if grenzen else None

    verlauf = Kontoverlauf(regeln=regeln, startkapital_usd=start)
    stand = start
    verlauf.tiefster_stand_usd = start

    hoechster_tagesschluss: float | None = None
    tagesverlust: dict[str, float] = {}
    gesperrt: set[str] = set()
    aktueller_tag: str | None = None
    gerissen = False

    def verlustgrenze() -> float | None:
        """Absoluter Kontostand, unter dem das Konto gerissen ist."""
        if regeln.max_verlust_usd is None:
            return None
        boden = start - regeln.max_verlust_usd
        if regeln.drawdown_art == DrawdownArt.STATISCH:
            return boden
        if hoechster_tagesschluss is None:
            return boden
        trail_ende = regeln.initiale_trail_grenze_usd
        if trail_ende is not None and hoechster_tagesschluss >= trail_ende:
            return start
        return max(boden, hoechster_tagesschluss - regeln.max_verlust_usd)

    sortiert = sorted(
        trades,
        key=lambda t: (str(t.get("session_datum", "")), str(t.get("ausstieg_utc", ""))),
    )

    for datensatz in sortiert:
        tag = str(datensatz.get("session_datum", ""))
        trade_id = str(datensatz.get("trade_id", ""))
        hypothese = str(datensatz.get("hypothese") or datensatz.get("setup") or "unbekannt")

        # Tageswechsel: Schlussstand festhalten, das ist die Grundlage des
        # nachziehenden Verlusts.
        if aktueller_tag is not None and tag != aktueller_tag:
            hoechster_tagesschluss = (
                stand if hoechster_tagesschluss is None
                else max(hoechster_tagesschluss, stand)
            )
        aktueller_tag = tag

        if gerissen:
            verlauf.trades.append(TradeRueckblick(
                trade_id, tag, hypothese, 0, 0.0, stand, "konto_gerissen",
                "Konto war zu diesem Zeitpunkt bereits gerissen",
            ))
            continue

        if tag in gesperrt:
            verlauf.trades.append(TradeRueckblick(
                trade_id, tag, hypothese, 0, 0.0, stand, "tag_gesperrt",
                "Tagesverlustlimit an diesem Tag bereits erreicht",
            ))
            continue

        risiko_punkte = _risiko_punkte(datensatz)
        if risiko_punkte is None:
            verlauf.trades.append(TradeRueckblick(
                trade_id, tag, hypothese, 0, 0.0, stand, "zu_teuer",
                "Stopabstand nicht rekonstruierbar - nicht neu dimensionierbar",
            ))
            continue

        kontrakte = _kontrakte_fuer(
            risiko_punkte=risiko_punkte, point_value=point_value,
            budget_usd=budget, hoechstens=kontraktlimit,
        )
        if kontrakte < 1:
            verlauf.trades.append(TradeRueckblick(
                trade_id, tag, hypothese, 0, 0.0, stand, "zu_teuer",
                f"Ein Kontrakt haette {risiko_punkte * point_value:.2f} USD "
                f"riskiert, Budget waren {budget:.2f} USD",
            ))
            continue

        punkte = float(datensatz.get("punkte_brutto") or 0.0)
        menge_original = max(1, int(datensatz.get("menge") or 1))
        kommission_je_kontrakt = (
            float(datensatz.get("kommission") or 0.0) / menge_original
        )
        pnl = punkte * point_value * kontrakte - kommission_je_kontrakt * kontrakte

        stand += pnl
        verlauf.tiefster_stand_usd = min(verlauf.tiefster_stand_usd, stand)
        tagesverlust[tag] = tagesverlust.get(tag, 0.0) + pnl

        verlauf.trades.append(TradeRueckblick(
            trade_id, tag, hypothese, kontrakte, pnl, stand, "gehandelt",
        ))

        grenze = verlustgrenze()
        if grenze is not None and stand <= grenze:
            gerissen = True
            verlauf.gerissen_am = tag
            verlauf.gerissen_grund = (
                f"Kontostand {stand:.2f} USD unter der Verlustgrenze "
                f"{grenze:.2f} USD ({regeln.drawdown_art})"
            )
            continue

        if (
            regeln.tagesverlust_usd is not None
            and tagesverlust[tag] <= -regeln.tagesverlust_usd
        ):
            gesperrt.add(tag)
            if tag not in verlauf.gesperrte_tage:
                verlauf.gesperrte_tage.append(tag)
            if regeln.tagesverlust_hart:
                gerissen = True
                verlauf.gerissen_am = tag
                verlauf.gerissen_grund = (
                    f"Tagesverlust {tagesverlust[tag]:.2f} USD - harter Bruch"
                )

        if (
            regeln.profit_ziel_usd is not None
            and verlauf.ziel_erreicht_am is None
            and stand - start >= regeln.profit_ziel_usd
        ):
            verlauf.ziel_erreicht_am = tag

    verlauf.endstand_usd = stand
    return verlauf


def _risiko_punkte(datensatz: dict[str, Any]) -> float | None:
    """Stopabstand in Punkten - oder ``None``, wenn nicht rekonstruierbar.

    Drei Wege, in dieser Reihenfolge:

    1. ``stop`` und ``einstiegskurs`` liegen vor - der direkte Weg.
    2. ``r_vielfaches`` und ``punkte_brutto`` liegen vor: der Stopabstand ist
       ``punkte / r``. Geht nur, wenn r nicht 0 ist.
    3. Nichts davon - dann ``None``. **Nicht schaetzen:** ein geratener
       Stopabstand ergaebe eine geratene Kontraktzahl und damit eine
       geratene P&L, und die saehe im Bericht aus wie eine gerechnete.
    """
    stop = datensatz.get("stop") or datensatz.get("stop_loss")
    einstieg = datensatz.get("einstiegskurs")
    if stop and einstieg:
        abstand = abs(float(einstieg) - float(stop))
        if abstand > 0:
            return abstand

    r = datensatz.get("r_vielfaches")
    punkte = datensatz.get("punkte_brutto")
    if r and punkte:
        try:
            abstand = abs(float(punkte) / float(r))
        except ZeroDivisionError:
            return None
        if abstand > 0:
            return abstand
    return None


def vergleiche_kontoprofile(
    trades: Iterable[dict[str, Any]],
    profile: Iterable[str],
    *,
    point_value: float,
    risiko_anteil: float = 0.07,
    eigenes_kontraktlimit: int | None = None,
) -> dict[str, Kontoverlauf]:
    """Dieselbe Handelsfolge gegen mehrere Regelwerke."""
    from common.kontoregeln import hole_kontoregeln

    trades = list(trades)
    return {
        name: spiele_durch(
            trades, hole_kontoregeln(name), point_value=point_value,
            risiko_anteil=risiko_anteil,
            eigenes_kontraktlimit=eigenes_kontraktlimit,
        )
        for name in profile
    }
