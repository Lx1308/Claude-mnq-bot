# Faktorkatalog — Kandidaten für die Research-Engine

**Erstellt:** 23.08.2026 aus Internet-Recherche.

> **Das Wichtigste zuerst: Nichts in diesem Dokument ist ein Erwartungswert.**
> Jeder Eintrag ist eine **Hypothese**, die jemand anders auf anderen Daten,
> in einem anderen Zeitraum, mit anderen Kosten gemessen hat. Der
> Erwartungswert für **dieses** Projekt entsteht erst durch die Validierung
> gegen die eigenen Daten (`MASTERPLAN.md` G und J).
>
> **Ein Katalog ist gefährlich.** Wer 40 Faktoren auf einem Datensatz prüft,
> findet bei α = 0,05 rund zwei „signifikante" allein durch Zufall. Deshalb
> gilt unverändert: Hypothesenzahl mitschreiben, Einzelfaktor vor Mehrfaktor,
> OOS-Block **einmalig**.

---

## 0. Der wichtigste Fund — eine Falsifikationsstudie zu genau unserem Fall

**Mesfin (2026): „Structural Limits of OHLCV-Based Intraday Signals in MNQ
Futures: A Systematic Falsification Study"**, arXiv 2605.04004.

Das ist keine Anekdote, sondern exakt unsere Ausgangslage: **MNQ,
Fünfminutenkerzen, nur OHLCV**.

| | |
|---|---|
| Daten | 947 Handelstage, 2021–2025, 5-Minuten |
| Geprüft | **14 Signalfamilien** |
| Kriterien | Walk-Forward, t ≥ 2,0, ≥ 30 Trades, positiv nach 2 Punkten Friktion, Konsistenz über Jahre |
| Ergebnis | **Keine einzige** Familie erfüllte alle Kriterien |
| Bruttoertrag | **0,07 bis 1,50 Punkte je Trade** |

**Das deckt sich mit unserer eigenen Messung.** Unsere vier Familien liegen
brutto bei rund −1 Punkt je Trade — im selben Größenbereich, nur am unteren
Rand.

### 0.1 Aber: die Kostenannahme ist der Hebel

Die Studie verwirft alles unterhalb von **2 Punkten Friktion**. Unsere
gemessenen Kosten sind niedriger:

| Posten | Punkte (MNQ, 2 USD/Punkt) |
|---|---|
| `private_ninjatrader`, 1,90 USD Round Turn | 0,95 |
| Slippage 1 Tick je Seite | 0,50 |
| **Summe** | **≈ 1,45** |

Ein Signal mit 1,50 Punkten brutto wäre unter Mesfins Annahme verworfen,
unter unseren Konditionen **knapp positiv**. Das ist kein Beleg für eine
Kante — aber es zeigt, dass die Schwelle nicht bei 2 Punkten liegen muss.

**Konsequenz für uns:** Die Suche ist nicht aussichtslos, aber der Zielkorridor
ist eng. Ein Faktor muss brutto deutlich über 1,45 Punkte liefern, sonst bleibt
nichts übrig. Alles, was hier folgt, ist daran zu messen.

---

## 1. Bewertungsraster

| Spalte | Bedeutung |
|---|---|
| **Evidenz** | A = mehrfach peer-reviewed, B = einzelne Studie, C = Praktikerwissen ohne belastbare Quelle |
| **Rechenbar** | Ob es aus **unseren** Daten ableitbar ist (OHLCV aus NT8) |
| **Arbitragerisiko** | Wie wahrscheinlich der Effekt durch Veröffentlichung verschwunden ist |

---

## 2. Zeitbasierte Faktoren — sofort rechenbar

Die stärkste Gruppe für uns: aus dem Zeitstempel ableitbar, keine neue
Datenquelle, kein Lookahead-Risiko.

### 2.1 Intraday-Momentum (erste halbe Stunde → letzte halbe Stunde)

**Evidenz A** · **rechenbar: ja** · **Arbitragerisiko: hoch**

Gao et al. zeigen für SPY 1993–2013, dass die Rendite der ersten halben Stunde
die der letzten halben Stunde vorhersagt — statistisch und ökonomisch
signifikant, **stärker an volatilen Tagen, an Tagen mit hohem Volumen und an
Tagen mit Makro-Veröffentlichungen**. Für FTSE-Futures: 1,84 % Rendite,
Sharpe 0,43.

