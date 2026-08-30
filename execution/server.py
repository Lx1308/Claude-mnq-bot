"""
Execution Server fuer die TRADAYRI Desktop App.

Stellt die REST-API bereit, die das React-Frontend erwartet.
Die Antwortstrukturen muessen exakt zu ui/frontend/src/api/types.ts passen,
sonst crashed das Frontend mit 'Cannot read properties of undefined'.
"""

import os
import sys
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pandas as pd
from pydantic import BaseModel
from typing import Optional

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("execution.server")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path("data")

def get_db(name: str):
    path = DATA_DIR / name
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Ausfuehrung: Konfiguration, Speicher, Risikopruefung
#
# Bewusst beim Start und nicht beim ersten Aufruf: eine kaputte Konfiguration
# soll den Server nicht anlaufen lassen, statt beim ersten Orderklick
# aufzufallen. Dieselbe Haltung wie bei Config.validate() im uebrigen Projekt.
# ---------------------------------------------------------------------------
from common.config import Config                      # noqa: E402
from common.instruments import get_instrument         # noqa: E402
from common.kontoregeln import aus_konfiguration      # noqa: E402
from execution import buchung                         # noqa: E402
from execution.risiko import Handelsfenster, RisikoPruefung   # noqa: E402
from execution.store import ExecutionStore, Order, OrderStatus  # noqa: E402

CONFIG = Config.load(PROJECT_ROOT / "config.yaml")
STORE = ExecutionStore(PROJECT_ROOT / "data" / "execution.sqlite3")

_AUS = CONFIG.ausfuehrung
REGELN = aus_konfiguration(_AUS.kontoprofil, _AUS.kontoprofile.get(_AUS.kontoprofil))
RISIKO = RisikoPruefung(
    REGELN,
    STORE,
    fenster=Handelsfenster(
        start=_AUS.handel_von,
        ende=_AUS.handel_bis,
        zeitzone=_AUS.handel_zeitzone,
        nur_wochentags=_AUS.nur_wochentags,
    ),
    eigenes_kontraktlimit=_AUS.max_kontrakte,
    startkapital_usd=_AUS.startkapital_usd,
)

logger.info("Kontoregeln: %s", REGELN.zeile())

# Der autonome Bot laeuft IM Serverprozess, auf demselben Speicher und
# derselben Risikopruefung. Ein eigener Prozess haette wieder zwei
# Risikozustaende, die einander nicht sehen - genau das Split-Brain, das im
# Audit vom 28.08.2026 stand.
from execution.bot import HandelsBot                   # noqa: E402

BOT = HandelsBot(
    CONFIG,
    STORE,
    RISIKO,
    bar_datenbank=str(PROJECT_ROOT / "data" / "ntbridge.sqlite3"),
    ideen_datenbank=str(PROJECT_ROOT / "data" / "ideas.sqlite3"),
)


@app.on_event("startup")
def _bot_starten() -> None:
    if CONFIG.ausfuehrung.enabled:
        BOT.start()
    else:
        logger.info(
            "Autonomer Bot ist aus (ausfuehrung.enabled=false). "
            "Das Order-Panel arbeitet unabhaengig davon."
        )


@app.on_event("shutdown")
def _bot_beenden() -> None:
    BOT.stop()


@app.get("/api/bot")
def get_bot():
    """Zustand des autonomen Bots - inklusive des letzten Durchgangs."""
    return {
        "aktiviert": CONFIG.ausfuehrung.enabled,
        "laeuft": BOT.laeuft,
        "takt_sekunden": CONFIG.ausfuehrung.takt_sekunden,
        "handelsfenster": RISIKO.fenster.beschreibung(),
        "fenster_offen": RISIKO.fenster.ist_offen(datetime.now(timezone.utc)),
        "risikobudget_usd": BOT.risikobudget_usd(),
        "letzter_lauf": BOT.letzter_lauf.to_dict() if BOT.letzter_lauf else None,
    }


@app.post("/api/bot/durchgang")
def bot_durchgang():
    """Einen Durchgang von Hand ausloesen - zum Pruefen, ohne zu warten."""
    return BOT.durchgang().to_dict()


# Das Frontend spricht LONG/SHORT, der autonome Bot sprach frueher BUY/SELL.
# Beides wird hier auf die eine interne Schreibweise gebracht - und was sich
# nicht eindeutig zuordnen laesst, wird abgelehnt statt geraten. Eine geratene
# Richtung ist ein Trade in die falsche Seite des Marktes; genau das ist im
# tcp_proxy passiert, wo "BUY" stillschweigend zu "SELL" wurde.
_RICHTUNG = {
    "LONG": "long", "BUY": "long", "BUYTOCOVER": "long",
    "SHORT": "short", "SELL": "short", "SELLSHORT": "short",
}


