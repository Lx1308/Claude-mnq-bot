"""Rueckblick: haette diese Handelsfolge ein Prop-Konto ueberstanden?

Laurins Frage vom 30.08.2026: "dann kann man ja irgendwann auswerten, welche
Hypothesen gut auf einem funded acc funktioniert haetten und welche nicht."

Die Tests hier pruefen vor allem, dass die Rechnung die drei Dinge beachtet,
die ein einfaches Aufsummieren uebersieht: andere Positionsgroesse, gesperrte
Tage, und dass der nachziehende Verlust am Pfad haengt.
"""

from __future__ import annotations

import pytest

from auswertung.kontovergleich import (
    EINSCHRAENKUNGEN,
    spiele_durch,
    vergleiche_kontoprofile,
)
from common.kontoregeln import hole_kontoregeln

MNQ_PUNKTWERT = 2.0


def _trade(
    tag: str,
    punkte: float,
    *,
    trade_id: str = "",
    stop_abstand: float = 20.0,
    hypothese: str = "vwap_reversion",
    zeit: str = "14:00",
) -> dict:
    """Ein Trade im Format des Ausfuehrungsspeichers."""
    einstieg = 20000.0
    return {
        "trade_id": trade_id or f"{tag}-{zeit}-{punkte}",
        "session_datum": tag,
        "ausstieg_utc": f"{tag}T{zeit}:00+00:00",
        "einstiegskurs": einstieg,
        "stop": einstieg - stop_abstand,
        "punkte_brutto": punkte,
        "kommission": 1.90,
        "menge": 1,
        "hypothese": hypothese,
        "r_vielfaches": punkte / stop_abstand,
    }


# -- Neudimensionierung -----------------------------------------------------

def test_kleineres_konto_nimmt_weniger_kontrakte():
    """Der Kern: dieselbe Handelsfolge ist auf zwei Konten nicht dieselbe."""
    trades = [_trade("2026-09-01", 20.0)]

    klein = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                         point_value=MNQ_PUNKTWERT)
    gross = spiele_durch(trades, hole_kontoregeln("lucid_pro_150k"),
                         point_value=MNQ_PUNKTWERT)

    assert klein.trades[0].kontrakte < gross.trades[0].kontrakte
    assert klein.trades[0].pnl_usd < gross.trades[0].pnl_usd


def test_zu_teurer_trade_wird_als_nicht_handelbar_ausgewiesen():
    """Nicht als Verlust und nicht als Gewinn - er haette nicht stattgefunden."""
    # 25k: Puffer 1.000, 7 Prozent = 70 USD Budget.
    # 200 Punkte Stop = 400 USD je Kontrakt.
    trades = [_trade("2026-09-01", 20.0, stop_abstand=200.0)]
    verlauf = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                           point_value=MNQ_PUNKTWERT)

    assert verlauf.trades[0].ausgang == "zu_teuer"
    assert verlauf.trades[0].pnl_usd == 0.0
    assert verlauf.nicht_handelbar == 1
    assert verlauf.netto_pnl_usd == 0.0


def test_ohne_rekonstruierbaren_stop_wird_nicht_geraten():
    """Ein geratener Stopabstand ergaebe eine geratene P&L - und die saehe im
    Bericht aus wie eine gerechnete."""
    trade = _trade("2026-09-01", 20.0)
    del trade["stop"]
    del trade["r_vielfaches"]

    verlauf = spiele_durch([trade], hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)
    assert verlauf.trades[0].ausgang == "zu_teuer"
    assert "nicht rekonstruierbar" in verlauf.trades[0].grund


def test_stop_kann_aus_dem_r_vielfachen_zurueckgerechnet_werden():
    trade = _trade("2026-09-01", 40.0, stop_abstand=20.0)
    del trade["stop"]      # r_vielfaches bleibt: 40/20 = 2.0

    verlauf = spiele_durch([trade], hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)
    assert verlauf.trades[0].ausgang == "gehandelt"


# -- Tagesverlustlimit ------------------------------------------------------

