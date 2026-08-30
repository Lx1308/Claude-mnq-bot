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
from contextlib import asynccontextmanager
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
#: Wie oft die groben Timeframes (4h, 1d) aus den neuen 1m-Kerzen nachgezogen
#: werden. Der Startchart zeigt Tageskerzen ueber die ganze Historie; die
#: koennen nicht bei jeder Anfrage neu aggregiert werden (~20 s), also einmal
#: rechnen und danach am rechten Rand fortschreiben. Fuenf Minuten Verzug auf
#: der Tageskerze sind im Chart unsichtbar.
_AGGREGAT_INTERVALL_S = 300


async def _aggregat_schleife():
    """Zieht 4h/1d im Hintergrund aus den hereinkommenden 1m-Kerzen nach."""
    import asyncio

    from werkzeuge.aggregiere_kerzen import aggregiere

    while True:
        try:
            await asyncio.to_thread(
                aggregiere,
                PROJECT_ROOT / "data" / "ntbridge.sqlite3",
                symbol=CONFIG.market.product,
                voll=False,
                config=CONFIG,
            )
        except Exception as exc:  # noqa: BLE001 - eine Anzeigehilfe, kein Kernpfad
            logger.warning("Aggregatlauf fehlgeschlagen: %s", exc)
        await asyncio.sleep(_AGGREGAT_INTERVALL_S)


@asynccontextmanager
async def lebenszyklus(_app: FastAPI):
    """Startet den autonomen Bot mit dem Server und beendet ihn mit ihm.

    ``lifespan`` statt der abgekuendigten ``@app.on_event``-Haken: die sind
    seit FastAPI 0.109 veraltet und werfen eine DeprecationWarning.
    """
    import asyncio

    if CONFIG.ausfuehrung.enabled:
        BOT.start()
    else:
        logger.info(
            "Autonomer Bot ist aus (ausfuehrung.enabled=false). "
            "Das Order-Panel arbeitet unabhaengig davon."
        )
    aggregat_task = asyncio.create_task(_aggregat_schleife())
    try:
        yield
    finally:
        aggregat_task.cancel()
        BOT.stop()


app = FastAPI(lifespan=lebenszyklus)

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
from execution import buchung, overlays               # noqa: E402
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
def _rahmen_zu_bars(df) -> list[dict]:
    """OHLCV-DataFrame -> Liste im types.ts-Bar-Format (ts in Nanosekunden).

    Ueber die Spalten-Arrays, nicht ueber ``iterrows`` - das ist bei ein paar
    tausend Kerzen der Unterschied zwischen Millisekunden und Sekunden.
    """
    if df is None or df.empty:
        return []
    ts_ns = df.index.asi8  # Nanosekunden seit Epoch, UTC
    o = df["open"].to_numpy(dtype="float64")
    h = df["high"].to_numpy(dtype="float64")
    lo = df["low"].to_numpy(dtype="float64")
    c = df["close"].to_numpy(dtype="float64")
    v = df["volume"].fillna(0.0).to_numpy(dtype="float64")
    return [
        {
            "ts": int(ts_ns[i]),
            "open": float(o[i]),
            "high": float(h[i]),
            "low": float(lo[i]),
            "close": float(c[i]),
            "volume": float(v[i]),
            "roll_boundary": False,
        }
        for i in range(len(ts_ns))
    ]


@app.get("/api/bars")
def get_bars(
    symbol: str = "MNQ",
    timeframe: str = "1m",
    limit: int = 1500,
    before: int | None = None,
):
    """Kerzen fuer den Chart.

    ``limit=0`` liefert die gesamte Historie im gewaehlten Timeframe - so
    zeigt der Startchart 2019 bis heute als Tageskerzen. ``before`` (ns)
    blaettert nach hinten: die neuesten ``limit`` Kerzen vor diesem
    Zeitpunkt, fuer das Nachladen beim Zurueckscrollen.
    """
    symbol = symbol or "MNQ"
    timeframe = timeframe or "1m"
    try:
        df = lade_anzeige_kerzen(symbol, timeframe, limit=limit, before_ns=before)
        bars = _rahmen_zu_bars(df)
    except Exception as e:  # noqa: BLE001 - eine leere Antwort ist besser als ein 500
        logger.error("Bars Fehler (%s/%s): %s", symbol, timeframe, e)
        bars = []

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

