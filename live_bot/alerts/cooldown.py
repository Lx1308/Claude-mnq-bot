"""Rate-Limiting fuer Alarme.

Zwei Bremsen:

1. **Cooldown pro Bedingungstyp** - dieselbe Bedingung loest fruehestens
   nach X Minuten erneut aus. X ist je Bedingung konfigurierbar
   (``alerts.conditions.<name>.cooldown_minutes``), sonst gilt
   ``alerts.default_cooldown_minutes``.

2. **Obergrenze pro Handelstag** - schuetzt gegen Alarmfluten und damit
   auch gegen unerwartete Claude-API-Kosten. Der Zaehler wird zu jedem
   Sessionwechsel zurueckgesetzt.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from common.config import AlertConfig
from common.logging_setup import log_event

log = logging.getLogger(__name__)


class CooldownTracker:
    def __init__(self, config: AlertConfig) -> None:
        self._config = config
        self._last_fired: dict[str, datetime] = {}
        self._session_day: date | None = None
        self._session_count = 0

    # -- Abfrage -----------------------------------------------------------

    def remaining_seconds(self, condition: str, now: datetime) -> float:
        """Wie lange die Bedingung noch gesperrt ist (0.0 = frei)."""
        last = self._last_fired.get(condition)
        if last is None:
            return 0.0
        cooldown = timedelta(minutes=self._config.cooldown_for(condition))
        remaining = (last + cooldown - now).total_seconds()
        return max(0.0, remaining)

    def session_limit_reached(self) -> bool:
        limit = self._config.max_alerts_per_session
        return limit > 0 and self._session_count >= limit

    def allows(self, condition: str, now: datetime, session_day: date | None = None) -> bool:
        """True, wenn die Bedingung jetzt ausloesen darf."""
        self._roll_session(session_day)

        if self.session_limit_reached():
            log_event(
                log,
                "alert.suppressed.session_limit",
                f"Alarm '{condition}' unterdrueckt: Tageslimit "
                f"({self._config.max_alerts_per_session}) erreicht",
                level=logging.WARNING,
                condition=condition,
                session_count=self._session_count,
            )
            return False

        remaining = self.remaining_seconds(condition, now)
        if remaining > 0:
            log_event(
                log,
                "alert.suppressed.cooldown",
                f"Alarm '{condition}' unterdrueckt: noch {remaining / 60:.1f} min Cooldown",
                level=logging.DEBUG,
                condition=condition,
                remaining_seconds=round(remaining, 1),
            )
            return False

        return True

    # -- Buchfuehrung ------------------------------------------------------

    def record(self, condition: str, now: datetime, session_day: date | None = None) -> None:
        """Vermerkt ein tatsaechlich ausgeloestes Ereignis."""
        self._roll_session(session_day)
        self._last_fired[condition] = now
        self._session_count += 1

    @property
    def session_count(self) -> int:
        return self._session_count

    def _roll_session(self, session_day: date | None) -> None:
        if session_day is None or session_day == self._session_day:
            return
        if self._session_day is not None:
            log_event(
                log,
                "alert.session_rollover",
                f"Neue Session {session_day} - Alarmzaehler zurueckgesetzt "
                f"(vorher {self._session_count})",
                previous_session=str(self._session_day),
                previous_count=self._session_count,
            )
        self._session_day = session_day
        self._session_count = 0