def test_gesperrter_tag_laesst_spaetere_trades_entfallen():
    """Nach dem Tageslimit haetten sie nicht stattgefunden - weder im Guten
    noch im Schlechten."""
    regeln = hole_kontoregeln("lucid_pro_50k")   # 1.200 USD/Tag
    # Budget 50k: Puffer 2.000 * 7 % = 140 USD, Stop 20 Punkte = 40 USD je
    # Kontrakt -> 3 Kontrakte. Ein Verlust von 100 Punkten = -600 USD.
    trades = [
        _trade("2026-09-01", -100.0, zeit="14:00"),
        _trade("2026-09-01", -100.0, zeit="15:00"),
        _trade("2026-09-01", +200.0, zeit="16:00"),   # haette gerettet
        _trade("2026-09-02", +50.0, zeit="14:00"),    # naechster Tag: wieder frei
    ]
    verlauf = spiele_durch(trades, regeln, point_value=MNQ_PUNKTWERT)

    ausgaenge = [t.ausgang for t in verlauf.trades]
    assert ausgaenge[:2] == ["gehandelt", "gehandelt"]
    assert ausgaenge[2] == "tag_gesperrt"
    assert ausgaenge[3] == "gehandelt", "der naechste Tag ist wieder offen"
    assert "2026-09-01" in verlauf.gesperrte_tage


def test_ohne_tageslimit_wird_nichts_gesperrt():
    """Das 25k-Konto hat als einziges kein Tagesverlustlimit."""
    trades = [
        _trade("2026-09-01", -30.0, zeit="14:00"),
        _trade("2026-09-01", -30.0, zeit="15:00"),
        _trade("2026-09-01", -30.0, zeit="16:00"),
    ]
    verlauf = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                           point_value=MNQ_PUNKTWERT)
    assert verlauf.gesperrte_tage == []


# -- Gesamtverlust ----------------------------------------------------------

def test_gerissenes_konto_beendet_die_folge():
    regeln = hole_kontoregeln("lucid_pro_25k")   # 1.000 USD Puffer
    trades = [_trade(f"2026-09-{tag:02d}", -400.0) for tag in range(1, 12)]

    verlauf = spiele_durch(trades, regeln, point_value=MNQ_PUNKTWERT)

    assert not verlauf.ueberlebt
    assert verlauf.gerissen_am is not None
    assert "Verlustgrenze" in verlauf.gerissen_grund
    # Alles nach dem Bruch zaehlt nicht mehr.
    nach_dem_bruch = [
        t for t in verlauf.trades if t.ausgang == "konto_gerissen"
    ]
    assert nach_dem_bruch, "nach dem Bruch muessen Trades entfallen"


def test_ein_groesseres_konto_allein_rettet_nichts():
    """Ein Ergebnis, das beim Schreiben dieses Tests ueberrascht hat.

    Bei PROPORTIONALEM Risiko - jedes Konto riskiert denselben Anteil seines
    Puffers - skaliert ein 150k-Konto seine Positionsgroesse mit. Dieselbe
    Verlustserie reisst es dann genauso schnell wie das 25k-Konto, nur mit
    groesseren Zahlen.

    Die Kontogroesse allein ist also keine Sicherheit. Was sich wirklich
    unterscheidet, ist, WELCHE Signale ueberhaupt bezahlbar sind - siehe
    test_grosses_konto_kann_signale_nehmen_die_das_kleine_nicht_bezahlt.
    """
    trades = [_trade(f"2026-09-{tag:02d}", -200.0) for tag in range(1, 9)]

    klein = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                         point_value=MNQ_PUNKTWERT)
    gross = spiele_durch(trades, hole_kontoregeln("lucid_pro_150k"),
                         point_value=MNQ_PUNKTWERT)

    assert not klein.ueberlebt
    assert not gross.ueberlebt, (
        "Bei proportionalem Risiko schuetzt ein groesseres Konto nicht - "
        "wer das erwartet, rechnet mit einem festen Betrag je Trade."
    )