def _richtung(wert: str) -> str:
    schluessel = str(wert or "").strip().upper()
    if schluessel not in _RICHTUNG:
        raise HTTPException(
            status_code=400,
            detail=f"Unlesbare Richtung {wert!r}. Erlaubt: "
                   f"{', '.join(sorted(_RICHTUNG))}",
        )
    return _RICHTUNG[schluessel]


class OrderRequest(BaseModel):
    """Feldnamen wie im Frontend (ui/frontend/src/panels/OrderPanel.tsx)."""

    symbol: str = "MNQ"
    side: str
    qty: int = 1
    price: Optional[float] = None
    stop_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    kind: Optional[str] = "MARKET"
    #: Freitext aus dem Order-Panel bzw. Hypothese des Bots.
    grund: Optional[str] = None
    idee_id: Optional[str] = None
    hypothese: Optional[str] = None


class FillEvent(BaseModel):
    """Genau das, was TradayriBridge.cs bei ``type: execution`` sendet.

    Die vorherige Fassung erwartete ``{symbol, price, quantity}`` - Felder,
    die das AddOn nie schickt. Jede Fuellung lief damit in einen
    422-Validierungsfehler und wurde verworfen; der Server erfuhr nie, dass
    ein Trade zustande gekommen war.
    """

    order_key: str
    exec_id: str
    role: str = ""
    ts: Optional[int] = None            # Epoch-Nanosekunden
    quantity: int = 1
    price: float
    commission: float = 0.0


class OrderUpdateEvent(BaseModel):
    """``type: order_update`` aus dem AddOn - der Lebenslauf einer Order."""

    order_key: str
    order_id: Optional[str] = None
    role: str = ""
    state: str = ""
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    error: str = ""


#: Wie NinjaTrader-Zustaende auf unsere abgebildet werden. Was hier nicht
#: steht, laesst den Status unveraendert - ein unbekannter Zustand darf eine
#: Order nicht stillschweigend als erledigt markieren.
_NT_ZUSTAND = {
    "accepted": OrderStatus.ANGENOMMEN,
    "working": OrderStatus.ANGENOMMEN,
    "submitted": OrderStatus.GESENDET,
    "partfilled": OrderStatus.TEILGEFUELLT,
    "filled": OrderStatus.GEFUELLT,
    "cancelled": OrderStatus.STORNIERT,
    "canceled": OrderStatus.STORNIERT,
    "rejected": OrderStatus.ABGELEHNT,
}

