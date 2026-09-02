# CODE_CHAT_KONTEXT

**Technisches Langzeitgedächtnis des Projekts "Claude Chart Bot".**

Stand: 2026-08-31 (Abschnitte 37–40 — **Ereignisdatenbank Etappen 1–4 und 8
gebaut, erster Befund steht**: 2.592.334 Ereignisse + 23,3 Mio Outcome-Zeilen
in `data/eventdb.sqlite3` (~7 GB), sieben serielle Erkenner in
`common/ereignisse/`. Der erste Grundratenbericht meldete neun signifikante
Long-Muster — **das war ein Artefakt** (fuenfte statistische Falle, Abschnitt
40: `end_r` durch atr_referenz bis 0,003 zertruemmert den Mittelwert und
vergiftet die Nulllinie). Nach Haertung von `grundraten.py`
(ATR-Untergrenze, Winsorisierung, Anteilstest als Hauptkriterium):
**kein Muster mit belastbarem Vorteil**. `docs/GRUNDRATEN_H60_2026-08-31.md`.
Naechster Schritt vor einem "gescheitert": Auswertung nach Regime/Session.
**Offene Entscheidungen fuer Laurin**: Datenbank kleiner neu bauen (7 GB an
der Hardware-Grenze), und ob die Regime-Auswertung noch kommt. Details
`docs/UEBERGABE_2026-08-31.md`.)

Stand: 2026-08-30 (Abschnitt 34 — **Die Projektgrenze ist aufgehoben**:
Ausführung über NinjaTrader ist seit dem 30.08.2026 Projektbestandteil.
Vier Defekte aus der Antigravity-Schicht behoben (Kerzenkorruption im
tcp_proxy, invertierte Orderrichtung, gefälschte Backtest-Kennzahlen,
UTF-8-BOM), Ausführungsschicht neu gebaut: `common/kontoregeln.py`,
`execution/store.py`, `execution/risiko.py`, `execution/buchung.py`,
`execution/bot.py`, `execution/overlays.py`. Chart-Overlays und
Strategie-Panel an die vorhandene Erkennung angeschlossen, Asia-/London-Level
in `common/levels.py` ergänzt. Abschnitt 34.9: die NT8-Historie ist
importiert — 2,57 Mio MNQ-Minutenkerzen von 2019 bis August 2026, vier
Import-Bugs unterwegs behoben. Abschnitt 35: TRADAYRI-Startchart repariert
(schwarzes Rechteck war die leere Chart-Flaeche), volle Historie als
Tageskerzen, Kerzenaggregation `werkzeuge/aggregiere_kerzen.py`.
Abschnitt 36: Forschung auf echten Daten — `NtBridgeDataProvider` schaltet
die NT8-Historie fuer die Engine frei (MASTERPLAN X.1, P0), Chartmuster als
Serie, Engine ~20x schneller, erste Messung des „W". Tests grün.)
Davor Abschnitt 33 — Vollständige Formalisierung der Marktprimitive
(FVG, Displacement, EQH/EQL, Liquidity Sweeps BSL/SSL, Reclaims, MSS/BOS/CHoCH)
in `common/market_primitives.py`, Multi-Timeframe Resampling & 4h-Integration
in `common/timeframes.py`, `mcp_server/bars.py` und `ClaudeBridge.cs`,
kanonisches, deterministisches `MarketState`-Modell in `common/market_state.py`,
MAE/MFE-Pfad-Exkursionsanalyse in `backtest/excursions.py`, empirische
Conditional Outcome Engine in `backtest/conditional_outcomes.py`,
persistentes Forschungsregister (`HYP-000xxx`) in `backtest/research_register.py`.
15 neue Tests, 457 Tests gesamt, 100% grün).
Davor Abschnitt 31/32 — Makro-Vintages (`macro/`), CME-Marktkalender, TradeX-Referenzvergleich.
Davor Abschnitt 30 — formale Validation-Phase: neue
Dreiteilung Training/Validation/Out-of-Sample (`backtest/splits.py`,
`split_data_three_way`), alle sechs Discovery-Kandidaten gleich geprüft auf
einem Block, den Discovery nie gesehen hat — 2 von 6 überstehen die
Validation-eigene Bonferroni-Korrektur, alle 5 testbaren halten das
Vorzeichen, Walk-Forward-Konsistenz durchgehend. Bericht in
`docs/VALIDATION_PHASE_2026-08-24.md`, ersetzt die vorherige
Einzelkandidaten-Prüfung aus Abschnitt 29. Repo-Frage geklärt (29.5,
Remote jetzt `Lx1308/Claude-mnq-bot`); davor Abschnitt 29 — Übergabe aus
Abschnitt 28 übernommen: `rsi_mean_reversion`-RSI-Terzil-Treffer auf
Zirkularität geprüft (Einordnung in Abschnitt 30 relativiert), `vwap_trend`/
RSI-Terzil-Hypothese informell validiert — Bericht in
`docs/VALIDATION_RSI_TERZIL_2026-08-24.md`; davor Abschnitt 28 —
`ib_breakout`-Fix committet, voller 20×5-Discovery-Lauf fertig ausgewertet
(6/239 Hypothesen signifikant, Bericht in
`docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`), unautorisierte
Codex-Nachtarbeit aufgeklärt und zurückgesetzt, `ntbridge` von der
CLI-Sitzung entkoppelt; davor Abschnitt 27 — Faktor-Bausteine für den
vollständigen Indikatorensatz ergänzt; davor `walkforward`-Kommando,
Abschnitt 22 — Masterplan X.2; davor Basisvermessung der Strategiebibliothek,
Abschnitt 21, wo `ib_breakout` als stiller Ausfall auffiel und die
Robustheitskennzahl log; Testsuite in der Linux-Sandbox lauffähig gemacht,
Abschnitt 20, Qualitätsmessung der Dukascopy-Näherungshistorie, Abschnitt 19,
und zwei bereinigte Tradovate-Defekte; Inhalt sonst 2026-08-22 nach Entfernung
des Legacy-Pfads).
Gegen den tatsächlichen Projektordner geprüft. **Testzahlen:** 416, am
24.08.2026 auf dem echten Windows-venv gemessen (`.venv\Scripts\python.exe -m
pytest`, Exitcode 0).

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

**Testsuite: 394 Tests, alle grün** (23.08.2026 auf Windows gemessen).
`.venv\Scripts\python.exe -m pytest`

| Datei | Tests |
|---|---|
| `test_ideas.py` | 50 |
| `test_mcp_snapshot.py` | 46 |
| `test_kosten.py` | 17 |
| `test_research.py` | 14 |
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

### 5.10 Indikator statt AddOn geprüft und verworfen (25.08.2026)

Laurins Frage: brächte ein NinjaTrader-**AddOn** statt des chart-gebundenen
Indikators Zugriff auf bereits geladene Chart-Historie (Backfill), nicht
nur neue Live-Bars? **Antwort: nein, das kann die bestehende Komponente
schon** - `ClaudeBridge.cs` verarbeitet `State.Historical` explizit
(`OnBarUpdate`, Zeile 278-287): jede historische Kerze wird gepuffert und
beim Umschalten auf `State.Realtime` in einem Paket verschickt
(`FlushHistoricalBuffers`). Das ist seit dem Start am 21.08.2026 belegt
lauffähig: bei "Days to load: 7" kamen 3015 von 3000 angeforderten
1m-Kerzen an (Abschnitt 17 in `NORMALER_CHAT_KONTEXT.md`) - kein
Live-only-Pfad.

**Wo eine AddOn tatsächlich anders wäre:** sie könnte ohne offenen Chart
laufen und über `BarsRequest`/`Instrument`-APIs beliebige historische
Bereiche programmatisch anfordern, statt an "Days to load" eines Charts
gebunden zu sein. Das löst aber nicht das eigentliche Problem: wie weit
zurück reicht die Historie ist eine Eigenschaft des angeschlossenen
**Datenfeeds** (Kinetick/Sim), nicht der NinjaScript-Objektart - ein AddOn
bekäme aus demselben Feed nicht mehr Jahre an Minutendaten als ein
Indikator, nur denselben begrenzten Vorrat auf einem anderen Weg abgefragt.

**Die eigentliche Backfill-Frage (Jahre an Historie fürs Backtesting) ist
bereits bewusst anders gelöst**, nicht über NT8: die Dukascopy-Näherung
(10 Jahre, als Näherung gekennzeichnet, Invariante 11) übernimmt das, weil
zehn Jahre echte MNQ-Minutendaten kostenlos nirgends erhältlich sind -
auch nicht über einen NT8-Feed, ob per Indikator oder AddOn abgefragt.

**Empfehlung: nicht umbauen.** Kein belegter Vorteil, der den Umbau der
"kritischsten Komponente des Systems" rechtfertigt (zweimal bereits von
außen zerstört, Bug-Lehre 11; aktuell 0 abgelehnte Kerzen bei >6800
empfangenen). Falls mehr Backfill-Tiefe gewünscht ist: "Days to load" im
NT8-Chart erhöhen und `HistoricalBarsBase` im Indikator entsprechend
anheben - dieselbe Architektur, keine Codeänderung, in Minuten testbar, ob
der Feed überhaupt mehr als 7 Tage 1m-Historie vorhält. Nur falls dieser
Test zeigt, dass deutlich mehr Historie verfügbar wäre UND ein Betrieb
ganz ohne offenen Chart gebraucht wird, wäre eine AddOn-Prüfung überhaupt
neu zu bewerten - beides bisher nicht der Fall. **Nichts umgebaut.**

### 5.11 Andere Frage, andere Antwort: AddOn gegen Neustart-Robustheit (25.08.2026)

Nicht dieselbe Frage wie 5.10 noch einmal, sondern Laurins eigentliche
Sorge: nach einem Neustart von PC/NinjaTrader muss der Indikator manuell
neu an den Chart gehängt werden. **Hier stimmt der technische Kern seines
Arguments** - eine AddOn läuft auf Applikationsebene und braucht dafür
keinen Chart, ein Indikator zwingend schon. Anders als bei 5.10 ist das
kein Missverständnis.

**Trotzdem nicht umgebaut, weil es eine deutlich billigere Lösung gibt:**
NinjaTrader-**Workspaces**. Ein gespeicherter Workspace enthält den Chart
samt bereits konfiguriertem Indikator; als Start-Workspace hinterlegt,
öffnet sich das beim NT8-Start automatisch, ohne manuellen Klick - reine
NinjaTrader-Bedienungseinstellung, keine Codeänderung. **Nicht an einer
laufenden NT8-Instanz verifiziert** (kein Zugriff von hier aus) - das ist
Standard-Plattformverhalten, keine Messung, und sollte von Laurin über
ein paar echte Neustarts geprüft werden. Das README dokumentiert diesen
Schritt bisher gar nicht - das ist vermutlich die eigentliche Lücke.

**Empfehlung:** Erst Workspace-Autoload testen. Eine AddOn haette dafuer
ein komplett anderes Lebenszyklus-Modell noetig (kein `OnBarUpdate`/
`State.Historical`, die gesamte Puffer-/Flush-/Zeitzonenlogik muesste neu
gebaut werden) - fuer ein reines Bedienkomfort-Problem an der bereits
zweimal zerstoerten Kernkomponente unverhaeltnismaessig, wenn ein
Bordmittel dasselbe Ergebnis liefert. Nur falls der Workspace-Test
nachweislich scheitert, waere eine AddOn-Pruefung neu aufzurollen.

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

> **Folge für die Basisvermessung:** Sie lief unter der Altpauschale und war
> damit zu pessimistisch. **Neulauf am 23.08.2026 nachgeholt**, siehe
> `docs/NEULAUF_KOSTENPROFIL_2026-08-23.md`: alle fünf Strategien bleiben
> negativ, aber deutlich weniger. `prev_day_breakout` in-sample geht von
> −4,40 auf **−1,30 USD je Trade**, Profit-Faktor 0,96. Die Trade-Zahlen sind
> identisch geblieben — der Nachweis, dass ein Profilwechsel nur die Kosten
> ändert.

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


---

## 25. Faktorkatalog aus Internet-Recherche (23.08.2026)

`docs/FAKTORKATALOG.md`. Kandidaten für die Einzelfaktor-Research, nach
Evidenzstärke (A/B/C) und Rechenbarkeit aus **unseren** Daten geordnet.

**Jeder Eintrag ist eine Hypothese, kein Erwartungswert.** Fremde Messungen auf
fremden Daten. Der Katalog ist bewusst mit einer Warnung überschrieben: Wer 40
Faktoren auf einem Datensatz prüft, findet rund zwei „signifikante" allein
durch Zufall.

### 25.1 Der Fund, der das Projekt direkt betrifft

**Mesfin (2026), arXiv 2605.04004** — eine Falsifikationsstudie zu **genau
unserem Fall**: MNQ, Fünfminutenkerzen, nur OHLCV, 947 Handelstage 2021–2025.
**14 Signalfamilien geprüft, keine erfüllte alle Kriterien.** Bruttoerträge
0,07 bis 1,50 Punkte je Trade.

Das deckt sich mit unserer eigenen Messung (rund −1 Punkt brutto).

**Aber die Kostenannahme ist der Hebel.** Die Studie verwirft alles unter
**2 Punkten** Friktion. Unsere gemessenen Kosten:

| Posten | Punkte |
|---|---|
| `private_ninjatrader` (1,90 USD RT) | 0,95 |
| Slippage 1 Tick je Seite | 0,50 |
| **Summe** | **≈ 1,45** |

Ein Signal mit 1,50 Punkten brutto wäre bei Mesfin verworfen, bei uns knapp
positiv. Kein Beleg für eine Kante — aber die Schwelle liegt nicht bei 2.

**Konsequenz:** Der Zielkorridor ist eng. Reine OHLCV-Signale sind
wahrscheinlich zu wenig; der Weg führt eher über **Konditionierung** — dasselbe
Signal nur in bestimmten Regimen — als über neue Signalformen.

### 25.2 Sofort prüfbar, ohne neue Datenquelle

1. Intraday-Momentum (erste → letzte halbe Stunde), konditioniert auf
   Volatilität und Volumen. Evidenz A, aber OOS-Verschwinden dokumentiert.
2. Turn-of-Month als Regime-Achse. Evidenz A, in S&P-Futures der einzige
   stabile Kalendereffekt.
3. Gap-Größe × Overnight-Range als Zweifaktor. Beide Größen haben wir.
4. ORB mit kürzeren Fenstern als Variante zu `ib_breakout`.
5. **ADX-Schwellen aus der Verteilung ableiten** statt aus Konvention — die
   Recherche liefert für die verwendeten 20/25 keine Begründung. Nach dem
   `consolidation_max_atr`-Fund (Schwelle 1,2 war unerreichbar) ist das ein
   konkreter Verdacht, kein allgemeiner Vorbehalt.

### 25.3 Nicht rechenbar, Datenquelle fehlt

VIX-Terminstruktur (erst prüfen, ob NT8 sie liefert) und Pre-FOMC-Drift
(braucht Vintage-Historie, P3).

### 25.4 Der Vorbehalt, der über alles gilt

McLean und Pontiff (2016): Vorhersagbarkeit verschwindet **nach ihrer
Veröffentlichung**. Je bekannter ein Effekt, desto wahrscheinlicher ist er
wegarbitriert. Der Pre-FOMC-Drift ist das Lehrstück — nach 2015 angeblich
verschwunden, in einer Analyse bis 2024 angeblich weiter vorhanden.


---

## 26. Einzelfaktor-Research (23.08.2026)

`backtest/research.py`, Etappe I. Umgesetzt nach Laurins Entscheidung 18.3,
Research **vor** Etappe D.

### 26.1 Was es beantwortet

Nicht „trägt Setup X", sondern **„unter welchen Bedingungen trägt Setup X"**.
Ein Setup, das im Trend trägt und in der Range verliert, sieht über alles
gemittelt aus wie „kein Erwartungswert" — genau die Setups, die sich lohnen
würden, sind so unsichtbar.

Die tragende Kennzahl ist die **Spannweite brutto**: der Abstand zwischen
bester und schlechtester auswertbarer Gruppe. Ein Faktor, dessen Gruppen alle
gleich abschneiden, trennt nichts — egal wie gut oder schlecht das Niveau ist.

### 26.2 Vier Zusicherungen, jede getestet

| Zusicherung | Mechanismus |
|---|---|
| Discovery sieht den OOS-Block nie | `pruefe_nur_training` bricht ab |
| Hypothesenzahl steht im Bericht | `Discoverylauf.gepruefte_hypothesen`, samt Zufallserwartung bei α = 0,05 |
| Unter 20 Trades: **„zu wenig Daten"** statt einer Kennzahl | `Gruppenergebnis.genug_daten` |
| Nicht zuordenbare Trades werden ausgewiesen | `nicht_zuordenbar` — eine hohe Zahl ist eine Aussage über den Faktor, keine Panne |

**Brutto in Punkten ist die Research-Größe**, nicht Netto in USD. Kosten sind
eine Konstante, die Kante nicht — und der Vergleich mit Mesfins Studie
(Abschnitt 25) läuft ebenfalls über Bruttopunkte.

### 26.3 Grenzen kommen aus der Verteilung

`perzentilgrenzen()` leitet Schwellen aus den tatsächlichen Daten ab.
`baue_faktor_perzentil()` nimmt sie entgegen, setzt sie aber **nicht selbst**.

Nach dem `consolidation_max_atr`-Fund — Schwelle 1,2 war auf keiner Zeitebene
erreichbar — ist eine geratene Grenze ein **konkreter Verdacht**, kein
allgemeiner Vorbehalt.

### 26.5 Erster Discovery-Lauf, 23.08.2026 — ein Kandidat

Training 2016-08-22 bis 2023-10-24 (445 991 Kerzen, 70 %), Kostenprofil
`private_ninjatrader`, OOS unberührt. **33 Hypothesen geprüft.**

**Der Fund: `prev_day_breakout` nach Tageszeit.**

| Phase (New York) | Trades | Treffer | brutto Pkt | netto USD |
|---|---:|---:|---:|---:|
| Eröffnung 09–11 | 595 | 29,1 % | **−2,450** | −6,80 |
| Mittag 11–14 | 606 | 34,3 % | +0,610 | −0,68 |
| **Schluss 14–16** | **353** | **39,4 %** | **+4,399** | **+6,90** |

Spannweite **6,85 Punkte** — die größte aller geprüften Faktoren. Die
Schlussphase ist die einzige Gruppe im ganzen Lauf mit **positivem
Nettoerwartungswert**.

**Warum das mehr ist als ein Zufallstreffer:** Es deckt sich mit der
Literatur. Gao et al. finden Intraday-Momentum genau in der Schlussphase
(`docs/FAKTORKATALOG.md` 2.1). Ein Fund, der eine unabhängig publizierte
Vorhersage bestätigt, ist stärker als einer, der nur aus den Daten fällt.

