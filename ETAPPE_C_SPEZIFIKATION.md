# Etappe C — Spezifikation: Ideen-Protokollierung

**Erstellt:** 21.08.2026, im normalen Chat (nicht in Claude Code), auf Basis von
`CODE_CHAT_KONTEXT.md` und `NORMALER_CHAT_KONTEXT.md`.

**Status:** Entwurf zur Abstimmung. Claude Code sollte das gegen den
tatsächlichen Code prüfen, bevor gebaut wird — insbesondere die Annahmen zu
`common/structure.py` und `common/patterns.py` in Abschnitt 2.

**Zweck dieses Dokuments:** Claude Code kann direkt daraus implementieren,
ohne das Datenmodell selbst entwerfen zu müssen. Offene Fragen sind explizit
als solche markiert, nicht stillschweigend entschieden.

---

## 0. Grundentscheidung (im Chat mit Laurin getroffen, 21.08.2026)

Es gibt **zwei getrennte Logs**, nie vermischt:

| | Haupt-Log (`ideas`) | Exploration-Log (`observations`) |
|---|---|---|
| **Inhalt** | Feste, regelbasierte Setups | Freie Beobachtungen ohne feste Regel |
| **Wer entscheidet, ob geloggt wird** | Eine Regel in Code/Config | Claude im Gespräch, nach eigenem Ermessen |
| **Reproduzierbar** | Ja — zwingend | Nein, per Definition |
| **Fließt in `evaluate_past_ideas` ein** | Ja | **Nein, nie** |
| **Zweck** | Statistik: "trägt dieses Setup einen Erwartungswert" | Ideenquelle: taucht ein Muster wiederholt auf, wird daraus später ein festes Setup im Haupt-Log |

**Warum diese Trennung zwingend ist:** Deine bestehende Entscheidung
(`NORMALER_CHAT_KONTEXT.md` Abschnitt 7) verbietet LLM-basierte
Ideen-Protokollierung für die Auswertung — eine LLM-Einschätzung ist nicht
reproduzierbar, zwei Aufrufe mit gleichen Daten können abweichen. Das
Exploration-Log verletzt diese Regel nicht, weil es **nie** in die
Erwartungswert-Rechnung eingeht. Es ist eine Sammlung von Kandidaten für
künftige feste Setups, kein Ersatz für sie.

**Eine dritte Quelle — geklärt (21.08.2026):** Wenn Laurin selbst mit Claudes
Hilfestellung manuell tradet, fließt das **in dieselbe Datenbank wie die
regelbasierten Ideen** (`ideas`, nicht `observations`) — mit eigenem Feld
`quelle` (`regel` / `manuell_assistiert`), damit sich später auswerten lässt,
ob assistierte Entscheidungen anders abschneiden als rein regelbasierte.

Konsequenz, die daraus zwingend folgt: Manuell-assistierte Ideen laufen dann
**genauso durch `evaluate_past_ideas`** wie regelbasierte — inklusive
Lucid-Simulation. Das ist inhaltlich in Ordnung, weil auch eine manuelle Idee
feste Werte hat (Entry, Stop, Ziel, Zeitpunkt) und damit genauso nachspielbar
ist wie ein regelbasiertes Signal. Der Unterschied zur Ablehnung von
LLM-Ideen liegt nicht darin, *wer* die Idee ausgelöst hat, sondern darin, dass
hier trotzdem **feste, protokollierte Werte** vorliegen statt einer
nachträglichen freien Einschätzung — die Reproduzierbarkeits-Anforderung
bleibt also erfüllt.

Für die Auswertung heißt das praktisch: `evaluate_past_ideas` sollte nach
`quelle` filterbar sein (z. B. "nur regelbasiert", "nur manuell_assistiert",
"beides"), damit die beiden sich nicht unbemerkt vermischen, wenn Laurin
gezielt vergleichen will.

---

## 1. Datenmodell Haupt-Log (`ideas`)

