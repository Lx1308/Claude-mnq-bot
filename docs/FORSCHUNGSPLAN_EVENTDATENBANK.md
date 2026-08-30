# Forschungsplan: empirische Ereignisdatenbank MNQ

**Auftrag Laurins vom 30.08.2026.** Ziel ist **keine Strategie**, sondern eine
reproduzierbare Wissensbasis: welche Marktsituationen treten auf, wie oft, und
wie entwickeln sie sich danach.

> **Stand 30.08.2026:** Die fünf offenen Entscheidungen sind getroffen
> (Abschnitt 15). Der Plan ist freigegeben, die Umsetzung folgt den
> Etappen aus Abschnitt 14.

---

## 1. Was bereits existiert

Das Projekt hat mehr fertige Forschungswerkzeuge, als je benutzt wurden. Der
Plan setzt darauf auf.

| Baustein | Zustand | Verwendung hier |
|---|---|---|
| `common/indicators.py` | ✅ in Betrieb | ATR, RSI, VWAP, SMA, Flaggen; erweitert MACD, Stoch, ADX, Bollinger, EMA-Stack |
| `common/levels.py` | ✅ | PDH/PDL/PDC, Initial Balance, Asia/London-Extrema |
| `common/structure.py` | ✅ | Swing-Punkte, S/R-Zonen, Trendbewertung |
| `common/patterns.py` | ⚠️ **punktuell** | Flagge, Dreieck, Doppeltop/-boden, Range-Kompression, Kerzenmuster |
| `common/market_primitives.py` | ⚠️ **punktuell, nur Anzeige** | FVG, Displacement, Equal Highs/Lows, **Liquidity Sweep**, BOS/CHoCH — je mit `event_time`/`availability_time` |
| `common/muster_serie.py` | ✅ Serie | Doppelboden/-top mit Verfügbarkeitszeitpunkt (30.08.2026) |
| `common/strukturniveaus.py` | ✅ Serie | letztes/vorletztes Swing-Tief und -Hoch (30.08.2026) |
| `common/regime.py` | ✅ Serie | Volatilität / Struktur / Liquidität, rückwärtsgerichtet (30.08.2026) |
| `backtest/excursions.py` | ✅ | MFE/MAE in Punkten und R, Zeit bis MFE/MAE, voller Pfad |
| `backtest/conditional_outcomes.py` | ✅ | Vorwärtsverlauf gegen bedingungslose Nulllinie, Ziel-Stop-Matrix, **überschneidungsfreie Statistik** |
| `backtest/splits.py` | ✅ | Dreiwege-Split mit Schutzriegeln |
| `backtest/research.py` | ✅ | t-Verteilung ohne scipy, Bonferroni-Buchführung |
| `backtest/research_register.py` | ✅ | unveränderliches Hypothesenregister |

**Neu zu bauen:** die Serien-Fassung der punktuellen Erkenner, die
Ereignisdatenbank selbst, die Outcome-Klassifikation und die Stop-Analyse.

---

## 2. Datengrundlage — und was fehlt

| | |
|---|---|
| Quelle | `data/ntbridge.sqlite3`, NinjaTrader-Export |
| Umfang | **2.573.719 Minutenkerzen**, 06.05.2019 – 28.08.2026 |
| Kontrakte | 30 Quartalskontrakte, an den Rollfenstern zusammengesetzt |
| Spalten | `open, high, low, close, volume, nt_instrument, source` |

### Was NICHT verfügbar ist — wird nicht genähert

| Fehlt | Folge |
|---|---|
| **Bid/Ask, Delta, Footprint** | Kein Order Flow. Absorption, Delta-Divergenz, Auction-Analyse sind **nicht messbar**. |
| **Ticks** | Keine Intrabar-Reihenfolge. Ob innerhalb einer Minute erst das High oder erst das Low kam, ist unbekannt. |
| **Orderbuch / DOM** | Keine Liquiditätstiefe. „Liquidity" wird hier ausschließlich als *Preisniveau, an dem Stops vermutet werden* definiert — nicht als tatsächliche Order-Liquidität. |
| **Terminkalender vor der laufenden Woche** | Forex Factory liefert nur die aktuelle Woche. Historische Termindaten gibt es nur über FRED/ALFRED (8 Makroreihen) und deterministisch ableitbare Termine (FOMC, NFP, Verfallstage, Monatsende). |

