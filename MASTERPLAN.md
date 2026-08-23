# MASTERPLAN — Claude Chart Bot

**Stand: 23.08.2026** · Verfasst gegen den tatsächlichen Code auf `main`
(Commit `3ca5fb5`), nicht gegen die Dokumentation.

> **Was diese Datei ist:** ein Planungsdokument. Sie beschreibt, was gebaut
> werden *soll*, in welcher Reihenfolge und warum. Sie ist **keine**
> Arbeitsanweisung zum sofortigen Umsetzen. Welcher P0-Punkt zuerst dran ist,
> entscheidet Laurin — nicht die Session.
>
> **Verhältnis zu den bestehenden Kontextdateien:** `CODE_CHAT_KONTEXT.md`
> beschreibt den *Ist-Zustand* und die *Historie*; `NORMALER_CHAT_KONTEXT.md`
> die *Ziele und Randbedingungen*; `ETAPPE_C_SPEZIFIKATION.md` die verbindliche
> Vorgabe für die Ideen-Protokollierung. Diese Datei ersetzt keine davon —
> sie spannt den Bogen darüber und reicht zeitlich weiter.

---

## 0. Projekt-Override vom 22.08.2026 — gilt ab sofort

Drei Festlegungen aus dem Master-Auftrag setzen ältere Annahmen außer Kraft:

| Festlegung | Konsequenz |
|---|---|
| **MGC ist vollständig aus dem Projekt entfernt** — nicht „auf Anfrage", nicht „später wieder" | Instrument-Register, Kalender-Zuordnung, Kommentare und Tests, die MGC nennen, sind zu bereinigen. Siehe P0-2. |
| **Tradovate ist vollständig raus** | Der Code-Pfad ist entfernt; es stehen aber noch **zwei echte Reste** in ausführbarem Code (siehe Abschnitt 3). |
| **Fokus ausschließlich MNQ + NinjaTrader 8** | Kein Mehr-Instrument-Stream, kein zweiter Broker, keine zweite Datenanbindung im Livepfad. |

Diese drei Punkte sind **entschieden** und stehen im Folgenden nicht mehr zur
Diskussion.

---

## 1. Ist-Zustand

### 1.1 In einem Satz

Das Projekt liest echte MNQ-Kerzen aus NinjaTrader 8, berechnet daraus eine
umfangreiche, getestete Kennzahlenschicht, kann sie über einen MCP-Server als
Snapshot ausliefern und über eine eigene Backtest-Engine historisch prüfen —
**aber es hat bis heute keine einzige echte Handelsidee protokolliert**, und
damit fehlt die Datengrundlage für jede Aussage über Setup-Güte.

### 1.2 Zahlen

| Kennzahl | Wert |
|---|---|
| Python-Quelltext | ~17 800 Zeilen in 63 Dateien (inkl. Tests) |
| Tests | 342, grün |
| Module | `common/`, `backtest/`, `ideas/`, `mcp_server/`, `ntbridge/`, `ninjatrader/` |
| Echte MNQ-Kerzen (`data/ntbridge.sqlite3`) | seit 21.08.2026, laufend wachsend |
| Näherungshistorie (`data/dukascopy_nas100_1m.sqlite3`) | 3 179 672 Minutenkerzen, 2016-08-22 – 2026-08-21, 384 MB |
| Protokollierte Ideen (`data/ideas.sqlite3`) | **0** |

### 1.3 Etappenstand A–F

| Etappe | Inhalt | Stand |
|---|---|---|
| **A** | NinjaScript-Bridge `ClaudeBridge.cs` | abgeschlossen, live verifiziert |
| **B** | Empfänger, SQLite-Speicher, `NTBridgeBarSource` | abgeschlossen, mit echten Daten verifiziert |
| **C** | Ideen-Protokollierung | **gebaut, aber nicht in Betrieb** — 4 von 12 Setup-Familien, keine geplante Aufgabe eingerichtet |
| **D** | Auswertung (`evaluate_past_ideas`, `get_performance_report`) | kein Code — und **verfrüht**, solange C keine Daten liefert |
| **E** | Dauerbetrieb-Härtung | offen |
| **F** | Liefergegenstände | teilweise |

### 1.4 Der eine Satz, auf den es ankommt

**Der Engpass ist nicht Code, sondern Datenbestand.** Alles unterhalb von
„Etappe C läuft stündlich und schreibt Ideen" ist Vorarbeit ohne messbares
Ergebnis. Jeder Ausbau der Architektur, der diesen Engpass nicht auflöst,
verschiebt den Zeitpunkt der ersten belastbaren Aussage nach hinten.

---

## 2. Architektur des Ist-Zustands

### 2.1 Module

