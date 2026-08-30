"""Die Ereignis-Abstraktion fuer die empirische Wissensbasis.

Auftrag Laurins vom 30.08.2026: eine reproduzierbare Datenbasis darueber,
welche Marktsituationen auftreten, wie oft, und wie sie sich entwickeln -
**keine Strategie**. Der Plan steht in ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``.

DIE VIER PHASEN
---------------
Jedes Ereignis traegt vier Zeitpunkte, strikt getrennt (Plan Abschnitt 3):

* ``entstehung_idx``  - die Struktur existiert im Chart (z.B. das zweite Tief)
* ``bestaetigung_idx``- die Definition ist erfuellt (z.B. Swing bestaetigt)
* ``verfuegbar_idx``  - **fruehester Zeitpunkt, zu dem ein Handelnder das
                        wissen konnte**. Nur DAS darf in eine Auswertung.
* Entry-Trigger       - eigene Tabelle, mehrere Varianten je Ereignis

Es gilt immer ``entstehung_idx <= bestaetigung_idx <= verfuegbar_idx``. Eine
Verletzung ist ein Abbruch, kein Hinweis - ``Ereignis`` prueft das im
Konstruktor.

WARUM INDIZES, NICHT ZEITSTEMPEL
-------------------------------
Intern arbeitet alles mit ganzzahligen Positionen in den vorbereiteten
Rahmen. Das ist schnell (numpy statt datetime-Vergleiche), eindeutig (kein
Zeitzonen- oder DST-Zweifel) und macht die Lookahead-Pruefung trivial: "kein
Merkmal aus einem Index > verfuegbar_idx". Zeitstempel entstehen erst beim
Schreiben in die Datenbank.

WARUM MERKMALE ALS DICT
-----------------------
Ein Doppelboden hat andere Rohmerkmale als ein Liquidity Sweep. Ein festes
Schema je Mustertyp waere entweder lueckenhaft oder aufgeblaeht. Das Dict
``merkmale`` haelt die musterspezifischen Rohzahlen; die Datenbank entpackt
sie in Spalten (Plan Abschnitt 9). Laurins Punkt 3: **nicht nur "Muster =
ja", die zugrunde liegenden Zahlen gehoeren gespeichert.**
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

#: Die kanonischen Erkennungs-Zeitebenen (Laurins Entscheidung 30.08.2026:
#: erkennen auf mehreren Ebenen, messen und handeln immer auf 1m).
ERKENNUNGS_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h")


class LookaheadVerletzung(RuntimeError):
    """Ein Ereignis wuerde Information aus der Zukunft verwenden."""


@dataclass(frozen=True)
class Ereignis:
    """Eine erkannte Marktsituation, auf dem 1m-Index verankert.

    ``detect_timeframe`` haelt fest, auf welcher Ebene das Muster erkannt
    wurde; alle drei ``*_idx`` sind Positionen im **1m-Rahmen**. Ein Muster,
    das auf 15m erkannt wurde, ist erst am Schluss seiner 15m-Kerze bekannt -
    der entsprechende 1m-Index steht dann in ``verfuegbar_idx``.
    """

    pattern_type: str
    pattern_variant: str
    detect_timeframe: str
    direction: int                       # +1 long-gedeutet, -1 short-gedeutet

    entstehung_idx: int
    bestaetigung_idx: int
    verfuegbar_idx: int

    #: Musterspezifische Rohzahlen. Preise, Abstaende, Dauer, Groesse -
    #: alles, woraus die Definition abgeleitet wurde.
    merkmale: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (self.entstehung_idx <= self.bestaetigung_idx <= self.verfuegbar_idx):
            raise LookaheadVerletzung(
                f"{self.pattern_type}/{self.pattern_variant}: "
                f"entstehung={self.entstehung_idx}, "
                f"bestaetigung={self.bestaetigung_idx}, "
                f"verfuegbar={self.verfuegbar_idx} - die Reihenfolge muss "
                "entstehung <= bestaetigung <= verfuegbar sein."
            )
        if self.direction not in (-1, 1):
            raise ValueError(
                f"direction muss +1 oder -1 sein, ist {self.direction}."
            )

    @property
    def dauer_bars(self) -> int:
        """Kerzen von der Entstehung bis zur Verfuegbarkeit."""
        return self.verfuegbar_idx - self.entstehung_idx

    def key(self) -> tuple:
        """Eindeutig im Rahmen eines Laufs - fuer Deduplizierung.

        Zwei Erkenner koennen dasselbe Ereignis liefern (ein Doppelboden IST
        oft auch ein doppelter Swing-Tief-Test). Sie werden nicht
        zusammengefasst - jede Sicht ist eine eigene Zeile -, aber ein
        einzelner Erkenner darf dasselbe Ereignis nicht doppelt melden.
        """
        return (
            self.pattern_type,
            self.pattern_variant,
            self.detect_timeframe,
            self.verfuegbar_idx,
            round(float(self.merkmale.get("level_2", self.merkmale.get("level_1", 0.0))), 4),
        )


def pruefe_lookahead(
    ereignisse: list[Ereignis],
    *,
    rahmen_laenge: int,
) -> None:
    """Sammelpruefung: kein Ereignis reicht ueber den Rahmen hinaus, und
    alle Indizes sind gueltig.

    Die eigentliche Lookahead-Sicherheit steckt in den einzelnen Erkennern
    und wird dort getestet (Reihe abschneiden, neu rechnen, Vergleich). Diese
    Funktion faengt die groben Fehler ab.
    """
    for e in ereignisse:
        if e.entstehung_idx < 0 or e.verfuegbar_idx >= rahmen_laenge:
            raise LookaheadVerletzung(
                f"{e.pattern_type}: Index ausserhalb des Rahmens "
                f"(0..{rahmen_laenge - 1}): entstehung={e.entstehung_idx}, "
                f"verfuegbar={e.verfuegbar_idx}"
            )


def grobe_kerze_zu_1m_index(
    grob_index: pd.DatetimeIndex,
    eins_index: pd.DatetimeIndex,
    grob_position: int,
) -> int | None:
    """Position einer groben Kerze -> 1m-Index, an dem sie **bekannt** ist.

    Eine 15m-Kerze mit Zeitstempel 14:15 (Schlusszeit, NT8-Konvention) fasst
    14:00:00 bis 14:14:59 zusammen. Bekannt ist sie ab dem Schluss der
    1m-Kerze 14:15 - also am 1m-Index mit genau diesem Zeitstempel.

    ``None``, wenn die 1m-Reihe zu diesem Zeitpunkt keine Kerze hat (Luecke)
    oder der Zeitpunkt jenseits des 1m-Endes liegt. Der Aufrufer verwirft das
    Ereignis dann - lieber eines weniger als eines mit falschem Zeitbezug.
    """
    if grob_position < 0 or grob_position >= len(grob_index):
        return None
    ziel = grob_index[grob_position]
    pos = eins_index.searchsorted(ziel, side="left")
    if pos >= len(eins_index) or eins_index[pos] != ziel:
        return None
    return int(pos)


__all__ = [
    "ERKENNUNGS_TIMEFRAMES",
    "Ereignis",
    "LookaheadVerletzung",
    "grobe_kerze_zu_1m_index",
    "pruefe_lookahead",
]
