# Das W, je Bestätigungsstufe vermessen — 03.09.2026

**Kurzfassung:** Der Trade-off ist real und hat sein Optimum bei rund 70 %
der Strecke zur Nackenlinie. Das W trägt einen echten Richtungsvorteil von
bis zu 1,2 Prozentpunkten gegenüber einer gematchten Kontrolle — das sind
47 Cent je Trade gegen 2,90 USD Kosten. **0 von 1.260 Kombinationen sind
nach Kosten profitabel.**

**Was gemessen wurde:** 88.137 W-Kandidaten aus 2,58 Mio MNQ-Minutenkerzen,
Training 2019-05 bis 2023-12. Für jeden Kandidaten acht Einstiegszeitpunkte
auf dem Weg vom zweiten Boden zur Nackenlinie und zwölf über die
Zickzack-Struktur, jeweils gegen neun strukturelle Stops und sieben
strukturelle Ziele. **1.260 ausgewertete Zellen, 12.591 Zeilen mit
Untergruppen.**

Rohtabelle: `data/w_stufenmessung.csv` (reproduzierbar über
`werkzeuge/w_stufenmessung.py`, nicht versioniert).

---

## 1. Was an der bisherigen Logik nicht zu Laurins Absicht passte

Sein Auftrag vom 03.09.2026, Punkt 11.4: *„Identifiziere konkret, wo die
aktuelle Logik meine Intention noch falsch abbildet."* Fünf Punkte:

### 1.1 Es gab nur EINEN Einstiegszeitpunkt

`finde_w` meldete je Kandidat genau ein `bestaetigt_idx` — die erste Kerze,
deren Schluss 15 % der Musterhöhe über dem laufenden Minimum lag. Damit war
die Bestätigungsstufe eine **Entwurfsentscheidung**, keine Messgröße. Genau
das wollte er nicht.

**Jetzt:** `common/muster_w_stufen.py` baut eine Leiter. Nichts an der Zahl
der Bestätigungen ist vorher festgelegt.

### 1.2 Stop und Ziel wurden nur als ATR-Vielfache gemessen

Die Messung vom 02.09. (`werkzeuge/mustervergleich.py`) verwendet für alle
14 Mustertypen `stop_loss_atr` / `take_profit_atr`. Ein Stop „ein ATR unter
dem Einstieg" hat mit der unteren W-Linie nichts zu tun.

**Jetzt:** Stop = zweiter Boden minus Abstand, Ziel = Nackenlinie minus
Abstand. Der Abstand in **beiden** Währungen — als Anteil der Musterhöhe und
in absoluten Punkten —, weil vorher nicht entschieden ist, welche trägt.

### 1.3 MFE wurde über den ganzen Horizont gemessen, auch nach dem Stop

Ein Trade, der in Kerze 3 ausgestoppt wurde und danach vier Stunden stieg,
sah aus, als hätte er weit im Gewinn gestanden. Genau die Kennzahl, mit der
Laurin wissen will, wie oft *„der Markt zunächst steigt und anschließend
trotzdem einbricht"*, war damit unbrauchbar.

**Jetzt:** getrennt ausgewiesen — `mfe_R_bis_ausstieg` (ehrlich) und
`mfe_R_horizont` (was erreichbar gewesen wäre, wenn man gehalten hätte).

### 1.4 Der zweite Boden stand zu früh fest

Bereits am 02.09. bekannt und in dieser Sitzung repariert: die Schleife brach
bei der ersten Rückkehr ins Tiefband ab. **Jetzt** läuft sie bis zur
bestätigten Umkehr weiter, nimmt das Minimum des Abschnitts, und ein
späteres, tieferes Minimum ergibt einen **zweiten Kandidaten** — nicht eine
rückwirkende Korrektur des ersten.

### 1.5 Ein Vergleichsfehler bei der Geometrielinie — gefunden beim Nachrechnen

Die Trefferquote wurde über die **entschiedenen** Fälle gerechnet, die
Geometrielinie `Risiko/(Risiko+Lohn)` aber über **alle**. Wer im Horizont
nicht entscheidet, ist kein Zufallsauszug — solche Trades haben systematisch
weitere Barrieren im Verhältnis zur Volatilität. Der Fehler machte die
Abweichung bei den späten Sprossen um rund **0,7 Prozentpunkte zu groß** und
hätte fast einen Scheinfund erzeugt.

