# MASTERPLAN — MNQ Research- und Analysesystem

**Erstellt:** 23.08.2026. **Grundlage:** gegen den tatsächlichen Code und die
tatsächlichen Datenbanken geprüft, nicht aus Notizen übernommen.

> **Dies ist ein Planungsdokument, kein Implementierungsstand.** Was hier unter
> „Zielarchitektur" steht, existiert überwiegend **nicht**. Der Ist-Zustand
> steht in Abschnitt A und in `CODE_CHAT_KONTEXT.md`.

**Verhältnis zu den anderen Dokumenten:**

| Datei | Rolle |
|---|---|
| `CODE_CHAT_KONTEXT.md` | **WIE und WIE WEIT** — technischer Ist-Stand, Bugs, Tests |
| `NORMALER_CHAT_KONTEXT.md` | **WAS und WARUM** — Ziele, Anforderungen, Etappen A–F |
| `ETAPPE_C_SPEZIFIKATION.md` | verbindliche Vorgabe für die Ideen-Protokollierung |
| **`MASTERPLAN.md`** (diese) | **WOHIN** — Zielarchitektur und Reihenfolge dorthin |

Bei Widersprüchen gilt: **tatsächlicher Code > `CODE_CHAT_KONTEXT.md` >
`NORMALER_CHAT_KONTEXT.md` > ältere Übergabedokumente.** Der MNQ/NinjaTrader-
Override aus dem Auftrag vom 23.08.2026 geht älteren MGC-/Tradovate-Angaben vor.

---

## A. Ist-Zustand — gemessen

**Testsuite: 343 Tests, alle grün** (`.venv\Scripts\python.exe -m pytest`).

### A.1 Was nachweislich funktioniert

| Komponente | Zeilen | Nachweis |
|---|---|---|
| `common/` | 3 962 | Indikatoren, Sessions, Level, Struktur, Muster — umfangreich getestet |
| `ntbridge/` | 874 | **live verifiziert**: 5 850+ Kerzen aus NT8, 0 abgelehnt |
| `mcp_server/` | 1 874 | Handshake gegen echten MCP-Client geprüft, 3 Werkzeuge |
| `backtest/` | 2 907 | eigene Event-Engine, Lookahead-Sperre getestet |
| `ideas/` | 2 196 | 4 Setup-Familien, 39 Ideen protokolliert und **alle nachvollziehbar** |
| `ninjatrader/` | 750 | `ClaudeBridge.cs` v1.0.1, in NT8 kompiliert, sendet live |

### A.2 Datenbestand — der eigentliche Engpass

| Datenbank | Umfang | Zeitraum |
|---|---|---|
| `data/ntbridge.sqlite3` (**echt, MNQ**) | ~5 850 Kerzen über 5 Zeitebenen | **~4 Tage** |
| `data/dukascopy_nas100_1m.sqlite3` (**Näherung**) | 3 179 672 Kerzen, 384 MB | 2016-08-22 bis 2026-08-21 |

**Das ist die zentrale Spannung des ganzen Projekts:** Es gibt zehn Jahre
Historie — aber als Index-CFD, nicht als MNQ-Futures. Und es gibt echte
MNQ-Daten — aber nur vier Tage. Jede Research-Planung muss davon ausgehen.

### A.3 Was gebaut, aber nicht in Betrieb ist

- **`python -m ideas` hängt an keinem Dauerlauf.** Es ist **keine einzige echte
  Idee protokolliert**. Die 39 aus dem Nachvollzugstest liefen gegen eine
  temporäre Datenbank.
- **Kein Backtest auf echten Marktdaten gerechnet** — weder auf den 4 Tagen
  MNQ noch auf der CFD-Historie.

### A.4 Bekannte offene Punkte

| Punkt | Art |
|---|---|
| MCP-Serverstart 7,5 s → Timeout in Cowork/Code | gemessen, Ursache bekannt (pandas), Fix nicht umgesetzt |
| Tagesserien-Lücke 31.07.–12.08.2026 | 1d-ATR dadurch Artefakt (~650 Punkte) |
| `backtest/cli.py:276` bietet `--provider tradovate` an | **Defekt**, siehe C |
| `csv_provider.py:57` verweist auf Tradovate-Download | **Defekt**, siehe C |

### A.5 Ausdrücklich unbekannt

- Ob der NT8-Simulationsfeed formal als Echtzeit gilt (praktisch: <2 s Verzug).
- Ob MNQ und MGC getrennte CME-Datenpakete brauchen — **durch den Override
  gegenstandslos**, siehe C.2.
- Wie gut die CFD-Näherung über **lange** Zeiträume trägt. Geprüft ist ein
  Tag: r = 0,95 auf Minutenänderungen, Niveauabstand −86 Punkte.

---

## B. Bestehende Architektur

```
NinjaTrader 8 (MNQ, 2 Charts)
  └─ ClaudeBridge.cs          Indikator, KEINE Strategy
     └─ HTTP POST → 127.0.0.1:8787/bars
        └─ ntbridge/receiver.py     nur localhost, exklusiv gebunden
           └─ ntbridge/store.py     SQLite WAL, idempotent
              ├─ mcp_server/        → Claude Desktop   (auf Zuruf)
              └─ ideas/             → data/ideas.sqlite3 (regelbasiert)

backtest/  ← liest CSV oder data/dukascopy_nas100_1m.sqlite3 (Näherung)
```

**Tragende Invarianten** (ausführlich in `CLAUDE.md`):

1. **Eine einzige Indikator- UND Signal-Implementierung.** `compute_indicators`
   für beide Seiten; `ideas/setups.py` bildet jede Familie auf eine
   `RuleStrategy` aus `backtest/strategies/` ab.
