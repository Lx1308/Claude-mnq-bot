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

5. **Der Mittelwert von R ist nicht belastbar.** ``end_r`` ist
   ``end_pkt / atr_referenz``. Im ersten Volllauf (31.08.2026) fanden sich
   Ereignisse mit ``atr_referenz`` bis hinunter zu 0,0026 Punkten - kein
   Marktzustand, sondern eingefrorene Kurse in duenner Fruehhistorie. Eine
   normale 150-Punkte-Bewegung ergibt dann ``end_r = -9.400``. Bei
   ``niveau_test [long]`` zog das den Mittelwert auf **-3,03**, waehrend der
   **Median bei +0,22** lag - wie bei jedem anderen Long-Muster. Dieser eine
   kaputte Mittelwert vergiftete zusaetzlich die Nulllinie aller Longs, und
   dadurch sah **jedes** andere Long-Muster wie ein Vorteil von +0,25 aus.
   Gegenmassnahmen hier: Ereignisse mit ``atr_referenz < ATR_UNTERGRENZE``
   werden verworfen (Artefakt, nicht handelbar), der Rest wird bei
   ``WINSOR_R`` gekappt, und die **massgebliche** Kennzahl ist der Vergleich
   der **Trefferanteile** (Vorzeichen von ``end_pkt``) gegen die Nulllinie -
   der ist gegen diesen Fehler immun, weil er die ATR gar nicht benutzt.

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

#: Ereignisse mit einer kleineren ATR-Referenz als das (in Punkten) werden
#: verworfen. Bei MNQ liegt die 1m-ATR praktisch immer ueber 2 Punkten; Werte
#: darunter stammen aus eingefrorenen Kursen (duenne Fruehhistorie, Luecken)
#: und sind kein handelbarer Zustand. R-Werte daraus sind Muell - siehe die
#: fuenfte Falle im Modul-Docstring.
ATR_UNTERGRENZE = 1.0