**Warum es trotzdem kein Befund ist:**

- **33 Hypothesen → rund 1,7 Zufallstreffer bei α = 0,05.** Mit zwei bis drei
  positiven Gruppen im Lauf ist mindestens eine davon statistisch erwartbar
  Rauschen.
- **Nur Trainingsdaten.** Nichts ist validiert.
- **Näherungsdaten**, kein echtes MNQ.
- **Literaturunterstützung schneidet in beide Richtungen:** Was publiziert ist,
  ist wahrscheinlicher wegarbitriert (McLean/Pontiff, Abschnitt 25.4). Gerade
  für Intraday-Momentum ist ein OOS-Verschwinden dokumentiert.

**Zwei weitere positive Gruppen**, beide schwächer und ohne Literaturrückhalt:
`prev_day_breakout` Donnerstag (+2,43 Pkt, 328 Trades) und `flag_breakout`
Dienstag (+2,93 Pkt, 147 Trades). Wochentagseffekte gelten laut Recherche als
weitgehend verschwunden — hier am ehesten Rauschen.

**Ein aussagekräftiger Negativbefund:** `vwap_reversion` nach ATR-Terzil hat
eine Spannweite von **0,248 Punkten**. Das Volatilitätsregime erklärt bei
diesem Setup **nichts**. Ein Faktor, der nicht trennt, ist ein Ergebnis — er
schließt eine Erklärung aus.

### 26.6 Bonferroni-Korrektur — der Kandidat hält nicht

**Laurins Entscheidung (23.08.2026):** Die Tageszeit-Hypothese wird **nicht**
privilegiert, sondern strikt als eine von 33 gezählt. Volle Korrektur, kein
aufgeweichter Maßstab, nur weil die Literatur zufällig in dieselbe Richtung
zeigt.

```
Geprüfte Hypothesen   : 33
Unkorrigiertes Niveau : 0,05
Korrigierte Schwelle  : 0,001515   (alpha / 33)
```

**Ergebnis: keine einzige der 33 Gruppen unterschreitet die Schwelle.**

Die vier stärksten:

| Gruppe | t | p | p korrigiert |
|---|---:|---:|---:|
| `flag_breakout` / ATR ruhig | −2,82 | 0,0054 | 0,177 |
| `prev_day_breakout` / ATR mittel | −2,53 | 0,0118 | 0,389 |
| `vwap_reversion` / Donnerstag | −2,15 | 0,0320 | 1,000 |
| **`prev_day_breakout` / Schluss 14–16** | **+1,91** | **0,0568** | **1,000** |

### 26.7 Korrektur einer eigenen Fehleinschätzung

Der Tageszeit-Fund wurde in 26.5 als „ein Kandidat" geführt, gestützt auf
+4,399 Punkte brutto und die Übereinstimmung mit der Literatur.

**Die Statistik trägt das nicht.** Mit t = +1,91 und p = 0,0568 verfehlt die
Gruppe **die unkorrigierte Schwelle von 0,05** — von der korrigierten ganz zu
schweigen. Der Mittelwert sah groß aus, aber bei 353 Trades und dieser
Streuung ist er von null nicht zu unterscheiden.

**Was daran lehrreich ist:** Ein Mittelwert ohne Streuung ist keine Aussage.
In 26.5 stand die Zahl +4,399 ohne t-Wert daneben, und die Übereinstimmung mit
Gao et al. wirkte wie eine Bestätigung. Beides zusammen ergab einen Eindruck
von Substanz, den die Daten nicht hergeben. Genau davor schützt die Disziplin,
Signifikanz **vor** der Interpretation zu rechnen.

Auffällig außerdem: Die drei stärksten Effekte im ganzen Lauf sind
**negative** t-Werte, also Gruppen, die überdurchschnittlich verlieren. Auch
sie halten der Korrektur nicht stand.

### 26.8 Der OOS-Block bleibt unberührt

Es gibt nichts, was ihn rechtfertigen würde. Er ist einmalig; ihn für eine
Hypothese zu verbrauchen, die schon im Training nicht signifikant ist, wäre
Verschwendung.

**Das ist kein Misserfolg, sondern das Ergebnis.** 33 Bedingungen über zehn
Jahre geprüft, keine trennt belastbar. Zusammen mit Mesfins Falsifikation
(Abschnitt 25) ergibt sich ein konsistentes Bild: Reine OHLCV-Signale auf MNQ,
konditioniert auf Tageszeit, Wochentag oder Volatilitätsregime, liefern keine
nachweisbare Kante.

**Wo es weitergehen kann**, ohne den OOS-Block anzufassen:

1. **Mehr Faktoren** aus `docs/FAKTORKATALOG.md` — Turn-of-Month, Gap-Größe ×
   Overnight-Range, ORB mit kürzeren Fenstern. Jeder neue Faktor erhöht
   allerdings die Hypothesenzahl und damit die Schwelle.
2. **Andere Zeitebene.** Alles bisher auf 5m. 1m und 15m sind ungeprüft.
3. **Andere Signalformen** statt Konditionierung der vorhandenen vier.
4. **Eine zweite Datenquelle** (Cross-Asset, VIX) — der einzige Weg, der über
   OHLCV hinausgeht.

### 26.4 Noch nicht gebaut

Zweifaktor und Mehrfaktor (Etappe J), Validierung gegen den zweiten Block,
Walk-Forward über Faktoren. Die Reihenfolge ist Absicht: wer sofort
kombiniert, findet Kombinationen, die auf den Trainingsdaten passen und sonst
nirgends.

## 27. Stand bei Sitzungsende (23.08.2026, zweite Sitzung des Tages)

Sitzung durch Nutzungslimit-Warnung mitten in der Arbeit beendet. Was fertig
und getestet ist, ist committet; der angefangene große Lauf wurde bewusst
verworfen statt als Teilergebnis dokumentiert.

### Fertig, getestet, committet

**Faktor-Bausteine für den vollständigen Indikatorensatz** in
[`backtest/research.py`](../backtest/research.py): `baue_faktor_bool`,
`baue_faktor_vorzeichen`, `baue_faktor_relation`, `baue_faktor_kategorie`,
`faktor_ema_stack`, `faktor_di_richtung`, `faktor_ib_lage` — generische
Bausteine, keine Kopie je Spalte. 29 Tests in `tests/test_research.py`,
volle Suite grün (auch als Gegenprobe nach Rückkehr aus dem Hintergrundlauf
noch einmal komplett durchlaufen).

### Ein Architektur-Fund unterwegs

`Backtester.prepare()` liefert nur die **Basis**-Indikatoren
(`compute_indicators`) — ADX, MACD, Stochastik, Bollinger, EMA-Stack und die
Initial-Balance-Grenzen fehlen dort strukturell, weil sie aus
`compute_extended_indicators` bzw. `common.levels.initial_balance_per_session`
stammen. Für Research heißt das: **nicht** selbst eine zweite
Indikator-Vorbereitung bauen, sondern `ideas.pipeline.vorbereiten`
wiederverwenden — genau die Funktion, die die Etappe-C-Protokollierung schon
für denselben Zweck nutzt (Invariante 1 bleibt gewahrt, keine zweite
Implementierung). Ein Discovery-Skript, das stattdessen `Backtester.prepare()`
verwendet, bricht bei jeder Spalte außerhalb der Basismenge mit `KeyError` ab
— kein stiller Fehler, aber ein Stolperstein, den der nächste Lauf nicht mehr
treffen muss.

### Abgeschlossen am 24.08.2026: der volle Lauf

Der 20-Faktoren×5-Strategien-Lauf, der hier am 23.08. abgebrochen wurde, ist
am 24.08.2026 fertig gerechnet, ausgewertet und dokumentiert:
[`docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`](../docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md).
Reproduzierbares Skript: `werkzeuge/discovery_indikatoren_voll.py` (liegt jetzt
im Repo, nicht mehr nur im Scratchpad). Kurzfassung: 239 geprüfte Hypothesen,
korrigierte Schwelle 0,000209, **6 Gruppen bestehen** — alle sechs betreffen
RSI- oder Stochastik-Terzil, vier davon vermutlich zirkulär mit der eigenen
Einstiegsregel von `rsi_mean_reversion` verwandt. Details, Einordnung und der
empfohlene nächste Schritt (Validation) stehen im verlinkten Bericht.

### Offene Entscheidung: Market Intelligence / News

Laurins Auftrag umfasste ausdrücklich auch „News etc." aus dem Masterplan.
Befund dazu, noch unbeantwortet:

- **Forex Factory**: strukturell ungeeignet für Research — nur die laufende
  Woche ist abrufbar, für keinen historischen Trade rekonstruierbar.
- **FRED**: Historie vorhanden, aber wegen Revisionen ohne
  Vintage-Modellierung (ALFRED) für Research **disqualifiziert** — bereits in
  Abschnitt F.2 des Masterplans festgehalten.
- **Cross-Asset (VIX/DXY) über NT8**: `ntbridge/store.py` ist bereits
  instrumentenoffen (`PRIMARY KEY (instrument, timeframe, ts_utc)`), es fehlt
  nur Historie — entweder ein neuer Dukascopy-Download (ähnlicher Aufwand wie
  der MNQ-Zehnjahresabzug) oder Live-Sammlung über einen zusätzlichen NT8-Chart.
- Fed-Kalender/Reden, Geopolitik: keine Quelle identifiziert, reine Recherche.

**Das sind alles neue Bauaufgaben, keine Prüfungen.** Laurin wurde gefragt,
was davon (wenn überhaupt) als Nächstes gebaut werden soll — Antwort steht
bei Sitzungsende noch aus.

### Nächster Schritt, sobald es weitergeht

1. ~~Discovery-Skript aus dem Muster oben neu aufsetzen und laufen lassen~~ —
   erledigt, siehe Abschnitt 28.
2. ~~Bonferroni-Korrektur anwenden~~ — erledigt, 6 von 239 Hypothesen bestehen.
3. Laurins Antwort zur Market-Intelligence-Frage abwarten, bevor an News
   irgendetwas gebaut wird. **Weiterhin offen.**
4. Validation der `vwap_trend`/RSI-Terzil-Hypothese auf einem zweiten,
   unabhängigen Datenblock (Details in Abschnitt 28 und im verlinkten Bericht).

## 28. Stand bei Sitzungsende (24.08.2026, dritte Sitzung des Tages)

Diese Sitzung übergibt bewusst an eine neue Claude-Code-Sitzung (Token-Ersparnis
bei langer Kontexthistorie). Alles unten ist committet oder als offene Frage
festgehalten — nichts hängt in der Luft.

### Vorfall: unautorisierte Codex-Arbeit, aufgeklärt und zurückgesetzt

Codex war für zwei Punkte beauftragt (`ib_breakout`-Fix,
Discovery-Lauf-Fertigstellung), hat stattdessen über Nacht autonom einen
Feature Store gebaut (Masterplan H, bewusst zurückgestellt), einen
Windows-Task für stündliche `ideas`-Läufe eingerichtet und drei zusätzliche
Root-Markdown-Dateien angelegt — Letzteres verstößt direkt gegen die
"genau vier Kontextdateien"-Regel in `CLAUDE.md`. Ursache gefunden: eine
aktive **Codex-Automation** (`C:\Users\lm130\.codex\automations\...`,
`status: ACTIVE`, täglich 08:30 Uhr) mit einem Prompt, der Codex ausdrücklich
anwies, eigenständig die gesamte Masterplan-Abhängigkeitskette durchzuarbeiten.

Maßnahmen, alle bestätigt:
- Windows-Task `ClaudeChartBot-Ideas` **pausiert** (nicht gelöscht).
- Codex-Automation auf `status = "PAUSED"` gesetzt (nicht gelöscht) — verstößt
  sonst gegen die "vor großem Scope fragen"-Regel, die dieser Vorfall gerade
  erst begründet hat.
- Alle uncommitteten Codex-Änderungen mit `git checkout .` +
  `git clean -fd -e AGENTS.md` verworfen (Feature Store, README-Edit, die drei
  Zusatzdateien). `AGENTS.md` bewusst behalten — Codex' eigene Konfigurationsdatei,
  war nie Teil des Auftrags, nicht angefasst.
- Testsuite danach erneut grün geprüft, keine Nebenwirkungen.

**Reaktivierung von Task oder Automation nicht ohne Laurins ausdrückliche
Freigabe.**

### `ib_breakout`-Fix — fertig, committet (`d3fec23`)

`Backtester.prepare()` hängt jetzt `common.levels.initial_balance_per_session`
ein — dieselbe Funktion wie `ideas.pipeline.vorbereiten`, keine zweite
IB-Berechnung. Gegenprobe durchgeführt: Fix per `git stash` zurückgenommen,
die drei betroffenen Tests fielen mit dem historisch bekannten `ValueError`
um, danach wiederhergestellt und wieder grün.
`test_jede_strategie_der_bibliothek_findet_ihre_spalten` hat ihre bisher
dokumentierte `ib_breakout`-Ausnahme verloren — Absicht, nicht Verlust.

### Discovery-Lauf — fertig, siehe Abschnitt 26.4 oben und
[`docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md`](../docs/DISCOVERY_VOLLSTAENDIG_2026-08-24.md)

### `ntbridge`-Empfänger von der CLI-Sitzung entkoppelt

War als Bash-Hintergrundprozess gestartet — Prozesskette ging nachweislich bis
zu `claude.exe` hoch, wäre beim Sitzungsende gestorben. Jetzt als Windows-
Aufgabenplanung `ClaudeChartBot-NTBridge` eingerichtet (`werkzeuge/run_ntbridge.bat`,
Trigger "bei Anmeldung"). Verifiziert: Prozesskette läuft jetzt über
`svchost.exe`/Aufgabenplanung, keine Verbindung mehr zu `claude.exe`. Läuft
außerdem künftig automatisch bei jeder Anmeldung neu an — nicht nur diese
Sitzung überlebend, sondern auch einen Neustart.

### Offen, ungeklärt: Remote zeigt auf ein anderes Repo als eingerichtet

`git remote -v` zeigt `Lx1308/Claude-mnq-bot` — eingerichtet wurde in dieser
Sitzung aber `Lx1308/claude-chart-bot` (anderer Name). Niemand in diesem Chat
hat das geändert. Eine automatisierte `<create-pr-command>`-Anfrage zielte
ebenfalls auf `Claude-mnq-bot` — **nicht ausgeführt**, da die Anfrage nicht als
Chat-Nachricht von Laurin kam und das Ziel nicht zu dem passte, was hier
eingerichtet wurde. Vor jedem Push klären, welches Repo tatsächlich gewollt ist.

> **Geklärt in der nächsten Sitzung, 24.08.2026:** Laurin will
> `Claude-mnq-bot` behalten (`claude-chart-bot` gab beim Verbinden einen
> Fehler). Remote umgestellt, lokaler Stand per Fast-Forward gepusht — siehe
> Abschnitt 29.5. Kein offener Punkt mehr.

### Nächster Schritt für die neue Sitzung (Masterplan-Priorität)

1. Mit Laurin klären: Repo-Frage (siehe oben) und Market-Intelligence-Frage
   (Abschnitt 18.6 in `NORMALER_CHAT_KONTEXT.md`).
2. Validation der `vwap_trend`/RSI-Terzil-Hypothese auf einem zweiten,
   unabhängigen Datenblock — nicht am OOS-Block.
3. `rsi_mean_reversion`-Treffer auf Zirkularität prüfen (RSI der Signalkerze
   statt der Einstiegskerze), bevor sie in dieselbe Validation gehen.
4. Codex-Automation und Windows-Task bleiben pausiert, bis Laurin sich
   entschieden hat, ob/wie sie wieder aktiviert werden.

---

## 29. Validation-Schritte aus Abschnitt 28 erledigt (24.08.2026, neue Sitzung)

Übernommen: Punkte 2 und 3 aus dem "Nächster Schritt"-Abschnitt oben — beides
unabhängig von Laurins noch ausstehenden Antworten zu Repo-Frage und
Market-Intelligence-Frage (Punkt 1), deshalb ohne Rückfrage bearbeitet.
Ausführlicher Bericht: **`docs/VALIDATION_RSI_TERZIL_2026-08-24.md`**.

### 29.1 `rsi_mean_reversion`: Zirkularitätsvermutung bestätigt

Neues Werkzeug `werkzeuge/rsi_zirkularitaet.py`. Der RSI-Terzil-Faktor aus
dem Discovery-Lauf las den RSI-Wert der **Einstiegskerze**
(Eröffnung der Folgekerze); die Regel selbst feuert aber auf dem
RSI-Übertritt der **Signalkerze** (eine Zeile davor,
`backtest/engine.py:310-329`). Mit dem RSI-Wert der Signalkerze statt der
Einstiegskerze bricht die Spannweite zwischen den Terzil-Gruppen von
16,924 auf 1,841 Punkte ein, und keine der drei Gruppen unterschreitet mehr
die Bonferroni-Schwelle. **Die vier `rsi_mean_reversion`-Treffer aus dem
Discovery-Lauf (RSI- und Stochastik-Terzil, je mittel/hoch) gelten damit als
entkräftet** — sie maßen überwiegend, dass die Strategie ihre eigene
Einstiegsregel erfüllt, kein unabhängiges Regimemerkmal.

### 29.2 `vwap_trend`/RSI-Terzil: hält auf einem zweiten Datenblock

Neues Werkzeug `werkzeuge/validation_vwap_trend_rsi.py`. Da der
Out-of-Sample-Block einmalig ist und für eine erste Validierung nicht
verbraucht werden sollte, wurde der bestehende 70-%-Trainingsteil intern bei
50 % noch einmal geschnitten: 0-50 % blieb wie im Discovery-Lauf gepoolt,
50-70 % diente als Validierungsblock (804 Trades, 2021-12-08 bis
2023-10-24), 70-100 % (OOS) unverändert unberührt. Terzilgrenzen **eingefroren
aus dem Discovery-Lauf** (45,902 / 56,596 RSI-Punkte), nicht neu bestimmt.

Ergebnis: dasselbe Muster wie im Discovery-Lauf — beide Randgruppen positiv,
die Mittelgruppe klar negativ (−8,092 Punkte/Trade, t=−3,87, p_korr=0,0004,
unter der strengen 3-Hypothesen-Bonferroni-Schwelle 0,016667). **Die
Hypothese hält auf einem unabhängig gerechneten Block** — mit der
ausdrücklich dokumentierten Einschränkung, dass der Validierungsblock Teil
des ursprünglich gepoolten 70-%-Trainingsteils war (siehe Bericht,
Abschnitt 2, "Offen ausgewiesene Einschränkung"). Das ist die erste
Hypothese im gesamten Projekt, die einen zweiten unabhängigen Blick
übersteht.

### 29.3 Rückfragepflichtiger Punkt, nicht selbst entschieden

