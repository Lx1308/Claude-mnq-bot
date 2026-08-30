"""Pine-Export und TradingView-Import.

Beide Richtungen der zweiten Research-Schiene: eine lokale Strategie geht als
Pine-Skript hinaus, das Ergebnis kommt als CSV zurueck. Der Wert der ganzen
Uebung haengt daran, dass beide Seiten **dieselbe** Strategie beschreiben -
deshalb pruefen diese Tests vor allem, dass nicht genaehert wird.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backtest.strategies.base import NichtUebersetzbar
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
from common.config import Config
from werkzeuge.pine_export import SPALTEN_NACH_PINE, baue_pine
from werkzeuge.tv_import import lies_tradingview


@pytest.fixture(scope="module")
def config() -> Config:
    return Config.load("config.yaml")


def _pine(name: str, config: Config) -> str:
    return baue_pine(
        build_strategy(name), config=config,
        kommission_je_seite=0.95, slippage_ticks=1.0,
    )


# -- Pine-Export ------------------------------------------------------------

def test_jede_strategie_ist_entweder_uebersetzbar_oder_nennt_den_grund(config):
    """Keine stillen Luecken.

    Eine Strategie, die weder uebersetzt noch begruendet abgelehnt wird,
    waere spaeter ein Raetsel - und die Versuchung gross, sie 'ungefaehr'
    nachzubauen.
    """
    for name in STRATEGY_LIBRARY:
        try:
            skript = _pine(name, config)
            assert "strategy(" in skript
        except NichtUebersetzbar as grund:
            assert str(grund), f"{name} lehnt ohne Begruendung ab"


def test_die_haengenden_strategien_sind_genau_die_erwarteten(config):
    """Haelt fest, WELCHE Strategien nicht uebersetzbar sind.

    Kaeme eine dazu, waere das ein Hinweis darauf, dass jemand eine Regel auf
    eine selbst gerechnete Spalte gesetzt hat, ohne den Pine-Weg mitzudenken.
    """
    nicht_moeglich = set()
    for name in STRATEGY_LIBRARY:
        try:
            _pine(name, config)
        except NichtUebersetzbar:
            nicht_moeglich.add(name)

    assert nicht_moeglich == {
        "flag_breakout",
        "ib_breakout",
        "doppelboden_bestaetigt",
        "doppelboden_nackenbruch",
    }, (
        "flag_breakout haengt an flag_breakout_up/-down, ib_breakout an "
        "ib_high/ib_low - beides Spalten, die es auf TradingView nicht gibt. "
        "Die beiden Doppelboden-Varianten haengen an der Musterserie aus "
        "common/muster_serie.py: sie in Pine nachzubauen hiesse, die "
        "Swing-Punkt-Analyse ein zweites Mal zu schreiben - und dann "
        "vergleicht man zwei verschiedene Muster, ohne es zu merken."
    )


def test_ausfuehrungsmodell_steht_im_skript(config):
    """Ohne diese drei Einstellungen waere es eine andere Strategie."""
    skript = _pine("vwap_reversion", config)
    assert "process_orders_on_close = false" in skript
    assert "pyramiding           = 0" in skript
    assert "calc_on_every_tick   = false" in skript


def test_kosten_kommen_aus_dem_profil_und_stehen_drin(config):
    skript = baue_pine(
        build_strategy("vwap_reversion"), config=config,
        kommission_je_seite=2.5, slippage_ticks=2.0,
    )
    assert "commission_value     = 2.5000" in skript
    assert "slippage             = 2" in skript


def test_vortageswerte_holen_keine_zukunft(config):
    """`lookahead_off` ist hier kein Detail.

    Mit der Vorgabe `lookahead_on` liefert request.security den Tageswert
    bereits waehrend des laufenden Tages - der Backtest saehe damit den
    Schlusskurs, bevor er entstanden ist.
    """
    skript = _pine("prev_day_breakout", config)
    assert skript.count("lookahead=barmerge.lookahead_off") >= 3
    assert "lookahead_on" not in skript


def test_vwap_setzt_mit_dem_cme_handelstag_zurueck(config):
    """Ein VWAP, der um Mitternacht zurueckspringt, ist ein anderer VWAP."""
    skript = _pine("vwap_reversion", config)
    assert '"1800-1700"' in skript


def test_atr_des_einstiegsbalkens_wird_festgehalten(config):
    """Wuerde der Stop mit dem aktuellen ATR mitlaufen, waere er ein
    nachziehender Stop - und damit eine andere Strategie."""
    skript = _pine("vwap_reversion", config)
    assert "var float einstiegsAtr = na" in skript
    assert "stopAtr * einstiegsAtr" in skript


def test_konstanten_bekommen_keinen_kerzenindex(config):
    """`30.0[1]` ist in Pine kein gueltiger Ausdruck."""
    skript = _pine("rsi_mean_reversion", config)
    assert "30.0[1]" not in skript
    assert "70.0[1]" not in skript


def test_unbekannte_spalte_wird_abgelehnt_statt_genaehert():
    from backtest.strategies.base import ColumnAbove

    with pytest.raises(NichtUebersetzbar, match="ib_high"):
        ColumnAbove("close", "ib_high").nach_pine(SPALTEN_NACH_PINE)


# -- TradingView-Import -----------------------------------------------------

BEISPIEL = """Trade #,Type,Signal,Date/Time,Price USD,Contracts,Profit USD,Profit %,Run-up USD,Drawdown USD
1,Entry long,Long,2026-01-05 09:35:00,20000.00,1,,,,
1,Exit long,Long-Aus,2026-01-05 10:05:00,20040.00,1,78.10,0.78,95.00,-22.00
2,Entry short,Short,2026-01-05 11:00:00,20100.00,1,,,,
2,Exit short,Short-Aus,2026-01-05 11:30:00,20130.00,1,-61.90,-0.62,12.00,-70.00
3,Entry long,Long,2026-01-06 09:40:00,20050.00,1,,,,
3,Exit long,Long-Aus,2026-01-06 10:10:00,20090.00,1,78.10,0.78,88.00,-15.00
"""


def test_zwei_zeilen_je_trade_werden_zusammengefuehrt(tmp_path):
    datei = tmp_path / "trades.csv"
    datei.write_text(BEISPIEL, encoding="utf-8")

    bericht = lies_tradingview(datei)
    assert len(bericht.trades) == 3

    erster = bericht.trades[0]
    assert erster.richtung == "long"
    assert erster.einstiegskurs == 20000.0
    assert erster.ausstiegskurs == 20040.0
    assert erster.pnl_usd == pytest.approx(78.10)


def test_runup_und_drawdown_werden_als_mfe_und_mae_gelesen(tmp_path):
    """Die liefert der lokale Lauf nicht - sie brauchen den Kursverlauf
    waehrend des Trades."""
    datei = tmp_path / "trades.csv"
    datei.write_text(BEISPIEL, encoding="utf-8")

    trade = lies_tradingview(datei).trades[0]
    assert trade.mfe_usd == pytest.approx(95.0)
    assert trade.mae_usd == pytest.approx(-22.0)


def test_kennzahlen_werden_gerechnet_und_nicht_erfunden(tmp_path):
    """Der Vorgaenger gab feste Werte zurueck (profit_factor 1.2,
    win_rate 0.45) und faellte darauf Urteile."""
    datei = tmp_path / "trades.csv"
    datei.write_text(BEISPIEL, encoding="utf-8")

    k = lies_tradingview(datei).kennzahlen()
    assert k["trades"] == 3
    assert k["gewinner"] == 2
    assert k["verlierer"] == 1
    assert k["trefferquote"] == pytest.approx(2 / 3)
    assert k["netto_pnl_usd"] == pytest.approx(78.10 - 61.90 + 78.10)
    assert k["profitfaktor"] == pytest.approx((78.10 + 78.10) / 61.90)


def test_profitfaktor_ohne_verlusttrade_ist_none(tmp_path):
    """Nicht 'unendlich gut', sondern nicht definiert."""
    datei = tmp_path / "trades.csv"
    datei.write_text(
        "Trade #,Type,Date/Time,Price USD,Contracts,Profit USD\n"
        "1,Entry long,2026-01-05 09:35:00,20000,1,\n"
        "1,Exit long,2026-01-05 10:05:00,20040,1,78.10\n",
        encoding="utf-8",
    )
    assert lies_tradingview(datei).kennzahlen()["profitfaktor"] is None


def test_offener_trade_am_ende_wird_gemeldet_nicht_verschluckt(tmp_path):
    datei = tmp_path / "trades.csv"
    datei.write_text(
        BEISPIEL
        + "4,Entry long,Long,2026-01-07 09:40:00,20200.00,1,,,,\n",
        encoding="utf-8",
    )
    bericht = lies_tradingview(datei)

    assert len(bericht.trades) == 3
    assert any("ohne Ausstiegszeile" in w for w in bericht.warnungen)


def test_semikolon_und_tausenderzeichen_werden_verkraftet(tmp_path):
    datei = tmp_path / "trades.csv"
    datei.write_text(
        "Trade #;Type;Date/Time;Price USD;Contracts;Profit USD\n"
        "1;Entry long;2026-01-05 09:35:00;20,000.00;1;\n"
        "1;Exit long;2026-01-05 10:05:00;20,040.00;1;1,078.10\n",
        encoding="utf-8",
    )
    trade = lies_tradingview(datei).trades[0]
    assert trade.einstiegskurs == pytest.approx(20000.0)
    assert trade.pnl_usd == pytest.approx(1078.10)


def test_fehlende_pflichtspalten_werden_benannt(tmp_path):
    datei = tmp_path / "kaputt.csv"
    datei.write_text("Irgendwas,Anderes\n1,2\n", encoding="utf-8")

    bericht = lies_tradingview(datei)
    assert bericht.trades == []
    assert any("fehlen" in w for w in bericht.warnungen)
