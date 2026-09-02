# Strukturvermessung MNQ — Messplan

**v2, Stand 01.09.2026 · ENTWURF, wartet auf Laurins Freigabe · nichts davon ist gelaufen**

v1 lag heute Nachmittag vor. Laurin hat sie ChatGPT zur Prüfung gegeben und
selbst widersprochen. Diese Fassung arbeitet beides ein. Abschnitt 0 sagt, was
sich geändert hat und warum — inklusive der Stellen, an denen ChatGPT falsch
liegt.

> **Dies ist ein Plan, kein Ergebnis.** Jede Zahl ist entweder nachgerechnet
> (Kosten, Stichprobenbedarf — die Rechenwege stehen dabei), eine Abzählung
> der Testfläche oder ausdrücklich als Schema gekennzeichnet.

Web-Fassung: <https://claude.ai/code/artifact/c7e4654f-c230-4157-bae3-5ce19e93df77>

---

## 0. Was sich gegenüber v1 geändert hat

### 0.1 ChatGPTs Kostenkorrektur ist falsch — v1 hatte recht

ChatGPT schreibt, der Round Turn betrage 1,95 Punkte statt 1,45, nennt das
„keinen kosmetischen Fehler" und zieht dem Kostenmodell dafür 5/10 ab.

Der Rechenweg dort lautet: *„1 Tick = $0,50. Also: Slippage = 0,500 Punkte."*

**Das ist eine Einheitenverwechslung.** Ein MNQ-Tick sind 0,25 Indexpunkte und
bei 2 USD Punktwert 0,50 **USD**. ChatGPT rechnet den Tick korrekt in Dollar um
und schreibt die Dollarzahl dann als Punkte weiter.

Nachgerechnet:

```
1 Tick               = 0,25 Punkte = 0,50 USD
Kommission je Seite  = 0,95 USD / 2,00 USD je Punkt = 0,475 Punkte
Slippage   je Seite  = 1 Tick                       = 0,250 Punkte
                                                    ---------------
je Seite                                              0,725 Punkte
ROUND TURN                                            1,450 Punkte = 2,90 USD
```

Gegenprobe in Dollar: 2 × 0,95 USD Kommission + 2 × 0,50 USD Slippage = 2,90 USD.
1,45 Punkte × 2 USD = 2,90 USD. Stimmt überein.

ChatGPT widerspricht sich dabei selbst: es fordert 1,95 Punkte, rechnet seine
eigene Break-even-Tabelle danach aber mit `C = 0,145 R` — und diese 0,145
folgen aus 1,45 Punkten bei 10 Punkten Stopweite, nicht aus 1,95.

### 0.2 Aber es hat einen echten Fehler in v1 gefunden

Die Break-even-Tabelle in v1 rechnete mit `C = 0,30 R` (Stopweite 1 ATR ≈ 4,85
Punkte), die Kostentabelle direkt darüber mit `C = 0,145 R` (Stopweite 10
Punkte). Beide Zahlen sind für sich richtig, aber die Annahme stand nirgends,
und nebeneinander widersprechen sie sich.

**Die Ursache ist inhaltlich wichtiger als der Fehler:** Es gibt gar keine eine
Break-even-Trefferquote. Sie hängt an der Stopweite, weil die Kosten in R an
der Stopweite hängen. Deshalb steht sie ab jetzt als Fläche da, nicht als
Spalte (Abschnitt 5).

### 0.3 ChatGPTs stärkster Punkt: „Kurve = ein Test" reicht nicht

Hier hat es recht, und das war die schwächste Stelle in v1.

17 Versatzwerte sind nicht ein Test — aber auch nicht 17, weil sie
hochkorreliert sind: dieselben Ereignisse, nur eine andere Barriere. Die
effektive Anzahl liegt irgendwo dazwischen, und „nennen wir es eine Kurve"
ist keine Statistik.

**Lösung: Permutationstest über die ganze Kurve.** Musterzugehörigkeit
zufällig vertauschen, die komplette Kurve neu rechnen, 1.000 Wiederholungen,
und fragen, wie oft eine mindestens so gute *und* so glatte Kurve zufällig
entsteht. Das liefert einen exakten p-Wert für die Aussage „diese Kurve ist
echt", ohne Tests zählen zu müssen, und behandelt die Korrelation von selbst
richtig. Dank der Vorberechnung aus Abschnitt 7 ist das billig.