### Datenqualität, die dokumentiert gehört

- **29 Kontraktnahtstellen** mit Preissprüngen von −0,55 % bis +1,46 %. Für
  Gap-artige Muster sind das Scheinsignale; `NtBridgeDataProvider.rollgrenzen`
  weist sie aus und sie werden aus Gap-Analysen **ausgeschlossen**.
- **Volumen an den Nahtstellen** ist zwischen zwei Kontrakten aufgeteilt und
  dort nicht vergleichbar.
- **2019–2021 dünner**: MNQ war ein junger Kontrakt. Häufigkeitsaussagen über
  diesen Zeitraum sind mit dem Vorbehalt zu versehen.

---

## 3. Die Ereignis-Abstraktion: vier Phasen

Laurins Punkt 6 wörtlich umgesetzt. Jedes Ereignis trägt **vier** Zeitpunkte,
strikt getrennt:

| Phase | Feld | Bedeutung |
|---|---|---|
| **A** Pattern entsteht | `entstehung_idx` | Die Struktur existiert im Chart (z.B. zweites Tief) |
| **B** Pattern bestätigt | `bestaetigung_idx` | Die Definition ist erfüllt (z.B. Swing bestätigt) |
| **C** verfügbar | `verfuegbar_idx` | **Frühester Zeitpunkt, zu dem ein Handelnder das wissen konnte** |
| **D** Entry-Trigger | eigene Tabelle | Mehrere Varianten je Ereignis, siehe Abschnitt 7 |

**Es gilt immer `entstehung_idx ≤ bestaetigung_idx ≤ verfuegbar_idx`.** Eine
Verletzung ist ein Abbruchgrund, kein Warnhinweis.

**Nur `verfuegbar_idx` darf in eine Auswertung eingehen.** `entstehung_idx`
existiert für die Anzeige und für Merkmale (Pattern-Dauer, -Größe).

Beispiel Doppelboden, `strength = 3`:
```
Kerze 100   erstes Tief          (entsteht)
Kerze 140   zweites Tief         entstehung_idx = 140
Kerze 143   Swing bestätigt      bestaetigung_idx = verfuegbar_idx = 143
Kerze 151   Nackenlinie gebrochen  → Entry-Variante "nackenbruch"
```

---

## 4. Musterkatalog

### 4.1 Was messbar ist

Aus reinem OHLCV auf 1-Minuten-Basis:

**Struktur**
- Swing-Hoch / Swing-Tief (Fraktale, Parameter `strength`)
- Higher High / Higher Low, Lower High / Lower Low
- BOS (Break of Structure) / CHoCH (Change of Character) — vorhanden
- Trend / Range / Übergang (Regime-Achse) — vorhanden

**Formationen**
- Doppelboden / Doppeltop — vorhanden als Serie
- Triple Bottom / Triple Top — *neu*
- Flagge / Wimpel — vorhanden punktuell
- Dreieck — vorhanden punktuell
- Range-Kompression → Expansion — vorhanden punktuell

**Niveau-Interaktion**
- Test / Reaktion an PDH, PDL, PDC, Overnight-Extrema, Initial Balance
- Mehrfachtests desselben Niveaus (2., 3., n-ter Test) — *neu*
- Ausbruch / Fehlausbruch / Ausbruch mit Retest — *neu*
- Range-Bruch / Range-Ablehnung — *neu*

**Imbalance / Liquidität** (Definitionen laut ICT/SMC, siehe Quellen)
- Fair Value Gap — vorhanden punktuell
- Displacement — vorhanden punktuell
- Equal Highs / Equal Lows — vorhanden punktuell
- Liquidity Sweep (Sweep + Reclaim) — vorhanden punktuell
- Order Block — *neu* (letzte Gegenkerze vor Displacement)

**Bewegung**
- Impuls + Konsolidierung
- Pullback im Trend (Fibonacci-Zonen als Merkmal, nicht als Regel)
- Reversal nach extremer Bewegung (n × ATR in m Kerzen)
- Mean Reversion zum VWAP / zur SMA

