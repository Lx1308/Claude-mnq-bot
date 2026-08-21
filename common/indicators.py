"""Indikator-Berechnungen - EINE Implementierung fuer Live-Bot und Backtest.

Beide Seiten rufen ``compute_indicators`` auf demselben DataFrame-Schema auf.
Damit ist ausgeschlossen, dass der Backtest andere Zahlen sieht als der
Live-Bot - der haeufigste und teuerste Fehler in solchen Projekten.

Erwartetes DataFrame-Schema
---------------------------
Index : ``pd.DatetimeIndex``, zeitzonenbehaftet (UTC), aufsteigend sortiert
Spalten: ``open``, ``high``, ``low``, ``close``, ``volume``
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from common.config import FlagConfig, IndicatorConfig, SessionConfig
from common.sessions import session_dates

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def validate_ohlcv(df: pd.DataFrame) -> None:
    missing = [column for column in OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"DataFrame fehlen die Spalten: {', '.join(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame muss einen DatetimeIndex haben.")
    if df.index.tz is None:
        raise ValueError("DatetimeIndex muss zeitzonenbehaftet sein (UTC empfohlen).")
    if not df.index.is_monotonic_increasing:
        raise ValueError("DatetimeIndex muss aufsteigend sortiert sein.")


# ---------------------------------------------------------------------------
# Basis-Indikatoren
# ---------------------------------------------------------------------------

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI nach Wilder (geglaettete Durchschnitte, nicht simple MA)."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder-Glaettung == EWM mit alpha = 1/period
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    result = 100.0 - (100.0 / (1.0 + rs))
    # avg_loss == 0 bedeutet ausschliesslich Gewinne -> RSI 100
    result = result.where(avg_loss != 0.0, 100.0)
    # avg_gain == 0 bedeutet ausschliesslich Verluste -> RSI 0
    result = result.where(avg_gain != 0.0, 0.0)
    return result.where(avg_gain.notna() & avg_loss.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    previous_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range nach Wilder."""
    return true_range(df).ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# ---------------------------------------------------------------------------
# Session-abhaengige Indikatoren
# ---------------------------------------------------------------------------

def session_vwap(df: pd.DataFrame, session_cfg: SessionConfig) -> pd.Series:
    """Session-VWAP - setzt zu jedem Sessionbeginn auf null zurueck."""
    sessions = session_dates(df.index, session_cfg)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    volume = df["volume"].fillna(0.0)

    price_volume = (typical_price * volume).groupby(sessions.values).cumsum()
    cumulative_volume = volume.groupby(sessions.values).cumsum()

    vwap = price_volume / cumulative_volume.replace(0.0, np.nan)
    # Fallback fuer volumenlose Bars (z.B. Datenluecken): typischer Preis
    return vwap.fillna(typical_price)


def previous_session_levels(
    df: pd.DataFrame, session_cfg: SessionConfig
) -> pd.DataFrame:
    """Hoch/Tief/Schluss der jeweils VORHERIGEN Session, pro Bar zugeordnet."""
    sessions = session_dates(df.index, session_cfg)
    grouped = df.groupby(sessions.values)
    per_session = pd.DataFrame(
        {
            "session_high": grouped["high"].max(),
            "session_low": grouped["low"].min(),
            "session_close": grouped["close"].last(),
        }
    ).sort_index()

    previous = per_session.shift(1)
    previous.columns = ["prev_session_high", "prev_session_low", "prev_session_close"]

    mapped = previous.reindex(sessions.values)
    mapped.index = df.index
    mapped["session_date"] = sessions.values
    return mapped


# ---------------------------------------------------------------------------
# Konsolidierungs- / Flaggen-Heuristik
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FlagColumns:
    """Namen der von :func:`flag_signals` erzeugten Spalten."""

    consolidation_high = "flag_range_high"
    consolidation_low = "flag_range_low"
    consolidation_range = "flag_range"
    impulse = "flag_impulse"
    in_consolidation = "flag_in_consolidation"
    direction = "flag_direction"       # +1 bullish, -1 bearish, 0 keine
    breakout_up = "flag_breakout_up"
    breakout_down = "flag_breakout_down"


