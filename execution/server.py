"""
Execution Server fuer die TradeX Desktop App.

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
# Risk (inline, kein Package-Import noetig)
# ---------------------------------------------------------------------------
class RiskState:
    def __init__(self):
        self.max_daily_loss = 1500.0
        self.current_daily_loss = 0.0
        self.max_contracts = 2

    def check_order(self, symbol: str, side: str, qty: int, price: float) -> bool:
        if self.current_daily_loss <= -self.max_daily_loss:
            logger.warning("RISK REJECT: Daily loss limit reached.")
            return False
        if qty > self.max_contracts:
            logger.warning(f"RISK REJECT: Max contracts ({self.max_contracts}) exceeded.")
            return False
        return True

risk = RiskState()

# ---------------------------------------------------------------------------
# Order-Queue (polling-basiert fuer NinjaTrader)
# ---------------------------------------------------------------------------
pending_orders = []
pending_modifies = []

class OrderRequest(BaseModel):
    symbol: str
    side: str
    qty: int
    price: float
    stop_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    kind: Optional[str] = "MARKET"

class StopUpdate(BaseModel):
    symbol: str
    new_stop: float

class FillEvent(BaseModel):
    symbol: str
    price: float
    quantity: int

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")

def get_db(name: str):
    path = DATA_DIR / name
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------------
# API Endpoints - Orders
# ---------------------------------------------------------------------------
@app.post("/api/order/submit")
def submit_order(order: OrderRequest):
    if not risk.check_order(order.symbol, order.side, order.qty, order.price):
        raise HTTPException(status_code=400, detail="Risk limit exceeded")
    
    order_id = str(uuid.uuid4())
    pending_orders.append({
        "order_id": order_id,
        "direction": order.side.upper(),
        "symbol": order.symbol,
        "quantity": order.qty,
        "limit_price": order.price,
        "stop_price": order.stop_price or 0.0,
        "stop_loss_price": order.stop_loss or 0.0,
        "take_profit_price": order.take_profit or 0.0,
        "kind": order.kind,
        "order_type": (order.kind or "MARKET").upper()
    })
    return {"status": "success", "message": "Order placed", "order_id": order_id}

@app.get("/api/orders/pending")
def get_pending_orders():
    res = list(pending_orders)
    pending_orders.clear()
    return res

@app.get("/api/orders/modify_pending")
def get_pending_modifies():
    res = list(pending_modifies)
    pending_modifies.clear()
    return res

@app.post("/api/orders/fill")
def handle_fill(fill: FillEvent):
    return {"status": "ok"}

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

@app.post("/api/backtest")
async def run_backtest(body: dict = None):
    """types.ts: BacktestReport - stub"""
    return {"detail": "Backtest nicht verfuegbar im Execution-Modus"}

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
    return []

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
