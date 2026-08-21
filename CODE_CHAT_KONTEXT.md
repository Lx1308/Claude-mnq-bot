# CODE_CHAT_KONTEXT

**Technisches Langzeitgedächtnis des Projekts "Claude Chart Bot".**

Stand: 2026-08-21 (abends). Geprüft gegen den tatsächlichen Projektordner.

---

## 0. Zweck und Verhältnis zur Schwesterdatei

**Es gibt genau zwei Kontextdateien.** Beide gehören zusammen ins Claude-Projekt:

| Datei | Rolle | Ändert sich |
|---|---|---|
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
| `backtest/` | **fertig** | ja, **nie auf echten Daten gerechnet** |
| `live_bot/` (Legacy: Tradovate + Telegram) | lauffähig, **nicht Zielsystem** | ja |
| `ideas/` (Etappe C) | **Zwischenstand, nicht nutzbar** | nein |
| Etappe D, Profil-Logik, Lucid-Simulation | **existiert nicht** | — |

**Testsuite: 334 Tests, alle grün.** `.venv\Scripts\python.exe -m pytest`

| Datei | Tests |
|---|---|
| `test_mcp_snapshot.py` | 43 |
| `test_levels_structure.py` | 39 |
| `test_ntbridge.py` | 37 |
| `test_on_demand.py` | 35 |
| `test_live_bot.py` | 29 |
| `test_instruments_sessions.py` | 26 |
| `test_event_risk.py` / `test_patterns.py` | je 22 |
| `test_extended_indicators.py` | 21 |
| `test_structure.py` | 17 |
| `test_indicators.py` / `test_metrics_and_splits.py` | je 15 |
| `test_engine.py` | 13 |

Verlauf: 124 → … → 286 → 326 → 332 → 335 → 329 → **334**.
Der Rückgang auf 329 war beabsichtigt: ein parametrisierter Test über acht
Moduldateien wurde durch zwei gezielte, stärkere ersetzt.

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
- **Etappe C ist nicht einsatzfähig** (Abschnitt 6).

### Bekannte Probleme

1. **Lücke in der Tagesserie: 2026-07-31 → 2026-08-12, acht Handelstage.**
   Die Kerze vom 12.08. bekommt dadurch eine True Range von rund **1560 Punkten**
   (Vortagesschluss 28441.50 → Hoch 30001.50), weil der Sprung über die Lücke als
   eine Tagesbewegung zählt. Das treibt den **1d-ATR auf 650 Punkte** — ein
   Datenartefakt, kein Marktzustand. Die 1d-Zeile im Snapshot ist nicht
   belastbar, bis die Lücke in NinjaTrader nachgeladen ist.
2. **Kein `.env` vorhanden.** Der MCP-Server startet trotzdem. Folge: ohne
   `FRED_API_KEY` liefert `get_event_risk` die **Termine** (Forex Factory braucht
   keinen Schlüssel), aber **keine Ist-Werte**.
3. **Tagesbar-Schluss ≠ letzter 1m-Schluss.** Für den 20.08. meldet die
   NT8-Tageskerze 29300.50, der letzte 1m-Schluss derselben Session 29317.00 —
   16,5 Punkte. Normal bei Futures (Settlement statt letztem Trade), aber
   relevant, falls Level je aus dem Tages- statt dem Intraday-Frame kommen.

### Offene technische Aufgaben

1. **Etappe C** gegen die Spezifikation neu aufsetzen (Abschnitt 6).
2. Etappe D: `evaluate_past_ideas`, `get_performance_report`.
3. Profil-Logik `demo`/`lucid` + Lucid-Regelsimulation.
4. Etappe E: Dauerbetrieb-Härtung.
5. Tagesserien-Lücke in NinjaTrader nachladen.
6. Entscheidung: Legacy-Pfad `live_bot/` samt Tradovate entfernen? (Abschnitt 7)

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

**Seit 21.08.2026 importiert `mcp_server/` ausschließlich aus `common/` und
`ntbridge/`** — kein `live_bot`, kein Tradovate. Zwei Tests sichern das
(Abschnitt 5.3).

### Legacy-Pfad (lauffähig, nicht Ziel)

```
Tradovate WebSocket -> live_bot/market/ -> Alarme -> Anthropic-API -> Telegram
```

Kostet Token je Alarm.

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

### `ideas/` — Etappe C, Zwischenstand

`model.py`, `detectors.py`, `filters.py`, `store.py`. **Nicht nutzbar**,
Abschnitt 6.

---

## 4. Konfiguration

`config.yaml`: `tradovate`, `market`, `indicators`, `alerts`, `claude`,
`on_demand`, `ntbridge`, **`ideas`**, `event_risk`, `notify`, `logging`,
`backtest`.

**Vorrang:** CLI > `.env` > YAML. Schwellenwerte nur in der YAML, Secrets nur in
`.env`.

### Namensfalle

