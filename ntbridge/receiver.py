"""HTTP-Empfaenger fuer die NinjaScript-Bridge.

Warum die Standardbibliothek und nicht FastAPI
----------------------------------------------
Der Empfaenger hat **einen** Endpunkt, **einen** Client (NinjaTrader auf
demselben Rechner) und ein Aufkommen von wenigen Anfragen pro Minute. Keine
Authentifizierung, kein TLS, keine oeffentliche Erreichbarkeit.

FastAPI braechte Starlette, Pydantic und Uvicorn mit - drei zusaetzliche
Abhaengigkeiten plus einen Event-Loop, fuer null Gewinn bei diesem Profil.
Die Validierung machen wir ohnehin selbst und strenger, als ein Schema es
tun wuerde (OHLC-Konsistenz, Zukunftszeitstempel).

``ThreadingHTTPServer`` bedient die parallelen Charts problemlos: jedes
NinjaTrader-Chart schickt unabhaengig, und jeder Request wird in einem
eigenen Thread abgearbeitet. Die Serialisierung zur Datenbank uebernimmt der
:class:`~ntbridge.store.BarStore`.

Sicherheit
----------
Gebunden wird ausschliesslich an ``127.0.0.1``. Der Port ist damit von aussen
nicht erreichbar, auch nicht im lokalen Netz.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from common.logging_setup import log_event
from ntbridge.store import BarStore, IngestResult

log = logging.getLogger(__name__)

# Groesse eines einzelnen POST-Koerpers. Die Historie von 3000 Kerzen liegt
# bei rund 1 MB - 16 MB ist grosszuegig und begrenzt trotzdem.
MAX_BODY_BYTES = 16 * 1024 * 1024


class ReceiverState:
    """Laufzeitzustand, geteilt von allen Request-Threads."""

    def __init__(self, store: BarStore, known_timeframes: set[str],
                 symbol_map: dict[str, str]) -> None:
        self.store = store
        self.known_timeframes = known_timeframes
        self.symbol_map = symbol_map
        self.started_at = datetime.now(timezone.utc)

        self._lock = threading.Lock()
        self.requests = 0
        self.accepted = 0
        self.rejected = 0
        self.reject_reasons: dict[str, int] = {}
        self.last_bar_at: datetime | None = None

    def record(self, result: IngestResult) -> None:
        with self._lock:
            self.requests += 1
            self.accepted += result.accepted
            self.rejected += result.rejected
            for reason, count in result.reasons.items():
                self.reject_reasons[reason] = self.reject_reasons.get(reason, 0) + count
            if result.accepted:
                self.last_bar_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "laeuft_seit_utc": self.started_at.isoformat(),
                "anfragen": self.requests,
                "kerzen_angenommen": self.accepted,
                "kerzen_abgelehnt": self.rejected,
                "ablehnungsgruende": dict(self.reject_reasons),
                "letzte_kerze_empfangen_utc": (
                    self.last_bar_at.isoformat() if self.last_bar_at else None
                ),
            }


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """Verarbeitet ``POST /bars`` und ``GET /status``."""

    server_version = "ClaudeChartBotBridge/1.0"
    state: ReceiverState   # wird von make_server gesetzt

    # -- Ausgabe ----------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Zugriffsprotokoll ins Projektlog statt nach stderr."""
        log.debug("%s - %s", self.address_string(), format % args)

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -- Endpunkte ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - von BaseHTTPRequestHandler vorgegeben
        if self.path.rstrip("/") in ("/status", ""):
            self._respond(200, self._status_payload())
        else:
            self._respond(404, {"fehler": f"Unbekannter Pfad {self.path!r}"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/bars":
            self._respond(404, {"fehler": f"Unbekannter Pfad {self.path!r}"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"fehler": "Content-Length unlesbar"})
            return

        if length <= 0:
            self._respond(400, {"fehler": "Leerer Koerper"})
            return
        if length > MAX_BODY_BYTES:
            self._respond(413, {"fehler": f"Koerper groesser als {MAX_BODY_BYTES} Bytes"})
            return

        try:
            raw = self.rfile.read(length)
            document = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            log_event(
                log,
                "ntbridge.bad_request",
                f"JSON nicht lesbar: {exc}",
                level=logging.WARNING,
                error=str(exc),
            )
            self._respond(400, {"fehler": f"JSON nicht lesbar: {exc}"})
            return

        bars = document.get("bars") if isinstance(document, dict) else None
        if not isinstance(bars, list):
            self._respond(400, {"fehler": "Erwartet wird {\"bars\": [...]}"})
            return

        try:
            result = self.state.store.ingest(
                bars,
                known_timeframes=self.state.known_timeframes,
                symbol_map=self.state.symbol_map,
            )
        except Exception as exc:  # noqa: BLE001 - der Empfaenger darf nie sterben
            log_event(
                log,
                "ntbridge.ingest_failed",
                f"Speichern fehlgeschlagen: {exc}",
                level=logging.ERROR,
                error=str(exc),
                exc_info=True,
            )
            self._respond(500, {"fehler": str(exc)})
            return

        self.state.record(result)

        if result.accepted:
            log_event(
                log,
                "ntbridge.bars_received",
                f"{result.accepted} Kerze(n) gespeichert"
                + (f", {result.rejected} abgelehnt" if result.rejected else ""),
                level=logging.INFO if result.rejected else logging.DEBUG,
                **result.to_dict(),
            )

        self._respond(200, result.to_dict())

    def _status_payload(self) -> dict[str, Any]:
        coverage = self.state.store.coverage()
        return {
            "status": "ok",
            "empfaenger": self.state.snapshot(),
            "datenbank": str(self.state.store.path),
            "kerzen_gesamt": self.state.store.total_bars(),
            "abdeckung": coverage,
            "hinweis": (
                "Ist 'abdeckung' leer, hat NinjaTrader noch nichts geschickt. "
                "Pruefe im NinjaScript-Output, ob die ClaudeBridge laeuft."
            ),
        }


class _ExklusiverServer(ThreadingHTTPServer):
    """HTTP-Server, der einen belegten Port NICHT uebernimmt.

    Der Standard setzt ``allow_reuse_address = 1``. Unter Linux betrifft das
    nur Sockets im Zustand TIME_WAIT und ist dort erwuenscht. Unter **Windows**
    hat SO_REUSEADDR eine andere Bedeutung: es erlaubt, sich auf einen Port zu
    binden, den ein anderer Prozess bereits **aktiv** bedient.

    Praktische Folge, die dieses Projekt bereits getroffen hat: Ein zweiter
    ``python -m ntbridge`` startete ohne Fehler, meldete "Empfaenger laeuft"
    und bekam nie eine Kerze - der erste Prozess bediente weiter. Wer nach
    einer Konfigurationsaenderung "neu startet", arbeitet dann stillschweigend
    mit den alten Einstellungen weiter.

    Deshalb unter Windows aus. Der Bind schlaegt dann mit ``OSError`` fehl,
    was der Aufrufer sauber melden kann.
    """

    allow_reuse_address = not sys.platform.startswith("win")


def make_server(
    store: BarStore,
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    known_timeframes: set[str] | None = None,
    symbol_map: dict[str, str] | None = None,
) -> tuple[ThreadingHTTPServer, ReceiverState]:
    """Baut den Server, ohne ihn zu starten (praktisch fuer Tests)."""
    from mcp_server.bars import ALL_TIMEFRAMES

    state = ReceiverState(
        store=store,
        known_timeframes=known_timeframes or set(ALL_TIMEFRAMES),
        symbol_map=symbol_map or {},
    )

    handler = type("BoundHandler", (BridgeRequestHandler,), {"state": state})
    server = _ExklusiverServer((host, port), handler)
    server.daemon_threads = True
    return server, state


def laeuft_bereits(host: str, port: int, *, timeout: float = 1.5) -> dict[str, Any] | None:
    """Fragt, ob auf ``host:port`` bereits ein Empfaenger antwortet.

    Rueckgabe ist dessen ``/status``-Antwort oder ``None``.

    Warum zusaetzlich zur Bind-Sperre: Der Bind-Fehler sagt nur "Port belegt".
    Diese Probe kann sagen, **seit wann** der andere laeuft und wie viele
    Kerzen er hat - damit ist sofort klar, ob man den falschen Prozess vor
    sich hat oder den richtigen bereits laufen laesst.
    """
    import json
    import urllib.error
    import urllib.request

    ziel = f"http://{host}:{port}/status"
    try:
        with urllib.request.urlopen(ziel, timeout=timeout) as antwort:
            geladen = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        # Nicht erreichbar, kein HTTP, kaputtes JSON: dann laeuft dort
        # jedenfalls kein funktionierender Empfaenger.
        return None
    return geladen if isinstance(geladen, dict) else None


__all__ = ["MAX_BODY_BYTES", "BridgeRequestHandler", "ReceiverState", "make_server"]
