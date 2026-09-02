"""Ziel vor Stop: die Zahl, aus der Profitabilitaet folgt.

Laurins Punkte 4 und 5 (Zieldefinition 01.09.2026) sind ohne diese Messung
nicht beantwortbar - weder der wirtschaftliche Entscheidungspunkt noch die
Frage, welcher Stop und welches Ziel zu einem Zustand passen.

WARUM MFE UND MAE DAFUER NICHT REICHEN
--------------------------------------
``outcomes.py`` liefert je Ereignis die groesste guenstige (MFE) und
unguenstigste (MAE) Auslenkung. Aus beiden **einzeln** laesst sich nicht
ableiten, was zuerst kam:

    MFE 3R, MAE 2R  =  erst 3R hoch, dann 2R runter   -> Gewinn
                    =  erst 2R runter, dann 3R hoch   -> ausgestoppt

Es ist dieselbe Zahlenkombination bei entgegengesetztem Ergebnis.

DER FEHLER IN DER VORHANDENEN NAEHERUNG
---------------------------------------
``backtest/conditional_outcomes.py`` versucht das ueber die Zeitstempel der
Extrema:

    if exc.time_to_mae_bars <= exc.time_to_mfe_bars: stop zuerst

``time_to_mfe_bars`` ist die Zeit bis zum **Maximum**, nicht bis zur **ersten
Zielberuehrung**. Beispiel: Ziel 1R wird in Kerze 1 erreicht, danach faellt
der Kurs in Kerze 5 auf -2R und steigt in Kerze 20 auf 3R. Dann ist
``time_to_mfe = 20`` und ``time_to_mae = 5`` - die Naeherung bucht "Stop
zuerst", obwohl das Ziel in Kerze 1 erreicht war. Das verzerrt die
Trefferquote **systematisch nach unten**, umso staerker, je enger das Ziel.

Hier wird stattdessen die **erste Beruehrung** gemessen, je Schwelle.

DIE INTRABAR-KONVENTION
-----------------------
Beruehrt eine Kerze Ziel **und** Stop, ist aus OHLC nicht rekonstruierbar,
was zuerst kam. Konvention wie in der Backtest-Engine (Invariante 4): **der
Stop gilt als zuerst erreicht.** Jede Auswertung weist aus, wie oft dieser
Fall eintrat - ist der Anteil hoch, haengt das Ergebnis an der Annahme.

WARUM ZIEL- UND STOPZEITEN GETRENNT GERECHNET WERDEN
----------------------------------------------------
Ein Raster aus 5 Zielen x 5 Stops sind 25 Kombinationen. Rechnet man jede
einzeln, laeuft man 25 mal durch den Horizont. Die **erste Beruehrung eines
Ziels** haengt aber nicht vom Stop ab und umgekehrt: 5 + 5 = 10 Durchlaeufe
genuegen, danach ist jede Kombination ein Vergleich zweier fertiger Arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv

#: Ziel-Abstaende in ATR-Vielfachen. Von "kaum mehr als Rauschen" bis zu
#: einer Bewegung, die auf 1m selten ist.
ZIEL_RASTER: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)

#: Stop-Abstaende in ATR-Vielfachen.
STOP_RASTER: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 3.0)

#: Kerze, ab der nichts mehr entschieden wird. ``None`` in den Trefferzeiten.
NICHT_ERREICHT = np.iinfo(np.int32).max


def erste_beruehrung(
    df: pd.DataFrame,
    einstieg_idx: np.ndarray,
    schwellenpreis: np.ndarray,
    horizont: int,
    *,
    nach_oben: bool,
) -> np.ndarray:
    """Kerzen bis zur **ersten** Beruehrung einer Preisschwelle.

    ``einstieg_idx`` sind die Positionen der Einstiegskerze (nicht der
    Ereigniskerze). ``schwellenpreis`` ist je Ereignis der Preis, der
    beruehrt werden muss. ``nach_oben=True`` prueft gegen ``high``, sonst
    gegen ``low``.

    Rueckgabe: int32-Array, 1-basiert (1 = gleich in der Einstiegskerze).
    ``NICHT_ERREICHT``, wo die Schwelle im Fenster nicht beruehrt wurde.

    Ein Durchlauf ueber den Horizont, vektorisiert ueber **alle** Ereignisse
    gleichzeitig - und er bricht ab, sobald jedes entschieden ist.
    """
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    n = len(df)

    treffer = np.full(len(einstieg_idx), NICHT_ERREICHT, dtype=np.int32)
    offen = np.ones(len(einstieg_idx), dtype=bool)

    for k in range(horizont):
        if not offen.any():
            break
        pos = einstieg_idx + k
        gueltig = offen & (pos < n)
        if not gueltig.any():
            break
        idx = np.nonzero(gueltig)[0]
        kurse = (highs if nach_oben else lows)[pos[idx]]
        beruehrt = (
            kurse >= schwellenpreis[idx] if nach_oben
            else kurse <= schwellenpreis[idx]
        )
        getroffen = idx[beruehrt]
        treffer[getroffen] = k + 1
        offen[getroffen] = False

    return treffer


@dataclass(frozen=True)
class Barriereergebnis:
    """Ein Ziel/Stop-Paar, ausgezaehlt ueber eine Ereignismenge."""

    ziel_r: float
    stop_r: float
    horizont: int

    n: int
    ziel_zuerst: int
    stop_zuerst: int
    keins: int              # weder Ziel noch Stop im Horizont
    ambig: int              # beide in derselben Kerze - Annahme entschied

    @property
    def entschieden(self) -> int:
        return self.ziel_zuerst + self.stop_zuerst

    @property
    def trefferquote(self) -> float:
        """Anteil Ziel-vor-Stop unter den **entschiedenen** Faellen."""
        return self.ziel_zuerst / self.entschieden if self.entschieden else float("nan")

    @property
    def ambig_anteil(self) -> float:
        """Wie oft die Intrabar-Annahme das Ergebnis bestimmt hat."""
        return self.ambig / self.entschieden if self.entschieden else float("nan")

    def erwartungswert_r(self, kosten_r: float = 0.0) -> float:
        """Erwartungswert je **eingegangenem** Trade, in R.

        Unentschiedene Faelle (Zeitablauf) werden mit 0 R gewertet - das ist
        die vorsichtige Annahme: in Wahrheit steht dort irgendetwas zwischen
        Ziel und Stop, und ohne Zeitstop-Regel ist nicht bestimmbar was.
        Der wahre Wert liegt darueber; diese Zahl ist eine Untergrenze.

        ``kosten_r`` ist die Friktion je Trade in R (Kommission + Boersen-
        gebuehren + Slippage, umgerechnet auf den ATR-Bezug des Ereignisses).
        """
        if self.n == 0:
            return float("nan")
        roh = (self.ziel_zuerst * self.ziel_r - self.stop_zuerst * self.stop_r) / self.n
        return roh - kosten_r

    def to_dict(self, kosten_r: float = 0.0) -> dict:
        return {
            "ziel_R": self.ziel_r,
            "stop_R": self.stop_r,
            "horizont": self.horizont,
            "n": self.n,
            "entschieden": self.entschieden,
            "ziel_zuerst": self.ziel_zuerst,
            "stop_zuerst": self.stop_zuerst,
            "zeitablauf": self.keins,
            "trefferquote": round(self.trefferquote, 4),
            "ambig_anteil": round(self.ambig_anteil, 4),
            "E[R]_brutto": round(self.erwartungswert_r(), 4),
            "E[R]_netto": round(self.erwartungswert_r(kosten_r), 4),
        }


@dataclass(frozen=True)
class Trefferzeiten:
    """Erste Beruehrung je Schwelle - die teure Rechnung, einmal gemacht.

    ``brauchbar`` ist die Maske auf der urspruenglichen Ereignisliste; alle
    Zeit-Arrays beziehen sich auf die **verbliebenen** Ereignisse in
    derselben Reihenfolge. So laesst sich dieselbe Rechnung fuer beliebig
    viele Gruppierungen auszaehlen, ohne sie zu wiederholen.
    """

    horizont: int
    brauchbar: np.ndarray                  # bool, Laenge der Eingabe
    ziel_zeit: dict[float, np.ndarray]
    stop_zeit: dict[float, np.ndarray]

    def __len__(self) -> int:
        return int(self.brauchbar.sum())


def berechne_trefferzeiten(
    df: pd.DataFrame,
    verfuegbar_idx: np.ndarray,
    richtung: np.ndarray,
    *,
    horizont: int,
    ziele: tuple[float, ...] = ZIEL_RASTER,
    stops: tuple[float, ...] = STOP_RASTER,
    atr_spalte: str = "atr",
    atr_untergrenze: float = 1.0,
) -> Trefferzeiten:
    """Die erste Beruehrung je Schwelle, fuer alle Ereignisse auf einmal.

    Einstieg zur Eroeffnung der Folgekerze (Invariante 4). Ereignisse ohne
    vollstaendiges Fenster oder mit unbrauchbarer ATR werden verworfen -
    letzteres, weil ein ATR von 0,003 Punkten kein Marktzustand ist, sondern
    eingefrorene Kurse (siehe ``grundraten`` Modul-Docstring).
    """
    validate_ohlcv(df)
    verfuegbar_idx = np.asarray(verfuegbar_idx, dtype=np.int64)
    richtung = np.asarray(richtung, dtype=np.int64)
    if len(verfuegbar_idx) != len(richtung):
        raise ValueError("verfuegbar_idx und richtung muessen gleich lang sein.")
    if not np.isin(richtung, (-1, 1)).all():
        raise ValueError("richtung darf nur +1 oder -1 enthalten.")

    n = len(df)
    opens = df["open"].to_numpy(dtype=float)
    atr = (
        df[atr_spalte].to_numpy(dtype=float)
        if atr_spalte in df.columns
        else np.full(n, np.nan)
    )

    einstieg = verfuegbar_idx + 1
    sicher = np.clip(verfuegbar_idx, 0, n - 1)
    brauchbar = (
        (einstieg >= 0)
        & (einstieg + horizont <= n)
        & np.isfinite(atr[sicher])
        & (atr[sicher] >= atr_untergrenze)
    )
    if not brauchbar.any():
        return Trefferzeiten(horizont, brauchbar, {}, {})

    e = einstieg[brauchbar]
    r = richtung[brauchbar]
    a = atr[verfuegbar_idx[brauchbar]]
    entry = opens[e]
    long = r == 1

    def zeiten(abstand: float, *, ist_ziel: bool) -> np.ndarray:
        # Ziel liegt beim Long oben, beim Short unten - Stop umgekehrt.
        vorzeichen = 1.0 if ist_ziel else -1.0
        preis = np.where(
            long, entry + vorzeichen * abstand * a, entry - vorzeichen * abstand * a
        )
        zeit = np.full(len(e), NICHT_ERREICHT, dtype=np.int32)
        oben_long = ist_ziel          # Long-Ziel oben, Long-Stop unten
        if long.any():
            zeit[long] = erste_beruehrung(
                df, e[long], preis[long], horizont, nach_oben=oben_long
            )
        if (~long).any():
            zeit[~long] = erste_beruehrung(
                df, e[~long], preis[~long], horizont, nach_oben=not oben_long
            )
        return zeit

    return Trefferzeiten(
        horizont=horizont,
        brauchbar=brauchbar,
        ziel_zeit={z: zeiten(z, ist_ziel=True) for z in ziele},
        stop_zeit={s: zeiten(s, ist_ziel=False) for s in stops},
    )


def zaehle_aus(
    zeiten: Trefferzeiten, *, auswahl: np.ndarray | None = None
) -> list[Barriereergebnis]:
    """Aus fertigen Trefferzeiten jede Ziel/Stop-Kombination auszaehlen.

    ``auswahl`` ist eine Bool-Maske auf den **verbliebenen** Ereignissen (also
    nach ``brauchbar``) - damit lassen sich Untergruppen auszaehlen, ohne die
    teure Rechnung zu wiederholen.
    """
    ergebnisse: list[Barriereergebnis] = []
    for z, tz_all in zeiten.ziel_zeit.items():
        tz = tz_all if auswahl is None else tz_all[auswahl]
        for s, ts_all in zeiten.stop_zeit.items():
            ts = ts_all if auswahl is None else ts_all[auswahl]
            beide_offen = (tz == NICHT_ERREICHT) & (ts == NICHT_ERREICHT)
            # Gleichstand = beide in derselben Kerze: Stop gilt (pessimistisch).
            gleich = (tz == ts) & ~beide_offen
            ergebnisse.append(
                Barriereergebnis(
                    ziel_r=z, stop_r=s, horizont=zeiten.horizont,
                    n=int(len(tz)),
                    ziel_zuerst=int((tz < ts).sum()),
                    stop_zuerst=int(((ts < tz) | gleich).sum()),
                    keins=int(beide_offen.sum()),
                    ambig=int(gleich.sum()),
                )
            )
    return ergebnisse


def barrieren_raster(
    df: pd.DataFrame,
    verfuegbar_idx: np.ndarray,
    richtung: np.ndarray,
    *,
    horizont: int,
    ziele: tuple[float, ...] = ZIEL_RASTER,
    stops: tuple[float, ...] = STOP_RASTER,
    atr_spalte: str = "atr",
    atr_untergrenze: float = 1.0,
) -> list[Barriereergebnis]:
    """Bequemlichkeit: Trefferzeiten rechnen und gleich auszaehlen.

    Fuer mehrere Gruppierungen ueber dieselbe Ereignismenge stattdessen
    ``berechne_trefferzeiten`` einmal und ``zaehle_aus`` mehrfach.
    """
    zeiten = berechne_trefferzeiten(
        df, verfuegbar_idx, richtung, horizont=horizont, ziele=ziele,
        stops=stops, atr_spalte=atr_spalte, atr_untergrenze=atr_untergrenze,
    )
    if not zeiten.ziel_zeit:
        return []
    return zaehle_aus(zeiten)


def zufalls_nulllinie(
    df: pd.DataFrame,
    richtung: int,
    *,
    horizont: int,
    anzahl: int = 200_000,
    ziele: tuple[float, ...] = ZIEL_RASTER,
    stops: tuple[float, ...] = STOP_RASTER,
    seed: int = 20260901,
    atr_spalte: str = "atr",
) -> list[Barriereergebnis]:
    """Dieselbe Messung auf **zufaellig gewaehlten** Kerzen.

    Das ist die Nulllinie, gegen die jedes Muster antreten muss. Ohne sie ist
    "Ziel wurde in 62 % der Faelle zuerst erreicht" wertlos - bei Ziel 1R und
    Stop 2R ist eine hohe Trefferquote die **Normalitaet**, nicht der Befund.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    kandidaten = rng.integers(0, max(1, n - horizont - 2), size=anzahl)
    return barrieren_raster(
        df, np.sort(kandidaten), np.full(anzahl, richtung),
        horizont=horizont, ziele=ziele, stops=stops, atr_spalte=atr_spalte,
    )


__all__ = [
    "Barriereergebnis",
    "NICHT_ERREICHT",
    "STOP_RASTER",
    "ZIEL_RASTER",
    "barrieren_raster",
    "erste_beruehrung",
    "zufalls_nulllinie",
]
