# CODE_CHAT_KONTEXT

**Technisches Langzeitgedächtnis des Projekts "Claude Chart Bot".**

Stand: 2026-08-23 (`walkforward`-Kommando, Abschnitt 22 — Masterplan X.2; davor
Basisvermessung der Strategiebibliothek, Abschnitt 21, wo `ib_breakout` als
stiller Ausfall auffiel und die Robustheitskennzahl log; Testsuite in der
Linux-Sandbox lauffähig gemacht, Abschnitt 20, Qualitätsmessung der
Dukascopy-Näherungshistorie, Abschnitt 19, und zwei bereinigte
Tradovate-Defekte; Inhalt sonst 2026-08-22 nach Entfernung des Legacy-Pfads).
Gegen den tatsächlichen Projektordner geprüft. **Testzahlen:** 361, gemessen am
23.08.2026 — allerdings in der Linux-Ersatzumgebung (Abschnitt 20), nicht unter
dem Windows-venv. Der Windows-Lauf bleibt vor einer Freigabe auszuführen.

---

## 0. Zweck und Verhältnis zur Schwesterdatei

**Es gibt genau zwei Kontextdateien.** Beide gehören zusammen ins Claude-Projekt:

| Datei | Rolle | Ändert sich |
|---|---|---|
| **`MASTERPLAN.md`** | **WOHIN**: Zielarchitektur, Research-Engine, Etappenplan bis zum Endzustand | selten |
| **CODE_CHAT_KONTEXT.md** (diese) | **WIE und WIE WEIT**: Architektur, Module, Implementierungsstand, Bugs mit Fundstelle, Tests, technische Entscheidungen, Blocker | bei Bauarbeiten |
| `NORMALER_CHAT_KONTEXT.md` | **WAS und WARUM**: Ziele, Anforderungen, Nutzerpräferenzen, Kostenrahmen, Kontostatus, Lucid-Regelwerk, Etappen A–F | selten |

Ergänzend im Projektordner, **nicht** zum Hochladen: `CLAUDE.md` (lädt Claude
Code automatisch) und `README.md`.

**Vorgängerdateien:** `PROJECT_CONTEXT.md` und `CURRENT_STATE.md` sind in diesen
beiden aufgegangen und entfernt.

---

## 1. AKTUELLER TECHNISCHER STAND

### Implementierungsstand nach Komponente

| Komponente | Stand | Getestet |
|---|---|---|
| `common/` | **fertig** | ja, umfangreich |
| `ntbridge/` (Empfänger + SQLite-Store) | **fertig** | ja, **mit echten NT8-Daten verifiziert** |
| `ninjatrader/ClaudeBridge.cs` v1.0.1 | **fertig** | **in NT8 kompiliert, läuft live** |
| `mcp_server/` (3 Tools) | **fertig, an Claude Desktop angebunden** | ja |
| `backtest/` | **fertig**, nur noch CSV-Quelle | ja, **nie auf echten Daten gerechnet** |
| `ideas/` (Etappe C) | **4 Setup-Familien fertig, Einstiegspunkt `python -m ideas` da**, aber noch in keiner Aufgabenplanung eingetragen | ja, 44 Tests |
| Etappe D, Lucid-Simulation | **existiert nicht** | — |

**Testsuite: 380 Tests, alle grün** (23.08.2026 auf Windows gemessen).
`.venv\Scripts\python.exe -m pytest`

| Datei | Tests |
|---|---|
| `test_ideas.py` | 50 |
| `test_mcp_snapshot.py` | 46 |
| `test_kosten.py` | 17 |
| `test_levels_structure.py` | 39 |
| `test_ntbridge.py` | 37 |
| `test_instruments_sessions.py` | 26 |
| `test_event_risk.py` / `test_patterns.py` | je 22 |
| `test_dukascopy.py` / `test_extended_indicators.py` | je 21 |
| `test_metrics_and_splits.py` | 18 |
| `test_engine.py` / `test_structure.py` | je 17 |
| `test_indicators.py` | 15 |
| `test_walkforward.py` | 12 |

Verlauf: 124 → … → 316 → 337 → 342 → 343 → 361 → **380**.

**Der Rückgang ist keine Regression.** Mit dem Legacy-Pfad fielen
`test_live_bot.py` (29) und `test_on_demand.py` (35) weg — 64 Tests für Code,
den es nicht mehr gibt. Gegengerechnet kamen 7 hinzu: der repo-weite
Kostentest, die von `candle_buffer_size` nach `ideas.bars` umgezogene
Puffer-Prüfung samt Gegenprobe, und die Tests zu `DeviationReentry`.
373 − 64 + 7 = 316.

**Erledigt: die offene Messung.** Eine frühere Fassung dieser Datei nannte
„erwartet 378 Tests" — gerechnet, nicht gemessen, weil jener Lauf in einem
Linux-Sandkasten stattfand und `pytest` dort nicht startete. Der Lauf auf
Windows ist nachgeholt; die Zahlen oben sind gemessen. Die 378 waren ohnehin
gegenstandslos, da sie den entfernten Legacy-Pfad mitzählten.

**Bekannte Flakiness:** `test_ntbridge.py::test_empfaenger_lehnt_falschen_pfad_ab`
fiel einmal mit `ConnectionAbortedError` (WinError 10053) aus und war isoliert
sowie im Wiederholungslauf grün. Socket-Timing unter Windows, kein Codefehler —
aber bei einem Fehlschlag zuerst wiederholen, bevor man sucht.

### Was seit dem 21.08.2026 nachweislich läuft

**Der komplette Live-Pfad steht:** NinjaTrader → `ClaudeBridge.cs` → ntbridge →
SQLite → MCP → Claude Desktop.

- ClaudeBridge in NT8 kompiliert, zwei Charts für **MNQ SEP26** (1m mit 5m/15m;
  Day 1 mit 1h).
- Über 6800 Kerzen angenommen, **0 abgelehnt**. Null Ablehnungen heißt: Zeitzone,
  Feldnamen und Umschlag zwischen C# und Python passen zusammen.
- Live-Bars mit **unter 2 Sekunden** Verzögerung.
- Zeitzone ohne Versatz (`W. Europe Standard Time`).
- MCP-Server in `claude_desktop_config.json` eingetragen und mit dem echten
  MCP-Client verifiziert: Handshake (Protokoll `2025-11-25`), drei Werkzeuge,
  realer Tool-Aufruf liefert Daten.

### Was nicht läuft bzw. nie lief

- **Kein Backtest auf echten Marktdaten.** Einzige Datendatei ist
  `data/DEMO_1m.csv`, ein synthetischer Zufallspfad. Daraus dürfen **keine**
  Aussagen über Strategiegüte abgeleitet werden.
- **Etappe C ist noch in keiner Aufgabenplanung eingetragen.** Der
  Einstiegspunkt `python -m ideas` existiert seit dem 22.08. und wurde als
  Probelauf gegen die echten Kerzen gefahren (Abschnitt 6.5), aber nichts ruft
  ihn regelmäßig auf. Es ist **noch keine einzige echte Idee protokolliert** —
  das bleibt Laurins Schritt auf dem Windows-Rechner.

### Bekannte Probleme

1. **Kein `.env` vorhanden.** Der MCP-Server startet trotzdem. Folge: ohne
   `FRED_API_KEY` liefert `get_event_risk` die **Termine** (Forex Factory braucht
   keinen Schlüssel), aber **keine Ist-Werte**.
2. **Tagesbar-Schluss ≠ letzter 1m-Schluss.** Für den 20.08. meldet die
   NT8-Tageskerze 29300.50, der letzte 1m-Schluss derselben Session 29317.00 —
   16,5 Punkte. Normal bei Futures (Settlement statt letztem Trade), aber
   relevant, falls Level je aus dem Tages- statt dem Intraday-Frame kommen.
3. ~~**MCP-Serverstart dauert ~7,5 Sekunden.**~~ **Behoben am 23.08.2026**,
   siehe Abschnitt 24. Handshake jetzt 1,73 s. Die frühere Beschreibung war in
   zwei Punkten falsch und steht unten korrigiert.

   *Ursprünglicher Text:* **MCP-Serverstart dauert ~7,5 Sekunden.** Gemessen über einen echten
   stdio-Handshake. Cowork und Code starten je eine **eigene** Kopie des Servers
   und laufen dabei in einen Timeout; Claude Desktop hält seine Instanz offen und
   ist deshalb unauffällig. Ursache ist fast ausschließlich der Importpfad
   (1190 Module): pandas dominiert, dahinter `mcp` und numpy. **Gebraucht wird
   pandas erst beim ersten Werkzeugaufruf, nicht für den Handshake** — ein
   verzögerter Import wäre die Abhilfe, ist aber noch nicht umgesetzt.

### Erledigt am 22.08.2026

- **Datenlücke 20.08. geschlossen.** Rund vier Stunden ab 16:00 CT fehlten in
  1m/5m/15m (193/39/13 Kerzen). Beim Öffnen von NinjaTrader lieferte die Bridge
  die Historie nach; der idempotente Speicher nahm sie ohne Duplikate auf.
  `pruefe_datenluecken.py` meldet jetzt **0 größere Lücken** über sieben Tage.
- **Die ältere Tagesserien-Lücke** (2026-07-31 → 2026-08-12) liegt außerhalb des
  Sieben-Tage-Fensters der Prüfung und ist damit **nicht** als erledigt belegt.
  Vor Aussagen über den 1d-ATR mit `--tage 0` gegenprüfen.
- **README um Etappe C ergänzt** (neuer Abschnitt 8, Abschnitte 8–14
  durchnummeriert). Dabei ein **Widerspruch aufgelöst**: beide Kontextdateien
  führten "README beschreibt nur den Tradovate-Pfad" als offenen Punkt, obwohl
  Commit `e932844` sie längst auf NinjaTrader/MCP umgestellt hatte. Die echte
  Lücke war eine andere: `ideas/` kam in der README überhaupt nicht vor. Der
  Punkt ist in `NORMALER_CHAT_KONTEXT.md` jetzt korrigiert.

### Erledigt am 22.08.2026 (Nachmittagslauf)

- **Einstiegspunkt `python -m ideas`** (`ideas/__main__.py`) — ein Einzellauf
  über die jüngsten Kerzen, gedacht für die Windows-Aufgabenplanung, nicht als
  Dauerprozess. Begründung im Modul-Docstring: ein Einzellauf ist zustandslos,
  der Speicher idempotent, ein Lauf zu viel schadet nicht.
- **Blackout-Schicht `ideas/kalender.py`** mit Abdeckungsgrenze
  (`ideas.filter.blackout_max_alter_tage`, Vorgabe 7 Tage).
- **`DeviationReentry`** in `backtest/strategies/base.py` — behebt eine
  Signalhäufung in `vwap_reversion` (Lehre 17).
- **Messung im Docstring von `DeviationReentry` nachgerechnet** und um ihre
  Grundlage ergänzt. Sie stimmt: 47 Signale in 10 Bewegungen, größte mit 11 —
  gilt aber nur für die **Long-Seite** bei Bündelung mit höchstens drei Kerzen
  Abstand. Beides stand vorher nicht dabei und wäre später nicht nachprüfbar
  gewesen.

### Override vom 23.08.2026 — Widerspruch festgestellt, nicht aufgelöst

Laurin hat angeordnet: **MNQ und NinjaTrader ausschließlich**, MGC und
Tradovate vollständig raus.

**Tradovate: erfüllt.** Der Legacy-Pfad ist am 22.08. entfernt; die beiden am
23.08. gemeldeten Restdefekte (`backtest/cli.py` bot `--provider tradovate` an,
`csv_provider.py` riet im Fehlertext zum Tradovate-Download) sind **behoben**.
Verblieben sind nur datierte historische Erklärungen im Code — sie begründen,
warum Dinge so sind, und bleiben bewusst stehen.

**Für MGC widerspricht der Code dem Override**, und das wird hier festgehalten
statt still bereinigt:

- MGC wird **nicht** protokolliert, gestreamt oder gespeichert — insoweit ist
  der Override bereits erfüllt.
- MGC steht aber im **Instrument-Register** (`common/instruments.py`) und in
  **14 Testfällen** (Gesamtzahl der Treffer am 23.08.: 43 in 14 Dateien, nach
  Kürzung von zuvor 48). Der MGC-Verfallstest ist der einzige, der beweist, dass
  `expiry_rule` instrumentspezifisch ist und nicht eine hartverdrahtete
  MNQ-Annahme (Bug-Lehre 9). Entfernt man ihn, kann die MNQ-Regel später still
  falsch werden.

**Empfehlung in `MASTERPLAN.md` C.2:** Register-Eintrag behalten, MGC aus
nutzersichtbaren Texten entfernen. **Entscheidung steht bei Laurin aus.**

### Bereinigung der Dokumentation (23.08.2026)

Einmal vollständig gegengeprüft, welche Dokumentationsdateien noch gebraucht
werden.

**Gelöscht:**

| Datei | Grund |
|---|---|
| `PROMPT_CLAUDE_CODE_ETAPPE_C.md` | Auftragsbeschreibung, mit der Etappe C am 21.08. beauftragt wurde. **Keine einzige Referenz** im Projekt; Inhalt durchgehend überholt (nannte 326 Tests, forderte das Anlegen des Git-Repos). Der historische Wert ist über `git log` erhalten, die Datei selbst stiftete nur Verwirrung neben `ETAPPE_C_SPEZIFIKATION.md`, die weiter gilt. |

**Geprüft und behalten** — alle vier werden aktiv referenziert:

| Datei | Warum sie bleibt |
|---|---|
| `ETAPPE_C_SPEZIFIKATION.md` | verbindliche Vorgabe, aus `CLAUDE.md`, `MASTERPLAN.md` und `ideas/setups.py` referenziert |
| `MASTERPLAN.md` | Zielarchitektur; aus Code heraus referenziert (`csv_provider.py`, `base.py` verweisen auf Abschnitt X.1) |
| `docs/BASISVERMESSUNG_2026-08-23.md` | datierter Messbericht, kein Duplikat — hält Zahlen fest, die sonst verloren wären |
| `docs/BACKTESTING_ENTSCHEIDUNG.md` | begründet die eigene Engine; verhindert, dass die Frage neu aufgerollt wird |

**Nicht vorhanden** (in älteren Aufträgen genannt, längst aufgegangen):
`PROJECT_CONTEXT.md`, `DECISIONS.md`, `CURRENT_STATE.md`,
`PROJEKTKONTEXT_UEBERGABE.md`.

**Zu prüfen, nicht angefasst:** `werkzeuge/` (`pytest_linux.py`,
`python_linux.py`, `dukascopy_export.py`) sind Hilfsskripte aus einer
Linux-Sandbox-Sitzung mit dokumentiertem Zweck. Ob sie auf dem Windows-Rechner
noch gebraucht werden, ist **unklar** — deshalb stehen sie, statt geraten zu
werden.

### Offene technische Aufgaben

1. `python -m ideas` in die Windows-Aufgabenplanung eintragen (mindestens
   täglich, besser stündlich — sonst greift die Blackout-Prüfung nicht, siehe
   6.5). Erst damit entstehen echte Ideen.
2. Die 8 weiteren Setup-Familien (Spezifikation 2.2), schrittweise.
3. Etappe D: `evaluate_past_ideas`, `get_performance_report`.
4. Lucid-Regelsimulation.
5. MCP-Startzeit: pandas verzögert importieren.
6. Etappe E: Dauerbetrieb-Härtung.

---

## 2. Gesamtarchitektur und Datenfluss

```
NinjaTrader 8 Chart
  └─ ClaudeBridge.cs   Indikator, KEINE Strategy
     │                 AddDataSeries -> mehrere Timeframes aus EINER Instanz
     │                 fire-and-forget, Timeout, Zwischenspeicher
     └─ HTTP POST {"bars":[...]} -> 127.0.0.1:8787/bars
        └─ ntbridge/receiver.py     nur localhost, exklusiv gebunden
           └─ ntbridge/store.py     SQLite WAL, idempotent
              └─ mcp_server/        Level, Indikatoren, Struktur, Muster
                 └─ Claude Desktop  <- Interpretation NUR hier
```

Daneben liest `ideas/` denselben Speicher und protokolliert regelbasiert
(Abschnitt 6). **Keiner der beiden Wege ruft die Anthropic-API auf** — seit dem
22.08.2026 für das gesamte Repository getestet (Abschnitt 5.3).

**Der Legacy-Pfad (Tradovate → `live_bot/` → Anthropic-API → Telegram) ist am
22.08.2026 entfernt worden**, Abschnitt 7.

---

## 3. Modul-Referenz

### `common/`

| Datei | Inhalt |
|---|---|
| `indicators.py` | **Zentrale Invariante.** `compute_indicators` = Hot Path (`rsi, atr, vwap, sma_fast, sma_slow`, Vortagesmarken, Flaggen). `compute_extended_indicators` ergänzt `macd`, `stochastic`, `adx`, `bollinger`, `ema_stack` |
| `sessions.py` | CME-Session, 18:00-ET-Rollover, `session_dates`, `session_bounds`, `session_context`, Liquiditäts- und Dünnzonenfenster |
| `instruments.py` | 8 Instrumente (MNQ, MGC, MES, ES, NQ, SIL, ZN, M6E) mit `expiry_rule` |
| `levels.py` | `compute_levels()`, `history_dependent_metrics()`, `volume_profile()`, **`initial_balance_per_session()`** |
| `structure.py` | Swings, S/R-Zonen, `classify_market_structure` (BOS/CHoCH), `detect_rsi_divergence` |
| `patterns.py` | Flagge, Dreieck, Doppeltop/-boden, Range-Kompression, Kerzenmuster an Leveln |
| `contracts.py` | **neu 21.08.2026** — `Contract` (id, name, expiry), brokerneutral |
| `config.py` | `Config.validate()` mit abbrechenden Startprüfungen |
| `logging_setup.py` | `log_event` mit positions-only Parametern |

### `ntbridge/`

| Datei | Inhalt |
|---|---|
| `receiver.py` | `_ExklusiverServer` (kein Port-Reuse unter Windows), `laeuft_bereits()`, `POST /bars`, `GET /status` |
| `store.py` | SQLite WAL, Schlüssel `(instrument, timeframe, ts_utc)`, idempotent, `validate_bar()` mit benannten Ablehnungsgründen |
| `__main__.py` | Startprüfungen: nur localhost, kein zweiter Empfänger |

### `mcp_server/`

| Datei | Inhalt |
|---|---|
| `server.py` | drei Tools: `get_market_snapshot`, `get_event_risk`, `list_instruments` |
| `snapshot.py` | `build_snapshot_payload()`, **`_vorsession_vollstaendig()`** |
| `bars.py` | `BarSet`, `LoadedBars`, `BarSource`-Protokoll, `NTBridgeBarSource` |
| `calendar_provider.py` | Forex Factory (Termine) + FRED (Ist-Werte) |
| `context.py` | langlebiger Zustand, kein Login, keine Zugangsdaten |
| `cli.py` | Terminal-Dump (`snapshot`, `levels`) |

### `ideas/` — Etappe C

| Datei | Inhalt |
|---|---|
| `setups.py` | **Setup-Bibliothek.** 4 Familien, jede auf eine `RuleStrategy` abgebildet. `pruefe_konfiguration()` bricht bei unbekanntem Schlüssel oder durchweg abgeschalteten Familien ab |
| `__main__.py` | `python -m ideas` — ein Protokollierungslauf, `--probelauf`, `--kein-kalender` |
| `erkennung.py` | läuft über die Kerzen und wertet die Regel-Objekte über `BarContext` aus; `pruefe_spalten()`, `Erkennungsbericht` |
| `filters.py` | vier Filter, **drei** Ausgänge (durch / abgelehnt / nicht prüfbar), `Filterbilanz.kontext` |
| `model.py` | `TradeIdee` (Haupt-Log), `Beobachtung` (Exploration-Log), `berechne_crv` |
| `store.py` | SQLite, Tabellen `ideen` und `observations` |
| `pipeline.py` | `vorbereiten()`, `baue_idee()`, `protokolliere()` (mit `nur_rechnen` für den Probelauf) |
| `kalender.py` | `KalenderBlackout` — Abdeckungsgrenze vor `CalendarService`; kennt nur ein Protokoll, **nicht** `mcp_server` |
| `__main__.py` | Einzellauf-CLI: `--probelauf`, `--kein-kalender`, `--symbol`, `--bars`. Verdrahtet den Kalender als **einzige** Stelle mit `mcp_server`-Import |

**`detectors.py` gibt es nicht mehr** — sie war die zweite Signal-Implementierung
(Abschnitt 6). Ein Test verhindert ihre Rückkehr.

---

## 4. Konfiguration

`config.yaml`: `tradovate`, `market`, `indicators`, `alerts`, `claude`,
`on_demand`, `ntbridge`, **`ideas`**, `event_risk`, `notify`, `logging`,
`backtest`.

**Vorrang:** CLI > `.env` > YAML. Schwellenwerte nur in der YAML, Secrets nur in
`.env`.

### Namensfalle

`config.yaml` enthält `environment: demo` **unter `tradovate:`** — das ist die
Broker-Umgebung, **nicht** die Kontoumgebung aus `ideas.profil`.

Genau deshalb heißt der Vorgabewert dort **`sim_frei`** und nicht `demo`: ein
eigener Wertebereich macht die Verwechslung unmöglich. Erlaubt sind
`sim_frei`, `lucid_challenge`, `lucid_funded` (`ideas.profile_erlaubt`);
`Config.validate()` bricht bei allem anderen ab — ein Tippfehler würde die
spätere Auswertung sonst still in zwei Gruppen zerlegen.

### Claude-Desktop-Anbindung

`%APPDATA%\Claude\claude_desktop_config.json`:

```json
"mcpServers": {
  "claude-chart-bot": {
    "command": "C:\\Users\\lm130\\Desktop\\Claude chart bot\\.venv\\Scripts\\python.exe",
    "args": ["-m", "mcp_server"],
    "cwd": "C:\\Users\\lm130\\Desktop\\Claude chart bot",
    "env": { "PYTHONPATH": "C:\\Users\\lm130\\Desktop\\Claude chart bot" }
  }
}
```

**Gemessen, nicht vermutet:** aus fremdem Arbeitsverzeichnis gestartet
funktioniert `cwd` allein, `PYTHONPATH` allein — **weder noch schlägt fehl**.
Beide gesetzt, weil Claude Desktop `cwd` je nach Version unterschiedlich
behandelt. Eine `.env` ist zum Start **nicht** nötig.

Einstiegspunkt ist `python -m mcp_server` (`__main__.py` →
`server.run(transport="stdio")`), **nicht** `python mcp_server/server.py` — das
zerbricht die Paketimporte.

---

## 5. Technische Entscheidungen mit Begründung

### 5.1 Eine einzige Indikator-Implementierung

`compute_indicators` wird von Live-Bot **und** Backtest aufgerufen. Eine zweite
Rechenlogik hieße, dass der Backtest eine andere Strategie testet als die, die
live läuft.

**Sie gilt auch für die Signal-Logik, nicht nur für die Indikatoren.** Das war
der Grund, den Etappe-C-Zwischenstand zu ersetzen statt fortzuschreiben
(Abschnitt 6): `ideas/detectors.py` war eine zweite Fassung der Erkennung.
`ideas/setups.py` bildet jetzt jede Familie auf eine `RuleStrategy` aus
`backtest/strategies/` ab, und ein Test prüft das.

### 5.2 Eigene Backtest-Engine

`docs/BACKTESTING_ENTSCHEIDUNG.md`. `backtesting.py` hat kein Futures-Modell
(Kommission prozentual statt USD je Seite, keine Kontraktmultiplikatoren);
`vectorbt` macht zustandsabhängige Regeln schwer debugbar.

### 5.3 Transitiv prüfender Kostentest (seit 22.08. repo-weit)

Bis 21.08.2026 importierte `bars.py` fünf `live_bot`-Module, gebraucht nur von
`TradovateBarSource`. Der Kostengarantie-Test prüfte je Datei nur deren **eigene**
Importzeilen gegen eine Verbotsliste, über `glob("*.py")`.

Die Zusage lautet aber nicht „importiert nichts Verbotenes direkt", sondern
**„von hier aus ist kein Anthropic-Aufruf erreichbar"**. Sie galt durch Glück:
ein einziger neuer Import in einem der fünf Module hätte sie gebrochen, der Test
wäre grün geblieben.

Jetzt: `TradovateBarSource` entfernt, `Contract` nach `common/contracts.py`,
Test rechnet die **transitive Hülle** (`rglob`) und nennt im Fehlerfall den
vollständigen Importweg.

### 5.4 SQLite im WAL-Modus

Zwei Prozesse (Empfänger schreibt, MCP liest). Der Speicher **ist** der
ursprünglich verschobene Bar-Cache.

### 5.5 Indikator statt NinjaScript-Strategy

Ein Indikator *kann* in NinjaTrader keine Orders platzieren. Die Order-Sperre ist
damit in der Architektur verankert, nicht nur vereinbart.

### 5.6 Zwei Charts je Instrument

Sekundärserien aus `AddDataSeries` erben „Days to load". Deshalb: Intraday-Chart
(Minute 1, Zusatz `5,15`) und Tages-Chart (Day 1, Zusatz `60`). Session Template
**ETH**, nicht RTH — sonst kämen Vortagesmarken nur aus 08:30–15:15 CT. Kein
Fehler, keine Warnung, nur andere Zahlen.

### 5.7 `BarsPeriodType.Day` statt 1440 Minuten

1440-Minuten-Bars folgen nicht der Session-Definition des Kontrakts; die beiden
liegen um Stunden auseinander. Die Bridge lehnt 1440 aktiv ab, mit Log-Meldung.

### 5.8 Kein Delta-Pfad

`store.py` hat keine Bid-/Ask-Spalten. Delta bleibt null **mit Begründung** und
wird nie geschätzt — eine Schätzung sähe aus wie eine Messung.

### 5.9 `log_event` mit positions-only Parametern

Sonst kollidiert ein Payload-Feld `message` mit dem Positionsparameter, und zwar
im Fehlerpfad.

---

## 6. Etappe C: gebaut am 22.08.2026

`ETAPPE_C_SPEZIFIKATION.md` liegt seit dem 22.08. **im Projektordner** (vorher
nur im normalen Chat, was einen halben Tag Rätselraten gekostet hat). Sie ist
die Vorgabe; Abschnitt 4 (Rolle des `profil`-Felds) ist inzwischen geklärt.

Der Zwischenstand vom 21.08. (`739cd1c`) wurde **nicht fortgeschrieben**,
sondern in den abweichenden Punkten ersetzt:

| Punkt | Zwischenstand | jetzt |
|---|---|---|
| **Signal-Logik** | eigene Erkenner in `detectors.py` | Regel-Objekte aus `backtest/strategies/` |
| Logs | nur `ideas` | zusätzlich `observations`, gesperrt gegen die Auswertung |
| Herkunftsfeld | fehlte | `quelle` = `regel` / `manuell_assistiert` |
| Primärschlüssel | `(instrument, setup, ts_utc)` | `idea_id` PK + UNIQUE-Index |
| Setup-Schlüssel | Richtung im Namen | eine Familie je Schlüssel, Richtung als Spalte |
| Freitext | fehlte | `notiz` |
| Tests | bewusst keine | 36 |

### 6.1 Die Spezifikation ordnete zwei Familien falsch zu