2. **Keine Anthropic-API im gesamten Repository** — repo-weit getestet.
3. **Nur Simulationskonten.** *(Ersetzt am 30.08.2026 die frühere Invariante
   „Read-only: keine Orders, kein Kontozugriff“ — Laurin hat die
   Projektgrenze aufgehoben, Ausführung ist jetzt Projektbestandteil.)*
   Das AddOn `TradayriBridge.cs` handelt ausschließlich auf Konten mit
   `Account.Provider == Provider.Simulator`, geprüft am **Konto** statt an
   der Verbindung, ohne Schalter. Der Datenweg bleibt getrennt: Kerzen kommen
   nur über `ClaudeBridge.cs`, und das ist ein *Indikator*, der strukturell
   keine Orders platzieren kann.
4. **Näherungen werden gekennzeichnet**, nie als Messung ausgegeben.
5. **Keine stillen Ausfälle:** `null` mit Begründung plus abbrechende
   Startprüfung.

---

## C. Veraltete Komponenten

### C.1 Tradovate — zwei echte Defekte, sonst Historie

Der Legacy-Pfad ist am 22.08.2026 entfernt (`live_bot/`, Provider, Config,
Secrets, 64 Tests). Verblieben sind **48 Treffer**, davon:

| Fundstelle | Art | Handlung |
|---|---|---|
| `backtest/cli.py:276` | **Defekt** — CLI bietet `--provider tradovate`, Provider ist gelöscht | **bereinigen** (P0, Minutenaufwand) |
| `backtest/data/csv_provider.py:57` | **Defekt** — Fehlertext rät zum Tradovate-Download | **bereinigen** (P0) |
| `tests/test_ideas.py:875`, `tests/test_ntbridge.py:504` | toter Config-Abschnitt in Fixtures | bereinigen (P2) |
| `tests/test_mcp_snapshot.py:76` | Docstring nennt `TradovateBarSource` | bereinigen (P2) |
| `backtest/data/base.py:4` | Docstring nennt Tradovate als mögliche Quelle | umformulieren (P2) |
| `mcp_server/bars.py`, `context.py`, `common/contracts.py`, `instruments.py`, `config.yaml` | **datierte historische Erklärungen** | **behalten** — sie begründen, warum Dinge so sind |

`live_bot/` enthielt am 23.08.2026 nur noch `__pycache__` ohne Quelldateien;
diese Reste sind entfernt.

### C.2 MGC — WIDERSPRUCH ZUM OVERRIDE, nicht still aufgelöst

**Der Override sagt:** MGC ist vollständig entfernt, wird nicht analysiert,
gespeichert, protokolliert oder getestet, und es soll keine MGC-Architektur
gebaut werden.

**Der Code sagt etwas anderes.** 48 MGC-Treffer in 14 Dateien:

| Ort | Was |
|---|---|
| `common/instruments.py` | MGC ist ein **registriertes Instrument** mit eigener `expiry_rule` |
| `tests/test_instruments_sessions.py` | **14 Treffer** — MGC-Verfallsregel ist getestet |
| `tests/test_levels_structure.py`, `test_event_risk.py`, `test_mcp_snapshot.py`, `test_ntbridge.py` | MGC als zweites Instrument in Testfällen |
| `mcp_server/server.py`, `cli.py` | MGC in Beispielen/Beschreibungen |

**Wo der Override bereits erfüllt ist:** MGC wird **nicht** protokolliert
(`ideas.instrumente: ["MNQ"]`), **nicht** gestreamt, **nicht** gesammelt. Es
gibt keine MGC-Daten in `ntbridge.sqlite3`. Insofern gilt „nicht analysiert,
nicht gespeichert, nicht protokolliert" **schon heute**.

**Wo er nicht erfüllt ist:** MGC steht im Instrument-Register und in Tests.

**Meine Empfehlung: das Register nicht anfassen — und zwar begründet.**

- Das Register ist **keine Multi-Instrument-Architektur**, sondern eine
  Nachschlagetabelle für Ticksize, Punktwert, Sessionzeiten und Verfallsregel.
  MGC dort zu belassen kostet **keine Laufzeitkomplexität** und erzeugt keine
  Datenhaltung.
- Die MGC-Tests sichern **Bug-Lehre 9** ab: MNQ rollt zum 3. Freitag, MGC zum
  drittletzten Geschäftstag. Dieser Test ist der einzige, der beweist, dass
  `expiry_rule` überhaupt eine Regel *pro Instrument* ist und nicht eine
  hartverdrahtete MNQ-Annahme. Entfernt man ihn, kann die MNQ-Regel später
  stillschweigend falsch werden, ohne dass ein Test es merkt.
- `Config.validate()` prüft Ticksize und Punktwert gegen das Register. Diese
  Prüfung existiert wegen eines konkreten Fehlerbilds (Mini- statt
  Micro-Punktwert → alle USD-Angaben Faktor 10 daneben).

**Was ich stattdessen vorschlage:** MGC aus **nutzersichtbaren** Stellen
entfernen (MCP-Werkzeugbeschreibungen, CLI-Beispiele, README), damit niemand
den Eindruck bekommt, MGC werde unterstützt — und im Register mit einem
Kommentar belassen, der genau das festhält.

**Das ist eine Entscheidung, die Laurin gehört.** Sie steht in W.

### C.3 Was nicht mehr existiert

`live_bot/` samt Alarmen, Telegram und `/analyse`; `tradovate_provider.py`;
die Config-Abschnitte `tradovate`, `alerts`, `claude`, `notify`; `Secrets` bis
auf `FRED_API_KEY`.

---

## D. Zielarchitektur