**Prinzip: nachspielbar, nicht nur ergebnisorientiert.** Die Kerzen liegen
ohnehin vollständig in `ntbridge.sqlite3`. Das Log muss nur die Eckdaten plus
Zeitstempel enthalten — der Kursverlauf drumherum wird bei der Auswertung aus
der Bar-Datenbank rekonstruiert. Das ist zwingend, sonst kann
`evaluate_past_ideas` mit `rules="lucid"` gar nicht rechnen, was beim
Zwangsschluss 16:45 EST passiert wäre, wenn dieser Preis nicht separat
gespeichert wurde.

**Vorgeschlagene Felder:**

| Feld | Typ | Beispiel | Bemerkung |
|---|---|---|---|
| `idea_id` | INTEGER PK | — | |
| `erstellt_utc` | TEXT (ISO) | `2026-08-21T14:32:00+00:00` | Zeitpunkt des Signals |
| `instrument` | TEXT | `MNQ` | Nur MNQ aktiv, MGC-Feld vorhanden für später |
| `setup` | TEXT | `pdh_bruch` | Schlüssel aus der Setup-Bibliothek, Abschnitt 2 |
| `richtung` | TEXT | `long` / `short` | |
| `timeframe` | TEXT | `5m` | Auf welcher Zeitebene ausgelöst |
| `entry` | REAL | 29383.5 | |
| `stop` | REAL | 29365.0 | |
| `ziel` | REAL | 29420.5 | |
| `crv` | REAL | 2.0 | berechnet, nicht eingegeben |
| `unter_crv_schwelle` | BOOLEAN | false | CRV < 1:1,5 → true, aus `config.yaml` |
| `quelle` | TEXT | `regel` | `regel` / `manuell_assistiert` — beide im selben Log, siehe Abschnitt 0 |
| `profil` | TEXT | `sim_frei` | tatsächliche Kontoumgebung zum Zeitpunkt der Idee — siehe Abschnitt 4 |
| `filter_context` | TEXT (JSON) | `{"adx_regime": "trend", "blackout": false, ...}` | Snapshot der Filterwerte zum Signalzeitpunkt, für spätere Nachvollziehbarkeit |
| `notiz` | TEXT | optional | Freitext, nie für die Auswertung genutzt |

**Bewusst NICHT gespeichert:** Ergebnis (Gewinn/Verlust), da das erst durch
`evaluate_past_ideas` und die Regelanwendung (Abschnitt 3) entsteht — sonst
gäbe es zwei Wahrheiten, je nachdem wann man hinschaut.

---

## 2. Setup-Bibliothek

### 2.1 Bestehend (laut `NORMALER_CHAT_KONTEXT.md` Abschnitt 9)

| Schlüssel | Setup | Basis |
|---|---|---|
| `pdh_pdl_bruch` | PDH/PDL-Bruch | `common/levels.py` |
| `vwap_reversion` | VWAP-Reversion | `common/indicators.py` |
| `ib_bruch` | Initial-Balance-Bruch | `common/levels.py` |
| `flaggen_ausbruch` | Flaggen-Ausbruch | `common/patterns.py::detect_flag` |

Diese vier existieren bereits **auch** als Backtest-Strategien in
`backtest/strategies/library.py` (`prev_day_breakout`, `rsi_mean_reversion`,
`flag_breakout`, `vwap_trend`). **Wichtig laut Entscheidung 5.1:** Eine
einzige Implementierung für Live und Backtest. Die Ideen-Protokollierung
sollte dieselbe Signal-Logik aufrufen wie der Backtest, nicht eine zweite
Fassung schreiben.

### 2.2 Vorschlag für Erweiterung — nutzt ausschließlich bereits vorhandene Berechnungen

Alle folgenden Setups brauchen **keine neue Indikator-Mathematik**. Die
zugrunde liegenden Signale sind laut `CODE_CHAT_KONTEXT.md` Abschnitt 3
bereits gebaut und getestet — es fehlt nur die Einstiegs-/Stop-/Ziel-Regel
drumherum.

