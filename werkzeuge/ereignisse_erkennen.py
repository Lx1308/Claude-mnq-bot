"""Ereignisse ueber die Historie erkennen und in die Ereignisdatenbank schreiben.

Etappe 3 aus ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``.

    .venv\\Scripts\\python.exe -m werkzeuge.ereignisse_erkennen --probelauf
    .venv\\Scripts\\python.exe -m werkzeuge.ereignisse_erkennen
    .venv\\Scripts\\python.exe -m werkzeuge.ereignisse_erkennen --von 2024-01-01

``--probelauf`` erkennt und zaehlt, **schreibt aber nichts**. Immer damit
anfangen: der volle Lauf dauert je nach Rechner eine Viertelstunde und legt
Millionen Zeilen an.

WAS HIER PASSIERT
-----------------
1. Die 1m-Historie aus ``data/ntbridge.sqlite3`` laden (``NtBridgeDataProvider``)
2. ``Backtester.prepare`` - Indikatoren, IB, Opening Range, Musterserien.
   **Dieselbe** Vorbereitung wie im Backtest (Invariante 1).
3. Regime anreichern (``common/regime.py``) - rueckwaertsgerichtet
4. Alle Erkenner aus ``common/ereignisse/`` laufen lassen
5. Lookahead-Sammelpruefung
6. Schreiben, mit Kontext, Cluster-IDs und Datensatzblock

ALLES AUF 1-MINUTEN-KERZEN. Der Bot wird auf Minutenkerzen handeln; eine
Untersuchung auf 5m maesse eine andere Strategie als die, die spaeter laeuft.
Die groeberen Erkennungsebenen (5m/15m/1h, Plan Entscheidung 1) sind noch
nicht angeschlossen - sie kommen als eigener Schritt, mit der Umrechnung des
Verfuegbarkeitszeitpunkts auf den 1m-Index (``basis.grobe_kerze_zu_1m_index``).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest.data import BarRequest, create_provider  # noqa: E402
from backtest.engine import Backtester  # noqa: E402
from common.config import Config  # noqa: E402
from common.ereignisse.basis import pruefe_lookahead  # noqa: E402
from common.ereignisse.datenbank import (  # noqa: E402
    massenschreiben,
    notiere_lauf,
    oeffne,
    schreibe_outcomes,
    zaehle,
)
from common.ereignisse.displacement import displacement_serie  # noqa: E402
from common.ereignisse.eqhl import eqhl_ereignisse  # noqa: E402
from common.ereignisse.fvg import fvg_serie  # noqa: E402
from common.ereignisse.niveaus import niveau_ereignisse  # noqa: E402
from common.ereignisse.orderblocks import orderblock_ereignisse  # noqa: E402
from common.ereignisse.outcomes import HORIZONTE, alle_horizonte  # noqa: E402
from common.ereignisse.struktur import struktur_ereignisse, struktur_spalten  # noqa: E402
from common.ereignisse.sweeps import sweep_ereignisse  # noqa: E402
from common.regime import regime_spalten, relatives_volumen  # noqa: E402

#: Die Erkenner in fester Reihenfolge. Der Name landet im Herkunftseintrag.
ERKENNER = (
    ("struktur", struktur_ereignisse),
    ("fvg", fvg_serie),
    ("displacement", displacement_serie),
    ("orderblocks", orderblock_ereignisse),
    ("eqhl", eqhl_ereignisse),
    ("sweeps", sweep_ereignisse),
    ("niveaus", niveau_ereignisse),
)

#: Vorgabepfad der Ereignisdatenbank.
DATENBANK = "data/eventdb.sqlite3"


def _log(text: str) -> None:
    print(text, flush=True)


def vorbereiten(config: Config, *, von=None, bis=None):
    """1m-Historie laden und anreichern. Rueckgabe ``(rahmen, rollgrenzen)``."""
    t0 = time.perf_counter()
    provider = create_provider("ntbridge", database=config.ntbridge.database)
    df = provider.load(
        BarRequest(symbol=config.market.product, interval_minutes=1,
                   start=von, end=bis)
    )
    _log(f"  geladen:   {len(df):>10,} Kerzen   {time.perf_counter() - t0:6.1f}s")
    if df.empty:
        return df, []

    t0 = time.perf_counter()
    rahmen = Backtester(config.market, config.indicators).prepare(df)
    _log(f"  prepare:   {time.perf_counter() - t0:6.1f}s")

    # Regime - rueckwaertsgerichtet, rollendes Fenster (nie Gesamthistorie).
    t0 = time.perf_counter()
    regime = regime_spalten(
        rahmen, config.indicators, config.market.session, kerzen_minuten=1
    )
    for spalte in regime.columns:
        rahmen[spalte] = regime[spalte]
    # Das relative Volumen selbst - aus DERSELBEN Funktion, aus der auch der
    # Liquiditaetsrang gebildet wird. Eine zweite Formel hier waere der
    # Anfang davon, dass Ereignismerkmal und Regimeachse auseinanderlaufen.
    rahmen["volumen_relativ"] = relatives_volumen(rahmen)
    _log(f"  regime:    {time.perf_counter() - t0:6.1f}s")

    gefuellt = int(rahmen["vola_regime"].notna().sum())
    if gefuellt == 0:
        _log(
            "  ! Regime bleibt leer: der Zeitraum ist kuerzer als das "
            "rollende Fenster (60 Handelstage). Die Ereignisse werden ohne "
            "Regime-Kontext geschrieben - das ist eine ehrliche Luecke, "
            "aber fuer eine Regime-Auswertung braucht es einen laengeren "
            "Ausschnitt."
        )
    else:
        _log(f"  regime gefuellt: {gefuellt:,} von {len(rahmen):,} Kerzen")

    # Trendlage aus der Swing-Struktur - Kontext fuer jedes Ereignis.
    t0 = time.perf_counter()
    struktur = struktur_spalten(rahmen)
    for spalte in struktur.columns:
        rahmen[spalte] = struktur[spalte]
    _log(f"  struktur:  {time.perf_counter() - t0:6.1f}s")

    return rahmen, list(getattr(provider, "rollgrenzen", []))


def erkennen(rahmen: pd.DataFrame) -> list:
    """Alle Erkenner laufen lassen, mit Lookahead-Sammelpruefung."""
    alle = []
    for name, fn in ERKENNER:
        t0 = time.perf_counter()
        ereignisse = fn(rahmen)
        pruefe_lookahead(ereignisse, rahmen_laenge=len(rahmen))
        _log(
            f"  {name:14s} {time.perf_counter() - t0:6.1f}s "
            f"{len(ereignisse):>10,}"
        )
        alle.extend(ereignisse)
    return alle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ereignisse_erkennen",
        description="Erkennt alle Ereignisse ueber die 1m-Historie und "
                    "schreibt sie in die Ereignisdatenbank.",
    )
    parser.add_argument(
        "--probelauf", action="store_true",
        help="Erkennen und zaehlen, aber NICHTS schreiben. Immer damit "
             "anfangen - der volle Lauf legt Millionen Zeilen an.",
    )
    parser.add_argument("--datenbank", default=DATENBANK)
    parser.add_argument("--von", default=None, help="ISO-Datum, z.B. 2024-01-01")
    parser.add_argument("--bis", default=None)
    parser.add_argument(
        "--lauf-id", default=None,
        help="Kennung dieses Laufs. Vorgabe: Zeitstempel. Derselbe Wert "
             "ueberschreibt die Zeilen des vorherigen Laufs.",
    )
    parser.add_argument(
        "--ohne-outcomes", action="store_true",
        help="Nur die Ereignisse schreiben, den Kursverlauf danach nicht "
             "messen (Etappe 4 ueberspringen).",
    )
    parser.add_argument("--notiz", default="")
    args = parser.parse_args(argv)

    config = Config.load(PROJECT_ROOT / "config.yaml")
    von = pd.Timestamp(args.von, tz="UTC") if args.von else None
    bis = pd.Timestamp(args.bis, tz="UTC") if args.bis else None

    _log("Vorbereiten")
    rahmen, rollgrenzen = vorbereiten(config, von=von, bis=bis)
    if rahmen.empty:
        _log("Keine Kerzen im gewaehlten Bereich - nichts zu tun.")
        return 1
    _log(
        f"  Zeitraum:  {rahmen.index[0]} bis {rahmen.index[-1]}\n"
        f"  Rollnaehte:{len(rollgrenzen):>4}"
    )

    _log("\nErkennen")
    ereignisse = erkennen(rahmen)
    _log(f"  GESAMT:    {len(ereignisse):>10,} Ereignisse")

    verteilung = Counter(e.pattern_type for e in ereignisse)
    _log("\nJe Mustertyp")
    for typ, anzahl in verteilung.most_common():
        _log(f"  {typ:24s} {anzahl:>10,}")

    if args.probelauf:
        _log("\n--probelauf: nichts geschrieben.")
        return 0

    lauf_id = args.lauf_id or f"L{pd.Timestamp.now('UTC'):%Y%m%d-%H%M%S}"
    pfad = Path(args.datenbank)
    if not pfad.is_absolute():
        pfad = PROJECT_ROOT / pfad

    _log(f"\nSchreiben nach {pfad}  (lauf_id={lauf_id})")
    t0 = time.perf_counter()
    # massenschreiben statt schreibe_events: die Sekundaerindizes werden vorher
    # verworfen und danach am Stueck neu gebaut. Mit stehenden Indizes brauchte
    # der erste Volllauf (2,59 Mio Zeilen) 7.087 Sekunden.
    conn = oeffne(pfad, mit_indizes=False)
    try:
        n = massenschreiben(
            conn, ereignisse, rahmen,
            lauf_id=lauf_id,
            instrument=config.market.product,
            rollgrenzen=rollgrenzen,
        )
        notiere_lauf(
            conn, lauf_id=lauf_id, instrument=config.market.product,
            rahmen=rahmen, erkenner=[n for n, _ in ERKENNER],
            ereignisse=n, notiz=args.notiz,
        )
        _log(f"  {n:,} Zeilen in {time.perf_counter() - t0:.1f}s")

        if not args.ohne_outcomes:
            _log("\nOutcomes (Etappe 4)")
            t0 = time.perf_counter()
            import numpy as np

            # Die event_ids stehen in derselben Reihenfolge wie die
            # Ereignisliste - schreibe_events vergibt sie fortlaufend. Die
            # Reihenfolge ist der Schluessel: passt sie nicht, landen
            # Ergebnisse beim falschen Ereignis, und man saehe es keiner
            # Zeile an. schreibe_outcomes prueft die Laenge.
            event_ids = [f"{lauf_id}-{k:09d}" for k in range(len(ereignisse))]
            verfuegbar = np.fromiter(
                (e.verfuegbar_idx for e in ereignisse), dtype=np.int64,
                count=len(ereignisse),
            )
            richtungen = np.fromiter(
                (e.direction for e in ereignisse), dtype=np.int64,
                count=len(ereignisse),
            )
            ergebnis = alle_horizonte(rahmen, verfuegbar, richtungen)
            _log(f"  gerechnet: {time.perf_counter() - t0:.1f}s")
            for h in HORIZONTE:
                gueltig = int(ergebnis[h].gueltig.sum())
                fehlend = len(ereignisse) - gueltig
                _log(
                    f"    H={h:>3}  {gueltig:>10,} gueltig"
                    + (f"   ({fehlend:,} Fenster unvollstaendig)" if fehlend else "")
                )

            t0 = time.perf_counter()
            m = schreibe_outcomes(conn, event_ids, ergebnis)
            _log(f"  {m:,} Outcome-Zeilen in {time.perf_counter() - t0:.1f}s")

        uebersicht = zaehle(conn)
        _log("\nIn der Datenbank, je Block")
        je_block = uebersicht.groupby("datensatz_block")["n"].sum()
        for block in ("train", "validation", "oos"):
            _log(f"  {block:12s} {int(je_block.get(block, 0)):>10,}")
    finally:
        conn.close()

    _log("\nFertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
