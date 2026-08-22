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
    AnalyseConfig,
    BacktestConfig,
    Config,
    LoggingConfig,
)
from common.instruments import MGC, MNQ
from common.contracts import Contract
from mcp_server.bars import DAILY, BarSet, LoadedBars
from common.sessions import session_dates
from mcp_server.snapshot import _vorsession_vollstaendig, build_snapshot_payload

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
        market=market_cfg,
        indicators=indicator_cfg,
        analyse=AnalyseConfig(swing_strength=3, swing_lookback=120, max_zones=3),
        logging=LoggingConfig(),
        backtest=BacktestConfig(),
    )


TIMEFRAMES = ["1m", "5m", "15m", "1h", DAILY]


# ---------------------------------------------------------------------------
# Kein Anthropic-Aufruf im MCP-Pfad
# ---------------------------------------------------------------------------

MCP_MODULES = sorted((PROJECT_ROOT / "mcp_server").rglob("*.py"))

# Pakete, deren Import im MCP-Pfad Kosten erzeugen wuerde.
VERBOTENE_WURZELN = {"anthropic"}

# Projektmodule, ueber die ein solcher Import hereinkommen koennte.
VERBOTENE_PROJEKTMODULE = {
    "live_bot.ai.claude_client",
    "live_bot.ai",
    "live_bot.notify.notifier",
    "backtest.cli",
}