**Zeit / Session**
- Opening Range (erste n Minuten je Session)
- Initial Balance (erste Stunde RTH) — vorhanden
- Session-Extrema Asia / London / NY — vorhanden
- Tageswechsel, Wochentag, Verfallswoche, Monatsende

### 4.2 Mehrere Definitionen — Beispiel Doppelboden

Laurins Punkt 2 verlangt getrennte Dokumentation von Varianten. Für den
Doppelboden gibt es drei sinnvolle und **sie sind nicht dasselbe**:

| | Variante A (Projekt) | Variante B (klassische TA) | Variante C (SMC/Sweep) |
|---|---|---|---|
| Tiefs | 2 bestätigte Swing-Tiefs | 2 lokale Tiefs | 2. Tief **unterschreitet** das 1. |
| Ähnlichkeit | \|L1−L2\| ≤ 0,5 × ATR | \|L1−L2\| ≤ 3 % | 2. Tief tiefer, aber Reclaim |
| Zwischenhoch | ≥ 1,0 × ATR über den Tiefs | ≥ 10 % über den Tiefs | beliebig |
| Zeitfenster | ≤ 120 Kerzen | offen | ≤ 120 Kerzen |
| Idee dahinter | Struktur | Struktur | **Stop-Abholung**, dann Umkehr |

Variante C ist **ein anderes Muster** — sie beschreibt genau das, was ohne
Reclaim ein Fehlausbruch wäre. Sie wird als eigener `pattern_type` geführt,
nicht als Variante.

Dasselbe Vorgehen für alle Muster: **eine Primärdefinition, benannte
Varianten, jede als eigener `pattern_variant` in der Datenbank.**

---

## 5. Outcome-Messung

Über `backtest/excursions.py`, das bereits liefert:

- MFE / MAE in **Punkten** und **R** (R = ATR zum Ereigniszeitpunkt)
- Zeit bis MFE / Zeit bis MAE
- Endergebnis
- den vollständigen Pfad je Kerze

**Horizonte:** 1, 3, 5, 10, 20, 30, 60, 120, 240 Minutenkerzen
(120 = 2 h, 240 = 4 h). Zusätzlich „bis Sessionende".

**Ausgewiesen in:** Punkten, Ticks, R (ATR-Vielfache). Prozent zusätzlich, weil
MNQ von 7.500 auf 29.500 gelaufen ist und Punkte über die Historie nicht
vergleichbar sind.

### Annahme, die benannt werden muss

**Intrabar-Reihenfolge ist unbekannt.** Wenn eine Minutenkerze sowohl das Ziel
als auch den Stop enthält, ist aus OHLC nicht rekonstruierbar, was zuerst kam.
Konvention hier, wie in der Backtest-Engine: **der Stop gilt als zuerst
erreicht** (pessimistisch). Jede Auswertung weist aus, wie oft dieser Fall
eintrat — ist der Anteil hoch, ist das Ergebnis von der Annahme abhängig.

---

## 6. Outcome-Klassifikation

Laurins Punkt 5. Die Klassen brauchen **objektive Schwellen**, sonst ist es
Chartlesen im Nachhinein.

Vorschlag am Beispiel Doppelboden (long), Bezugsniveau = Nackenlinie `N`,
zweites Tief `L2`, Schwelle `s = 0,5 × ATR`, Horizont `H`:

| Klasse | Regel |
|---|---|
| `breakout_bestaetigt` | Schluss > N + s, und innerhalb H kein Schluss < L2 |
| `breakout_retest_fortsetzung` | Schluss > N + s, danach Rücklauf ≤ N + s, danach erneut > N + s |
| `breakout_retest_scheitern` | Schluss > N + s, danach Schluss < N − s |
| `fehlausbruch` | High > N + s **ohne** Schluss > N + s, danach Schluss < L2 |
| `rejection_ohne_breakout` | nie Schluss > N + s, aber auch nie Schluss < L2 − s |
| `erneuter_test` | Low erreicht L2 ± s, ohne Schluss < L2 − s |
| `breakdown` | Schluss < L2 − s |
| `seitwaerts` | Spanne über H < 1,0 × ATR, keine der obigen |