def _iso_zu_ns(wert: str | None) -> int:
    if not wert:
        return 0
    try:
        return int(pd.Timestamp(wert, tz="UTC").value)
    except Exception:  # noqa: BLE001
        return 0


@app.get("/api/coverage")
def get_coverage():
    """types.ts: Coverage[] - was tatsaechlich in der Kerzendatenbank liegt.

    ``first_ts``/``last_ts`` in Nanosekunden (wie ueberall im Frontend-
    Vertrag); vorher standen hier fest ``0``, weshalb die Oberflaeche den
    abgedeckten Zeitraum nicht anzeigen konnte.
    """
    conn = get_db("ntbridge.sqlite3")
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT instrument, timeframe, COUNT(*) AS cnt, "
            "MIN(ts_utc) AS first_ts, MAX(ts_utc) AS last_ts "
            "FROM bars GROUP BY instrument, timeframe"
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()

    return [
        {
            "symbol": r["instrument"],
            "timeframe": r["timeframe"],
            "first_ts": _iso_zu_ns(r["first_ts"]),
            "last_ts": _iso_zu_ns(r["last_ts"]),
            "bar_count": r["cnt"],
        }
        for r in rows
        if r["cnt"] > 0
    ]

#: Wie viele Kerzen die Erkennung sieht. Mehr Kerzen kosten Rechenzeit, ohne
#: dass ein Muster von vor drei Tagen den Chart noch interessiert.
OVERLAY_KERZEN = 1500


# ---------------------------------------------------------------------------
# Anzeige-Kerzen.
#
# Seit dem NT8-Import (30.08.2026) liegen ~2,5 Mio MNQ-Minutenkerzen ab 2019
# in der Datenbank - aber nur als 1m. Die groeberen Timeframes werden mit
# werkzeuge/aggregiere_kerzen.py aus 1m vorberechnet und als eigene
# timeframe-Zeilen gespeichert (source="resampled_1m"), damit der Chart 2019
# bis heute in Millisekunden liefern kann statt 2,5 Mio Kerzen je Anfrage neu
# zu aggregieren (~20 s gemessen). Der Serverprozess zieht die juengsten
# Buckets im Hintergrund nach (siehe _aggregat_schleife).
#
# resample_ohlcv aus common/timeframes.py - dieselbe Regel wie im Backtest.
# KEINE zweite Rechenlogik.
# ---------------------------------------------------------------------------
from common.timeframes import (  # noqa: E402
    TimeframeSpec,
    normalize_timeframe,
    resample_ohlcv,
)


def _lies_bars(
    symbol: str,
    timeframe: str,
    *,
    limit: int | None,
    before_iso: str | None = None,
) -> pd.DataFrame:
    """Kerzen eines gespeicherten Timeframes, aufsteigend, UTC-Index.

    Eigene Verbindung ohne ``row_factory`` und mit festem Zeitstempelformat:
    ueber ``sqlite3.Row`` und Formaterkennung war schon das Lesen von 45.000
    1h-Kerzen mehrere Sekunden.
    """
    columns = ["ts_utc", "open", "high", "low", "close", "volume"]
    leer = pd.DataFrame(
        columns=columns[1:], index=pd.DatetimeIndex([], tz="UTC")
    )
    pfad = PROJECT_ROOT / "data" / "ntbridge.sqlite3"
    if not pfad.exists():
        return leer
    query = (
        "SELECT ts_utc, open, high, low, close, volume FROM bars "
        "WHERE instrument = ? AND timeframe = ?"
    )
    params: list = [symbol.upper(), timeframe]
    if before_iso is not None:
        query += " AND ts_utc < ?"
        params.append(before_iso)
    query += " ORDER BY ts_utc DESC"
    if limit:
        query += " LIMIT ?"
        params.append(int(limit))

    conn = sqlite3.connect(str(pfad))
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()
    if not rows:
        return leer
    rows.reverse()
    df = pd.DataFrame(rows, columns=columns)
    df.index = pd.to_datetime(df.pop("ts_utc"), utc=True, format="ISO8601")
    return df


