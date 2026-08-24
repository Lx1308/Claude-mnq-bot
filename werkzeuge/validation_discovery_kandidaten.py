"""Validation-Phase: alle sechs Discovery-Kandidaten, gleich behandelt.

WOZU
----
Der vollstaendige 20x5-Discovery-Lauf (24.08.2026,
``docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md``) prueft 239 Hypothesen und
findet 6 Gruppen, die die Bonferroni-Korrektur unterschreiten. Nach
Masterplan G (Discovery -> Validation -> Confirmation -> Monitoring) ist das
eine Kandidatenliste, kein Befund. Dieses Skript ist die Validation-Phase:
alle sechs werden auf einem Block getestet, den Discovery nie gesehen hat -
KEINE Vorauswahl, kein Ausschluss wegen "klingt plausibler" oder "klingt
zirkulaerer". Jede der vier zugrundeliegenden (Strategie, Faktor)-Kombinationen
zaehlt gleich; die Bonferroni-Korrektur dieser Phase skaliert mit der Zahl der
hier tatsaechlich auswertbaren Gruppen (>= 20 Trades), nicht mit einer
Teilmenge.

Ergaenzend zu den frueheren informellen Pruefungen aus der letzten Sitzung
(``werkzeuge/rsi_zirkularitaet.py``, ``werkzeuge/validation_vwap_trend_rsi.py``,
Bericht ``docs/VALIDATION_RSI_TERZIL_2026-08-24.md``): jene Laeufe waren
Einzelfall-Pruefungen auf einem Block, der teilweise mit dem Discovery-Pool
ueberlappte. Dieses Skript ersetzt sie fuer die formale Validation-Phase durch
eine sauber abgetrennte, fuer ALLE sechs Kandidaten einheitliche Pruefung -
siehe ``backtest/splits.py::split_data_three_way`` fuer die neue Dreiteilung.

DIE NEUE DREITEILUNG
---------------------
``split_data_three_way`` (backtest/splits.py, neu) teilt den bisherigen
Out-of-Sample-Rest (30 % nach der 70-%-Trainingsgrenze) ein zweites Mal:
``backtest.split.validation_fraction`` (config.yaml, Vorgabe 0.5) davon wird
Validation, der Rest bleibt Out-of-Sample - weiterhin unberuehrt und
einmalig fuer die Confirmation-Phase.

    0 % ------------- 70 % --------- 85 % ------------------- 100 %
    TRAINING            | VALIDATION  |      OUT-OF-SAMPLE
    (Discovery, bereits  | (dieses     |      (weiterhin unberuehrt,
     verbraucht, gepoolt)| Skript)     |       einmalig fuer Confirmation)

Die 70-%-Grenze ist UNVERAENDERT dieselbe wie im Discovery-Lauf - sie wird
durch die Dreiteilung nicht verschoben (siehe Test
``test_dreiwege_split_traingrenze_ist_dieselbe_wie_beim_zweiwege_split``).
Der Validation-Block (70-85 %) ist damit ein Block, auf dem noch nie
irgendeine Kennzahl berechnet wurde - anders als beim Ansatz der letzten
Sitzung, der einen Teil des bereits gepoolten Trainingsblocks wiederverwendet
hatte.

EINGEFRORENE HYPOTHESEN
------------------------
Faktordefinition, Terzilgrenzen und Strategie sind exakt aus dem
Discovery-Lauf uebernommen - NICHTS wird auf dem Validation-Block neu
angepasst. Eine neu bestimmte Grenze wuerde die Hypothese neu anpassen statt
sie zu pruefen.

WALK-FORWARD-KONSISTENZ
------------------------
Zusaetzlich zum gepoolten Validation-Ergebnis wird der Validation-Block in
mehrere chronologische Unterfenster geteilt (kein Fitting je Fenster - alle
Parameter bleiben eingefroren, deshalb keine Wiederverwendung von
``backtest.splits.walk_forward_windows``, die fuer Trainings-/Testfenster-Paare
mit Refitting gedacht ist). Masterplan J verlangt "Plateaus, keine Spitzen":
ein Effekt, der nur in einem einzelnen Unterfenster steckt, ist ein Fund in
einer Marktphase, keine robuste Kante.

KEINE MAKRO-/NEWS-FAKTOREN
----------------------------
Dieser Lauf enthaelt wie der Discovery-Lauf keine Makro- oder Newsdaten -
Begruendung in CODE_CHAT_KONTEXT.md Abschnitt 27/28 (keine Quelle mit
Vintage-/availability_time-Modellierung verfuegbar). Die Lookahead-Pflicht
fuer availability_time betrifft diesen Lauf deshalb nicht; sie gilt erst,
wenn eine Makro-/News-Spalte hinzukommt (Masterplan K).

Aufruf (braucht PYTHONPATH, da ausserhalb der CLI):
    $env:PYTHONPATH = (Get-Location).Path
    .venv\\Scripts\\python.exe werkzeuge\\validation_discovery_kandidaten.py
"""