def test_grosses_konto_kann_signale_nehmen_die_das_kleine_nicht_bezahlt():
    """DAS ist der Unterschied zwischen den Kontogroessen.

    Ein Signal mit weitem Stop ist auf dem 25k-Konto schlicht nicht
    handelbar; auf dem 150k-Konto schon. Ueber viele Signale hinweg handeln
    die beiden Konten damit unterschiedliche Stichproben - und genau deshalb
    ist die Frage "welche Hypothese haette auf einem funded acc getragen"
    nicht durch Hochrechnen zu beantworten.
    """
    # 150 Punkte Stop = 300 USD je Kontrakt.
    # 25k:  Puffer 1.000 * 7 % =  70 USD -> nicht handelbar
    # 150k: Puffer 4.500 * 7 % = 315 USD -> ein Kontrakt geht
    trades = [_trade("2026-09-01", +60.0, stop_abstand=150.0)]

    klein = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                         point_value=MNQ_PUNKTWERT)
    gross = spiele_durch(trades, hole_kontoregeln("lucid_pro_150k"),
                         point_value=MNQ_PUNKTWERT)

    assert klein.trades[0].ausgang == "zu_teuer"
    assert gross.trades[0].ausgang == "gehandelt"


def test_freies_konto_kennt_keine_verlustgrenze():
    trades = [_trade(f"2026-09-{tag:02d}", -500.0) for tag in range(1, 20)]
    verlauf = spiele_durch(
        trades, hole_kontoregeln("frei"),
        point_value=MNQ_PUNKTWERT, startkapital_usd=25_000.0,
    )
    assert verlauf.ueberlebt
    assert verlauf.gerissen_am is None


def test_eod_trailing_zieht_erst_ueber_den_tageswechsel_nach():
    """Ein Gewinn INNERHALB des Tages hebt die Grenze noch nicht.

    Waere es Intraday-Trailing, saehe dieselbe Folge anders aus - deshalb ist
    die Unterscheidung in den Kontoregeln kein Detail.
    """
    regeln = hole_kontoregeln("lucid_pro_50k")
    trades = [
        _trade("2026-09-01", +500.0, zeit="14:00"),
        _trade("2026-09-02", -100.0, zeit="14:00"),
    ]
    verlauf = spiele_durch(trades, regeln, point_value=MNQ_PUNKTWERT)
    assert verlauf.ueberlebt


# -- Ziel und Konsistenz ----------------------------------------------------

def test_erreichtes_gewinnziel_wird_vermerkt():
    regeln = hole_kontoregeln("lucid_pro_25k")    # Ziel 1.250 USD
    trades = [_trade(f"2026-09-{tag:02d}", +200.0) for tag in range(1, 8)]

    verlauf = spiele_durch(trades, regeln, point_value=MNQ_PUNKTWERT)
    assert verlauf.ziel_erreicht_am is not None


def test_konsistenzregel_wird_gerechnet_aber_blockiert_nicht():
    """Sie greift bei Lucid erst beim Auszahlungsantrag."""
    trades = [
        _trade("2026-09-01", +500.0),
        _trade("2026-09-02", +10.0),
    ]
    verlauf = spiele_durch(trades, hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)

    assert verlauf.konsistenz() > 0.9
    assert verlauf.konsistenz_eingehalten() is False
    # Trotzdem wurden beide gehandelt.
    assert len(verlauf.gehandelte) == 2


def test_konsistenz_ohne_gewinn_ist_none_und_nicht_null():
    trades = [_trade("2026-09-01", -20.0)]
    verlauf = spiele_durch(trades, hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)
    assert verlauf.konsistenz() is None


# -- Auswertung je Hypothese ------------------------------------------------

def test_je_hypothese_zeigt_wer_getragen_und_wer_gerissen_haette():
    """Der eigentliche Zweck: nicht 'hat das Konto ueberlebt', sondern
    WELCHE Idee es getragen haette."""
    trades = [
        _trade("2026-09-01", +40.0, hypothese="vwap_reversion"),
        _trade("2026-09-01", +30.0, hypothese="vwap_reversion", zeit="15:00"),
        _trade("2026-09-02", -60.0, hypothese="ib_bruch"),
        _trade("2026-09-02", -50.0, hypothese="ib_bruch", zeit="15:00"),
    ]
    verlauf = spiele_durch(trades, hole_kontoregeln("lucid_pro_100k"),
                           point_value=MNQ_PUNKTWERT)
    je = verlauf.je_hypothese()

    assert je["vwap_reversion"]["pnl_usd"] > 0
    assert je["ib_bruch"]["pnl_usd"] < 0
    assert je["vwap_reversion"]["trefferquote"] == 1.0
    assert je["ib_bruch"]["trefferquote"] == 0.0