PROJEKT_PAKETE = {"common", "live_bot", "ntbridge", "backtest", "mcp_server", "ideas"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _modul_zu_pfad(modul: str) -> Path | None:
    datei = PROJECT_ROOT / (modul.replace(".", "/") + ".py")
    if datei.exists():
        return datei
    paket = PROJECT_ROOT / modul.replace(".", "/") / "__init__.py"
    return paket if paket.exists() else None


def _transitive_huelle(start: list[Path]) -> tuple[set[str], dict[str, list[str]]]:
    """Alle Projektmodule, die von ``start`` aus erreichbar sind.

    Liefert zusaetzlich je Modul den Pfad, ueber den es erreicht wurde -
    ohne den ist eine Verletzung kaum zu finden.
    """
    gesehen: set[Path] = set()
    erreichbar: set[str] = set()
    weg: dict[str, list[str]] = {}
    rand: list[tuple[Path, list[str]]] = [(p, [p.name]) for p in start]

    while rand:
        datei, pfad = rand.pop()
        if datei in gesehen:
            continue
        gesehen.add(datei)
        for modul in _imported_modules(datei):
            wurzel = modul.split(".")[0]
            if wurzel not in PROJEKT_PAKETE and wurzel not in VERBOTENE_WURZELN:
                continue
            if modul not in erreichbar:
                erreichbar.add(modul)
                weg[modul] = pfad + [modul]
            ziel = _modul_zu_pfad(modul)
            if ziel is not None:
                rand.append((ziel, pfad + [modul]))

    return erreichbar, weg


def test_mcp_pfad_erreicht_keine_anthropic_api():
    """Der Server liefert Daten - interpretiert wird in Claude Desktop.

    WARUM TRANSITIV UND NICHT NUR DIREKTE IMPORTE
    ---------------------------------------------
    Die fruehere Fassung pruefte je Datei unter ``mcp_server/`` nur deren
    **eigene** Importzeilen gegen eine Verbotsliste. Die Zusage lautet aber
    nicht "importiert nichts Verbotenes direkt", sondern "von hier aus ist
    kein Anthropic-Aufruf erreichbar".

    Der Unterschied war real: ``mcp_server/bars.py`` zog fuenf
    ``live_bot``-Module herein. Ein einziger neuer Import in einem davon
    haette die Kostengarantie gebrochen, und der Test waere gruen geblieben.

    Ausserdem lief die alte Fassung ueber ``glob("*.py")`` - ein Unterpaket
    unter ``mcp_server/`` waere gar nicht geprueft worden. Jetzt ``rglob``.
    """
    erreichbar, weg = _transitive_huelle(MCP_MODULES)

    verboten = {
        modul
        for modul in erreichbar
        if modul.split(".")[0] in VERBOTENE_WURZELN or modul in VERBOTENE_PROJEKTMODULE
    }

    assert not verboten, "Vom MCP-Pfad aus erreichbar: " + "; ".join(
        f"{modul} ueber {' -> '.join(weg[modul])}" for modul in sorted(verboten)
    )


def test_mcp_pfad_zieht_kein_live_bot_mehr():
    """Das Zielsystem haengt nicht mehr am Legacy-Pfad.

    Kein Selbstzweck: ueber ``live_bot`` kaeme jede kuenftige Abhaengigkeit
    des Alarm-Pfads in den Importweg des MCP-Servers und koennte ihn beim
    Start mitreissen - bei einem Prozess, den Claude Desktop startet, sieht
    man das nur im Log.
    """
    erreichbar, weg = _transitive_huelle(MCP_MODULES)
    treffer = {m for m in erreichbar if m.split(".")[0] == "live_bot"}

    assert not treffer, "live_bot ist wieder im MCP-Pfad: " + "; ".join(
        f"{modul} ueber {' -> '.join(weg[modul])}" for modul in sorted(treffer)
    )


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
        assert "vorsession_vollstaendig" in entry
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


# ---------------------------------------------------------------------------
# Vollstaendigkeit der Vorsession (Regression)
# ---------------------------------------------------------------------------
#
#  Die fruehere Pruefung zaehlte verschiedene Session-DATEN. Ein auf 1500
#  Bars gedeckelter 1-Minuten-Frame beruehrt zwei Session-Daten, enthaelt
#  die aeltere aber nur zu einem Bruchteil - und lieferte trotzdem ein
#  "Vortageshoch" aus dem angeschnittenen Tag, ohne Fehlermeldung.
#
#  An echten MNQ-Daten (21.08.2026) waren das 29686.75 statt 29688.50.
#  Der Fehler ist nicht nach oben begrenzt: faellt das echte Hoch frueh in
#  die Session, liegt der Wert beliebig weit daneben.

# Session-Modell 18:00-17:00 ET: die Session "2025-06-10" beginnt am
# 2025-06-09 um 18:00 Ortszeit.
VORSESSION_START = "2025-06-09 18:00"
BARS_EINE_SESSION = 23 * 60


def _frame_mit_vollstaendiger_vorsession() -> pd.DataFrame:
    """Ganze Session 2025-06-10 plus ein Stueck der Folgesession."""
    return synthetic_frame(bars=BARS_EINE_SESSION + 240, minutes=1, start=VORSESSION_START)


def test_vollstaendige_vorsession_wird_erkannt(session_cfg):
    frame = _frame_mit_vollstaendiger_vorsession()

    tage = sorted(set(session_dates(frame.index, session_cfg).values))
    assert len(tage) >= 2, "Testdaten muessen zwei Sessions beruehren"

    assert _vorsession_vollstaendig(frame, session_cfg) is True


def test_angeschnittene_vorsession_gilt_nicht_als_vollstaendig(session_cfg):
    """Der eigentliche Regressionstest.

    Der gedeckelte Frame beruehrt weiterhin ZWEI Session-Daten - genau
    deshalb kam die alte Zaehlpruefung durch. Er enthaelt den Beginn der
    Vorsession aber nicht mehr.
    """
    voll = _frame_mit_vollstaendiger_vorsession()
    gedeckelt = voll.iloc[-600:]

    tage = sorted(set(session_dates(gedeckelt.index, session_cfg).values))
    assert len(tage) >= 2, (
        "Der gedeckelte Frame muss weiterhin zwei Session-Daten beruehren - "
        "sonst prueft dieser Test nicht den gemeldeten Fehler."
    )

    assert _vorsession_vollstaendig(gedeckelt, session_cfg) is False


def test_loch_am_sessionanfang_gilt_nicht_als_vollstaendig(session_cfg):
    """Auch eine Datenluecke am Sessionbeginn macht die Vorsession unbrauchbar."""
    voll = _frame_mit_vollstaendiger_vorsession()
    start = voll.index[0]
    ohne_anfang = voll[voll.index > start + pd.Timedelta(minutes=30)]

    assert _vorsession_vollstaendig(ohne_anfang, session_cfg) is False


def test_einzelne_session_reicht_nicht(session_cfg):
    nur_eine = synthetic_frame(bars=200, minutes=1, start=VORSESSION_START)
    assert _vorsession_vollstaendig(nur_eine, session_cfg) is False


def test_levelframe_ueberspringt_angeschnittenen_timeframe(mcp_config):
    """Ende zu Ende: das Vortageshoch stammt aus der VOLLSTAENDIGEN Session.

    Aufbau wie im echten Fehlerfall: der 1m-Frame ist gedeckelt und damit
    angeschnitten, der 5m-Frame reicht weit genug zurueck. Beide beschreiben
    denselben Kursverlauf.
    """
    voll_1m = _frame_mit_vollstaendiger_vorsession()
    gedeckelt_1m = voll_1m.iloc[-600:]

    # 5m-Frame aus demselben Verlauf aggregieren - so ist das wahre
    # Vortageshoch in beiden Frames dasselbe, sofern man weit genug zurueckschaut.
    voll_5m = voll_1m.resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "bid_volume": "sum",
            "ask_volume": "sum",
        }
    ).dropna()

    tage = session_dates(voll_1m.index, mcp_config.market.session)
    vorsession = sorted(set(tage.values))[-2]
    wahres_hoch = float(voll_1m[tage.values == vorsession]["high"].max())
    hoch_aus_stumpf = float(
        gedeckelt_1m[
            session_dates(gedeckelt_1m.index, mcp_config.market.session).values == vorsession
        ]["high"].max()
    )

    assert hoch_aus_stumpf < wahres_hoch, (
        "Testdaten taugen nicht: der angeschnittene Frame muesste ein zu "
        "niedriges Vortageshoch ergeben, sonst zeigt der Test nichts."
    )

    geladen = make_loaded()
    geladen.sets["1m"] = BarSet(
        timeframe="1m", frame=gedeckelt_1m, source="test",
        contract="MNQZ5", requested_bars=len(gedeckelt_1m),
    )
    geladen.sets["5m"] = BarSet(
        timeframe="5m", frame=voll_5m, source="test",
        contract="MNQZ5", requested_bars=len(voll_5m),
    )

    payload = build_snapshot_payload(geladen, mcp_config, timeframes=["1m", "5m"])

    assert payload["levels"]["berechnet_aus_timeframe"] != "1m"

    pdh = next(
        level for level in payload["levels"]["levels"] if level["name"] == "prev_day_high"
    )
    assert pdh["price"] == pytest.approx(wahres_hoch, abs=0.01)


def test_provenienz_meldet_angeschnittene_vorsession(mcp_config):
    """Der Snapshot darf Vollstaendigkeit nicht faelschlich bestaetigen."""
    voll_1m = _frame_mit_vollstaendiger_vorsession()

    geladen = make_loaded()
    geladen.sets["1m"] = BarSet(
        timeframe="1m", frame=voll_1m.iloc[-600:], source="test",
        contract="MNQZ5", requested_bars=600,
    )
    geladen.sets["5m"] = BarSet(
        timeframe="5m", frame=voll_1m.resample("5min").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last",
             "volume": "sum", "bid_volume": "sum", "ask_volume": "sum"}
        ).dropna(),
        source="test", contract="MNQZ5", requested_bars=400,
    )

    payload = build_snapshot_payload(geladen, mcp_config, timeframes=["1m", "5m"])
    je_tf = payload["datenherkunft"]["je_timeframe"]

    assert je_tf["1m"]["vorsession_vollstaendig"] is False
    assert je_tf["5m"]["vorsession_vollstaendig"] is True
