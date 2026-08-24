# Validation der RSI-Terzil-Funde aus dem vollständigen Discovery-Lauf

**24.08.2026 (vierte Sitzung des Tages).** Setzt die beiden Punkte aus dem
"Nächster Schritt"-Abschnitt von
[`DISCOVERY_VOLLSTAENDIG_2026-08-24.md`](DISCOVERY_VOLLSTAENDIG_2026-08-24.md)
um: die `rsi_mean_reversion`-Treffer auf Zirkularität prüfen, dann die
`vwap_trend`/RSI-Terzil-Hypothese auf einem zweiten, unabhängigen
Datenblock validieren - beides ohne den Out-of-Sample-Block anzurühren.

**Näherung, keine Messung.** Wie jeder Lauf auf `data/DUKA_5m.csv`:
Index-CFD statt MNQ-Futures, rein informativ (Invariante 10/11).

---

## 1. `rsi_mean_reversion`: die Zirkularitätsvermutung bestätigt sich

**Reproduzierbar mit:** `werkzeuge/rsi_zirkularitaet.py`.

### Ausgangslage

Der Discovery-Lauf fand vier signifikante Gruppen bei `rsi_mean_reversion`
(RSI-Terzil mittel/hoch, Stochastik-Terzil mittel/hoch) und markierte sie als
"vermutlich zirkulär": Die Strategie steigt genau dann ein, wenn RSI die 30
von unten bzw. die 70 von oben kreuzt
(`backtest/strategies/library.py:105-112`). Der bisherige RSI-Faktor
(`backtest/research.py::_wert_bei_einstieg`) liest den RSI-Wert der
**Einstiegskerze** (Eröffnung der Folgekerze, Invariante 4) - nicht den der
**Signalkerze**, auf deren Schlusskurs die Regel tatsächlich feuerte.

### Methode

RSI-Terzil-Gruppierung ein zweites Mal gerechnet, diesmal mit dem RSI-Wert
der Zeile `entry_index - 1` im selben vorbereiteten Rahmen - exakt die Zeile,
auf der `backtest/engine.py` das Signal setzt (Zeile 310-329: Signal auf
Zeile i-1, Ausführung auf Zeile i). Dieselben eingefrorenen Terzilgrenzen
wie im Discovery-Lauf (45,902 / 56,596), auf demselben Trainingsteil
(70 %, 2016-08-22 bis 2023-10-24, 445 991 Kerzen, Kostenprofil
`private_ninjatrader`).

### Ergebnis

| RSI-Quelle | Ausprägung | Trades | Trefferquote | Brutto Pkt/Trade | t |
|---|---|---:|---:|---:|---:|
| Einstiegskerze (Discovery-Lauf) | 1 niedrig | 1805 | 49,2 % | −1,864 | −1,98 |
| Einstiegskerze (Discovery-Lauf) | **2 mittel** | 331 | 75,5 % | **+13,112** | **+6,87** |
| Einstiegskerze (Discovery-Lauf) | **3 hoch** | 1705 | 43,7 % | **−3,812** | **−4,81** |
| Signalkerze (tatsächliche Regel) | 1 niedrig | 1877 | 51,0 % | −1,036 | −1,14 |
| Signalkerze (tatsächliche Regel) | 2 mittel | 141 | 56,0 % | −0,113 | −0,03 |
| Signalkerze (tatsächliche Regel) | 3 hoch | 1823 | 46,5 % | −1,955 | −2,49 |

**Spannweite brutto: 16,924 Punkte (Einstiegskerze) gegen 1,841 Punkte
(Signalkerze).** Unter der Bonferroni-Korrektur für diese 6 Hypothesen
(Schwelle 0,008333) bestehen nur noch die beiden Einstiegskerzen-Gruppen -
keine einzige Signalkerzen-Gruppe.

Am deutlichsten bei der "2 mittel"-Gruppe: Sie schrumpft von 331 auf 141
Trades (RSI bewegt sich zwischen Signal- und Einstiegskerze aus der
Randzone in die Mitte) und ihr Ergebnis kollabiert von +13,112 Punkten bei
75,5 % Trefferquote auf −0,113 Punkte bei 56,0 % - im Rauschen.

### Einordnung

**Die Zirkularitätsvermutung des Discovery-Berichts wird bestätigt.** Der
RSI-Terzil-Fund bei `rsi_mean_reversion` misst überwiegend, dass die
Strategie tut, was sie soll (nahe der eigenen Ein-/Ausstiegsschwellen
einsteigt), nicht ein unabhängiges Regimemerkmal. **Diese vier Gruppen
gelten damit als entkräftet und gehen nicht in die Validierung.** Die
Stochastik-Terzil-Treffer wurden hier nicht gesondert nachgerechnet - sie
teilen dieselbe strukturelle Nähe zur Einstiegsregel (Stochastik und RSI
korrelieren stark auf demselben Kursverlauf) und sind aus demselben Grund
mit Vorbehalt zu lesen, aber nicht Gegenstand dieser Prüfung.

---

## 2. `vwap_trend`/RSI-Terzil: hält auf einem zweiten Datenblock

