"""Persistenter Ausfuehrungsspeicher: Orders, Fuellungen, Trades, Entscheidungen.

Warum eine Datenbank und keine Liste im Arbeitsspeicher
------------------------------------------------------
Die erste Fassung hielt die offenen Orders in einer Python-Liste, und
``GET /api/orders/pending`` **leerte** sie beim Abholen. Das hatte drei
Folgen, von denen jede einzeln gereicht haette:

* Ein zweiter Abholer (ein zweiter Bridge-Prozess, ein Neuladen der
  Oberflaeche) nahm Orders weg, die nie bei NinjaTrader ankamen.
* Ein Neustart des Servers loeschte jede offene Order - ohne Spur, dass es
  sie gab.
* Es gab keinerlei Nachvollziehbarkeit. Die Frage "warum wurde dieser Trade
  eigentlich eroeffnet" war nicht beantwortbar.

Hier liegt deshalb alles auf der Platte, und der Abholvorgang ist ein
**Zustandswechsel** (``angelegt`` -> ``gesendet``), kein Entnehmen.

Was hier NICHT passiert
-----------------------
Dieser Speicher entscheidet nichts. Er rechnet keine Risikogrenzen und lehnt
nichts ab - das macht ``execution.risiko`` auf seiner Grundlage. Die Trennung
ist Absicht: ein Speicher, der auch urteilt, laesst sich nicht mehr testen,
ohne die Urteile mitzutesten.

Zeitstempel sind durchgehend ISO-8601 in UTC, wie ueberall im Projekt.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

__all__ = ["OrderStatus", "Order", "ExecutionStore"]


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    erstellt_utc    TEXT NOT NULL,
    zuletzt_utc     TEXT NOT NULL,
    quelle          TEXT NOT NULL,          -- 'ui' | 'bot'
    konto           TEXT NOT NULL,
    instrument      TEXT NOT NULL,
    richtung        TEXT NOT NULL,          -- 'long' | 'short'
    art             TEXT NOT NULL,          -- 'MARKET' | 'LIMIT' | 'STOP'
    menge           INTEGER NOT NULL,
    limit_preis     REAL,
    stop_preis      REAL,
    stop_loss       REAL,
    take_profit     REAL,
    status          TEXT NOT NULL,
    nt_zustand      TEXT,                   -- letzter Zustand laut NinjaTrader
    fehler          TEXT,
    idee_id         TEXT,
    hypothese       TEXT,
    begruendung     TEXT                    -- JSON: warum diese Order
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status, erstellt_utc);

CREATE TABLE IF NOT EXISTS fills (
    exec_id     TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL,
    rolle       TEXT NOT NULL,              -- 'entry' | 'stop' | 'target' | ''
    ts_utc      TEXT NOT NULL,
    menge       INTEGER NOT NULL,
    preis       REAL NOT NULL,
    kommission  REAL NOT NULL DEFAULT 0,
    empfangen_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fills_order ON fills (order_id, ts_utc);

-- Ein geschlossener Trade. Entsteht erst, wenn eine Ausstiegsfuellung
-- vorliegt - eine offene Position ist hier bewusst kein Datensatz, sonst
-- gaebe es zwei Wahrheiten darueber, was offen ist.
CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,
    order_id        TEXT NOT NULL,
    instrument      TEXT NOT NULL,
    richtung        TEXT NOT NULL,
    menge           INTEGER NOT NULL,
    einstieg_utc    TEXT NOT NULL,
    einstiegskurs   REAL NOT NULL,
    ausstieg_utc    TEXT NOT NULL,
    ausstiegskurs   REAL NOT NULL,
    grund_ausstieg  TEXT NOT NULL,          -- 'stop' | 'target' | 'manuell' | ...
    punkte_brutto   REAL NOT NULL,
    kommission      REAL NOT NULL,
    pnl_usd         REAL NOT NULL,
    r_vielfaches    REAL,                   -- None, wenn kein Stop bekannt war
    mae_punkte      REAL,                   -- None, solange nicht nachgerechnet
    mfe_punkte      REAL,
    session_datum   TEXT NOT NULL,          -- CME-Handelstag (18:00-ET-Regel)
    idee_id         TEXT,
    hypothese       TEXT
);

CREATE INDEX IF NOT EXISTS idx_trades_session ON trades (session_datum);

-- Jede Entscheidung des Bots, auch die gegen einen Trade. Ohne die Ablehnungen
-- laesst sich spaeter nicht unterscheiden, ob ein Filter zu scharf stand oder
-- ob es schlicht kein Signal gab - dieselbe Ueberlegung wie bei den
-- gefilterten Ideen in Etappe C.
CREATE TABLE IF NOT EXISTS entscheidungen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_utc          TEXT NOT NULL,
    instrument      TEXT NOT NULL,
    ergebnis        TEXT NOT NULL,          -- 'order' | 'abgelehnt' | 'kein_signal'
    grund           TEXT NOT NULL,
    order_id        TEXT,
    idee_id         TEXT,
    hypothese       TEXT,
    marktzustand    TEXT                    -- JSON-Momentaufnahme
);

CREATE INDEX IF NOT EXISTS idx_entscheidungen_ts ON entscheidungen (ts_utc);

-- Kontostand zum Sitzungsschluss. Grundlage des nachziehenden Verlustlimits:
-- bei EOD-Trailing zaehlt genau dieser Wert, nicht der hoechste Stand
-- waehrend des Tages.
CREATE TABLE IF NOT EXISTS tagesabschluss (
    session_datum   TEXT PRIMARY KEY,
    schlussstand_usd REAL NOT NULL,
    realisiert_usd  REAL NOT NULL,
    trades          INTEGER NOT NULL,
    geschrieben_utc TEXT NOT NULL
);
"""


