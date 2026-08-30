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

    #: t und p ueber ALLE Vorkommen - **ueberlappend gerechnet und deshalb
    #: nicht belastbar**. Steht hier nur, weil der Unterschied zur ehrlichen
    #: Rechnung die eigentliche Auskunft ist.
    t_statistic: float
    p_value: float

    #: Dieselbe Groesse ueber ueberschneidungsfreie Vorkommen. **Das sind die
    #: Zahlen, die gelten.**
    #:
    #: WARUM ES DIESE ZWEITE RECHNUNG BRAUCHT
    #: --------------------------------------
    #: Die Vorwaertsrendite ab Kerze i und die ab Kerze i+1 teilen sich
    #: ``horizon_bars - 1`` ihrer Kerzen. Sie sind nicht unabhaengig, die
    #: t-Statistik setzt das aber voraus. Am 30.08.2026 auf echten MNQ-Daten
    #: nachgemessen, Horizont 24 Kerzen:
    #:
    #:     ueberlappend      n=149.975   t=8,49   p=2,0e-17
    #:     ueberschneidungsfrei  n=6.249  t=1,71   p=0,088
    #:     Faktor 4,98 - erwartet sqrt(24) = 4,90
    #:
    #: Dieselben Daten, dieselbe Kante. Einmal sieht sie aus wie eine
    #: Gewissheit, einmal ist sie nicht einmal auf 5 % signifikant. Wer die
    #: ueberlappende Zahl berichtet, berichtet einen Messfehler.
    sample_size_unabhaengig: int = 0
    t_statistic_unabhaengig: float = 0.0
    p_value_unabhaengig: float = 1.0

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
            # Die ueberschneidungsfreien Zahlen zuerst - sie sind die, die
            # gelten. Die ueberlappenden stehen daneben, damit der
            # Unterschied sichtbar bleibt.
            "stichprobe_unabhaengig": self.sample_size_unabhaengig,
            "t_statistik": round(self.t_statistic_unabhaengig, 3),
            "p_wert": round(self.p_value_unabhaengig, 6),
            "signifikant_alpha_005": bool(self.p_value_unabhaengig < 0.05),
            "t_statistik_ueberlappend": round(self.t_statistic, 3),
            "p_wert_ueberlappend": round(self.p_value, 6),
            "hinweis_ueberlappung": (
                "Die ueberlappenden Werte setzen unabhaengige Beobachtungen "
                "voraus, die es nicht gibt (Vorwaertsfenster teilen sich "
                "Kerzen). Sie ueberschaetzen die Signifikanz um rund "
                "sqrt(Horizont). Massgeblich sind t_statistik und p_wert."
            ),
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

    def _t_und_p(werte: np.ndarray) -> tuple[float, float]:
        anzahl = len(werte)
        if anzahl < 2:
            return 0.0, 1.0
        varianz = float(np.var(werte, ddof=1))
        fehler = math.sqrt(varianz / anzahl)
        if fehler <= 0:
            return 0.0, 1.0
        t = (float(np.mean(werte)) - base_mean) / fehler
        return t, p_wert_zweiseitig(t, max(1, anzahl - 1))

    # Ueberlappend - nur zum Vergleich, siehe Feld-Dokumentation.
    t_stat, p_val = _t_und_p(cond_r)

    # Ueberschneidungsfrei: aus den Vorkommen nur solche behalten, die
    # mindestens einen Horizont auseinander liegen.
    #
    # WARUM GREEDY UND NICHT JEDES n-te: bei einer seltenen Bedingung (ein
    # Muster, das alle paar hundert Kerzen auftritt) sind die Vorkommen
    # ohnehin fast alle unabhaengig - jedes 24. zu nehmen wuerde 23 von 24
    # gueltigen Beobachtungen wegwerfen. Der gierige Durchlauf behaelt
    # alles, was sich nicht ueberschneidet, und duennt nur dort aus, wo es
    # noetig ist.
    unabhaengige_positionen: list[int] = []
    letzter_index = -(horizon_bars + 1)
    for laufnummer, kerzenindex in enumerate(cond_indices):
        if kerzenindex - letzter_index >= horizon_bars:
            unabhaengige_positionen.append(laufnummer)
            letzter_index = kerzenindex
    unabhaengig_r = cond_r[unabhaengige_positionen]
    t_unab, p_unab = _t_und_p(unabhaengig_r)

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
                    sample_size=len(cond_r),
                )
            )

    return ConditionalOutcomeReport(
        condition_name=condition_name,
        sample_size=len(cond_r),
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
        sample_size_unabhaengig=len(unabhaengig_r),
        t_statistic_unabhaengig=t_unab,
        p_value_unabhaengig=p_unab,
        target_stop_grid=grid_results,
    )
