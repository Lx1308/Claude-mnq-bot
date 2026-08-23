# NORMALER_CHAT_KONTEXT.md

**Dauerhaftes Gedächtnis der inhaltlichen Projektseite.**
Für künftige Claude-Chat-Sessions ohne Zugriff auf den alten Verlauf.

**Stand: 23. August 2026** — vollständig gegen Code, Datenbanken und Testlauf
gegengeprüft, nicht aus Notizen fortgeschrieben.
**Ergänzt 22. August 2026: Legacy-Pfad (Tradovate/Telegram/Alarme) entfernt.**
**Ergänzt 21. August 2026 (nachts): Etappe A und B erstmals mit echten
NT8-Live-Marktdaten verifiziert (siehe Abschnitt 17).**
**Ergänzt 22. August 2026: Profil-Begriff entflochten (Abschnitt 8) — `profil`
und `rules` sind zwei verschiedene Dinge und hießen vorher beide „Profil".**

> **Es gibt jetzt vier Kontextdateien**, nicht mehr zwei:
>
> | Datei | Rolle |
> |---|---|
> | `NORMALER_CHAT_KONTEXT.md` (diese) | **WAS und WARUM** — Ziele, Anforderungen, Historie |
> | `CODE_CHAT_KONTEXT.md` | **WIE und WIE WEIT** — Architektur, Stand, Bugs, Tests |
> | `MASTERPLAN.md` | **WOHIN** — Zielarchitektur, Research-Engine, Etappen bis zum Ende |
> | `ETAPPE_C_SPEZIFIKATION.md` | verbindliche Vorgabe der Ideen-Protokollierung |
> Beide Dateien gehören zusammen ins Projekt. Diese hier sagt **WAS und WARUM**,
> die andere **WIE und WIE WEIT**.

---

## 1. WAS GEBAUT WIRD

Ein lokal laufendes Analysewerkzeug für Futures-Trading. Laurin fragt in **Claude
Desktop** nach der Marktlage und bekommt eine dichte technische Einordnung —
Level, Indikatoren über mehrere Zeitebenen, Marktstruktur, Terminrisiko. Parallel
protokolliert das System im Hintergrund regelbasiert Trade-Ideen, um nach einigen
Wochen auswerten zu können, welche Setups tatsächlich einen Erwartungswert haben.

**Ausgangsproblem:** Vorher musste er für jede Einschätzung Chart-Screenshots
hochladen. Langsam, ungenau (Preise wurden aus Bildern abgelesen), nicht
protokollierbar.

**Langfristiges Ziel des Nutzers:** autonomes Handeln — erst Demo, dann live.
Der Weg dorthin führt ausdrücklich über die Auswertung (Tool 4/5), nicht daran
vorbei.

---

## 2. DER NUTZER

Laurin, Privattrader. Intraday-Futures, **ausschließlich MNQ**.
Zeitebenen 1m/5m/15m, Haltedauer oft nur Minuten.

> **Override vom 23.08.2026:** MGC ist aus dem Projekt heraus. Es wird nicht
> analysiert, gespeichert, protokolliert oder als Erweiterung geplant. Ältere
> Stellen in dieser Datei, die MGC erwähnen, sind historisch und **nicht mehr
> gültig**. Zum verbliebenen Register-Eintrag siehe Abschnitt 18.

- Kann kein C#, Python nur oberflächlich
- Braucht für alles außerhalb des Codes Schritt-für-Schritt-Anleitungen
- **Diktiert häufig per Sprache** — Transkriptionsfehler sind normal, bei
  Unklarheit nachfragen statt raten
- Will die **Begründung** bei technischen Entscheidungen, nicht nur das Ergebnis
- Will **keine erfundenen Zahlen**. Lieber null mit Begründung als eine
  Schätzung, die aussieht wie eine Messung. Das ist ein tragendes Prinzip des
  ganzen Projekts.
- Sagt selbst: das Werkzeug soll ihn **besser** machen, nicht nur schneller

---

## 3. ANFORDERUNGEN

### MUSS

- On-Demand-Analyse in Claude Desktop, ohne Screenshots
- Kostenlos im Betrieb (siehe 4.)
- Level, Indikatoren, Marktstruktur, Muster über 1m/5m/15m plus 1h/1d als Kontext
- Wirtschaftskalender mit Blackout-Fenstern
- Hintergrund-Protokollierung von Trade-Ideen mit Entry, Stop, Ziel, CRV
- Spätere Auswertung: welche Setups tragen, welche nicht
- Keine stillen Ausfälle

### SOLLTE

- Zwei Regelwerke in der Auswertung: ohne Einschränkungen und Lucid
  (`rules`, siehe Abschnitt 8)
- Dauerbetrieb auf dem Laptop

### OPTIONAL / SPÄTER

- Order-Ausführung (bewusst gesperrt, siehe 7.)
- Kumulatives Delta (braucht kostenpflichtiges NT8-Add-on)

---

## 4. KOSTENRAHMEN — harte Anforderung

Mehrfach betont: **ohne laufende Kosten**.

- **Nichts im Projekt ruft die Anthropic-API auf.** Interpretation passiert in
  der Claude-Desktop-Unterhaltung über das bestehende Abo. Seit dem 22.08.2026
  prüft ein Test das für das **gesamte** Repository, nicht mehr nur für den
  MCP-Server — es gibt keine Stelle mehr, die die API rufen dürfte.
- Der ältere Telegram-/Alert-Pfad kostete Token je Alarm und ist am 22.08.2026
  **vollständig entfernt** worden. Die frühere Notiz „bleibt bestehen, ist aber
  nicht mehr das Ziel" ist damit aufgehoben.