Sie behauptet (Abschnitt 2.1), alle vier Setups existierten bereits als
Backtest-Strategien. Für zwei stimmt das nicht:

- `rsi_mean_reversion` ist eine RSI-Mittelwertrückkehr und hat mit der
  **Initial Balance** nichts zu tun.
- `vwap_trend` ist Trendfolge (Einstieg **mit** der VWAP-Kreuzung), während
  `vwap_reversion` die Gegenbewegung **zurück** zum Anker meint.

Statt die Zuordnung zu übernehmen, wurden `ib_breakout` und `vwap_reversion`
als Fabriken in `library.py` ergänzt — im bestehenden Regel-Framework, damit
beide auch im Backtest rechenbar sind. Dafür drei neue Regel-Objekte in
`base.py`: `Rising`, `Falling`, `PreviousDeviationExceeds`.

### 6.2 `profil` ist Herkunft, kein Steuerungsfeld

Wert ist **`sim_frei`**, nicht `demo` — `demo` wäre mit `tradovate.environment`
verwechselbar (die Namensfalle aus Abschnitt 4). Erlaubte Werte stehen in
`config.yaml` unter `ideas.profile_erlaubt`; `Config.validate()` bricht bei
allem anderen ab.

Die Unterscheidung, auf die es ankommt:

| | hält fest | wann |
|---|---|---|
| `profil` (Feld an der Idee) | was **tatsächlich** war — welches Konto | beim Protokollieren |
| `rules` (Parameter von `evaluate_past_ideas`) | was **gewesen wäre** — welches Regelwerk | beim Auswerten |

`lade_fuer_auswertung()` filtert deshalb **nicht** nach `profil`, außer man
verlangt es ausdrücklich.

### 6.3 Was bewusst NICHT gespeichert wird

Kein Ergebnisfeld (Gewinn/Verlust). Das entsteht erst durch
`evaluate_past_ideas` unter einem bestimmten Regelwerk — stünde es im Log,
gäbe es zwei Wahrheiten, je nachdem wann man hinschaut.

Damit die Auswertung trotzdem **nachspielen** kann, tragen Ideen
`atr_referenz`, `stop_atr` und `ziel_atr` mit: der tatsächliche Einstieg ist
die Eröffnung der Folgekerze, nicht der gespeicherte Schlusskurs. Ohne diese
drei Felder wäre das R-Vielfache nicht rekonstruierbar.

### 6.5 Nachvollziehbarkeit ist geprüft, nicht behauptet

Spezifikation Abschnitt 5, Schritt 3 — seit 22.08.2026 erfüllt.
`ideas/nachvollzug.py` rechnet eine gespeicherte Idee gegen die vorbereiteten
Kerzen zurück und meldet jede Abweichung einzeln:

1. Zur `erstellt_utc` existiert eine Kerze.
2. `entry` ist deren Schlusskurs.
3. `atr_referenz` ist deren ATR.
4. `stop` und `ziel` ergeben sich aus `entry` und den ATR-Faktoren.
5. **Die Einstiegsregel war auf jener Kerze tatsächlich erfüllt.**

Punkt 5 ist der Kern. Die ersten vier prüfen Arithmetik — eine frei erfundene
Zeile, deren Zahlen zueinander passen, bestünde sie alle. Ein Test setzt genau
so eine Zeile auf eine ruhige Kerze und weist nach, dass sie durchfällt.

Gegen echte MNQ-Daten: **39 von 39** protokollierten Ideen nachvollziehbar.

### 6.4 Noch offen

Die **8 weiteren Familien** aus Spezifikation 2.2 (BOS, CHoCH, RSI-Divergenz,
Doppeltop/-boden, Dreieck, Range-Kompression, Gap-Fill, Gap-and-Go) sind
bewusst nicht gebaut — die Spezifikation empfiehlt schrittweise, und keine
davon ist gegen echte Daten geprüft.

`protokolliere()` hängt an **keinem Dauerprozess**. Es ist noch keine einzige
echte Idee protokolliert.

---

## 7. Legacy-Pfad entfernt (22.08.2026)

**Entschieden und umgesetzt.** Diese Frage stand seit dem 21.08.2026 offen, weil
der Satz *„tradovate ist raus brauche dazu nichts mehr"* nicht eindeutig deckte,
wie weit die Entfernung reichen sollte. Laurin hat am 22.08.2026 ausdrücklich
entschieden: der gesamte Pfad geht.

Entfernt in vier Commits auf dem Branch `legacy-entfernen`:

| Was | Umfang |
|---|---|
| `live_bot/` | 20 Dateien, 3868 Zeilen |
| `backtest/data/tradovate_provider.py` | samt Registrierung in der Factory |
| `tests/test_live_bot.py`, `tests/test_on_demand.py` | 64 Tests |
| `config.yaml` | Abschnitte `tradovate`, `alerts`, `claude`, `notify` |
| `common/config.py` | 6 Klassen, `with_environment`, `require_tradovate` |

`Secrets` trägt nur noch `FRED_API_KEY`.

### 7.1 Zwei Dinge, die dabei NICHT verlorengehen durften

**Der `on_demand`-Abschnitt konnte nicht ersatzlos weg.** Die Arbeitsanweisung
nannte ihn unter den zu löschenden, aber `mcp_server/snapshot.py` liest von dort
Swing-Stärke, Lookback, Zonen und Trendparameter. Nach der Rangfolge schlägt der
Code die Anweisung — deshalb behalten, auf die sechs tatsächlich genutzten
Felder eingedampft und zu **`analyse`** umbenannt. Ein Abschnitt, der nach dem
gelöschten `/analyse`-Kommando des Telegram-Bots heißt, wäre irreführend.

**Die Vortagesmarken-Zusicherung ist umgezogen, nicht gestrichen.** Sie hing an
`market.candle_buffer_size` und den Vortages-Alarmen. Der Alarmpfad ist weg, die
Gefahr nicht: bleiben `prev_session_high`/`-low` NaN, löst `pdh_pdl_bruch`
**nie** aus, ohne Fehlermeldung. `Config.validate()` prüft das jetzt an
`ideas.bars`, skaliert nach `ideas.timeframe`.

`market.candle_buffer_size` und `warmup_bars` bleiben als Felder erhalten, werden
aber **von keinem laufenden Prozess mehr ausgewertet** — der MCP-Server holt über
`DEFAULT_BAR_COUNTS`, die Ideen-Protokollierung über `ideas.bars`.

### 7.2 Verlorene Zusicherungen aus `test_on_demand.py`

Mit der Datei sind drei Zusagen entfallen, die vorher einzeln getestet waren:
Disclaimer in der Claude-Antwort, Schlüsselmenge der Payloads, Verbot direkter
Handelsempfehlungen.

Sie sind **durch Entfernung gegenstandslos**, nicht ungeprüft: es gibt keinen
Claude-Aufruf mehr, den sie absichern könnten. An ihre Stelle tritt der
repo-weite Kostentest (Abschnitt 9) — er sichert die stärkere Zusage, dass
überhaupt nirgends mehr ein Anthropic-Import steht.

## 8. Bugs und Fehlerlehren

Alle von derselben Art: **sieht aus wie „kein Signal", ist aber „Messung
kaputt"**.

| # | Fehler | Schutz im Code |
|---|---|---|
| 1 | `candle_buffer_size: 500` bei 23-h-Session → `prev_session_high` dauerhaft NaN, zwei Alarme hätten **nie** ausgelöst | Defaults 3000/2880 + `Config.validate()` bricht ab |
| 2 | OOS-Block isoliert vorbereitet → erste ~50 Kerzen ohne SMA50 | `prepare_split()`, `assert_in_sample_only` |
| 3 | Tagesaddition auf dem Zeitstempel statt auf dem Datum | `sessions.py` rechnet auf dem Datum |
| 4 | Squeeze über „unterstes Perzentil" wird zur eigenen Referenz | Keltner-Containment |
| 5 | Range-Kompression 20 vs. 60 Bars: √(20/60)≈0,58 < Schwelle 0,6 | gleich lange Fenster |
| 6 | Kalenderausfall hätte „keine Termine" bedeutet — eine **Freigabe** | `calendar_available: false` |
| 7 | Terminsortierung lag beim Provider | Sortierung im Service |
| 8 | `FastMCP` heißt in mcp 2.0 `MCPServer`; `sys.stdout = sys.stderr` hätte den Kanal zerstört | AST-Test |
| 9 | MGC-Verfall nicht wie MNQ (19.12. vs. 29.12.) | `expiry_rule` im Register |
| 10 | Feldnamen/Umschlag der Bridge ohne Compiler-Schutz | bei jeder C#-Änderung gegen `store.py` prüfen |
| **11** | **Vortagesmarken aus angeschnittener Session** | **`_vorsession_vollstaendig()`** |
| **12** | **Zweiter Empfänger lief still daneben** | **`laeuft_bereits()` + `_ExklusiverServer`** |
| **13** | **Kostengarantie-Test prüfte nur direkte Importe** | **transitive Hülle** |
| **15** | **Schichtumkehr zog `backtest` in die MCP-Importhülle** | **Prüfung nach `ideas.setups` verschoben** |
| **16** | **UTF-8-BOM ließ den AST-Test scheitern** | **BOM entfernt, ASCII-Konvention** |
| **17** | **`flaggen_ausbruch` konnte nie auslösen** | **Schwelle aus der Verteilung abgeleitet (8.17)** |
| **18** | **Ein-Minuten-Versatz in der Dukascopy-Quelle** | **`label="right"`, Abschnitt 14.2** |

