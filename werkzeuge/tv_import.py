"""TradingView-Ergebnisse einlesen und gegen den lokalen Lauf halten.

Der Ablauf, den Laurin sich vorgenommen hat
-------------------------------------------
1. ``werkzeuge/pine_export.py`` erzeugt aus einer Strategie ein Pine-Skript.
2. TradingView rechnet es im Deep-Backtesting ueber rund 2 Mio. Kerzen.
3. Der Strategy Tester exportiert die **List of Trades** als CSV.
4. Dieses Werkzeug liest sie, rechnet dieselben Kennzahlen wie
   ``backtest/metrics.py`` und stellt sie neben den lokalen Lauf.

Warum der Vergleich und nicht nur das TradingView-Ergebnis
----------------------------------------------------------
Weil eine Uebereinstimmung die eigentliche Information ist. Stimmen beide
Laeufe auf dem **gemeinsamen** Zeitraum ueberein, ist die Pine-Fassung
nachweislich dieselbe Strategie - und erst dann sagt das Ergebnis auf den
uebrigen 2 Mio. Kerzen etwas aus. Weichen sie ab, misst TradingView etwas
anderes, und jede Schlussfolgerung daraus waere ueber eine fremde Strategie.

Ein frueherer Anlauf (``research/tradingview/tv_import.py``, von Antigravity
gebaut und inzwischen geloescht) hat TradingView-Exporte **gar nicht
ausgewertet**, sondern feste Werte zurueckgegeben - ``profit_factor = 1.2``,
``win_rate = 0.45`` - und darauf Urteile wie ``LIVE_SIM_READY`` gefaellt. Das
ist der Grund, warum hier jede Zahl aus der Datei kommt und fehlende Angaben
``None`` bleiben.

Was TradingView liefert, das der lokale Lauf nicht hat
------------------------------------------------------
``Run-up`` und ``Drawdown`` je Trade - das sind MFE und MAE. Der lokale
Ausfuehrungsspeicher laesst beide bewusst leer, weil sie den Kursverlauf
waehrend des Trades brauchen. Von hier kommen sie mit.

Aufruf
------
    .venv\\Scripts\\python.exe werkzeuge\\tv_import.py trades.csv
    .venv\\Scripts\\python.exe werkzeuge\\tv_import.py trades.csv --strategie vwap_reversion
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: Spaltennamen, die TradingView je nach Sprache und Version verwendet.
#: Zugeordnet wird auf unsere internen Namen. Was sich nicht zuordnen laesst,
#: wird gemeldet - nicht stillschweigend ignoriert.
SPALTEN_ALIASE: dict[str, tuple[str, ...]] = {
    "nummer": ("trade #", "trade", "nr", "#"),
    "art": ("type", "typ"),
    "signal": ("signal",),
    "zeitpunkt": ("date/time", "datum/zeit", "date", "time"),
    "preis": ("price usd", "price", "preis usd", "preis"),
    "menge": ("contracts", "quantity", "kontrakte"),
    "pnl": ("profit usd", "p&l usd", "profit", "gewinn usd"),
    "pnl_prozent": ("profit %", "p&l %", "gewinn %"),
    "runup": ("run-up usd", "run up usd", "runup usd"),
    "drawdown": ("drawdown usd", "drawdown"),
}


@dataclass
class TvTrade:
    """Ein Trade aus dem TradingView-Export.

    TradingView schreibt zwei Zeilen je Trade (Einstieg und Ausstieg); hier
    sind sie bereits zusammengefuehrt.
    """

    nummer: int
    richtung: str
    einstieg_utc: datetime | None
    einstiegskurs: float | None
    ausstieg_utc: datetime | None
    ausstiegskurs: float | None
    menge: float
    pnl_usd: float | None
    mfe_usd: float | None = None
    mae_usd: float | None = None


@dataclass
class TvBericht:
    trades: list[TvTrade] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    # -- Kennzahlen, gerechnet wie in backtest/metrics.py ------------------

    def kennzahlen(self) -> dict[str, Any]:
        mit_pnl = [t for t in self.trades if t.pnl_usd is not None]
        if not mit_pnl:
            return {
                "trades": 0,
                "hinweis": "Keine Trades mit P&L in der Datei.",
            }

        gewinne = [t.pnl_usd for t in mit_pnl if t.pnl_usd > 0]
        verluste = [t.pnl_usd for t in mit_pnl if t.pnl_usd < 0]
        gesamt = sum(t.pnl_usd for t in mit_pnl)

        summe_verluste = abs(sum(verluste))
        mfe = [t.mfe_usd for t in mit_pnl if t.mfe_usd is not None]
        mae = [t.mae_usd for t in mit_pnl if t.mae_usd is not None]

        return {
            "trades": len(mit_pnl),
            "gewinner": len(gewinne),
            "verlierer": len(verluste),
            "trefferquote": len(gewinne) / len(mit_pnl),
            "netto_pnl_usd": gesamt,
            # None statt 0, wenn es keinen Verlusttrade gibt: ein
            # Profitfaktor ist dann nicht definiert und nicht "unendlich gut".
            "profitfaktor": (sum(gewinne) / summe_verluste) if summe_verluste else None,
            "erwartungswert_usd": gesamt / len(mit_pnl),
            "groesster_gewinn": max(gewinne, default=None),
            "groesster_verlust": min(verluste, default=None),
            # MFE/MAE liefert der lokale Lauf nicht - sie brauchen den
            # Kursverlauf waehrend des Trades. Von hier kommen sie mit.
            "mfe_median_usd": statistics.median(mfe) if mfe else None,
            "mae_median_usd": statistics.median(mae) if mae else None,
            "zeitraum": (
                (min(t.einstieg_utc for t in mit_pnl if t.einstieg_utc),
                 max(t.ausstieg_utc for t in mit_pnl if t.ausstieg_utc))
                if any(t.einstieg_utc for t in mit_pnl) else None
            ),
        }


def _kopf_zuordnen(kopf: list[str]) -> tuple[dict[str, int], list[str]]:
    zuordnung: dict[str, int] = {}
    normalisiert = [(spalte or "").strip().lower() for spalte in kopf]
    for intern, aliase in SPALTEN_ALIASE.items():
        for position, spalte in enumerate(normalisiert):
            if spalte in aliase or any(spalte.startswith(a) for a in aliase):
                zuordnung[intern] = position
                break
    fehlend = [
        name for name in ("art", "zeitpunkt", "preis")
        if name not in zuordnung
    ]
    return zuordnung, fehlend


def _zahl(text: str | None) -> float | None:
    """TradingView schreibt Tausenderpunkte und Prozentzeichen mit."""
    if text is None:
        return None
    bereinigt = (
        str(text).replace("−", "-").replace("%", "").replace("$", "")
        .replace(" ", "").replace(" ", "").replace(",", "")
    )
    if not bereinigt or bereinigt in ("-", "n/a", "na"):
        return None
    try:
        return float(bereinigt)
    except ValueError:
        return None


def _zeitpunkt(text: str | None) -> datetime | None:
    if not text:
        return None
    for muster in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                   "%d.%m.%Y %H:%M", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(str(text).strip(), muster)
        except ValueError:
            continue
    return None


def lies_tradingview(pfad: Path) -> TvBericht:
    """Die "List of Trades"-CSV einlesen.

    TradingView schreibt zwei Zeilen je Trade. Die Einstiegszeile traegt
    ``Entry long``/``Entry short``, die Ausstiegszeile ``Exit long``/
    ``Exit short`` samt P&L, Run-up und Drawdown.
    """
    bericht = TvBericht()
    text = pfad.read_text(encoding="utf-8-sig", errors="replace")
    trenner = ";" if text.count(";") > text.count(",") else ","
    zeilen = list(csv.reader(text.splitlines(), delimiter=trenner))

    if not zeilen:
        bericht.warnungen.append("Datei ist leer.")
        return bericht

    zuordnung, fehlend = _kopf_zuordnen(zeilen[0])
    if fehlend:
        bericht.warnungen.append(
            "Diese Spalten fehlen im Export: " + ", ".join(fehlend)
            + ". Erwartet wird die 'List of Trades' aus dem Strategy Tester."
        )
        return bericht

    def feld(zeile: list[str], name: str) -> str | None:
        position = zuordnung.get(name)
        if position is None or position >= len(zeile):
            return None
        return zeile[position]

    offen: dict[int, TvTrade] = {}
    for zeile in zeilen[1:]:
        if not any(z.strip() for z in zeile):
            continue
        art = (feld(zeile, "art") or "").strip().lower()
        nummer = int(_zahl(feld(zeile, "nummer")) or len(offen) + 1)
        richtung = "long" if "long" in art else "short" if "short" in art else "?"

        if art.startswith("entry") or art.startswith("einstieg"):
            offen[nummer] = TvTrade(
                nummer=nummer,
                richtung=richtung,
                einstieg_utc=_zeitpunkt(feld(zeile, "zeitpunkt")),
                einstiegskurs=_zahl(feld(zeile, "preis")),
                ausstieg_utc=None,
                ausstiegskurs=None,
                menge=_zahl(feld(zeile, "menge")) or 1.0,
                pnl_usd=None,
            )
        elif art.startswith("exit") or art.startswith("ausstieg"):
            trade = offen.get(nummer)
            if trade is None:
                bericht.warnungen.append(
                    f"Ausstieg fuer Trade {nummer} ohne zugehoerigen Einstieg."
                )
                continue
            trade.ausstieg_utc = _zeitpunkt(feld(zeile, "zeitpunkt"))
            trade.ausstiegskurs = _zahl(feld(zeile, "preis"))
            trade.pnl_usd = _zahl(feld(zeile, "pnl"))
            trade.mfe_usd = _zahl(feld(zeile, "runup"))
            trade.mae_usd = _zahl(feld(zeile, "drawdown"))
            bericht.trades.append(trade)
            offen.pop(nummer, None)

    if offen:
        bericht.warnungen.append(
            f"{len(offen)} Trade(s) ohne Ausstiegszeile - am Ende des "
            "Zeitraums noch offen. Sie sind nicht in die Kennzahlen "
            "eingegangen."
        )
    bericht.trades.sort(key=lambda t: t.nummer)
    return bericht


def vergleiche(tv: dict[str, Any], lokal: dict[str, Any]) -> list[str]:
    """Zeilenweiser Vergleich - ohne Urteil.

    Ausdruecklich kein "bestanden"/"nicht bestanden": ob eine Abweichung
    von 8 Prozent Trefferquote viel ist, haengt an der Trade-Zahl, und diese
    Einordnung gehoert in die Auswertung, nicht in einen Datei-Leser.
    """
    zeilen = [
        f"{'Kennzahl':<24}{'TradingView':>16}{'lokal':>16}",
        "-" * 56,
    ]
    for schluessel, beschriftung in (
        ("trades", "Trades"),
        ("trefferquote", "Trefferquote"),
        ("netto_pnl_usd", "Netto-P&L USD"),
        ("profitfaktor", "Profitfaktor"),
        ("erwartungswert_usd", "Erwartungswert USD"),
    ):
        a, b = tv.get(schluessel), lokal.get(schluessel)
        zeilen.append(
            f"{beschriftung:<24}{_darstellen(a):>16}{_darstellen(b):>16}"
        )
    return zeilen


def _darstellen(wert: Any) -> str:
    if wert is None:
        return "-"
    if isinstance(wert, float):
        return f"{wert:.3f}"
    return str(wert)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tv_import",
        description="Liest eine TradingView-'List of Trades' und rechnet die "
                    "Kennzahlen des Projekts darauf.",
    )
    parser.add_argument("datei", type=Path)
    parser.add_argument(
        "--strategie",
        help="Wenn angegeben, wird derselbe Lauf lokal gerechnet und "
             "danebengestellt.",
    )
    parser.add_argument("--symbol", default="MNQ")
    args = parser.parse_args(argv)

    if not args.datei.exists():
        print(f"Datei nicht gefunden: {args.datei}", file=sys.stderr)
        return 2

    bericht = lies_tradingview(args.datei)
    for warnung in bericht.warnungen:
        print(f"HINWEIS: {warnung}", file=sys.stderr)

    kennzahlen = bericht.kennzahlen()
    if not bericht.trades:
        print("Keine Trades gelesen.", file=sys.stderr)
        return 3

    print(f"TradingView-Export: {args.datei.name}")
    print(f"  {kennzahlen['trades']} Trades")
    if kennzahlen.get("zeitraum"):
        von, bis = kennzahlen["zeitraum"]
        print(f"  Zeitraum: {von} bis {bis}")
    for name in ("trefferquote", "netto_pnl_usd", "profitfaktor",
                 "erwartungswert_usd", "mfe_median_usd", "mae_median_usd"):
        print(f"  {name:<20} {_darstellen(kennzahlen.get(name))}")

    if not args.strategie:
        print(
            "\nZum Vergleich mit dem lokalen Lauf: --strategie <name> angeben."
        )
        return 0

    from common.config import Config
    from backtest.cli import _backtester_bauen  # noqa: F401
    from backtest.engine import Backtester, CostModel
    from backtest.kosten import profil_aus_config
    from backtest.strategies.library import build_strategy
    from common.indicators import compute_indicators
    from ntbridge.store import BarStore
    import backtest.metrics as bm

    config = Config.load(PROJECT_ROOT / "config.yaml")
    speicher = BarStore(PROJECT_ROOT / "data" / "ntbridge.sqlite3")
    try:
        df = speicher.load_frame(args.symbol, config.ideas.timeframe)
    finally:
        speicher.close()

    if df.empty:
        print("\nKein lokaler Vergleich moeglich: keine Kerzen in der "
              "Datenbank.", file=sys.stderr)
        return 3

    profil = profil_aus_config(config.backtest)
    tester = Backtester(
        config.market, config.indicators,
        CostModel.aus_profil(
            profil, tick_size=config.market.tick_size,
            point_value=config.market.point_value,
        ),
    )
    ergebnis = tester.run(tester.prepare(df), build_strategy(args.strategie))
    m = bm.compute_metrics(ergebnis, initial_capital=10000)
    lokal = {
        "trades": m.trades,
        "trefferquote": m.win_rate,
        "netto_pnl_usd": m.total_pnl,
        "profitfaktor": m.profit_factor,
        "erwartungswert_usd": m.expectancy,
    }

    print()
    for zeile in vergleiche(kennzahlen, lokal):
        print(zeile)
    print(
        f"\nACHTUNG: der lokale Lauf umfasst {len(df)} Kerzen "
        f"({df.index[0]:%Y-%m-%d} bis {df.index[-1]:%Y-%m-%d}), der "
        "TradingView-Lauf in der Regel ein Vielfaches davon. Verglichen "
        "werden darf nur der GEMEINSAME Zeitraum - alles andere ist ein "
        "Vergleich zweier verschiedener Maerkte."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
