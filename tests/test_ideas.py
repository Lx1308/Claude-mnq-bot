"""Tests der Ideen-Protokollierung (Etappe C).

Schwerpunkt liegt auf den Zusicherungen, die still brechen koennten:
kein Lookahead, keine zweite Signal-Implementierung, keine Vermischung von
Haupt- und Exploration-Log, keine stillen Ausfaelle.
"""

from __future__ import annotations

import inspect
from datetime import datetime, time as dtime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backtest.strategies.base import (
    BarContext,
    ColumnBelow,
    DeviationReentry,
    Falling,
    PreviousDeviationExceeds,
    Rising,
)
from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
from common.config import (
    Config,
    ConfigError,
    IdeasConfig,
    IdeenFilterConfig,
    IdeenSetupParameter,
)
from common.instruments import MNQ
from ideas import erkennung, store as store_modul
from ideas.erkennung import FehlendeSpalte, aktive_setups, erkenne, pruefe_spalten
from ideas.filters import filter_blackout
from ideas.kalender import KalenderBlackout
from ideas.model import (
    QUELLE_MANUELL,
    QUELLE_REGEL,
    RICHTUNG_LONG,
    RICHTUNG_SHORT,
    Beobachtung,
    TradeIdee,
    UngueltigeIdee,
    berechne_crv,
)
from ideas.setups import (
    ALLE_SETUPS,
    ART_FORTSETZUNG,
    ART_REVERSION,
    SETUP_BIBLIOTHEK,
    hole_setup,
    pruefe_konfiguration,
)
from ideas.store import IdeenStore


# ---------------------------------------------------------------------------
#  Hilfen
# ---------------------------------------------------------------------------

def idee(**ueberschreibungen) -> TradeIdee:
    """Eine gueltige Long-Idee, gezielt abwandelbar."""
    vorgabe = dict(
        instrument="MNQ",
        setup="pdh_pdl_bruch",
        richtung=RICHTUNG_LONG,
        timeframe="5m",
        erstellt_utc=datetime(2026, 8, 20, 14, 30, tzinfo=timezone.utc),
        entry=29400.0,
        stop=29380.0,
        ziel=29440.0,
        crv=2.0,
        unter_crv_schwelle=False,
        atr_referenz=13.0,
        stop_atr=1.5,
        ziel_atr=3.0,
        quelle=QUELLE_REGEL,
        profil="sim_frei",
    )
    vorgabe.update(ueberschreibungen)
    return TradeIdee(**vorgabe)


@pytest.fixture
def temp_store(tmp_path) -> IdeenStore:
    """Speicher auf einer temporaeren Datei.

    Ausdruecklich NIE die produktive Datenbank: sie wird im Betrieb
    beschrieben, und ein Test darf echte Historie nicht anfassen.
    """
    with IdeenStore(tmp_path / "ideen_test.sqlite3") as speicher:
        yield speicher


# ---------------------------------------------------------------------------
#  Setup-Bibliothek: keine zweite Signal-Implementierung
# ---------------------------------------------------------------------------

def test_jede_setup_familie_verweist_auf_eine_backtest_strategie():
    """Die tragende Invariante: eine Signal-Logik fuer Backtest und Protokoll.

    Faende sich je ein Setup, das seine Bedingung selbst ausrechnet statt
    eine RuleStrategy zu bauen, pruefte der Backtest etwas anderes als das,
    was protokolliert wird.
    """
    for schluessel, definition in SETUP_BIBLIOTHEK.items():
        strategie = definition.baue(IdeenSetupParameter())
        assert strategie.long_entry is not None, schluessel
        assert strategie.short_entry is not None, schluessel
        # Der Name traegt den Bibliotheksnamen, ggf. mit Parameter-Suffix.
        basis = strategie.name.split("[")[0]
        assert basis in STRATEGY_LIBRARY, (
            f"{schluessel} baut keine Strategie aus STRATEGY_LIBRARY, "
            f"sondern {strategie.name!r}."
        )


def test_setup_familien_tragen_die_richtung_nicht_im_schluessel():
    """Eine Familie je Schluessel, Richtung als eigene Spalte.

    Stuende die Richtung im Schluessel, liesse sich die Frage "traegt der
    Vortagesmarken-Bruch" nur noch durch Zusammenaddieren zweier Kategorien
    beantworten.
    """
    for schluessel in ALLE_SETUPS:
        assert not schluessel.endswith(("_hoch", "_tief", "_long", "_short")), schluessel


