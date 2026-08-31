"""Was nach einem Ereignis passiert - MFE, MAE, Endergebnis je Horizont.

Etappe 4 aus ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``. Das ist der Schritt,
nach dem sich zum ersten Mal Saetze bilden lassen wie "nach dem zweiten Test
des Vortagestiefs lief der Kurs in X % der Faelle mindestens 1 ATR nach
oben".

WARUM NICHT ``backtest/excursions.py``
-------------------------------------
``compute_path_excursions`` rechnet je Einstieg eine Python-Schleife ueber
den Horizont: O(Ereignisse x Horizont). Bei 2,59 Mio Ereignissen und
Horizonten bis 240 Kerzen waeren das Milliarden Iterationen.

Hier dieselbe Definition, aber ueber **rollende Fenster auf der ganzen
Kursreihe**: einmal je Horizont gerechnet, danach ist alles Nachschlagen. Ein
Test in ``tests/test_ereignisse_outcomes.py`` vergleicht beide Fassungen Zeile
fuer Zeile.

**Ein Unterschied ist Absicht.** ``compute_path_excursions`` setzt bei
fehlendem ATR ersatzweise ``5.0`` ein. Das ist eine erfundene Zahl, die
aussieht wie eine Messung - fuer eine Anzeige verzeihlich, fuer eine
Wissensbasis nicht (Invariante 11). Hier bleiben die R-Werte ``NaN``, wenn
kein ATR vorliegt.

DAS AUSFUEHRUNGSMODELL
----------------------
* Ein Ereignis ist bei ``verfuegbar_idx`` bekannt.
* Gehandelt wird zur **Eroeffnung der Folgekerze** (``open[v+1]``) - wie in
  der Backtest-Engine (Invariante 4) und wie Plan Abschnitt 10 Punkt 4 es
  verlangt. Der Schlusskurs bei ``v`` ist nicht handelbar.
* Das Outcome-Fenster beginnt bei ``v+1`` und umfasst ``H`` Kerzen.
* Reicht das Fenster ueber das Ende der Reihe, wird das Ereignis fuer diesen
  Horizont **verworfen**, nicht gekuerzt (Plan Abschnitt 10). Ein gekuerztes
  Fenster sieht aus wie ein vollstaendiges und verzerrt die Statistik zum
  Reihenende hin.

VORZEICHEN
----------
Alles aus Sicht der **gedeuteten Richtung** des Ereignisses:

* ``mfe`` (Maximum Favourable Excursion) - wie weit lief es zugunsten
* ``mae`` (Maximum Adverse Excursion) - wie weit dagegen

Beide sind **nicht negativ**. Bei einem Long ist MFE ``max(high) - entry``,
bei einem Short ``entry - min(low)``.

INTRABAR-AMBIGUITAET
--------------------
Aus OHLC ist nicht rekonstruierbar, ob innerhalb einer Kerze erst das Hoch
oder erst das Tief kam. Fuer MFE und MAE getrennt spielt das keine Rolle -
beide sind Extremwerte ueber das Fenster. Es spielt eine Rolle, sobald ein
Ziel **und** ein Stop im Spiel sind; das ist Etappe 7. ``outcomes`` liefert
die Rohzahlen, aus denen sich das dort entscheiden laesst.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv

#: Die Horizonte aus dem Plan (Abschnitt 5), in Kerzen.
#: 120 = 2 h, 240 = 4 h auf 1-Minuten-Basis.
HORIZONTE: tuple[int, ...] = (1, 3, 5, 10, 20, 30, 60, 120, 240)

#: Wie viele Kerzen je Block verarbeitet werden, wenn Zeit-bis-MFE gebraucht
#: wird. Der gleitende Fensterblick braucht ``block x horizont`` Zellen; bei
#: 200.000 x 240 sind das rund 380 MB - passt, und groessere Bloecke bringen
#: nichts mehr.
BLOCK = 200_000


@dataclass(frozen=True)
class Vorwaertsfenster:
    """Rollende Extrema ueber ``horizont`` Kerzen ab jeder Position.

    Alle Arrays haben die Laenge der Kursreihe. ``hoch[i]`` ist das hoechste
    Hoch der Kerzen ``i .. i+horizont-1``; ``NaN``, wenn das Fenster ueber das
    Reihenende hinausreicht.

    ``bis_hoch[i]`` ist die Zahl der Kerzen bis zu diesem Hoch, 1-basiert
    (1 = gleich in der ersten Kerze des Fensters) - wie
    ``PathExcursion.time_to_mfe_bars``.
    """

    horizont: int
    hoch: np.ndarray
    tief: np.ndarray
    schluss: np.ndarray          # Schlusskurs der LETZTEN Kerze des Fensters
    bis_hoch: np.ndarray         # int, -1 wo das Fenster unvollstaendig ist
    bis_tief: np.ndarray


def vorwaertsfenster(
    df: pd.DataFrame, horizont: int, *, mit_zeiten: bool = True
) -> Vorwaertsfenster:
    """Rollende Vorwaerts-Extrema fuer einen Horizont, ueber die ganze Reihe.

    ``mit_zeiten=False`` laesst die Zeit-bis-Extremum weg - das ist der teure
    Teil und wird nicht immer gebraucht.
    """
    if horizont < 1:
        raise ValueError(f"Horizont muss mindestens 1 sein, ist {horizont}.")

    hoch_roh = df["high"].to_numpy(dtype=float)
    tief_roh = df["low"].to_numpy(dtype=float)
    schluss_roh = df["close"].to_numpy(dtype=float)
    n = len(df)

    leer = np.full(n, np.nan)
    if n < horizont:
        return Vorwaertsfenster(
            horizont, leer, leer.copy(), leer.copy(),
            np.full(n, -1, dtype=np.int32), np.full(n, -1, dtype=np.int32),
        )

    # max(high[i : i+H]) - rollendes Maximum, um H-1 nach vorn geschoben.
    reihe_h = pd.Series(hoch_roh)
    reihe_t = pd.Series(tief_roh)
    hoch = reihe_h.rolling(horizont).max().shift(-(horizont - 1)).to_numpy()
    tief = reihe_t.rolling(horizont).min().shift(-(horizont - 1)).to_numpy()

    # Schluss der letzten Kerze des Fensters.
    schluss = np.full(n, np.nan)
    schluss[: n - horizont + 1] = schluss_roh[horizont - 1 :]

    bis_hoch = np.full(n, -1, dtype=np.int32)
    bis_tief = np.full(n, -1, dtype=np.int32)
    if mit_zeiten:
        gueltig = n - horizont + 1
        for start in range(0, gueltig, BLOCK):
            ende = min(start + BLOCK, gueltig)
            # Fensteransicht ohne zu kopieren; argmax/argmin liefern die
            # Position des ERSTEN Extremums - wie die Schleife in
            # compute_path_excursions, die nur bei echtem ">" nachfuehrt.
            fenster_h = np.lib.stride_tricks.sliding_window_view(
                hoch_roh[start : ende + horizont - 1], horizont
            )
            fenster_t = np.lib.stride_tricks.sliding_window_view(
                tief_roh[start : ende + horizont - 1], horizont
            )
            bis_hoch[start:ende] = fenster_h.argmax(axis=1) + 1
            bis_tief[start:ende] = fenster_t.argmin(axis=1) + 1

    return Vorwaertsfenster(horizont, hoch, tief, schluss, bis_hoch, bis_tief)


@dataclass(frozen=True)
class Outcomes:
    """Ergebnis je Ereignis fuer **einen** Horizont.

    Alle Arrays haben die Laenge der uebergebenen Ereignisliste. Wo das
    Fenster nicht vollstaendig in die Reihe passt, steht ``NaN`` bzw. ``False``
    in ``gueltig`` - solche Zeilen gehoeren nicht in eine Auswertung.
    """

    horizont: int
    gueltig: np.ndarray          # bool
    entry_preis: np.ndarray
    atr_referenz: np.ndarray
    mfe_pkt: np.ndarray
    mae_pkt: np.ndarray
    end_pkt: np.ndarray
    mfe_r: np.ndarray
    mae_r: np.ndarray
    end_r: np.ndarray
    end_prozent: np.ndarray
    zeit_bis_mfe: np.ndarray     # int, -1 wo ungueltig
    zeit_bis_mae: np.ndarray

    def __len__(self) -> int:
        return len(self.gueltig)


def berechne_outcomes(
    df: pd.DataFrame,
    verfuegbar_idx: np.ndarray,
    richtung: np.ndarray,
    horizont: int,
    *,
    fenster: Vorwaertsfenster | None = None,
    atr_spalte: str = "atr",
) -> Outcomes:
    """MFE, MAE und Endergebnis je Ereignis fuer einen Horizont.

    ``verfuegbar_idx`` und ``richtung`` (+1/-1) sind gleich lange Arrays.
    Gehandelt wird zur Eroeffnung von ``verfuegbar_idx + 1``.

    ``fenster`` kann vorberechnet uebergeben werden - ueber viele Ereignisse
    hinweg lohnt sich das immer, weil die rollenden Extrema nicht von den
    Ereignissen abhaengen.
    """
    validate_ohlcv(df)
    verfuegbar_idx = np.asarray(verfuegbar_idx, dtype=np.int64)
    richtung = np.asarray(richtung, dtype=np.int64)
    if len(verfuegbar_idx) != len(richtung):
        raise ValueError(
            "verfuegbar_idx und richtung muessen gleich lang sein "
            f"({len(verfuegbar_idx)} vs. {len(richtung)})."
        )
    if not np.isin(richtung, (-1, 1)).all():
        raise ValueError("richtung darf nur +1 oder -1 enthalten.")

    if fenster is None:
        fenster = vorwaertsfenster(df, horizont)
    elif fenster.horizont != horizont:
        raise ValueError(
            f"Vorberechnetes Fenster ist fuer Horizont {fenster.horizont}, "
            f"verlangt ist {horizont}."
        )

    n = len(df)
    m = len(verfuegbar_idx)
    opens = df["open"].to_numpy(dtype=float)
    atr = (
        df[atr_spalte].to_numpy(dtype=float)
        if atr_spalte in df.columns
        else np.full(n, np.nan)
    )

    einstieg_idx = verfuegbar_idx + 1
    # Gueltig ist ein Ereignis nur, wenn Einstieg UND volles Fenster in die
    # Reihe passen. Kuerzen waere schlimmer als verwerfen: ein gekuerztes
    # Fenster sieht aus wie ein vollstaendiges.
    gueltig = (einstieg_idx >= 0) & (einstieg_idx + horizont <= n)

    leer = np.full(m, np.nan)
    ergebnis = {
        name: leer.copy()
        for name in (
            "entry_preis", "atr_referenz", "mfe_pkt", "mae_pkt", "end_pkt",
            "mfe_r", "mae_r", "end_r", "end_prozent",
        )
    }
    zeit_mfe = np.full(m, -1, dtype=np.int32)
    zeit_mae = np.full(m, -1, dtype=np.int32)

    if not gueltig.any():
        return Outcomes(horizont, gueltig, **ergebnis,
                        zeit_bis_mfe=zeit_mfe, zeit_bis_mae=zeit_mae)

    g = np.nonzero(gueltig)[0]
    e = einstieg_idx[g]
    r = richtung[g]

    entry = opens[e]
    # Der ATR-Bezug steht auf der Ereigniskerze, nicht auf der Einstiegskerze:
    # er ist das, was zum Entscheidungszeitpunkt bekannt war.
    a = atr[verfuegbar_idx[g]]

    hoch = fenster.hoch[e]
    tief = fenster.tief[e]
    schluss = fenster.schluss[e]

    long = r == 1
    mfe = np.where(long, hoch - entry, entry - tief)
    mae = np.where(long, entry - tief, hoch - entry)
    end = np.where(long, schluss - entry, entry - schluss)

    # MFE und MAE sind Exkursionen, keine Vorzeichen: eine Kerze, die nie
    # ueber den Einstieg lief, hat MFE 0, nicht "minus drei".
    mfe = np.maximum(mfe, 0.0)
    mae = np.maximum(mae, 0.0)

    ergebnis["entry_preis"][g] = entry
    ergebnis["atr_referenz"][g] = a
    ergebnis["mfe_pkt"][g] = mfe
    ergebnis["mae_pkt"][g] = mae
    ergebnis["end_pkt"][g] = end

    # R nur, wo ein ATR vorliegt. KEIN Ersatzwert - eine erfundene Zahl, die
    # aussieht wie eine Messung, ist in diesem Projekt der schwerste Fehler.
    mit_atr = np.isfinite(a) & (a > 0)
    idx_r = g[mit_atr]
    ergebnis["mfe_r"][idx_r] = mfe[mit_atr] / a[mit_atr]
    ergebnis["mae_r"][idx_r] = mae[mit_atr] / a[mit_atr]
    ergebnis["end_r"][idx_r] = end[mit_atr] / a[mit_atr]

    # Prozent, weil MNQ von 7.500 auf 29.500 gelaufen ist und Punkte ueber die
    # Historie nicht vergleichbar sind (Plan Abschnitt 5).
    mit_preis = np.isfinite(entry) & (entry != 0)
    ergebnis["end_prozent"][g[mit_preis]] = (
        end[mit_preis] / entry[mit_preis] * 100.0
    )

    # Zeit bis zur guenstigen bzw. unguenstigen Exkursion - je nach Richtung
    # ist das Hoch oder das Tief das guenstige Extrem.
    bis_hoch = fenster.bis_hoch[e]
    bis_tief = fenster.bis_tief[e]
    zeit_mfe[g] = np.where(long, bis_hoch, bis_tief)
    zeit_mae[g] = np.where(long, bis_tief, bis_hoch)

    return Outcomes(horizont, gueltig, **ergebnis,
                    zeit_bis_mfe=zeit_mfe, zeit_bis_mae=zeit_mae)


def alle_horizonte(
    df: pd.DataFrame,
    verfuegbar_idx: np.ndarray,
    richtung: np.ndarray,
    *,
    horizonte: tuple[int, ...] = HORIZONTE,
    mit_zeiten: bool = True,
) -> dict[int, Outcomes]:
    """``berechne_outcomes`` fuer alle Horizonte, mit gemeinsamer Vorarbeit.

    Die rollenden Extrema haengen nicht von den Ereignissen ab und werden je
    Horizont **einmal** gerechnet - das ist der ganze Geschwindigkeitsgewinn
    gegenueber einer Schleife je Ereignis.
    """
    ergebnis: dict[int, Outcomes] = {}
    for h in horizonte:
        f = vorwaertsfenster(df, h, mit_zeiten=mit_zeiten)
        ergebnis[h] = berechne_outcomes(
            df, verfuegbar_idx, richtung, h, fenster=f
        )
    return ergebnis


__all__ = [
    "BLOCK",
    "HORIZONTE",
    "Outcomes",
    "Vorwaertsfenster",
    "alle_horizonte",
    "berechne_outcomes",
    "vorwaertsfenster",
]
