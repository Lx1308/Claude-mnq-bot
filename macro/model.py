"""Kanonisches Event-Schema fuer Makro- und Wirtschaftskalenderdaten.

EIN SCHEMA, ZWEI KUENFTIGE FUELLSTELLEN
----------------------------------------
Dieselbe Tabelle soll spaeter sowohl Makro-Beobachtungen (FRED/ALFRED, seit
dieser Fassung angebunden) als auch echte Kalendertermine eines
kostenpflichtigen Anbieters (noch NICHT angebunden, siehe
``macro/provider.py::EconomicCalendarProvider``) aufnehmen - ohne
Schema-Umbau, wenn der zweite Anbieter dazukommt. ``event_type``
unterscheidet die Herkunft.

WARUM NICHT DAS VOLLE, IN DER RECHERCHE VORGESCHLAGENE SCHEMA
----------------------------------------------------------------
Die Recherche schlug zusaetzlich Monetary-Policy-Felder (decision_type,
old_rate/new_rate, statement_available_at, ...) und eine eigene
News-Tabelle vor. Beides ist laut Laurins eigener Priorisierung Phase 2/3,
und beides liesse sich als rein additive Spalten/Tabelle nachruesten, ohne
bestehende Zeilen anzufassen. Sie jetzt schon anzulegen waere eine
Abstraktion fuer einen Bedarf, den es noch nicht gibt - deshalb bewusst
weggelassen (CLAUDE.md: keine Abstraktionen ueber den tatsaechlichen
Bedarf hinaus).

POINT-IN-TIME: DIE DREI ZEITSTEMPEL
-------------------------------------
``scheduled_at_utc``   wann der Termin angekuendigt war (nur ein echter
                        Kalenderanbieter kann das liefern - bei FRED/ALFRED
                        immer ``None``, FRED kennt keine Vorankuendigungen).
``released_at_utc``    wann der Wert real veroeffentlicht wurde. Bei
                        FRED/ALFRED identisch mit ``available_at_utc``,
                        weil FRED keine getrennte "Veroeffentlichung vs.
                        Aufnahme in die Datenbank"-Unterscheidung anbietet.
``available_at_utc``   die einzige Spalte, die fuer Lookahead-Schutz zaehlt:
                        vor diesem Zeitpunkt war der Wert nicht bekannt.
                        JEDE Abfrage "was wusste man zum Zeitpunkt T" MUSS
                        auf diese Spalte filtern, nie auf
                        ``beobachtungszeitraum_utc``.

WARUM ``beobachtungszeitraum_utc`` ZUSAETZLICH ZUM VORGESCHLAGENEN SCHEMA
----------------------------------------------------------------------------
FRED/ALFRED beschreiben einen Wert IMMER relativ zu einer Berichtsperiode
(z.B. "VPI fuer Juli 2026") UND zu einem Vintage (wann genau dieser Wert
so bekannt war). Das vorgeschlagene Schema kennt dafuer nur
``scheduled_at_utc`` - das waere semantisch falsch belegt (Berichtsperiode
ist nicht "wann angekuendigt"). Eine eigene Spalte ist ehrlicher als eine
ueberladene.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MacroObservation:
    """Eine einzelne, unveraenderliche Zeile: ein Wert in genau einem Vintage.

    Jede Revision einer Reihe ist eine EIGENE ``MacroObservation`` - nie ein
    Update einer bestehenden. Siehe ``macro/store.py`` fuer die
    Persistenz-Garantie dahinter.
    """

    source: str                          # z.B. "fred_alfred"
    source_event_id: str                 # z.B. "CPIAUCSL:2026-07-01"
    event_name: str                      # z.B. "VPI (Index)"
    event_type: str                      # "macro_release" | (spaeter) "scheduled_release"

    beobachtungszeitraum_utc: datetime   # welche Periode der Wert beschreibt
    available_at_utc: datetime           # ab wann bekannt - der Lookahead-Schutz
    released_at_utc: datetime            # Veroeffentlichungszeitpunkt (bei FRED = available_at_utc)
    revision: int                        # 0 = Erstveroeffentlichung, dann aufsteigend
    revision_at_utc: datetime            # Zeitpunkt dieser Revision (bei FRED = available_at_utc)

    actual: str                          # als Text gespeichert - FRED liefert Text, Konvertierung beim Lesen

    country: str = "US"
    currency: str = "USD"
    category: str | None = None
    source_url: str | None = None

    # Nur von einem echten Kalenderanbieter befuellbar, bei FRED/ALFRED immer None.
    scheduled_at_utc: datetime | None = None
    importance: str | None = None
    forecast: str | None = None
    previous: str | None = None
    status: str = "released"

    def __post_init__(self) -> None:
        for feld, wert in (
            ("beobachtungszeitraum_utc", self.beobachtungszeitraum_utc),
            ("available_at_utc", self.available_at_utc),
            ("released_at_utc", self.released_at_utc),
            ("revision_at_utc", self.revision_at_utc),
            ("scheduled_at_utc", self.scheduled_at_utc),
        ):
            if wert is not None and wert.tzinfo is None:
                raise ValueError(
                    f"MacroObservation.{feld} muss zeitzonenbewusst sein (UTC), "
                    f"war naiv: {wert!r}. Naive Zeitstempel sind im gesamten "
                    "Projekt verboten - ein Vergleich gegen einen anderen "
                    "Zeitstempel waere sonst falsch, ohne dass Python das meldet."
                )


__all__ = ["MacroObservation"]