def test_ideas_modul_hat_keine_eigenen_erkenner_mehr():
    """Regressionsschutz gegen die Rueckkehr von ideas/detectors.py.

    Der Zwischenstand vom 21.08.2026 hatte eigene Erkenner. Sie wurden
    entfernt, weil sie die Invariante brechen - dieser Test haelt das fest.
    """
    import ideas

    from pathlib import Path

    paket = Path(ideas.__file__).parent
    assert not (paket / "detectors.py").exists(), (
        "ideas/detectors.py ist wieder da. Signal-Logik gehoert nach "
        "backtest/strategies/, sonst testet der Backtest eine andere "
        "Strategie als die protokollierte."
    )


def test_ib_setup_fordert_die_ib_spalten_an():
    """Ohne diese Anforderung bliebe das IB-Setup stumm statt zu meckern."""
    definition = hole_setup("ib_bruch")
    assert "ib_high" in definition.benoetigte_spalten
    assert "ib_low" in definition.benoetigte_spalten


def test_vwap_reversion_ist_reversion_und_nicht_trendfolge():
    """Die Spezifikation ordnete vwap_trend zu - das ist das Gegenteil.

    vwap_trend steigt MIT der VWAP-Kreuzung ein, vwap_reversion gegen die
    Uebertreibung zurueck zum Anker. Waeren die vertauscht, protokollierte
    das System systematisch das falsche Setup.
    """
    assert hole_setup("vwap_reversion").art == ART_REVERSION
    assert hole_setup("pdh_pdl_bruch").art == ART_FORTSETZUNG
    assert hole_setup("ib_bruch").art == ART_FORTSETZUNG
    assert hole_setup("flaggen_ausbruch").art == ART_FORTSETZUNG


# ---------------------------------------------------------------------------
#  Neue Regel-Objekte
# ---------------------------------------------------------------------------

def kontext(jetzt: dict, vorher: dict | None = None) -> BarContext:
    return BarContext(
        row=pd.Series(jetzt),
        previous=pd.Series(vorher) if vorher is not None else None,
        timestamp=pd.Timestamp("2026-08-20 14:30", tz="UTC"),
        position=0,
    )


def test_rising_und_falling_brauchen_eine_vorkerze():
    assert Rising("close").evaluate(kontext({"close": 10.0}, {"close": 9.0}))
    assert not Rising("close").evaluate(kontext({"close": 9.0}, {"close": 10.0}))
    assert Falling("close").evaluate(kontext({"close": 9.0}, {"close": 10.0}))
    # Ohne Vorkerze kein Signal - NaN darf nie ein Signal ausloesen.
    assert not Rising("close").evaluate(kontext({"close": 10.0}))


def test_previous_deviation_misst_auf_der_vorkerze():
    """Abweichung auf der Vorkerze, Umkehr auf der aktuellen.

    Wuerde beides auf derselben Kerze gemessen, waere die Bedingung
    entweder nie oder immer erfuellt.
    """
    regel = PreviousDeviationExceeds("close", "vwap", 1.5, "below")
    # Vorkerze 30 Punkte unter VWAP bei ATR 10 -> 3.0 ATR, reicht.
    assert regel.evaluate(
        kontext({"close": 90.0, "vwap": 100.0, "atr": 10.0},
                {"close": 70.0, "vwap": 100.0, "atr": 10.0})
    )
    # Vorkerze nur 10 Punkte entfernt -> 1.0 ATR, reicht nicht.
    assert not regel.evaluate(
        kontext({"close": 95.0, "vwap": 100.0, "atr": 10.0},
                {"close": 90.0, "vwap": 100.0, "atr": 10.0})
    )


def test_deviation_reentry_feuert_nur_beim_uebertritt():
    """Die Kernkorrektur: eine Rueckkehrbewegung ergibt EIN Signal.

    Gefunden an echten MNQ-5m-Daten: die urspruengliche Komposition
    (`PreviousDeviationExceeds & Rising & ColumnBelow`) feuerte auf jeder
    steigenden Kerze der Rueckkehr erneut - 47 Signale in 10 Bewegungen,
    die groesste mit 11. In der Erwartungswert-Rechnung haette eine einzige
    Bewegung elffach gezaehlt.
    """
    regel = DeviationReentry("close", "vwap", 1.5, "below")

    # Kurs kommt von -3.0 ATR langsam zurueck: -30, -25, -20, -14, -8, -2.
    # Das Band liegt bei -15. Uebertritt findet zwischen -20 und -14 statt.
    verlauf = [-30.0, -25.0, -20.0, -14.0, -8.0, -2.0]
    treffer = []
    for vorher, jetzt in zip(verlauf, verlauf[1:]):
        ctx = kontext(
            {"close": 100.0 + jetzt, "vwap": 100.0, "atr": 10.0},
            {"close": 100.0 + vorher, "vwap": 100.0, "atr": 10.0},
        )
        if regel.evaluate(ctx):
            treffer.append(jetzt)

    assert treffer == [-14.0], (
        f"Genau ein Uebertritt erwartet, bekam {treffer}. Feuert die Regel "
        "mehrfach, zaehlt dieselbe Bewegung spaeter mehrfach."
    )


