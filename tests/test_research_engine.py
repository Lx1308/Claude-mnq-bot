"""Die Research-Engine: rechnet sie wirklich, und sagt sie die Wahrheit?

Die Vorgaengerfassung sah aus wie eine Research-Engine und war keine. Diese
Tests halten die vier Stellen fest, an denen sie gescheitert ist.
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from execution import research_engine as re_modul
from execution.research_engine import (
    MIN_TRADES_FUER_URTEIL,
    _t_test,
    _trade_tabelle,
    lade_kerzen,
)


class _Trade:
    """Nachbau eines Trades aus backtest.engine - nur die Felder der Tabelle."""

    def __init__(self, pnl: float = 10.0):
        self.direction = 1
        self.entry_time = pd.Timestamp("2026-09-02 14:00", tz="UTC")
        self.exit_time = pd.Timestamp("2026-09-02 14:30", tz="UTC")
        self.entry_price = 20000.0
        self.exit_price = 20005.0
        self.gross_points = 5.0
        self.commission = 1.9
        self.pnl = pnl
        self.bars_held = 6
        self.exit_reason = "target"


# -- Datenauswahl -----------------------------------------------------------

def test_kerzen_werden_nach_instrument_und_zeitebene_gefiltert():
    """Der Vorgaenger lud SELECT ... FROM bars ORDER BY ts_utc OHNE WHERE.

    Damit lagen 1m-, 5m-, 15m-, 1h- und Tageskerzen in einem Topf, und der
    Backtest rechnete auf einer Reihe, die es so nie gegeben hat.
    """
    quelltext = inspect.getsource(lade_kerzen)
    assert "load_frame" in quelltext
    assert "symbol" in quelltext and "timeframe" in quelltext


def test_lade_kerzen_ohne_datenbank_liefert_leer(tmp_path):
    df = lade_kerzen("MNQ", "5m", datenbank=tmp_path / "leer.sqlite3")
    assert df.empty


# -- Trade-Tabelle ----------------------------------------------------------

def test_jede_spalte_der_trade_tabelle_ist_gefuellt():
    """Der Vorgaenger schrieb P&L und R-Vielfaches als leere Zellen - die
    f-Strings waren kaputt und niemand hat es gemerkt."""
    zeilen = _trade_tabelle([_Trade(pnl=78.10)])

    assert len(zeilen) == 3          # Kopf, Trennlinie, ein Trade
    datenzeile = zeilen[2]
    zellen = [z.strip() for z in datenzeile.strip("|").split("|")]

    assert all(zellen), f"leere Zelle in {datenzeile!r}"
    assert "+78.10" in datenzeile
    assert "1.90" in datenzeile
    assert "target" in datenzeile


def test_leere_tradeliste_wird_benannt():
    zeilen = _trade_tabelle([])
    assert zeilen == ["Keine Trades im Trainingsblock."]


def test_lange_tradeliste_wird_gekuerzt_und_sagt_das():
    zeilen = _trade_tabelle([_Trade() for _ in range(150)], hoechstens=10)
    assert any("140 weitere" in z for z in zeilen)


def test_verlust_traegt_ein_vorzeichen():
    zeile = _trade_tabelle([_Trade(pnl=-42.5)])[2]
    assert "-42.50" in zeile


# -- Statistik --------------------------------------------------------------

def test_unter_der_mindestzahl_gibt_es_keinen_p_wert():
    """Ein p-Wert aus zwoelf Trades ist Rauschen mit Nachkommastellen.

    None ist hier die richtige Antwort - eine Zahl waere eine Einladung,
    sie zu benutzen.
    """
    t, p = _t_test([1.0] * (MIN_TRADES_FUER_URTEIL - 1))
    assert t is None and p is None


def test_ohne_streuung_gibt_es_keinen_p_wert():
    t, p = _t_test([5.0] * (MIN_TRADES_FUER_URTEIL + 10))
    assert t is None and p is None


def test_deutlicher_effekt_ergibt_kleinen_p_wert():
    werte = [10.0, 12.0, 8.0, 11.0, 9.0] * 12   # 60 Werte, klar positiv
    t, p = _t_test(werte)
    assert t is not None and t > 0
    assert p is not None and p < 0.01


def test_reines_rauschen_ergibt_grossen_p_wert():
    werte = [1.0, -1.0] * 30
    t, p = _t_test(werte)
    assert p is not None and p > 0.5


# -- Urteil -----------------------------------------------------------------

def test_kandidat_wird_ausdruecklich_nicht_als_bestaetigung_bezeichnet():
    """Ein p < 0,05 ohne Mehrfachtestkorrektur ist eine Vermutung.

    Der Quelltext muss das sagen - sonst liest jemand "KANDIDAT" und haelt
    es fuer ein Ergebnis.
    """
    quelltext = inspect.getsource(re_modul.rechne_hypothese)
    assert "KEINE Bestaetigung" in quelltext
    assert "Mehrfachtestkorrektur" in quelltext


def test_protokoll_weist_das_kostenprofil_aus():
    quelltext = inspect.getsource(re_modul.schreibe_protokoll)
    assert "Kostenprofil" in quelltext
    assert "Annahme" in quelltext
    assert "Datensatz-Hash" in quelltext
    assert "Git-Commit" in quelltext