| Modul | Rolle | Zeilen (ca.) |
|---|---|---|
| `ninjatrader/ClaudeBridge.cs` | NT8-**Indikator**, POSTet Kerzenschlüsse an `localhost:8787` | — |
| `ntbridge/` | HTTP-Empfänger, Validierung, SQLite-Speicher (`BarStore`) | 430 + Empfänger |
| `common/indicators.py` | **die einzige Indikator-Implementierung** — `compute_indicators` / `compute_extended_indicators` | 471 |
| `common/structure.py` | Swings, S/R-Zonen, Trend, BOS/CHoCH, RSI-Divergenz — bewusst **außerhalb** von `compute_indicators` | 682 |
| `common/patterns.py` | Flagge, Doppeltop/-boden, Dreieck, Range-Kompression | — |
| `common/levels.py` | Preisniveaus, Abstände in Punkten **und** ATR-Vielfachen | — |
| `common/sessions.py` | 18:00-ET-Rollover, Session-Zuordnung auf dem **Datum** | — |
| `common/instruments.py` | Kontraktregister, Verfallsregeln | 380 |
| `common/config.py` | YAML + `.env`, **abbrechende** Startprüfungen | — |
| `backtest/engine.py` | Ausführungsmodell: Signal auf Close, Fill auf nächster Open | 322 |
| `backtest/strategies/` | Regel-Objekte, `BarContext` (nur aktuelle + vorherige Zeile) | 336 + Basis |
| `backtest/splits.py` | IS/OOS, `OutOfSampleViolation`, `walk_forward_windows` | 115 |
| `backtest/metrics.py` | Kennzahlen inkl. Drawdown, Konsekutivverluste | 234 |
| `backtest/compare.py` | Vergleich, Parametersuche, Export | 296 |
| `ideas/` | Erkennung, Filter, Kalender, Speicher, Nachvollzug | ~1 600 |
| `mcp_server/` | 3 Tools: `get_market_snapshot`, `get_event_risk`, `list_instruments` | ~1 100 |

### 2.2 Datenfluss (Ist)

```
NinjaTrader 8 (2 Charts je Instrument)
        │  ClaudeBridge.cs  (Indikator, kein Strategy — kann strukturell keine Order senden)
        ▼  HTTP POST localhost:8787
   ntbridge/receiver.py ──▶ validate_bar ──▶ BarStore (data/ntbridge.sqlite3)
        │
        ├──▶ mcp_server/bars.py ──▶ compute_indicators ──▶ snapshot.py ──▶ MCP-Tool
        │                                                       │
        │                                                       ▼
        │                                            Claude-Desktop-Unterhaltung
        │                                            (Interpretation, KEIN API-Aufruf)
        │
        └──▶ ideas/pipeline.py ──▶ erkennung.py (dieselben RuleStrategy-Objekte
                     │              wie der Backtest) ──▶ filters.py (3 Ausgänge)
                     ▼
              IdeenStore (data/ideas.sqlite3): Tabellen `ideen` und `observations`

Parallel, offline:
   data/DEMO_1m.csv (synthetisch)  ─┐
   Dukascopy NAS100-CFD (Näherung) ─┴─▶ CsvDataProvider ──▶ Backtester ──▶ Metrics
```

### 2.3 Die tragenden Invarianten

Sie stehen ausführlich in `CLAUDE.md`; hier nur, was für die Zielarchitektur
bindend bleibt:

1. **Eine einzige Indikator-Implementierung** für Live und Backtest.
2. **Session-Modell 18:00 ET**, gerechnet auf dem Datum.
3. **Kerzenvorrat deckt zwei Sessions ab** — sonst schweigt `pdh_pdl_bruch`
   lautlos.
4. **Signal auf Close, Fill auf nächster Open**; bei Stop und Ziel in derselben
   Kerze gilt der Stop.
5. **IS/OOS**: Indikatoren einmal über die Gesamthistorie, dann schneiden.
6. **Ideen-Protokollierung ruft dieselbe Signal-Logik** wie der Backtest.
7. **Filter haben drei Ausgänge**: durch / abgelehnt / **nicht prüfbar**.
8. **Zwei Logs, strikt getrennt**: `ideen` reproduzierbar, `observations` frei.
9. **Kerzen tragen die Schlusszeit.**
10. **Näherungen werden gekennzeichnet** — eine Schätzung, die aussieht wie
    eine Messung, ist der schwerste Fehler im Projekt.
11. **Schwellenwerte nur in `config.yaml`**, abbrechende Startprüfungen.

Diese elf Punkte sind **nicht verhandelbar** und gelten für jede neue
Komponente unverändert weiter.

---

## 3. Veraltete und widersprüchliche Komponenten

Gegen den Code geprüft am 23.08.2026. Getrennt nach *echtem Defekt* und
*bloßer Alterung des Textes*.

### 3.1 Echte Defekte in ausführbarem Code

| Fundstelle | Befund | Schwere |
|---|---|---|
| `backtest/cli.py:276` | `--provider` bietet weiterhin `choices=("csv", "tradovate")` an. Der Tradovate-Provider ist gelöscht; `create_provider` kennt nur `csv`. Der Aufruf bräche mit `DataProviderError` ab. **Dieselbe Klasse Fehler wie das bereits behobene `fetch`-Kommando** — kein Test ruft es auf. | mittel |
| `backtest/data/csv_provider.py:57` | Fehlermeldung an den Nutzer verweist auf „Historie von Tradovate herunterladen" — ein Weg, den es nicht mehr gibt. Führt den Nutzer in die Irre. | mittel |
| `backtest/data/__init__.py` | `create_provider` kennt **nur** `csv`. Der Dukascopy-Speicher mit 3,18 Mio. Kerzen ist damit über den normalen Backtest-Pfad **nicht erreichbar** — die Daten liegen da, die Engine kommt nicht dran. | **hoch** |
| `backtest/cli.py` | Kommandos: `list`, `run`, `compare`, `optimize`. **Kein `walkforward`** — `splits.walk_forward_windows` existiert, ist getestet und von der CLI aus nicht aufrufbar. Toter, aber korrekter Code. | mittel |

### 3.2 MGC — noch überall im Code

Der Override sagt „vollständig entfernt". Tatsächlich steht MGC noch an
mindestens acht Stellen:

- `common/instruments.py:205` — MGC ist als Instrument **registriert**
- `common/instruments.py:8,15` — Modul-Docstring begründet sich mit MGC
- `common/instruments.py:358` — MGC in der Instrumentenliste
- `common/config.py:203` — Kommentar „Kommt MGC dazu …"
- `common/levels.py:5`, `common/patterns.py:153`,
  `backtest/strategies/base.py:266` — MGC als Vergleichsbeispiel in
  Begründungen