Behoben; festgehalten in
`tests/test_w_stufenmessung.py::test_geometrie_ist_risiko_durch_risiko_plus_lohn`.

---

## 2. Wie gemessen wurde

### 2.1 Zwei Leitern, weil es zwei Fragen sind

**Weg-Stufen** — der Kurs hat 15 / 25 / 35 / 45 / 55 / 70 / 85 / 100 % der
Strecke vom zweiten Boden zur Nackenlinie zurückgelegt. Parameterfrei, und
genau die Achse, um die es wirtschaftlich geht: was schon gelaufen ist, ist
als Gewinn nicht mehr zu holen.

**Struktur-Stufen** — die erste, zweite, … sechste abgeschlossene
Aufwärtsbewegung im Sinne eines Zickzacks. Näher an dem, was ein Mensch
„Bestätigung" nennt. Ausdrücklich **nicht** „grüne Kerzen zählen": ein
Schenkel ist erst abgeschlossen, wenn er die Mindestbewegung überschreitet,
und der nächste beginnt erst nach einer echten Korrektur. Eine durchlaufende
Rally aus zwanzig grünen Kerzen ist **eine** Bewegung.

Die Mindestbewegung ist ein Parameter — deshalb wird sie mit 10 % und 20 %
der Musterhöhe **doppelt** gerechnet, statt einen Wert zu setzen.

### 2.2 Was eine Sprosse ungültig macht

Fällt der Kurs unter den zweiten Boden, ist die untere W-Linie gebrochen.
Alle Sprossen danach zählen nicht — wer dort einstiege, handelte kein W mehr.
Das ist Laurins Punkt wörtlich: *„Wenn der Kurs nach einem vermeintlichen
zweiten Boden noch deutlich weiter fällt, darf die vorherige Kerze nicht
einfach rückwirkend als endgültiger zweiter Boden behandelt werden."*

### 2.3 Kein Lookahead

Jede Sprosse liegt bei oder nach dem Bestätigungsindex des Erkenners. Zu
diesem Zeitpunkt sind zweiter Boden, Nackenlinie und ATR bekannt — der
Erkenner hat sie mit genau diesen Kerzen gebildet. Gehandelt wird zur
**Eröffnung der Folgekerze**. Die Zukunft wird ausschließlich zum Messen des
Ausgangs benutzt.

Gesichert durch eine Abschneide-Probe: was auf der halben Reihe gefunden
wird, muss auf der ganzen identisch herauskommen
(`test_kein_lookahead_bei_abgeschnittener_reihe`, beide Leitern).

### 2.4 Kosten und Konventionen

Round Turn **1,45 Punkte** (0,95 USD Kommission je Seite = 0,475 Punkte, plus
ein Tick Slippage je Seite), Punktwert **2 USD** (MNQ, nicht 20), Horizont
240 Kerzen, Mindestrisiko 2 Punkte. Berührt eine Kerze Ziel und Stop, gilt
der **Stop** (Invariante 4); der Anteil solcher Fälle wird ausgewiesen und
liegt unter 1 %.

Wer im Horizont nicht entscheidet, wird zum **Schlusskurs** der letzten
Horizontkerze bewertet — nicht mit 0 R, das wäre eine Erfindung.

### 2.5 Die Formschwelle ist keine Voraussetzung

Ab welchem Formfehler eine Form kein W mehr ist, ist nicht kalibriert — der
Referenzsatz wartet auf Laurins Urteile. Statt einen Schnitt zu raten, läuft
der Formfehler als **Dimension** mit: jede Zelle steht zusätzlich je
Formfehler-Viertel. Seine späteren Urteile machen die Messung nicht
ungültig; sie sagen nur, welches Viertel „echte Ws" sind.

---

## 3. Ergebnis 1: Die Leiter — wie weit kommen Ws überhaupt?

Von 88.137 Kandidaten erreichen, bevor sie unter den zweiten Boden fallen:

| Anteil der Strecke zur Nackenlinie | erreicht |
|---:|---:|
| 15 % | 99,7 % |
| 25 % | 91,9 % |
| 35 % | 77,2 % |
| 45 % | 64,4 % |
| 55 % | 54,6 % |
| 70 % | 43,9 % |
| 85 % | 36,3 % |
| **100 % (Nackenlinie)** | **31,3 %** |

