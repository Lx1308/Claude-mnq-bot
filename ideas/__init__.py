"""Regelbasierte Ideen-Protokollierung (Etappe C).

Protokolliert im Hintergrund, WANN eine Setup-Bedingung erfuellt war - mit
Einstieg, Stop, Ziel und CRV aus den Daten bis genau diesem Moment. Keine
Order, keine Empfehlung: Datengrundlage fuer die spaetere Frage, welche
Setups tatsaechlich einen Erwartungswert haben.

Aufbau:

* ``setups``    - Setup-Familien, jede auf eine Backtest-Strategie abgebildet
* ``erkennung`` - laeuft ueber die Kerzen und wertet deren Regel-Objekte aus
* ``filters``   - vier Filter mit drei Ausgaengen (durch/abgelehnt/nicht pruefbar)
* ``model``     - TradeIdee (Haupt-Log) und Beobachtung (Exploration-Log)
* ``store``     - SQLite, Tabellen ``ideen`` und ``observations``
* ``pipeline``  - der Ablauf von Kerzen zu gespeicherten Ideen

Die Signal-Logik liegt ausschliesslich in ``backtest/strategies/``. Hier gibt
es bewusst keine zweite Fassung; sonst pruefte der Backtest eine andere
Strategie als die, die protokolliert wird.
"""
