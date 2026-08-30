"""Die Chart-Overlays: aus echten Primitiven, nicht aus leeren Listen.

``/api/overlays``, ``/api/analysis`` und ``/api/strategy`` lieferten bis zum
30.08.2026 fest verdrahtete leere Antworten. Die Erkennungslogik lag seit dem
27.08.2026 im Projekt, war aber nirgends angeschlossen - deshalb blieb der
Chart nackt, obwohl die Haken gesetzt waren.

Diese Tests halten fest, dass die Verdrahtung besteht UND dass sie ueber die
vorhandenen Erkenner laeuft statt ueber eine zweite Implementierung.
"""

from __future__ import annotations

import pandas as pd
import pytest

from common.config import Config
from common.instruments import get_instrument
from common.indicators import compute_indicators
from execution.overlays import MAX_PRIMITIVE, baue_analyse, baue_overlays


@pytest.fixture(scope="module")
def rahmen() -> pd.DataFrame:
    """Ein synthetischer Verlauf mit Luecken, Impulsen und Ruecklaeufen.

    Bewusst synthetisch: die Tests sollen auch dann laufen, wenn gerade keine
    Kerzen in ``ntbridge.sqlite3`` liegen.
    """
    import numpy as np

    zufall = np.random.default_rng(42)
    n = 400
    schritte = zufall.normal(0, 8, n).cumsum() + 20000
    index = pd.date_range("2026-09-01 00:00", periods=n, freq="5min", tz="UTC")

    hoch = schritte + zufall.uniform(2, 20, n)
    tief = schritte - zufall.uniform(2, 20, n)
    df = pd.DataFrame(
        {
            "open": schritte,
            "high": hoch,
            "low": tief,
            "close": schritte + zufall.normal(0, 3, n),
            "volume": zufall.uniform(100, 2000, n),
        },
        index=index,
    )
    cfg = Config.load("config.yaml")
    return compute_indicators(df, cfg.indicators, cfg.market.session)


@pytest.fixture(scope="module")
def overlays(rahmen):
    cfg = Config.load("config.yaml")
    return baue_overlays(
        rahmen,
        get_instrument("MNQ"),
        cfg,
        symbol="MNQ",
        timeframe="5m",
        level={"prev_day_high": 20100.0, "asia_low": 19900.0},
    )


def test_alle_vom_frontend_erwarteten_schluessel_sind_da(overlays):
    """Fehlt ein Feld, wirft React 'Cannot read properties of undefined'
    und der Chart bleibt schwarz - genau das ist am 29.08.2026 passiert."""
    for schluessel in ("symbol", "timeframe", "swings", "fvgs", "pools",
                       "sweeps", "structure_events", "displacements"):
        assert schluessel in overlays


def test_es_werden_tatsaechlich_primitive_erkannt(overlays):
    assert overlays["swings"], "keine Swings erkannt"
    assert overlays["fvgs"], "keine Fair Value Gaps erkannt"


def test_zeitstempel_sind_nanosekunden(overlays):
    """Das Frontend rechnet in Nanosekunden. Millisekunden waeren um den
    Faktor 1.000.000 daneben und der Chart zeichnete ins Jahr 1970."""
    for swing in overlays["swings"]:
        assert swing["ts"] > 1_000_000_000_000_000_000


def test_offene_gaps_haben_vorrang_vor_geschlossenen(overlays):
    """Ein noch offener Gap von gestern ist wichtiger als ein geschlossener
    von vor zehn Minuten - die Obergrenze darf ihn nicht verdraengen."""
    zustaende = {g["state"] for g in overlays["fvgs"]}
    assert zustaende, "keine Gaps"
    offen = [g for g in overlays["fvgs"] if g["state"] == "open"]
    if len(overlays["fvgs"]) >= MAX_PRIMITIVE:
        assert offen, "bei voller Liste muessen die offenen Gaps enthalten sein"


def test_benannte_niveaus_werden_zu_liquiditaetszonen(overlays):
    """Asia-, London- und Vortagesniveaus sind Orte, an denen Stops liegen.

    Genau danach hatte Laurin gefragt: "da war zum Beispiel das London High,
    da war das Asia High".
    """
    beschriftungen = {p["label"] for p in overlays["pools"]}
    assert "prev_day_high" in beschriftungen
    assert "asia_low" in beschriftungen

    asia = next(p for p in overlays["pools"] if p["label"] == "asia_low")
    assert asia["kind"] == "session"
    assert asia["side"] == "sell_side"     # ein Tief ist Sell-Side-Liquiditaet


def test_hochs_sind_buy_side_und_tiefs_sell_side(overlays):
    for pool in overlays["pools"]:
        if pool["label"].endswith("_high"):
            assert pool["side"] == "buy_side"
        elif pool["label"].endswith("_low"):
            assert pool["side"] == "sell_side"


def test_obergrenze_wird_eingehalten(overlays):
    """Ein Chart mit 400 Gaps ist unlesbar, und die Uebertragung waechst
    mit jeder Kerze."""
    for schluessel in ("swings", "fvgs", "sweeps", "structure_events",
                       "displacements"):
        assert len(overlays[schluessel]) <= MAX_PRIMITIVE


def test_leerer_rahmen_liefert_die_leere_struktur_statt_eines_fehlers():
    leer = pd.DataFrame(
        columns=["open", "high", "low", "close", "volume"],
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    ergebnis = baue_overlays(
        leer, get_instrument("MNQ"), Config.load("config.yaml"),
        symbol="MNQ", timeframe="5m",
    )
    assert ergebnis["fvgs"] == []
    assert ergebnis["symbol"] == "MNQ"


def test_richtungen_sind_bullish_oder_bearish(overlays):
    """Der types.ts-Vertrag kennt nur diese beiden Werte."""
    for gap in overlays["fvgs"]:
        assert gap["direction"] in ("bullish", "bearish")
    for d in overlays["displacements"]:
        assert d["direction"] in ("bullish", "bearish")


# -- Analyse ----------------------------------------------------------------

def test_analyse_bewertet_jede_uebergebene_zeitebene(rahmen):
    cfg = Config.load("config.yaml")
    ergebnis = baue_analyse({"5m": rahmen, "15m": rahmen}, cfg, symbol="MNQ")

    assert set(ergebnis["timeframes"]) == {"5m", "15m"}
    assert ergebnis["bias"]["bias"] in ("bullish", "bearish", "neutral")
    assert len(ergebnis["bias"]["reasons"]) == 2


def test_analyse_ohne_daten_meldet_neutral_statt_zu_raten(rahmen):
    cfg = Config.load("config.yaml")
    leer = rahmen.iloc[0:0]
    ergebnis = baue_analyse({"5m": leer}, cfg, symbol="MNQ")

    assert ergebnis["timeframes"] == {}
    assert ergebnis["bias"]["bias"] == "neutral"
    assert ergebnis["bias"]["score"] == 0.0


def test_analyse_nutzt_assess_trend_und_keine_eigene_formel():
    """Invariante: keine zweite Trendbewertung.

    Der Quelltext des Adapters darf keine eigene Trendlogik enthalten,
    sondern muss ``assess_trend`` aufrufen - sonst zeigte die Oberflaeche
    einen anderen Trend als der ``/analyse``-Bericht.
    """
    import inspect

    import execution.overlays as modul

    quelltext = inspect.getsource(modul.baue_analyse)
    assert "assess_trend(" in quelltext
    assert "classify_market_structure(" in quelltext
