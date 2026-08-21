# NORMALER_CHAT_KONTEXT.md

**Dauerhaftes Gedächtnis der inhaltlichen Projektseite.**
Für künftige Claude-Chat-Sessions ohne Zugriff auf den alten Verlauf.

**Stand: 21. August 2026** — gegen den tatsächlichen Code verifiziert.
**Ergänzt 21. August 2026 (nachts): Etappe A und B erstmals mit echten
NT8-Live-Marktdaten verifiziert (siehe Abschnitt 17).**

> **Schwesterdatei:** `CODE_CHAT_KONTEXT.md` enthält die technische Seite —
> Architektur, Module, Implementierungsstand, Bugs mit Fundstelle im Code, Tests.
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

Laurin, Privattrader. Intraday-Futures, hauptsächlich **MNQ**, gelegentlich
**MGC**. Zeitebenen 1m/5m/15m, Haltedauer oft nur Minuten.

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

- MGC-Analyse auf Abruf (Protokollierung nur MNQ)
- Zwei Regelprofile: demo und lucid
- Dauerbetrieb auf dem Laptop

### OPTIONAL / SPÄTER

- Order-Ausführung (bewusst gesperrt, siehe 7.)
- Kumulatives Delta (braucht kostenpflichtiges NT8-Add-on)

---

## 4. KOSTENRAHMEN — harte Anforderung

Mehrfach betont: **ohne laufende Kosten**.

- Der MCP-Server ruft **niemals** die Anthropic-API auf. Interpretation passiert
  in der Claude-Desktop-Unterhaltung über das bestehende Abo. Ein Test sichert
  das ab.
- Der ältere Telegram-/Alert-Pfad ruft die API auf und kostet Token. Bleibt
  bestehen, ist aber nicht mehr das Ziel.
- Einzige akzeptierte Ausgabe: ~4 USD/Monat CME-Marktdaten bei NinjaTrader.
  MNQ (CME Index) und MGC (COMEX Metals) liegen in verschiedenen Börsengruppen —
  eventuell zwei Pakete nötig.

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

**Altlast:** Der Tradovate-Code liegt weiterhin im Projekt (`live_bot/tradovate/`,
`backtest/data/tradovate_provider.py`, `tradovate:`-Abschnitt in `config.yaml`).
Das ist kein Widerspruch — der alte Pfad bleibt lauffähig, ist aber nicht Ziel.

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
- **Kein Mehr-Instrument-Stream.** Protokollierung nur MNQ. MGC nur auf Abruf.
- **Keine Schätzungen, die wie Messungen aussehen.** Delta bleibt null statt
  geraten. Volume Profile ist als Näherung gekennzeichnet.

---

## 8. PROFIL-ARCHITEKTUR UND AUSWERTUNG — die eigentliche Zielfrage

**Zwei Profile in der Config:**

| Profil | Bedeutung |
|---|---|
| `demo` | keine Einschränkungen: kein Zwangsschluss, Overnight erlaubt, keine Haltedauer-Grenze, kein Drawdown-Limit, Hedging erlaubt |
| `lucid` | alle Regeln aus Abschnitt 6 aktiv |

Alle Werte konfigurierbar, keine Magic Numbers im Code.

**Eine gemeinsame Ideen-Datenbank** mit Profilfeld je Idee.

`evaluate_past_ideas` bekommt den Parameter `rules = "none" | "lucid" | "both"`.
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

| Etappe | Inhalt | Status (21.08.2026, gegen Code und Live-Test geprüft) |
|---|---|---|
| **A** | NinjaScript-Bridge (`ClaudeBridge.cs`), Indikator, HTTP POST an `localhost:8787` | **ABGESCHLOSSEN** — kompiliert, auf zwei Charts angewandt, live verifiziert |
| **B** | Empfänger (`ntbridge/receiver.py`), SQLite-Speicher, `NTBridgeBarSource` | **ABGESCHLOSSEN** — Code fertig, Tests grün, **mit echten Daten verifiziert** |
| **C** | Ideen-Protokollierung, regelbasiert, MNQ | **offen, kein Code vorhanden — jetzt der nächste Schritt** |
| **D** | Auswertung: `evaluate_past_ideas`, `get_performance_report` | offen, kein Code vorhanden |
| **E** | Dauerbetrieb-Härtung | offen |
| **F** | Liefergegenstände (Anleitungen, Configs, Startbefehle) | teilweise erledigt |

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

## 11. WAS BEREITS STEHT — **326 Tests grün**