def flag_signals(df: pd.DataFrame, atr_series: pd.Series, cfg: FlagConfig) -> pd.DataFrame:
    """Erkennt "Impuls -> enge Range -> Ausbruch".

    Die Konsolidierungs-Range wird bewusst OHNE die aktuelle Kerze gemessen
    (``shift(1)``), sonst wuerde die Ausbruchskerze ihre eigene Range setzen
    und es koennte per Konstruktion nie einen Ausbruch geben.
    """
    consolidation = cfg.consolidation_lookback
    impulse_window = cfg.impulse_lookback

    range_high = df["high"].shift(1).rolling(consolidation, min_periods=consolidation).max()
    range_low = df["low"].shift(1).rolling(consolidation, min_periods=consolidation).min()
    range_width = range_high - range_low

    # Impuls: Preisbewegung ueber die Kerzen VOR der Konsolidierung.
    impulse = df["close"].shift(consolidation) - df["close"].shift(consolidation + impulse_window)

    # Referenz-ATR: letzter bekannter Wert vor der aktuellen Kerze.
    atr_ref = atr_series.shift(1)

    impulse_up = impulse >= (cfg.impulse_min_atr * atr_ref)
    impulse_down = impulse <= (-cfg.impulse_min_atr * atr_ref)
    is_tight = range_width <= (cfg.consolidation_max_atr * atr_ref)

    buffer = cfg.breakout_buffer_atr * atr_ref
    breakout_up = impulse_up & is_tight & (df["close"] > (range_high + buffer))
    breakout_down = impulse_down & is_tight & (df["close"] < (range_low - buffer))

    direction = pd.Series(0, index=df.index, dtype="int64")
    direction = direction.mask(impulse_up.fillna(False) & is_tight.fillna(False), 1)
    direction = direction.mask(impulse_down.fillna(False) & is_tight.fillna(False), -1)

    in_consolidation = (
        (impulse_up | impulse_down).fillna(False)
        & is_tight.fillna(False)
        & ~breakout_up.fillna(False)
        & ~breakout_down.fillna(False)
    )

    columns = FlagColumns()
    return pd.DataFrame(
        {
            columns.consolidation_high: range_high,
            columns.consolidation_low: range_low,
            columns.consolidation_range: range_width,
            columns.impulse: impulse,
            columns.direction: direction,
            columns.in_consolidation: in_consolidation,
            columns.breakout_up: breakout_up.fillna(False),
            columns.breakout_down: breakout_down.fillna(False),
        },
        index=df.index,
    )


# ---------------------------------------------------------------------------
# Gesamtberechnung
# ---------------------------------------------------------------------------

def compute_indicators(
    df: pd.DataFrame,
    indicator_cfg: IndicatorConfig,
    session_cfg: SessionConfig,
) -> pd.DataFrame:
    """Haengt alle Indikatorspalten an ein OHLCV-DataFrame an.

    Rueckgabe ist eine Kopie; das Eingabe-DataFrame bleibt unveraendert.
    """
    validate_ohlcv(df)
    result = df.copy()

    result["rsi"] = rsi(result["close"], indicator_cfg.rsi_period)
    result["sma_fast"] = sma(result["close"], indicator_cfg.sma_fast)
    result["sma_slow"] = sma(result["close"], indicator_cfg.sma_slow)
    result["atr"] = atr(result, indicator_cfg.atr_period)
    result["vwap"] = session_vwap(result, session_cfg)

    levels = previous_session_levels(result, session_cfg)
    for column in levels.columns:
        result[column] = levels[column]

    flags = flag_signals(result, result["atr"], indicator_cfg.flag)
    for column in flags.columns:
        result[column] = flags[column]

    return result