def lade_anzeige_kerzen(
    symbol: str,
    timeframe: str,
    *,
    limit: int,
    before_ns: int | None = None,
) -> pd.DataFrame:
    """OHLCV fuer die Chart-Anzeige.

    ``limit`` = 0 heisst "so weit die Historie reicht" (fuer den groben
    Startchart ueber 2019 bis heute). ``before_ns`` blaettert nach hinten: die
    neuesten ``limit`` Kerzen VOR diesem Zeitpunkt.

    1m und die vorberechneten groeberen Timeframes kommen direkt aus der
    Datenbank. Fehlt ein grober Timeframe noch (Aggregatlauf nicht
    durchgelaufen), wird das begrenzte Fenster als Rueckfallebene direkt aus
    1m aggregiert.
    """
    symbol = (symbol or "MNQ").upper()
    tf = normalize_timeframe(timeframe or "1m")
    lim = None if (not limit or limit <= 0) else int(limit)
    before_iso = (
        pd.Timestamp(before_ns, unit="ns", tz="UTC").isoformat()
        if before_ns is not None
        else None
    )

    df = _lies_bars(symbol, tf, limit=lim, before_iso=before_iso)
    if not df.empty or tf == "1m":
        return df

    # Rueckfallebene: grober Timeframe noch nicht vorberechnet. Nur ein
    # begrenztes Fenster aus 1m aggregieren - die volle Historie waere hier
    # zu langsam.
    minuten = TimeframeSpec.from_label(tf).minutes
    roh_limit = (lim or 3_000) * minuten * 2 + 5_000
    roh = _lies_bars(symbol, "1m", limit=roh_limit, before_iso=before_iso)
    if roh.empty:
        return roh
    grob = resample_ohlcv(roh, tf, CONFIG.market.session)
    return grob.iloc[-lim:] if lim and len(grob) > lim else grob


def _vorbereiteter_rahmen(symbol: str, timeframe: str, kerzen: int = OVERLAY_KERZEN):
    """Kerzen laden und die Indikatoren anhaengen - ueber DIE eine Rechnung.

    ``compute_indicators`` aus ``common/indicators.py``, also dieselbe
    Funktion, die auch Backtest und Ideen-Protokollierung benutzen
    (Invariante 1). Eine eigene ATR-Formel fuer die Oberflaeche waere der
    Anfang davon, dass der Chart etwas anderes zeigt als das, was gemessen
    wurde.
    """
    from common.indicators import compute_indicators

    # Ueber lade_anzeige_kerzen, damit die Erkennung auch auf Timeframes
    # laeuft, die nicht roh gespeichert sind: seit dem NT8-Import liegt nur
    # 1m vollstaendig vor, 5m/15m/1h werden daraus aggregiert.
    df = lade_anzeige_kerzen(symbol, timeframe, limit=kerzen)
    if df.empty:
        return df
    return compute_indicators(df, CONFIG.indicators, CONFIG.market.session)


def _tagesniveaus(df) -> dict[str, float]:
    """Benannte Niveaus als {name: preis} - inklusive Asia und London."""
    from common.levels import compute_levels

    if df.empty:
        return {}
    try:
        satz = compute_levels(
            df,
            get_instrument(CONFIG.market.product),
            atr_value=float(df["atr"].iloc[-1]) if "atr" in df.columns else None,
            session_cfg=CONFIG.market.session,
        )
    except ValueError:
        return {}
    return {level.name: float(level.price) for level in satz.levels}


@app.get("/api/overlays")
def get_overlays(symbol: str = "MNQ", timeframe: str = "5m"):
    """FVG, Swings, Liquiditaetszonen, Sweeps, Strukturbrueche, Displacements.

    Stand hier vorher als leere Liste - deshalb blieb der Chart nackt,
    obwohl die Haken gesetzt waren und die Erkennungslogik seit dem
    27.08.2026 im Projekt liegt.
    """
    symbol = symbol or "MNQ"
    timeframe = timeframe or "5m"
    df = _vorbereiteter_rahmen(symbol, timeframe)
    if df.empty:
        return overlays.baue_overlays(
            df, get_instrument(CONFIG.market.product), CONFIG,
            symbol=symbol, timeframe=timeframe,
        )
    return overlays.baue_overlays(
        df,
        get_instrument(CONFIG.market.product),
        CONFIG,
        symbol=symbol,
        timeframe=timeframe,
        level=_tagesniveaus(df),
    )