**Die Schwelle `s` ist eine Annahme.** Sie wird als Parameter geführt und die
Klassifikation für `s ∈ {0,25; 0,5; 1,0} × ATR` gerechnet, damit sichtbar
wird, wie stark das Ergebnis daran hängt.

**Reihenfolge der Prüfung ist festgelegt und dokumentiert** — eine Kerze kann
mehrere Regeln erfüllen, und wer zuerst prüft, entscheidet.

---

## 7. Entry-Trigger — getrennt vom Muster

Je Ereignis werden **mehrere** Entry-Definitionen gerechnet, jede als eigene
Zeile in der Trigger-Tabelle:

| `entry_type` | Zeitpunkt | Charakter |
|---|---|---|
| `bestaetigung` | bei `verfuegbar_idx`, Eröffnung der Folgekerze | frühest möglich, unbestätigt |
| `nackenbruch` | erster Schluss jenseits der Nackenlinie | Lehrbuch |
| `nackenbruch_retest` | Rücklauf an die Nackenlinie nach dem Bruch | besserer Kurs, seltener |
| `retest_l2` | Rücklauf auf das zweite Tief ± Puffer | bester Kurs, riskanter |
| `impuls` | erst nach einer Kerze mit Spanne > 1,5 × ATR in Richtung | Bestätigung durch Bewegung |

Jede Variante hat **Fälle, in denen sie nie auslöst** — der Retest kommt nicht
immer. Das wird gezählt (`nie_ausgeloest`), nicht weggelassen: eine Variante,
die nur in 30 % der Fälle einen Einstieg liefert, ist etwas anderes als eine
mit 100 %.

---

## 8. Stop-Analyse — der eigentliche Kern

Laurins Punkte 7 und 8. Das ist die Frage, die dieses Projekt noch nie gestellt
hat.

### 8.1 Untersuchte Stop-Positionen

| Bezug | Varianten |
|---|---|
| zweites Tief `L2` | −0,1 / −0,2 / −0,3 / −0,5 / −1,0 × ATR |
| erstes Tief `L1` | dieselben Abstände |
| Pattern-Extremum (tieferes der beiden) | dieselben |
| letztes Swing-Tief davor | dieselben |
| Vortagestief | fest |
| reines ATR-Vielfaches vom Einstieg | 0,5 / 1,0 / 1,5 / 2,0 / 3,0 × ATR |

### 8.2 Die vier Fälle — Laurins Punkt 8

Für jede Stop-Position und jedes Ereignis:

| Fall | Bedeutung | Was er sagt |
|---|---|---|
| **A** | Stop getroffen, Muster wäre danach **doch** aufgegangen | Stop war **zu eng** |
| **B** | Stop getroffen, Muster scheitert danach tatsächlich | Stop hat **funktioniert** |
| **C** | Stop nicht getroffen, Muster geht auf | Stop war **weit genug** |
| **D** | Stop nicht getroffen, Muster entwickelt sich nicht | Stop **irrelevant**, Zeitstop nötig |

„Wäre doch aufgegangen" braucht eine Definition: **innerhalb des Horizonts H
wird das Ziel (z.B. 2 × ATR) erreicht, obwohl der Stop vorher lag.** Das ist
messbar aus dem Pfad.

### 8.3 Was die Analyse liefert

Für jedes Muster:

- **Verteilung der MAE erfolgreicher Fälle** — die zentrale Zahl. Wenn 90 % der
  erfolgreichen Doppelböden nie mehr als 0,4 × ATR gegen den Einstieg laufen,
  ist ein Stop bei 0,5 × ATR strukturell begründet und nicht optimiert.
- **Quantile**: 50 %, 75 %, 90 %, 95 % der MAE erfolgreicher Fälle
- **Anteil Fall A** je Stop-Position — die Kurve „wie viel Erfolg kostet mich
  ein engerer Stop"
- **Trennschärfe**: bei welcher Distanz unterscheiden sich MAE-Verteilung der
  Erfolge und der Fehlschläge am stärksten

