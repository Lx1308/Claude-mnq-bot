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

## 1. Was ist das zweite Tief? — offen seit 03.09.2026, **blockiert alles**

**Blockiert:** den Referenzsatz, die Kalibrierung, jede weitere Messung.

Am ersten W (31.08.2026) liegen zwei Kandidaten für den zweiten Boden:

| | Zeit | Kurs | |
|---|---|---|---|
| **A** | 02:42 | 29.286,50 | das **tiefste** Tief |
| **B** | 02:53 | 29.291,75 | 5,25 Punkte **höher** — das, was Laurin markiert |

Dazwischen: nach A kommen zwei Aufwärtskerzen (02:42, 02:43), der Kurs steigt
40 Punkte auf 29.326 — und fällt bis 02:53 **komplett zurück**. Erst ab 02:54
läuft die Bewegung wirklich.

**Der Erkenner kann B strukturell nicht wählen.** `_kandidaten_zum_tief`
führt ein laufendes Minimum und meldet je Minimum höchstens einen Kandidaten;
ein späteres, *höheres* Tief aktualisiert das Minimum nicht und wird nie zum
zweiten Boden. Das ist keine Schwelle, sondern die Konstruktion.

Damit feuert der Erkenner bei Laurins eigenem W auf A und steigt 02:45 ein —
in einen Trade, der 40 Punkte ins Plus lief und bei null wieder herauskam.

**Meine Vermutung, Laurin vorgelegt und noch nicht bestätigt:** Das zweite
Tief zählt erst, wenn danach ein **höheres Tief** entsteht. A war nur der
erste Anlauf; weil der Kurs komplett zurückkam, war A nicht die Umkehr. B
liegt über A, und das bestätigt, dass die untere Linie hält.

Wäre das die Regel, verschöbe sich der Einstieg von 02:45 auf 02:54 — und
der Fehltrade fiele weg.

**Solange das offen ist, wird nichts gemessen und kein Referenzsatz gebaut.**
Ein Erkenner, der den zweiten Boden anders bestimmt als Laurin, misst wieder
das falsche Objekt — zum fünften Mal.

---

## 2. Der Formfehler ordnet Laurins eigenes W nicht nach oben ein

**Blockiert:** die Formfehler-Schranke aus AP3.

Sein erstes W (31.08.) hat einen Formfehler von **0,207**. Der Median über
alle 150 Kandidaten des Referenzsatzes lag bei 0,189 — sein Beispiel liegt
also in der **schlechteren Hälfte**.

Die Gegenprobe aus AP2b („Laurins Ws müssen die kleinsten Formfehler haben")
ist damit auch am ersten Beispiel nicht bestanden. Zusammen mit dem Befund,
dass die Formfehler-Viertel in der Messung vom 03.09. **kein Gefälle** in die
erwartete Richtung zeigen, spricht das dafür, dass die Schablone die falsche
Größe misst.

Die Schablone wurde weiterhin **nicht** angepasst.

---

## 3. Der Formfehler benachteiligt kurze Muster — offen seit 03.09.2026

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

## 4. Der Formfehler wählt bei deinem W den falschen Kandidaten — offen seit 03.09.2026

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

## 5. Der Bildschnitt — ERLEDIGT am 03.09.2026

Die Beurteilungsbilder endeten am **zweiten Tief**. Damit fehlte der zweite
Anstieg, und ein W ist Tief – Hoch – Tief – **hoch**. Laurin nach vierzig
Bildern: *„keins war annähernd ein W."* Alle vierzig Urteile lauteten „nein" —
die richtige Antwort auf das falsche Bild.

Die Bilder reichen jetzt bis zur **Bestätigung**, dem frühesten handelbaren
Zeitpunkt. Das ist kein Nachlauf: die Bestätigung gehört zum Muster und ist
zum Entscheidungszeitpunkt bekannt. Verdeckt bleibt nur, was danach passiert.

Die vierzig Urteile sind gelöscht.

---

## Entschieden

**`max_unter` bleibt bei 0,15** (03.09.2026). Der Konflikt bestand nur gegen
das zweite Beispiel vom 02.09., und Laurin hat es ausdrücklich verworfen
(*„verwirf das zweite W mal komplett"*). Sein **erstes** W vom 31.08. hat
einen Versatz von 5,75 Punkten auf 76,50 Punkte Höhe — **7,5 %**, weit
innerhalb der Schwelle. Der Test
`test_konflikt_max_unter_verwirft_laurins_w2` bleibt bestehen, weil er die
Mechanik korrekt beschreibt; er ist kein Blocker mehr.

**Mindestens zwei Aufwärtskerzen nach dem zweiten Tief** (03.09.2026).
Laurins Regel, wörtlich: *„frühestens ab der zweiten Kerze nach oben, da man
da erst sieht, dass die erste erst ca. auf selber Höhe aufgehört hat und der
Chart wieder nach oben geht."* Eingebaut als
`patterns.doppelboden.min_aufwaerts_kerzen`. Sie allein reicht allerdings
nicht — siehe Punkt 1.

**Die große Lesart des ersten W** (03.09.2026). Nicht der Buckel um 01:30 mit
dem Rücksetzer um 01:50, sondern: erstes Tief 01:12, mittlere Spitze 02:11
(die Nackenlinie), zweites Tief danach. Alles vor der mittleren Spitze gehört
zum linken Schenkel.
