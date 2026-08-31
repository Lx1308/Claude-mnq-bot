"""Grundraten: was folgt auf ein Muster - und was folgt ohne es?

Etappe 8 aus ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``. Hier entsteht die
Tabelle, um die es Laurin von Anfang an ging: fuer jedes Muster eine Zahl,
wie oft es wie weiterlief - **und immer gegen die bedingungslose Nulllinie**.

DIE VIER FALLEN, DIE HIER UMGANGEN WERDEN
-----------------------------------------
1. **Keine Nulllinie.** "In 62 % der Faelle ging es hoch" ist wertlos, wenn
   es ohne das Muster in 61 % der Faelle hochgeht. Jede Zahl steht neben der
   Grundrate aller Kerzen.

2. **Ueberschneidung.** Zwei Ereignisse 5 Kerzen auseinander teilen sich bei
   Horizont 60 fast das ganze Fenster. Als unabhaengige Beobachtungen
   gezaehlt, blaeht das die Signifikanz um rund ``sqrt(horizont)`` auf. Die
   ueberschneidungsfreie Stichprobe wird getrennt ausgewiesen und ist die
   **massgebliche**.

3. **Klumpen.** Um 15:35 koennen sieben Erkenner dasselbe melden. Ueber
   ``cluster_id`` zaehlt ein Klumpen als **eine** Beobachtung (Plan 12.1).

4. **Auswahl.** Wer aus 100 gemessenen Mustern das beste herausgreift, hat
   eine Auswahl getroffen - ab da gilt die Mehrfachtestkorrektur gegen die
   Gesamtzahl. Deshalb gibt dieses Modul **alle** Zeilen aus, auch die
   uninteressanten, und nennt die Zahl der Vergleiche.

WAS HIER NICHT PASSIERT
-----------------------
Keine Kosten, keine Slippage, keine Stops. Das sind Rohverlaeufe. Ein
positives ``E[R]`` von 0,02 ist bei einer Friktion von rund 1,45 Punkten
kein Handelssignal, sondern Rauschen - die Kostenrechnung kommt in der
Strategieauswertung dazu, mit benanntem Kostenprofil (Invariante 10).
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backtest.research import p_wert_zweiseitig


def wilson_intervall(
    treffer: int, gesamt: int, *, z: float = 1.96
) -> tuple[float, float]:
    """Konfidenzintervall fuer einen Anteil nach Wilson.

    Fuer Anteile korrekter als die Normalapproximation: die faellt bei
    kleinen ``n`` oder Anteilen nahe 0 bzw. 1 aus dem Intervall ``[0, 1]``
    heraus und behauptet dann Unsinn mit Nachkommastellen.
    """
    if gesamt <= 0:
        return (float("nan"), float("nan"))
    p = treffer / gesamt
    nenner = 1.0 + z * z / gesamt
    mitte = (p + z * z / (2 * gesamt)) / nenner
    spanne = (
        z * math.sqrt(p * (1 - p) / gesamt + z * z / (4 * gesamt * gesamt))
    ) / nenner
    return (max(0.0, mitte - spanne), min(1.0, mitte + spanne))


def ueberschneidungsfrei(
    indizes: np.ndarray, horizont: int
) -> np.ndarray:
    """Auswahl von Ereignissen, deren Fenster sich nicht ueberschneiden.

    Gieriger Durchlauf von vorn: das erste Ereignis wird genommen, danach
    das naechste, dessen Fenster vollstaendig hinter dem vorigen beginnt.

    Warum das noetig ist: Vorwaertsrenditen aus Kerze ``i`` und ``i+1``
    teilen sich ``horizont - 1`` Kerzen. Die t-Statistik unterstellt aber
    Unabhaengigkeit und wird dadurch um rund ``sqrt(horizont)`` zu gross -
    empirisch gemessen am 30.08.2026: t = 8,49 ueberschneidend gegen t = 1,71
    ueberschneidungsfrei, Faktor 4,98 bei Horizont 24.
    """
    if len(indizes) == 0:
        return np.zeros(0, dtype=bool)
    ordnung = np.argsort(indizes, kind="stable")
    behalten = np.zeros(len(indizes), dtype=bool)
    letzter = -(10**18)
    for pos in ordnung:
        idx = int(indizes[pos])
        if idx - letzter >= horizont:
            behalten[pos] = True
            letzter = idx
    return behalten


@dataclass(frozen=True)
class Grundrate:
    """Ein Muster, ein Horizont, eine Kennzahl - mit ihrer Nulllinie."""

    name: str
    horizont: int
    n: int
    n_unabhaengig: int
    n_cluster: int

    mittel_r: float
    median_r: float
    streuung_r: float
    anteil_positiv: float
    anteil_positiv_ki: tuple[float, float]

    mfe_r_median: float
    mae_r_median: float
    mae_r_p90: float

    basis_mittel_r: float
    basis_anteil_positiv: float

    t_statistik: float
    p_wert: float
    t_ueberschneidend: float
    p_ueberschneidend: float

    hinweis: str = ""

    @property
    def kante_r(self) -> float:
        """Ueberschuss gegenueber der bedingungslosen Nulllinie."""
        return self.mittel_r - self.basis_mittel_r

    def to_dict(self) -> dict:
        return {
            "muster": self.name,
            "horizont": self.horizont,
            "n": self.n,
            "n_unabhaengig": self.n_unabhaengig,
            "n_cluster": self.n_cluster,
            "E[R]": round(self.mittel_r, 4),
            "median_R": round(self.median_r, 4),
            "anteil_positiv": round(self.anteil_positiv, 4),
            "anteil_positiv_ki": (
                round(self.anteil_positiv_ki[0], 4),
                round(self.anteil_positiv_ki[1], 4),
            ),
            "mae_R_median": round(self.mae_r_median, 3),
            "mae_R_p90": round(self.mae_r_p90, 3),
            "mfe_R_median": round(self.mfe_r_median, 3),
            "basis_E[R]": round(self.basis_mittel_r, 4),
            "basis_anteil_positiv": round(self.basis_anteil_positiv, 4),
            "kante_R": round(self.kante_r, 4),
            "t": round(self.t_statistik, 3),
            "p": round(self.p_wert, 5),
            "t_ueberschneidend": round(self.t_ueberschneidend, 3),
            "p_ueberschneidend": round(self.p_ueberschneidend, 5),
            "hinweis": self.hinweis,
        }


#: Unter dieser Stichprobengroesse wird gar nichts ausgewiesen (Plan 12).
MIN_N = 30

#: Darunter mit ausdruecklichem Vorbehalt.
BELASTBAR_AB = 200


def _t_und_p(werte: np.ndarray, nullwert: float) -> tuple[float, float]:
    """Einstichproben-t-Test gegen die Nulllinie."""
    n = len(werte)
    if n < 2:
        return (0.0, 1.0)
    streuung = float(np.std(werte, ddof=1))
    if streuung <= 0:
        return (0.0, 1.0)
    t = (float(np.mean(werte)) - nullwert) / (streuung / math.sqrt(n))
    return (t, p_wert_zweiseitig(t, n - 1))


def grundrate_aus_rahmen(
    rahmen: pd.DataFrame,
    basis: pd.DataFrame,
    *,
    name: str,
    horizont: int,
) -> Grundrate | None:
    """Kennzahlen fuer eine Ereignismenge gegen eine Nulllinie.

    ``rahmen`` braucht die Spalten ``end_r``, ``mfe_r``, ``mae_r``,
    ``verfuegbar_idx`` und ``cluster_id``. ``basis`` ist die
    bedingungslose Vergleichsmenge (dieselben Spalten, ohne Bedingung).

    ``None``, wenn die Stichprobe unter ``MIN_N`` liegt - dann wird nichts
    behauptet.
    """
    rahmen = rahmen.dropna(subset=["end_r"])
    if len(rahmen) < MIN_N:
        return None

    werte = rahmen["end_r"].to_numpy(dtype=float)
    basis_werte = basis["end_r"].dropna().to_numpy(dtype=float)
    basis_mittel = float(np.mean(basis_werte)) if len(basis_werte) else 0.0
    basis_anteil = (
        float(np.mean(basis_werte > 0)) if len(basis_werte) else float("nan")
    )

    # Klumpen: gleichzeitige Signale zaehlen einmal (Plan 12.1).
    n_cluster = int(rahmen["cluster_id"].nunique())

    # Ueberschneidungsfrei - das ist die massgebliche Stichprobe.
    maske = ueberschneidungsfrei(
        rahmen["verfuegbar_idx"].to_numpy(dtype=np.int64), horizont
    )
    unabhaengig = werte[maske]

    t_ueber, p_ueber = _t_und_p(werte, basis_mittel)
    if len(unabhaengig) >= 2:
        t_frei, p_frei = _t_und_p(unabhaengig, basis_mittel)
    else:
        t_frei, p_frei = (0.0, 1.0)

    treffer = int(np.sum(werte > 0))
    hinweise = []
    if len(rahmen) < BELASTBAR_AB:
        hinweise.append("Stichprobe zu klein fuer belastbare Aussage")
    if len(unabhaengig) < MIN_N:
        hinweise.append(
            f"nur {len(unabhaengig)} ueberschneidungsfreie Faelle - "
            "der p-Wert ist nicht belastbar"
        )

    return Grundrate(
        name=name,
        horizont=horizont,
        n=len(rahmen),
        n_unabhaengig=int(maske.sum()),
        n_cluster=n_cluster,
        mittel_r=float(np.mean(werte)),
        median_r=float(np.median(werte)),
        streuung_r=float(np.std(werte, ddof=1)),
        anteil_positiv=treffer / len(werte),
        anteil_positiv_ki=wilson_intervall(treffer, len(werte)),
        mfe_r_median=float(np.nanmedian(rahmen["mfe_r"])),
        mae_r_median=float(np.nanmedian(rahmen["mae_r"])),
        mae_r_p90=float(np.nanpercentile(rahmen["mae_r"], 90)),
        basis_mittel_r=basis_mittel,
        basis_anteil_positiv=basis_anteil,
        t_statistik=t_frei,
        p_wert=p_frei,
        t_ueberschneidend=t_ueber,
        p_ueberschneidend=p_ueber,
        hinweis="; ".join(hinweise),
    )


def lade_fuer_auswertung(
    conn: sqlite3.Connection,
    *,
    horizont: int,
    block: str = "train",
    zusatzspalten: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Ereignisse mit ihren Outcomes fuer einen Horizont.

    **Nur der angegebene Datensatzblock.** Vorgabe ``train`` - Validation und
    OOS werden nicht beilaeufig mitgelesen (Plan Abschnitt 11).
    """
    if block not in ("train", "validation", "oos", "alle"):
        raise ValueError(
            f"Unbekannter Block {block!r}. Erlaubt: train, validation, oos, alle."
        )
    spalten = [
        "e.event_id", "e.pattern_type", "e.pattern_variant", "e.direction",
        "e.verfuegbar_idx", "e.cluster_id", "e.vola_regime",
        "e.struktur_regime", "e.liquiditaet_regime", "e.session",
        "e.datensatz_block", "e.nahe_rollgrenze",
        "o.end_r", "o.mfe_r", "o.mae_r", "o.end_pkt", "o.zeit_bis_mfe",
    ] + [f"e.{s}" for s in zusatzspalten]

    frage = (
        f"SELECT {','.join(spalten)} FROM outcomes o "
        "JOIN events e USING(event_id) WHERE o.horizont_bars = ?"
    )
    params: list = [horizont]
    if block != "alle":
        frage += " AND e.datensatz_block = ?"
        params.append(block)
    return pd.read_sql_query(frage, conn, params=params)


