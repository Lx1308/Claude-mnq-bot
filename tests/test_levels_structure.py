"""Tests fuer Level-Berechnung, Marktstruktur und RSI-Divergenz."""

from __future__ import annotations

from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

from common.config import SessionConfig
from common.indicators import compute_indicators
from common.instruments import MGC, MNQ
from common.levels import (
    SESSIONS_REQUIRED,
    compute_levels,
    history_dependent_metrics,
    make_level,
    overnight_mask,
    rth_mask,
    volume_profile,
)
from common.structure import (
    classify_market_structure,
    detect_rsi_divergence,
)
from tests.conftest import make_ohlcv


def zigzag(turning_points, *, bars_per_leg=10, spread=0.5):
    """Baut eine Zickzack-Reihe durch die angegebenen Wendepunkte.

    Wichtig fuer Swing-Tests: die Ruecksetzer muessen tief genug sein, dass
    nach einem Hoch tatsaechlich mehrere tiefere Hochs folgen. Steigt die
    Reihe je Schritt staerker als sie zurueckgeht, sind die Hochs faktisch
    monoton und die Fraktal-Erkennung findet zu Recht keinen einzigen Swing.
    """
    closes: list[float] = []
    for start, end in zip(turning_points, turning_points[1:]):
        closes.extend(np.linspace(start, end, bars_per_leg, endpoint=False))
    closes.append(float(turning_points[-1]))
    return make_ohlcv(closes, spread=spread)


def extend_with(frame, target, *, bars=6, spread=0.5):
    """Haengt eine gerichtete Bewegung bis ``target`` an einen Frame an."""
    last_close = float(frame["close"].iloc[-1])
    extra = np.linspace(last_close, target, bars + 1)[1:]
    tail = make_ohlcv(extra, spread=spread)
    tail.index = pd.date_range(
        start=frame.index[-1] + pd.Timedelta(minutes=1),
        periods=len(extra),
        freq="1min",
        tz="UTC",
    )
    return pd.concat([frame, tail])


def rth_frame(closes, *, start_et="2025-06-10 09:30", freq="1min", spread=1.0):
    """OHLCV-Frame mit Startzeit in New Yorker Boersenzeit."""
    index = pd.date_range(
        start=pd.Timestamp(start_et, tz="America/New_York"),
        periods=len(closes),
        freq=freq,
    ).tz_convert("UTC")
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + spread,
            "low": np.minimum(opens, closes) - spread,
            "close": closes,
            "volume": np.full(len(closes), 100.0),
        },
        index=index,
    )


# ---------------------------------------------------------------------------
# Level-Grundlagen
# ---------------------------------------------------------------------------

def test_level_abstand_in_punkten_ticks_und_atr():
    level = make_level("test", 21050.0, 21000.0, MNQ, atr_value=25.0)

    assert level is not None
    assert level.distance_points == pytest.approx(50.0)
    assert level.distance_ticks == pytest.approx(200.0)      # 50 / 0.25
    assert level.distance_atr == pytest.approx(2.0)          # 50 / 25
    assert level.side == "above"


def test_level_unterhalb_hat_negatives_vorzeichen():
    level = make_level("test", 20950.0, 21000.0, MNQ, atr_value=25.0)
    assert level.distance_points == pytest.approx(-50.0)
    assert level.side == "below"


def test_level_ohne_preis_ist_none():
    assert make_level("test", None, 21000.0, MNQ, atr_value=25.0) is None
    assert make_level("test", float("nan"), 21000.0, MNQ, atr_value=25.0) is None


def test_level_ohne_atr_liefert_none_statt_zu_raten():
    level = make_level("test", 21050.0, 21000.0, MNQ, atr_value=None)
    assert level.distance_atr is None
    assert level.distance_points == pytest.approx(50.0)


