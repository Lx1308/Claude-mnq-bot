"""Timeframe-Infrastruktur und Resampling-Logik fuer Multi-Timeframe-Analysen.

Unterstuetzt alle kanonischen Zeitebenen:
    "1m", "5m", "15m", "30m", "1h", "4h", "1d"

Invariante zur Kerzenbeschriftung (NinjaTrader-Konvention):
-----------------------------------------------------------
NinjaTrader beschriftet eine Kerze mit dem ENDE ihres Intervalls:
Die Ticks/Minuten von 14:00:00 bis 14:04:59 ergeben die Kerze 14:05.
Resampling muss deshalb zwingend mit ``closed="left", label="right"``
arbeiten, sonst entsteht ein Versatz, der Korrelationen zerstoert.

Session-Treue bei Tages- und 4h-Kerzen:
----------------------------------------
Eine CME-Globex-Tageskerze laeuft 18:00 ET bis 17:00 ET (23 Stunden, nicht
24*60 Minuten ab Mitternacht UTC). 4h-Kerzen werden ab der Globex-Eroeffnung
18:00 ET ausgerichtet (18:00-22:00, 22:00-02:00, 02:00-06:00, 06:00-10:00,
10:00-14:00, 14:00-17:00).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from common.config import SessionConfig
from common.indicators import validate_ohlcv
from common.sessions import market_timezone, session_dates

ET = ZoneInfo("America/New_York")

TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 23 * 60,
}

CANONICAL_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")


@dataclass(frozen=True)
class TimeframeSpec:
    """Spezifikation eines Timeframes."""

    label: str
    minutes: int
    is_intraday: bool
    is_daily: bool

    @classmethod
    def from_label(cls, label: str) -> TimeframeSpec:
        cleaned = label.strip().lower()
        if cleaned in ("1d", "d", "day", "daily"):
            return cls("1d", 23 * 60, is_intraday=False, is_daily=True)
        if cleaned.endswith("h"):
            try:
                hours = int(cleaned[:-1])
                return cls(f"{hours}h", hours * 60, is_intraday=True, is_daily=False)
            except ValueError:
                pass
        if cleaned.endswith("m"):
            try:
                mins = int(cleaned[:-1])
                if mins == 60:
                    return cls("1h", 60, is_intraday=True, is_daily=False)
                if mins == 240:
                    return cls("4h", 240, is_intraday=True, is_daily=False)
                return cls(f"{mins}m", mins, is_intraday=True, is_daily=False)
            except ValueError:
                pass
        if cleaned in TIMEFRAME_MINUTES:
            mins = TIMEFRAME_MINUTES[cleaned]
            return cls(cleaned, mins, is_intraday=(cleaned != "1d"), is_daily=(cleaned == "1d"))
        raise ValueError(f"Unbekannter Timeframe: {label!r}. Gueltig: {CANONICAL_TIMEFRAMES}")


def normalize_timeframe(tf: str) -> str:
    """Normalisiert Timeframe-Bezeichner (z.B. '240m' -> '4h', '60m' -> '1h')."""
    return TimeframeSpec.from_label(tf).label


def resample_ohlcv(
    df: pd.DataFrame,
    target_timeframe: str,
    session_cfg: SessionConfig | None = None,
) -> pd.DataFrame:
    """Aggregiert ein OHLCV-DataFrame auf einen groeberen Timeframe.

    Parameter:
        df: Datensatz mit DatetimeIndex in UTC und Spalten open, high, low, close, volume.
        target_timeframe: Ziel-Timeframe (z.B. "5m", "15m", "1h", "4h", "1d").
        session_cfg: Optionale Session-Konfiguration (Standard: 18:00 ET Rollover).

    Rueckgabe:
        Neues aggregiertes DataFrame mit identischem Spaltenschema.
    """
    validate_ohlcv(df)
    if df.empty:
        return df.copy()

    spec = TimeframeSpec.from_label(target_timeframe)
    target_tf = spec.label

    if len(df) >= 2:
        diff_seconds = (df.index[1] - df.index[0]).total_seconds()
        if abs(diff_seconds - spec.minutes * 60) < 1.0:
            return df.copy()

    cfg = session_cfg or SessionConfig()

    if spec.is_daily:
        return _resample_to_globex_daily(df, cfg)

    if target_tf == "4h":
        return _resample_to_4h(df, cfg)

    rule_str = f"{spec.minutes}min"
    resampled = df.resample(rule=rule_str, closed="left", label="right").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    for extra_col in ("bid_volume", "ask_volume"):
        if extra_col in df.columns:
            resampled[extra_col] = df[extra_col].resample(rule=rule_str, closed="left", label="right").sum()

    clean = resampled.dropna(subset=["open", "high", "low", "close"])
    return clean


def _resample_to_globex_daily(df: pd.DataFrame, cfg: SessionConfig) -> pd.DataFrame:
    """Aggregiert Kerzen nach CME-Handelstag (18:00 ET Vortag bis 17:00 ET)."""
    s_dates = session_dates(df.index, cfg)
    df_with_session = df.copy()
    df_with_session["_session_date"] = s_dates

    grouped = df_with_session.groupby("_session_date")
    tz = market_timezone(cfg)
    rows: list[dict[str, Any]] = []
    indices: list[datetime] = []

    for s_date, group in grouped:
        if group.empty:
            continue
        end_et = datetime.combine(s_date, cfg.end_time, tzinfo=tz)
        end_utc = end_et.astimezone(timezone.utc)

        row_dict = {
            "open": float(group["open"].iloc[0]),
            "high": float(group["high"].max()),
            "low": float(group["low"].min()),
            "close": float(group["close"].iloc[-1]),
            "volume": float(group["volume"].sum()),
        }
        if "bid_volume" in group.columns and "ask_volume" in group.columns:
            row_dict["bid_volume"] = float(group["bid_volume"].sum())
            row_dict["ask_volume"] = float(group["ask_volume"].sum())

        rows.append(row_dict)
        indices.append(end_utc)

    if not rows:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], tz="UTC"),
        )

    result_df = pd.DataFrame(rows, index=pd.DatetimeIndex(indices, tz="UTC"))
    return result_df.sort_index()


def _resample_to_4h(df: pd.DataFrame, cfg: SessionConfig) -> pd.DataFrame:
    """Aggregiert 4-Stunden-Kerzen ausgerichtet an der Globex-Eroeffnung 18:00 ET."""
    tz = market_timezone(cfg)
    local_index = df.index.tz_convert(tz)

    df_local = df.copy()
    df_local.index = local_index

    resampled = df_local.resample(
        rule="4h",
        offset="2h",
        closed="left",
        label="right",
    ).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    for extra_col in ("bid_volume", "ask_volume"):
        if extra_col in df.columns:
            resampled[extra_col] = df_local[extra_col].resample(
                rule="4h", offset="2h", closed="left", label="right"
            ).sum()

    clean = resampled.dropna(subset=["open", "high", "low", "close"])
    clean.index = clean.index.tz_convert(timezone.utc)
    return clean
