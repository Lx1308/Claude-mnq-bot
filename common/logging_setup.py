"""Strukturiertes Logging.

Zwei Senken parallel:
  * ``logs/bot.log``      - menschenlesbar, rotierend
  * ``logs/events.jsonl`` - eine JSON-Zeile pro Event, maschinell auswertbar

Alle Trigger, Claude-Antworten und Fehler laufen ueber ``log_event`` und
landen damit automatisch in beiden Senken.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common.config import LoggingConfig

# Feldnamen, die das logging-Modul selbst belegt - dienen zur Trennung von
# unseren eigenen Payload-Feldern.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "asctime",
    "message",
    "taskName",
}

EVENT_KEY = "event"
PAYLOAD_KEY = "payload"


class JsonLineFormatter(logging.Formatter):
    """Serialisiert jeden LogRecord als eine JSON-Zeile."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        event = getattr(record, EVENT_KEY, None)
        if event:
            entry[EVENT_KEY] = event

        payload = getattr(record, PAYLOAD_KEY, None)
        if isinstance(payload, dict) and payload:
            entry[PAYLOAD_KEY] = payload

        # Zusaetzliche ad-hoc-Felder aus extra={...}
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and key not in (EVENT_KEY, PAYLOAD_KEY)
        }
        if extras:
            entry.setdefault(PAYLOAD_KEY, {}).update(extras)

        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False, default=str)


class EventTextFormatter(logging.Formatter):
    """Textformat, das den Event-Namen mit anzeigt, falls vorhanden."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        event = getattr(record, EVENT_KEY, None)
        if event:
            base = f"{base}  [event={event}]"
        payload = getattr(record, PAYLOAD_KEY, None)
        if isinstance(payload, dict) and payload:
            base = f"{base}  {json.dumps(payload, ensure_ascii=False, default=str)}"
        return base


def setup_logging(cfg: LoggingConfig, *, logger_name: str | None = None) -> logging.Logger:
    """Konfiguriert Root-Logging und liefert den gewuenschten Logger zurueck.

    Mehrfachaufrufe sind unschaedlich - bestehende Handler werden ersetzt.
    """
    log_dir = Path(cfg.directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, cfg.level, logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    text_handler = logging.handlers.RotatingFileHandler(
        log_dir / cfg.text_file,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    text_handler.setFormatter(
        EventTextFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root.addHandler(text_handler)

    json_handler = logging.handlers.RotatingFileHandler(
        log_dir / cfg.json_file,
        maxBytes=cfg.max_bytes,
        backupCount=cfg.backup_count,
        encoding="utf-8",
    )
    json_handler.setFormatter(JsonLineFormatter())
    root.addHandler(json_handler)

    if cfg.console:
        console = logging.StreamHandler()
        console.setFormatter(
            EventTextFormatter("%(asctime)s %(levelname)-8s %(message)s")
        )
        root.addHandler(console)

    # Fremdbibliotheken nicht auf DEBUG mitlaufen lassen
    for noisy in ("httpx", "httpcore", "websockets", "anthropic", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger(logger_name or "claude_chart_bot")


def log_event(
    logger: logging.Logger,
    event: str,
    message: str,
    /,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **payload: Any,
) -> None:
    """Schreibt ein benanntes Event mit strukturiertem Payload.

    Beispiel::

        log_event(log, "alert.triggered", "Vortageshoch gekreuzt",
                  condition="prev_day_high_cross", price=21345.25)

    Die ersten drei Parameter sind bewusst positions-only (``/``): sonst
    wuerde ein Payload-Feld namens ``logger``, ``event`` oder ``message``
    mit ihnen kollidieren und zur Laufzeit einen TypeError ausloesen -
    ausgerechnet im Fehlerpfad, wo Logging am wichtigsten ist.
    """
    logger.log(
        level,
        message,
        exc_info=exc_info,
        extra={EVENT_KEY: event, PAYLOAD_KEY: payload},
    )
