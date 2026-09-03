# Offene Fragen — Entscheidungen, die bei Laurin liegen

Diese Datei sammelt Punkte, die ich beim Arbeiten gefunden habe und **nicht
selbst entscheiden darf**. Sie ist kein Ideenspeicher: hier steht nur, was den
Fortschritt an einer Stelle blockiert oder was ich sonst stillschweigend
festlegen würde.

Nach der Eskalationsregel vom 03.09.2026 gehören hierher:

- der Arbeitspunkt von Schwellen
- ob ein von Laurin verworfener Kandidat trotzdem im Erkenner bleibt
- die Übertragung einer Methode auf weitere Muster
- alles, was Entry-, Stop- oder Zielregeln betrifft

Erledigte Punkte wandern nach unten unter „Entschieden" — mit dem Datum und
der Entscheidung, damit die Begründung nicht verloren geht.

---

## 1. `max_unter: 0.15` verwirft Laurins eigenes W — offen seit 03.09.2026

**Blockiert:** nichts. Der Erkenner läuft, der Widerspruch ist festgehalten.

Du hast am 03.09.2026 vorgegeben: `max_unter` von 0,30 auf **0,15**. Damit
darf das zweite Tief höchstens 15 % der Musterhöhe unter dem ersten liegen.

Dein W vom 02.09.2026 verletzt das:

| | |
|---|---|
| erstes Tief | 29.036,75 (13:38 UTC / 09:38 ET) |
| Hoch | 29.119,00 (13:43) |
| zweites Tief | 29.017,25 (13:56) |
| Unterschreitung | 19,50 Punkte |
| bezogen auf die damals bekannte Spanne (82,25) | **23,7 %** |
| bezogen auf die volle Musterhöhe (101,75) | 19,2 % |

Mit `max_unter = 0.15` bricht der Erkenner die Suche ab, sobald der Kurs unter
29.024,4 fällt — das ist die Kerze 13:55. Der Kandidat mit dem richtigen Tief
um 13:56 **entsteht gar nicht**. Nachgeprüft und festgenagelt in
`tests/test_muster_w.py::test_konflikt_max_unter_verwirft_laurins_w2`.

Es ist genau die Variante, die du selbst als die starke beschrieben hast: das
erste Tief wird abgeräumt, und *danach* dreht es.

**Was zur Wahl steht**

1. `max_unter` zurück auf 0,30 (dann existiert dein W wieder als Kandidat)
2. bei 0,15 bleiben und dein W als Ausnahme akzeptieren
3. offen lassen bis AP3 — dann sagt der Referenzsatz, wie viele der von dir
   bejahten Formen ein zweites Tief unter 15 % haben

**Mein Vorschlag:** 3, und bis dahin 0,30 als Arbeitswert. Ein Wert, der das
einzige bestätigte Beispiel verwirft, kann nicht die Voreinstellung sein,
solange nichts Besseres gemessen ist.

**Deine Entscheidung.**

---

## 2. Der Formfehler benachteiligt kurze Muster — offen seit 03.09.2026

**Blockiert:** die Schwelle aus AP3 wäre sonst dauerabhängig, ohne dass es
jemandem auffällt.

Der Formfehler wird berechnet, indem die geglättete Linie per **Min-Max** auf
[0,1] gestreckt und gegen die Schablone gelegt wird — so ist es in AP2b
vorgegeben. Das hat einen Nebeneffekt, den ich gemessen habe:

Ein **perfektes** W bekommt nicht den Fehler null, wenn seine Spitze zwischen
zwei Kerzen fällt. Die Normierung setzt das *beobachtete* Maximum auf 1,0;
liegt es unter der wahren Spitze, wird die ganze Linie mit hochgezogen und
weicht überall ab.

| Stützstellen | Formfehler eines perfekten W |
|---|---|
| 8 | 0,082 |
| 12 | 0,052 |
| 20 | 0,030 |
| 100 | 0,006 |
| 400 | 0,001 |

Zum Vergleich: dein echtes W vom 02.09. kommt auf **0,085**. Bei kurzen
Formationen liegt der Rauschboden also in derselben Größenordnung wie das
Signal. Eine einzige Schranke über alle Dauern hinweg würde kurze Muster
systematisch verwerfen — und dein zweites Beispiel ist mit 18 Kerzen genau so
eines.

