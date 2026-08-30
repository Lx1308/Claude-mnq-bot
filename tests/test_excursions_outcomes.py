"""Tests fuer backtest/excursions.py und backtest/conditional_outcomes.py."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.conditional_outcomes import analyze_conditional_outcomes
from backtest.excursions import compute_path_excursions
from tests.conftest import make_ohlcv


def test_path_excursions_long_and_short():
    # 20 Kerzen, Einstieg bei Kerze 5
    dates = pd.date_range("2026-08-24 14:00:00", periods=20, freq="5min", tz="UTC")
    closes = [100.0] * 5 + [105.0, 110.0, 115.0, 95.0, 90.0] + [100.0] * 10
    df = make_ohlcv(closes, start=dates[0], spread=1.0)
    df["atr"] = 5.0

    # Long Exkursion ab Kerze 5 (Ausfuehrung auf Kerze 6 Open)
    long_exc = compute_path_excursions(df, entry_indices=[5], direction=1, horizon_bars=5)
    assert len(long_exc) == 1
    e_long = long_exc[0]
    assert e_long.direction == 1
    assert e_long.entry_price == df["open"].iloc[6]
    # Maximum High in den 5 Kerzen nach Einstieg
    assert e_long.mfe_points >= 4.0
    assert e_long.mae_points >= 9.0

    # Short Exkursion
    short_exc = compute_path_excursions(df, entry_indices=[5], direction=-1, horizon_bars=5)
    assert len(short_exc) == 1
    e_short = short_exc[0]
    assert e_short.direction == -1
    assert e_short.mfe_points == e_long.mae_points


def test_conditional_outcomes_analysis():
    # 100 Kerzen mit simuliertem Trend-Verhalten
    dates = pd.date_range("2026-08-24 14:00:00", periods=100, freq="5min", tz="UTC")
    closes = np.linspace(100, 200, 100)
    df = make_ohlcv(closes, start=dates[0], spread=0.5)
    df["atr"] = 5.0

    # Bedingung: jede 5. Kerze
    cond_mask = np.zeros(100, dtype=bool)
    cond_mask[::5] = True

    report = analyze_conditional_outcomes(
        df,
        cond_mask,
        condition_name="Aufwaertstrend_Test",
        direction=1,
        horizon_bars=10,
        target_r_grid=(1.0, 2.0),
        stop_r_grid=(1.0, 2.0),
    )

    assert report.sample_size > 0
    assert report.unconditional_sample_size > report.sample_size
    assert report.mean_return_pts > 0.0
    assert len(report.target_stop_grid) == 4
    # Serialisierung testen
    d = report.to_dict()
    assert d["bedingung"] == "Aufwaertstrend_Test"
    assert "target_stop_matrix" in d


# ---------------------------------------------------------------------------
# Ueberlappung - der Defekt vom 30.08.2026
# ---------------------------------------------------------------------------

def test_ueberschneidungsfreie_stichprobe_ist_kleiner():
    """Die Vorwaertsfenster benachbarter Kerzen teilen sich Kerzen.

    Wer alle Vorkommen als unabhaengig rechnet, ueberschaetzt die
    Signifikanz. Bei einer Dauerbedingung (jede Kerze erfuellt sie) muessen
    aus n Vorkommen rund n/Horizont unabhaengige werden.
    """
    import numpy as np
    import pandas as pd

    from backtest.conditional_outcomes import analyze_conditional_outcomes

    n, horizont = 2000, 20
    rng = np.random.default_rng(30082026)
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 5.0, n))
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise, "high": preise + 6.0, "low": preise - 6.0,
            "close": preise, "volume": 1000.0,
        },
        index=index,
    )
    immer = pd.Series(True, index=index)

    bericht = analyze_conditional_outcomes(
        df, immer, condition_name="immer", horizon_bars=horizont,
        atr_series=pd.Series(10.0, index=index),
    )

    assert bericht.sample_size_unabhaengig < bericht.sample_size
    erwartet = bericht.sample_size / horizont
    assert erwartet * 0.7 <= bericht.sample_size_unabhaengig <= erwartet * 1.3


def test_seltene_bedingung_verliert_kaum_beobachtungen():
    """Gierig statt 'jedes n-te': bei einem Muster, das alle paar hundert
    Kerzen auftritt, sind die Vorkommen ohnehin unabhaengig. Jedes 20. zu
    nehmen wuerde 19 von 20 gueltigen Beobachtungen wegwerfen.
    """
    import numpy as np
    import pandas as pd

    from backtest.conditional_outcomes import analyze_conditional_outcomes

    n, horizont = 4000, 20
    rng = np.random.default_rng(1)
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 5.0, n))
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise, "high": preise + 6.0, "low": preise - 6.0,
            "close": preise, "volume": 1000.0,
        },
        index=index,
    )
    # Alle 100 Kerzen ein Ereignis - weit auseinander, also unabhaengig.
    selten = pd.Series(False, index=index)
    selten.iloc[::100] = True

    bericht = analyze_conditional_outcomes(
        df, selten, condition_name="selten", horizon_bars=horizont,
        atr_series=pd.Series(10.0, index=index),
    )

    assert bericht.sample_size_unabhaengig == bericht.sample_size


def test_der_ueberlappende_p_wert_ist_kleiner_als_der_ehrliche():
    """Der Kern des Defekts, als Test festgehalten.

    Am 30.08.2026 auf echten MNQ-Daten gemessen: t = 8,49 gegen t = 1,71,
    Faktor 4,98 bei Horizont 24 (erwartet sqrt(24) = 4,90).
    """
    import numpy as np
    import pandas as pd

    from backtest.conditional_outcomes import analyze_conditional_outcomes

    n, horizont = 6000, 24
    rng = np.random.default_rng(7)
    # Leichte Aufwaertsdrift, damit ueberhaupt ein Effekt da ist.
    preise = 20000.0 + np.cumsum(rng.normal(0.15, 5.0, n))
    index = pd.date_range("2026-01-05 09:00", periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": preise, "high": preise + 6.0, "low": preise - 6.0,
            "close": preise, "volume": 1000.0,
        },
        index=index,
    )

    # Eine echte Teilmenge mit LANGEN Laeufen - so entsteht Ueberlappung.
    # Bei "immer wahr" waere die Bedingung gleich der Basislinie und t exakt
    # null; der Test haette dann nichts gemessen.
    maske = pd.Series(False, index=index)
    for start in range(0, n, 600):
        maske.iloc[start : start + 300] = True

    bericht = analyze_conditional_outcomes(
        df, maske, condition_name="lange_laeufe",
        horizon_bars=horizont, atr_series=pd.Series(10.0, index=index),
    )

    assert bericht.sample_size_unabhaengig < bericht.sample_size
    assert abs(bericht.t_statistic) > abs(bericht.t_statistic_unabhaengig)
    assert bericht.p_value <= bericht.p_value_unabhaengig
    # Und das Urteil im Bericht haengt am ehrlichen Wert.
    daten = bericht.to_dict()
    assert daten["signifikant_alpha_005"] == (bericht.p_value_unabhaengig < 0.05)
