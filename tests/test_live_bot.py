"""Tests des Live-Bots: Kerzenaggregation, Alarme, Rate-Limiting, Claude-Payload."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from common.config import AlertConfig, ConditionConfig
from live_bot.ai.claude_client import DISCLAIMER, SYSTEM_PROMPT, build_metrics_payload
from live_bot.alerts.conditions import (
    FLAG_BREAKOUT,
    PREV_DAY_HIGH_CROSS,
    PREV_DAY_LOW_CROSS,
    RSI_EXIT_OVERBOUGHT,
    RSI_EXIT_OVERSOLD,
    Alert,
    ConditionEvaluator,
)
from live_bot.alerts.cooldown import CooldownTracker
from live_bot.market.candles import (
    CandleAggregator,
    CandleBuffer,
    candles_from_tradovate_bars,
    tick_from_quote,
)
from live_bot.market.state import MarketSnapshot
from live_bot.notify.notifier import format_alert_message

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Kerzenaggregation
# ---------------------------------------------------------------------------

def test_aggregator_schliesst_kerze_erst_im_naechsten_intervall():
    aggregator = CandleAggregator(1)
    base = datetime(2025, 1, 2, 15, 0, 0, tzinfo=UTC)

    assert aggregator.add_tick(base, 100.0, 1) is None
    assert aggregator.add_tick(base + timedelta(seconds=30), 102.0, 2) is None

    closed = aggregator.add_tick(base + timedelta(minutes=1), 101.0, 1)

    assert closed is not None
    assert closed.open == 100.0
    assert closed.high == 102.0
    assert closed.low == 100.0
    assert closed.close == 102.0
    assert closed.volume == 3.0
    # Die neue Kerze laeuft bereits.
    assert aggregator.current is not None
    assert aggregator.current.open == 101.0


def test_aggregator_verwirft_verspaetete_ticks():
    aggregator = CandleAggregator(1)
    base = datetime(2025, 1, 2, 15, 1, 0, tzinfo=UTC)
    aggregator.add_tick(base, 100.0, 1)

    # Tick aus dem bereits abgeschlossenen Vorintervall
    assert aggregator.add_tick(base - timedelta(minutes=1), 999.0, 1) is None
    assert aggregator.current.high == 100.0


def test_close_expired_schliesst_kerze_auch_ohne_neue_ticks():
    aggregator = CandleAggregator(1)
    base = datetime(2025, 1, 2, 15, 0, 0, tzinfo=UTC)
    aggregator.add_tick(base, 100.0, 1)

    assert aggregator.close_expired(base + timedelta(seconds=30)) is None

    closed = aggregator.close_expired(base + timedelta(minutes=1, seconds=1))
    assert closed is not None
    assert closed.close == 100.0
    assert aggregator.current is None


def test_candle_buffer_ist_rollierend_und_sortiert():
    buffer = CandleBuffer(3)
    aggregator = CandleAggregator(1)
    base = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)

    for minute in range(6):
        aggregator.add_tick(base + timedelta(minutes=minute), 100.0 + minute, 1)
        closed = aggregator.close_expired(base + timedelta(minutes=minute + 1, seconds=1))
        if closed:
            buffer.append(closed)

    assert len(buffer) <= 3
    frame = buffer.to_dataframe()
    assert frame.index.is_monotonic_increasing
    assert str(frame.index.tz) == "UTC"


def test_tick_aus_quote_bevorzugt_echte_trades():
    quote = {
        "timestamp": "2025-01-02T15:00:00Z",
        "entries": {
            "Bid": {"price": 20000.0, "size": 5},
            "Offer": {"price": 20001.0, "size": 5},
            "Trade": {"price": 20000.5, "size": 3},
        },
    }
    tick = tick_from_quote(quote)
    assert tick is not None
    assert tick.price == pytest.approx(20000.5)
    assert tick.size == 3.0


def test_tick_aus_quote_faellt_auf_mittelkurs_zurueck_ohne_volumen():
    quote = {
        "timestamp": "2025-01-02T15:00:00Z",
        "entries": {"Bid": {"price": 20000.0}, "Offer": {"price": 20002.0}},
    }
    tick = tick_from_quote(quote)
    assert tick is not None
    assert tick.price == pytest.approx(20001.0)
    # Ohne echten Trade darf kein Volumen erfunden werden.
    assert tick.size == 0.0


def test_tick_aus_quote_ohne_preise_ist_none():
    assert tick_from_quote({"timestamp": "2025-01-02T15:00:00Z", "entries": {}}) is None


def test_tradovate_bars_werden_normalisiert():
    bars = [
        {
            "timestamp": "2025-01-02T15:00:00Z",
            "open": 100, "high": 101, "low": 99, "close": 100.5,
            "upVolume": 30, "downVolume": 20,
        },
        {"timestamp": "kaputt", "open": 1, "high": 1, "low": 1, "close": 1},
        {"timestamp": "2025-01-02T15:01:00Z", "open": 100.5},   # unvollstaendig
    ]
    candles = candles_from_tradovate_bars(bars, 1)

    assert len(candles) == 1
    assert candles[0].volume == 50.0
    assert candles[0].close == 100.5


# ---------------------------------------------------------------------------
# Alarm-Bedingungen
# ---------------------------------------------------------------------------

def snapshot(**overrides) -> MarketSnapshot:
    defaults = dict(
        symbol="NQZ5",
        timestamp=datetime(2025, 1, 2, 15, 0, tzinfo=UTC),
        interval_minutes=1,
        bars_available=300,
        open=20000.0,
        high=20010.0,
        low=19990.0,
        close=20005.0,
        volume=1000.0,
        rsi=50.0,
        sma_fast=20000.0,
        sma_slow=19990.0,
        vwap=20002.0,
        atr=15.0,
        session_date=date(2025, 1, 2),
        prev_session_high=20050.0,
        prev_session_low=19950.0,
        prev_session_close=20000.0,
        flag_direction=0,
        flag_in_consolidation=False,
        flag_breakout_up=False,
        flag_breakout_down=False,
        flag_range_high=None,
        flag_range_low=None,
    )
    defaults.update(overrides)
    return MarketSnapshot(**defaults)


@pytest.fixture
def evaluator(market_cfg) -> ConditionEvaluator:
    config = AlertConfig(
        default_cooldown_minutes=30,
        max_alerts_per_session=0,
        conditions={
            PREV_DAY_HIGH_CROSS: ConditionConfig(enabled=True, buffer_ticks=4),
            PREV_DAY_LOW_CROSS: ConditionConfig(enabled=True, buffer_ticks=4),
            RSI_EXIT_OVERBOUGHT: ConditionConfig(enabled=True, level=70),
            RSI_EXIT_OVERSOLD: ConditionConfig(enabled=True, level=30),
            FLAG_BREAKOUT: ConditionConfig(enabled=True),
        },
    )
    return ConditionEvaluator(config, market_cfg)


def test_vortageshoch_kreuzung_loest_aus(evaluator):
    previous = snapshot(close=20040.0)
    current = snapshot(close=20055.0)   # Puffer = 4 Ticks * 0.25 = 1.0 Punkt

    alerts = evaluator.evaluate(previous, current)
    conditions = {alert.condition for alert in alerts}

    assert PREV_DAY_HIGH_CROSS in conditions


def test_vortageshoch_kreuzung_loest_innerhalb_des_puffers_nicht_aus(evaluator):
    previous = snapshot(close=20040.0)
    current = snapshot(close=20050.5)   # nur 0.5 Punkte darueber, Puffer 1.0

    conditions = {alert.condition for alert in evaluator.evaluate(previous, current)}
    assert PREV_DAY_HIGH_CROSS not in conditions


def test_vortageshoch_loest_nicht_erneut_aus_wenn_kurs_schon_darueber_lag(evaluator):
    previous = snapshot(close=20060.0)
    current = snapshot(close=20070.0)

    conditions = {alert.condition for alert in evaluator.evaluate(previous, current)}
    assert PREV_DAY_HIGH_CROSS not in conditions


def test_vortagestief_kreuzung_loest_aus(evaluator):
    previous = snapshot(close=19960.0)
    current = snapshot(close=19945.0)

    conditions = {alert.condition for alert in evaluator.evaluate(previous, current)}
    assert PREV_DAY_LOW_CROSS in conditions


def test_rsi_verlaesst_ueberkaufte_zone(evaluator):
    alerts = evaluator.evaluate(snapshot(rsi=72.0), snapshot(rsi=68.0))
    conditions = {alert.condition for alert in alerts}
    assert RSI_EXIT_OVERBOUGHT in conditions
    assert RSI_EXIT_OVERSOLD not in conditions


def test_rsi_verlaesst_ueberverkaufte_zone(evaluator):
    alerts = evaluator.evaluate(snapshot(rsi=28.0), snapshot(rsi=34.0))
    assert RSI_EXIT_OVERSOLD in {alert.condition for alert in alerts}


def test_rsi_innerhalb_der_zone_loest_nicht_aus(evaluator):
    assert evaluator.evaluate(snapshot(rsi=75.0), snapshot(rsi=78.0)) == []


def test_flaggen_ausbruch_loest_nur_bei_der_flanke_aus(evaluator):
    previous = snapshot(flag_breakout_up=False)
    current = snapshot(flag_breakout_up=True, flag_range_high=20010.0, flag_range_low=19995.0)

    assert FLAG_BREAKOUT in {alert.condition for alert in evaluator.evaluate(previous, current)}
    # Zweite Kerze mit demselben Zustand darf nicht erneut ausloesen.
    assert evaluator.evaluate(current, current) == []


def test_ohne_vorherigen_snapshot_gibt_es_keine_alarme(evaluator):
    assert evaluator.evaluate(None, snapshot()) == []


def test_unfertige_indikatoren_loesen_keine_alarme_aus(evaluator):
    unfertig = snapshot(rsi=None, sma_slow=None, atr=None)
    assert evaluator.evaluate(snapshot(), unfertig) == []


def test_deaktivierte_bedingung_feuert_nicht(market_cfg):
    config = AlertConfig(
        conditions={PREV_DAY_HIGH_CROSS: ConditionConfig(enabled=False, buffer_ticks=0)}
    )
    evaluator = ConditionEvaluator(config, market_cfg)
    assert evaluator.evaluate(snapshot(close=20040.0), snapshot(close=20060.0)) == []


# ---------------------------------------------------------------------------
# Rate-Limiting
# ---------------------------------------------------------------------------

def test_cooldown_sperrt_dieselbe_bedingung():
    config = AlertConfig(default_cooldown_minutes=30, max_alerts_per_session=0)
    tracker = CooldownTracker(config)
    now = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)

    assert tracker.allows("x", now) is True
    tracker.record("x", now)

    assert tracker.allows("x", now + timedelta(minutes=29)) is False
    assert tracker.allows("x", now + timedelta(minutes=31)) is True


def test_cooldown_ist_pro_bedingung_getrennt():
    tracker = CooldownTracker(AlertConfig(default_cooldown_minutes=30))
    now = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)

    tracker.record("a", now)
    assert tracker.allows("a", now + timedelta(minutes=1)) is False
    assert tracker.allows("b", now + timedelta(minutes=1)) is True


def test_bedingungsspezifischer_cooldown_schlaegt_den_standard():
    config = AlertConfig(
        default_cooldown_minutes=30,
        conditions={"kurz": ConditionConfig(enabled=True, cooldown_minutes=5)},
    )
    tracker = CooldownTracker(config)
    now = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)

    tracker.record("kurz", now)
    assert tracker.allows("kurz", now + timedelta(minutes=6)) is True


def test_tageslimit_greift_und_wird_zur_neuen_session_zurueckgesetzt():
    config = AlertConfig(default_cooldown_minutes=0, max_alerts_per_session=2)
    tracker = CooldownTracker(config)
    now = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)
    tag = date(2025, 1, 2)

    tracker.record("a", now, tag)
    tracker.record("b", now, tag)
    assert tracker.allows("c", now, tag) is False

    # Neuer Handelstag -> Zaehler zurueck auf null.
    assert tracker.allows("c", now, date(2025, 1, 3)) is True


# ---------------------------------------------------------------------------
# Claude-Payload und Nachrichtenformat
# ---------------------------------------------------------------------------

def test_claude_payload_enthaelt_nur_kennzahlen():
    alert = Alert(
        condition=PREV_DAY_HIGH_CROSS,
        headline="Test",
        direction="up",
        details={"level": 20050.0},
    )
    payload = build_metrics_payload(snapshot(), alert)

    assert set(payload) == {
        "instrument",
        "kerzenintervall_minuten",
        "zeitpunkt_utc",
        "handelstag",
        "kerze",
        "indikatoren",
        "vortagesmarken",
        "konsolidierung",
        "ausgeloeste_bedingung",
    }
    assert payload["indikatoren"]["rsi_14"] == 50.0
    assert payload["ausgeloeste_bedingung"]["schluessel"] == PREV_DAY_HIGH_CROSS
    # Keine Rohdaten, keine Kerzenliste, keine Bilder.
    assert "bars" not in payload
    assert "ticks" not in payload


def test_systemprompt_verbietet_handelsempfehlungen_und_verlangt_disclaimer():
    assert "NIEMALS eine direkte Kauf- oder Verkaufsempfehlung" in SYSTEM_PROMPT
    assert "Wenn-Dann-Szenarien" in SYSTEM_PROMPT
    assert DISCLAIMER in SYSTEM_PROMPT


def test_alarmnachricht_enthaelt_kennzahlen_und_disclaimer():
    from live_bot.ai.claude_client import ClaudeComment

    alert = Alert(condition=FLAG_BREAKOUT, headline="NQZ5: Ausbruch", direction="up")
    comment = ClaudeComment(text=f"Szenario A ...\n\n{DISCLAIMER}", succeeded=True)

    message = format_alert_message(alert, snapshot(), comment)

    assert "NQZ5: Ausbruch" in message
    assert "RSI(14) 50.0" in message
    assert "VWAP" in message
    assert DISCLAIMER in message


def test_alarmnachricht_funktioniert_ohne_claude():
    alert = Alert(condition=FLAG_BREAKOUT, headline="NQZ5: Ausbruch", direction="up")
    message = format_alert_message(alert, snapshot(), None)

    assert "NQZ5: Ausbruch" in message
    assert "Close: 20005.00" in message


# ---------------------------------------------------------------------------
# Zustellung
# ---------------------------------------------------------------------------

def test_konsolen_fallback_funktioniert_ohne_telegram_konfiguration():
    """Regressionstest: der Fallback-Pfad darf nie selbst eine Exception werfen.

    Er ist genau der Pfad, der greift, wenn ohnehin schon etwas schiefliegt.
    """
    import asyncio

    from common.config import NotifyConfig
    from live_bot.notify.notifier import Notifier

    async def scenario():
        async with Notifier(NotifyConfig(telegram_enabled=True), None, None) as notifier:
            return await notifier.send("Testalarm", context={"condition": "test"})

    result = asyncio.run(scenario())
    assert result.delivered_via == "console"
    assert result.error is None


def test_log_event_vertraegt_payload_felder_mit_reservierten_namen():
    """``message`` als Payload-Feld darf nicht mit dem Parameter kollidieren."""
    import logging as std_logging

    from common.logging_setup import log_event

    logger = std_logging.getLogger("test.log_event")
    # Wuerde bei nicht-positions-only Signatur einen TypeError werfen.
    log_event(logger, "test.event", "Kurztext", message="Payload", event="Payload")