| Schlüssel | Setup | Nutzt bereits vorhandene Funktion | Long/Short |
|---|---|---|---|
| `bos_fortsetzung` | Einstieg nach bestätigtem Trendwechsel | `structure.py::classify_market_structure` (BOS) | beide |
| `choch_reversal` | Reversal nach Charakterwechsel | `structure.py::classify_market_structure` (CHoCH) | beide |
| `rsi_divergenz_reversal` | Reversal bei RSI-Divergenz an einem Level | `structure.py::detect_rsi_divergence` | beide |
| `doppeltop_boden` | Reversal an Doppeltop/-boden | `patterns.py::detect_double_top_bottom` | beide |
| `dreieck_ausbruch` | Ausbruch aus Dreiecksformation | `patterns.py::detect_triangle` | beide |
| `range_kompression_ausbruch` | Ausbruch nach Squeeze (Keltner-Containment) | `patterns.py::detect_range_compression` | beide |
| `gap_fill` | Rückkehr zum Vortagesschluss nach Gap | `levels.py` (Gap-Level) | beide |
| `gap_and_go` | Fortsetzung in Gap-Richtung, kein Fill | `levels.py` (Gap-Level) | beide |

**Damit: 12 Setup-Familien statt 4, jede long und short — 24 Kategorien.**
Bei Laurins eigener Schwelle von 20 Ideen pro Kategorie für eine erste
Aussage sind das potenziell 480 Ideen, bis überall genug Daten da sind. Das
ist deutlich mehr als bei 4 Setups, aber ehrlich mehr Zeit, nicht weniger —
**das beschleunigt einzelne Kategorien (mehr Auslöser pro Woche insgesamt),
verkürzt aber nicht automatisch die Zeit bis zur ersten belastbaren Aussage
pro einzelnem Setup.**

**Zu entscheiden, nicht hier vorentschieden:** Ob alle 12 auf einmal gebaut
werden, oder ob die 4 bestehenden zuerst produktiv laufen und die 8 neuen
schrittweise ergänzt werden. Empfehlung: schrittweise, damit jedes neue Setup
einzeln gegen echte Daten geprüft werden kann, statt 8 neue Fehlerquellen auf
einmal einzuführen — passend zu der Grundhaltung aus Abschnitt 8.2 der
Code-Doku ("erst prüfen, ob die Bedingung überhaupt erfüllt werden kann").

### 2.3 Filter (gelten für alle Setups, laut Abschnitt 9)

- ADX-Regime (aus `common/indicators.py::compute_extended_indicators`)
- Blackout-Fenster (aus dem Wirtschaftskalender, Tool 2)
- Liquiditätszone / Dünnzone

Schwellenwerte ausschließlich in `config.yaml`, wie im Rest des Projekts.

---

## 3. Datenmodell Exploration-Log (`observations`)

Bewusst schlanker, weil hier keine Regel dahintersteht, die geprüft werden
muss:

| Feld | Typ | Bemerkung |
|---|---|---|
| `observation_id` | INTEGER PK | |
| `erstellt_utc` | TEXT | |
| `instrument` | TEXT | |
| `beschreibung` | TEXT | Freitext, was Claude auffiel |
| `chart_kontext` | TEXT (JSON) | Snapshot-Auszug zum Zeitpunkt, damit später nachvollziehbar |
| `wurde_festes_setup` | TEXT, nullable | Verweis auf `setup`-Schlüssel aus Abschnitt 2, falls daraus später ein festes Setup wurde |

**Explizite Sperre, testbar:** Ein AST- oder Integrations-Test analog zu
`test_mcp_modul_ruft_keine_anthropic_api` sollte sicherstellen, dass
`evaluate_past_ideas` niemals auf die Tabelle `observations` zugreift. Sonst
schleicht sich über eine Abkürzung genau das LLM-Rauschen in die Statistik,
das die Trennung verhindern soll.

---

## 4. Rolle des `profil`-Felds — GEKLÄRT (21.08.2026)

