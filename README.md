# Claude Chart Bot

Live-Marktbeobachtung fuer CME-Index-Futures ueber Tradovate, mit
Claude-Kommentar und Telegram-Alarm — plus ein getrenntes
Backtesting-Framework.

> **Kein Handelssystem.** Das Projekt liest Marktdaten, rechnet Indikatoren,
> loest Alarme aus und verschickt Nachrichten. Es gibt **keinen einzigen
> Aufruf eines Order-Endpunkts** — bewusst nicht. Kein Bestandteil dieses
> Projekts ist eine Anlageberatung.

---

## Inhalt

1. [Was der Bot macht](#1-was-der-bot-macht)
2. [Projektstruktur](#2-projektstruktur)
3. [Installation](#3-installation)
4. [Einrichtung](#4-einrichtung)
5. [Live-Bot starten](#5-live-bot-starten)
6. [Der Befehl /analyse](#6-der-befehl-analyse)
7. [Backtesting](#7-backtesting)
8. [Konfiguration im Detail](#8-konfiguration-im-detail)
9. [Logging](#9-logging)
10. [Tests](#10-tests)
11. [Bekannte Grenzen](#11-bekannte-grenzen)

---

## 1. Was der Bot macht

```
Tradovate WebSocket ──► Tick-Aggregation ──► rollierender Kerzenpuffer
                                                      │
                                                      ▼
                            RSI(14) · SMA(20/50) · Session-VWAP · ATR
                            Vortageshoch/-tief · Flaggen-Heuristik
                                                      │
                    ┌─────────────────┬───────────────┴──────────────┐
                    ▼                 ▼                              ▼
          Alarm-Bedingungen    /analyse (Telegram)          strukturiertes Log
          + Cooldown/Tageslimit  + Swings/Zonen/Trend        (logs/events.jsonl)
                    │                 │
                    └────────┬────────┘
                             ▼
                   Claude (nur Kennzahlen)
                   kurzer Prompt | ausfuehrlicher Prompt
                             │
                             ▼
                   Telegram ──(Fallback)──► Konsole + Log
```

Zwei Wege zum selben Kern: das **automatische** Alert-System reagiert auf
Bedingungen, der **On-Demand-Befehl** `/analyse` fragt jederzeit ab. Beide
nutzen dieselbe Indikator-Pipeline und denselben Claude-Client — sie
unterscheiden sich nur im System-Prompt und im Token-Budget.

**Alarm-Bedingungen** (alle in `config.yaml` an-/abschaltbar und mit
eigenem Cooldown):

| Schluessel | Ausloeser |
|---|---|
| `prev_day_high_cross` | Schlusskurs kreuzt das Vortageshoch von unten (mit Tick-Puffer) |
| `prev_day_low_cross` | Schlusskurs kreuzt das Vortagestief von oben |
| `rsi_exit_overbought` | RSI faellt von ≥ 70 wieder darunter |
| `rsi_exit_oversold` | RSI steigt von ≤ 30 wieder darueber |
| `flag_breakout` | Impuls → enge Range → Schlusskurs ausserhalb der Range |

Alle Bedingungen sind **Flankenerkennungen**: sie feuern beim Uebergang,
nicht dauerhaft, solange ein Zustand anhaelt.

**An Claude gehen ausschliesslich berechnete Kennzahlen** — keine Rohdaten,
keine Tickstroeme, keine Bilder. Was genau uebertragen wird, steht an einer
Stelle: `build_metrics_payload()` in `live_bot/ai/claude_client.py`
(mit Test).

---

## 2. Projektstruktur

```
Claude chart bot/
├── config.yaml                  Alle Schwellenwerte und Schalter
├── .env.example                 Vorlage fuer Secrets (nach .env kopieren)
├── requirements.txt
├── pytest.ini
│
├── common/                      Von Live-Bot UND Backtest genutzt
│   ├── config.py                config.yaml + .env laden und validieren
│   ├── logging_setup.py         Textlog + JSON-Lines-Log
│   ├── sessions.py              CME-Handelstag (18:00-ET-Rollover)
│   ├── indicators.py            RSI, SMA, ATR, VWAP, Vortagesmarken, Flagge
│   └── structure.py             Swing-Punkte, S/R-Zonen, Trend-Einschaetzung
│
├── live_bot/
│   ├── main.py                  Einstiegspunkt + CLI
│   ├── on_demand_report.py      /analyse: Bericht auf Zuruf
│   ├── tradovate/
│   │   ├── auth.py              Login, Token-Refresh, Penalty-Handling
│   │   ├── rest.py              Authentifizierter REST-Wrapper mit Retries
│   │   ├── contracts.py         Frontmonat-Aufloesung (NQ -> NQZ5)
│   │   └── md_socket.py         Market-Data-WebSocket (eine Verbindung)
│   ├── market/
│   │   ├── candles.py           Tick -> Kerze, rollierender Puffer
│   │   ├── feed.py              Reconnect mit Backoff + Historien-Nachladen
│   │   └── state.py             Kerzenpuffer -> MarketSnapshot
│   ├── alerts/
│   │   ├── conditions.py        Die fuenf Alarm-Bedingungen
│   │   └── cooldown.py          Cooldown je Bedingung + Tageslimit
│   ├── ai/claude_client.py      Anthropic Messages API (Alarm + Bericht)
│   └── notify/
│       ├── notifier.py          Telegram senden, mit Konsolen-Fallback
│       └── telegram_commands.py Telegram-Befehle empfangen (Long-Polling)
│
├── backtest/
│   ├── cli.py                   list / run / compare / optimize / fetch
│   ├── engine.py                Event-Engine (Ausfuehrung zur Folgekerze)
│   ├── metrics.py               Trefferquote, Profit-Faktor, DD, Sharpe
│   ├── splits.py                IS/OOS-Trennung + Overfitting-Schutzriegel
│   ├── compare.py               Strategievergleich, Export, Parametersuche
│   ├── data/                    Austauschbare Datenquellen
│   │   ├── base.py              DataProvider-Schnittstelle
│   │   ├── csv_provider.py
│   │   └── tradovate_provider.py
│   └── strategies/
│       ├── base.py              Regel-Objekte (Rule, AllOf, CrossesAbove, ...)
│       └── library.py           Fertige Strategien
│
├── docs/
│   └── BACKTESTING_ENTSCHEIDUNG.md   backtesting.py vs. vectorbt vs. eigen
│
└── tests/
```

**Der wichtigste Baustein ist `common/indicators.py`.** Live-Bot und
Backtest rufen dieselbe Funktion auf. Damit ist ausgeschlossen, dass der
Backtest andere Zahlen sieht als der laufende Bot — der teuerste Fehler in
Projekten dieser Art.

---

## 3. Installation

Auf diesem Rechner liegt Python 3.14 unter dem Python Install Manager:
`C:\Users\lm130\AppData\Local\Python\bin\python.exe`. Der Name `python` ist
in der PATH-Variable nur der Microsoft-Store-Platzhalter — deshalb einmal
den vollen Pfad verwenden:

```bash
C:\Users\lm130\AppData\Local\Python\bin\python.exe -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Danach reicht im aktivierten venv wieder `python`.

Das venv ist bereits angelegt und die Abhaengigkeiten sind installiert
(pandas 3.0.5, numpy 2.5.1, anthropic 0.120.2, websockets 17.0, …). Pruefen:

```bash
.venv\Scripts\python.exe -m pytest
# -> 124 passed
```

### Sofort ausprobieren, ohne Zugangsdaten

Unter `data/DEMO_1m.csv` liegt ein **synthetischer** Datensatz
(25 Handelstage NQ-aehnlicher 1-Minuten-Bars, Zufallspfad). Er ist nur zum
Ausprobieren der Backtest-CLI da — aus den Ergebnissen darf man
selbstverstaendlich nichts ueber echte Strategien ableiten:

```bash
.venv\Scripts\python.exe -m backtest.cli compare --symbol DEMO --csv data\DEMO_1m.csv
```

---

## 4. Einrichtung

### 4.1 Secrets

```bash
copy .env.example .env
```

Dann `.env` ausfuellen. Die Datei steht in `.gitignore` und darf niemals
committet werden.

| Variable | Woher |
|---|---|
| `TRADOVATE_USERNAME` / `TRADOVATE_PASSWORD` | Dein Tradovate-Login |
| `TRADOVATE_CID` / `TRADOVATE_SECRET` | Tradovate API Access Portal (`Application Access`) |
| `TRADOVATE_DEVICE_ID` | Frei waehlbar, aber **stabil lassen** — Tradovate bindet Tokens daran |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | Von `@BotFather` in Telegram |
| `TELEGRAM_CHAT_ID` | `https://api.telegram.org/bot<TOKEN>/getUpdates` aufrufen, nachdem du dem Bot geschrieben hast |

### 4.2 Benachrichtigungsweg testen

Ohne Tradovate-Verbindung, kostet nichts:

```bash
python -m live_bot.main --test-notification
```

Kommt die Nachricht in Telegram an, ist der Weg frei. Fehlen die
Telegram-Variablen, landet sie auf der Konsole — das ist der eingebaute
Fallback, kein Fehler.

### 4.3 Demo zuerst

`config.yaml` steht ab Werk auf:

```yaml
tradovate:
  environment: demo
  allow_live_environment: false
```

Die Live-Umgebung ist **doppelt** gesichert: `allow_live_environment: true`
in der `config.yaml` **und** das Flag `--i-know-this-is-live` beim Start.
Beides fehlt absichtlich in der Standardkonfiguration.

---

## 5. Live-Bot starten

```bash
# Demo-Umgebung, Frontmonat-NQ wird automatisch ermittelt
python -m live_bot.main

# anderes Symbol/Intervall: in config.yaml unter "market" setzen

# Live-Umgebung (erst nach ausdruecklicher Freigabe in der config.yaml)
python -m live_bot.main --environment live --i-know-this-is-live
```

Beenden mit `Strg+C`.

**Was beim Start passiert**

1. Login bei Tradovate, Token merken (wird 5 Minuten vor Ablauf erneuert).
2. Frontmonat-Kontrakt aufloesen (`NQ` → z.B. `NQZ5`). Feste Vorgabe ueber
   `market.contract_override`.
3. Market-Data-WebSocket oeffnen, letzte 300 Kerzen als Historie laden
   (damit RSI/SMA sofort belastbar sind), Quotes abonnieren.
4. Ticks zu Kerzen aggregieren; bei jedem Kerzenschluss Indikatoren neu
   rechnen und Bedingungen pruefen.

**Wenn die Verbindung abbricht**

Der Feed verbindet mit exponentiellem Backoff (2s → 4s → 8s … max 120s,
mit Jitter) neu, laedt die Historie nach — womit die entstandene Luecke
geschlossen wird — und abonniert erneut. Zusaetzlich gilt: kommen laenger
als `stale_data_timeout_seconds` (Standard 90s) gar keine Daten an, wird
die Verbindung aktiv verworfen und neu aufgebaut. Ein stiller Stillstand
ist damit ausgeschlossen.

---

## 6. Der Befehl /analyse

Jederzeit per Telegram abrufbar — unabhaengig davon, ob gerade eine
Alarm-Bedingung erfuellt ist:

```
/analyse            Bericht zum laufenden Symbol
/analyse NQ         Bericht zu einem anderen Produkt (Frontmonat)
/analyse ESZ5       Bericht zu einem konkreten Kontrakt
/help               Kurze Befehlsuebersicht
```

### Was passiert dabei

1. **Indikatoren neu rechnen** — dieselbe `compute_indicators`-Funktion wie
   im Alert-System und im Backtest. RSI(14), SMA20/50, Session-VWAP,
   Vortageshoch/-tief, Konsolidierungs-Heuristik.
2. **Zusaetzlich** (`common/structure.py`):
   - **ATR(14)** als Volatilitaetsmass — dient zugleich als Bezugsgroesse
     fuer Stop-Abstaende und Zonenbreiten
   - **Unterstuetzungs-/Widerstandszonen** aus bestaetigten Swing-Punkten
     der letzten `swing_lookback` Kerzen. Nahe beieinanderliegende Swings
     werden zu einer Zone zusammengefasst, mit Anzahl der Beruehrungen.
   - **Trend-Einschaetzung** aus Lage zur SMA50 und Steigung der SMA20.
     Die Steigung wird in ATR pro Kerze normiert — sonst waere derselbe
     Schwellwert fuer NQ und ES nicht sinnvoll.
3. **Claude-Aufruf** mit ausfuehrlicherem System-Prompt und groesserem
   Token-Budget (`claude.report_max_tokens`, Standard 4000).
4. **Antwort** als Telegram-Nachricht, bei Bedarf automatisch in mehrere
   Teile aufgeteilt (Telegram-Limit sind 4096 Zeichen).

### Aufbau des Berichts

Der Prompt fordert genau diese Abschnitte an:

| Abschnitt | Inhalt |
|---|---|
| `LAGE` | Trend oder Seitwaerts, Lage zu VWAP/SMA20/SMA50, RSI, Position in der Tagesspanne |
| `STRUKTUR` | Naechste Zonen mit Zahlen, Abstand und Anzahl der Tests |
| `SZENARIO A` / `B` | Zwei gegenlaeufige Wenn-Dann-Szenarien mit Invalidierungspunkt |
| `MARKEN` | Einstiegszone (Spanne), Stop mit Herleitung, Ziel, Risiko/Chance in Punkten **und** USD je Kontrakt, CRV |
| `EINSCHAETZUNG` | Welche Richtung die Struktur eher stuetzt — als Szenario formuliert |

**Was der Prompt ausdruecklich verbietet:** direkte Handlungsanweisungen
("kaufe", "verkaufe", "du solltest"), Empfehlungen zur Kontraktanzahl oder
Positionsgroesse, sowie Prozentangaben zu Wahrscheinlichkeiten, die die
Daten nicht hergeben. Der Punktwert wird mitgeschickt, damit das Risiko in
USD **je einzelnem Kontrakt** beziffert werden kann — die Stueckzahl bleibt
deine Entscheidung. Ergibt sich kein CRV von mindestens 1:1.5, soll der
Bericht das sagen statt Marken zu erzwingen.

Am Ende steht immer: *"Dies ist keine Anlageberatung. Marktbedingungen
koennen sich schnell aendern — pruefe alle Marken selbst am Chart."* Fehlt
der Satz in der Antwort, ergaenzt ihn der Code.

### Datenherkunft

| Anfrage | Quelle | Dauer |
|---|---|---|
| `/analyse` oder `/analyse NQ` bei laufendem NQZ5 | Live-Puffer im Speicher | sofort, kein Netzaufruf |
| `/analyse ES` bei laufendem NQZ5 | Frontmonat aufloesen + `md/getChart` | einige Sekunden |

Der Kopf der Nachricht weist aus, welche Quelle verwendet wurde.

### Kostenbremse

Jeder Bericht ist genau ein Claude-Aufruf mit deutlich mehr Tokens als ein
Alarm. Zwei getrennte Bremsen (`on_demand` in der `config.yaml`):

- `cooldown_seconds` (Standard 60) — Mindestabstand zwischen zwei Berichten
- `max_reports_per_day` (Standard 50) — Tageslimit

Beide sind **unabhaengig** vom Alarm-Kontingent: ein Schwung `/analyse`
kann das Tageslimit der automatischen Alarme nicht aufbrauchen, und
umgekehrt.

### Sicherheit

Es werden ausschliesslich Nachrichten aus der konfigurierten
`TELEGRAM_CHAT_ID` verarbeitet. Jeder, der den Bot-Namen kennt, kann ihm
schreiben — solche Nachrichten werden verworfen und mit dem Event
`telegram.listener.rejected` protokolliert.

Beim Start wird der Telegram-Rueckstau uebersprungen. Sonst wuerde ein
Neustart alle waehrend der Downtime gesendeten `/analyse` auf einmal
abarbeiten, inklusive der zugehoerigen Claude-Aufrufe.

Faellt Claude aus (Timeout, Rate-Limit), kommt die Nachricht trotzdem — mit
dem berechneten Zahlenkopf und einem Hinweis, dass die Analyse fehlt.

---

## 7. Backtesting

### 7.1 Daten besorgen

```bash
# Von Tradovate in eine CSV ziehen (einmalig, schont das API-Kontingent)
python -m backtest.cli fetch --symbol NQZ5 --bars 5000
```

Alternativ eine eigene CSV nach `data/NQZ5_1m.csv` legen. Erwartete
Spalten: `timestamp,open,high,low,close,volume` (Zeitstempel ohne Zeitzone
werden als UTC gelesen).

### 7.2 Strategien ansehen und testen

```bash
# Welche Strategien gibt es?
python -m backtest.cli list

# Eine Strategie, getrennt nach In-Sample und Out-of-Sample
python -m backtest.cli run --symbol NQZ5 --strategy prev_day_breakout

# Mit anderen Parametern
python -m backtest.cli run --symbol NQZ5 --strategy prev_day_breakout \
    --param rsi_max=65 --param stop_loss_atr=1.0

# Mehrere Strategien nebeneinander (Tabelle + Equity-Chart + Trade-CSVs)
python -m backtest.cli compare --symbol NQZ5 \
    --strategy prev_day_breakout --strategy vwap_trend --strategy flag_breakout
```

`compare` schreibt nach `backtest_results/`:
`vergleich.csv`, `equity.png` und je Strategie/Zeitraum eine Trade-Liste.

### 7.3 Parametersuche — mit Schutzriegel

```bash
python -m backtest.cli optimize --symbol NQZ5 --strategy prev_day_breakout \
    --grid "rsi_max=60,65,70,75" --grid "stop_loss_atr=1.0,1.5,2.0" \
    --objective pnl_per_drawdown
```

Die Suche laeuft **ausschliesslich auf dem In-Sample-Zeitraum**. Danach
wird die beste Variante **einmal** out-of-sample geprueft und das
Verhaeltnis Ø-Trade OOS/IS ausgewiesen. Faellt es unter 0.5, gibt es eine
Overfitting-Warnung.

Der Schutz ist kein guter Vorsatz, sondern Code: jede Optimierung ruft
`assert_in_sample_only()` auf und bricht mit `OutOfSampleViolation` ab,
sobald auch nur eine Out-of-Sample-Kerze im Datensatz liegt.

### 7.4 Eigene Strategie schreiben

Strategien sind Kompositionen kleiner Regel-Objekte:

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

Als Spaltennamen sind alle Indikatoren aus `common/indicators.py`
verfuegbar: `close`, `rsi`, `sma_fast`, `sma_slow`, `vwap`, `atr`,
`prev_session_high`, `prev_session_low`, `prev_session_close`,
`flag_breakout_up`, `flag_breakout_down`, …

Fuer die CLI in `backtest/strategies/library.py` unter `STRATEGY_LIBRARY`
eintragen.

### 7.5 Berechnete Kennzahlen

Trefferquote · Profit-Faktor · Netto-P&L · Ø Gewinn/Verlust je Trade ·
Erwartungswert · Anzahl Trades · max. Drawdown (absolut und relativ) ·
laengste Verluststraehne · Ø Haltedauer · Marktexposition · Sharpe Ratio.

**Zur Sharpe Ratio bei Intraday-Futures:** Die klassische Formel setzt eine
Rendite auf eingesetztes Kapital voraus. Bei Futures ist das eingesetzte
Kapital eine Margin-Entscheidung, keine Eigenschaft der Strategie —
dieselben Trades ergeben je nach Kontogroesse voellig verschiedene
"Renditen". Deshalb wird standardmaessig `sharpe_pnl` ausgewiesen (auf
taegliche P&L in USD, kapitalunabhaengig). `sharpe_on_capital` gibt es nur,
wenn du ein Startkapital angibst. Bei wenigen Trades sind beide wenig
aussagekraeftig — `trades`, `profit_factor` und `max_drawdown` sind hier die
belastbareren Groessen.

### 7.6 Ausfuehrungsmodell

- Regeln werden auf dem **Schlusskurs** ausgewertet, ausgefuehrt wird zur
  **Eroeffnung der Folgekerze**. Look-ahead ist damit strukturell
  ausgeschlossen (dafuer gibt es einen Test).
- Stop und Ziel greifen **innerhalb** der Kerze ueber High/Low.
- Werden beide in derselben Kerze beruehrt, gilt der **Stop** — aus OHLC
  laesst sich nicht rekonstruieren, was zuerst kam.
- Immer hoechstens **eine** Position.
- Kosten: Kommission je Seite plus Slippage je Seite in Ticks.

Warum eine eigene Engine statt `backtesting.py` oder `vectorbt`:
siehe [`docs/BACKTESTING_ENTSCHEIDUNG.md`](docs/BACKTESTING_ENTSCHEIDUNG.md).

---

## 8. Konfiguration im Detail

Alles Wesentliche steckt in `config.yaml`. Die wichtigsten Stellschrauben:

```yaml
market:
  product: NQ                    # Root-Symbol; Frontmonat wird ermittelt
  contract_override: null        # z.B. "NQZ5" fuer festen Kontrakt
  candle_interval_minutes: 1     # 1 oder 5
  candle_buffer_size: 3000       # siehe Kasten unten - nicht blind verkleinern
  warmup_bars: 2880
  tick_size: 0.25
  point_value: 20.0              # NQ = 20, ES = 50

indicators:
  flag:                          # Konsolidierungs-/Flaggen-Heuristik
    impulse_lookback: 20         # Kerzen, ueber die der Impuls gemessen wird
    impulse_min_atr: 2.5         # Impuls muss so viele ATR gross sein
    consolidation_lookback: 10   # Laenge der engen Range
    consolidation_max_atr: 1.2   # Range darf hoechstens so viele ATR sein
    breakout_buffer_atr: 0.1     # Puffer fuer den Ausbruch

alerts:
  default_cooldown_minutes: 30
  max_alerts_per_session: 20     # Tageslimit; 0 = unbegrenzt

claude:
  model: claude-sonnet-5
  max_tokens: 2000               # deckelt Denk- UND Antworttokens (Alarm)
  effort: low
  report_max_tokens: 4000        # /analyse braucht mehr Raum
  report_effort: medium

on_demand:
  cooldown_seconds: 60           # Mindestabstand zwischen zwei /analyse
  max_reports_per_day: 50        # eigenes Kontingent, getrennt vom Alarm
  swing_strength: 3              # Kerzen links/rechts fuer ein Swing-Extrem
  swing_lookback: 120            # Fenster fuer die Zonensuche
  max_zones: 3                   # Zonen je Seite
  zone_merge_atr: 0.5            # Swings naeher als X*ATR = eine Zone
```

> **`candle_buffer_size` nicht blind verkleinern.**
> Vortageshoch und -tief brauchen die komplette Vorsession **plus** die
> laufende. Eine CME-Globex-Session dauert 23 Stunden, also 2 × 23 × 60 =
> **2760 Ein-Minuten-Kerzen**. Ist der Puffer kleiner, bleiben die
> Vortagesmarken dauerhaft leer und die Alarme `prev_day_high_cross` /
> `prev_day_low_cross` loesen **nie** aus — ohne jede Fehlermeldung.
> Der Bot prueft das beim Start und verweigert den Dienst mit einer
> erklaerenden Meldung, statt still nichts zu melden. Bei 5-Minuten-Kerzen
> genuegen 552 Kerzen (z.B. 700).
> Kosten: die Indikatorberechnung ueber 3000 Kerzen dauert rund **35 ms**
> und laeuft einmal pro Kerzenschluss — das faellt nicht ins Gewicht.

**Zu `max_tokens`:** Claude Sonnet 5 denkt standardmaessig adaptiv, und
`max_tokens` begrenzt Denk- und Antworttokens zusammen. Zu knapp gesetzt
wird die Antwort mittendrin abgeschnitten. 2000 ist bei `effort: low`
komfortabel; der Bot erkennt eine Abschneidung und protokolliert sie.

**Zum Tageslimit:** `max_alerts_per_session` bremst nicht nur die
Benachrichtigungsflut, sondern deckelt auch die Claude-API-Kosten. Jeder
Alarm ist genau ein API-Aufruf.

---

## 9. Logging

Zwei Dateien parallel in `logs/` (rotierend, je 10 MB, 5 Generationen):

| Datei | Zweck |
|---|---|
| `bot.log` | Menschenlesbar, fuer den Blick zwischendurch |
| `events.jsonl` | Eine JSON-Zeile je Ereignis, maschinell auswertbar |

Jedes Ereignis hat einen Typ (`event`) und einen strukturierten Payload.
Wichtige Typen: `alert.triggered`, `alert.suppressed.cooldown`,
`claude.response`, `claude.error`, `notify.telegram.sent`,
`notify.telegram.failed`, `feed.reconnect_scheduled`, `md.disconnected`.

Auswertung, z.B. alle Trigger eines Tages:

```bash
python -c "import json;[print(json.loads(l)['payload']) for l in open('logs/events.jsonl',encoding='utf-8') if '\"alert.triggered\"' in l]"
```

Claude-Antworten stehen im Volltext im Log (`claude.response` →
`response_text`) — damit laesst sich im Nachhinein nachvollziehen, was zu
welchem Zeitpunkt gemeldet wurde.

---

## 10. Tests

```bash
python -m pytest              # alles
python -m pytest -v           # ausfuehrlich
python -m pytest tests/test_engine.py
```

Abgedeckt sind unter anderem:

- RSI/SMA/ATR gegen bekannte Randfaelle, VWAP-Reset zum Sessionwechsel,
  Vortagesmarken ueber den 18:00-ET-Rollover
- Flaggen-Heuristik: erkennt den konstruierten Ausbruch, meldet auf reinem
  Seitwaerts nichts
- Engine: kein Look-ahead, Ausfuehrung zur Folgekerze, Stop vor Ziel,
  Zeitstop, Sessionende, nur eine Position
- Kennzahlen: Profit-Faktor inkl. Randfaellen, Drawdown, Verluststraehne
- IS/OOS: chronologische Teilung, `OutOfSampleViolation` beim Fehlgriff
- Alarme: Flankenerkennung, Tick-Puffer, Cooldown, Tageslimit
- Claude-Payload: enthaelt nur Kennzahlen, System-Prompt verbietet
  Handelsempfehlungen und verlangt den Disclaimer
- Marktstruktur: Swing-Erkennung (auch der Randfall "letzte Kerzen koennen
  noch kein bestaetigtes Extrem sein"), Zonen-Zusammenfassung, Trend
- `/analyse`: Befehls-Parsing inkl. `/analyse@BotName`, Rate-Limiting,
  kompletter Berichtspfad ohne Netz, Aufteilung langer Nachrichten
- Konfiguration: zu kleiner Kerzenpuffer wird beim Start abgefangen

Die Netzwerkschichten (WebSocket, REST, Telegram, Anthropic) sind bewusst
nicht mit Mocks nachgebaut — dort testet man sonst vor allem die eigenen
Mocks. Sie sind stattdessen so gebaut, dass jeder Fehler abgefangen wird
und protokolliert statt eskaliert.

---

## 11. Bekannte Grenzen

**Tradovate als Datenquelle.** Tradovate ist ein Broker-Feed, kein
Datenanbieter. Wie weit die Historie zurueckreicht, haengt am Datenabo, und
`md/getChart` liefert pro Anfrage eine begrenzte Anzahl Bars. Fuer
mehrjaehrige Minutenhistorie ist ein spezialisierter Anbieter besser —
genau deshalb ist die Datenquelle ueber `DataProvider` austauschbar.

**Kontraktrollover.** Ein zusammengesetzter Frontmonat-Chart hat an den
Rolltagen Preissprunge. Wer ueber Rollover hinweg backtestet, sollte
back-adjusted Daten verwenden. Der Live-Bot rollt automatisch drei Tage vor
Verfall (`DEFAULT_ROLL_BUFFER_DAYS` in `contracts.py`).

**Frontmonat-Heuristik.** Der Kontrakt wird aus dem Namen abgeleitet
(CME-Monatscode + 3. Freitag). Fuer NQ/ES ist das korrekt; bei Produkten
mit abweichendem Verfallskalender bitte `market.contract_override` setzen.

**Volumen ausserhalb aktiver Phasen.** Liefert ein Quote keinen Trade,
sondern nur Bid/Ask, wird der Mittelkurs mit Volumen 0 verwendet. Die
Kerzen bleiben damit lueckenlos, ohne dass Volumen erfunden wird — der
VWAP ignoriert solche Bars entsprechend.

**Die Flaggen-Heuristik ist eine Heuristik.** "Impuls, dann enge Range,
dann Ausbruch" ist kein bestaetigtes Chartmuster. Die Schwellenwerte sind
Startwerte, keine Empfehlung; sie gehoeren auf deinen Daten kalibriert.

**Prop-Firm-Regeln sind nicht abgebildet.** Tageslimits, maximaler
Drawdown, Konsistenzregeln von Lucid Trading pruefft dieses Projekt nicht.
Es beobachtet den Markt, nicht dein Konto.

**Zonen sind Swing-Punkte, keine geprueften Niveaus.** Die Unterstuetzungs-
und Widerstandszonen entstehen rein mechanisch aus lokalen Extrema der
letzten `swing_lookback` Kerzen. Sie kennen weder Volumenprofile noch
runde Marken, Eroeffnungspreise oder uebergeordnete Zeitebenen. Eine Zone
mit einer einzigen Beruehrung ist kaum mehr als ein Zufallshoch — die
Anzahl der Beruehrungen steht deshalb in jedem Bericht mit dabei.

**`warmup_bars: 2880` ist eine grosse Historienanfrage.** Ob Tradovate sie
in einem Stueck beantwortet, haengt am Datenabo. Kommt weniger zurueck,
laeuft der Bot trotzdem weiter — die Vortagesmarken stehen dann erst zur
Verfuegung, wenn der Puffer im laufenden Betrieb voll ist. Das Log zeigt
unter `md.history.loaded`, wie viele Bars tatsaechlich ankamen.
