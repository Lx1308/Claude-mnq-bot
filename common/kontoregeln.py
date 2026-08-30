"""Kontoregeln: was ein Konto erlaubt, als benanntes Profil.

Warum das ein eigenes Modul ist
-------------------------------
Ein Prop-Konto ist nicht durch eine Zahl beschrieben. Ein Tagesverlustlimit
verhaelt sich anders als ein nachziehender Gesamtverlust, und der wiederum
anders als eine Konsistenzregel, die erst beim Auszahlungsantrag greift. Wer
das in eine Konstante ``MAX_DD = 1500`` presst, misst spaeter das Falsche und
merkt es nicht.

Dieselbe Trennung wie bei den Handelskosten (``backtest/kosten.py``): ein
**benanntes Profil** mit ``quelle`` und ``ist_annahme``, nicht eine Zahl im
Code. Und derselbe Grund: dasselbe Handelsverhalten ist unter 25k-Regeln ein
anderes Geschaeft als unter 150k-Regeln, und ein Ergebnis ohne diese Angabe
laesst sich nicht einordnen.

Verhaeltnis zu ``ideas.profil``
-------------------------------
``ideas.profil`` (``sim_frei``/``lucid_challenge``/``lucid_funded``)
dokumentiert die **tatsaechliche Kontoumgebung**, in der eine Idee entstanden
ist - ein Protokollfeld, kein Steuerungsfeld (Invariante 6). Die Regeln hier
sind das Gegenstueck fuer die **Ausfuehrung**: sie entscheiden, ob eine Order
rausgehen darf. Beide muessen zusammenpassen, duerfen aber nicht vermischt
werden.

Woher die Zahlen stammen - und was daran unsicher ist
-----------------------------------------------------
Lucids eigenes Hilfe-Center (``support.lucidtrading.com``) antwortet
automatisierten Abrufen mit HTTP 403. Die Werte hier stammen deshalb aus
**zwei unabhaengigen Uebersichten Dritter** (Stand 30.08.2026) und sind
**nicht gegen Lucids eigene Bedingungen geprueft**. Wo die beiden Quellen
sich widersprachen, steht hier der **striktere** Wert - eine zu scharfe
Grenze kostet einen Trade, eine zu lasche kostet das Konto.

Jedes Lucid-Profil traegt deshalb ``ist_annahme=True``. Das ist keine
Formalie: solange das so steht, darf keine Auswertung behaupten, ein Lauf
habe "die Lucid-Regeln eingehalten" - er hat die hier hinterlegte Annahme
eingehalten. Laurin bestaetigt die Zahlen aus seinem Konto-Dashboard, dann
wird ``ist_annahme`` auf False gesetzt und ``quelle`` benannt.

Ein 300k-Konto ist in beiden Quellen **nicht** aufgefuehrt; die groesste
Stufe ist 150k. Es ist deshalb auch hier nicht eingetragen - lieber ein
"kenne ich nicht" als eine erfundene Stufe.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

__all__ = [
    "DrawdownArt",
    "Kontoregeln",
    "KONTOREGELN",
    "hole_kontoregeln",
    "bekannte_kontoprofile",
    "aus_konfiguration",
]


class DrawdownArt:
    """Wie der Gesamtverlust nachgezogen wird.

    Die Unterscheidung ist nicht kosmetisch: bei ``EOD_TRAILING`` zaehlt der
    Kontostand zum Sitzungsschluss, bei ``INTRADAY_TRAILING`` der hoechste
    Stand waehrend des Tages - inklusive unrealisierter Gewinne. Dieselbe
    Handelsfolge reisst im zweiten Fall Grenzen, die im ersten nie beruehrt
    werden.
    """

    KEINER = "keiner"
    STATISCH = "statisch"
    EOD_TRAILING = "eod_trailing"
    INTRADAY_TRAILING = "intraday_trailing"

    ALLE = frozenset({KEINER, STATISCH, EOD_TRAILING, INTRADAY_TRAILING})


@dataclass(frozen=True)
class Kontoregeln:
    """Ein benanntes Regelwerk.

    ``None`` heisst durchgehend **"diese Regel gibt es hier nicht"**, nicht
    "unbekannt". Was unbekannt ist, gehoert nicht ins Register, sondern bleibt
    weg - siehe Modul-Docstring zum 300k-Konto.
    """

    name: str
    anbieter: str
    kontogroesse_usd: float

    #: Gewinnziel der Pruefungsphase. Bei einem freien Konto None.
    profit_ziel_usd: float | None

    #: Groesster zulaessiger Gesamtverlust ab dem massgeblichen Hoechststand.
    max_verlust_usd: float | None
    drawdown_art: str

    #: Tagesverlustlimit. None heisst: es gibt keins (nicht: unbegrenzt riskant).
    tagesverlust_usd: float | None

    #: Ein weicher Bruch sperrt nur den Handelstag, ein harter kostet das Konto.
    tagesverlust_hart: bool

    max_kontrakte_micro: int | None
    max_kontrakte_mini: int | None

    #: Groesster Einzeltag hoechstens dieser Anteil am Gesamtgewinn (0.40 = 40 %).
    #: Greift erst beim Auszahlungsantrag, nicht beim Handeln - deshalb ist es
    #: hier eine Kennzahl zum Beobachten, kein Ausfuehrungsriegel.
    konsistenz_anteil: float | None

    min_handelstage: int | None

    quelle: str
    ist_annahme: bool

    def __post_init__(self) -> None:
        if self.drawdown_art not in DrawdownArt.ALLE:
            raise ValueError(
                f"Unbekannte drawdown_art {self.drawdown_art!r}. "
                f"Bekannt: {', '.join(sorted(DrawdownArt.ALLE))}"
            )
        if self.kontogroesse_usd < 0:
            raise ValueError("kontogroesse_usd darf nicht negativ sein.")
        for feld in ("max_verlust_usd", "tagesverlust_usd", "profit_ziel_usd"):
            wert = getattr(self, feld)
            if wert is not None and wert <= 0:
                raise ValueError(f"{feld} muss positiv sein oder None, nicht {wert}.")
        if self.max_verlust_usd is None and self.drawdown_art != DrawdownArt.KEINER:
            raise ValueError(
                "Ohne max_verlust_usd ergibt eine drawdown_art keinen Sinn."
            )

    # -- Abgeleitetes ------------------------------------------------------

    @property
    def initiale_trail_grenze_usd(self) -> float | None:
        """Kontostand, ab dem der nachziehende Verlust festfriert.

        Lucid zieht den Verlustpuffer mit dem Kontostand hoch, aber nur bis
        Startbalance + max_verlust. Wer darueber schliesst, hat die Grenze
        dauerhaft auf der Startbalance stehen - ab da kann das Konto nicht
        mehr unter den Ausgangswert fallen, ohne gerissen zu sein.

        **Annahme.** Dass die Grenze genau bei Startbalance + max_verlust
        einfriert, ist die uebliche Auslegung, aber aus den Quellen nicht
        woertlich belegt (siehe Modul-Docstring).
        """
        if self.max_verlust_usd is None:
            return None
        return self.kontogroesse_usd + self.max_verlust_usd

    def max_kontrakte(self, instrument_ist_micro: bool = True) -> int | None:
        return (
            self.max_kontrakte_micro if instrument_ist_micro else self.max_kontrakte_mini
        )

    def to_dict(self) -> dict[str, Any]:
        """Fuer Protokolle und Berichte - jede Zahl mit ihrer Herkunft."""
        return {
            "name": self.name,
            "anbieter": self.anbieter,
            "kontogroesse_usd": self.kontogroesse_usd,
            "profit_ziel_usd": self.profit_ziel_usd,
            "max_verlust_usd": self.max_verlust_usd,
            "drawdown_art": self.drawdown_art,
            "tagesverlust_usd": self.tagesverlust_usd,
            "tagesverlust_hart": self.tagesverlust_hart,
            "max_kontrakte_micro": self.max_kontrakte_micro,
            "max_kontrakte_mini": self.max_kontrakte_mini,
            "konsistenz_anteil": self.konsistenz_anteil,
            "min_handelstage": self.min_handelstage,
            "quelle": self.quelle,
            "ist_annahme": self.ist_annahme,
        }

    def zeile(self) -> str:
        """Einzeiler fuer Berichtskoepfe."""
        if self.max_verlust_usd is None:
            return f"{self.name}: keine Kontoregeln (Eigenkapital)"
        tag = (
            f"{self.tagesverlust_usd:.0f} USD/Tag"
            if self.tagesverlust_usd is not None
            else "kein Tageslimit"
        )
        vermerk = " [ANNAHME, nicht gegen die Bedingungen geprueft]" if self.ist_annahme else ""
        return (
            f"{self.name}: {self.kontogroesse_usd:.0f} USD, "
            f"max. Verlust {self.max_verlust_usd:.0f} USD ({self.drawdown_art}), "
            f"{tag}, max. {self.max_kontrakte_micro} Micro{vermerk}"
        )


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

_LUCID_QUELLE = (
    "Zwei unabhaengige Uebersichten Dritter, abgerufen 30.08.2026 "
    "(damnpropfirms.com, tradetanto.com). Lucids eigenes Hilfe-Center "
    "antwortet automatisierten Abrufen mit HTTP 403. NICHT gegen Lucids "
    "Bedingungen geprueft. Bei Widerspruch steht hier der striktere Wert."
)


def _lucid_pro(
    groesse: int,
    ziel: float,
    max_verlust: float,
    tagesverlust: float | None,
    micro: int,
    mini: int,
) -> Kontoregeln:
    return Kontoregeln(
        name=f"lucid_pro_{groesse // 1000}k",
        anbieter="lucid",
        kontogroesse_usd=float(groesse),
        profit_ziel_usd=ziel,
        max_verlust_usd=max_verlust,
        drawdown_art=DrawdownArt.EOD_TRAILING,
        tagesverlust_usd=tagesverlust,
        # Beide Quellen nennen die Lucid-Tageslimits ausdruecklich "soft":
        # der Handelstag ist zu Ende, das Konto bleibt bestehen.
        tagesverlust_hart=False,
        max_kontrakte_micro=micro,
        max_kontrakte_mini=mini,
        konsistenz_anteil=0.40,
        min_handelstage=1,
        quelle=_LUCID_QUELLE,
        ist_annahme=True,
    )


#: Freies Konto - eigenes Geld, keine fremden Regeln.
#:
#: Ausdruecklich KEIN "unbegrenzt": es gibt hier nur keine Vorgaben eines
#: Anbieters. Was der Bot sich selbst zumutet, steht in ``execution.risiko``
#: und gilt auch hier.
FREI = Kontoregeln(
    name="frei",
    anbieter="frei",
    kontogroesse_usd=0.0,
    profit_ziel_usd=None,
    max_verlust_usd=None,
    drawdown_art=DrawdownArt.KEINER,
    tagesverlust_usd=None,
    tagesverlust_hart=False,
    max_kontrakte_micro=None,
    max_kontrakte_mini=None,
    konsistenz_anteil=None,
    min_handelstage=None,
    quelle="Eigenkapital - keine Anbieterregeln.",
    ist_annahme=False,
)


KONTOREGELN: dict[str, Kontoregeln] = {
    regeln.name: regeln
    for regeln in (
        FREI,
        # LucidPro. Das 25k-Konto hat als einziges kein Tagesverlustlimit.
        _lucid_pro(25_000, 1_250, 1_000, None, micro=20, mini=2),
        _lucid_pro(50_000, 3_000, 2_000, 1_200, micro=40, mini=4),
        # 100k: eine Quelle nennt 1.800, die andere 2.100 - der striktere gilt.
        _lucid_pro(100_000, 6_000, 3_000, 1_800, micro=60, mini=6),
        # 150k: 2.700 gegen 3.000 - dito.
        _lucid_pro(150_000, 9_000, 4_500, 2_700, micro=100, mini=10),
    )
}

#: LucidFlex unterscheidet sich in der Pruefungsphase nur dadurch, dass es
#: kein Tagesverlustlimit gibt (dafuer eine 50-Prozent-Konsistenzregel).
for _groesse in (50_000, 100_000, 150_000):
    _basis = KONTOREGELN[f"lucid_pro_{_groesse // 1000}k"]
    KONTOREGELN[f"lucid_flex_{_groesse // 1000}k"] = replace(
        _basis,
        name=f"lucid_flex_{_groesse // 1000}k",
        tagesverlust_usd=None,
        konsistenz_anteil=0.50,
    )
del _groesse, _basis


def bekannte_kontoprofile() -> list[str]:
    return sorted(KONTOREGELN)


def hole_kontoregeln(name: str) -> Kontoregeln:
    """Regelwerk nach Namen - oder ein Fehler, der die Auswahl nennt."""
    schluessel = str(name).strip().lower()
    if schluessel not in KONTOREGELN:
        raise KeyError(
            f"Unbekanntes Kontoprofil {name!r}. "
            f"Bekannt: {', '.join(bekannte_kontoprofile())}"
        )
    return KONTOREGELN[schluessel]


def aus_konfiguration(name: str, rohdaten: dict[str, Any] | None) -> Kontoregeln:
    """Ein Registerprofil, ueberschrieben mit den Werten aus ``config.yaml``.

    Damit laesst sich eine Zahl korrigieren, sobald Laurin sie aus seinem
    Dashboard bestaetigt hat, ohne den Code anzufassen. Wer etwas
    ueberschreibt, muss ``quelle`` mitliefern - sonst stuende im Protokoll
    eine Zahl ohne Herkunft, und das ist genau der Zustand, den dieses Modul
    verhindern soll.
    """
    basis = hole_kontoregeln(name)
    if not rohdaten:
        return basis

    erlaubt = {
        "kontogroesse_usd", "profit_ziel_usd", "max_verlust_usd", "drawdown_art",
        "tagesverlust_usd", "tagesverlust_hart", "max_kontrakte_micro",
        "max_kontrakte_mini", "konsistenz_anteil", "min_handelstage",
        "quelle", "ist_annahme",
    }
    unbekannt = set(rohdaten) - erlaubt
    if unbekannt:
        raise ValueError(
            f"Unbekannte Felder im Kontoprofil {name!r}: {', '.join(sorted(unbekannt))}"
        )

    aenderungen = {k: v for k, v in rohdaten.items() if k != "quelle"}
    if aenderungen and "quelle" not in rohdaten:
        raise ValueError(
            f"Kontoprofil {name!r} wird ueberschrieben, aber ohne 'quelle'. "
            "Eine geaenderte Zahl ohne Herkunft ist im Protokoll wertlos."
        )
    return replace(basis, **rohdaten)
