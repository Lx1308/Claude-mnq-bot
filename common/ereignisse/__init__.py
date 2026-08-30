"""Ereignis-Erkennung fuer die empirische Wissensbasis.

Siehe ``docs/FORSCHUNGSPLAN_EVENTDATENBANK.md``. Jeder Erkenner liefert eine
Liste von :class:`Ereignis` - auf dem 1m-Index verankert, mit den vier
getrennten Zeitpunkten (entstehung / bestaetigung / verfuegbar / Trigger).

Alle Erkenner sind **O(n) oder O(n log n)**. Die punktuellen Erkenner in
``common/patterns.py`` und ``common/market_primitives.py`` haben teils
quadratische Schleifen (Mitigation-Verfolgung, Strukturbruch je Swing) - auf
2,5 Mio Kerzen unbrauchbar. Deshalb hier eigene, serientaugliche Fassungen;
die Musterdefinition bleibt dieselbe, und Tests halten die Gleichheit fest.
"""

from common.ereignisse.basis import (
    ERKENNUNGS_TIMEFRAMES,
    Ereignis,
    LookaheadVerletzung,
    grobe_kerze_zu_1m_index,
    pruefe_lookahead,
)

__all__ = [
    "ERKENNUNGS_TIMEFRAMES",
    "Ereignis",
    "LookaheadVerletzung",
    "grobe_kerze_zu_1m_index",
    "pruefe_lookahead",
]
