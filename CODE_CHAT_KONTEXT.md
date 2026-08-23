# CODE_CHAT_KONTEXT

**Technisches Langzeitgedächtnis des Projekts "Claude Chart Bot".**

Stand: 2026-08-23 (Nachprüfung des Branch-Stands; Inhalt sonst 2026-08-22,
nach Entfernung des Legacy-Pfads). Gegen den tatsächlichen
Projektordner geprüft, Testzahlen auf Windows **gemessen**.

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

**Testsuite: 343 Tests, alle grün.** `.venv\Scripts\python.exe -m pytest`

| Datei | Tests |
|---|---|
| `test_mcp_snapshot.py` | 44 |
| `test_dukascopy.py` | 21 |
| `test_ideas.py` | 50 |
| `test_levels_structure.py` | 39 |
| `test_ntbridge.py` | 37 |
| `test_instruments_sessions.py` | 26 |
| `test_event_risk.py` / `test_patterns.py` | je 22 |
| `test_extended_indicators.py` | 21 |
| `test_structure.py` | 17 |
| `test_metrics_and_splits.py` | 16 |
| `test_indicators.py` | 15 |
| `test_engine.py` | 13 |

Verlauf: 124 → … → 334 → 370 → 373 → 316 → 337 → 342 → **343**.

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
3. **MCP-Serverstart dauert ~7,5 Sekunden.** Gemessen über einen echten
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
Tradovate vollständig raus. Für Tradovate ist das seit dem 22.08. erfüllt
(zwei Restdefekte in `backtest/cli.py` und `csv_provider.py`, siehe
`MASTERPLAN.md` C.1).

**Für MGC widerspricht der Code dem Override**, und das wird hier festgehalten
statt still bereinigt:

- MGC wird **nicht** protokolliert, gestreamt oder gespeichert — insoweit ist
  der Override bereits erfüllt.
- MGC steht aber im **Instrument-Register** (`common/instruments.py`) und in
  **14 Testfällen**. Der MGC-Verfallstest ist der einzige, der beweist, dass
  `expiry_rule` instrumentspezifisch ist und nicht eine hartverdrahtete
  MNQ-Annahme (Bug-Lehre 9). Entfernt man ihn, kann die MNQ-Regel später still
  falsch werden.

**Empfehlung in `MASTERPLAN.md` C.2:** Register-Eintrag behalten, MGC aus
nutzersichtbaren Texten entfernen. **Entscheidung steht bei Laurin aus.**

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

---

## 17. MASTERPLAN.md erstellt (23.08.2026)

Der Master-Auftrag vom 22.08.2026 verlangte eine Bestandsaufnahme plus
Masterplan fuer die langfristige Architektur. Da die dafuer vorgesehene
Arbeitssitzung nicht mehr existiert (Abschnitt 16), ist `MASTERPLAN.md`
stattdessen von der Watchdog-Instanz gegen den tatsaechlichen Code auf
`main` (`3ca5fb5`) geschrieben worden — nicht gegen die Dokumentation.

**Es ist ein Planungsdokument, keine Arbeitsanweisung.** Welcher P0-Punkt
zuerst umgesetzt wird, entscheidet Laurin.

### Was die Pruefung gegen den Code zutage foerderte

Vier Befunde, die vorher nirgends standen:

1. **`backtest/data/__init__.py::create_provider` kennt nur `csv`.** Der
   Dukascopy-Speicher mit 3 179 672 Kerzen (384 MB) ist ueber den normalen
   Backtest-Pfad **nicht erreichbar**. Die Daten liegen da, die Engine kommt
   nicht dran. Schwerster der vier Befunde.
2. **`backtest/cli.py:276`** bietet `--provider choices=("csv", "tradovate")`
   an. Der Provider ist geloescht; der Aufruf braeche mit
   `DataProviderError` ab. **Dieselbe Fehlerklasse wie das bereits behobene
   `fetch`-Kommando** — kein Test ruft es auf.
3. **`backtest/data/csv_provider.py:57`** weist den Nutzer in einer
   Fehlermeldung an, "Historie von Tradovate herunterladen" — ein Weg, den
   es nicht mehr gibt.
4. **`splits.walk_forward_windows` ist getestet und von der CLI aus nicht
   aufrufbar.** Die CLI kennt `list`, `run`, `compare`, `optimize` — kein
   `walkforward`. Toter, aber korrekter Code.

Zusaetzlich: **MGC steht noch an acht Stellen im Code**, obwohl der
Projekt-Override vom 22.08.2026 sagt, es sei vollstaendig entfernt.
`list_instruments` liefert MGC weiterhin aus. Widerspruch zwischen Vorgabe
und Code — festgestellt, nicht stillschweigend aufgeloest.

Die uebrigen Tradovate-Fundstellen (`common/contracts.py`,
`backtest/data/base.py`, `mcp_server/bars.py`, `mcp_server/context.py`,
`ntbridge/__init__.py`, `config.yaml:165,303`) sind ausdruecklich als
historisch markierte Absaetze und damit die gewollte *Warum*-Dokumentation.
Nicht anfassen.

### Priorisierung im Plan

P0-1 Etappe C in Betrieb nehmen · P0-2 MGC entfernen · P0-3 Dukascopy als
`DataProvider` registrieren · P0-4 die zwei Tradovate-Reste in ausfuehrbarem
Code.

Zwei Punkte sind **zeitkritisch, nicht wichtigkeitskritisch**: die Regime
Engine (P1-5) und Konfidenzintervalle in `metrics.py` (P1-3). Beide sind
spaeter technisch genauso machbar, aber spaeter **nutzlos** fuer alles, was
in der Zwischenzeit protokolliert oder behauptet wurde — ein Regime-Feld
laesst sich an bereits geschriebene Ideen nicht rueckwirkend anhaengen.

### Offene Entscheidung, die P0-1 blockiert

**4 oder 12 Setup-Familien, bevor die Protokollierung anlaeuft?** Das ist
eine Entscheidung ueber den Umfang der Setup-Familien und damit
ausdruecklich Laurins. Empfehlung im Plan: mit den vorhandenen 4 sofort
starten, die 8 weiteren schrittweise nachziehen — verlorene Sammeltage sind
nicht nachholbar, fehlende Setups schon.

### Neue Lookahead-Gefahr, die der Plan benennt

**FRED-Serien werden revidiert.** Der heute ausgelieferte Wert fuer Maerz
2024 ist nicht der Wert, der im Maerz 2024 bekannt war. Wer die heutige
Serie in einen Backtest von 2024 einsetzt, hat einen Lookahead, den *nichts
an den Kursen verraet* — exakt die Fehlerklasse, die bei den
Dukascopy-Daten schon einmal zugeschlagen hat (r = -0,06 statt +0,95).
Konsequenz im Plan: Makrodaten nur als **Vintage** mit
Veroeffentlichungszeitstempel (ALFRED), sonst `null` mit Begruendung.
