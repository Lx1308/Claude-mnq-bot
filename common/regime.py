"""Marktregime auf drei unabhaengigen Achsen - rueckwaertsgerichtet.

WOZU
----
Ein Setup, das im Trend traegt und in der Range verliert, sieht ueber alles
gemittelt aus wie "kein Erwartungswert". Ohne Regime-Trennung sind genau die
Setups unsichtbar, die sich lohnen wuerden (MASTERPLAN I).

Die erste Messung des Doppelbodens (30.08.2026) hat das vorgefuehrt: dieselbe
Strategie ist in-sample negativ und out-of-sample positiv. Ob das am Regime
liegt oder Zufall ist, laesst sich ohne diese Achsen nicht entscheiden.

Laengerfristig ist das hier die **grobe Stufe** von Laurins Zielbild: der Bot
soll erkennen "diese Situation kam schon mal vor, ist meist so verlaufen".
Drei Achsen ergeben ueberschaubare Schubladen; ein feineres
Aehnlichkeitsmass kaeme spaeter. Die grobe Stufe zuerst ist kein Formalismus -
sie ist die einzige, bei der sich noch abzaehlen laesst, wie viele Hypothesen
geprueft wurden.

DIE GRENZEN KOMMEN AUS DER VERTEILUNG, NICHT AUS EINER ANNAHME
--------------------------------------------------------------
Am 22.08.2026 stellte sich heraus, dass der geerbte Wert
``consolidation_max_atr = 1.2`` auf keiner Zeitebene erreichbar war - das
Setup konnte nie ausloesen, ohne dass irgendwo ein Fehler erschien.
Regime-Grenzen haben dasselbe Risiko: "ADX ueber 25 heisst Trend" ist eine
Zahl aus einem Lehrbuch, nicht aus diesen Daten.

Deshalb wird hier nichts geschwellt, sondern **rangiert**: eine Kerze liegt im
oberen, mittleren oder unteren Drittel der Verteilung des jeweils
zurueckliegenden Fensters.

DER LOOKAHEAD, DER DABEI VERHINDERT WIRD
----------------------------------------
Die Perzentile ueber die **Gesamthistorie** zu rechnen waere bequem und
falsch: das Regime einer Kerze von 2019 haenge dann davon ab, wie volatil
2026 war. Im Backtest saehe das ausgezeichnet aus, und live gaebe es diese
Information nicht.

Alle Achsen benutzen deshalb ein **rollendes, zurueckliegendes Fenster**
(``Series.rolling(...).rank(pct=True)``). Was am Anfang der Reihe noch kein
volles Fenster hinter sich hat, bekommt ``None`` - "unbestimmt" - und nicht
das naechstbeste Regime. Der dritte Ausgang, wie bei den Filtern der
Ideen-Protokollierung.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.config import IndicatorConfig, SessionConfig
from common.indicators import adx, validate_ohlcv

#: Wie viele Handelstage das rollende Fenster umfasst, aus dem die Verteilung
#: gebildet wird. Drei Monate: lang genug, dass die Verteilung stabil ist,
#: kurz genug, dass ein Regimewechsel innerhalb eines Quartals sichtbar wird.
STANDARD_FENSTER_SESSIONS = 60

#: Wie viele Kerzen ein CME-Handelstag ungefaehr hat, je Zeitebene. Nur zur
#: Umrechnung des Fensters - eine exakte Zahl gibt es nicht (Feiertage,
#: Frueh-Schluesse).
KERZEN_JE_SESSION = {
    1: 1380, 5: 276, 15: 92, 30: 46, 60: 23, 240: 6, 1440: 1,
}

#: Ab welchem Anteil des Fensters ueberhaupt rangiert wird. Unter einem
#: Drittel waere der Rang von zu wenigen Werten abgeleitet.
MIN_ANTEIL_FENSTER = 1 / 3

#: Terzilgrenzen. Drei Auspraegungen je Achse - genug, um zu trennen, wenig
#: genug, dass je Schublade noch Trades uebrig bleiben. 3 x 3 x 3 = 27.
UNTERES_TERZIL = 1.0 / 3.0
OBERES_TERZIL = 2.0 / 3.0

#: Die Achsen und ihre Auspraegungen, von "wenig" nach "viel".
ACHSEN: dict[str, tuple[str, str, str]] = {
    "vola_regime": ("niedrig", "mittel", "hoch"),
    "struktur_regime": ("range", "uebergang", "trend"),
    "liquiditaet_regime": ("duenn", "normal", "rege"),
}

#: Die Spalten, die :func:`regime_spalten` erzeugt.
REGIME_SPALTEN = (
    "vola_rang", "vola_regime",
    "struktur_rang", "struktur_regime",
    "liquiditaet_rang", "liquiditaet_regime",
    "regime",
)


def fenster_kerzen(kerzen_minuten: int, sessions: int = STANDARD_FENSTER_SESSIONS) -> int:
    """Fenstergroesse in Kerzen fuer eine gewuenschte Zahl Handelstage."""
    je_session = KERZEN_JE_SESSION.get(int(kerzen_minuten))
    if je_session is None:
        raise ValueError(
            f"Unbekannte Kerzenlaenge {kerzen_minuten} Minuten. Bekannt: "
            + ", ".join(str(k) for k in sorted(KERZEN_JE_SESSION))
        )
    return max(50, je_session * sessions)


def _terzil(rang: pd.Series, namen: tuple[str, str, str]) -> pd.Series:
    """Perzentilrang -> Auspraegung. ``None``, wo der Rang unbestimmt ist."""
    werte = np.full(len(rang), None, dtype=object)
    gueltig = rang.notna().to_numpy()
    r = rang.to_numpy(dtype=float)

    werte[gueltig & (r <= UNTERES_TERZIL)] = namen[0]
    werte[gueltig & (r > UNTERES_TERZIL) & (r <= OBERES_TERZIL)] = namen[1]
    werte[gueltig & (r > OBERES_TERZIL)] = namen[2]
    return pd.Series(werte, index=rang.index, dtype=object)


def _rollender_rang(reihe: pd.Series, fenster: int) -> pd.Series:
    """Perzentilrang im zurueckliegenden Fenster - streng rueckwaertsgerichtet.

    ``rolling`` schliesst die aktuelle Kerze ein und keine spaetere; damit ist
    der Rang genau die Information, die auch live vorlaege.
    """
    mindestens = max(20, int(fenster * MIN_ANTEIL_FENSTER))
    return reihe.rolling(fenster, min_periods=mindestens).rank(pct=True)


def relatives_volumen(df: pd.DataFrame, sessions: int = STANDARD_FENSTER_SESSIONS) -> pd.Series:
    """Volumen im Verhaeltnis zum ueblichen Volumen DERSELBEN Tageszeit.

    Warum nicht einfach das Volumen rangieren: das Volumen hat eine starke
    Tagesform. Ein roher Rang wuerde die Eroeffnung immer als "rege" und die
    Nacht immer als "duenn" einstufen - eine Aussage, die schon in der
    Session-Angabe steckt und nichts hinzufuegt.

    Interessant ist das Verhaeltnis: ist die 10:00-Kerze **heute** belebter
    als die 10:00-Kerze ueblicherweise? Der Median der letzten ``sessions``
    gleichen Uhrzeiten ist der Bezug; er wird rollend gebildet und schaut
    damit nicht nach vorn.
    """
    volumen = df["volume"].astype(float)
    tageszeit = df.index.tz_convert("UTC").time

    ueblich = volumen.groupby(tageszeit).transform(
        lambda s: s.rolling(sessions, min_periods=max(5, sessions // 4)).median()
    )
    # Ein uebliches Volumen von null ist kein Bezugspunkt.
    return volumen / ueblich.where(ueblich > 0)


@dataclass(frozen=True)
class Regimeverteilung:
    """Wie sich die Kerzen auf die Schubladen verteilen - fuer den Bericht."""

    je_achse: dict[str, pd.Series]
    kombiniert: pd.Series
    unbestimmt: int
    gesamt: int

    def bericht(self, min_anteil: float = 0.01) -> str:
        zeilen = [
            f"{self.gesamt} Kerzen, davon {self.unbestimmt} ohne Regime "
            f"({self.unbestimmt / self.gesamt:.1%} - Fenstervorlauf)",
            "",
        ]
        for achse, verteilung in self.je_achse.items():
            zeilen.append(f"{achse}:")
            for auspraegung, anzahl in verteilung.items():
                zeilen.append(
                    f"  {str(auspraegung):<12} {anzahl:>8}  {anzahl / self.gesamt:>6.1%}"
                )
            zeilen.append("")

        zeilen.append("Kombiniert (Schubladen ueber 1 % der Kerzen):")
        for kombination, anzahl in self.kombiniert.items():
            anteil = anzahl / self.gesamt
            if anteil >= min_anteil:
                zeilen.append(f"  {str(kombination):<28} {anzahl:>8}  {anteil:>6.1%}")
        return "\n".join(zeilen)


def regime_spalten(
    df: pd.DataFrame,
    indicator_cfg: IndicatorConfig,
    session_cfg: SessionConfig | None = None,
    *,
    kerzen_minuten: int = 5,
    sessions: int = STANDARD_FENSTER_SESSIONS,
) -> pd.DataFrame:
    """Die drei Regime-Achsen als Spalten.

    Erwartet einen bereits mit ``compute_indicators`` vorbereiteten Rahmen
    (braucht ``atr``). ADX wird hier ueber ``common.indicators.adx``
    nachgerechnet - dieselbe Funktion wie in
    ``compute_extended_indicators``, keine zweite Implementierung.

    Ergebnis je Kerze:

    * ``vola_regime``        niedrig / mittel / hoch      (ATR-Rang)
    * ``struktur_regime``    range / uebergang / trend    (ADX-Rang)
    * ``liquiditaet_regime`` duenn / normal / rege        (relatives Volumen)
    * ``regime``             die drei zusammengesetzt, z.B. "hoch|trend|rege"

    Wo das Fenster noch nicht gefuellt ist, steht ``None`` - unbestimmt, nicht
    geraten.
    """
    validate_ohlcv(df)
    if "atr" not in df.columns:
        raise ValueError(
            "Ohne ATR-Spalte kein Volatilitaetsregime. Schick den Rahmen "
            "zuerst durch common.indicators.compute_indicators."
        )

    fenster = fenster_kerzen(kerzen_minuten, sessions)

    vola_rang = _rollender_rang(df["atr"].astype(float), fenster)
    adx_werte = adx(df, indicator_cfg.atr_period)["adx"].astype(float)
    struktur_rang = _rollender_rang(adx_werte, fenster)
    liq_rang = _rollender_rang(relatives_volumen(df, sessions), fenster)

    ergebnis = pd.DataFrame(index=df.index)
    ergebnis["vola_rang"] = vola_rang
    ergebnis["vola_regime"] = _terzil(vola_rang, ACHSEN["vola_regime"])
    ergebnis["struktur_rang"] = struktur_rang
    ergebnis["struktur_regime"] = _terzil(struktur_rang, ACHSEN["struktur_regime"])
    ergebnis["liquiditaet_rang"] = liq_rang
    ergebnis["liquiditaet_regime"] = _terzil(liq_rang, ACHSEN["liquiditaet_regime"])

    # Die Schublade. None, sobald auch nur eine Achse unbestimmt ist - eine
    # halb bestimmte Schublade waere schlimmer als gar keine.
    teile = [
        ergebnis["vola_regime"],
        ergebnis["struktur_regime"],
        ergebnis["liquiditaet_regime"],
    ]
    vollstaendig = ~pd.concat(teile, axis=1).isna().any(axis=1)
    kombiniert = pd.Series([None] * len(df), index=df.index, dtype=object)
    kombiniert[vollstaendig] = (
        teile[0][vollstaendig].astype(str)
        + "|" + teile[1][vollstaendig].astype(str)
        + "|" + teile[2][vollstaendig].astype(str)
    )
    ergebnis["regime"] = kombiniert

    return ergebnis[list(REGIME_SPALTEN)]


def verteilung(regime: pd.DataFrame) -> Regimeverteilung:
    """Wie viele Kerzen in welcher Schublade liegen."""
    je_achse = {
        achse: regime[achse].value_counts(dropna=True).sort_index()
        for achse in ACHSEN
    }
    return Regimeverteilung(
        je_achse=je_achse,
        kombiniert=regime["regime"].value_counts(dropna=True),
        unbestimmt=int(regime["regime"].isna().sum()),
        gesamt=len(regime),
    )


__all__ = [
    "ACHSEN",
    "KERZEN_JE_SESSION",
    "MIN_ANTEIL_FENSTER",
    "OBERES_TERZIL",
    "REGIME_SPALTEN",
    "STANDARD_FENSTER_SESSIONS",
    "UNTERES_TERZIL",
    "Regimeverteilung",
    "fenster_kerzen",
    "regime_spalten",
    "relatives_volumen",
    "verteilung",
]