- Einzige akzeptierte Ausgabe: ~4 USD/Monat CME-Marktdaten bei NinjaTrader.
  Nur das Paket **CME Index** für MNQ; die frühere Überlegung zu einem zweiten
  Paket für COMEX Metals ist mit dem Override vom 23.08.2026 hinfällig.

Wichtige Klarstellung, die im Chat mehrfach nötig war: **Claude Pro deckt keine
API-Aufrufe ab.** Abo und API sind getrennte Dinge.

---

## 5. DATENQUELLEN-HISTORIE — nicht erneut aufrollen

Fünf Ansätze wurden geprüft. Alle Ablehnungen haben konkrete Gründe:

| Ansatz | Status | Grund |
|---|---|---|
| TradingView API | VERWORFEN | Keine offizielle API für Chartdaten, nur Alerts/Webhooks raus |
| TradingView MCP (Chrome DevTools) | VERWORFEN | Community-Projekt auf undokumentierten internen APIs; braucht zusätzlich bezahltes TV-Abo; mehr Fragilität ohne Gewinn |
| Tradovate API | VERWORFEN | Verlangt LIVE-Konto mit 1.000 USD plus kostenpflichtiges Add-on. Mit Prop-Firm-Sim-Kapital nicht erfüllbar. Fiel erst auf, als der mcp_server größtenteils darauf gebaut war. |
| yfinance | VERWORFEN | Kostenlos, aber 15+ Minuten Verzögerung bei Futures. Vom Nutzer abgelehnt. |
| **NinjaTrader 8 / NinjaScript** | **AKTIV, seit 21.08.2026 live bewiesen** | Offizielle dokumentierte API, kein Reverse Engineering. Echtzeitdaten laufen ohnehin durch den Chart. Keine Zusatzkosten. Lokal. Lucid unterstützt NT8 ausdrücklich. |

**Nachtrag 21.08.2026:** Die Entscheidung für NinjaTrader hat sich bestätigt.
Der Live-Test lieferte MNQ-Kerzen mit unter 2 Sekunden Verzögerung in die
Datenbank — also echte Echtzeitdaten, nicht die 15-Minuten-Verzögerung, an der
yfinance gescheitert war. Die offene Frage, ob der kostenlose
NT8-Simulationsfeed verzögert liefert, ist damit **praktisch beantwortet: er
liefert zeitnah.** Ein Gegencheck gegen TradingView zur endgültigen Bestätigung
wäre trotzdem sinnvoll, wurde aber noch nicht gemacht.

**Lehre daraus, die in künftigen Sessions gilt:** Bei jeder neuen Datenquelle
ZUERST prüfen, welche Konto- und Kostenvoraussetzungen sie hat. Der
Tradovate-Umweg kostete erhebliche Arbeit, weil das zu spät geprüft wurde.

**Altlast erledigt (22.08.2026):** Der Tradovate-Code ist entfernt —
`live_bot/` vollständig, `backtest/data/tradovate_provider.py`, der
`tradovate:`-Abschnitt in `config.yaml` und alle `TRADOVATE_*`-Variablen aus der
`.env`. Wer die Altlast in älteren Notizen erwähnt findet: es gibt sie nicht
mehr.

---

## 6. KONTOSTATUS — hat sich geändert

**Historisch:** Lucid-Trading-Challenge (25K). **Nicht bestanden.**

**Aktuell:** Eigenes NinjaTrader-Simulationskonto, ausschließlich als Datenquelle
und Testumgebung. Dort gelten **keine** Prop-Firm-Regeln — kein Zwangsschluss,
kein Overnight-Verbot, kein Drawdown-Limit, kein Hedging-Verbot.

**Ziel bleibt**, später wieder eine Lucid-Challenge zu starten. Deshalb müssen
die Lucid-Regeln als optionales Regelwerk modellierbar bleiben.

> **Wichtig für künftige Chats:** Wenn Lucid-Regeln im Code auftauchen, sind sie
> ein **Simulationsmodell**, kein Abbild des aktuellen Kontostatus. Nie verwechseln.

### Lucid-Regeln (recherchiert, aus deren FAQ)

**Regeln, die einzelne Ideen-Ausgänge verändern:**
- Mindesthaltedauer 5 Sekunden; über 50 % Gewinn aus Trades unter 5 s → Markierung
- Alle Positionen glatt bis 16:45 EST — Position wird zum Marktpreis geschlossen,
  unabhängig davon, ob Stop oder Ziel erreicht war
- Kein Halten über Nacht auf Sim-Funded
- Kein Hedging, auch nicht kontenübergreifend

**Regeln, die den Kontoverlauf betreffen (der wichtigere Teil):**
- **Trailing Drawdown ist END-OF-DAY, nicht intraday** — unrealisierte Verluste
  während der Session lösen keinen Verstoß aus. Wesentlicher Unterschied zu
  intraday-trailenden Firmen.
- Der Trailing Drawdown wird zum **statischen Boden**, sobald die Schwelle das
  ursprüngliche Kontoguthaben erreicht
- 25K: kein Daily Loss Limit (gilt erst ab 50K). Trotzdem konfigurierbar bauen.
- Konto gilt als gerissen, wenn die Max-Loss-Schwelle unterschritten wird

**Weiteres:**
- Automatisierte Strategien und Trade-Copier erlaubt, keine Genehmigung nötig
- Hochfrequenzhandel verboten, automatisierte Erkennung
- 30 Tage ohne Handel → Konto wird dauerhaft gelöscht
- **Trader trägt volle Verantwortung für Softwarefehler**

Der letzte Punkt ist die Begründung für Abschnitt 7.

**Konkrete Zahlen** (Profit-Ziel, Max-Loss, Startkapital) dürfen **nicht hart
verdrahtet** werden — Platzhalter mit Kommentar, plus Hinweis, sie vor Gebrauch
auf Lucids Website zu verifizieren.