```
                    ┌──────────────────────────────────────┐
                    │  NinjaTrader 8 — MNQ, einzige        │
                    │  Marktdatenquelle (Indikator)        │
                    └───────────────┬──────────────────────┘
                                    │ HTTP, lokal
    ┌───────────────────────────────▼──────────────────────────────┐
1.  │  MARKET DATA          ntbridge → bars (SQLite)               │
    └───────────────────────────────┬──────────────────────────────┘
    ┌───────────────────────────────▼──────────────────────────────┐
2.  │  FEATURE STORE        gerechnete Kennzahlen je Kerze,        │
    │                       mit as-of-Zeitstempel                  │
    └──────┬─────────────────────────┬──────────────────┬──────────┘
    ┌──────▼───────┐  ┌──────────────▼─────┐  ┌─────────▼─────────┐
3.  │ MACRO        │  │ NEWS/EVENTS        │  │ CROSS-ASSET       │
    │ (FRED)       │  │ (Forex Factory)    │  │ (später, s. F)    │
    │ + Revisionen │  │ + availability_time│  │                   │
    └──────┬───────┘  └──────────┬─────────┘  └─────────┬─────────┘
    ┌──────▼─────────────────────▼──────────────────────▼──────────┐
4.  │  REGIME ENGINE        Volatilität / Trend / Liquidität       │
    └───────────────────────────────┬──────────────────────────────┘
    ┌──────────────────┬────────────▼─────────────┬────────────────┐
5.  │  IDEAS           │  RESEARCH ENGINE         │  MONITORING    │
    │  (Etappe C, da)  │  Discovery→Validation→   │  Drift, Regime │
    │                  │  Confirmation            │                │
    └──────────────────┴────────────┬─────────────┴────────────────┘
    ┌───────────────────────────────▼──────────────────────────────┐
6.  │  MCP → Claude Desktop   NUR Interpretation, keine Statistik  │
    └──────────────────────────────────────────────────────────────┘
```

**Die Schichtregel:** Jede Schicht darf nur nach **unten** greifen. Schicht 6
rechnet nichts. Schicht 5 erfindet keine Features. Ein Verstoß wie die
Schichtumkehr vom 22.08.2026 (`common` importierte `ideas`) wird durch den
Importhüllen-Test gefangen — der bleibt und wird erweitert.

---

## E. Datenfluss

**Live** (läuft): NT8 schließt Kerze → `ClaudeBridge.cs` POSTet → `receiver.py`
validiert (`validate_bar` mit benannten Ablehnungsgründen) → `store.py`
idempotenter Upsert.

**Auf Zuruf** (läuft): Claude Desktop ruft `get_market_snapshot` → `bars.py`
lädt je Timeframe → `compute_extended_indicators` → `snapshot.py` baut
Kennzahlen → **nur berechnete Werte** gehen raus, keine Rohdaten.

**Regelbasiert** (gebaut, nicht in Betrieb): `python -m ideas` → `vorbereiten()`
→ `erkenne()` wertet Regel-Objekte aus → `pruefe_alle()` filtert mit drei
Ausgängen → `store.speichere()`.

**Research** (existiert nicht): Feature Store → Regime → Discovery →
Validierung → Bericht.

---

## F. Market Intelligence — Quellenbewertung

> **Bewusst zurückhaltend.** Der Auftrag sagt: im Zweifel lieber wenige Quellen
> gründlich bewerten als viele parallel bauen. Ich bewerte deshalb nur die
> **zwei bereits integrierten** Quellen vollständig — dort kenne ich Verhalten
> und Grenzen aus dem Code. Alles andere ist als **ungeprüft** markiert;
> Angaben zu Kosten, Lizenz und API dieser Quellen wären erfunden.

### F.1 Forex Factory — integriert

| Kriterium | Bewertung |
|---|---|
| Daten | Wirtschaftstermine mit Zeitpunkt, Währung, Impact-Stufe |
| Historie | **Nur laufende Woche** — gemessen |
| Echtzeit | Termine im Voraus, keine Ist-Werte |
| Timestamp-Qualität | Termin-Zeitpunkt vorhanden; **kein `actual`-Feld** |
| API | inoffizieller JSON-Endpunkt, kein Schlüssel |
| Kosten | keine |
| Lizenz | **ungeklärt** — inoffiziell, kann jederzeit brechen |
| Zuverlässigkeit | mittel; Ausfall wird als `calendar_available: false` gemeldet |
| **Lookahead-Risiko** | **hoch, wenn man nicht aufpasst.** Die Wochengrenze bedeutet: für ältere Zeitpunkte findet sich kein Termin und die Antwort wäre „kein Blackout" — eine Entwarnung aus einer Wissenslücke. Abgesichert durch `ideas/kalender.py` mit Abdeckungsgrenze. |
| Nutzen | hoch für Live-Blackouts, **null für Research** über längere Zeiträume |

### F.2 FRED — integriert

| Kriterium | Bewertung |
|---|---|
| Daten | Ist-Werte veröffentlichter Makro-Reihen |
| Historie | lang (Jahrzehnte) |
| Echtzeit | **verzögert** — erscheint erst nach der Veröffentlichung |
| Timestamp-Qualität | Beobachtungsdatum vorhanden; **`availability_time` nicht modelliert** |
| API | offiziell, Schlüssel nötig (`FRED_API_KEY`) |
| Kosten | keine |
| Lizenz | offiziell, nutzbar; **ISM/PMI ausgenommen** (Lizenz zurückgezogen) |
| Zuverlässigkeit | hoch |
| **Lookahead-Risiko** | **hoch und derzeit ungelöst.** FRED liefert **revidierte** Werte. Wer einen heutigen FRED-Wert einem Zeitpunkt von 2019 zuordnet, verwendet eine Zahl, die es damals nicht gab. Für Live-Anzeige unproblematisch, für Research **disqualifizierend**, solange Revisionen nicht modelliert sind. |
| Nutzen | mittel live, **hoch für Research — aber erst nach ALFRED-artiger Vintage-Modellierung** |

### F.3 Kandidaten — ungeprüft

Diese sind **nicht bewertet**. Vor jeder Integration ist eine Prüfung nach
demselben Raster Pflicht, insbesondere Lizenz und Kosten (Bug-Lehre: der
Tradovate-Umweg kostete erhebliche Arbeit, weil Kontovoraussetzungen zu spät
geprüft wurden).

| Kandidat | Wofür | Zu klären vor Bewertung |
|---|---|---|
| FRED/ALFRED-Vintages | Revisionssichere Makrodaten | Ob ALFRED die benötigten Reihen als Vintage führt |
| Treasury-Renditekurve | Zins-/Risikoumfeld | Quelle, Lizenz, Verfügbarkeitszeit |
| Cross-Asset (VIX, DXY, Öl) | Regime-Kontext | **Ob NT8 sie liefert** — das wäre die kostenfreie Option |
| Fed-Kalender/Reden | Event-Risiko | Strukturierte Quelle überhaupt vorhanden? |
| News/Geopolitik | Ereigniskontext | Zeitstempelqualität; **hier ist das Lookahead-Risiko am größten** |

