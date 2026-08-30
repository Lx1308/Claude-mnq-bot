"""Niveau-Interaktion als Serie: Test, n-ter Test, Ausbruch, Fehlausbruch,
Ausbruch mit Retest, Range-Bruch, Range-Ablehnung.

Laurins Kerninteresse (Punkt 2 und 4 im Plan): "mehrere aufeinanderfolgende
Tests eines Levels", "Support-/Resistance-Reaktion", "Breakout / Failed
Breakout / Breakout + Retest", "Range Break / Range Rejection".

WAS EIN NIVEAU IST
------------------
Ein Preis, an dem der Kurs schon einmal gedreht hat und der deshalb als Halt
oder Widerstand wirkt. Hier vier Quellen, alle bereits als Serie im
vorbereiteten Rahmen bzw. aus ``swing_serie``:

* Vortageshoch / -tief / -schluss  (``prev_session_high/low/close``)
* Initial-Balance-Grenzen          (``ib_high``/``ib_low``, aus Backtester.prepare)
* das zuletzt bestaetigte Swing-Hoch / -Tief
* Overnight-Extrema, falls im Rahmen

**Kein Orderbuch.** "Liquiditaet" heisst hier: Preisniveau, an dem Stops
vermutet werden - nicht tatsaechliche Order-Tiefe (Plan Abschnitt 2).

WIE EIN TEST GEZAEHLT WIRD
-------------------------
Der Kurs "testet" ein Niveau, wenn die Kerze es beruehrt (``low <= L + tol``
und ``high >= L - tol``), ohne mit dem Schluss klar hindurchzugehen. Der
n-te Test in Folge ist der n-te solcher Beruehrungen, bevor das Niveau
gebrochen oder lange gemieden wird.

KEIN LOOKAHEAD
--------------
Alle Niveauserien stehen zum Bezugszeitpunkt fest (Vortagesmarken:
Sessionende gestern; IB: erste Stunde heute; Swing: ``p + strength``). Ein
Test, ein Bruch, ein Retest werden auf dem Schluss der jeweiligen Kerze
erkannt und sind ab da verfuegbar. Ein Fehlausbruch braucht die
Bestaetigung (Rueckkehr) und ist erst dann verfuegbar - das steht im
jeweiligen ``verfuegbar_idx``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.ereignisse.basis import Ereignis
from common.ereignisse.swings import STANDARD_STRENGTH, swing_serie
from common.indicators import validate_ohlcv

#: Beruehrungstoleranz in ATR. Ein Test "auf den Tick genau" gibt es selten;
#: 0,1 ATR faengt das normale Rauschen um eine Marke ein.
TOLERANZ_ATR = 0.10

#: Ab welchem Schluss-Abstand jenseits des Niveaus ein Bruch gilt.
BRUCH_ATR = 0.10

#: Wie viele Kerzen nach einem Bruch der Retest spaetestens kommen muss,
#: damit er noch als zum Ausbruch gehoerig gilt.
RETEST_FENSTER = 60

#: Wie viele Kerzen nach einem Bruch der Kurs jenseits bleiben muss, damit es
#: KEIN Fehlausbruch war. Kommt er vorher zurueck und schliesst wieder
#: diesseits, ist es ein Fehlausbruch.
FEHLAUSBRUCH_FENSTER = 20


def _niveau_interaktion(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr: np.ndarray,
    niveau: np.ndarray,
    *,
    niveau_name: str,
    detect_timeframe: str,
    toleranz_atr: float,
    bruch_atr: float,
) -> list[Ereignis]:
    """Ein Niveau, ein Vorwaertsdurchlauf. Erzeugt Test-, Ausbruch-,
    Fehlausbruch- und Retest-Ereignisse."""
    n = len(closes)
    ereignisse: list[Ereignis] = []

    tests_in_folge = 0
    letzter_test_idx = -10_000
    # -1 = Kurs stand zuletzt klar unter dem Niveau, +1 = klar darueber, 0 = noch
    # nicht festgelegt. Ein Ausbruch ist nur ein Wechsel der etablierten Seite -
    # ein blosser Abpraller von einem Niveau, an dem der Kurs ohnehin schon
    # anlag, ist keiner.
    etablierte_seite = 0
    gebrochen_bei = -1
    bruch_richtung = 0
    bruch_niveau = np.nan
    retest_gemeldet = False

    for i in range(1, n):
        L = niveau[i]
        a = atr[i]
        if not (np.isfinite(L) and np.isfinite(a) and a > 0):
            continue
        tol = toleranz_atr * a
        puffer = bruch_atr * a
        abstand = closes[i] - L

        # --- laufender Ausbruch: Fehlausbruch oder Retest? ---------------
        if gebrochen_bei >= 0:
            seit = i - gebrochen_bei
            wieder_diesseits = (
                (bruch_richtung == 1 and closes[i] < bruch_niveau - puffer)
                or (bruch_richtung == -1 and closes[i] > bruch_niveau + puffer)
            )
            if wieder_diesseits and seit <= FEHLAUSBRUCH_FENSTER:
                ereignisse.append(
                    Ereignis(
                        pattern_type="fehlausbruch",
                        pattern_variant=niveau_name,
                        detect_timeframe=detect_timeframe,
                        direction=-bruch_richtung,   # Fehlausbruch dreht die Richtung
                        entstehung_idx=gebrochen_bei,
                        bestaetigung_idx=i,
                        verfuegbar_idx=i,
                        merkmale={
                            "level_neckline": round(float(bruch_niveau), 4),
                            "ausbruch_richtung": int(bruch_richtung),
                            "kerzen_jenseits": int(seit),
                        },
                    )
                )
                gebrochen_bei = -1
                retest_gemeldet = False
                etablierte_seite = -bruch_richtung   # zurueck auf die alte Seite
            elif not retest_gemeldet and seit <= RETEST_FENSTER:
                beruehrt = lows[i] <= bruch_niveau + tol and highs[i] >= bruch_niveau - tol
                haelt = (
                    (bruch_richtung == 1 and closes[i] > bruch_niveau)
                    or (bruch_richtung == -1 and closes[i] < bruch_niveau)
                )
                if beruehrt and haelt:
                    ereignisse.append(
                        Ereignis(
                            pattern_type="ausbruch_retest",
                            pattern_variant=niveau_name,
                            detect_timeframe=detect_timeframe,
                            direction=int(bruch_richtung),
                            entstehung_idx=gebrochen_bei,
                            bestaetigung_idx=i,
                            verfuegbar_idx=i,
                            merkmale={
                                "level_neckline": round(float(bruch_niveau), 4),
                                "kerzen_bis_retest": int(seit),
                            },
                        )
                    )
                    retest_gemeldet = True
            elif seit > RETEST_FENSTER:
                gebrochen_bei = -1
                retest_gemeldet = False

        # --- Ausbruch: Wechsel der etablierten Seite ------------------
        if etablierte_seite == -1 and closes[i] > L + puffer:
            ereignisse.append(
                Ereignis(
                    pattern_type="ausbruch",
                    pattern_variant=niveau_name,
                    detect_timeframe=detect_timeframe,
                    direction=1,
                    entstehung_idx=i,
                    bestaetigung_idx=i,
                    verfuegbar_idx=i,
                    merkmale={
                        "level_neckline": round(float(L), 4),
                        "tests_vor_ausbruch": int(tests_in_folge),
                        "bruch_atr": round(float((closes[i] - L) / a), 3),
                    },
                )
            )
            gebrochen_bei, bruch_richtung, bruch_niveau = i, 1, float(L)
            retest_gemeldet = False
            tests_in_folge = 0
            etablierte_seite = 1
        elif etablierte_seite == 1 and closes[i] < L - puffer:
            ereignisse.append(
                Ereignis(
                    pattern_type="ausbruch",
                    pattern_variant=niveau_name,
                    detect_timeframe=detect_timeframe,
                    direction=-1,
                    entstehung_idx=i,
                    bestaetigung_idx=i,
                    verfuegbar_idx=i,
                    merkmale={
                        "level_neckline": round(float(L), 4),
                        "tests_vor_ausbruch": int(tests_in_folge),
                        "bruch_atr": round(float((L - closes[i]) / a), 3),
                    },
                )
            )
            gebrochen_bei, bruch_richtung, bruch_niveau = i, -1, float(L)
            retest_gemeldet = False
            tests_in_folge = 0
            etablierte_seite = -1
        else:
            # --- Test (Beruehrung ohne Bruch) --------------------------
            beruehrt = lows[i] <= L + tol and highs[i] >= L - tol
            durch = abs(abstand) > puffer
            if beruehrt and not durch:
                if i - letzter_test_idx > RETEST_FENSTER:
                    tests_in_folge = 0
                tests_in_folge += 1
                letzter_test_idx = i
                # Richtung der erwarteten Reaktion: zurueck auf die Seite, von
                # der der Kurs ans Niveau herangekommen ist (Support = von oben).
                von_oben = etablierte_seite == 1 or (
                    etablierte_seite == 0 and closes[i - 1] > L
                )
                ereignisse.append(
                    Ereignis(
                        pattern_type="niveau_test",
                        pattern_variant=niveau_name,
                        detect_timeframe=detect_timeframe,
                        direction=1 if von_oben else -1,
                        entstehung_idx=i,
                        bestaetigung_idx=i,
                        verfuegbar_idx=i,
                        merkmale={
                            "level_neckline": round(float(L), 4),
                            "test_nummer": int(tests_in_folge),
                            "als_support": bool(von_oben),
                            "abstand_schluss_atr": round(
                                float(abs(abstand) / a), 3
                            ),
                        },
                    )
                )

        # --- etablierte Seite fortschreiben --------------------------
        # Nur wenn der Kurs klar auf einer Seite steht - sonst bleibt die
        # zuletzt bekannte Seite erhalten (ein Test aendert sie nicht).
        if abs(abstand) > max(tol, puffer):
            etablierte_seite = 1 if abstand > 0 else -1

    return ereignisse


#: (Spaltenname im Rahmen, Kurzname fuers Ereignis)
NIVEAU_QUELLEN: tuple[tuple[str, str], ...] = (
    ("prev_session_high", "pdh"),
    ("prev_session_low", "pdl"),
    ("prev_session_close", "pdc"),
    ("ib_high", "ib_high"),
    ("ib_low", "ib_low"),
    ("overnight_high", "onh"),
    ("overnight_low", "onl"),
)


def niveau_ereignisse(
    df: pd.DataFrame,
    *,
    detect_timeframe: str = "1m",
    strength: int = STANDARD_STRENGTH,
    toleranz_atr: float = TOLERANZ_ATR,
    bruch_atr: float = BRUCH_ATR,
) -> list[Ereignis]:
    """Alle Niveau-Interaktionen ueber alle verfuegbaren Niveauquellen.

    Erwartet einen mit ``compute_indicators`` und
    ``initial_balance_per_session`` vorbereiteten Rahmen (also den Output von
    ``Backtester.prepare``).
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError("niveau_ereignisse braucht die atr-Spalte.")

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)

    ereignisse: list[Ereignis] = []

    for spalte, name in NIVEAU_QUELLEN:
        if spalte not in df.columns:
            continue
        niveau = df[spalte].to_numpy(dtype=float)
        if not np.isfinite(niveau).any():
            continue
        ereignisse.extend(
            _niveau_interaktion(
                highs, lows, closes, atr, niveau,
                niveau_name=name, detect_timeframe=detect_timeframe,
                toleranz_atr=toleranz_atr, bruch_atr=bruch_atr,
            )
        )

    # Zuletzt bestaetigte Swings als Niveau.
    serie = swing_serie(df, strength=strength)
    for kind, name in (("hoch", "swing_hoch"), ("tief", "swing_tief")):
        preis, _ = serie.letzte_swings(kind)
        ereignisse.extend(
            _niveau_interaktion(
                highs, lows, closes, atr, preis,
                niveau_name=name, detect_timeframe=detect_timeframe,
                toleranz_atr=toleranz_atr, bruch_atr=bruch_atr,
            )
        )

    ereignisse.sort(key=lambda e: e.verfuegbar_idx)
    return ereignisse


__all__ = [
    "BRUCH_ATR",
    "FEHLAUSBRUCH_FENSTER",
    "NIVEAU_QUELLEN",
    "RETEST_FENSTER",
    "TOLERANZ_ATR",
    "niveau_ereignisse",
]
