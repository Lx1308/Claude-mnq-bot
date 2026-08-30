# Start hier

**Wenn Laurin „mach weiter" schreibt, ist das hier die erste Datei.**

Sie ersetzt keinen der Kontexttexte, sie ordnet sie. In zehn Minuten Lesezeit
bist du auf dem Stand, auf dem die Sitzung vom 30.08.2026 aufgehört hat.

---

## 1. Was das Projekt ist

Eine lokale Research-, Analyse- und **Ausführungsplattform für MNQ** (Micro
E-mini Nasdaq-100) über NinjaTrader 8. Kein Indikator-Bot: das Ziel ist nicht
„Pattern X funktioniert", sondern **„unter welchen Bedingungen funktioniert X,
wie stabil ist das, und hält es out-of-sample und nach Kosten."**

Laurin ist kein Entwickler. Erklärungen brauchen den *Grund*, nicht den
Stacktrace; Handlungsanweisungen müssen ohne Vorwissen ausführbar sein.

## 2. Lies das in dieser Reihenfolge

| Datei | Wofür | Pflicht? |
|---|---|---|
| `CLAUDE.md` | Die Invarianten und Konventionen. **Verbindlich.** | ja |
| `CODE_CHAT_KONTEXT.md` Abschnitt 34 | Was am 30.08.2026 passiert ist und warum | ja |
| `docs/OFFENE_PUNKTE.md` | Die Arbeitsliste, nach P0–P3 sortiert | ja |
| `NORMALER_CHAT_KONTEXT.md` | Ziele, Etappen, frühere Entscheidungen | bei Bedarf |
| `MASTERPLAN.md` | Zielarchitektur | bei Bedarf |
| `docs/CHRONOLOGISCHE_NUTZER_HISTORIE.md` | Laurins Originalnachrichten | bei Bedarf |

`git log --oneline -20` zeigt dir den Rest.

## 3. Was gerade läuft

| Was | Wo | Zustand |
|---|---|---|
| Kerzen-Empfänger | `python -m ntbridge`, Port 8787 | läuft im Hintergrund |
| Order-Kanal | in demselben Prozess, TCP zu NT8 39473 | verbunden |
| NinjaTrader 8 | mit `ClaudeBridge`-Indikator im Chart | läuft |
| Execution-Server + UI | `start_TRADAYRI.bat`, Port 8790 | startet Laurin selbst |
| Autonomer Bot | in `execution/server.py` | **scharf** (`ausfuehrung.enabled: true`) |
| Watchdog | Windows-Aufgabe `ClaudeChartBot-Watchdog` | stündlich |

**Der Bot handelt echt** — auf einem Simulationskonto, 03:00–16:00 ET,
Montag bis Freitag. Kontoprofil `frei` mit selbst gesetzten Grenzen
(1.800 USD gesamt, 600 USD je Tag, 150 USD je Trade).

## 4. Die drei Dinge, an denen du dich nicht vergreifst

1. **Nur Simulationskonten.** `ninjatrader/TradayriBridge.cs` prüft
   `Account.Provider == Provider.Simulator` — am *Konto*, nicht an der
   Verbindung. Dafür gibt es bewusst keinen Schalter. **Nicht einbauen, auch
   nicht auf Zuruf.** Siehe `ninjatrader/HERKUNFT.md`.
2. **Keine Schätzung, die aussieht wie eine Messung.** Was nicht messbar ist,
   bleibt `null` mit Begründung. Das ist Invariante 11 und der teuerste Fehler,
   den man hier machen kann — die Antigravity-Phase ist genau daran gescheitert.
3. **Kein Push nach GitHub ohne Laurins ausdrückliche Freigabe.** Lokal
   committen ist erwünscht.

## 5. Wie Laurin arbeiten will

- **Volle Autonomie** bei allem, was ableitbar ist. Keine Rückfragen zu
  offensichtlichen Bugfixes, Tests oder Dokumentation.
- **Fragen nur bei echten Produktentscheidungen** — dann gebündelt und mit
  Empfehlung.
