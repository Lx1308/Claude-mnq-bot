"""Orchestriert das Nachladen von Makro-Vintages in den Speicher.

Ein Aufruf pro Reihe: ALFRED liefert immer die VOLLSTAENDIGE Historie
zurueck (kein inkrementelles "nur was neu ist" - ALFRED kennt kein
seit-Datum-Filter fuer Vintages). ``MacroStore.speichere`` ist idempotent
(``ON CONFLICT DO NOTHING``), ein wiederholter Lauf ueber dieselbe Reihe
kostet also nur unnoetigen Netzwerkverkehr, keine Dateninkonsistenz.
"""

from __future__ import annotations

import dataclasses
import logging

from common.logging_setup import log_event
from macro.provider import STANDARD_SERIEN, FredAlfredProvider, MacroProviderError
from macro.store import MacroStore

log = logging.getLogger(__name__)


def aktualisiere(
    store: MacroStore,
    provider: FredAlfredProvider,
    *,
    serien: dict[str, str] | None = None,
    wichtigkeit: dict[str, str] | None = None,
) -> dict[str, int]:
    """Holt jede konfigurierte Reihe und speichert neue Vintages.

    Rueckgabe: Reihen-ID -> Anzahl neu gespeicherter Vintages. Eine Reihe,
    bei der die Abfrage fehlschlaegt, bricht NICHT den ganzen Lauf ab -
    andere Reihen sollen trotzdem ankommen - wird aber namentlich als Fehler
    ausgewiesen, nicht stillschweigend als "0 neue" verbucht.

    ``wichtigkeit`` traegt die kuratierte Impact-Einstufung
    (``config.yaml``, ``macro.wichtigkeit``) in die gespeicherten Zeilen ein
    - FRED liefert selbst keine Einstufung, das ist reine fachliche
    Einordnung (Begruendung: CODE_CHAT_KONTEXT.md Abschnitt 31.10). Eine
    Reihe ohne Eintrag bleibt ``importance = None``, nicht geraten.
    """
    ziel_serien = serien if serien is not None else STANDARD_SERIEN
    wichtigkeit = wichtigkeit or {}
    ergebnis: dict[str, int] = {}

    for series_id in ziel_serien:
        try:
            vintages = _hole_synchron(provider, series_id)
        except MacroProviderError as exc:
            log_event(
                log,
                "macro.pipeline.reihe_fehlgeschlagen",
                f"Reihe {series_id} konnte nicht geholt werden: {exc}",
                level=logging.WARNING,
                series=series_id,
                error=str(exc),
            )
            ergebnis[series_id] = -1  # -1 heisst "Fehler", nicht "0 neue"
            continue

        stufe = wichtigkeit.get(series_id)
        if stufe is not None:
            vintages = [dataclasses.replace(v, importance=stufe) for v in vintages]

        neu = store.speichere(vintages)
        ergebnis[series_id] = neu

    store.setze_herkunft(
        provider.name,
        f"FRED/ALFRED, {len(ziel_serien)} kuratierte Reihen, "
        "volle Vintage-Historie je Reihe.",
    )
    return ergebnis


def _hole_synchron(provider: FredAlfredProvider, series_id: str) -> list:
    import asyncio

    return asyncio.run(provider.hole_vintages(series_id))


__all__ = ["aktualisiere"]