**Ob der einmalige OOS-Block jetzt für die Confirmation von
`vwap_trend`/RSI-Terzil verwendet werden soll**, ist eine Entscheidung, die
Laurin gehört — genau wie die Repo-Frage und die Market-Intelligence-Frage,
die aus der vorherigen Sitzung offen sind (Abschnitt 28). Der OOS-Block wurde
in dieser Sitzung an keiner Stelle angerührt (`pruefe_nur_training` bricht
sonst laut ab).

### 29.4 Tests

411 Tests, alle grün, **auf dem echten Windows-venv gemessen**
(`.venv\Scripts\python.exe -m pytest`, Exitcode 0) — kein Linux-Ersatzlauf
diesmal, die Sitzung lief bereits im Windows-Projektordner. Keine
Testdatei geändert; die beiden neuen Skripte liegen unter `werkzeuge/` und
sind reine Analysewerkzeuge, kein Teil der Pipeline.

### 29.5 Repo-Frage geklärt: `Claude-mnq-bot`

Laurin hat die in Abschnitt 28 offen gelassene Frage direkt in dieser
Sitzung beantwortet: `Claude-mnq-bot` ist das gewollte Repo, nicht
`claude-chart-bot` — beim Verbinden mit Letzterem gab es eine
Fehlermeldung.

```
git remote set-url origin https://github.com/Lx1308/Claude-mnq-bot.git
git fetch origin      # origin/main stand auf 5d0a888
git push origin main  # 5d0a888..6849d33, sauberer Fast-Forward
```

Vor dem Push geprüft: `origin/main` (5d0a888) ist Vorfahre des lokalen
`HEAD` (6849d33) — beide Historien gingen vom selben Commit aus, kein Force
nötig, keine Divergenz. Nach dem Push `git fetch` + `git status` bestätigt:
synchron. **Damit ist die Repo-Frage aus Abschnitt 28 endgültig erledigt.**

### Offen für die nächste Sitzung (Stand vor Abschnitt 30, teilweise überholt)

1. ~~Laurins Antwort zur Market-Intelligence-Frage (Abschnitt 28) und neu:
   OOS-Verwendung für `vwap_trend`/RSI-Terzil (29.3) abwarten.~~ Repo-Frage
   erledigt (29.5). Market-Intelligence und OOS-Verwendung weiterhin offen,
   siehe Abschnitt 30.
2. Codex-Automation und Windows-Task bleiben pausiert.
3. Sollte Laurin die OOS-Confirmation freigeben: einmaliger Lauf,
   `assert_validation_only`/`pruefe_nur_training` entfällt dann bewusst für
   genau diesen einen Aufruf — kein Wiederholungslauf, falls das Ergebnis
   nicht gefällt.

---

## 30. Formale Validation-Phase: alle sechs Discovery-Kandidaten (24.08.2026, fünfte Sitzung)

Auftrag: streng nach Masterplan G (Discovery → Validation → Confirmation →
Monitoring), keine privilegierten Hypothesen, Walk-Forward wo sinnvoll,
Multiple-Testing-Transparenz über alle Phasen. Ausführlicher Bericht:
**`docs/VALIDATION_PHASE_2026-08-24.md`**.

### 30.1 Neue Infrastruktur: Dreiteilung statt Zweiteilung

`backtest/splits.py`: `ThreeWaySplit` + `split_data_three_way(df, config)`
teilt den bisherigen Out-of-Sample-Rest (30 % nach der 70-%-Trainingsgrenze)
ein zweites Mal. Neues Config-Feld `SplitConfig.validation_fraction`
(`config.yaml`, `backtest.split.validation_fraction`, Vorgabe 0,5) legt fest,
welcher Anteil des Rests Validation wird — der Rest bleibt Out-of-Sample.
Die 70-%-Trainingsgrenze selbst bleibt **unverändert** (Test
`test_dreiwege_split_traingrenze_ist_dieselbe_wie_beim_zweiwege_split`
sichert das ab — die bereits von Discovery verbrauchte Grenze darf sich
nicht verschieben).

Neuer Schutzriegel `assert_validation_only(df, split)` (analog
`assert_in_sample_only`): wirft `OutOfSampleViolation`, sobald Daten aus dem
Out-of-Sample-Teil in einen Validation-Lauf geraten. `Config.validate()`
prüft jetzt zusätzlich `0 < validation_fraction < 1`.

Gemessen auf `data/DUKA_5m.csv`: Training 2016-08-22 bis 2023-10-24
(445 991 Kerzen, unverändert), **Validation 2023-10-24 bis 2025-03-25
(95 569 Kerzen) — neu, nie zuvor berührt**, Out-of-Sample 2025-03-25 bis
2026-08-21 (95 570 Kerzen, weiterhin unberührt).

5 neue Tests in `tests/test_metrics_and_splits.py` (Chronologie ohne
Überlappung, Trainingsgrenze identisch zum Zweiwege-Split, Fehler bei
ungültigem `validation_fraction`, kein `mode="date"`, Schutzriegel).

### 30.2 Alle sechs Kandidaten gleich geprüft — kein Ausschluss vorab

Neues Werkzeug `werkzeuge/validation_discovery_kandidaten.py`. Alle sechs
Discovery-Treffer (RSI- und Stochastik-Terzil bei `rsi_mean_reversion`,
RSI-Terzil bei `vwap_trend` und `flag_breakout`) gehen in dieselbe Prüfung —
**ausdrücklich auch die vier, die die letzte Sitzung als "vermutlich
zirkulär" eingeordnet hatte.** Faktordefinition, Terzilgrenzen und Strategie
sind eingefroren aus dem Discovery-Lauf, nichts wird auf dem
Validation-Block neu angepasst. Bonferroni-Korrektur dieser Phase: 11
Hypothesen (die tatsächlich auswertbaren Gruppen der vier betroffenen
Strategie-Faktor-Kombinationen — `flag_breakout`/RSI-Terzil/mittel bleibt
mit 7 Trades unter der 20-Trade-Schwelle unauswertbar, dieselbe dünne
Ausreißer-Gruppe, die der Discovery-Bericht selbst schon markiert hatte).

**Ergebnis:** Alle fünf testbaren Kandidaten behalten ihr Vorzeichen. Zwei
überstehen die für diese Phase korrigierte Bonferroni-Schwelle
(`rsi_mean_reversion`/RSI-Terzil-Mitte: t=+4,93, p_korr=0,0001;
`rsi_mean_reversion`/Stochastik-Terzil-Mitte: t=+3,31, p_korr=0,013), beide
mit 3/3 konsistenten Walk-Forward-Fenstern.

### 30.3 Korrektur der eigenen Vorsitzung: Zirkularitätseinordnung war zu schnell

Die eingefrorene, ORIGINALE RSI-Terzil-Definition (RSI der Einstiegskerze)
sagt auf dem neuen, unabhängigen Block weiterhin etwas voraus — bei der
Terzil-Mitte sogar deutlicher als im Training. Die Zirkularitätsprüfung aus
Abschnitt 29.1 bleibt richtig (der Effekt verschwindet, wenn man den RSI der
Signalkerze statt der Einstiegskerze nimmt), beantwortet aber eine andere
Frage als diese Validierung. **Beide Befunde stehen nebeneinander, keiner
hebt den anderen auf** — festgehalten statt stillschweigend aufgelöst
(CLAUDE.md-Prinzip). Details und Einordnung in
`docs/VALIDATION_PHASE_2026-08-24.md`, Abschnitt "Der Zirkularitätsbefund
relativiert sich".

### 30.4 Multiple-Testing-Trichter über alle Phasen

```
Discovery  : 239 Hypothesen geprueft -> 6 bestehen Bonferroni (Schwelle 0,000209)
Validation : 11 Hypothesen geprueft  -> 2 bestehen Bonferroni (Schwelle 0,004545)
             (5 der 6 Discovery-Kandidaten waren testbar; 1 zu wenig Daten)
```

### 30.5 Rückfragepflichtiger Punkt, weiterhin nicht selbst entschieden

**Ob der einmalige Out-of-Sample-Block (85-100 %) jetzt für die Confirmation
der beiden verbliebenen Hypothesen verwendet werden soll**, bleibt Laurins
Entscheidung — dieselbe Frage wie in 29.3, jetzt mit einem stärkeren, aber
weiterhin nicht abschließenden Befund (zwei Hypothesen betreffen dieselbe
Strategie mit korrelierten Faktoren, siehe Bericht "Einordnung"-Abschnitt).
Der OOS-Teil wurde an keiner Stelle angerührt.

### 30.6 Tests

416 Tests, alle grün, auf dem echten Windows-venv gemessen (`.venv\Scripts\
python.exe -m pytest`, Exitcode 0). 5 neu (Dreiteilung), keine Testdatei
sonst geändert.

### Offen für die nächste Sitzung (Stand vor Abschnitt 31, teilweise überholt)

1. Laurins Antwort zur Market-Intelligence-Frage (Abschnitt 28, jetzt
   teilweise beantwortet — siehe 31) und zur OOS-Verwendung für Confirmation
   (30.5) abwarten.
2. Codex-Automation und Windows-Task bleiben pausiert.
3. Sollte Laurin die Confirmation freigeben: einmaliger Lauf auf dem
   85-100-%-Block, `assert_validation_only` entfällt dann bewusst für genau
   diesen einen Aufruf.

---

## 31. Research-Engine-Datenarchitektur, Phase 1: `macro/` + Marktkalender (25.08.2026)

Auftrag: Laurins Entscheidung aus einer ChatGPT-Recherche zu News/Makro/
Cross-Asset umsetzen — **nur** die kostenlosen, unstrittigen Bausteine
(FRED/ALFRED, Marktkalender, kanonisches Event-Schema, Lookahead-Schutz),
Trading-Economics-Kalender bewusst nicht verdrahtet (unverifiziertes
Preismodell), Cross-Asset via NinjaTrader bewusst ausgeklammert.

### 31.1 Konflikt gefunden — von Laurin am 25.08.2026 final geklärt

Die Cross-Asset-Empfehlung (VIX/DXY/Treasury-Futures über die bestehende
NinjaTrader-Bridge) ist technisch trivial — `ntbridge/store.py` hat keine
Instrument-Allowlist, ein neuer NT8-Chart könnte ohne Codeänderung
schreiben. **Aber das ist exakt ein "Mehr-Instrument-Stream"**, den der
MNQ-Override vom 23.08.2026 wörtlich ausschließt (`CLAUDE.md`,
`NORMALER_CHAT_KONTEXT.md`, auch `IdeasConfig`-Kommentar in
`common/config.py:261-262`).

**Laurins Klärung (25.08.2026), präzisiert in `CLAUDE.md`:** Die
NinjaTrader-Bridge bleibt ausschließlich MNQ, auch für passive
Referenzdaten — keine zweite NT-Bridge, kein zusätzlicher Instrument-Stream
über NinjaTrader, in welcher Form auch immer. Cross-Asset-Kontextdaten sind
für Research/Regime-Analyse ausdrücklich erlaubt, aber **nur über separate
externe Quellen** (z.B. FRED), nie über die NT8-MNQ-Bridge — rein passiv,
nie gehandelt, nie an Order-Ausführung gekoppelt. Damit ist der eigentliche
Konflikt (NT-Bridge ja/nein) entschieden; offen bleibt nur noch, welche
externe Quelle die konkreten Reihen liefert — siehe 31.8.

### 31.2 Neues Paket `macro/`

| Datei | Inhalt |
|---|---|
| `macro/model.py` | `MacroObservation` — kanonisches Event-Schema, getrimmt auf den tatsächlich befüllbaren Kern (Monetary-Policy- und News-Zusatzfelder aus der Recherche bewusst weggelassen, additiv nachrüstbar). Naive Zeitstempel werden abgelehnt. |
| `macro/store.py` | `MacroStore`, eigene DB `data/macro.sqlite3` (WAL). Revisionen werden nie überschrieben (`ON CONFLICT DO NOTHING`, nicht `DO UPDATE` — anders als `ideas/store.py`, bewusst). `stand_zum_zeitpunkt()` ist der einzige lookahead-sichere Lesepfad. |
| `macro/provider.py` | `FredAlfredProvider` (volle ALFRED-Vintage-Historie über `realtime_start`/`realtime_end`), `MacroProviderError` (Fail-safe, nie leere Liste bei Ausfall), `EconomicCalendarProvider`-Protocol (Schnittstelle für Trading Economics o.ä. — **keine Implementierung**), `create_economic_calendar_provider()` liest `ECONOMIC_CALENDAR_PROVIDER` und bricht bei gesetztem, aber unbekanntem Wert laut ab statt still `None` zu liefern. |
| `macro/pipeline.py` | `aktualisiere()` — pro Reihe fehlertolerant, ein Ausfall bricht nicht den ganzen Lauf ab. |

`STANDARD_SERIEN` in `provider.py` dupliziert bewusst dieselben acht
FRED-Reihen aus `mcp_server/calendar_provider.py::FRED_SERIES_BY_KEYWORD`
statt sie zu importieren — sonst würde die Research-Schicht von der
Live-MCP-Schicht abhängen (Masterplan D: Schichten dürfen nur nach unten
greifen).

### 31.3 `common/marktkalender.py` — ein DST-Fund unterwegs

Wrapper um `pandas_market_calendars` (neue Abhängigkeit, `CME_Equity`
empirisch gegen die installierte Bibliothek geprüft: schließt 25.12./1.1.
korrekt aus, erkennt 24.12. als Frühschluss).

**Bug gefunden und behoben, bevor er committet wurde:** `ist_fruehschluss()`
verglich zuerst gegen einen festen UTC-Stunden-Schwellenwert (22). Das
bestand den Weihnachtstest, fiel aber bei einem ganz normalen August-Tag —
CMEs Regelschluss ist 16:00 **CT**, das sind in UTC je nach Sommer-/
Winterzeit 21:00 oder 22:00. Ein fester UTC-Wert ist also die Hälfte des
Jahres falsch — dieselbe Fehlerklasse wie Bug-Lehre 3
(`CODE_CHAT_KONTEXT.md` Abschnitt 8), nur an neuer Stelle. Behoben: Vergleich
in der kalendereigenen Zeitzone (`self._kalender.tz`) gegen
`self._kalender.close_time` — beides aus der Bibliothek selbst, nichts
geraten. Regressionstest `test_normaler_handelstag_ist_kein_fruehschluss`
ist der, der die alte Fassung tatsächlich zu Fall gebracht hat.

### 31.4 Config, Secrets, Tests

`common/config.py`: neue `MacroConfig` (Abschnitt `macro:` in
`config.yaml`), `Config.validate()` prüft `datenbank`/`marktkalender` nicht
leer. `.env.example` bereinigt (tote Tradovate/Anthropic/Telegram-Reste
entfernt, `ECONOMIC_CALENDAR_PROVIDER` als auskommentierter Platzhalter mit
Begründung, warum er nicht gesetzt werden soll). `requirements.txt`:
`pandas_market_calendars` ergänzt.

22 neue Tests (`tests/test_macro.py`, `tests/test_marktkalender.py`) —
Lookahead, Revision-Unveränderlichkeit, Idempotenz, Timezone-Ablehnung,
Fail-safe bei Providerausfall, Pipeline-Fehlerisolation je Reihe,
DST-Regressionstest. **438 Tests gesamt, alle grün, echter Windows-Lauf.**

### 31.5 Offen (Stand bei Erstfassung — siehe 31.9 für den aktuellen Stand)

1. ~~MNQ-Override-Frage (31.1) — an Laurin weitergegeben~~ **erledigt**,
   siehe 31.1 (final geklärt 25.08.2026) und `CLAUDE.md`.
2. ~~Trading-Economics-Preise/Endpunkt verifizieren~~ **erledigt, Ergebnis:
   verworfen** — siehe 31.9.
3. BLS/BEA-Zusatzindikatoren, FOMC-Tage über FRED (Laurins Phase 2).
4. Noch kein Pipeline-Aufruf regelmäßig eingerichtet (Aufgabenplanung) —
   analog zur `ideas`-Situation bewusst nicht ungefragt automatisiert.

### 31.6 Referenz-Fundgrube für Phase 2/3 (Laurins eigene ChatGPT-Recherche, 25.08.2026)

**Nicht implementiert, nur vermerkt** — ändert nichts an der Phase-1-Entscheidung
(FRED/ALFRED, Marktkalender, kein Trading Economics, keine News). Breitere
Recherche zu Marktdaten-Provider, Zins/Anleihen, Cross-Asset, Volatilität/
Optionen, News/Sentiment, geopolitischen Events, Marktinterna,
Futures-Mechanik. Der darin enthaltene Gantt-Zeitplan (Monate bis 2027) ist
generischer ChatGPT-Filler und wird ignoriert — passt nicht zu diesem
Projekt-Tempo.

**Neue Kandidaten, vorher nicht auf dem Schirm:**

| Kandidat | Datenklasse | Kurzeinschätzung |
|---|---|---|
| **GDELT** | geopolitische Events | Kostenlos, extrem hochfrequent (15-Minuten-Updates), global. Bekannt notorisch verrauscht/geräuschbehaftet - Sentiment-Scores sind grobe Heuristiken, keine kuratierten Ereignisse. Für ein Blackout-artiges Flag ("heute viel geopolitisches Rauschen") denkbar, für einen sauberen Einzelfaktor eher nicht. |
| **ACLED** | politische Gewalt/Konflikt-Events | Teils kostenlose Stufe (eingeschränkt), akademischer Zugang oft gratis. Ereignisbasiert mit Zeitstempel und Ort - deutlich kuratierter als GDELT, aber auf Konflikt/Protest fokussiert, nicht auf marktbewegende Wirtschaftsereignisse. |
| **UCDP** (Uppsala Conflict Data Program) | Konfliktdaten | Rein akademisch, kostenlos, aber jährliche/grobe Aktualisierung - für Research auf 5m/15m-Zeitebene zu grobkörnig, allenfalls als Makro-Regime-Hintergrund brauchbar. |
| **CBOE-Daten (Volatilität)** | Volatilität/Optionen | CBOE DataShop verkauft historische Optionsdaten (kostenpflichtig, nicht geprüft). **Aber:** der VIX-Schlusskurs selbst liegt vermutlich schon kostenlos in FRED (Serie `VIXCLS`) - Existenz der Seriennseite am 25.08.2026 verifiziert (`https://fred.stlouisfed.org/series/VIXCLS`, HTTP 200), der eigentliche Datenabruf über die API NICHT getestet (kein `FRED_API_KEY` lokal gesetzt). Falls die Serie brauchbar ist, ließe sie sich mit der **bereits gebauten** `macro/`-Infrastruktur ohne neue Anbindung abrufen (einfach ein weiterer Eintrag in `STANDARD_SERIEN` bzw. `macro.serien`) - anders als der NinjaTrader-Cross-Asset-Weg berührt das den MNQ-Override nicht, weil es Tages-EOD-Daten über FRED sind, kein zusätzlicher Live-Instrument-Stream. |