def grundratentabelle(
    daten: pd.DataFrame,
    *,
    horizont: int,
    gruppierung: tuple[str, ...] = ("pattern_type",),
    nur_richtung: bool = True,
) -> pd.DataFrame:
    """Grundraten fuer jede Gruppe, gegen die bedingungslose Nulllinie.

    ``nur_richtung=True`` rechnet die Nulllinie **je Richtung** getrennt: die
    unbedingte Rendite eines Long unterscheidet sich von der eines Short um
    das Vorzeichen, und ein Muster, das nur Shorts erzeugt, waere gegen eine
    gemischte Nulllinie systematisch falsch bewertet.

    **Alle** Gruppen werden ausgegeben, auch die uninteressanten. Wer daraus
    eine auswaehlt, trifft eine Auswahl - ab da gilt die
    Mehrfachtestkorrektur gegen ``len(ergebnis)``.
    """
    zeilen = []
    gruppen = daten.groupby(list(gruppierung) + (["direction"] if nur_richtung else []))
    for schluessel, teil in gruppen:
        if not isinstance(schluessel, tuple):
            schluessel = (schluessel,)
        if nur_richtung:
            richtung = schluessel[-1]
            basis = daten[daten["direction"] == richtung]
            name = "/".join(str(s) for s in schluessel[:-1])
            name += f" [{'long' if richtung == 1 else 'short'}]"
        else:
            basis = daten
            name = "/".join(str(s) for s in schluessel)

        rate = grundrate_aus_rahmen(
            teil, basis, name=name, horizont=horizont
        )
        if rate is not None:
            zeilen.append(rate.to_dict())

    if not zeilen:
        return pd.DataFrame()
    tabelle = pd.DataFrame(zeilen).sort_values("kante_R", ascending=False)
    return tabelle.reset_index(drop=True)


def bonferroni_schwelle(anzahl_vergleiche: int, alpha: float = 0.05) -> float:
    """Die Schwelle, ab der ein p-Wert bei so vielen Vergleichen zaehlt.

    Wer 100 Muster misst und das beste herausgreift, hat 100 Vergleiche
    angestellt - nicht einen. Ohne diese Korrektur findet man bei alpha=0,05
    in 100 reinen Zufallsreihen rund fuenf "signifikante" Muster.
    """
    return alpha / max(1, anzahl_vergleiche)


__all__ = [
    "BELASTBAR_AB",
    "Grundrate",
    "MIN_N",
    "bonferroni_schwelle",
    "grundrate_aus_rahmen",
    "grundratentabelle",
    "lade_fuer_auswertung",
    "ueberschneidungsfrei",
    "wilson_intervall",
]