from dataclasses import dataclass

import pandas as pd

from backtest.engine import Backtester, BacktestResult, CostModel
from backtest.kosten import profil_aus_config
from backtest.research import (
    Discoverylauf,
    Faktorergebnis,
    baue_faktor_perzentil,
    pruefe_faktor,
)
from backtest.splits import assert_validation_only, split_data_three_way
from backtest.strategies.library import build_strategy
from common.config import Config
from common.instruments import get_instrument
from ideas.pipeline import vorbereiten

NAMEN = ["1 niedrig", "2 mittel", "3 hoch"]

# Eingefroren aus dem Discovery-Lauf vom 24.08.2026
# (docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md) - NICHT auf dem
# Validation-Block neu bestimmt.
GRENZEN_RSI = [45.902, 56.596]
GRENZEN_STOCHASTIK = [35.858, 71.374]


@dataclass(frozen=True)
class DiscoveryKandidat:
    """Eine der sechs Gruppen, die den Discovery-Lauf ueberstanden haben."""

    strategie: str
    faktor_name: str
    faktor_spalte: str
    grenzen: list[float]
    auspraegung: str          # welche der drei Terzil-Gruppen war der Fund
    discovery_trades: int
    discovery_brutto: float
    discovery_t: float


# Die sechs Kandidaten - unveraendert aus der Tabelle in
# docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md. Keine Vorauswahl, keine
# Ausschluesse: alle sechs gehen in dieselbe Pruefung.
KANDIDATEN = [
    DiscoveryKandidat("flag_breakout", "RSI-Terzil", "rsi", GRENZEN_RSI,
                       "2 mittel", 35, -12.773, -8.97),
    DiscoveryKandidat("rsi_mean_reversion", "RSI-Terzil", "rsi", GRENZEN_RSI,
                       "2 mittel", 331, 13.112, 6.87),
    DiscoveryKandidat("rsi_mean_reversion", "RSI-Terzil", "rsi", GRENZEN_RSI,
                       "3 hoch", 1705, -3.812, -4.81),
    DiscoveryKandidat("vwap_trend", "RSI-Terzil", "rsi", GRENZEN_RSI,
                       "2 mittel", 1435, -3.199, -4.74),
    DiscoveryKandidat("rsi_mean_reversion", "Stochastik-Terzil", "stoch_k", GRENZEN_STOCHASTIK,
                       "2 mittel", 694, 5.407, 4.42),
    DiscoveryKandidat("rsi_mean_reversion", "Stochastik-Terzil", "stoch_k", GRENZEN_STOCHASTIK,
                       "3 hoch", 1462, -3.841, -4.30),
]


def lade_und_teile():
    cfg = Config.load("config.yaml")
    profil = profil_aus_config(cfg.backtest)
    kosten = CostModel.aus_profil(
        profil, tick_size=cfg.market.tick_size, point_value=cfg.market.point_value
    )
    bt = Backtester(cfg.market, cfg.indicators, kosten)

    roh = pd.read_csv("data/DUKA_5m.csv", parse_dates=["timestamp"], index_col="timestamp")
    if roh.index.tz is None:
        roh.index = roh.index.tz_localize("UTC")

    split = split_data_three_way(roh, cfg.backtest.split)
    print(split.describe())
    print()

    instrument = get_instrument(cfg.market.product)
    # Indikatoren ueber Training + Validation gemeinsam (Invariante 5) -
    # der Validation-Block darf keine isoliert vorbereiteten, warmlaufenden
    # ersten Kerzen haben.
    training_und_validation = pd.concat([split.train, split.validation])
    vorbereitet = vorbereiten(training_und_validation, instrument, cfg)
    assert_validation_only(vorbereitet, split)

    validation = vorbereitet.iloc[len(split.train):]
    return cfg, bt, vorbereitet, validation, split


@dataclass(frozen=True)
class WalkForwardBefund:
    zeilen: str
    auswertbare_fenster: int
    gleiches_vorzeichen: int