**Ausdrücklich kein „optimaler Stop".** Die Ausgabe ist eine Verteilung und
eine Kurve, keine Empfehlung. Die Frage ist „welche Gegenbewegung ist bei
diesem Muster normal", nicht „welcher Stop hätte am meisten verdient".

---

## 9. Datenbankstruktur

`data/eventdb.sqlite3`, vier Tabellen. SQLite, weil das Projekt es durchgehend
benutzt und die Abfragen filternd sind; zusätzlich Parquet-Export für
Massenauswertung.

### `events` — ein Datensatz je erkanntem Muster

```
event_id            TEXT PRIMARY KEY     EVT-000000001
pattern_type        TEXT                 double_bottom | liquidity_sweep | ...
pattern_variant     TEXT                 A | B | swc
detect_timeframe    TEXT                 1m | 5m | 15m | 1h
direction           INTEGER              +1 long, -1 short

entstehung_ts       TEXT                 Phase A
bestaetigung_ts     TEXT                 Phase B
verfuegbar_ts       TEXT                 Phase C  <- nur das zaehlt
entstehung_idx      INTEGER
verfuegbar_idx      INTEGER

-- Rohmerkmale (Laurins Punkt 3: NICHT nur "ja")
level_1             REAL                 erstes Tief/Hoch
level_2             REAL                 zweites Tief/Hoch
level_neckline      REAL                 Nackenlinie / Bezugsniveau
swing_high_ref      REAL
swing_low_ref       REAL
pattern_dauer_bars  INTEGER
pattern_hoehe_pkt   REAL
pattern_hoehe_atr   REAL
pattern_breite_bars INTEGER
symmetrie           REAL                 |L1-L2| / ATR

-- Kontext zum Verfuegbarkeitszeitpunkt
atr                 REAL
vola_regime         TEXT
struktur_regime     TEXT
liquiditaet_regime  TEXT
session             TEXT                 asia | london | ny_rth | ny_eth
wochentag           INTEGER
minuten_seit_open   INTEGER
trend_1h            TEXT
trend_4h            TEXT
abstand_vwap_atr    REAL
abstand_pdh_atr     REAL
abstand_pdl_atr     REAL
volumen_relativ     REAL                 vs. gleiche Tageszeit
naechstes_level_ueber REAL
naechstes_level_unter REAL

-- Herkunft
nt_kontrakt         TEXT
nahe_rollgrenze     INTEGER              0/1
datensatz_block     TEXT                 train | validation | oos
```

### `outcomes` — Kursverlauf je Ereignis und Horizont

```
event_id, horizont_bars,
mfe_pkt, mfe_r, zeit_bis_mfe,
mae_pkt, mae_r, zeit_bis_mae,
end_pkt, end_r, end_prozent,
max_hoch_pkt, max_tief_pkt,
weg_bis_naechstes_level_atr,
klasse                        -- Abschnitt 6
```

### `triggers` — Entry-Varianten je Ereignis

```
event_id, entry_type, ausgeloest (0/1),
trigger_ts, trigger_idx, entry_preis,
verzoegerung_bars             -- verfuegbar_idx -> trigger_idx
```

### `stop_szenarien` — je Ereignis × Entry × Stop-Position

```
event_id, entry_type, stop_bezug, stop_abstand_atr, stop_preis,
getroffen (0/1), zeit_bis_stop,
fall                          -- A/B/C/D aus 8.2
ziel_erreicht_trotz_stop (0/1),
r_ergebnis
```

**Schätzung des Umfangs:** bei ~20 Mustern × ~2–3 Varianten über 2,57 Mio
Kerzen erwarte ich grob 200.000–800.000 Ereignisse, × 9 Horizonte für
`outcomes`, × 5 Entries × ~25 Stop-Positionen für `stop_szenarien`. Letztere
Tabelle wird groß (zweistellige Millionen Zeilen) — deshalb Parquet für sie
und Aggregate in SQLite.

---

## 10. Lookahead-Schutz

Fünf Maßnahmen, jede als Test:

