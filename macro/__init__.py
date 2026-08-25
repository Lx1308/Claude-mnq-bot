"""Makro- und Wirtschaftskalenderdaten fuer die Research-Engine.

Getrennt von ``mcp_server/calendar_provider.py``: jenes Modul ist ein
zustandsloser Live-Dienst fuer Claude Desktop (TTL-Cache, kein Verlauf).
Dieses Paket ist das Gegenstueck fuer Research - persistiert, versioniert
nach Revision, point-in-time-korrekt. Beide teilen sich bewusst keinen
Code: unterschiedliche Anforderungen (Live-Aktualitaet vs. historische
Reproduzierbarkeit) rechtfertigen unterschiedliche Implementierungen, siehe
Invariante 1 (gilt fuer Signal-/Indikatorlogik, nicht fuer jede Datenquelle).

Siehe MASTERPLAN.md Abschnitt F.2, K, L fuer die Architekturbegruendung.
"""