# ===========================================================================
# Erweiterte Indikatoren
# ===========================================================================
#
# Bewusst NICHT Teil von compute_indicators: die Funktion laeuft bei jeder
# Backtest-Kerze und bei jedem Kerzenschluss im Live-Bot. Was hier steht,
# wird nur beim On-Demand-Snapshot gebraucht - einmal je Anfrage, nicht
# 300.000-mal je Backtest. Wer eine dieser Groessen in einer Strategie
# braucht, ruft compute_extended_indicators auf.


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponentiell gewichteter Durchschnitt (Standard-Glaettung 2/(n+1))."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD-Linie, Signallinie und Histogramm."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "macd_signal": signal_line,
            "macd_hist": macd_line - signal_line,
        },
        index=close.index,
    )


def stochastic(
    df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3
) -> pd.DataFrame:
    """Langsame Stochastik (%K geglaettet, %D als Durchschnitt von %K)."""
    lowest = df["low"].rolling(period, min_periods=period).min()
    highest = df["high"].rolling(period, min_periods=period).max()
    span = (highest - lowest).replace(0.0, np.nan)

    raw_k = 100.0 * (df["close"] - lowest) / span
    percent_k = raw_k.rolling(smooth_k, min_periods=smooth_k).mean()
    percent_d = percent_k.rolling(smooth_d, min_periods=smooth_d).mean()

    return pd.DataFrame(
        {"stoch_k": percent_k, "stoch_d": percent_d}, index=df.index
    )


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """ADX mit +DI/-DI nach Wilder.

    Der entscheidende Wert fuer Scalping: er trennt Trend von Chop. Unter
    etwa 20 laufen Ausbruchsstrategien typischerweise ins Leere, ueber 25
    funktionieren Mean-Reversion-Ansaetze schlechter.
    """
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
    )

    alpha = 1.0 / period
    smoothed_tr = true_range(df).ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    smoothed_plus = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    smoothed_minus = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    safe_tr = smoothed_tr.replace(0.0, np.nan)
    plus_di = 100.0 * smoothed_plus / safe_tr
    minus_di = 100.0 * smoothed_minus / safe_tr

    di_sum = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / di_sum
    adx_line = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    return pd.DataFrame(
        {"adx": adx_line, "plus_di": plus_di, "minus_di": minus_di}, index=df.index
    )


def bollinger(
    df: pd.DataFrame,
    period: int = 20,
    num_std: float = 2.0,
    *,
    keltner_period: int = 20,
    keltner_atr_mult: float = 1.5,
) -> pd.DataFrame:
    """Bollinger-Baender inklusive Squeeze-Erkennung nach Keltner-Vergleich.

    Squeeze-Definition: das Bollinger-Band liegt vollstaendig INNERHALB des
    Keltner-Kanals (EMA +/- ``keltner_atr_mult`` x ATR).

    Warum nicht "Bandbreite im untersten Perzentil der letzten N Kerzen":
    diese Definition ist selbstbezueglich. Haelt eine ruhige Phase laenger
    als das Lookback-Fenster an, wird sie zu ihrer eigenen Referenz und der
    Squeeze verschwindet - genau dann, wenn die Kompression am groessten
    ist. Der Keltner-Vergleich hat diesen blinden Fleck nicht, weil er die
    Streuung der Schlusskurse gegen die tatsaechliche Handelsspanne stellt.
    """
    close = df["close"]

    middle = close.rolling(period, min_periods=period).mean()
    deviation = close.rolling(period, min_periods=period).std(ddof=0)
    upper = middle + num_std * deviation
    lower = middle - num_std * deviation

    keltner_middle = ema(close, keltner_period)
    keltner_range = keltner_atr_mult * atr(df, keltner_period)
    keltner_upper = keltner_middle + keltner_range
    keltner_lower = keltner_middle - keltner_range

    bandwidth = (upper - lower) / middle.replace(0.0, np.nan)
    squeeze = (upper < keltner_upper) & (lower > keltner_lower)

    return pd.DataFrame(
        {
            "bb_upper": upper,
            "bb_middle": middle,
            "bb_lower": lower,
            "bb_bandwidth": bandwidth,
            "kc_upper": keltner_upper,
            "kc_lower": keltner_lower,
            "bb_squeeze": squeeze.fillna(False),
        },
        index=df.index,
    )


