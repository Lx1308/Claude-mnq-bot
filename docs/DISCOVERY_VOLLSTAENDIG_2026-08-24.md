# Vollstaendiger Einzelfaktor-Discovery-Lauf — 24.08.2026

**Anlass:** Laurin wollte moeglichst viele Indikatoren als Regimefaktoren
geprueft haben (23.08.2026), nicht nur die drei aus dem ersten Discovery-Lauf
(Abschnitt 26 in `CODE_CHAT_KONTEXT.md`). Dieser Lauf deckt 20 Faktoren aus
allen verfuegbaren Indikatorspalten ab, ueber fuenf Strategien.

**Reproduzierbar mit:** `werkzeuge/discovery_indikatoren_voll.py`
(braucht `$env:PYTHONPATH`, siehe Kopf des Skripts). Rechenzeit ca. 15 Minuten.

**Daten:** `data/DUKA_5m.csv`, Dukascopy-Naeherung. Trainingsteil (70 %):
445 991 Kerzen, 2016-08-22 bis 2023-10-24. Der Out-of-Sample-Block wurde nicht
angeruehrt (`pruefe_nur_training` haette sonst laut abgebrochen).

**Kostenprofil:** `private_ninjatrader` — 0,95 USD/Seite, 1,90 USD Round Turn.

> **Naeherung, keine Messung.** Wie jeder Lauf auf `DUKA_5m.csv`: Index-CFD
> statt MNQ-Futures, rein informativ.

---

## Strategien und Faktoren

**Fuenf Strategien** (in-sample-Trades): `prev_day_breakout` (1554),
`vwap_reversion` (4885), `flag_breakout` (843), `vwap_trend` (3248),
`rsi_mean_reversion` (3841).

`ib_breakout` fehlt bewusst — die Strategie lief zum Zeitpunkt, als dieser
Lauf konzipiert wurde, noch nicht (der `ib_high`/`ib_low`-Bug wurde erst
danach behoben, siehe Commit `d3fec23`). Sie nachtraeglich in denselben Lauf
aufzunehmen haette die Hypothesenzahl und damit die Bonferroni-Schwelle
veraendert, ohne dass der Rest neu gerechnet wurde.

**20 Faktoren**, alle mit Grenzen aus der tatsaechlichen Verteilung des
Trainingsteils (nicht geraten): Tageszeit, Wochentag, ATR-Terzil,
RSI-Terzil, ADX-Terzil, Stochastik-Terzil, Bollinger-Bandbreite-Terzil,
MACD-Histogramm-Vorzeichen, DI-Richtung, EMA-Stack, Konsolidierung,
Range-Flag, Impuls-Flag, Breakout-Up-Flag, Breakout-Down-Flag,
Bollinger-Squeeze, Flag-Richtung, IB-Lage, VWAP-Lage, Vortagesschluss-Lage.

Gemessene Terzilgrenzen: ATR 5,154/11,036 — RSI 45,902/56,596 —
ADX 19,679/29,076 — Stochastik-K 35,858/71,374 —
Bollinger-Bandbreite 0,002/0,005.

---

## Multiple-Testing-Korrektur (Bonferroni)

| Kennzahl | Wert |
|---|---|
| Geprüfte Hypothesen (auswertbare Gruppen, ≥20 Trades) | **239** |
| Unkorrigiertes Niveau α | 0,05 |
| **Korrigierte Schwelle** | **0,000209** (= α / 239) |
| Bei α = 0,05 zufällig erwartete "Treffer" | ~12 |
| Tatsächlich unter der korrigierten Schwelle | **6** |

Laurins Entscheidung vom 23.08.2026 gilt unveraendert: keine Hypothese wird
privilegiert, auch nicht bei Literaturuebereinstimmung. Alle 239 Gruppen
wurden gleich behandelt.

---

## Die sechs Gruppen, die die korrigierte Schwelle unterschreiten

| Strategie / Faktor / Gruppe | Trades | Trefferquote | Brutto Pkt/Trade | t | p (unkorr.) |
|---|---:|---:|---:|---:|---:|
| `flag_breakout` / RSI-Terzil / **2 mittel** | 35 | 2,9 % | −12,773 | −8,97 | 0,0000 |
| `rsi_mean_reversion` / RSI-Terzil / **2 mittel** | 331 | 75,5 % | +13,112 | +6,87 | 0,0000 |
| `rsi_mean_reversion` / RSI-Terzil / **3 hoch** | 1705 | 43,7 % | −3,812 | −4,81 | 0,000002 |
| `vwap_trend` / RSI-Terzil / **2 mittel** | 1435 | 16,9 % | −3,199 | −4,74 | 0,000002 |
| `rsi_mean_reversion` / Stochastik-Terzil / **2 mittel** | 694 | 60,7 % | +5,407 | +4,42 | 0,000011 |
| `rsi_mean_reversion` / Stochastik-Terzil / **3 hoch** | 1462 | 43,7 % | −3,841 | −4,30 | 0,000018 |