**Der entscheidende Vorbehalt:** Eine Untersuchung der
Out-of-Sample-Periode fand, dass **die Vorhersagbarkeit verschwindet**.

**Für uns:** Direkt als Regel formulierbar. Die Regimeabhängigkeit
(Volatilität, Volumen) passt exakt zu unserer geplanten Regime-Engine — das
wäre ein Einzelfaktor-Test mit vorab definierter Bedingung, nicht ein
nachträglich gefundener Filter.

### 2.2 Overnight vs. Intraday

**Evidenz A** · **rechenbar: ja** · **Arbitragerisiko: mittel**

Ein außergewöhnlich robuster Befund: Übernacht-Renditen sind stark positiv,
Intraday-Renditen negativ. Für QQQ über fünf Jahre: **+53,5 % Close-to-Open
gegen +30,3 % Open-to-Close**. Der Effekt ist seit den 1990ern über die meisten
Aktienmärkte hinweg stabil und **auffallend wenig erforscht**.

**Für uns:** Wir handeln intraday — der Effekt sagt also, dass wir im
**ungünstigeren** Zeitfenster arbeiten. Das ist keine Handelsregel, aber ein
wichtiger Kontext: Ein Long-Bias intraday kämpft gegen diesen Wind.

### 2.3 Turn-of-Month

**Evidenz A** · **rechenbar: ja** · **Arbitragerisiko: mittel**

Von allen Kalendereffekten der einzige, der in S&P-500-Futures **statistisch
und ökonomisch signifikant und über die Zeit stabil** ist — letzte vier und
erste drei Handelstage des Monats. Die ökonomische Signifikanz erreichte in den
letzten fünf Jahren des Samples ihren Höhepunkt.

**Für uns:** Als Regime-Achse verwendbar, nicht als eigenständiges Setup.

### 2.4 Wochentagseffekt

**Evidenz B** · **rechenbar: ja** · **Arbitragerisiko: hoch**

Gemischt. Eine Untersuchung über 99 Jahre DJIA-Futures findet, dass
Renditeverteilungen sich nach Wochentag signifikant unterscheiden, mit
**höheren Montag-Übernacht-Renditen**. Andere Analysen finden Montag um
5,3 Basispunkte **niedriger**. Der klassische Montagseffekt hat sich
offenbar verändert.

**Für uns:** Billig mitzuprüfen als Regime-Achse, aber ohne Erwartung.

---

## 3. Struktur- und Levelbasierte Faktoren

### 3.1 Opening Range Breakout

**Evidenz B, widersprüchlich** · **rechenbar: ja** (wir haben Opening Range)

Eine begutachtete Studie zu „Timely ORB" über DJIA, S&P 500, NASDAQ, HSI und
TAIEX (2003–2013) findet über 8 % Jahresrendite bei p < 0,03, im TAIEX bis
20,28 %. Bemerkenswert: **die optimale Beobachtungsdauer war in den USA kurz,
in Asien lang** — der Parameter ist also marktabhängig.

**Dagegen:** Praktische Backtests auf S&P-500-Futures zeigen minimale Gewinne
(bestenfalls 0,04 % je Trade).

**Für uns:** Wir haben bereits `ib_breakout` (Initial Balance = erste RTH-
Stunde). ORB mit **kürzerem** Fenster (5/15/30 Minuten) wäre eine naheliegende
Variante — und die Studie legt nahe, dass die Fensterlänge der wichtigere
Parameter ist als die Regel selbst.

### 3.2 Gap-Statistik

**Evidenz B/C** · **rechenbar: ja** (wir haben Gap-Level)

Die konkretesten Zahlen der ganzen Recherche, allerdings aus Praktikerquellen:

| Befund | Zahl |
|---|---|
| ES-Gaps schließen in derselben Session | 68–72 % |
| NQ-Median bis zum Schluss | 18 Minuten |
| 90. Perzentil | 207 Minuten |
| Gap-Downs schließen häufiger als Gap-Ups | 62,2 % vs. 58,8 % |
| **Große Gaps (> 30 Punkte ES)** | Schließwahrscheinlichkeit fällt auf **8,2 %** |