def test_gleiche_punktdistanz_ist_bei_mnq_und_mgc_unterschiedlich_weit():
    """Der Grund, warum jeder Level auch in ATR ausgewiesen wird."""
    mnq_level = make_level("x", 21020.0, 21000.0, MNQ, atr_value=20.0)
    mgc_level = make_level("x", 2420.0, 2400.0, MGC, atr_value=4.0)

    assert mnq_level.distance_points == mgc_level.distance_points == pytest.approx(20.0)
    assert mnq_level.distance_atr == pytest.approx(1.0)
    assert mgc_level.distance_atr == pytest.approx(5.0)   # bei MGC eine Weltreise


# ---------------------------------------------------------------------------
# Fenster-Masken
# ---------------------------------------------------------------------------

def test_rth_maske_trifft_die_regulaere_handelszeit():
    frame = rth_frame([21000.0] * 60, start_et="2025-06-10 09:00")
    mask = rth_mask(frame, MNQ)

    # 09:00-09:29 sind ausserhalb, ab 09:30 innerhalb
    assert not mask.iloc[0]
    assert mask.iloc[30]


def test_rth_maske_unterscheidet_mnq_und_mgc():
    frame = rth_frame([2400.0] * 120, start_et="2025-06-10 08:00")

    mnq_mask = rth_mask(frame, MNQ)   # ab 09:30
    mgc_mask = rth_mask(frame, MGC)   # ab 08:20

    assert mgc_mask.iloc[30] and not mnq_mask.iloc[30]     # 08:30
    assert mgc_mask.iloc[100] and mnq_mask.iloc[100]        # 09:40


def test_overnight_maske_deckt_die_nachtsitzung_ab():
    frame = rth_frame([21000.0] * 30, start_et="2025-06-10 03:00")
    mask = overnight_mask(frame, MNQ)
    assert mask.all()   # 03:00-03:29 ET liegt vor RTH-Start


# ---------------------------------------------------------------------------
# Tagesniveaus
# ---------------------------------------------------------------------------

def test_initial_balance_und_opening_range_werden_berechnet():
    # 120 Minuten ab RTH-Eroeffnung, Kurs steigt gleichmaessig
    frame = rth_frame(np.linspace(21000, 21120, 120), start_et="2025-06-10 09:30")
    levels = compute_levels(frame, MNQ, atr_value=10.0)

    ib_high = levels.price_of("initial_balance_high")
    ib_low = levels.price_of("initial_balance_low")

    assert ib_low is not None and ib_high is not None
    assert ib_low < ib_high
    assert levels.initial_balance_complete is True

    # Opening Ranges muessen mit dem Fenster wachsen
    or5 = levels.opening_ranges["5m"]["range_points"]
    or15 = levels.opening_ranges["15m"]["range_points"]
    or30 = levels.opening_ranges["30m"]["range_points"]
    assert or5 <= or15 <= or30


def test_initial_balance_ist_unvollstaendig_kurz_nach_eroeffnung():
    frame = rth_frame(np.linspace(21000, 21030, 30), start_et="2025-06-10 09:30")
    levels = compute_levels(frame, MNQ, atr_value=10.0)

    assert levels.initial_balance_complete is False
    assert levels.opening_ranges["5m"]["complete"] is True
    assert levels.opening_ranges["30m"]["complete"] is False


def test_tageshoch_und_tief_stammen_aus_dem_laufenden_handelstag():
    frame = rth_frame([21000, 21050, 20980, 21020], start_et="2025-06-10 10:00", spread=0.0)
    levels = compute_levels(frame, MNQ, atr_value=10.0)

    assert levels.price_of("day_high") == pytest.approx(21050.0)
    assert levels.price_of("day_low") == pytest.approx(20980.0)


def test_vortagesmarken_fehlen_mit_begruendung_wenn_nur_ein_tag_geladen_ist():
    frame = rth_frame([21000.0] * 60, start_et="2025-06-10 10:00")
    levels = compute_levels(frame, MNQ, atr_value=10.0)

    assert levels.price_of("prev_day_high") is None
    assert "previous_day" in levels.unavailable