```
common/instruments.py   8 Instrumente (MNQ, MGC, MES, ES, NQ, SIL, ZN, M6E),
                        MGC-Verfallsregel korrigiert
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
live_bot/               Alert-System, Telegram, on_demand_report (Legacy)
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

> **Wichtig, weiterhin gültig:** Es wurde **nie ein Backtest auf echten
> Marktdaten gerechnet**. Seit 21.08.2026 liegen zwar erstmals echte Daten in
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

| | MNQ | MGC |
|---|---|---|
| Name | Micro E-mini Nasdaq 100 | Micro Gold |
| Börsengruppe | CME Index | COMEX Metals |
| Ticksize | 0,25 Punkte | 0,10 USD/oz |
| Punktwert | 2 USD | 10 USD (10 oz) |
| Kontraktmonate | H/M/U/Z | G/J/M/Q/V/Z |
| Verfall | 3. Freitag | drittletzter Geschäftstag des Liefermonats |
| NT8 Session Template | `CME US Index Futures ETH` | `COMEX Metals ETH` |

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

Etappe C beginnen: die regelbasierte Ideen-Protokollierung. Erst damit entsteht
das, worum es dem Nutzer eigentlich geht — auswertbare Setups statt
Bauchgefühl.

### Erledigt

- Gesamte Rechenlogik in `common/` (**326 Tests grün**)
- MCP-Server mit Tool 1 und Tool 2, Terminal-Dump
- **Etappe A abgeschlossen** (Bridge kompiliert, zwei Charts, live sendend)
- **Etappe B abgeschlossen** (Empfänger, SQLite-Speicher, BarSource — mit
  echten Daten verifiziert)

### Offen

1. **HOCH:** Etappe C — regelbasierte Ideen-Protokollierung (MNQ). Der nächste
   inhaltliche Schritt.
2. **HOCH:** Empfänger dauerhaft mitlaufen lassen; Laptop nicht schlafen legen.
   Jede Lücke kostet Historie, die historienabhängige Kennzahlen brauchen.
3. **MITTEL:** Etappe D — `evaluate_past_ideas`, `get_performance_report`.
4. **MITTEL:** Profil-Logik demo/lucid; Lucid-Regeln als Simulationsmodell
   inklusive EOD-Trailing-Drawdown über die Kontofolge.
5. **MITTEL:** Etappen E–F.
6. **MITTEL:** README aktualisieren — sie beschreibt noch ausschließlich den
   Tradovate-Pfad und erwähnt weder MCP noch NinjaTrader.
7. **NIEDRIG, aber Voraussetzung für unbeaufsichtigtes Arbeiten:** Git-Repo
   anlegen, privates GitHub, `.gitignore` prüfen (`.env`, `.venv/`, `*.sqlite3`,
   Logs). Ohne das gibt es kein Rückholnetz für fehlerhafte Änderungen.
8. **NIEDRIG:** Gegencheck, ob der NT8-Feed wirklich Echtzeit ist (Vergleich mit
   TradingView). Nach dem Live-Test praktisch schon sehr wahrscheinlich.
9. **NIEDRIG:** `laeuft_seit_utc` in `/status` zeigt nach frischem Start ein
   altes Datum — vermutlich ein persistierter DB-Wert statt der echten
   Prozesslaufzeit. Kosmetisch, aber irreführend.

> **Korrektur gegenüber älteren Fassungen:** Die früheren Punkte 1–5 unter
> "Offen" (kompilieren, Empfänger starten, Charts einrichten, Erfolgstest,
> Etappe B verifizieren) sind **alle erledigt**.

### Blocker

**Keine.** Der einzige echte Test — ob der nie kompilierte C#-Code in
NinjaTrader funktioniert — ist bestanden.

### Unsicherheiten

- Ob MNQ und MGC zwei getrennte CME-Datenpakete erfordern (CME Index vs. COMEX
  Metals), falls MGC später dazukommen soll.
- Ob der NT8-Feed formal als Echtzeit gilt (praktisch verhielt er sich so).

> **Erledigte Unsicherheiten (21.08.2026):** `IsSuspendedWhileInactive`
> kompiliert; `System.Net.Http` ist ohne Zusatzreferenz verfügbar; die NT8-
> Zeitzone weicht nicht von Windows ab; "Days to load 7" reicht für die
> 1m-Serie (3015 von 3000 Ziel-Kerzen erreicht).

### Nächster sinnvoller Schritt

Etappe C planen und bauen. Vorher, falls unbeaufsichtigt gearbeitet werden
soll: Git-Repo anlegen (Abschnitt 16, Warnung).

---

## 18. KONSISTENZ UND PFLEGE

**Es gibt genau zwei Kontextdateien.** Beide gehören ins Claude-Projekt:

| Datei | Inhalt | Ändert sich |
|---|---|---|
| `NORMALER_CHAT_KONTEXT.md` (diese) | WAS/WARUM, Anforderungen, Historie, Entscheidungen | selten |
| `CODE_CHAT_KONTEXT.md` | WIE, Module, technischer Stand, Bugs mit Fundstelle, Tests | bei Bauarbeiten |

**Bei Widersprüchen gilt die Rangfolge:**

1. **tatsächlicher Code** — Wahrheit über den aktuellen Implementierungsstand
2. **`CODE_CHAT_KONTEXT.md`** — Wahrheit über technische Umsetzung und Historie
3. **diese Datei** — Wahrheit über Ziele, Anforderungen und Gründe

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