**Cross-Asset über NT8 ist der naheliegendste erste Schritt**, weil die
Infrastruktur (Bridge, Empfänger, Speicher) bereits steht und keine neue
Quelle, kein Schlüssel und keine Lizenz nötig wäre. Das ist zu prüfen, bevor
externe Anbieter erwogen werden.

---

## G. Research Engine

**Vier strikt getrennte Phasen.** Die Trennung ist der ganze Punkt — ohne sie
ist jedes Ergebnis ein Data-Snooping-Artefakt.

| Phase | Frage | Daten | Ausgabe |
|---|---|---|---|
| **Discovery** | Welche Bedingungen *könnten* tragen? | nur Train | Hypothesen, **keine Aussage über Güte** |
| **Validation** | Hält die Hypothese auf ungesehenen Daten? | Validation | Hypothese verworfen oder weiterverfolgt |
| **Confirmation** | Hält sie auf dem finalen OOS-Block? | OOS, **einmalig** | bestätigt/verworfen |
| **Monitoring** | Hält sie weiterhin? | Live | Drift-Warnung, **keine Regeländerung** |

**Reihenfolge der Komplexität — nicht überspringen:**

1. **Einzelfaktor.** „Trägt Bedingung X allein?" Jede Bedingung einzeln, mit
   Zählung der geprüften Hypothesen.
2. **Zweifaktor.** Nur Kombinationen, deren Einzelfaktoren auffällig waren.
3. **Mehrfaktor.** Erst wenn 1 und 2 belastbare Ergebnisse geliefert haben.

**Entry und Exit getrennt.** Ein Setup mit gutem Einstieg und schlechtem
Ausstieg sieht aus wie ein schlechtes Setup. Beides gemeinsam zu optimieren
verwischt, woran es liegt.

**Multiple-Testing-Schutz:** Jeder Discovery-Lauf schreibt mit, **wie viele
Hypothesen geprüft wurden**. Ohne diese Zahl ist ein p-Wert bedeutungslos —
bei 100 geprüften Bedingungen sind fünf „signifikante" bei α = 0,05 der
Erwartungswert, nicht ein Fund.

---

## H. Feature Store

**Zweck:** Kennzahlen einmal rechnen, mit as-of-Zeitstempel ablegen, von
Research und Live gemeinsam nutzen. Verhindert, dass Research andere Zahlen
sieht als der Live-Pfad — dieselbe Logik wie Invariante 1.

**Features aus dem vorhandenen Code** (nichts Neues erfinden):

| Gruppe | Konkret | Quelle im Code |
|---|---|---|
| Preis/Volatilität | `atr`, ATR-Perzentil, True Range | `common/indicators.py` |
| Trend | `sma_fast`, `sma_slow`, `adx`, `ema_stack` | `indicators.py` |
| Oszillatoren | `rsi`, `stochastic`, `macd` | `indicators.py` |
| Bänder | `bollinger`, Keltner-Containment, Squeeze | `indicators.py` |
| Anker | `vwap`, Abstand in ATR | `indicators.py` |
| Level | PDH/PDL/PDC, Overnight, IB, Opening Range, Gap | `common/levels.py` |
| Struktur | HH/HL, LH/LL, BOS, CHoCH, RSI-Divergenz | `common/structure.py` |
| Muster | Flagge, Dreieck, Doppeltop/-boden, Range-Kompression | `common/patterns.py` |
| Session | Session-Datum, Liquiditäts-/Dünnzone | `common/sessions.py` |

**Jede Zeile trägt `as_of`** — den Zeitpunkt, ab dem der Wert bekannt war.
Für Kerzen-Features ist das der Kerzenschluss. Für Makro-Features der
Veröffentlichungszeitpunkt, **nicht** das Beobachtungsdatum.

---

## I. Regime Engine

**Zweck:** Ein Setup, das im Trend trägt und in der Range verliert, sieht über
alles gemittelt aus wie „kein Erwartungswert". Ohne Regime-Trennung sind genau
die Setups unsichtbar, die sich lohnen.

**Vorschlag: drei unabhängige Achsen**, jede aus vorhandenen Größen:

| Achse | Kennzahl | Grenzen |
|---|---|---|
| Volatilität | ATR-Perzentil über N Sessions | Terzile, aus der Verteilung |
| Trend/Range | `adx` | Schwellen aus der Verteilung, nicht geraten |
| Liquidität | Session-Fenster + relatives Volumen | `common/sessions.py` |

**Die Grenzen werden aus der Verteilung abgeleitet, nicht gesetzt.** Genau wie
bei `consolidation_max_atr` am 22.08.2026: der geerbte Wert 1,2 war auf keiner
Zeitebene erreichbar, das Setup konnte nie auslösen. Regime-Grenzen haben
dasselbe Risiko.

**Regime-Zuordnung ist zustandslos und rückwärtsgerichtet** — sie darf nur
Daten bis zum jeweiligen Zeitpunkt verwenden.

---

## J. Statistische Validierung

**Expectancy statt Winrate.** Winrate allein ist wertlos: 90 % Treffer bei
1:9 CRV ist ein Verlustgeschäft. Maßgeblich ist der Erwartungswert **in R**:

```
E[R] = (Trefferquote × Ø-Gewinn_in_R) − (Fehlquote × Ø-Verlust_in_R)
```

**Aufteilung mit zeitlicher Trennung** — nie zufällig, das wäre Lookahead
über Autokorrelation:

| Block | Anteil | Rolle |
|---|---|---|
| Train | ~60 % | Discovery |
| Validation | ~20 % | Hypothesen aussortieren |
| **OOS** | ~20 % | **einmalig**, nur zur Bestätigung |

Der bestehende `assert_in_sample_only` wirft bereits `OutOfSampleViolation` —
dieser Mechanismus wird für Research übernommen, nicht neu gebaut.