@app.get("/api/levels")
def get_levels(symbol: str = "MNQ", timeframe: str = "1m"):
    """Die benannten Tagesniveaus mit Abstand - auch in ATR-Vielfachen.

    Nur die Punktzahl waere zwischen einem ruhigen und einem hektischen Tag
    nicht vergleichbar; deshalb steht der ATR-Abstand ueberall daneben.
    """
    from common.levels import compute_levels

    df = _vorbereiteter_rahmen(symbol or "MNQ", timeframe or "1m")
    if df.empty:
        raise HTTPException(
            status_code=409, detail=f"Keine Kerzen fuer {symbol}/{timeframe}."
        )
    satz = compute_levels(
        df,
        get_instrument(CONFIG.market.product),
        atr_value=float(df["atr"].iloc[-1]) if "atr" in df.columns else None,
        session_cfg=CONFIG.market.session,
    )
    return {
        "symbol": symbol or "MNQ",
        "kurs": satz.current_price,
        "atr": satz.atr_value,
        "levels": [
            {
                "name": level.name,
                "preis": level.price,
                "abstand_punkte": level.distance_points,
                "abstand_atr": level.distance_atr,
            }
            for level in satz.levels
        ],
        "nicht_verfuegbar": getattr(satz, "unavailable", {}),
    }


@app.get("/api/analysis")
def get_analysis(symbol: str = "MNQ"):
    """Trend und Struktur ueber mehrere Zeitebenen.

    Der 1H-Trend, den das Strategie-Panel anzeigt, kommt von hier - und zwar
    aus ``common/structure.py::assess_trend``, derselben Bewertung wie im
    ``/analyse``-Bericht. Vorher stand hier fest "neutral".
    """
    symbol = symbol or "MNQ"
    rahmen = {
        tf: _vorbereiteter_rahmen(symbol, tf, kerzen=600)
        for tf in ("5m", "15m", "1h")
    }
    ergebnis = overlays.baue_analyse(rahmen, CONFIG, symbol=symbol)
    ergebnis["session"] = _session_name()
    return ergebnis


def _session_name() -> str:
    from common.sessions import primary_session

    return primary_session(datetime.now(timezone.utc))

