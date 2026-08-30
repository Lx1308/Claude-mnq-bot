# Auftrag für den Watchdog

Diese Datei ist der Text, den `werkzeuge/watchdog.py` an Claude Code
übergibt, wenn er die Arbeit fortsetzt. Sie steht bewusst außerhalb des Codes:
Laurin kann sie ändern, ohne zu programmieren, und im Protokoll ist nachlesbar,
womit ein Lauf gestartet wurde.

**Alles ab der nächsten Zeile wird als Prompt übergeben.**

---

Setze die Arbeit an diesem Projekt eigenständig fort.

## Zuerst orientieren

1. `CODE_CHAT_KONTEXT.md`, Abschnitt 34 — der aktuelle Stand.
2. `docs/OFFENE_PUNKTE.md` — die Liste, die abgearbeitet wird.
3. `git log --oneline -15` — was zuletzt passiert ist.

Wenn ein Punkt schon erledigt aussieht, prüfe das am Code und hake ihn in
`docs/OFFENE_PUNKTE.md` ab, statt ihn noch einmal zu bauen. Doppelte Arbeit ist
schlimmer als keine.

## Dann arbeiten

Nimm den obersten offenen Punkt mit der höchsten Priorität. Arbeite ihn
vollständig ab: Ursache verstehen, Lösung bauen, Tests schreiben, Tests laufen
lassen, dokumentieren.

Die Reihenfolge der Prioritäten steht in `docs/OFFENE_PUNKTE.md`. Wenn du einen
wichtigeren Punkt findest, der dort fehlt, trage ihn ein und begründe warum.

## Was gilt

- `CLAUDE.md` ist verbindlich — besonders die Invarianten und die
  Projektgrenze (nur Simulationskonten, kein Schalter dafür).
- **Keine Schätzung, die aussieht wie eine Messung.** Was nicht messbar ist,
  bleibt `null` mit Begründung.
- Tests müssen grün sein, bevor du committest:
  `.venv\Scripts\python.exe -m pytest`
- **Committe lokal. Pushe NICHTS nach GitHub.** Laurin hat das am 29.08.2026
  ausdrücklich verlangt: in GitHub sollen nur laufende Versionen liegen, und er
  gibt jeden Push selbst frei.
- Ändere nichts an der Simulationskonto-Sperre in
  `ninjatrader/TradayriBridge.cs`.
- Wenn `ausfuehrung.enabled` in `config.yaml` auf `true` steht, läuft der Bot
  auf Sim101. Schalte ihn nicht ohne Grund ab — und wenn doch, schreib in den
  Commit warum.

## Am Ende

Aktualisiere `docs/OFFENE_PUNKTE.md`: erledigte Punkte abhaken, neu gefundene
eintragen. Schreib in einen kurzen Abschnitt, was du gemacht hast und was als
Nächstes dran ist — damit der nächste Lauf (oder Laurin) sofort weiß, wo es
steht.

Wenn du auf eine echte Produktentscheidung stößt, die du nicht ableiten kannst:
**nicht raten.** Trag sie in `docs/OFFENE_PUNKTE.md` unter „Fragen an Laurin"
ein und arbeite an etwas anderem weiter.