def test_nicht_handelbare_trades_zaehlen_je_hypothese_getrennt():
    trades = [
        _trade("2026-09-01", +40.0, hypothese="eng", stop_abstand=10.0),
        _trade("2026-09-01", +40.0, hypothese="weit", stop_abstand=300.0),
    ]
    je = spiele_durch(trades, hole_kontoregeln("lucid_pro_25k"),
                      point_value=MNQ_PUNKTWERT).je_hypothese()

    assert je["eng"]["gehandelt"] == 1
    assert je["weit"]["zu_teuer"] == 1
    assert je["weit"]["pnl_usd"] == 0.0


# -- Bericht ----------------------------------------------------------------

def test_zusammenfassung_traegt_die_einschraenkungen_mit():
    """Eine Zahl ohne sie saehe aus wie eine Messung."""
    verlauf = spiele_durch([_trade("2026-09-01", 20.0)],
                           hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)
    zusammenfassung = verlauf.zusammenfassung()

    assert zusammenfassung["einschraenkungen"] == list(EINSCHRAENKUNGEN)
    assert zusammenfassung["regeln_sind_annahme"] is True


def test_vergleich_mehrerer_profile_auf_derselben_folge():
    trades = [_trade(f"2026-09-{tag:02d}", -150.0) for tag in range(1, 10)]
    ergebnis = vergleiche_kontoprofile(
        trades, ["lucid_pro_25k", "lucid_pro_50k", "lucid_pro_150k"],
        point_value=MNQ_PUNKTWERT,
    )

    assert set(ergebnis) == {"lucid_pro_25k", "lucid_pro_50k", "lucid_pro_150k"}
    # Je groesser das Konto, desto spaeter (oder gar nicht) der Bruch.
    assert not ergebnis["lucid_pro_25k"].ueberlebt


def test_leere_folge_ergibt_einen_unveraenderten_kontostand():
    verlauf = spiele_durch([], hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)
    assert verlauf.endstand_usd == verlauf.startkapital_usd
    assert verlauf.netto_pnl_usd == 0.0
    assert verlauf.ueberlebt


def test_reihenfolge_wird_erzwungen_nicht_vorausgesetzt():
    """Die Eingabe darf unsortiert sein - der Pfad haengt an der Reihenfolge."""
    spaet = _trade("2026-09-05", +40.0)
    frueh = _trade("2026-09-01", +40.0)
    verlauf = spiele_durch([spaet, frueh], hole_kontoregeln("lucid_pro_50k"),
                           point_value=MNQ_PUNKTWERT)

    assert [t.session_datum for t in verlauf.trades] == ["2026-09-01", "2026-09-05"]


def test_dieselbe_kontraktformel_wie_im_bot():
    """Zwei Formeln, die dasselbe tun sollen, laufen frueher oder spaeter
    auseinander. Hier wird festgehalten, dass sie es (noch) nicht tun."""
    from execution.bot import kontraktzahl
    from auswertung.kontovergleich import _kontrakte_fuer

    for budget in (70.0, 140.0, 300.0, 1000.0):
        for stop in (5.0, 20.0, 55.0):
            aus_bot, _ = kontraktzahl(
                risikobudget_usd=budget, entry=20000.0, stop=20000.0 - stop,
                point_value=MNQ_PUNKTWERT, hoechstens=20,
            )
            aus_rueckblick = _kontrakte_fuer(
                risiko_punkte=stop, point_value=MNQ_PUNKTWERT,
                budget_usd=budget, hoechstens=20,
            )
            assert aus_bot == aus_rueckblick, (budget, stop)
