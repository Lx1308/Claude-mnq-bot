"""Session-Logik fuer CME-Futures.

Der Globex-Handelstag laeuft von 18:00 ET des Vortages bis 17:00 ET.
Ein Tick um 19:30 ET am Montag gehoert damit bereits zum Handelstag
"Dienstag". Genau diese Zuordnung braucht sowohl der Session-VWAP
(setzt taeglich zurueck) als auch Vortageshoch/-tief.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pandas as pd

from common.config import SessionConfig

if TYPE_CHECKING:  # nur fuer Typannotationen - vermeidet Importzyklus
    from common.instruments import Instrument

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")


def market_timezone(cfg: SessionConfig) -> ZoneInfo:
    return ZoneInfo(cfg.timezone)


def session_date_for(timestamp: datetime, cfg: SessionConfig) -> date:
    """Handelstag, zu dem ein einzelner Zeitstempel gehoert.

    ``timestamp`` muss zeitzonenbehaftet sein (idealerweise UTC).
    """
    if timestamp.tzinfo is None:
        raise ValueError("session_date_for erwartet einen zeitzonenbehafteten Zeitstempel.")
    local = timestamp.astimezone(market_timezone(cfg))
    # Bewusst auf dem Datum rechnen, nicht auf dem Zeitstempel: eine Addition
    # von 24h waere an Zeitumstellungstagen um eine Stunde daneben.
    if local.time() >= cfg.start_time:
        return local.date() + timedelta(days=1)
    return local.date()


def session_dates(index: pd.DatetimeIndex, cfg: SessionConfig) -> pd.Series:
    """Vektorisierte Variante von :func:`session_date_for` fuer einen Index."""
    if index.tz is None:
        raise ValueError("session_dates erwartet einen zeitzonenbehafteten DatetimeIndex.")
    local = index.tz_convert(market_timezone(cfg))

    start_minutes = cfg.start_time.hour * 60 + cfg.start_time.minute
    rolls_over = (local.hour * 60 + local.minute) >= start_minutes

    # Zeitzone abstreifen und auf Mitternacht normalisieren: danach ist die
    # Addition eines Tages reine Kalenderarithmetik und damit DST-sicher.
    naive_midnight = pd.Series(local.tz_localize(None).normalize(), index=index)
    return pd.Series(
        naive_midnight.where(~rolls_over, naive_midnight + pd.Timedelta(days=1)).dt.date,
        index=index,
    )


def session_bounds(session_day: date, cfg: SessionConfig) -> tuple[datetime, datetime]:
    """(Start, Ende) einer Session als zeitzonenbehaftete UTC-Zeitstempel."""
    tz = market_timezone(cfg)
    start_local = datetime.combine(session_day - timedelta(days=1), cfg.start_time, tzinfo=tz)
    end_local = datetime.combine(session_day, cfg.end_time, tzinfo=tz)
    return (
        start_local.astimezone(ZoneInfo("UTC")),
        end_local.astimezone(ZoneInfo("UTC")),
    )


def floor_to_interval(timestamp: datetime, interval_minutes: int) -> datetime:
    """Rundet einen Zeitstempel auf den Beginn seines Kerzenintervalls ab."""
    if timestamp.tzinfo is None:
        raise ValueError("floor_to_interval erwartet einen zeitzonenbehafteten Zeitstempel.")
    total_minutes = timestamp.hour * 60 + timestamp.minute
    floored = (total_minutes // interval_minutes) * interval_minutes
    return timestamp.replace(
        hour=floored // 60, minute=floored % 60, second=0, microsecond=0
    )


# ===========================================================================
# Handelssessions (Asien / London / New York) und Globex-Rahmen
# ===========================================================================
#
# Die Fenster werden bewusst in IHRER EIGENEN Zeitzone definiert, nicht als
# fester ET-Offset. Grund: US- und UK-Sommerzeit schalten nicht am selben
# Wochenende. Zwischen dem zweiten Sonntag im Maerz und dem letzten Sonntag
# im Maerz liegt London aus US-Sicht eine Stunde anders als sonst - wer
# "London = 03:00-11:30 ET" hart verdrahtet, liegt in diesen Wochen daneben.
# Mit ZoneInfo-Konvertierung passiert das automatisch richtig.


@dataclass(frozen=True)
class SessionWindow:
    """Ein Handelsfenster in seiner Heimat-Zeitzone."""

    name: str
    timezone: str
    start: dtime
    end: dtime

    def contains(self, timestamp: datetime) -> bool:
        local = timestamp.astimezone(ZoneInfo(self.timezone)).time()
        if self.start <= self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end   # ueber Mitternacht


# Reihenfolge = Prioritaet bei Ueberlappung (spaeter schlaegt frueher).
SESSION_WINDOWS: tuple[SessionWindow, ...] = (
    SessionWindow("asia", "Asia/Tokyo", dtime(9, 0), dtime(18, 0)),
    SessionWindow("london", "Europe/London", dtime(8, 0), dtime(16, 30)),
    SessionWindow("new_york", "America/New_York", dtime(9, 30), dtime(17, 0)),
)

# CME-Globex: Sonntag 17:00 CT bis Freitag 16:00 CT, taeglich Wartungspause
# 16:00-17:00 CT.
GLOBEX_OPEN_CT = dtime(17, 0)
GLOBEX_CLOSE_CT = dtime(16, 0)


def _to_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        raise ValueError("Zeitstempel muss zeitzonenbehaftet sein.")
    return timestamp.astimezone(UTC)


def globex_state(timestamp: datetime) -> str:
    """``"open"`` | ``"maintenance"`` | ``"weekend"``."""
    local = _to_utc(timestamp).astimezone(CT)
    weekday = local.weekday()   # Montag=0 ... Sonntag=6
    clock = local.time()

    if weekday == 5:                                     # Samstag
        return "weekend"
    if weekday == 4 and clock >= GLOBEX_CLOSE_CT:        # Freitag nach 16:00 CT
        return "weekend"
    if weekday == 6 and clock < GLOBEX_OPEN_CT:          # Sonntag vor 17:00 CT
        return "weekend"
    if GLOBEX_CLOSE_CT <= clock < GLOBEX_OPEN_CT:        # taegliche Pause
        return "maintenance"
    return "open"


def active_sessions(timestamp: datetime) -> list[str]:
    """Alle gerade laufenden Sessions (koennen sich ueberlappen)."""
    moment = _to_utc(timestamp)
    if globex_state(moment) != "open":
        return []
    return [window.name for window in SESSION_WINDOWS if window.contains(moment)]


def primary_session(timestamp: datetime) -> str:
    """Die dominierende Session - bei Ueberlappung die zuletzt gestartete.

    London und New York ueberlappen sich taeglich mehrere Stunden; fuer die
    Einordnung ist dann New York die relevante.
    """
    running = active_sessions(timestamp)
    if not running:
        state = globex_state(timestamp)
        return "closed" if state == "weekend" else state
    for window in reversed(SESSION_WINDOWS):
        if window.name in running:
            return window.name
    return running[-1]


def _next_local_occurrence(
    timestamp: datetime, target: dtime, timezone: str, *, skip_weekend: bool = True
) -> datetime:
    """Naechster Zeitpunkt, an dem es in ``timezone`` ``target`` Uhr ist."""
    zone = ZoneInfo(timezone)
    local = _to_utc(timestamp).astimezone(zone)

    for offset in range(0, 8):
        candidate_date = (local + timedelta(days=offset)).date()
        candidate = datetime.combine(candidate_date, target, tzinfo=zone)
        if candidate <= local:
            continue
        if skip_weekend and candidate.weekday() >= 5:
            continue
        return candidate.astimezone(UTC)

    raise ValueError(f"Kein naechstes Vorkommen von {target} in {timezone} gefunden.")


def minutes_until_rth_open(timestamp: datetime, instrument: "Instrument") -> float:
    """Minuten bis zur naechsten RTH-Eroeffnung. 0.0, wenn RTH gerade laeuft."""
    if is_rth(timestamp, instrument):
        return 0.0
    target = _next_local_occurrence(timestamp, instrument.rth_start, instrument.timezone)
    return (target - _to_utc(timestamp)).total_seconds() / 60.0


def minutes_until_rth_close(timestamp: datetime, instrument: "Instrument") -> float | None:
    """Minuten bis zum RTH-Schluss. ``None``, wenn RTH gerade nicht laeuft."""
    if not is_rth(timestamp, instrument):
        return None
    zone = ZoneInfo(instrument.timezone)
    local = _to_utc(timestamp).astimezone(zone)
    close = datetime.combine(local.date(), instrument.rth_end, tzinfo=zone)
    return (close.astimezone(UTC) - _to_utc(timestamp)).total_seconds() / 60.0


def minutes_until_globex_close(timestamp: datetime) -> float:
    """Minuten bis zur naechsten taeglichen Globex-Pause (16:00 CT)."""
    target = _next_local_occurrence(
        timestamp, GLOBEX_CLOSE_CT, "America/Chicago", skip_weekend=False
    )
    return (target - _to_utc(timestamp)).total_seconds() / 60.0


def is_rth(timestamp: datetime, instrument: "Instrument") -> bool:
    """Laeuft gerade die regulaere Handelszeit des Instruments?"""
    if globex_state(timestamp) != "open":
        return False
    local = _to_utc(timestamp).astimezone(ZoneInfo(instrument.timezone))
    if local.weekday() >= 5:
        return False
    return instrument.rth_start <= local.time() < instrument.rth_end


def is_liquid_window(timestamp: datetime, instrument: "Instrument") -> bool:
    """Laeuft das Fenster mit belastbarer Liquiditaet?"""
    if globex_state(timestamp) != "open":
        return False
    local = _to_utc(timestamp).astimezone(ZoneInfo(instrument.timezone))
    if local.weekday() >= 5:
        return False
    return instrument.liquid_start <= local.time() < instrument.liquid_end


def is_first_hour_after_maintenance(timestamp: datetime) -> bool:
    """Erste Stunde nach der Globex-Wiedereroeffnung (17:00-18:00 CT).

    In diesem Fenster ist das Buch duenn und die ersten Kurse sind haeufig
    nicht repraesentativ - Levels aus dieser Phase taugen wenig.
    """
    if globex_state(timestamp) != "open":
        return False
    local = _to_utc(timestamp).astimezone(CT)
    return GLOBEX_OPEN_CT <= local.time() < dtime(GLOBEX_OPEN_CT.hour + 1, GLOBEX_OPEN_CT.minute)


def is_thin_window(timestamp: datetime, instrument: "Instrument") -> bool:
    """Duenne Mittagszone - Ausbrueche scheitern hier haeufiger."""
    local = _to_utc(timestamp).astimezone(ZoneInfo(instrument.timezone))
    return instrument.thin_start <= local.time() < instrument.thin_end


def format_timestamps(timestamp: datetime) -> dict[str, str]:
    """Ein Zeitpunkt in UTC, ET und CT - intern wird ausschliesslich UTC gerechnet."""
    moment = _to_utc(timestamp)
    return {
        "utc": moment.isoformat(),
        "et": moment.astimezone(ET).isoformat(),
        "ct": moment.astimezone(CT).isoformat(),
    }


def session_context(timestamp: datetime, instrument: "Instrument") -> dict[str, object]:
    """Vollstaendiger Session-Block fuer den Snapshot."""
    moment = _to_utc(timestamp)
    state = globex_state(moment)
    rth_close = minutes_until_rth_close(moment, instrument)

    return {
        "timestamp": format_timestamps(moment),
        "globex_state": state,
        "globex_frame": "So 17:00 CT bis Fr 16:00 CT, taegliche Pause 16:00-17:00 CT",
        "primary_session": primary_session(moment),
        "active_sessions": active_sessions(moment),
        "trading_day": session_date_for(
            moment, SessionConfig(timezone=instrument.timezone)
        ).isoformat(),
        "is_rth": is_rth(moment, instrument),
        "is_liquid_window": is_liquid_window(moment, instrument),
        "is_thin_midday_window": is_thin_window(moment, instrument),
        "is_first_hour_after_maintenance": is_first_hour_after_maintenance(moment),
        "minutes_to_rth_open": round(minutes_until_rth_open(moment, instrument), 1),
        "minutes_to_rth_close": round(rth_close, 1) if rth_close is not None else None,
        "minutes_to_globex_close": round(minutes_until_globex_close(moment), 1),
    }


__all__ = [
    "CT",
    "ET",
    "GLOBEX_CLOSE_CT",
    "GLOBEX_OPEN_CT",
    "SESSION_WINDOWS",
    "SessionWindow",
    "UTC",
    "active_sessions",
    "dtime",
    "floor_to_interval",
    "format_timestamps",
    "globex_state",
    "is_first_hour_after_maintenance",
    "is_liquid_window",
    "is_rth",
    "is_thin_window",
    "market_timezone",
    "minutes_until_globex_close",
    "minutes_until_rth_close",
    "minutes_until_rth_open",
    "primary_session",
    "session_bounds",
    "session_context",
    "session_date_for",
    "session_dates",
]