def test_alte_komposition_wuerde_den_test_nicht_bestehen():
    """Gegenprobe: die fehlerhafte Variante testweise wieder eingesetzt.

    Ein Test, der vorher und nachher gruen ist, beweist nichts. Diese
    Gegenprobe zeigt, dass der Test oben die Haeufung tatsaechlich faengt.
    """
    alt = (
        PreviousDeviationExceeds("close", "vwap", 1.5, "below")
        & Rising("close")
        & ColumnBelow("close", "vwap")
    )

    verlauf = [-30.0, -25.0, -20.0, -14.0, -8.0, -2.0]
    treffer = []
    for vorher, jetzt in zip(verlauf, verlauf[1:]):
        ctx = kontext(
            {"close": 100.0 + jetzt, "vwap": 100.0, "atr": 10.0},
            {"close": 100.0 + vorher, "vwap": 100.0, "atr": 10.0},
        )
        if alt.evaluate(ctx):
            treffer.append(jetzt)

    assert len(treffer) > 1, (
        "Die alte Komposition muss hier mehrfach feuern - sonst traefe der "
        "Test oben den gemeldeten Fehler gar nicht."
    )


def test_deviation_reentry_feuert_nicht_wenn_die_referenz_schon_durchbrochen_ist():
    """Ist der VWAP bereits ueberschritten, ist die Rueckkehr gelaufen."""
    regel = DeviationReentry("close", "vwap", 1.5, "below")
    # Sprung von -3.0 ATR direkt ueber den VWAP hinaus.
    ctx = kontext(
        {"close": 105.0, "vwap": 100.0, "atr": 10.0},
        {"close": 70.0, "vwap": 100.0, "atr": 10.0},
    )
    assert not regel.evaluate(ctx)


def test_previous_deviation_verwirft_ungueltigen_atr():
    """ATR 0 wuerde jede Abweichung als ausreichend erscheinen lassen."""
    regel = PreviousDeviationExceeds("close", "vwap", 1.5, "below")
    assert not regel.evaluate(
        kontext({"close": 90.0, "vwap": 100.0, "atr": 0.0},
                {"close": 70.0, "vwap": 100.0, "atr": 0.0})
    )
    assert not regel.evaluate(
        kontext({"close": 90.0, "vwap": 100.0, "atr": float("nan")},
                {"close": 70.0, "vwap": 100.0, "atr": float("nan")})
    )


# ---------------------------------------------------------------------------
#  Datenmodell
# ---------------------------------------------------------------------------

def test_idee_mit_stop_auf_der_falschen_seite_wird_abgelehnt():
    """Eine solche Zeile waere kein Signal, sondern ein Rechenfehler."""
    with pytest.raises(UngueltigeIdee):
        idee(stop=29420.0)  # Stop ueber dem Einstieg bei einer Long-Idee
    with pytest.raises(UngueltigeIdee):
        idee(richtung=RICHTUNG_SHORT)  # Long-Marken bei Short-Richtung


def test_idee_verlangt_zeitzonenbehafteten_zeitstempel():
    """Ein naiver Zeitstempel waere gegen die Kerzen nicht eindeutig."""
    with pytest.raises(UngueltigeIdee):
        idee(erstellt_utc=datetime(2026, 8, 20, 14, 30))


def test_idee_kennt_kein_ergebnisfeld():
    """Bewusst kein Gewinn/Verlust: das entsteht erst bei der Auswertung.

    Stuende es hier, gaebe es zwei Wahrheiten, je nachdem wann man
    hinschaut - das Ergebnis haengt vom angewandten Regelwerk ab.
    """
    felder = set(TradeIdee.__dataclass_fields__)
    for verboten in ("ergebnis", "pnl", "gewinn", "verlust", "ausgang", "r_vielfaches"):
        assert verboten not in felder


def test_idee_traegt_die_bemessungsgrundlagen_fuer_das_nachspielen():
    """Ohne ATR-Bezug und Faktoren waere das R-Vielfache nicht rekonstruierbar.

    Der tatsaechliche Einstieg ist die Eroeffnung der Folgekerze, nicht der
    hier gespeicherte Schlusskurs. Stop und Ziel muessen sich daher relativ
    zum echten Fill neu bilden lassen.
    """
    felder = set(TradeIdee.__dataclass_fields__)
    assert {"atr_referenz", "stop_atr", "ziel_atr"} <= felder