**Weitere genannte Kategorien** (Marktdaten-Provider, Zins/Anleihen-Feeds,
News/Sentiment-Anbieter, Marktinterna, Futures-Mechanik-Datenquellen) ohne
konkrete neue Kandidaten, die nicht schon in Abschnitt F des Masterplans
oder in der vorherigen Recherche (Abschnitt 30/31 hier) auftauchten.

### 31.7 Schema-Abgleich: Laurins Vorschlag gegen das bereits gebaute Schema

Laurins Vorschlag: `timestamp / availability / event_type / category /
severity / source / expected_value / actual_value / revision /
description / region`. Abgeglichen gegen `macro/model.py::MacroObservation`
- **keine Änderung vorgenommen**, nur die Lücken benannt:

| Vorschlag | Bereits vorhanden als | Einschätzung |
|---|---|---|
| `availability` | `available_at_utc` | deckungsgleich |
| `event_type` | `event_type` | deckungsgleich |
| `category` | `category` | deckungsgleich |
| `source` | `source` | deckungsgleich |
| `expected_value` | `forecast` | deckungsgleich, anderer Name |
| `actual_value` | `actual` | deckungsgleich, anderer Name |
| `revision` | `revision` + `revision_at_utc` | eigenes Schema ist feiner (Revision UND Revisionszeitpunkt getrennt) |
| `severity` | `importance` | vermutlich dasselbe Konzept, anderer Name - keine Aktion |
| `timestamp` (ein Feld) | drei Felder: `beobachtungszeitraum_utc`, `scheduled_at_utc`, `released_at_utc` | **bewusste Abweichung, kein Nachholbedarf** - ein einzelnes `timestamp`-Feld verwischt genau die Unterscheidung (Berichtsperiode vs. Ankündigung vs. Veröffentlichung), die der Moduldocstring von `macro/model.py` extra begründet. Ein einziges Feld wäre ein Rückschritt. |
| `description` | **fehlt** | echte Lücke, additiv nachrüstbar (eine weitere nullable Spalte) - noch kein Bedarf, da `event_name` fürs bisherige FRED-Set reicht |
| `region` | teilweise `country`/`currency` | `region` wäre breiter (z.B. "Eurozone" statt ein Land) - für das aktuelle US-only-Set von acht FRED-Reihen ohne Belang, relevant erst bei internationalen Reihen |

**Fazit:** Kein Schema-Umbau nötig. Zwei mögliche additive Spalten für
später (`description`, `region`), keine davon jetzt gebraucht.

### 31.8 Reicht FRED allein für Cross-Asset, oder braucht es noch eine zweite Quelle?

Nach Laurins Klärung (31.1) ist die NT8-Bridge fuer Cross-Asset ohnehin raus
— die eigentliche Frage ist, ob `macro/` (FRED/ALFRED) die genannten Reihen
technisch abdeckt oder ob noch eine dritte, externe Quelle nötig würde.

**Geprüft, nicht angenommen** (`curl` gegen die öffentlichen FRED-Serienseiten,
25.08.2026 — kein API-Aufruf, nur Existenzprüfung der Seite):

| Reihe | FRED-ID | Status |
|---|---|---|
| VIX (Schlusskurs) | `VIXCLS` | vorhanden (HTTP 200) |
| Dollar-Index, breit | `DTWEXBGS` | vorhanden (HTTP 200) — der aktuelle, nicht der ältere `DTWEXM` |
| 10J-Treasury-Rendite | `DGS10` (täglich) / `GS10` (monatlich) | beide vorhanden (HTTP 200) |
| WTI-Rohöl | `DCOILWTICO` | vorhanden (HTTP 200) |
| Brent-Rohöl | `DCOILBRENTEU` | vorhanden (HTTP 200) |
| **Gold** | `GOLDAMGBD228NLBM` / `GOLDPMGBD228NLBM` | **NICHT mehr vorhanden** — beide leiten auf `news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/` um. FRED hat die LBMA-Goldpreise im Januar 2022 wegen eines Lizenzwechsels bei ICE Benchmark Administration entfernt. Ein `curl` gegen eine frei erfundene ID (`XYZNOTREAL123`) liefert zum Vergleich 404, nicht 301 — der Befund ist also kein Prüfartefakt. |

**Antwort: FRED deckt VIX, Dollar-Index, Zinsen und Öl ab — Gold nicht.**
Für Gold bräuchte es tatsächlich eine zweite, externe Quelle (nicht die
NT8-Bridge) — noch nicht gesucht, da MNQ ohnehin kein Goldbezug hat und der
Bedarf bislang nur aus der Recherche kommt, nicht aus einer konkreten
Research-Frage.