### 0.4 Die Zahl, die den Plan am stärksten verändert

v1 setzte eine Mindeststichprobe von 200. ChatGPT merkt zu Recht an, dass 200
keine magische Grenze ist. Nachgerechnet ist es schlimmer als das:

| Stichprobe | kleinster erkennbarer Effekt (α = 0,05, Power 0,80) |
|---:|---|
| 100 | +19,3 Prozentpunkte (69 % gegen 50 %) |
| **200** | **+13,8 Prozentpunkte (64 % gegen 50 %)** |
| 500 | +8,8 Prozentpunkte |
| 1.000 | +6,2 Prozentpunkte |
| 1.500 | +5,1 Prozentpunkte |
| 5.000 | +2,8 Prozentpunkte |

Umgekehrt, was ein realistischer Vorteil kostet:

| Zu belegender Effekt | nötige unabhängige Fälle |
|---|---:|
| 65 % gegen 50 % | 169 |
| 60 % gegen 50 % | 387 |
| **55 % gegen 50 %** | **1.565** |
| 53 % gegen 50 % | 4.355 |
| 52 % gegen 50 % | 9.806 |

**Bei n = 200 sehen wir nur Effekte, die es fast sicher nicht gibt.** Der
realistische Bereich liegt bei 52–55 % — dafür braucht es 1.500 bis 10.000
unabhängige Fälle. Die Mindeststichprobe steigt deshalb von 200 auf **1.500
überschneidungsfreie Fälle** für einen berichteten Fund; darunter wird
gemessen und gelistet, aber ausdrücklich als „nicht entscheidbar" markiert.

