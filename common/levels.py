"""Handelsrelevante Preisniveaus mit Abstandsangabe.

Jeder Level traegt seinen Abstand zum aktuellen Kurs **in Punkten, in Ticks
und in ATR-Vielfachen**. Punkte allein sind zwischen Instrumenten nicht
vergleichbar: 20 Punkte sind bei MNQ ein Nichts und bei MGC eine Weltreise.
Erst das ATR-Vielfache macht die Aussage "nah" oder "weit" ueberhaupt
uebertragbar.

Alle Fenster werden ueber die Boersenzeit des Instruments bestimmt, damit
die Sommerzeit automatisch mitlaeuft (siehe :mod:`common.sessions`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.instruments import Instrument
from common.sessions import GLOBEX_OPEN_CT, session_dates, SESSION_WINDOWS, SessionWindow
from common.config import SessionConfig

# Opening-Range-Fenster in Minuten
OPENING_RANGE_MINUTES = (5, 15, 30)
# Initial Balance = erste Stunde der regulaeren Handelszeit
INITIAL_BALANCE_MINUTES = 60

# Begruendungstext fuer Felder, die ohne Bar-Cache nicht berechenbar sind.
NEEDS_CACHE = "benoetigt Bar-Cache, noch nicht verfuegbar"


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True


def _clean(value: Any) -> float | None:
    if value is None or _is_nan(value):
        return None
    return float(value)


@dataclass(frozen=True)
class Level:
    """Ein Preisniveau samt Abstand zum aktuellen Kurs.

    ``distance_points`` ist **vorzeichenbehaftet**: positiv bedeutet, der
    Level liegt ueber dem aktuellen Kurs. Damit ist ohne Zusatzfeld
    erkennbar, ob es sich gerade um Widerstand oder Unterstuetzung handelt.
    """

    name: str
    price: float
    distance_points: float
    distance_ticks: float
    distance_atr: float | None
    side: str                     # "above" | "below" | "at"
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "price": round(self.price, 4),
            "distance_points": round(self.distance_points, 4),
            "distance_ticks": round(self.distance_ticks, 1),
            "distance_atr": round(self.distance_atr, 2) if self.distance_atr is not None else None,
            "side": self.side,
            "note": self.note,
        }


def make_level(
    name: str,
    price: float | None,
    current_price: float,
    instrument: Instrument,
    atr_value: float | None,
    *,
    note: str | None = None,
) -> Level | None:
    """Baut einen :class:`Level` - oder ``None``, wenn der Preis fehlt."""
    cleaned = _clean(price)
    if cleaned is None:
        return None

    distance = cleaned - current_price
    if abs(distance) < instrument.tick_size / 2:
        side = "at"
    else:
        side = "above" if distance > 0 else "below"

    return Level(
        name=name,
        price=cleaned,
        distance_points=distance,
        distance_ticks=distance / instrument.tick_size,
        distance_atr=(distance / atr_value) if atr_value else None,
        side=side,
        note=note,
    )


# ---------------------------------------------------------------------------
# Fenster-Masken
# ---------------------------------------------------------------------------

def _local_times(index: pd.DatetimeIndex, instrument: Instrument) -> pd.Series:
    """Ortszeit (Boersenzeit) als ``datetime.time`` je Bar."""
    local = index.tz_convert(ZoneInfo(instrument.timezone))
    return pd.Series([stamp.time() for stamp in local], index=index)


def _globex_open_local(instrument: Instrument) -> dtime:
    """Globex-Eroeffnung in der Boersenzeit des Instruments.

    17:00 CT entspricht 18:00 ET. Wird ueber einen konkreten Zeitpunkt
    konvertiert, damit die Sommerzeit korrekt einfliesst.
    """
    reference = datetime(2026, 6, 1, GLOBEX_OPEN_CT.hour, GLOBEX_OPEN_CT.minute,
                         tzinfo=ZoneInfo("America/Chicago"))
    return reference.astimezone(ZoneInfo(instrument.timezone)).time()


def rth_mask(df: pd.DataFrame, instrument: Instrument) -> pd.Series:
    """Bars innerhalb der regulaeren Handelszeit."""
    times = _local_times(df.index, instrument)
    return (times >= instrument.rth_start) & (times < instrument.rth_end)


def overnight_mask(df: pd.DataFrame, instrument: Instrument) -> pd.Series:
    """Bars der Globex-Nachtsitzung: Eroeffnung bis RTH-Start."""
    times = _local_times(df.index, instrument)
    globex_open = _globex_open_local(instrument)
    # Ueber Mitternacht: entweder nach der Globex-Eroeffnung am Vorabend
    # oder vor dem RTH-Start am Handelstag.
    return (times >= globex_open) | (times < instrument.rth_start)


def session_mask(df: pd.DataFrame, fenster: "SessionWindow") -> pd.Series:
    """Bars innerhalb eines benannten Handelsfensters (Asia/London/New York).

    Ueber ``SessionWindow.contains`` und damit ueber echte
    Zeitzonenkonvertierung. Eine hart verdrahtete ET-Spanne ("London =
    03:00-11:30 ET") liegt in den Wochen daneben, in denen Europa und die USA
    ihre Zeitumstellung an verschiedenen Terminen haben - genau davor warnt
    der Kommentar ueber ``SESSION_WINDOWS`` in ``common/sessions.py``.
    """
    if df.empty:
        return pd.Series([], dtype=bool, index=df.index)
    return pd.Series(
        [fenster.contains(stamp) for stamp in df.index], index=df.index
    )


def session_extremes(
    df: pd.DataFrame, *, namen: tuple[str, ...] = ("asia", "london")
) -> dict[str, float]:
    """Hoch und Tief je Handelsfenster - fuer die Bars, die uebergeben werden.

    Der Aufrufer schneidet auf den Handelstag zu; hier wird bewusst NICHT
    noch einmal nach Sessions gruppiert. Zwei Stellen, die entscheiden,
    welcher Tag gemeint ist, waeren zwei Stellen, an denen die 18:00-ET-Regel
    auseinander laufen kann.

    Fehlt ein Fenster im uebergebenen Ausschnitt, taucht es im Ergebnis gar
    nicht auf - eine 0 oder ein NaN saehe aus wie ein gemessener Kurs.
    """
    ergebnis: dict[str, float] = {}
    if df.empty:
        return ergebnis

    for fenster in SESSION_WINDOWS:
        if fenster.name not in namen:
            continue
        treffer = df[session_mask(df, fenster).values]
        if treffer.empty:
            continue
        ergebnis[f"{fenster.name}_high"] = float(treffer["high"].max())
        ergebnis[f"{fenster.name}_low"] = float(treffer["low"].min())
    return ergebnis


def initial_balance_per_session(
    df: pd.DataFrame,
    instrument: Instrument,
    session_cfg: SessionConfig,
) -> pd.DataFrame:
    """Initial-Balance-Hoch/-Tief je Handelstag, auf jede Kerze abgebildet.

    ``compute_levels`` liefert die Initial Balance nur fuer den zuletzt
    laufenden Handelstag. Die Ideen-Protokollierung braucht sie ueber eine
    laengere Historie, also je Session.

    Bewusst KEINE zweite Definition der Initial Balance: dieselbe Konstante
    ``INITIAL_BALANCE_MINUTES``, dieselbe ``rth_mask``, derselbe
    Minutenzaehler wie in ``compute_levels``.

    LOOKAHEAD-SCHUTZ - der eigentliche Punkt dieser Funktion:
    Die Werte stehen einer Kerze erst zur Verfuegung, wenn das IB-Fenster
    **abgelaufen** ist. Waehrend der ersten 60 RTH-Minuten bleiben sie NaN.
    Wuerde man den Tageswert einfach auf alle Kerzen des Tages verteilen,
    kennte eine Kerze um 09:45 bereits das Hoch, das erst um 10:30 feststeht -
    und jede darauf gebaute Auswertung waere wertlos.

    Rueckgabe: Spalten ``ib_high``, ``ib_low`` (float, NaN bis das Fenster
    abgelaufen ist).
    """
    leer = pd.DataFrame(
        {"ib_high": np.nan, "ib_low": np.nan},
        index=df.index,
        dtype="float64",
    )
    if df.empty:
        return leer

    tage = session_dates(df.index, session_cfg)
    innerhalb_rth = rth_mask(df, instrument)
    verstrichen = _minutes_from_rth_open(df, instrument)

    im_ib_fenster = innerhalb_rth & (verstrichen >= 0) & (verstrichen < INITIAL_BALANCE_MINUTES)
    if not bool(im_ib_fenster.any()):
        return leer

    fenster = df[im_ib_fenster.values]
    tage_im_fenster = tage[im_ib_fenster.values]

    hoch_je_tag = fenster["high"].groupby(tage_im_fenster.values).max()
    tief_je_tag = fenster["low"].groupby(tage_im_fenster.values).min()

    ergebnis = leer.copy()
    ergebnis["ib_high"] = tage.map(hoch_je_tag).astype("float64").values
    ergebnis["ib_low"] = tage.map(tief_je_tag).astype("float64").values

    # Erst nach Ablauf des Fensters sichtbar machen.
    noch_nicht_bekannt = (verstrichen < INITIAL_BALANCE_MINUTES).values
    ergebnis.loc[noch_nicht_bekannt, ["ib_high", "ib_low"]] = np.nan

    return ergebnis


def _minutes_from_rth_open(df: pd.DataFrame, instrument: Instrument) -> pd.Series:
    """Minuten seit RTH-Eroeffnung (negativ vor der Eroeffnung)."""
    local = df.index.tz_convert(ZoneInfo(instrument.timezone))
    open_minutes = instrument.rth_start.hour * 60 + instrument.rth_start.minute
    bar_minutes = pd.Series(local.hour * 60 + local.minute, index=df.index)
    return bar_minutes - open_minutes


# ---------------------------------------------------------------------------
# Berechnung
# ---------------------------------------------------------------------------

@dataclass
class LevelSet:
    """Alle Niveaus eines Handelstags plus Metadaten."""

    trading_day: date | None
    current_price: float
    atr_value: float | None
    levels: list[Level] = field(default_factory=list)
    gap: dict[str, Any] = field(default_factory=dict)
    initial_balance_complete: bool = False
    opening_ranges: dict[str, dict[str, Any]] = field(default_factory=dict)
    unavailable: dict[str, str] = field(default_factory=dict)

    def by_name(self, name: str) -> Level | None:
        for level in self.levels:
            if level.name == name:
                return level
        return None

    def price_of(self, name: str) -> float | None:
        level = self.by_name(name)
        return level.price if level else None

    def nearest(self, count: int = 5) -> list[Level]:
        return sorted(self.levels, key=lambda level: abs(level.distance_points))[:count]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trading_day": self.trading_day.isoformat() if self.trading_day else None,
            "current_price": round(self.current_price, 4),
            "atr_reference": round(self.atr_value, 4) if self.atr_value else None,
            "levels": [level.to_dict() for level in self.levels],
            "nearest_levels": [level.name for level in self.nearest()],
            "gap": self.gap,
            "initial_balance_complete": self.initial_balance_complete,
            "opening_ranges": self.opening_ranges,
            "unavailable": self.unavailable,
        }


def compute_levels(
    df: pd.DataFrame,
    instrument: Instrument,
    *,
    atr_value: float | None = None,
    session_cfg: SessionConfig | None = None,
) -> LevelSet:
    """Berechnet alle Tagesniveaus aus einem OHLCV-DataFrame.

    ``df`` muss den UTC-Index und die OHLCV-Spalten des Projektschemas
    tragen; Indikatorspalten duerfen zusaetzlich vorhanden sein.
    """
    if df.empty:
        raise ValueError("compute_levels benoetigt mindestens eine Kerze.")

    session_cfg = session_cfg or SessionConfig(timezone=instrument.timezone)
    sessions = session_dates(df.index, session_cfg)
    current_day = sessions.iloc[-1]
    current_price = float(df["close"].iloc[-1])

    if atr_value is None and "atr" in df.columns:
        atr_value = _clean(df["atr"].iloc[-1])

    today = df[sessions.values == current_day]
    earlier_days = sorted({day for day in sessions.values if day < current_day})
    previous_day_bars = (
        df[sessions.values == earlier_days[-1]] if earlier_days else df.iloc[0:0]
    )

    levels: list[Level] = []
    unavailable: dict[str, str] = {}

    def add(name: str, price: float | None, note: str | None = None) -> None:
        level = make_level(name, price, current_price, instrument, atr_value, note=note)
        if level is not None:
            levels.append(level)

    # --- Tagesspanne bisher ---------------------------------------------
    add("day_high", today["high"].max() if not today.empty else None)
    add("day_low", today["low"].min() if not today.empty else None)

    # --- Vortag (PDH/PDL/PDC) -------------------------------------------
    if previous_day_bars.empty:
        unavailable["previous_day"] = (
            "Vortagessitzung liegt nicht im geladenen Fenster"
        )
    else:
        add("prev_day_high", previous_day_bars["high"].max())
        add("prev_day_low", previous_day_bars["low"].min())
        add("prev_day_close", previous_day_bars["close"].iloc[-1])

    # --- Handelsfenster Asia / London -----------------------------------
    #
    # Ausdruecklich gewuenscht: "da war zum Beispiel das London High, da war
    # das Asia High" (30.08.2026). Beide liegen im selben CME-Handelstag wie
    # die laufende US-Sitzung, weil der Tag um 18:00 ET beginnt.
    if today.empty:
        unavailable["session_extremes"] = "keine Bars des laufenden Handelstages"
    else:
        extremwerte = session_extremes(today)
        if not extremwerte:
            unavailable["session_extremes"] = (
                "weder Asia- noch London-Fenster im geladenen Ausschnitt"
            )
        for name, preis in extremwerte.items():
            add(name, preis, note="Hoch/Tief des Handelsfensters am laufenden Tag")

    # --- Overnight / Globex ---------------------------------------------
    overnight = today[overnight_mask(today, instrument).values] if not today.empty else today
    if overnight.empty:
        unavailable["overnight"] = "keine Bars der Nachtsitzung im Fenster"
    else:
        add("overnight_high", overnight["high"].max(), note="Globex vor RTH-Eroeffnung")
        add("overnight_low", overnight["low"].min(), note="Globex vor RTH-Eroeffnung")

    # --- RTH-abhaengige Niveaus -----------------------------------------
    rth = today[rth_mask(today, instrument).values] if not today.empty else today
    initial_balance_complete = False

    if rth.empty:
        unavailable["initial_balance"] = "RTH hat noch nicht begonnen"
        unavailable["opening_range"] = "RTH hat noch nicht begonnen"
        opening_ranges: dict[str, dict[str, Any]] = {}
        gap_info = _gap_info(None, previous_day_bars, current_price, instrument, atr_value)
    else:
        elapsed = _minutes_from_rth_open(rth, instrument)

        initial_balance = rth[(elapsed >= 0) & (elapsed < INITIAL_BALANCE_MINUTES)]
        if not initial_balance.empty:
            add("initial_balance_high", initial_balance["high"].max(),
                note=f"erste {INITIAL_BALANCE_MINUTES} Min RTH")
            add("initial_balance_low", initial_balance["low"].min(),
                note=f"erste {INITIAL_BALANCE_MINUTES} Min RTH")
            initial_balance_complete = bool(elapsed.max() >= INITIAL_BALANCE_MINUTES)

        opening_ranges = {}
        for minutes in OPENING_RANGE_MINUTES:
            window = rth[(elapsed >= 0) & (elapsed < minutes)]
            if window.empty:
                continue
            high = float(window["high"].max())
            low = float(window["low"].min())
            opening_ranges[f"{minutes}m"] = {
                "high": round(high, 4),
                "low": round(low, 4),
                "range_points": round(high - low, 4),
                "range_atr": round((high - low) / atr_value, 2) if atr_value else None,
                "complete": bool(elapsed.max() >= minutes),
            }
            add(f"opening_range_{minutes}m_high", high, note=f"erste {minutes} Min RTH")
            add(f"opening_range_{minutes}m_low", low, note=f"erste {minutes} Min RTH")

        cash_open = float(rth["open"].iloc[0])
        add("cash_open", cash_open, note="erster RTH-Kurs")
        gap_info = _gap_info(rth, previous_day_bars, current_price, instrument, atr_value)

    return LevelSet(
        trading_day=current_day if isinstance(current_day, date) else None,
        current_price=current_price,
        atr_value=atr_value,
        levels=levels,
        gap=gap_info,
        initial_balance_complete=initial_balance_complete,
        opening_ranges=opening_ranges,
        unavailable=unavailable,
    )


def _gap_info(
    rth: pd.DataFrame | None,
    previous_day_bars: pd.DataFrame,
    current_price: float,
    instrument: Instrument,
    atr_value: float | None,
) -> dict[str, Any]:
    """Gap zwischen Cash-Eroeffnung und Vortagesschluss, offen oder geschlossen."""
    if rth is None or rth.empty or previous_day_bars.empty:
        return {
            "available": False,
            "reason": "Cash-Eroeffnung oder Vortagesschluss nicht im Fenster",
        }

    cash_open = float(rth["open"].iloc[0])
    prev_close = float(previous_day_bars["close"].iloc[-1])
    gap_points = cash_open - prev_close

    # Geschlossen, sobald der Kurs den Vortagesschluss nach der Eroeffnung
    # wieder beruehrt hat.
    if gap_points > 0:
        filled = bool((rth["low"] <= prev_close).any())
    elif gap_points < 0:
        filled = bool((rth["high"] >= prev_close).any())
    else:
        filled = True

    return {
        "available": True,
        "cash_open": round(cash_open, 4),
        "prev_day_close": round(prev_close, 4),
        "gap_points": round(gap_points, 4),
        "gap_ticks": round(gap_points / instrument.tick_size, 1),
        "gap_atr": round(gap_points / atr_value, 2) if atr_value else None,
        "direction": "up" if gap_points > 0 else ("down" if gap_points < 0 else "none"),
        "filled": filled,
        "distance_to_fill_points": (
            round(prev_close - current_price, 4) if not filled else 0.0
        ),
    }


# ---------------------------------------------------------------------------
# Vom Bar-Cache abhaengige Groessen - bewusst als null mit Begruendung
# ---------------------------------------------------------------------------

# Wie viele abgeschlossene Handelssessions ein Feld braucht, um belastbar
# zu sein. Darunter wird KEIN Naeherungswert ausgegeben, sondern null mit
# Angabe, was noch fehlt - ein aus zwei Tagen geschaetztes 20-Tage-Perzentil
# saehe aus wie eine Messung und waere keine.
SESSIONS_REQUIRED = {
    "week_high": 5,
    "week_low": 5,
    "volume_profile": 2,        # heute + Vortag
    "relative_volume": 10,
    "atr_percentile": 20,
}


def _session_series(df: pd.DataFrame, session_cfg: SessionConfig) -> pd.Series:
    return session_dates(df.index, session_cfg)


def _completed_sessions(sessions: pd.Series) -> list[date]:
    """Alle Sessions ausser der laufenden (die ist noch unvollstaendig)."""
    unique = sorted(set(sessions.values))
    return unique[:-1] if len(unique) > 1 else []


def _unavailable(bars: int, sessions: int, required: int, unit: str) -> dict[str, Any]:
    return {
        "value": None,
        "unit": unit,
        "available": False,
        "sessions_available": sessions,
        "sessions_required": required,
        "bars_available": bars,
        "reason": (
            f"Braucht {required} abgeschlossene Handelssessions, "
            f"vorhanden sind {sessions}. Fuellt sich im laufenden Betrieb."
        ),
    }


def volume_profile(
    df: pd.DataFrame, instrument: Instrument, *, value_area: float = 0.70
) -> dict[str, Any] | None:
    """POC, VAH und VAL als Naeherung aus OHLCV-Bars.

    Das Volumen einer Kerze wird gleichmaessig ueber ihre Spanne verteilt.
    Das ist **keine** echte Volumenverteilung - dafuer braeuchte es Tickdaten
    oder volumetrische Bars. Die Naeherung liegt in ruhigen Phasen nah dran
    und weicht bei langen Kerzen ab; das Feld ist entsprechend markiert.
    """
    if df.empty or float(df["volume"].sum()) <= 0:
        return None

    bin_size = instrument.tick_size * 4       # Tick-Raster waere unnoetig fein
    low = float(df["low"].min())
    high = float(df["high"].max())
    if high <= low:
        return None

    bin_count = max(2, min(500, int(round((high - low) / bin_size)) + 1))
    edges = np.linspace(low, high, bin_count + 1)
    centres = (edges[:-1] + edges[1:]) / 2.0
    volume_at_price = np.zeros(bin_count, dtype=float)

    for bar_low, bar_high, bar_volume in zip(
        df["low"].to_numpy(float), df["high"].to_numpy(float), df["volume"].to_numpy(float)
    ):
        if bar_volume <= 0:
            continue
        first = int(np.searchsorted(edges, bar_low, side="right") - 1)
        last = int(np.searchsorted(edges, bar_high, side="left"))
        first = max(0, min(first, bin_count - 1))
        last = max(first + 1, min(last, bin_count))
        volume_at_price[first:last] += bar_volume / (last - first)

    total = float(volume_at_price.sum())
    if total <= 0:
        return None

    poc_index = int(np.argmax(volume_at_price))

    # Value Area: vom POC aus nach beiden Seiten wachsen, immer zur
    # volumenstaerkeren Seite, bis der Zielanteil erreicht ist.
    lower = upper = poc_index
    covered = volume_at_price[poc_index]
    while covered < value_area * total and (lower > 0 or upper < bin_count - 1):
        take_below = volume_at_price[lower - 1] if lower > 0 else -1.0
        take_above = volume_at_price[upper + 1] if upper < bin_count - 1 else -1.0
        if take_above >= take_below:
            upper += 1
            covered += take_above
        else:
            lower -= 1
            covered += take_below

    return {
        "poc": round(float(centres[poc_index]), 4),
        "vah": round(float(centres[upper]), 4),
        "val": round(float(centres[lower]), 4),
        "bins": bin_count,
        "abgedeckter_volumenanteil": round(covered / total, 3),
    }


def history_dependent_metrics(
    df: pd.DataFrame,
    instrument: Instrument,
    session_cfg: SessionConfig,
    *,
    atr_series: pd.Series | None = None,
    daily_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Kennzahlen, die mehrere Handelssessions Historie brauchen.

    Jedes Feld weist aus, wie viele Sessions es braucht und wie viele
    vorliegen. Solange es nicht reicht, kommt ``null`` mit Begruendung -
    niemals ein aus zu wenig Daten gerechneter Wert.

    Diese Felder fuellen sich im laufenden Betrieb von selbst, weil der
    NinjaTrader-Speicher mit jeder Session waechst.

    ``daily_frame`` ist optional: Wochenhoch und -tief brauchen keine
    Intraday-Aufloesung, wohl aber fuenf Handelstage. Aus einem 1m-Frame
    mit zwei Sessions waeren sie unnoetig lange nicht verfuegbar, obwohl
    die Tageskerzen laengst vorliegen.
    """
    result: dict[str, Any] = {}
    bars = len(df)

    if df.empty:
        for name, required in SESSIONS_REQUIRED.items():
            result[name] = _unavailable(0, 0, required, "n/a")
        return result

    sessions = _session_series(df, session_cfg)
    completed = _completed_sessions(sessions)
    session_count = len(completed)
    current_session = sessions.iloc[-1]

    # --- Wochenhoch / -tief ---------------------------------------------
    # Bevorzugt aus Tageskerzen: die decken fuenf Handelstage schon nach
    # kurzer Laufzeit ab, waehrend ein 1m-Frame dafuer Tage braeuchte.
    week_source = df
    week_sessions = sessions
    week_completed = completed
    week_bars = bars
    if daily_frame is not None and not daily_frame.empty:
        week_source = daily_frame
        week_sessions = _session_series(daily_frame, session_cfg)
        week_completed = _completed_sessions(week_sessions)
        week_bars = len(daily_frame)

    week_count = len(week_completed)
    week_current = week_sessions.iloc[-1]

    for name, column, aggregate in (("week_high", "high", "max"), ("week_low", "low", "min")):
        required = SESSIONS_REQUIRED[name]
        if week_count < required:
            result[name] = _unavailable(week_bars, week_count, required, "preis")
            continue
        recent = week_completed[-required:] + [week_current]
        window = week_source[week_sessions.isin(recent).values]
        value = float(getattr(window[column], aggregate)())
        result[name] = {
            "value": round(value, 4),
            "unit": "preis",
            "available": True,
            "sessions_available": week_count,
            "sessions_required": required,
            "bars_available": week_bars,
            "quelle": "tageskerzen" if week_source is daily_frame else "intraday",
        }

    # --- Volume Profile --------------------------------------------------
    required = SESSIONS_REQUIRED["volume_profile"]
    if session_count < required - 1:
        result["volume_profile"] = _unavailable(bars, session_count, required, "preis")
    else:
        today = df[(sessions == current_session).values]
        previous = (
            df[(sessions == completed[-1]).values] if completed else df.iloc[0:0]
        )
        result["volume_profile"] = {
            "heute": volume_profile(today, instrument),
            "vortag": volume_profile(previous, instrument) if not previous.empty else None,
            "unit": "preis",
            "available": True,
            "sessions_available": session_count,
            "sessions_required": required,
            "naeherung": True,
            "hinweis": (
                "Naeherung: das Volumen jeder Kerze wird gleichmaessig ueber ihre "
                "Spanne verteilt. Echtes Volumen-at-Price braucht Tickdaten."
            ),
        }

    # --- Relatives Volumen ----------------------------------------------
    required = SESSIONS_REQUIRED["relative_volume"]
    if session_count < required:
        result["relative_volume"] = _unavailable(bars, session_count, required, "verhaeltnis")
    else:
        result["relative_volume"] = _relative_volume(
            df, sessions, completed[-required:], current_session, instrument, required, bars
        )

    # --- ATR-Perzentil ---------------------------------------------------
    required = SESSIONS_REQUIRED["atr_percentile"]
    if atr_series is None or session_count < required:
        result["atr_percentile"] = _unavailable(bars, session_count, required, "perzentil")
    else:
        result["atr_percentile"] = _atr_percentile(
            df, atr_series, sessions, completed[-required:], required, bars, instrument
        )

    return result


def _minutes_of_day(index: pd.DatetimeIndex, instrument: Instrument) -> np.ndarray:
    local = index.tz_convert(ZoneInfo(instrument.timezone))
    return np.asarray(local.hour * 60 + local.minute)


def _relative_volume(
    df: pd.DataFrame,
    sessions: pd.Series,
    reference_sessions: list[date],
    current_session: date,
    instrument: Instrument,
    required: int,
    bars: int,
) -> dict[str, Any]:
    """Kumuliertes Session-Volumen gegen den Durchschnitt zur selben Uhrzeit.

    Ein Vergleich mit dem Tagesdurchschnitt waere irrefuehrend: um 10:00 ET
    ist naturgemaess erst ein Bruchteil des Tagesvolumens gehandelt. Nur der
    Vergleich mit derselben Uhrzeit frueherer Sessions sagt etwas aus.
    """
    minutes = _minutes_of_day(df.index, instrument)
    session_values = sessions.values
    cutoff = int(minutes[-1])

    current_mask = (session_values == current_session) & (minutes <= cutoff)
    current_volume = float(df.loc[current_mask, "volume"].sum())

    historical: list[float] = []
    for session in reference_sessions:
        mask = (session_values == session) & (minutes <= cutoff)
        if mask.any():
            historical.append(float(df.loc[mask, "volume"].sum()))

    if not historical or current_volume <= 0:
        return _unavailable(bars, len(reference_sessions), required, "verhaeltnis")

    average = float(np.mean(historical))
    if average <= 0:
        return _unavailable(bars, len(reference_sessions), required, "verhaeltnis")

    return {
        "value": round(current_volume / average, 3),
        "unit": "verhaeltnis",
        "available": True,
        "sessions_available": len(historical),
        "sessions_required": required,
        "bars_available": bars,
        "volumen_bisher": round(current_volume, 0),
        "durchschnitt_zur_selben_uhrzeit": round(average, 0),
        "hinweis": "1.0 = normales Volumen zur selben Tageszeit.",
    }


def _atr_percentile(
    df: pd.DataFrame,
    atr_series: pd.Series,
    sessions: pd.Series,
    reference_sessions: list[date],
    required: int,
    bars: int,
    instrument: Instrument,
) -> dict[str, Any]:
    """Perzentilrang der aktuellen ATR gegenueber derselben Uhrzeit frueherer Sessions.

    Die Uhrzeit wird in BOERSENZEIT bestimmt, nicht in UTC. Ueber eine
    Zeitumstellung hinweg waeren die Vergleichsfenster sonst um eine Stunde
    gegeneinander verschoben - genau der DST-Fehler, den wir schon einmal
    hatten.
    """
    current_atr = _clean(atr_series.iloc[-1])
    if current_atr is None:
        return _unavailable(bars, len(reference_sessions), required, "perzentil")

    session_values = sessions.values
    minutes = _minutes_of_day(df.index, instrument)
    target_minute = int(minutes[-1])

    # Fenster von +/- 15 Minuten um die aktuelle Uhrzeit, damit auch bei
    # groeberen Timeframes genug Vergleichswerte zusammenkommen.
    comparable: list[float] = []
    for session in reference_sessions:
        mask = (session_values == session) & (np.abs(minutes - target_minute) <= 15)
        values = atr_series[mask].dropna()
        if not values.empty:
            comparable.append(float(values.mean()))

    if len(comparable) < 3:
        return _unavailable(bars, len(comparable), required, "perzentil")

    below = sum(1 for value in comparable if value < current_atr)
    percentile = 100.0 * below / len(comparable)

    return {
        "value": round(percentile, 1),
        "unit": "perzentil",
        "available": True,
        "sessions_available": len(comparable),
        "sessions_required": required,
        "bars_available": bars,
        "atr_aktuell": round(current_atr, 4),
        "atr_median_vergleich": round(float(np.median(comparable)), 4),
        "hinweis": (
            "Perzentilrang der aktuellen ATR gegenueber derselben Uhrzeit "
            "(+/- 15 Min) frueherer Sessions. 50 = normal, 90 = ungewoehnlich volatil."
        ),
    }


__all__ = [
    "INITIAL_BALANCE_MINUTES",
    "NEEDS_CACHE",
    "OPENING_RANGE_MINUTES",
    "SESSIONS_REQUIRED",
    "Level",
    "LevelSet",
    "compute_levels",
    "history_dependent_metrics",
    "initial_balance_per_session",
    "make_level",
    "overnight_mask",
    "rth_mask",
    "volume_profile",
]
