"""Tests des MCP-Servers und des Snapshot-Aufbaus - ohne Netzzugriff."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

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
from common.instruments import MGC, MNQ
from live_bot.tradovate.contracts import Contract
from mcp_server.bars import DAILY, BarSet, LoadedBars
from mcp_server.snapshot import build_snapshot_payload

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Testdaten
# ---------------------------------------------------------------------------

def synthetic_frame(
    *,
    bars: int,
    minutes: int,
    start: str = "2025-06-09 18:00",
    base: float = 21000.0,
    with_flow: bool = True,
    seed: int = 7,
) -> pd.DataFrame:
    """OHLCV(+Flow) mit Startzeit in New Yorker Boersenzeit."""
    rng = np.random.default_rng(seed)
    index = pd.date_range(
        start=pd.Timestamp(start, tz="America/New_York"),
        periods=bars,
        freq=f"{minutes}min",
    ).tz_convert("UTC")

    closes = base + np.cumsum(rng.normal(0, base * 0.0002, bars))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    spread = base * 0.0003

    frame = pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + spread,
            "low": np.minimum(opens, closes) - spread,
            "close": closes,
            "volume": rng.integers(50, 500, bars).astype(float),
        },
        index=index,
    )
    if with_flow:
        frame["bid_volume"] = rng.integers(10, 250, bars).astype(float)
        frame["ask_volume"] = rng.integers(10, 250, bars).astype(float)
    else:
        frame["bid_volume"] = 0.0
        frame["ask_volume"] = 0.0
    return frame


def make_loaded(
    instrument=MNQ, *, with_flow: bool = True, base: float = 21000.0
) -> LoadedBars:
    """Baut ein LoadedBars-Objekt wie es TradovateBarSource liefern wuerde."""
    specs = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
    counts = {"1m": 900, "5m": 800, "15m": 500, "1h": 300}

    sets = {}
    for timeframe, minutes in specs.items():
        sets[timeframe] = BarSet(
            timeframe=timeframe,
            frame=synthetic_frame(
                bars=counts[timeframe], minutes=minutes, base=base, with_flow=with_flow
            ),
            source="test",
            contract=f"{instrument.root}Z5",
            requested_bars=counts[timeframe],
        )
    sets[DAILY] = BarSet(
        timeframe=DAILY,
        frame=synthetic_frame(bars=120, minutes=1440, base=base, with_flow=with_flow),
        source="test",
        contract=f"{instrument.root}Z5",
        requested_bars=120,
    )

    return LoadedBars(
        symbol=instrument.root,
        contract=Contract(id=1, name=f"{instrument.root}Z5", expiry=None),
        instrument=instrument,
        sets=sets,
    )


@pytest.fixture
def mcp_config(market_cfg, indicator_cfg) -> Config:
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


TIMEFRAMES = ["1m", "5m", "15m", "1h", DAILY]


# ---------------------------------------------------------------------------
# Kein Anthropic-Aufruf im MCP-Pfad
# ---------------------------------------------------------------------------

MCP_MODULES = sorted((PROJECT_ROOT / "mcp_server").glob("*.py"))

VERBOTENE_IMPORTE = {
    "anthropic",
    "live_bot.ai.claude_client",
    "live_bot.ai",
    "live_bot.notify.notifier",
    "backtest.cli",
}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.parametrize("module_path", MCP_MODULES, ids=lambda p: p.name)
def test_mcp_modul_ruft_keine_anthropic_api(module_path: Path):
    """Der Server liefert Daten - interpretiert wird in Claude Desktop.

    Ein Claude-Aufruf im Serverpfad wuerde bei jedem Snapshot Kosten
    erzeugen, die der Nutzer nicht sieht.
    """
    imported = _imported_modules(module_path)
    treffer = imported & VERBOTENE_IMPORTE
    assert not treffer, f"{module_path.name} importiert {treffer}"


def _referenced_names(path: Path) -> set[str]:
    """Alle im CODE verwendeten Namen und Attribute.

    Ueber den AST statt ueber den Dateitext: Docstrings und Kommentare
    erklaeren hier bewusst, warum bestimmte Aufrufe NICHT vorkommen duerfen.
    Eine reine Textsuche wuerde genau diese Erklaerungen als Verstoss werten.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


@pytest.mark.parametrize("module_path", MCP_MODULES, ids=lambda p: p.name)
def test_mcp_quelltext_enthaelt_keinen_claude_aufruf(module_path: Path):
    verboten = {"ClaudeCommentator", "AsyncAnthropic", "Anthropic"}
    treffer = _referenced_names(module_path) & verboten
    assert not treffer, f"{module_path.name} verwendet {treffer}"


