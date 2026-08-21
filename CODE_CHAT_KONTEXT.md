# CODE_CHAT_KONTEXT

**Technisches Langzeitgedächtnis des Projekts "Claude Chart Bot".**

Stand: 2026-08-21. Geprüft gegen den tatsächlichen Projektordner.

---

## 0. Zweck und Verhältnis zur Schwesterdatei

**Es gibt genau zwei Kontextdateien.** Beide gehören zusammen ins Claude-Projekt:

| Datei | Rolle | Ändert sich |
|---|---|---|
| **CODE_CHAT_KONTEXT.md** (diese) | **WIE und WIE WEIT**: Architektur, Module, Implementierungsstand, Bugs mit Fundstelle im Code, Tests, technische Entscheidungen, Blocker, nächste technische Schritte | bei Bauarbeiten |
| `NORMALER_CHAT_KONTEXT.md` | **WAS und WARUM**: Ziele, Anforderungen, Nutzerpräferenzen, Kostenrahmen, Kontostatus, Lucid-Regelwerk, Etappen A–F, Arbeitsteilung | selten |

Im Projektordner ergänzend, **nicht** zum Hochladen gedacht:
`CLAUDE.md` (wird von Claude Code automatisch geladen) und `README.md`
(veraltet, siehe W5).

**Bewusst nicht dupliziert:** Nutzerprofil, Kostenanforderung, Lucid-Regelwerk im
Wortlaut, Verwerfungsgründe für TradingView/Tradovate/yfinance auf Produktebene.
Das steht in `NORMALER_CHAT_KONTEXT.md`. Hier stehen nur deren **technische
Folgen**.

**Vorgängerdateien:** `PROJECT_CONTEXT.md` und `CURRENT_STATE.md` sind in diesen
beiden Dateien aufgegangen und aus dem Projektordner entfernt. Falls sie in einer
alten Projekt-Kopie noch auftauchen: veraltet, nicht verwenden.

---

## 1. AKTUELLER TECHNISCHER STAND

### Implementierungsstand nach Komponente

| Komponente | Stand | Getestet |
|---|---|---|
| `common/` (Indikatoren, Sessions, Level, Struktur, Muster, Instrumente, Config) | **fertig** | ja, umfangreich |
| `mcp_server/` (3 Tools, Snapshot, Kalender, CLI) | **fertig** | ja |
| `ntbridge/` (Empfänger + SQLite-Store) | **fertig** | ja, jetzt auch mit echten NT8-Live-Daten verifiziert (21.08.2026, siehe Abschnitt 9) |
| `ninjatrader/ClaudeBridge.cs` | **fertig, v1.0.1** | **in NT8 kompiliert und live verifiziert (21.08.2026)** |
| `backtest/` (Engine, Metriken, Splits, Strategien, CLI) | **fertig** | ja |
| `live_bot/` (Alarme, Claude-Kommentar, Telegram, `/analyse`) | **fertig, Legacy** | ja |
| Ideen-Protokollierung (Etappe C) | **existiert nicht** | — |
| Auswertung `evaluate_past_ideas` (Etappe D) | **existiert nicht** | — |
| Profil-Logik `demo`/`lucid` | **existiert nicht** | — |
| Lucid-Regelsimulation | **existiert nicht** | — |

**Testsuite: 326 Tests, alle grün.** Befehl:
`.venv\Scripts\python.exe -m pytest`

### Was funktioniert

- Der gesamte Rechenpfad von Kerzen zu Snapshot, verifiziert mit **synthetischen**
  Daten.
- Der Empfänger nimmt Bars an, validiert, speichert idempotent, liefert `/status`.
- Der MCP-Server erzeugt einen vollständigen Snapshot mit Provenienz.
- Backtest-Engine mit IS/OOS-Trennung und Lookahead-Schutz.
- **NEU (21.08.2026): Der komplette Live-Pfad NinjaTrader → `ClaudeBridge.cs` →
  `ntbridge`-Empfänger → SQLite läuft nachweislich mit echten MNQ-Marktdaten.**
  Siehe Abschnitt 9 für den vollständigen Verifikationslauf mit Zahlen.

### Was nicht funktioniert bzw. nie lief

- **Es wurde nie ein Backtest auf echten Marktdaten gerechnet** (siehe Abschnitt 9).
  Echte Daten liegen inzwischen in der produktiven Datenbank vor, ein Backtest
  darauf wurde aber noch nicht ausgeführt.

> **Korrektur gegenüber älteren Fassungen (21.08.2026):** Hier standen bis zu
> diesem Update zwei Punkte, die nicht mehr zutreffen: *"`ClaudeBridge.cs` wurde
> nie in NinjaTrader kompiliert"* und *"Es sind nie echte NT8-Marktdaten im
> System angekommen"*. Beides ist überholt — siehe Abschnitt 9.

### Bekannte Probleme

1. **`ClaudeBridge.cs` wurde in dieser Session zweimal von außen zerstört**
   (Details Abschnitt 8.1). Wiederhergestellt, aber es gibt **keine
   Versionskontrolle** als Netz.
2. **Das Projekt ist kein Git-Repository** (`git rev-parse` schlägt fehl). Git for
   Windows ist installiert, das Projekt nur nicht initialisiert.
   **NICHT BEKANNT**, ob das Absicht ist.
3. **Startreihenfolge ist heikel:** Läuft der Empfänger beim Chartstart nicht,
   gehen von 3000 historischen Kerzen 2800 verloren (Retry-Puffer deckelt bei
   200, verwirft die ältesten). Abhilfe: Chart-F5 nach Empfängerstart.
   **Praktisch entschärft (21.08.2026):** Der Retry-Puffer hat im realen Test
   auch nach mehreren Minuten ohne laufenden Empfänger alle zwischengespeicherten
   Kerzen beim Verbindungsaufbau nachgeliefert (0 Kerzen verloren, siehe
   Abschnitt 9). Das Risiko besteht trotzdem bei sehr langen Ausfallzeiten
   (Puffer deckelt bei 200) — Abhilfe bleibt gültig.

### Offene technische Aufgaben

1. Etappe C: regelbasierte Ideen-Protokollierung.
2. Etappe D: `evaluate_past_ideas`, `get_performance_report`.
3. Profil-Logik `demo`/`lucid` + Lucid-Regelsimulation.
4. Etappe E: Dauerbetrieb-Härtung.
5. README auf den NinjaTrader-Stand bringen (beschreibt noch den Tradovate-Pfad).
6. Erster Backtest auf den jetzt vorhandenen echten Marktdaten (informativ, keine
   Grundlage für Strategieentscheidungen, bis genug Historie/Sessions vorliegen).

