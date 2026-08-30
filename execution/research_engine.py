"""Eine Hypothese rechnen, eintragen und protokollieren.

Was die Vorgaengerfassung falsch machte
---------------------------------------
Sie sah aus wie eine Research-Engine und war keine:

* Sie lud ``SELECT ... FROM bars ORDER BY ts_utc`` **ohne WHERE** - also 1m-,
  5m-, 15m-, 1h- und Tageskerzen aller Instrumente in einen Topf. Der
  resultierende "Datensatz" war eine Mischung aus fuenf Zeitebenen.
* Sie rechnete mit ``point_value=20.0`` - das ist NQ. Bei MNQ sind es 2.
* Ins Protokoll schrieb sie ``**Net PnL:** \\n`` und in der Trade-Tabelle
  ``| \\ |  |`` - P&L und R-Vielfaches fehlten **buchstaeblich**, die
  f-Strings waren kaputt.
* Es gab keinen Split, keine Kosten, keinen Registereintrag. Ein Ergebnis
  ohne diese Angaben laesst sich spaeter nicht einordnen und nicht
  wiederholen.

Was hier stattdessen passiert
-----------------------------
Ein Lauf ist erst dann ein Ergebnis, wenn er **reproduzierbar** ist. Deshalb
gehoert zu jedem:

* Ein benannter Datensatz mit Hash (``dataset_hash``), Zeitraum und Zeitebene.
* Der Git-Commit, unter dem gerechnet wurde.
* Das benannte Kostenprofil.
* Ein chronologischer Split - Training und ein Block, den die Regel nicht
  gesehen hat.
* Ein Eintrag im Forschungsregister (``HYP-000xxx``).

Der p-Wert
----------
Gerechnet wird ein einfacher t-Test auf "Erwartungswert je Trade ist 0". Das
ist bewusst bescheiden: er sagt, ob die beobachtete Serie mit reinem Zufall
vertraeglich ist, und **nicht**, ob eine Kante existiert. Bei wenigen Trades
sagt er ohnehin fast nichts, und genau das steht dann auch im Protokoll.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Unter dieser Trade-Zahl wird kein Urteil gefaellt. Trefferquote und
#: Profitfaktor aus zwoelf Trades sind Rauschen mit Nachkommastellen.
MIN_TRADES_FUER_URTEIL = 30


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip() or "unbekannt"
    except Exception:  # noqa: BLE001
        return "unbekannt"


def lade_kerzen(symbol: str, timeframe: str, *, datenbank: Path | None = None):
    """Kerzen EINES Instruments und EINER Zeitebene.

    Das ``WHERE`` ist der ganze Punkt: ohne es kamen 1m-, 5m-, 15m-, 1h- und
    Tageskerzen gemeinsam heraus, chronologisch sortiert, und der Backtest
    rechnete auf einer Reihe, die es so nie gegeben hat.
    """
    from ntbridge.store import BarStore

    pfad = datenbank or (PROJECT_ROOT / "data" / "ntbridge.sqlite3")
    speicher = BarStore(pfad)
    try:
        return speicher.load_frame(symbol, timeframe)
    finally:
        speicher.close()


def _t_test(werte: list[float]) -> tuple[float | None, float | None]:
    """t-Statistik und p-Wert fuer "Mittelwert ist 0".

    Ohne scipy: die Normalverteilungsnaeherung reicht hier, und eine
    zusaetzliche Abhaengigkeit fuer eine Zahl, die ohnehin nur grob
    eingeordnet wird, waere unverhaeltnismaessig. Bei unter 30 Werten wird
    ``None`` geliefert statt einer Zahl, die niemand benutzen sollte.
    """
    import math
    import statistics

    if len(werte) < MIN_TRADES_FUER_URTEIL:
        return None, None
    mittel = statistics.fmean(werte)
    streuung = statistics.stdev(werte)
    if streuung == 0:
        return None, None
    t = mittel / (streuung / math.sqrt(len(werte)))
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return t, p


def rechne_hypothese(
    *,
    strategie_name: str,
    begruendung: str,
    parameter: dict[str, Any] | None = None,
    symbol: str = "MNQ",
    timeframe: str | None = None,
    ins_register: bool = True,
) -> dict[str, Any]:
    """Ein vollstaendiger, reproduzierbarer Lauf."""
    from backtest.compare import prepare_split
    from backtest.engine import Backtester, CostModel
    from backtest.kosten import profil_aus_config
    from backtest.research_register import ResearchRegister, hash_dataframe
    from backtest.splits import SplitConfig, split_data
    from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
    from common.config import Config
    import backtest.metrics as bm

    if strategie_name not in STRATEGY_LIBRARY:
        raise ValueError(
            f"Unbekannte Strategie {strategie_name!r}. Bekannt: "
            + ", ".join(sorted(STRATEGY_LIBRARY))
        )

    config = Config.load(PROJECT_ROOT / "config.yaml")
    timeframe = timeframe or config.ideas.timeframe
    df = lade_kerzen(symbol, timeframe)
    if df.empty:
        raise ValueError(
            f"Keine {timeframe}-Kerzen fuer {symbol} in ntbridge.sqlite3."
        )

    profil = profil_aus_config(config.backtest)
    tester = Backtester(
        config.market,
        config.indicators,
        CostModel.aus_profil(
            profil,
            tick_size=config.market.tick_size,
            point_value=config.market.point_value,
        ),
    )
    strategie = build_strategy(strategie_name, **(parameter or {}))

    split = split_data(df, SplitConfig(mode="fraction", in_sample_fraction=0.7))
    vorbereitet_is, vorbereitet_oos = prepare_split(tester, split)

    lauf_is = tester.run(vorbereitet_is, strategie, label="training",
                         already_prepared=True)
    lauf_oos = tester.run(vorbereitet_oos, strategie, label="out-of-sample",
                          already_prepared=True)

    kennzahlen_is = bm.compute_metrics(lauf_is, initial_capital=10000)
    kennzahlen_oos = bm.compute_metrics(lauf_oos, initial_capital=10000)

    pnl_is = [t.pnl for t in lauf_is.trades]
    t_wert, p_wert = _t_test(pnl_is)

    if t_wert is None:
        urteil = "UNENTSCHIEDEN"
        urteilsgrund = (
            f"Nur {len(pnl_is)} Trades im Trainingsblock - unter "
            f"{MIN_TRADES_FUER_URTEIL} wird kein Urteil gefaellt."
        )
    elif p_wert is not None and p_wert < 0.05 and kennzahlen_is.total_pnl > 0:
        urteil = "KANDIDAT"
        urteilsgrund = (
            f"p = {p_wert:.4f} im Training. Das ist KEINE Bestaetigung - "
            "es heisst nur, dass die Serie schwer mit reinem Zufall zu "
            "erklaeren ist. Ohne Mehrfachtestkorrektur und ohne "
            "Confirmation auf einem unberuehrten Block bleibt es eine "
            "Vermutung."
        )
    else:
        urteil = "VERWORFEN"
        urteilsgrund = (
            f"p = {p_wert:.4f}, Netto-P&L {kennzahlen_is.total_pnl:.2f} USD "
            "im Training."
        ) if p_wert is not None else "Kein Effekt messbar."

    ergebnis: dict[str, Any] = {
        "strategie": strategie_name,
        "begruendung": begruendung,
        "parameter": dict(strategie.params),
        "symbol": symbol,
        "timeframe": timeframe,
        "kerzen": len(df),
        "zeitraum": (df.index[0], df.index[-1]),
        "kostenprofil": profil.name,
        "kosten_je_seite": profil.summe_je_seite,
        "kosten_ist_annahme": profil.ist_annahme,
        "git_commit": _git_commit(),
        "dataset_hash": hash_dataframe(df),
        "split": "70/30 chronologisch",
        "training": kennzahlen_is,
        "out_of_sample": kennzahlen_oos,
        "t_wert": t_wert,
        "p_wert": p_wert,
        "urteil": urteil,
        "urteilsgrund": urteilsgrund,
        "trades_training": lauf_is.trades,
        "trades_oos": lauf_oos.trades,
    }

    if ins_register:
        register = ResearchRegister(PROJECT_ROOT / "data" / "research_register.sqlite3")
        eintrag = register.register(
            title=f"{strategie_name} auf {symbol}/{timeframe}",
            description=begruendung,
            verdict=urteil,
            timeframe=timeframe,
            dataset_name=f"ntbridge:{symbol}:{timeframe}",
            dataset_hash=ergebnis["dataset_hash"],
            git_commit=ergebnis["git_commit"],
            config_hash=profil.name,
            sample_size_train=kennzahlen_is.trades,
            sample_size_oos=kennzahlen_oos.trades,
            p_value_raw=p_wert if p_wert is not None else 1.0,
            conditions={
                "strategie": strategie_name,
                "parameter": dict(strategie.params),
                "split": "70/30 chronologisch",
                "kostenprofil": profil.name,
            },
            metrics={
                "training": kennzahlen_is.to_dict(),
                "out_of_sample": kennzahlen_oos.to_dict(),
            },
            notes=urteilsgrund,
        )
        ergebnis["hypothese_id"] = eintrag.hypothesis_id

    return ergebnis


def schreibe_protokoll(ergebnis: dict[str, Any], ziel: Path | None = None) -> Path:
    """Ein Protokoll, aus dem sich der Lauf wiederholen laesst."""
    zeitstempel = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    kennung = ergebnis.get("hypothese_id", ergebnis["strategie"])
    ziel = ziel or (
        PROJECT_ROOT / "backtest_results" / f"protokoll_{kennung}_{zeitstempel}.md"
    )
    ziel.parent.mkdir(parents=True, exist_ok=True)

    training = ergebnis["training"]
    oos = ergebnis["out_of_sample"]
    von, bis = ergebnis["zeitraum"]

    def zahl(wert, stellen=2, einheit="") -> str:
        if wert is None:
            return "nicht bestimmbar"
        return f"{wert:.{stellen}f}{einheit}"

    zeilen: list[str] = [
        f"# Forschungsprotokoll {kennung}",
        "",
        f"**Erzeugt:** {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}  ",
        f"**Strategie:** `{ergebnis['strategie']}`  ",
        f"**Git-Commit:** `{ergebnis['git_commit']}`  ",
        f"**Urteil:** **{ergebnis['urteil']}**",
        "",
        "## Hypothese",
        "",
        ergebnis["begruendung"],
        "",
        "## Datengrundlage",
        "",
        "| | |",
        "|---|---|",
        f"| Instrument | {ergebnis['symbol']} |",
        f"| Zeitebene | {ergebnis['timeframe']} |",
        f"| Kerzen | {ergebnis['kerzen']} |",
        f"| Zeitraum | {von:%Y-%m-%d %H:%M} bis {bis:%Y-%m-%d %H:%M} UTC |",
        f"| Datensatz-Hash | `{ergebnis['dataset_hash']}` |",
        f"| Aufteilung | {ergebnis['split']} |",
        f"| Kostenprofil | {ergebnis['kostenprofil']} "
        f"({ergebnis['kosten_je_seite']:.2f} USD je Seite"
        + (", **Annahme**)" if ergebnis["kosten_ist_annahme"] else ", belegt)")
        + " |",
        "",
        "## Parameter",
        "",
        "| Parameter | Wert |",
        "|---|---|",
    ]
    for name, wert in sorted(ergebnis["parameter"].items()):
        zeilen.append(f"| `{name}` | {wert} |")

    zeilen += [
        "",
        "## Ergebnis",
        "",
        "| Kennzahl | Training (70 %) | Out-of-Sample (30 %) |",
        "|---|---:|---:|",
        f"| Trades | {training.trades} | {oos.trades} |",
        f"| Trefferquote | {zahl(training.win_rate * 100, 1, ' %')} | "
        f"{zahl(oos.win_rate * 100, 1, ' %')} |",
        f"| Netto-P&L | {zahl(training.total_pnl, 2, ' USD')} | "
        f"{zahl(oos.total_pnl, 2, ' USD')} |",
        f"| Erwartungswert je Trade | {zahl(training.expectancy, 2, ' USD')} | "
        f"{zahl(oos.expectancy, 2, ' USD')} |",
        f"| Profitfaktor | {zahl(training.profit_factor)} | "
        f"{zahl(oos.profit_factor)} |",
        f"| Groesster Rueckgang | {zahl(training.max_drawdown, 2, ' USD')} | "
        f"{zahl(oos.max_drawdown, 2, ' USD')} |",
        f"| Verluste in Folge | {training.max_consecutive_losses} | "
        f"{oos.max_consecutive_losses} |",
        "",
        "## Statistische Einordnung",
        "",
        f"- t-Wert: {zahl(ergebnis['t_wert'], 3)}",
        f"- p-Wert (roh, Training): {zahl(ergebnis['p_wert'], 4)}",
        "",
        ergebnis["urteilsgrund"],
        "",
        "> Der p-Wert prueft ausschliesslich, ob der Erwartungswert je Trade",
        "> mit 0 vertraeglich ist. Er ist **nicht** mehrfachtestkorrigiert.",
        "> Wer mehrere Strategien durchprobiert, findet zwangslaeufig eine mit",
        "> p < 0,05 - deshalb ist ein Treffer hier ein Kandidat und kein",
        "> Ergebnis.",
        "",
        "## Trades (Training)",
        "",
    ]

    zeilen += _trade_tabelle(ergebnis["trades_training"])

    ziel.write_text(chr(10).join(zeilen) + chr(10), encoding="utf-8")
    return ziel


def _trade_tabelle(trades, hoechstens: int = 100) -> list[str]:
    """Eine Trade-Tabelle, in der jede Spalte auch wirklich gefuellt ist.

    Die Vorgaengerfassung schrieb hier eine Tabelle mit leeren Zellen - die f-Strings waren
    kaputt, P&L und R-Vielfaches fehlten buchstaeblich in der Datei. Deshalb
    wird jeder Wert einzeln geholt und formatiert, und Fehlendes wird als
    ``-`` ausgewiesen statt als leere Zelle.
    """
    if not trades:
        return ["Keine Trades im Trainingsblock."]

    zeilen = [
        "| Einstieg | Ausstieg | Richtung | Einstieg | Ausstieg | Punkte "
        "| Kommission | P&L USD | Kerzen | Grund |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for trade in trades[:hoechstens]:
        richtung = "long" if trade.direction > 0 else "short"
        zeilen.append(
            "| {ein:%Y-%m-%d %H:%M} | {aus:%Y-%m-%d %H:%M} | {richtung} "
            "| {ekurs:.2f} | {akurs:.2f} | {punkte:+.2f} | {komm:.2f} "
            "| {pnl:+.2f} | {kerzen} | {grund} |".format(
                ein=trade.entry_time,
                aus=trade.exit_time,
                richtung=richtung,
                ekurs=trade.entry_price,
                akurs=trade.exit_price,
                punkte=trade.gross_points,
                komm=trade.commission,
                pnl=trade.pnl,
                kerzen=trade.bars_held,
                grund=trade.exit_reason,
            )
        )
    if len(trades) > hoechstens:
        zeilen.append("")
        zeilen.append(f"... und {len(trades) - hoechstens} weitere Trades.")
    return zeilen


def run_hypothesis(
    hypothesis_id: str, strategy_name: str, reason: str, params: dict
) -> str:
    """Rueckwaertskompatibler Einstieg fuer ``POST /api/research/run``."""
    ergebnis = rechne_hypothese(
        strategie_name=strategy_name, begruendung=reason, parameter=params
    )
    return str(schreibe_protokoll(ergebnis))


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "vwap_reversion"
    ergebnis = rechne_hypothese(
        strategie_name=name,
        begruendung=f"Kommandozeilenlauf fuer {name}.",
    )
    pfad = schreibe_protokoll(ergebnis)
    print(f"{ergebnis['urteil']}: {ergebnis['urteilsgrund']}")
    print(f"Protokoll: {pfad}")