def test_crv_bei_verschwindendem_risiko_ist_null_statt_unendlich():
    assert berechne_crv(100.0, 100.0, 120.0) == 0.0


def test_beobachtung_ohne_beschreibung_wird_abgelehnt():
    with pytest.raises(UngueltigeIdee):
        Beobachtung(
            instrument="MNQ",
            beschreibung="   ",
            erstellt_utc=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )


# ---------------------------------------------------------------------------
#  Speicher: Trennung der beiden Logs
# ---------------------------------------------------------------------------

def test_auswertung_liest_niemals_das_exploration_log():
    """Die Sperre aus Spezifikation Abschnitt 3, als Quelltextpruefung.

    Analog zum Kostengarantie-Test: die Zusage lautet nicht "greift gerade
    nicht darauf zu", sondern "kann es nicht". Ohne diese Sperre schliche
    sich nicht-reproduzierbares LLM-Rauschen in die Erwartungswert-Statistik.
    """
    quelltext = inspect.getsource(IdeenStore.lade_fuer_auswertung)
    assert "observations" not in quelltext, (
        "lade_fuer_auswertung nennt die Tabelle observations. Das "
        "Exploration-Log darf nie in die Auswertung fliessen."
    )


def test_beobachtungen_tauchen_nicht_in_der_auswertung_auf(temp_store):
    """Gegenprobe zur Quelltextpruefung: auch praktisch getrennt."""
    temp_store.speichere([idee()])
    temp_store.speichere_beobachtung(
        Beobachtung(
            instrument="MNQ",
            beschreibung="Auffaellige Reaktion am Vortageshoch.",
            erstellt_utc=datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc),
        )
    )

    assert temp_store.gesamt() == 1
    assert temp_store.gesamt_beobachtungen() == 1
    ausgewertet = temp_store.lade_fuer_auswertung()
    assert len(ausgewertet) == 1
    assert all("beschreibung" not in datensatz for datensatz in ausgewertet)


def test_wiederholter_lauf_erzeugt_keine_duplikate(temp_store):
    """Der Erkennungslauf faehrt ueber ein ueberlappendes Fenster.

    idea_id ist AUTOINCREMENT und taugt nicht zur Duplikaterkennung -
    dafuer liegt ein UNIQUE-Index auf der fachlichen Kombination.
    """
    assert temp_store.speichere([idee()]) == 1
    assert temp_store.speichere([idee()]) == 0
    assert temp_store.gesamt() == 1


def test_manuelle_und_regelbasierte_idee_zur_selben_kerze_koexistieren(temp_store):
    """quelle gehoert in den Eindeutigkeitsschluessel.

    Sonst ueberschriebe eine manuell-assistierte Idee die regelbasierte
    derselben Kerze - und der Vergleich der beiden Quellen waere unmoeglich.
    """
    temp_store.speichere([idee(quelle=QUELLE_REGEL)])
    temp_store.speichere([idee(quelle=QUELLE_MANUELL)])
    assert temp_store.gesamt() == 2


def test_profil_filtert_nur_auf_ausdrueckliche_anfrage(temp_store):
    """Vorgabe ist "alle Ideen", unabhaengig von der Kontoumgebung.

    Nur so laesst sich fragen, welche Setups auch unter Prop-Firm-Regeln
    tragen. Wuerde profil stillschweigend filtern, rechnete die Auswertung
    nur noch auf einem Ausschnitt.
    """
    temp_store.speichere([idee(profil="sim_frei")])
    temp_store.speichere(
        [idee(profil="lucid_challenge",
              erstellt_utc=datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc))]
    )

    assert len(temp_store.lade_fuer_auswertung()) == 2
    assert len(temp_store.lade_fuer_auswertung(profil="sim_frei")) == 1


def test_gefilterte_ideen_werden_gespeichert_aber_nicht_ausgewertet(temp_store):
    """Beides ist noetig: aufheben zum Nachpruefen, weglassen beim Rechnen."""
    temp_store.speichere([idee(gefiltert=True, filter_gruende=("termin_blackout",))])
    assert temp_store.gesamt() == 1
    assert temp_store.lade_fuer_auswertung() == []
    assert len(temp_store.lade()) == 1


def test_kategorien_zaehlen_nach_setup_und_richtung(temp_store):
    """Die Kategorie der Auswertung ist setup/richtung, nicht nur setup."""
    temp_store.speichere([idee()])
    temp_store.speichere(
        [idee(richtung=RICHTUNG_SHORT, entry=29400.0, stop=29420.0, ziel=29360.0)]
    )
    kategorien = temp_store.anzahl_je_kategorie()
    assert kategorien["pdh_pdl_bruch/long"]["handelbar"] == 1
    assert kategorien["pdh_pdl_bruch/short"]["handelbar"] == 1


