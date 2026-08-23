# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Kontextdateien — zuerst lesen, am Ende pflegen

**Vier** Dateien bilden das Projektgedächtnis (seit 23.08.2026; vorher zwei).
**Zu Beginn einer Aufgabe lesen**, bevor du Code änderst:

| Datei | Inhalt |
|---|---|
| `CODE_CHAT_KONTEXT.md` | **WIE und WIE WEIT**: Architektur, Module, Implementierungsstand, Blocker, Bugs mit Fundstelle, Tests, verworfene Ansätze |
| `NORMALER_CHAT_KONTEXT.md` | **WAS und WARUM**: Ziele, Anforderungen, Nutzerpräferenzen, Kostenrahmen, Etappen A–F, **offene Fragen an Laurin** (Abschnitt 18) |
| `MASTERPLAN.md` | **WOHIN**: Zielarchitektur, Market Intelligence, Research-Engine, Etappen G–L |
| `ETAPPE_C_SPEZIFIKATION.md` | verbindliche Vorgabe der Ideen-Protokollierung |

Alle werden vom Nutzer zusätzlich als Kontext in ein Claude-Projekt geladen.
Sie müssen deshalb **ohne diesen Chatverlauf verständlich** bleiben.

> **Override vom 23.08.2026, geht allen älteren Angaben vor:** Das Projekt
> arbeitet **ausschließlich mit MNQ und NinjaTrader 8**. Kein MGC, kein
> Tradovate, keine Multi-Instrument-Architektur. Zum verbliebenen
> MGC-Register-Eintrag siehe `NORMALER_CHAT_KONTEXT.md` 18.2 — **Entscheidung
> steht aus**.

**Am Ende einer Aufgabe prüfen und selbständig aktualisieren**, wenn dauerhaft
relevantes Wissen entstanden ist:

- **`CODE_CHAT_KONTEXT.md`** bei: geändertem Implementierungsstand, neuen oder
  entfernten wichtigen Dateien, Architekturänderungen, technischen Entscheidungen,
  verworfenen Ansätzen, Bugs mit Ursache und Lösung, Tests und Backtests mit
  Ergebnissen, neuen Einschränkungen, neuen Blockern.
  **Das Datum in der Kopfzeile mitziehen.**
- **`NORMALER_CHAT_KONTEXT.md`** nur bei Änderungen an Zielen, Anforderungen,
  Etappen-Status oder dauerhaften Entscheidungen.
- **`MASTERPLAN.md`** nur bei Änderungen an der Zielarchitektur oder der
  Etappenreihenfolge — nicht bei jedem Baufortschritt.

`PROJECT_CONTEXT.md`, `CURRENT_STATE.md`, `DECISIONS.md` und
`PROJEKTKONTEXT_UEBERGABE.md` waren Vorgängerdateien und existieren nicht mehr.
`PROMPT_CLAUDE_CODE_ETAPPE_C.md` ist am 23.08.2026 entfallen (unreferenziert und
überholt). **Nicht neu anlegen.**

**Nicht** dokumentiert werden Kleinigkeiten, Formatierungen oder Zwischenstände.
Die Dateien sind kein Git-Diff und kein Chatprotokoll.

**Bei Widersprüchen zwischen Dokumentation und Code:** Der Code ist die Wahrheit
über den *aktuellen Implementierungsstand*; die Kontextdateien sind die Wahrheit
über *historische Entscheidungen und Gründe*. Widerspruch nicht stillschweigend
auflösen — feststellen, dokumentieren, den Nutzer informieren.

## Projektgrenze

Read-only by design. Das Projekt liest Marktdaten, rechnet und protokolliert —
es gibt **keinen Order-Endpunkt, keine Positionsverwaltung, kein Lesen von
Kontodaten**, und das ist eine bewusste Entscheidung des Nutzers, keine offene
Lücke. Nicht unaufgefordert ergänzen oder vorschlagen, auch nicht als inertes
Interface; bei Aufgaben, die daran rühren, vorher nachfragen.

*Struktureller Schutz:* `ClaudeBridge.cs` ist ein NinjaTrader-**Indikator**, und
ein Indikator kann dort keine Orders platzieren.

**Kosten:** Nichts im Projekt ruft die Anthropic-API auf. Interpretiert wird
ausschließlich in der Claude-Desktop-Unterhaltung über das bestehende Abo. Seit
dem 22.08.2026 prüft `test_kein_modul_im_projekt_erreicht_die_anthropic_api`
das **repo-weit**.

## Befehle

`python` im PATH ist auf diesem Rechner nur der Microsoft-Store-Platzhalter.
Immer das venv des Projekts verwenden:

```bash
.venv\Scripts\python.exe -m pytest                          # alle Tests (aktuell 380)
.venv\Scripts\python.exe -m pytest tests/test_engine.py      # eine Datei
.venv\Scripts\python.exe -m pytest -k lookahead -v           # einzelne Tests nach Namensmuster
.venv\Scripts\python.exe -m pytest tests/test_ideas.py::test_deviation_reentry_feuert_nur_beim_uebertritt
```

Neu aufsetzen (der Interpreter liegt unter dem Python Install Manager):

```bash
C:\Users\lm130\AppData\Local\Python\bin\python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Betrieb und Backtest:

```bash
.venv\Scripts\python.exe -m ntbridge                            # Empfänger für NT8-Kerzen
.venv\Scripts\python.exe -m mcp_server.cli snapshot --symbol MNQ  # Terminal-Dump
.venv\Scripts\python.exe -m ideas --probelauf                   # Ideen erkennen, nichts schreiben
.venv\Scripts\python.exe -m ideas                               # Protokollierungslauf
.venv\Scripts\python.exe pruefe_datenluecken.py                 # Lücken in der Kerzenabdeckung
.venv\Scripts\python.exe -m backtest.cli list
.venv\Scripts\python.exe -m backtest.cli compare --symbol DEMO --csv data\DEMO_1m.csv
.venv\Scripts\python.exe -m backtest.cli optimize --symbol DEMO --csv data\DEMO_1m.csv \
    --strategy vwap_trend --grid "stop_loss_atr=1.0,1.5,2.0"
.venv\Scripts\python.exe -m backtest.cli walkforward --symbol DEMO --csv data\DEMO_1m.csv \
    --strategy vwap_trend --train-bars 2000 --test-bars 1000