**Walk-Forward:** rollierendes Fenster, damit ein Ergebnis nicht an einer
einzelnen Marktphase hängt.

**Parameter-Robustheit:** Ein Parameter, dessen Ergebnis bei ±10 % einbricht,
ist ein Zufallsfund. Gesucht sind **Plateaus, keine Spitzen**.

**Drei Zahlen gehören in jeden Bericht**, sonst ist er irreführend:
1. **Anzahl geprüfter Hypothesen.**
2. **Anzahl Trades je Kategorie** — unter Laurins Schwelle von 20 gilt
   ausdrücklich „zu wenig Daten", nicht „schwaches Ergebnis".
3. **Das verwendete Kostenprofil** (seit 23.08.2026, siehe `backtest/kosten.py`).
   Dieselbe Strategie ist unter 0,50 und unter 2,50 USD je Seite ein völlig
   anderes Geschäft — bei `prev_day_breakout` machten die Kosten 5,00 USD je
   Trade gegen 2,00 USD Bruttoverlust aus. Ein Ergebnis ohne diese Angabe
   lässt sich nicht einordnen.

**Jede Research-Aussage muss unter beiden Profilen geprüft werden**
(`private_ninjatrader` und `lucid`). Ein Setup, das nur unter dem günstigeren
trägt, ist keine Kante, sondern eine Kostenwette.

---

## K. Lookahead-Schutz

**Der Schutz ist strukturell, nicht durch Sorgfalt.** Bestehend:

| Mechanismus | Wo |
|---|---|
| `BarContext` gibt nur aktuelle + vorherige Zeile frei | `backtest/strategies/base.py` |
| Ausführung zur Eröffnung der Folgekerze | `backtest/engine.py` |
| `ib_high`/`ib_low` bleiben NaN bis Fensterende | `common/levels.py` |
| Indikatoren einmal über die Gesamthistorie, dann schneiden | `compare.prepare_split` |
| Kalender-Abdeckungsgrenze | `ideas/kalender.py` |

**Neu nötig für Makro und News:**

- **`availability_time` als Pflichtspalte.** Ein Wert darf einem Zeitpunkt
  erst zugeordnet werden, wenn er damals verfügbar war.
- **Revisionsketten.** FRED liefert revidierte Werte. Ohne Vintage-Modellierung
  ist jede Makro-Research wertlos — man rechnet mit Zahlen, die es damals nicht
  gab. **Das ist der Grund, warum Makro-Research spät kommt** (siehe R).
- **News-Zeitstempel sind verdächtig.** Veröffentlichungszeit ≠ Ereigniszeit ≠
  Indexierungszeit. Ohne belastbare Verfügbarkeitszeit keine Verwendung.

---

## L. Datenbank

**Bestehend:**

| Datei | Tabellen | Schlüssel |
|---|---|---|
| `ntbridge.sqlite3` | `bars` | `(instrument, timeframe, ts_utc)`, WAL |
| `ideas.sqlite3` | `ideen`, `observations` | `idea_id` PK + UNIQUE `(instrument, setup, richtung, timeframe, erstellt_utc, quelle)` |
| `dukascopy_nas100_1m.sqlite3` | `bars`, `geholte_stunden`, **`herkunft`** | `ts_utc` PK |

**Regeln, die überall gelten:**

- **Alles UTC**, ISO-8601 mit Zeitzone. Naive Zeitstempel werden abgelehnt.
- **`herkunft`-Tabelle** bei jeder Näherungsquelle — sie wandert mit der Datei.
- **Getrennte Dateien** je Datenart. Echte Messungen und Näherungen nie in
  derselben Datei.

**Neu vorgeschlagen:**

| Tabelle | Zweck | Besonderheit |
|---|---|---|
| `features` | Feature Store | `(ts_utc, timeframe, name)` PK, Spalte `as_of` |
| `macro_werte` | Makro-Reihen | `(reihe, beobachtung_datum, vintage)` PK, `availability_time` |
| `regime` | Regime je Kerze | `(ts_utc, achse)` PK |
| `hypothesen` | Research-Buchführung | inkl. **Anzahl geprüfter Hypothesen je Lauf** |
| `research_laeufe` | Reproduzierbarkeit | Code-Stand, Datenstand, Parameter |

---

## M. MCP-Werkzeuge

**Bestehend, alle drei gerechtfertigt:** `get_market_snapshot`,
`get_event_risk`, `list_instruments`.

**Neu — nur nach echtem Bedarf:**

| Werkzeug | Wann | Begründung |
|---|---|---|
| `evaluate_past_ideas` | Etappe D | Kernzweck des Projekts |
| `get_performance_report` | Etappe D | ebenda |
| `get_regime` | nach Regime-Engine | nur wenn Claude es für die Einordnung braucht |
| `get_research_findings` | nach Confirmation | **erst wenn es bestätigte Funde gibt** |

**Ausdrücklich nicht:** ein Werkzeug je Kennzahl. Der Snapshot liefert bereits
ein zusammenhängendes Bild; viele kleine Werkzeuge erzeugen viele Roundtrips
bei 7,5 s Startzeit.

**Vorbedingung für jedes neue Werkzeug: die Startzeit muss runter.** Solange
der Server 7,5 s braucht, verschlechtert jedes zusätzliche Werkzeug die Lage.

---

## N. Live-Monitoring

**Zweck:** Erkennen, wann ein Setup aufhört zu funktionieren — nicht, es
automatisch zu ändern.

| Größe | Prüfung |
|---|---|
| Ideen je Kategorie und Woche | Bricht die Rate ein, hat sich der Markt oder die Datenlage geändert |
| Verteilung der Filtergründe | Verschiebt sich, was Ideen blockiert |
| Anteil „nicht prüfbar" | Steigt er, ist eine Datenquelle stumm geworden |
| Regime-Verteilung | Verschiebt sich das Marktumfeld |

**Das System ändert nie selbst eine Regel.** Es meldet und begründet.

---

## O. Drift Detection