Die Nummern folgen den Unterabschnitten; **14 fehlt in der Tabelle**, weil
8.14 („Gegenprobe als Methode") kein Bug ist, sondern ein Arbeitsprinzip.

### 8.15 Schichtumkehr (behoben, `142fd11`)

Die Startprüfung der Setup-Schlüssel stand zuerst in `Config.validate()` und
importierte dafür `ideas.setups`. Das ist eine **Schichtumkehr** — `common` ist
die Basis, `ideas` liegt darüber — und hatte eine Nebenwirkung, die niemand
beabsichtigt hatte: über diesen Import zog der MCP-Server `ideas` **samt
`backtest.strategies`** in seine Importhülle.

Aufgefallen ist es nur, weil der Kostengarantie-Test die transitive Hülle
rechnet (Lehre 13). Ohne ihn wäre die Hülle still gewachsen.

Jetzt: `ideas.setups.pruefe_konfiguration()`, aufgerufen von
`pipeline.protokolliere()`. In `Config.validate()` bleibt nur, was ohne
Fachwissen prüfbar ist (Profil gegen `profile_erlaubt`, „mindestens eine
Familie aktiv"). Ein eigener Test hält `Config.validate` frei von
`ideas`-Importen.

### 8.16 BOM in einer Quelldatei — Ursache gefunden

`backtest/strategies/library.py` trug plötzlich ein UTF-8-BOM, das aus keinem
Commit stammte. Folge: `ast.parse` warf `SyntaxError: invalid non-printable
character U+FEFF`, und **beide** Kostengarantie-Tests fielen aus, ohne dass an
ihrer Zusage etwas dran war.

**Die Ursache stand am 22.08.2026 fest:** `Set-Content -Encoding UTF8` schreibt
unter **Windows PowerShell 5.1 grundsätzlich mit BOM**. Aufgefallen ist es beim
Zurücknehmen einer Gegenprobe — dieselbe Datei war danach kaputt, obwohl der
Inhalt stimmte.

**Regel daraus:** Quelldateien nie über `Set-Content` zurückschreiben, sondern
über `git checkout <datei>`. Für Änderungen die Datei-Werkzeuge nehmen.

Zweite Lehre: Ein Fehlschlag im Importhüllen-Test kann eine **Parse**-Ursache
haben statt einer fachlichen. Erst die Fehlermeldung lesen, dann suchen.

### 8.17 `flaggen_ausbruch` konnte nie auslösen (behoben, 22.08.2026)

**Der Befund.** `indicators.flag.consolidation_max_atr` stand auf `1.2`. Die
Bedingung lautet `range_width <= consolidation_max_atr * atr`, der Wert ist also
eine Obergrenze für `Range/ATR`. Gemessen:

| Zeitebene | n | Minimum | p10 | p25 | Median |
|---|---|---|---|---|---|
| MNQ 1m | 4312 | 1,08 | 2,08 | 2,46 | 3,02 |
| MNQ 5m | 850 | **1,37** | 2,11 | 2,47 | 2,92 |
| MNQ 15m | 323 | 1,40 | 1,91 | 2,31 | 2,77 |
| CFD 5m | 12243 | 0,50 | 2,02 | 2,40 | 3,02 |

`flag_in_consolidation` war **0 von 864** auf 5m. Das Setup stand als `aktiv`
in der Config und lieferte garantiert nichts — die Protokollierung meldete
0 Signale, was aussieht wie „kein Setup aufgetreten", tatsächlich aber
„Bedingung unerfüllbar" war.

> **Korrektur einer früheren Aussage in dieser Datei:** Es hieß hier, die
> Schwelle stamme aus der 1m-Konfiguration. Die Messung widerlegt das — die
> Verteilung ist über alle Zeitebenen nahezu gleich (Median 2,77–3,02). `1.2`
> war auf **keiner** Zeitebene praktikabel.

### 8.17.1 Wie der neue Wert zustande kam

**Genehmigung.** Laurin hat das Setzen **dieses einen** Werts ausdrücklich
erlaubt („hab da auch keine Ahnung"). Das ist eine benannte Ausnahme von der
Regel, dass Setup-Parameter Trading-Logik sind und ihm vorgelegt werden —
**andere Setup-Parameter bleiben rückfragepflichtig.** Es war keine
eigenmächtige Entscheidung.

**Methode.** Nicht geraten, sondern aus der Verteilung abgeleitet:

1. `Range/ATR` über beide Datenquellen gemessen. Beide Verteilungen stimmen
   auf **0,07** überein (MNQ p25 = 2,47, CFD p25 = 2,40) — die Kennzahl ist
   normiert und überträgt sich, was die breitere CFD-Stichprobe rechtfertigt.
2. Auslösehäufigkeit je Kandidat auf **12 871 Kerzen über 107 Tage** gemessen,
   nicht auf den 3 Tagen MNQ-Historie. Dort sprang die Zahl zwischen 2,40 (null
   Ausbrüche) und 2,47 (drei) — ein reines Kleinstichproben-Artefakt, nach dem
   man nicht wählen darf.
3. Gewählt: **p25 = 2,40**, der niedrigere und damit selektivere der beiden
   Werte, aus der größeren Stichprobe.

| Schwelle | Ausbrüche/Woche | Wochen bis 20 je Richtung |
|---|---|---|
| 1,20 (vorher) | 0,3 | 152 |
| 2,00 (p10) | 3,7 | 10,7 |
| **2,40 (p25)** | **7,4** | **5,4** |
| 3,00 (Median) | 12,6 | 3,2 |

Die Definition ist begründbar: **das engste Viertel der Konsolidierungen gilt
als „eng"** — selektiv, ohne extrem zu sein. Die ~5 Wochen bis zu Laurins
eigener Schwelle von 20 Ideen je Kategorie passen zur Projektprämisse „nach
einigen Wochen auswerten".

**Was der Wert nicht ist.** Keine getestete Trading-Entscheidung. Er legt
fest, wie oft das Setup künftig auslöst, nicht ob es trägt — das beantwortet
erst Etappe D. Änderbar in `config.yaml`, ohne Codeänderung.

**Wirkung, gemessen.** Auf 1m: 368 enge Phasen, **25 Ausbrüche** (vorher 0/0).
Auf 5m: 45 enge Phasen, 0 Ausbrüche in den vorhandenen 3 Tagen — bei
geschätzten 7/Woche ein plausibler Zufall, kein Fehler. Die Bedingung ist
damit **erfüllbar** statt strukturell tot.

`test_flaggen_schwelle_ist_ueberhaupt_erfuellbar` hält eine grobe Untergrenze
(1,4) fest. Sie erzwingt keinen bestimmten Wert, verhindert aber die Rückkehr
eines unerreichbaren. Gegenprobe durchgeführt: bei 1,2 fällt der Test.

### 8.11 Vortagesmarken (behoben, `cd5bcc6`)

`_spans_two_sessions()` zählte verschiedene Session-**Daten**. Ein auf 1500 Bars
gedeckelter 1m-Frame umfasst ~25 h, berührt damit zwei Session-Daten, enthält die
ältere aber nur zu einem Bruchteil.

Belegt an echten MNQ-Daten:

| Frame | prev_day_high |
|---|---|
| 1m, limit=1500 (25 h) | **29686.75** ← falsch |
| 1m vollständig / 5m / 15m | 29688.50 |
| NT8-Tageskerze 20.08. | 29688.50 |

Hier 1,75 Punkte, **nach oben nicht begrenzt** — fällt das echte Hoch früh in die
Session, liegt der Wert beliebig weit daneben. Verschärfend: der Snapshot wies
`deckt_zwei_sessions: true` aus, versicherte also aktiv etwas Falsches. Das Feld
heißt jetzt `vorsession_vollstaendig`.

### 8.12 Zweiter Empfänger (behoben, `4af9df3`)

`ThreadingHTTPServer` setzt `allow_reuse_address = 1`. Unter Linux betrifft das
nur Sockets in TIME_WAIT; unter **Windows** erlaubt SO_REUSEADDR das Binden auf
einen Port, den ein anderer Prozess **aktiv** bedient. Ein zweiter Start meldete
„Empfaenger laeuft" und bekam nie eine Kerze — wer nach einer
Konfigurationsänderung neu startete, arbeitete still mit den alten Einstellungen
weiter. Das erklärt auch das drei Wochen alte Datum in `/status`.

Zwei Riegel: aktive `/status`-Probe vor dem Binden (nennt Startzeit, Kerzenzahl
und Datenbank des laufenden Prozesses) **und** `allow_reuse_address = False`
unter Windows.

### 8.13 Testdaten-Fehler (dauerhaft relevant)

Mehrere Testfehlschläge lagen an **fehlerhaften Testdaten**, nicht am Code:
Zigzag stieg je Schritt mehr als er zurücksetzte; degenerierter ADX-Sägezahn;
die Prämisse „EMA-Stack ist in Rauschen selten" war falsch (58 % gestapelt — ein
**Form-**, kein Stärkesignal); Session-Grenzen in VWAP-Tests falsch ausgerichtet.

**Regel:** Schlägt ein Test fehl, zuerst prüfen, ob die Testdaten die Bedingung
überhaupt erfüllen können. Assertions nicht abschwächen, um grün zu werden.

### 8.14 Gegenprobe als Methode

Seit dem 21.08.2026 wird jeder Regressionsfix so abgesichert: die alte,
fehlerhafte Implementierung wird **testweise wieder eingesetzt** und geprüft, ob
die neuen Tests fallen. Ein Test, der vorher und nachher grün ist, beweist
nichts.

Durchgeführt für 8.11 (4 von 6 Tests fallen), 8.12 (Test **hängt** — `main()`
bindet dann und geht in `serve_forever()`; steht als Hinweis im Test), 8.13
(beide Tests fallen und melden den vollen Importweg) und die
IB-Lookahead-Sperre (Kerze um 09:30 kennt sonst `ib_high` von 10:30).

---

## 9. Tests: was einzelne Tests zusichern

**Nicht entfernen:**

- `test_kein_modul_im_projekt_erreicht_die_anthropic_api` — seit 22.08.2026
  **repo-weit**, nicht mehr nur `mcp_server/`. Sichert die Kostenanforderung.
  Gegenprobe beim Bau durchgeführt: ein testweise eingefügtes
  `import anthropic` lässt ihn fallen.
- `test_kein_modul_im_projekt_importiert_live_bot` — ein verbliebener Import
  wäre ein ImportError zur Laufzeit, den kein Test bemerkt, solange das Modul
  nicht angefasst wird.
- AST-Test gegen `sys.stdout = sys.stderr`.
- `test_kein_lookahead_...` — Backtest-Ausführungsmodell.
- `test_angeschnittene_vorsession_gilt_nicht_als_vollstaendig` und
  `test_levelframe_ueberspringt_angeschnittenen_timeframe`.
- `test_zweiter_start_bricht_ab_statt_still_danebenzulaufen`.
- `test_initial_balance_ist_waehrend_des_fensters_noch_nicht_bekannt`.
- ~~Tests auf Schlüsselmenge der Claude-Payloads, Disclaimer und Verbot
  direkter Handelsempfehlungen~~ — mit `test_on_demand.py` entfallen. **Durch
  Entfernung gegenstandslos**, nicht ungeprüft: es gibt keinen Claude-Aufruf
  mehr, den sie absichern könnten. Ersetzt durch den repo-weiten Kostentest
  (Abschnitt 7.2).

Aus `test_ideas.py` (Etappe C):

- `test_jede_setup_familie_verweist_auf_eine_backtest_strategie` — die
  tragende Invariante 5.1, als Prüfung statt als Absichtserklärung.
- `test_ideas_modul_hat_keine_eigenen_erkenner_mehr` — verhindert die Rückkehr
  von `detectors.py`.
- `test_auswertung_liest_niemals_das_exploration_log` — Quelltextprüfung, dass
  `lade_fuer_auswertung` die Tabelle `observations` nicht einmal nennt.
- `test_config_validate_zieht_ideas_nicht_in_die_importhuelle` — Lehre 14.
- `test_fehlende_spalte_bricht_laut_ab_statt_still_zu_schweigen` — ohne sie
  bliebe ein Setup bei fehlender Spalte stumm.
- `test_erkennung_sieht_nie_in_die_zukunft` und
  `test_ib_bruch_loest_vor_ablauf_des_ib_fensters_nicht_aus`.
- `test_gueltige_minimalkonfiguration_kommt_durch` — Gegenprobe zu den
  Startprüfungen: ohne sie blieben die grün, auch wenn `validate()` aus einem
  ganz anderen Grund immer würfe.

**Testdaten tragen eigene Zusicherungen.** Beispiel: der Vorsession-Test prüft
selbst, dass der gedeckelte Frame weiterhin zwei Session-Daten berührt — sonst
träfe er den gemeldeten Fehler gar nicht.

---

## 10. Bekannte Einschränkungen

| Einschränkung | Grund | Umgang |
|---|---|---|
| Volume Profile ist Näherung | braucht Tickdaten | `naeherung: true` |
| Delta dauerhaft null | „Order Flow +" nicht lizenziert | `null` mit Begründung, **nie geschätzt** |
| Sekundärserien erben „Days to load" | NT8-Verhalten | Zwei-Charts-Layout; Bridge warnt |
| Antwortzeit 10–30 s | MCP-Roundtrip | Nutzen in Vorbereitung und Auswertung |
| Historienabhängige Felder brauchen Zeit | `SESSIONS_REQUIRED` 5/2/10/20 | `null` + Fortschritt (`11/20 Sessions`) |
| ISM/PMI ohne Ist-Wert | FRED-Lizenz zurückgezogen | Feld leer mit Begründung |
| Forex Factory inoffiziell, **kein `actual`-Feld** | — | FF = Termine, FRED = Ist-Werte |

---

## 11. Umgebung und Befehle

Windows 11, Projekt unter `C:\Users\lm130\Desktop\Claude chart bot`.
Python 3.14.6, venv im Projekt. **`python` im PATH ist nur der
Microsoft-Store-Platzhalter** — immer `.venv\Scripts\python.exe`. Kein
`pip install -e .`; Skripte außerhalb der CLIs brauchen
`$env:PYTHONPATH = (Get-Location).Path`.

**Seit 21.08.2026 ist das Projekt ein Git-Repository** (Branch `main`).
`.gitignore` deckt `.env`, `.venv/`, `logs/`, `*.sqlite3` (inkl. `-shm`/`-wal`)
und `.claude/settings.local.json` ab. `core.autocrlf=false`.

```
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ntbridge
.venv\Scripts\python.exe -m mcp_server.cli snapshot --symbol MNQ
.venv\Scripts\python.exe pruefe_datenluecken.py            # letzte 7 Tage
.venv\Scripts\python.exe pruefe_datenluecken.py --tage 0   # gesamte Historie
```

**Datenlücken-Prüfung** (`pruefe_datenluecken.py`, neu am 22.08.2026): meldet
Lücken in der Kerzenabdeckung und trennt dabei erwartete Nicht-Handelszeit
(Wartungspause, Wochenende) von echten Ausfällen — NinjaTrader erzeugt ohne
Handel gar keine Kerze, einzelne fehlende Minuten sind in dünnen Phasen normal.
Öffnet die Datenbank **nur lesend** (`mode=ro`), läuft also neben dem
Empfänger. Exitcodes: `0` sauber, `2` Lücken gefunden, `1` Prüfung nicht möglich
— der Unterschied zwischen 1 und 2 ist wichtig.

Läuft zusätzlich täglich um 08:00 über die Windows-Aufgabenplanung
(`Claude Chart Bot - Datenluecken-Pruefung` → `pruefe_datenluecken_taeglich.bat`)
und hängt die Ausgabe an `datenluecken_log.txt` an (nicht versioniert).
Der Wrapper setzt das Arbeitsverzeichnis — ohne das fände das Skript seine
Datenbank nicht, und die Aufgabe scheiterte täglich lautlos.

### Unbeaufsichtigte Läufe: die Testsuite läuft dort nicht

Der geplante Lauf ("resume-project-work") arbeitet aus einem **Linux-Sandkasten**
auf den gemounteten Projektordner. Dort gibt es nur **Python 3.10** und **kein
Netz**; das Projekt braucht 3.14, und `.venv/` enthält Windows-Binärpakete.
Versucht und gescheitert: pytest aus `.venv/Lib/site-packages` unter 3.10
nachzunutzen — es fehlt `exceptiongroup`, das erst 3.11 in die Standardbibliothek
kam. Ein Shim dafür wäre falsch, weil 3.10 `BaseExceptionGroup` gar nicht kennt.

**Folge:** ein unbeaufsichtigter Lauf kann `pytest` **nicht** ausführen. Er darf
deshalb nur Änderungen committen, die er anders belegen kann — Dokumentation,
oder Code, dessen Verhalten sich mit einem gezielten `python3 -c`-Skript
nachweisen lässt. Import- und API-Prüfungen funktionieren: `PYTHONPATH=. python3 -c
"import ideas.pipeline"` läuft unter 3.10 durch, und die transitive Importhülle
lässt sich über `sys.modules` gegenprüfen.

**Konventionen:** Quelldateien **ASCII** (Umlaute als ae/oe/ue); README, `docs/`
und Kontextdateien mit echten Umlauten. Nutzertexte, Docstrings, Kommentare und
Testnamen **deutsch**. Kommentare erklären das *Warum*.

---

## 12. Dauerhafte Randbedingungen

1. **Keine Order-Ausführung**, auch nicht als inertes Interface.
2. **Kein Anthropic-Aufruf in `mcp_server/`** — transitiv abgesichert.
3. **Stille Ausfälle sind unzulässig:** `null` mit Begründungsfeld, plus
   abbrechende Startprüfung.
4. **Keine Schätzung, die wie eine Messung aussieht.**
5. **Bestehende Tests bleiben grün.**
6. **Schwellenwerte in `config.yaml`, nie im Code.**
7. **Die produktive `data/ntbridge.sqlite3` nie in Tests verwenden** — sie wird
   im Betrieb beschrieben. Tests laufen gegen temporäre Datenbanken.

---

## 13. Pflege dieser Datei

Selbständig aktualisieren bei: geändertem Implementierungsstand, neuen oder
entfernten wichtigen Dateien, Architekturänderungen, technischen Entscheidungen,
verworfenen Ansätzen, Bugs mit Ursache und Lösung, Tests und Backtests mit
Ergebnissen, neuen Einschränkungen und Blockern. **Datum in der Kopfzeile
mitziehen.**

Nicht dokumentiert werden Kleinigkeiten und Zwischenstände — die Datei ist kein
Git-Diff und kein Chatprotokoll.

**Hochladen ins Claude-Projekt:** Die dortige Kopie ist eingefroren und
aktualisiert sich **nicht**. Nach Meilensteinen beide Kontextdateien neu
hochladen; das Datum in der Kopfzeile verrät, ob die Kopie noch stimmt.

---

## 14. Dukascopy: Backtest-Historie als Näherung (22.08.2026)

Zehn Jahre echte CME-MNQ-Minutendaten sind **kostenlos nicht erhältlich**
(Databento, CME DataMine, dxFeed — alle kostenpflichtig). Kostenlos ist
Dukascopys öffentliche Tickhistorie, dort aber als **CFD auf den
Nasdaq-100-Index**, nicht als Futures.

| Datei | Inhalt |
|---|---|
| `backtest/data/dukascopy.py` | bi5-Dekodierung, Verdichtung zu 1m-Kerzen |
| `backtest/data/dukascopy_store.py` | eigene SQLite mit Tabelle `herkunft` |
| `lade_dukascopy.py` | Download, parallel und wiederaufnehmbar |
| `tests/test_dukascopy.py` | 21 Tests der Import-/Konvertierungslogik |

### 14.1 Diese Daten sind eine Näherung — das ist keine Formalie

* **Andere Preisbildung:** ein Market Maker statt CME-Orderbuch.
* **Kein echtes Handelsvolumen.** Die Volumenspalte trägt Dukascopy-Liquidität
  in Millionen Einheiten. Alles Volumenbasierte (relatives Volumen, Volume
  Profile, VWAP) bedeutet hier etwas anderes.
* **Keine Kontraktabläufe.** Echte MNQ-Historie hat vierteljährlich einen
  Rollover-Sprung, der CFD nicht.
* **Andere Sessionstruktur** — nicht CME-Globex mit Wartungspause.

Gemessener Niveauabstand zu echten MNQ-Kerzen desselben Tages: **−86 Punkte**
(Streuung 5,6), weil der CFD den Index abbildet und MNQ das Futures mit
Aufschlag.

**Ergebnisse eines Backtests auf diesen Daten sind rein informativ.** Sie
taugen dazu, eine Strategie auf Plausibilität und Programmierfehler
abzuklopfen — nicht als Grundlage für eine Entscheidung über Geld. Das Projekt
verlangt das schon für den Backtest auf den eigenen NT8-Daten; hier gilt es
stärker. Die Warnung steht in der erzeugten Datei selbst (Tabelle `herkunft`),
nach dem Vorbild von `naeherung: true` beim Volume Profile.

### 14.2 Drei Dinge, die nur ein Abgleich zeigt

**Das Symbol ist gemessen, nicht geraten.** `USATECHIDXUSD`. Die naheliegenden
`USA100IDXUSD` und `NAS100IDXUSD` liefern 404. Ebenso der Preisfaktor 1000:
29408411 / 1000 = 29408.41 passt zum Nasdaq-Niveau.

**`duka` ist unbrauchbar.** Das empfohlene Paket setzt keinen
`User-Agent`-Header; Dukascopy antwortet darauf mit **HTTP 403** und einer
Cloudflare-Seite — gemessen auch für `EURUSD`, das es garantiert gibt. `duka`
läuft in seine Wiederholungsschleife und bricht ab. Der Download ist deshalb
selbst gebaut (rund 30 Zeilen).

**Ein-Minuten-Versatz, gefunden nur durch Kreuzvergleich.** Beide Reihen
bewegen sich um 5,3 Punkte je Minute, ihre Minutenänderungen korrelierten aber
mit **r = −0,06**, also gar nicht. Ursache: `resample` beschriftet mit dem
**Anfang** des Fensters, NinjaTrader mit der **Schlusszeit**. Nach der
Korrektur (`closed="left", label="right"`): **r = +0,9492** bei Versatz 0.

Nichts an den Kursen selbst hätte das verraten — die Reihe sah lückenlos und
plausibel aus. **Lehre:** Eine neue Datenquelle gegen eine bekannte
kreuzprüfen, und zwar auf *Änderungen*, nicht auf Niveaus. Ein Niveauvergleich
hätte den Versatz nicht gezeigt.

### 14.3 Dauer und Bedienung

Zehn Jahre sind rund **87.600 Stunden**; seriell gemessen ~6 s je Stunde, also
über fünf Tage. Der Download läuft deshalb parallel, ist **wiederaufnehmbar**
(geholte Stunden stehen in der Datenbank) und hält HTTP 503 aus — Dukascopy
drosselt bei zu vielen Anfragen, mit exponentiellem Backoff über vier Versuche.

```bash
.venv\Scripts\python.exe lade_dukascopy.py --jahre 10 --parallel 12
.venv\Scripts\python.exe lade_dukascopy.py --von 2024-01-01 --bis 2024-02-01
```

Historie reicht bis mindestens 2015 zurück; 2014 liefert nichts mehr.
Die Datei ist in `.gitignore`, sie ist groß und jederzeit neu ladbar.

**Der Vollabzug ist am 22.08.2026 gelaufen** (Stand 23.08.2026 gegen die Datei
gemessen, nicht aus Notizen übernommen):

| Kennzahl | Wert |
|---|---|
| Datei | `data/dukascopy_nas100_1m.sqlite3`, 384 MB |
| Kerzen (`bars`) | 3 179 672 |
| Abdeckung | 2016-08-22T06:01Z bis 2026-08-21T20:15Z |
| geholte Stunden | 87 010 |
| `herkunft` | 9 Einträge, `ist_naeherung = true` |

Die Jahre 2017–2025 liegen bei 337 000–340 000 Kerzen und sind damit
untereinander plausibel; 2016 (78 238) und 2026 (216 866) sind die
angeschnittenen Randjahre. Der Startpunkt liegt bei zehn Jahren rückwärts, nicht
bei den in 14.x erwähnten „mindestens 2015" — wer weiter zurück will, muss
`--von` setzen.

**Diese Zeilen standen bis zum 23.08.2026 im Widerspruch zur Datei**: hier
stand „Vollabzug noch nicht gelaufen, nur ein Probetag (1335 Kerzen)", während
die Datenbank bereits 3,18 Mio. Kerzen enthielt. Die Notiz war schlicht älter
als der Download. **Lehre, wieder dieselbe:** eine Zustandsbeschreibung in einer
Kontextdatei ist nur so lange wahr, wie niemand den Zustand ändert — vor dem
Zitieren gegen die Datei prüfen.

---

## 15. Stand bei Sitzungsende (22.08.2026)

### Fertig und committet

Branch **`legacy-entfernen`**, fünf Commits, **316 Tests grün** (auf Windows
gemessen, nicht gerechnet).

| Commit | Inhalt |
|---|---|
| `57e0c08` | `live_bot/`, Tradovate-Provider, zwei Testdateien entfernt |
| `31b0d60` | Konfiguration bereinigt, `on_demand` → `analyse`, Puffer-Prüfung umgezogen |
| `c68b4b6` | Kostentest repo-weit, Gegenprobe durchgeführt |
| `78f494c` | README auf den Stand nach der Entfernung |
| `578a0e1` | `CODE_CHAT_KONTEXT.md`, Testzahlen gemessen |
| `09e3c12` | `NORMALER_CHAT_KONTEXT.md`, Notiz „bleibt bestehen" aufgehoben |
| `0240132` | kaputtes `fetch`-Kommando, veraltete Begründungen |

Der Branch ist **nicht** nach `main` gemerged — das ist bewusst offen gelassen.

### Ein echter Defekt, den die Aufräumarbeit zutage förderte

`backtest/cli.py` bot weiterhin ein `fetch`-Kommando an, das Historie von
Tradovate lädt. Der Provider war gelöscht — das Kommando wäre mit
`DataProviderError` abgebrochen. Kein Test hatte es bemerkt, weil kein Test es
aufrief. **Lehre:** Nach dem Entfernen einer Datenquelle nicht nur die Importe
prüfen, sondern auch die Kommandozeile, die sie anbietet.

### Drei Annahmen der Arbeitsanweisung waren überholt

Festgehalten, weil sie zeigen, wie schnell Notizen altern:

1. „Der Zwischenstand in `ideas/` ist nach der Spezifikation entstanden und
   überholt, `detectors.py` ist der schwerwiegende Punkt" — `detectors.py` war
   zu diesem Zeitpunkt bereits entfernt (`142fd11`), `ideas/` gegen die
   Spezifikation neu gebaut.
2. „README beschreibt derzeit ausschließlich den gelöschten Pfad" — sie war
   seit `e932844` auf NinjaTrader/MCP umgestellt; der Legacy-Teil war ein klar
   gekennzeichneter Abschnitt 9.
3. „`kumulatives_delta.reason` nennt noch Tradovate" — nennt seit längerem
   korrekt NinjaTrader und das fehlende Add-on.

### Neu hinzugekommen: Dukascopy-Näherungsdaten

Import, Speicher, Download und 21 Tests stehen (Abschnitt 14). ~~Der
Zehn-Jahres-Vollabzug ist bewusst nicht gestartet.~~ — **überholt:** der Abzug
ist am 22.08.2026 gelaufen und vollständig, 3 179 672 Kerzen von 2016-08-22 bis
2026-08-21. Zahlen und Nachprüfung stehen in Abschnitt 14.

### Was auf Laurin wartet

1. ~~`flaggen_ausbruch` kann nie auslösen~~ — **erledigt am 22.08.2026.**
   Laurin hat das Setzen dieses einen Werts genehmigt; er ist aus der
   gemessenen Verteilung abgeleitet (Bug 8.17). **Andere Setup-Parameter
   bleiben rückfragepflichtig.**

2. ~~**Branch mergen?** `legacy-entfernen` wartet auf `main`.~~ — **hinfällig,
   am 23.08.2026 gegen das Repository geprüft.** Es gibt nur noch den Branch
   `main`; er enthält `57e0c08` und alle weiteren Legacy-Commits, das Reflog
   zeigt den Wechsel `legacy-entfernen` → `main` auf demselben Commit
   (`1d0e01d`). Der Arbeitsbaum ist sauber. Hier stand also eine Frage, die der
   Code bereits beantwortet hatte — dieselbe Alterung wie beim „Kleinkram"
   weiter unten.
3. **Die 8 weiteren Setup-Familien** — alle oder schrittweise?
4. ~~**Dukascopy-Vollabzug starten?**~~ — **hinfällig, am 23.08.2026 gegen die
   Datei geprüft.** Der Abzug ist gelaufen: 3 179 672 Kerzen, 2016-08-22 bis
   2026-08-21, 384 MB. Damit ist Arbeitspaket 4 auf der Datenseite fertig.
   Offen bleibt die *Auswertung* — und die ist rein informativ, weil es ein
   Index-CFD und kein MNQ-Futures ist (Invariante 10).

### Halbfertig

**Nichts.** Jeder Commit lässt die Suite grün.

Was **gebaut, aber nicht in Betrieb** ist: `python -m ideas` läuft, hängt aber an
keiner geplanten Aufgabe. Es ist weiterhin **keine einzige echte Idee
protokolliert**. Bewusst nicht eingerichtet, solange Punkt 1 offen ist — sonst
sammelt die Aufgabe ab sofort Daten mit einem Setup, das garantiert leer bleibt.

### Was als nächstes dran wäre

1. Punkt 1 klären, dann die geplante Aufgabe einrichten (mindestens täglich,
   besser stündlich — die Blackout-Prüfung deckt nur die letzten 7 Tage ab).
2. **Etappe D ist verfrüht.** Ohne geloggte Ideen ließe sich
   `evaluate_past_ideas` nur gegen synthetische Daten testen. Laurin hat die
   Reihenfolge so angefordert, wollte aber ausdrücklich darauf hingewiesen
   werden. Der Datenbestand ist die Voraussetzung, nicht die Kür.
3. MCP-Startzeit: pandas verzögert importieren (7,5 s → nahezu sofort).
4. Erster Backtest auf echten MNQ-Daten, rein informativ. **Nur 1m/5m/15m** —
   die Tagesserie hat eine Lücke 31.07.–12.08., der 1d-ATR ist dadurch ein
   Artefakt von rund 650 Punkten.

### Kleinkram

Am 22.08.2026 nachgeprüft — die zuvor hier stehende Liste war bereits erledigt
und damit ein Widerspruch zwischen Dokumentation und Code:

- `kumulatives_delta.reason` (`mcp_server/snapshot.py:241`) nennt **korrekt**
  NinjaTrader und das fehlende Add-on „Order Flow +", nicht Tradovate.
- Der Docstring in `mcp_server/context.py` nennt Tradovate nur noch in einem
  ausdrücklich als historisch markierten Absatz („hier stand bis zum
  21.08.2026"); die Zeilen darüber stellen klar, dass es keinen Broker-Login
  gibt. Das ist die vom Projekt gewollte *Warum*-Dokumentation, kein Rest.

Tatsächlich noch offen war eine andere Stelle, jetzt behoben:
`common/instruments.py` verwies mit `:func:` auf
`live_bot.tradovate.contracts.third_friday` — ein Modul, das es nicht mehr
gibt; die Funktion steht seit der Entfernung in derselben Datei. Ebenso zeigte
der Kommentar über `MONTH_CODE_BY_NUMBER` auf eine gelöschte zweite Kopie, und
die Einleitung begründete das Modul noch mit dem Live-Bot.

**Lehre:** Eine „noch offen"-Liste am Sitzungsende altert genauso schnell wie
die Arbeitsanweisung, die sie erzeugt hat. Vor dem Abarbeiten gegen den Code
prüfen, nicht danach.

Weiterhin auf der Platte, aber nicht in Git: ein leerer Ordner `live_bot/` mit
`__pycache__`-Resten. Nicht gelöscht — Aufräumen im Dateisystem gehört Laurin.
Am 23.08.2026 nachgesehen: die Unterordner `ai/`, `alerts/`, `market/`,
`notify/`, `tradovate/` liegen dort noch, sämtlich nur `__pycache__`. Kein
Quelltext, kein Import zeigt darauf.

---

## 16. Nachtrag 23.08.2026 — die Arbeitssitzung existiert nicht mehr

Die autonome Claude-Code-Sitzung mit der ID `local_143554db-…`, an der die
geplante Aufgabe „resume-project-work" ihre Anweisungen schickte, ist **nicht
mehr auffindbar**. Sie steht in keiner Sitzungsliste; ein `continue` erreicht
sie nicht. Der Arbeitsauftrag vom 22.08.2026 (Arbeitspakete 1–4) ist damit
ohne ausführende Instanz.

Was das **nicht** heißt: es ist nichts verloren. Der Arbeitsbaum ist sauber,
alle Commits liegen auf `main`, die Kontextdateien beschreiben den Stand. Eine
neue Sitzung kann aus `CLAUDE.md` und dieser Datei nahtlos weitermachen — genau
dafür sind sie da.

Zu klären ist nur, **welche** Sitzung: Laurins Vorgabe vom 22.08.2026 lautet,
neue Sitzungen mit `claude-opus-5` zu starten.

### Nachtrag zum Masterplan (23.08.2026, zweiter Durchgang)

Beim Gegenlesen kamen zwei Befunde dazu, die in der ersten Fassung fehlten
(jetzt Abschnitt X in `MASTERPLAN.md`):

1. **`backtest/data/__init__.py::create_provider` kennt nur `"csv"`.** Es gibt
   keinen `DukascopyDataProvider`. Die 3 179 672 Kerzen sind ueber den
   normalen Backtest-Pfad **nicht erreichbar**; erreichbar ist nur, was als
   CSV in `data/` liegt — und das ist dort ausschliesslich der synthetische
   `DEMO_1m.csv`. Der Satz "kein Backtest auf echten Marktdaten gerechnet" ist
   damit keine Frage der Zeit, sondern eine fehlende Codezeile. **P0.**
   Ein CSV-Export waere ein Umweg, wuerde aber die Herkunftstabelle aus
   `DukascopyStore` abschneiden und damit die Naeherungskennzeichnung
   verlieren — Invariante 10.
2. **`splits.walk_forward_windows` ist getestet und von der CLI aus nicht
   aufrufbar.** Die CLI kennt `list`, `run`, `compare`, `optimize`; `compare.py`
   ruft die Funktion ebenfalls nicht auf. Toter, aber korrekter Code. **P1** —
   bestes Verhaeltnis von Aufwand zu Erkenntnisgewinn im ganzen Plan, weil die
   Rechenlogik steht und nur der Einstiegspunkt fehlt.

Beide Punkte sind Erreichbarkeitsluecken, keine Entwurfsfragen, und beruehren
keinen der rueckfragepflichtigen Bereiche.

### Zwei Git-Sperrdateien aus dem Absturz (23.08.2026)

Die abgestürzte Sitzung hat um 04:16 Uhr **zwei** leere Sperrdateien
hinterlassen: `.git/index.lock` **und** `.git/HEAD.lock`. Solange sie liegen
bleiben, schlägt jedes schreibende Git-Kommando fehl — `git add`, `git commit`,
`git checkout`, `git update-ref`.

Der zu diesem Zeitpunkt gestagete Stand (Masterplan-Abschnitt X und der
Nachtrag oben) ist trotzdem **committet**: der Commit wurde über
`write-tree`/`commit-tree` erzeugt und `refs/heads/main` direkt geschrieben,
weil beide Wege ohne Sperrdatei auskommen. `main` steht auf diesem Commit, der
Arbeitsbaum ist sauber. Ein Reflog-Eintrag fehlt — das ist die einzige Folge.

**Vor der nächsten Sitzung im Projektordner auszuführen:**

```
del ".git\index.lock" ".git\HEAD.lock"
del /s ".git\objects\tmp_obj_*"
```

Danach arbeitet Git wieder normal; ein weiterer `git commit` ist **nicht**
nötig und würde nur einen leeren Commit versuchen.

Die zweite Zeile räumt Reste auf: jeder Commit aus der Linux-Umgebung schreibt
seine Objekte erfolgreich, kann die zugehörigen Temporärdateien danach aber
nicht entfernen (derselbe fehlende Löschrechte-Mount). Git ignoriert sie, weil
ihre Namen nicht dem Hash-Muster entsprechen — sie kosten nur Platz. Stand
23.08.2026 liegen davon über 20 Stück im Objektspeicher. `git fsck` und
`git gc` laufen dadurch nicht auf einen Fehler.

---

## 17. Zwei Tradovate-Defekte bereinigt (23.08.2026)

Der Masterplan führte sie als P0 mit Minutenaufwand (Abschnitt B, Zeilen zu
`backtest/cli.py:276` und `backtest/data/csv_provider.py:57`). Beides sind
Erreichbarkeits- beziehungsweise Wegweiser-Fehler, keine Entwurfsfragen, und
sie berühren keinen der rückfragepflichtigen Bereiche — deshalb ohne Rückfrage
erledigt.

1. **`backtest/cli.py`** bot `--provider tradovate` an. `create_provider` kennt
   nur `"csv"`; die Option lief also in einen `DataProviderError` statt gar
   nicht erst wählbar zu sein. Jetzt `choices=("csv",)`. Gegenprobe:
   `--provider tradovate` scheitert nun im Argumentparser mit
   *invalid choice: 'tradovate' (choose from 'csv')*.

2. **`backtest/data/csv_provider.py`** riet bei fehlender Datei zu
   `python -m backtest.cli fetch --symbol …`, einem Kommando, das es nicht mehr
   gibt, für einen Anbieter, den es nicht mehr gibt. Der Fehlertext nennt jetzt
   die erwartete Namenskonvention, `--csv` als Alternative und sagt ausdrücklich,
   dass es **kein** Download-Kommando gibt und die Dukascopy-Näherungshistorie
   über diesen Provider nicht erreichbar ist (Verweis auf MASTERPLAN X.1).

3. **`backtest/data/base.py`** nannte Tradovate im Modul-Docstring als Beispiel
   einer austauschbaren Quelle. Ersetzt durch die Dukascopy-Historie, mit dem
   Hinweis, dass am 23.08.2026 nur `csv` registriert ist.

**Nicht angefasst:** die übrigen Tradovate-Nennungen in `common/config.py`,
`common/contracts.py`, `common/instruments.py`, `mcp_server/bars.py`,
`ntbridge/__init__.py`, `config.yaml` und `README.md`. Das sind
Historien-Kommentare, die das *Warum* einer Entfernung festhalten — sie zu
löschen würde die Begründung vernichten, nicht einen Defekt.

**Verifikation eingeschränkt:** Der Lauf fand in einer Linux-Umgebung ohne
`pytest` statt (Installation gesperrt). Geprüft wurden Import beider Module,
der erzeugte Fehlertext, die Ablehnung der entfernten CLI-Option und die
ASCII-Reinheit aller drei Dateien. **Die Testsuite ist auf Windows noch
nachzuziehen:** `.venv\Scripts\python.exe -m pytest`. Erwartung: unverändert
grün, da keine Testdatei die geänderten Zeichenketten prüft (`grep -rn
tradovate tests/` trifft nur `test_ideas.py` und `test_ntbridge.py`, beide zur
`environment: demo`-Namensfalle, und `test_mcp_snapshot.py` in einem Docstring).

### Git-Sperrdateien weiterhin vorhanden

`.git/index.lock` und `.git/HEAD.lock` liegen noch. Aus dieser Umgebung sind
sie **nicht löschbar** (der Mount erlaubt Anlegen und Ändern, aber kein
Löschen). Der Commit dieser Änderung entstand deshalb erneut über einen
alternativen Index (`GIT_INDEX_FILE`), `write-tree`/`commit-tree` und ein
direktes Schreiben von `refs/heads/main`. Folge wie beim letzten Mal: kein
Reflog-Eintrag. Die Aufräumanweisung aus Abschnitt 16 gilt unverändert.

---

## 18. Arbeitspaket 4 (Dukascopy-Vollabzug) ist abgeschlossen — nachgemessen 23.08.2026

Der im Hintergrund laufende Vollabzug ist **fertig**, nicht mehr laufend. Gegen
`data/dukascopy_nas100_1m.sqlite3` (367 MB) gemessen:

| Kennzahl | Wert |
|---|---|
| Minutenkerzen (`bars`) | 3 179 672 |
| Zeitraum (`ts_utc`) | 2016-08-22T06:01Z bis 2026-08-21T20:15Z |
| Quittierte Stunden (`geholte_stunden`) | 87 010 |
| Tabellen | `bars`, `geholte_stunden`, `herkunft` |

Die Herkunftstabelle traegt die Naeherungskennzeichnung vollstaendig
(`ist_naeherung = true`, `symbol = USATECHIDXUSD`, `preis_faktor = 1000.0`,
Warntext). Invariante 10 ist damit auf der Datenseite erfuellt.

**Der Bestand ist zehn Jahre tief und trotzdem nicht nutzbar** — genau der
Befund aus MASTERPLAN X.1: `create_provider` kennt nur `"csv"`, es gibt keinen
`DukascopyDataProvider`. Arbeitspaket 4 ist also nicht mehr eine Frage der
Laufzeit, sondern wartet ausschliesslich auf die P0-Entscheidung.

### Testsuite weiterhin nicht nachgezogen

Die Gegenprobe aus Abschnitt 17 steht unveraendert aus. In der Linux-Umgebung
ist `pytest` **nicht installierbar** (der Paketproxy antwortet mit 403), und
das Windows-venv ist von dort nicht aufrufbar. Auszufuehren bleibt im
Projektordner:

```
.venv\Scripts\python.exe -m pytest
```

### Es gibt keine ausfuehrende Sitzung mehr

Bestaetigt: `local_143554db-...` taucht in keiner Sitzungsliste auf. Alle
aufgefuehrten Sitzungen sind Laeufe der geplanten Aufgabe selbst. Eine neue
Arbeitssitzung (`claude-opus-5`) muss gestartet werden; die beiden Git-Sperr-
dateien aus Abschnitt 16 sind vorher zu loeschen.

---

## 19. Qualitaetsmessung der Dukascopy-Naeherungshistorie (23.08.2026)

Arbeitspaket 4 war zuvor nur *mengenmaessig* nachgemessen (Abschnitt 18:
3 179 672 Kerzen, zehn Jahre, Herkunftstabelle vollstaendig). Was fehlte, war
die **inhaltliche** Pruefung — und Invariante 9 verlangt sie ausdruecklich, weil
der Ein-Minuten-Versatz seinerzeit an den Kursen selbst nicht sichtbar war.
Gemessen wurde gegen eine Arbeitskopie der Datei; die produktive Datenbank wurde
nur lesend geoeffnet. Kein Code im Projekt wurde dafuer geaendert.

### 19.1 Formale Integritaet: fehlerfrei

| Pruefung | Befund |
|---|---|
| `high < low` | 0 |
| `high` kleiner als `open`/`close` | 0 |
| `low` groesser als `open`/`close` | 0 |
| Preis <= 0 | 0 |
| Volumen < 0 oder = 0 | 0 |
| Zeitindex streng aufsteigend und eindeutig | ja |
| Zeitstempel mit Sekundenanteil != 0 | 0 |
| Aufeinanderfolgende Kerzen genau 1 Minute auseinander | 99,81 % |

Die groessten Luecken sind ausnahmslos Wochenenden und Feiertage (Weihnachten,
Karfreitag, Zeitumstellungswochen: 73,8 h bis 82,1 h). Kein einziger
unerklaerter Ausfall.

Die Preisniveaus je Jahr folgen dem Nasdaq-100 plausibel: 4830 (2016),
Corona-Tief 6638 (2020), Hoch 16 769 (2021), Tief 10 432 (2022), 22 538 (2025),
27 232 im Mittel 2026. Der `preis_faktor = 1000.0` ist also richtig angewandt.

### 19.2 Kreuzvergleich gegen echte MNQ-Kerzen: Ausrichtung bestaetigt

Nach Invariante 9 auf **Veraenderungen** geprueft, nicht auf Niveaus, ueber die
gesamte verfuegbare Ueberschneidung (4147 gemeinsame Minuten, 18.–21.08.2026):

| Versatz | r |
|---|---|
| −1 Minute | −0,0170 |
| **0** | **+0,9967** |
| +1 Minute | −0,0206 |

Eindeutig, und deutlich schaerfer als die +0,9492 der damaligen Stichprobe
(Abschnitt 904 ff.). Die Beschriftungskonvention `closed="left", label="right"`
ist ueber den Vollabzug hinweg korrekt durchgehalten.

### 19.3 Neuer Befund: taegliche Handelspause 16:16–18:00 ET

Der CFD ruht taeglich von **16:16 bis 18:00 ET** (105 Minuten, exakt und ohne
Ausnahme ueber die letzten drei Jahre). MNQ handelt dagegen bis **17:00 ET**.

Zwei Folgen, gegenlaeufig:

1. **Gut:** Die erste Kerze nach der Pause traegt die Beschriftung **18:01 ET** —
   genau der CME-Rollover aus Invariante 2. Auch die Sonntagseroeffnung liegt
   auf 18:01 ET. Die Sessiongrenze selbst stimmt also, `common/sessions.py`
   braucht fuer diese Quelle keine Sonderbehandlung.
2. **Schlecht:** Die **letzten 45 Minuten jedes Handelstages (16:16–17:00 ET)
   fehlen vollstaendig.** `prev_session_high` und `prev_session_low` werden auf
   dieser Quelle daher systematisch aus einer um 45 Minuten verkuerzten Session
   gebildet, und der Session-VWAP endet zu frueh. Das Setup `pdh_pdl_bruch`
   haengt unmittelbar daran. Es ist **kein stiller Ausfall** — die Marken
   entstehen, sie beziehen sich nur auf ein anderes Fenster als live.

Zusaetzlich sind die ersten acht Minuten nach dem Rollover duenn besetzt
(18:01–18:08 ET: rund 70–73 % der Referenzbesetzung, ab 18:09 ET wieder ueber
99 %). Der Market Maker stellt dort nicht durchgaengig. Fruehe Session-VWAP-Werte
ruhen auf entsprechend weniger Kerzen.

### 19.4 Neuer Befund: die Spanne ist rund 7 % zu klein

Auf denselben gemeinsamen Minuten, Ein-Minuten-Spanne (`high − low`) in Punkten:

| | MNQ | Dukascopy | Verhaeltnis |
|---|---|---|---|
| Median | 9,75 | 9,01 | 0,92 |
| 75 % | 14,75 | 13,63 | 0,92 |
| 90 % | 21,50 | 20,11 | 0,94 |
| Mittel | 12,05 | 11,23 | 0,93 |

Korrelation der Spannen: r = +0,9956. Die Reihe atmet also im Takt, aber
**flacher**. Ein ATR auf dieser Quelle faellt rund 7 % zu niedrig aus. Da
Stops und Ziele im Projekt ATR-Vielfache sind, skalieren sie mit — die
Verzerrung schlaegt dort durch, wo **absolute** Groessen dagegenstehen: das
`CostModel` rechnet mit echtem Punktwert und Ticksize, also wiegen Kosten auf
dieser Quelle relativ rund 7 % schwerer. Die Richtung ist konservativ; die
Zahlen bleiben trotzdem nicht auf MNQ uebertragbar.

Die **Basis** (MNQ minus CFD) lag im Messfenster bei 75,8 bis 94,4 Punkten und
driftete in drei Tagen um rund 10 Punkte. Fuer Regeln auf absoluten
Preisniveaus ist sie damit kein konstanter Versatz, den man herausrechnen
koennte.

### 19.5 Einschraenkung dieser Messung

Der Kreuzvergleich stuetzt sich auf **drei Handelstage** — mehr echte
MNQ-Minutenkerzen liegen in `ntbridge.sqlite3` nicht vor (4326 Kerzen,
18.–21.08.2026). Die Ausrichtung (19.2) ist damit sicher belegt, die
Groessenordnung der Spannen-Verzerrung (19.4) ist eine **Schaetzung aus kurzer
Stichprobe** und sollte nachgemessen werden, sobald mehr Live-Historie
vorliegt. Sie ist ausdruecklich keine Messung im Sinne von Invariante 10.

**Fazit fuer die P0-Entscheidung:** Die Datei ist technisch einwandfrei und
richtig ausgerichtet. Ein `DukascopyDataProvider` waere damit auf der Datenseite
unbedenklich — er muesste aber die Pause 16:16–18:00 ET und die flachere Spanne
in der erzeugten Ausgabe kennzeichnen, sonst saehe eine Naeherung aus wie eine
Messung.

---

## 20. Die Testsuite laeuft doch unbeaufsichtigt — 343 Tests gruen (23.08.2026)

Abschnitt 17 und 18 fuehrten die Gegenprobe als offene Schuld: `pytest` sei in
der Linux-Sandbox nicht installierbar (Paketproxy antwortet 403) und das
Windows-venv von dort nicht aufrufbar, also blieben die Aenderungen aus
Abschnitt 17 ungeprueft. Beides stimmt einzeln — der Schluss war trotzdem
falsch.

### Warum es doch geht

`pytest`, `pluggy`, `iniconfig`, `httpx`, `yaml`, `dotenv`, `tabulate` und die
uebrigen Testabhaengigkeiten sind **reines Python** und liegen bereits im
Windows-venv des Projekts. Nur `pandas` und `numpy` tragen kompilierte
Endungen — und die stellt die Linux-Umgebung selbst (pandas 2.3.3, numpy
2.2.6). Es fehlte einzig `exceptiongroup`: Python 3.10 bringt
`BaseExceptionGroup` noch nicht mit, pytest 9.1.1 setzt es voraus, das Backport
ist nicht ladbar. Ein Minimalersatz von rund 40 Zeilen genuegt, weil pytest
davon nur isinstance-Pruefungen und das Buendeln mehrerer Fehler braucht.

Das Vorgehen steckt jetzt in **`werkzeuge/pytest_linux.py`** (neuer Ordner,
reines Entwicklerwerkzeug, kein Teil der Pipeline). Es kopiert die Pakete nach
`/tmp`, schreibt den Ersatz dazu und startet pytest — ohne irgendetwas im
Projekt zu aendern.

```
python3 werkzeuge/pytest_linux.py
```

### Ergebnis

**343 Tests, alle gruen, 31 s.** Damit ist die Gegenprobe zu Abschnitt 17
(zwei Tradovate-Defekte in `backtest/cli.py`, `backtest/data/base.py`,
`backtest/data/csv_provider.py`) eingeloest: die Aenderungen brechen nichts.

### Die dokumentierte Testzahl war veraltet

`CLAUDE.md` nannte 337, ein Commit vom 22.08. sprach von 342, tatsaechlich sind
es **343**. Nach der Regel "der Code ist die Wahrheit ueber den aktuellen
Stand" ist die Zahl in `CLAUDE.md` auf 343 gezogen. Genau die Alterung, die
Abschnitt 15 unter "Lehre" beschreibt — diesmal an einer Zahl statt an einer
Aufgabenliste.

### Eine pandas-Abkuendigung im Testcode beseitigt

`tests/test_metrics_and_splits.py:37` erzeugte einen `FutureWarning`: bei
leerer Trade-Liste ist `pd.Series(pnls)` object-dtype, und `ffill` darauf ist
abgekuendigt. Jetzt `pd.Series(pnls, dtype="float64")`. Kein Verhaltens-
unterschied heute, aber in einer kuenftigen pandas-Version waere daraus ein
Fehler geworden. Gegenprobe: Lauf weiterhin 343 gruen, Warnung verschwunden.

### Grenze dieser Messung

Der Lauf fand unter **Python 3.10** mit den Linux-Versionen von pandas und
numpy statt, nicht unter dem Python des Projekt-venv (3.14). Ein gruener Lauf
belegt, dass die Testlogik traegt; er ersetzt den Windows-Lauf nicht. Der
bleibt vor einer Freigabe auszufuehren:

```
.venv\Scripts\python.exe -m pytest
```

Nach Invariante 10 ausdruecklich so benannt und nicht als der Windows-Lauf
ausgegeben.

### Unveraendert offen

- Die beiden Git-Sperrdateien aus Abschnitt 16 (`.git/index.lock`,
  `.git/HEAD.lock`) liegen weiterhin und sind aus dieser Umgebung nicht
  loeschbar. Der Commit dieses Abschnitts entstand erneut ueber
  `GIT_INDEX_FILE` + `write-tree`/`commit-tree` + direktes Schreiben von
  `refs/heads/main`. Folge wie bisher: kein Reflog-Eintrag. Nebenwirkung: der
  im Repository liegende Index ist seit dem Absturz veraltet, `git status`
  zeigt deshalb Dateien als geaendert an, die es nicht sind — `git diff HEAD`
  ist leer und damit die verlaessliche Auskunft.
- Die **P0-Entscheidung** aus dem Masterplan liegt bei Laurin. Er wurde am
  23.08.2026 mit Zusammenfassung und Vorschlag (1. Ideen-Dauerlauf,
  2. Dukascopy-Provider, 3. MCP-Startzeit) angeschrieben; eine Antwort steht
  aus. Bis dahin nur Arbeit, die keine der rueckfragepflichtigen Fragen
  beruehrt.

---

## 21. Arbeitspaket 3: Basisvermessung der Strategiebibliothek (23.08.2026)

**Der ausfuehrliche Bericht steht in `docs/BASISVERMESSUNG_2026-08-23.md`.**
Hier nur, was dauerhaft am Code haengt.

### Werkzeuge

- **`werkzeuge/python_linux.py`** (neu) startet ein beliebiges Projektmodul in
  derselben Ersatzumgebung, die Abschnitt 20 fuer pytest aufgebaut hat. Es ruft
  `pytest_linux.vorbereiten` auf, statt die Sammellogik ein zweites Mal
  hinzuschreiben. Damit kann ein unbeaufsichtigter Lauf die Backtest-CLI
  bedienen, nicht nur die Tests.
- **`werkzeuge/dukascopy_export.py`** (neu) zieht einen CSV-Auszug aus
  `data/dukascopy_nas100_1m.sqlite3`. **Das ist ausdruecklich kein
  DataProvider** — ein richtiger Dukascopy-Provider ist P0 im Masterplan und
  Laurins Entscheidung. Beim Verdichten auf groebere Kerzen rechnet das Skript
  erst auf Startzeit zurueck und danach wieder auf die Schlusszeit
  (Invariante 9); der Rundlauf ist gegen die Minutenkerzen nachgerechnet.
- `pytest_linux.SCRATCH` traegt jetzt die Benutzerkennung im Namen. Jede
  Sandbox laeuft unter einer eigenen Kennung, `/tmp` bleibt aber ueber
  Sandbox-Grenzen liegen — der Rest eines frueheren Laufs gehoerte `nobody`,
  `shutil.rmtree(..., ignore_errors=True)` schluckte den Fehler und
  `copytree` fiel eine Ebene tiefer mit `FileExistsError` um, ohne die Ursache
  zu nennen. Das `ignore_errors` ist mit raus.

### Befund 1: `ib_breakout` war seit jeher tot — und es sah aus wie ein Ergebnis

Die Strategie verlangt `ib_high`/`ib_low` aus
`common.levels.initial_balance_per_session`; **`compute_indicators` erzeugt
diese Spalten nicht**. `BarContext.value` loest einen unbekannten Spaltennamen
zu NaN auf, `_valid` verwirft NaN, die Regel feuert nie. Ergebnis ueber zehn
Jahre: null Trades, keine Warnung, kein Eintrag im Log.

Behoben ist der **stille** Teil:

- `Rule.benoetigte_spalten()` (`backtest/strategies/base.py`) meldet je Regel
  die gebrauchten Spalten, rekursiv ueber `AllOf`/`AnyOf`/`Not`. Konstanten
  zaehlen nicht mit (`_spaltennamen`).
- `RuleStrategy.benoetigte_spalten()` fasst ueber alle vier Regelplaetze
  zusammen.
- `Backtester.run` prueft einmal vor der Hauptschleife und bricht mit Nennung
  der fehlenden **und** der vorhandenen Spalten ab.

**Nicht** entschieden — das beruehrt Invariante 1 und ist Architektur: ob die
Initial Balance in `compute_indicators` aufgenommen wird.
`test_jede_strategie_der_bibliothek_findet_ihre_spalten` fuehrt die Luecke als
bekannt und erwartet und faellt um, sobald sie geschlossen wird. Dann gehoert
der Eintrag aus der Liste, **nicht der Test entschaerft**.

### Befund 2: die Robustheitskennzahl behauptete das Gegenteil

`prev_day_breakout`: Ø-Trade -4,40 USD in-sample, -9,02 USD out-of-sample —
und daneben stand `Robustheit OOS/IS: 2,05 -> stabil`. Der Quotient dreht bei
negativem Nenner sein Vorzeichen um.

`StrategyRun.robustness` liefert jetzt `None`, sobald der Ø-Trade in-sample
nicht positiv ist; an einer Strategie, die schon in-sample verliert, gibt es
nichts zu bestaetigen. `print_report` schreibt in dem Fall ausdruecklich
"nicht aussagekraeftig" hin, statt die Zeile wegzulassen — eine fehlende Zeile
haelt man fuer einen Darstellungsfehler statt fuer eine Aussage.

### Befund 3: "% vom Hoch" beim Drawdown — festgehalten, nicht geaendert

`8.539,68 USD (78037,8 % vom Hoch)`. Die Equity-Kurve startet bei null (reine
P&L, kein Startkapital); steht der bisherige Hoechststand bei ein paar Cent,
kommen fuenfstellige Prozentwerte heraus. Die Abfrage `peak_at_worst > 0` in
`max_drawdown` greift zu spaet. Rechnerisch nicht falsch, nur nutzlos.

Sinnvoll wuerde der Wert erst mit einem Startkapital im Modell — das ist eine
Modellentscheidung, keine Fehlerkorrektur, und deshalb hier nur notiert.
Solange gilt: die USD-Angabe lesen, die Prozentangabe ignorieren.

### Die Zahlen in einem Satz

Auf zehn Jahren Naeherungshistorie (5-Minuten-Kerzen, unveraenderte Parameter,
**keine** Optimierung, deshalb ist der OOS-Zeitraum nicht verbraucht) ist jede
Strategie netto negativ, Profitfaktoren 0,75 bis 0,87 — aber **vor Kosten**
liegen vier von fuenf ungefaehr bei null, und die 6,00 USD Reibung je Round
Turn machen den Unterschied aus. Die Break-even-Trefferquote liegt in allen
zehn Faellen nur 3 bis 7 Prozentpunkte ueber der tatsaechlichen. Das stuetzt
die Praemisse von Etappe C: der Hebel liegt in der **Auswahl**, nicht am Ein-
und Ausstieg. Es ersetzt sie nicht — die Daten sind ein CFD, kein MNQ.

### Tests

343 -> **349**. Neu: vier in `tests/test_engine.py` (Abbruch bei fehlender
Spalte, Sammeln ueber verschachtelte Regeln, Konstanten zaehlen nicht,
Bibliothek gegen die vorhandenen Spalten) und zwei in
`tests/test_metrics_and_splits.py` (Robustheit ohne bzw. mit positivem
In-Sample-Vorteil). Gegenprobe in der Linux-Ersatzumgebung gruen; der
Windows-Lauf steht wie immer noch aus.

---

## 22. `walkforward`-Kommando: der tote Code hat einen Einstiegspunkt (23.08.2026)

Der Masterplan führt das als **X.2** und als P1 direkt hinter dem
Dukascopy-Provider: `backtest/splits.py::walk_forward_windows` war gebaut,
getestet und wurde im Plan mehrfach als Kern der Confirmation-Phase
vorausgesetzt — aufrufbar war es nur aus einem Python-Interpreter. Die CLI
kannte `list`, `run`, `compare`, `optimize` und sonst nichts.

Das ist eine Erreichbarkeitslücke, keine Entwurfsfrage, und berührt keinen der
rückfragepflichtigen Bereiche (keine Entry-/Stop-/Ziel-Regeln, kein Umfang der
Setup-Familien, nichts an der Ordersperre) — deshalb ohne Rückfrage erledigt.
Die P0-Entscheidung selbst steht weiterhin bei Laurin.

### Neu: `backtest/walkforward.py`

- `lauf(...)` rechnet eine Strategie über alle rollierenden Testfenster und
  liefert einen `WalkForwardBericht` mit einem `FensterErgebnis` je Fenster.
- Die Indikatoren entstehen **einmal über die Gesamthistorie** und werden erst
  danach geschnitten — dieselbe Begründung wie bei `compare.prepare_split`
  (Invariante 5): ein isoliert vorbereitetes Fenster hätte in seinen ersten
  Kerzen keinen gültigen SMA(50) und die Strategie bliebe dort stumm.
- `bericht_text(...)` und `export_walkforward(...)` für Konsole und CSV.

### Drei Entscheidungen, die dabei getroffen wurden

**1. Es ist ausdrücklich kein Walk-Forward mit Optimierung.** Die Strategie
läuft mit festen Parametern durch alle Fenster; im Trainingsfenster wird
nichts gesucht. Das Trainingsfenster ist reiner **Vorlauf** und geht in keine
Kennzahl ein. Genau so ist es auch beschriftet — `MODUS_FESTE_PARAMETER` steht
im Bericht, und darunter der Satz, dass der Lauf keine Parameterwahl
bestätigt. Eine Auswertung, die aussieht wie ein Walk-Forward, aber keine
Optimierung enthält, wäre nach Invariante 10 eine Schätzung im Gewand einer
Messung.

Die Fassung **mit** Parametersuche je Fenster ist die nächste Stufe. Sie ist
Research-Entwurf und gehört in den Masterplan-Strang, nicht in eine
Nebenentscheidung.

**2. Summen bleiben bei überlappenden Fenstern leer.** Bei
`step_bars < test_bars` steckt dieselbe Kerze in mehreren Testfenstern; eine
Summe über Trades oder Netto-P&L zählte sie mehrfach. `summe_trades` und
`summe_netto` liefern dann `None`, und der Bericht **schreibt hin**, warum die
Zeile fehlt — eine kommentarlos fehlende Zeile hält man für einen
Darstellungsfehler statt für eine Aussage (dieselbe Überlegung wie bei
`print_report` und der Robustheitskennzahl, Abschnitt 21).

**3. Die Fenstergrößen haben keinen Vorgabewert.** `--train-bars` und
`--test-bars` sind Pflichtargumente. Ein stiller Vorgabewert ließe einen Lauf
entstehen, dessen Fensterwahl niemand bewusst getroffen hat — und die
sinnvolle Größe hängt an Kerzenlänge und Zeitraum. `--step-bars` ist optional
und entspricht ohne Angabe `--test-bars`, also keiner Überlappung.

Die aussagekräftigste Zahl des Berichts ist **`anteil_positiver_fenster`**:
eine Strategie, die insgesamt im Plus steht, aber nur in zwei von zwanzig
Fenstern verdient hat, lebt von einer einzelnen Marktphase. `None` statt `0.0`,
solange es keine Fenster gibt — „kein Fenster war positiv" und „es gab keine
Fenster" sind verschiedene Aussagen.

### Kein stiller Ausfall bei zu kurzer Historie

`walk_forward_windows` liefert bei `train_bars + test_bars > len(df)`
kommentarlos eine leere Liste. Das liest sich wie „die Strategie hat nichts
gefunden" statt wie „die Historie reicht für diese Fenstergrößen nicht".
`lauf(...)` prüft vorher und wirft `WalkForwardError` mit beiden Zahlen.

### `pruefe_chronologie`

Wirft, wenn ein Testfenster nicht hinter seinem Trainingsfenster liegt. Das ist
ein Lookahead-Test, kein Formtest — bei vertauschter Reihenfolge liefe die
Auswertung auf Daten, die zum Entscheidungszeitpunkt noch nicht existierten.

### Tests

349 -> **361**. `tests/test_walkforward.py`, zwölf Stück: Chronologie der
Fenster und die Gegenprobe mit vertauschten Fenstern, Nicht-Überlappung bei
`step_bars == test_bars`, ein Ergebnis je Fenster, Abbruch bei zu kurzer
Historie, Modusangabe, Summen bei und ohne Überlappung, `None` statt `0.0` ohne
Fenster, korrekte Zählung des positiven Anteils, und zwei auf der CLI (das
Kommando existiert; ohne Fenstergrößen bricht der Parser ab).

Zusätzlich von Hand gegen `data/DEMO_1m.csv` durchlaufen: zehn Fenster, Tabelle
und Hinweistext erscheinen. Die **Zahlen daraus sind bedeutungslos** — DEMO ist
ein synthetischer Zufallspfad.

Gegenprobe in der Linux-Ersatzumgebung grün; der Windows-Lauf steht wie immer
noch aus.

### Weiterhin offen und weiterhin Laurins Entscheidung

Der P0-Punkt (Ideen-Dauerlauf / Dukascopy-Provider / MCP-Startzeit) ist damit
**nicht** vorweggenommen. Insbesondere hilft `walkforward` erst dann wirklich,
wenn X.1 erledigt ist: über die Backtest-Seite erreichbar sind bislang nur
CSV-Dateien aus `data/`, und das ist dort ausschließlich der synthetische
`DEMO_1m.csv`. Ein Walk-Forward über zehn Jahre Näherungshistorie ist der erste
Lauf, der etwas aussagen würde.

---

## 23. Gegenprobe vom Wachhund, 23.08.2026 mittags — 361 Tests grün auf `c33c818`

Der geplante Lauf „resume-project-work" hat um 12:47 den Stand unabhängig
nachgemessen. Drei Befunde, alle bestätigend:

1. **Die Testsuite ist grün.** `python3 werkzeuge/pytest_linux.py` in der
   Linux-Ersatzumgebung: **361 passed** in 34 s, gegen den Arbeitsbaum auf
   `c33c818` („walkforward-Kommando"). Das deckt sich mit der in Abschnitt 22
   genannten Zahl. **Der Windows-Lauf steht weiterhin aus** — die Ersatzumgebung
   ist eine Gegenprobe, kein Ersatz (Invariante 10, `CLAUDE.md`).

2. **Die Arbeitssitzung ist endgültig weg.** Abschnitt 16 vermutete es, jetzt ist
   es geprüft: die vollständige Sitzungsliste (113 Einträge) enthält
   `local_143554db-…` nicht. Alle 113 sind Läufe des Wachhunds selbst. Der
   Wachhund hat in diesem Lauf zudem **kein** Werkzeug, um einer Sitzung eine
   Nachricht zu schicken. Die Automatik hat damit weder eine ausführende Instanz
   noch einen Weg, eine neue anzusteuern — sie läuft leer weiter, bis Laurin eine
   neue Sitzung startet (Vorgabe: `claude-opus-5`).

3. **Der Git-Index ist veraltet, der Arbeitsbaum nicht.** `.git/index` datiert vom
   23.08. 04:15, `HEAD` steht auf 10:48. Folge: `git status` meldet
   `backtest/walkforward.py`, `tests/test_walkforward.py`, `werkzeuge/*` und
   `docs/BASISVERMESSUNG_2026-08-23.md` gleichzeitig als **gelöscht** (Index) und
   **unversioniert** (Arbeitsbaum), und ein Dutzend Dateien als „MM".
   Das ist eine Anzeigefolge des eingefrorenen Index, **kein** Datenverlust:
   `git diff HEAD` ist inhaltlich leer, alle sechs Dateien liegen im
   `HEAD`-Baum und im Arbeitsbaum.

   **Gefahr:** ein arglos abgesetztes `git commit -a` in diesem Zustand würde
   die sechs Dateien aus der Versionierung entfernen. Erst die Aufräumanweisung
   aus Abschnitt 16 ausführen, dann einmal `git reset` (setzt nur den Index auf
   `HEAD`, rührt den Arbeitsbaum nicht an), dann ist `git status` wieder sauber.

   Die Sperrdateien sind aus der Linux-Umgebung weiterhin nicht löschbar
   (`rm` → *Operation not permitted*), erneut geprüft. Die vollständige
   Anweisung für den Projektordner unter Windows:

   ```
   del ".git\index.lock" ".git\HEAD.lock"
   del /s ".git\objects\tmp_obj_*"
   git reset
   ```

   Im Ordner `.git/` liegen zusätzlich vier leere Sondierungsdateien früherer
   Läufe (`probe.tmp`, `testschreib`, `zz_test_delete_me.txt`,
   `loeschtest_watchdog`). Sie stören Git nicht und können bei Gelegenheit mit
   weg.

**Nicht angefasst** wurde der offene P0-Punkt. X.1 (Dukascopy-Provider) wäre die
technisch naheliegendste Arbeit und ist als Erreichbarkeitslücke eingestuft —
sie umzusetzen hieße aber, die P0-Reihenfolge zu wählen, und genau das ist
Laurins Entscheidung (Master-Auftrag, rückfragepflichtiger Punkt d).


---

## 24. Handelskosten und Startzeit (23.08.2026)

### 24.1 Kostenprofile statt Pauschale

`backtest/kosten.py`. Bis zum 23.08. rechnete der Backtest mit
`commission_per_side: 2.50` — einer Zahl **ohne Herkunftsangabe**, die drei
Dinge verdeckte, die sich unterschiedlich verhalten:

| Posten | Verhalten |
|---|---|
| Broker-Kommission | verhandelbar, ändert sich beim Brokerwechsel |
| Börse / Clearing / NFA | **nicht** verhandelbar, bleiben gleich |
| Slippage | **keine Gebühr** — Ausführungsqualität, steckt im Füllkurs |

Wer sie zusammenwirft, hält Kosten für beeinflussbar, die es nicht sind.

**Drei Profile:** `private_ninjatrader` (0,95/Seite, belegt), `lucid`
(0,50/Seite, **Annahme**), `pauschale_alt` (2,50/Seite, zum Nachrechnen).

**Die Aufteilung wird nicht erfunden.** Belegt ist nur die Summe, deshalb
bleiben `broker_kommission_je_seite` und die anderen Posten `None`. Erfundene
Einzelposten, die zufällig richtig aufsummieren, sähen aus wie eine Recherche.
`__post_init__` prüft, dass eine *angegebene* Aufteilung zur Summe passt, und
lehnt ein Profil **ohne Quellenangabe** ab — genau diese Angabe fehlte der
Altpauschale, weshalb sich nie feststellen ließ, ob sie stimmte.

**Nachgewiesen:** `vwap_trend` auf dem DEMO-Datensatz ergibt unter allen drei
Profilen **identisch 70 Trades**; nur die Netto-P&L unterscheidet sich
(374,06 / 437,06 / 157,06 USD), auf den Cent passend zur Kostendifferenz. Ein
Profil ändert also **nur** die Kosten — sonst verglichen zwei Läufe zwei
verschiedene Strategien.

`--kostenprofil` in der CLI erlaubt einen zweiten Lauf ohne Config-Änderung.
Der Bericht weist Profil, Quelle und Annahmestatus aus.

> **Folge für die Basisvermessung:** Sie lief unter der Altpauschale und ist
> damit **zu pessimistisch**. Der Bruttobefund bleibt gültig.

### 24.2 Startzeit — und zwei Korrekturen

pandas wird nicht mehr beim Serverstart geladen:

- `mcp_server/bars.py` braucht es nur in Typannotationen → `TYPE_CHECKING`.
- `DEFAULT_BARS_IN_OUTPUT` von `snapshot.py` nach `bars.py` verschoben.
  `server.py` braucht die Konstante als Vorgabewert einer Signatur — allein ihr
  Import zog pandas herein.
- `build_snapshot_payload` wird erst in der Werkzeugfunktion importiert.

**Gemessen:** Handshake **2,6 s → 1,73 s**, Module **1190 → 751**.

**Zwei Korrekturen an der früheren Diagnose in dieser Datei:**

1. Die genannten **7,5 s waren eine Kaltmessung.** Warm waren es 2,6 s.
2. Warm dominiert **nicht pandas**, sondern die Bibliothek `mcp.server`
   selbst — sie lädt ihren Client-Code mit (`mcp.client` über
   `mcp.client._input_required`). Daran lässt sich von hier aus nichts ändern.

Der Gewinn liegt vor allem im **Kaltstart**, wo pandas rund 18 von 30 Sekunden
ausmachte. Warm sind es 0,9 s.

**Lehre:** Eine Startzeit einmal kalt und einmal warm messen, bevor man die
Ursache benennt. Der Unterschied betrug hier den Faktor drei und zeigte auf
einen anderen Schuldigen.