**Der interessanteste Teil ist die Bedingtheit:** Bildete sich das Gap aus
einer **engen** Overnight-Range, füllt es eher; war die Overnight-Session ein
gerichteter Trend über 40+ Punkte, ist es eher eine Fortsetzung.

**Für uns:** Das ist ein fertig formulierter Zweifaktor-Test (Gap-Größe ×
Overnight-Range), und beide Größen haben wir. **Vorsicht:** Die Quellen sind
Praktikerseiten, nicht begutachtet. Die Zahlen sind als Hypothese zu behandeln,
nicht als Referenz.

---

## 4. Regime-Faktoren

### 4.1 ADX-Schwelle für Trend gegen Range

**Evidenz C** · **rechenbar: ja** (haben wir)

Verbreitete Praktikerregel: ADX über 25 mit steigender Steigung = Momentum-
Regime, unter 20 = Range, wo Mean-Reversion zahlt.

**Für uns:** Wir verwenden bereits ADX-Schwellen im Ideen-Filter
(`adx_trend_min: 20`, `adx_range_max: 25`). Die Recherche liefert **keine
Begründung für diese konkreten Zahlen** — sie sind Konvention. Nach dem
`consolidation_max_atr`-Fund (Schwelle 1,2 war unerreichbar) gehören auch
diese aus der Verteilung abgeleitet statt übernommen.

### 4.2 Volatilitäts-Clustering

**Evidenz A** (Clustering selbst ist gesichert) · **rechenbar: ja**

Hohe ATR-Perioden gruppieren sich, ruhige ebenso. Regimewechsel kommen in
Phasen, nicht im Wechsel.

**Für uns:** Das rechtfertigt die geplante Regime-Achse „ATR-Perzentil" —
und es heißt, dass Regime **persistent** genug sind, um darauf zu
konditionieren.

### 4.3 VIX-Terminstruktur

**Evidenz B** · **rechenbar: NEIN — Datenquelle fehlt**

Contango (VIX < VIX3M) in etwa 84 % der Zeit, Backwardation 16 % und ein
Stresssignal. Ein Befund verdient Beachtung: **Der Beginn der Backwardation war
über 17 Jahre kein Kaufsignal — der Markt fiel danach in 74 % der Fälle
weiter.**

**Für uns:** Braucht eine zweite Datenquelle. `MASTERPLAN.md` F.3 nennt
Cross-Asset über NT8 als naheliegendsten Weg — **zuerst prüfen, ob NT8 VIX
liefert**, bevor externe Anbieter erwogen werden.

---

## 5. Ereignisbasierte Faktoren

### 5.1 Pre-FOMC-Drift

**Evidenz A, aber umstritten** · **rechenbar: NEIN** (Terminhistorie fehlt)

Lucca und Moench (2015): Die 24 Stunden vor planmäßigen FOMC-Ankündigungen
erklärten **über 80 % der gesamten Aktienrisikoprämie** von 1994 bis 2011.

**Der Streit:** Eine Untersuchung findet, der Drift sei **nach 2015
verschwunden**. Eine Analyse bis Dezember 2024 findet ihn **weiterhin
vorhanden**, stärker in Hochvolatilitätsphasen.

**Der allgemeine Punkt, der über diesen Faktor hinausgeht:** McLean und Pontiff
(2016) zeigen, dass Vorhersagbarkeit **nach ihrer Veröffentlichung
verschwindet**. Das gilt für jeden Eintrag in diesem Katalog — je bekannter ein
Effekt, desto wahrscheinlicher ist er wegarbitriert.

**Für uns:** Nicht rechenbar. Forex Factory liefert nur die laufende Woche;
FRED hat keine Vintage-Historie. Genau deshalb steht Makro-Research im
Masterplan auf **P3**.

---

## 6. Was daraus folgt

### 6.1 Sofort prüfbar (nur unsere Daten, keine neue Quelle)

Nach Evidenz geordnet:

1. **Intraday-Momentum**, konditioniert auf Volatilität und Volumen (2.1)
2. **Turn-of-Month** als Regime-Achse (2.3)
3. **Gap-Größe × Overnight-Range** als Zweifaktor (3.2)
4. **ORB mit kürzeren Fenstern** als `ib_breakout`-Variante (3.1)
5. **ADX-Schwellen aus der Verteilung** statt aus Konvention (4.1)
6. **Wochentag** als billige Regime-Achse (2.4)

### 6.2 Braucht eine Datenquelle — später

- VIX-Terminstruktur (4.3) — erst prüfen, ob NT8 sie liefert
- Pre-FOMC und Makro (5.1) — braucht Vintage-Modellierung, P3

### 6.3 Die unbequeme Erkenntnis

Mesfins Studie hat **14 Signalfamilien auf genau unserem Instrument, unserer
Zeitebene und mit genau unserer Datenart** geprüft und **keine** gefunden, die
alle Kriterien erfüllt. Unsere eigene Messung zeigt dasselbe Bild.

Das heißt nicht, dass die Suche sinnlos ist. Es heißt:

- **Der Zielkorridor ist eng.** Brutto über 1,45 Punkte je Trade, sonst bleibt
  nichts übrig.
- **Reine OHLCV-Signale sind wahrscheinlich zu wenig.** Der Weg führt eher über
  **Konditionierung** — dasselbe Signal, aber nur in bestimmten Regimen — als
  über neue Signalformen.
- **Ein negatives Ergebnis ist ein Ergebnis.** Mesfin hebt ausdrücklich den
  Wert dokumentierter Negativbefunde hervor. Für dieses Projekt gilt dasselbe:
  „Setup X trägt nicht" ist eine verwertbare Antwort.

---

## Quellen

- [Market intraday momentum (Gao et al., ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0304405X18301351)
- [Intraday Momentum: The First Half-Hour Return Predicts the Last Half-Hour Return](https://www.smallake.kr/wp-content/uploads/2015/01/SSRN-id2440866.pdf)
- [Understanding intraday momentum strategies (Journal of Futures Markets)](https://onlinelibrary.wiley.com/doi/abs/10.1002/fut.22375)
- [Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures (Mesfin 2026)](https://arxiv.org/abs/2605.04004)
- [Assessing the Profitability of Timely Opening Range Breakout on Index Futures Markets (IEEE)](https://ieeexplore.ieee.org/document/8641124/)
- [Assessing the profitability of intraday opening range breakout strategies (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1544612312000438)
- [Night Moves: Is the Overnight Drift the Grandmother of All Market Anomalies? (Elm Wealth)](https://elmwealth.com/night-moves-overnight-drift/)
- [Strikingly Suspicious Overnight and Intraday Returns (arXiv)](https://arxiv.org/pdf/2010.01727)
- [Turn of the Month in Equity Indexes (Quantpedia)](https://quantpedia.com/strategies/turn-of-the-month-in-equity-indexes)
- [Equity Returns at the Turn of the Month (Xu & McConnell)](https://www.chesler.us/resources/academia/turn_of_the_month_stock_returns.pdf)
- [The Pre-FOMC Announcement Drift (Lucca & Moench, NBER)](https://conference.nber.org/confer/2013/MEs13/Lucca_Moench.pdf)
- [The disappearing pre-FOMC announcement drift (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S1544612320315956)
- [Trading the Fed: The Pre-FOMC Drift is Alive (QuantSeeker)](https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift)
- [VIX Futures Curve Explained (QuantVPS)](https://www.quantvps.com/blog/vix-futures-curve-explained)
- [Using VIX futures term structure (Harbourfront Quant)](https://harbourfrontquant.substack.com/p/using-vix-futures-term-structure)
- [Gap Fill Strategy: 2,791 Days of NQ Data 2015–2025 (TradingStats)](https://tradingstats.net/gap-fill-strategy/)
- [When Do Gaps Fill? ES & NQ Gap Fill Timing Data (TradingStats)](https://tradingstats.net/when-do-gaps-fill/)
- [Gap Fill Trading Strategies (QuantifiedStrategies)](https://www.quantifiedstrategies.com/gap-fill-trading-strategies/)
- [Volatility Regimes Explained (Volatility Box)](https://volatilitybox.com/research/volatility-regimes-explained/)
- [QuantPedia — Encyclopedia of Quantitative Trading Strategies](https://quantpedia.com/)