def walk_forward_konsistenz(
    validation: pd.DataFrame,
    ergebnis: BacktestResult,
    faktor_spalte: str,
    grenzen: list[float],
    auspraegung: str,
    *,
    erwartet_positiv: bool,
    fenster: int,
    punktwert: float,
) -> WalkForwardBefund:
    """Teilt den Validation-Block in ``fenster`` gleich lange Unterfenster.

    Kein Fitting je Fenster - Faktor und Grenzen bleiben eingefroren. Meldet,
    in wie vielen Fenstern die Auspraegung ueberhaupt genug Trades hat und in
    wie vielen davon das Vorzeichen mit dem urspruenglichen Discovery-Fund
    (``erwartet_positiv``) uebereinstimmt (Masterplan J: Plateaus, keine
    Spitzen - ein Effekt aus einem einzelnen Unterfenster ist keine robuste
    Kante).
    """
    grenze_zeiten = [validation.index[int(len(validation) * i / fenster)] for i in range(fenster)]
    grenze_zeiten.append(validation.index[-1] + pd.Timedelta(seconds=1))

    faktor = baue_faktor_perzentil(faktor_spalte, grenzen, NAMEN)
    auswertbar = 0
    gleiches_vorzeichen = 0
    zeilen = []
    for i in range(fenster):
        fenster_trades = [
            t for t in ergebnis.trades
            if grenze_zeiten[i] <= pd.Timestamp(t.entry_time) < grenze_zeiten[i + 1]
        ]
        teilergebnis = BacktestResult(
            strategy_name=ergebnis.strategy_name, strategy_description="",
            trades=fenster_trades, equity=pd.Series(dtype=float), bars=0, label="fenster",
        )
        fg = pruefe_faktor(teilergebnis, validation, faktor_spalte, faktor, punktwert=punktwert)
        gruppe = next((g for g in fg.gruppen if g.auspraegung == auspraegung), None)
        if gruppe is None or not gruppe.genug_daten:
            trades_n = gruppe.trades if gruppe else 0
            zeilen.append(f"    Fenster {i + 1}: {trades_n} Trades -> zu wenig Daten")
            continue
        auswertbar += 1
        passt = (gruppe.brutto_punkte_je_trade > 0) == erwartet_positiv
        gleiches_vorzeichen += int(passt)
        zeilen.append(
            f"    Fenster {i + 1}: {gruppe.trades:>4} Trades  "
            f"brutto {gruppe.brutto_punkte_je_trade:>+7.3f} Pkt  "
            f"({'passt zu Discovery' if passt else 'widerspricht Discovery'})"
        )
    return WalkForwardBefund(zeilen="\n".join(zeilen), auswertbare_fenster=auswertbar,
                              gleiches_vorzeichen=gleiches_vorzeichen)