Das betrifft direkt Laurins eigene Vorgabe („Minimum von 100 Mal das Muster").
100 Fälle reichen nicht — aber **nicht, weil das Muster schlecht wäre, sondern
weil es unmessbar ist.** Der Unterschied ist wichtig: wir sortieren seltene
Muster nicht als unprofitabel aus, sondern als unentscheidbar.

### 0.5 Was weder ChatGPT noch Laurin genannt hat: der Fluch des Siegers

Laurin will am Ende ein **Ranking** — „Muster 1 zu 68 %, Muster 2 zu 66 %".
Genau diese Bauform hat einen systematischen Fehler.

Wenn für jedes Muster über hunderte Konfigurationen der beste Stop und das
beste Ziel gesucht wird und danach die Sieger nach ihrer *auf denselben Daten
gemessenen* Trefferquote sortiert werden, ist jede Zahl in der Rangliste **nach
oben verzerrt** — und zwar am stärksten bei den Mustern mit der kleinsten
Stichprobe. Die Rangliste sortiert dann teilweise nach Rauschen.

Das ist der klassische Weg, auf dem eine saubere Messmaschine ein unbrauchbares
Endergebnis produziert. Zwei Gegenmaßnahmen, beide verbindlich:

1. **Die berichtete Zahl kommt nie aus dem Trainingsdatensatz.** Parameter in
   Training suchen, einfrieren, Zahl aus Validation. Der Trainingswert wird
   mit ausgewiesen, aber als das gekennzeichnet, was er ist: der
   auswahlverzerrte Schätzer.
2. **Bootstrap-Korrektur schon in Training**, damit die Schrumpfung sichtbar
   wird, bevor Validation verbraucht ist.

### 0.6 Laurins Einwand — er hat recht, und mehr als ich zugegeben habe

Sein Punkt: *„der kann doch gar nicht wissen, welche Muster er durchtesten
will."* Er will nicht 22 vorgegebene Muster, sondern: alles durchgehen, alles
katalogisieren, Häufigkeiten zählen, aussortieren, dann vermessen.

Ich hatte in v1 geschrieben, unüberwachte Formsuche könne seine Frage nicht
beantworten, weil ein Cluster keine Strukturlinie hat. **Das war zu schnell
abgetan.** Ein gefundenes Formcluster hat sehr wohl objektive Linien: das
Hoch und das Tief seines eigenen Fensters. Und wenn die Extrema innerhalb des
Clusters reproduzierbar an denselben Positionen liegen — etwa an Position 5
und 15 —, dann ist das eine W-artige Form, und diese beiden Punkte *sind* die
Anker. Die Linien entstehen aus der Statistik des Clusters selbst.

Seine Vision ist damit umsetzbar, und Abschnitt 9 sagt wie. Drei ehrliche
Einschränkungen stehen dort ebenfalls.

### 0.7 Weiteres aus ChatGPTs Kritik, das übernommen wird

- **MAE der späteren Gewinner ist Diagnose, kein Optimierer.** Richtig — sie
  bedingt auf die Zukunft. Präziser als beide Fassungen: sie liefert eine
  **Obergrenze für den Preis des Engerstellens** (wie viele Gewinner man
  verliert), sagt aber nichts über die Verluste, die man dadurch früher
  beendet. Sie ist eine Seite der Bilanz, nicht die Bilanz.
- **Limit-Füllungen sind aus OHLC nicht simulierbar.** Richtig.
  Warteschlangenposition, Volumen vor der eigenen Order, tatsächlich
  gehandelte Kontrakte — nichts davon steht in OHLC. Die Regel „mindestens
  ein Tick hindurch" ist eine **Modellannahme mit unquantifizierbarem
  Fehler**. Konsequenz: Limit-Ergebnisse werden durchgehend als weniger
  belastbar gekennzeichnet als Markt- und Stop-Ergebnisse. Tickdaten wären
  der Ausweg, sind aber am 29.08. geprüft und verworfen worden.
- **E[R] allein reicht nicht.** Drawdown, Verlustklumpung, Regime-Stabilität,
  Parameter-Empfindlichkeit und Handelsfrequenz fehlten. Sie stehen jetzt in
  Abschnitt 6 und gehen in die Rangliste ein.
- **Erst tief, dann breit.** Beide Seiten stimmen zu. Begründung ist jetzt
  schärfer formuliert (Abschnitt 8).

---

## 1. Die Forschungsfrage

Nicht „welches Muster funktioniert", sondern:

> **Welche wiederkehrenden Marktzustände existieren, wie oft treten sie auf,
> und welche davon verändern die Vorwärtsverteilung so, dass daraus nach
> realistischen Kosten ein robuster Erwartungswert entsteht — bei einer
> Position, die relativ zur Struktur des Zustands konstruiert ist?**

Der Kern gegenüber allem Bisherigen: Stop und Ziel hängen an der
**Strukturlinie**, nicht an einem ATR-Vielfachen. Eine Strukturlinie ist der
Ort, an dem die Stops anderer Marktteilnehmer liegen. Ein ATR-Abstand ist nur
eine Zahl.

### Was schon dasteht

`level_1`, `level_2`, `level_neckline`, `pattern_hoehe_pkt`,
`pattern_hoehe_atr` liegen bereits je Ereignis in der Datenbank, dazu alles
Musterspezifische als JSON. Für die elf vorhandenen Erkenner ist **keine
Neuerkennung nötig**.

Ebenfalls tragfähig: der Lookahead-Schutz (`verfuegbar_idx` als einzige
zulässige Quelle), die Erste-Berührungs-Messung in
`common/ereignisse/barrieren.py`, der Zeit-Split, die Regime-Achsen,
`cluster_id` für überlappende Ereignisse.

---

## 2. Der Startkatalog — ausdrücklich nicht die Wahrheit

Die folgenden Muster sind der **Startkatalog für den ersten Durchstich**, weil
elf davon technisch fertig und geprüft sind. Sie sind keine Aussage darüber,
welche Strukturen der Markt besitzt. Abschnitt 9 lässt den Katalog aus den
Daten wachsen.

| Muster | Richtung | Strukturlinien — die Anker für Stop und Ziel | Stand |
|---|---|---|---|
| Doppelboden (W) | long | tief 1, tief 2, Nackenlinie, Musterhöhe | vorhanden |
| Doppeltop (M) | short | hoch 1, hoch 2, Nackenlinie, Musterhöhe | vorhanden |
| Liquidity Sweep | gegen den Sweep | gefegtes Niveau, Sweep-Extrem, Reclaim-Kerze | vorhanden |
| Fair Value Gap | in Gap-Richtung | obere Kante, untere Kante, Mitte | vorhanden |
| Order Block | in OB-Richtung | OB-Hoch, OB-Tief, OB-Öffnung | vorhanden |
| Equal Highs / Lows | gegen | das gemeinsame Niveau, Toleranzband | vorhanden |
| Displacement | in Bewegungsrichtung | Start, Ende, 50-%-Marke | vorhanden |
| MSS / BOS | in Bruchrichtung | gebrochener Swingpunkt, letzter Gegenswing | vorhanden |
| Swing-Hoch / -Tief | beide | der Swingpunkt selbst | vorhanden |
| S/R-Zonentest | beide | Zonengrenzen, Mitte, Anzahl Tests | vorhanden |
| Opening-Range-Bruch | in Bruchrichtung | IB-Hoch, IB-Tief, IB-Mitte | vorhanden |
| Flagge / Wimpel | in Impulsrichtung | Flaggengrenzen, Impulsstart, Messziel | neu |
| Rechteck / Range | Bruchrichtung | Range-Hoch, Range-Tief, Mitte | neu |
| Dreieck / Keil | Bruchrichtung | die zwei konvergierenden Linien, Apex | neu |
| Kompression (NR7, Inside) | Bruchrichtung | Kompressionshoch, -tief | neu |
| Kopf-Schulter | Bruchrichtung | Nackenlinie, Kopf, Schultern | neu |
| Drei Antriebe | Umkehr | die drei Extreme, Kanallinie | neu |
| Trendlinienbruch | Bruchrichtung | die Trendlinie, letzter Berührpunkt | neu |
| Runde Marke | beide | 25er- / 50er- / 100er-Marke | neu |
| VWAP-Zustand | beide | VWAP, ±1σ, ±2σ | Spalte da |
| Sessionmarken | beide | PDH, PDL, Midnight Open, Globex-H/L | Spalte da |
| Eröffnungsgap | Schließungsrichtung | Vortagesschluss, Eröffnung, Mitte | neu |

**Offene Frage an die Daten, nicht an uns:** Messen diese Erkenner überhaupt
verschiedene Dinge? Bei Minutendaten kann dieselbe Bewegung nacheinander als
Swing, Sweep, MSS, BOS, Displacement und W erscheinen. Wenn ja, ist der Katalog
kleiner, als er aussieht, und die Stichproben sind kleiner, als sie aussehen.
Phase 0 misst das, bevor irgendetwas anderes läuft.

---

## 3. Sechs Achsen

Jede Musterinstanz wird durch sechs Entscheidungen zu einem Trade. Alle sechs
sind Forschungsfragen; keine wird gesetzt.

**Achse 1 — Wann wird entschieden.** Zeitbestätigung 0…5 Kerzen, alle sechs
nach derselben, vorher festgelegten Regel. Preisbestätigung (Kurs erreicht ein
Niveau) = **Stop-Order**. Rücklaufbestätigung = **Limit-Order**. Laurins beide
Ordertypen sind zwei Formen derselben Frage: Bestätigung durch Preis statt
durch Zeit.

**Achse 2 — Womit eingestiegen wird.** Markt, Stop, Limit. Berichtet wird nie
`E[R] je Füllung`, sondern `Füllquote × E[R | gefüllt]` — der Erwartungswert
**je Signal**. Ein Limit verpasst genau die Bewegungen, die ohne Rücklauf
davonlaufen; das sind oft die besten. Limit-Zahlen tragen zusätzlich die
Kennzeichnung aus 0.7.

**Achse 3 — Wo der Stop liegt.** Anker: die Strukturlinie. Versatz `k`
darunter (long): `0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32, 40, 52, 64, 80`
Ticks — und parallel dasselbe in ATR-Anteilen. Kontrollgruppe: der reine
ATR-Stop ohne Strukturbezug. Wenn der gleich gut ist, war die Struktur-Idee
nichts wert, und das muss sichtbar bleiben.

**Achse 4 — Wo das Ziel liegt.** Anker: Gegenlinie, nächstes S/R-Niveau,
PDH/PDL, VWAP, Messziel aus der Musterhöhe. Versatz `j` **vor** dem Niveau:
0…24 Ticks. Kontrollgruppe: feste R-Vielfache.

**Achse 5 — Wie sonst noch beendet wird.** Zeitstopp, Sessionende,
Einstandsverschiebung nach +xR, ATR- und Swing-Trailing, Teilausstieg.
Vorher hingeschriebene, falsifizierbare Erwartung: **Einstandsverschiebung
hebt die Trefferquote und senkt E[R].**

**Achse 6 — Wie gut das Muster ist.** Merkmalsvektor je Instanz:
Schenkelverhältnis, Abstand der Extrema, Symmetrie, Dauer, Größe in ATR,
Volatilität während der Bildung, Volumen am Extremum, Lage in der Session,
HTF-Trend, Abstand zum nächsten Niveau, vorausgegangener Sweep. **Die Liste
steht fest, bevor der erste Lauf startet** — bei genug Merkmalen findet sich
zu jeder Lage eine ähnliche Lage.

---

## 4. Was je Zelle berichtet wird

Die zwölf Fragen aus Laurins ChatGPT-Verlauf, plus die fünf, die in v1
fehlten.

| Nr | Frage | Gemessene Größe |
|---:|---|---|
| 1 | Wie häufig tritt der Zustand auf? | `n`, `n_überschneidungsfrei`, Gelegenheiten je Jahr |
| 2 | Wie häufig folgt welches Outcome? | Ziel zuerst / Stop zuerst / unentschieden / uneindeutig |
| 3 | Wie weit läuft es? | MFE Median, p75, p90 — in R und Punkten |
| 4 | Wie wahrscheinlich sind Zielbereiche? | `P(erreicht)` je Anker und Versatz — die Zielkurve |
| 5 | Wie wahrscheinlich ist Invalidierung? | `P(Strukturlinie schließt gebrochen)`, getrennt vom Stop |
| 6 | Wie groß sind MAE und MFE? | beide Verteilungen; MAE der Gewinner **als Diagnose** (0.7) |
| 7 | Wie lange dauert es? | Median und p90 der Kerzen bis Ziel bzw. Stop, getrennt |
| 8 | Wirkung zunehmender Bestätigung? | dieselbe Zeile für N = 0…5 nebeneinander |
| 9 | Ab wann wird es sicher? | Wilson-Breite über N, und wo `n` unter die Grenze fällt |
| 10 | Ab wann ist zu viel Gewinn weg? | **Restpotential**: MFE ab Einstieg / MFE ab Musterabschluss |
| 11 | Bester Entscheidungspunkt? | `argmax E[R] nach Kosten` über N |
| 12 | Hohe Quote ohne Edge? | Zellen mit `P > 0,65` und `E[R] ≤ 0` werden gelistet |
| **13** | **Wie sieht die Equitykurve aus?** | max. Drawdown in R, längste Verlustserie |
| **14** | **Klumpen die Verluste?** | Autokorrelation der Ergebnisfolge, Verlustserienverteilung |
| **15** | **Hält es über die Zeit?** | E[R] je Kalenderjahr und je Volatilitätsregime, getrennt |
| **16** | **Wie empfindlich sind die Parameter?** | E[R] der Nachbarversätze; zackige Kurve = kein Fund |
| **17** | **Ist es wirtschaftlich nutzbar?** | `E[R] × Gelegenheiten/Jahr`, mit unterer Konfidenzgrenze |

Nummer 17 ist Laurins eigener Punkt: *„es bringt ja nichts, wenn man einen
theoretischen Trade hat, der 10.000 Dollar machen würde, aber der funktioniert
nur in einem von 100 Fällen."* Berichtet wird deshalb nie E[R] allein,
sondern immer zusammen mit der Frequenz — und die **untere** Konfidenzgrenze
des Jahresertrags entscheidet, nicht der Punktschätzer.

---

## 5. Kosten

MNQ, NinjaTrader-Free, aus `backtest/kosten.py`. Rechenweg in Abschnitt 0.1.

| Einstieg | Ausstieg | Kommission | Slippage | Round Turn |
|---|---|---:|---:|---:|
| Markt | Stop (Markt) | 0,95 Pkt | 0,50 Pkt | **1,45 Pkt** |
| Stop-Order | Stop (Markt) | 0,95 Pkt | ≥ 0,50 Pkt | ≥ 1,45 Pkt |
| Limit | Stop (Markt) | 0,95 Pkt | 0,25 Pkt | 1,20 Pkt |
| Limit | Limit (Ziel) | 0,95 Pkt | 0,00 Pkt | 0,95 Pkt |

Zwischen teuerster und billigster Zeile liegen 35 %. Die Slippage bei
Stop-Füllungen ist die einzige Annahme und wird als solche geführt.

### Break-even ist eine Fläche, keine Zahl

Weil die Kosten in R an der Stopweite hängen, hängt auch die nötige
Trefferquote daran. Marktorder, 1,45 Punkte Round Turn:

| Ziel / Stop | Stop 3 Pkt | Stop 5 Pkt | Stop 10 Pkt | Stop 20 Pkt |
|---|---:|---:|---:|---:|
| 0,5R / 1R | 98,9 % | 86,0 % | 76,3 % | 71,5 % |
| 1R / 1R | 74,2 % | 64,5 % | 57,2 % | 53,6 % |
| 2R / 1R | 49,4 % | 43,0 % | 38,2 % | 35,8 % |
| 3R / 1R | 37,1 % | 32,2 % | 28,6 % | 26,8 % |

Lies die Ecken: **oben links ist nicht handelbar** (98,9 % bei engem Stop und
nahem Ziel), **unten rechts sehr wohl** (26,8 %). Das ist die ganze Lehre —
die Trefferquote allein sagt nichts, und ein enger Stop ist nicht deshalb
schlecht, weil er ausgelöst wird, sondern weil er strukturell teuer ist.

---

## 6. Was zusätzlich untersucht wird

**6.1 Die Niveau-Annäherungsstudie.** Musterunabhängig: nähert sich der Kurs
*irgendeinem* Niveau — wie oft wird es erreicht, wie oft um x Ticks
überschossen, wie oft dreht er vorher? Eine Tabelle, die danach für jedes
Muster gilt, aus allen 2,5 Mio Kerzen. Das wertvollste Einzelstück im Plan.

**6.2 MAE der späteren Gewinner — als Diagnose.** Siehe 0.7. Liefert die
Obergrenze für den Preis des Engerstellens, nicht die Bilanz.

**6.3 Die Spiegelprobe.** Gilt für M dasselbe wie für W, gespiegelt? Wenn
nein: entweder echte Marktasymmetrie (bei Aktienindizes plausibel) oder ein
Fehler bei uns. Kostet nichts, fängt einen ganzen Fehlertyp ab.

**6.4 Versatz in Ticks *und* in ATR.** Laurin sagte Ticks. Vermutung: ATR
gewinnt, weil das Rauschen um 03:00 ET drei- bis viermal kleiner ist als um
09:30 ET. Beide werden gemessen und nebeneinandergestellt.

**6.5 Rückwärtsanalyse als Hypothesenquelle.** Laurins „kreuz und quer":
nicht nur vom Muster zum Ergebnis, sondern von den großen Bewegungen zurück zu
den Zuständen, die ihnen vorausgingen. Als **Evidenz unbrauchbar** (bedingt
auf das Ergebnis), als **Kandidatenlieferant sehr brauchbar** — die so
gefundenen Zustände werden anschließend regulär vorwärts getestet. Läuft
ausschließlich auf Trainingsdaten.

---

## 7. Die Testfläche

Alles Obige als unabhängige Einzeltests:

```
  22 Muster x 2 Richtungen                            44
  x 3 Einstiegsmechaniken                            132
  x 3 Stop-Anker x 17 Versatzwerte                 6.732
  x 4 Ziel-Anker x 10 Versatzwerte               269.280
  x 4 Horizonte                                1.077.120
  ------------------------------------------------------
  bei alpha = 0,05 rein zufaellig "signifikant"  ~53.856
```

Fünf Maßnahmen, alle **vor** dem ersten Lauf:

1. **Permutationstest über die ganze Kurve** statt „Kurve = ein Test"
   (Abschnitt 0.3). Exakter p-Wert, Korrelation korrekt behandelt.
2. **Benjamini-Hochberg-FDR** über die verbleibenden Kurventests. Bonferroni
   läge bei α = 0,000036 und erschlüge jeden realen Effekt mit.
3. **Angepasste Nulllinie**: gleicher Bestätigungszustand, gleiches Regime,
   gleiche Niveauart — nur ohne das Muster. Nicht Zufallskerzen; sonst misst
   man den Effekt von drei Aufwärtskerzen.
4. **Mindestens 1.500 überschneidungsfreie Fälle** für einen berichteten Fund
   (Abschnitt 0.4). Darunter wird gemessen und als unentscheidbar markiert.
5. **Geschlossene Türen.** Training ≤ 31.12.2023. Validation 2024 und OOS ab
   2025 bleiben während der ganzen Suche zu. Was in Training gewinnt, wird
   genau einmal auf Validation geworfen — mit eingefrorenen Parametern, und
   die **Validationszahl ist die berichtete** (Abschnitt 0.5).

### Die Rechenzeit ist gelöst

Je Ereignis werden laufendes Hoch und laufendes Tief des Vorwärtsfensters
einmal vorberechnet. Beide sind **monoton**, also findet `np.searchsorted` die
erste Berührung für jeden beliebigen Preis in Logarithmuszeit. Jeder Versatz,
jedes Ziel, jeder Ordertyp ist danach ein Nachschlag statt eines Durchlaufs.
Rund 100 MB je Muster (50.000 Ereignisse × 240 Kerzen × 2 Reihen × 4 Byte),
Stunden statt Wochen. Der Permutationstest wird dadurch überhaupt erst
bezahlbar.

---

## 8. Die Phasen

### Phase 0 — Bestandsaufnahme *(neu, billig, kann sofort laufen)*

Genau der Schritt, den Laurin beschrieben hat: erst zählen, dann aussortieren.
Läuft gegen die vorhandene Datenbank, ohne eine einzige Outcome-Zahl
anzufassen.

- Häufigkeit je `pattern_type` × `direction`, roh und überschneidungsfrei
- Verteilung über Jahre, Sessions, Regime — tritt es durchgehend auf oder nur
  2020?
- **Überlappungsmatrix**: wie oft feuern zwei Erkenner auf derselben Bewegung?
  Antwortet auf die Frage aus Abschnitt 2.
- Abgleich gegen die Stichprobentabelle aus 0.4: was ist überhaupt
  entscheidbar?

**Ergebnis:** die erste echte Aussortierung, mit Zahlen statt Annahmen. Kann
gut sein, dass von 22 Erkennern nur acht die Frequenzhürde nehmen und drei
davon dieselbe Bewegung beschreiben.

Wichtig: Phase 0 sieht **keine Ergebnisse an** und verbraucht deshalb kein
Testbudget.

### Phase 1 — Die Messmaschine an einem Muster härten

Doppelboden long, vollständig durch alle sechs Achsen. **Zweck ist nicht, einen
Vorteil zu finden**, sondern zu beweisen, dass die Messung stimmt: Spiegelprobe
gegen M, Kontrollgruppen, Permutationstest, angepasste Nulllinie, Kosten,
Validation.

Der Grund für „tief statt breit" ist nicht Bequemlichkeit: **ein Fehler in der
Maschine erzeugt bei 22 Mustern 22 falsche Ergebnisse, die alle plausibel
aussehen** — und wir hätten keinen Weg, es zu merken. Am W merken wir es, weil
wir wissen, wie ein W sich verhalten sollte.

### Phase 2 — Der Katalog durch die geprüfte Maschine

Alle Muster, die Phase 0 überstanden haben. Ergebnis ist Laurins Rangliste —
aber mit Validationszahlen, Frequenz, Drawdown und Unsicherheit je Zeile, nicht
nur einer Prozentzahl.

Kategorien werden erst nach Phase 1 methodisch begründet festgelegt, nicht
vorher erfunden.

### Phase 3 — Der Katalog wächst aus den Daten

Siehe Abschnitt 9. Erst hier, weil vorher die Maschine nicht bewiesen ist.

---

## 9. Wie Laurins Entdeckungs-Vision umgesetzt wird

Sein Ziel: nicht 22 vorgegebene Muster, sondern alle wiederkehrenden Formen
finden, zählen, aussortieren, vermessen, ranken.

**Das ist umsetzbar.** Das Verfahren heißt Motiv-Suche und ist Standard:

1. Jedes Fenster fester Länge (20, 40, 60 Kerzen) aus der Reihe schneiden.
2. **Normalisieren** — Mittelwert abziehen, durch ATR teilen. Übrig bleibt die
   Form, unabhängig von Kursniveau und Volatilität.
3. Wiederkehrende Formen finden. Das *Matrix Profile* macht das in
   `O(n log n)` je Fensterlänge über FFT — auf 2,5 Mio Kerzen machbar.
4. Häufigkeiten zählen: „diese Form 3.000-mal, jene 500-mal, diese dreimal".
   Aussortieren nach der Tabelle aus 0.4.
5. Die überlebenden Formen durch **dieselbe** Maschine schicken wie den
   benannten Katalog.

**Und die Strukturlinien gibt es doch** (Korrektur zu v1): Hoch und Tief des
Motivfensters sind objektive Anker. Liegen die Extrema innerhalb eines Clusters
reproduzierbar an denselben Positionen, ist das eine benennbare Form, und diese
Punkte sind die Linien.

Drei ehrliche Einschränkungen:

- **Die Normalisierung entscheidet, was gefunden wird.** Z-normiert sind ein
  5-Punkte-W und ein 50-Punkte-W dieselbe Form; ATR-normiert nicht. Volumen
  drin oder nicht. Diese Wahl wird **vorher** festgelegt und nicht optimiert.
- **Die Entdeckung läuft ausschließlich auf Trainingsdaten.** Formen auf der
  Gesamthistorie zu suchen wäre ein subtiler Blick in die Zukunft. Der Katalog
  wird aus Training eingefroren und dann auf Validation angewandt.
- **Die Entdeckung selbst kostet kein Testbudget**, weil sie keine Ergebnisse
  ansieht — nur die Vermessung danach zählt. Das ist der Grund, warum das
  überhaupt sauber geht.

---

## 10. Woran ein Fund erkannt wird — vorher festgelegt

Alle acht Punkte müssen zutreffen:

1. `E[R]` nach Kosten > 0 auf **Validation**, mit eingefrorenen Parametern.
2. Permutationstest der Kurve besteht, FDR-korrigiert.
3. Die Nachbarversätze sind ebenfalls positiv — glatte Kuppe, keine Einzelzelle.
4. Die **angepasste** Nulllinie wird geschlagen, nicht nur die Null.
5. Mindestens 1.500 überschneidungsfreie Fälle.
6. Uneindeutiger Anteil (Kerze berührt Ziel und Stop) unter 15 %.
7. `E[R] × Gelegenheiten/Jahr` ist mit unterer Konfidenzgrenze positiv.
8. Kein einzelnes Kalenderjahr trägt das Ergebnis allein.

> **Bekannte Lücke.** Der Wirtschaftskalender deckt im Wesentlichen die
> laufende Woche ab. Für sieben Jahre Historie haben wir keine Termindaten.
> Konditionierung auf Nachrichten ist vorerst unmöglich — FOMC- und
> CPI-Minuten bleiben als Rauschen in allen Zahlen. Das wird ausgewiesen, nicht
> weggelassen.

---

## 11. Offene Fragen an Laurin

Zwei davon sind Handelswissen, das ich nicht erfinden sollte.

1. **Welche Linie ist bei einem W *die* untere Linie?** Tiefstes der beiden
   Tiefs, das zweite (aktuellere), oder der Mittelwert? *Vorschlag: das
   tiefste — darunter liegen die Stops der anderen. Alle drei werden gemessen.*
2. **Wo steigst du bei einem W tatsächlich ein?** Gemessen werden: zweites
   Tief, Stop-Order über der Nackenlinie, Limit beim Retest. *Gibt es eine
   vierte, die du benutzt?*
3. **Am Sessionende glattstellen?** *Vorschlag: ja, intraday — zusätzlich
   einmal ohne, um zu sehen, was die Grenze kostet.*
4. **Ein Kontrakt oder Teilausstiege?** *Vorschlag: erst alles mit einem;
   Teilausstiege als eigene Runde.*
5. **Historische Termindaten besorgen?** *Vorschlag: erste Runde ohne, Lücke
   ausgewiesen.*
6. **Startet Phase 0 sofort?** Sie ist billig, sieht keine Ergebnisse an und
   liefert genau die Aussortierung, die du beschrieben hast. *Vorschlag: ja,
   unabhängig von den übrigen Antworten.*

---

## 12. Was aus diesem Plan folgt, wenn er stimmt

Erste Lieferung nach Phase 0: eine Tabelle, welche Muster überhaupt oft genug
vorkommen, um messbar zu sein, und welche Erkenner dieselbe Bewegung doppelt
zählen.

Erste Lieferung nach Phase 1: die Versatzkurve für Doppelboden long, Stop an
der unteren W-Linie, gegen die angepasste Nulllinie, mit Permutations-p-Wert,
auf Trainingsdaten — und die Validationszahl der eingefrorenen Konfiguration.

Und die realistische Erwartung, die vorher hier stehen muss: **es kann sein,
dass nichts übrig bleibt.** Bei 52–55 % erwartetem Effekt und dem
Stichprobenbedarf aus 0.4 ist das ein möglicher Ausgang. Auch das wäre ein
Ergebnis — sauber gemessen, statt teuer im Livebetrieb gelernt.
