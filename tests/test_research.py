"""Tests der Einzelfaktor-Research.

Schwerpunkt auf den Zusicherungen, die still brechen: keine OOS-Berührung,
Hypothesenzählung, "zu wenig Daten" statt einer Kennzahl, und dass ein
nicht zuordenbarer Trade nicht heimlich einer Gruppe zugeschlagen wird.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestResult, Trade
from backtest.research import (
    MIN_TRADES_JE_GRUPPE,
    Discoverylauf,
    OutOfSampleBeruehrung,
    baue_faktor_bool,
    baue_faktor_kategorie,
    baue_faktor_perzentil,
    baue_faktor_relation,
    baue_faktor_vorzeichen,
    faktor_di_richtung,
    faktor_ema_stack,
    faktor_ib_lage,
    faktor_tageszeit,
    faktor_wochentag,
    perzentilgrenzen,
    pruefe_faktor,
    pruefe_nur_training,
)


def trade(
    stunde_utc: int,
    pnl: float,
    punkte: float | None = None,
    tag: int = 20,
    entry_price: float = 100.0,
) -> Trade:
    """Ein Trade zu einer bestimmten Stunde."""
    ein = datetime(2026, 8, tag, stunde_utc, 0, tzinfo=timezone.utc)
    return Trade(
        direction=1,
        entry_time=ein,
        entry_price=entry_price,
        exit_time=ein + timedelta(minutes=15),
        exit_price=101.0,
        bars_held=3,
        exit_reason="signal",
        gross_points=pnl if punkte is None else punkte,
        commission=1.9,
        pnl=pnl,
    )


def lauf(trades: list[Trade]) -> BacktestResult:
    return BacktestResult(
        strategy_name="test_strategie",
        strategy_description="",
        trades=trades,
    )


def rahmen_mit(spalte: str, werte: list[float], start: str = "2026-08-20 12:00") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(werte), freq="1h", tz="UTC")
    return pd.DataFrame({spalte: werte}, index=index)


# ---------------------------------------------------------------------------
#  Der OOS-Block bleibt unberührt
# ---------------------------------------------------------------------------

def test_discovery_auf_oos_daten_bricht_ab():
    """Der einzige unabhängige Block ist einmalig und danach verbraucht.

    Sieht Discovery ihn versehentlich, merkt es niemand — das Ergebnis wird
    nur besser. Deshalb bricht das laut ab.
    """
    rahmen = rahmen_mit("atr", [1.0] * 10, start="2026-08-20 12:00")
    grenze = pd.Timestamp("2026-08-20 15:00", tz="UTC")

    with pytest.raises(OutOfSampleBeruehrung, match="einmalig"):
        pruefe_nur_training(rahmen, grenze)


def test_discovery_innerhalb_des_trainings_geht_durch():
    """Gegenprobe — sonst bliebe der Test auch grün, wenn er immer würfe."""
    rahmen = rahmen_mit("atr", [1.0] * 4, start="2026-08-20 12:00")
    pruefe_nur_training(rahmen, pd.Timestamp("2026-08-21 00:00", tz="UTC"))


def test_leerer_rahmen_ist_keine_beruehrung():
    pruefe_nur_training(pd.DataFrame(), pd.Timestamp("2026-08-20", tz="UTC"))


# ---------------------------------------------------------------------------
#  Gruppierung
# ---------------------------------------------------------------------------

def test_tageszeit_trennt_die_sitzungsphasen():
    """13:30 UTC ist 09:30 New York — Eröffnung."""
    ergebnis = pruefe_faktor(
        lauf([trade(13, 10.0), trade(17, -5.0), trade(20, 3.0), trade(2, 1.0)]),
        rahmen_mit("atr", [1.0]),
        "Tageszeit",
        faktor_tageszeit,
        punktwert=2.0,
    )
    bezeichnungen = [g.auspraegung for g in ergebnis.gruppen]
    assert "1 Eroeffnung 09-11" in bezeichnungen
    assert "2 Mittag 11-14" in bezeichnungen
    assert "4 ausserhalb RTH" in bezeichnungen


def test_wochentag_wird_in_boersenzeit_bestimmt():
    """20.08.2026 ist ein Donnerstag."""
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0, tag=20)]),
        rahmen_mit("atr", [1.0]),
        "Wochentag",
        faktor_wochentag,
        punktwert=2.0,
    )
    assert ergebnis.gruppen[0].auspraegung == "4 Do"


def test_nicht_zuordenbare_trades_werden_ausgewiesen():
    """Sie dürfen nicht heimlich einer Gruppe zugeschlagen werden.

    Eine hohe Zahl heißt, dass der Faktor für viele Trades gar nicht
    definiert war — das ist eine Aussage über den Faktor, keine Panne.
    """
    faktor = baue_faktor_perzentil("adx", [20.0], ["niedrig", "hoch"])
    # Der Rahmen hat keine Spalte "adx" -> nichts ist bestimmbar.
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0)]),
        rahmen_mit("atr", [1.0, 1.0], start="2026-08-20 14:00"),
        "ADX",
        faktor,
        punktwert=2.0,
    )
    assert ergebnis.gruppen == []
    assert ergebnis.nicht_zuordenbar == 2


def test_perzentilgrenzen_kommen_aus_der_verteilung():
    """Nicht geraten. Nach dem consolidation_max_atr-Fund ist eine geratene
    Grenze ein konkreter Verdacht, kein allgemeiner Vorbehalt."""
    rahmen = rahmen_mit("atr", list(range(1, 101)))
    unten, oben = perzentilgrenzen(rahmen, "atr", [33.0, 67.0])
    assert 30 < unten < 40
    assert 64 < oben < 72


def test_perzentilgrenzen_auf_leerer_spalte_brechen_ab():
    rahmen = pd.DataFrame(
        {"atr": [float("nan")] * 3},
        index=pd.date_range("2026-08-20", periods=3, freq="1h", tz="UTC"),
    )
    with pytest.raises(ValueError, match="keine gueltigen Werte"):
        perzentilgrenzen(rahmen, "atr", [50.0])


# ---------------------------------------------------------------------------
#  „Zu wenig Daten" statt einer Kennzahl
# ---------------------------------------------------------------------------

def test_kleine_gruppe_meldet_zu_wenig_daten_statt_einer_zahl():
    """Unter der Schwelle gilt „zu wenig Daten", nicht „schwaches Ergebnis".

    Eine Kennzahl aus fünf Trades sieht aus wie eine Aussage und ist keine.
    """
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0) for _ in range(3)]),
        rahmen_mit("atr", [1.0]),
        "Tageszeit",
        faktor_tageszeit,
        punktwert=2.0,
    )
    gruppe = ergebnis.gruppen[0]
    assert gruppe.trades == 3
    assert gruppe.genug_daten is False
    assert "zu wenig Daten" in gruppe.zeile()


def test_grosse_gruppe_zeigt_die_kennzahlen():
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]),
        rahmen_mit("atr", [1.0]),
        "Tageszeit",
        faktor_tageszeit,
        punktwert=2.0,
    )
    gruppe = ergebnis.gruppen[0]
    assert gruppe.genug_daten is True
    assert "brutto" in gruppe.zeile()


def test_spannweite_braucht_zwei_auswertbare_gruppen():
    """Ein Faktor mit nur einer belastbaren Gruppe trennt nichts."""
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)] + [trade(17, 5.0)]),
        rahmen_mit("atr", [1.0]),
        "Tageszeit",
        faktor_tageszeit,
        punktwert=2.0,
    )
    assert ergebnis.spannweite_brutto is None


def test_spannweite_misst_ob_der_faktor_trennt():
    """Die eigentliche Research-Frage.

    Ein Faktor, dessen Gruppen alle gleich abschneiden, ist wertlos — egal
    wie gut oder schlecht das Niveau ist.
    """
    trades = (
        [trade(14, 4.0, punkte=2.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
        + [trade(17, -4.0, punkte=-2.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    )
    ergebnis = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    assert len(ergebnis.auswertbare_gruppen) == 2
    assert ergebnis.spannweite_brutto == pytest.approx(4.0)


# ---------------------------------------------------------------------------
#  Hypothesen-Buchführung
# ---------------------------------------------------------------------------

def test_lauf_zaehlt_die_gepruefen_hypothesen():
    """Ohne diese Zahl ist jede Signifikanzaussage wertlos.

    Bei 40 Hypothesen und alpha = 0,05 sind zwei „signifikante" Funde der
    Erwartungswert, nicht ein Ergebnis.
    """
    gross = [trade(14, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    gross += [trade(17, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    klein = [trade(20, 1.0) for _ in range(3)]

    ergebnis = pruefe_faktor(
        lauf(gross + klein), rahmen_mit("atr", [1.0]), "Tageszeit",
        faktor_tageszeit, punktwert=2.0,
    )
    lauf_obj = Discoverylauf(ergebnisse=[ergebnis])

    # Nur Gruppen MIT genug Daten zaehlen als gepruefte Hypothese.
    assert lauf_obj.gepruefte_hypothesen == 2


def test_bericht_nennt_die_hypothesenzahl_und_die_zufallserwartung():
    """Beides gehört in den Bericht, nicht in eine Fußnote."""
    trades = [trade(14, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    ergebnis = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    text = Discoverylauf(ergebnisse=[ergebnis]).bericht()

    assert "Geprüfte Hypothesen" in text
    assert "Zufallstreffer" in text
    assert "keine Befund" in text or "kein Befund" in text


# ---------------------------------------------------------------------------
#  Statistik und Multiple-Testing-Korrektur
# ---------------------------------------------------------------------------

def test_t_verteilung_trifft_bekannte_werte():
    """Ohne scipy selbst gerechnet — also gegen Lehrbuchwerte prüfen.

    Die Normalapproximation wäre bequem, weicht aber tief im
    Verteilungsrand ab — und genau dorthin schiebt Bonferroni die Schwelle.
    """
    from backtest.research import p_wert_zweiseitig

    assert p_wert_zweiseitig(1.96, 100000) == pytest.approx(0.05, abs=1e-4)
    assert p_wert_zweiseitig(2.576, 100000) == pytest.approx(0.01, abs=1e-4)
    assert p_wert_zweiseitig(2.0, 10) == pytest.approx(0.0734, abs=1e-3)
    assert p_wert_zweiseitig(0.0, 50) == pytest.approx(1.0)


def test_bonferroni_schwelle_haengt_an_der_hypothesenzahl():
    """Laurins Entscheidung: streng korrigieren, nichts privilegieren."""
    from backtest.research import ALPHA, Discoverylauf

    gross = [trade(14, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    gross += [trade(17, 1.0) for _ in range(MIN_TRADES_JE_GRUPPE)]
    erg = pruefe_faktor(
        lauf(gross), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    lauf_obj = Discoverylauf(ergebnisse=[erg])

    assert lauf_obj.gepruefte_hypothesen == 2
    assert lauf_obj.bonferroni_schwelle == pytest.approx(ALPHA / 2)


def test_streuung_wird_erfasst_sonst_gibt_es_keine_signifikanz():
    """Ein Mittelwert allein sagt nichts darüber, ob er von null abweicht."""
    trades = [trade(14, 1.0, punkte=p) for p in (1.0, 2.0, 3.0, 4.0, 5.0)]
    erg = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    gruppe = erg.gruppen[0]
    assert gruppe.brutto_punkte_std == pytest.approx(1.5811, abs=1e-3)
    assert gruppe.t_statistik is not None


def test_gruppe_ohne_streuung_hat_keine_t_statistik():
    """Ein einzelner Trade erlaubt keine Aussage — None statt einer Zahl."""
    erg = pruefe_faktor(
        lauf([trade(14, 1.0)]), rahmen_mit("atr", [1.0]), "Tageszeit",
        faktor_tageszeit, punktwert=2.0,
    )
    assert erg.gruppen[0].t_statistik is None
    assert erg.gruppen[0].p_wert is None


def test_schwaches_signal_besteht_die_korrigierte_schwelle_nicht():
    """Der Kern der Entscheidung.

    Ein Signal, das unkorrigiert signifikant wäre, fällt nach der Korrektur
    durch. Genau dafür ist sie da.
    """
    import numpy as np
    from backtest.research import ALPHA, Discoverylauf

    rng = np.random.default_rng(42)
    # Schwacher Vorteil: Mittelwert 0,3 bei Streuung 3 über 100 Trades.
    # t ≈ 1 -> unkorrigiert nicht signifikant, erst recht nicht korrigiert.
    werte = rng.normal(0.3, 3.0, 100)
    trades = [trade(14, 1.0, punkte=float(w)) for w in werte]
    erg = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    lauf_obj = Discoverylauf(ergebnisse=[erg])

    assert lauf_obj.signifikante() == []


def test_starkes_signal_besteht_auch_korrigiert():
    """Gegenprobe — sonst bliebe der Test oben auch grün, wenn nie etwas
    besteht."""
    import numpy as np
    from backtest.research import Discoverylauf

    rng = np.random.default_rng(7)
    # Deutlicher Vorteil: Mittelwert 2,0 bei Streuung 1 über 100 Trades.
    werte = rng.normal(2.0, 1.0, 100)
    trades = [trade(14, 1.0, punkte=float(w)) for w in werte]
    erg = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    lauf_obj = Discoverylauf(ergebnisse=[erg])

    assert len(lauf_obj.signifikante()) == 1


def test_statistikbericht_nennt_schwelle_und_urteil():
    """Beides gehört in den Bericht — die Schwelle allein reicht nicht."""
    trades = [trade(14, 1.0, punkte=0.1) for _ in range(MIN_TRADES_JE_GRUPPE)]
    erg = pruefe_faktor(
        lauf(trades), rahmen_mit("atr", [1.0]), "Tageszeit", faktor_tageszeit,
        punktwert=2.0,
    )
    text = Discoverylauf(ergebnisse=[erg]).statistikbericht()

    assert "Bonferroni" in text
    assert "Korrigierte Schwelle" in text
    assert "p_korr" in text


# ---------------------------------------------------------------------------
#  Zusaetzliche Faktor-Bausteine (23.08.2026 - vollstaendiger Indikatorlauf)
# ---------------------------------------------------------------------------

def rahmen_spalten(spalten: dict[str, list], start: str = "2026-08-20 14:00") -> pd.DataFrame:
    """Rahmen mit mehreren Spalten, stuendlich ab ``start`` - fuer Faktoren,
    die mehr als eine Spalte lesen (EMA-Stack, DI-Richtung, IB-Lage)."""
    laenge = len(next(iter(spalten.values())))
    index = pd.date_range(start, periods=laenge, freq="1h", tz="UTC")
    return pd.DataFrame(spalten, index=index)


def test_bool_faktor_liest_die_spalte_und_benennt_beide_auspraegungen():
    faktor = baue_faktor_bool("flag_in_consolidation", ("1 ja", "2 nein"))
    rahmen = rahmen_spalten({"flag_in_consolidation": [True, False]})
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0)]),
        rahmen, "Konsolidierung", faktor, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 ja", "2 nein"}
    assert ergebnis.nicht_zuordenbar == 0


def test_vorzeichen_faktor_trennt_positiv_negativ_null():
    faktor = baue_faktor_vorzeichen("macd_hist")
    rahmen = rahmen_spalten({"macd_hist": [1.5, -2.0, 0.0]})
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0), trade(16, 3.0)]),
        rahmen, "MACD-Vorzeichen", faktor, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 positiv", "2 negativ", "3 null"}


def test_relation_faktor_vergleicht_einstiegskurs_gegen_spaltenwert():
    faktor = baue_faktor_relation("vwap", "VWAP")
    rahmen = rahmen_spalten({"vwap": [100.0, 100.0, 100.0]})
    ergebnis = pruefe_faktor(
        lauf([
            trade(14, 1.0, entry_price=105.0),
            trade(15, 2.0, entry_price=95.0),
            trade(16, 3.0, entry_price=100.0),
        ]),
        rahmen, "VWAP-Lage", faktor, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 ueber VWAP", "2 unter VWAP", "3 auf VWAP"}


def test_kategorie_faktor_bildet_ganzzahlen_auf_namen_ab():
    faktor = baue_faktor_kategorie(
        "flag_direction", {1: "1 bullisch", -1: "2 baerisch", 0: "3 neutral"}
    )
    rahmen = rahmen_spalten({"flag_direction": [1, -1, 0]})
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0), trade(16, 3.0)]),
        rahmen, "Flag-Richtung", faktor, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 bullisch", "2 baerisch", "3 neutral"}


def test_ema_stack_kombiniert_zwei_spalten_zu_drei_auspraegungen():
    rahmen = rahmen_spalten({
        "ema_stacked_bullish": [True, False, False],
        "ema_stacked_bearish": [False, True, False],
    })
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0), trade(16, 3.0)]),
        rahmen, "EMA-Stack", faktor_ema_stack, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {
        "1 bullisch gestapelt", "2 baerisch gestapelt", "3 keine Ordnung",
    }


def test_di_richtung_vergleicht_plus_und_minus_di():
    rahmen = rahmen_spalten({
        "plus_di": [30.0, 10.0, 20.0],
        "minus_di": [10.0, 30.0, 20.0],
    })
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0), trade(15, 2.0), trade(16, 3.0)]),
        rahmen, "DI-Richtung", faktor_di_richtung, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 +DI fuehrt", "2 -DI fuehrt", "3 gleich"}


def test_ib_lage_erkennt_ueber_unter_und_innerhalb():
    rahmen = rahmen_spalten({
        "ib_high": [100.0, 100.0, 100.0],
        "ib_low": [90.0, 90.0, 90.0],
    })
    ergebnis = pruefe_faktor(
        lauf([
            trade(14, 1.0, entry_price=105.0),
            trade(15, 2.0, entry_price=85.0),
            trade(16, 3.0, entry_price=95.0),
        ]),
        rahmen, "IB-Lage", faktor_ib_lage, punktwert=2.0,
    )
    bezeichnungen = {g.auspraegung for g in ergebnis.gruppen}
    assert bezeichnungen == {"1 ueber IB", "2 unter IB", "3 innerhalb IB"}


def test_ib_lage_ohne_beide_spalten_ist_nicht_zuordenbar():
    """Nur ib_high vorhanden -> nicht heimlich mit ib_low=NaN rechnen."""
    rahmen = rahmen_spalten({"ib_high": [100.0]})
    ergebnis = pruefe_faktor(
        lauf([trade(14, 1.0, entry_price=105.0)]),
        rahmen, "IB-Lage", faktor_ib_lage, punktwert=2.0,
    )
    assert ergebnis.gruppen == []
    assert ergebnis.nicht_zuordenbar == 1