def test_tests_fassen_die_produktive_datenbank_nicht_an(temp_store):
    """Die echte Historie darf ein Test nie beschreiben."""
    assert "ntbridge" not in str(temp_store.path)
    assert temp_store.path.parent != (
        __import__("pathlib").Path.cwd() / "data"
    )


# ---------------------------------------------------------------------------
#  Erkennung
# ---------------------------------------------------------------------------

def ideen_cfg(**ueberschreibungen) -> IdeasConfig:
    vorgabe = dict(
        profil="sim_frei",
        timeframe="5m",
        setups={schluessel: IdeenSetupParameter() for schluessel in ALLE_SETUPS},
        filter=IdeenFilterConfig(
            adx_aktiv=False,
            liquiditaet_aktiv=False,
            duennzone_aktiv=False,
            blackout_aktiv=False,
        ),
    )
    vorgabe.update(ueberschreibungen)
    return IdeasConfig(**vorgabe)


def test_fehlende_spalte_bricht_laut_ab_statt_still_zu_schweigen():
    """Der wichtigste Test dieses Moduls.

    Fehlte ib_high, wuerde die IB-Regel ueber ihren NaN-Schutz einfach nie
    ausloesen - ohne Fehlermeldung. Genau diese Klasse stiller Ausfaelle hat
    das Projekt schon einmal Wochen gekostet.
    """
    df = pd.DataFrame(
        {
            "open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0],
            "atr": [1.0], "vwap": [1.0],
        },
        index=pd.date_range("2026-08-20", periods=1, tz="UTC"),
    )
    with pytest.raises(FehlendeSpalte) as fehler:
        pruefe_spalten(df, [hole_setup("ib_bruch")])
    # Die Meldung muss sagen, WER die Spalte braucht - sonst sucht man lange.
    assert "ib_high" in str(fehler.value)
    assert "ib_bruch" in str(fehler.value)


def test_abgeschaltete_familie_wird_nicht_gebaut():
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=True),
            "ib_bruch": IdeenSetupParameter(aktiv=False),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    aktive = [definition.schluessel for definition, _ in aktive_setups(cfg)]
    assert aktive == ["pdh_pdl_bruch"]


def baue_rahmen(closes, *, start="2026-08-20 13:35", freq="5min", **spalten):
    """Vorbereiteter Rahmen mit frei setzbaren Indikatorspalten."""
    closes = np.asarray(closes, dtype=float)
    index = pd.date_range(start=start, periods=len(closes), freq=freq, tz="UTC")
    opens = np.concatenate([[closes[0]], closes[:-1]])
    rahmen = pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + 1.0,
            "low": np.minimum(opens, closes) - 1.0,
            "close": closes,
            "volume": np.full(len(closes), 100.0),
            "atr": np.full(len(closes), 10.0),
            "vwap": np.full(len(closes), closes[0]),
            "rsi": np.full(len(closes), 50.0),
            "sma_fast": np.full(len(closes), closes[0]),
            "sma_slow": np.full(len(closes), closes[0]),
            "adx": np.full(len(closes), 25.0),
            "prev_session_high": np.full(len(closes), np.nan),
            "prev_session_low": np.full(len(closes), np.nan),
            "ib_high": np.full(len(closes), np.nan),
            "ib_low": np.full(len(closes), np.nan),
            "flag_breakout_up": np.zeros(len(closes), dtype=bool),
            "flag_breakout_down": np.zeros(len(closes), dtype=bool),
        },
        index=index,
    )
    for name, wert in spalten.items():
        rahmen[name] = wert
    return rahmen


def test_vortagesbruch_loest_auf_der_flanke_aus_und_nicht_dauerhaft():
    """Flankenerkennung, nicht Zustandsabfrage.

    Ohne sie taeuchte ein einmal gebrochenes Vortageshoch bei jeder
    folgenden Kerze erneut als Idee auf und verwaesserte die Statistik mit
    Dutzenden Kopien derselben Bewegung.
    """
    # Marke bei 100, Kurs steigt darueber und bleibt oben.
    rahmen = baue_rahmen(
        [98.0, 99.0, 105.0, 106.0, 107.0],
        prev_session_high=100.0,
        prev_session_low=50.0,
    )
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=True),
            "ib_bruch": IdeenSetupParameter(aktiv=False),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    signale, _ = erkenne(rahmen, cfg)
    long_signale = [s for s in signale if s.richtung == RICHTUNG_LONG]
    assert len(long_signale) == 1, (
        "Der Bruch muss genau einmal melden, nicht auf jeder Kerze oberhalb."
    )