# ---------------------------------------------------------------------------
@app.post("/api/research/run")
async def run_research(body: dict):
    from execution.research_engine import run_hypothesis
    import uuid
    
    hyp_id = body.get("hypothesis_id", str(uuid.uuid4())[:8])
    strategy = body.get("strategy", "vwap_trend")
    reason = body.get("reason", "No reason provided")
    params = body.get("params", {})
    
    try:
        filename = run_hypothesis(hyp_id, strategy, reason, params)
        return {"status": "ok", "protocol": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# API Endpoints - Orders
# ---------------------------------------------------------------------------
@app.post("/api/order/submit")
def submit_order(anfrage: OrderRequest):
    """Order annehmen, pruefen, persistent ablegen.

    Abgelehnte Orders werden ebenso protokolliert wie angenommene. Ohne die
    Ablehnungen liesse sich spaeter nicht beantworten, ob ein Limit zu scharf
    stand oder ob schlicht kein Signal kam - dieselbe Ueberlegung wie bei den
    gefilterten Ideen in Etappe C.
    """
    richtung = _richtung(anfrage.side)
    art = (anfrage.kind or "MARKET").upper()

    urteil = RISIKO.pruefe(menge=anfrage.qty)
    if not urteil.erlaubt:
        STORE.protokolliere_entscheidung(
            instrument=anfrage.symbol, ergebnis="abgelehnt", grund=urteil.grund,
            idee_id=anfrage.idee_id, hypothese=anfrage.hypothese,
            marktzustand=urteil.kennzahlen,
        )
        logger.warning("Order abgelehnt: %s", urteil.grund)
        raise HTTPException(status_code=409, detail=urteil.grund)

    try:
        order = Order(
            instrument=anfrage.symbol,
            richtung=richtung,
            art=art,
            menge=urteil.menge,
            quelle=anfrage.hypothese and "bot" or "ui",
            konto=CONFIG.ausfuehrung.konto,
            limit_preis=anfrage.price if art == "LIMIT" else None,
            stop_preis=anfrage.stop_price if art == "STOP" else None,
            stop_loss=anfrage.stop_loss or None,
            take_profit=anfrage.take_profit or None,
            idee_id=anfrage.idee_id,
            hypothese=anfrage.hypothese,
            begruendung={
                "grund": anfrage.grund,
                "angefragte_menge": anfrage.qty,
                "risikourteil": urteil.grund,
                "kontoprofil": RISIKO.regeln.name,
                "regeln_sind_annahme": RISIKO.regeln.ist_annahme,
            },
        )
    except ValueError as fehler:
        raise HTTPException(status_code=400, detail=str(fehler)) from fehler

    order_id = str(uuid.uuid4())
    STORE.lege_order_an(order, order_id)
    STORE.protokolliere_entscheidung(
        instrument=order.instrument, ergebnis="order", grund=urteil.grund,
        order_id=order_id, idee_id=order.idee_id, hypothese=order.hypothese,
        marktzustand=urteil.kennzahlen,
    )
    logger.info(
        "Order %s angelegt: %s %s %d %s", order_id, order.art, order.richtung,
        order.menge, order.instrument,
    )
    return {
        "status": "success",
        "message": urteil.grund,
        "order_id": order_id,
        "menge": order.menge,
        "gekuerzt": order.menge != anfrage.qty,
    }


@app.get("/api/orders/pending")
def get_pending_orders():
    """Wird von der Bridge abgeholt und dabei auf 'gesendet' gesetzt.

    Das Format bleibt das, was ``ntbridge/tcp_proxy.py`` liest.
    """
    return [
        {
            "order_id": o["order_id"],
            "direction": o["richtung"],
            "symbol": o["instrument"],
            "quantity": o["menge"],
            "order_type": o["art"],
            "limit_price": o["limit_preis"] or 0.0,
            "stop_price": o["stop_preis"] or 0.0,
            "stop_loss_price": o["stop_loss"] or 0.0,
            "take_profit_price": o["take_profit"] or 0.0,
            "account_name": o["konto"],
        }
        for o in STORE.zu_senden()
    ]


@app.get("/api/orders/modify_pending")
def get_pending_modifies():
    # Stopanpassungen sind noch nicht gebaut. Eine leere Liste ist hier die
    # ehrliche Antwort - vorher stand hier eine Liste, die beim Lesen geleert
    # wurde und deshalb genauso leer war, nur unabsichtlich.
    return []


@app.get("/api/orders")
def get_orders(limit: int = 100):
    return STORE.orders(limit=limit)


@app.post("/api/orders/fill")
def handle_fill(fill: FillEvent):
    """Eine Fuellung aus NinjaTrader verbuchen.

    Hier lief vorher ``return {"status": "ok"}`` - der Server nahm die Meldung
    entgegen und warf sie weg. Damit blieb jedes Risikolimit fuer immer bei
    einem Tagesverlust von 0 stehen.
    """
    ts_utc = buchung.ts_aus_nanosekunden(fill.ts)
    neu = STORE.erfasse_fill(
        exec_id=fill.exec_id,
        order_id=fill.order_key,
        rolle=(fill.role or "").lower(),
        ts_utc=ts_utc,
        menge=fill.quantity,
        preis=fill.price,
        kommission=fill.commission,
    )
    if not neu:
        # Nach einem Verbindungsabriss schickt NinjaTrader Ereignisse erneut.
        return {"status": "bekannt", "exec_id": fill.exec_id}

    instrument = get_instrument(CONFIG.market.product)
    trade = buchung.verbuche(STORE, fill.order_key, instrument.point_value)
    if trade is not None:
        STORE.schreibe_trade(trade)
        STORE.setze_status(fill.order_key, OrderStatus.GEFUELLT)
        logger.info(
            "Trade gebucht: %s %s, %.2f USD (%s)",
            trade["richtung"], trade["instrument"], trade["pnl_usd"],
            trade["grund_ausstieg"],
        )
        return {"status": "trade", "trade_id": trade["trade_id"],
                "pnl_usd": trade["pnl_usd"]}

    return {"status": "erfasst", "exec_id": fill.exec_id}


@app.post("/api/orders/update")
def handle_order_update(ereignis: OrderUpdateEvent):
    """Zustandsmeldung aus NinjaTrader ('accepted', 'rejected', ...).

    Der Lebenslauf ist der einzige Weg, eine Ablehnung ueberhaupt zu
    bemerken - eine Order, die die Boerse nicht annimmt, meldet sich sonst
    nirgends. Genau danach hat Laurin am 29.08.2026 gefragt ("kriege ich die
    Fehlermeldung direkt in der App oder in NinjaTrader?").
    """
    status = _NT_ZUSTAND.get(str(ereignis.state or "").lower())
    if status is None:
        return {"status": "unbeachtet", "nt_zustand": ereignis.state}

    STORE.setze_status(
        ereignis.order_key, status,
        nt_zustand=ereignis.state,
        fehler=ereignis.error or None,
    )
    if ereignis.error:
        logger.warning(
            "NinjaTrader meldet Fehler zu Order %s: %s",
            ereignis.order_key, ereignis.error,
        )
    return {"status": "uebernommen", "neuer_status": status}


@app.get("/api/risiko")
def get_risiko():
    """Was das Risikomodul gerade sieht - fuer Oberflaeche und Protokoll."""
    kennzahlen = RISIKO.kennzahlen()
    # Ueber RISIKO.regeln und nicht ueber das Modul-Global REGELN: sonst gaebe
    # es zwei Quellen fuer dieselbe Angabe, und die koennen auseinander laufen.
    kennzahlen["regeln"] = RISIKO.regeln.to_dict()
    kennzahlen["regeln_zeile"] = RISIKO.regeln.zeile()
    return kennzahlen


@app.get("/api/entscheidungen")
def get_entscheidungen(limit: int = 100):
    """Jede Entscheidung, auch die gegen einen Trade."""
    return STORE.entscheidungen(limit=limit)

# ---------------------------------------------------------------------------
# API Endpoints - Bars (aus ntbridge.sqlite3)
#
# Das Frontend erwartet BarsResponse: {symbol, timeframe, bars: Bar[], forming, live}
# Bar = {ts (nanoseconds!), open, high, low, close, volume, roll_boundary}
# ---------------------------------------------------------------------------
@app.get("/api/bars")
def get_bars(symbol: str = "MNQ", timeframe: str = "1m", limit: int = 300):
    bars = []
    conn = get_db("ntbridge.sqlite3")
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT ts_utc, open, high, low, close, volume "
                "FROM bars "
                "WHERE instrument = ? AND timeframe = ? "
                "ORDER BY ts_utc DESC LIMIT ?",
                (symbol, timeframe, limit)
            )
            for r in reversed(cur.fetchall()):
                try:
                    dt = datetime.fromisoformat(r["ts_utc"])
                    # Frontend erwartet Nanosekunden-Timestamps
                    ts_ns = int(dt.timestamp() * 1_000_000_000)
                except Exception:
                    ts_ns = 0
                bars.append({
                    "ts": ts_ns,
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "close": r["close"],
                    "volume": r["volume"] or 0,
                    "roll_boundary": False,
                })
        except Exception as e:
            logger.error(f"Bars Fehler: {e}")
        finally:
            conn.close()

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": bars,
        "forming": None,
        "live": None,
    }

