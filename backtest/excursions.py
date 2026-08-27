"""MAE- und MFE-Pfad-Analyse fuer hypothetische Einstiege und Trades.

Wissenschaftliche Exkursions-Analyse:
- MFE (Maximum Favorable Excursion): maximale guenstige Kursbewegung
- MAE (Maximum Adverse Excursion): maximaler zwischenzeitlicher Buchverlust
- Time-to-MFE / Time-to-MAE: Verweildauer in Kerzen bis zum Extremum
- Pfad-Trajektorie: vollstaendiger Intrabar-Pfad ueber N Folgekerzen
- R-Vielfache bezogen auf die ATR-Referenz zum Einstiegszeitpunkt
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Sequence

import numpy as np
import pandas as pd

from common.indicators import validate_ohlcv


@dataclass(frozen=True)
class PathExcursion:
    """Quantitative Exkursions-Messung eines einzelnen Einstiegs."""

    entry_time: datetime
    entry_price: float
    direction: int                # 1 = Long, -1 = Short
    horizon_bars: int
    atr_ref: float

    # Exkursionen in Punkten
    mfe_points: float
    mae_points: float
    final_points: float

    # Exkursionen in R / ATR-Vielfachen
    mfe_r: float
    mae_r: float
    final_r: float

    # Timing
    time_to_mfe_bars: int
    time_to_mae_bars: int

    # Intrabar Pfad (Delta-Punkte je Kerze)
    path_points: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "einstieg_zeit_utc": self.entry_time.isoformat(),
            "einstiegskurs": round(self.entry_price, 4),
            "richtung": "long" if self.direction == 1 else "short",
            "horizont_kerzen": self.horizon_bars,
            "atr_referenz": round(self.atr_ref, 4),
            "mfe_punkte": round(self.mfe_points, 4),
            "mae_punkte": round(self.mae_points, 4),
            "end_punkte": round(self.final_points, 4),
            "mfe_in_r": round(self.mfe_r, 2),
            "mae_in_r": round(self.mae_r, 2),
            "end_in_r": round(self.final_r, 2),
            "kerzen_bis_mfe": self.time_to_mfe_bars,
            "kerzen_bis_mae": self.time_to_mae_bars,
        }


def compute_path_excursions(
    df: pd.DataFrame,
    entry_indices: Sequence[int],
    direction: int = 1,
    horizon_bars: int = 20,
    atr_series: pd.Series | None = None,
) -> list[PathExcursion]:
    """Berechnet MAE, MFE und Pfad-Statistiken fuer gegebene Einstiegs-Indizes."""
    validate_ohlcv(df)
    if not entry_indices or len(df) < 2:
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    opens = df["open"].to_numpy(dtype=float)
    timestamps = df.index

    atrs = None
    if atr_series is not None:
        atrs = atr_series.to_numpy(dtype=float)
    elif "atr" in df.columns:
        atrs = df["atr"].to_numpy(dtype=float)

    n = len(df)
    excursions: list[PathExcursion] = []

    for idx in entry_indices:
        # Ausfuehrung zur Eroeffnung der Folgekerze (Lookahead-Schutz):
        exec_idx = idx + 1
        if exec_idx >= n:
            continue

        entry_p = opens[exec_idx]
        entry_t = timestamps[exec_idx].to_pydatetime()
        atr_val = float(atrs[idx]) if (atrs is not None and not math.isnan(atrs[idx])) else 5.0
        if atr_val <= 0:
            atr_val = 5.0

        end_idx = min(n, exec_idx + horizon_bars)
        act_horizon = end_idx - exec_idx

        path_pts: list[float] = []
        max_fav = 0.0
        max_adv = 0.0
        t_mfe = 0
        t_mae = 0

        for step, k in enumerate(range(exec_idx, end_idx)):
            h, l, c = highs[k], lows[k], closes[k]

            if direction == 1:  # Long
                fav = max(0.0, h - entry_p)
                adv = max(0.0, entry_p - l)
                delta_c = c - entry_p
            else:               # Short
                fav = max(0.0, entry_p - l)
                adv = max(0.0, h - entry_p)
                delta_c = entry_p - c

            path_pts.append(delta_c)

            if fav > max_fav:
                max_fav = fav
                t_mfe = step + 1
            if adv > max_adv:
                max_adv = adv
                t_mae = step + 1

        final_delta = path_pts[-1] if path_pts else 0.0

        excursions.append(
            PathExcursion(
                entry_time=entry_t,
                entry_price=float(entry_p),
                direction=direction,
                horizon_bars=act_horizon,
                atr_ref=float(atr_val),
                mfe_points=float(max_fav),
                mae_points=float(max_adv),
                final_points=float(final_delta),
                mfe_r=float(max_fav / atr_val),
                mae_r=float(max_adv / atr_val),
                final_r=float(final_delta / atr_val),
                time_to_mfe_bars=t_mfe,
                time_to_mae_bars=t_mae,
                path_points=path_pts,
            )
        )

    return excursions
