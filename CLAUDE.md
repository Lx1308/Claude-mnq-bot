# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Kontextdateien — zuerst lesen, am Ende pflegen

**Zwei** Dateien bilden das Projektgedächtnis. **Zu Beginn einer Aufgabe lesen**,
bevor du Code änderst:

| Datei | Inhalt |
|---|---|
| `CODE_CHAT_KONTEXT.md` | **WIE und WIE WEIT**: Architektur, Module, Implementierungsstand, Blocker, nächste technische Schritte, Bugs mit Fundstelle, Tests, verworfene technische Ansätze |
| `NORMALER_CHAT_KONTEXT.md` | **WAS und WARUM**: Ziele, Anforderungen, Nutzerpräferenzen, Kostenrahmen, Kontostatus, Lucid-Regelwerk, Etappen A–F, Arbeitsteilung |

Beide werden vom Nutzer zusätzlich als Kontext in ein Claude-Projekt geladen.
Sie müssen deshalb **ohne diesen Chatverlauf verständlich** bleiben.

**Am Ende einer Aufgabe prüfen und selbständig aktualisieren**, wenn dauerhaft
relevantes Wissen entstanden ist:

- **`CODE_CHAT_KONTEXT.md`** bei: geändertem Implementierungsstand, neuen oder
  entfernten wichtigen Dateien, Architekturänderungen, technischen Entscheidungen,
  verworfenen Ansätzen, Bugs mit Ursache und Lösung, Tests und Backtests mit
  Ergebnissen, neuen Einschränkungen, neuen Blockern.
  **Das Datum in der Kopfzeile mitziehen.**
- **`NORMALER_CHAT_KONTEXT.md`** nur bei Änderungen an Zielen, Anforderungen,
  Etappen-Status oder dauerhaften Entscheidungen.

`PROJECT_CONTEXT.md` und `CURRENT_STATE.md` waren Vorgängerdateien und sind in
diesen beiden aufgegangen. Nicht neu anlegen.

**Nicht** dokumentiert werden Kleinigkeiten, Formatierungen oder Zwischenstände.
Die Dateien sind kein Git-Diff und kein Chatprotokoll.

**Bei Widersprüchen zwischen Dokumentation und Code:** Der Code ist die Wahrheit
über den *aktuellen Implementierungsstand*; die Kontextdateien sind die Wahrheit
über *historische Entscheidungen und Gründe*. Widerspruch nicht stillschweigend
auflösen — feststellen, dokumentieren, den Nutzer informieren.

## Projektgrenze

Read-only by design. Der Bot liest Marktdaten, rechnet, alarmiert und
kommentiert — es gibt **keinen Aufruf eines Tradovate-Order-Endpunkts**, und
das ist eine bewusste Entscheidung des Nutzers, keine offene Lücke. Order-
Routing, Positionsverwaltung oder Auto-Execution nicht unaufgefordert
ergänzen oder vorschlagen; bei Aufgaben, die daran rühren, vorher nachfragen.

## Befehle

`python` im PATH ist auf diesem Rechner nur der Microsoft-Store-Platzhalter.
Immer das venv des Projekts verwenden:

```bash
.venv\Scripts\python.exe -m pytest                          # alle Tests (aktuell 124)
.venv\Scripts\python.exe -m pytest tests/test_engine.py      # eine Datei
.venv\Scripts\python.exe -m pytest -k lookahead -v           # einzelne Tests nach Namensmuster
.venv\Scripts\python.exe -m pytest tests/test_on_demand.py::test_parse_command_mit_symbol
```

Neu aufsetzen (der Interpreter liegt unter dem Python Install Manager):

```bash
C:\Users\lm130\AppData\Local\Python\bin\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Live-Bot und Backtest:

```bash
.venv\Scripts\python.exe -m live_bot.main --test-notification    # Zustellweg prüfen, ohne Tradovate
.venv\Scripts\python.exe -m live_bot.main                        # Demo-Umgebung
.venv\Scripts\python.exe -m backtest.cli list
.venv\Scripts\python.exe -m backtest.cli compare --symbol DEMO --csv data\DEMO_1m.csv
.venv\Scripts\python.exe -m backtest.cli optimize --symbol DEMO --csv data\DEMO_1m.csv \
    --strategy vwap_trend --grid "stop_loss_atr=1.0,1.5,2.0"