# ---------------------------------------------------------------------------
# API Endpoints - Trades (aus ideas.sqlite3)
# ---------------------------------------------------------------------------
@app.get("/api/trades")
def get_trades(symbol: str = "MNQ"):
    result = []
    conn = get_db("ideas.sqlite3")
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT idea_id, erstellt_utc, instrument, setup, richtung, "
                "timeframe, entry, stop, ziel, crv, atr_referenz "
                "FROM ideen WHERE instrument = ? ORDER BY erstellt_utc ASC",
                (symbol,)
            )
            for r in cur.fetchall():
                result.append({
                    "idea_id": r["idea_id"],
                    "erstellt_utc": r["erstellt_utc"],
                    "instrument": r["instrument"],
                    "setup": r["setup"],
                    "richtung": r["richtung"],
                    "timeframe": r["timeframe"],
                    "entry": r["entry"],
                    "stop": r["stop"],
                    "ziel": r["ziel"],
                })
        except Exception as e:
            logger.error(f"Trades Fehler: {e}")
        finally:
            conn.close()
    return result

# ---------------------------------------------------------------------------
# API Endpoints - Schema-konforme Stubs
#
# Diese muessen EXAKT zu ui/frontend/src/api/types.ts passen.
# Fehlende Felder -> 'Cannot read properties of undefined' -> schwarzer Screen.
# ---------------------------------------------------------------------------

