# Backtesting: `backtesting.py`, `vectorbt` oder eigene Engine?

Du hast darum gebeten, beide Bibliotheken zu pruefen und eine begruendete
Empfehlung zu geben, statt beides halbfertig einzubauen. Hier ist die
Pruefung — und eine Empfehlung, die von beiden Optionen abweicht.

**Kurzfassung:** Fuer diesen Anwendungsfall ist eine eigene, schlanke
Event-Engine (`backtest/engine.py`, ca. 300 Zeilen) die bessere Wahl.
`vectorbt` bleibt sinnvoll als *spaeterer Zusatz* fuer sehr grosse
Parameter-Sweeps. `backtesting.py` empfehle ich hier nicht.

---

## 1. Was dieses Projekt konkret braucht

| Anforderung | Warum sie hier zaehlt |
|---|---|
| **Punktwert und Ticksize** | NQ = 20 USD/Punkt, ES = 50 USD/Punkt, Tick 0.25. P&L in USD muss stimmen, sonst sind Profit-Faktor und Drawdown wertlos. |
| **Feste Kosten je Kontrakt** | Kommission ist ein Fixbetrag pro Seite (z.B. 2.50 USD), kein Prozentsatz vom Volumen. |
| **Genau eine Position** | Prop-Firm-Regeln und dein Handelsstil — kein Pyramidisieren, kein Netting mehrerer Signale. |
| **Intrabar-Stops** | Stop und Ziel muessen innerhalb der Kerze anhand High/Low greifen, nicht erst auf dem Schlusskurs. |
| **Session-Logik** | Vortageshoch/-tief und Session-VWAP brauchen den CME-Handelstag (18:00 ET Rollover), nicht den Kalendertag. |
| **Positionsschluss zum Sessionende** | Intraday heisst intraday. Übernacht-Risiko darf im Backtest nicht durch die Hintertuer entstehen. |
| **Erzwungene IS/OOS-Trennung** | Der eigentliche Grund fuer diesen Teil des Projekts. |
| **Identische Indikatoren wie live** | Sonst testest du eine andere Strategie als die, die dich nachts weckt. |

Punkt 8 ist der wichtigste und wird von keiner Bibliothek geloest: Er
haengt daran, dass Live-Bot und Backtest dieselbe Berechnungsfunktion
benutzen. Genau das tun sie hier — beide rufen
`common.indicators.compute_indicators` auf.

---

## 2. `backtesting.py`

**Was gut passt**

- Sehr niedrige Einstiegshuerde: `Strategy.init()` / `Strategy.next()`.
- Eingebaute Trade-Liste, Equity-Kurve, HTML-Plot.
- `optimize()` mit Rasterlauf und optionaler Bayes-Optimierung.

**Was nicht passt**

1. **Kein Futures-Modell.** Positionsgroessen sind Stueckzahlen oder ein
   Anteil am Cash; es gibt keinen Kontraktmultiplikator. Du kannst zwar
   `size=1` setzen und die Kurse als Punkte interpretieren, dann sind aber
   `Equity Final`, `Return [%]` und `Sharpe Ratio` in einer Fantasie-Waehrung.
   Jede USD-Zahl muesstest du nachtraeglich selbst umrechnen — und genau
   dann verlierst du den Nutzen der eingebauten Kennzahlen.
2. **Kommission ist relativ.** `commission=0.002` ist ein Anteil vom
   Handelswert. 2.50 USD pro Kontraktseite bei ~20.000 Punkten Kurswert
   laesst sich nur als grober Prozentsatz annaehern — und der stimmt nur
   bei genau einem Kursniveau.
3. **Margin statt Kontraktspezifikation.** `margin=1/leverage` ist eine
   Naeherung, kein Futures-Margin-Modell.
4. **`optimize()` kennt keine Out-of-Sample-Grenze.** Du bekommst genau
   die Funktion, die den Overfitting-Fehler begeht, ohne Schutzriegel.
5. **Nur ein Instrument, feste Spaltennamen** (`Open`, `High`, ...) — ein
   kleiner, aber staendiger Reibungspunkt.

**Fazit:** Der Anpassungsaufwand fuer Punktwert, Kosten und IS/OOS ist in
etwa so gross wie die eigene Engine — nur endest du mit Kennzahlen, denen
du erst nach Umrechnung trauen kannst.

---

## 3. `vectorbt`

**Was gut passt**

- Enorm schnell: Zehntausende Parameterkombinationen in Sekunden statt
  Stunden. Fuer breite Sweeps gibt es nichts Besseres im Open-Source-Raum.
- `from_signals` kennt `sl_stop`, `tp_stop` und `size` — Futures lassen
  sich ueber `size` plus skalierte Preise abbilden.
- Sehr reichhaltige Kennzahlen und Plots.

**Was nicht passt**

