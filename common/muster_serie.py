"""Chartmuster als Serie ueber die ganze Historie - nicht nur am rechten Rand.

WOZU
----
``common/patterns.py`` erkennt Muster **punktuell**: es sieht ans Ende eines
DataFrames und sagt "hier ist gerade ein Doppelboden". Das ist richtig fuer
den ``/analyse``-Bericht und fuer die Oberflaeche.

Fuer Forschung reicht das nicht. Die Frage "traegt ein W, und in wie vielen
Faellen" laesst sich nur beantworten, wenn fuer **jede** Kerze der Historie
feststeht, ob dort ein Muster vorlag. Aus einem punktuellen Erkenner wird
sonst eine Schleife ueber 500.000 Kerzen, die jedes Mal die Swing-Punkte neu
sucht - Stunden Rechenzeit fuer etwas, das in Sekunden geht.

DER LOOKAHEAD, DER HIER VERHINDERT WIRD
---------------------------------------
Ein Swing-Tief ist an seiner eigenen Kerze **nicht erkennbar**.
``find_swing_points`` sagt es selbst: die letzten ``strength`` Kerzen koennen
per Definition kein bestaetigtes Extrem sein, "ob sie eines werden,
entscheidet sich erst in der Zukunft".

Damit gilt fuer ein W: das zweite Tief liegt bei Kerze *i*, bekannt ist es
fruehestens bei Kerze *i + strength*. Wer im Backtest "am zweiten Tief"
einsteigt, handelt mit Wissen aus der Zukunft - und das Ergebnis sieht
hervorragend aus, ohne dass an den Kursen etwas verdaechtig waere.

Dieses Modul fuehrt deshalb beide Zeitpunkte getrennt (wie
``common/market_primitives.py``):

* ``event_index`` - wo das Muster im Chart **liegt** (das zweite Tief).
  Fuer die Anzeige.
* ``verfuegbar_index`` - ab wann es **bekannt** war. Ausschliesslich das
  darf in eine Auswertung eingehen.

Die erzeugten Spalten sind auf ``verfuegbar_index`` gesetzt. Wer die
Ereigniszeit braucht, findet sie in ``w_event_ts``.

GLEICHHEIT MIT DEM PUNKTUELLEN ERKENNER
---------------------------------------
Es gibt hier **keine zweite Musterdefinition**. Die Bedingungen
(Spitzenabstand, Tiefe des Zwischentals, Konfidenzformel) sind aus
``detect_double_top_bottom`` uebernommen, und ein Test prueft an echten Daten,
dass beide zum selben Urteil kommen. Zwei Definitionen desselben Musters
waeren derselbe Fehler wie zwei Indikator-Implementierungen (Invariante 1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv
from common.patterns import _clamp
from common.structure import find_swing_points

#: Vorgaben aus ``detect_double_top_bottom``. Hier gespiegelt, damit beide
#: Wege nachweislich dieselben Schwellen benutzen; der Gleichheitstest
#: vergleicht sie.
STANDARD_STRENGTH = 3
STANDARD_MAX_SPITZENABSTAND_ATR = 0.5
STANDARD_MIN_TALTIEFE_ATR = 1.0

#: Wie viele Kerzen zurueck ein Muster hoechstens reichen darf. Entspricht
#: ``lookback`` des punktuellen Erkenners: liegt die erste Spitze weiter
#: zurueck, ist der Zusammenhang zwischen den beiden Extrema nicht mehr
#: plausibel.
STANDARD_LOOKBACK = 120


@dataclass(frozen=True)
class Musterfund:
    """Ein Doppelboden oder Doppeltop mit beiden Zeitpunkten."""

    art: str                    # "Doppelboden" | "Doppeltop"
    richtung: str               # "bullish" | "bearish"
    event_index: int            # Kerze des zweiten Extrems - fuer die Anzeige
    verfuegbar_index: int       # ab hier bekannt - NUR das zaehlt fuer Auswertung
    erste_spitze: float
    zweite_spitze: float
    nackenlinie: float
    spitzenabstand: float
    taltiefe: float
    konfidenz: float

    #: Kerze des ERSTEN Extrems. Zusammen mit ``event_index`` ergibt das die
    #: Formationsdauer - das Merkmal, an dem sich ein W vom Marktrauschen
    #: unterscheiden laesst. Zwei Tiefs vier Kerzen auseinander sind eine
    #: andere Sache als zwei Tiefs sechzig Kerzen auseinander, und ohne
    #: diesen Index war das nicht unterscheidbar.
    erst_index: int = -1

    @property
    def dauer_bars(self) -> int:
        """Kerzen zwischen den beiden Extrema. ``-1``, wenn unbekannt."""
        return -1 if self.erst_index < 0 else self.event_index - self.erst_index


def finde_doppelmuster(
    df: pd.DataFrame,
    *,
    atr: pd.Series | None = None,
    strength: int = STANDARD_STRENGTH,
    lookback: int = STANDARD_LOOKBACK,
    max_spitzenabstand_atr: float = STANDARD_MAX_SPITZENABSTAND_ATR,
    min_taltiefe_atr: float = STANDARD_MIN_TALTIEFE_ATR,
) -> list[Musterfund]:
    """Alle Doppelboeden und Doppeltops der Reihe, in zeitlicher Ordnung.

    ``atr`` ist die ATR-Spalte des vorbereiteten Rahmens. Bewertet wird mit
    dem ATR-Wert **am Verfuegbarkeitszeitpunkt** - dem einzigen, der zu
    diesem Zeitpunkt bekannt war.

    Die Swing-Punkte werden **einmal** ueber die ganze Reihe gesucht statt je
    Kerze neu. Das ist der ganze Geschwindigkeitsgewinn: aus O(n x lookback)
    wird O(n).
    """
    validate_ohlcv(df)
    if len(df) < 2 * strength + 2:
        return []

    if atr is None:
        atr = df.get("atr")
    if atr is None:
        raise ValueError(
            "Ohne ATR ist kein Doppelmuster bewertbar - die Schwellen fuer "
            "Spitzenabstand und Taltiefe sind ATR-Vielfache. Uebergib die "
            "atr-Spalte des vorbereiteten Rahmens."
        )
    atr_werte = np.asarray(atr, dtype=float)

    punkte = find_swing_points(df, strength=strength)
    if len(punkte) < 3:
        return []

    # find_swing_points liefert bars_ago relativ zum Reihenende. Fuer eine
    # Serie ist der absolute Index handlicher.
    letzter = len(df) - 1
    geordnet = sorted(punkte, key=lambda p: letzter - p.bars_ago)
    indizes = [letzter - p.bars_ago for p in geordnet]

    funde: list[Musterfund] = []

    for art, kind, richtung in (
        ("Doppelboden", "low", "bullish"),
        ("Doppeltop", "high", "bearish"),
    ):
        gleiche = [
            (idx, p) for idx, p in zip(indizes, geordnet) if p.kind == kind
        ]
        gegen = [(idx, p) for idx, p in zip(indizes, geordnet) if p.kind != kind]

        # Die Gegen-Swings als aufsteigende Arrays: den "Berg"/"Talpunkt"
        # zwischen zwei gleichartigen Swings sucht sonst je Paar eine
        # Komplettschleife ueber alle Gegen-Swings - O(Swings^2), auf 2,5 Mio
        # Kerzen (~250.000 Swings) nicht rechenbar. Mit searchsorted wird je
        # Paar nur das kurze Fenster dazwischen betrachtet.
        gegen_idx = np.fromiter((idx for idx, _ in gegen), dtype=np.int64,
                                count=len(gegen))
        gegen_preis = np.fromiter((p.price for _, p in gegen), dtype=float,
                                  count=len(gegen))
        gegen_punkt = [p for _, p in gegen]

        for n in range(1, len(gleiche)):
            erst_idx, erst = gleiche[n - 1]
            zweit_idx, zweit = gleiche[n]

            # Bekannt ist das zweite Extrem erst ``strength`` Kerzen spaeter.
            verfuegbar = zweit_idx + strength
            if verfuegbar > letzter:
                continue

            if zweit_idx - erst_idx > lookback:
                continue

            atr_wert = atr_werte[verfuegbar]
            if not np.isfinite(atr_wert) or atr_wert <= 0:
                continue

            spitzenabstand = abs(zweit.price - erst.price)
            if spitzenabstand > max_spitzenabstand_atr * atr_wert:
                continue

            lo = int(np.searchsorted(gegen_idx, erst_idx, side="right"))
            hi = int(np.searchsorted(gegen_idx, zweit_idx, side="left"))
            if hi <= lo:
                continue

            # Beim Doppelboden ist das Zwischenhoch das hoechste, beim
            # Doppeltop das Zwischentief das tiefste. ``argmax``/``argmin``
            # liefern - wie Pythons ``max``/``min`` - bei Gleichstand den
            # ersten Treffer.
            teil = gegen_preis[lo:hi]
            rel = int(teil.argmax() if kind == "low" else teil.argmin())
            tal = gegen_punkt[lo + rel]

            taltiefe = abs(((erst.price + zweit.price) / 2.0) - tal.price)
            if taltiefe < min_taltiefe_atr * atr_wert:
                continue

            naehe = 1.0 - (spitzenabstand / (max_spitzenabstand_atr * atr_wert))
            tiefe_score = _clamp(taltiefe / (2.0 * min_taltiefe_atr * atr_wert))
            konfidenz = _clamp(0.4 * naehe + 0.6 * tiefe_score)

            funde.append(
                Musterfund(
                    art=art,
                    richtung=richtung,
                    event_index=zweit_idx,
                    verfuegbar_index=verfuegbar,
                    erste_spitze=float(erst.price),
                    zweite_spitze=float(zweit.price),
                    nackenlinie=float(tal.price),
                    spitzenabstand=float(spitzenabstand),
                    taltiefe=float(taltiefe),
                    konfidenz=float(konfidenz),
                    erst_index=erst_idx,
                )
            )

    funde.sort(key=lambda f: f.verfuegbar_index)
    return funde


#: Spaltennamen der Musterserie. ``w_`` fuer den Doppelboden (das "W"),
#: ``m_`` fuer das Doppeltop.
DOPPELMUSTER_SPALTEN = (
    "w_erkannt", "w_nackenlinie", "w_zweites_tief", "w_konfidenz",
    "w_event_ts", "w_nackenbruch",
    "m_erkannt", "m_nackenlinie", "m_zweites_hoch", "m_konfidenz",
    "m_event_ts", "m_nackenbruch",
)


def doppelmuster_spalten(
    df: pd.DataFrame,
    *,
    atr: pd.Series | None = None,
    strength: int = STANDARD_STRENGTH,
    lookback: int = STANDARD_LOOKBACK,
    gueltig_kerzen: int = 24,
    **schwellen: float,
) -> pd.DataFrame:
    """Die Musterfunde als Spalten - anschlussfaehig fuer Regeln und Backtest.

    Die Spalten stehen auf dem **Verfuegbarkeitszeitpunkt**, nicht auf dem
    zweiten Extrem. ``w_event_ts`` haelt fest, wo das Muster im Chart liegt.

    ``gueltig_kerzen`` bestimmt, wie lange ein erkanntes Muster "steht":
    ``w_nackenbruch`` kann so viele Kerzen nach der Erkennung noch ausloesen.
    Ohne dieses Fenster waere der Nackenbruch eine Zustandsabfrage statt
    einer Flanke, und dieselbe Bewegung zaehlte vielfach (CLAUDE.md,
    Erweiterungspunkte).

    Zwei Einstiegszeitpunkte, ausdruecklich getrennt:

    * ``w_erkannt``   - das Muster ist bestaetigt (frueh, schlechterer Kurs)
    * ``w_nackenbruch`` - der Kurs schliesst jenseits der Nackenlinie
      (spaeter, teurerer Einstieg, aber bestaetigt)

    Welcher der bessere ist, ist eine Messfrage, keine Meinungsfrage.
    """
    funde = finde_doppelmuster(
        df, atr=atr, strength=strength, lookback=lookback, **schwellen
    )

    n = len(df)
    spalten: dict[str, np.ndarray] = {
        "w_erkannt": np.zeros(n, dtype=bool),
        "w_nackenlinie": np.full(n, np.nan),
        "w_zweites_tief": np.full(n, np.nan),
        "w_konfidenz": np.full(n, np.nan),
        "m_erkannt": np.zeros(n, dtype=bool),
        "m_nackenlinie": np.full(n, np.nan),
        "m_zweites_hoch": np.full(n, np.nan),
        "m_konfidenz": np.full(n, np.nan),
    }
    w_event = np.full(n, np.nan)
    m_event = np.full(n, np.nan)
    w_bruch = np.zeros(n, dtype=bool)
    m_bruch = np.zeros(n, dtype=bool)

    schluss = df["close"].to_numpy(dtype=float)
    zeitstempel = df.index.asi8

    for fund in funde:
        i = fund.verfuegbar_index
        if fund.art == "Doppelboden":
            spalten["w_erkannt"][i] = True
            spalten["w_nackenlinie"][i] = fund.nackenlinie
            spalten["w_zweites_tief"][i] = fund.zweite_spitze
            spalten["w_konfidenz"][i] = fund.konfidenz
            w_event[i] = zeitstempel[fund.event_index]
            # Nackenbruch: erster Schluss ueber der Nackenlinie innerhalb des
            # Gueltigkeitsfensters. Genau eine Flanke je Muster.
            ende = min(i + gueltig_kerzen, n - 1)
            ueber = np.nonzero(schluss[i : ende + 1] > fund.nackenlinie)[0]
            if len(ueber):
                w_bruch[i + int(ueber[0])] = True
        else:
            spalten["m_erkannt"][i] = True
            spalten["m_nackenlinie"][i] = fund.nackenlinie
            spalten["m_zweites_hoch"][i] = fund.zweite_spitze
            spalten["m_konfidenz"][i] = fund.konfidenz
            m_event[i] = zeitstempel[fund.event_index]
            ende = min(i + gueltig_kerzen, n - 1)
            unter = np.nonzero(schluss[i : ende + 1] < fund.nackenlinie)[0]
            if len(unter):
                m_bruch[i + int(unter[0])] = True

    spalten["w_event_ts"] = w_event
    spalten["m_event_ts"] = m_event
    spalten["w_nackenbruch"] = w_bruch
    spalten["m_nackenbruch"] = m_bruch

    return pd.DataFrame(spalten, index=df.index)[list(DOPPELMUSTER_SPALTEN)]


__all__ = [
    "DOPPELMUSTER_SPALTEN",
    "STANDARD_LOOKBACK",
    "STANDARD_MAX_SPITZENABSTAND_ATR",
    "STANDARD_MIN_TALTIEFE_ATR",
    "STANDARD_STRENGTH",
    "Musterfund",
    "doppelmuster_spalten",
    "finde_doppelmuster",
]