**Was zur Wahl steht**

1. so lassen und in AP3 die Schranke **je Größenkategorie** kalibrieren
2. die Normierung ändern: Schablone per kleinster Quadrate affin an die Linie
   anpassen statt sie an zwei Extremwerten aufzuhängen. Das ist skalen- und
   versatzfrei per Konstruktion und macht den Aufschlag verschwinden
3. so lassen und den Aufschlag ignorieren

**Mein Vorschlag:** 2. Es ist eine Änderung an einer Stelle
(`common/w_schablone.py`), sie ändert nichts an der Schablone selbst, und sie
beseitigt eine Verzerrung, statt sie später mit einer zweiten Schwelle zu
kompensieren.

Ich habe es **nicht** gemacht, weil AP2b die Min-Max-Normierung ausdrücklich
vorschreibt und weil „melden, nicht anpassen" die Regel war. Festgehalten in
`tests/test_w_schablone.py::test_kurze_muster_tragen_einen_diskretisierungsaufschlag`.

---

## 3. Der Formfehler wählt bei deinem W den falschen Kandidaten — offen seit 03.09.2026

**Blockiert:** die Gegenprobe aus AP2b ist damit nicht bestanden.

AP2b verlangte: deine beiden Ws müssen die kleinsten Formfehler unter allen
gezeigten Kandidaten haben. Gemessen an deinem W vom 02.09. (erstes Tief
13:38):

| zweites Tief | Höhe | Formfehler |
|---|---|---|
| 13:50 bei 29.041,75 (zu früh) | 82,25 | **0,040** |
| 13:56 bei 29.017,25 (deins) | 101,75 | 0,085 |

Der Erkenner findet jetzt **beide** — das war das Ziel von AP2 und ist
erreicht. Aber der Formfehler bevorzugt den abgeschnittenen. Der Grund ist
Punkt 2: der kürzere Ausschnitt hat weniger Stützstellen und schmiegt sich
allein deshalb besser an.

Ich habe die Schablone **nicht** angepasst — genau davor warnt AP2b.

**Was zur Wahl steht**

1. Punkt 2 lösen (affine Anpassung); dann sind die beiden vergleichbar und
   die Rangfolge kann sich umdrehen
2. zusätzlich zur Form ein zweites Merkmal heranziehen, etwa die Tiefe des
   zweiten Tiefs oder die Musterhöhe — dann wäre es aber wieder keine *eine*
   Kennzahl
3. akzeptieren, dass beide Kandidaten stehenbleiben, und die Entscheidung in
   AP3 aus dem Referenzsatz holen

**Mein Vorschlag:** erst 1, dann neu messen. Wenn es dann immer noch nicht
stimmt, ist die Schablone falsch — und *das* wäre der Befund.

---

## 4. Bilder ohne Nachlauf — bestätigen, bevor du 250 Stück beurteilst

**Blockiert:** AP3 vollständig.

Der Referenzsatz zeigt dir jedes Fenster **ohne** Datum, **ohne** Kursniveau
und **ohne** das, was danach passiert ist. Der Grund steht in
`werkzeuge/w_referenz.py`: sähest du den Ausgang, würdest du Gewinner
beschriften statt Ws, und der Erkenner lernte den Ausgang statt der Form.

Das heißt aber auch: du beurteilst mit weniger Information, als du beim
Traden hättest. Wenn dir das für die Frage „ist das ein W" zu wenig ist, sag
es, bevor du dich durch 250 Bilder klickst — dann ändere ich das Rendering,
nicht die Urteile.

Eine **Abweichung** von der Vorgabe steckt schon drin: der Vorlauf ist nicht
fest 40 Kerzen, sondern 80 % der Formationsdauer (mindestens 15, höchstens
60). Bei einer 10-Kerzen-Formation hätten feste 40 Kerzen vier Fünftel des
Bildes gefüllt, und du hättest den Vorlauf beurteilt statt die Form. Beide
Klassen bekommen dieselbe Regel.

---

## Entschieden

*(noch nichts)*
