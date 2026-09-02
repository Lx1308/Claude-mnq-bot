"""Swing-Punkte als vektorisierte Serie - die Grundlage der Strukturerkennung.

``common/structure.py::find_swing_points`` liefert eine Liste mit ``bars_ago``
relativ zum Reihenende. Fuer eine Auswertung ueber 2,5 Mio Kerzen braucht es
statt dessen Arrays: je Position, ob dort ein Swing bestaetigt wurde, sein
Preis und der Index seines Extremums.

DIESELBE DEFINITION
-------------------
Ein Swing-Hoch bei Position ``p``:

    high[p] > max(high[p-strength : p])   und
    high[p] >= max(high[p+1 : p+strength+1])

Streng groesser nach links, groesser-gleich nach rechts - bei Plateaus wird so
genau ein Punkt gemeldet. Identisch zu ``find_swing_points``; ein Test in
``tests/test_ereignisse_swings.py`` vergleicht beide auf echten Kursdaten.

KEIN LOOKAHEAD
--------------
Das Extremum liegt bei ``p``, **bekannt** ist es erst bei ``p + strength`` -
vorher kann eine spaetere Kerze es noch ueberbieten. Alle Ausgabe-Arrays sind
deshalb auf ``p + strength`` gesetzt, nicht auf ``p``. Die
``*_ursprung_idx``-Arrays halten ``p`` fest, fuer Merkmale wie die Dauer eines
Musters.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv

STANDARD_STRENGTH = 3


@dataclass(frozen=True)
class SwingSerie:
    """Swings als Arrays, alle auf dem Bestaetigungsindex ``p + strength``.

    ``hoch_bestaetigt[i]`` ist wahr, wenn bei ``i`` ein Swing-Hoch bestaetigt
    wurde. Dessen Extremum lag bei ``hoch_ursprung_idx[i]`` zum Preis
    ``hoch_preis[i]``. Wo nichts bestaetigt wurde: ``False`` bzw. ``NaN`` bzw.
    ``-1``.
    """

    strength: int
    hoch_bestaetigt: np.ndarray          # bool[n]
    hoch_preis: np.ndarray               # float[n], NaN wo nichts
    hoch_ursprung_idx: np.ndarray        # int[n], -1 wo nichts
    tief_bestaetigt: np.ndarray
    tief_preis: np.ndarray
    tief_ursprung_idx: np.ndarray

    def __len__(self) -> int:
        return len(self.hoch_bestaetigt)

    def letzte_swings(self, kind: str) -> tuple[np.ndarray, np.ndarray]:
        """Je Position: Preis und Ursprungsindex des zuletzt bestaetigten
        Swings der gewuenschten Art, vorwaerts fortgeschrieben.

        ``kind`` ist ``"hoch"`` oder ``"tief"``. ``NaN``/``-1`` bis zum ersten
        bestaetigten Swing.
        """
        best = self.hoch_bestaetigt if kind == "hoch" else self.tief_bestaetigt
        preis = self.hoch_preis if kind == "hoch" else self.tief_preis
        ursprung = self.hoch_ursprung_idx if kind == "hoch" else self.tief_ursprung_idx

        n = len(best)
        letzter_preis = np.full(n, np.nan)
        letzter_ursprung = np.full(n, -1, dtype=np.int64)
        p, u = np.nan, -1
        for i in range(n):
            if best[i]:
                p, u = preis[i], ursprung[i]
            letzter_preis[i] = p
            letzter_ursprung[i] = u
        return letzter_preis, letzter_ursprung


def _rollmax_links(werte: np.ndarray, fenster: int) -> np.ndarray:
    """max(werte[i-fenster : i]) je i - streng links, ohne i selbst."""
    s = pd.Series(werte)
    return s.rolling(fenster).max().shift(1).to_numpy()


def _rollmax_rechts(werte: np.ndarray, fenster: int) -> np.ndarray:
    """max(werte[i+1 : i+fenster+1]) je i.

    Schaut nach vorn - das ist hier erlaubt, weil das Ergebnis anschliessend
    auf ``i + fenster`` verschoben wird und dort dann keine Zukunft mehr ist.
    """
    s = pd.Series(werte)
    return s.rolling(fenster).max().shift(-fenster).to_numpy()


def _rollmin_links(werte: np.ndarray, fenster: int) -> np.ndarray:
    s = pd.Series(werte)
    return s.rolling(fenster).min().shift(1).to_numpy()


def _rollmin_rechts(werte: np.ndarray, fenster: int) -> np.ndarray:
    s = pd.Series(werte)
    return s.rolling(fenster).min().shift(-fenster).to_numpy()


def swing_serie(df: pd.DataFrame, *, strength: int = STANDARD_STRENGTH) -> SwingSerie:
    """Vektorisierte Swing-Erkennung. O(n)."""
    validate_ohlcv(df)
    if strength < 1:
        raise ValueError("strength muss mindestens 1 sein.")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    n = len(df)

    hoch_best = np.zeros(n, dtype=bool)
    hoch_preis = np.full(n, np.nan)
    hoch_ursprung = np.full(n, -1, dtype=np.int64)
    tief_best = np.zeros(n, dtype=bool)
    tief_preis = np.full(n, np.nan)
    tief_ursprung = np.full(n, -1, dtype=np.int64)

    if n < 2 * strength + 1:
        return SwingSerie(
            strength, hoch_best, hoch_preis, hoch_ursprung,
            tief_best, tief_preis, tief_ursprung,
        )

    links_h = _rollmax_links(highs, strength)
    rechts_h = _rollmax_rechts(highs, strength)
    links_l = _rollmin_links(lows, strength)
    rechts_l = _rollmin_rechts(lows, strength)

    # Positionen p mit einem Extremum. NaN-Vergleiche liefern False - die
    # Raender fallen damit von selbst weg.
    ist_hoch = (highs > links_h) & (highs >= rechts_h)
    ist_tief = (lows < links_l) & (lows <= rechts_l)

    p_hoch = np.nonzero(ist_hoch)[0]
    p_tief = np.nonzero(ist_tief)[0]

    # Auf den Bestaetigungsindex verschieben.
    b_hoch = p_hoch + strength
    b_tief = p_tief + strength
    gueltig_h = b_hoch < n
    gueltig_l = b_tief < n

    hoch_best[b_hoch[gueltig_h]] = True
    hoch_preis[b_hoch[gueltig_h]] = highs[p_hoch[gueltig_h]]
    hoch_ursprung[b_hoch[gueltig_h]] = p_hoch[gueltig_h]
    tief_best[b_tief[gueltig_l]] = True
    tief_preis[b_tief[gueltig_l]] = lows[p_tief[gueltig_l]]
    tief_ursprung[b_tief[gueltig_l]] = p_tief[gueltig_l]

    return SwingSerie(
        strength, hoch_best, hoch_preis, hoch_ursprung,
        tief_best, tief_preis, tief_ursprung,
    )


__all__ = ["STANDARD_STRENGTH", "SwingSerie", "swing_serie"]