def test_stop_und_ziel_folgen_den_atr_faktoren_der_strategie():
    """Dieselbe ATR-Bedeutung wie in der Backtest-Engine.

    Waeren die Faktoren hier anders interpretiert, rechnete die Auswertung
    ein anderes R-Vielfache als der Backtest.
    """
    rahmen = baue_rahmen(
        [98.0, 99.0, 105.0],
        prev_session_high=100.0,
        prev_session_low=50.0,
    )
    parameter = IdeenSetupParameter(aktiv=True, stop_atr=1.5, ziel_atr=3.0)
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": parameter,
            "ib_bruch": IdeenSetupParameter(aktiv=False),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    signale, _ = erkenne(rahmen, cfg)
    signal = [s for s in signale if s.richtung == RICHTUNG_LONG][0]

    assert signal.entry == pytest.approx(105.0)
    assert signal.atr_referenz == pytest.approx(10.0)
    assert signal.stop == pytest.approx(105.0 - 1.5 * 10.0)
    assert signal.ziel == pytest.approx(105.0 + 3.0 * 10.0)
    assert signal.crv == pytest.approx(2.0)


def test_erkennung_meldet_signale_ohne_gueltigen_atr_statt_sie_zu_verschweigen():
    """Ein leeres Ergebnis darf nicht wie "keine Signale" aussehen.

    Ohne gueltigen ATR gibt es kein Stop und kein Ziel. Diese Faelle werden
    gezaehlt und ausgewiesen - waere die Zahl hoch, hiesse das, dass die
    Historie zu kurz fuer den ATR-Vorlauf ist.
    """
    rahmen = baue_rahmen(
        [98.0, 99.0, 105.0],
        prev_session_high=100.0,
        prev_session_low=50.0,
        atr=np.nan,
    )
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=True),
            "ib_bruch": IdeenSetupParameter(aktiv=False),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    signale, bericht = erkenne(rahmen, cfg)
    assert signale == []
    assert bericht.ohne_atr >= 1, (
        "Signale ohne ATR muessen gezaehlt werden, sonst sieht ein leeres "
        "Ergebnis faelschlich nach 'keine Signale' aus."
    )


def test_erkennung_sieht_nie_in_die_zukunft():
    """Strukturell ueber BarContext, nicht durch Sorgfalt.

    Wuerde eine spaetere Kerze das Signal beeinflussen, aenderte sich das
    Ergebnis, sobald man mehr Historie anhaengt. Genau das darf nicht sein.
    """
    basis = baue_rahmen(
        [98.0, 99.0, 105.0, 106.0],
        prev_session_high=100.0,
        prev_session_low=50.0,
    )
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=True),
            "ib_bruch": IdeenSetupParameter(aktiv=False),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    kurz, _ = erkenne(basis.iloc[:3], cfg)

    verlaengert = baue_rahmen(
        [98.0, 99.0, 105.0, 80.0, 70.0, 60.0],
        prev_session_high=100.0,
        prev_session_low=50.0,
    )
    lang, _ = erkenne(verlaengert.iloc[:3], cfg)

    assert [(s.setup, s.richtung, s.entry) for s in kurz] == [
        (s.setup, s.richtung, s.entry) for s in lang
    ]


def test_ib_bruch_loest_vor_ablauf_des_ib_fensters_nicht_aus():
    """ib_high ist waehrend des Fensters NaN - Lookahead-Sperre.

    Eine Kerze um 09:45 darf das Hoch nicht kennen, das erst um 10:30
    feststeht.
    """
    rahmen = baue_rahmen([98.0, 99.0, 105.0, 106.0])
    # ib_high bleibt durchgehend NaN, wie waehrend des laufenden Fensters.
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=False),
            "ib_bruch": IdeenSetupParameter(aktiv=True),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    signale, _ = erkenne(rahmen, cfg)
    assert signale == []


def test_uebergang_von_nan_auf_wert_erzeugt_kein_scheinsignal():
    """Die erste Kerze nach Fensterende darf nicht allein deshalb feuern."""
    rahmen = baue_rahmen([98.0, 99.0, 105.0, 106.0])
    ib = [np.nan, np.nan, 100.0, 100.0]
    rahmen["ib_high"] = ib
    rahmen["ib_low"] = [np.nan, np.nan, 50.0, 50.0]
    cfg = ideen_cfg(
        setups={
            "pdh_pdl_bruch": IdeenSetupParameter(aktiv=False),
            "ib_bruch": IdeenSetupParameter(aktiv=True),
            "vwap_reversion": IdeenSetupParameter(aktiv=False),
            "flaggen_ausbruch": IdeenSetupParameter(aktiv=False),
        }
    )
    signale, _ = erkenne(rahmen, cfg)
    zeitpunkte = [s.zeitpunkt for s in signale]
    assert rahmen.index[2] not in zeitpunkte, (
        "Die erste Kerze mit bekanntem ib_high darf nicht allein wegen des "
        "Uebergangs NaN -> Wert als Bruch gelten."
    )


