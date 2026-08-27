"""Empirische Conditional Outcome Engine.

Beantwortet die fundamentale Research-Frage:
"Wenn Bedingung X vorliegt, was passiert danach historisch mit dem Kurs?"

Untersucht Forward-Renditen, MAE/MFE-Verteilungen und Target-vs-Stop-
Wahrscheinlichkeiten voellig unberuehrt von willkuerlichen Exit-Regeln.
Vergleicht jedes Ergebnis strikt mit der bedingungslosen Markt-Baseline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd

from backtest.excursions import PathExcursion, compute_path_excursions
from backtest.research import p_wert_zweiseitig
from common.indicators import validate_ohlcv


@dataclass(frozen=True)
class TargetStopOutcome:
    """Trefferquote fuer eine spezifische Target-vs-Stop Kombination in R."""

    target_r: float
    stop_r: float
    win_rate: float                      # Anteil, der Target vor Stop erreicht
    target_hits: int
    stop_hits: int
    neither_hits: int                    # Weder noch im Horizont erreicht
    sample_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ziel_in_r": self.target_r,
            "stop_in_r": self.stop_r,
            "trefferquote": round(self.win_rate, 4),
            "ziel_erreicht": self.target_hits,
            "stop_erreicht": self.stop_hits,
            "zeitablauf": self.neither_hits,
            "stichprobe": self.sample_size,
        }


@dataclass(frozen=True)
class ConditionalOutcomeReport:
    """Vollstaendiger statistischer Bericht einer Bedingungsuntersuchung."""

    condition_name: str
    sample_size: int
    unconditional_sample_size: int
    horizon_bars: int

    # Rendite-Verteilung (Punkte)
    mean_return_pts: float
    median_return_pts: float
    std_return_pts: float

    # Rendite-Verteilung (R / ATR)
    mean_return_r: float
    median_return_r: float

    # MAE & MFE Mediane
    median_mfe_r: float
    median_mae_r: float

    # Baseline-Vergleich (Unconditional)
    baseline_mean_r: float
    baseline_median_r: float
    edge_r: float                        # Differenz Mean R vs Baseline Mean R
    t_statistic: float
    p_value: float

    # Grid von Target / Stop Resultaten
    target_stop_grid: list[TargetStopOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bedingung": self.condition_name,
            "stichprobe": self.sample_size,
            "baseline_stichprobe": self.unconditional_sample_size,
            "horizont_kerzen": self.horizon_bars,
            "erwartungswert_r": round(self.mean_return_r, 4),
            "median_r": round(self.median_return_r, 4),
            "edge_ueber_baseline_r": round(self.edge_r, 4),
            "median_mfe_in_r": round(self.median_mfe_r, 2),
            "median_mae_in_r": round(self.median_mae_r, 2),
            "t_statistik": round(self.t_statistic, 3),
            "p_wert": round(self.p_value, 6),
            "signifikant_alpha_005": bool(self.p_value < 0.05),
            "target_stop_matrix": [o.to_dict() for o in self.target_stop_grid],
        }


def analyze_conditional_outcomes(
    df: pd.DataFrame,
    condition_mask: pd.Series | Sequence[bool],
    *,
    condition_name: str = "Bedingung",
    direction: int = 1,
    horizon_bars: int = 20,
    target_r_grid: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0),
    stop_r_grid: tuple[float, ...] = (1.0, 1.5, 2.0),
    atr_series: pd.Series | None = None,
) -> ConditionalOutcomeReport:
    """Fuehrt eine empirische Forward-Outcome-Analyse durch."""
    validate_ohlcv(df)
    n = len(df)
    if n < horizon_bars + 2:
        raise ValueError("Datensatz zu kurz fuer diesen Horizont.")

    mask_arr = np.asarray(condition_mask, dtype=bool)
    if len(mask_arr) != n:
        raise ValueError(f"Maskenlaenge ({len(mask_arr)}) weicht von Datenlaenge ({n}) ab.")

    # Indizes mit erfuellter Bedingung (nur bis n - horizon - 1)
    max_idx = n - horizon_bars - 1
    cond_indices = [i for i in range(max_idx) if mask_arr[i]]
    uncond_indices = list(range(max_idx))

    if not cond_indices:
        raise ValueError(f"Keine Eintraege erfuellen Bedingung {condition_name!r}.")

    cond_excursions = compute_path_excursions(
        df, cond_indices, direction=direction, horizon_bars=horizon_bars, atr_series=atr_series
    )
    uncond_excursions = compute_path_excursions(
        df, uncond_indices, direction=direction, horizon_bars=horizon_bars, atr_series=atr_series
    )

    cond_r = np.array([e.final_r for e in cond_excursions], dtype=float)
    uncond_r = np.array([e.final_r for e in uncond_excursions], dtype=float)

    mean_pts = float(np.mean([e.final_points for e in cond_excursions]))
    median_pts = float(np.median([e.final_points for e in cond_excursions]))
    std_pts = float(np.std([e.final_points for e in cond_excursions]))

    mean_r = float(np.mean(cond_r))
    median_r = float(np.median(cond_r))
    med_mfe = float(np.median([e.mfe_r for e in cond_excursions]))
    med_mae = float(np.median([e.mae_r for e in cond_excursions]))

    base_mean = float(np.mean(uncond_r))
    base_median = float(np.median(uncond_r))
    edge = mean_r - base_mean

    # t-Statistik gegen Baseline
    s_cond = len(cond_r)
    var_cond = float(np.var(cond_r, ddof=1)) if s_cond > 1 else 1.0
    se = math.sqrt(var_cond / s_cond) if s_cond > 0 else 1.0
    t_stat = (mean_r - base_mean) / se if se > 0 else 0.0
    deg_f = max(1, s_cond - 1)
    p_val = p_wert_zweiseitig(t_stat, deg_f)

    # Grid-Evaluation: Target vs Stop
    grid_results: list[TargetStopOutcome] = []
    for tgt_r in target_r_grid:
        for stp_r in stop_r_grid:
            tgt_hits = 0
            stp_hits = 0
            neither = 0

            for exc in cond_excursions:
                # Rekonstruiere intrabar Beruehrung aus Pfad
                hit_target = exc.mfe_r >= tgt_r
                hit_stop = exc.mae_r >= stp_r

                if hit_target and hit_stop:
                    # Wer zuerst beruehrt wurde (Timing)
                    if exc.time_to_mae_bars <= exc.time_to_mfe_bars:
                        stp_hits += 1  # Konservativ Stop zuerst
                    else:
                        tgt_hits += 1
                elif hit_target:
                    tgt_hits += 1
                elif hit_stop:
                    stp_hits += 1
                else:
                    neither += 1

            total_decided = tgt_hits + stp_hits
            wr = (tgt_hits / total_decided) if total_decided > 0 else 0.0

            grid_results.append(
                TargetStopOutcome(
                    target_r=tgt_r,
                    stop_r=stp_r,
                    win_rate=wr,
                    target_hits=tgt_hits,
                    stop_hits=stp_hits,
                    neither_hits=neither,
                    sample_size=s_cond,
                )
            )

    return ConditionalOutcomeReport(
        condition_name=condition_name,
        sample_size=s_cond,
        unconditional_sample_size=len(uncond_r),
        horizon_bars=horizon_bars,
        mean_return_pts=mean_pts,
        median_return_pts=median_pts,
        std_return_pts=std_pts,
        mean_return_r=mean_r,
        median_return_r=median_r,
        median_mfe_r=med_mfe,
        median_mae_r=med_mae,
        baseline_mean_r=base_mean,
        baseline_median_r=base_median,
        edge_r=edge,
        t_statistic=t_stat,
        p_value=p_val,
        target_stop_grid=grid_results,
    )