- `mcp_server/calendar_provider.py:46` — Terminzuordnung „für MNQ und MGC"

`list_instruments` liefert MGC damit weiterhin aus. **Das ist ein
Widerspruch zwischen Vorgabe und Code**, kein Defekt im engeren Sinn — er ist
festgestellt, nicht stillschweigend aufgelöst (siehe `CLAUDE.md`,
„Bei Widersprüchen").

### 3.3 Nur gealterter Text — kein Handlungsbedarf

`common/contracts.py`, `backtest/data/base.py`, `mcp_server/bars.py`,
`mcp_server/context.py`, `ntbridge/__init__.py`, `config.yaml:165,303` nennen
Tradovate ausschließlich in ausdrücklich als historisch markierten Absätzen.
Das ist die vom Projekt **gewollte** *Warum*-Dokumentation. Nicht anfassen.

### 3.4 Auf der Platte, nicht in Git

Leerer Ordner `live_bot/` mit `__pycache__`-Resten in `ai/`, `alerts/`,
`market/`, `notify/`, `tradovate/`. Kein Quelltext, kein Import zeigt darauf.
**Aufräumen im Dateisystem gehört Laurin** — nicht ohne Ansage löschen.

---

## 4. Zielarchitektur

### 4.1 Leitgedanke

Der heutige Aufbau ist eine **Messkette**: Kerzen rein, Kennzahlen raus,
Interpretation im Chat. Die Zielarchitektur macht daraus einen **geschlossenen
Erkenntniskreislauf**: messen → Hypothese erzeugen → statistisch prüfen →
protokollieren → nachmessen → Abweichung erkennen → Hypothese verwerfen oder
härten.

Die drei neuen Blöcke — Market Intelligence, Research Engine, Regime Engine —
sind **keine neuen Rechenwege**. Sie sind Schichten *über* dem, was schon steht.
Invariante 1 gilt für sie unverändert: keine zweite Indikator- oder
Signalimplementierung, niemals.

### 4.2 Schichtenbild (Ziel)

```
┌──────────────────────────────────────────────────────────────────┐
│  Schicht 5 — Beobachtung                                         │
│  Live-Monitoring · Drift Detection · Health Checks               │
│  „Verhält sich die Strategie noch so wie im Test?"               │
├──────────────────────────────────────────────────────────────────┤
│  Schicht 4 — Erkenntnis                                          │
│  Research Engine: Discovery → Validation → OOS → Walk-Forward    │
│  Statistische Validierung (Multiple-Testing, Bootstrap)          │
├──────────────────────────────────────────────────────────────────┤
│  Schicht 3 — Kontext                                             │
│  Regime Engine (Volatilität, Trend/Range, Session, Event-Nähe)   │
│  Market Intelligence (Kalender, Makro, Terminstruktur)           │
├──────────────────────────────────────────────────────────────────┤
│  Schicht 2 — Merkmale                                            │
│  Feature Store: materialisierte Kennzahlen je (Instrument, TF, t)│
│  gespeist AUSSCHLIESSLICH aus compute_indicators / structure     │
├──────────────────────────────────────────────────────────────────┤
│  Schicht 1 — Rohdaten                                            │
│  ntbridge (MNQ live) · Dukascopy (Näherung, gekennzeichnet)      │
└──────────────────────────────────────────────────────────────────┘
        ▲                                                    │
        └──────── MCP-Server liest quer durch alle Schichten ─┘
```

### 4.3 Datenfluss (Ziel)

```
NT8 ──▶ ntbridge ──▶ BarStore
                        │
                        ▼
              ┌── Feature Store (materialisiert, versioniert) ──┐
              │   Schlüssel: (instrument, timeframe, ts)        │
              │   Quelle: compute_indicators + structure        │
              │   Feld: feature_set_version                     │
              └────────────────────────────────────────────────┘
                        │                         │
        ┌───────────────┘                         └───────────────┐
        ▼                                                         ▼
  Regime Engine                                          Research Engine
  regime(t) = f(ATR-Perzentil,                    Discovery ─▶ Validation
               ADX, Session, Event-Nähe)                 │        │
        │                                                 ▼        ▼
        │                                              IS-Fit   OOS-Test
        ▼                                                 │        │
  ideas/pipeline ──▶ IdeenStore                           ▼        ▼
        │            (+ regime-Feld an jeder Idee)   Walk-Forward · Bootstrap
        ▼                                                     │
  Etappe D: evaluate_past_ideas(rules=…)  ◀───────────────────┘
        │
        ▼
  Live-Monitoring / Drift Detection
  „erwartete Verteilung (aus OOS)  vs.  beobachtete Verteilung (aus ideen)"
```

---

## 5. Die neuen Komponenten im Einzelnen

### 5.1 Feature Store

**Problem, das er löst:** Heute werden Indikatoren bei jedem Snapshot, jedem
Ideenlauf und jedem Backtest neu gerechnet. Das ist bei 3,18 Mio. Kerzen der
teuerste Schritt und macht jede Parametersuche unnötig langsam. Zudem lässt
sich im Nachhinein nicht rekonstruieren, *mit welcher Fassung* der
Indikatorlogik eine Idee entstanden ist.

**Entwurf:**

- Eigene SQLite-Datei `data/features.sqlite3`, getrennt von Kerzen und Ideen.
- Primärschlüssel `(instrument, timeframe, ts)`, dazu `feature_set_version`.
- Befüllt **ausschließlich** durch `compute_indicators` /
  `compute_extended_indicators` / `structure` — kein eigener Rechenweg.
  Der Store ist ein **Cache mit Gedächtnis**, keine zweite Wahrheit.
- Inkrementell: nur neue Kerzen werden nachgerechnet, alte bleiben stehen.
- `feature_set_version` steigt, sobald sich eine Berechnung ändert. Alte Zeilen
  werden **nicht überschrieben**, sondern behalten ihre Version — sonst wäre
  eine Idee vom Vormonat nachträglich nicht mehr reproduzierbar.
- Herkunftstabelle analog zu `DukascopyStore._schreibe_herkunft`.

**Fallstrick, den er nicht einführen darf:** Ein Cache, der bei Lücken still
alte Werte liefert, wäre genau der Ausfall, gegen den das ganze Projekt
gebaut ist. Fehlende Zeilen müssen als **fehlend** durchgereicht werden
(`null` mit Begründung), nie als letzter bekannter Wert.

### 5.2 Regime Engine

**Problem:** Eine Setup-Statistik über alle Marktphasen hinweg mittelt
Trendphasen und Seitwärtsphasen zusammen. Genau das verwischt die einzige
Frage, die Laurin beantwortet haben will — *wann* trägt ein Setup.

**Entwurf:**

- Ein Regime ist eine **Klassifikation, keine Vorhersage**. Es beschreibt den
  Zustand bis einschließlich Kerze *t* — nie darüber hinaus.
- Dimensionen (alle aus vorhandenen Berechnungen):
  - **Volatilität**: ATR-Perzentil über rollierendes Fenster → niedrig / normal / hoch
  - **Richtung**: ADX-Regime (`snapshot.py::_adx_regime` existiert bereits) → Trend / Range
  - **Session**: Asien / Europa / US-Vorbörse / RTH / Nachbörse, über `common/sessions.py`
  - **Event-Nähe**: Abstand zum nächsten High-Impact-Termin, über `mcp_server/calendar_provider.py`
- Ergebnis: ein Tupel, das an **jede protokollierte Idee** geschrieben wird.
- Schwellen in `config.yaml` unter neuem Abschnitt `regime:`.
- **Kein Lookahead:** Perzentile werden über ein *rückwärts* geschlossenes
  Fenster gerechnet. Ein Perzentil über die Gesamthistorie wäre der klassische
  stille Lookahead — es würde eine Volatilität von 2019 danach beurteilen, was
  bis 2026 noch kam.

**Was die Regime Engine ausdrücklich nicht tut:** sie filtert keine Ideen. Sie
etikettiert sie. Ob ein Regime ein Setup ausschließt, entscheidet die
Auswertung in Etappe D — und letztlich Laurin.

### 5.3 Market Intelligence

Heute: `mcp_server/calendar_provider.py` (Forex Factory für Termine, FRED für
Ist-Werte), `event_risk`-Konfiguration, Blackout-Fenster ±15 min.

**Ausbaustufen:**

1. **Kalenderabdeckung ehrlich machen** — bereits gelöst über
   `ideas.filter.blackout_max_alter_tage` und den dritten Filterausgang.
   Bleibt so.
2. **Terminstruktur / Roll-Nähe**: Der MNQ-Roll verzerrt Kursniveaus. Das
   Instrument-Register kennt die Verfallsregel bereits; der Abstand zum Roll
   gehört als Merkmal in den Feature Store.
3. **Makro-Serien aus FRED** als *zusätzliche* Regime-Dimension — mit einer
   harten Randbedingung, siehe unten.

> **Lookahead-Falle bei Makrodaten — der wichtigste Punkt in diesem Abschnitt.**
> FRED-Serien werden **revidiert**. Der Wert, den FRED heute für März 2024
> ausliefert, ist nicht der Wert, der im März 2024 bekannt war. Wer die heutige
> Serie in einen Backtest von 2024 einsetzt, hat einen Lookahead, den *nichts an
> den Kursen verrät* — exakt die Fehlerklasse, die bei den Dukascopy-Daten schon
> einmal zugeschlagen hat (r = −0,06 statt +0,95).
>
> **Konsequenz:** Makrodaten kommen nur als **Vintage** (Erstveröffentlichung
> mit Veröffentlichungszeitstempel) in das System, oder gar nicht. FRED
> liefert das über ALFRED/`realtime_start`. Ist ein Vintage nicht beschaffbar,
> bleibt das Merkmal `null` mit Begründung — nach Invariante 10.

### 5.4 Research Engine

Der Kern des Ausbaus. Vier Stufen, strikt in dieser Reihenfolge; eine Hypothese,
die eine Stufe nicht besteht, geht **nicht** weiter.

| Stufe | Was passiert | Vorhandene Bausteine | Was fehlt |
|---|---|---|---|
| **1 Discovery** | Kandidatenparameter erzeugen | `compare.parameter_grid`, `optimize_in_sample` | Protokollierung *aller* getesteten Kombinationen (für Stufe 3) |
| **2 Validation** | In-Sample-Fit bewerten | `metrics.compute_metrics` | Mindestanforderungen als Config-Schwellen |
| **3 OOS** | Einmaliger Test auf ungesehenem Zeitraum | `splits.split_data`, `assert_in_sample_only` | **Zähler für „wie oft wurde OOS schon angefasst"** |
| **4 Walk-Forward** | Rollierende Wiederholung über die Historie | `splits.walk_forward_windows` (getestet!) | **CLI-Anbindung fehlt vollständig** |

**Der teuerste Fehler, den diese Engine verhindern muss:** Out-of-Sample ist
nur beim *ersten* Blick out-of-sample. Wer nach einem enttäuschenden
OOS-Ergebnis die Parameter ändert und erneut testet, hat den OOS-Zeitraum
faktisch zum In-Sample gemacht. `assert_in_sample_only` schützt heute gegen
das *versehentliche* Optimieren auf OOS-Daten, nicht gegen dieses
schrittweise Aufbrauchen.

**Vorschlag:** ein OOS-Zugriffszähler je (Strategie, Datensatz), persistent
gespeichert. Kein Verbot — eine **Sichtbarmachung**. Steht am Ergebnis
„OOS-Zugriff Nr. 7", ist die Zahl selbst die Warnung. Ein stiller Zähler wäre
sinnlos; ein hartes Verbot wäre bevormundend und würde umgangen.

### 5.5 Statistische Validierung

Heute liefert `metrics.py` Punktschätzer: Trefferquote, Profitfaktor, Erwartungswert,
Drawdown, maximale Verluststrecke. Das ist korrekt gerechnet und **beantwortet die
entscheidende Frage nicht**: ist der Unterschied zu „Zufall" größer als die
Streuung?

**Ausbau, in dieser Reihenfolge:**

1. **Konfidenzintervall statt Punktschätzer.** Bei 20 Trades und 55 %
   Trefferquote reicht das Intervall grob von 32 % bis 77 %. Laurins eigene
   Schwelle von 20 Ideen je Kategorie sollte im Ergebnis **sichtbar** neben dem
   Intervall stehen, damit die Zahl nicht mehr Gewissheit ausstrahlt, als sie
   trägt.
2. **Bootstrap über Trade-Reihenfolge** für Drawdown und Verluststrecken. Der
   beobachtete Maximaldrawdown ist eine *Stichprobe von eins*.
3. **Multiple-Testing-Korrektur.** Wer 200 Parameterkombinationen prüft, findet
   auch in Rauschen mehrere „signifikante". Die Discovery-Stufe muss die Zahl
   der Versuche mitliefern, damit diese Korrektur überhaupt möglich ist —
   deshalb steht sie oben unter Stufe 1 als Lücke.
4. **Benchmark „zufälliger Einstieg".** Gleiche Anzahl Trades, gleiche
   Haltedauer, gleicher Stop/Ziel-Abstand, Einstiegszeitpunkte gelost. Ein
   Setup, das diesen Vergleich nicht schlägt, hat keine Kante — es hat nur eine
   Ereignisverteilung.

**Randbedingung:** Diese Kennzahlen gehören in `metrics.py` neben die
bestehenden, **nicht an deren Stelle**. Bestehende Testerwartungen dürfen sich
nicht verschieben.

### 5.6 Lookahead-Schutz — die vollständige Liste

Bereits strukturell abgesichert:

- `BarContext` gibt nur aktuelle und vorherige Zeile frei
- Signal auf Close, Fill auf nächster Open (`test_kein_lookahead_…`)
- `assert_in_sample_only` / `OutOfSampleViolation`
- Indikatoren rückwärtsgerichtet, IS/OOS-Schnitt nach der Berechnung

Neu zu sichern, wenn die Zielarchitektur kommt:

| Quelle | Gefahr | Gegenmittel |
|---|---|---|
| Regime-Perzentile | Fenster über Gesamthistorie | rollierendes, rückwärts geschlossenes Fenster; Test |
| Makro-/FRED-Werte | Revisionen | nur Vintages mit Veröffentlichungszeitstempel |
| Wirtschaftskalender | nachträglich korrigierte Termine | Abdeckungsgrenze, dritter Filterausgang (steht) |
| Feature Store | nachträgliches Überschreiben alter Zeilen | `feature_set_version`, kein Update alter Versionen |
| Roll-/Terminstruktur | rückwirkend verkettete Kursreihen | Rollzeitpunkt als Merkmal, keine stille Verkettung |
| OOS-Wiederholung | schleichender Verbrauch | Zugriffszähler (5.4) |

**Diese Tabelle gehört in den Testplan**, nicht nur in die Dokumentation. Jede
Zeile ohne Test ist eine Absichtserklärung.

### 5.7 Datenbank

Ist: vier getrennte SQLite-Dateien — `ntbridge.sqlite3` (Kerzen),
`ideas.sqlite3` (Ideen + Beobachtungen), `dukascopy_nas100_1m.sqlite3`
(Näherung), `DEMO_1m.csv` (synthetisch).

**Die Trennung bleibt.** Sie ist keine Nachlässigkeit, sondern schützt: der
produktive Kerzenspeicher wird im laufenden Betrieb geschrieben, ein
Testlauf darf ihn nie berühren.

Ergänzungen:

- `features.sqlite3` als fünfte Datei (5.1)
- **Herkunftstabelle in jeder Datei** — `DukascopyStore` macht es vor
- WAL-Modus überall dort, wo gleichzeitig gelesen und geschrieben wird
- Ein `VACUUM`/Retention-Konzept für `ntbridge.sqlite3`, bevor sie über Jahre
  wächst — heute noch nicht dringend, aber Etappe E

### 5.8 MCP-Server

Ist: drei Tools — `get_market_snapshot`, `get_event_risk`, `list_instruments`.
Startzeit ~7,5 s, im Wesentlichen der pandas-Import.

Ziel:

- **P1: pandas verzögert importieren** — 7,5 s → nahezu sofort. Kleiner
  Aufwand, spürbarer Effekt bei jedem Chatstart.
- **Etappe D braucht Tools**: `evaluate_past_ideas`, `get_performance_report`.
  Sie lesen aus `IdeenStore.lade_fuer_auswertung` — und **nur** daraus.
- Ein `get_regime`-Tool, sobald 5.2 steht.
- **Unverändert bindend:** nichts in `mcp_server/` ruft die Anthropic-API auf.
  Der Test `test_kein_modul_im_projekt_erreicht_die_anthropic_api` prüft das
  repo-weit und bleibt.

### 5.9 Live-Monitoring und Drift Detection

Erst sinnvoll, wenn Etappe C Daten liefert **und** ein OOS-Ergebnis existiert,
gegen das man vergleichen kann. Vorher gibt es keine Erwartung, von der etwas
abweichen könnte.

**Was überwacht wird:**

| Ebene | Frage | Signal |
|---|---|---|
| Datenzufluss | Kommen Kerzen an? | letzte Kerze älter als *n* Minuten während der Session |
| Datenqualität | Lücken? | `pruefe_datenluecken.py` besteht bereits |
| Ideenfluss | Feuern die Setups noch? | Ideen je Setup und Woche gegen historischen Erwartungswert |
| Filterbilanz | Steht ein Filter zu scharf? | Ablehnquote je Filter, Anteil „nicht prüfbar" |
| Regime-Verteilung | Anderer Markt als im Test? | Regime-Häufigkeiten live vs. Testzeitraum |
| Ergebnisdrift | Trägt das Setup noch? | Trefferquote/Erwartungswert im Konfidenzband der OOS-Schätzung |

**Wichtig:** Drift Detection darf **nichts abschalten**. Sie meldet. Die
Entscheidung, ein Setup stillzulegen, ist eine Handelsentscheidung und gehört
Laurin — dieselbe Logik wie bei der Ordersperre.

### 5.10 Datenquellen

| Quelle | Status | Rolle in der Zielarchitektur |
|---|---|---|
| **NinjaTrader 8 / ntbridge** | in Betrieb | **die** Livequelle. Einzige Quelle für belastbare MNQ-Aussagen. |
| **Dukascopy NAS100-CFD** | 3,18 Mio. Kerzen liegen vor | Näherung, Index-CFD ≠ MNQ-Futures. Backtests darauf **rein informativ**. Nicht über `create_provider` erreichbar — siehe P0-3. |
| **DEMO_1m.csv** | synthetisch | CLI-Ausprobieren. **Keine** Grundlage für Aussagen. |
| **Forex Factory** | in Betrieb | Termine. Inoffizieller Endpunkt, kann brechen. Kein `actual`. |
| **FRED** | in Betrieb | Ist-Werte. Für Backtests nur als Vintage (5.3). |
| **Order Flow / Delta** | nicht lizenziert | bleibt `null` mit Begründung. **Nicht schätzen.** |

**Nicht auf der Liste, bewusst:** Databento, Rithmic, kommerzielle Feeds. Der
Erweiterungspunkt (`DataProvider` + `create_provider`) steht bereit; ein
Wechsel ist eine Kostenentscheidung und gehört Laurin.

---

## 6. Priorisierung

Die Reihenfolge folgt einer einzigen Frage: **was bringt den Zeitpunkt der
ersten belastbaren Aussage näher?**

### P0 — blockiert alles Weitere

| # | Punkt | Warum P0 | Aufwand |
|---|---|---|---|
| **P0-1** | **Etappe C in Betrieb nehmen**: geplante Aufgabe einrichten, stündlich, `python -m ideas` | Ohne protokollierte Ideen ist Etappe D nicht testbar und die gesamte Schicht 4/5 gegenstandslos. **Der Engpass.** Jeder Tag ohne Lauf ist ein verlorener Tag Datensammlung. | klein |
| **P0-2** | **MGC vollständig entfernen** | Vorgabe vs. Code stehen im Widerspruch; `list_instruments` liefert MGC weiter aus. Betrifft Register, Kalenderzuordnung, Docstrings, Tests. | mittel |
| **P0-3** | **Dukascopy als `DataProvider` registrieren** | 384 MB Historie liegen unerreichbar da. Ohne sie gibt es keinen einzigen Backtest über mehr als ein paar Wochen. | klein |
| **P0-4** | **Zwei Tradovate-Reste in ausführbarem Code beseitigen** (`cli.py:276`, `csv_provider.py:57`) | Bekannte Fehlerklasse, bereits einmal aufgetreten. Klein, aber genau deshalb sofort. | sehr klein |

> **P0-1 verdient eine Anmerkung.** Es ist der einzige Punkt, der nicht
> hauptsächlich Code ist. Er hängt an einer offenen Frage aus
> `CODE_CHAT_KONTEXT.md`: **werden die 8 fehlenden Setup-Familien vorher gebaut,
> oder läuft die Protokollierung erst mit den vorhandenen 4 an?** Das ist eine
> Entscheidung über den Umfang der Setup-Familien und damit **ausdrücklich
> Laurins**, nicht die der Session.
>
> *Sachlage, damit die Entscheidung leichter fällt:* Sofort mit 4 anzufangen
> kostet nichts und sammelt ab heute Daten; die 8 weiteren lassen sich später
> ergänzen, ihre Kategorien starten dann eben später bei null. Erst alle 12 zu
> bauen verzögert den Datenbeginn um Tage und führt 8 neue Fehlerquellen auf
> einmal ein — wogegen sich die Spezifikation in Abschnitt 2.2 selbst
> ausgesprochen hat.

### P1 — hoher Nutzen, kein Blocker

| # | Punkt | Nutzen |
|---|---|---|
| **P1-1** | Walk-Forward an die CLI anbinden | Getesteter Code, der niemand aufrufen kann. Größte Aussagekraft pro Zeile Arbeit im ganzen Plan. |
| **P1-2** | Erster informativer Backtest auf echten MNQ-Daten (**nur 1m/5m/15m**) | Erste Berührung von Engine und Realdaten. *Die Tagesserie hat eine Lücke 31.07.–12.08.; der 1d-ATR ist ein Artefakt von ~650 Punkten — 1d bleibt draußen.* |
| **P1-3** | Konfidenzintervalle in `metrics.py` | Verhindert Fehlschlüsse aus kleinen Stichproben, bevor die ersten Zahlen da sind. Danach wirkt es wie ein Rückzieher. |
| **P1-4** | MCP-Startzeit: pandas verzögert importieren | 7,5 s → sofort, bei jedem Chatstart. |
| **P1-5** | Regime Engine (5.2) | Etikettiert Ideen ab dem ersten Lauf. **Nachträglich nicht nachholbar** für Ideen, die ohne Regime-Feld protokolliert wurden — deshalb früh, nicht spät. |

### P2 — Ausbau, sobald Daten fließen

- Etappe D: `evaluate_past_ideas`, `get_performance_report` als MCP-Tools
- Feature Store (5.1)
- Bootstrap und Multiple-Testing-Korrektur (5.3)
- Benchmark „zufälliger Einstieg"
- Die 8 weiteren Setup-Familien, schrittweise — **nach Laurins Entscheidung**
- OOS-Zugriffszähler

### P3 — später, bewusst zurückgestellt

- Makro-Vintages aus ALFRED
- Terminstruktur / Roll-Nähe als Merkmal
- Live-Monitoring-Dashboard
- Drift Detection mit Alarmschwellen
- Retention/`VACUUM` für den Kerzenspeicher

---

## 7. Etappenplan

Die Etappen A–F bleiben verbindlich und werden **nicht umbenannt**. Der
Masterplan hängt sich daran an:

| Etappe | Inhalt | Enthält aus diesem Plan |
|---|---|---|
| **C′** | Etappe C in Betrieb | P0-1, P0-2, P0-3, P0-4, P1-5 |
| **D** | Auswertung | P1-3, P2 (Etappe-D-Tools, Bootstrap, Benchmark) |
| **D′** | Research Engine | P1-1, P1-2, OOS-Zähler, Multiple-Testing |
| **E** | Dauerbetrieb-Härtung | Live-Monitoring, Drift Detection, Retention |
| **F** | Liefergegenstände | Anleitungen, Configs, Startbefehle nachziehen |

Feature Store (5.1) läuft **quer** — er ist Beschleunigung, kein
Funktionszuwachs, und wird eingezogen, wenn die Rechenzeit stört, nicht vorher.

---

## 8. Abhängigkeiten

```
P0-1 (Etappe C läuft)
  ├─▶ Datenbestand wächst ────▶ Etappe D testbar ────▶ Drift Detection möglich
  └─▶ setzt voraus: Entscheidung „4 oder 12 Setups"  ◀── LAURIN

P0-3 (Dukascopy-Provider)
  └─▶ P1-1 (Walk-Forward CLI) ──▶ D′ Research Engine
        └─▶ braucht: Multiple-Testing-Korrektur (P2), sonst überschätzt sie

P1-5 (Regime Engine)
  └─▶ muss VOR nennenswertem Datenbestand stehen,
      sonst fehlt das Regime-Feld rückwirkend

P1-3 (Konfidenzintervalle)
  └─▶ muss VOR den ersten Ergebniszahlen stehen

Feature Store (P2)
  └─▶ keine Abhängigkeit, reine Beschleunigung
```

**Zwei Punkte sind zeitkritisch, nicht wichtigkeitskritisch:** die Regime
Engine und die Konfidenzintervalle. Beide sind später technisch genauso
machbar — aber später **nutzlos** für alles, was in der Zwischenzeit
protokolliert oder behauptet wurde.

---

## 9. Testplan

Der Bestand von 342 Tests bleibt grün. Jede neue Komponente bringt Tests der
folgenden Art mit:

| Komponente | Zusicherung | Art |
|---|---|---|
| Regime Engine | Perzentil-Fenster ist rückwärts geschlossen | Lookahead-Test |
| Regime Engine | Regime-Feld liegt an jeder protokollierten Idee an | Integration |
| Feature Store | fehlende Zeile → `null` mit Begründung, **nie** letzter bekannter Wert | Ausfalltest |
| Feature Store | alte `feature_set_version` wird nicht überschrieben | Regression |
| Dukascopy-Provider | `create_provider("dukascopy")` liefert einen Provider | Regression zu P0-3 |
| Dukascopy-Provider | Ergebnisse tragen die Näherungskennzeichnung weiter | Invariante 10 |
| Walk-Forward-CLI | Fenster überlappen nicht, kein Testfenster vor seinem Trainingsfenster | Lookahead-Test |
| OOS-Zähler | Zähler steigt je Zugriff, wird persistiert | Regression |
| Konfidenzintervalle | bei n = 1 kein NaN, kein Absturz, sondern ehrliches „zu wenig Daten" | Randfall |
| Multiple Testing | Zahl der Versuche wird aus Discovery durchgereicht | Integration |
| MGC-Entfernung | kein Modul nennt MGC als **aktives** Instrument | Repo-weiter Test, analog zum Anthropic-API-Test |
| Makro-Vintages | ohne Veröffentlichungszeitstempel wird kein Wert übernommen | Lookahead-Test |
| Drift Detection | meldet, schaltet **nicht** ab | Verhaltenstest |

**Gegenprobe bei Regressionsfixes bleibt Pflicht:** erst zeigen, dass der Test
ohne den Fix fehlschlägt.

---

## 10. Risiken

| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| **Architektur wächst schneller als der Datenbestand** | Fünf Schichten über null protokollierten Ideen. Der Plan ist dann Selbstzweck. | P0-1 zuerst. Jede P2/P3-Arbeit erst, wenn Ideen fließen. |
| **Zweite Rechenlogik schleicht sich ein** | Backtest testet etwas anderes als live läuft — der Kernfehler, gegen den Invariante 1 steht. Feature Store und Regime Engine sind die naheliegendsten Einfallstore. | Beide dürfen nur *lesen*, was `compute_indicators`/`structure` liefern. Test. |
| **Stiller Lookahead über Makrodaten** | Ein Backtest, der brillant aussieht und nichts wert ist. Bei Dukascopy hat genau das schon zugeschlagen und war an den Kursen nicht zu sehen. | Nur Vintages. Kein Vintage → `null` mit Begründung. |
| **OOS wird aufgebraucht** | Nach dem fünften Durchlauf ist der Zeitraum faktisch In-Sample. | Zugriffszähler sichtbar am Ergebnis. |
| **Kleine Stichproben werden überinterpretiert** | 20 Trades tragen keine Aussage über Profitfaktoren. | Konfidenzintervalle **vor** den ersten Zahlen (P1-3). |
| **Dukascopy-Ergebnisse werden als MNQ-Aussage gelesen** | Index-CFD ≠ Futures. | Kennzeichnung wandert bis ins Ergebnis mit, nicht nur in die Herkunftstabelle. |
| **Forex Factory bricht weg** | Blackout-Prüfung fällt aus. | Dritter Filterausgang steht bereits — Ideen werden protokolliert und als ungeprüft vermerkt. |
| **Kontextdateien altern** | Bereits zweimal passiert: „noch offen"-Listen waren beim Abarbeiten längst erledigt. | Vor dem Abarbeiten gegen den Code prüfen, nicht danach. |

---

## 11. Ausdrückliche Nicht-Ziele

Nichts davon wird gebaut. Nicht „später", nicht „als inertes Interface".

- **Keine Orderausführung.** Kein Order-Endpunkt, keine Positionsverwaltung,
  kein Lesen von Kontodaten. Read-only by design, bewusst entschieden.
  Struktureller Schutz: `ClaudeBridge.cs` ist ein NT8-**Indikator** und kann
  dort keine Orders platzieren.
- **Kein Anthropic-API-Aufruf aus dem Projekt.** Interpretation ausschließlich
  in der Claude-Desktop-Unterhaltung über das bestehende Abo. Repo-weit
  getestet.
- **Kein MGC**, kein zweites Instrument im Livepfad.
- **Kein Tradovate**, kein zweiter Broker.
- **Keine automatische Abschaltung** von Setups durch Drift Detection. Melden,
  nicht handeln.
- **Kein Machine Learning auf Kursdaten** in diesem Plan. Nicht aus Prinzip,
  sondern aus Reihenfolge: bei null protokollierten Ideen und ohne
  Multiple-Testing-Disziplin wäre es Kurvenanpassung mit mehr Rechenaufwand.
- **Keine geschätzten Werte, die wie Messungen aussehen.** Delta bleibt `null`,
  Volume Profile trägt `naeherung: true`, Dukascopy trägt seine Einschränkung
  in der Datei selbst.
- **Keine Ergebnisspalte im Ideen-Log.** Gewinn und Verlust entstehen erst bei
  der Auswertung unter einem bestimmten Regelwerk. Zwei Wahrheiten wären
  schlimmer als keine.
- **Kein `backtesting.py`, kein `vectorbt`** — begründet in
  `docs/BACKTESTING_ENTSCHEIDUNG.md`. Vor jedem neuen Vorschlag dort lesen.

---

## 12. Der nächste konkrete Schritt

**Laurin entscheidet, mit welchem P0-Punkt begonnen wird.** Das ist keine
Formalie: P0-1 hängt an einer Umfangsfrage (4 oder 12 Setup-Familien), die die
Session ausdrücklich nicht selbst entscheiden darf.

**Empfehlung, falls gefragt:** **P0-4, dann P0-3, dann P0-1 mit den 4
vorhandenen Setups.**

Begründung: P0-4 sind zwei Zeilen und beseitigen eine Fehlerklasse, die in
diesem Projekt schon zweimal zugeschlagen hat. P0-3 macht 3,18 Mio. Kerzen
erreichbar und ist die Voraussetzung für jeden ernsthaften Backtest. P0-1 mit
4 Setups startet die Datensammlung **heute** statt in einer Woche — und die
fehlenden 8 Familien lassen sich jederzeit nachziehen, während verlorene
Sammeltage nicht nachholbar sind.

P0-2 (MGC) ist unstrittig, aber es blockiert nichts und verändert keinen
Messwert. Es gehört in denselben Durchgang, nicht davor.

---

## 13. Pflege dieser Datei

`MASTERPLAN.md` ist ein **Planungsdokument mit Verfallsdatum**. Sie wird
aktualisiert, wenn ein P0/P1-Punkt erledigt ist oder eine Priorisierung sich
ändert — nicht bei jedem Commit.

Sie ersetzt **nicht** `CODE_CHAT_KONTEXT.md` (Ist-Zustand und Historie) und
**nicht** `NORMALER_CHAT_KONTEXT.md` (Ziele und Randbedingungen). Widersprüche
zwischen dieser Datei und dem Code werden **festgestellt und dokumentiert**,
nicht stillschweigend aufgelöst.