**Auffaellig: alle sechs Treffer sind RSI- oder Stochastik-Terzil.** Kein
Zeit-, Wochentag-, Trend- oder Flag-Faktor hat die Korrektur ueberstanden.

---

## Einordnung — drei getrennte Befunde, nicht einer

### 1. `rsi_mean_reversion` — vier der sechs Treffer, aber vermutlich zirkulaer

`rsi_mean_reversion` steigt selbst genau dann ein, wenn RSI die 30 von unten
bzw. die 70 von oben kreuzt (`backtest/strategies/library.py:105`). Der
Einstieg erfolgt eine Kerze spaeter, zur Eroeffnung der Folgekerze — der
RSI-Faktor liest den RSI-Wert dieser Folgekerze, nicht den der Signalkerze.
Dass ein Teil der Trades dabei in die Terzil-Mitte (45,9–56,6) statt in die
Randbereiche faellt, ist nicht unplausibel (RSI kann sich zwischen
Signal- und Einstiegskerze deutlich bewegen), macht den Faktor aber
**strukturell nah an der eigenen Einstiegsregel** — ein Fund hier bestaetigt
moeglicherweise nur, dass die Strategie tut, was sie soll, nicht dass RSI ein
unabhaengiges Regimemerkmal ist. **Nicht als eigenstaendige Entdeckung werten**,
ohne das explizit zu pruefen.

### 2. `vwap_trend` / RSI-Terzil / 2 mittel — der belastbarste Einzelfund

`vwap_trend` verwendet RSI **nirgends** in seiner Einstiegslogik (VWAP-Kreuzung
plus SMA-Struktur). 1435 Trades, deutlich ueber der Mindestgroesse. Beide
Randgruppen sind positiv (niedrig +1,217 / hoch +2,671 Punkte je Trade), nur
die Mitte ist tief negativ (−3,199). Eine plausible Lesart: `vwap_trend` ist
eine Trendfolge-Strategie, und ein RSI in der Mitte deutet typischerweise auf
eine richtungslose Phase — genau dort, wo Trendfolge schwaech(er) tragen sollte.
**Das ist eine Hypothese fuer die Validierung, kein Befund** — aber die
unabhaengigste und am besten mit Daten unterlegte der sechs.

### 3. `flag_breakout` / RSI-Terzil / 2 mittel — staerkster t-Wert, aber duennste Gruppe

t = −8,97, der staerkste Wert im ganzen Lauf — bei nur **35 Trades** und einer
Trefferquote von 2,9 %. Das ist eine kleine, extreme Gruppe: knapp ueber der
Mindestschwelle (20), fast durchgehend Verlierer. Passt formal durch die
Korrektur, weil der Effekt so gross ist, aber ein derart kleines n bei einem
derart extremen Wert ist typisch fuer eine Handvoll Ausreisser-Trades in einer
bestimmten Marktphase, nicht fuer ein robustes Muster. **Vor jeder Verwendung
gezielt nachsehen, welche Trades das sind und ob sie zeitlich streuen oder
aus einem einzelnen Cluster stammen.**

---

## Was das NICHT ist

Wie in Abschnitt G des Masterplans festgelegt: Discovery ist Phase 1 von vier
(Discovery → Validation → Confirmation → Monitoring). Ein Fund hier ist eine
**Hypothese fuer die Validierung**, kein Befund. Der Out-of-Sample-Block bleibt
unberuehrt — nichts hier rechtfertigt bisher, ihn anzutasten.

Wie bei jedem Lauf auf der Dukascopy-Naeherung: die Ergebnisse sind zur
Faktorfindung geeignet, aber keine Aussage ueber echtes MNQ-Verhalten.

---

## Naechster Schritt

Laut Etappenplan (Masterplan R, Reihenfolge C+ → G → H → I → (J | D)):
Validation der `vwap_trend`/RSI-Terzil-Hypothese auf einem zweiten,
unabhaengigen Datenblock, bevor irgendetwas an den OOS-Block geht. Die
`rsi_mean_reversion`-Treffer zuerst auf Zirkularitaet pruefen (RSI-Wert der
Signalkerze statt der Einstiegskerze vergleichen), bevor sie in dieselbe
Validation gehen.