def hauptlauf() -> None:
    cfg, bt, vorbereitet, validation, split = lade_und_teile()
    print(f"Validation-Block: {len(validation)} Kerzen\n")

    # Jede benoetigte Strategie genau einmal laufen lassen, auch wenn
    # mehrere Kandidaten dieselbe Strategie mit unterschiedlichen Faktoren
    # betreffen (rsi_mean_reversion: RSI- und Stochastik-Terzil).
    strategien = sorted({k.strategie for k in KANDIDATEN})
    ergebnisse: dict[str, BacktestResult] = {}
    for name in strategien:
        ergebnisse[name] = bt.run(validation, build_strategy(name), already_prepared=True)
        print(f"{name}: {len(ergebnisse[name].trades)} Trades im Validation-Block "
              f"(Discovery-Trainingsteil zum Vergleich: siehe DISCOVERY_VOLLSTAENDIG_2026-08-24.md)")
    print()

    # Jede (Strategie, Faktor)-Kombination genau einmal auswerten - liefert
    # alle drei Terzil-Gruppen, nicht nur die urspruenglich markierte.
    kombinationen: dict[tuple[str, str], Faktorergebnis] = {}
    for k in KANDIDATEN:
        schluessel = (k.strategie, k.faktor_name)
        if schluessel in kombinationen:
            continue
        faktor = baue_faktor_perzentil(k.faktor_spalte, k.grenzen, NAMEN)
        kombinationen[schluessel] = pruefe_faktor(
            ergebnisse[k.strategie], validation, k.faktor_name, faktor,
            punktwert=cfg.market.point_value,
        )

    lauf = Discoverylauf(ergebnisse=list(kombinationen.values()))

    print("=" * 100)
    print("VOLLSTAENDIGES ERGEBNIS ALLER GRUPPEN (nicht nur die sechs Discovery-Treffer):")
    print("=" * 100)
    print(lauf.bericht())
    print("=" * 100)
    print(lauf.statistikbericht())
    print()

    print("=" * 100)
    print("VERGLEICH: Discovery-Lauf gegen Validation-Block, alle sechs Kandidaten gleich behandelt")
    print("=" * 100)
    signifikante_schluessel = {
        (erg.strategie, erg.faktor, gr.auspraegung)
        for erg, gr in lauf.signifikante()
    }
    for k in KANDIDATEN:
        fg = kombinationen[(k.strategie, k.faktor_name)]
        gruppe = next((g for g in fg.gruppen if g.auspraegung == k.auspraegung), None)
        vorzeichen_original = "positiv" if k.discovery_brutto > 0 else "negativ"
        print(f"\n{k.strategie} / {k.faktor_name} / {k.auspraegung}:")
        print(f"  Discovery : {k.discovery_trades:>5} Trades  brutto {k.discovery_brutto:>+8.3f} Pkt  "
              f"t={k.discovery_t:>+6.2f}  ({vorzeichen_original})")
        if gruppe is None or not gruppe.genug_daten:
            trades_n = gruppe.trades if gruppe else 0
            print(f"  Validation: {trades_n:>5} Trades  -> zu wenig Daten (Schwelle 20)")
            continue
        t_wert = gruppe.t_statistik
        vorzeichen_haelt = (gruppe.brutto_punkte_je_trade > 0) == (k.discovery_brutto > 0)
        bonferroni_besteht = (k.strategie, k.faktor_name, k.auspraegung) in signifikante_schluessel
        print(f"  Validation: {gruppe.trades:>5} Trades  brutto {gruppe.brutto_punkte_je_trade:>+8.3f} Pkt  "
              f"t={t_wert:>+6.2f}" if t_wert is not None else
              f"  Validation: {gruppe.trades:>5} Trades  brutto {gruppe.brutto_punkte_je_trade:>+8.3f} Pkt")
        print(f"  -> Vorzeichen haelt: {'JA' if vorzeichen_haelt else 'NEIN'}   "
              f"Bonferroni (diese Phase) bestanden: {'JA' if bonferroni_besteht else 'NEIN'}")

        # Walk-Forward-Konsistenz nur, wenn genug Daten fuer sinnvolle
        # Unterfenster da sind (Schwelle: mindestens 3x die Mindestgruppengroesse).
        if gruppe.trades >= 60:
            fenster_n = 3
            befund = walk_forward_konsistenz(
                validation, ergebnisse[k.strategie], k.faktor_spalte, k.grenzen, k.auspraegung,
                erwartet_positiv=(k.discovery_brutto > 0), fenster=fenster_n,
                punktwert=cfg.market.point_value,
            )
            print(f"  Walk-Forward-Konsistenz ({fenster_n} Unterfenster, eingefrorene Parameter):")
            print(befund.zeilen)
            print(f"    -> {befund.gleiches_vorzeichen}/{befund.auswertbare_fenster} auswertbare "
                  "Fenster stimmen im Vorzeichen mit Discovery ueberein.")
        else:
            print("  Walk-Forward-Konsistenz: uebersprungen, zu wenig Trades fuer sinnvolle Unterfenster.")

    print()
    print("=" * 100)
    print("MULTIPLE-TESTING-TRICHTER (Transparenz ueber alle Phasen)")
    print("=" * 100)
    print("  Discovery (20x5-Lauf, 24.08.2026)         : 239 Hypothesen geprueft, 6 ueberstehen Bonferroni")
    print(f"  Validation (dieser Lauf)                  : {lauf.gepruefte_hypothesen} Hypothesen geprueft "
          f"(alle auswertbaren Gruppen der 4 betroffenen Faktor-Strategie-Kombinationen),")
    print(f"                                               {len(lauf.signifikante())} ueberstehen die "
          f"fuer DIESE Phase korrigierte Schwelle {lauf.bonferroni_schwelle:.6f}")
    print("  Von den urspruenglich 6 Discovery-Kandidaten ueberstehen auf dem Validation-Block:",
          sum(1 for k in KANDIDATEN
              if (k.strategie, k.faktor_name, k.auspraegung) in signifikante_schluessel))


if __name__ == "__main__":
    hauptlauf()