def session_cumulative_delta(
    df: pd.DataFrame, session_cfg: SessionConfig
) -> pd.Series | None:
    """Kumulatives Volumen-Delta, das zu jedem Sessionbeginn zurueckstellt.

    Erwartet die Spalten ``bid_volume`` und ``ask_volume`` (aus den
    Tradovate-Feldern ``bidVolume``/``offerVolume``). Fehlen sie oder sind
    sie durchgehend null, wird ``None`` zurueckgegeben - **nicht** ein aus
    Auf-/Abwaertskerzen geschaetztes Ersatzdelta. Ein geschaetztes Delta
    sieht aus wie eine Messung und ist keine.
    """
    if "bid_volume" not in df.columns or "ask_volume" not in df.columns:
        return None

    flow = df["ask_volume"].fillna(0.0) + df["bid_volume"].fillna(0.0)
    if float(flow.sum()) <= 0.0:
        return None

    delta = df["ask_volume"].fillna(0.0) - df["bid_volume"].fillna(0.0)
    sessions = session_dates(df.index, session_cfg)
    return delta.groupby(sessions.values).cumsum()


DEFAULT_EMA_PERIODS = (9, 21, 50, 200)


def ema_stack(close: pd.Series, periods: tuple[int, ...] = DEFAULT_EMA_PERIODS) -> pd.DataFrame:
    """Mehrere EMAs plus Flag, ob sie sauber gestapelt sind.

    "Gestapelt" heisst: streng monoton in der Periodenreihenfolge - also
    EMA9 > EMA21 > EMA50 > EMA200 (bullisch) oder umgekehrt (baerisch).
    Das ist ein deutlich belastbareres Trendsignal als eine einzelne
    Kreuzung.

    Wichtige Einschraenkung: das Flag beschreibt die FORM, nicht die
    STAERKE. In einer engen Seitwaertsphase koennen die EMAs formal sauber
    gestaffelt sein und trotzdem nur Cents auseinanderliegen. Deshalb steht
    im Snapshot der ADX daneben - erst beide zusammen ergeben eine Aussage.
    """
    columns: dict[str, pd.Series] = {}
    for period in periods:
        columns[f"ema_{period}"] = ema(close, period)

    frame = pd.DataFrame(columns, index=close.index)
    ordered = [frame[f"ema_{period}"] for period in periods]

    bullish = pd.Series(True, index=close.index)
    bearish = pd.Series(True, index=close.index)
    for faster, slower in zip(ordered, ordered[1:]):
        bullish &= faster > slower
        bearish &= faster < slower

    valid = frame.notna().all(axis=1)
    frame["ema_stacked_bullish"] = (bullish & valid).fillna(False)
    frame["ema_stacked_bearish"] = (bearish & valid).fillna(False)
    return frame


def compute_extended_indicators(
    df: pd.DataFrame,
    indicator_cfg: IndicatorConfig,
    session_cfg: SessionConfig,
    *,
    ema_periods: tuple[int, ...] = DEFAULT_EMA_PERIODS,
) -> pd.DataFrame:
    """``compute_indicators`` plus MACD, Stochastik, ADX, Bollinger, EMA-Stack.

    Baut ausdruecklich auf der gemeinsamen Basisfunktion auf - RSI, ATR,
    VWAP und Vortagesmarken werden nicht neu implementiert.
    """
    result = compute_indicators(df, indicator_cfg, session_cfg)

    for block in (
        macd(result["close"]),
        stochastic(result, indicator_cfg.rsi_period),
        adx(result, indicator_cfg.atr_period),
        bollinger(result),
        ema_stack(result["close"], ema_periods),
    ):
        for column in block.columns:
            result[column] = block[column]

    return result


__all__ = [
    "DEFAULT_EMA_PERIODS",
    "OHLCV_COLUMNS",
    "FlagColumns",
    "adx",
    "atr",
    "bollinger",
    "compute_extended_indicators",
    "compute_indicators",
    "ema",
    "ema_stack",
    "flag_signals",
    "macd",
    "previous_session_levels",
    "rsi",
    "session_cumulative_delta",
    "session_vwap",
    "sma",
    "stochastic",
    "true_range",
    "validate_ohlcv",
]
