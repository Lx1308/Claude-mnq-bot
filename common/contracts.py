"""Aufgeloester Kontrakt - brokerneutral.

WARUM DIESES MODUL EXISTIERT
----------------------------
:class:`Contract` lag frueher in ``live_bot/tradovate/contracts.py``. Damit
zog jeder, der einen aufgeloesten Kontrakt brauchte, den kompletten
Tradovate-Stack mit - auch der MCP-Server, der mit Tradovate nichts zu tun
hat und seine Kerzen aus NinjaTrader bekommt.

Inhaltlich ist an der Klasse nichts brokerspezifisch: ein Bezeichner, ein
Name, ein Verfallsdatum. Sie gehoert deshalb nach ``common/``, wo alle
Pfade sie ohne Ballast benutzen koennen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Contract:
    """Ein konkreter Kontraktmonat, z.B. ``MNQ SEP26``.

    ``id`` ist der Bezeichner der Datenquelle. Die NinjaTrader-Bridge kennt
    keine numerischen Kontrakt-IDs und setzt hier ``0`` - das Feld bleibt
    erhalten, weil andere Quellen es fuellen koennen.
    """

    id: int
    name: str
    expiry: date | None = None


__all__ = ["Contract"]
