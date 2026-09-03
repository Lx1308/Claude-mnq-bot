# Claude Chart Bot

Lokales Analysewerkzeug für CME-Futures. Marktdaten kommen aus **NinjaTrader 8**,
laufen über einen lokalen Empfänger in eine SQLite-Datenbank und werden von einem
**MCP-Server** an **Claude Desktop** geliefert — Level, Indikatoren über mehrere
Zeitebenen, Marktstruktur, Muster, Terminrisiko.

Dazu ein getrenntes Backtesting-Framework.

> **Kein Handelssystem.** Das Projekt liest Marktdaten, rechnet und stellt Zahlen
> bereit. Es gibt **keinen einzigen Aufruf eines Order-Endpunkts** — bewusst
> nicht, auch nicht als leere Schnittstelle. Der NinjaTrader-Teil ist ein
> **Indikator**, keine Strategy; ein Indikator *kann* in NinjaTrader keine Orders
> platzieren. Kein Bestandteil dieses Projekts ist eine Anlageberatung.

---

## Inhalt

1. [Wie das Ganze zusammenhängt](#1-wie-das-ganze-zusammenhängt)
2. [Projektstruktur](#2-projektstruktur)
3. [Installation](#3-installation)
4. [NinjaTrader einrichten](#4-ninjatrader-einrichten)
5. [Empfänger starten](#5-empfänger-starten)
6. [MCP-Server in Claude Desktop](#6-mcp-server-in-claude-desktop)
7. [Terminal-Dump ohne Claude Desktop](#7-terminal-dump-ohne-claude-desktop)
8. [Ideen-Protokollierung (Etappe C)](#8-ideen-protokollierung-etappe-c)
9. [Backtesting](#9-backtesting)
10. [Konfiguration im Detail](#10-konfiguration-im-detail)
11. [Logging](#11-logging)
12. [Musterreferenzsatz beurteilen](#12-musterreferenzsatz-beurteilen)
13. [Tests](#13-tests)
14. [Bekannte Grenzen](#14-bekannte-grenzen)

---

## 1. Wie das Ganze zusammenhängt

```
NinjaTrader 8 Chart
  └─ ClaudeBridge.cs          Indikator, KEINE Strategy
     │                        AddDataSeries → mehrere Timeframes aus EINER Instanz
     │                        fire-and-forget, Timeout, Zwischenspeicher
     └─ HTTP POST {"bars":[…]} ──► 127.0.0.1:8787/bars
        └─ ntbridge/receiver.py     nur an localhost gebunden
           └─ ntbridge/store.py     SQLite im WAL-Modus, idempotent
              └─ mcp_server/        Level · Indikatoren · Struktur · Muster
                 └─ Claude Desktop  ◄── die Deutung passiert hier
```

**Warum die Deutung erst in Claude Desktop passiert:** Der MCP-Server ruft
**niemals** die Anthropic-API auf. Er liefert ausschließlich Zahlen mit
Einheiten. Interpretiert wird in der Unterhaltung, über das bestehende Abo — das
hält den laufenden Betrieb kostenfrei. Ein Test hält das fest
(`test_mcp_modul_ruft_keine_anthropic_api`, AST-basiert über jedes Modul unter
`mcp_server/`).

### Die drei MCP-Werkzeuge

| Werkzeug | Liefert |
|---|---|
| `get_market_snapshot` | Level (PDH/PDL/PDC, Overnight, Initial Balance, Opening Ranges, Gap), Indikatoren je Timeframe, Marktstruktur, Muster, Datenherkunft |
| `get_event_risk` | Wirtschaftstermine und Blackout-Fenster |
| `list_instruments` | Welche Instrumente das Register kennt |

### Ein Weg, zwei Nutzungsarten

```
NinjaTrader → ntbridge → SQLite ─┬─→ MCP → Claude Desktop   (auf Zuruf)
                                 └─→ ideas/                 (regelbasiert)
```

Beide lesen dieselbe Datenbasis. Der MCP-Server liefert auf Anfrage eine
Momentaufnahme; `ideas/` (Abschnitt 8) protokolliert im Hintergrund
regelbasiert Trade-Ideen.

**Keiner von beiden ruft die Anthropic-API auf.** Interpretiert wird
ausschließlich in der Claude-Desktop-Unterhaltung über das bestehende Abo.
Seit dem 22.08.2026 prüft ein Test das für das **gesamte** Repository, nicht
mehr nur für den MCP-Pfad — es gibt keine Stelle mehr, die die API rufen
dürfte.

> **Entfernt am 22.08.2026:** Ein älterer Pfad (Tradovate → `live_bot/` →
> Anthropic-API → Telegram) mit Alarmen und einem `/analyse`-Bericht wurde
> vollständig entfernt. Er kostete Token je Alarm und war nicht mehr das
> Ziel. Wer ihn in älteren Notizen erwähnt findet: er existiert nicht mehr.

---

## 2. Projektstruktur

```
Claude chart bot/
├── config.yaml                  Alle Schwellenwerte und Schalter
├── .env.example                 Vorlage für Secrets (nach .env kopieren)
├── requirements.txt
├── pytest.ini
├── CODE_CHAT_KONTEXT.md         Technisches Projektgedächtnis
├── NORMALER_CHAT_KONTEXT.md     Ziele, Anforderungen, Entscheidungen
│
├── ninjatrader/
│   └── ClaudeBridge.cs          NT8-Indikator (Quelle der Wahrheit)
│
├── ntbridge/                    Empfänger und Speicher
│   ├── receiver.py              HTTP-Server auf 127.0.0.1:8787
│   ├── store.py                 SQLite (WAL), idempotent, Bar-Validierung
│   └── __main__.py              python -m ntbridge
│
├── mcp_server/                  Für Claude Desktop — NIE ein Anthropic-Aufruf
│   ├── server.py                Die drei Werkzeuge
│   ├── snapshot.py              Baut die Momentaufnahme zusammen
│   ├── bars.py                  NTBridgeBarSource, Veraltet-Erkennung
│   ├── calendar_provider.py     Forex Factory (Termine) + FRED (Ist-Werte)
│   ├── context.py               Langlebiger Zustand des Dauerprozesses
│   └── cli.py                   Terminal-Dump ohne Claude Desktop
│
├── common/                      Von ALLEN Pfaden genutzt
│   ├── config.py                config.yaml + .env laden und validieren
│   ├── logging_setup.py         Textlog + JSON-Lines-Log
│   ├── instruments.py           Register: Ticksize, Punktwert, Verfallsregel
│   ├── sessions.py              CME-Handelstag (18:00-ET-Rollover)
│   ├── indicators.py            RSI/ATR/VWAP im Hot-Path; MACD, Stochastik,
│   │                            ADX, Bollinger/Keltner, EMA-Stack daneben
│   ├── levels.py                PDH/PDL/PDC, Overnight, IB, Opening Range, Gap
│   ├── structure.py             Swings, S/R-Zonen, BOS/CHoCH, RSI-Divergenz
│   └── patterns.py              Flagge, Dreieck, Doppeltop/-boden, Kompression
│
├── ideas/                       Etappe C: regelbasierte Ideen-Protokollierung
│   ├── setups.py                4 Familien → je eine Backtest-Strategie
│   ├── erkennung.py             wertet die Regel-Objekte über den Kerzen aus
│   ├── filters.py               ADX, Liquidität, Dünnzone, Blackout
│   ├── model.py                 TradeIdee, Beobachtung, CRV
│   ├── store.py                 SQLite: Tabellen `ideen` und `observations`
│   ├── pipeline.py              vorbereiten / baue_idee / protokolliere
│   ├── kalender.py              Abdeckungsgrenze vor dem Wirtschaftskalender
│   └── __main__.py              python -m ideas (Einzellauf für die Aufgabenplanung)
│
├── backtest/
│   ├── cli.py                   list / run / compare / optimize / fetch
│   ├── engine.py                Event-Engine (Ausführung zur Folgekerze)
│   ├── metrics.py               Trefferquote, Profit-Faktor, DD, Sharpe
│   ├── splits.py                IS/OOS-Trennung + Overfitting-Schutzriegel
│   ├── compare.py               Strategievergleich, Export, Parametersuche
│   ├── data/                    Austauschbare Datenquellen
│   └── strategies/              Regel-Objekte + Bibliothek
│
├── docs/
│   └── BACKTESTING_ENTSCHEIDUNG.md
│
└── tests/
```

**Der wichtigste Baustein ist `common/indicators.py`.** Live-Bot, MCP-Server und
Backtest rufen dieselbe Funktion auf. Damit ist ausgeschlossen, dass der Backtest
andere Zahlen sieht als der laufende Betrieb — der teuerste Fehler in Projekten
dieser Art.

---

## 3. Installation

Auf diesem Rechner liegt Python 3.14 unter dem Python Install Manager:
`C:\Users\lm130\AppData\Local\Python\bin\python.exe`. Der Name `python` ist in
der PATH-Variable nur der Microsoft-Store-Platzhalter — deshalb einmal den vollen
Pfad verwenden:

```bash
C:\Users\lm130\AppData\Local\Python\bin\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Prüfen:

```bash
.venv\Scripts\python.exe -m pytest
```

Erwartet: **326 passed**.

Es gibt **kein** `pip install -e .`. Skripte außerhalb der mitgelieferten CLIs
brauchen deshalb `$env:PYTHONPATH = (Get-Location).Path`. In den Tests erledigt
das `tests/conftest.py`.

### Sofort ausprobieren, ohne alles andere

Unter `data/DEMO_1m.csv` liegt ein **synthetischer** Datensatz (Zufallspfad).
Er ist nur zum Ausprobieren der Backtest-CLI da — aus den Ergebnissen darf man
nichts über echte Strategien ableiten:

```bash
.venv\Scripts\python.exe -m backtest.cli compare --symbol DEMO --csv data\DEMO_1m.csv
```

---

## 4. NinjaTrader einrichten

### 4.1 Indikator installieren und kompilieren

`ninjatrader/ClaudeBridge.cs` nach
`C:\Users\<Benutzer>\Documents\NinjaTrader 8\bin\Custom\Indicators\` kopieren.

Dann in NinjaTrader: **Control Center → New → NinjaScript Editor → F5**.
Der Reiter *Errors* muss leer bleiben.

> Meldet der Compiler `The type or namespace name 'Http' does not exist in the
> namespace 'System.Net'`, fehlt eine Referenz: im Editor Rechtsklick →
> `References…` → `Add` → `System.Net.Http`, dann erneut F5.

**Die Datei im Projektordner ist die Quelle der Wahrheit.** Die Kopie im
NinjaTrader-Ordner wird daraus erzeugt, nie umgekehrt. Die Versionsnummer
erscheint beim Start im NinjaScript-Output und ist der einzige verlässliche
Nachweis, welche Fassung tatsächlich läuft.

### 4.2 Zwei Charts je Instrument

Sekundärserien aus `AddDataSeries` **erben den Ladezeitraum des Charts**
("Days to load"). Ein 1-Minuten-Chart mit 7 Tagen liefert einer Tagesserie also
nur 7 Tageskerzen. Deshalb braucht es zwei Charts:

**Chart 1 — Intraday (liefert 1m, 5m, 15m)**

| Einstellung | Wert |
|---|---|
| Chart-Typ / Periode | Minute, 1 |
| Days to load | 7 |
| **Session Template** | **`CME US Index Futures ETH`** (MNQ) |
| Zusaetzliche Minuten-Timeframes | `5,15` |
| Tagesserie mitliefern | aus |

**Chart 2 — Tagesebene (liefert 1d, 1h)**

| Einstellung | Wert |
|---|---|
| Chart-Typ / Periode | Day, 1 |
| Days to load | 400 |
| Session Template | `CME US Index Futures ETH` |
| Zusaetzliche Minuten-Timeframes | `60` |
| Tagesserie mitliefern | aus (das Chart *ist* die Tagesserie) |

Für MGC dieselbe Struktur mit Session Template `COMEX Metals ETH`.

> **Das Session Template ist die kritischste Einstellung.** Mit **RTH** statt
> **ETH** kämen Vortageshoch und -tief nur aus 08:30–15:15 CT statt aus dem
> vollen Globex-Tag, den `common/sessions.py` unterstellt. **Kein Fehler, keine
> Warnung — nur andere Zahlen.**

### 4.3 Parameter des Indikators

| Gruppe | Name | Vorbelegung |
|---|---|---|
| Verbindung | Empfaenger-URL | `http://127.0.0.1:8787/bars` |
| Verbindung | Timeout (ms) | 1500 |
| Verbindung | Zwischenspeicher (Kerzen) | 200 |
| Daten | Historische Kerzen (Basis 1-Minuten-Ebene) | 3000 |
| Daten | Untergrenze historische Kerzen | 250 |
| Daten | Zusaetzliche Minuten-Timeframes | `5,15` |
| Daten | Tagesserie mitliefern | aus |
| Daten | Zeitzone (optional) | leer |
| Diagnose | Ausfuehrliches Log | beim Einrichten an |

**Warum 3000 historische Kerzen:** Eine Globex-Session dauert 23 Stunden, also
1380 Minutenkerzen. Vortageshoch, -tief und -schluss brauchen die Vorsession
**komplett plus** die laufende — mindestens 2760. Die gröberen Timeframes
bekommen automatisch anteilig weniger (5m→600, 15m→250, 1h→250, 1d→250).

**Warum die Tagesebene über `BarsPeriodType.Day` läuft und nicht über 1440
Minuten:** 1440-Minuten-Bars zählen schlicht Uhrzeit ab einem beliebigen Anker
und folgen **nicht** der Handelszeiten-Vorlage des Kontrakts. Die beiden liegen
um Stunden auseinander. Da genau aus dieser Session-Abgrenzung die
Vortagesmarken entstehen, wäre die Minutenvariante lautlos falsch. Der Indikator
lehnt `1440` in der Timeframe-Liste aktiv ab und schreibt eine Meldung.

---

## 5. Empfänger starten

**Immer zuerst den Empfänger, dann den Indikator an den Chart hängen.** Sonst
laufen die historischen Kerzen in den Zwischenspeicher, der bei 200 deckelt —
von 3000 blieben 200 übrig (protokolliert, aber verworfen). Passiert das doch:
Chart anklicken und **F5** (Reload Historical Data).

```bash
.venv\Scripts\python.exe -m ntbridge
```

Der Start gibt Datenbankpfad, Kerzenzahl und eine Abdeckungstabelle aus. Der
Server bindet **ausschließlich an 127.0.0.1** und ist auch im LAN nicht
erreichbar; ein anderer Host wird beim Start abgewiesen.

### Kontrolle

Im NinjaScript-Output (`New > NinjaScript Output`) muss stehen:

```
[ClaudeBridge hh:mm:ss] ClaudeBridge 1.0.1 bereit. Instrument MNQ, 3 Datenserie(n), Zeitzone …
  Serie 0: 1m - Ziel 3000 historische Kerzen
  Serie 1: 5m - Ziel 600 historische Kerzen
  Serie 2: 15m - Ziel 250 historische Kerzen
```

Erscheint `WARNUNG: nur N von M Kerzen für … vorhanden`, ist "Days to load" zu
klein. Diese Zeile ist maßgeblich — ohne sie blieben die Vortagesmarken einfach
leer.

Auf der Python-Seite:

```bash
curl http://127.0.0.1:8787/status
```

Die Antwort nennt angenommene und abgelehnte Kerzen, die Ablehnungsgründe und
je Instrument/Timeframe die Abdeckung samt Alter des jüngsten Bars.

### Wenn Kerzen abgelehnt werden

Jede Ablehnung hat einen benannten Grund — nichts wird still verworfen:

| Grund | Bedeutung |
|---|---|
| `zeitstempel_in_zukunft` | Die NinjaTrader-Zeitzone weicht von der Windows-Zeitzone ab. Parameter "Zeitzone (optional)" setzen, z.B. `US Eastern Standard Time` |
| `zeitstempel_unlesbar` | Feldname oder Format passt nicht |
| `timeframe_unbekannt` | z.B. Tick- oder Range-Chart; nicht unterstützt |
| `high_kleiner_low`, `ohlc_widerspruechlich` | Kerze in sich unstimmig |
| `preis_ungueltig`, `volumen_ungueltig` | negative oder nicht-numerische Werte |

---

## 6. MCP-Server in Claude Desktop

In `claude_desktop_config.json` eintragen:

```json
{
  "mcpServers": {
    "claude-chart-bot": {
      "command": "C:\\Users\\lm130\\Desktop\\Claude chart bot\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server"],
      "cwd": "C:\\Users\\lm130\\Desktop\\Claude chart bot"
    }
  }
}
```

`cwd` ist nicht optional: `python -m` stellt das Arbeitsverzeichnis in den
Suchpfad, und ohne das findet der Server die Pakete `common` und `ntbridge`
nicht.

Danach Claude Desktop neu starten. Der Server läuft als Dauerprozess; Zustand
und Kontraktauflösung werden **einmal** beim Aufbau erzeugt, nicht je Aufruf.

### Was in der Momentaufnahme steht

| Block | Inhalt |
|---|---|
| `meta` | Zeitstempel, Version |
| `instrument` | Ticksize, Punktwert, Kontraktmonat, Verfall |
| `session` | RTH ja/nein, liquide Phase, dünne Mittagszone, Minuten bis RTH-Schluss/Globex-Schluss |
| `datenherkunft` | Je Timeframe: Anzahl Bars, Alter, `veraltet` mit Hinweis |
| `levels` | PDH/PDL/PDC, Overnight, IB, Opening Ranges, Gap, Cash Open — in Punkten, Ticks und ATR |
| `historienabhaengig` | Wochenhoch/-tief, Volume Profile, relatives Volumen, ATR-Perzentil |
| `timeframes` | Indikatoren, Struktur und Muster je Zeitebene |

### Felder, die erst mit der Zeit belastbar werden

Einige Kennzahlen brauchen abgeschlossene Sessions. Bis dahin liefert das Feld
`null` **mit Begründung und Fortschrittsangabe** — nie eine Schätzung:

| Feld | Benötigte Sessions |
|---|---|
| `week_high` / `week_low` | 5 |
| `volume_profile` | 2 |
| `relative_volume` | 10 |
| `atr_percentile` | 20 |

Beispielausgabe: `noch nicht belastbar - 12/20 Sessions`.

---

## 7. Terminal-Dump ohne Claude Desktop

Dieselben Zahlen, direkt im Terminal — nützlich zum Prüfen, ob die Kette steht:

```bash
.venv\Scripts\python.exe -m mcp_server.cli snapshot --symbol MNQ
.venv\Scripts\python.exe -m mcp_server.cli levels --symbol MNQ
```

Optionen: `--timeframes 1m,5m,15m` · `--bars N` · `--no-bars` · `--json` ·
`--config` · `--env-file`.

### .env-Checkliste

```bash
copy .env.example .env
```

Es wird genau eine Variable gebraucht:

| Variable | Wofür | Nötig für |
|---|---|---|
| `FRED_API_KEY` | Ist-Werte der Wirtschaftstermine | `get_event_risk` |

Das ist **die einzige** Variable, die das Projekt noch kennt. `ANTHROPIC_API_KEY`,
`TELEGRAM_*` und `TRADOVATE_*` sind mit dem Legacy-Pfad am 22.08.2026 entfallen.

Ohne `FRED_API_KEY` läuft alles weiter — `get_event_risk` weist die Ist-Werte
dann als nicht verfügbar aus, statt so zu tun, als gäbe es keine Termine.

---

## 8. Ideen-Protokollierung (Etappe C)

`ideas/` schreibt regelbasiert erkannte Setups in eine eigene SQLite-Datei
(`data/ideas.sqlite3`), getrennt vom Kerzenspeicher. Ziel ist ein auswertbarer
Datensatz statt Erinnerung — die Auswertung selbst ist Etappe D und **existiert
noch nicht**.

> **Noch nicht eingeplant.** Der Einzellauf `python -m ideas` ist gebaut und
> getestet (Abschnitt 8.7), steht aber in **keiner Aufgabenplanung** — nichts
> ruft ihn regelmäßig auf. Es ist bislang **keine einzige echte Idee
> protokolliert**.

### 8.1 Die vier Setup-Familien

| Schlüssel | Was | Art | Backtest-Strategie |
|---|---|---|---|
| `pdh_pdl_bruch` | Bruch des Vortageshochs bzw. -tiefs | Fortsetzung | `prev_day_breakout` |
| `ib_bruch` | Bruch der Initial Balance der ersten RTH-Stunde | Fortsetzung | `ib_breakout` |
| `vwap_reversion` | Rückkehr zum VWAP nach weiter Abweichung | Reversion | `vwap_reversion` |
| `flaggen_ausbruch` | Ausbruch aus der Konsolidierung nach Impuls | Fortsetzung | `flag_breakout` |

**Jede Familie ist eine Backtest-Strategie, keine zweite Implementierung.**
`ideas/setups.py` baut die Regel-Objekte über `build_strategy()` aus
`backtest/strategies/library.py`; die Erkennung wertet sie über denselben
`BarContext` aus, den auch die Engine benutzt. Ein Test prüft diese Zuordnung
(`test_jede_setup_familie_verweist_auf_eine_backtest_strategie`), ein zweiter
verhindert die Rückkehr eigener Erkenner
(`test_ideas_modul_hat_keine_eigenen_erkenner_mehr`). Das ist dieselbe
Invariante wie bei `common/indicators.py`, nur eine Ebene höher: sonst
protokollierte der Bot etwas anderes, als der Backtest später nachrechnet.

Acht weitere Familien (BOS, CHoCH, RSI-Divergenz, Doppeltop/-boden, Dreieck,
Range-Kompression, Gap-Fill, Gap-and-Go) sind spezifiziert, aber bewusst **nicht
gebaut** — keine davon ist gegen echte Daten geprüft.

### 8.2 Die vier Filter haben drei Ausgänge

`ideas/filters.py`: ADX (Fortsetzung braucht Trend, Reversion braucht Range),
Liquiditätsfenster, Dünnzone, Termin-Blackout.

Jeder Filter endet **durch**, **abgelehnt** oder **nicht prüfbar**. Der dritte
Ausgang ist der Punkt: ist der Wirtschaftskalender nicht erreichbar, wird die
Idee mit `blackout_nicht_pruefbar` markiert und **nicht** stillschweigend
durchgewinkt. Ein Ausfall darf nie wie Entwarnung aussehen.

Abgelehnte Ideen werden trotzdem gespeichert (`speichere_gefilterte: true`).
Sonst ließe sich später weder prüfen, ob ein Filter zu scharf steht, noch
beantworten, wie viele Ideen ein Regelwerk verhindert hätte.

### 8.3 Zwei Logs, strikt getrennt

| Tabelle | Inhalt | Auswertung |
|---|---|---|
| `ideen` | regelbasiert erkannte Setups (`quelle = regel`) | ja |
| `observations` | freie Beobachtungen ohne Regel dahinter | **nie** |

`lade_fuer_auswertung()` nennt die Tabelle `observations` nicht einmal; ein
Quelltext-Test hält das fest. Eine Beobachtung ist kein Trade — sie hat weder
Einstieg noch Stop noch CRV.

### 8.4 Was bewusst NICHT gespeichert wird

**Kein Ergebnisfeld.** Gewinn oder Verlust entsteht erst durch
`evaluate_past_ideas` unter einem bestimmten Regelwerk. Stünde ein Ergebnis im
Log, gäbe es zwei Wahrheiten, je nachdem wann man hinsieht.

Damit die Auswertung trotzdem **nachspielen** kann, trägt jede Idee
`atr_referenz`, `stop_atr` und `ziel_atr` mit. Das Feld `entry` ist der
**Schlusskurs der Signalkerze**, nicht der Fill — gefüllt wird zur Eröffnung
der Folgekerze, genau wie in der Backtest-Engine. Ohne die drei ATR-Felder wäre
das R-Vielfache relativ zum echten Fill nicht rekonstruierbar.

`erstellt_utc` ist ebenfalls der **Schlusszeitpunkt der Signalkerze**, nicht der
Schreibzeitpunkt — nur so ist die Idee gegen die Kerzen in `ntbridge.sqlite3`
nachvollziehbar.

### 8.5 `profil` ist Herkunft, kein Steuerungsfeld

|  | hält fest | wann |
|---|---|---|
| `profil` (Feld an der Idee) | was **tatsächlich** war — welches Konto | beim Protokollieren |
| `rules` (Parameter von `evaluate_past_ideas`) | was **gewesen wäre** — welches Regelwerk | beim Auswerten |

Deshalb filtert `lade_fuer_auswertung()` **nicht** nach `profil`, außer man
verlangt es ausdrücklich: die interessante Frage ist, welche Setups auch unter
Prop-Firm-Regeln tragen, und die beantwortet man, indem man alle Ideen durch
beide Regelwerke rechnet.

> **Warum nicht `demo`.** Erlaubt sind `sim_frei`, `lucid_challenge`,
> `lucid_funded`. Der eigene Wertebereich stammt aus der Zeit, als die
> `config.yaml` unter `tradovate:` ein `environment: demo` führte und beides
> verwechselbar war; der Abschnitt ist seit dem 22.08.2026 entfallen, die
> präzisere Benennung bleibt. `Config.validate()` bricht bei jedem anderen Wert
> ab — ein Tippfehler würde die spätere Auswertung sonst still in zwei Gruppen
> zerlegen.

### 8.6 Abbrechen statt schweigen

- `ideas/setups.py::pruefe_konfiguration()` bricht ab, wenn ein Setup-Schlüssel
  unbekannt ist oder **alle** Familien abgeschaltet sind — eine Konfiguration,
  die nie auslösen kann, soll nicht so aussehen wie "keine Signale".
- `ideas/erkennung.py::pruefe_spalten()` wirft `FehlendeSpalte`, wenn eine
  benötigte Spalte fehlt. Ohne diese Prüfung bliebe das betroffene Setup stumm.
  Deshalb stehen `ib_high`/`ib_low` ausdrücklich in `zusatzspalten`: sie kommen
  aus `common/levels.py`, nicht aus `compute_indicators`.
- Eine in sich unschlüssige Idee (Stop auf der falschen Seite) wirft
  `UngueltigeIdee` und landet als `verworfen` im Protokollbericht, statt
  übersprungen zu werden.

Die Prüfung sitzt **in `ideas.setups`, nicht in `Config.validate()`**. Stünde
sie dort, zöge `common` einen Import aus `ideas` — eine Schichtumkehr, über die
der MCP-Server still `ideas` samt `backtest.strategies` in seine Importhülle
bekam. Ein eigener Test hält `Config.validate` frei davon.

### 8.7 Aufruf

```bash
.venv\Scripts\python.exe -m ideas                  # ein Lauf über die jüngsten Kerzen
.venv\Scripts\python.exe -m ideas --probelauf      # rechnen, aber nichts schreiben
.venv\Scripts\python.exe -m ideas --kein-kalender  # ohne Blackout-Abfrage
.venv\Scripts\python.exe -m ideas --symbol MNQ --bars 2000
```

Der Lauf geht **einmal** durch und beendet sich; für den Dauerbetrieb gehört er
in die Windows-Aufgabenplanung, genau wie `pruefe_datenluecken.py`. Ein
Dauerprozess hätte eigenen Zustand, eigene Absturzszenarien und ein eigenes
Neustartproblem — ein Einzellauf liest, was da ist, schreibt was fehlt, und ist
fertig. Der Speicher ist idempotent, ein Lauf zu viel schadet also nicht.

**Mindestens täglich, besser stündlich.** Der Blackout-Filter kann nur über die
letzten Tage Auskunft geben (Abschnitt 8.8). Wer einmal im Monat aufholt, bekommt
für fast alle Ideen „Blackout nicht prüfbar" — protokolliert, aber weniger wert.

Programmatisch:

```python
from common.config import Config
from ideas.pipeline import protokolliere
from ideas.store import IdeenStore

cfg = Config.load("config.yaml")
with IdeenStore(cfg.ideas.datenbank) as store:
    bericht = protokolliere(df, "MNQ", cfg, store)   # df = 5m-Kerzen aus ntbridge
    print(bericht.to_dict())
```

`protokolliere()` erkennt, filtert und speichert in einem Lauf und gibt einen
`Protokollbericht` zurück (erzeugt / gefiltert / neu gespeichert / verworfen).
Überlappende Läufe sind unschädlich: `ab_zeitpunkt` spart die Filterarbeit, der
UNIQUE-Index fängt Wiederholungen ohnehin ab.

Die Schwellenwerte stehen unter `ideas:` in `config.yaml` (Abschnitt 11).

### 8.8 Der Kalender kennt nur die letzten Tage

`ideas/kalender.py` liegt als **Abdeckungsgrenze** vor dem Wirtschaftskalender.
Grund: Forex Factory liefert im Wesentlichen die laufende Woche. Fragt man die
Schnittstelle nach einem drei Wochen alten Zeitpunkt, findet sie dort keinen
Termin und meldet `blackout.aktiv = false`. Das sieht aus wie „geprüft, alles
frei", ist aber „der Kalender kennt diesen Zeitraum gar nicht" — dieselbe
Verwechslung von Ausfall und Entwarnung wie in Abschnitt 7.

Zeitpunkte jenseits von `ideas.filter.blackout_max_alter_tage` (Vorgabe 7) werden
deshalb gar nicht erst angefragt und als **nicht prüfbar** vermerkt. Der Lauf
meldet am Ende, wie oft das vorkam. Zukünftige Zeitpunkte sind unproblematisch —
dort stehen die Termine ja.

`ideas` importiert `mcp_server` dabei **nicht**: die Blackout-Schicht kennt nur
ein Protokoll (`Terminquelle`), die konkrete `CalendarService`-Klasse wird erst
in `ideas/__main__.py` verdrahtet. Sonst wüchsen die beiden Oberschichten
zusammen.

## 9. Backtesting

### 9.1 Strategien ansehen und testen

```bash
.venv\Scripts\python.exe -m backtest.cli list

.venv\Scripts\python.exe -m backtest.cli run --symbol NQZ5 --strategy prev_day_breakout

.venv\Scripts\python.exe -m backtest.cli compare --symbol NQZ5 \
    --strategy prev_day_breakout --strategy vwap_trend --strategy flag_breakout
```

`compare` schreibt nach `backtest_results/`: `vergleich.csv`, `equity.png` und je
Strategie/Zeitraum eine Trade-Liste.

Eigene CSV nach `data/<SYMBOL>_1m.csv` legen. Erwartete Spalten:
`timestamp,open,high,low,close,volume` (Zeitstempel ohne Zeitzone werden als UTC
gelesen).

### 9.2 Parametersuche — mit Schutzriegel

```bash
.venv\Scripts\python.exe -m backtest.cli optimize --symbol NQZ5 \
    --strategy prev_day_breakout \
    --grid "rsi_max=60,65,70,75" --grid "stop_loss_atr=1.0,1.5,2.0" \
    --objective pnl_per_drawdown
```

Die Suche läuft **ausschließlich auf dem In-Sample-Zeitraum**. Danach wird die
beste Variante **einmal** out-of-sample geprüft und das Verhältnis Ø-Trade OOS/IS
ausgewiesen. Fällt es unter 0.5, gibt es eine Overfitting-Warnung.

Der Schutz ist kein guter Vorsatz, sondern Code: jede Optimierung ruft
`assert_in_sample_only()` auf und bricht mit `OutOfSampleViolation` ab, sobald
auch nur eine Out-of-Sample-Kerze im Datensatz liegt.

Die Indikatoren werden dabei **einmal über die Gesamthistorie** gerechnet und
erst danach geschnitten. Würde man den OOS-Block isoliert vorbereiten, hätten
dessen erste ~50 Kerzen keinen gültigen SMA(50) und die Strategie bliebe dort
stumm — ein stiller Verlust an OOS-Zeitraum.

### 9.2b Walk-Forward — dieselbe Strategie über viele Zeitfenster

```bash
.venv\Scripts\python.exe -m backtest.cli walkforward --symbol NQZ5 \
    --strategy vwap_trend --train-bars 5000 --test-bars 1000
```

Ein einzelner In-/Out-of-Sample-Schnitt sagt nur etwas über *eine* Marktphase
aus. Der Lauf zerlegt die Historie stattdessen in viele aufeinanderfolgende
Testfenster und weist die eigentlich interessante Größe aus: **wie viele**
Fenster positiv waren, nicht nur die Summe über alles. Eine Strategie, die
insgesamt im Plus steht, aber nur in zwei von zwanzig Fenstern verdient hat,
lebt von einer einzelnen Marktphase.

Drei Dinge, die der Bericht ausdrücklich sagt statt sie zu verschweigen:

- **Im Trainingsfenster wird nichts gesucht.** Die Parameter stehen fest; das
  Trainingsfenster ist reiner Vorlauf. Das ist damit ein abschnittsweiser
  Out-of-Sample-Lauf, kein Walk-Forward *mit Optimierung* — und der Bericht
  schreibt das über jede Ausgabe.
- **Bei überlappenden Fenstern** (`--step-bars` kleiner als `--test-bars`)
  bleiben Trade- und P&L-Summen leer, weil dieselben Trades sonst mehrfach
  gezählt würden. Die Begründung steht an der Stelle der fehlenden Zeile.
- **Fenstergrößen haben keinen Vorgabewert.** Ein stiller Standard ließe einen
  Lauf entstehen, dessen Fensterwahl niemand bewusst getroffen hat.

### 9.3 Eigene Strategie schreiben

```python
from backtest.strategies.base import ColumnAbove, CrossesAbove, CrossesBelow, RuleStrategy

meine_strategie = RuleStrategy(
    name="vwap_reclaim",
    long_entry=CrossesAbove("close", "vwap") & ColumnAbove("rsi", 45),
    long_exit=CrossesBelow("close", "sma_fast"),
    stop_loss_atr=1.5,
    take_profit_atr=3.0,
    max_bars_in_trade=90,
)
```

In `backtest/strategies/library.py` unter `STRATEGY_LIBRARY` eintragen.
`BarContext` gibt bewusst nur die aktuelle und die vorherige Zeile frei —
Look-ahead ist damit strukturell ausgeschlossen.

### 9.4 Ausführungsmodell

- Regeln werden auf dem **Schlusskurs** ausgewertet, ausgeführt wird zur
  **Eröffnung der Folgekerze**.
- Stop und Ziel greifen **innerhalb** der Kerze über High/Low.
- Werden beide in derselben Kerze berührt, gilt der **Stop** — aus OHLC lässt
  sich nicht rekonstruieren, was zuerst kam.
- Immer höchstens **eine** Position; Zwangsschluss am Sessionende.
- Kosten über `CostModel` mit echtem Punktwert und Ticksize. **P&L ist USD, keine
  Punktzahl.**

**Zur Sharpe Ratio bei Intraday-Futures:** Die klassische Formel setzt eine
Rendite auf eingesetztes Kapital voraus. Bei Futures ist das eingesetzte Kapital
eine Margin-Entscheidung, keine Eigenschaft der Strategie. Deshalb wird
standardmäßig `sharpe_pnl` ausgewiesen (tägliche P&L in USD, kapitalunabhängig).
Bei wenigen Trades sind `trades`, `profit_factor` und `max_drawdown` die
belastbareren Größen.

Warum eine eigene Engine statt `backtesting.py` oder `vectorbt`:
siehe [`docs/BACKTESTING_ENTSCHEIDUNG.md`](docs/BACKTESTING_ENTSCHEIDUNG.md).

---

## 10. Konfiguration im Detail

Alles Wesentliche steckt in `config.yaml`, Secrets ausschließlich in `.env`.
Vorrang: **CLI > .env > YAML**.

```yaml
ntbridge:
  enabled: true
  host: "127.0.0.1"              # NUR lokal. Anderes wird beim Start abgewiesen.
  port: 8787
  database: "data/ntbridge.sqlite3"
  stale_factor: 2.0              # Jüngster Bar älter als factor * Bar-Länge
  symbol_map: {}                 # nur nötig bei abweichenden NT-Namen

market:
  product: MNQ
  tick_size: 0.25
  point_value: 2.0               # MNQ = 2, NQ = 20, ES = 50
  # candle_buffer_size / warmup_bars stammen aus der Zeit des Live-Bots und
  # werden von keinem laufenden Prozess mehr ausgewertet.

analyse:                         # hiess bis 22.08.2026 "on_demand"
  swing_strength: 3
  swing_lookback: 120
  max_zones: 3

indicators:
  flag:
    impulse_lookback: 20
    impulse_min_atr: 2.5
    consolidation_lookback: 10
    consolidation_max_atr: 1.2
    breakout_buffer_atr: 0.1

ideas:                           # Etappe C, siehe Abschnitt 8
  enabled: true
  profil: sim_frei               # NICHT "demo" - siehe Namensfalle unten
  datenbank: "data/ideas.sqlite3"
  instrumente: ["MNQ"]
  timeframe: "5m"
  bars: 1500
  crv_schwelle: 1.5              # darunter: markiert, aber trotzdem gespeichert
  speichere_gefilterte: true     # sonst fehlt der Vergleichsmaßstab
  setups:
    pdh_pdl_bruch: { aktiv: true, puffer_punkte: 1.0, stop_atr: 1.5, ziel_atr: 3.0 }
    ib_bruch:      { aktiv: true, puffer_punkte: 1.0, stop_atr: 1.5, ziel_atr: 3.0 }
    vwap_reversion: { aktiv: true, abweichung_atr: 1.5, stop_atr: 1.5, ziel_atr: 2.0 }
    flaggen_ausbruch: { aktiv: true, stop_atr: 1.2, ziel_atr: 2.5 }
```

`stop_atr` / `ziel_atr` sind ATR-Vielfache ab Einstieg — **dieselbe Bedeutung**
wie `stop_loss_atr` / `take_profit_atr` in der Backtest-Engine, damit Protokoll
und Backtest dasselbe rechnen. Fehlt eine Familie unter `setups:`, gelten die
Vorgabewerte aus `IdeenSetupParameter`.

> **`candle_buffer_size` nicht blind verkleinern.**
> Vortageshoch und -tief brauchen die komplette Vorsession **plus** die laufende.
> Eine CME-Globex-Session dauert 23 Stunden, also 2 × 23 × 60 = **2760
> Ein-Minuten-Kerzen**. Ist der Puffer kleiner, bleiben die Vortagesmarken
> dauerhaft leer und die Alarme `prev_day_high_cross` / `prev_day_low_cross`
> lösen **nie** aus — ohne jede Fehlermeldung. `Config.validate()` bricht deshalb
> beim Start ab, statt still nichts zu melden.

`Config.validate()` prüft beim Start außerdem, ob `tick_size` und `point_value`
zum Instrument-Register passen (fängt "Produkt MNQ mit NQ-Werten" ab) und ob der
Swing-Lookback mindestens `2*strength+1` beträgt.

**Zu `max_tokens` im Legacy-Pfad:** Claude Sonnet 5 denkt standardmäßig adaptiv,
und `max_tokens` begrenzt Denk- und Antworttokens **zusammen**. Zu knapp gesetzt
wird die Antwort mittendrin abgeschnitten. Sampling-Parameter wie `temperature`
sind auf diesem Modell nicht erlaubt.

---

## 11. Logging

Zwei Dateien parallel in `logs/` (rotierend), je Prozess ein Paar:

| Datei | Zweck |
|---|---|
| `ntbridge.log` / `ideas.log` | Menschenlesbar |
| `ntbridge_events.jsonl` / `ideas_events.jsonl` | Eine JSON-Zeile je Ereignis |

Jedes Ereignis hat einen Typ im Schema `bereich.aktion` und einen strukturierten
Payload. Wichtige Typen: `ntbridge.started`, `ntbridge.bars.accepted`,
`ntbridge.bars.rejected`, `ideen.lauf`, `ideen.verworfen`,
`ideen.blackout.ausserhalb_abdeckung`.

```bash
.venv\Scripts\python.exe -c "import json;[print(json.loads(l)['payload']) for l in open('logs/ntbridge_events.jsonl',encoding='utf-8') if 'rejected' in l]"
```

---

## 12. Musterreferenzsatz beurteilen

Bevor auf einer Musterdefinition gemessen wird, muss sie **freigegeben** sein.
Grundlage der Freigabe ist kein einzelnes Beispiel, sondern ein Referenzsatz:
150 Kandidaten aus der ganzen Historie und 100 Zufallsfenster, gemischt und
äußerlich nicht unterscheidbar.

Bauen (dauert einige Minuten, schreibt 250 PNGs nach `data/w_referenz_bilder/`):

```bash
.venv\Scripts\python.exe -m werkzeuge.w_referenz
```

Beurteilen:

```bash
.venv\Scripts\python.exe -m werkzeuge.w_referenz_server
```

Die Seite öffnet sich unter <http://127.0.0.1:8795>. Tastatur: `1` = Ja,
`2` = Nein, `3` = Unklar, Pfeil links = zurück. Jedes Urteil wird sofort
gespeichert; Schließen und später weitermachen ist vorgesehen.

Die Bilder zeigen **bewusst nicht**, wie es weiterging, und weder Datum noch
Kursniveau. Beurteilt wird die Form, nicht der Ausgang — sonst würden Gewinner
beschriftet statt Muster.

Die Urteile liegen in `data/w_referenz.sqlite3` und zusätzlich als Text in
`data/w_referenz_urteile.csv`. Nur das CSV wird versioniert: die Bilder sind
jederzeit neu zu erzeugen, die Urteile nicht.

```bash
.venv\Scripts\python.exe -m werkzeuge.w_referenz --export          # CSV neu schreiben
.venv\Scripts\python.exe -m werkzeuge.w_referenz --import-urteile  # CSV zurücklesen
```

---

## 13. Tests

```bash
.venv\Scripts\python.exe -m pytest              # alles (316)
.venv\Scripts\python.exe -m pytest -v
.venv\Scripts\python.exe -m pytest tests/test_ntbridge.py
.venv\Scripts\python.exe -m pytest -k lookahead -v
```

Tests laufen **immer gegen temporäre Datenbanken**, nie gegen
`data/ntbridge.sqlite3` — die wird im Betrieb beschrieben.

Abgedeckt sind unter anderem:

- RSI/SMA/ATR gegen bekannte Randfälle, VWAP-Reset zum Sessionwechsel,
  Vortagesmarken über den 18:00-ET-Rollover
- Empfänger: Bar-Validierung mit jedem einzelnen Ablehnungsgrund, Idempotenz des
  Upserts, Abweisung von Nicht-localhost-Hosts
- Engine: kein Look-ahead, Ausführung zur Folgekerze, Stop vor Ziel, Zeitstop,
  Sessionende, nur eine Position
- IS/OOS: chronologische Teilung, `OutOfSampleViolation` beim Fehlgriff
- Marktstruktur: Swing-Erkennung inkl. des Randfalls "letzte Kerzen können noch
  kein bestätigtes Extrem sein", Zonen-Zusammenfassung, BOS/CHoCH
- Kosten: **kein Anthropic-Import im gesamten Projekt** (AST-basiert, seit dem
  22.08.2026 repo-weit statt nur in `mcp_server/`), kein Umbiegen von
  `sys.stdout`, Schlüsselmenge der Payloads
- Konfiguration: zu wenig `ideas.bars` für die Vortagesmarken wird beim Start
  abgefangen, skaliert nach Timeframe
- Ideen (`test_ideas.py`): jede Setup-Familie verweist auf eine
  Backtest-Strategie, keine eigenen Erkenner, die Auswertung liest nie das
  Exploration-Log, fehlende Spalte bricht laut ab, Erkennung sieht nie in die
  Zukunft, IB-Bruch löst vor Ablauf des IB-Fensters nicht aus

Die verbliebenen Netzwerkschichten (Forex Factory, FRED) sind bewusst nicht mit
Mocks nachgebaut — dort testet man sonst vor allem die eigenen Mocks. Sie sind
stattdessen so gebaut, dass jeder Fehler abgefangen und protokolliert statt
eskaliert wird, und ein Ausfall wird als `calendar_available: false` ausgewiesen
statt als „keine Termine".

---

## 14. Bekannte Grenzen

**Antwortzeit 10–30 Sekunden.** Für den Auslöser eines 1-Minuten-Einstiegs zu
langsam. Der Nutzen liegt in der Vorbereitung und in der späteren Auswertung.

**Volume Profile ist eine Näherung.** Echtes Volume-at-Price bräuchte Tickdaten.
Aus 1m-Bars lässt sich Volumen nur über die High-Low-Spanne verteilen. Das Feld
ist als `naeherung: true` gekennzeichnet.

**Kumulatives Delta bleibt null.** Bid-/Ask-Volumen je Kerze gibt es in NT8 nur
mit dem kostenpflichtigen Add-on "Order Flow +" — nicht lizenziert. Es wird
**bewusst nicht geschätzt**: eine Schätzung aus Auf- und Abwärtskerzen sähe aus
wie eine Messung und wäre keine. Die Nachrüststelle ist in `ClaudeBridge.cs`
markiert.

**Sekundärserien erben den Ladezeitraum des Charts.** Daraus folgt zwingend das
Zwei-Charts-Layout aus Abschnitt 4.2.

**Der Empfänger-Vertrag hat keinen Compiler.** Ändert man in `ClaudeBridge.cs`
einen Feldnamen oder den Umschlag, meldet **nichts** einen Fehler — die Kerzen
werden schlicht abgelehnt. Bei jeder Änderung an der Bridge gegen
`ntbridge/store.py` und `ntbridge/receiver.py` gegenprüfen. Feld heißt
`timestampUtc`, Umschlag ist `{"bars":[…]}`.

**ISM/PMI und Fed-Reden bleiben ohne Ist-Wert.** ISM hat die FRED-Lizenz
zurückgezogen, es gibt keine brauchbare Gratisquelle.

**Forex Factory ist ein inoffizieller Endpunkt** und kann brechen. Er hat zudem
kein `actual`-Feld — daher die Aufteilung: Forex Factory liefert den Terminplan,
FRED die Ist-Werte. Ist der Kalender nicht erreichbar, steht
`calendar_available: false` mit Begründung da — **niemals** "keine Termine". Ein
Ausfall darf nie wie Entwarnung aussehen.

**Die Ideen-Protokollierung läuft in keinem Dauerprozess.**
`ideas.pipeline.protokolliere()` ist gebaut und getestet, wird aber von nichts
regelmäßig aufgerufen — es ist bislang keine einzige echte Idee protokolliert.
Die Auswertung (Etappe D: `evaluate_past_ideas`, `get_performance_report`)
existiert noch nicht.

**Es wurde nie auf echten Marktdaten backgetestet.** Die einzige Datendatei
`data/DEMO_1m.csv` ist ein synthetischer Zufallspfad zum Ausprobieren der CLI.
Aus ihr lassen sich **keine** Aussagen über die Güte einer Strategie ableiten.

**Kontraktrollover.** Ein zusammengesetzter Frontmonat-Chart hat an den Rolltagen
Preissprünge. Wer über Rollover hinweg backtestet, sollte back-adjusted Daten
verwenden.

**Verfallsregeln sind instrumentspezifisch.** MNQ rollt zum 3. Freitag, MGC zum
**drittletzten Geschäftstag des Liefermonats** (Kontraktmonate G/J/M/Q/V/Z). Die
Regel liegt im Instrument-Register, nicht als Annahme im Code.

**Die Flaggen-Heuristik ist eine Heuristik.** "Impuls, dann enge Range, dann
Ausbruch" ist kein bestätigtes Chartmuster. Die Schwellenwerte sind Startwerte,
keine Empfehlung.

**Zonen sind Swing-Punkte, keine geprüften Niveaus.** Sie entstehen rein
mechanisch aus lokalen Extrema. Eine Zone mit einer einzigen Berührung ist kaum
mehr als ein Zufallshoch — die Anzahl der Berührungen steht deshalb immer dabei.

**Prop-Firm-Regeln sind nicht abgebildet.** Zwangsschluss, Trailing Drawdown und
Konsistenzregeln prüft dieses Projekt derzeit nicht. Es beobachtet den Markt,
nicht dein Konto. Ein optionales Regelwerk dafür ist geplant.

**LLM-Chartanalyse aus Screenshots ist ungenau.** Preise werden abgelesen, nicht
gemessen. Bei MNQ mit 0,25-Punkte-Ticks kann das um Punkte danebenliegen — einer
der Gründe, warum es dieses Projekt gibt.