1. **Verfügbarkeitszeitpunkt.** Kein Ereignismerkmal darf aus Kerzen nach
   `verfuegbar_idx` stammen. Prüfung: Reihe abschneiden, Ereignisse neu
   rechnen, Felder müssen identisch sein. (So wie bei `muster_serie` und
   `regime` bereits gemacht.)
2. **Swing-Bestätigung.** Ein Swing bei `i` ist erst bei `i + strength`
   bekannt. Bereits durchgesetzt.
3. **Regime rückwärtsgerichtet.** Rollendes Fenster, nie Gesamthistorie.
   Bereits durchgesetzt und getestet.
4. **Entry zur Folgekerze.** Ein Trigger, der auf Kerzenschluss auslöst, wird
   zur Eröffnung der **nächsten** Kerze ausgeführt — wie in der Engine.
5. **Outcome-Fenster beginnt nach dem Entry**, nie beim Muster.

**Zusätzlich:** ein Ereignis, dessen Fenster über das Ende des jeweiligen
Datenblocks hinausreicht, wird verworfen statt gekürzt.

---

## 11. IS / Validation / OOS

**Zeitbasierter Schnitt**, nicht anteilig — damit die Grenze über alle Läufe
hinweg dieselbe bleibt und nicht mit dem Datenbestand wandert:

**Entschieden am 30.08.2026.**

| Block | Zeitraum | Rolle |
|---|---|---|
| **Training** | 06.05.2019 – 31.12.2023 | Ereignisse erkennen, Grundraten messen, Hypothesen bilden |
| **Validation** | 01.01.2024 – 31.12.2024 | Hypothesen prüfen |
| **Out-of-Sample** | 01.01.2025 – 28.08.2026 | **Einmalig**, ganz am Ende |

Jedes Ereignis trägt `datensatz_block`. **Die Grundratentabelle wird zunächst
nur auf Training gerechnet.**

**Vorwärtsdaten sind der eigentliche OOS.** Läuft das Projekt zwei Jahre, wächst
täglich echtes, nie durchsuchtes Material nach. Das ist das einzige Material,
das sich nicht data-minen lässt.

---

## 12. Statistik

Je Muster mit `n ≥ 30`:

- Stichprobengröße, **und die überschneidungsfreie Stichprobengröße**
- Häufigkeit (Ereignisse je 1.000 Kerzen, je Session, je Jahr)
- Anteil je Outcome-Klasse mit **Konfidenzintervall** (Wilson, für Anteile
  korrekter als die Normalapproximation)
- E[R], Median, Standardabweichung, Quantile (10/25/50/75/90)
- MFE- und MAE-Verteilung
- **immer gegen die bedingungslose Nulllinie**
- t und p **überschneidungsfrei** gerechnet

**Kennzeichnung:**
- `n < 30` → gar nicht ausgewiesen
- `n < 200` → „Stichprobe zu klein für belastbare Aussage"
- `n ≥ 200` → Zahlen mit Konfidenzintervall

**Keine Auswahl im Bericht.** Alle gemessenen Muster werden aufgeführt, auch
die uninteressanten. Wer daraus eines herausgreift, trifft eine Auswahl — und
ab da gilt die Mehrfachtestkorrektur gegen die Gesamtzahl.

---

## 13. Unbekannte Muster (Clustering)

Laurins Punkt 13, als **letzte** Etappe.

Verfahren: Merkmalsvektor je Kerze (normalisierte Form der letzten n Kerzen,
Regime, Session), dann k-Means oder HDBSCAN.

**Bedingungen, ohne die es nicht gemacht wird:**
- Merkmalsvektor **vorher** festgelegt, nicht gesucht
- Clusterzahl über Silhouette bestimmt, nicht nach Ergebnis gewählt
- **Stabilitätsprüfung**: Cluster auf Training gebildet, auf Validation
  wiedergefunden? Instabile Cluster sind Rauschen.
- Ergebnisse ausdrücklich als „empirisch gefundenes Muster ohne Namen"
  geführt, nie mit erfundener Bezeichnung

---

## 14. Etappen und Reihenfolge