1. **Signal-Arrays statt Zustand.** Regeln wie "Ausstieg nach 120 Kerzen"
   oder "am Sessionende zwangsschliessen" sind zustandsabhaengig. In einem
   vektorisierten Modell muessen sie in Boolean-Arrays vorberechnet werden,
   was fuer alles ausser einfachen Fällen schnell unuebersichtlich wird.
2. **ATR-Stops pro Trade.** `sl_stop` erwartet einen Anteil, nicht einen
   absoluten Preisabstand. Ein ATR-Stop wird damit zu einem Array, das vom
   noch unbekannten Einstiegskurs abhaengt — machbar, aber fehleranfaellig.
3. **Debugging.** Ein falsches Signalarray sieht aus wie ein richtiges. Bei
   einer Bar-Schleife kannst du an der fraglichen Kerze anhalten und
   nachsehen. Das ist bei einer Strategie, mit der echtes Geld riskiert
   wird, kein Nebenaspekt.
4. **Projektstatus.** Die Open-Source-Variante wird deutlich weniger
   gepflegt als das kostenpflichtige `vectorbt PRO`; die Dokumentation
   verweist regelmaessig auf PRO-Features.
5. **Lernkurve.** Deutlich steiler als bei den anderen beiden Optionen.

**Fazit:** Das richtige Werkzeug fuer den Moment, in dem du 20.000
Parametervarianten screenen willst. Als Fundament fuer die erste, sauber
nachvollziehbare Version zu indirekt.

---

## 4. Empfehlung: eigene Engine — mit klarer Anschlussstelle

Die Engine in `backtest/engine.py` ist bewusst klein gehalten und macht
genau die sieben Dinge aus Abschnitt 1 explizit:

```python
CostModel(commission_per_side=2.50, slippage_ticks_per_side=1.0,
          tick_size=0.25, point_value=20.0)
```

Kein Umrechnen, kein Interpretieren — Kontraktspezifikation als Datenobjekt.

Die drei Entwurfsentscheidungen, die den groessten Unterschied machen:

1. **Signal auf Schlusskurs, Ausfuehrung zur naechsten Eroeffnung.**
   Look-ahead ist damit strukturell ausgeschlossen, nicht nur "beachtet".
   Es gibt einen Test dafuer (`test_kein_lookahead_...`).
2. **Bei Stop *und* Ziel in derselben Kerze gilt der Stop.** Aus OHLC laesst
   sich nicht rekonstruieren, was zuerst kam. Die pessimistische Annahme
   ist die einzige, die dich nicht anluegt.
3. **`assert_in_sample_only` in jeder Optimierung.** Der Versuch, auf
   Out-of-Sample-Daten zu optimieren, wird zum lauten Fehler statt zu einem
   stillen, gut aussehenden Ergebnis.

**Kosten dieser Entscheidung:** Die Engine ist eine Bar-Schleife in Python.
Ein Jahr NQ-Minutendaten (~370.000 Kerzen) laeuft in der Groessenordnung
von Sekunden bis wenigen Minuten pro Strategie — fuer den Vergleich von
einer Handvoll Varianten voellig ausreichend, fuer einen Sweep ueber
Tausende Kombinationen nicht.

**Anschlussstelle:** Die Regel-Objekte (`backtest/strategies/base.py`)
haengen nicht an der Engine. Wenn der Sweep-Bedarf kommt, ist der Weg:

1. Regeln einmal vektorisiert auswerten -> Boolean-Arrays,
2. Grobscreening mit `vectorbt` ueber das grosse Raster,
3. die 10–20 Ueberlebenden in dieser Engine mit korrekten Kosten,
   Intrabar-Stops und Out-of-Sample-Pruefung nachrechnen.

So bekommst du die Geschwindigkeit dort, wo sie zaehlt, und die
Nachvollziehbarkeit dort, wo Geld dranhaengt.

---

## 5. Was du im Blick behalten solltest

Unabhaengig vom Werkzeug bleiben diese Punkte die eigentlichen Risiken:

- **Datenqualitaet.** Tradovate ist ein Broker-Feed, kein Datenanbieter.
  Fuer mehrjaehrige Minutenhistorie mit sauberen Kontraktrollovers ist ein
  spezialisierter Anbieter (z.B. Databento, Kibot, CQG) die bessere Quelle.
  Deshalb ist die Datenquelle in diesem Projekt austauschbar.
- **Kontraktrollover.** Ein zusammengesetzter Frontmonat-Chart hat an den
  Rolltagen Preissprunge. Wer ueber Rollover hinweg testet, sollte
  back-adjusted Daten verwenden.
- **Slippage-Annahme.** 1 Tick pro Seite ist fuer NQ in ruhigen Phasen
  realistisch, bei News deutlich zu optimistisch. Rechne einmal mit 2–3
  Ticks gegen — wenn die Strategie das nicht ueberlebt, ueberlebt sie auch
  den Livebetrieb nicht.
- **Anzahl Trades.** Unter ~30 Trades sind Trefferquote und Profit-Faktor
  Rauschen. Die Kennzahlenausgabe weist ausdruecklich darauf hin.
