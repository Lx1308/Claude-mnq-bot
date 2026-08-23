"""Benannte Handelskostenprofile - getrennt nach Herkunft der Kosten.

WARUM NICHT EINE ZAHL
---------------------
Bis zum 23.08.2026 rechnete der Backtest mit einer einzigen Pauschale
(``commission_per_side: 2.50``). Das verdeckte drei verschiedene Dinge, die
sich voellig unterschiedlich verhalten:

* **Broker-Kommission** - verhandelbar, aendert sich beim Brokerwechsel.
* **Boersen-, Clearing- und NFA-Gebuehren** - NICHT verhandelbar, bleiben bei
  einem Brokerwechsel gleich. Wer sie in die Kommission einrechnet, haelt
  Kosten fuer beeinflussbar, die es nicht sind.
* **Slippage** - gar keine Gebuehr, sondern Ausfuehrungsqualitaet. Sie haengt
  an Liquiditaet und Ordertyp, nicht am Preismodell des Brokers.

Die Basisvermessung vom 23.08.2026 zeigte, wie sehr das zaehlt: bei
``prev_day_breakout`` lagen die Kosten bei 5,00 USD je Trade gegen einen
Bruttoverlust von 2,00 USD. Die Kostenannahme dominierte das Ergebnis. Eine
Zahl, die das Ergebnis dominiert, gehoert nicht pauschal gesetzt.

GEMESSEN GEGEN ANGENOMMEN
-------------------------
Jedes Profil traegt ``ist_annahme`` und ``quelle``. Ein Wert, den niemand
verifiziert hat, wird als Annahme gekennzeichnet und nicht als Tatsache
ausgegeben - dieselbe Haltung wie ``naeherung: true`` beim Volume Profile.

WENN DIE AUFSCHLUESSELUNG FEHLT
-------------------------------
Die Einzelposten sind ``float | None``. Ist die Aufteilung nicht bekannt,
bleiben sie **None** und nur ``summe_je_seite`` traegt den Wert. Erfundene
Einzelposten, die zufaellig richtig aufsummieren, waeren schlimmer als eine
ehrliche Luecke: sie saehen aus wie eine Recherche.

DASSELBE SETUP UNTER BEIDEN PROFILEN
------------------------------------
Ein Profil aendert **nur** die Kosten. Strategie- und Research-Logik bleiben
unberuehrt, damit ein Ergebnis unter ``PRIVATE_NINJATRADER`` und ``LUCID``
vergleichbar ist. Wer dafuer die Strategie anfassen muesste, verglaeche zwei
verschiedene Strategien.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Kostenprofil:
    """Ein benanntes Kostenmodell mit nachvollziehbarer Herkunft.

    Massgeblich fuer die Rechnung ist ``summe_je_seite``. Die Einzelposten
    dienen der Nachvollziehbarkeit und duerfen ``None`` sein, wenn die
    Aufteilung nicht belegt ist.
    """

    name: str
    beschreibung: str

    #: Was der Backtest tatsaechlich verrechnet, je Kontrakt und Seite.
    summe_je_seite: float

    #: Slippage - bewusst KEIN Bestandteil der Summe oben. Sie ist keine
    #: Gebuehr, sondern Ausfuehrungsqualitaet, und wird im Fuellkurs
    #: beruecksichtigt statt als Betrag abgezogen.
    slippage_ticks_je_seite: float

    #: Woher die Zahlen stammen. Pflichtangabe.
    quelle: str

    #: True, solange der Wert nicht gegen eine Abrechnung geprueft ist.
    ist_annahme: bool

    # -- Aufschluesselung, optional -----------------------------------------
    broker_kommission_je_seite: float | None = None
    boerse_je_seite: float | None = None
    clearing_je_seite: float | None = None
    nfa_je_seite: float | None = None

    def __post_init__(self) -> None:
        if self.summe_je_seite < 0:
            raise ValueError("summe_je_seite darf nicht negativ sein.")
        if self.slippage_ticks_je_seite < 0:
            raise ValueError("slippage_ticks_je_seite darf nicht negativ sein.")
        if not self.quelle.strip():
            raise ValueError(
                f"Kostenprofil {self.name!r} ohne Quellenangabe. Woher die Zahl "
                "stammt, gehoert zum Wert - sonst laesst sie sich spaeter nicht "
                "pruefen."
            )
        # Ist die Aufteilung angegeben, muss sie zur Summe passen. Eine
        # Aufschluesselung, die etwas anderes ergibt als der verrechnete
        # Betrag, waere schlimmer als gar keine.
        if self.aufschluesselung_bekannt:
            summe = (
                (self.broker_kommission_je_seite or 0.0)
                + (self.boerse_je_seite or 0.0)
                + (self.clearing_je_seite or 0.0)
                + (self.nfa_je_seite or 0.0)
            )
            if abs(summe - self.summe_je_seite) > 0.005:
                raise ValueError(
                    f"Kostenprofil {self.name!r}: die Einzelposten ergeben "
                    f"{summe:.4f}, verrechnet wird aber {self.summe_je_seite:.4f}."
                )

    @property
    def aufschluesselung_bekannt(self) -> bool:
        """Ist die Aufteilung in Einzelposten belegt?"""
        return any(
            wert is not None
            for wert in (
                self.broker_kommission_je_seite,
                self.boerse_je_seite,
                self.clearing_je_seite,
                self.nfa_je_seite,
            )
        )

    @property
    def round_turn(self) -> float:
        """Kosten einer vollstaendigen Position (Eroeffnung plus Schluss)."""
        return 2.0 * self.summe_je_seite

    def to_dict(self) -> dict[str, Any]:
        """Fuer den Bericht - der Backtest MUSS ausweisen, womit gerechnet wurde."""
        return {
            "name": self.name,
            "beschreibung": self.beschreibung,
            "je_seite_usd": round(self.summe_je_seite, 4),
            "round_turn_usd": round(self.round_turn, 4),
            "slippage_ticks_je_seite": self.slippage_ticks_je_seite,
            "ist_annahme": self.ist_annahme,
            "quelle": self.quelle,
            "aufschluesselung": (
                {
                    "broker_kommission": self.broker_kommission_je_seite,
                    "boerse": self.boerse_je_seite,
                    "clearing": self.clearing_je_seite,
                    "nfa": self.nfa_je_seite,
                }
                if self.aufschluesselung_bekannt
                else None
            ),
            "aufschluesselung_hinweis": (
                None
                if self.aufschluesselung_bekannt
                else "Nicht aufgeschluesselt - nur die Summe je Seite ist belegt."
            ),
        }

    def zeile(self) -> str:
        """Einzeiler fuer die Konsole."""
        art = "ANNAHME" if self.ist_annahme else "belegt"
        return (
            f"{self.name}: {self.summe_je_seite:.2f} USD/Seite "
            f"({self.round_turn:.2f} Round Turn), "
            f"Slippage {self.slippage_ticks_je_seite:g} Ticks/Seite [{art}]"
        )


# ---------------------------------------------------------------------------
#  Mitgelieferte Profile
# ---------------------------------------------------------------------------
#
# Die Zahlen stammen von Laurin (23.08.2026). Sie sind hier als Vorgabe
# hinterlegt, damit das Projekt ohne config.yaml lauffaehig bleibt -
# massgeblich ist aber die Konfiguration, nicht dieser Code.

PRIVATE_NINJATRADER = Kostenprofil(
    name="private_ninjatrader",
    beschreibung=(
        "MNQ ueber das NinjaTrader-Free-Modell auf Laurins privatem Konto. "
        "Enthaelt Broker-Kommission sowie Boersen-, Clearing- und "
        "NFA-Gebuehren; die Aufteilung ist nicht belegt."
    ),
    summe_je_seite=0.95,
    slippage_ticks_je_seite=1.0,
    quelle="Laurin, 23.08.2026 - NinjaTrader-Free-Modell, rund 1,90 USD Round Turn",
    # Der Gesamtbetrag ist belegt, die AUFTEILUNG nicht. Deshalb bleiben die
    # Einzelposten None statt mit plausibel klingenden Zahlen gefuellt zu
    # werden - siehe Modul-Docstring.
    ist_annahme=False,
)

LUCID = Kostenprofil(
    name="lucid",
    beschreibung=(
        "MNQ unter einer Lucid-Prop-Firm-Struktur. Arbeitsannahme, nicht "
        "gegen eine Abrechnung geprueft."
    ),
    summe_je_seite=0.50,
    slippage_ticks_je_seite=1.0,
    quelle=(
        "Arbeitsannahme Laurin, 23.08.2026 - extern NICHT verifiziert, "
        "vor Gebrauch gegen die Lucid-Konditionen pruefen"
    ),
    ist_annahme=True,
)

#: Historisches Profil. Bis zum 23.08.2026 rechnete der Backtest damit, ohne
#: dass die Zahl je belegt worden waere. Bleibt erhalten, damit sich aeltere
#: Ergebnisse (etwa die Basisvermessung) nachrechnen lassen.
PAUSCHALE_BIS_23_08_2026 = Kostenprofil(
    name="pauschale_alt",
    beschreibung=(
        "Die pauschale Altannahme von 2,50 USD je Seite. Nur zum Nachrechnen "
        "aelterer Ergebnisse - fuer neue Laeufe ungeeignet."
    ),
    summe_je_seite=2.50,
    slippage_ticks_je_seite=1.0,
    quelle="Altbestand ohne Herkunftsangabe, vermutlich Platzhalter",
    ist_annahme=True,
)

PROFILE: dict[str, Kostenprofil] = {
    profil.name: profil
    for profil in (PRIVATE_NINJATRADER, LUCID, PAUSCHALE_BIS_23_08_2026)
}


class UnbekanntesKostenprofil(KeyError):
    """Der Profilname steht nicht in der Bibliothek."""


def hole_profil(name: str) -> Kostenprofil:
    profil = PROFILE.get(name.lower())
    if profil is None:
        raise UnbekanntesKostenprofil(
            f"Unbekanntes Kostenprofil {name!r}. Verfuegbar: "
            + ", ".join(sorted(PROFILE))
        )
    return profil


def aus_konfiguration(name: str, rohdaten: dict[str, Any]) -> Kostenprofil:
    """Baut ein Profil aus einem YAML-Abschnitt.

    Fehlt die Quellenangabe oder die Summe, bricht das ab statt eine Vorgabe
    zu erfinden - eine Kostenannahme ohne Herkunft ist genau das, was am
    23.08.2026 ersetzt wurde.
    """
    if "summe_je_seite" not in rohdaten:
        raise ValueError(
            f"Kostenprofil {name!r} in der config.yaml hat kein "
            "'summe_je_seite'. Ohne Betrag laesst sich nichts rechnen."
        )

    def optional(schluessel: str) -> float | None:
        wert = rohdaten.get(schluessel)
        return None if wert is None else float(wert)

    return Kostenprofil(
        name=name.lower(),
        beschreibung=str(rohdaten.get("beschreibung", "")).strip(),
        summe_je_seite=float(rohdaten["summe_je_seite"]),
        slippage_ticks_je_seite=float(rohdaten.get("slippage_ticks_je_seite", 1.0)),
        quelle=str(rohdaten.get("quelle", "")).strip(),
        ist_annahme=bool(rohdaten.get("ist_annahme", True)),
        broker_kommission_je_seite=optional("broker_kommission_je_seite"),
        boerse_je_seite=optional("boerse_je_seite"),
        clearing_je_seite=optional("clearing_je_seite"),
        nfa_je_seite=optional("nfa_je_seite"),
    )


def profil_aus_config(backtest_cfg: Any, name: str | None = None) -> Kostenprofil:
    """Das konfigurierte Profil - oder ein ausdruecklich verlangtes anderes.

    ``name`` erlaubt, dasselbe Setup unter einem zweiten Profil zu rechnen,
    ohne die Konfiguration zu aendern. Genau dafuer sind die Profile da.
    """
    gewaehlt = (name or backtest_cfg.kostenprofil).lower()
    rohdaten = getattr(backtest_cfg, "kostenprofile", {}) or {}

    if gewaehlt in rohdaten:
        return aus_konfiguration(gewaehlt, rohdaten[gewaehlt])
    if gewaehlt in PROFILE:
        # In der YAML nicht definiert, aber im Code hinterlegt.
        return PROFILE[gewaehlt]

    raise UnbekanntesKostenprofil(
        f"Kostenprofil {gewaehlt!r} steht weder in der config.yaml unter "
        f"backtest.kostenprofile noch in der Bibliothek. Verfuegbar: "
        + ", ".join(sorted(set(rohdaten) | set(PROFILE)))
    )


__all__ = [
    "LUCID",
    "aus_konfiguration",
    "profil_aus_config",
    "PAUSCHALE_BIS_23_08_2026",
    "PRIVATE_NINJATRADER",
    "PROFILE",
    "Kostenprofil",
    "UnbekanntesKostenprofil",
    "hole_profil",
]