**Von Laurin entschieden:** Das Feld `profil` hält fest, in welcher
**tatsächlichen Kontoumgebung** die Idee entstanden ist. Es ist reine
Dokumentation der Herkunft, kein Steuerungsfeld.

**Werte:** aktuell `sim_frei` (eigenes NinjaTrader-Simulationskonto, keine
Prop-Firm-Regeln), später z. B. `lucid_challenge` oder `lucid_funded`.

> **Namenshinweis, wichtig:** **Nicht** `demo` als Wert verwenden.
> `config.yaml` enthält bereits `environment: demo` unter `tradovate:` —
> das ist die Tradovate-Umgebung und hat nichts hiermit zu tun. Diese
> Verwechslung ist in `CODE_CHAT_KONTEXT.md` Abschnitt 4 als "Namensfalle"
> ausdrücklich benannt. Ein eigener Wertebereich vermeidet sie.

**Die tragende Unterscheidung:**

| | hält fest | Zeitpunkt |
|---|---|---|
| `profil` (Feld an der Idee) | **was tatsächlich war** — auf welchem Konto | beim Protokollieren |
| `rules` (Parameter von `evaluate_past_ideas`) | **was gewesen wäre** — unter welchem Regelwerk gerechnet wird | beim Auswerten |

**Daraus folgt für die Implementierung:**

1. `evaluate_past_ideas(rules="both")` rechnet **alle** Ideen durch **beide**
   Regelwerke — unabhängig von ihrem `profil`. Das Feld wird dabei **nicht**
   als Filter benutzt. Nur so lässt sich die wörtlich gestellte Frage
   beantworten: *"Welche meiner Setups tragen auch unter Prop-Firm-Regeln,
   und welche sehen nur gut aus, weil sie über Nacht laufen durften."*
2. `profil` soll aber als **optionaler Filter** abrufbar sein, damit sich
   später gezielt fragen lässt: "nur die Ideen von echtem Prop-Firm-Konto".
   Vorgabe: kein Filter = alle Ideen.
3. Der Wert wird beim Protokollieren aus der Konfiguration gelesen, nicht je
   Idee eingegeben.

---

## 5. Reihenfolge für Claude Code (Vorschlag)

1. Schema für `ideas` und `observations` in SQLite anlegen (gemeinsame DB mit
   Profilfeld, wie in Abschnitt 8 der Chat-Doku gefordert — **nicht** getrennt
   pro Profil, das bleibt bestehen und ist unabhängig von der
   Haupt-/Exploration-Trennung in diesem Dokument).
2. Die 4 bestehenden Setups aus 2.1 ans Live-Logging anschließen, unter
   Wiederverwendung der Backtest-Strategie-Logik.
3. Test: jede geloggte Idee muss aus den in der DB liegenden Bars zum
   angegebenen Zeitpunkt vollständig nachvollziehbar sein (Regressionsschutz
   für "nachspielbar, nicht nur Ergebnis").
4. Test: `evaluate_past_ideas`-Pfad darf `observations` nicht referenzieren
   (sobald Tool 4/5 existiert).
5. Erst danach schrittweise die 8 neuen Setups aus 2.2 ergänzen, je eins nach
   dem anderen gegen echte Daten geprüft.
6. Beide Felder `quelle` und `profil` sind seit 21.08.2026 geklärt (Abschnitt
   0 bzw. 4) — es steht keine Schema-Entscheidung mehr aus. Der Wertebereich
   für `profil` gehört in `config.yaml`, nicht hart in den Code.

---

## 6. Nicht Teil dieser Spezifikation

- Etappe D (`evaluate_past_ideas`, `get_performance_report`) — eigenes
  Dokument, sobald Etappe C steht.
- Lucid-Regelsimulation (Teil 3) — braucht Etappe D als Voraussetzung.
- Konkrete Zahlen für Entry/Stop/Ziel je Setup — das ist Trading-Logik, die
  Laurin selbst festlegen sollte, nicht etwas, das im Chat vorentschieden
  wird.