@app.get("/api/health")
def get_health():
    """types.ts: Health"""
    return {
        "ok": True,
        "mode": "execution",
        "live_trading_enabled": True,
        "symbol": "MNQ",
        "config_hash": "local",
        "strategy_version": "1.0.0",
        "display_timezone": "America/New_York",
        "providers": [],
        "warnings": [],
    }

@app.get("/api/instruments")
def get_instruments():
    """types.ts: Instrument[]"""
    return [{
        "symbol": "MNQ",
        "name": "Micro E-mini Nasdaq-100",
        "exchange": "CME",
        "currency": "USD",
        "tick_size": 0.25,
        "tick_value": 0.50,
        "point_value": 2.0,
        "price_decimals": 2,
        "live_capable": True,
    }]

@app.get("/api/coverage")
def get_coverage():
    """types.ts: Coverage[]"""
    # Pruefe ob tatsaechlich Daten vorhanden
    conn = get_db("ntbridge.sqlite3")
    if conn:
        try:
            r = conn.execute(
                "SELECT COUNT(*) as cnt, MIN(ts_utc) as first_ts, MAX(ts_utc) as last_ts "
                "FROM bars WHERE instrument = 'MNQ' AND timeframe = '1m'"
            ).fetchone()
            conn.close()
            if r and r["cnt"] > 0:
                return [{
                    "symbol": "MNQ",
                    "timeframe": "1m",
                    "first_ts": 0,
                    "last_ts": 0,
                    "bar_count": r["cnt"],
                }]
        except Exception:
            pass
    return []

@app.get("/api/overlays")
def get_overlays(symbol: str = "", timeframe: str = ""):
    """types.ts: Overlays"""
    return {
        "symbol": symbol or "MNQ",
        "timeframe": timeframe or "5m",
        "swings": [],
        "fvgs": [],
        "pools": [],
        "sweeps": [],
        "structure_events": [],
        "displacements": [],
    }

@app.get("/api/analysis")
def get_analysis(symbol: str = ""):
    """types.ts: ContextSnapshot"""
    return {
        "symbol": symbol or "MNQ",
        "last_ts": 0,
        "session": "",
        "bias": {
            "bias": "neutral",
            "score": 0.0,
            "per_timeframe": [],
            "reasons": [],
        },
        "timeframes": {},
    }

@app.get("/api/strategy")
def get_strategy(symbol: str = "", limit: int = 30):
    """types.ts: StrategyState"""
    return {
        "symbol": symbol or "MNQ",
        "enabled": True,
        "setup_timeframe": "5m",
        "confirmation_timeframe": "1m",
        "stop_anchor": "local",
        "min_rr": 2.0,
        "active_setups": [],
        "recent_decisions": [],
        "last_signal": None,
        "decisions_total": 0,
        "trades_total": 0,
        "no_trades_total": 0,
        "rejection_counts": {},
    }

@app.get("/api/market")
def get_market(symbol: str = ""):
    """types.ts: MarketStatus"""
    now = datetime.now(timezone.utc)
    return {
        "symbol": symbol or "MNQ",
        "server_ts": int(now.timestamp()),
        "session": "ETH",
        "is_open": True,
        "is_rth": False,
        "timezone": "America/New_York",
    }

@app.get("/api/session")
def get_session():
    """types.ts: SessionStatus"""
    return {
        "broker": {
            "enabled": False,
            "provider": "",
            "connected": False,
            "account": "",
            "is_paper": True,
            "paper_evidence": "",
            "blocked_reason": "",
            "open_orders": 0,
            "tradeable_symbols": [],
            "ready": False,
        },
        "active": False,
        "feed": "",
        "symbols": ["MNQ"],
        "session_id": 0,
        "warnings": [],
        "stopped_by": "",
        "error": "",
        "last_prices": {},
        "running": False,
        "connected": False,
        "halted_reason": "",
        "accepts_entries": False,
        "mode": "",
        "started_ts": 0,
        "last_bar_ts": 0,
        "last_message_ts": 0,
        "bars_seen": 0,
        "signals": 0,
        "trades_closed": 0,
        "open_positions": 0,
        "start_equity": 0,
        "equity": 0,
        "realized_pnl": 0,
        "day_pnl": 0,
        "trading_day": 0,
    }

@app.get("/api/logs")
def get_logs(limit: int = 120):
    """types.ts: LogEntry[]"""
    return []

@app.get("/api/watch")
def get_watch():
    """types.ts: WatchState"""
    return {
        "running": False,
        "symbol": "",
        "connected": False,
        "bars_seen": 0,
        "ticks_seen": 0,
        "last_price": 0,
        "detail": "",
    }