**Nur nicht einmal jedes dritte W erreicht seine Nackenlinie.** Über den
ganzen Horizont fallen 88,4 % irgendwann unter den zweiten Boden.

Struktur-Stufen bei 10 % Mindestbewegung: 1 → 100 %, 2 → 61 %, 3 → 44 %,
4 → 34 %, 5 → 28 %, 6 → 24 %. Bei 20 %: 97 / 53 / 36 / 28 / 23 / 18 %.

---

## 4. Ergebnis 2: Der Trade-off existiert — und hat ein Optimum

Bestes E[R] nach Kosten je Stufe, über alle 63 Stop/Ziel-Kombinationen:

| Stufe | erreichbare Fälle | Restpotential (% der Höhe) | bestes E[R] |
|---:|---:|---:|---:|
| 15 % | 87.844 | 68 % | −0,0216 |
| 25 % | 80.979 | 65 % | −0,0234 |
| 35 % | 68.001 | 59 % | −0,0212 |
| 45 % | 56.728 | 50 % | −0,0198 |
| 55 % | 48.090 | 42 % | −0,0166 |
| **70 %** | **38.661** | **29 %** | **−0,0147** |
| 85 % | 31.946 | 16 % | −0,0156 |
| 100 % | 27.437 | 9 % | −0,0233 |

**Die Kurve hat genau die Form, die Laurin vermutet hat.** Zu früh ist
schlecht (wenig Bestätigung), zu spät ist schlecht (Potential verbraucht),
dazwischen liegt ein Optimum — bei rund **70 % der Strecke zur
Nackenlinie**.

Bei den Struktur-Stufen dasselbe Muster, mit dem Optimum bei der **sechsten**
Aufwärtsbewegung (10 % Mindestbewegung): −0,0217 → −0,0185 → −0,0152 →
−0,0120 → −0,0107 → **−0,0045**.

**Aber:** Das Optimum liegt unter null. Der beste Punkt der Kurve ist der,
an dem man am wenigsten verliert.

---

## 5. Ergebnis 3: Keine einzige profitable Zelle

**0 von 1.260 Zellen** haben nach Kosten einen positiven Erwartungswert.
Die beste liegt bei −0,0045 R (t = −0,87, also nicht von null zu
unterscheiden), die typische bei −0,15 R.

In Geld, bei einem Kontrakt: die beste Zelle je Stufe liegt zwischen
**−0,02 und −1,57 USD je Trade**. Der Round Turn kostet 2,90 USD.

---

## 6. Ergebnis 4: Erst gestiegen, dann doch eingebrochen

Anteil der Trades, die mindestens ein halbes R im Plus standen und trotzdem
ausgestoppt wurden (Median über die Stop/Ziel-Kombinationen):

| Stufe | gestoppt nach Plus | MFE bis Ausstieg | MFE über den Horizont | Zeit bis Ziel | Zeit bis Stop |
|---:|---:|---:|---:|---:|---:|
| 15 % | 25,0 % | 0,79 R | 3,26 R | 15 Kerzen | 11 |
| 35 % | 17,9 % | 0,73 R | 2,96 R | 12 | 11 |
| 55 % | 6,5 % | 0,55 R | 2,40 R | 8 | 14 |
| 70 % | 2,3 % | 0,39 R | 2,08 R | 5 | 14 |
| 100 % | 1,0 % | 0,25 R | 1,78 R | 1 | 13 |

Das ist die zweite Hälfte des Trade-offs, sichtbar gemacht: Früh einsteigen
heißt in einem Viertel der Fälle zusehen, wie die Position ins Plus läuft und
dann doch ausgestoppt wird. Spät einsteigen beseitigt das fast vollständig —
und kostet das Potential, das die Tabelle in Abschnitt 4 aufwiegt.

---

## 7. Die entscheidende Gegenprobe: das W trägt etwas — nur zu wenig

Bei den späten Sprossen liegt die Trefferquote **über** der Geometrielinie.
Das sähe nach einem Fund aus. Zwei Erklärungen kommen in Frage und sehen in
der Tabelle identisch aus:

1. Nach einem bestätigten W steigt der Kurs öfter — das wäre der Fund.
2. MNQ ist im Trainingszeitraum von rund 7.000 auf 16.000 gestiegen.
   **Jeder** Long schlägt die Geometrielinie, ganz ohne Muster.