**Drei Arten, die nicht verwechselt werden dürfen:**

1. **Performance-Drift** — Setup verliert Erwartungswert bei gleichem Regime.
   Echter Befund.
2. **Regime-Drift** — das Umfeld hat sich verschoben. Kein Setup-Problem;
   möglicherweise ein Anwendungsproblem.
3. **Daten-Drift** — die Messung ist kaputt. **Zuerst ausschließen.**

**Reihenfolge ist zwingend:** erst Daten prüfen (`pruefe_datenluecken.py`),
dann Regime, dann Performance. Andernfalls wird ein Empfänger-Ausfall als
„Setup funktioniert nicht mehr" fehlgedeutet — genau das Fehlermuster, das
dieses Projekt wiederholt getroffen hat.

---

## P. Datenquellen — Gesamtsicht

| Quelle | Art | Kosten | Status |
|---|---|---|---|
| NinjaTrader 8 (MNQ) | **Messung** | ~4 USD/Monat CME-Daten | **aktiv**, einzige Marktdatenquelle |
| Dukascopy NAS100-CFD | **Näherung** | keine | **vorhanden**, 10 Jahre, nur informativ |
| Forex Factory | Termine | keine | aktiv, nur laufende Woche |
| FRED | Makro-Ist-Werte | keine | aktiv, **ohne Vintage-Modellierung** |
| `data/DEMO_1m.csv` | synthetisch | — | nur CLI-Demo, **kein Beleg** |

**Warum keine bezahlte Futures-Historie:** Der Kostenrahmen ist eine harte
Anforderung. Zehn Jahre echte MNQ-Minutendaten sind kostenlos nicht erhältlich
— das ist geprüft. Die CFD-Näherung ist der Kompromiss, **mit gekennzeichneter
Einschränkung**.

---

## Q. Priorisierung

| Prio | Komponente | Begründung |
|---|---|---|
| **P0** | Ideen-Dauerlauf einrichten | **Zeitkritisch.** Jeder Tag ohne Protokollierung ist unwiederbringlich. Ohne Daten kein Research. |
| **P0** | Zwei Tradovate-Defekte bereinigen | Kaputte CLI-Option, irreführender Fehlertext. Minutenaufwand. |
| **P0** | MCP-Startzeit senken | Blockiert Cowork/Code **heute** und jedes künftige Werkzeug. |
| **P1** | Etappe D — `evaluate_past_ideas` | Kernzweck. **Braucht Daten aus P0.** |
| **P1** | Feature Store | Voraussetzung für Research; verhindert zweite Rechenwege. |
| **P1** | Backtest auf CFD-Historie | Erster echter Praxistest der Engine. Rein informativ. |
| **P2** | Regime Engine | Ohne sie sind Research-Ergebnisse über alles gemittelt. |
| **P2** | Research Engine (Einzelfaktor) | Braucht Feature Store und Regime. |
| **P2** | Live-Monitoring / Drift | Braucht laufende Protokollierung über Wochen. |
| **P2** | MGC-Sichtbarkeit klären | Entscheidung, kein Aufwand. |
| **P3** | Makro mit Vintage-Modellierung | Hoher Aufwand, hohes Lookahead-Risiko. |
| **P3** | Cross-Asset über NT8 | Erst prüfen, ob NT8 es liefert. |
| **P3** | News/Geopolitik | Höchstes Lookahead-Risiko, geringster gesicherter Nutzen. |
| **—** | Lucid-Regelsimulation | Bleibt Etappe D zugeordnet; kein Research-Blocker. |

---

## R. Etappenplan

**Die bestehende Struktur A–F bleibt.** A und B sind abgeschlossen, C ist
gebaut, D–F offen. Neue Etappen setzen **nach** C an.

| Etappe | Inhalt | Status |
|---|---|---|
| **A** | NinjaScript-Bridge | **abgeschlossen**, live verifiziert |
| **B** | Empfänger + SQLite + BarSource | **abgeschlossen**, live verifiziert |
| **C** | Regelbasierte Ideen-Protokollierung | **gebaut**, nicht in Betrieb |
| **C+** | **Dauerlauf + Betriebsnachweis** | **NEU, P0** |
| **D** | `evaluate_past_ideas`, `get_performance_report` | offen, **nach I** (Entscheidung 18.3) |
| **G** | Feature Store | **NEU**, braucht C+ |
| **H** | Regime Engine | **NEU**, braucht G |
| **I** | Research Engine, Einzelfaktor | **NEU**, braucht G+H — **vor D** |
| **J** | Research, Zwei-/Mehrfaktor | **NEU**, braucht I |
| **K** | Live-Monitoring und Drift | **NEU**, braucht D + Wochen an Daten |
| **E** | Dauerbetrieb-Härtung | offen, sinnvoll parallel zu K |
| **L** | Makro mit Vintage | **NEU, P3** |
| **F** | Liefergegenstände | fortlaufend |

**Begründung der Reihenfolge:**

- **C+ zuerst, weil Zeit die einzige nicht aufholbare Ressource ist.** Code
  lässt sich nachbauen, vergangene Marktdaten nicht. Bei ~13 Ideen je Woche
  über 8 Kategorien braucht Laurins Schwelle von 20 je Kategorie **Monate**.
  Jeder Tag Verzögerung verschiebt jede spätere Etappe um einen Tag.
- **Research vor D** — **geändert am 23.08.2026 durch Laurins Entscheidung
  (18.3).** Ursprünglich stand hier „D vor Research", weil
  `evaluate_past_ideas` den Maßstab setzen sollte. Die Basisvermessung hat das
  Argument entwertet: die vier Setups haben **brutto** keine Kante. Etappe D
  würde also vier Setups auswerten, bei denen es nichts auszuwerten gibt.
  Research sucht stattdessen, unter **welchen Bedingungen** überhaupt eine
  entsteht — und ist auf den zehn Jahren Näherungshistorie sofort rechenbar.
