"""Risikopruefung: die eine Stelle, an der eine Order abgelehnt wird.

Warum es diese Datei gibt
-------------------------
Vorher existierten **drei** Risikoimplementierungen nebeneinander:
``execution/risk.py`` (SQLite, Trailing-Drawdown fest auf 1500 USD),
``execution/risk_engine.py`` (im Arbeitsspeicher, Tagesverlust fest auf 500)
und eine dritte, inline in ``execution/server.py`` (Tagesverlust 1500).
Keine davon war an die Fuellungen angeschlossen - ``handle_fill`` tat nichts,
also blieb der Tagesverlust in allen dreien fuer immer 0 und jede Grenze war
Zierde. Ein Risikomodul, das nie ausloest, ist gefaehrlicher als keines: es
erzeugt Vertrauen, das es nicht traegt.

Der Aufbau hier
---------------
Die Regeln kommen aus ``common.kontoregeln`` (benanntes Profil), der Zustand
aus ``execution.store`` (echte Fuellungen auf der Platte). Dieses Modul
rechnet nur zusammen und urteilt.

Vier Riegel, in dieser Reihenfolge:

1. **Handelsfenster** - ausserhalb wird gar nicht erst gerechnet.
2. **Tagesverlustlimit** - der Handelstag ist zu Ende.
3. **Nachziehender Gesamtverlust** - das Konto ist zu Ende.
4. **Positionsgroesse** - Anbietergrenze UND eigenes Limit, das kleinere gilt.

Was hier bewusst NICHT geprueft wird
------------------------------------
Die Konsistenzregel (groesster Tag hoechstens X Prozent des Gesamtgewinns)
greift bei Lucid erst beim Auszahlungsantrag, nicht beim Handeln. Sie wird
in :meth:`RisikoPruefung.kennzahlen` **berichtet**, aber sie lehnt keine
Order ab - eine Order zu blockieren, weil der Tag zu gut laeuft, waere eine
Regel, die es so nicht gibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from common.kontoregeln import DrawdownArt, Kontoregeln
from execution.store import ExecutionStore, OrderStatus

__all__ = ["Handelsfenster", "RisikoUrteil", "RisikoPruefung"]

_ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Handelsfenster:
    """Wann der Bot ueberhaupt handeln darf, in Boersenzeit (ET).

    Die Vorgabe 03:00-16:00 ET deckt die London-Eroeffnung und die gesamte
    US-Sitzung ab. Ausserhalb ist der Nasdaq duenn; ein Bot produziert dort
    vor allem schlechte Fuellungen.

    Das Fenster gilt fuer den **Einstieg**. Eine laufende Position wird davon
    nicht angefasst - ihr Stop und ihr Ziel liegen als echte Orders bei
    NinjaTrader und wirken weiter.
    """

    start: dtime = dtime(3, 0)
    ende: dtime = dtime(16, 0)
    zeitzone: str = "America/New_York"
    nur_wochentags: bool = True

    def ist_offen(self, zeitpunkt: datetime) -> bool:
        lokal = zeitpunkt.astimezone(ZoneInfo(self.zeitzone))
        if self.nur_wochentags and lokal.weekday() >= 5:
            return False
        return self.start <= lokal.time() < self.ende

    def beschreibung(self) -> str:
        return (
            f"{self.start:%H:%M}-{self.ende:%H:%M} "
            f"{self.zeitzone.split('/')[-1]}"
            + (", Mo-Fr" if self.nur_wochentags else "")
        )


@dataclass(frozen=True)
class RisikoUrteil:
    """Erlaubt oder nicht - und immer mit Begruendung.

    ``menge`` kann kleiner sein als angefragt: wenn die Anbietergrenze eine
    kleinere Position zulaesst, wird gekuerzt statt abgelehnt. Gekuerzt wird
    aber nur nach unten und nie auf 0 - eine Position der Groesse 0 waere
    eine Ablehnung, die sich als Erfolg meldet.
    """

    erlaubt: bool
    grund: str
    menge: int = 0
    kennzahlen: dict[str, Any] | None = None


class RisikoPruefung:
    """Prueft Orders gegen ein Kontoprofil und den tatsaechlichen Zustand."""

    def __init__(
        self,
        regeln: Kontoregeln,
        store: ExecutionStore,
        *,
        fenster: Handelsfenster | None = None,
        eigenes_kontraktlimit: int | None = None,
        startkapital_usd: float | None = None,
    ) -> None:
        self.regeln = regeln
        self.store = store
        self.fenster = fenster or Handelsfenster()
        # Ein eigenes, meist strengeres Limit. Die Anbietergrenze ist das
        # Maximum des Erlaubten, nicht eine Empfehlung: 20 Micro-Kontrakte auf
        # einem 25k-Konto sind formal zulaessig und trotzdem unvernuenftig.
        self.eigenes_kontraktlimit = eigenes_kontraktlimit
        self.startkapital_usd = (
            startkapital_usd
            if startkapital_usd is not None
            else regeln.kontogroesse_usd
        )

    # -- Zustand -----------------------------------------------------------

    def session_datum(self, zeitpunkt: datetime | None = None) -> str:
        """CME-Handelstag als ISO-Datum (18:00-ET-Rollover).

        Bewusst ueber ``common.sessions.session_date_for`` - dieselbe Regel,
        die auch Session-VWAP und Vortagesmarken benutzen. Eine zweite
        Tagesdefinition in der Ausfuehrungsschicht waere genau die Art
        Doppelung, an der spaeter niemand mehr merkt, dass sie auseinander
        laeuft.
        """
        from common.config import SessionConfig
        from common.sessions import session_date_for

        zeitpunkt = zeitpunkt or datetime.now(timezone.utc)
        return session_date_for(zeitpunkt, SessionConfig()).isoformat()

    def kontostand(self) -> float:
        return self.startkapital_usd + self.store.realisiert()

    def max_verlust_grenze(self) -> float | None:
        """Absoluter Kontostand, unter dem das Konto gerissen ist.

        EOD-Trailing: die Grenze zieht mit dem hoechsten **Tagesschluss** nach,
        friert aber ein, sobald das Konto die initiale Trail-Grenze
        ueberschritten hat. Danach steht sie dauerhaft auf der Startbalance.

        Intraday-Trailing waere der hoechste Stand waehrend des Tages - den
        fuehren wir hier nicht mit, weil kein Lucid-Profil im Register ihn
        verlangt. Sollte einer dazukommen, ist das die Stelle.
        """
        if self.regeln.max_verlust_usd is None:
            return None

        start = self.startkapital_usd
        grenze = start - self.regeln.max_verlust_usd

        if self.regeln.drawdown_art == DrawdownArt.STATISCH:
            return grenze

        hoechster = self.store.hoechster_tagesschluss()
        if hoechster is None:
            return grenze

        trail_ende = self.regeln.initiale_trail_grenze_usd
        if trail_ende is not None and hoechster >= trail_ende:
            # Eingefroren auf der Startbalance - ab hier kann das Konto nicht
            # mehr unter seinen Ausgangswert fallen, ohne gerissen zu sein.
            return start
        return max(grenze, hoechster - self.regeln.max_verlust_usd)

    def max_kontrakte(self) -> int | None:
        anbieter = self.regeln.max_kontrakte_micro
        eigen = self.eigenes_kontraktlimit
        kandidaten = [w for w in (anbieter, eigen) if w is not None]
        return min(kandidaten) if kandidaten else None

    def kennzahlen(self, zeitpunkt: datetime | None = None) -> dict[str, Any]:
        """Alles, was die Oberflaeche und das Protokoll anzeigen sollen."""
        tag = self.session_datum(zeitpunkt)
        heute = self.store.realisiert(session_datum=tag)
        stand = self.kontostand()
        grenze = self.max_verlust_grenze()
        trades = self.store.trades(limit=1000)

        # Konsistenz: groesster Gewinntag im Verhaeltnis zum Gesamtgewinn.
        je_tag: dict[str, float] = {}
        for t in trades:
            je_tag[t["session_datum"]] = je_tag.get(t["session_datum"], 0.0) + t["pnl_usd"]
        gesamtgewinn = sum(w for w in je_tag.values() if w > 0)
        groesster_tag = max(je_tag.values(), default=0.0)
        konsistenz = (
            groesster_tag / gesamtgewinn if gesamtgewinn > 0 else None
        )

        return {
            "kontoprofil": self.regeln.name,
            "regeln_sind_annahme": self.regeln.ist_annahme,
            "session_datum": tag,
            "kontostand_usd": stand,
            "realisiert_heute_usd": heute,
            "realisiert_gesamt_usd": stand - self.startkapital_usd,
            "tagesverlust_limit_usd": self.regeln.tagesverlust_usd,
            "tagesverlust_rest_usd": (
                None if self.regeln.tagesverlust_usd is None
                else self.regeln.tagesverlust_usd + min(0.0, heute)
            ),
            "max_verlust_grenze_usd": grenze,
            "abstand_zur_grenze_usd": None if grenze is None else stand - grenze,
            "drawdown_art": self.regeln.drawdown_art,
            "max_kontrakte": self.max_kontrakte(),
            "handelsfenster": self.fenster.beschreibung(),
            "fenster_offen": self.fenster.ist_offen(
                zeitpunkt or datetime.now(timezone.utc)
            ),
            "konsistenz_ist": konsistenz,
            "konsistenz_grenze": self.regeln.konsistenz_anteil,
            "trades_gesamt": len(trades),
            "handelstage": len(je_tag),
        }

    # -- Urteil ------------------------------------------------------------

    def pruefe(
        self,
        *,
        menge: int,
        zeitpunkt: datetime | None = None,
        ist_einstieg: bool = True,
        fenster_erzwingen: bool = True,
    ) -> RisikoUrteil:
        """Darf diese Order raus?

        ``ist_einstieg=False`` fuer Orders, die eine bestehende Position
        schliessen: ein Ausstieg darf **nie** an einem Risikolimit scheitern.
        Genau dann will man raus.
        """
        zeitpunkt = zeitpunkt or datetime.now(timezone.utc)
        kennzahlen = self.kennzahlen(zeitpunkt)

        if not ist_einstieg:
            return RisikoUrteil(True, "Ausstieg - keine Pruefung", menge, kennzahlen)

        if fenster_erzwingen and not self.fenster.ist_offen(zeitpunkt):
            return RisikoUrteil(
                False,
                f"Ausserhalb des Handelsfensters ({self.fenster.beschreibung()})",
                0, kennzahlen,
            )

        limit = self.regeln.tagesverlust_usd
        heute = kennzahlen["realisiert_heute_usd"]
        if limit is not None and heute <= -limit:
            return RisikoUrteil(
                False,
                f"Tagesverlustlimit erreicht: {heute:.2f} von -{limit:.2f} USD"
                + ("" if self.regeln.tagesverlust_hart else " (weich - Konto bleibt)"),
                0, kennzahlen,
            )

        grenze = kennzahlen["max_verlust_grenze_usd"]
        if grenze is not None and kennzahlen["kontostand_usd"] <= grenze:
            return RisikoUrteil(
                False,
                f"Gesamtverlustgrenze erreicht: Stand {kennzahlen['kontostand_usd']:.2f} "
                f"USD, Grenze {grenze:.2f} USD",
                0, kennzahlen,
            )

        offen = self.store.orders(status=OrderStatus.OFFEN, limit=100)
        offene_menge = sum(int(o["menge"]) for o in offen)
        hoechstens = self.max_kontrakte()
        if hoechstens is not None:
            frei = hoechstens - offene_menge
            if frei <= 0:
                return RisikoUrteil(
                    False,
                    f"Kontraktlimit ausgeschoepft: {offene_menge} von {hoechstens} "
                    "bereits offen",
                    0, kennzahlen,
                )
            if menge > frei:
                return RisikoUrteil(
                    True,
                    f"Auf {frei} Kontrakte gekuerzt (Limit {hoechstens}, "
                    f"{offene_menge} offen)",
                    frei, kennzahlen,
                )

        return RisikoUrteil(True, "Innerhalb aller Grenzen", menge, kennzahlen)