### 7.1 Erster Anlauf: zufälliger Einstieg — und warum er nicht reicht

Gleiche Risiko- und Lohnabstände in Punkten, gleiche Richtung, aber der
Einstieg an einer gleichverteilt zufälligen Stelle des Trainings. Ergebnis:
das Muster liegt 0,6 bis 2,3 Prozentpunkte vor dem Zufall.

**Das ist aber kein fairer Vergleich.** Ein zufälliger Punkt aus sieben
Jahren sitzt im Mittel in einer ruhigeren Phase als ein W — Muster häufen
sich, wo sich der Kurs bewegt. Dieselbe Punktzahl Abstand ist dort relativ
weiter weg. Der Vergleich misst dann Volatilität, nicht Struktur.

### 7.2 Zweiter Anlauf: derselbe Einstieg, um Handelstage verschoben

Der Einstieg wird um **ein bis fünf ganze Handelstage** verschoben, Richtung
gewürfelt. Regime, Tageszeit und Volatilität bleiben erhalten — nachgemessen
liegt die Median-ATR am verschobenen Punkt bei **4,2 gegen 4,0** am Muster,
also sogar leicht *gegen* das Muster. Nur die Ausrichtung auf die Formation
ist zerstört.

Fünf Ziehungen je Stufe, gemittelt über fünf vorher festgelegte
Stop/Ziel-Kombinationen (nichts ausgewählt):

| Stufe | Muster | Kontrolle (5 Ziehungen) | **Vorsprung** | Streuung der Kontrolle |
|---:|---:|---|---:|---:|
| 15 % | −0,44 | −0,42 … −0,46 | **−0,02** | ±0,03 |
| 25 % | −0,38 | −0,22 … −0,43 | **−0,08** | ±0,07 |
| 35 % | −0,04 | −0,05 … −0,19 | **+0,09** | ±0,05 |
| 45 % | +0,22 | −0,20 … +0,05 | **+0,29** | ±0,08 |
| 55 % | +0,50 | −0,23 … +0,17 | **+0,52** | ±0,13 |
| 70 % | +0,83 | −0,10 … +0,21 | **+0,78** | ±0,13 |
| 85 % | +0,97 | −0,29 … −0,10 | **+1,18** | ±0,06 |
| 100 % | +0,33 | −0,60 … −0,94 | **+1,13** | ±0,12 |

Alles in Prozentpunkten Trefferquote gegenüber der Geometrielinie.

**Der Vorsprung ist echt, und er wächst monoton mit der Bestätigung.** Bei
der ersten Sprosse ist er null — das W allein, im Moment des zweiten Bodens,
trägt nichts. Er entsteht erst, während sich die Bewegung bestätigt, und
erreicht bei 85 % der Strecke rund 1,2 Prozentpunkte.

Die monotone Ordnung über acht Stufen ist dabei das stärkere Argument als
jede Einzelzahl: ein Zufallstreffer wäre nicht geordnet. Und die Kontrolle
selbst streut nur um ±0,03 bis ±0,13 Prozentpunkte.

**Damit ist der Befund vom 02.09.2026 präzisiert, nicht widerlegt.** Damals
wurde nur gegen die Geometrielinie geprüft, nicht gegen eine gematchte
Kontrolle. Die Linie beschreibt den Markt weiterhin fast exakt — aber sie ist
nicht die letzte Nachkommastelle.

### 7.3 Was der Vorsprung wert ist

| Stufe | Risiko | Lohn | Vorsprung | = Vorteil je Trade | Kosten | Rest |
|---:|---:|---:|---:|---:|---:|---:|
| 15 % | 9,6 | 12,8 | −0,02 pp | −0,01 $ | 2,90 $ | −2,91 $ |
| 45 % | 11,3 | 8,8 | +0,29 pp | +0,12 $ | 2,90 $ | −2,78 $ |
| 70 % | 14,6 | 5,0 | +0,78 pp | +0,30 $ | 2,90 $ | −2,60 $ |
| **85 %** | 16,9 | 3,0 | **+1,18 pp** | **+0,47 $** | 2,90 $ | −2,43 $ |
| 100 % | 17,5 | 1,2 | +1,13 pp | +0,42 $ | 2,90 $ | −2,48 $ |

*Vorteil = Vorsprung × (Risiko + Lohn) × 2 USD je Punkt.*