- **G vor H vor I**, weil Regime auf Features beruht und Research auf beidem.
- **K spät**, weil Drift-Erkennung Vergleichsdaten über Wochen braucht.
- **L zuletzt**, weil die Vintage-Modellierung aufwendig ist und ohne sie jede
  Makro-Research falsch wäre. Lieber spät und richtig als früh und wertlos.

---

## S. Abhängigkeiten

```
A ──> B ──> C ──> C+ ──> G ──> H ──> I ──┬──> J
                                          └──> D ──> K

                            L (unabhängig, P3)

Geändert am 23.08.2026: D hängt jetzt hinter I, nicht davor (Entscheidung 18.3).
```

| Etappe | braucht zwingend | Grund |
|---|---|---|
| C+ | C | Pipeline muss existieren |
| D | C+ | ohne geloggte Ideen nichts auszuwerten |
| G | C+ | Features werden gegen echte Kerzen geprüft |
| H | G | Regime beruht auf Features |
| I | G, H | Research braucht beide |
| J | I | Mehrfaktor erst nach Einzelfaktor |
| K | D, ~8 Wochen Live-Daten | Drift braucht Vergleichszeitraum |
| L | — | unabhängig, aber P3 |

---

## T. Testplan

**Bestehend und nicht zu entfernen** (`CODE_CHAT_KONTEXT.md` Abschnitt 9):
repo-weiter Anthropic-Test, Lookahead-Tests, Vorsession-Vollständigkeit,
IB-Fenster, Exploration-Log-Sperre, Nachvollziehbarkeit.

**Neu je Bereich:**

| Bereich | Test |
|---|---|
| **Timestamp** | Naive Zeitstempel werden abgelehnt. Kerzen tragen die **Schlusszeit** (Invariante 9 — der Dukascopy-Versatz war nur im Kreuzvergleich sichtbar). |
| **Lookahead** | Ein Feature zum Zeitpunkt T darf sich nicht ändern, wenn man Daten nach T anhängt. **Als Test formulierbar:** zweimal rechnen, einmal mit gekürzter Historie. |
| **Revision** | Ein Makro-Wert mit `availability_time` nach T darf für T nicht sichtbar sein. |
| **Missing Data** | Fehlende Kerze erzeugt keine erfundene Zeile. Fehlender Makro-Wert ergibt `null` mit Begründung, nie 0. |
| **Research** | Discovery darf nicht auf OOS zugreifen (`OutOfSampleViolation`). Die Hypothesenzahl wird mitgeschrieben. |
| **Statistik** | Expectancy gegen von Hand gerechnete Beispiele. Unter 20 Trades meldet der Bericht „zu wenig Daten", keine Kennzahl. |

**Gegenprobe bleibt Pflicht:** Jeder Regressionsfix wird geprüft, indem die
fehlerhafte Variante testweise wieder eingesetzt wird. Ein Test, der vorher und
nachher grün ist, beweist nichts.

---

## U. Risiken

### U.1 Technisch

| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| **Datenlücken** | zerstören Statistik still | `pruefe_datenluecken.py` täglich; Laptop durchlaufen lassen |
| **Zwei Sessions auf einem Arbeitsbaum** | **am 22.08. beinahe Datenverlust**: halb ausgeführter Checkout, mehrfach verwaiste `index.lock` | Nur eine schreibende Sitzung; vor Branchwechsel Status prüfen |
| MCP-Startzeit 7,5 s | Timeouts, blockiert neue Werkzeuge | pandas verzögert importieren |
| Forex Factory bricht | Blackout-Prüfung fällt aus | `calendar_available: false`, nie „keine Termine" |
| SQLite bei Millionen Zeilen | Research wird langsam | Indizes; Feature Store getrennt halten |

### U.2 Research

| Risiko | Wirkung | Gegenmittel |
|---|---|---|
| **Data Snooping** | Zufallsfunde als Erkenntnis | Hypothesenzahl mitschreiben, OOS **einmalig** |
| **Zu wenig echte MNQ-Daten** | keine belastbare Aussage | „zu wenig Daten" ausweisen; Zeit ist die Lösung |
| **CFD-Näherung wird wie Messung behandelt** | falsche Schlüsse über echte Trades | `herkunft`-Tabelle; Ergebnisse als informativ kennzeichnen |
| **Makro-Revisionen** | Research rechnet mit damals unbekannten Zahlen | Vintage-Modellierung **vor** jeder Makro-Research |
| Regime-Grenzen geraten | wie `consolidation_max_atr` 1,2: Bedingung nie erfüllbar | Grenzen aus der Verteilung ableiten |
| Überanpassung an eine Marktphase | bricht live ein | Walk-Forward, Plateaus statt Spitzen |

---

## V. Was ausdrücklich nicht gemacht wird

- ~~**Keine automatische Orderausführung**, kein Order-Routing, kein Lesen
  von Konto- oder Positionsdaten.~~ **Überholt seit 30.08.2026.** Laurin hat
  die Projektgrenze aufgehoben; Ausführung läuft über `execution/` und das
  AddOn `TradayriBridge.cs`. Was bleibt: **ausschließlich Simulationskonten**,
  und der Riegel dafür sitzt im AddOn ohne Schalter. Einzelheiten in
  `CODE_CHAT_KONTEXT.md` Abschnitt 34 und `ninjatrader/HERKUNFT.md`.
- **Keine NinjaScript-Strategy.** Der Orderweg läuft über ein AddOn mit
  Befehls-Whitelist, nicht über eine im Chart laufende Strategie.
- **Kein MGC** als analysiertes, gespeichertes oder protokolliertes Instrument.
- **Kein Tradovate** in irgendeiner Form.
- **Keine Multi-Instrument-Architektur** für aktuell nicht benötigte Instrumente.
- **Kein Anthropic-API-Aufruf** irgendwo im Repository.
- **Das LLM ist kein Messinstrument.** Claude interpretiert bereitgestellte
  Kennzahlen und erzeugt keine.
- **Kein blindes Optimieren** auf die beste Equity-Kurve.
- **Kein maschinelles Lernen**, bevor Datengrundlage, Feature Store und
  Validierung stehen.
- **Keine erfundenen Zahlen.** Lieber `null` mit Begründung.