@app.get("/api/strategy")
def get_strategy(symbol: str = "MNQ", limit: int = 30):
    """Erkannte Setups und jede Entscheidung - auch die gegen einen Trade.

    Die Quellen sind dieselben, aus denen der Bot handelt: die Ideen aus
    ``ideas.sqlite3`` und das Entscheidungsprotokoll der Ausfuehrung. Vorher
    stand hier eine leere Huelle, weshalb das Panel dauerhaft "KEIN SETUP"
    meldete, egal was der Markt tat.

    ``recent_decisions`` enthaelt ausdruecklich auch die Ablehnungen mit
    ihrem Grund. Ohne sie liesse sich nicht unterscheiden, ob gerade kein
    Signal da war oder ob ein Filter es verhindert hat.
    """
    from ideas.setups import SETUP_BIBLIOTHEK

    symbol = symbol or "MNQ"
    ideen: list[dict] = []
    conn = get_db("ideas.sqlite3")
    if conn:
        try:
            cur = conn.execute(
                "SELECT idea_id, erstellt_utc, setup, richtung, timeframe, entry, "
                "stop, ziel, crv, atr_referenz, gefiltert, filter_gruende "
                "FROM ideen WHERE instrument = ? ORDER BY erstellt_utc DESC LIMIT ?",
                (symbol, int(limit)),
            )
            ideen = [dict(r) for r in cur.fetchall()]
        except Exception as fehler:  # noqa: BLE001
            logger.error("Ideen nicht lesbar: %s", fehler)
        finally:
            conn.close()

    aktive_setups = [
        name for name, parameter in CONFIG.ideas.setups.items() if parameter.aktiv
    ]

    def _signal(idee: dict) -> dict:
        risiko = abs(float(idee["entry"]) - float(idee["stop"]))
        instrument = get_instrument(CONFIG.market.product)
        return {
            "setup_id": int(idee["idea_id"]),
            "symbol": symbol,
            "strategy": idee["setup"],
            "side": "LONG" if idee["richtung"] == "long" else "SHORT",
            "entry": float(idee["entry"]),
            "stop": float(idee["stop"]),
            "target": float(idee["ziel"]),
            "stop_ticks": risiko / instrument.tick_size if instrument.tick_size else 0.0,
            "rr": float(idee["crv"] or 0.0),
            "quantity": 0,
            "risk_amount": risiko * instrument.point_value,
            "reward_amount": abs(float(idee["ziel"]) - float(idee["entry"]))
            * instrument.point_value,
            "entry_ts": _ts_ns(idee["erstellt_utc"]),
            "stop_anchor": "atr",
            "target_source": "atr",
        }

    entscheidungen = []
    ablehnungen: dict[str, int] = {}
    for idee in ideen:
        import json as _json

        gruende = []
        try:
            gruende = _json.loads(idee.get("filter_gruende") or "[]")
        except Exception:  # noqa: BLE001
            gruende = []
        gefiltert = bool(idee["gefiltert"])
        for grund in gruende:
            # Nach der Ursache zaehlen, nicht nach dem Messwert: die Gruende
            # tragen ihre Zahl mit ("adx_zu_niedrig... (16.0 < 20.0)"), und
            # ungekuerzt waere jeder Grund einmalig. Eine Haeufigkeitsliste, in
            # der alles genau einmal vorkommt, sagt nichts.
            art = grund.split(" (")[0]
            ablehnungen[art] = ablehnungen.get(art, 0) + 1

        entscheidungen.append({
            "ts": _ts_ns(idee["erstellt_utc"]),
            "symbol": symbol,
            "timeframe": idee["timeframe"],
            "setup_id": int(idee["idea_id"]),
            "direction": "bullish" if idee["richtung"] == "long" else "bearish",
            "decision": "NO_TRADE" if gefiltert else (
                "LONG" if idee["richtung"] == "long" else "SHORT"
            ),
            "stage": "filtered" if gefiltert else "ready",
            "htf_bias": "neutral",
            "strategy": idee["setup"],
            "checklist": {"filter": not gefiltert},
            "missing": list(gruende),
            "blocking_reason": ", ".join(gruende),
            "reasons": [],
            "signal": None if gefiltert else _signal(idee),
        })

    ungefiltert = [i for i in ideen if not i["gefiltert"]]
    return {
        "symbol": symbol,
        "enabled": CONFIG.ausfuehrung.enabled,
        "setup_timeframe": CONFIG.ideas.timeframe,
        "confirmation_timeframe": CONFIG.ideas.timeframe,
        "stop_anchor": "atr",
        "min_rr": CONFIG.ideas.crv_schwelle,
        "active_setups": [],
        "recent_decisions": entscheidungen,
        "last_signal": _signal(ungefiltert[0]) if ungefiltert else None,
        "decisions_total": len(ideen),
        "trades_total": len(ungefiltert),
        "no_trades_total": len(ideen) - len(ungefiltert),
        "rejection_counts": ablehnungen,
        # Zusatzfelder ausserhalb des types.ts-Vertrags: welche Setup-Familien
        # ueberhaupt scharf sind. Ohne die Angabe sieht ein leeres Panel
        # genauso aus wie ein abgeschaltetes.
        "aktive_setup_familien": aktive_setups,
        "bekannte_setup_familien": sorted(SETUP_BIBLIOTHEK),
    }


def _ts_ns(wert) -> int:
    """ISO-Zeitstempel in Nanosekunden - die Einheit des Frontends."""
    try:
        zeitpunkt = datetime.fromisoformat(str(wert))
        if zeitpunkt.tzinfo is None:
            zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
        return int(zeitpunkt.timestamp() * 1_000_000_000)
    except (TypeError, ValueError):
        return 0

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