| # | Etappe | Ergebnis |
|---|---|---|
| 1 | Punktuelle Erkenner → Serien (`market_primitives`, `patterns`) | Alle Muster als Spalten mit Verfügbarkeitszeitpunkt |
| 2 | Ereignis-Abstraktion + `eventdb.sqlite3` | Schema, Schreibweg, Lookahead-Tests |
| 3 | Ereignisse über die Historie erkennen | `events`-Tabelle gefüllt |
| 4 | Outcomes über alle Horizonte | `outcomes`-Tabelle |
| 5 | Outcome-Klassifikation | `klasse` je Zeile |
| 6 | Entry-Trigger-Varianten | `triggers`-Tabelle |
| 7 | Stop-Szenarien, Fälle A–D | `stop_szenarien` |
| 8 | Statistische Auswertung, Bericht | Grundratentabelle |
| 9 | Hypothesenbudget im Register | Auswahlschritt wird zählbar |
| 10 | Clustering | optional, zuletzt |

**Etappen 1–4 sind die Grundlage; erst danach lohnen 5–8.**

---

## 15. Entschieden am 30.08.2026

Diese Punkte waren **Entscheidungen, keine Ableitungen**. Laurin hat sie
beantwortet; sie sind damit verbindlich.

1. **Erkennungs-Zeitebene: 1m + 5m + 15m + 1h.** Struktur wird auf mehreren
   Ebenen erkannt, **gemessen und gehandelt wird immer auf 1m**. Jedes
   Ereignis trägt `detect_timeframe`. So sieht ein Trader den Markt — und ein
   Doppelboden mit fünf Minuten zwischen den Tiefs bleibt vom Doppelboden mit
   zwei Stunden unterscheidbar, statt in einen Topf zu fallen.

   *Folge:* rund vierfache Rechenzeit, und die Ereigniszahl steigt
   entsprechend. Ausdrücklich in Kauf genommen.

   *Technisch:* Die groberen Ebenen entstehen über
   `common.timeframes.resample_ohlcv` aus derselben 1m-Reihe (dieselbe
   Funktion wie überall sonst). Der Verfügbarkeitszeitpunkt eines Musters auf
   einer groberen Ebene ist der **Schluss der groberen Kerze**, umgerechnet
   auf den 1m-Index — ein 15m-Muster ist nicht mitten in der 15m-Kerze
   bekannt.

2. **Klassifikationsschwelle `s` = 0,5 × ATR**, zusätzlich gerechnet für 0,25
   und 1,0, damit sichtbar bleibt, wie stark das Ergebnis daran hängt.

3. **Zeitbasierter Split** wie in Abschnitt 11: Training bis 31.12.2023,
   Validation 2024, OOS ab 01.01.2025. Feste Grenzen, die nicht mit dem
   Datenbestand wandern.

4. **Rollgrenzen werden markiert** (`nahe_rollgrenze`), nicht generell
   ausgeschlossen. Ausschluss nur dort, wo der Kontraktsprung das Ergebnis
   fälscht: Gap-, Imbalance- und Ausbruchsmuster.

5. **Stop-Szenarien im vollen Umfang.** 25 Positionen × 5 Entries × alle
   Ereignisse. Eine ausgedünnte Rasterung könnte genau die Distanz verfehlen,
   an der sich Erfolg und Fehlschlag trennen — und die Stop-Frage ist der Kern
   dieser Untersuchung. Laufzeit über Nacht ist eingeplant.

---

## Quellen für Musterdefinitionen

Externe Quellen dienen **ausschließlich** der Definition, nie als Beleg für
Profitabilität auf MNQ — diese Aussage kommt allein aus diesen Daten.

- ICT / Smart Money Concepts: Order Block, Fair Value Gap, Liquidity Sweep,
  BOS/CHoCH — siehe `docs/FAKTORKATALOG.md` und die dort geführten Quellen
- Klassische Chartformationen: Doppeltop/-boden, Dreieck, Flagge — Standard-TA
- Mesfin (2026), arXiv 2605.04004: Falsifikationsstudie zu OHLCV-Signalen auf
  MNQ 5m. **Kontext, kein Gegenbeweis** — die Studie prüfte 14 Signalfamilien
  mit 2 Punkten Friktion; unsere Friktion liegt bei ~1,45 Punkten.
