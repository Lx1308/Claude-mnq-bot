"""In-Sample / Out-of-Sample-Trennung.

Der haeufigste Selbstbetrug beim Backtesting ist, Parameter auf denselben
Daten zu optimieren, auf denen spaeter "getestet" wird. Dieses Modul macht
das schwer:

* :func:`split_data` teilt die Historie chronologisch (nie zufaellig -
  Zeitreihen duerfen nicht gemischt werden).
* :func:`assert_in_sample_only` wird von jeder Optimierung aufgerufen und
  wirft, sobald auch nur eine Kerze aus dem Out-of-Sample-Zeitraum im
  Datensatz liegt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from common.config import SplitConfig

log = logging.getLogger(__name__)


class OutOfSampleViolation(RuntimeError):
    """Es wurde versucht, auf Out-of-Sample-Daten zu optimieren."""


@dataclass(frozen=True)
class DataSplit:
    in_sample: pd.DataFrame
    out_of_sample: pd.DataFrame
    boundary: pd.Timestamp

    def describe(self) -> str:
        return (
            f"In-Sample : {self.in_sample.index[0]:%Y-%m-%d %H:%M} bis "
            f"{self.in_sample.index[-1]:%Y-%m-%d %H:%M}  ({len(self.in_sample)} Kerzen)\n"
            f"Out-of-Sample: {self.out_of_sample.index[0]:%Y-%m-%d %H:%M} bis "
            f"{self.out_of_sample.index[-1]:%Y-%m-%d %H:%M}  ({len(self.out_of_sample)} Kerzen)"
        )


def split_data(df: pd.DataFrame, config: SplitConfig) -> DataSplit:
    """Teilt die Daten chronologisch in In-Sample und Out-of-Sample."""
    if df.empty:
        raise ValueError("Leerer Datensatz laesst sich nicht teilen.")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Daten muessen chronologisch sortiert sein.")

    if config.mode == "date":
        boundary = pd.Timestamp(config.split_date)
        if boundary.tz is None:
            boundary = boundary.tz_localize("UTC")
    else:
        cut = int(len(df) * config.in_sample_fraction)
        cut = max(1, min(cut, len(df) - 1))
        boundary = df.index[cut]

    in_sample = df[df.index < boundary]
    out_of_sample = df[df.index >= boundary]

    if in_sample.empty or out_of_sample.empty:
        raise ValueError(
            f"Aufteilung an {boundary} ergibt einen leeren Teil "
            f"(In-Sample: {len(in_sample)}, Out-of-Sample: {len(out_of_sample)}). "
            "Bitte in_sample_fraction oder split_date anpassen."
        )

    split = DataSplit(in_sample=in_sample, out_of_sample=out_of_sample, boundary=boundary)
    log.info("Datenaufteilung:\n%s", split.describe())
    return split


def assert_in_sample_only(df: pd.DataFrame, split: DataSplit, *, context: str = "Optimierung") -> None:
    """Schutzriegel: wirft, wenn ``df`` Out-of-Sample-Daten enthaelt."""
    if df.empty:
        return
    last = df.index[-1]
    if last >= split.boundary:
        raise OutOfSampleViolation(
            f"{context} laeuft auf Daten bis {last}, die Out-of-Sample-Grenze liegt aber "
            f"bei {split.boundary}. Optimiert wird ausschliesslich auf dem In-Sample-Teil - "
            "sonst ist das Ergebnis wertlos."
        )


def walk_forward_windows(
    df: pd.DataFrame,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Erzeugt rollierende (Trainings-, Test-)Fenster fuer Walk-Forward-Tests.

    Ein einzelner In-/Out-of-Sample-Schnitt sagt nur etwas ueber genau eine
    Marktphase aus. Walk-Forward wiederholt den Test ueber die gesamte
    Historie und ist damit deutlich aussagekraeftiger.
    """
    step = step_bars or test_bars
    windows: list[tuple[pd.DataFrame, pd.DataFrame]] = []
    start = 0
    while start + train_bars + test_bars <= len(df):
        train = df.iloc[start : start + train_bars]
        test = df.iloc[start + train_bars : start + train_bars + test_bars]
        windows.append((train, test))
        start += step
    return windows


def boundary_timestamp(split: DataSplit) -> datetime:
    return split.boundary.to_pydatetime()