> **Korrektur gegenüber älteren Fassungen (21.08.2026):** Die früheren Punkte 1
> ("`ClaudeBridge.cs` in NT8 kompilieren") und 2 ("Zwei Charts je Instrument
> einrichten, Ende-zu-Ende mit echten Daten verifizieren") sind erledigt und
> entfallen. Die Liste wurde entsprechend neu nummeriert.

### Relevante Unsicherheiten

- **NICHT BEKANNT**, ob MNQ und MGC zwei getrennte CME-Datenpakete erfordern
  (CME Index vs. COMEX Metals).

> **Korrektur gegenüber älteren Fassungen (21.08.2026):** Zwei frühere
> Unsicherheiten sind durch den realen Kompilier- und Live-Test geklärt:
> - `System.Net.Http` ist auf diesem Rechner ohne manuelle Referenz verfügbar —
>   der Compile-Lauf in NT8 war fehlerfrei.
> - Die NT8-Anzeigezeitzone weicht **nicht** von der Windows-Zeitzone ab.
>   Gemeldete Zeitzone `W. Europe Standard Time` entspricht Europe/Berlin: die
>   UTC-Zeitstempel in der Datenbank stimmten beim Test auf wenige Minuten genau
>   mit der tatsächlichen Uhrzeit überein, kein Versatz. Kein Nacharbeiten am
>   Zeitzonen-Parameter nötig.

---

## 2. Gesamtarchitektur und Datenfluss

### Zielarchitektur (aktiv)

```
NinjaTrader 8 Chart
  └─ ClaudeBridge.cs   Indikator, KEINE Strategy
     │                 AddDataSeries → mehrere Timeframes aus EINER Instanz
     │                 fire-and-forget, Timeout, Retry-Puffer
     └─ HTTP POST {"bars":[...]} → 127.0.0.1:8787/bars
        └─ ntbridge/receiver.py    ThreadingHTTPServer, nur localhost
           └─ ntbridge/store.py    SQLite WAL, idempotent
              └─ mcp_server/bars.py :: NTBridgeBarSource
                 └─ mcp_server/snapshot.py
                    └─ mcp_server/server.py   3 MCP-Tools
                       └─ Claude Desktop   ← Interpretation NUR hier
```

**Zwei Prozesse, geteilte Datei:** Der Empfänger schreibt, der MCP-Server liest —
deshalb **SQLite im WAL-Modus** (ein Schreiber, mehrere Leser über
Prozessgrenzen).

### Legacy-Pfad (lauffähig, nicht Ziel)

```
Tradovate WebSocket → live_bot/market/ → Alarme → Anthropic API → Telegram
```

Dieser Pfad **ruft die Anthropic-API auf und kostet Token**. Er bleibt bestehen,
ist aber nicht das Zielsystem.

### Harte Trennlinie

**`mcp_server/` darf niemals die Anthropic-API aufrufen.** Erzwungen durch
`tests/test_mcp_snapshot.py::test_mcp_modul_ruft_keine_anthropic_api` — ein
**AST-basierter Test**, der jedes Modul unter `mcp_server/` prüft.

---

## 3. Modul-Referenz

### `common/` — geteilte Rechenlogik

| Datei | Inhalt |
|---|---|
| `indicators.py` | **Zentrale Invariante.** `compute_indicators` ist der Hot Path, liefert `rsi, atr, vwap, sma_fast, sma_slow`. Daneben `compute_extended_indicators` mit `macd`, `stochastic`, `adx` (+DI/−DI), `bollinger`, `ema_stack`, `session_cumulative_delta`. `validate_ohlcv` erzwingt das Schema. |
| `sessions.py` | CME-Session-Modell, 18:00-ET-Rollover, Tageswechsel **auf dem Datum** gerechnet |
| `instruments.py` | Instrument-Register mit Ticksize, Punktwert, Handelszeiten, **`expiry_rule`** |
| `levels.py` | `compute_levels()` (PDH/PDL/PDC, Overnight, IB, Opening Ranges, Gap, Cash Open), `history_dependent_metrics()`, `overnight_mask()`, `volume_profile()` |
| `structure.py` | `find_swing_points`, `support_resistance_zones`, `assess_trend`, `classify_market_structure` (BOS/CHoCH), `detect_rsi_divergence` |
| `patterns.py` | `detect_flag`, `detect_triangle`, `detect_double_top_bottom`, `detect_range_compression`, `detect_candle_patterns_at_levels`, `detect_all_patterns` |
| `config.py` | `Config.validate()` mit Startprüfungen, die **abbrechen** |
| `logging_setup.py` | `log_event` mit positions-only Parametern |

**Schema überall:** `pd.DatetimeIndex` in UTC, aufsteigend, Spalten
`open, high, low, close, volume`.

**Warum `structure.py` außerhalb von `compute_indicators` liegt:** Es läuft nur
punktuell beim `/analyse`-Bericht, nicht bei jeder Backtest-Kerze. Die Trennung ist
eine Performance-Entscheidung, keine Zufälligkeit.

### `ntbridge/` — Etappe B

| Datei | Inhalt |
|---|---|
| `receiver.py` | `ThreadingHTTPServer`, **nur an 127.0.0.1 gebunden**. `POST /bars`, `GET /status`. `ReceiverState` zählt requests/accepted/rejected/reasons/last_bar_at. Erwartet Umschlag `{"bars": [...]}`. |
| `store.py` | SQLite. Schlüssel `(instrument, timeframe, ts_utc)`, `ON CONFLICT DO UPDATE`, WAL. Methoden `upsert`, `ingest`, `load_frame`, `latest_timestamp`, `nt_instrument`, `coverage`, `total_bars`. **Keine Bid-/Ask-Spalten.** |
| `__main__.py` | Startprüfung, **weist Nicht-localhost-Hosts ab**; gibt DB-Pfad, Kerzenzahl, Abdeckungstabelle aus |

**`validate_bar()` Ablehnungsgründe** (jeder benannt, nie stumm):
`instrument_fehlt`, `timeframe_unbekannt`, `zeitstempel_unlesbar`,
`zeitstempel_in_zukunft` (5 min Toleranz — **die Meldung nennt ausdrücklich den
ClaudeBridge-Zeitzonenparameter**), `preis_ungueltig`, `volumen_ungueltig`,
`high_kleiner_low`, `ohlc_widerspruechlich`.

**Beobachtung aus dem Live-Test (21.08.2026):** `/status` meldet ein Feld
`laeuft_seit_utc`, das nach einem frischen Prozessstart trotzdem ein altes Datum
(30.07./31.07.) zeigte statt der tatsächlichen Startzeit. Da beim Neustart kein
"Port bereits belegt"-Fehler auftrat, lief kein zweiter Prozess im Hintergrund
weiter — das Feld liest vermutlich einen in der SQLite-Datenbank persistierten
Erst-Start-Zeitpunkt statt der echten Prozesslaufzeit. Funktional unkritisch,
aber bei Gelegenheit im Code (`ReceiverState`/`store.py`) prüfen, ob das Feld
umbenannt oder korrigiert werden sollte, damit es nicht als "Prozess läuft seit"
missverstanden wird.

### `mcp_server/`

| Datei | Inhalt |
|---|---|
| `server.py` | Registriert **3 Tools**: `get_market_snapshot`, `get_event_risk`, `list_instruments` |
| `snapshot.py` | `build_snapshot_payload()` → Blöcke `meta`, `instrument`, `session`, `datenherkunft`, `levels`, `historienabhaengig`, `timeframes`. `_choose_level_frame()` wählt den feinsten TF, der zwei Sessions abdeckt; `_choose_history_frame()` den Intraday-TF mit den meisten Sessions |
| `bars.py` | `BarSet` (mit `timeframe_minutes`, Tageskerze = 23*60, und `is_stale(now, factor=2.0)`), `NTBridgeBarSource`, `BarStoreProtocol` |
| `calendar_provider.py` | Forex Factory (Termine) + FRED (Ist-Werte) |
| `context.py` | **Langlebiger Zustand.** Der Server läuft als Dauerprozess unter Claude Desktop; Login und Kontraktauflösung passieren **einmal beim Aufbau**, nicht je Werkzeugaufruf |
| `cli.py` | Kommandos `snapshot` und `levels`; Optionen `--symbol`, `--timeframes` (Standard `1m,5m,15m`), `--bars`, `--no-bars`, `--json`, `--config`, `--env-file` |

> **Doku-Drift in `context.py`:** Der Modul-Docstring begründet das Zwischenhalten
> noch mit **Tradovate**-Login-Drosselung und REST-Roundtrips, obwohl das Modul
> inzwischen `NTBridgeBarSource` importiert. Die Entscheidung (Zustand einmal
> aufbauen) bleibt richtig, die Begründung ist veraltet. Kosmetisch, aber beim
> nächsten Anfassen mitziehen.

**Die ursprünglich geplanten Tools 4/5** (Ideen protokollieren / auswerten) sind
**nicht gebaut** — das ist Etappe C/D.

**`BarStoreProtocol` existiert aus einem bestimmten Grund:** Es hält `bars.py`
frei von `ntbridge`-Importen. Sonst hinge der MCP-Server an der Speicher-
Implementierung.

### `backtest/`

`engine.py`, `metrics.py`, `splits.py`, `compare.py`, `cli.py`,
`data/{base,csv_provider,tradovate_provider}.py`,
`strategies/{base,library}.py`.

**Strategien in `library.py::STRATEGY_LIBRARY`:** `prev_day_breakout`,
`rsi_mean_reversion`, `flag_breakout`, `vwap_trend`.

**Ausführungsmodell (nicht verhandelbar):**
- Regeln werden auf dem **Schlusskurs** ausgewertet, ausgeführt wird zur
  **Eröffnung der Folgekerze**. Lookahead damit strukturell ausgeschlossen.
- Stop und Ziel greifen intrabar über High/Low. **Bei beidem in derselben Kerze
  gilt der Stop** — aus OHLC ist nicht rekonstruierbar, was zuerst kam.
- Immer höchstens eine Position; Zwangsschluss am Sessionende.
- Kosten über `CostModel` mit echtem Punktwert und Ticksize. **P&L ist USD, keine
  Punktzahl.**

`BarContext` gibt bewusst **nur die aktuelle und die vorherige Zeile** frei.

### `live_bot/` — Legacy-Alarmpfad (lauffähig, nicht Ziel)

| Datei | Inhalt |
|---|---|
| `main.py` | Einstiegspunkt + CLI; `LiveBot.run` startet `feed`, `candle-ticker`, optional `telegram-commands` |
| `market/state.py` | `MarketState` — Kerzenpuffer + Indikatoren als Momentaufnahme, neu berechnet bei jeder abgeschlossenen Kerze **mit exakt derselben Funktion wie der Backtest** |
| `market/feed.py` | Reconnect mit Backoff, Neu-Abonnieren, Historien-Nachladen nach Ausfall (schließt die Datenlücke) |
| `market/candles.py` | Kerzenaggregation |
| `alerts/conditions.py` | `ConditionEvaluator._checks`. **Alle Bedingungen sind Flankenerkennungen** — Vergleich vorheriger/aktueller Snapshot, keine Zustandsabfragen |
| `alerts/cooldown.py` | Zwei Bremsen: Cooldown je Bedingungstyp und globale Rate-Begrenzung |
| `ai/claude_client.py` | `ClaudeCommentator.comment` / `.report`, beide über `_create()` |
| `notify/notifier.py` | `Notifier.send` mit Fallback auf Konsole+Log; `send_long` teilt an Absatzgrenzen (Telegram-Limit 4096 Zeichen) |
| `on_demand_report.py` | `/analyse`-Bericht |
| `tradovate/` | `auth.py`, `rest.py`, `md_socket.py`, `contracts.py` — Altlast |

**Dieser Pfad ruft die Anthropic-API auf und kostet Token.** Er ist bewusst
erhalten, aber nicht das Zielsystem.

### `ninjatrader/ClaudeBridge.cs`

**750 Zeilen, Version 1.0.1, ASCII.** Indikator, keine Strategy.

**Quelle der Wahrheit ist die Repo-Fassung**; die Kopie unter
`C:\Users\lm130\Documents\NinjaTrader 8\bin\Custom\Indicators\ClaudeBridge.cs`
wird daraus erzeugt. Beide aktuell byte-identisch.

**Historien-Skalierung** (`HistoricalBarsFor`, Basis 3000 für 1m):
1m→3000, 5m→600, 15m→250, 1h→250, 1d→250. Untergrenze 250 deckt EMA200 und die
Swing-Erkennung ab. Tageskerze wird mit 23*60 Minuten angesetzt, **nicht 24 h**.

**Payload je Kerze:** `instrument, ntInstrument, timeframe, timestampUtc,
timestampLocal, timeZoneId, open, high, low, close, volume, bidVolume:null,
askVolume:null, source, bridgeVersion`. Umschlag **immer** `{"bars":[...]}`.

**Live-Verifikation (21.08.2026):** In NT8 kompiliert (Reiter *Errors* leer),
auf zwei Charts angewandt — 1m-Chart (Zusatz-TFs `5,15`, Session Template
`CME US Index Futures ETH`) und Day-1-Chart (Zusatz-TF `60`). Output-Fenster
zeigte korrekt `ClaudeBridge 1.0.1 bereit` mit den erwarteten Serien und
Zielwerten. Ohne laufenden Empfänger griff der Timeout (1500 ms) und die
Zwischenspeicherung sauber; nach Start des Empfängers lieferte der Retry-Puffer
alle zwischengespeicherten Kerzen automatisch nach — 5669 angenommen, 0
abgelehnt. Details siehe Abschnitt 9.

---

## 4. Konfiguration

`config.yaml` — Abschnitte: `tradovate`, `market`, `indicators`, `alerts`,
`claude`, `on_demand`, **`ntbridge`**, `event_risk`, `notify`, `logging`,
`backtest`.

`ntbridge`-Abschnitt: `enabled`, `host` (127.0.0.1), `port` (8787), `database`
(`data/ntbridge.sqlite3`), `stale_factor` (2.0), `symbol_map` (leer).

**Vorrang:** CLI > `.env` > YAML.
**Schwellenwerte ausschließlich in `config.yaml`, Secrets ausschließlich in `.env`.**

### Namensfalle (wichtig)

`config.yaml` Zeile 14 enthält `environment: demo` **unter `tradovate:`**. Das ist
die **Tradovate-Umgebung (demo/live)** und hat **nichts** mit dem geplanten Profil
`demo`/`lucid` zu tun. Beim Bau der Profil-Logik einen anderen Schlüsselnamen
wählen, sonst entsteht genau die Verwechslung, die dieses Projekt vermeiden will.

### `Config.validate()` — Startprüfungen, die abbrechen

1. **Instrument-Registry-Konsistenz** (`tick_size`/`point_value` gegen das
   Register) — fängt "Produkt MNQ mit NQ-Werten" ab.
2. **Zwei-Sessions-Pufferbedingung**, wenn Vortages-Alarme aktiv sind.
3. **Swing-Lookback ≥ 2*strength+1.**

**Diese Prüfungen nicht abschwächen** — sie existieren wegen konkreter stiller
Ausfälle (Abschnitt 8).

### Live-Schutz

Doppelt gesichert: `allow_live_environment: true` in der `config.yaml` **und**
`--i-know-this-is-live` beim Start. Beide Riegel beibehalten.

---

## 5. Technische Entscheidungen mit Begründung

### 5.1 Eine einzige Indikator-Implementierung

`common/indicators.py::compute_indicators` wird von **beiden** Seiten aufgerufen —
Live-Bot (`MarketState._recompute`) und Backtest (`Backtester.prepare`).

**Grund:** Eine zweite Rechenlogik hieße, dass der Backtest eine andere Strategie
testet als die, die live läuft. **Niemals eine zweite einführen.**

### 5.2 Eigene Backtest-Engine statt `backtesting.py` / `vectorbt`

Begründet in `docs/BACKTESTING_ENTSCHEIDUNG.md`. **Diese Datei lesen, bevor eine
der beiden Bibliotheken vorgeschlagen wird.**

### 5.3 Python-stdlib-HTTP statt FastAPI für den Empfänger

Begründung steht im Modul-Docstring von `receiver.py`. Kurz: eine Abhängigkeit
weniger für einen Server, der genau zwei Endpunkte hat und nur an localhost
lauscht.

### 5.4 SQLite im WAL-Modus

Zwei Prozesse (Empfänger schreibt, MCP-Server liest) brauchen gleichzeitigen
Zugriff. WAL erlaubt einen Schreiber plus mehrere Leser.

**Der SQLite-Speicher IST der ursprünglich verschobene Bar-Cache.** Er wurde
bewusst nicht doppelt gebaut.

### 5.5 Indikator statt NinjaScript-Strategy

Ein Indikator **kann** in NinjaTrader keine Orders platzieren. Damit ist die
Order-Sperre (siehe `NORMALER_CHAT_KONTEXT.md` Abschnitt 7) nicht nur eine Vereinbarung,
sondern **in der Architektur verankert**.

### 5.6 `AddDataSeries` statt mehrerer Chart-Instanzen

Eine Indikator-Instanz auf einem 1m-Chart liefert zusätzlich 5m und 15m.

**Erzwungene Konsequenz:** Sekundärserien **erben den Ladezeitraum des Charts**
("Days to load"). Ein 1m-Chart mit 7 Tagen gäbe einer Tagesserie nur 7
Tageskerzen. Daraus folgt zwingend das **Zwei-Charts-pro-Instrument-Layout**:

| Chart | Periode | Days to load | Zusatz-TFs | Tagesserie |
|---|---|---|---|---|
| Intraday | Minute, 1 | 7 | `5,15` | aus |
| Tagesebene | Day, 1 | 400 | `60` | aus |

**Live eingerichtet und verifiziert (21.08.2026):** Beide Charts wie oben
angelegt, beide senden korrekt (siehe Abschnitt 9).

### 5.7 `BarsPeriodType.Day` statt 1440 Minuten

**Ausdrückliche Nutzerkorrektur (Zitat):** *"1440 MINUTEN IST KEIN TAGESCHART.
BarsPeriodType.Minute mit 1440 richtet sich nicht nach der Session-Definition des
Kontrakts."*

`Minute` mit 1440 zählt 1440 Minuten Uhrzeit ab einem beliebigen Anker; die
Tagesserie folgt der Trading-Hours-Vorlage (Globex 18:00–17:00 ET). Die beiden
liegen um **Stunden** auseinander. Da PDH/PDL/PDC genau aus dieser
Session-Abgrenzung entstehen, wäre die Minutenvariante **lautlos falsch**.

`TimeframeLabel()` gibt für `Minute/1440` **explizit `null` zurück**, und
`ParseTimeframeList()` lehnt 1440 aktiv ab **mit Log-Meldung** — nicht stumm.

### 5.8 Kein Delta-Pfad auf der Empfängerseite

**Ausdrückliche Nutzerentscheidung (Zitat):** *"nein, nicht lizenziert. Delta
bleibt dauerhaft null, die Nachrüststelle im Code kann bleiben, aber die
Empfängerseite bitte ohne Delta-Pfad bauen."*

Folge: `store.py` hat **keine Bid-/Ask-Spalten**. Die Bridge sendet
`bidVolume:null, askVolume:null`. Die Nachrüststelle ist in `ClaudeBridge.cs`
markiert.

**Es wird bewusst nicht geschätzt** — eine Schätzung aus Auf-/Abwärtskerzen sähe
aus wie eine Messung und wäre keine.

### 5.9 `log_event` mit positions-only Parametern

`log_event(logger, event, message, /, *, level=…, **payload)`

Der `/` ist Absicht: sonst kollidiert ein Payload-Feld namens `message` mit dem
Positionsparameter und wirft zur Laufzeit einen `TypeError` — **ausgerechnet im
Fehlerpfad**. Payload-Schlüssel dürfen deshalb beliebig heißen.

Zwei Senken parallel: `logs/*.log` (lesbar) und `logs/*.jsonl` (eine JSON-Zeile
pro Event). Neue Ereignisse immer über `log_event`, Event-Name im Schema
`bereich.aktion`.

### 5.10 Async-Aufbau des Live-Bots (Legacy, aber gültig)

`LiveBot.run` startet drei Tasks: `feed`, `candle-ticker` (schließt Kerzen auch
ohne Ticks), optional `telegram-commands`. `self._lock` serialisiert alles, was den
`MarketState` anfasst.

**`_live_state_snapshot` kopiert den Puffer unter dem Lock und gibt ihn frei,
bevor der mehrere Sekunden dauernde Claude-Aufruf startet.** Neue lange
Operationen niemals unter dem Lock laufen lassen.

---

## 6. Verworfene technische Ansätze

> Produktseitige Verwerfungen (TradingView, Tradovate, yfinance) stehen mit voller
> Begründung in `NORMALER_CHAT_KONTEXT.md` Abschnitt 5. Hier nur die **technischen**
> Verwerfungen und ihre Codefolgen.

| Verworfen | Grund | Codefolge |
|---|---|---|
| **Tradovate `md/getChart` als Datenquelle des `mcp_server`** | Live-Konto ≥1000 USD + kostenpflichtiges API-Add-on | **Der Großteil des `mcp_server` war bereits darauf gebaut.** Umbau auf `NTBridgeBarSource` mit **identischem `load()`-Protokoll**, `snapshot.py` blieb strukturell unverändert |
| **`sys.stdout = sys.stderr` zum Schutz des MCP-Kanals** | Der stdio-Transport löst stdout bereits auf fd-Ebene (`os.dup(2)`) und prüft `stream.buffer.fileno() == 1` — die Zuweisung hätte den Kanal **zerstört statt geschützt** | Nicht implementiert. **Ein AST-Test verbietet die Zuweisung** |
| **Squeeze über "Bandbreite im untersten Perzentil"** | selbstbezüglich (Abschnitt 8.4) | Ersetzt durch **Keltner-Containment** |
| **Range-Kompression 20 gegen 60 Bars** | Skalierungsfehler (Abschnitt 8.5) | Ersetzt durch gleich lange Fenster gegen den Median rollierender gleich langer Fenster |
| **`cache_dependent_placeholders()`** | zu unspezifisch | Ersetzt durch `history_dependent_metrics()` mit `SESSIONS_REQUIRED` und Feld-genauer Begründung |
| **Kalendersortierung im Provider** | Providerwechsel hätte "nächster Termin" still gebrochen | Verschoben nach `CalendarService._relevant()` |
| **`backtesting.py` / `vectorbt`** | siehe `docs/BACKTESTING_ENTSCHEIDUNG.md` | eigene Engine |
| **Getrennte Ideen-Logs pro Profil** | Vergleich zwischen Regelwerken wäre unmöglich | **Geplant:** eine gemeinsame DB mit Profilfeld |

**Diese Ansätze nicht erneut implementieren.** Nur neue relevante Information
rechtfertigt eine Neubewertung.

---

## 7. Wichtige Implementierungsdetails, die man dem Code nicht ansieht

### 7.1 NinjaScript-Fallen (teuer erlernt)

- **`AddDataSeries` darf ausschließlich in `State.Configure` aufgerufen werden.**
- **`HttpClient` als `static readonly`**, sonst laufen die TCP-Ports über
  `TIME_WAIT` nach einigen Stunden voll (eine Kerze/Minute × 5 Timeframes).
- **`HttpClient.Timeout` lässt sich nach dem ersten Request nicht mehr ändern** →
  das nutzerkonfigurierbare Timeout je Anfrage über **`CancellationTokenSource`**.
- **Niemals auf das Ergebnis des HTTP-Aufrufs warten** (`.Result`/`.Wait()`):
  NinjaScript-Methoden laufen auf dem Berechnungs-Thread, die Chartberechnung
  stünde still. Im NinjaTrader-Forum als Ursache eingefrorener Oberflächen
  dokumentiert. **Fire-and-forget mit `Task.Run`**, und **jede** Ausnahme innen
  abfangen — eine entkommene Ausnahme könnte NinjaTrader beenden.
- **`CultureInfo.InvariantCulture` bei jeder Zahl.** Auf deutschem Windows liefert
  `ToString()` `21345,25` **mit Komma** — kein gültiges JSON, der Empfänger würde
  **jede** Kerze ablehnen.
- **`IsSuspendedWhileInactive = false`**, sonst pausiert der Indikator, sobald der
  Chart-Tab nicht im Vordergrund ist → Datenlücken beim Tabwechsel.
- **Session Template ist die kritischste Chart-Einstellung.** Mit **RTH** statt
  **ETH** kämen Vortagesmarken nur aus 08:30–15:15 CT statt aus dem vollen
  Globex-Tag, den `common/sessions.py` unterstellt. **Kein Fehler, keine Warnung —
  nur andere Zahlen.** MNQ → `CME US Index Futures ETH`, MGC → `COMEX Metals ETH`.

**Alle diese Punkte im Live-Test (21.08.2026) implizit bestätigt:** fehlerfreie
Kompilierung, `InvariantCulture` korrekt (0 Ablehnungen wegen Kommazahlen),
Timeout-Handling griff sauber, kein UI-Einfrieren, `IsSuspendedWhileInactive`
kompilierte ohne Probleme.

### 7.2 Der Empfänger-Vertrag ist Teil der Bridge

Die C#-Seite hat **keinen Compiler, der diesen Vertrag absichert**. Bei jeder
Änderung an `ClaudeBridge.cs` gegen `ntbridge/store.py` (Feldnamen,
`validate_bar`) und `ntbridge/receiver.py` (Umschlag) prüfen.

Konkret: Feld heißt **`timestampUtc`**, nicht `ts_utc`. Umschlag ist
**`{"bars":[...]}`**, nicht ein nacktes Array.

### 7.3 CME-Session-Modell

Globex Sonntag 17:00 CT → Freitag 16:00 CT, tägliche Wartungspause 16:00–17:00 CT.
Eine Session = **23 Stunden = 1380 1-Minuten-Kerzen**. Der Handelstag rollt um
**18:00 ET**: ein Tick um 19:30 ET am Montag gehört zum Handelstag **Dienstag**.

Für Vortagesmarken braucht es **zwei Sessions = 2760 Kerzen**
(`MarketConfig.bars_for_previous_session`).

### 7.4 Kontraktspezifika

| | MNQ | MGC |
|---|---|---|
| Ticksize | 0,25 Punkte | 0,10 USD/oz |
| Punktwert | 2 USD | 10 USD (10 oz) |
| Kontraktmonate | H/M/U/Z | **G/J/M/Q/V/Z** |
| Verfall | 3. Freitag | **drittletzter Geschäftstag des Liefermonats** |

Im Register auch NQ (20 USD/Punkt) und ES (50 USD/Punkt).

### 7.5 Anthropic-Details (nur Legacy-Pfad)

- Modell **`claude-sonnet-5`** (Nutzerwunsch).
- **Sampling-Parameter wie `temperature` sind auf diesem Modell nicht erlaubt (400).**
- **`max_tokens` deckelt Denk- und Antworttokens zusammen**, weil adaptives Denken
  standardmäßig an ist.
- `ClaudeCommentator.comment` (Alarm) und `.report` (`/analyse`) unterscheiden sich
  nur in System-Prompt, `max_tokens` und `effort`; beide laufen durch `_create()`
  mit derselben Fehler-, Refusal- und Truncation-Behandlung.
- `build_metrics_payload` und `build_report_payload` sind die **einzigen** Stellen,
  an denen Daten das Haus verlassen — nur berechnete Kennzahlen, keine Rohdaten,
  keine Kerzenlisten, keine Bilder. Tests prüfen die Schlüsselmenge.
- Beide System-Prompts verbieten direkte Handelsempfehlungen und verlangen einen
  Disclaimer; fehlt er, ergänzt ihn `_create`. Tests sichern das einzeln ab.

### 7.6 Tradovate-Market-Data-Protokoll (Legacy)

Textbasiert, SockJS-ähnlich (`live_bot/tradovate/md_socket.py`): Frames mit Präfix
`o`/`h`/`a`/`c`, Requests als `<endpoint>\n<id>\n<query>\n<body>`,
**Client-Heartbeat `[]` alle ~2,5 s (Pflicht)**. `MarketDataSocket` kapselt genau
**eine** Verbindung; Reconnect mit Backoff und Historien-Nachladen liegen eine
Ebene höher in `market/feed.py`.

---

## 8. Bugs und Fehlerlehren

> Die ausführliche narrative Fassung der neun Lehren steht in
> `NORMALER_CHAT_KONTEXT.md` Abschnitt 12. Hier die **technische** Fassung: wo der
> Schutz im Code sitzt.

Alle Fehler dieser Klasse haben dieselbe Signatur: **sie sehen aus wie "kein
Signal", sind aber "Messung kaputt".**

| # | Fehler | Schutz im Code |
|---|---|---|
| 1 | `candle_buffer_size: 500` bei 23-h-Session → `prev_session_high` dauerhaft NaN, zwei Alarme hätten **nie** ausgelöst, ohne Fehlermeldung | Defaults 3000/2880 + **`Config.validate()` bricht ab** |
| 2 | OOS-Block isoliert vorbereitet → erste ~50 Kerzen ohne SMA50, Strategie stumm | `compare.prepare_split()` rechnet über die Gesamthistorie, schneidet danach; `splits.assert_in_sample_only` wirft `OutOfSampleViolation` |
| 3 | Tagesaddition auf dem Zeitstempel statt auf dem Datum; ATR-Perzentil auf UTC-Minute | `common/sessions.py` rechnet auf dem **Datum**; Fenster in börsenlokaler Zeit |
| 4 | Squeeze über "unterstes Perzentil der letzten N Kerzen" — wird zur eigenen Referenz, verschwindet bei größter Kompression | **Keltner-Containment** |
| 5 | Range-Kompression 20 vs. 60 Bars: √(20/60)≈0,58 < Schwelle 0,6 → hätte auf **jedem** Kursverlauf gefeuert | gleich lange Fenster gegen Median rollierender gleich langer Fenster |
| 6 | Kalender nicht erreichbar hätte "keine Termine" bedeutet — also eine **Freigabe zum Handeln** | `calendar_available: false` mit Begründung |
| 7 | Terminsortierung lag beim Provider | Sortierung in `CalendarService._relevant()` |
| 8 | `FastMCP` heißt in mcp 2.0 **`MCPServer`**; `sys.stdout = sys.stderr` hätte den stdio-Kanal zerstört | **AST-Test** verbietet die Zuweisung |
| 9 | `contracts.py` nahm 3. Freitag auch für MGC an — **MNQZ5 19.12., MGCZ5 29.12., zehn Tage Unterschied** | `expiry_rule` im Instrument-Register |

**Zusätzlich (Lehre 10, neu 2026-08-20):** Der Empfänger-Vertrag ist Teil der
Bridge (Abschnitt 7.2).

### 8.1 Zwei Zerstörungsvorfälle an `ClaudeBridge.cs`

Beide in dieser Session, beide von außerhalb dieses Projekts:

**Vorfall 1 — Fremdwerkzeug schrieb die Datei auf 204 Zeilen neu.** Sechs vom
Nutzer benannte Regressionen: fehlende `InvariantCulture`, leeres `catch { }`,
kein Timeout, fehlendes `IsSuspendedWhileInactive`, `AddDataSeries` komplett
entfernt, `ToUniversalTime()` statt UTC+lokal+Zeitzonen-ID.

**Zwei weitere, vom Nutzer nicht bemerkte Brüche:** Feldname `ts_utc` statt
`timestampUtc`, und nacktes Array statt Umschlag `{"bars":[...]}`. Diese beiden
allein hätten bewirkt, dass **jede einzelne Kerze abgelehnt** worden wäre —
historisch wie in Echtzeit.

**Vorfall 2 — Browser speicherte eine Gemini-Webseite** (3,2 MB HTML plus Ordner
`ClaudeBridge_files`) unter genau diesem Dateinamen.

**Beide Male aus `ninjatrader/ClaudeBridge.cs` wiederhergestellt.**

**Daraus die Betriebsregel:** Die Repo-Fassung ist die Quelle der Wahrheit. Die
Versionsnummer im NinjaScript-Output (**aktuell 1.0.1**, vorher 1.0.0) ist der
einzige verlässliche Nachweis, welche Fassung wirklich läuft. Die Anhebung auf
1.0.1 geschah genau deswegen. **Bestätigt im Live-Test (21.08.2026):** Der
Output zeigte durchgehend `ClaudeBridge 1.0.1 bereit` — die richtige Fassung
lief.

### 8.2 Fehler in selbst erzeugten Testdaten (wichtig für die Zukunft)

In früheren Sessions waren **mehrere Testfehlschläge auf fehlerhafte Testdaten
zurückzuführen, nicht auf fehlerhaften Produktivcode**. Sie wurden korrigiert,
statt die Assertions abzuschwächen:

- **Zigzag stieg je Schritt mehr, als er zurücksetzte** → keine bestätigten Swings.
- **Degenerierter ADX-Sägezahn** (identische Highs/Lows) → ADX 100.
- **Prämisse "EMA-Stack ist in Rauschen selten" war falsch** — tatsächlich waren
  58 % der Bars gestapelt. Der EMA-Stack ist ein **Form-**, kein Stärkesignal.
- **Session-Grenzen in VWAP-Tests waren falsch ausgerichtet.**

**Regel:** Schlägt ein Test fehl, zuerst prüfen, ob die **Testdaten** die
Bedingung überhaupt erfüllen können. Assertions nicht abschwächen, um grün zu
werden.

### 8.3 Weitere behobene Einzelfehler

- **`or` auf einem DataFrame** in `snapshot.py` → `ValueError: truth value
  ambiguous`. Behoben mit explizitem `is None`-Test.
- **`week_high` meldete "1/5 Sessions"** trotz 250 Tageskerzen im Speicher — es
  wurde aus dem 1m-Frame gerechnet. Behoben über `_choose_history_frame()` und
  einen `daily_frame`-Parameter.
- **Forex Factory hat kein `actual`-Feld** — gegen den Live-Feed verifiziert.
  Führte zur Aufteilung FF (Termine) + FRED (Ist-Werte).

---

## 9. Tests und Backtests

### Testsuite

**326 Tests, alle grün.** Verteilung:

| Datei | Tests |
|---|---|
| `test_mcp_snapshot.py` | 43 |
| `test_on_demand.py` | 35 |
| `test_levels_structure.py` | 34 |
| `test_ntbridge.py` | 34 |
| `test_live_bot.py` | 29 |
| `test_instruments_sessions.py` | 26 |
| `test_event_risk.py` | 22 |
| `test_patterns.py` | 22 |
| `test_extended_indicators.py` | 21 |
| `test_structure.py` | 17 |
| `test_indicators.py` | 15 |
| `test_metrics_and_splits.py` | 15 |
| `test_engine.py` | 13 |

**Entwicklung über die Sessions:** 124 → 171 → 199 → 221 → 260 → 286 → 292 → 326.

**Besondere Tests, die Zusagen absichern (nicht entfernen):**
- `test_mcp_modul_ruft_keine_anthropic_api` — AST-basiert, prüft jedes
  `mcp_server/`-Modul. Sichert die Kostenanforderung.
- AST-Test gegen `sys.stdout = sys.stderr`.
- `test_kein_lookahead_...` — sichert das Backtest-Ausführungsmodell.
- Tests auf die Schlüsselmenge von `build_metrics_payload` /
  `build_report_payload` — sichern zu, dass keine Rohdaten das Haus verlassen.
- Tests auf Disclaimer und Verbot direkter Handelsempfehlungen.

**Testdatei fehlt für:** `common/patterns.py`-Integration in den Snapshot ist
über `test_mcp_snapshot.py` abgedeckt; ein eigener Test für Etappe C/D existiert
noch nicht, weil der Code nicht existiert.

### Backtests — WICHTIG

**Es wurde nie ein Backtest auf echten Marktdaten gerechnet.**

- Die **einzige** Datendatei zum Ausprobieren der CLI ist `data/DEMO_1m.csv` —
  ein **synthetischer Zufallspfad**. **Keine Grundlage für Aussagen über
  Strategien.**
- Es existieren **keine gespeicherten Backtest-Ergebnisse**, keine Reports, keine
  Kennzahlen.
- **Seit 21.08.2026 liegen aber erstmals echte Marktdaten in der produktiven
  Datenbank `data/ntbridge.sqlite3` vor** (siehe Verifikationslauf unten). Damit
  ist die Datengrundlage für einen künftigen echten Backtest vorhanden — ein
  solcher Backtest wurde bislang trotzdem **nicht** ausgeführt.

**Das ist kein Versäumnis der Dokumentation, sondern der tatsächliche Zustand.**
Ein zukünftiger Chat darf daraus **weiterhin keine** Aussagen über Strategiegüte
ableiten, bis ein Backtest tatsächlich gelaufen ist.

**Verfügbare Backtest-Kommandos** (auf echten Daten noch nie ausgeführt):

```
.venv\Scripts\python.exe -m backtest.cli list
.venv\Scripts\python.exe -m backtest.cli compare --symbol DEMO --csv data\DEMO_1m.csv
.venv\Scripts\python.exe -m backtest.cli optimize --symbol DEMO --csv data\DEMO_1m.csv --strategy vwap_trend --grid "stop_loss_atr=1.0,1.5,2.0"
```

### Verifizierter Ende-zu-Ende-Lauf (synthetische Daten, ältere Session)

In einer früheren Session wurde die Kette einmal vollständig durchgespielt:
Empfänger gestartet, **4450 synthetische Bars** über 5 Timeframes gepostet,
`/status` korrekt, Snapshot mit plausiblen Leveln und Indikatoren gerendert.
Beispielausgabe u. a. `week_high`, `week_low`, `volume_profile` (POC/VAH/VAL,
als Näherung markiert), `relative_volume`, und `atr_percentile` als
`noch nicht belastbar - 12/20 Sessions`.

Diese Bars lagen in einer temporären DB, nicht in der produktiven.

### Verifizierter Ende-zu-Ende-Lauf mit ECHTEN Daten (21.08.2026) — NEU

**Ablauf:**
1. `ClaudeBridge.cs` im NinjaScript-Editor kompiliert, Reiter *Errors* leer.
2. Zwei Charts eingerichtet (MNQ SEP26): 1m-Chart mit Zusatz-TFs `5,15`,
   Session Template `CME US Index Futures ETH`; Day-1-Chart mit Zusatz-TF `60`,
   Days to load 400.
3. Indikator zunächst **ohne laufenden Empfänger** angewandt (Empfänger war zu
   dem Zeitpunkt noch nicht gestartet). NinjaScript-Output zeigte korrekt:
   Startmeldung `ClaudeBridge 1.0.1 bereit`, korrekte Serienliste und
   Zielwerte (1m→3000, 5m→600, 15m→250, 1h→250, 1d→250), danach für jede
   Serie `Zeitueberschreitung nach 1500 ms ... Kerzen zwischengespeichert` —
   erwartetes, korrektes Fail-Handling ohne Absturz.
4. Empfänger gestartet: `.venv\Scripts\python.exe -m ntbridge`.
5. **Ohne weiteres Zutun** lieferte der Retry-Puffer der Bridge die
   zwischengespeicherten Kerzen beim nächsten Kontakt automatisch nach.
   Empfänger-Startmeldung zeigte direkt danach bereits **4366–4369 Bars** in
   der produktiven Datenbank, über alle 5 erwarteten Serien.
6. `curl http://127.0.0.1:8787/status` bestätigte:
   - `kerzen_angenommen: 5669`, `kerzen_abgelehnt: 0`, `ablehnungsgruende: {}`
   - `kerzen_gesamt: 4369` in `data/ntbridge.sqlite3`
   - Abdeckung je Serie: MNQ 1m (3015 Bars), 5m (603), 15m (251), 1h (250),
     1d (250)
   - `letzte_kerze_empfangen_utc` lag **~2 Minuten** hinter der tatsächlichen
     Uhrzeit zum Prüfzeitpunkt (2026-08-21, 02:20 UTC empfangen vs. 02:22 UTC
     real geprüft) — live, nicht nur historischer Backfill.
   - `alter_sekunden` bei 1m/5m: **1,9 Sekunden** — Kerzen kamen buchstäblich
     in dem Moment an, in dem geprüft wurde.
7. Zeitzonen-Check: gemeldete Zeitzone `W. Europe Standard Time` entspricht
   Europe/Berlin; UTC-Zeitstempel in der DB ohne Versatz zur echten Uhrzeit.
   Keine Diskrepanz gefunden.

**Ergebnis: Etappe A und Etappe B sind damit erstmals mit echten NT8-Live-
Marktdaten (MNQ) vollständig verifiziert, nicht mehr nur mit synthetischen
Daten.** Diese Bars liegen — anders als beim früheren synthetischen Lauf — in
der **produktiven** Datenbank.

**Offen geblieben, nicht Teil dieses Tests:** ob der bereits erwähnte
`laeuft_seit_utc`-Wert in `/status` korrekt aus der tatsächlichen
Prozesslaufzeit oder aus einem persistierten DB-Feld stammt (siehe Abschnitt 3,
`ntbridge/`). Kein Blocker, nur eine offene Detailfrage für den nächsten
Code-Zugriff.

### Erster Snapshot auf echten Daten (21.08.2026, 02:40 UTC) — NEU

Direkt nach dem Live-Test wurde erstmals
`.venv\Scripts\python.exe -m mcp_server.cli snapshot --symbol MNQ` auf echten
Daten ausgeführt. **Der Snapshot rendert vollständig und plausibel.**

**Korrekt verifiziert:**
- Zeitzonen-Umrechnung: 02:40 UTC → 22:40 ET (−4) → 21:40 CT (−5). Stimmt.
- Session-Erkennung: `asia`, Globex offen, RTH nein, **"noch 650 Min bis
  RTH-Eroeffnung"** — von 22:40 ET bis 09:30 ET sind exakt 10 h 50 min =
  650 min. Die Session-Logik rechnet richtig.
- Kontraktdaten: Tick 0,25 = 0,50 USD, Punktwert 2,0 USD — deckt sich mit dem
  Instrument-Register.
- `atr_percentile` meldet ehrlich `noch nicht belastbar - 11/20 Sessions`
  statt einer Schätzung. Das Kernprinzip funktioniert im Realbetrieb.

**Drei Beobachtungen, die beim nächsten Code-Zugriff zu prüfen sind
(NICHT als Fehler bestätigt, nur auffällig):**

1. **`relative_volume` meldete 0,02.** Das hieße 2 % des normalen Volumens.
   Der Globex-Tag rollt um 18:00 ET, zum Messzeitpunkt (22:40 ET) waren also
   erst ~4 h 40 min der 23-Stunden-Session vergangen — man würde grob 20 %
   erwarten, nicht 2 %. **Verdacht: Es wird das bisher aufgelaufene
   Teilsession-Volumen gegen ein Durchschnitts-VOLLsession-Volumen verglichen.**
   Das wäre exakt derselbe Fehlertyp wie Bug-Lehre 5 (ungleich lange Fenster,
   Abschnitt 8). Zu prüfen in `common/levels.py::history_dependent_metrics()`.
   Falls bestätigt: entweder auf gleich lange Fenster normalisieren (Volumen
   bis zur selben Session-Uhrzeit an den Vergleichstagen) oder das Feld
   während einer laufenden Session als `null` mit Begründung ausweisen.
2. **`volume_profile` meldete `VAL == POC` (beide 29314,2438),** bei
   `VAH 29355,7188`. Normalerweise gilt VAL < POC < VAH. Ein Wertbereich, der
   vollständig oberhalb des POC liegt, ist nicht unmöglich, aber ungewöhnlich
   genug für einen Blick auf die Randbehandlung der Value-Area-Berechnung.
   Feld ist ohnehin als `naeherung` markiert.
3. **Die Tagesserie wurde mit `1d (120 Bars)` gerechnet,** obwohl 250
   Tageskerzen in der Datenbank liegen und auch gesendet wurden. Vermutlich ein
   konfigurierter Lookback (analog `1m (1500 Bars)` bei 3015 vorhandenen), also
   wahrscheinlich Absicht — aber einmal bestätigen, damit nicht still
   Historie verworfen wird.

---

## 10. Bekannte technische Einschränkungen

| Einschränkung | Technischer Grund | Umgang im Code |
|---|---|---|
| **Volume Profile ist Näherung** | Echtes Volume-at-Price braucht Tickdaten; aus 1m-Bars nur Verteilung über die High-Low-Spanne | Feld als `naeherung: true` markiert |
| **Kumulatives Delta dauerhaft null** | Bid-/Ask je Kerze nur mit kostenpflichtigem "Order Flow +", nicht lizenziert | `null` mit Begründung, **nie geschätzt**; Nachrüststelle markiert |
| **Sekundärserien erben "Days to load"** | NT8-Verhalten | Zwei-Charts-Layout; Bridge protokolliert `WARNUNG: nur N von M Kerzen` |
| **Antwortzeit 10–30 s** | MCP-Roundtrip + Rechnung | Nutzen liegt in Vorbereitung und Auswertung, **nicht im 1-Minuten-Einstieg** |
| **Historienabhängige Kennzahlen brauchen Zeit** | `SESSIONS_REQUIRED`: `week_high`/`week_low` 5, `volume_profile` 2, `relative_volume` 10, `atr_percentile` 20 | `{"value": null, "available": false, "sessions_available": N, "sessions_required": M, "reason": "..."}` |
| **ISM/PMI und Fed-Reden ohne Actual** | ISM hat die FRED-Lizenz zurückgezogen | keine Gratisquelle; Feld bleibt leer mit Begründung |
| **Forex Factory inoffiziell** | kann brechen, hat **kein `actual`-Feld** | FF = Termine, FRED = Ist-Werte; fail-safe |

---

## 11. Widersprüche zwischen Chat/Dokumentation und aktuellem Code

### W1 — Etappe B: "offen" vs. vollständig gebaut vs. jetzt live verifiziert

- **Übergabedatei `PROJEKTKONTEXT_UEBERGABE.md` sagt:** "Etappe B — STATUS: offen."
- **Stand bis 20.08.2026:** Code fertig, Tests grün, aber **nie mit echten Daten
  gelaufen**.
- **Stand seit 21.08.2026:** Code fertig **und** mit echten NT8-Live-Daten
  verifiziert (siehe Abschnitt 9). Die Übergabedatei ist damit doppelt
  überholt — sie beschreibt einen Stand von vor dem Bau von Etappe B.
- **Es gilt:** Etappe B ist **vollständig verifiziert** (Code fertig, Tests
  grün, echte Live-Daten bestätigt). Die einzige verbleibende Lücke betrifft
  Etappe C/D, nicht mehr Etappe B selbst.

### W2 — "16:45 EST ist hart verdrahtet"

- **Frühere Chataussage:** In der Auswertung sei der Zwangsschluss 16:45 EST
  teilweise hart verdrahtet und müsse in Profile überführt werden.
- **Code zeigt:** **Trifft nicht zu.** Gezielte Suche nach `16:45`,
  `trailing_drawdown`, `hedging`, `forced_close`, `Zwangsschluss` über `common/`,
  `mcp_server/`, `live_bot/`, `ntbridge/`, `backtest/`, `config.yaml` findet
  **keine Prop-Firm-Logik**.
  Die Treffer auf `overnight_*` sind **Marktstruktur-Level** (Globex-Nachtsitzung,
  `common/levels.py`); die Treffer auf `drawdown` sind **Backtest-Kennzahlen**
  (`backtest/metrics.py::max_drawdown`).
- **Erklärung:** Die Auswertung (Etappe D) **existiert noch gar nicht**. Es kann
  dort nichts hart verdrahtet sein.
- **Es gilt:** Die Profil-Logik wird **auf der grünen Wiese** gebaut, nicht aus
  bestehendem Code herausgelöst.

### W3 — "Days to load: 5"

- **Übergabedatei sagt:** Days to load = 5.
- **Rechnung:** 3000 1-Minuten-Kerzen ≈ 50 Stunden ≈ 2,2 Globex-Sessions.
  "Days to load" zählt **Kalendertage**; über ein Wochenende reichen 5 knapp, ohne
  Reserve.
- **Status:** In dieser Session wurde **7** verwendet und funktionierte im
  Live-Test: die 1m-Serie erreichte mit 7 Tagen 3015 von 3000 Ziel-Kerzen, also
  sogar leicht über Ziel. Damit praktisch bestätigt, dass 7 ausreicht — nicht
  mehr nur hergeleitet. Maßgeblich bleibt weiterhin die
  `WARNUNG: nur N von M Kerzen`-Zeile im NinjaScript-Output, falls sich das
  Marktumfeld ändert.

### W4 — Erfolgstest der Übergabedatei ist überholt

- **Übergabedatei sagt:** Im NinjaScript-Output müssen **Zeitüberschreitungen**
  erscheinen, weil der Empfänger noch nicht existiert.
- **Es gilt:** Der Empfänger **ist gebaut und live verifiziert**. Erwartet werden
  jetzt **erfolgreich gespeicherte Bars** — im Test vom 21.08.2026 tatsächlich
  beobachtet (0 Ablehnungen, Live-Bars mit unter 2 Sekunden Alter).

### W5 — README ist zwei Architekturen zurück

`README.md` (Stand 2026-07-31) beschreibt ausschließlich den Tradovate-Live-Bot.
Gezählt: **13 Tradovate-Erwähnungen, 0 Erwähnungen von MCP/Claude Desktop, 0 von
NinjaTrader/ClaudeBridge/ntbridge.**

Der dortige Projektstruktur-Baum listet weder `mcp_server/` noch `ntbridge/` noch
`ninjatrader/`, und bei `common/` fehlen `levels.py`, `patterns.py`,
`instruments.py`.

**Es gilt:** Die README beschreibt den **Legacy-Pfad**, nicht das Zielsystem. Sie
ist als Einstiegsdokument derzeit **irreführend**. Aktualisierung ist offene
Aufgabe (Etappe F). Bis dahin sind `NORMALER_CHAT_KONTEXT.md` und diese Datei die
maßgeblichen Beschreibungen.

### W6 — `environment: demo` ist nicht das Profil `demo`

Siehe Abschnitt 4, "Namensfalle". Rein terminologisch, aber verwechslungsanfällig.

---

## 12. Nächste technische Schritte

1. **Empfänger dauerhaft mitlaufen lassen**, damit sich historienabhängige
   Kennzahlen (Wochen-H/L, ATR-Perzentil usw.) über die Zeit füllen.
2. **`relative_volume` prüfen** — meldete im ersten echten Snapshot 0,02,
   möglicherweise Teilsession gegen Vollsession verglichen (Abschnitt 9,
   Beobachtung 1). Wäre derselbe Fehlertyp wie Bug-Lehre 5. **Von den drei
   Beobachtungen die einzige mit echtem Fehlerverdacht** — hat Vorrang.
3. **`volume_profile` (VAL == POC) und Tagesserien-Lookback (120 statt 250)
   prüfen** — Abschnitt 9, Beobachtungen 2 und 3. Vermutlich harmlos.
4. **`laeuft_seit_utc` in `/status` prüfen** — vermutlich liest es einen
   persistierten DB-Wert statt der echten Prozesslaufzeit (Abschnitt 3, 9).
   Kein Blocker, aber klärungsbedürftig beim nächsten Code-Zugriff.
5. **Etappe C beginnen:** regelbasierte Ideen-Protokollierung, MNQ.
6. Danach **Etappe D**: `evaluate_past_ideas`, `get_performance_report`.

> **Korrektur gegenüber älteren Fassungen (21.08.2026):** Die früheren Schritte
> 1–6 dieser Liste (Kompilieren, Empfänger starten, zwei Charts einrichten,
> Erfolgstest, Etappe B verifizieren) sind **erledigt** — siehe Abschnitt 9 für
> den vollständigen Nachweis. Die Liste wurde entsprechend neu aufgesetzt.

### Vom Nutzer angeforderte, noch offene Arbeitspakete

- **Teil 2 — Profil-Logik `demo`/`lucid`** in der Config, alle Werte
  konfigurierbar, **eine gemeinsame Ideen-Datenbank mit Profilfeld**.
- **Teil 3 — Lucid-Regelwerk als Simulationsmodell.** Inklusive
  `evaluate_past_ideas(rules="none"|"lucid"|"both")` und dem **Pflicht-Test, dass
  der EOD-Trailing-Drawdown nicht versehentlich intraday prüft** — intraday wäre
  erheblich strenger als die tatsächliche Regel und ließe die Setups des Nutzers
  zu Unrecht schlecht aussehen.

**Technischer Hinweis:** Teil 2 und 3 setzen streng genommen Etappe C/D voraus —
es gibt noch keine Ideen, die man auswerten könnte. Der Nutzer hat sie trotzdem in
dieser Reihenfolge angefordert. Falls das relevant wird: **ansprechen, nicht
stillschweigend umbauen.**

---

## 13. Dauerhafte Randbedingungen für jede zukünftige Session

Diese gelten unabhängig von der jeweiligen Aufgabe:

1. **Keine Order-Ausführung**, auch nicht als inertes Interface, kein
   `send_trade_signal`, keine NinjaScript-Strategy, kein Lesen von Konto- oder
   Positionsdaten. **Bewusste Nutzerentscheidung, keine offene Lücke.**
2. **Kein Anthropic-Aufruf in `mcp_server/`.**
3. **Stille Ausfälle sind unzulässig:** `null` mit Begründungsfeld, plus
   Startprüfung, die abbricht.
4. **Keine erfundenen Zahlen**, keine Schätzung, die wie eine Messung aussieht.
5. **Bestehende Tests bleiben grün.**
6. **Quelldateien ASCII** (Umlaute als `ae`/`oe`/`ue`); README, `docs/` und die
   Kontextdateien mit echten Umlauten. Nutzertexte, Docstrings, Kommentare und
   Testnamen **deutsch**.
7. **Schwellenwerte in `config.yaml`, nie im Code.**
8. **Immer das venv verwenden** — `python` im PATH ist nur der
   Microsoft-Store-Platzhalter.

---

## 14. Pflege dieser Datei

`CODE_CHAT_KONTEXT.md` ist das technische Langzeitgedächtnis und wird **selbständig
aktualisiert**, wenn technisch dauerhaft relevantes Wissen entsteht:

neue oder entfernte wichtige Dateien, Architekturänderungen, technische
Entscheidungen und verworfene Ansätze, Bugs mit Ursache und Lösung, Tests und
Backtests mit Ergebnissen, geänderter Implementierungsstand, neue Einschränkungen,
neue offene Aufgaben.

**Nicht** dokumentiert werden: jede kleine Codeänderung, Formatierungen,
Zwischenstände. Die Datei ist **kein Git-Diff und kein Chatprotokoll**.

Bei Änderungen an Zielen, Anforderungen oder dauerhaften Entscheidungen
zusätzlich `NORMALER_CHAT_KONTEXT.md` prüfen.

**Hochladen ins Claude-Projekt:** Was dort liegt, ist eine eingefrorene Kopie und
aktualisiert sich **nicht** automatisch, wenn diese Datei auf der Festplatte
fortgeschrieben wird. Nach Meilensteinen beide Dateien neu hochladen. Das Datum
in der Kopfzeile verrät, ob die hochgeladene Fassung noch aktuell ist.

**Hinweis zu diesem Update (21.08.2026):** Dieser Stand wurde **im normalen Chat**
(nicht in Claude Code) auf Basis der vom Nutzer im Gespräch eingefügten
NinjaTrader- und `/status`-Ausgaben aktualisiert, nicht durch erneute Prüfung
gegen den tatsächlichen Quellcode. Inhaltlich ist das durch die zitierten
Live-Ausgaben gut belegt, aber die übliche Rangfolge (Code vor dieser Datei)
gilt weiterhin — bei nächster Gelegenheit gegen den echten Code abgleichen und
diese Kopie ggf. korrigieren.