@app.post("/api/watch/start")
async def watch_start(body: dict = None):
    return get_watch()

@app.post("/api/watch/stop")
def watch_stop():
    return get_watch()

@app.get("/api/positions")
def get_positions():
    return {"positions": {}}

@app.get("/api/status")
def get_status():
    return {"status": "running"}

# SSE-Stubs: das Frontend verbindet zu /api/stream als EventSource.
from starlette.responses import StreamingResponse
import asyncio

async def sse_generator():
    """Leerer SSE-Strom, damit das Frontend keinen MIME-Fehler wirft."""
    while True:
        yield "event: heartbeat\ndata: {}\n\n"
        await asyncio.sleep(10)

@app.get("/api/stream")
async def session_stream_main():
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.get("/api/session/stream")
async def session_stream_alt():
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.get("/api/ticks")
async def tick_stream(symbol: str = "", timeframe: str = ""):
    return StreamingResponse(sse_generator(), media_type="text/event-stream")

# --- Fehlende POST-Endpoints, die das Frontend beim Symbolwechsel aufruft ---

@app.post("/api/load")
async def load_data(body: dict = None):
    """types.ts: LoadResponse"""
    symbol = (body or {}).get("symbol", "MNQ")
    conn = get_db("ntbridge.sqlite3")
    bar_count = 0
    if conn:
        try:
            r = conn.execute(
                "SELECT COUNT(*) as cnt FROM bars WHERE instrument = ?",
                (symbol,)
            ).fetchone()
            bar_count = r["cnt"] if r else 0
        except Exception:
            pass
        finally:
            conn.close()
    return {
        "symbol": symbol,
        "base_timeframe": "1m",
        "base_bars": bar_count,
        "cursor": bar_count,
        "progress": 1.0,
        "integrity": None,
        "warnings": [],
    }

@app.post("/api/step")
async def step_data(body: dict = None):
    """types.ts: StepResponse"""
    symbol = (body or {}).get("symbol", "MNQ")
    count = (body or {}).get("count", 100)
    conn = get_db("ntbridge.sqlite3")
    bar_count = 0
    if conn:
        try:
            r = conn.execute(
                "SELECT COUNT(*) as cnt FROM bars WHERE instrument = ?",
                (symbol,)
            ).fetchone()
            bar_count = r["cnt"] if r else 0
        except Exception:
            pass
        finally:
            conn.close()
    return {
        "symbol": symbol,
        "cursor": bar_count,
        "base_bars": bar_count,
        "progress": 1.0,
        "exhausted": True,
        "new_swings": 0,
        "new_fvgs": 0,
        "new_sweeps": 0,
        "new_structure_events": 0,
        "new_displacements": 0,
    }

@app.post("/api/reset")
async def reset_data(symbol: str = "MNQ"):
    """types.ts: StepResponse"""
    return {
        "symbol": symbol,
        "cursor": 0,
        "base_bars": 0,
        "progress": 0.0,
        "exhausted": False,
        "new_swings": 0,
        "new_fvgs": 0,
        "new_sweeps": 0,
        "new_structure_events": 0,
        "new_displacements": 0,
    }

#: Ab wie vielen Trades eine Kennzahlenreihe ueberhaupt aussagekraeftig ist.
#: Darunter dimmt die Oberflaeche den Bericht ab (``is_significant``).
MIN_TRADES_FUER_AUSSAGE = 30