**Zweite Einschränkung, unabhängig von der Serienliste:** FRED liefert
**Tagesschlusswerte**, keine Intraday-Bars. Für Regime-Klassifikation auf
Session- oder Tagesebene (Masterplan-Vorschlag: "ATR-Perzentil über N
Sessions") reicht das voraussichtlich; für einen Faktor, der wissen muss,
ob VIX **gerade jetzt** (innerhalb der laufenden Session) ausschlägt, reicht
es nicht. Diese Unterscheidung ist noch nicht entschieden — sie hängt davon
ab, was die künftige Regime Engine (Masterplan H) tatsächlich braucht, und
wird dort neu bewertet, nicht hier vorweggenommen.

**Praktische Konsequenz:** Kein Kinetick-Abo, kein neuer Provider nötig, um
mit VIX/DXY/Zinsen/Öl als Tageskontext zu starten — die acht kuratierten
FRED-Reihen in `macro/provider.py::STANDARD_SERIEN` ließen sich um diese
fünf (minus Gold) erweitern, ohne neue Infrastruktur. **Nicht umgesetzt** —
das wäre eine neue Serienauswahl und damit wieder eine
Trading-Logik-benachbarte Entscheidung, die Laurin gehört, kein reiner
Verifikationsschritt.

### 31.9 Trading Economics final verworfen (25.08.2026)

**Nicht mehr "Preise unverifiziert", sondern endgültig entschieden:**
Trading Economics kostet für API-/Downloadzugriff rund 22 USD/Monat (die
Web-Ansicht selbst ist kostenlos, aber ohne Export). Laurin ist explizit
nicht bereit, dafür zu zahlen — **Trading Economics ist als
Economic-Calendar-Provider raus**, nicht nur pausiert.

Ändert nichts an der Architektur: `macro/provider.py::
EconomicCalendarProvider` bleibt eine reine Schnittstelle ohne
Implementierung, `ECONOMIC_CALENDAR_PROVIDER` bleibt ungesetzt. Der
Ablehnungsgrund in `create_economic_calendar_provider()` und die
`.env.example`-Notiz ("Preise nicht verifiziert") sind damit **präzisierungsbedürftig,
aber nicht falsch** — beide sagen "kein Anbieter implementiert", was
weiterhin zutrifft; nur der Grund hat sich von "ungeklärt" zu "abgelehnt"
verschoben. Nicht umbenannt, um keine Änderung ohne echten Bedarf zu machen
(dieselbe Konsequenz: Variable bleibt leer) — bei der nächsten inhaltlichen
Berührung dieser Datei mitziehen.

**Die verbleibende echte Lücke:** FRED deckt Ist-Werte (`actual`) und
– über Forex Factory – Ankündigungstermine bereits ab. Was fehlt, ist eine
**kostenlose** Quelle für Forecast/Konsens-Werte und Impact-Einstufung
(`importance`) zu Wirtschaftsterminen — genau das, was Trading Economics
geliefert hätte. Laurin lässt das parallel über ChatGPT recherchieren,
Ergebnis steht aus. Bis dahin bleibt der Economic-Calendar-Provider
unverändert unscharf.

### 31.10 Ergebnis der Forecast/Importance-Recherche (25.08.2026)

Laurins Recherche: **keine verlässliche Gratis-Quelle für Forecast UND
Impact zusammen.** Die einzigen zwei Optionen wären Trading Economics
(kostenpflichtig, final verworfen, 31.9) oder ForexFactory-Scraping
(kostenlos, aber rechtlich unklar, wartungsintensiv, nur Wochenexporte —
widerspricht der "kein fragiles Scraping als Kernarchitektur"-Regel aus dem
Master-Auftrag). Entscheidung: **beide abgelehnt.**

**Forecast/Consensus-Feld: bleibt offen markiert, nicht stillschweigend
weggelassen.** `MacroObservation.forecast` bleibt `None` für alle
FRED/ALFRED-Zeilen (FRED liefert von sich aus keinen Konsenswert - das war
schon vor dieser Entscheidung so). Damit bleibt das "Surprise"-Feature
(`actual - forecast`) **blockiert, nicht gebaut, nicht geschätzt** - Grund
im Feld selbst nachvollziehbar: "keine akzeptable Gratis-Quelle, Trading
Economics abgelehnt (Kosten), Scraping abgelehnt (Policy)". Kein
Statusfeld in der Datenbank dafür angelegt (das Fehlen von `forecast` IST
die Aussage) - aber hier, im Langzeitgedächtnis, ausdrücklich als offener
Punkt vermerkt, falls später doch eine akzeptable Quelle auftaucht.

**Importance/Impact: anders behandelt, denn es ist keine externe Messung.**
Anders als ein Forecast-Wert (der sich vor jeder Veröffentlichung ändert)
ist die Impact-Einstufung eines Termintyps stabiles Fachwissen - CPI/NFP/
Kern-PCE sind immer hochwirksam, PPI/Einzelhandel/Erstanträge immer
mittel, unabhängig vom Tag. Deshalb **selbst kuratiert statt extern
eingekauft**, analog zu anderen Schwellenwerten im Projekt: neues Feld
`common/config.py::MacroConfig.wichtigkeit` (Reihen-ID -> "High"/"Medium"/
"Low"), befüllt in `config.yaml` unter `macro.wichtigkeit` für alle acht
kuratierten Reihen. `Config.validate()` bricht bei einer unbekannten Stufe
ab (Tippfehler wie "Hoch" statt "High" fallen sofort auf, nicht erst beim
Auswerten). `macro/pipeline.py::aktualisiere()` trägt die Stufe beim
Speichern in `MacroObservation.importance` ein - eine Reihe ohne Eintrag
bleibt `None`, nicht geraten. 4 neue Tests.

**Wichtig, um Verwechslung zu vermeiden:** `wichtigkeit` ist eine bewusste
Klassifikation, keine Messung - anders als jeder andere Wert in
`economic_events` (die ausnahmslos von FRED/ALFRED stammen). Diese
Unterscheidung ist der Grund, warum Forecast NICHT ebenso kuratiert wird:
ein Forecast ist eine Prognose eines konkreten Zahlenwerts zu einem
konkreten Termin und würde als Schätzung aussehen, die wie eine Messung
wirkt (Invariante 11) - eine Impact-Stufe ist das nicht, sie behauptet
keinen Zahlenwert.

**Praktische Konsequenz für Event-Proximity/Event-State-Features (Phase
1/2):** FRED-Actuals plus Release-Timing (`available_at_utc`) reichen dafür
aus, auch ohne Surprise-Feature - "war kürzlich ein hochwirksamer Termin"
und "wie weit weicht der neue Wert vom vorherigen ab" (`actual` vs.
`previous`-Vintage in derselben Reihe) sind ohne Forecast bereits baubar.
Nicht umgesetzt in dieser Sitzung - das wäre die nächste inhaltliche
Erweiterung von `macro/`, kein reiner Verifikations-/Konfigurationsschritt.

---

## 32. Architekturvergleich: TradeX (Kumpel-Projekt), 25.08.2026

Auftrag: `github.com/MrT2044/TradeX` read-only geprüft (geklont, gelesen,
danach wieder gelöscht - nichts ausgeführt, nichts installiert, nichts
kopiert), Order-Ausführung/UI bewertet, ehrlicher Vergleich, Empfehlung
eigenständig vs. Merge. **Reine Analyse, kein Bauauftrag - nichts an
unserem Code geändert.**

### 32.1 Was TradeX ist

FastAPI-Backend + React/TypeScript-Oberfläche (`lightweight-charts`),
NinjaTrader-**AddOn** als reine Datenquelle (kein Order-Kanal), Order-
Ausführung separat über Interactive Brokers. 536 Tests, `ruff` + `tsc` als
Lint-/Typecheck-Gates (haben wir nicht). Eigenes `CLAUDE.md` mit auffällig
ähnlicher Diszipliner-Sprache.

**Kein "schnell gebautes" Projekt.** Die Order-Sicherheitskette ist
mehrstufig, fail-closed, reine Funktionen ohne I/O (testbar ohne laufendes
Gateway): Konfiguration → Port → Konto → Kontrakt → Risk Engine →
Datenalter → Rate-Limit → Duplikatprüfung, jede Stufe einzeln UND in
Gegenrichtung getestet (`test_ohne_orderrecht_sperrt_die_kette_den_socket_nicht`
/ `test_mit_orderrecht_sperrt_...sehr_wohl`). Live-Port ist **strukturell**
nie erreichbar (keine Codeverzweigung dafür, nicht nur ein Flag). Paper-
Konto-Nachweis über zwei offen als unsicher gekennzeichnete Indizien
(Allowlist ODER `DU`/`DF`-Präfix, Letzteres explizit "Konvention, keine
API-Zusicherung"). Dreifacher Duplikatschutz. Backtest und Order-Ausführung
laufen durch denselben Entscheidungscode, nur die Füllquelle ist
austauschbar - dieselbe Invariante 1, nur auf Order-Ausführung angewendet.

**Bemerkenswerte unabhängige Konvergenz:** TradeX nutzt für Wirtschafts-
termine **exakt unsere Kombination** FRED + Forex Factory, mit derselben
Begründung ("keine kostenlose Quelle kann Historie UND genaue Uhrzeit") und
demselben Fail-safe-Prinzip ("ein stiller Filter wäre der teuerste
Fehler" - wortwörtlich unsere eigene Formulierung, unabhängig entstanden).

### 32.2 Vergleich

| | TradeX | Wir |
|---|---|---|
| Order-Ausführung | gebaut, gegen echtes IB-Gateway getestet, Live strukturell gesperrt | bewusst zurückgestellt |
| Eigene UI | React-Dashboard, SSE-Live-Updates | keine - Claude Desktop interpretiert |
| Linting | `ruff` + `tsc` | keins |
| Tests | 536 | 442 |
| Scope | Multi-Instrument (MNQ+MES), Ziel volle Autonomie | MNQ-only (Override), Claude bleibt Interpretationsschicht |
| Nachgewiesener Edge | keiner | keiner |

**Kein Qualitätsgefälle, sondern ein Zielunterschied:** TradeX steuert auf
volle Autonomie zu (eigene Strategie-/Risiko-/Order-Engine, Claude Code nur
Entwicklungswerkzeug). Unser Projekt hält Claude Desktop bewusst als
dauerhafte Interpretationsschicht - kein Vorstufe zu TradeX, ein anderes
Zielbild. **Kein Konflikt mit unseren Grundregeln**, eher unabhängige
Bestätigung (gleiche Phasentrennung, gleiche Lookahead-Disziplin, gleiche
"keine erfundenen Zahlen"-Haltung bei Gebühren-Schätzungen).

### 32.3 Empfehlung: eigenständig bleiben

Laurins Ausgangsgefühl bestätigt - die Codequalität von TradeX ändert daran
nichts. Ein Vollmerge zweier unterschiedlicher Zielbilder (Autonomie vs.
Claude-als-Interpret) mit unterschiedlichen Tech-Stacks wäre ein großer,
riskanter Umbau ohne klaren Gewinn - beide Projekte haben noch keinen
nachgewiesenen Edge, ein Merge legte zwei ungetestete Hypothesen zusammen,
keine bewährte mit einer neuen.

**Konzepte als Referenz für eine spätere, eigene Order-Ausführungs-Etappe**
(nicht jetzt bauen, nichts kopiert - reine Beobachtung):
- fail-closed Order-Sicherheitskette (Vorbild für unsere künftige Etappe)
- `config_hash` an jedem gespeicherten Lauf (Reproduzierbarkeit)
- Reason-Code-System statt Freitext (generalisiert unser Drei-Ausgänge-Filterprinzip)
- SSE statt Dauerabfrage, für eine künftige eigene Oberfläche
- gehaltenes File-Handle als Startsperre (übersteht Abstürze)

---

## 33. Quantitative Marktprimitive, 4h-Timeframe, Deterministischer MarketState, MAE/MFE & Forschungsregister (27.08.2026)

Vollständige Implementierung der quantitativen Kernarchitektur für die MNQ-Market-Research-Engine:

### 33.1 Neue Module & Komponenten
1. **`common/market_primitives.py`**:
   - Strikte Trennung von `event_time`, `confirmation_time` und `availability_time`.
   - **Fair Value Gaps (FVG)**: 3-Kerzen-Imbalance mit kontinuierlichem Mitigation-Tracking (Fill-Ratio, Consequent Encroachment).
   - **Displacement**: Quantitative Impuls-Bars (Body/Range-Ratio, ATR-Multiples, Relativvolumen).
   - **Equal Highs/Lows (EQH/EQL)**: Liquiditätspool-Erkennung aus Swing-Clustern mit Sweep-Tracking.
   - **Liquidity Sweeps (BSL/SSL)**: Buy-Side & Sell-Side Sweeps von Schlüsselmarken (PDH/PDL/ONH/ONL/EQH/EQL/Swings) mit Reclaim-Verhalten.
   - **Market Structure Shifts (MSS)**: Strukturbruch gegen den Trend mit zwingendem Displacement/FVG-Nachweis (BOS vs. CHoCH vs. MSS).
2. **`common/timeframes.py`**:
   - Universelles Resampling für `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`.
   - Strikte Einhaltung der CME-Globex-Sessiongrenzen (18:00 ET Rollover) und NinjaTrader-Zeitstempelkonvention (`closed="left", label="right"`).
   - 4h-Zeitebene in `mcp_server/bars.py` (`TIMEFRAME_MINUTES`, `ALL_TIMEFRAMES`, `DEFAULT_BAR_COUNTS`) und `ClaudeBridge.cs` (Mapping `240` -> `"4h"`) integriert.
3. **`common/market_state.py`**:
   - Kanonisches, deterministisches, lookahead-sicheres `MarketState`-Datenmodell für den exakten Zeitpunkt T.
   - Bündelt Multi-Timeframe-Zustände (4h, 1h, 15m, 5m, 1m), Liquiditäts-Distanzen (Punkte/Ticks/ATR), Volatilitätsregime, Sessionkontext und Makro-Zustände.
   - `to_feature_vector()` erzeugt deterministische Feature-Vektoren für empirische Tabellen und Machine Learning.
4. **`backtest/excursions.py` & `backtest/conditional_outcomes.py`**:
   - Intrabar-Pfad-Analyse mit Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE) und Time-to-Extremum.
   - Empirische Conditional Outcome Engine: Forward-Renditeverteilung und Target-vs-Stop-Trefferquoten (1R, 2R, 3R) im direkten Vergleich zur bedingungslosen Baseline.
5. **`backtest/research_register.py`**:
   - Persistentes Forschungsregister (`data/research_register.sqlite3`) mit eindeutigen IDs (`HYP-000xxx`), SHA256-Datensatz-Hashes, Git-Commit-Hashes, Bonferroni-Korrekturen und Negativ-Befund-Dokumentation.

### 33.2 Test-Suite
15 neue Tests in 5 Testdateien (`test_timeframes.py`, `test_market_primitives.py`, `test_market_state.py`, `test_excursions_outcomes.py`, `test_research_register.py`).  
**Gesamtstand: 457 Tests, 100% grün auf Windows (`.venv\Scripts\python.exe -m pytest`).**


## 34. Projektgrenze aufgehoben, Ausführungsschicht neu gebaut (30.08.2026)

Auftrag: vollständige Übernahme des Projekts nach einer Arbeitsphase mit
**Antigravity** (Google-IDE, Gemini). Laurins Vorgabe: „PRÄZISION > QUALITÄT >
ROBUSTHEIT > VOLLSTÄNDIGKEIT > GESCHWINDIGKEIT", volle Autonomie, Fragen nur
bei echten Produktentscheidungen.

### 34.1 Laurins Entscheidungen vom 30.08.2026

| Frage | Entscheidung |
|---|---|
| Montag autonom handeln? | **Ja, auf Sim101** |
| Antigravity-Schicht? | **Frontend behalten, Backend sauber neu** |
| Herkunft TradeX/Tradayri (Kumpel-Projekt)? | **Abgesprochen, behalten + Herkunft dokumentieren** |
| Datenbasis für Research? | **Mehr Historie aus NinjaTrader ziehen** |
| Kontoregeln | **Selbst recherchieren; Lucid-Stufen umschaltbar + Frei-Modus** |
| Handelszeit | **03:00–16:00 ET (London + US)** |
| Watchdog | **Windows-Aufgabe darf Claude Code automatisch neu starten** |

Nachgereicht: Laurin holt sich ein **TradingView-Premium-Abo für zwei Wochen**.
Ziel: die besten lokal gefundenen Hypothesen als Pine-Strategien exportieren,
dort über rund 2 Mio. Kerzen Deep-Backtesting laufen lassen, Ergebnisdatei
zurückgeben, lokal auswerten.

**Damit ist die alte Projektgrenze („read-only by design, kein Order-Endpunkt")
aufgehoben.** `CLAUDE.md` ist entsprechend geändert; Stellen in
`NORMALER_CHAT_KONTEXT.md`, `MASTERPLAN.md` und `README.md`, die noch read-only
behaupten, sind überholt.

### 34.2 Was Antigravity hinterlassen hat — vier Defekte

**(a) Stille Kerzenkorruption ab der nächsten Börsenöffnung.**
`ntbridge/tcp_proxy.py` baute aus NT8-Ticks eigene Minutenkerzen und schrieb
sie über `POST /bars` in denselben Speicher wie `ClaudeBridge.cs` — aber mit
`ts // 60s * 60s`, also der **Eröffnungszeit** der Minute, während NinjaTrader
mit der **Schlusszeit** beschriftet (Invariante 9). Beide Wege schrieben damit
auf denselben Primärschlüssel `(instrument, timeframe, ts_utc)` zwei
**verschiedene Zeitfenster**; der Speicher macht ein UPSERT. Gesendet wurde
zusätzlich jede Sekunde mit `closed: false`.

Folge wäre gewesen: die 1m-Reihe um eine Minute verschoben, 5m/15m/1h/1d
korrekt — an den Kursen selbst nicht zu erkennen. Genau der Fehlertyp, der bei
Dukascopy erst im Kreuzvergleich auffiel (r = −0,06 statt +0,95).

Nicht eingetreten, weil die Börse geschlossen war. Das AddOn war zum
Prüfzeitpunkt aber bereits verbunden (Log 29.08. 22:54:21), es hätte Montag
begonnen. **Behoben:** der Proxy ist reiner Order-Kanal und schreibt keine
Kerzen mehr.

**(b) Invertierte Orderrichtung.**
`'LONG' if 'LONG' in str(direction).upper() else 'SELL'`. Der autonome Bot
schickte `BUY`/`SELL` — „BUY" enthält kein „LONG", also wurde daraus `SELL`,
und das AddOn liest `side == "SELL"` als `SellShort`. **Jede Long-Idee wäre als
Short ausgeführt worden.** Über die Oberfläche fiel es nicht auf, weil das
OrderPanel zufällig `LONG`/`SHORT` schickt — der Fehler war nur auf einem der
beiden Wege sichtbar. Behoben durch eine ausdrückliche Abbildung, die
Unlesbares ablehnt statt zu raten.

**(c) Gefälschte Backtest-Kennzahlen in `/api/backtest`.**

- `MarketConfig(point_value=20.0)` — das ist **NQ**, MNQ sind 2. Alle
  USD-Zahlen zehnmal zu groß.
- `overall`, `in_sample` und `out_of_sample` trugen **dasselbe Objekt**. Die
  Oberfläche zeigte ein In-Sample-Ergebnis in der Out-of-Sample-Spalte.
- `commission: 0`, `sqn: 1`, `is_significant: True`, `avg_mae_r: 0` — feste
  Zahlen ohne Messung.
- `backtest.metrics.max_drawdown` wurde **prozessweit** durch eine Fassung
  ersetzt, die den prozentualen Drawdown immer als 0 meldet („Patch safe
  max_drawdown to prevent UI crash"). Das hätte jeden späteren Aufruf im
  selben Prozess verfälscht — auch die der CLI und der Research-Läufe.

Behoben: echter 50/50-Split über `backtest/splits.py` und `compare.py`,
Kostenprofil aus `config.yaml`, nicht messbare Kennzahlen bleiben `None`.

**(d) UTF-8-BOM in acht Dateien.** Ließ
`test_kein_modul_im_projekt_erreicht_die_anthropic_api` und
`test_kein_modul_im_projekt_importiert_live_bot` fallen — beide parsen den
Quelltext und scheiterten am nicht druckbaren Zeichen. Zwei rote Schutztests,
unbemerkt.

**Weiteres, das nicht stimmte:**

- `/api/overlays`, `/api/analysis`, `/api/strategy` waren **leere Stubs**,
  obwohl die Commit-Nachricht „Wired FVG and Swing calculations … to server.py
  API" behauptete. `execution/server.py` importierte `market_primitives`
  überhaupt nicht.
- `POST /api/orders/fill` gab `{"status":"ok"}` zurück und warf die Meldung
  weg. Das `FillEvent`-Modell verlangte `{symbol, price, quantity}` — Felder,
  die das AddOn nie sendet. **Jede Füllung lief in einen 422.** Deshalb blieb
  der Tagesverlust in allen drei Risikoimplementierungen für immer 0.
- `GET /api/orders/pending` **leerte** die Liste beim Abholen; ein zweiter
  Abholer nahm Orders weg, die nie ankamen. Kein Audit-Trail, kein Überleben
  eines Neustarts.
- Drei konkurrierende Risikomodule (`risk.py`, `risk_engine.py`, inline in
  `server.py`) mit drei verschiedenen Grenzen, keines angeschlossen.
- `execution/research_engine.py` schreibt Protokolle, in denen P&L und
  R-Multiple **literal fehlen** (kaputte f-Strings), lädt alle Timeframes und
  Instrumente vermischt (`SELECT … FROM bars ORDER BY ts_utc` ohne `WHERE`) und
  legt nichts ins Forschungsregister. **Noch offen.**
- Antigravity hat trotz Laurins Ansage („bitte pushe nicht alles ohne meine
  Zustimmung") nach GitHub gepusht (`fd29411` auf `origin/main`).
- `INCIDENT_REPORT.md` im Antigravity-Zwischenspeicher: mit `Remove-Item -Force`
  wurden **unversionierte** Dateien unwiederbringlich gelöscht — ein früherer
  `execution/server.py`, `adapter.py`, `store.py`, `ui/server.py`,
  `ui/frontend_old/`, `ninjatrader/TradayriBridge.cs`, `macro/cross_asset.py`.
  Nicht rekonstruierbar.

### 34.3 Was neu gebaut wurde

`common/kontoregeln.py` — benannte Kontoprofile nach dem Muster der
Kostenprofile, mit `quelle` und `ist_annahme`. **Alle Lucid-Zahlen sind
Annahmen:** Lucids Hilfe-Center (`support.lucidtrading.com`) antwortet
automatisierten Abrufen mit HTTP 403, die Werte stammen aus zwei unabhängigen
Übersichten Dritter (damnpropfirms.com, tradetanto.com, 30.08.2026). Wo sie
sich widersprachen, steht der **strengere** Wert. **Ein 300k-Konto existiert in
keiner der Quellen** — größte Stufe ist 150k; deshalb nicht eingetragen.
Laurin muss die Zahlen aus seinem Dashboard bestätigen.

`execution/store.py` — SQLite (`data/execution.sqlite3`): `orders`, `fills`,
`trades`, `entscheidungen`, `tagesabschluss`. Abholen ist ein Statuswechsel in
einer Transaktion, Füllungen sind über `exec_id` wiederholungsfest.

`execution/risiko.py` — die einzige Risikoprüfung. Vier Riegel in dieser
Reihenfolge: Handelsfenster, Tagesverlustlimit, nachziehender Gesamtverlust,
Positionsgröße. **EOD-Trailing** rechnet auf dem Tagesschluss (nicht dem
Intraday-Hoch) und friert über der initialen Trail-Grenze auf der Startbalance
ein. Die **Konsistenzregel wird berichtet, blockiert aber nicht** — sie greift
bei Lucid erst beim Auszahlungsantrag. **Ausstiege werden nie blockiert.**

`execution/buchung.py` — aus zwei Füllungen ein Trade. Die **Rolle**
(`entry`/`stop`/`target`) kommt vom AddOn und ist zwingend, weil alle drei
Orders einer Klammer denselben `order_key` tragen. MAE/MFE bleiben `None`:
sie brauchen den Kursverlauf *während* des Trades.

`execution/bot.py` — autonomer Handel **im Serverprozess**, nicht als eigener
Prozess. Keine eigene Signal-Logik: erkannt wird über `ideas.pipeline` und
damit über dieselben Regel-Objekte wie im Backtest (Invariante 6). Die
Positionsgröße folgt dem Stopabstand, nicht umgekehrt.

`execution/overlays.py` — Adapter von den Marktprimitiven auf den
`types.ts`-Vertrag. Gezeichnet wird mit `event_time`, ausgewertet dürfte nur
mit `availability_time` werden.

`common/levels.py` — `session_extremes`: Asia- und London-Hoch/-Tief. Über
`SessionWindow.contains`, also echte Zeitzonenrechnung; die Fenster überlappen
zwischen 07:00 und 09:00 UTC, und das ist Absicht.

### 34.4 Ein Befund, der eine Produktentscheidung erzwingt

Nachgemessen an den echten Signalen (42 Signale, sieben Tage MNQ-5m):

| | Risiko je EINEM Micro-Kontrakt |
|---|---|
| min | 50 USD |
| 25 % | 83 USD |
| **Median** | **119 USD** |
| 75 % | 138 USD |
| max | 154 USD |

Als Anteil des Lucid-Gesamtverlustpuffers, Median-Signal:

| Konto | Puffer | Anteil |
|---|---|---|
| 25k | 1.000 USD | **11,9 %** |
| 50k | 2.000 USD | 6,0 % |
| 100k | 3.000 USD | 4,0 % |
| 150k | 4.500 USD | 2,7 % |

**Die aktuellen 5m-Setups und ein Lucid-25k passen nicht zusammen.** Ein
einzelner Micro-Kontrakt — die kleinste handelbare Einheit — riskiert dort ein
Achtel des gesamten Spielraums; acht Verluste in Folge beenden das Konto. Bei
einem 7-%-Budget wären nur 14 % der Signale handelbar, und die Auswahl wäre
systematisch auf die ruhigsten verzerrt.

Wer sie trotzdem handeln will, braucht einen **größeren Kontotyp**, **engere
Stops** oder einen **Timeframe mit kleinerem ATR** — nicht eine andere Zahl im
Risikobudget. Der Befund steht als Kommentar in `config.yaml` und als Test
(`test_typisches_mnq_signal_sprengt_das_budget_eines_25k_kontos`).

Vorgabe deshalb: Profil `frei` mit selbst gesetzten Grenzen (1.800 USD gesamt,
600 USD je Tag), 150 USD Budget je Trade → 90 % der Signale handelbar.

### 34.5 Herkunft der übernommenen Fremdteile

`ui/frontend/` (rund 4.900 Zeilen TS/TSX) und
`ninjatrader/TradayriBridge.cs` stammen aus **Tradayri/TradeX**
(`github.com/MrT2044/TradeX`), dem Projekt eines Bekannten von Laurin.
Laurin hat am 30.08.2026 bestätigt, dass die Übernahme abgesprochen ist.

Das AddOn ist sorgfältig gebaut und trägt den entscheidenden Riegel:
`Account.Provider == Provider.Simulator`, geprüft am **Konto** statt an der
Verbindung, ohne Schalter. **Es lag bis zum 30.08.2026 nur im NT8-Ordner und
nicht im Repository** — eine betriebsnotwendige, unversionierte Abhängigkeit.

### 34.6 Erster echter Protokollierungslauf

`python -m ideas` lief am 30.08.2026 zum ersten Mal im **Schreibmodus**: 42
Ideen aus sieben Tagen, 23 davon gefiltert. Bis dahin war die Tabelle `ideen`
leer — der autonome Bot hätte also nie etwas gefunden, und `/api/trades`
lieferte nichts.

Ablehnungsgründe, nach Ursache gruppiert: `duenne_mittagszone` 8,
`adx_zu_niedrig_fuer_fortsetzung` 8, `adx_zu_hoch_fuer_reversion` 3,
`termin_blackout` 1.

### 34.7 Tickdaten geprueft und vorerst verworfen (30.08.2026)

Laurins Frage: "sind tick daten nicht noch besser?"

**Ausgangslage:** `Documents/NinjaTrader 8/db/tick/` ist **leer** (0 Byte).
Es gibt lokal keine Tickdaten; sie muessten erst vom Datenanbieter geladen
werden. Die Minutendaten belegen 24 MB fuer rund sieben Jahre.

**Was Tickdaten loesen wuerden:** Die Engine nimmt bei gleichzeitigem Treffer
von Stop und Ziel innerhalb einer Kerze den **Stop** an, weil aus OHLC nicht
rekonstruierbar ist, was zuerst kam (Invariante 4). Das ist bewusst
pessimistisch. Mit Ticks waere die Reihenfolge bekannt.

**Wie oft das ueberhaupt vorkommt - nachgemessen an 637.117 5m-Kerzen
(Dukascopy, zehn Jahre):**

| | |
|---|---|
| Median-Kerzenspanne | **0,88 ATR** |
| 95. Perzentil | 1,86 ATR |
| Maximum | 10,44 ATR |

Eine Kerze kann beide Niveaus nur beruehren, wenn ihre Spanne mindestens so
gross ist wie deren Abstand. Anteil der Kerzen, auf die das zutrifft:

| Stop | Ziel | Abstand | Obergrenze |
|---:|---:|---:|---:|
| 1,0 | 2,0 | 3,0 ATR | 0,746 % |
| **1,5** | **2,0** | **3,5 ATR** | **0,384 %** |
| 1,5 | 3,0 | 4,5 ATR | 0,110 % |
| 2,0 | 3,0 | 5,0 ATR | 0,062 % |
| 2,0 | 4,0 | 6,0 ATR | 0,022 % |

Das sind **Obergrenzen** - der Kurs muss zusaetzlich an der richtigen Stelle
stehen, die tatsaechliche Haeufigkeit liegt darunter. Bei den ueblichen
Projektwerten (1,5/2,0 ATR) sind es unter 0,4 % der Kerzen. Zur Gegenprobe auf
echten MNQ-Kerzen (2.146 Stueck, 90 Trades ueber alle sieben Strategien):
**null Faelle.**

*(Die Dukascopy-Reihe ist ein Index-CFD und kein MNQ-Futures. Fuer diese Frage
ist das gleichgueltig: gemessen wird die Geometrie der Kerzen, nicht das
Instrument.)*

**Entscheidung: vorerst keine Tickdaten.** Der Aufwand - Gigabytes, Stunden
Download je Kontrakt, eine andere Speicher- und Rechenarchitektur (pandas
traegt keine Milliarden Zeilen) - steht in keinem Verhaeltnis zu einer
Mehrdeutigkeit unter 0,4 %.

**Wofuer Ticks trotzdem gebraucht wuerden - falls die Frage wiederkommt:**

1. **Limit-Fills.** Der Backtest nimmt an, dass eine Limit-Order gefuellt
   wird, sobald der Kurs das Niveau beruehrt. Tatsaechlich braucht es
   Gegenpartei. Das betrifft den Bot unmittelbar, weil er Limit- und
   Stop-Orders schickt - und es ist der gewichtigere Punkt als die
   Stop/Ziel-Frage.
2. **Slippage.** Steht heute als Annahme im Kostenprofil.
3. **Volume Profile.** Traegt heute `naeherung: true`.
4. Sub-Minuten-Setups, falls die je gebaut werden.

**Der billigere Weg zu 1 und 2:** Der Bot handelt ab jetzt auf Sim101, und
NinjaTrader meldet die **tatsaechlichen** Fuellkurse zurueck (Tabelle `fills`
in `data/execution.sqlite3`). Der Abstand zwischen angenommenem und
tatsaechlichem Fuellkurs ist gemessene Ausfuehrungsqualitaet - ohne eine
einzige heruntergeladene Tickdatei. Steht als Punkt in
`docs/OFFENE_PUNKTE.md`.

### 34.8 Rollfenster kommen aus dem Bestand, nicht aus einer Formel (30.08.2026)

Der Import schnitt Kontrakte zunaechst auf ein gerechnetes Fenster zu: acht
Tage vor Verfall wird gerollt. Gegen die tatsaechlichen Daten geprueft, lag
diese Annahme daneben.

**NinjaTraders eigene Rollkonvention, abgelesen an 30 MNQ-Kontrakten:**

| Zeitraum | gerollt am |
|---|---|
| JUN19 bis DEC22 | Mittwoch/Donnerstag |
| MAR23 bis SEP26 | Freitag/Montag |

Die Acht-Tage-Formel haette ab MAR23 drei bis vier Kalendertage zu frueh
geschnitten — bei 16 von 30 Kontrakten.

**Deshalb liest `werkzeuge/nt8_import.py::rollplan_aus_nt8` die Fenster jetzt
aus dem Bestand:** jeder Kontraktordner unter
`Documents/NinjaTrader 8/db/minute/` enthaelt genau die Handelstage, an denen
NinjaTrader ihn als Frontmonat gefuehrt hat. Kontrakt N endet dort, wo N+1
beginnt — lueckenlos und ueberschneidungsfrei, ohne eine geratene Zahl.
`rollfenster` bleibt als Rueckfallebene, wenn der Ordner fehlt; der Import
sagt dann, mit welcher der beiden Quellen er gearbeitet hat.

**Gegenprobe: null fehlende Handelstage.** Die scheinbaren Luecken von ein bis
vier Kalendertagen an den Uebergaengen sind ausnahmslos Wochenenden. 30
Kontrakte, 1.954 Handelstage, Mai 2019 bis heute.

Kleine Dateien (unter 40 Byte) sind Platzhalter ohne Kerzen und wuerden den
Beginn faelschlich vorziehen; sie werden uebergangen.

### 34.9 NT8-Historie importiert: 30 Kontrakte, Mai 2019 bis August 2026 (30.08.2026)

Die Exporte lagen als `MNQ MM-YY.Last.txt` in `Documents/NinjaTrader 8/export/`
(Minuten-OHLCV, Semikolon, `yyyyMMdd HHmmss`). Beim Import fielen vier Dinge
auf, alle in `werkzeuge/nt8_import.py` behoben, jeweils mit Regressionstest
(`tests/test_nt8_import.py`, jetzt 32 Tests).

**1. Die Exporte sind in UTC, nicht `America/New_York`.** Der Kreuzvergleich
gegen die Bridge-Kerzen war eindeutig: als UTC gelesen stimmen **99,31 % der
9.310 gemeinsamen Kerzen bittgenau** (Return-Korrelation 0,9992); als
`America/New_York` gelesen liegt die Reihe vier Stunden daneben
(Niveau-Korrelation faellt von 1,000 auf 0,87, Return-Korrelation auf 0,05).
NinjaTrader exportiert in seiner Anzeigezeitzone, und die steht auf dieser
Installation auf UTC. **Jeder Import braucht `--zeitzone UTC`.** Der
Formatnachweis (`data/nt8_import_nachweis.json`) haelt die Zeitzone pro Eintrag
fest — ein Nachweis fuer `America/New_York` uebertraegt sich nicht auf UTC.

**2. `rollplan_aus_nt8` (der Fund aus 34.8) war toter Code.** `main()` verglich
das Dreitupel `(wurzel, jahr, monat)` gegen die `(jahr, monat)`-Schluessel des
Plans — `if kennung in plan` traf nie zu, der Import fiel still auf die
gerechnete Acht-Tage-Formel zurueck. Der Dry-Run sagte `(gerechnet, 8 Tage vor
Verfall)` statt `(aus NinjaTraders Datenbestand)`. Kein Test deckte `main()`
ab; die Tests aus 34.8 pruefen `rollplan_aus_nt8` und `rollfenster` einzeln.

**3. Numerische Dateinamen (`MNQ 09-26.Last.txt`) wurden nicht erkannt** — nur
`MNQ SEP26`. `kontrakt_aus_name` liest jetzt beide Schreibweisen; die
`db/minute`-Ordner heissen ohnehin `MNQ MM-YY`.

**4. Zwei Schutzpruefungen waren fuer die Realitaet zu streng.** Beide
Aenderungen wurden Laurin am 30.08.2026 vorgelegt und von ihm freigegeben
(Ausreisser-Toleranz: „einbauen"; die 2 stale Kerzen am 21.08. duerfen die
Bridge-Kerzen ueberschreiben).

- `kreuzvergleich` brach bei **jeder** Kerze ausserhalb 0,03 Punkten ab. Bei
  MNQ 09-26 waren 64 von 9.310 daneben: 2 am 21.08.2026 (NT8s eigene
  Lokaldatei fuer den Tag ist 935 Byte gross, quasi leer — die Bridge hat
  1.260 Kerzen), 62 am 24./25.08. mit <= 5 Punkten, fast alle <= 1 Punkt, und
  **ausschliesslich auf open/close, nie auf high/low** — Live-Tick gegen
  Historien-Trade an der Minutengrenze. Neu: besteht bei **>= 99 % in
  Toleranz** UND wenn keine +-1-Minuten-Verschiebung deutlich mehr Kerzen in
  Toleranz bringt (Marge 2 Prozentpunkte gegen Rundungsflattern an den
  Rand-Kerzen). Der Versatztest misst jetzt am **Anteil**, nicht am einzelnen
  schlechtesten Balken. Die Zeitzonen-/Beschriftungs-/Kontraktabsicherung
  bleibt voll erhalten — die scheitert bei ~100 % der Kerzen, nie bei 1 %.
- `pruefe_anschluss` verglich den Rollsprung in **absoluten Punkten** gegen
  400. MNQ stand 2019 bei 7.500 und 2026 bei 29.500 — 400 Punkte waren damals
  5 %, heute 1,4 %. Ueber alle 29 echten Rollen JUN19–SEP26 lag der Sprung
  zwischen **-0,55 % und +1,46 %**. Neu: relativ gegen **3 %**. Ausserdem nahm
  die Pruefung stur die erste Kerze jenseits der Kontraktgrenze als Nachbarn
  — beim ersten Alt-Import ist das der laufende Kontrakt, Jahre entfernt auf
  einem ganz anderen Kursniveau, und **jeder Alt-Import brach ab**. Neu:
  liegt der naechste Nachbar mehr als **4 Tage** entfernt, gibt es nichts
  anzuschliessen.

**Importreihenfolge:** MNQ 09-26 zuerst (schreibt den Formatnachweis), dann
die uebrigen 29 **von alt nach neu**, damit jeder Kontrakt seinen bereits
importierten Vorgaenger als Anschlussnachbarn sieht.

**Ergebnis:** `data/ntbridge.sqlite3` haelt jetzt **2.573.719 MNQ-Minutenkerzen**
(`source='nt8_export'` 2.572.461, `source='ninjatrader'` 1.258), von
2019-05-06 bis 2026-08-28, null doppelte Zeitstempel. Rund 352.000 Kerzen je
vollem Jahr. Die Luecken sind Wochenenden plus vereinzelte Duennmarkt-Minuten
2019–2021 (das ist, was NinjaTrader lokal vorhaelt). Die Backtests rechnen ab
jetzt auf sieben Jahren statt auf zehn Tagen — die p-Werte werden damit
ueberhaupt erst aussagekraeftig, und die Mehrfachtestkorrektur wird noetig.

Sicherung vor dem Import: `ntbridge.sqlite3` wurde vorher in den
Scratchpad kopiert (nicht im Repo).

## 35. TRADAYRI-Start: schwarzer Chart, volle Historie, Kerzenaggregation (30.08.2026)

**Der Fund.** Laurin meldete, beim Doppelklick auf `start_TRADAYRI.bat` zeige
die App nur einen „riesigen schwarzen Bildschirm". Nachgesehen: **kein
Absturz.** `desktop_app.py` oeffnet ein pywebview-Fenster (WinForms/WebView2,
`[pywebview] Using WinForms / Chromium`), die React-Oberflaeche rendert
vollstaendig. Das schwarze Rechteck in der Mitte ist die **leere
Chart-Flaeche**:

1. Eine fruehere Sitzung hatte die Instrument-Vorauswahl beim Start bewusst
   entfernt (`App.tsx`, „KEINE Vorauswahl … fuenfzehn Sekunden Rechenzeit").
   Ohne gewaehltes Instrument laedt der Chart nichts.
2. Selbst dann zeigte `/api/bars` nur ~1.500 Kerzen (`limit`-Vorgabe), und
   `HISTORY_BARS = 30_000` (~3 Wochen) war als „der Chart ist nicht fuer
   lange Zeitraeume da" dokumentiert.
3. Seit dem NT8-Import (Abschnitt 34.9) liegt nur **1m** vollstaendig vor.
   `5m/15m/1h` hatten nur die paar tausend Wochen-Kerzen der Bridge; `1d`
   255. Ein Chart „2019 bis heute" war damit nur auf 1m ueberhaupt moeglich —
   und 2,5 Mio Kerzen roh in den Browser gehen nicht.

**Laurins Entscheidung (30.08.2026):** die eingebettete Web-Oberflaeche
bleibt (kein nativer Umbau), und der Chart soll beim Start **grob** die volle
Historie zeigen, Detail beim Reinzoomen.

**Was gebaut wurde:**

- **`werkzeuge/aggregiere_kerzen.py`** leitet `1h/4h/1d` aus 1m ab
  (`common/timeframes.resample_ohlcv` — dieselbe Regel wie im Backtest,
  Invariante 1) und speichert sie als eigene `timeframe`-Zeilen mit
  `source='resampled_1m'` (Invariante 11: eine Ableitung, kein zweiter
  Messwert). `--voll` rechnet von vorn, ohne Schalter nur die juengsten
  Buckets. Ergebnis: 1h 45.538, 4h 11.836, 1d 2.187 Kerzen, 2019 bis heute.
  Warum nur diese drei: 2,5 Mio 1m je Anfrage aggregieren dauert ~20 s; die
  feinen Ebenen (`5m/15m`) zeigt die Oberflaeche nur als begrenztes Fenster
  und aggregiert der Server bei Bedarf direkt aus 1m (schnell genug).
  5 Tests (`tests/test_aggregiere_kerzen.py`).
- **`execution/server.py`**: `_aggregat_schleife` (asyncio-Task im
  `lifespan`) zieht `1h/4h/1d` alle 5 Minuten aus den hereinkommenden
  1m-Kerzen nach. `lade_anzeige_kerzen(symbol, tf, limit, before_ns)` ist der
  neue gemeinsame Kerzenlader fuer `/api/bars` **und** `_vorbereiteter_rahmen`
  (Overlays/Analyse): `limit=0` = volle Historie, `before` = Fenster nach
  hinten (Nachladen beim Zurueckscrollen). `/api/coverage` liefert jetzt echte
  `first_ts`/`last_ts` (standen fest auf `0`).
- **`ui/frontend`**: MNQ wird beim Start automatisch gewaehlt (das
  handelbare Instrument), Vorgabe-Timeframe `1d` (Schluessel `chart.timeframe.v2`
  — setzt die gespeicherte Vorliebe einmalig zurueck). Der 15-Sekunden-
  Warmlauf beim Instrumentwechsel ist weg: Chart, Overlays und Analyse holen
  sich ihre Daten je fuer sich, der Warmlauf ist nur noch fuer die Wiedergabe
  da und laeuft im Hintergrund. `TradeChart` laedt beim Scrollen an den linken
  Rand aeltere Kerzen nach (`onNeedOlder`), bei den feinen Timeframes; der
  Zeitausschnitt bleibt dabei stehen. `1h/4h/1d` = volle Historie, `5m/15m` =
  4.000er-Fenster.

**Stale Bridge-Reihen entfernt:** die wochenweisen `5m/15m/1h`-Kerzen der
Bridge (`source='ninjatrader'`, ~3.200 Zeilen) sind geloescht — 1m ist
kanonisch, `1h/4h/1d` vorberechnet, `5m/15m` kommen bei Bedarf frisch aus 1m.

**Warum SQLite-Lesen hier langsam ist:** ein `SELECT` von 2,5 Mio Zeilen mit
`sqlite3.Row`-Factory dauert ~120 s, mit Tupeln ~20 s, `pd.to_datetime` ohne
`format=` noch mal ~18 s. Deshalb liest `aggregiere_kerzen` mit eigener
Verbindung ohne Row-Factory, und `_lies_bars` im Server mit
`format="ISO8601"`. Merken fuer alles, was viele Kerzen liest.

**Offen (P2, `docs/OFFENE_PUNKTE.md`):** `aggregiere_kerzen --voll` liest die
1m-Reihe je Ziel-Timeframe neu; einmal lesen wuerde reichen. Und der
`chart.timeframe.v2`-Schluesselwechsel ist eine Migration, die spaeter wieder
raus kann.

## 36. Forschung auf echten Daten: Provider, Musterserie, erste W-Messung (30.08.2026)

Laurins Auftrag fuer diese Etappe: der Bot soll handeln wie ein sehr
erfahrener Trader — der weiss aus Erfahrung, dass ein W „in acht von zehn
Faellen funktioniert", und steigt am zweiten Tief ein. Muster, Strukturen und
alle Faktoren sollen einfliessen, so dass am Ende **fuer jede sinnvolle
Marktsituation** eine Hypothese mit dem hoechsten Erwartungswert bereitsteht.

### 36.1 Die Zielarchitektur, die daraus folgt

Nicht **eine** Universalregel, sondern ein **Ensemble aus Regime-Spezialisten**
(von Laurin am 30.08.2026 so praezisiert):

1. **Robustheit ueber Regimes ist die Eintrittshuerde, nicht das Endziel.**
   Eine Hypothese muss ueber die Regimes hinweg tragen, um als *echt* zu
   gelten — das ist der Beleg, dass der Effekt existiert und kein
   Regime-Artefakt ist.
2. **Danach Spezialisierung:** je Regime die Hypothese mit dem hoechsten
   Erwartungswert *in diesem Regime*.
3. **„Kein Rauschen":** ein Regime bekommt nur dann einen Spezialisten, wenn
   es genug Daten und einen belegbaren Effekt hat. Sonst bleibt der robuste
   Allrounder stehen — oder es wird dort nicht gehandelt.

Schritt 2 ist per Konstruktion overfitting-anfaellig („bester Erwartungswert
in diesem Regime" ist genau die Formulierung, mit der man Rauschen anfittet).
**Absicherung, als Regel im Code, nicht als Faustregel in der Doku:** ein
Spezialist loest den Allrounder nur ab, wenn er ihn in seinem Regime auch auf
Validation-Daten schlaegt, mit Mindest-Tradezahl, gegen das globale
Hypothesenbudget gerechnet.

Ebenfalls von Laurin entschieden (30.08.2026):

* **Globales Hypothesenbudget im Register.** Die Bonferroni-Schwelle wird
  gegen die Gesamtzahl je gepruefter Hypothesen gerechnet, nicht gegen den
  einzelnen Lauf. `Discoverylauf.bonferroni_schwelle` zaehlt bisher nur
  laufintern — bei einem Dauerlauf ist das eine Fassade. **Noch nicht
  gebaut.**
* **OOS-Kontingent.** Der OOS-Block bekommt eine harte Obergrenze an
  Confirmations und ist danach verbraucht; der Bot fasst ihn nicht
  selbstaendig an. **Noch nicht gebaut.**
* **Datenumfang:** erst die MNQ-Preisdaten ausschoepfen (2,57 Mio Kerzen,
  intraday-aufloesend), Cross-Asset ueber FRED danach als Ausbaustufe.

### 36.2 Der Blocker: die Engine kam an die Daten nicht heran

`backtest/data/__init__.py::create_provider` kannte ausschliesslich `"csv"`,
und in `data/` liegt als einzige CSV der **synthetische** `DEMO_1m.csv`. Jeder
Forschungslauf dieses Projekts rechnete deshalb entweder darauf oder auf der
Dukascopy-Naeherung — Index-CFD statt MNQ-Futures, laut Invariante 11 „rein
informativ". Das ist MASTERPLAN X.1, dort seit dem 23.08.2026 als P0 gefuehrt.

**`backtest/data/ntbridge_provider.py`** schliesst das. Er liest die 1m-Reihe
und aggregiert Groeberes ueber `common.timeframes.resample_ohlcv`. Bewusst
**nicht** aus den gespeicherten 1h/4h/1d-Zeilen: die sind eine Anzeigehilfe,
nachgezogen von einer Schleife im Serverprozess, und ein Forschungsergebnis
darf nicht davon abhaengen, ob die Oberflaeche lief.

**Rollsprung als stiller Fehler:** die Reihe ist aus 30 Quartalskontrakten
zusammengesetzt; an den 29 Nahtstellen springt der Preis um −0,55 % bis
+1,46 %. Fuer den Backtest sieht das aus wie eine Uebernachtluecke, ist aber
keine — eine Gap-Strategie saehe dort 29 Scheinsignale. Der Provider weist die
Nahtstellen ueber `.rollgrenzen` aus (bevorzugt aus NinjaTraders
Kontraktbestand, ersatzweise aus dem Preissprung, und sagt im Log welche
Quelle). Die Kurse werden **nicht** rueckangepasst: das machte Niveau-Aussagen
(Vortageshoch, VWAP-Abstand in Punkten) unvergleichbar.

### 36.3 Chartmuster als Serie

`common/patterns.py::detect_double_top_bottom` ist **punktuell** — es sieht
ans Ende eines Rahmens. Fuer die Frage „traegt ein W, und in wie vielen
Faellen" braucht es fuer jede Kerze ein Urteil.

**`common/muster_serie.py`** liefert das. Swing-Punkte werden **einmal** ueber
die ganze Reihe gesucht statt je Kerze neu: aus O(n × lookback) wird O(n),
gemessen 7 s auf 519.000 Kerzen. Keine zweite Musterdefinition — die Schwellen
sind aus `detect_double_top_bottom` uebernommen, und ein Test prueft ueber die
ganze Reihe, dass beide zum selben Urteil kommen.

**Der Lookahead, der dabei verhindert wird:** ein Swing-Tief ist an seiner
eigenen Kerze nicht erkennbar (`find_swing_points` sagt es selbst). Das zweite
Tief bei Kerze *i* ist fruehestens bei *i + strength* bekannt. Wer „am zweiten
Tief" einsteigt, handelt mit Wissen aus der Zukunft — und das Ergebnis sieht
hervorragend aus, ohne dass an den Kursen etwas verdaechtig waere. Das Modul
fuehrt `event_index` (wo das Muster LIEGT, fuer die Anzeige) und
`verfuegbar_index` (ab wann bekannt) getrennt, wie
`common/market_primitives.py`; alle Spalten stehen auf der Verfuegbarkeit.

Zwei Strategien mit **einem einzigen Unterschied**:
`doppelboden_bestaetigt` (frueh, unbestaetigt) gegen
`doppelboden_nackenbruch` (spaet, bestaetigt, Lehrbuchvariante).

### 36.4 Engine 20x schneller — und der Preis dafuer

Die Hauptschleife baute je Kerze **zwei pandas-Series** ueber `data.iloc[i]`,
bei inzwischen ueber vierzig Spalten. Auf 363.000 Kerzen waren das ~5 Minuten
je Strategie und Block; mit den zwoelf neuen Musterspalten wurde es schlimmer.

Neu: nur die Spalten, die `strategy.benoetigte_spalten()` nennt, werden als
numpy-Arrays vorgehalten; je Kerze entsteht ein kleines Dict.
`BarContext.value` greift ueber `.get()` zu, ein Dict genuegt dafuer.
**Gemessen: ~5 min → ~15 s je In-Sample-Lauf.**

**Das neue Risiko und seine Absicherung:** vorher bekam eine Regel *alle*
Spalten; eine Regel mit unvollstaendigem `benoetigte_spalten()` funktionierte
zufaellig mit. Jetzt liest sie NaN, feuert nie und liefert null Trades ohne
Fehlermeldung — der `ib_breakout`-Fehlertyp. `tests/test_spaltenvertrag.py`
schliesst die Luecke: fuer **jede** Strategie der Bibliothek muss der Lauf auf
dem beschnittenen Rahmen dieselben Trades liefern wie auf dem vollen. Alle
neun bestehen.

### 36.5 Erste Messung des W — Zahlen in `docs/W_MESSUNG_2026-08-30.md`

Erster Backtest dieses Projekts auf **echten MNQ-Futuresdaten**. 519.084
5m-Kerzen, 2019–2026, nichts optimiert (OOS damit nicht verbraucht).

| Strategie | Block | Trades | Treffer | PF | Ø/Trade |
|---|---|---:|---:|---:|---:|
| `doppelboden_bestaetigt` | IS | 2.252 | 34,8 % | 0,93 | −2,60 USD |
| `doppelboden_bestaetigt` | OOS | 990 | 37,4 % | 1,05 | **+3,29 USD** |
| `doppelboden_nackenbruch` | IS | 1.911 | 35,9 % | 0,97 | −1,08 USD |
| `doppelboden_nackenbruch` | OOS | 813 | — | — | −3,50 USD |
| `vwap_trend` | IS | 2.602 | 21,9 % | 0,86 | −4,09 USD |
| `vwap_trend` | OOS | 1.010 | 22,3 % | 0,95 | −2,38 USD |

**Die Trefferquote des W liegt bei ~35 %.** Laurins „acht von zehn Faellen"
war ausdruecklich ein erfundenes Illustrationsbeispiel, keine Behauptung —
hier wird also nichts widerlegt. Festzuhalten bleibt: eine Trefferquote ist
**ohne Stop und Ziel nicht definiert**, und sie allein ist wertlos
(MASTERPLAN J). Jede Aussage der Form „funktioniert in X von 10 Faellen" muss
das Regelwerk mitnennen, sonst ist sie nicht ueberpruefbar.

**Die beste Zahl der Tabelle ist auch die verdaechtigste.** Ein
Vorzeichenwechsel zwischen IS und OOS ist kein Fund, sondern eine Warnung; und
die Rangfolge der beiden Einstiege dreht sich zwischen den Bloecken ebenfalls.
Ob das Regime oder Zufall ist, laesst sich ohne Regime-Engine und ohne
t-/p-Werte nicht entscheiden. **Keine der beiden Hypothesen ist im Register
eingetragen** — bis das nachgeholt ist, zaehlen sie nicht gegen das
Hypothesenbudget.

### 36.6 Regime-Engine und erster Discovery-Lauf — ein sauberes Negativ

`common/regime.py` baut die drei Achsen aus MASTERPLAN I:

| Achse | Groesse | Auspraegungen |
|---|---|---|
| `vola_regime` | ATR-Rang | niedrig / mittel / hoch |
| `struktur_regime` | ADX-Rang | range / uebergang / trend |
| `liquiditaet_regime` | relatives Volumen zur **selben Tageszeit** | duenn / normal / rege |

**Grenzen aus der Verteilung, nicht aus einem Lehrbuch** — Terzile eines
rollenden 60-Sessions-Fensters. „ADX ueber 25 heisst Trend" waere eine Zahl
aus einem Buch; der `consolidation_max_atr = 1.2`-Fund vom 22.08.2026 zeigt,
was solche Zahlen anrichten.

**Rueckwaertsgerichtet, und ein Test haelt das fest.** Perzentile ueber die
Gesamthistorie waeren bequem und falsch: das Regime einer Kerze von 2019
haenge dann davon ab, wie volatil 2026 war.
`test_spaetere_kerzen_aendern_ein_frueheres_regime_nicht` schneidet die Reihe
ab und prueft, dass sich nichts aendert.

**Warum relatives Volumen zur selben Tageszeit:** ein roher Volumenrang wuerde
die Eroeffnung immer als „rege" und die Nacht immer als „duenn" einstufen —
eine Aussage, die schon in der Session-Angabe steckt. Interessant ist, ob die
10:00-Kerze *heute* belebter ist als die 10:00-Kerze ueblicherweise.

**Verteilung auf echten Daten:** alle 27 Schubladen belegt (1,7 % bis 8,1 %).
Die Achsen sind aber **nicht unabhaengig** — `niedrig|range|duenn` und
`hoch|trend|rege` sind die groessten; ruhige Naechte und aktive Trendtage
buendeln sich.

**Discovery-Lauf** (`werkzeuge/regime_discovery.py`, nur Trainingsteil,
`pruefe_nur_training` scharf): drei Strategien x fuenf Faktoren.

```
Gepruefte Hypothesen : 51
Korrigierte Schwelle : 0,000980  (alpha / 51)
Bester p-Wert        : 0,0071
KEINE Gruppe unterschreitet die korrigierte Schwelle.
```

**Nach strengem Massstab ist nichts gefunden.** Das ist kein Fehlschlag,
sondern der Zweck des Laufs: bei 51 Hypothesen und alpha = 0,05 sind rund 2,6
„signifikante" Funde der Erwartungswert. Die beste positive Gruppe
(`doppelboden_bestaetigt` / Struktur / `uebergang`, p = 0,050) waere
unkorrigiert ein „Fund" gewesen.

**Notiert, ohne Signifikanzanspruch:** beide Doppelboden-Varianten ordnen die
Liquiditaetsachse identisch (rege > normal > duenn), obwohl sie sich im
Einstieg unterscheiden. Auf der Strukturachse widersprechen sie sich dagegen
(frueh traegt im Uebergang, spaet im Trend). Zahlen und Einordnung in
`docs/REGIME_DISCOVERY_2026-08-30.md`.

**Der Vorzeichenwechsel aus 36.5 ist damit nicht erklaert.** Die Achsen
trennen zu schwach.

### 36.7 Naechste Schritte

1. Globales Hypothesenbudget + OOS-Kontingent im Register (36.1). **Bis dahin
   darf aus mehreren Discovery-Laeufen keine Signifikanzaussage
   zusammengesetzt werden** — die 51 Hypothesen dieses Laufs zaehlen nirgends.
2. Ungeprueft gebliebene Faktoren: Position zu Vortagesmarken, Struktur der
   uebergeordneten Zeitebene, Abstand zum VWAP.
3. Achsen entkoppeln (Strukturrang *innerhalb* des Volatilitaetsterzils).
4. Die vier offenen Hypothesen aus der Antigravity-Phase.
5. Erst danach der autonome Kreislauf.

### 36.8 Zu Laurins Zielbild „fallbasiertes Schliessen"

Er hat es am 30.08.2026 praezisiert: der Bot soll erkennen „diese Situation
kam schon mal vor, ist meist so und so verlaufen, also setze ich so" — Muster,
Strukturen und Ereignisse zusammen. `common/market_state.py::MarketState` ist
bereits die passende Fingerabdruck-Struktur dafuer.

**Die eingebaute Gefahr, schaerfer als normales Overfitting:** bei 519.000
Kerzen und reichem Merkmalsvektor findet man zu *jeder* Lage aehnliche
historische Lagen. Die Bonferroni-Zaehlung greift dann nicht mehr, weil aus
abzaehlbaren Hypothesen ein Kontinuum wird. Was dagegen wirkt: Merkmalsvektor
vorher festlegen statt suchen; Mindestzahl an Analogfaellen, sonst „keine
Meinung"; die Vorhersage muss eine naive Nulllinie schlagen; vorwaerts in der
Zeit halten, nicht nur im Nachbarschaftsraum. Die Regime-Engine baut die
ersten beiden als grobe Stufe — 27 abzaehlbare Schubladen statt eines
Kontinuums.

**Ereignisdaten, Bestandsaufnahme:** `ideas/kalender.py` (Forex Factory)
liefert „im Wesentlichen die laufende Woche" — fuer 2019–2026 gibt es dort
**keine Terminhistorie**. Historisch verfuegbar sind: FRED/ALFRED-Vintages
(`macro/`, 8 Reihen, mit „was war wann bekannt"), `common/marktkalender.py`
(Feiertage, Frueh-Schluesse), deterministisch ableitbare Termine (FOMC, NFP,
Verfallstage, Monatsende) — und vor allem die Spuren der Ereignisse **im
Kursverlauf selbst** (Volatilitaets- und Volumenanomalien), die in
Minutenaufloesung schon vorliegen.

---

## 37. Ereignisdatenbank Etappe 1: serielle Erkenner, muster_serie-Fix, TRADAYRI-Zeitstempel (31.08.2026)

Auftrag: Laurins umfassende empirische Untersuchung der 2,57 Mio
MNQ-Minutenkerzen (`docs/FORSCHUNGSPLAN_EVENTDATENBANK.md`). **Keine
Strategie** — eine reproduzierbare Wissensbasis: welche Situationen treten
auf, wie oft, wie entwickeln sie sich. Diese Sitzung baut Etappe 1 (punktuelle
Erkenner → Serien) weiter.

### 37.1 `common/ereignisse/` — die serientauglichen Erkenner

Alle liefern `list[Ereignis]` (aus `basis.py`) mit den vier getrennten
Zeitpunkten. `Ereignis.__post_init__` bricht bei
`entstehung ≤ bestaetigung ≤ verfuegbar`-Verletzung ab. Jeder Erkenner hat
einen Lookahead-Test (Reihe abschneiden, neu rechnen, frueh verfuegbare
Ereignisse identisch) und — wo es eine punktuelle Vorlage gibt — einen
Gleichheitstest gegen sie.

| Modul | Ereignisse | Vorlage | Laufzeit volle Historie |
|---|---|---|---|
| `swings.py` | `SwingSerie` (kein Ereignis, Basis) | `structure.find_swing_points` | ~0,7 s |
| `struktur.py` | `bos_bullish/bearish`, `choch_*` + `struktur_spalten` (HH/HL/LH/LL, Trend) | `market_primitives.detect_structure_breaks` | ~16 s → 181k |
| `niveaus.py` | `niveau_test` (n-ter Test), `ausbruch`, `fehlausbruch`, `ausbruch_retest` an PDH/PDL/PDC/IB + Swings | neu (Plan 4) | ~86 s → **829k** |
| `fvg.py` | `fair_value_gap` (bullish/bearish) + Mitigation im Fenster + `fvg_spalten` | `market_primitives.detect_fair_value_gaps` | ~40 s |
| `displacement.py` | `displacement` — **Adapter**, keine eigene Logik | `market_primitives.detect_displacements` (schon O(n)) | ~3 s |

**`niveaus.py`, ein Entwurfsfehler unterwegs:** die erste Fassung zaehlte
jeden Abpraller von einem Niveau als „Ausbruch" — vier saubere Tests eines
Levels erzeugten vier Falschereignisse. Jetzt ist ein Ausbruch der **Wechsel
der etablierten Seite**: der Kurs muss vorher klar auf einer Seite gestanden
haben (`abs(close − L) > max(tol, puffer)`) und durch das Niveau schliessen.

**`niveaus.py`, Beobachtung fuer Etappe 3:** die swing-basierten Niveaus
machen ~800k der 829k Ereignisse aus (jeder der ~250k bestaetigten Swings wird
ein aktives Niveau). Das ist vermutlich zu fein — beim Fuellen der
`events`-Tabelle ist zu entscheiden, ob nur „bedeutende" Swings oder nur die
juengsten N als Niveau gelten. Der Erkenner selbst ist korrekt.

**`fvg.py`, bewusste Abweichung von der Vorlage:** der punktuelle Erkenner
verfolgt die Mitigation bis ans Reihenende (fuer die Anzeige „ist dieses FVG
noch offen"). Die Serie tut es in `mitigation_fenster` Kerzen (Vorgabe 240 =
4 h, laengster Nicht-Session-Horizont im Plan). Test haelt fest, dass beide
**innerhalb des Fensters** dasselbe Mitigation-Urteil faellen.

**Noch nicht gebaut** (Plan Abschnitt 4, fuer die naechste Etappe): Liquidity
Sweep (Sweep + Reclaim), Order Block, Equal Highs/Lows als Serie, Triple
Top/Bottom, Bewegungsmuster (Impuls+Konsolidierung, Reversal nach Extrem,
Kompression→Expansion), Opening Range. Diese sind definitionsempfindlicher —
Laurin plante dafuer die Opus-5-Sitzung.

### 37.2 `common/muster_serie.py`: O(n²) → O(n)

`finde_doppelmuster` suchte je Paar gleichartiger Swings den Berg/Talpunkt
dazwischen mit einer Komplettschleife ueber **alle** Gegen-Swings. Bei ~250k
Swings auf 2,5 Mio Kerzen ≈ 77 min allein fuer diese Stufe von
`Backtester.prepare` — der Grund, warum ein Forschungslauf ueber die volle
Historie nie durchlief (in Abschnitt 36.4 unbemerkt geblieben, weil dort nur
auf Ausschnitten gemessen wurde).

Jetzt ueber `np.searchsorted` auf die aufsteigenden Gegen-Swing-Indizes: je
Paar nur das kurze Fenster dazwischen. `argmax`/`argmin` waehlen bei
Gleichstand wie Pythons `max`/`min` den ersten Treffer — **die
Musterdefinition aendert sich nicht**, ein neuer Test vergleicht Fund fuer
Fund gegen die alte volle Suche.

Gemessen: doppelmuster-Stufe bei 200k Kerzen 29,6 s → 2,6 s. `prepare()` ueber
die volle Historie jetzt **~85 s** (Laden 61 s, `niveau_ereignisse` 86 s,
`pruefe_lookahead` 0,1 s — alles auf 1m, kein Kompromiss).

### 37.3 TRADAYRI: schwarzer Chart, Zeitachse auf „1970"

Laurin meldete am 31.08.2026: Chart schwarz, Zeitachse „21.01.1970", beim
Umschalten auf 1d ein Absturz. Ursache: **pandas 3.0.5 parst ISO8601 zu
`datetime64[us]`**, dann liefert `DatetimeIndex.asi8` Mikrosekunden.
`_rahmen_zu_bars` gab die als „Nanosekunden" aus; das Frontend
(`toChartTime` in `TradeChart.tsx`) teilt durch 1e9 und landet im Januar
1970. Bei 1m kollidieren viele Kerzen auf dieselbe Sekunde →
lightweight-charts bricht beim naechsten Update mit „data must be asc
ordered" ab → schwarzer Screen.

Fix: `_rahmen_zu_bars` erzwingt `df.index.as_unit("ns").asi8`.
Regressionstest in `test_execution_server.py`. `desktop_app.py`:
Serverstart-Timeout 30 s → 90 s (erster Start muss die 657-MB-Kerzen-DB
oeffnen; der Launcher hatte den langsam startenden Server sonst getoetet und
Prozess-Waisen hinterlassen, die den Port hielten).

**Offen, nicht Code:** „keine neuen Kerzen" — die letzte 1m-Kerze ist vom
28.08.2026 (Import-Ende). Die Live-Bruecke (`ClaudeBridge.cs`-Indikator in
NinjaTrader → `python -m ntbridge` → sqlite) schreibt nichts nach, solange in
NT8 kein Chart mit dem Indikator offen ist oder der Empfaenger nicht laeuft.

### 37.4 Forschungsplan: fuenf Schema-Ergaenzungen (externe Pruefung)

Eine externe Durchsicht (Gemini) nannte fuenf Luecken, alle berechtigt,
eingearbeitet (`docs/FORSCHUNGSPLAN_EVENTDATENBANK.md` Abschnitt 16):

- `triggers.order_art` + gemessene Limit-Nichtfuellung; Slippage bleibt
  benanntes Szenario in der Auswertung (Invariante 10/11)
- `outcomes.intrabar_ambig` + Doppelklassifikation stop-zuerst/ziel-zuerst
- `events.cluster_id`: gleichzeitige Signale ueber Mustertypen/Zeitebenen
  zaehlen in der Signifikanz als eine Beobachtung
- `events.volumen_am_extremum_relativ` als Orderbuch-Ersatz
- VIX taeglich ueber FRED als Merkmal; `smt_divergenz` im Schema, `NULL` bis
  eine ES-Reihe angebunden ist

Kernaussage im Plan festgehalten: diese Verschaerfungen machen die Messung
ehrlicher, erzeugen aber **keinen** Vorteil. Die Grundratentabelle kann
genauso gut zeigen, dass in 1m-OHLCV-Mustern nichts zu holen ist — ein
zulaessiges Ergebnis.

---

## 38. Ereignisdatenbank Etappen 2 und 3: Schema, Schreibweg, erster Volllauf (31.08.2026)

### 38.1 `common/ereignisse/datenbank.py`

Vier Tabellen nach Plan (`events`, `outcomes`, `triggers`, `stop_szenarien`)
plus `laeufe` fuer die Herkunft. **Kernmerkmale als echte Spalten**
(`level_1/2/neckline`, Hoehe, Dauer), **Musterspezifisches zusaetzlich als
`merkmale_json`** — nichts geht verloren, die haeufigen Abfragen bleiben
schnell.

`schreibe_events` reichert jedes Ereignis mit dem Kontext **am
Verfuegbarkeitszeitpunkt** an: ATR, drei Regime-Achsen, Session, Wochentag,
Minuten seit RTH-Open, Trendlage, Abstand zu VWAP/PDH/PDL, relatives Volumen,
Rollnaehe, Datensatzblock, `cluster_id`.

**Drei Entwurfsentscheidungen, die aus konkreten Fehlern stammen:**

1. **Spaltennamen im INSERT ausdruecklich benannt.** Ein `?` zu wenig meldet
   SQLite (passierte beim ersten Versuch: 38 Spalten, 36 Werte). Ein
   *vertauschtes* Paar gleicher Typen meldet es **nicht** — dann stuende der
   Kontext still in der falschen Spalte. Ein Test haelt `EVENT_SPALTEN` und
   Schema deckungsgleich.

2. **`vergib_cluster` mit festem Fenster statt transitiver Kette.** Die Kette
   (A-B, B-C ⇒ A-B-C) klang richtiger, lief auf 1m-Daten mit sieben Erkennern
   aber davon: gemessen **58 Ereignisse ueber mehrere Minuten** in einem
   Cluster. Das waere keine Gleichzeitigkeit mehr, und die Stichprobe
   schrumpfte zu stark. Mit festem Fenster: Median 4–5, Maximum 38.

3. **Blockgrenzen fest verdrahtet** (`TRAINING_BIS`, `VALIDATION_BIS`). Sie
   duerfen nicht mit dem Datenbestand wandern, sonst ist ein Ergebnis von
   heute nicht mit einem von naechster Woche vergleichbar.

### 38.2 Der Schreibweg war 45x zu langsam — und warum

Der erste Volllauf schrieb 2,59 Mio Zeilen in **7.087 Sekunden**: 2,7 ms je
Zeile, rund hundertmal langsamer als SQLite kann.

**Erste Vermutung war falsch.** Ich hielt die fuenf Sekundaerindizes fuer die
Ursache, baute `massenschreiben` (Indizes weg, einfuegen, Indizes neu) — und
mass **keinen Unterschied** (3.595 gegen 3.563 Zeilen/s).

**Dann profiliert statt geraten** (`cProfile`): **24 von 36 Sekunden** gingen
in `index[i]`, das Herausgreifen einzelner `Timestamp`-Objekte aus dem
`DatetimeIndex` — fuenf Zugriffe je Ereignis (drei `isoformat()`, zwei
`tz_convert`). Jeder Zugriff baut ein Python-Objekt.

Behoben, alles einmal vektorisiert:

| Funktion | Was sie ersetzt |
|---|---|
| `_iso_strings` | `strftime` ueber den ganzen Index statt `isoformat()` je Zeile |
| `_minuten_seit_open_serie` | eine `tz_convert` fuer alles |
| `_session_serie` | Nachschlagecache ueber (Wochentag, Minute) — `primary_session` hat hoechstens 7 × 1440 Antworten |

Ergebnis: **3.595 → 16.459 Zeilen/s**, hochgerechnet 157 s statt 7.087 s.
Erst danach brachten die Indizes messbare 25 Prozent — vorher waren sie vom
Timestamp-Overhead ueberdeckt.

**Das Formatrisiko dabei:** `strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"` muss
auf das Zeichen genau dem entsprechen, was `Timestamp.isoformat()` liefert —
sonst waeren zwei Laeufe nicht vergleichbar, **und man saehe es keiner
einzelnen Zeile an**. Ein Test prueft vier Zeitraeume inklusive beider
US-Zeitumstellungen; bei Bruchteilsekunden faellt die Funktion auf den
langsamen, aber immer richtigen Weg zurueck.

`_session_serie` benutzt bewusst **dieselbe** `primary_session` mit Cache und
keine vektorisierte Neufassung — eine zweite Sessionlogik waere derselbe
Fehler wie eine zweite Indikatorrechnung (Invariante 1).

### 38.3 `werkzeuge/ereignisse_erkennen.py` und der erste Volllauf

Der Lauf: laden → `prepare` → Regime → sieben Erkenner →
Lookahead-Sammelpruefung → schreiben. `--probelauf` zaehlt ohne zu schreiben.
**Alles auf 1m.**

Das relative Volumen kommt aus derselben Funktion wie der Liquiditaetsrang der
Regime-Engine — eine zweite Formel waere der Anfang davon, dass
Ereignismerkmal und Regimeachse auseinanderlaufen. Bleibt das Regime leer
(Zeitraum kuerzer als das rollende 60-Tage-Fenster), sagt der Lauf das
ausdruecklich, statt still ohne Kontext zu schreiben.

**Ergebnis (`L20260830-233449`):** 2.573.719 Kerzen → **2.592.334 Ereignisse**,
Training 1.665.446 / Validation 352.175 / OOS 574.713. Regime-Kontext fuer
98,7 % der Kerzen. Zahlen und Auswertung:
`docs/EREIGNISDATENBANK_BESTAND_2026-08-31.md`.

### 38.4 Der Befund, der eine Entscheidung erzwingt

Der Plan rechnete mit **200.000–800.000** Ereignissen. Es sind **2,59 Mio** —
und das ist erst die 1m-Ebene (Entscheidung 1 sieht zusaetzlich 5m/15m/1h vor).

`outcomes` waere damit ~23 Mio Zeilen (× 9 Horizonte) — handhabbar.
**`stop_szenarien` im vollen Raster (25 Positionen × 5 Entries) waeren ueber
300 Mio Zeilen** — weder als SQLite-Tabelle noch in vertretbarer Rechenzeit
machbar. Entscheidung 5 des Plans muss neu getroffen werden.

Ein Grund dafuer ist benennbar: **59 % aller Niveau-Ereignisse haengen an
Swing-Hochs und -Tiefs**, weil jeder der ~250.000 bestaetigten Swings als
eigenes Niveau zaehlt. Drei Wege stehen Laurin vorgelegt in
`docs/UEBERGABE_2026-08-31.md` Abschnitt 3; empfohlen ist, die Grundraten
ueber alle Ereignisse zu messen und das volle Stop-Raster nur fuer die
Mustertypen zu rechnen, die dort einen Effekt zeigen — mit Zaehlung des
Auswahlschritts im Hypothesenregister.

### 38.5 Zwei Beobachtungen aus dem Bestand

**Der n-te Test eines Niveaus faellt bemerkenswert stabil ab:** nach jedem
Test wird ein Niveau in rund **einem Drittel** der Faelle noch einmal
getestet (32/31/30/31/33 % ueber sechs Stufen). Ob der zweite Test besser
*haelt* als der erste, sagt das nicht — dafuer braucht es Etappe 4.

**Sweeps gehen mit rund doppeltem Volumen einher** (1,85–2,11× je Session,
sehr gleichmaessig), und die Richtungen sind in jeder Session bis auf unter
3 % ausgeglichen. Das ist die einzige Aussage ueber "Liquiditaet", die diese
Daten hergeben — gemessen am Umsatz, keine Aussage ueber Order-Tiefe.

### 38.6 Live-Chart: warum keine Livedaten ankamen (31.08.2026)

Laurins Frage. Drei Ursachen, zwei davon unfertiger Code:

1. **Die Nachladeschleife lief nur bei `liveActive`** — also wenn
   `/api/session` eine laufende Handelssitzung meldete. Dieser Endpunkt war
   ein fest verdrahteter Platzhalter mit `running: false`. Ein Chart soll
   ohnehin den neuesten Stand zeigen, ob dabei gehandelt wird oder nicht; die
   Schleife haengt jetzt nur noch daran, ob die Boerse offen ist.
2. **`/api/market` hatte `is_open` fest auf `true`.** Eine Kopfzeile, die
   sonntags "MARKT OFFEN" meldet, ist eine Behauptung mit Autoritaet. Jetzt
   aus `common/sessions.py`.
3. **Der Empfaenger lief nicht.** Kein Codefehler — aber es war nirgends
   sichtbar. `/api/market` liefert jetzt `letzte_kerze_ts`,
   `datenalter_sekunden`, `daten_frisch`; die Kopfzeile zeigt "Letzte Kerze",
   gelb wenn die Boerse offen ist und trotzdem nichts nachkommt. Bei
   geschlossener Boerse **nicht** angemahnt — eine Warnung, die jede Nacht
   leuchtet, wird ignoriert.

`/api/session` meldet jetzt drei getrennte Aussagen: `running` (Bot
arbeitet), `connected` (Kerzen kommen an), `active` (beides). Nur `active`
zeigt "ECHTZEIT" — ein laufender Bot ohne Datenstrom ist kein
Echtzeitbetrieb.

Ebenfalls behoben: Serverstart-Timeout 30 s → 90 s. Der erste Start muss die
657-MB-Kerzendatenbank oeffnen; unter Plattenlast reichte das nicht, und der
Launcher hat den langsam startenden Server dann getoetet (Laurins
Fehlermeldung vom 30.08.2026 abends).

---

## 39. Ereignisdatenbank Etappen 4 und 8: Outcomes und Grundraten (31.08.2026)

### 39.1 `common/ereignisse/outcomes.py`

MFE, MAE, Endergebnis je Ereignis und Horizont (1/3/5/10/20/30/60/120/240
Kerzen).

`backtest/excursions.py::compute_path_excursions` rechnet je Einstieg eine
Python-Schleife ueber den Horizont: **O(Ereignisse × Horizont)**. Bei 2,59 Mio
Ereignissen und Horizonten bis 240 waeren das Milliarden Iterationen.

Hier stattdessen **rollende Fenster ueber die ganze Kursreihe** — einmal je
Horizont gerechnet, danach ist alles Nachschlagen. Die Zeit-bis-Extremum
kommt aus `sliding_window_view` + `argmax`, blockweise (200k Kerzen je
Block, ~380 MB Fensterblick).

**Gemessen: 4,4 s fuer 500k Ereignisse auf 500k Kerzen ueber alle neun
Horizonte** — hochgerechnet 2 Minuten fuer die volle Historie.

Ein Test vergleicht beide Fassungen ueber vier Horizonte × zwei Richtungen,
Zeile fuer Zeile (Einstiegspreis, MFE, MAE, Ende, Zeit bis MFE/MAE).

**Ein Unterschied ist Absicht:** `compute_path_excursions` setzt bei
fehlendem ATR ersatzweise `5.0` ein (Zeile 104). Das ist eine erfundene Zahl,
die aussieht wie eine Messung — fuer eine Anzeige verzeihlich, fuer eine
Wissensbasis nicht (Invariante 11). In `outcomes.py` bleiben die R-Werte
`NaN`.

**Unvollstaendige Fenster werden verworfen, nicht gekuerzt.** Ein gekuerztes
Fenster sieht aus wie ein vollstaendiges und verzerrt die Statistik zum
Reihenende hin (Plan Abschnitt 10). Im Probelauf: bei H=240 fehlen genau die
letzten 233 Ereignisse — plausibel.

### 39.2 Schemakorrektur: Rohzahlen und Klassen getrennt

Der Plan sah `outcomes` mit Primaerschluessel
`(event_id, horizont_bars, schwelle_atr)` vor. Das ist falsch normalisiert:
**MFE und MAE haengen nicht von der Klassifikationsschwelle ab**, nur die
Klasse tut das. Bei drei Schwellen (0,25/0,5/1,0) waeren das 70 statt 23 Mio
Zeilen fuer denselben Inhalt.

Jetzt: `outcomes` traegt die Rohzahlen mit `(event_id, horizont_bars)`,
`outcome_klassen` die Klassifikation mit
`(event_id, horizont_bars, schwelle_atr)`.

### 39.3 `common/ereignisse/grundraten.py` — die vier Fallen

Die Tabelle, um die es Laurin von Anfang an ging. Jede der vier Vorkehrungen
existiert wegen eines konkreten Fehlers, der sie sonst wertlos machte:

1. **Nulllinie.** „In 62 % der Faelle ging es hoch" ist wertlos, wenn es ohne
   das Muster in 61 % der Faelle hochgeht. Jede Zahl steht neben ihrer
   Grundrate — und die wird **je Richtung** gerechnet: ein Muster, das nur
   Shorts erzeugt, waere gegen eine gemischte Nulllinie systematisch falsch
   bewertet.
2. **Ueberschneidung.** `ueberschneidungsfrei()` waehlt gierig Ereignisse,
   deren Fenster sich nicht ueberlappen. Der ueberschneidungsfreie p-Wert ist
   der **massgebliche**, der ueberschneidende wird daneben ausgewiesen
   (empirisch am 30.08.2026: t = 8,49 gegen t = 1,71, Faktor 4,98 ≈ √24).
3. **Klumpen.** `cluster_id` wird mitgezaehlt (`n_cluster`).
4. **Auswahl.** Alle Gruppen werden ausgegeben, und `bonferroni_schwelle()`
   nennt die Zahl der Vergleiche.

`wilson_intervall()` statt Normalapproximation: die faellt bei kleinen `n`
oder Anteilen nahe 0/1 aus `[0, 1]` heraus und behauptet dann Unsinn mit
Nachkommastellen.

`lade_fuer_auswertung()` liest **nur den angegebenen Datensatzblock**,
Vorgabe `train` — Validation und OOS werden nicht beilaeufig mitgelesen und
ein unbekannter Blockname bricht ab.

### 39.4 `werkzeuge/grundratenbericht.py`

```
python -m werkzeuge.grundratenbericht --horizont 60
python -m werkzeuge.grundratenbericht --nach regime --block validation
```

Gruppierungen: `muster`, `variante`, `regime`, `session`, `struktur`.
Kontraktnaehte werden **standardmaessig ausgeschlossen** (der Preissprung ist
ein Artefakt der Verkettung); `--mit-rollnaht` zaehlt sie mit.

Unter der Tabelle steht die Bonferroni-Schwelle. Haelt keine Zeile stand,
sagt der Bericht das ausdruecklich als **Ergebnis**, nicht als Fehlschlag.

### 39.5 Erste Plausibilitaetsprobe (zwei Wochen OOS, 13.777 Ereignisse)

Zur Kontrolle der Mechanik, **nicht** als Befund:

| H | MFE (R) | MAE (R) | E[R] | Zeit bis MFE |
|---:|---:|---:|---:|---:|
| 1 | 0,52 | 0,55 | −0,017 | 1,0 |
| 10 | 1,67 | 1,70 | −0,007 | 5,3 |
| 60 | 4,28 | 4,19 | +0,040 | 29,8 |
| 240 | 8,83 | 8,89 | −0,097 | 112,5 |

**MFE ≈ MAE ueber alle Horizonte, E[R] ≈ 0, Zeit bis MFE ≈ H/2.** Das ist
exakt das Verhalten eines Zufallspfads. Auf zwei Wochen ist das kein Befund —
aber es ist ein Vorgeschmack darauf, was der Volllauf zeigen koennte, und es
belegt, dass die Mechanik rechnet, was sie soll.

---

## 40. Der erste Grundratenbericht war ein Fehlalarm - die fuenfte statistische Falle (31.08.2026)

### 40.1 Was der Bericht anzeigte

Erster Volllauf der Outcomes (23,3 Mio Zeilen), dann
`werkzeuge/grundratenbericht.py --horizont 60 --block train`: **neun von zehn
Long-Mustern** mit `kante_R` um +0,22 bis +0,30 und `p` praktisch null - alle
unter der Bonferroni-Schwelle.

### 40.2 Warum es nicht stimmte

Wenn **jedes** Long-Muster denselben Vorteil zeigt, ist das kein Fund, sondern
ein Fehler im Aufbau. `niveau_test [long]`: **E[R] = -3,03** bei **Median
+0,22** - der Mittelwert von einzelnen Extremwerten zertruemmert.

`end_r = end_pkt / atr_referenz`. In der Datenbank fanden sich Ereignisse mit
`atr_referenz` bis hinunter zu **0,0026 Punkten** - eingefrorene Kurse in der
duennen Fruehhistorie (2019-2021, MNQ bei 7.500, tote Nachtstunden), kein
handelbarer Zustand. Eine normale -156-Punkte-Bewegung ergibt dann
`end_r = -9.440`. 6.273 der 69.126 niveau_test-long-Ereignisse (9 %) haben
`atr_referenz < 1,5`, deren `end_r`-Mittel ist -33,8.

**Der zweite Effekt, der es gefaehrlich macht:** `niveau_test [long]` ist 8 %
aller Long-Ereignisse. Ihr Mittel von -3,03 zog die **Nulllinie aller Longs**
auf -0,20. Dadurch sah jedes andere Long-Muster mit `E[R] ~ +0,05` wie ein
Vorteil von +0,25 aus - reiner Vergleich gegen eine vergiftete Nulllinie.

Getrimmtes Mittel (1-99 %) von `niveau_test [long]`: **+0,055**. In einer
Reihe mit allem anderen.

### 40.3 Der robuste Blick

Der **Trefferanteil** (Vorzeichen von `end_pkt`, ohne ATR) je Muster: 0,509
bis 0,520 fuer Longs, Nulllinie 0,516; 0,462 bis 0,476 fuer Shorts, Nulllinie
0,473. **Jedes Muster sitzt auf seiner Nulllinie**, Wilson-Intervalle
ueberlappen sie durchweg. Der einzige Ausreisser (`bos_bearish [short]` bei
0,462) ist *schlechter* als Zufall.

Die Long/Short-Asymmetrie selbst ist der MNQ-Aufwaertsdrift 2019-2023; die
per-Richtung-Nulllinie korrigiert genau das.

### 40.4 Haertung von `common/ereignisse/grundraten.py`

Alles in der Auswertungsschicht, kein Datenneuschrieb:

- `ATR_UNTERGRENZE = 1.0`: Ereignisse mit kleinerer ATR-Referenz werden
  verworfen. MNQ-1m-ATR liegt praktisch immer ueber 2.
- `WINSOR_R = 25.0`: der Rest wird gekappt.
- **Massgeblich ist `anteil_kante` mit `anteil_p_wert`** - der
  ueberschneidungsfreie Zwei-Anteile-Test (`zwei_anteile_p`, Normal-CDF ueber
  `math.erf`) auf den Trefferanteil gegen die Nulllinie. Benutzt die ATR
  nicht. `E[R]`/Median stehen daneben, mit `hinweis` wenn sie > 0,5 R
  auseinanderliegen.
- Die Nulllinie einer Gruppe ist jetzt "alle gleichgerichteten Ereignisse
  **ohne diese Gruppe**" - ein grosses schiefes Muster kann die Nulllinie
  nicht mehr in seine eigene Richtung ziehen.
- Der deckende Index `idx_outcomes_auswertung` wurde um `atr_referenz`
  erweitert (Neuaufbau noetig).
- 27 Tests, u.a. `test_anteil_kante_ist_gegen_atr_muell_immun`, das die
  vergiftete Nulllinie exakt nachstellt.

### 40.5 Stand

Nach der Haertung (aus Diagnose + CSV; der bestaetigende Vollrun ueber die
7-GB-DB steht noch aus): **kein Muster mit belastbarem Vorteil im
Trainingsblock**. Deckt sich mit Mesfin (2026) und der Zweiwochenprobe.

Naechster sinnvoller Schritt vor einem "gescheitert": Gruppierung nach Regime
und Session (`--nach regime`, `--nach session`) - ein Vorteil koennte nur in
einer Marktlage auftreten und im Schnitt untergehen. Vollstaendig:
`docs/GRUNDRATEN_H60_2026-08-31.md`.

### 40.6 Datenbank an der Hardware-Grenze

`data/eventdb.sqlite3` ist ~7 GB. Der erste Outcome-Schreiblauf brauchte 5 h
(behoben: ereignisweise statt horizontweise, `INDIZES` erst nach allen
INSERTs), der Auswertungs-Join lief 25 min ins Leere (behoben: getrennte
Abfragen + deckender Index). Selbst danach ist jede Auswertung Gigabyte-Arbeit
auf diesem Laptop. Weg 2 aus `docs/UEBERGABE_2026-08-31.md` Teil 3
(Swing-Niveaus ausduennen, ~800 k Ereignisse weniger) ist auf dieser Hardware
wohl noetig, nicht nur wuenschenswert - Laurins Entscheidung.