def test_vortagesmarken_werden_ueber_zwei_sessions_erkannt():
    # Tag 1: 10:00-11:00 ET, Tag 2: 10:00-11:00 ET am Folgetag
    tag1 = rth_frame(np.linspace(21000, 21100, 60), start_et="2025-06-10 10:00", spread=0.0)
    tag2 = rth_frame(np.linspace(21050, 21080, 60), start_et="2025-06-11 10:00", spread=0.0)
    frame = pd.concat([tag1, tag2])

    levels = compute_levels(frame, MNQ, atr_value=10.0)

    assert levels.price_of("prev_day_high") == pytest.approx(21100.0)
    assert levels.price_of("prev_day_low") == pytest.approx(21000.0)
    assert levels.price_of("prev_day_close") == pytest.approx(21100.0)


# ---------------------------------------------------------------------------
# Gap
# ---------------------------------------------------------------------------

def test_offene_aufwaertsluecke_wird_erkannt():
    tag1 = rth_frame([21000.0] * 60, start_et="2025-06-10 10:00", spread=0.0)
    # Eroeffnung 100 Punkte hoeher, Kurs faellt nie auf 21000 zurueck
    tag2 = rth_frame([21100.0] * 60, start_et="2025-06-11 09:30", spread=0.0)
    frame = pd.concat([tag1, tag2])

    gap = compute_levels(frame, MNQ, atr_value=10.0).gap

    assert gap["available"] is True
    assert gap["direction"] == "up"
    assert gap["gap_points"] == pytest.approx(100.0)
    assert gap["filled"] is False


def test_geschlossene_luecke_wird_als_geschlossen_gemeldet():
    tag1 = rth_frame([21000.0] * 60, start_et="2025-06-10 10:00", spread=0.0)
    # Eroeffnung hoeher, faellt dann unter den Vortagesschluss
    tag2 = rth_frame([21100.0] * 10 + [20990.0] * 50, start_et="2025-06-11 09:30", spread=0.0)
    frame = pd.concat([tag1, tag2])

    gap = compute_levels(frame, MNQ, atr_value=10.0).gap

    assert gap["direction"] == "up"
    assert gap["filled"] is True


# ---------------------------------------------------------------------------
# Cache-abhaengige Felder
# ---------------------------------------------------------------------------

def multi_session_frame(sessions: int, *, bars_per_session: int = 30, base: float = 21000.0):
    """Baut einen Frame ueber mehrere Handelstage (je 10:00-ET-Block)."""
    frames = []
    for day in range(sessions):
        start = pd.Timestamp("2025-06-02 10:00", tz="America/New_York") + pd.Timedelta(days=day)
        if start.weekday() >= 5:      # Wochenenden ueberspringen
            continue
        closes = base + day * 5 + np.linspace(0, 20, bars_per_session)
        frames.append(rth_frame(closes, start_et=str(start)[:16], spread=2.0))
    return pd.concat(frames)


def test_historienabhaengige_felder_sind_null_solange_daten_fehlen(session_cfg):
    """Ein Tag Historie reicht fuer keine dieser Kennzahlen."""
    frame = multi_session_frame(1)
    metrics = history_dependent_metrics(frame, MNQ, session_cfg)

    for name in ("week_high", "week_low", "relative_volume", "atr_percentile"):
        assert metrics[name]["value"] is None
        assert metrics[name]["available"] is False
        assert metrics[name]["sessions_required"] == SESSIONS_REQUIRED[
            name if name != "atr_percentile" else "atr_percentile"
        ]
        # Es muss dranstehen, WAS noch fehlt - nicht nur dass etwas fehlt.
        assert "Handelssessions" in metrics[name]["reason"]


def test_wochenmarken_werden_ab_genug_sessions_berechnet(session_cfg):
    frame = multi_session_frame(9)
    metrics = history_dependent_metrics(frame, MNQ, session_cfg)

    assert metrics["week_high"]["available"] is True
    assert metrics["week_low"]["available"] is True
    assert metrics["week_high"]["value"] > metrics["week_low"]["value"]
    assert metrics["week_high"]["sessions_available"] >= SESSIONS_REQUIRED["week_high"]


