# Prompt für eine neue Claude-Code-Session (Etappe C)

Im Projektordner `C:\Users\lm130\Desktop\Claude chart bot` eine Terminal-Session
starten und Folgendes einfügen:

---

Lies zuerst `CLAUDE.md`, `CODE_CHAT_KONTEXT.md` und `NORMALER_CHAT_KONTEXT.md`
vollständig, bevor du irgendetwas änderst. Sie sind das Projektgedächtnis und
gehen jeder Annahme vor.

Deine Aufgabe: **Etappe C — regelbasierte Ideen-Protokollierung für MNQ**
(Punkt 1 unter "Offen" in `NORMALER_CHAT_KONTEXT.md`).

Vorgehen:

1. **Vorarbeit zuerst.** Punkt 7 unter "Offen" ist ausdrücklich Voraussetzung
   für unbeaufsichtigtes Arbeiten: lege ein lokales Git-Repo an und prüfe die
   `.gitignore` auf `.env`, `.venv/`, `*.sqlite3` und Logs. Kein Push zu GitHub
   ohne meine ausdrückliche Freigabe. Ohne Repo gibt es kein Rückholnetz.
2. **Plane, bevor du baust.** Schreib mir erst einen kurzen Entwurf: welche
   Regeln eine Idee auslösen, welche Felder eine protokollierte Idee hat, wo sie
   gespeichert wird, wie sie später von Etappe D (`evaluate_past_ideas`,
   `get_performance_report`) auswertbar bleibt. Dann bauen.
3. **Arbeite in kleinen, committeten Schritten.** Jeder Commit lässt die
   bestehenden Tests grün (aktuell 326). Neue Logik bekommt Tests, kritische
   Logik zusätzlich eine unabhängige Gegenprobe.

Feste Randbedingungen, die nicht verhandelbar sind:

- **Eine einzige Indikator-/Signal-Implementierung.** Alles rechnet über
  `common/indicators.py::compute_indicators`. Keine zweite Rechenlogik, auch
  nicht "nur für Etappe C".
- **Read-only by design.** Kein Order-Endpunkt, keine Positionsverwaltung, keine
  Auto-Execution — nicht ergänzen, nicht vorschlagen.
- **Kein Anthropic-API-Aufruf in `mcp_server/`.**
- **Keine stillen Ausfälle.** Fehlende Voraussetzungen brechen mit klarer
  Meldung ab, statt still NaN zu liefern (siehe Puffergrößen-Invariante).
- **Schwellenwerte nur in `config.yaml`**, Secrets nur in `.env`.
- **Deutsche Kommentare, Docstrings und Testnamen; Quelldateien in ASCII**
  (Umlaute als ae/oe/ue).
- **Keine erfundenen Zahlen.** Kennzahlen kommen aus echten Daten oder gar
  nicht. `data/DEMO_1m.csv` ist synthetisch und taugt nicht als Beleg.
- **Widersprüche zwischen Doku und Code** dokumentierst du und meldest sie mir,
  statt sie still aufzulösen.

Wenn du an einer Stelle eine Entscheidung brauchst, die du nicht aus den
Kontextdateien ableiten kannst: **rate nicht.** Vermerk die offene Frage als
`# OFFENE FRAGE:`-TODO im Code, sag sie mir in einem Satz, und arbeite
solange an einem unabhängigen Punkt aus der Liste "Offen" weiter
(README aktualisieren, Test-Härtung, Etappe-D-Vorarbeiten).

Am Ende der Arbeit: `CODE_CHAT_KONTEXT.md` aktualisieren (Stand, neue Dateien,
Entscheidungen, verworfene Ansätze, Testzahl, Datum in der Kopfzeile) und
`NORMALER_CHAT_KONTEXT.md` nur, falls sich Ziele oder Etappen-Status geändert
haben.

---
