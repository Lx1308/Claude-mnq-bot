"""In-Sample / Out-of-Sample-Trennung.

Der haeufigste Selbstbetrug beim Backtesting ist, Parameter auf denselben
Daten zu optimieren, auf denen spaeter "getestet" wird. Dieses Modul macht
das schwer:

* :func:`split_data` teilt die Historie chronologisch (nie zufaellig -
  Zeitreihen duerfen nicht gemischt werden).
* :func:`assert_in_sample_only` wird von jeder Optimierung aufgerufen und
  wirft, sobald auch nur eine Kerze aus dem Out-of-Sample-Zeitraum im
  Datensatz liegt.
* :func:`split_data_three_way` und :func:`assert_validation_only` erweitern
  das auf die Research-Engine-Phasentrennung Discovery -> Validation ->
  Confirmation (Masterplan G): der bisherige Out-of-Sample-Rest wird ein
  zweites Mal geteilt, damit fuer Validation ein Block existiert, den
  Discovery nie gesehen hat, WAEHREND ein kleinerer OOS-Rest fuer die
  einmalige Confirmation reserviert bleibt.
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


@dataclass(frozen=True)
class ThreeWaySplit:
    """Chronologische Dreiteilung: Training, Validation, Out-of-Sample.

    ``validation_boundary`` ist dieselbe Grenze, die ein zweiweiser
    :func:`split_data` mit gleichem ``in_sample_fraction`` als
    ``boundary`` liefern wuerde - eine bereits fuer Discovery verbrauchte
    Trainingsgrenze wird durch die Dreiteilung also NICHT verschoben.
    """

    train: pd.DataFrame
    validation: pd.DataFrame
    out_of_sample: pd.DataFrame
    validation_boundary: pd.Timestamp
    oos_boundary: pd.Timestamp

    def describe(self) -> str:
        return (
            f"Training     : {self.train.index[0]:%Y-%m-%d %H:%M} bis "
            f"{self.train.index[-1]:%Y-%m-%d %H:%M}  ({len(self.train)} Kerzen)\n"
            f"Validation   : {self.validation.index[0]:%Y-%m-%d %H:%M} bis "
            f"{self.validation.index[-1]:%Y-%m-%d %H:%M}  ({len(self.validation)} Kerzen)\n"
            f"Out-of-Sample: {self.out_of_sample.index[0]:%Y-%m-%d %H:%M} bis "
            f"{self.out_of_sample.index[-1]:%Y-%m-%d %H:%M}  ({len(self.out_of_sample)} Kerzen)"
        )


def split_data_three_way(df: pd.DataFrame, config: SplitConfig) -> ThreeWaySplit:
    """Teilt die Daten chronologisch in Training, Validation und Out-of-Sample.

    ``config.in_sample_fraction`` bestimmt wie bei :func:`split_data` die
    Trainingsgrenze. Neu ist, dass der bisherige Out-of-Sample-Rest ein
    zweites Mal geteilt wird: ``config.validation_fraction`` davon wird
    Validation, der Rest bleibt Out-of-Sample - weiterhin unberuehrt und
    einmalig fuer die Confirmation-Phase.

    Nur ``mode="fraction"`` wird unterstuetzt. Ein datumsbasierter Schnitt
    muesste zwei Daten statt eines pflegen; dafuer besteht aktuell kein
    Bedarf, siehe :func:`split_data` fuer die Zweiweg-Variante mit Datum.
    """
    if df.empty:
        raise ValueError("Leerer Datensatz laesst sich nicht teilen.")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Daten muessen chronologisch sortiert sein.")
    if config.mode != "fraction":
        raise ValueError(
            f"split_data_three_way unterstuetzt nur mode='fraction', nicht {config.mode!r}."
        )
    if not (0.0 < config.validation_fraction < 1.0):
        raise ValueError(
            f"validation_fraction muss zwischen 0 und 1 liegen, ist {config.validation_fraction}."
        )

    train_cut = int(len(df) * config.in_sample_fraction)
    train_cut = max(1, min(train_cut, len(df) - 2))
    rest = len(df) - train_cut
    validation_len = max(1, min(int(rest * config.validation_fraction), rest - 1))
    validation_cut = train_cut + validation_len

    train = df.iloc[:train_cut]
    validation = df.iloc[train_cut:validation_cut]
    out_of_sample = df.iloc[validation_cut:]

    if train.empty or validation.empty or out_of_sample.empty:
        raise ValueError(
            f"Dreiwege-Aufteilung ergibt einen leeren Teil (Training: {len(train)}, "
            f"Validation: {len(validation)}, Out-of-Sample: {len(out_of_sample)}). "
            "Bitte in_sample_fraction oder validation_fraction anpassen."
        )

    split = ThreeWaySplit(
        train=train,
        validation=validation,
        out_of_sample=out_of_sample,
        validation_boundary=df.index[train_cut],
        oos_boundary=df.index[validation_cut],
    )
    log.info("Dreiwege-Datenaufteilung:\n%s", split.describe())
    return split


def assert_validation_only(
    df: pd.DataFrame, split: ThreeWaySplit, *, context: str = "Validation"
) -> None:
    """Schutzriegel: wirft, wenn ``df`` in den Out-of-Sample-Teil hineinreicht.

    Analog zu :func:`assert_in_sample_only`, nur gegen die zweite Grenze der
    Dreiteilung. Erlaubt sind Training und Validation gemeinsam - die
    Validation-Phase darf auf beidem rechnen (Indikatoren brauchen den
    Trainingsvorlauf, Invariante 5), nur der Out-of-Sample-Rest ist tabu.
    """
    if df.empty:
        return
    last = df.index[-1]
    if last >= split.oos_boundary:
        raise OutOfSampleViolation(
            f"{context} laeuft auf Daten bis {last}, die Out-of-Sample-Grenze liegt aber "
            f"bei {split.oos_boundary}. Validation rechnet ausschliesslich auf Training und "
            "Validation - der Out-of-Sample-Teil ist einmalig fuer die Confirmation reserviert."
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