#: R-Werte werden hierauf gekappt (Winsorisierung, nicht Loeschung - die
#: Stichprobengroesse bleibt). Nichts Reales bewegt sich in den gemessenen
#: Horizonten um 25 ATR; ein groesserer Wert ist ein Rechenartefakt.
WINSOR_R = 25.0


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def zwei_anteile_p(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """Zweiseitiger Test auf Gleichheit zweier Trefferanteile.

    ``(z, p)``. Gepoolter Anteil fuer den Standardfehler. Dieser Test benutzt
    nur das **Vorzeichen** des Ausgangs, nie die ATR - deshalb ist er die
    massgebliche Kennzahl, wenn die ATR-Normierung unzuverlaessig ist.
    """
    if n1 <= 0 or n2 <= 0:
        return (0.0, 1.0)
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se <= 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    return (z, 2.0 * (1.0 - _normal_cdf(abs(z))))


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
    """Ein Muster, ein Horizont, eine Kennzahl - mit ihrer Nulllinie.

    **Massgeblich ist ``anteil_kante`` mit ``anteil_p_wert``** (der
    ueberschneidungsfreie Zwei-Anteile-Test). Die R-Mittelwerte stehen
    daneben, weil man sie erwartet - aber sie sind gegen einzelne winzige
    ATR-Werte empfindlich, der Anteilstest nicht.
    """

    name: str
    horizont: int
    n: int
    n_verworfen_atr: int
    n_winsorisiert: int
    n_unabhaengig: int
    n_cluster: int

    # -- Trefferanteil: die belastbare Kennzahl --------------------------
    anteil_positiv: float
    anteil_positiv_ki: tuple[float, float]
    basis_anteil_positiv: float
    anteil_p_wert: float                 # ueberschneidungsfrei - massgeblich
    anteil_p_wert_ueberschneidend: float

    # -- R-Kennzahlen: daneben, mit Vorbehalt ---------------------------
    mittel_r: float
    median_r: float
    streuung_r: float
    basis_mittel_r: float
    basis_median_r: float
    mfe_r_median: float
    mae_r_median: float
    mae_r_p90: float
    t_statistik: float
    p_wert: float
    t_ueberschneidend: float
    p_ueberschneidend: float

    hinweis: str = ""

    @property
    def anteil_kante(self) -> float:
        """Ueberschuss im Trefferanteil gegenueber der Nulllinie. DIE Zahl."""
        return self.anteil_positiv - self.basis_anteil_positiv

    @property
    def kante_r(self) -> float:
        """Ueberschuss im R-Mittel. Mit Vorbehalt - siehe ``hinweis``."""
        return self.mittel_r - self.basis_mittel_r

    @property
    def median_kante_r(self) -> float:
        """Ueberschuss im R-Median. Robust, aber grob (Median in R-Schritten)."""
        return self.median_r - self.basis_median_r

    def to_dict(self) -> dict:
        return {
            "muster": self.name,
            "horizont": self.horizont,
            "n": self.n,
            "n_unabhaengig": self.n_unabhaengig,
            "n_cluster": self.n_cluster,
            "n_verworfen_atr": self.n_verworfen_atr,
            "n_winsorisiert": self.n_winsorisiert,
            "anteil_positiv": round(self.anteil_positiv, 4),
            "anteil_positiv_ki": (
                round(self.anteil_positiv_ki[0], 4),
                round(self.anteil_positiv_ki[1], 4),
            ),
            "basis_anteil_positiv": round(self.basis_anteil_positiv, 4),
            "anteil_kante": round(self.anteil_kante, 4),
            "anteil_p": round(self.anteil_p_wert, 6),
            "anteil_p_ueberschneidend": round(self.anteil_p_wert_ueberschneidend, 6),
            "E[R]": round(self.mittel_r, 4),
            "median_R": round(self.median_r, 4),
            "kante_R": round(self.kante_r, 4),
            "median_kante_R": round(self.median_kante_r, 4),
            "basis_E[R]": round(self.basis_mittel_r, 4),
            "mae_R_median": round(self.mae_r_median, 3),
            "mae_R_p90": round(self.mae_r_p90, 3),
            "mfe_R_median": round(self.mfe_r_median, 3),
            "t_ueberschneidend": round(self.t_ueberschneidend, 3),
            "p_R_ueberschneidend": round(self.p_ueberschneidend, 5),
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


def _saeubere(rahmen: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """ATR-Artefakte verwerfen, R winsorisieren.

    Rueckgabe ``(sauber, verworfen, winsorisiert)``. ``rahmen`` bleibt
    unveraendert.
    """
    rahmen = rahmen.dropna(subset=["end_r"])
    if "atr_referenz" in rahmen.columns:
        genug_atr = rahmen["atr_referenz"] >= ATR_UNTERGRENZE
        verworfen = int((~genug_atr).sum())
        rahmen = rahmen[genug_atr]
    else:
        verworfen = 0

    winsorisiert = 0
    rahmen = rahmen.copy()
    for spalte in ("end_r", "mfe_r", "mae_r"):
        if spalte not in rahmen.columns:
            continue
        werte = rahmen[spalte].to_numpy(dtype=float)
        aussen = np.abs(werte) > WINSOR_R
        winsorisiert = max(winsorisiert, int(np.sum(aussen)))
        rahmen[spalte] = np.clip(werte, -WINSOR_R, WINSOR_R)
    return rahmen, verworfen, winsorisiert


def grundrate_aus_rahmen(
    rahmen: pd.DataFrame,
    basis: pd.DataFrame,
    *,
    name: str,
    horizont: int,
    schon_gesaeubert: bool = False,
) -> Grundrate | None:
    """Kennzahlen fuer eine Ereignismenge gegen eine Nulllinie.

    ``rahmen`` braucht ``end_r``, ``mfe_r``, ``mae_r``, ``end_pkt``,
    ``verfuegbar_idx``, ``cluster_id`` und - fuer die Saeuberung -
    ``atr_referenz``. ``basis`` ist die Vergleichsmenge ohne die Bedingung.

    ``schon_gesaeubert=True``, wenn ATR-Filter und Winsorisierung schon auf
    beide Rahmen angewendet wurden (spart die Wiederholung in der Tabelle).

    ``None``, wenn die Stichprobe unter ``MIN_N`` liegt.
    """
    if schon_gesaeubert:
        verworfen = winsorisiert = 0
    else:
        rahmen, verworfen, winsorisiert = _saeubere(rahmen)
        basis, _, _ = _saeubere(basis)

    if len(rahmen) < MIN_N:
        return None

    werte = rahmen["end_r"].to_numpy(dtype=float)
    # Der Trefferanteil kommt aus end_pkt, NICHT aus end_r - er braucht die
    # ATR nicht und ist damit gegen die fuenfte Falle immun.
    vorzeichen = rahmen["end_pkt"].to_numpy(dtype=float) > 0
    basis_vorzeichen = basis["end_pkt"].to_numpy(dtype=float) > 0
    basis_werte = basis["end_r"].to_numpy(dtype=float)

    basis_mittel = float(np.mean(basis_werte)) if len(basis_werte) else 0.0
    basis_median = float(np.median(basis_werte)) if len(basis_werte) else 0.0
    basis_anteil = (
        float(np.mean(basis_vorzeichen)) if len(basis_vorzeichen) else float("nan")
    )

    n_cluster = int(rahmen["cluster_id"].nunique())

    # Ueberschneidungsfrei - fuer den Anteilstest UND den R-Test.
    maske = ueberschneidungsfrei(
        rahmen["verfuegbar_idx"].to_numpy(dtype=np.int64), horizont
    )
    basis_maske = ueberschneidungsfrei(
        basis["verfuegbar_idx"].to_numpy(dtype=np.int64), horizont
    )
    unab_werte = werte[maske]
    unab_vorz = vorzeichen[maske]
    basis_unab_vorz = basis_vorzeichen[basis_maske]

    treffer = int(np.sum(vorzeichen))
    _, anteil_p_ueber = zwei_anteile_p(
        treffer, len(vorzeichen),
        int(np.sum(basis_vorzeichen)), len(basis_vorzeichen),
    )
    if len(unab_vorz) >= MIN_N and len(basis_unab_vorz) >= MIN_N:
        _, anteil_p_frei = zwei_anteile_p(
            int(np.sum(unab_vorz)), len(unab_vorz),
            int(np.sum(basis_unab_vorz)), len(basis_unab_vorz),
        )
    else:
        anteil_p_frei = 1.0

    t_ueber, p_ueber = _t_und_p(werte, basis_mittel)
    t_frei, p_frei = (
        _t_und_p(unab_werte, basis_mittel) if len(unab_werte) >= 2 else (0.0, 1.0)
    )

    hinweise = []
    if len(rahmen) < BELASTBAR_AB:
        hinweise.append("Stichprobe zu klein fuer belastbare Aussage")
    if int(maske.sum()) < MIN_N:
        hinweise.append(
            f"nur {int(maske.sum())} ueberschneidungsfreie Faelle"
        )
    mittel = float(np.mean(werte))
    median = float(np.median(werte))
    if abs(mittel - median) > 0.5:
        hinweise.append(
            f"E[R] ({mittel:.2f}) und Median ({median:.2f}) weit auseinander - "
            "schwere Raender, der Mittelwert traegt nicht"
        )
    if verworfen > 0.02 * (len(rahmen) + verworfen):
        hinweise.append(
            f"{verworfen} Ereignisse wegen zu kleiner ATR verworfen "
            f"({verworfen / (len(rahmen) + verworfen) * 100:.1f} %)"
        )

    return Grundrate(
        name=name,
        horizont=horizont,
        n=len(rahmen),
        n_verworfen_atr=verworfen,
        n_winsorisiert=winsorisiert,
        n_unabhaengig=int(maske.sum()),
        n_cluster=n_cluster,
        anteil_positiv=treffer / len(vorzeichen),
        anteil_positiv_ki=wilson_intervall(treffer, len(vorzeichen)),
        basis_anteil_positiv=basis_anteil,
        anteil_p_wert=anteil_p_frei,
        anteil_p_wert_ueberschneidend=anteil_p_ueber,
        mittel_r=mittel,
        median_r=median,
        streuung_r=float(np.std(werte, ddof=1)),
        basis_mittel_r=basis_mittel,
        basis_median_r=basis_median,
        mfe_r_median=float(np.nanmedian(rahmen["mfe_r"])),
        mae_r_median=float(np.nanmedian(rahmen["mae_r"])),
        mae_r_p90=float(np.nanpercentile(rahmen["mae_r"], 90)),
        t_statistik=t_frei,
        p_wert=p_frei,
        t_ueberschneidend=t_ueber,
        p_ueberschneidend=p_ueber,
        hinweis="; ".join(hinweise),
    )


#: Die Ereignisspalten, die eine Auswertung braucht.
_EVENT_SPALTEN = (
    "event_id", "pattern_type", "pattern_variant", "direction",
    "verfuegbar_idx", "cluster_id", "vola_regime", "struktur_regime",
    "liquiditaet_regime", "session", "datensatz_block", "nahe_rollgrenze",
)

#: Die Outcome-Spalten, die eine Auswertung braucht. ``atr_referenz`` ist
#: fuer die Saeuberung noetig (fuenfte Falle), ``end_pkt`` fuer den
#: ATR-freien Trefferanteil. Diese Liste deckt sich mit dem deckenden Index
#: ``idx_outcomes_auswertung`` - laeuft sie auseinander, wird jede Abfrage
#: wieder ein Tabellendurchlauf (siehe ``datenbank.INDIZES``).
_OUTCOME_SPALTEN = ("event_id", "end_r", "mfe_r", "mae_r", "end_pkt",
                    "atr_referenz", "zeit_bis_mfe")


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

    WARUM ZWEI ABFRAGEN STATT EINES JOINS
    -------------------------------------
    Der naheliegende ``JOIN ... USING(event_id)`` liess SQLite fuer **jede**
    der Millionen Outcome-Zeilen einzeln in ``events`` nachschlagen - ueber
    eine 5,4-GB-Datenbank (31.08.2026) nach 25 Minuten noch nicht fertig.
    Beide Tabellen **getrennt** und jeweils am Stueck zu lesen und in pandas
    zusammenzufuehren vermeidet die Einzelzugriffe. Der Filter auf den
    Datensatzblock greift dabei zuerst auf der kleineren Seite (``events``).

    Die Outcome-Abfrage bleibt nur schnell, solange ``_OUTCOME_SPALTEN`` sich
    mit dem deckenden Index ``idx_outcomes_auswertung`` deckt (siehe
    ``datenbank.INDIZES``) - sonst folgt fuer jede Zeile wieder ein Zugriff in
    die grosse Tabelle.
    """
    if block not in ("train", "validation", "oos", "alle"):
        raise ValueError(
            f"Unbekannter Block {block!r}. Erlaubt: train, validation, oos, alle."
        )

    spalten = list(_EVENT_SPALTEN) + [
        s for s in zusatzspalten if s not in _EVENT_SPALTEN
    ]
    frage_e = f"SELECT {','.join(spalten)} FROM events"
    params_e: list = []
    if block != "alle":
        frage_e += " WHERE datensatz_block = ?"
        params_e.append(block)
    ereignisse = pd.read_sql_query(frage_e, conn, params=params_e)
    if ereignisse.empty:
        return ereignisse

    outcomes = pd.read_sql_query(
        f"SELECT {','.join(_OUTCOME_SPALTEN)} FROM outcomes "
        "WHERE horizont_bars = ?",
        conn, params=[horizont],
    )
    if outcomes.empty:
        return outcomes

    return ereignisse.merge(outcomes, on="event_id", how="inner")


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

    Die Nulllinie einer Gruppe ist "alle gleichgerichteten Ereignisse **ohne
    diese Gruppe**". Waere die Gruppe selbst in der Nulllinie, vergliche man
    sie teilweise mit sich - und ein grosses, schiefes Muster wie
    ``niveau_test`` verschoebe die Nulllinie in seine eigene Richtung.
    """
    # ATR-Artefakte einmal fuer den ganzen Datensatz entfernen (fuenfte
    # Falle) - danach ist jede Teilmenge sauber.
    daten, verworfen_gesamt, _ = _saeubere(daten)
    if daten.empty:
        return pd.DataFrame()

    gruppenspalten = list(gruppierung) + (["direction"] if nur_richtung else [])
    zeilen = []
    for schluessel, teil in daten.groupby(gruppenspalten):
        if not isinstance(schluessel, tuple):
            schluessel = (schluessel,)
        if nur_richtung:
            richtung = schluessel[-1]
            gleiche_richtung = daten["direction"] == richtung
            # Nulllinie ohne die eigene Gruppe.
            eigene = pd.Series(True, index=daten.index)
            for spalte, wert in zip(gruppenspalten, schluessel):
                eigene &= daten[spalte] == wert
            basis = daten[gleiche_richtung & ~eigene]
            name = "/".join(str(s) for s in schluessel[:-1])
            name += f" [{'long' if richtung == 1 else 'short'}]"
        else:
            basis = daten.drop(teil.index)
            name = "/".join(str(s) for s in schluessel)

        rate = grundrate_aus_rahmen(
            teil, basis, name=name, horizont=horizont, schon_gesaeubert=True
        )
        if rate is not None:
            zeilen.append(rate.to_dict())

    if not zeilen:
        return pd.DataFrame()
    tabelle = pd.DataFrame(zeilen)
    if verworfen_gesamt:
        tabelle.attrs["verworfen_atr_gesamt"] = int(verworfen_gesamt)
    # Nach dem Anteilsueberschuss sortiert - das ist die belastbare Kennzahl.
    return tabelle.sort_values(
        "anteil_kante", key=lambda s: s.abs(), ascending=False
    ).reset_index(drop=True)


def bonferroni_schwelle(anzahl_vergleiche: int, alpha: float = 0.05) -> float:
    """Die Schwelle, ab der ein p-Wert bei so vielen Vergleichen zaehlt.

    Wer 100 Muster misst und das beste herausgreift, hat 100 Vergleiche
    angestellt - nicht einen. Ohne diese Korrektur findet man bei alpha=0,05
    in 100 reinen Zufallsreihen rund fuenf "signifikante" Muster.
    """
    return alpha / max(1, anzahl_vergleiche)


__all__ = [
    "ATR_UNTERGRENZE",
    "BELASTBAR_AB",
    "Grundrate",
    "MIN_N",
    "WINSOR_R",
    "bonferroni_schwelle",
    "grundrate_aus_rahmen",
    "grundratentabelle",
    "lade_fuer_auswertung",
    "ueberschneidungsfrei",
    "wilson_intervall",
    "zwei_anteile_p",
]