```

`data/DEMO_1m.csv` ist ein **synthetischer** Zufallspfad zum Ausprobieren der
CLI ohne Zugangsdaten — keine Grundlage für Aussagen über Strategien.

Skripte außerhalb der CLI brauchen `$env:PYTHONPATH = (Get-Location).Path`;
es gibt kein `pip install -e .`. In den Tests erledigt das `tests/conftest.py`.

Es gibt keinen Linter und keinen Formatter im Projekt.

## Architektur: die tragenden Invarianten

Das Folgende ergibt sich nicht aus einer einzelnen Datei — hier steckt der
eigentliche Entwurf.

### 1. Eine einzige Indikator-Implementierung

`common/indicators.py::compute_indicators` wird von **beiden** Seiten
aufgerufen: vom Live-Bot bei jedem Kerzenschluss (`MarketState._recompute`)
und vom Backtest (`Backtester.prepare`). Das ist der Kern des Projekts —
niemals eine zweite Rechenlogik einführen, sonst testet der Backtest eine
andere Strategie als die, die live läuft.

Erwartetes Schema überall: `pd.DatetimeIndex` in UTC, aufsteigend, Spalten
`open, high, low, close, volume`. `validate_ohlcv` erzwingt das.

`common/structure.py` (Swings, S/R-Zonen, Trend) liegt **bewusst außerhalb**
von `compute_indicators`: es läuft nur punktuell beim `/analyse`-Bericht,
nicht bei jeder Backtest-Kerze.

### 2. Session-Modell (18:00-ET-Rollover)

Ein CME-Handelstag läuft 18:00 ET bis 17:00 ET. Ein Tick um 19:30 ET am
Montag gehört zum Handelstag *Dienstag*. Davon hängen Session-VWAP (setzt
täglich zurück) und Vortageshoch/-tief ab.

`common/sessions.py` rechnet den Tageswechsel **auf dem Datum**, nicht auf
dem Zeitstempel — eine Addition von 24 h wäre an Zeitumstellungstagen um
eine Stunde daneben.

### 3. Der Kerzenpuffer muss zwei Sessions abdecken

Vortagesmarken brauchen die komplette Vorsession **plus** die laufende, also
2 × 23 × 60 = 2760 Ein-Minuten-Kerzen (`MarketConfig.bars_for_previous_session`).
Ist `candle_buffer_size` kleiner, bleibt `prev_session_high` dauerhaft NaN und
die Alarme `prev_day_high_cross` / `prev_day_low_cross` feuern **nie** — ohne
Fehlermeldung. `Config.validate()` bricht deshalb beim Start ab, sofern diese
Bedingungen aktiv sind. Diese Prüfung nicht abschwächen; sie existiert wegen
genau dieses stillen Ausfalls.

### 4. Backtest-Ausführungsmodell

- Regeln werden auf dem **Schlusskurs** ausgewertet, ausgeführt wird zur
  **Eröffnung der Folgekerze**. Look-ahead ist damit strukturell ausgeschlossen
  (`test_kein_lookahead_...` sichert das ab).
- Stop und Ziel greifen intrabar über High/Low. Bei beidem in derselben Kerze
  gilt der **Stop** — aus OHLC ist nicht rekonstruierbar, was zuerst kam.
- Immer höchstens eine Position; Zwangsschluss am Sessionende.
- Kosten über `CostModel` mit echtem Punktwert und Ticksize (NQ = 20 USD/Punkt,
  ES = 50). P&L ist USD, keine Punktzahl.

### 5. In-Sample/Out-of-Sample

`compare.prepare_split` rechnet die Indikatoren **einmal über die
Gesamthistorie** und schneidet erst danach. Würde man den OOS-Block isoliert
vorbereiten, hätten dessen erste ~50 Kerzen keinen gültigen SMA(50) und die
Strategie bliebe dort stumm — ein stiller Verlust an OOS-Zeitraum. Da alle
Indikatoren rückwärtsgerichtet sind, entsteht dabei kein Blick in die Zukunft.

Jede Parametersuche ruft `splits.assert_in_sample_only` auf und wirft
`OutOfSampleViolation`, sobald OOS-Daten im Datensatz liegen.

### 6. Zwei Claude-Pfade, ein Aufrufweg

`ClaudeCommentator.comment` (Alarm) und `.report` (`/analyse`) unterscheiden
sich nur in System-Prompt, `max_tokens` und `effort`; beide laufen durch
`_create()` mit derselben Fehler-, Refusal- und Truncation-Behandlung.

`build_metrics_payload` (Alarm) und `build_report_payload` (Bericht) sind die
**einzigen** Stellen, an denen Daten das Haus verlassen — ausschließlich
berechnete Kennzahlen, keine Rohdaten, keine Kerzenlisten, keine Bilder. Tests
prüfen die Schlüsselmenge; neue Felder dort bewusst hinzufügen.

Beide System-Prompts verbieten direkte Handelsempfehlungen und verlangen einen
Disclaimer; fehlt er in der Antwort, ergänzt ihn `_create`. Tests sichern diese
Zusagen einzeln ab — beim Umformulieren mitziehen.

Modell ist `claude-sonnet-5` (Nutzerwunsch). Sampling-Parameter wie
`temperature` sind auf diesem Modell **nicht erlaubt** (400). `max_tokens`
deckelt Denk- *und* Antworttokens zusammen, weil adaptives Denken
standardmäßig an ist.

### 7. Zustellung geht nie verloren

`Notifier.send` versucht Telegram und fällt bei jedem Fehler auf Konsole +
Log zurück. `send_long` teilt Texte über dem 4096-Zeichen-Limit an
Absatzgrenzen. Der Fallback-Pfad darf selbst nie werfen — er greift genau
dann, wenn ohnehin schon etwas schiefliegt.

### 8. `log_event` hat positions-only Parameter

`log_event(logger, event, message, /, *, level=…, **payload)`. Der `/` ist
Absicht: sonst kollidiert ein Payload-Feld namens `message` mit dem
Positionsparameter und wirft zur Laufzeit einen `TypeError` — ausgerechnet im
Fehlerpfad. Payload-Schlüssel dürfen deshalb beliebig heißen.

Zwei Senken parallel: `logs/bot.log` (lesbar) und `logs/events.jsonl` (eine
JSON-Zeile pro Event). Neue Ereignisse immer über `log_event` mit einem
Event-Namen im Schema `bereich.aktion`.

### 9. Async-Aufbau des Live-Bots

`LiveBot.run` startet drei Tasks: `feed` (Marktdaten), `candle-ticker`
(schließt Kerzen auch ohne Ticks) und optional `telegram-commands`. `self._lock`
serialisiert alles, was den `MarketState` anfasst.

Wichtig: `_live_state_snapshot` kopiert den Puffer **unter** dem Lock und gibt
ihn frei, bevor der mehrere Sekunden dauernde Claude-Aufruf startet. Neue
lange Operationen niemals unter dem Lock laufen lassen.

Netzwerkschichten fangen jeden Fehler ab und protokollieren ihn, statt ihn
eskalieren zu lassen — ein einzelner Fehler darf den Bot nie beenden.

### 10. Tradovate-Market-Data-Protokoll

Textbasiert, SockJS-ähnlich (`live_bot/tradovate/md_socket.py`): Frames mit
Präfix `o`/`h`/`a`/`c`, Requests als `<endpoint>\n<id>\n<query>\n<body>`,
Client-Heartbeat `[]` alle ~2,5 s (Pflicht). `MarketDataSocket` kapselt genau
**eine** Verbindung; Reconnect mit Backoff, Neu-Abonnieren und Historien-
Nachladen liegen eine Ebene höher in `market/feed.py`. Nach einem Ausfall wird
die Historie neu geladen, was die entstandene Datenlücke schließt.

### 11. Konfiguration und Live-Schutz

Schwellenwerte ausschließlich in `config.yaml`, Secrets ausschließlich in
`.env` — nichts davon im Code. Umgebungs-Vorrang: CLI > `.env` > YAML.

Die Live-Umgebung ist doppelt gesichert: `allow_live_environment: true` in der
`config.yaml` **und** `--i-know-this-is-live` beim Start. Beide Riegel
beibehalten.

### 12. Erweiterungspunkte

- **Datenquellen**: `DataProvider` implementieren und in
  `backtest/data/__init__.py::create_provider` registrieren. `finalize()` in
  der Basisklasse übernimmt Normalisierung, Zeitfilter und Validierung.
- **Strategien**: aus Regel-Objekten komponieren (`backtest/strategies/base.py`)
  und in `library.py::STRATEGY_LIBRARY` eintragen. `BarContext` gibt bewusst nur
  die aktuelle und die vorherige Zeile frei — Look-ahead ist damit strukturell
  ausgeschlossen.
- **Alarm-Bedingungen**: Prüfmethode in `ConditionEvaluator._checks` ergänzen,
  Schlüssel in `config.yaml` unter `alerts.conditions` anlegen. Alle Bedingungen
  sind Flankenerkennungen (Vergleich vorheriger/aktueller Snapshot), nicht
  Zustandsabfragen.

## Konventionen

- Nutzertexte, Docstrings, Kommentare und Testnamen sind **deutsch**.
- Quelldateien sind **ASCII**: Umlaute als `ae`/`oe`/`ue` transliteriert.
  README und `docs/` verwenden echte Umlaute.
- Kommentare erklären das *Warum* einer Entscheidung, nicht das *Was* der
  nächsten Zeile.
- Schwellenwerte gehören in die Config, nicht in den Code.

## Weiterführend

- `README.md` — Einrichtung, `/analyse`-Bericht, bekannte Grenzen
- `docs/BACKTESTING_ENTSCHEIDUNG.md` — warum eine eigene Engine statt
  `backtesting.py` oder `vectorbt`; lies das, bevor du eine der beiden
  Bibliotheken vorschlägst