# ---------------------------------------------------------------------------
#  Startpruefungen
# ---------------------------------------------------------------------------

def test_gueltige_minimalkonfiguration_kommt_durch():
    """Gegenprobe: die Startpruefungen duerfen nicht alles ablehnen.

    Ohne diesen Test wuerden die vier folgenden auch dann gruen bleiben,
    wenn Config.validate() aus einem ganz anderen Grund immer wirft.
    """
    cfg = Config.from_dict(_minimalkonfiguration())
    assert cfg.ideas.profil == "sim_frei"


def test_unbekanntes_profil_bricht_beim_start_ab():
    """Ein Tippfehler wuerde die Auswertung still in zwei Gruppen zerlegen."""
    # Config.from_dict ruft validate() selbst auf - der Abbruch faellt also
    # schon hier und nicht erst bei einem spaeteren, leicht vergessenen Aufruf.
    with pytest.raises(ConfigError) as fehler:
        Config.from_dict(_minimalkonfiguration(profil="sim-frei"))
    assert "profil" in str(fehler.value).lower()


def test_demo_ist_als_profil_ausdruecklich_ungueltig():
    """Namensfalle: "demo" ist die Tradovate-Umgebung, nicht die Kontoumgebung."""
    with pytest.raises(ConfigError) as fehler:
        Config.from_dict(_minimalkonfiguration(profil="demo"))
    assert "demo" in str(fehler.value)


def test_unbekannter_setup_schluessel_bricht_ab():
    """Er wirkt sonst wie eine konfigurierte Familie, loest aber nie aus.

    Die Pruefung liegt in ``ideas.setups`` und nicht in ``Config.validate``:
    ``common`` ist die Basisschicht und soll nichts aus ``ideas``
    importieren - sonst haenge auch die Importhuelle des MCP-Servers daran.
    """
    cfg = ideen_cfg(
        setups={
            # Genau der Schluessel aus dem alten Zwischenstand, der die
            # Richtung noch im Namen trug.
            "pdh_bruch": IdeenSetupParameter(aktiv=True),
        }
    )
    with pytest.raises(ConfigError) as fehler:
        pruefe_konfiguration(cfg)
    assert "pdh_bruch" in str(fehler.value)


def test_alle_familien_abgeschaltet_bricht_ab():
    """Sonst liefe die Protokollierung dauerhaft ohne Ergebnis."""
    cfg = ideen_cfg(
        setups={schluessel: IdeenSetupParameter(aktiv=False) for schluessel in ALLE_SETUPS}
    )
    with pytest.raises(ConfigError):
        pruefe_konfiguration(cfg)

    # Gegenprobe: mit einer aktiven Familie geht dieselbe Pruefung durch.
    # Ohne sie bliebe der Test auch dann gruen, wenn die Funktion immer wirft.
    gueltig = ideen_cfg(
        setups={schluessel: IdeenSetupParameter(aktiv=False) for schluessel in ALLE_SETUPS}
        | {"pdh_pdl_bruch": IdeenSetupParameter(aktiv=True)}
    )
    pruefe_konfiguration(gueltig)


def test_config_validate_zieht_ideas_nicht_in_die_importhuelle():
    """Die Basisschicht darf nicht auf die Fachschicht zurueckgreifen.

    Ein Import von ``ideas`` in ``common/config.py`` zoege ``ideas`` samt
    ``backtest.strategies`` in den Importweg des MCP-Servers, der bewusst
    schmal gehalten ist.
    """
    quelltext = inspect.getsource(Config.validate)
    assert "import ideas" not in quelltext
    assert "from ideas" not in quelltext


# ---------------------------------------------------------------------------
#  Blackout-Schicht: Abdeckungsgrenze des Wirtschaftskalenders
# ---------------------------------------------------------------------------

class _Kalenderattrappe:
    """Minimale Terminquelle. Zaehlt, wie oft sie gefragt wurde."""

    def __init__(self, antwort: dict) -> None:
        self.antwort = antwort
        self.abfragen = 0

    async def event_risk(self, *, now=None, symbol=None) -> dict:
        self.abfragen += 1
        return self.antwort