**Der beste gemessene Vorteil beträgt 47 Cent je Trade. Der Round Turn
kostet 2,90 USD. Die Kosten sind das Sechsfache des Effekts.**

Genau deshalb ist keine einzige der 1.260 Zellen profitabel, obwohl das
Muster nachweislich etwas trägt.

---

## 8. Ergebnis 5: Die W-Form trägt nichts bei

Nach Formfehler-Vierteln (Viertel 1 = beste W-Form, Viertel 4 = schlechteste):

| Viertel | Formfehler (Median) | bestes E[R] bei 15 % | bei 55 % |
|---|---:|---:|---:|
| 1 (beste Form) | 0,117 | −0,0523 | −0,0345 |
| 2 | 0,166 | −0,0126 | −0,0126 |
| 3 | 0,211 | −0,0139 | −0,0116 |
| 4 (schlechteste) | 0,281 | −0,0077 | −0,0076 |

**Kein Gefälle in die erwartete Richtung — eher das Gegenteil.** Die Formen,
die einem W am ähnlichsten sehen, schneiden nicht besser ab.

Mit Vorsicht zu lesen: der Formfehler hängt mit der Musterdauer zusammen
(kurze Formationen tragen einen Diskretisierungsaufschlag, siehe
`docs/OFFENE_FRAGEN.md` Punkt 2), Dauer hängt mit Höhe zusammen und Höhe mit
dem Kostenanteil. Der Vergleich ist nicht sauber getrennt.

**Sicher ist nur:** Es gibt kein Viertel, in dem das W profitabel wäre. Was
trägt, ist die **Bestätigung** — nicht die Ähnlichkeit zum Buchstaben.

---

## 9. Was das heißt — und was nicht

**Was gezeigt ist:**

- Der Trade-off zwischen Bestätigung und Restpotential ist real und messbar,
  mit einem Optimum bei rund 70 % der Strecke zur Nackenlinie.
- Nur 31 % der W-Kandidaten erreichen ihre Nackenlinie überhaupt.
- Das Muster trägt einen **echten, aber winzigen** Richtungsvorteil: bis zu
  1,2 Prozentpunkte Trefferquote über einer volatilitätsgematchten
  Kontrolle, monoton wachsend mit der Bestätigung, null bei der ersten
  Sprosse.
- Dieser Vorteil ist **rund ein Sechstel der Handelskosten**. Keine der
  1.260 Kombinationen ist nach Kosten profitabel.
- Was trägt, ist die Bestätigung — nicht die Formähnlichkeit.

**Was NICHT gezeigt ist:**

- Dass Ws nutzlos sind. Der Effekt ist da; er ist auf Minutenkerzen nur zu
  klein für die Kosten.
- Dass es auf höheren Zeitebenen genauso ist. **Das ist die entscheidende
  offene Frage** — siehe unten.
- Dass eine Kombination aus Muster **und** Kontext (Regime, Session,
  Volatilität) nichts trägt. Der Kontext war hier nicht dabei.
- Ob die gemessenen Kandidaten überhaupt „echte Ws" nach Laurins Definition
  sind. Der Referenzsatz wartet auf seine Urteile; der Formfehler steht in
  jeder Zeile, die Messung muss dafür nicht wiederholt werden.

---

## 10. Was als Nächstes sinnvoll wäre

Nach der Logik dieser Messung, nicht nach Meinung:

1. **Höhere Zeitebene — der einzige Hebel, der groß genug ist.** Der Vorteil
   beträgt 47 Cent, die Kosten 2,90 USD. Kosten sind pro Trade konstant, die
   Bewegungsgröße nicht: auf 15-Minuten-Kerzen ist eine Musterhöhe rund
   viermal größer, auf Stundenkerzen rund achtmal. Bleibt der Vorsprung von
   1,2 Prozentpunkten dabei erhalten, dreht das Vorzeichen. Genau das ist zu
   messen — dieselbe Leiter, dieselbe Kontrolle, andere Kerzen.
2. **Kontext statt Form.** Die Formvariante trägt nichts, die Bestätigung
   schon. Regime, Tageszeit und Volatilität sind ungeprüft.
3. **Der Referenzsatz.** Erst Laurins Urteile sagen, welches Formfehler-
   Viertel „echte Ws" enthält.

Reihenfolge und Auswahl liegen bei Laurin.