@app.post("/api/backtest")
async def run_backtest_api(body: dict = None):
    """Backtest aus der Oberflaeche - ueber dieselbe Maschinerie wie die CLI.

    Drei Dinge sind hier nicht verhandelbar, weil eine fruehere Fassung sie
    alle drei verletzt hat:

    1. **In-Sample und Out-of-Sample sind zwei verschiedene Zeitraeume.**
       Vorher stand in allen drei Feldern (``overall``, ``in_sample``,
       ``out_of_sample``) dasselbe Objekt - die Oberflaeche zeigte damit ein
       In-Sample-Ergebnis in der Out-of-Sample-Spalte an. Geteilt wird jetzt
       ueber ``backtest.splits``/``backtest.compare``, also genau dort, wo
       Invariante 5 die Indikatoren einmal ueber die Gesamthistorie rechnet
       und erst danach schneidet.
    2. **Kosten sind ein benanntes Profil, keine Null.** ``commission: 0`` war
       schlicht falsch; gerechnet wird mit dem in ``config.yaml`` gesetzten
       Profil, und der Name steht im Bericht (``assumptions``).
    3. **Nichts wird erfunden.** ``sqn`` und die MAE/MFE-Felder kennt
       ``backtest.metrics`` nicht - sie bleiben ``None`` statt mit einer
       plausiblen Zahl gefuellt zu werden (Invariante 11).
    """
    body = body or {}
    symbol = body.get("symbol", "MNQ")
    strategie_name = body.get("strategy", "power_hour_vwap")
    parameter = body.get("params") or {}
    startkapital = float(body.get("initial_capital", 10000))

    from common.config import Config
    from backtest.engine import Backtester, CostModel
    from backtest.kosten import profil_aus_config
    from backtest.splits import SplitConfig, split_data
    from backtest.compare import prepare_split
    from backtest.strategies.library import STRATEGY_LIBRARY, build_strategy
    from execution.overlay_helpers import get_df_for_overlays
    import backtest.metrics as bm

    if strategie_name not in STRATEGY_LIBRARY:
        raise HTTPException(
            status_code=400,
            detail=f"Unbekannte Strategie {strategie_name!r}. "
                   f"Bekannt: {', '.join(sorted(STRATEGY_LIBRARY))}",
        )

    df = get_df_for_overlays(symbol, "1m", 15000)
    if df is None or df.empty:
        raise HTTPException(
            status_code=409,
            detail=f"Keine 1m-Kerzen fuer {symbol} in data/ntbridge.sqlite3.",
        )

    # Konfiguration statt Inline-Werte: MarketConfig() steht per Vorgabe auf
    # NQ (20 USD/Punkt). MNQ sind 2 USD/Punkt - jede USD-Zahl waere sonst
    # zehnmal zu gross gewesen.
    config = Config.load(str(PROJECT_ROOT / "config.yaml"))
    profil = profil_aus_config(config.backtest)
    kosten = CostModel.aus_profil(
        profil,
        tick_size=config.market.tick_size,
        point_value=config.market.point_value,
    )
    tester = Backtester(config.market, config.indicators, kosten)

    strategie = build_strategy(strategie_name, **parameter)

    split = split_data(df, SplitConfig(mode="fraction", in_sample_fraction=0.5))
    vorbereitet_is, vorbereitet_oos = prepare_split(tester, split)
    vorbereitet_gesamt = pd.concat([vorbereitet_is, vorbereitet_oos])

    lauf_gesamt = tester.run(vorbereitet_gesamt, strategie, already_prepared=True)
    lauf_is = tester.run(vorbereitet_is, strategie, label="in-sample", already_prepared=True)
    lauf_oos = tester.run(vorbereitet_oos, strategie, label="out-of-sample", already_prepared=True)

    def kennzahlen(lauf) -> dict:
        m = bm.compute_metrics(lauf, initial_capital=startkapital)
        kommission = sum(abs(t.commission) for t in lauf.trades)
        return {
            "trades": m.trades,
            "win_rate": m.win_rate,
            "expectancy_r": m.expectancy,
            "profit_factor": m.profit_factor,
            "payoff_ratio": abs(m.avg_win / m.avg_loss) if m.avg_loss else None,
            # backtest.metrics kennt kein SQN und keine MAE/MFE-Aggregate.
            # Lieber leer als geschaetzt - siehe Invariante 11.
            "sqn": None,
            "net_pnl": m.total_pnl,
            "commission": kommission,
            "final_equity": startkapital + m.total_pnl,
            "return_pct": (m.total_pnl / startkapital * 100) if startkapital else 0.0,
            "max_drawdown_usd": m.max_drawdown,
            "max_drawdown_pct": m.max_drawdown_pct,
            "max_consecutive_losses": m.max_consecutive_losses,
            "avg_bars_held": m.avg_bars_held,
            "avg_mae_r": None,
            "avg_mfe_r": None,
            "start_equity": startkapital,
        }

    gesamt = kennzahlen(lauf_gesamt)

    hinweise = [
        f"Datenbasis: {len(vorbereitet_gesamt)} 1m-Kerzen aus der Live-Sammlung "
        f"(ntbridge.sqlite3), {vorbereitet_gesamt.index[0]:%Y-%m-%d} bis "
        f"{vorbereitet_gesamt.index[-1]:%Y-%m-%d}. Das ist kein geprueftes "
        "Research-Ergebnis, sondern ein Probelauf auf einem kurzen Zeitraum.",
        f"Kostenprofil: {profil.name} ({profil.summe_je_seite:.2f} USD je Seite"
        + (", Annahme)" if profil.ist_annahme else ", belegt)"),
        "Der Out-of-Sample-Block ist die zweite Haelfte desselben Zeitraums - "
        "eine Aufteilung zur Orientierung, keine Confirmation nach Masterplan G.",
    ]
    if gesamt["trades"] < MIN_TRADES_FUER_AUSSAGE:
        hinweise.append(
            f"Nur {gesamt['trades']} Trades - unter {MIN_TRADES_FUER_AUSSAGE} "
            "sagen Trefferquote und Profitfaktor nichts aus."
        )

    return {
        "symbol": symbol,
        "instrument_name": config.market.product,
        "base_timeframe": "1m",
        "bars": len(vorbereitet_gesamt),
        "first_ts": int(vorbereitet_gesamt.index[0].timestamp() * 1000),
        "last_ts": int(vorbereitet_gesamt.index[-1].timestamp() * 1000),
        "backtest_version": "2.0",
        "warnings": hinweise,
        "is_significant": gesamt["trades"] >= MIN_TRADES_FUER_AUSSAGE,
        "min_trades": MIN_TRADES_FUER_AUSSAGE,
        "overall": gesamt,
        "in_sample": kennzahlen(lauf_is),
        "out_of_sample": kennzahlen(lauf_oos),
        "by_strategy": {strategie_name: gesamt},
        "by_symbol": {symbol: gesamt},
        "by_session": {},
        "by_direction": {},
        "by_exit": {},
        "by_stop_anchor": {},
        "by_target_source": {},
        "exit_counts": {},
        "rejections": {},
        "assumptions": {
            "kostenprofil": profil.name,
            "kosten_je_seite_usd": profil.summe_je_seite,
            "kosten_ist_annahme": profil.ist_annahme,
            "punktwert_usd": config.market.point_value,
            "split": "50/50 chronologisch",
            "strategie": strategie_name,
            "parameter": strategie.params,
        },
        "equity": [
            {"index": i, "ts": int(ts.timestamp() * 1000), "equity": wert}
            for i, (ts, wert) in enumerate(lauf_gesamt.equity.items())
        ],
    }

