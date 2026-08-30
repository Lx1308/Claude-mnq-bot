"""Auswertung: was haetten die Ergebnisse unter welchen Regeln bedeutet?

Die dritte Frage des Projekts, neben den beiden bestehenden:

* **Research** (``backtest/``) fragt: funktioniert dieses Muster ueberhaupt?
* **Ausfuehrung** (``execution/``) fragt: darf ich jetzt gerade handeln?
* **Auswertung** (hier) fragt: was haetten die tatsaechlichen Ergebnisse unter
  einem bestimmten Regelwerk bedeutet - haette das Konto ueberlebt, waere das
  Ziel erreicht worden, welche Hypothese haette getragen?

Diese Trennung folgt Invariante 6: ``profil`` dokumentiert die tatsaechliche
Kontoumgebung eines Trades, ``rules`` entscheidet beim **Auswerten**, was
gerechnet wird. Der Bot handelt auf einem freien Sim-Konto; welche
Prop-Regelwerke diese Handelsfolge ueberstanden haette, ist eine Frage, die
hier und erst im Nachhinein beantwortet wird.
"""

from auswertung.kontovergleich import (
    Kontoverlauf,
    TradeRueckblick,
    spiele_durch,
    vergleiche_kontoprofile,
)

__all__ = [
    "Kontoverlauf",
    "TradeRueckblick",
    "spiele_durch",
    "vergleiche_kontoprofile",
]