@pytest.mark.parametrize("module_path", MCP_MODULES, ids=lambda p: p.name)
def test_server_biegt_stdout_nicht_um(module_path: Path):
    """Regressionstest gegen eine naheliegende, aber schaedliche "Absicherung".

    Der stdio-Transport prueft ``stream.buffer.fileno() == 1``, um fd 1 zu
    beanspruchen, und biegt fd 1 selbst auf stderr um. Zeigte sys.stdout
    bereits auf stderr, schluege diese Pruefung fehl und das Protokoll
    landete auf stderr - der Kanal waere kaputt statt geschuetzt.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr in {"stdout", "stderr"}:
                pytest.fail(
                    f"{module_path.name} weist sys.{target.attr} neu zu - "
                    "das zerstoert den JSON-RPC-Kanal."
                )


# ---------------------------------------------------------------------------
# Snapshot-Aufbau
# ---------------------------------------------------------------------------

def test_snapshot_hat_alle_hauptbloecke(mcp_config):
    payload = build_snapshot_payload(
        make_loaded(), mcp_config, timeframes=TIMEFRAMES
    )

    for key in (
        "meta", "instrument", "session", "datenherkunft",
        "levels", "historienabhaengig", "timeframes",
    ):
        assert key in payload, f"Block {key} fehlt"


def test_snapshot_enthaelt_alle_timeframes(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    assert set(payload["timeframes"]) == set(TIMEFRAMES)


def test_jeder_timeframe_hat_momentum_volatilitaet_volumen_struktur(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)

    for timeframe, block in payload["timeframes"].items():
        for key in ("momentum", "volatilitaet", "volumen", "struktur", "muster"):
            assert key in block, f"{timeframe}: {key} fehlt"

        momentum = block["momentum"]
        for key in ("rsi_14", "macd_12_26_9", "stochastik_14_3_3", "ema", "adx_14"):
            assert key in momentum, f"{timeframe}: momentum.{key} fehlt"


def test_kontraktdaten_stammen_aus_dem_register(mcp_config):
    payload = build_snapshot_payload(make_loaded(MNQ), mcp_config, timeframes=TIMEFRAMES)
    instrument = payload["instrument"]

    assert instrument["root"] == "MNQ"
    assert instrument["tick_size_points"] == 0.25
    assert instrument["tick_value_usd"] == 0.5
    assert instrument["point_value_usd"] == 2.0


def test_mgc_liefert_eigene_kontraktdaten(mcp_config):
    payload = build_snapshot_payload(
        make_loaded(MGC, base=2400.0), mcp_config, timeframes=TIMEFRAMES
    )
    instrument = payload["instrument"]

    assert instrument["root"] == "MGC"
    assert instrument["tick_value_usd"] == 1.0
    assert instrument["point_value_usd"] == 10.0
    assert instrument["rth_end_local"] == "13:30"


def test_atr_wird_in_punkten_ticks_und_usd_ausgewiesen(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    atr = payload["timeframes"]["5m"]["volatilitaet"]["atr_14"]

    assert atr["punkte"] is not None
    assert atr["ticks"] == pytest.approx(atr["punkte"] / 0.25, rel=0.02)
    assert atr["usd_je_kontrakt"] == pytest.approx(atr["punkte"] * 2.0, rel=0.02)


def test_levels_werden_einmal_und_aus_einem_timeframe_berechnet(mcp_config):
    """Derselbe PDH darf nicht je Chart einen anderen Wert haben."""
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    levels = payload["levels"]

    assert levels["berechnet_aus_timeframe"] in TIMEFRAMES
    assert isinstance(levels["levels"], list)
    # Levels liegen auf oberster Ebene, nicht je Timeframe
    for block in payload["timeframes"].values():
        assert "levels" not in block


def test_jeder_level_traegt_punkte_ticks_und_atr(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)

    assert payload["levels"]["levels"], "Es sollten Levels berechnet werden."
    for level in payload["levels"]["levels"]:
        assert {"name", "price", "distance_points", "distance_ticks", "distance_atr", "side"} <= set(level)


def test_historienabhaengige_felder_weisen_ihren_bedarf_aus(mcp_config):
    """Jedes Feld sagt, wie viele Sessions es braucht und wie viele da sind."""
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    metrics = payload["historienabhaengig"]

    for key in ("week_high", "week_low", "relative_volume", "atr_percentile", "volume_profile"):
        entry = metrics[key]
        assert "available" in entry
        assert "sessions_required" in entry
        if not entry["available"]:
            assert entry["value"] is None
            assert "Handelssessions" in entry["reason"]
            # Der Bedarf muss konkret dranstehen, nicht nur "fehlt".
            assert entry["sessions_available"] < entry["sessions_required"]


def test_delta_wird_geliefert_wenn_flow_vorhanden(mcp_config):
    payload = build_snapshot_payload(
        make_loaded(with_flow=True), mcp_config, timeframes=TIMEFRAMES
    )
    delta = payload["timeframes"]["5m"]["volumen"]["kumulatives_delta"]

    assert delta["verfuegbar"] is True
    assert delta["kumulativ"] is not None


def test_delta_ist_null_mit_begruendung_ohne_flow(mcp_config):
    """Ohne bidVolume/offerVolume wird nichts geschaetzt."""
    payload = build_snapshot_payload(
        make_loaded(with_flow=False), mcp_config, timeframes=TIMEFRAMES
    )
    delta = payload["timeframes"]["5m"]["volumen"]["kumulatives_delta"]

    assert delta["verfuegbar"] is False
    assert delta["kumulativ"] is None
    assert "geschaetzt" in delta["reason"]


def test_vwap_hat_sigma_baender(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    vwap = payload["timeframes"]["5m"]["volumen"]["session_vwap"]

    assert vwap["value"] is not None
    assert vwap["sigma1_oben"] > vwap["value"] > vwap["sigma1_unten"]
    assert vwap["sigma2_oben"] > vwap["sigma1_oben"]


def test_datenherkunft_weist_alter_und_sessionabdeckung_aus(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    provenance = payload["datenherkunft"]["je_timeframe"]

    for timeframe in TIMEFRAMES:
        entry = provenance[timeframe]
        assert entry["verfuegbar"] is True
        assert "alter_juengster_bar_sekunden" in entry
        assert "deckt_zwei_sessions" in entry
        assert "bid_ask_volumen_vorhanden" in entry


def test_session_block_enthaelt_alle_warnflags(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    session = payload["session"]

    for key in (
        "is_rth", "is_liquid_window", "is_thin_midday_window",
        "is_first_hour_after_maintenance", "minutes_to_rth_open",
        "minutes_to_rth_close", "globex_state", "primary_session",
    ):
        assert key in session, f"Session-Feld {key} fehlt"

    assert set(session["timestamp"]) == {"utc", "et", "ct"}


def test_rohkerzen_koennen_abgeschaltet_werden(mcp_config):
    mit = build_snapshot_payload(
        make_loaded(), mcp_config, timeframes=TIMEFRAMES, include_bars=True, bars_in_output=20
    )
    ohne = build_snapshot_payload(
        make_loaded(), mcp_config, timeframes=TIMEFRAMES, include_bars=False
    )

    assert len(mit["timeframes"]["5m"]["letzte_bars"]) == 20
    assert "letzte_bars" not in ohne["timeframes"]["5m"]
    assert len(json.dumps(ohne, default=str)) < len(json.dumps(mit, default=str))


def test_snapshot_ist_json_serialisierbar(mcp_config):
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    rendered = json.dumps(payload, ensure_ascii=False, default=str)

    assert "MNQ" in rendered
    assert len(rendered) > 1000


def test_snapshot_bleibt_kompakt(mcp_config):
    """Kontextverbrauch in Claude Desktop im Blick behalten."""
    payload = build_snapshot_payload(
        make_loaded(), mcp_config, timeframes=TIMEFRAMES, bars_in_output=20
    )
    groesse = len(json.dumps(payload, ensure_ascii=False, default=str))
    assert groesse < 60_000, f"Snapshot ist {groesse} Zeichen gross"


def test_terminal_ausgabe_rendert_ohne_fehler(mcp_config, capsys):
    """Die Textfassung fuer den Chart-Abgleich muss durchlaufen."""
    from mcp_server.cli import _print_summary

    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    _print_summary(payload)

    ausgabe = capsys.readouterr().out
    assert "MNQ" in ausgabe
    assert "Zeit UTC" in ausgabe and "ET" in ausgabe and "CT" in ausgabe
    assert "Levels aus Timeframe" in ausgabe
    assert "Historienabhaengige Kennzahlen" in ausgabe
    # Jeder Timeframe bekommt einen Abschnitt
    for timeframe in TIMEFRAMES:
        assert f"--- {timeframe} " in ausgabe


def test_snapshot_enthaelt_keine_prosa_interpretation(mcp_config):
    """Der Server bewertet nicht - er liefert Zahlen."""
    payload = build_snapshot_payload(make_loaded(), mcp_config, timeframes=TIMEFRAMES)
    rendered = json.dumps(payload, ensure_ascii=False, default=str).lower()

    for verboten in ("kaufe", "verkaufe", "einstieg jetzt", "du solltest"):
        assert verboten not in rendered