def test_blackout_ausserhalb_der_kalenderabdeckung_bleibt_offen():
    """Der Kernfall: alte Zeitpunkte duerfen keine Entwarnung ergeben.

    Forex Factory kennt im Wesentlichen die laufende Woche. Fragt man einen
    drei Wochen alten Zeitpunkt ab, findet sich dort kein Termin - die
    Antwort saehe aus wie "geprueft, frei", waere aber "nicht gewusst".
    Das ist Bug-Lehre 6 in neuer Verkleidung.
    """
    quelle = _Kalenderattrappe(
        {"calendar_available": True, "blackout": {"aktiv": False}}
    )
    jetzt = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    pruefer = KalenderBlackout(quelle, max_alter_tage=7.0, jetzt=jetzt)

    alt = jetzt - timedelta(days=21)
    assert pruefer(alt) is None, (
        "Ausserhalb der Abdeckung muss die Frage offen bleiben, nicht mit "
        "'kein Blackout' beantwortet werden."
    )
    assert quelle.abfragen == 0, (
        "Der Kalender darf gar nicht erst gefragt werden - seine Antwort "
        "waere ja das Problem."
    )
    assert pruefer.ausserhalb_der_abdeckung == 1


def test_blackout_innerhalb_der_abdeckung_wird_wirklich_gefragt():
    """Gegenprobe: sonst blieben die Tests oben auch gruen, wenn die
    Schicht grundsaetzlich nie fragte."""
    quelle = _Kalenderattrappe(
        {"calendar_available": True, "blackout": {"aktiv": True}}
    )
    jetzt = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    pruefer = KalenderBlackout(quelle, max_alter_tage=7.0, jetzt=jetzt)

    assert pruefer(jetzt - timedelta(hours=2)) is True
    assert quelle.abfragen == 1
    assert pruefer.ausserhalb_der_abdeckung == 0


def test_blackout_in_der_zukunft_gilt_als_abgedeckt():
    """Termine stehen im Kalender, bevor sie stattfinden - nur die
    Vergangenheit faellt aus der Abdeckung."""
    quelle = _Kalenderattrappe(
        {"calendar_available": True, "blackout": {"aktiv": False}}
    )
    jetzt = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    pruefer = KalenderBlackout(quelle, max_alter_tage=7.0, jetzt=jetzt)

    assert pruefer(jetzt + timedelta(days=3)) is False
    assert quelle.abfragen == 1


def test_nicht_erreichbarer_kalender_ist_nicht_pruefbar_statt_frei():
    """``calendar_available: false`` heisst "unbekannt", nicht "frei"."""
    quelle = _Kalenderattrappe(
        {"calendar_available": False, "blackout": {"aktiv": False}}
    )
    jetzt = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    pruefer = KalenderBlackout(quelle, max_alter_tage=7.0, jetzt=jetzt)

    assert pruefer(jetzt - timedelta(hours=1)) is None


def test_offener_blackout_wird_zum_dritten_filterausgang():
    """Die Schicht haengt am Filter: ``None`` muss dort als 'nicht
    pruefbar' ankommen und darf die Idee weder durchwinken noch ablehnen."""
    ergebnis = filter_blackout(
        datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc),
        IdeenFilterConfig(blackout_aktiv=True),
        lambda _zeitpunkt: None,
    )
    assert not ergebnis.abgelehnt
    assert ergebnis.ungeprueft


def _minimalkonfiguration(*, profil: str = "sim_frei") -> dict:
    """Kleinste Konfiguration, die Config.validate() erreicht."""
    import copy

    from common.config import Config as _Config

    daten = copy.deepcopy(_BASIS_KONFIGURATION)
    daten["ideas"]["profil"] = profil
    return daten


_BASIS_KONFIGURATION: dict = {
    "tradovate": {
        "environment": "demo",
        "websocket": {},
    },
    "market": {
        "product": "MNQ",
        "candle_interval_minutes": 1,
        "candle_buffer_size": 3000,
        "warmup_bars": 2880,
        "tick_size": 0.25,
        "point_value": 2.0,
        "session": {
            "timezone": "America/New_York",
            "start_time": "18:00",
            "end_time": "17:00",
        },
    },
    "indicators": {},
    "alerts": {"conditions": {}},
    "claude": {},
    "on_demand": {},
    "ntbridge": {},
    "ideas": {
        "enabled": True,
        "profil": "sim_frei",
        "profile_erlaubt": ["sim_frei", "lucid_challenge", "lucid_funded"],
        "setups": {schluessel: {"aktiv": True} for schluessel in ALLE_SETUPS},
        "filter": {},
    },
    "event_risk": {},
    "notify": {},
    "logging": {},
    "backtest": {},
}