---

## 7. DINGE, DIE AUSDRÜCKLICH NICHT GEMACHT WERDEN

- **Keine Order-Ausführung**, auch nicht als inertes Interface. Kein
  `send_trade_signal`, keine NinjaScript-Strategy, kein Lesen von Konto- oder
  Positionsdaten.
  Grund: Es existiert noch keine einzige protokollierte Idee, also keine
  Erwartungswert-Statistik. Ausführung davor wäre eine Wette auf eine ungetestete
  Hypothese mit dem Konto als Einsatz.
  *Struktureller Schutz:* `ClaudeBridge.cs` ist ein **Indikator**, und ein
  Indikator kann in NinjaTrader keine Orders platzieren.
- **Kein Anthropic-API-Aufruf im `mcp_server/`-Pfad** (Kostenregel)
- **Keine LLM-basierte Ideen-Protokollierung.** Entschieden: regelbasiert.
  Grund: Eine Regel ist auswertbar, nachjustierbar und automatisierbar. Eine
  LLM-Einschätzung ist nicht reproduzierbar — zwei Aufrufe mit gleichen Daten
  können abweichen. Als Grundlage für "wird über die Zeit besser" unbrauchbar.
- **Keine getrennten Logs pro Profil.** Eine gemeinsame Ideen-DB mit Profil-Feld.
  Grund: Bei getrennten Dateien ließe sich später nicht mehr fragen, wie ein
  Setup unter dem anderen Regelwerk abgeschnitten hätte.
- **Kein Mehr-Instrument-Stream und keine Multi-Instrument-Architektur.**
  Ausschließlich MNQ (Override 23.08.2026).
- **Keine Schätzungen, die wie Messungen aussehen.** Delta bleibt null statt
  geraten. Volume Profile ist als Näherung gekennzeichnet.

---

## 8. PROFIL-ARCHITEKTUR UND AUSWERTUNG — die eigentliche Zielfrage

> **Begriffsklärung vom 22.08.2026 — vorher stand hier eine Vermischung.**
> Ältere Fassungen dieser Datei sprachen von „zwei Profilen `demo`/`lucid`"
> und meinten damit *beides zugleich*: auf welchem Konto gehandelt wurde
> **und** nach welchem Regelwerk gerechnet wird. Das sind zwei verschiedene
> Dinge, und sie werden seither getrennt geführt.

**Erstens: `profil` — was tatsächlich war.** Ein Feld an jeder Idee, gesetzt
beim Protokollieren. Reine Herkunftsdokumentation, kein Steuerungsfeld.

| Wert | Bedeutung |
|---|---|
| `sim_frei` | eigenes NinjaTrader-Simulationskonto, keine Prop-Firm-Regeln (aktuell) |
| `lucid_challenge` | laufende Lucid-Challenge |
| `lucid_funded` | bestandene Challenge, Sim-Funded |

Der Wertebereich steht in `config.yaml` unter `ideas.profile_erlaubt`; ein
Tippfehler bricht beim Start ab, statt die Auswertung still in zwei Gruppen zu
zerlegen.

> **Warum nicht `demo`:** `config.yaml` enthält bereits `environment: demo`
> unter `tradovate:` — das ist die Broker-Umgebung. Ein eigener Wertebereich
> macht die Verwechslung unmöglich.

**Zweitens: `rules` — was gewesen wäre.** Ein Parameter von
`evaluate_past_ideas`, gesetzt beim Auswerten:

| Wert | Bedeutung |
|---|---|
| `none` | keine Einschränkungen: kein Zwangsschluss, Overnight erlaubt, keine Haltedauer-Grenze, kein Drawdown-Limit, Hedging erlaubt |
| `lucid` | alle Regeln aus Abschnitt 6 aktiv |
| `both` | beides nebeneinander |

Alle Werte konfigurierbar, keine Magic Numbers im Code.

**Eine gemeinsame Ideen-Datenbank** mit Profilfeld je Idee.