def test_volume_profile_liefert_poc_zwischen_vah_und_val(session_cfg):
    frame = multi_session_frame(4)
    metrics = history_dependent_metrics(frame, MNQ, session_cfg)
    profile = metrics["volume_profile"]

    assert profile["available"] is True
    assert profile["naeherung"] is True, "Die Naeherung muss als solche markiert sein."

    heute = profile["heute"]
    assert heute is not None
    assert heute["val"] <= heute["poc"] <= heute["vah"]
    assert 0.6 <= heute["abgedeckter_volumenanteil"] <= 1.0


def test_volume_profile_findet_den_meistgehandelten_bereich():
    """Kuenstliche Verteilung: das meiste Volumen liegt um 21050."""
    closes = [21000.0] * 5 + [21050.0] * 40 + [21100.0] * 5
    frame = rth_frame(closes, start_et="2025-06-10 10:00", spread=1.0)

    profile = volume_profile(frame, MNQ)

    assert profile is not None
    assert abs(profile["poc"] - 21050.0) < 15.0


def test_volume_profile_ohne_volumen_ist_none():
    frame = rth_frame([21000.0] * 30, start_et="2025-06-10 10:00")
    frame["volume"] = 0.0
    assert volume_profile(frame, MNQ) is None


def test_relatives_volumen_vergleicht_dieselbe_uhrzeit(session_cfg):
    # 25 Kalendertage ergeben rund 18 Handelstage - genug fuer die
    # geforderten 10 abgeschlossenen Sessions.
    frame = multi_session_frame(25)
    metrics = history_dependent_metrics(frame, MNQ, session_cfg)
    relative = metrics["relative_volume"]

    assert relative["available"] is True
    # Alle Sessions haben dasselbe Volumen -> Verhaeltnis nahe 1
    assert relative["value"] == pytest.approx(1.0, abs=0.2)
    assert "selben Tageszeit" in relative["hinweis"]


def test_atr_perzentil_braucht_atr_spalte(session_cfg, indicator_cfg):
    # 35 Kalendertage ergeben rund 25 Handelstage - genug fuer die
    # geforderten 20 abgeschlossenen Sessions.
    frame = multi_session_frame(35)
    ohne = history_dependent_metrics(frame, MNQ, session_cfg, atr_series=None)
    assert ohne["atr_percentile"]["available"] is False

    enriched = compute_indicators(frame, indicator_cfg, session_cfg)
    mit = history_dependent_metrics(
        enriched, MNQ, session_cfg, atr_series=enriched["atr"]
    )
    assert mit["atr_percentile"]["available"] is True
    assert 0.0 <= mit["atr_percentile"]["value"] <= 100.0


def test_leerer_frame_liefert_alle_felder_als_nicht_verfuegbar(session_cfg):
    leer = rth_frame([21000.0]).iloc[0:0]
    metrics = history_dependent_metrics(leer, MNQ, session_cfg)

    assert set(metrics) == set(SESSIONS_REQUIRED)
    for entry in metrics.values():
        assert entry["available"] is False


# ---------------------------------------------------------------------------
# Marktstruktur
# ---------------------------------------------------------------------------

# Hochs 21100 -> 21160 -> 21220 (HH), Tiefs 21040 -> 21100 (HL)
UPTREND_POINTS = [21000, 21100, 21040, 21160, 21100, 21220, 21160]
DOWNTREND_POINTS = [21220, 21120, 21180, 21060, 21120, 21000, 21060]


def test_aufwaertsstruktur_wird_als_uptrend_erkannt():
    structure = classify_market_structure(
        zigzag(UPTREND_POINTS), strength=2, lookback=100
    )
    assert structure.trend == "uptrend"


def test_abwaertsstruktur_wird_als_downtrend_erkannt():
    structure = classify_market_structure(
        zigzag(DOWNTREND_POINTS), strength=2, lookback=100
    )
    assert structure.trend == "downtrend"


def test_zu_wenige_swings_ergeben_unklare_struktur():
    frame = make_ohlcv([21000.0] * 20, spread=0.5)
    structure = classify_market_structure(frame, strength=3)

    assert structure.trend == "unklar"
    assert structure.labelled_swings == []
    assert "Zu wenige" in structure.description


