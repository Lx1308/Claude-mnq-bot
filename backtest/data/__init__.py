"""Austauschbare Datenquellen fuer historische OHLCV-Daten."""

from backtest.data.base import BarRequest, DataProvider, DataProviderError
from backtest.data.csv_provider import CsvDataProvider

__all__ = [
    "BarRequest",
    "CsvDataProvider",
    "DataProvider",
    "DataProviderError",
    "create_provider",
]


def create_provider(name: str, **kwargs: object) -> DataProvider:
    """Factory - haelt den Rest des Frameworks frei von Anbieter-Details.

    Ein neuer Anbieter (Databento, Rithmic, CSV-Dump vom Broker, ...) wird
    hier registriert und ist danach ueberall nutzbar, ohne dass Engine,
    Strategien oder CLI etwas davon wissen muessen.
    """
    key = name.lower()
    if key == "csv":
        return CsvDataProvider(**kwargs)  # type: ignore[arg-type]
    raise DataProviderError(
        f"Unbekannte Datenquelle {name!r}. Verfuegbar: 'csv'."
    )
