"""Die vier Setup-Erkenner der Ideen-Protokollierung.

ALLE ERKENNER SIND FLANKENERKENNUNGEN.
--------------------------------------
Sie vergleichen die gerade geschlossene Kerze mit ihrer Vorgaengerin und
melden den **Uebergang**, nicht den Zustand. Ohne das wuerde ein einmal
gebrochenes Vortageshoch stundenlang bei jeder Kerze erneut als Idee
auftauchen und die spaetere Statistik mit Dutzenden Kopien derselben
Bewegung verwaessern.

Dasselbe Prinzip verwendet bereits ``live_bot/alerts/conditions.py``.

KEIN LOOKAHEAD
--------------
Jeder Erkenner sieht ausschliesslich die Zeilen ``i`` und ``i-1``. Es gibt
keinen Zugriff auf spaetere Kerzen, und Einstieg, Stop und Ziel werden
ausschliesslich aus Werten dieser beiden Zeilen gebildet.

Der Einstieg ist der **Schlusskurs** der Signalkerze. Das ist bewusst eine
Referenz und keine Fill-Annahme: die Auswertung in Etappe D setzt den
tatsaechlichen Einstieg auf die Eroeffnung der Folgekerze, genauso wie es
die Backtest-Engine tut.

ABSTAENDE IN ATR, NICHT IN PUNKTEN
----------------------------------
Alle Schwellen und Abstaende sind ATR-Vielfache. 20 Punkte sind bei MNQ ein
Nichts und bei MGC eine Weltreise - ein fester Punktwert waere zwischen
Instrumenten nicht uebertragbar.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from common.config import IdeenSetupConfig
from ideas.model import (
    RICHTUNG_LONG,
    RICHTUNG_SHORT,
    SETUP_FLAGGE_HOCH,
    SETUP_FLAGGE_TIEF,
    SETUP_IB_BRUCH_HOCH,
    SETUP_IB_BRUCH_TIEF,
    SETUP_PDH_BRUCH,
    SETUP_PDL_BRUCH,
    SETUP_VWAP_REVERSION,
)

# Spalten, die ein vorbereitetes DataFrame tragen muss.
BENOETIGTE_SPALTEN: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "atr",
    "vwap",
    "prev_session_high",
    "prev_session_low",
    "ib_high",
    "ib_low",
    "flag_breakout_up",
    "flag_breakout_down",
    "flag_range_high",
    "flag_range_low",
)


@dataclass(frozen=True)
class Rohidee:
    """Erkanntes Setup mit Marken - noch ohne CRV, Filter und Profil."""

    setup: str
    richtung: str
    entry: float
    stop: float
    ziel: float
    begruendung: dict[str, Any] = field(default_factory=dict)


class FehlendeSpalte(KeyError):
    """Das DataFrame ist nicht vorbereitet worden."""


def pruefe_spalten(df: pd.DataFrame) -> None:
    """Wirft, wenn eine benoetigte Spalte fehlt.

    Absichtlich laut: fehlt etwa ``ib_high``, wuerde der IB-Erkenner sonst
    einfach nie ausloesen - ohne Fehlermeldung. Genau diese Klasse stiller
    Ausfaelle hat das Projekt schon einmal Wochen gekostet.
    """
    fehlend = [name for name in BENOETIGTE_SPALTEN if name not in df.columns]
    if fehlend:
        raise FehlendeSpalte(
            "Dem DataFrame fehlen Spalten fuer die Ideen-Erkennung: "
            + ", ".join(fehlend)
            + ". Wurde ideas.pipeline.vorbereiten() aufgerufen?"
        )


def _zahl(wert: Any) -> float | None:
    """float oder None - NaN und nicht-numerische Werte werden zu None."""
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(zahl) or math.isinf(zahl) else zahl


def _wahr(wert: Any) -> bool:
    """Robuste Wahrheitspruefung fuer moeglicherweise fehlende Flags."""
    return bool(wert) and wert == wert  # NaN ist ungleich sich selbst


# ---------------------------------------------------------------------------
#  1 + 2  Bruch einer horizontalen Marke (Vortageshoch/-tief, IB-Hoch/-Tief)
# ---------------------------------------------------------------------------

def _markenbruch(
    vorher: pd.Series,
    jetzt: pd.Series,
    *,
    spalte: str,
    setup: str,
    nach_oben: bool,
    cfg: IdeenSetupConfig,
) -> Rohidee | None:
    """Gemeinsame Mechanik fuer Vortages- und Initial-Balance-Bruch.

    Beide Setups sind dieselbe Bewegung an einer anderen Marke. Sie zweimal
    auszuprogrammieren hiesse, sie spaeter zweimal korrigieren zu muessen.
    """
    atr = _zahl(jetzt.get("atr"))
    marke = _zahl(jetzt.get(spalte))
    schluss = _zahl(jetzt.get("close"))
    schluss_vorher = _zahl(vorher.get("close"))
    marke_vorher = _zahl(vorher.get(spalte))

    if None in (atr, marke, schluss, schluss_vorher, marke_vorher) or atr <= 0:
        return None

    puffer = cfg.bruch_puffer_atr * atr
    schwelle = marke + puffer if nach_oben else marke - puffer
    schwelle_vorher = marke_vorher + puffer if nach_oben else marke_vorher - puffer

    # Flanke: vorher nicht jenseits der Schwelle, jetzt schon.
    if nach_oben:
        flanke = schluss_vorher <= schwelle_vorher and schluss > schwelle
    else:
        flanke = schluss_vorher >= schwelle_vorher and schluss < schwelle
    if not flanke:
        return None

    if nach_oben:
        stop = marke - cfg.bruch_stop_atr * atr
        ziel = schluss + cfg.bruch_ziel_atr * atr
        richtung = RICHTUNG_LONG
    else:
        stop = marke + cfg.bruch_stop_atr * atr
        ziel = schluss - cfg.bruch_ziel_atr * atr
        richtung = RICHTUNG_SHORT

    return Rohidee(
        setup=setup,
        richtung=richtung,
        entry=schluss,
        stop=stop,
        ziel=ziel,
        begruendung={
            "marke": round(marke, 4),
            "marke_spalte": spalte,
            "puffer_atr": cfg.bruch_puffer_atr,
            "schwelle": round(schwelle, 4),
            "atr": round(atr, 4),
        },
    )


def erkenne_vortagesbruch(
    vorher: pd.Series, jetzt: pd.Series, cfg: IdeenSetupConfig
) -> list[Rohidee]:
    """Schlusskurs bricht Vortageshoch nach oben bzw. Vortagestief nach unten."""
    treffer: list[Rohidee] = []
    hoch = _markenbruch(
        vorher, jetzt, spalte="prev_session_high",
        setup=SETUP_PDH_BRUCH, nach_oben=True, cfg=cfg,
    )
    if hoch:
        treffer.append(hoch)
    tief = _markenbruch(
        vorher, jetzt, spalte="prev_session_low",
        setup=SETUP_PDL_BRUCH, nach_oben=False, cfg=cfg,
    )
    if tief:
        treffer.append(tief)
    return treffer


def erkenne_ib_bruch(
    vorher: pd.Series, jetzt: pd.Series, cfg: IdeenSetupConfig
) -> list[Rohidee]:
    """Bruch der Initial Balance.

    ``ib_high``/``ib_low`` sind waehrend der ersten RTH-Stunde NaN - siehe
    ``common.levels.initial_balance_per_session``. Damit kann dieses Setup
    konstruktionsbedingt nicht ausloesen, bevor die Initial Balance
    ueberhaupt feststeht.
    """
    treffer: list[Rohidee] = []
    hoch = _markenbruch(
        vorher, jetzt, spalte="ib_high",
        setup=SETUP_IB_BRUCH_HOCH, nach_oben=True, cfg=cfg,
    )
    if hoch:
        treffer.append(hoch)
    tief = _markenbruch(
        vorher, jetzt, spalte="ib_low",
        setup=SETUP_IB_BRUCH_TIEF, nach_oben=False, cfg=cfg,
    )
    if tief:
        treffer.append(tief)
    return treffer


# ---------------------------------------------------------------------------
#  3  VWAP-Reversion
# ---------------------------------------------------------------------------

def erkenne_vwap_reversion(
    vorher: pd.Series, jetzt: pd.Series, cfg: IdeenSetupConfig
) -> list[Rohidee]:
    """Kurs war weit vom VWAP entfernt und dreht zurueck.

    Bedingung in zwei Teilen:
    1. Die **vorherige** Kerze lag mindestens ``vwap_abweichung_atr`` ATR
       vom VWAP entfernt.
    2. Die aktuelle Kerze schliesst wieder in Richtung VWAP.

    Ziel ist der VWAP selbst - nicht ein ATR-Vielfaches. Bei einer
    Rueckkehrbewegung ist der Anker die Referenz, zu der zurueckgekehrt
    wird; ein fester ATR-Abstand haette damit nichts zu tun.

    Der Stop liegt hinter dem Extrem der Abweichung, damit er nicht
    ausgerechnet dort sitzt, wo die Bewegung noch einmal hinlaeuft.
    """
    atr = _zahl(jetzt.get("atr"))
    vwap = _zahl(jetzt.get("vwap"))
    schluss = _zahl(jetzt.get("close"))
    schluss_vorher = _zahl(vorher.get("close"))
    vwap_vorher = _zahl(vorher.get("vwap"))

    if None in (atr, vwap, schluss, schluss_vorher, vwap_vorher) or atr <= 0:
        return []

    abweichung_vorher = (schluss_vorher - vwap_vorher) / atr
    if abs(abweichung_vorher) < cfg.vwap_abweichung_atr:
        return []

    # Nur solange der Kurs den VWAP noch nicht erreicht hat - sonst waere
    # die Rueckkehr bereits gelaufen und es gaebe nichts mehr zu holen.
    if abweichung_vorher < 0:
        dreht_zurueck = schluss > schluss_vorher and schluss < vwap
        richtung = RICHTUNG_LONG
        tief = _zahl(vorher.get("low")) or schluss_vorher
        stop = tief - cfg.vwap_stop_atr * atr
    else:
        dreht_zurueck = schluss < schluss_vorher and schluss > vwap
        richtung = RICHTUNG_SHORT
        hoch = _zahl(vorher.get("high")) or schluss_vorher
        stop = hoch + cfg.vwap_stop_atr * atr

    if not dreht_zurueck:
        return []

    return [
        Rohidee(
            setup=SETUP_VWAP_REVERSION,
            richtung=richtung,
            entry=schluss,
            stop=stop,
            ziel=vwap,
            begruendung={
                "abweichung_atr_vorher": round(abweichung_vorher, 2),
                "vwap": round(vwap, 4),
                "atr": round(atr, 4),
            },
        )
    ]


# ---------------------------------------------------------------------------
#  4  Flaggen-Ausbruch
# ---------------------------------------------------------------------------

def erkenne_flaggen_ausbruch(
    vorher: pd.Series, jetzt: pd.Series, cfg: IdeenSetupConfig
) -> list[Rohidee]:
    """Ausbruch aus der Konsolidierung nach einem Impuls.

    Nutzt die vorhandenen Spalten aus ``common.indicators.flag_signals`` -
    es wird ausdruecklich keine zweite Flaggen-Heuristik eingefuehrt.

    Die Flanke ist noetig, obwohl ``flag_breakout_up`` bereits eine
    Ausbruchsbedingung ist: sie bleibt wahr, solange der Kurs oberhalb der
    Range schliesst.
    """
    atr = _zahl(jetzt.get("atr"))
    schluss = _zahl(jetzt.get("close"))
    if atr is None or schluss is None or atr <= 0:
        return []

    puffer = cfg.flagge_stop_puffer_atr * atr

    if _wahr(jetzt.get("flag_breakout_up")) and not _wahr(vorher.get("flag_breakout_up")):
        range_tief = _zahl(jetzt.get("flag_range_low"))
        if range_tief is None:
            return []
        return [
            Rohidee(
                setup=SETUP_FLAGGE_HOCH,
                richtung=RICHTUNG_LONG,
                entry=schluss,
                stop=range_tief - puffer,
                ziel=schluss + cfg.flagge_ziel_atr * atr,
                begruendung={
                    "range_hoch": _zahl(jetzt.get("flag_range_high")),
                    "range_tief": round(range_tief, 4),
                    "atr": round(atr, 4),
                },
            )
        ]

    if _wahr(jetzt.get("flag_breakout_down")) and not _wahr(vorher.get("flag_breakout_down")):
        range_hoch = _zahl(jetzt.get("flag_range_high"))
        if range_hoch is None:
            return []
        return [
            Rohidee(
                setup=SETUP_FLAGGE_TIEF,
                richtung=RICHTUNG_SHORT,
                entry=schluss,
                stop=range_hoch + puffer,
                ziel=schluss - cfg.flagge_ziel_atr * atr,
                begruendung={
                    "range_hoch": round(range_hoch, 4),
                    "range_tief": _zahl(jetzt.get("flag_range_low")),
                    "atr": round(atr, 4),
                },
            )
        ]

    return []


# ---------------------------------------------------------------------------
#  Alle Erkenner auf einer Kerze
# ---------------------------------------------------------------------------

ERKENNER = (
    erkenne_vortagesbruch,
    erkenne_ib_bruch,
    erkenne_vwap_reversion,
    erkenne_flaggen_ausbruch,
)


def erkenne_auf_kerze(
    vorher: pd.Series, jetzt: pd.Series, cfg: IdeenSetupConfig
) -> list[Rohidee]:
    """Alle Setups auf einer einzelnen Flanke pruefen."""
    treffer: list[Rohidee] = []
    for erkenner in ERKENNER:
        treffer.extend(erkenner(vorher, jetzt, cfg))
    return treffer


__all__ = [
    "BENOETIGTE_SPALTEN",
    "ERKENNER",
    "FehlendeSpalte",
    "Rohidee",
    "erkenne_auf_kerze",
    "erkenne_flaggen_ausbruch",
    "erkenne_ib_bruch",
    "erkenne_vortagesbruch",
    "erkenne_vwap_reversion",
    "pruefe_spalten",
]