---

## W. Nächster konkreter Schritt

**Empfehlung: Etappe C+ — den Ideen-Dauerlauf einrichten.**

**Warum dieser und kein anderer:** Es ist der einzige P0-Punkt, bei dem
Verzögerung **unwiederbringlich** ist. Code lässt sich jederzeit nachbauen;
vergangene Marktdaten nicht. Etappe D, der Feature Store und jede Research-Stufe
warten auf denselben Datenbestand. Bei ~13 Ideen je Woche über 8 Kategorien
dauert Laurins Schwelle von 20 je Kategorie ohnehin Monate — jeder Tag
Verzögerung verschiebt alles Nachfolgende um einen Tag.

**Umfang, klein gehalten:**

1. Geplante Windows-Aufgabe, stündlich (nicht täglich — die Blackout-Prüfung
   deckt nur die letzten 7 Tage ab, und stündlich hält die Kalenderantwort
   belastbar).
2. Wrapper analog `pruefe_datenluecken_taeglich.bat`, Ausgabe in eine Logdatei.
3. Ein Betriebsnachweis nach einigen Läufen: Ideen entstehen, sind
   nachvollziehbar, Duplikate entstehen nicht.

**Zwei Dinge, die ich dabei mitnehmen würde**, weil sie Minuten kosten und
sonst später stören: die zwei Tradovate-Defekte aus C.1.

### Was auf Laurins Entscheidung wartet

1. **MGC im Instrument-Register belassen?** (C.2) Meine Empfehlung: ja, aber
   aus nutzersichtbaren Texten entfernen. Der Register-Eintrag kostet nichts
   und der MGC-Verfallstest sichert ab, dass `expiry_rule` überhaupt
   instrumentspezifisch ist.
2. **Reihenfolge nach C+:** Etappe D oder Feature Store zuerst? Ich rate zu
   **D**, weil es die Projektfrage für die vier vorhandenen Familien direkt
   beantwortet und den Maßstab für alles Spätere setzt.
3. **MCP-Startzeit jetzt oder später?** Sie stört heute (Cowork/Code-Timeouts)
   und ist ein abgegrenzter Eingriff.

---

## X. Nachtrag 23.08.2026 — zwei Befunde, die beim Gegenlesen dazukamen

Dieser Plan wurde am selben Tag ein zweites Mal gegen den Code gelesen. Zwei
Punkte fehlten und gehören zu Abschnitt C (veraltete Komponenten) und
Abschnitt Q (Priorisierung).

### X.1 Die Dukascopy-Historie ist über den Backtest-Pfad nicht erreichbar

`backtest/data/__init__.py::create_provider` kennt **ausschließlich** `"csv"`:

```python
key = name.lower()
if key == "csv":
    return CsvDataProvider(**kwargs)
raise DataProviderError(f"Unbekannte Datenquelle {name!r}. Verfuegbar: 'csv'.")
```

`DukascopyStore` existiert, ist getestet und hält 3 179 672 Kerzen — aber es
gibt **keinen** `DukascopyDataProvider` und keine Registrierung. Die Engine
kommt an die einzige lange Historie des Projekts nicht heran; erreichbar sind
nur CSV-Dateien aus `data/`, und das ist dort ausschließlich der synthetische
`DEMO_1m.csv`.

**Damit ist Abschnitt A.3 („kein Backtest auf echten Marktdaten gerechnet")
nicht nur eine Frage der Zeit, sondern eine fehlende Codezeile.** Der Umweg
über einen CSV-Export wäre möglich, würde aber die Herkunftstabelle aus
`DukascopyStore` abschneiden — und damit die Näherungskennzeichnung, die nach
Invariante 10 bis ins Ergebnis mitwandern muss.

**Einstufung: P0.** Klein im Aufwand (`DataProvider` implementieren,
`finalize()` der Basisklasse erledigt Normalisierung und Validierung,
in `create_provider` eintragen), groß in der Wirkung: ohne diesen Schritt gibt
es keinen einzigen Backtest über mehr als vier Tage.

**Test dazu:** `create_provider("dukascopy")` liefert einen Provider, **und**
das Ergebnis trägt die Näherungskennzeichnung weiter. Der zweite Teil ist der
wichtigere.

### X.2 Walk-Forward ist gebaut, getestet und nicht aufrufbar

`backtest/splits.py::walk_forward_windows` erzeugt rollierende
(Trainings-, Test-)Fenster, ist getestet und wird in diesem Plan an mehreren
Stellen als Kern der Confirmation-Phase vorausgesetzt.

Die CLI kennt vier Kommandos: `list`, `run`, `compare`, `optimize`. **Kein
`walkforward`.** Auch `compare.py` ruft die Funktion nicht auf. Es ist toter,
aber korrekter Code — die aussagekräftigste Prüfung des Projekts ist derzeit
nur aus einem Python-Interpreter heraus erreichbar.

**Einstufung: P1**, direkt hinter X.1 (ohne lange Historie hätte ein
Walk-Forward nichts, worüber er rollen könnte). Das Verhältnis von Aufwand zu
Erkenntnisgewinn ist das beste in diesem ganzen Plan: die Rechenlogik steht,
es fehlt der Einstiegspunkt.

**Test dazu:** Fenster überlappen nicht, und kein Testfenster liegt vor seinem
Trainingsfenster — ein Lookahead-Test, kein Formtest.

### X.3 Folge für die Priorisierung

Die Reihenfolge aus Abschnitt Q bleibt, ergänzt um:

| Rang | Punkt | Begründung |
|---|---|---|
| P0 | X.1 Dukascopy-Provider | schaltet zehn Jahre Historie überhaupt erst frei |
| P1 | X.2 `walkforward`-Kommando | größter Erkenntnisgewinn pro Zeile Arbeit |

Beide berühren **keinen** der Punkte, die die Session nicht selbst entscheiden
darf: keine Entry-/Stop-/Ziel-Regeln, kein Umfang der Setup-Familien, nichts an
der Ordersperre. Es sind Erreichbarkeitslücken, keine Entwurfsfragen.