@app.get("/api/backtest")
async def get_last_backtest(symbol: str = "MNQ"):
    raise HTTPException(status_code=404, detail="Kein Backtest vorhanden")

@app.get("/api/backtest/runs")
async def get_backtest_runs(symbol: str = "MNQ", limit: int = 10):
    return []

@app.post("/api/session/start")
async def session_start(body: dict = None):
    return get_session()

@app.post("/api/session/halt")
async def session_halt():
    return get_session()

@app.post("/api/session/resume")
async def session_resume():
    return get_session()

@app.post("/api/session/stop")
async def session_stop():
    return get_session()

@app.get("/api/session/trades")
async def session_trades(limit: int = 50):
    """Tatsaechlich ausgefuehrte Trades - vollstaendig rekonstruierbar.

    Jeder Datensatz traegt Ein- und Ausstieg, Grund des Ausstiegs, Menge,
    Kommission, P&L und - sofern ein Stop bekannt war - das R-Vielfache.
    MAE/MFE bleiben leer, bis sie aus den Kerzen nachgerechnet sind; eine
    Schaetzung waere hier eine Zahl, die aussieht wie eine Messung.
    """
    return STORE.trades(limit=limit)

@app.get("/api/sessions")
async def session_runs(limit: int = 10):
    return []

@app.post("/api/history/nt8")
async def import_nt8_history(body: dict = None):
    """types.ts: HistoryResponse"""
    return {
        "symbol": (body or {}).get("symbol", "MNQ"),
        "bars": 0,
        "first_ts": 0,
        "last_ts": 0,
        "complete": True,
        "detail": "NinjaTrader Import nicht konfiguriert",
    }

# ---------------------------------------------------------------------------
# Static files (React build)
# ---------------------------------------------------------------------------
dist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ui', 'frontend', 'dist')
dist_path = os.path.normpath(dist_path)

if os.path.exists(dist_path):
    assets_path = os.path.join(dist_path, 'assets')
    if os.path.exists(assets_path):
        app.mount('/assets', StaticFiles(directory=assets_path), name='assets')

    @app.get('/')
    def read_root():
        return FileResponse(os.path.join(dist_path, 'index.html'))

    @app.get('/{catchall:path}')
    def read_catchall(catchall: str):
        if catchall.startswith('api/'):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(os.path.join(dist_path, 'index.html'))
else:
    logger.warning(f"UI dist nicht gefunden: {dist_path}")

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host='127.0.0.1', port=8790)












