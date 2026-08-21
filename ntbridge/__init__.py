"""Empfaenger fuer Kerzen aus NinjaTrader 8.

Ersetzt die Tradovate-Datenbeschaffung. Alles in ``common/`` und die
MCP-Werkzeuge bleiben unveraendert - sie verarbeiten OHLCV und wissen nicht,
woher es kommt.

Der SQLite-Speicher hier IST zugleich der Bar-Cache, den wir frueher
verschoben hatten: er waechst im Betrieb und schaltet damit nach und nach
die Felder frei, die historische Tiefe brauchen.
"""
