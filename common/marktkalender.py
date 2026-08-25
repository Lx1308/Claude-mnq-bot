"""Boersenfeiertage und Frueh-Schluesse - Ergaenzung zu ``common/sessions.py``.

WARUM EIN EIGENES MODUL
-------------------------
``sessions.py`` rechnet den taeglichen CME-Rollover (18:00 ET) auf dem
Datum, kennt aber keine Feiertage - ein Handelstag, der komplett ausfaellt
(Weihnachten, Neujahr), wird dort nicht erkannt. Fuer die Research-Engine
(Regime-Zuordnung, Makro-Verfuegbarkeitspruefung an Feiertagen) reicht das
nicht mehr.

QUELLE: ``pandas_market_calendars``, KALENDER EMPIRISCH GEPRUEFT
--------------------------------------------------------------------
Der Kalendername ist keine Vermutung: gegen die installierte Bibliothek
geprueft (24.08.2026) - ``CME_Equity`` schliesst den 25.12. und 1.1. korrekt
aus und zeigt den 24.12. korrekt als Fruehschluss (Handelsende 18:00 UTC
statt 22:00 UTC). Das ist der Kalender fuer CME-Index-Futures (MNQ/MES/ES/NQ)
- ``CME_Agriculture``/``CME_Rate``/etc. haben ANDERE Feiertage und waeren
hier falsch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import pandas_market_calendars as mcal

DEFAULT_CALENDAR = "CME_Equity"


class MarktkalenderFehler(RuntimeError):
    """Der angegebene Kalendername ist der Bibliothek unbekannt."""


@dataclass
class Marktkalender:
    """Duenner, zustandsbehafteter Wrapper - haelt den Kalender fuer
    wiederholte Abfragen im Speicher statt ihn bei jedem Aufruf neu zu bauen.
    """

    name: str = DEFAULT_CALENDAR

    def __post_init__(self) -> None:
        try:
            self._kalender = mcal.get_calendar(self.name)
        except RuntimeError as exc:
            # abbrechende Startpruefung statt stiller Fehlfunktion
            # (Invariante 12) - ein Tippfehler im Kalendernamen soll sofort
            # auffallen, nicht dazu fuehren, dass jeder Tag als Handelstag
            # gilt.
            raise MarktkalenderFehler(
                f"Kalender {self.name!r} ist pandas_market_calendars nicht "
                f"bekannt. Verfuegbare Namen: {mcal.get_calendar_names()}"
            ) from exc

    def ist_handelstag(self, datum: date) -> bool:
        zeitplan = self._kalender.schedule(start_date=datum, end_date=datum)
        return not zeitplan.empty

    def ist_fruehschluss(self, datum: date) -> bool:
        """Endet die Session an diesem Tag vor der ueblichen Schlusszeit?

        Vergleich in der Boersenzeit des Kalenders (``self._kalender.tz``),
        NICHT in UTC: der UTC-Zeitpunkt der regulaeren Schlusszeit
        verschiebt sich mit der Sommerzeit (21:00 UTC im Sommer, 22:00 UTC
        im Winter fuer denselben lokalen 16:00-CT-Schluss) - ein fester
        UTC-Stundenwert waere in der Haelfte des Jahres falsch. Das war ein
        echter Fehler in einer frueheren Fassung dieser Funktion, gefunden
        beim Testen gegen einen ganz normalen August-Handelstag, der sich
        gegen einen winterfesten UTC-Schwellenwert wie ein Fruehschluss las.

        Regulaere Schlusszeit kommt aus ``self._kalender.close_time`` - der
        eigenen Angabe der Bibliothek, nicht aus einem geschaetzten Wert.
        """
        zeitplan = self._kalender.schedule(start_date=datum, end_date=datum)
        if zeitplan.empty:
            return False
        schluss = zeitplan.iloc[0]["market_close"]
        if schluss.tzinfo is None:
            schluss = schluss.tz_localize("UTC")
        schluss_lokal = schluss.tz_convert(self._kalender.tz)
        return schluss_lokal.time() < self._kalender.close_time

    def naechster_handelstag(self, ab: date) -> date:
        """Der naechste Tag (ab einschliesslich) mit gueltiger Session."""
        zeitplan = self._kalender.schedule(
            start_date=ab, end_date=ab + pd.Timedelta(days=14)
        )
        if zeitplan.empty:
            raise MarktkalenderFehler(
                f"Kein Handelstag in den 14 Tagen ab {ab} gefunden - "
                "Kalenderdaten pruefen."
            )
        erster = zeitplan.index[0]
        return erster.date() if hasattr(erster, "date") else erster.to_pydatetime().date()

    def handelstage_zwischen(self, start: date, ende: date) -> list[date]:
        zeitplan = self._kalender.schedule(start_date=start, end_date=ende)
        return [
            (idx.date() if hasattr(idx, "date") else idx.to_pydatetime().date())
            for idx in zeitplan.index
        ]


__all__ = ["DEFAULT_CALENDAR", "Marktkalender", "MarktkalenderFehler"]
