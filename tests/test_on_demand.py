"""Tests des On-Demand-Berichts (/analyse)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from common.config import (
    AlertConfig,
    BacktestConfig,
    ClaudeConfig,
    Config,
    LoggingConfig,
    NotifyConfig,
    OnDemandConfig,
    TradovateConfig,
)
from live_bot.ai.claude_client import (
    REPORT_DISCLAIMER,
    REPORT_SYSTEM_PROMPT,
    ClaudeComment,
    ClaudeCommentator,
)
from live_bot.notify.notifier import Notifier, split_message
from live_bot.notify.telegram_commands import Command, parse_command
from live_bot.on_demand_report import (
    COMMAND_NAME,
    OnDemandReportService,
    ReportRateLimiter,
    ReportUnavailable,
    build_report_payload,
    format_report_message,
)
from tests.conftest import make_ohlcv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def full_config(market_cfg, indicator_cfg) -> Config:
    return Config(
        tradovate=TradovateConfig(),
        market=market_cfg,
        indicators=indicator_cfg,
        alerts=AlertConfig(),
        claude=ClaudeConfig(),
        on_demand=OnDemandConfig(swing_strength=3, swing_lookback=120, max_zones=3),
        notify=NotifyConfig(telegram_enabled=False),
        logging=LoggingConfig(),
        backtest=BacktestConfig(),
    )


@pytest.fixture
def trending_frame() -> pd.DataFrame:
    """300 Kerzen mit Aufwaertstrend und ein paar sauberen Swings."""
    base = np.linspace(20000, 20250, 300)
    wave = np.sin(np.linspace(0, 8 * np.pi, 300)) * 18.0
    return make_ohlcv(base + wave, spread=1.5)


def make_service(config: Config, frame: pd.DataFrame | None, symbol: str = "NQZ5"):
    async def provider():
        return None if frame is None else (symbol, frame)

    return OnDemandReportService(
        config,
        secrets=None,  # type: ignore[arg-type]  - wird ohne Netzzugriff nicht benutzt
        claude=ClaudeCommentator(config.claude, api_key=None),
        notifier=Notifier(config.notify, None, None),
        live_state_provider=provider,
    )


# ---------------------------------------------------------------------------
# Befehls-Parsing
# ---------------------------------------------------------------------------

def test_parse_command_ohne_argument():
    command = parse_command("/analyse", "123")
    assert command is not None
    assert command.name == "analyse"
    assert command.args == []
    assert command.first_arg is None


def test_parse_command_mit_symbol():
    command = parse_command("/analyse NQ", "123")
    assert command is not None
    assert command.first_arg == "NQ"


def test_parse_command_mit_botnamen():
    """In Gruppen adressiert Telegram Befehle als /analyse@MeinBot."""
    command = parse_command("/analyse@MeinTradingBot ES", "123")
    assert command is not None
    assert command.name == "analyse"
    assert command.first_arg == "ES"


def test_parse_command_ignoriert_normalen_text():
    assert parse_command("guten morgen", "123") is None
    assert parse_command("", "123") is None
    assert parse_command("/", "123") is None


def test_parse_command_normalisiert_grossschreibung():
    command = parse_command("/ANALYSE", "123")
    assert command is not None
    assert command.name == "analyse"


# ---------------------------------------------------------------------------
# Rate-Limiting
# ---------------------------------------------------------------------------

def test_ratelimiter_erlaubt_den_ersten_bericht():
    limiter = ReportRateLimiter(cooldown_seconds=60, max_per_day=10)
    assert limiter.check() is None


def test_ratelimiter_sperrt_waehrend_des_cooldowns():
    limiter = ReportRateLimiter(cooldown_seconds=60, max_per_day=10)
    limiter.record()
    rejection = limiter.check()

    assert rejection is not None
    assert "warten" in rejection


def test_ratelimiter_ohne_cooldown_laesst_durch():
    limiter = ReportRateLimiter(cooldown_seconds=0, max_per_day=10)
    limiter.record()
    assert limiter.check() is None


def test_ratelimiter_setzt_tageslimit_durch():
    limiter = ReportRateLimiter(cooldown_seconds=0, max_per_day=2)
    limiter.record()
    limiter.record()

    rejection = limiter.check()
    assert rejection is not None
    assert "Tageslimit" in rejection


def test_ratelimiter_setzt_zaehler_am_naechsten_tag_zurueck():
    limiter = ReportRateLimiter(cooldown_seconds=0, max_per_day=1)
    limiter.record()
    assert limiter.check() is not None

    morgen = datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert limiter.check(morgen) is None


# ---------------------------------------------------------------------------
# Datensammlung ueber die bestehende Pipeline
# ---------------------------------------------------------------------------

def test_collect_nutzt_den_live_puffer(full_config, trending_frame):
    service = make_service(full_config, trending_frame)
    data = asyncio.run(service.collect(None))

    assert data.symbol == "NQZ5"
    assert data.source == "live-puffer"
    assert data.bars_used == len(trending_frame)
    # Indikatoren stammen aus derselben Pipeline wie Live-Bot und Backtest.
    assert data.snapshot.rsi is not None
    assert data.snapshot.atr is not None
    assert data.snapshot.vwap is not None
    assert data.trend.direction in {"aufwaerts", "abwaerts", "seitwaerts", "unklar"}


def test_collect_findet_zonen_beidseitig(full_config, trending_frame):
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))

    assert data.supports or data.resistances
    for zone in data.supports:
        assert zone.price < data.snapshot.close
    for zone in data.resistances:
        assert zone.price > data.snapshot.close


def test_collect_akzeptiert_produkt_kuerzel_des_laufenden_kontrakts(full_config, trending_frame):
    """"/analyse NQ" soll den laufenden NQZ5-Puffer treffen, nicht nachladen."""
    data = asyncio.run(make_service(full_config, trending_frame).collect("NQ"))
    assert data.source == "live-puffer"
    assert data.symbol == "NQZ5"


def test_collect_meldet_zu_wenige_kerzen(full_config):
    kurz = make_ohlcv(np.linspace(20000, 20010, 20), spread=1.0)
    service = make_service(full_config, kurz)

    with pytest.raises(ReportUnavailable, match="Zu wenige Kerzen"):
        asyncio.run(service.collect(None))


def test_collect_ohne_live_daten_und_ohne_symbol(full_config):
    service = make_service(full_config, None)
    with pytest.raises(ReportUnavailable, match="Live-Puffer"):
        asyncio.run(service.collect(None))


def test_fremdes_symbol_ohne_tradovate_zugang_meldet_klar(full_config, trending_frame):
    service = make_service(full_config, trending_frame)
    with pytest.raises(ReportUnavailable, match="Tradovate-Zugang"):
        asyncio.run(service.collect("ES"))


def test_symbol_override_kann_abgeschaltet_werden(full_config, trending_frame):
    from dataclasses import replace

    config = replace(
        full_config, on_demand=replace(full_config.on_demand, allow_symbol_override=False)
    )
    service = make_service(config, trending_frame)

    with pytest.raises(ReportUnavailable, match="deaktiviert"):
        asyncio.run(service.collect("ES"))


# ---------------------------------------------------------------------------
# Claude-Payload
# ---------------------------------------------------------------------------

def test_payload_enthaelt_alle_geforderten_bloecke(full_config, trending_frame):
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    payload = build_report_payload(data, full_config)

    assert set(payload) == {
        "instrument",
        "kerzenintervall_minuten",
        "zeitpunkt_utc",
        "handelstag",
        "datenquelle",
        "kerzen_im_fenster",
        "kontrakt",
        "kerze",
        "indikatoren",
        "trend",
        "tagesspanne",
        "vortagesmarken",
        "konsolidierung",
        "zonen",
        "letzte_swing_punkte",
    }

    # ATR als Volatilitaetsmass, Zonen und Trend sind die neuen Pflichtfelder.
    assert payload["indikatoren"]["atr"] is not None
    assert payload["indikatoren"]["rsi_14"] is not None
    assert payload["indikatoren"]["vwap_session"] is not None
    assert "richtung" in payload["trend"]
    assert "unterstuetzungen" in payload["zonen"]
    assert "widerstaende" in payload["zonen"]

    # Punktwert wird mitgeschickt, damit Risiko in USD je Kontrakt
    # bezifferbar ist - ohne Positionsgroessen zu empfehlen.
    assert payload["kontrakt"]["punktwert_usd"] == 20.0


def test_payload_enthaelt_keine_rohdaten(full_config, trending_frame):
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    payload = build_report_payload(data, full_config)

    for verboten in ("bars", "ticks", "kerzen", "ohlcv", "dataframe"):
        assert verboten not in payload

    # Swing-Punkte sind aggregierte Extrema, keine Kursreihe.
    assert len(payload["letzte_swing_punkte"]) <= 4


def test_payload_ist_json_serialisierbar(full_config, trending_frame):
    import json

    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    payload = build_report_payload(data, full_config)

    rendered = json.dumps(payload, ensure_ascii=False)
    assert "instrument" in rendered


def test_zonen_im_payload_tragen_beruehrungen_und_abstand(full_config, trending_frame):
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    payload = build_report_payload(data, full_config)

    zonen = payload["zonen"]["unterstuetzungen"] + payload["zonen"]["widerstaende"]
    assert zonen, "Die Testdaten sollten Zonen liefern."
    for zone in zonen:
        assert {"preis", "beruehrungen", "abstand_punkte", "abstand_in_atr"} <= set(zone)
        assert zone["beruehrungen"] >= 1


# ---------------------------------------------------------------------------
# System-Prompt
# ---------------------------------------------------------------------------

def test_report_prompt_verbietet_handlungsanweisungen():
    assert "Keine Handlungsanweisungen" in REPORT_SYSTEM_PROMPT
    for verboten in ('"kaufe"', '"verkaufe"', "du solltest"):
        assert verboten in REPORT_SYSTEM_PROMPT


def test_report_prompt_verlangt_die_geforderten_abschnitte():
    for abschnitt in ("LAGE", "STRUKTUR", "SZENARIO A", "MARKEN", "EINSCHAETZUNG"):
        assert abschnitt in REPORT_SYSTEM_PROMPT

    # Stop-Herleitung, Ziel und CRV muessen ausdruecklich gefordert sein.
    assert "Stop-Marke" in REPORT_SYSTEM_PROMPT
    assert "Chance-Risiko-Verhaeltnis" in REPORT_SYSTEM_PROMPT
    assert "ATR-Vielfachen" in REPORT_SYSTEM_PROMPT


def test_report_prompt_verbietet_positionsgroessen():
    assert "Positionsgroesse" in REPORT_SYSTEM_PROMPT


def test_report_prompt_endet_mit_disclaimer():
    assert REPORT_DISCLAIMER in REPORT_SYSTEM_PROMPT
    assert "schnell aendern" in REPORT_DISCLAIMER


def test_report_prompt_verbietet_markdown():
    """Der Text geht unveraendert an Telegram - Markdown wuerde stoeren."""
    assert "Markdown" in REPORT_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Nachrichtenformat
# ---------------------------------------------------------------------------

def test_berichtsnachricht_enthaelt_zahlenkopf_und_claude_text(full_config, trending_frame):
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    comment = ClaudeComment(text=f"LAGE\nAlles ruhig.\n\n{REPORT_DISCLAIMER}", succeeded=True)

    message = format_report_message(data, comment)

    assert "MARKTBERICHT NQZ5" in message
    assert "RSI" in message and "ATR" in message and "VWAP" in message
    assert "Trend:" in message
    assert "LAGE" in message
    assert REPORT_DISCLAIMER in message


def test_berichtsnachricht_funktioniert_ohne_claude(full_config, trending_frame):
    """Faellt Claude aus, muessen die Kennzahlen trotzdem ankommen."""
    data = asyncio.run(make_service(full_config, trending_frame).collect(None))
    comment = ClaudeComment(text="", succeeded=False, error="Timeout")

    message = format_report_message(data, comment)

    assert "MARKTBERICHT NQZ5" in message
    assert "Timeout" in message
    assert "Kennzahlen oben stammen direkt aus der Pipeline" in message


# ---------------------------------------------------------------------------
# Aufteilung langer Nachrichten
# ---------------------------------------------------------------------------

def test_kurze_nachricht_bleibt_ungeteilt():
    assert split_message("kurz") == ["kurz"]


def test_lange_nachricht_wird_an_absaetzen_geteilt():
    absatz = "A" * 1000
    text = "\n\n".join([absatz] * 6)   # 6000+ Zeichen

    chunks = split_message(text, limit=2500)

    assert len(chunks) > 1
    assert all(len(chunk) <= 2500 for chunk in chunks)
    # Nichts darf verloren gehen.
    assert sum(chunk.count("A") for chunk in chunks) == 6000


def test_ueberlanger_einzelabsatz_wird_hart_geschnitten():
    text = "B" * 5000
    chunks = split_message(text, limit=1000)

    assert len(chunks) == 5
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_send_long_nutzt_den_konsolen_fallback(full_config):
    async def scenario():
        async with Notifier(NotifyConfig(telegram_enabled=False), None, None) as notifier:
            return await notifier.send_long("Ein Bericht.\n\nMit zwei Absaetzen.")

    result = asyncio.run(scenario())
    assert result.delivered_via == "console"


# ---------------------------------------------------------------------------
# Befehlsverarbeitung Ende-zu-Ende (ohne Netz)
# ---------------------------------------------------------------------------

def test_unbekannter_befehl_wird_beantwortet(full_config, trending_frame):
    service = make_service(full_config, trending_frame)

    async def scenario():
        async with service._notifier:  # noqa: SLF001 - im Test bewusst
            await service.handle_command(Command(name="quatsch", chat_id="1"))

    asyncio.run(scenario())   # darf nicht werfen


def test_analyse_ohne_claude_liefert_trotzdem_kennzahlen(full_config, trending_frame, capsys):
    """Ohne API-Key laeuft der komplette Pfad bis zur Konsolenzustellung durch."""
    service = make_service(full_config, trending_frame)

    async def scenario():
        async with service._notifier:  # noqa: SLF001
            await service.handle_command(Command(name=COMMAND_NAME, chat_id="1"))

    asyncio.run(scenario())

    ausgabe = capsys.readouterr().out
    assert "MARKTBERICHT NQZ5" in ausgabe
    assert "Claude-Analyse nicht verfuegbar" in ausgabe


def test_zweite_anfrage_wird_durch_cooldown_gebremst(full_config, trending_frame, capsys):
    service = make_service(full_config, trending_frame)

    async def scenario():
        async with service._notifier:  # noqa: SLF001
            await service.handle_command(Command(name=COMMAND_NAME, chat_id="1"))
            await service.handle_command(Command(name=COMMAND_NAME, chat_id="1"))

    asyncio.run(scenario())

    ausgabe = capsys.readouterr().out
    assert ausgabe.count("MARKTBERICHT NQZ5") == 1
    assert "warten" in ausgabe