**Reproduzierbar mit:** `werkzeuge/validation_vwap_trend_rsi.py`.

### Ausgangslage

`vwap_trend` verwendet RSI **nirgends** in der eigenen Einstiegslogik
(VWAP-Kreuzung plus SMA-Struktur) - der "belastbarste Einzelfund" des
Discovery-Laufs: 1435 Trades in der Mittelgruppe, beide Randgruppen positiv
(niedrig +1,217 / hoch +2,671 Punkte je Trade), nur die Mitte tief negativ
(−3,199 Punkte, t=−4,74).

### Methode: welcher "zweite, unabhängige Datenblock"

Der einzige bisher unberührte Block ist der Out-of-Sample-Teil (letzte
30 % von `data/DUKA_5m.csv`) - und der ist einmalig (`pruefe_nur_training`).
Ihn für eine erste Validierung zu verbrauchen wäre Verschwendung, wenn die
Hypothese schon vorher scheitert. Deshalb wurde der bestehende
70-%-Trainingsteil intern noch einmal geschnitten:

```
0 % ----------- 50 % ----------- 70 % ------------------- 100 %
"Sub-Training"   |  VALIDATION   |         OUT-OF-SAMPLE
(im Discovery-    |  (dieser      |         (weiterhin unberührt,
 Lauf mitgepoolt) |   Lauf)       |          einmalig für Confirmation)
```

Die OOS-Grenze bei 70 % bleibt exakt wie im Discovery-Lauf. Die
Terzilgrenzen sind **eingefroren aus dem Discovery-Lauf übernommen**
(45,902 / 56,596), **nicht** auf dem Validierungsblock neu bestimmt - eine
neu bestimmte Grenze würde die Hypothese neu anpassen statt sie zu prüfen.
Indikatoren wurden über die vollen 70 % gerechnet (Invariante 5) und danach
erst auf den Block 50-70 % geschnitten.

**Offen ausgewiesene Einschränkung:** Der Validierungsblock (50-70 %) war
Teil des 70-%-Trainingsteils, den der Discovery-Lauf gepoolt ausgewertet hat
- er ist also nicht im strengen Sinn nie gesehen worden. Er ist aber ein
chronologisch abgegrenztes Fenster, auf dem noch nie eine eigene
Gruppenkennzahl berechnet wurde, mit einer eingefrorenen, nicht neu
angepassten Hypothese. Das ist eine Näherung an eine echte blinde
Validierung, keine vollständige - der einzige Weg zu einer vollständig
unberührten Prüfung wäre der einmalige OOS-Block selbst.

### Ergebnis

Validierungsblock: 2021-12-08 bis 2023-10-24, 127 426 Kerzen, 804 Trades
(gegen 3248 im gesamten 70-%-Trainingsteil).

| Ausprägung | Trades | Trefferquote | Brutto Pkt/Trade | t | p (unkorr.) |
|---|---:|---:|---:|---:|---:|
| 1 niedrig | 277 | 27,8 % | +4,240 | +1,36 | 0,175 |
| **2 mittel** | 337 | 14,2 % | **−8,092** | **−3,87** | **0,000129** |
| 3 hoch | 190 | 27,4 % | +3,295 | +0,86 | 0,393 |

**Dasselbe Muster wie im Discovery-Lauf: beide Randgruppen positiv, die
Mitte deutlich negativ.** Die Mittelgruppe unterschreitet mit p_korr = 0,0004
klar die Bonferroni-Schwelle für diesen Lauf (3 Hypothesen, Schwelle
0,016667) - nicht nur die unkorrigierte.

### Einordnung

**Die Hypothese hält auf dem Validierungsblock**, unter Beachtung der oben
genannten Teilüberlappung. Effektgröße und Vorzeichen stimmen mit dem
Discovery-Lauf überein (Mitte klar negativ, Ränder positiv), und die
Signifikanz ist auf dem kleineren, unabhängig gerechneten Block sogar
stärker (t=−3,87 gegen t=−4,74 auf mehr als der vierfachen Trade-Zahl -
konsistent, keine Verwässerung).

**Das ist immer noch kein Befund**, wie Masterplan G es vorsieht
(Discovery → Validation → Confirmation → Monitoring): Die Näherungsdaten
sind ein CFD, kein MNQ; der Validierungsblock überlappt teilweise mit dem
Discovery-Pool; und die eigentliche Bestätigung braucht den einmaligen
OOS-Block. Aber es ist die erste Hypothese des ganzen Projekts, die einen
zweiten, unabhängig gerechneten Blick übersteht - stark genug, um die
Frage an Laurin zu rechtfertigen, ob der OOS-Block für die Confirmation
dieser einen Hypothese verwendet werden soll.

---

## Nächster Schritt

**Rückfragepflichtig, nicht selbst entschieden:** Ob und wann der
Out-of-Sample-Block für die Confirmation von `vwap_trend`/RSI-Terzil
verwendet wird - er ist einmalig, und diese Sitzung greift nicht eigenmächtig
darauf zu. Bis dahin bleibt er unberührt, wie in jedem bisherigen Lauf.
