"""Austauschbare Datenquellen fuer historische OHLCV-Daten."""

from backtest.data.base import BarRequest, DataProvider, DataProviderError
from backtest.data.csv_provider import CsvDataProvider
from backtest.data.ntbridge_provider import NtBridgeDataProvider

__all__ = [
    "BarRequest",
    "CsvDataProvider",
    "DataProvider",
    "DataProviderError",
    "NtBridgeDataProvider",
    "create_provider",
]

#: Registrierte Datenquellen. Ein neuer Anbieter (Databento, Rithmic,
#: CSV-Dump vom Broker, ...) wird hier eingetragen und ist danach ueberall
#: nutzbar, ohne dass Engine, Strategien oder CLI etwas davon wissen muessen.
PROVIDER: dict[str, type[DataProvider]] = {
    "csv": CsvDataProvider,
    "ntbridge": NtBridgeDataProvider,
}


def create_provider(name: str, **kwargs: object) -> DataProvider:
    """Factory - haelt den Rest des Frameworks frei von Anbieter-Details."""
    key = name.lower()
    klasse = PROVIDER.get(key)
    if klasse is None:
        raise DataProviderError(
            f"Unbekannte Datenquelle {name!r}. "
            f"Verfuegbar: {', '.join(repr(k) for k in sorted(PROVIDER))}."
        )
    return klasse(**kwargs)  # type: ignore[arg-type]