`config.yaml` enthält `environment: demo` **unter `tradovate:`** — das ist die
Broker-Umgebung, **nicht** das Profil `demo`/`lucid` aus `ideas.profil`.

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
live läuft. **Diese Invariante ist der Grund, warum der Etappe-C-Zwischenstand
überarbeitet werden muss** (Abschnitt 6).

### 5.2 Eigene Backtest-Engine

`docs/BACKTESTING_ENTSCHEIDUNG.md`. `backtesting.py` hat kein Futures-Modell
(Kommission prozentual statt USD je Seite, keine Kontraktmultiplikatoren);
`vectorbt` macht zustandsabhängige Regeln schwer debugbar.

### 5.3 `mcp_server` ohne `live_bot` — und ein transitiv prüfender Test

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

## 6. Etappe C: Zwischenstand vs. Spezifikation

**Wichtigster offener Punkt.** Am 21.08.2026 wurden Modell, Erkenner, Filter und
Speicher gebaut (`739cd1c`). **Danach** kam `ETAPPE_C_SPEZIFIKATION.md` (im
normalen Chat erstellt). Sie weicht mehrfach ab. **Vor dem Weiterbauen
abgleichen, nicht darauf aufsetzen.**

| Punkt | Zwischenstand | Spezifikation |
|---|---|---|
| **Signal-Logik** | eigene Erkenner in `detectors.py` | **Backtest-Strategie-Logik wiederverwenden**, keine zweite Fassung |
| Logs | nur `ideas` | zusätzlich `observations` (Exploration, fließt **nie** in `evaluate_past_ideas`) |
| Herkunftsfeld | fehlt | `quelle` = `regel` / `manuell_assistiert` |
| Primärschlüssel | `(instrument, setup, ts_utc)` | `idea_id` INTEGER PK |
| Setup-Schlüssel | Richtung im Namen (`pdh_bruch`/`pdl_bruch`) | eine Familie je Schlüssel, Richtung als eigene Spalte |
| Umfang | 4 Setups | 12 Familien, schrittweise |
| Freitext | fehlt | `notiz` |

**Der erste Punkt ist der schwerwiegende:** `detectors.py` ist genau die zweite
Implementierung, die Invariante 5.1 ausschließt. Deshalb wurden für `ideas/`
bewusst **keine Tests** geschrieben — Aufwand für Code, der so nicht bleibt.

**Vor dem Bau zu klären (laut Spezifikation offen):** Rolle des `profil`-Felds —
nur Herkunft mitführen, oder beim Auswerten filtern?

**Tragfähig aus dem Zwischenstand:** die drei Filter-Ausgänge (durch / abgelehnt
/ nicht prüfbar), das Speichern auch gefilterter Ideen, und
`initial_balance_per_session()` in `common/levels.py` (getestet).

---

## 7. Offene Entscheidung: Legacy-Pfad entfernen?

Der Nutzer sagte am 21.08.2026: *„tradovate ist raus brauche dazu nichts mehr."*
Umgesetzt ist daraufhin die **Entkopplung des Zielsystems** (5.3). Die
vollständige Entfernung ist **bewusst nicht** erfolgt, weil sie weiter reicht,
als der Satz eindeutig deckt:

| Betroffen | Umfang |
|---|---|
| `live_bot/tradovate/` | 1007 Zeilen |
| `backtest/data/tradovate_provider.py` | 126 Zeilen |
| `live_bot/` gesamt (Alarme, Telegram, `/analyse`) | hängt vollständig daran |
| Tests | `test_live_bot.py` (29) + `test_on_demand.py` (35) = **64** |
| `config.yaml` | `Config.from_dict` **verlangt** den `tradovate:`-Abschnitt |

Zudem hält `NORMALER_CHAT_KONTEXT.md` fest, der Legacy-Pfad *„bleibt bestehen,
ist aber nicht mehr das Ziel"* — eine dokumentierte frühere Entscheidung.
**Widerspruch festgestellt, nicht stillschweigend aufgelöst.** Zu klären.

---

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

- `test_mcp_pfad_erreicht_keine_anthropic_api` — transitive Hülle, sichert die
  Kostenanforderung.
- `test_mcp_pfad_zieht_kein_live_bot_mehr` — hält das Zielsystem vom Legacy-Pfad
  frei.
- AST-Test gegen `sys.stdout = sys.stderr`.
- `test_kein_lookahead_...` — Backtest-Ausführungsmodell.
- `test_angeschnittene_vorsession_gilt_nicht_als_vollstaendig` und
  `test_levelframe_ueberspringt_angeschnittenen_timeframe`.
- `test_zweiter_start_bricht_ab_statt_still_danebenzulaufen`.
- `test_initial_balance_ist_waehrend_des_fensters_noch_nicht_bekannt`.
- Tests auf Schlüsselmenge der Claude-Payloads, Disclaimer und Verbot direkter
  Handelsempfehlungen.

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
```

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