def test_intakter_aufwaertstrend_meldet_weder_bos_noch_choch():
    """Kurs liegt zwischen letztem Swing-Hoch und letztem hoeheren Tief."""
    structure = classify_market_structure(
        zigzag(UPTREND_POINTS), strength=2, lookback=100
    )

    assert structure.break_of_structure is False
    assert structure.change_of_character is False


def test_break_of_structure_im_aufwaertstrend():
    """Kurs schliesst ueber dem letzten Swing-Hoch - Fortsetzung."""
    frame = extend_with(zigzag(UPTREND_POINTS), 21300.0)
    structure = classify_market_structure(frame, strength=2, lookback=100)

    assert structure.break_of_structure is True
    assert structure.bos_direction == "up"
    assert structure.bos_level == pytest.approx(21220.0, abs=1.0)
    assert structure.change_of_character is False


def test_change_of_character_im_aufwaertstrend():
    """Kurs faellt unter das letzte hoehere Tief - Charakterwechsel."""
    frame = extend_with(zigzag(UPTREND_POINTS), 21000.0)
    structure = classify_market_structure(frame, strength=2, lookback=100)

    assert structure.change_of_character is True
    assert structure.choch_direction == "down"
    assert structure.break_of_structure is False


def test_bos_und_choch_schliessen_sich_aus():
    """Beides gleichzeitig waere ein Widerspruch - der Kurs kann nur eine Seite brechen."""
    for target in (21300.0, 21000.0):
        structure = classify_market_structure(
            extend_with(zigzag(UPTREND_POINTS), target), strength=2, lookback=100
        )
        assert not (structure.break_of_structure and structure.change_of_character)


def test_swing_labels_werden_vergeben():
    structure = classify_market_structure(
        zigzag(UPTREND_POINTS), strength=2, lookback=100
    )
    labels = {swing.label for swing in structure.labelled_swings}

    assert labels & {"HH", "HL"}
    assert all(swing.label in {"HH", "LH", "HL", "LL", "first"}
               for swing in structure.labelled_swings)


# ---------------------------------------------------------------------------
# RSI-Divergenz
# ---------------------------------------------------------------------------

def test_baerische_divergenz_wird_erkannt(indicator_cfg, session_cfg):
    """Kurs macht ein hoeheres Hoch, der Schwung laesst aber nach.

    Erste Spitze mit steilem Anstieg (hoher RSI), zweite Spitze minimal
    hoeher, aber nach flacherem Anstieg - der RSI bleibt zurueck.
    """
    closes = (
        list(np.linspace(21000, 21000, 40))          # ruhiger Vorlauf
        + list(np.linspace(21000, 21200, 20))        # steiler Anstieg
        + list(np.linspace(21200, 21050, 20))        # Ruecksetzer
        + list(np.linspace(21050, 21210, 60))        # flacher Anstieg, hoeheres Hoch
        + list(np.linspace(21210, 21150, 15))        # Ruecksetzer bestaetigt Swing
    )
    frame = compute_indicators(make_ohlcv(closes, spread=1.0), indicator_cfg, session_cfg)

    divergence = detect_rsi_divergence(frame, strength=3, lookback=200)

    assert divergence.detected is True
    assert divergence.kind == "bearish"
    assert divergence.price_second > divergence.price_first
    assert divergence.rsi_second < divergence.rsi_first


def test_keine_divergenz_bei_gleichlaufendem_rsi(indicator_cfg, session_cfg):
    frame = compute_indicators(
        make_ohlcv(np.linspace(21000, 21400, 300), spread=1.0), indicator_cfg, session_cfg
    )
    divergence = detect_rsi_divergence(frame, strength=3, lookback=200)
    assert divergence.detected is False


def test_divergenz_verlangt_rsi_spalte():
    frame = make_ohlcv([21000.0] * 100, spread=1.0)
    with pytest.raises(ValueError, match="rsi"):
        detect_rsi_divergence(frame)