```

`walkforward` rechnet mit **festen** Parametern und sucht im Trainingsfenster
nichts — es ist ein abschnittsweiser Out-of-Sample-Lauf, kein Walk-Forward mit
Optimierung, und der Bericht sagt das auch. Die Fenstergrößen haben bewusst
keinen Vorgabewert.

`data/DEMO_1m.csv` ist ein **synthetischer** Zufallspfad zum Ausprobieren der
CLI ohne Zugangsdaten — keine Grundlage für Aussagen über Strategien.

Skripte außerhalb der CLI brauchen `$env:PYTHONPATH = (Get-Location).Path`;
es gibt kein `pip install -e .`. In den Tests erledigt das `tests/conftest.py`.

Es gibt keinen Linter und keinen Formatter im Projekt.

**Unbeaufsichtigte Läufe in der Linux-Sandbox** (geplante Aufgaben, Cowork)
erreichen das Windows-venv nicht und können `pytest` dort nicht nachinstallieren.
Sie sind trotzdem nicht testlos:

```bash
python3 werkzeuge/pytest_linux.py            # ganze Suite
python3 werkzeuge/pytest_linux.py -k lookahead -v
```

Das Skript sammelt die reinen Python-Testabhängigkeiten aus dem Windows-venv,
ergänzt einen Minimalersatz für `exceptiongroup` und startet pytest darüber;
pandas und numpy kommen aus der Linux-Umgebung. Es schreibt nur nach `/tmp`.
Der Lauf ist eine **Gegenprobe, kein Ersatz** für den Windows-Lauf — er läuft
unter einem anderen Python und anderen pandas/numpy-Versionen.

Dasselbe gilt für den Rest des Projekts. `werkzeuge/python_linux.py` startet
ein beliebiges Modul in derselben Ersatzumgebung:

```bash
python3 werkzeuge/python_linux.py -m backtest.cli list
python3 werkzeuge/python_linux.py werkzeuge/dukascopy_export.py --minuten 5
```

Auch hier: Gegenprobe, kein Ersatz. Ergebnisse aus dieser Umgebung dürfen in
der Dokumentation nicht als Windows-Lauf ausgegeben werden (Invariante 10).

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

### 3. Der Kerzenvorrat muss zwei Sessions abdecken

Vortagesmarken brauchen die komplette Vorsession **plus** die laufende. Bei
5-Minuten-Kerzen sind das 2 × 276 = 552, bei Minutenkerzen 2760. Reicht
`ideas.bars` nicht, bleibt `prev_session_high` dauerhaft NaN und das Setup
`pdh_pdl_bruch` löst **nie** aus — ohne Fehlermeldung. `Config.validate()`
bricht deshalb beim Start ab, skaliert nach `ideas.timeframe`.

Diese Zusicherung hing bis zum 22.08.2026 an `market.candle_buffer_size` und
den Alarmen des Live-Bots. Der Alarmpfad ist entfernt, die Gefahr nicht — sie
ist mit der Ideen-Protokollierung nur umgezogen. Die Prüfung nicht
abschwächen; sie existiert wegen genau dieses stillen Ausfalls.

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

### 6. Ideen-Protokollierung ruft dieselbe Signal-Logik wie der Backtest

Invariante 1 gilt **auch für Signale**, nicht nur für Indikatoren. Jede
Setup-Familie in `ideas/setups.py` bildet auf eine `RuleStrategy` aus
`backtest/strategies/library.py` ab; `ideas/erkennung.py` wertet deren
Regel-Objekte über denselben `BarContext` aus wie die Engine. Es gibt hier
bewusst **keine** eigenen Erkenner — ein früherer Zwischenstand
(`ideas/detectors.py`) hatte sie, und genau deshalb wurde er ersetzt. Ein Test
verhindert die Rückkehr.

Stop und Ziel entstehen aus `stop_loss_atr`/`take_profit_atr` derselben
Strategie. Gespeichert wird zusätzlich `atr_referenz` — der tatsächliche
Einstieg ist die Eröffnung der Folgekerze, nicht der protokollierte
Schlusskurs, und ohne den ATR-Bezug wäre das R-Vielfache nicht rekonstruierbar.

**Kein Ergebnisfeld** in der Ideen-Tabelle: Gewinn und Verlust entstehen erst
bei der Auswertung unter einem bestimmten Regelwerk. Stünden sie im Log, gäbe
es zwei Wahrheiten.

`profil` (`sim_frei`/`lucid_challenge`/`lucid_funded`) dokumentiert die
**tatsächliche** Kontoumgebung und ist kein Steuerungsfeld; `rules`
(`none`/`lucid`/`both`) entscheidet beim **Auswerten**, was gerechnet wird.
Die beiden nie vermischen.

### 7. Filter haben drei Ausgänge, nicht zwei

`ideas/filters.py`: durch, abgelehnt — oder **nicht prüfbar**. Der dritte ist
der wichtige. Ist der Wirtschaftskalender nicht erreichbar, wäre „keine
Termine, also durch" eine Freigabe aus einem Ausfall heraus, und „ablehnen"
vernichtete den Datensatz. Die Idee wird protokolliert und als ungeprüft
vermerkt.

Aus demselben Grund kennt `ideas/kalender.py` eine **Abdeckungsgrenze**: Forex
Factory liefert im Wesentlichen die laufende Woche, für ältere Zeitpunkte
findet sich dort kein Termin — die Antwort wäre „kein Blackout" aus einer
Wissenslücke heraus. Jenseits von `ideas.filter.blackout_max_alter_tage` bleibt
die Frage offen.

**Auch gefilterte Ideen werden gespeichert.** Sonst ließe sich weder prüfen, ob
ein Filter zu scharf steht, noch beantworten, wie viele Ideen ein Regelwerk
verhindert hätte.

### 8. Zwei Logs, strikt getrennt

Tabelle `ideen` (regelbasiert, reproduzierbar) und `observations`
(freie Beobachtungen). `IdeenStore.lade_fuer_auswertung` ist der einzige Weg,
auf dem Etappe D an Daten kommt, und liest **nur** `ideen`. Ein Test prüft, dass
der Quelltext dieser Methode das Wort `observations` nicht einmal enthält —
sonst schliche sich nicht-reproduzierbares Rauschen in die Statistik.

### 9. Kerzen tragen die Schlusszeit

NinjaTrader beschriftet eine Kerze mit dem Ende ihres Fensters: die Ticks von
14:00:00 bis 14:00:59 ergeben die Kerze **14:01**. Wer eine neue Datenquelle
anbindet, muss das treffen (`resample(..., closed="left", label="right")`).

Bei den Dukascopy-Daten war es zunächst falsch, und **nichts an den Kursen hat
es verraten** — die Reihe sah lückenlos und plausibel aus. Aufgefallen ist es
erst im Kreuzvergleich gegen echte MNQ-Kerzen: r = −0,06 statt +0,95. Eine neue
Quelle deshalb immer auf **Änderungen** gegenprüfen, nicht auf Niveaus.

### 10. Handelskosten sind ein benanntes Profil, keine Zahl

`backtest/kosten.py`. Broker-Kommission, nicht verhandelbare Börsengebühren und
Slippage verhalten sich unterschiedlich und werden getrennt geführt. Slippage
ist **keine Gebühr**, sondern Ausführungsqualität — sie steckt im Füllkurs.

Jedes Profil trägt `quelle` und `ist_annahme`. Eine Aufschlüsselung, die nicht
belegt ist, bleibt `None`, statt mit plausiblen Zahlen gefüllt zu werden.

Ein Profilwechsel darf **nur** die Kosten ändern. Muss dafür die Strategie
angefasst werden, vergleicht man zwei verschiedene Strategien. Jeder Bericht
weist aus, womit gerechnet wurde.

### 11. Näherungen werden gekennzeichnet

Delta bleibt `null` mit Begründung statt geschätzt zu werden. Volume Profile
trägt `naeherung: true`. Die Dukascopy-Historie ist ein Index-CFD und kein
MNQ-Futures; die Einschränkung steht in der erzeugten Datei selbst (Tabelle
`herkunft`), und Backtests darauf sind **rein informativ**.

Eine Schätzung, die aussieht wie eine Messung, ist in diesem Projekt der
schwerste Fehler.

### 12. Konfiguration und Startprüfungen

Schwellenwerte ausschließlich in `config.yaml`, Secrets ausschließlich in
`.env` — nichts davon im Code. Umgebungs-Vorrang: CLI > `.env` > YAML.

**Abbrechende Startprüfungen** statt stiller Fehlfunktion: `Config.validate()`
bricht bei unbekanntem `ideas.profil` ab und wenn `ideas.bars` nicht für zwei
Sessions reicht (sonst blieben die Vortagesmarken NaN und `pdh_pdl_bruch` löste
nie aus). `ideas.setups.pruefe_konfiguration` bricht bei unbekanntem
Setup-Schlüssel ab.

`Backtester.run` bricht ab, wenn eine Strategie eine Spalte verlangt, die der
vorbereitete Datensatz nicht hat (`RuleStrategy.benoetigte_spalten`). Ohne die
Prüfung liest die Regel NaN, feuert nie und liefert **null Trades ohne
Fehlermeldung** — was sich liest wie „hat nicht gegriffen". Genau so war
`ib_breakout` seit jeher tot (`ib_high`/`ib_low` entstehen in
`compute_indicators` nicht); aufgefallen ist es erst am 23.08.2026 bei der
Basisvermessung, siehe `docs/BASISVERMESSUNG_2026-08-23.md`.

Diese Prüfungen nicht abschwächen — jede existiert wegen eines konkreten
stillen Ausfalls.

### 13. Erweiterungspunkte

- **Datenquellen**: `DataProvider` implementieren und in
  `backtest/data/__init__.py::create_provider` registrieren. `finalize()` in
  der Basisklasse übernimmt Normalisierung, Zeitfilter und Validierung.
- **Strategien**: aus Regel-Objekten komponieren (`backtest/strategies/base.py`)
  und in `library.py::STRATEGY_LIBRARY` eintragen. `BarContext` gibt bewusst nur
  die aktuelle und die vorherige Zeile frei — Look-ahead ist damit strukturell
  ausgeschlossen.
- **Setup-Familien**: Strategie in `library.py` anlegen, dann in
  `ideas/setups.py::SETUP_BIBLIOTHEK` eintragen — mit `zusatzspalten`, sonst
  bliebe das Setup bei fehlender Spalte stumm statt zu meckern. Einstiegsregeln
  müssen **Flanken** sein, keine Zustandsabfragen: eine Zustandsregel feuert auf
  jeder Kerze der Bewegung erneut und zählt dieselbe Bewegung vielfach.

## Konventionen

- Nutzertexte, Docstrings, Kommentare und Testnamen sind **deutsch**.
- Quelldateien sind **ASCII**: Umlaute als `ae`/`oe`/`ue` transliteriert.
  README und `docs/` verwenden echte Umlaute.
- Kommentare erklären das *Warum* einer Entscheidung, nicht das *Was* der
  nächsten Zeile.
- Schwellenwerte gehören in die Config, nicht in den Code.

## Weiterführend

- `README.md` — Einrichtung, NinjaTrader, MCP, Ideen-Protokollierung, Grenzen
- `ETAPPE_C_SPEZIFIKATION.md` — verbindliche Vorgabe für die
  Ideen-Protokollierung, inklusive der acht noch nicht gebauten Setup-Familien
- `docs/BACKTESTING_ENTSCHEIDUNG.md` — warum eine eigene Engine statt
  `backtesting.py` oder `vectorbt`; lies das, bevor du eine der beiden
  Bibliotheken vorschlägst
- `docs/BASISVERMESSUNG_2026-08-23.md` — die Strategiebibliothek über zehn
  Jahre Näherungshistorie, unverändert und ohne Optimierung; enthält den
  `ib_breakout`-Befund und zwei Schwächen der Kennzahlen