class OrderStatus:
    """Lebenslauf einer Order.

    ``ANGELEGT`` heisst: angenommen und auf der Platte, aber noch nicht an
    NinjaTrader uebergeben. Erst ``GESENDET`` bedeutet, dass sie ueber den
    Draht ging. Der Unterschied ist nach einem Absturz die ganze Frage.
    """

    ANGELEGT = "angelegt"
    GESENDET = "gesendet"
    ANGENOMMEN = "angenommen"
    TEILGEFUELLT = "teilgefuellt"
    GEFUELLT = "gefuellt"
    STORNIERT = "storniert"
    ABGELEHNT = "abgelehnt"

    #: Zustaende, in denen die Order aus Sicht des Risikos noch "lebt".
    OFFEN = frozenset({ANGELEGT, GESENDET, ANGENOMMEN, TEILGEFUELLT})
    ENDGUELTIG = frozenset({GEFUELLT, STORNIERT, ABGELEHNT})


@dataclass
class Order:
    """Eine Orderanforderung, bevor sie gespeichert wird."""

    instrument: str
    richtung: str            # 'long' | 'short'
    art: str                 # 'MARKET' | 'LIMIT' | 'STOP'
    menge: int
    quelle: str = "ui"
    konto: str = "Sim101"
    limit_preis: float | None = None
    stop_preis: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    idee_id: str | None = None
    hypothese: str | None = None
    begruendung: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.richtung = str(self.richtung).strip().lower()
        if self.richtung not in ("long", "short"):
            raise ValueError(
                f"richtung muss 'long' oder 'short' sein, nicht {self.richtung!r}. "
                "Hier NICHT raten - eine geratene Richtung ist ein Trade in die "
                "falsche Seite des Marktes."
            )
        self.art = str(self.art).strip().upper()
        if self.art not in ("MARKET", "LIMIT", "STOP"):
            raise ValueError(f"Unbekannte Orderart {self.art!r}.")
        self.menge = int(self.menge)
        if self.menge <= 0:
            raise ValueError("menge muss > 0 sein.")
        if self.art == "LIMIT" and not self.limit_preis:
            raise ValueError("LIMIT-Order ohne limit_preis.")
        if self.art == "STOP" and not self.stop_preis:
            raise ValueError("STOP-Order ohne stop_preis.")


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionStore:
    """SQLite-Speicher der Ausfuehrungsschicht.

    Threadsicher ueber eine Sperre: der Server bedient mehrere Anfragen
    gleichzeitig, und zwei gleichzeitige Statuswechsel auf derselben Order
    waeren sonst ein Rennen.
    """

    def __init__(self, pfad: str | Path) -> None:
        self._pfad = Path(pfad)
        self._pfad.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._pfad), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL: der Bot schreibt, waehrend die Oberflaeche liest.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- Orders ------------------------------------------------------------

    def lege_order_an(self, order: Order, order_id: str) -> dict[str, Any]:
        jetzt = _jetzt()
        with self._lock:
            self._conn.execute(
                "INSERT INTO orders (order_id, erstellt_utc, zuletzt_utc, quelle, "
                "konto, instrument, richtung, art, menge, limit_preis, stop_preis, "
                "stop_loss, take_profit, status, idee_id, hypothese, begruendung) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    order_id, jetzt, jetzt, order.quelle, order.konto,
                    order.instrument, order.richtung, order.art, order.menge,
                    order.limit_preis, order.stop_preis, order.stop_loss,
                    order.take_profit, OrderStatus.ANGELEGT, order.idee_id,
                    order.hypothese, json.dumps(order.begruendung, default=str),
                ),
            )
            self._conn.commit()
        return self.order(order_id)

    def order(self, order_id: str) -> dict[str, Any] | None:
        with self._lock:
            zeile = self._conn.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        return dict(zeile) if zeile else None

    def orders(
        self, *, status: Iterable[str] | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        frage = "SELECT * FROM orders"
        werte: list[Any] = []
        if status is not None:
            status = list(status)
            frage += f" WHERE status IN ({','.join('?' * len(status))})"
            werte.extend(status)
        frage += " ORDER BY erstellt_utc DESC LIMIT ?"
        werte.append(int(limit))
        with self._lock:
            return [dict(z) for z in self._conn.execute(frage, werte).fetchall()]

    def zu_senden(self) -> list[dict[str, Any]]:
        """Orders abholen und dabei auf ``gesendet`` setzen.

        Beides in EINER Transaktion. Wuerde erst gelesen und dann geschrieben,
        koennte ein zweiter Abholer dazwischen dieselbe Order bekommen - genau
        der Fehler, den die alte Liste hatte, nur langsamer.
        """
        with self._lock:
            zeilen = self._conn.execute(
                "SELECT * FROM orders WHERE status = ? ORDER BY erstellt_utc",
                (OrderStatus.ANGELEGT,),
            ).fetchall()
            if zeilen:
                self._conn.executemany(
                    "UPDATE orders SET status = ?, zuletzt_utc = ? WHERE order_id = ?",
                    [(OrderStatus.GESENDET, _jetzt(), z["order_id"]) for z in zeilen],
                )
                self._conn.commit()
        return [dict(z) for z in zeilen]

    def setze_status(
        self,
        order_id: str,
        status: str,
        *,
        nt_zustand: str | None = None,
        fehler: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE orders SET status = ?, zuletzt_utc = ?, "
                "nt_zustand = COALESCE(?, nt_zustand), "
                "fehler = COALESCE(?, fehler) WHERE order_id = ?",
                (status, _jetzt(), nt_zustand, fehler, order_id),
            )
            self._conn.commit()

    # -- Fuellungen --------------------------------------------------------

    def erfasse_fill(
        self,
        *,
        exec_id: str,
        order_id: str,
        rolle: str,
        ts_utc: str,
        menge: int,
        preis: float,
        kommission: float = 0.0,
    ) -> bool:
        """Eine Fuellung ablegen. ``False``, wenn sie schon bekannt war.

        Die Wiederholungsfestigkeit ist kein Luxus: nach einem
        Verbindungsabriss schickt NinjaTrader Ereignisse erneut, und eine
        doppelt gezaehlte Fuellung verfaelscht sowohl den Tagesverlust als
        auch den nachziehenden Drawdown.
        """
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO fills (exec_id, order_id, rolle, ts_utc, menge, "
                    "preis, kommission, empfangen_utc) VALUES (?,?,?,?,?,?,?,?)",
                    (exec_id, order_id, rolle, ts_utc, int(menge), float(preis),
                     float(kommission), _jetzt()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def fills(self, order_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(z)
                for z in self._conn.execute(
                    "SELECT * FROM fills WHERE order_id = ? ORDER BY ts_utc",
                    (order_id,),
                ).fetchall()
            ]

    # -- Trades ------------------------------------------------------------

    def schreibe_trade(self, trade: dict[str, Any]) -> None:
        spalten = [
            "trade_id", "order_id", "instrument", "richtung", "menge",
            "einstieg_utc", "einstiegskurs", "ausstieg_utc", "ausstiegskurs",
            "grund_ausstieg", "punkte_brutto", "kommission", "pnl_usd",
            "r_vielfaches", "mae_punkte", "mfe_punkte", "session_datum",
            "idee_id", "hypothese",
        ]
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO trades ({','.join(spalten)}) "
                f"VALUES ({','.join('?' * len(spalten))})",
                [trade.get(s) for s in spalten],
            )
            self._conn.commit()

    def trades(
        self, *, session_datum: str | None = None, limit: int = 500
    ) -> list[dict[str, Any]]:
        frage = "SELECT * FROM trades"
        werte: list[Any] = []
        if session_datum is not None:
            frage += " WHERE session_datum = ?"
            werte.append(session_datum)
        frage += " ORDER BY ausstieg_utc DESC LIMIT ?"
        werte.append(int(limit))
        with self._lock:
            return [dict(z) for z in self._conn.execute(frage, werte).fetchall()]

    def realisiert(self, *, session_datum: str | None = None) -> float:
        frage = "SELECT COALESCE(SUM(pnl_usd), 0.0) AS s FROM trades"
        werte: list[Any] = []
        if session_datum is not None:
            frage += " WHERE session_datum = ?"
            werte.append(session_datum)
        with self._lock:
            return float(self._conn.execute(frage, werte).fetchone()["s"])

    # -- Entscheidungen ----------------------------------------------------

    def protokolliere_entscheidung(
        self,
        *,
        instrument: str,
        ergebnis: str,
        grund: str,
        order_id: str | None = None,
        idee_id: str | None = None,
        hypothese: str | None = None,
        marktzustand: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO entscheidungen (ts_utc, instrument, ergebnis, grund, "
                "order_id, idee_id, hypothese, marktzustand) VALUES (?,?,?,?,?,?,?,?)",
                (
                    _jetzt(), instrument, ergebnis, grund, order_id, idee_id,
                    hypothese,
                    json.dumps(marktzustand, default=str) if marktzustand else None,
                ),
            )
            self._conn.commit()

    def entscheidungen(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(z)
                for z in self._conn.execute(
                    "SELECT * FROM entscheidungen ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            ]

    # -- Tagesabschluss ----------------------------------------------------

    def schreibe_tagesabschluss(
        self, session_datum: str, schlussstand_usd: float, realisiert_usd: float,
        trades: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tagesabschluss (session_datum, "
                "schlussstand_usd, realisiert_usd, trades, geschrieben_utc) "
                "VALUES (?,?,?,?,?)",
                (session_datum, float(schlussstand_usd), float(realisiert_usd),
                 int(trades), _jetzt()),
            )
            self._conn.commit()

    def hoechster_tagesschluss(self) -> float | None:
        """Hoechster Kontostand zu einem Sitzungsschluss - oder None.

        ``None`` heisst "es gibt noch keinen abgeschlossenen Handelstag", und
        das ist etwas anderes als 0. Das nachziehende Verlustlimit steht dann
        noch auf seinem Startwert.
        """
        with self._lock:
            zeile = self._conn.execute(
                "SELECT MAX(schlussstand_usd) AS m FROM tagesabschluss"
            ).fetchone()
        return None if zeile is None or zeile["m"] is None else float(zeile["m"])

    def tagesabschluesse(self, limit: int = 60) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(z)
                for z in self._conn.execute(
                    "SELECT * FROM tagesabschluss ORDER BY session_datum DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            ]