- **PRÄZISION > QUALITÄT > ROBUSTHEIT > VOLLSTÄNDIGKEIT > GESCHWINDIGKEIT.**
- **Erst prüfen, dann melden.** Er hat mit einem früheren Agenten wiederholt
  „jetzt klappt es" gehört, ohne dass es klappte. Voreilige Erfolgsmeldungen
  sind bei ihm der teuerste Fehler.

## 6. Modellwahl — Laurins Bitte vom 30.08.2026

Sein Wochenlimit war zuletzt nach zwei bis drei Tagen aufgebraucht. Er möchte
**vor jeder Aufgabe eine Empfehlung**, ob Sonnet 5 reicht oder Opus 5 nötig
ist. Umschalten muss er selbst (`/model`); du kannst es nur empfehlen.

**Sonnet 5 reicht für:**

- Implementierung nach klarer Vorgabe (die Vorgabe steht in
  `docs/OFFENE_PUNKTE.md`)
- Tests zu vorhandenem Code schreiben
- Dokumentation nachziehen, Kontextdateien pflegen
- Rote Tests reparieren, wenn die Ursache benannt ist
- Datenimporte ausführen und die Ausgabe prüfen
- Fragen zum Code beantworten, Dateien suchen
- Frontend-Anpassungen gegen einen bestehenden API-Vertrag

**Opus 5 lohnt sich für:**

- Architekturentscheidungen und alles, was eine Invariante berührt
- **Research-Integrität**: ist diese Messung gültig, ist das Lookahead, hält
  dieses Ergebnis?
- Stille Fehler suchen — die, bei denen nichts abstürzt und das Ergebnis
  trotzdem falsch ist
- Statistik: p-Werte einordnen, Mehrfachtests, Stichprobengröße
- Wenn unklar ist, *was* überhaupt zu tun ist

**Die ehrliche Faustregel:** Eine Aufgabe, die Sonnet halb erledigt und die
danach noch einmal gemacht werden muss, kostet mehr als einmal Opus. Bei allem,
was mit Zahlen zu tun hat, auf die später eine Handelsentscheidung fußt, ist
Opus die günstigere Wahl. Bei Handwerk mit klarer Vorgabe ist es Sonnet.

**Nachdenkstufe:** Für die meisten Aufgaben reicht die Standardstufe. Erhöhen
lohnt bei Fehlersuche in still falschen Ergebnissen und bei Entwürfen, die
mehrere Bausteine gleichzeitig berühren.

## 7. Befehle

```bash
.venv\Scripts\python.exe -m pytest                      # 632 Tests, müssen grün sein
.venv\Scripts\python.exe -u desktop_app.py              # UI + Server
.venv\Scripts\python.exe -m ideas --probelauf           # Ideen erkennen, nichts schreiben
.venv\Scripts\python.exe werkzeuge\watchdog.py status
```

`python` im PATH ist nur der Microsoft-Store-Platzhalter — immer `.venv`.

## 8. Wo was liegt

| Bereich | Ort |
|---|---|
| Indikatoren, Levels, Marktprimitive, Struktur | `common/` |
| Backtest-Engine, Strategien, Kosten, Splits | `backtest/` |
| Ideen-Protokollierung | `ideas/` |
| Ausführung: Speicher, Risiko, Bot, Server | `execution/` |
| Rückblick auf Kontoregelwerke | `auswertung/` |
| Kerzen-Empfänger und Order-Kanal | `ntbridge/` |
| Werkzeuge (Import, Pine-Export, Watchdog) | `werkzeuge/` |
| NinjaScript | `ninjatrader/` + `HERKUNFT.md` |

## 9. Der nächste Schritt

Steht in `docs/OFFENE_PUNKTE.md` unter **P0**. Stand 30.08.2026:

1. Ende-zu-Ende-Probe des Orderwegs, sobald die Börse offen ist
2. Lucid-Zahlen bestätigen (alle sind derzeit **Annahmen**)
3. NT8-Historie importieren — das Werkzeug steht, der Export fehlt noch