**Entscheidend:** Bei `rules="both"` werden **alle** Ideen durch **beide**
Regelwerke gerechnet — unabhängig von ihrem `profil`. Das Feld wird dabei
ausdrücklich **nicht** als Filter benutzt; nur so lässt sich die Zielfrage
unten überhaupt beantworten. Als *optionaler* Filter bleibt es abrufbar
(„nur die Ideen vom echten Prop-Firm-Konto").

Bei `"both"` wird jede Idee **zweimal** ausgewertet und beides nebeneinander
ausgegeben, plus:
Bei `"both"` wird jede Idee **zweimal** ausgewertet und beides nebeneinander
ausgegeben, plus:

1. Wie viele Ideen wären unter Lucid **gar nicht zustande gekommen**
   (Hedging, Mindesthaltedauer)?
2. Wie viele hätten einen **anderen Ausgang** gehabt (Zwangsschluss statt
   Ziel/Stop)?
3. Wäre das **Konto in der Sequenz gerissen** — und wenn ja, wann?
4. **Erwartungswert in R** unter beiden Regelwerken.

**Die eigentliche Frage, die beantwortet werden soll (wörtlich):**

> "Welche meiner Setups tragen auch unter Prop-Firm-Regeln, und welche sehen nur
> gut aus, weil sie über Nacht laufen durften."

**Pflicht-Test:** Ein expliziter Test muss sicherstellen, dass die
EOD-Drawdown-Logik **nicht versehentlich intraday prüft**. Intraday wäre eine
erheblich strengere Regel als die tatsächliche und ließe die Setups zu Unrecht
schlecht aussehen.

---

## 9. REGELBASIERTE IDEEN-PROTOKOLLIERUNG

**Setups:** PDH/PDL-Bruch, VWAP-Reversion, Initial-Balance-Bruch,
Flaggen-Ausbruch.

**Filter:** ADX-Regime, Blackout-Fenster, Liquiditätszone, Dünnzone.

**Weiteres:** Schwellenwerte in `config.yaml`. CRV unter 1:1,5 wird als "unter
Schwelle" gekennzeichnet. Aktuell nur MNQ. Unter 20 Ideen pro Kategorie gilt
"zu wenig Daten".

---

## 10. ETAPPENSTRUKTUR A–F — verbindlich

Nicht umbenennen, nicht zusammenlegen, nicht überspringen.

| Etappe | Inhalt | Status (23.08.2026, gegen Code geprüft) |
|---|---|---|
| **A** | NinjaScript-Bridge, Indikator, HTTP POST | **ABGESCHLOSSEN**, live verifiziert |
| **B** | Empfänger, SQLite-Speicher, `NTBridgeBarSource` | **ABGESCHLOSSEN**, mit echten Daten verifiziert |
| **C** | Ideen-Protokollierung, regelbasiert, MNQ | **GEBAUT** — 4 Setup-Familien, 50 Tests. **Läuft aber in keinem Dauerprozess; es ist keine einzige echte Idee protokolliert.** |
| **C+** | Dauerlauf einrichten | **offen — der zeitkritische Punkt**, siehe Abschnitt 17 |
| **D** | Auswertung: `evaluate_past_ideas`, `get_performance_report` | offen |
| **E** | Dauerbetrieb-Härtung | offen |
| **F** | Liefergegenstände | teilweise erledigt |

**Neue Etappen G–L** (Feature Store, Regime, Research, Monitoring, Makro) sind
in `MASTERPLAN.md` Abschnitt R definiert und setzen **nach** C+ an.

> **Korrektur gegenüber älteren Fassungen dieser Datei:** Etappe B stand dort
> zuerst als "offen", dann als "Code fertig, aber nie mit echten Daten
> gelaufen". Beides ist überholt. Seit dem Live-Test am 21.08.2026 sind
> **Etappe A und B beide vollständig abgeschlossen** — inklusive Nachweis mit
> echten MNQ-Marktdaten. Details in `CODE_CHAT_KONTEXT.md` Abschnitt 9.

Der SQLite-Speicher aus Etappe B **ist** der ursprünglich verschobene Bar-Cache.
Damit füllen sich ATR-Perzentil, relatives Volumen, Volume Profile und Wochen-H/L
mit der Zeit von selbst — **das läuft jetzt tatsächlich an**, solange der
Empfänger mitläuft.

---

## 11. WAS BEREITS STEHT — **361 Tests grün**

```
common/instruments.py   Register mit Ticksize/Punktwert/Verfall.
                        Protokolliert und analysiert wird NUR MNQ.
common/sessions.py      Asien/London/NY, Globex, RTH je Instrument, DST-sicher
common/indicators.py    RSI/ATR/VWAP im Hot-Path; MACD, Stochastik, ADX,
                        Bollinger mit Keltner-Squeeze, EMA-Stack daneben
common/levels.py        PDH/PDL/PDC, Overnight, IB, Opening Range, Gap —
                        in Punkten, Ticks und ATR
common/structure.py     HH/HL vs LH/LL, BOS, CHoCH, RSI-Divergenz
common/patterns.py      Flagge, Dreieck, Doppeltop/-boden, Range-Kompression
mcp_server/             Tool 1 (get_market_snapshot), Tool 2 (get_event_risk),
                        list_instruments, cli.py (Terminal-Dump),
                        calendar_provider.py (Forex Factory + FRED)
ntbridge/               Empfänger + SQLite-Speicher (Etappe B) — LIVE VERIFIZIERT
ideas/                  Regelbasierte Ideen-Protokollierung (Etappe C)
backtest/               Eigene Event-Engine, Strategien, Metriken, Splits
ninjatrader/            ClaudeBridge.cs (v1.0.1) — KOMPILIERT UND LIVE VERIFIZIERT
```

**Testzahl-Historie:** 124 → 171 → 199 → 221 → 260 → 286 → 292 → **326**.
(Ältere Fassungen dieser Datei nannten 286 — das war ein Zwischenstand.)

**Backtest-Entscheidung:** Weder `backtesting.py` noch `vectorbt`, sondern eine
eigene Event-Engine (~300 Zeilen). Grund: `backtesting.py` hat kein Futures-Modell
(Kommission als Prozentsatz statt USD pro Seite, keine Kontraktmultiplikatoren);
`vectorbt` macht zustandsabhängige Regeln (Zeitstop, Sessionende, ATR-Stop relativ
zum noch unbekannten Einstieg) schwer debugbar. `vectorbt` bleibt als spätere
Screening-Schicht für große Parameter-Sweeps sinnvoll.
Ausführlich in `docs/BACKTESTING_ENTSCHEIDUNG.md`.

> **Präzisiert am 23.08.2026:** Auf **echten MNQ-Futures-Daten** wurde nie ein
> Backtest gerechnet — dafür reichen die ~4 Tage Historie nicht. Wohl aber auf
> der **Dukascopy-Näherung** (Index-CFD, 10 Jahre): erste Ergebnisse in
> `docs/BASISVERMESSUNG_2026-08-23.md`. Diese sind **rein informativ**.
> Ursprüngliche Formulierung: Seit 21.08.2026 liegen zwar erstmals echte Daten in
> der produktiven Datenbank, aber es ist **kein Backtest darauf gelaufen**.
> Daraus dürfen **keine** Aussagen über Strategiegüte abgeleitet werden.

---

## 12. BUG-LEHREN — der eigentliche Wert dieses Projekts

Alle bereits im Projekt aufgetreten. Alle von derselben Art: **sieht aus wie
"kein Signal", ist aber "Messung kaputt".**

Kurzfassung — **die technische Fassung mit Fundstelle im Code steht in
`CODE_CHAT_KONTEXT.md` Abschnitt 8:**

1. **Stille Ausfälle.** `candle_buffer_size` 500 bei 23-Stunden-Session →
   `prev_session_high` dauerhaft NaN, zwei Alarme hätten NIE ausgelöst, ohne
   Fehlermeldung. Korrigiert auf 3000/2880 plus abbrechende Startprüfung.
2. **Lookahead.** OOS-Block isoliert vorbereitet → erste ~50 Kerzen ohne
   gültigen SMA50, OOS-Zeitraum wäre still gekürzt worden.
3. **DST.** Tagesaddition auf dem Zeitstempel statt auf dem Datum.
4. **Selbstbezügliche Definition.** Squeeze als "unterstes Perzentil der letzten
   N Kerzen" wird bei anhaltender Ruhe zur eigenen Referenz und verschwindet,
   ausgerechnet bei größter Kompression. Ersetzt durch Keltner-Vergleich.
5. **Ungleich lange Fenster.** Range-Kompression verglich 20 gegen 60 Bars.
   Zufallsspannen wachsen mit √n, erwartetes Verhältnis 0,58 — unter der Schwelle
   von 0,6. Der Detektor hätte auf jedem Kursverlauf angeschlagen.
6. **Fail-safe statt fail-silent.** Kalender nicht erreichbar heißt
   `calendar_available: false`, NIEMALS "keine Termine" — das wäre eine Freigabe
   zum Handeln.
7. **Invarianten in den Service**, nicht in den Anbieter (Terminsortierung).
8. **Am Paket verifizieren.** FastMCP heißt in mcp 2.0 `MCPServer`. Der
   stdio-Transport löst stdout bereits auf fd-Ebene — ein `sys.stdout = sys.stderr`
   hätte den Kanal ZERSTÖRT statt geschützt.
9. **MGC-Verfallsregel.** MNQ rollt zum 3. Freitag, MGC zum drittletzten
   Geschäftstag des Liefermonats (G/J/M/Q/V/Z). MNQZ5 am 19.12., MGCZ5 am 29.12.
10. **InvariantCulture.** Auf deutschem Windows liefert `ToString()` "21345,25"
    mit Komma — ungültiges JSON, jede Kerze würde abgelehnt.
11. **Der Empfänger-Vertrag ist Teil der Bridge.** Ein Fremdwerkzeug schrieb
    `ClaudeBridge.cs` neu und änderte dabei Feldnamen (`ts_utc` statt
    `timestampUtc`) und ließ den Umschlag `{"bars":[…]}` weg. Jede Kerze wäre
    abgelehnt worden — kein Compiler meldet so etwas.

**Bestätigung dieser Vorsichtsmaßnahmen (21.08.2026):** Im ersten echten
Live-Lauf wurden **5669 Kerzen angenommen und 0 abgelehnt**. Kein einziger der
Ablehnungsgründe aus `validate_bar()` trat auf — weder Kommazahlen
(InvariantCulture), noch falsche Feldnamen, noch Zeitzonen-Versatz. Die aus den
Lehren 10 und 11 abgeleiteten Schutzmaßnahmen haben also im Realbetrieb
gehalten.

---

## 13. BEKANNTE EINSCHRÄNKUNGEN

- **Antwortzeit 10–30 Sekunden.** Für den Auslöser eines 1-Minuten-Einstiegs zu
  langsam. Der Nutzen liegt in der Vorbereitung und in der späteren Auswertung.
  Das wurde dem Nutzer mehrfach gesagt und ist akzeptiert.
  *(Betrifft den MCP-Roundtrip, nicht die Datenlieferung — die Bars selbst
  kommen mit unter 2 Sekunden an, wie der Live-Test zeigte.)*
- **Volume Profile ist eine Näherung.** Echtes Volume-at-Price bräuchte Tickdaten.
- **Kumulatives Delta bleibt null.** Braucht das kostenpflichtige NT8-Add-on
  "Order Flow +". Nicht lizenziert. Nachrüststelle im Code markiert. Wird
  **bewusst nicht geschätzt**.
- **Sekundärserien erben den Ladezeitraum des Charts.** Ein 1m-Chart mit wenigen
  Tagen liefert einer Tagesserie entsprechend wenige Tageskerzen. Tages- und
  Stundenebene gehören auf ein eigenes Chart mit großem Ladezeitraum. Daraus
  folgt zwingend **zwei Charts je Instrument** — seit 21.08.2026 genau so
  eingerichtet und in Betrieb.
- **Historienabhängige Kennzahlen brauchen Zeit:** Wochen-H/L 5 Sessions,
  Volume Profile 2, relatives Volumen 10, ATR-Perzentil 20. Bis dahin liefert das
  Feld `null` mit Begründung und Fortschrittsangabe — nie eine Schätzung.
  **Praktische Folge:** Der Empfänger sollte ab jetzt möglichst durchgehend
  mitlaufen, sonst dauert es entsprechend länger, bis diese Felder belastbar
  sind.
- **ISM/PMI und Fed-Reden ohne Actual-Wert.** ISM hat die FRED-Lizenz zurückgezogen.
- **Forex Factory ist ein inoffizieller Endpunkt** und kann brechen. Hat zudem
  **kein `actual`-Feld** — daher die Aufteilung: FF liefert Termine, FRED die
  Ist-Werte.
- **LLM-Chartanalyse aus Screenshots ist ungenau.** Preise werden abgelesen, nicht
  gemessen. Bei MNQ mit 0,25-Punkte-Ticks kann das um Punkte danebenliegen. War
  einer der Gründe für dieses Projekt.

---

## 14. KONTRAKTSPEZIFIKATIONEN

| | MNQ — das einzige gehandelte Instrument |
|---|---|
| Name | Micro E-mini Nasdaq 100 |
| Börsengruppe | CME Index |
| Ticksize | 0,25 Punkte |
| Punktwert | 2 USD |
| Kontraktmonate | H/M/U/Z |
| Verfall | 3. Freitag |
| NT8 Session Template | `CME US Index Futures ETH` |

> Die frühere MGC-Spalte ist mit dem Override vom 23.08.2026 entfallen. Die
> MGC-Verfallsregel bleibt als **Bug-Lehre 9** dokumentiert, weil sie erklärt,
> warum `expiry_rule` instrumentspezifisch sein muss.

**CME-Session:** Globex Sonntag 17:00 CT bis Freitag 16:00 CT, tägliche
Wartungspause 16:00–17:00 CT. Eine Session = 23 Stunden = 1380 Minutenkerzen.
Der Handelstag rollt um **18:00 ET** — ein Tick um 19:30 ET am Montag gehört zum
Handelstag Dienstag.

**Aktuell laufender Kontrakt (Stand 21.08.2026):** MNQ SEP26.

---

## 15. UMGEBUNG

- Windows-Laptop, Projektordner `C:\Users\lm130\Desktop\Claude chart bot`
- **Der Laptop ist der Datensammler** und soll dauerhaft laufen
  (Energiesparmodus aus, am Netzteil). Entscheidung gegen den PC, weil der
  Familienrechner ist und wochenweise wegfallen kann — **Datenlücken zerstören
  die Statistik**.
  **Ab 21.08.2026 ist das keine Theorie mehr:** Die Datensammlung läuft
  tatsächlich, jede Unterbrechung kostet jetzt echte Historie.
- Python 3.14.6 (Python Install Manager), venv im Projekt.
  `python` im PATH ist nur der Microsoft-Store-Platzhalter — immer
  `.venv\Scripts\python.exe` verwenden.
  **PowerShell-Hinweis:** Der Projektpfad enthält Leerzeichen, daher
  `cd "C:\Users\lm130\Desktop\Claude chart bot"` mit Anführungszeichen; ein Pfad
  ohne `cd` davor wird von PowerShell als Programmname interpretiert und
  scheitert.
- Claude Code als Desktop-App und als CLI installiert
- Git for Windows vorhanden, **das Projekt ist aber kein Git-Repository**
- NinjaTrader 8 mit eigenem Simulationskonto
- Externe SSD vorhanden, Projekt liegt aber auf dem Desktop

---

## 16. ARBEITSTEILUNG CHAT ↔ CLAUDE CODE

**Dieser Chat:** Planung, Analyse, Entscheidungen, Prompts für Claude Code,
Einordnung von Ergebnissen, Live-Chartanalyse auf Zuruf.

**Claude Code:** Technische Umsetzung im Projektordner.

**Wichtig:** Claude Code kann diesen Chat NICHT lesen. Projektwissen muss über
Dateien übergeben werden. Umgekehrt sieht dieser Chat den Code nicht — bei Fragen
zum tatsächlichen Stand muss der Nutzer ihn zeigen.

**Modellempfehlung für Claude Code:** Opus 5 mit Effort "Hoch" für Architektur
und knifflige Stellen. Für Boilerplate und Tests reicht Sonnet.

**Praktisch:** Berechtigungen dauerhaft setzen (Shift+Tab für den
Berechtigungsmodus), sonst fragt Claude Code alle zwei Minuten nach. Bei
Limit-Erreichung nach dem Reset `continue` tippen — der Kontext bleibt erhalten.

**Warnung zu unbeaufsichtigten Läufen:** Das Projekt hat **keine
Versionskontrolle**, und `ClaudeBridge.cs` wurde bereits zweimal von außen
zerstört (siehe Bug-Lehre 11). Solange kein Git-Repo existiert, gibt es bei
einem längeren unbeaufsichtigten Claude-Code-Lauf **kein Netz**, um eine
fehlerhafte Änderung zurückzunehmen. Ein Git-Repo anzulegen ist deshalb die
sinnvollste Voraussetzung für jede Arbeit ohne Aufsicht.

---

## 17. AKTUELLER STAND

> Der **technische** Detailstand steht in `CODE_CHAT_KONTEXT.md` Abschnitt 1
> und 9. Hier nur die Planungssicht.

### MEILENSTEIN 21.08.2026: Echte Marktdaten sind im System

Die zentrale offene Frage des gesamten bisherigen Projekts — *"kommen jemals
echte NT8-Daten an?"* — ist beantwortet. **Ja.**

Kurzfassung des Nachweises:
- `ClaudeBridge.cs` in NT8 kompiliert, fehlerfrei.
- Zwei Charts für MNQ SEP26 eingerichtet (1m mit 5m/15m, Day 1 mit 1h).
- Empfänger gestartet, Retry-Puffer lieferte die zwischengespeicherten Kerzen
  automatisch nach.
- **5669 Kerzen angenommen, 0 abgelehnt.** 4369 Bars in der produktiven
  Datenbank über alle 5 Zeitebenen.
- Live-Bars kamen mit **unter 2 Sekunden** Verzögerung an.
- Zeitzone stimmt ohne Versatz (`W. Europe Standard Time` = Europe/Berlin).

Damit sind **Etappe A und B abgeschlossen**. Ab hier sammelt das System
kontinuierlich Historie, solange der Empfänger läuft.

### Projektziel gerade

Etappe C **produktiv** machen: die Protokollierung steht, aber sie läuft nicht.
Solange sie an keinem Dauerprozess hängt, entsteht kein Datensatz — und ohne
Datensatz gibt es auch für Etappe D nichts auszuwerten.

### MEILENSTEIN 23.08.2026: erster Backtest über zehn Jahre

Auf der Dukascopy-Näherung (3 179 672 Kerzen, 2016–2026) liefen erstmals alle
vier Setup-Familien durch. **Ergebnis: alle vier negativ — und zwar brutto**,
also nicht bloß von Gebühren aufgefressen. Bei `prev_day_breakout` −2,00 USD je
Trade brutto gegen 5,00 USD Kosten.

**Das ist ein Befund, keine Niederlage:** genau dafür existiert das Projekt. Die
Setups laufen mit **nie angepassten Vorgabeparametern**; „keine Kante bei diesen
Parametern" ist nicht „keine Kante möglich". Details in
`docs/BASISVERMESSUNG_2026-08-23.md` und `MASTERPLAN.md` Abschnitt X.

### Erledigt

- Gesamte Rechenlogik in `common/` (**361 Tests grün**)
- MCP-Server mit Tool 1 und Tool 2, Terminal-Dump
- **Etappe A abgeschlossen** (Bridge kompiliert, zwei Charts, live sendend)
- **Etappe B abgeschlossen** (Empfänger, SQLite-Speicher, BarSource — mit
  echten Daten verifiziert)
- **Etappe C gebaut** (22.08.2026): 4 Setup-Familien, 4 Filter mit drei
  Ausgängen, zwei getrennte Logs — aber noch an keinen Dauerlauf gehängt
- Lokales Git-Repo, README auf das Zielsystem umgestellt und um Etappe C
  ergänzt
- **Legacy-Pfad vollständig entfernt** (22.08.): `live_bot/`, Tradovate-Provider,
  Config-Abschnitte, Secrets. Kostengarantie gilt jetzt repo-weit.
- **Dukascopy-Näherungshistorie** vollständig geladen (10 Jahre, 384 MB)
- **`MASTERPLAN.md`** (23.08.): Zielarchitektur, Research-Engine, Etappen G–L

### Offen

1. **HOCH:** Etappe C an einen Dauerlauf hängen. Die Protokollierung ist gebaut
   und getestet (4 Setup-Familien), wird aber von **keinem** laufenden Prozess
   aufgerufen — es ist bislang keine einzige echte Idee entstanden.
2. **HOCH:** Empfänger dauerhaft mitlaufen lassen; Laptop nicht schlafen legen.
   Jede Lücke kostet Historie, die historienabhängige Kennzahlen brauchen.
3. **MITTEL:** Etappe D — `evaluate_past_ideas`, `get_performance_report`.
4. **MITTEL:** Regelwerk-Simulation für `rules="lucid"` inklusive
   EOD-Trailing-Drawdown über die Kontofolge. (Das `profil`-Feld selbst ist
   seit 22.08.2026 fertig — es dokumentiert nur die Herkunft, siehe
   Abschnitt 8.)
5. **MITTEL:** Die 8 weiteren Setup-Familien (Spezifikation 2.2), schrittweise.
6. **MITTEL:** Etappen E–F.
7. **NIEDRIG:** Privates GitHub-Repo anlegen und pushen. Das **lokale** Git-Repo
   steht seit dem 21.08. samt geprüfter `.gitignore` (`.env`, `.venv/`, `logs/`,
   `*.sqlite3`); ein Push braucht **Laurins ausdrückliche Freigabe** und ist
   deshalb offen.
8. **NIEDRIG:** Gegencheck, ob der NT8-Feed wirklich Echtzeit ist (Vergleich mit
   TradingView). Nach dem Live-Test praktisch schon sehr wahrscheinlich.
9. **NIEDRIG:** `laeuft_seit_utc` in `/status` zeigt nach frischem Start ein
   altes Datum — vermutlich ein persistierter DB-Wert statt der echten
   Prozesslaufzeit. Kosmetisch, aber irreführend.

> **Korrektur gegenüber älteren Fassungen:** Die früheren Punkte 1–5 unter
> "Offen" (kompilieren, Empfänger starten, Charts einrichten, Erfolgstest,
> Etappe B verifizieren) sind **alle erledigt**.
>
> **Korrektur vom 22.08.2026:** Der Punkt "README aktualisieren — beschreibt nur
> den Tradovate-Pfad" war **veraltet**; die README war bereits auf
> NinjaTrader/MCP umgestellt. Die tatsächliche Lücke war eine andere: `ideas/`
> kam darin überhaupt nicht vor. Das ist jetzt Abschnitt 8 der README. Der Punkt
> ist damit erledigt und aus der Liste entfernt.

### Blocker

**Keine.** Der einzige echte Test — ob der nie kompilierte C#-Code in
NinjaTrader funktioniert — ist bestanden.

### Unsicherheiten

- Ob der NT8-Feed formal als Echtzeit gilt (praktisch verhielt er sich so).
- Wie gut die Dukascopy-Näherung über **lange** Zeiträume trägt. Geprüft ist
  ein Tag: r = 0,95 auf Minutenänderungen, Niveauabstand −86 Punkte,
  Volumenkorrelation +0,79.

> **Erledigte Unsicherheiten (21.08.2026):** `IsSuspendedWhileInactive`
> kompiliert; `System.Net.Http` ist ohne Zusatzreferenz verfügbar; die NT8-
> Zeitzone weicht nicht von Windows ab; "Days to load 7" reicht für die
> 1m-Serie (3015 von 3000 Ziel-Kerzen erreicht).
>
> **Erledigt am 23.08.2026:** Die Frage nach getrennten CME-Datenpaketen für
> MNQ und MGC ist durch den Override gegenstandslos — MGC kommt nicht dazu.

---

## 18. OFFENE FRAGEN AN LAURIN

**Stand 23.08.2026.** Diese Punkte blockieren Entscheidungen und lassen sich
nicht aus Code oder Dokumentation ableiten.

### 18.1 Sind die angesetzten Handelskosten realistisch?

Die Basisvermessung rechnet mit **2,50 USD je Seite** Kommission plus 1 Tick
Slippage, also **5,00 USD Round-Turn**. Bei MNQ mit 2 USD je Punkt muss ein
Setup damit **2,5 Punkte** verdienen, nur um bei null zu landen.

Für Micro-Kontrakte ist das hoch — Discount-Broker liegen eher bei 0,50–1,50
je Seite. **Was zahlst du tatsächlich?** Der Wert steht in `config.yaml` unter
`backtest.commission_per_side` und verändert jedes Ergebnis der Vermessung
erheblich.

### 18.2 MGC im Instrument-Register belassen?

Der Override sagt, MGC sei vollständig raus. **Erfüllt ist das schon heute**,
soweit es zählt: MGC wird nicht analysiert, gespeichert oder protokolliert.

**Nicht erfüllt:** MGC steht weiter im Register (`common/instruments.py`) und in
14 Testfällen. Die Empfehlung in `MASTERPLAN.md` C.2 ist, das so zu lassen —
der MGC-Verfallstest ist der **einzige** Nachweis, dass `expiry_rule`
instrumentspezifisch ist und nicht eine hartverdrahtete MNQ-Annahme
(Bug-Lehre 9). Fällt er weg, kann die MNQ-Regel später still falsch werden.

**Deine Entscheidung:** Register-Eintrag behalten (Empfehlung) oder komplett
entfernen?

### 18.3 Research-Engine vor Etappe D?

Ursprünglich war Etappe D (`evaluate_past_ideas`) als Nächstes vorgesehen. Nach
der Basisvermessung ist die Empfehlung **geändert**: Etappe D würde vier Setups
auswerten, die brutto keine Kante zeigen. Eine Einzelfaktor-Research würde
stattdessen systematisch suchen, unter **welchen Bedingungen** überhaupt eine
entsteht — und das ist auf den zehn Jahren Näherungshistorie sofort rechenbar.

**Deine Entscheidung:** Reihenfolge nach dem Dauerlauf — D oder Research?

### 18.4 MCP-Startzeit jetzt beheben?

Der Server braucht **7,5 Sekunden** bis zur ersten Antwort, fast ausschließlich
pandas-Import. Cowork und Code laufen dabei in einen Timeout; Claude Desktop
hält seine Instanz offen und ist unauffällig. Abgegrenzter Eingriff: pandas
verzögert importieren.

### 18.5 Parallele Sitzungen auf einem Arbeitsbaum

Am 22. und 23.08.2026 kam es dreimal zu Zwischenfällen: verwaiste Git-Sperren
(vier Stück, bis zu 24 h alt), ein halb ausgeführter `checkout`, ein veralteter
Index. Jedes Mal ging es gut, weil vor dem Eingriff geprüft wurde — **das ist
Glück, kein Verfahren.** Solange zwei Sitzungen denselben Arbeitsbaum
beschreiben, ist Datenverlust eine Frage der Zeit.

**Empfehlung:** immer nur eine schreibende Sitzung.

---

## 19. KONSISTENZ UND PFLEGE

**Es gibt vier Kontextdateien** (seit 23.08.2026, vorher zwei). Alle gehören
ins Claude-Projekt:

| Datei | Inhalt | Ändert sich |
|---|---|---|
| `NORMALER_CHAT_KONTEXT.md` (diese) | WAS/WARUM, Anforderungen, Historie, offene Fragen | selten |
| `CODE_CHAT_KONTEXT.md` | WIE, Module, technischer Stand, Bugs mit Fundstelle, Tests | bei Bauarbeiten |
| `MASTERPLAN.md` | WOHIN, Zielarchitektur, Research-Engine, Etappen G–L | selten |
| `ETAPPE_C_SPEZIFIKATION.md` | verbindliche Vorgabe der Ideen-Protokollierung | abgeschlossen |

**Bei Widersprüchen gilt die Rangfolge:**

1. **tatsächlicher Code** — Wahrheit über den aktuellen Implementierungsstand
2. **`CODE_CHAT_KONTEXT.md`** — Wahrheit über technische Umsetzung und Historie
3. **`MASTERPLAN.md`** — Wahrheit über die geplante Zielarchitektur
4. **diese Datei** — Wahrheit über Ziele, Anforderungen und Gründe

**Der MNQ/NinjaTrader-Override vom 23.08.2026 geht allen älteren MGC- und
Tradovate-Angaben vor**, unabhängig davon, in welcher Datei sie stehen.

Ein Widerspruch wird **festgestellt und dokumentiert**, nicht stillschweigend
aufgelöst.

**Hochladen ins Claude-Projekt:** Was dort liegt, ist eine eingefrorene Kopie.
Sie aktualisiert sich **nicht** automatisch, wenn Claude Code die Datei auf der
Festplatte fortschreibt. Nach Meilensteinen neu hochladen. Das Datum in der
Kopfzeile verrät, ob die hochgeladene Fassung noch aktuell ist.

**Hinweis zu diesem Update (21.08.2026):** Der Meilenstein-Eintrag in
Abschnitt 17 wurde **im normalen Chat** auf Basis der vom Nutzer eingefügten
NinjaTrader- und `/status`-Ausgaben geschrieben, nicht durch Prüfung gegen den
Quellcode. Die Zahlen stammen direkt aus den Live-Ausgaben und sind insofern
belastbar; die Rangfolge oben gilt trotzdem unverändert.
