# Was ist ein W? — Stand 03.09.2026, Definition noch nicht freigegeben

Diese Datei hält fest, wo die Definition des Doppelbodens gerade steht, was
Laurin an drei Anläufen bemängelt hat, und welche Frage offen ist. Sie ist
bewusst als Gesprächsgrundlage geschrieben.

**Wichtig: Es wurde noch nichts auf der aktuellen Definition gemessen.** Der
Fehler dieser Woche war, vor der Definition zu messen — dreimal.

---

## 1. Warum das überhaupt ein Problem ist

Ein Mensch erkennt ein W in einer halben Sekunde. Ein Erkenner braucht Regeln,
die auf 2,5 Millionen Kerzen dasselbe treffen. Zwischen beidem klafft mehr, als
es aussieht.

Die Messungen dieser Woche haben gezeigt: **wenn die Definition daneben liegt,
misst man sauber das Falsche.** Alle Zahlen stimmen, alle Tests sind grün, das
Ergebnis ist wertlos.

---

## 2. Drei verworfene Anläufe

### 2.1 `common/muster_serie.py` — Zappler statt Muster

Verlangt zwei bestätigte Swingtiefs mit Stärke 3, höchstens 120 Kerzen
auseinander, Zwischenhoch mindestens 1 ATR über ihrem Mittel.

**Findet:** 49.207 Stück, Median **12,2 Punkte** hoch und **8 Kerzen** lang.

**Problem:** Das sind Minutenzappler, die niemand handelt. Laurins Beispiel ist
sechsmal höher und dreizehnmal länger. Ursache: Swing-Stärke 3 findet
Mikro-Tiefs, und weil nur *aufeinanderfolgende* Tiefs gepaart werden, kommt das
Paar der beiden großen Tiefs nie zur Prüfung.

**Zweiter Fehler:** Beide Tiefs müssen bestätigte Swings sein. Bei Stärke 45
heißt das, das zweite Tief ist erst 45 Kerzen später bekannt — der Einstieg
landete im Median bei **69 % der Strecke** zur Nackenlinie, mit 3,2 Punkten
Rest gegen 11,7 Punkte Risiko. Ein Trade, den niemand eingehen würde.

### 2.2 `common/muster_handelbar.py` — kein Formtest

Repariert die Bestätigungsverzögerung: nur das *erste* Tief braucht
Bestätigung, das zweite ist ein Rücklauf und sofort sichtbar. Einstieg dadurch
bei **21 % der Höhe** statt 69 %.

**Problem:** Es prüft die Form überhaupt nicht. Verlangt wird nur: bestätigtes
Tief, irgendwann danach ein Hoch, Rücklauf aufs Tiefniveau. Zwischen den Tiefs
darf alles passieren — eine 300 Kerzen lange Seitwärtsphase mit zufälligem Hoch
zählt genauso wie ein sauberes W.

Laurins Urteil über die Beispiele: **„das sind alle keine Ws."**

### 2.3 Formtest auf Rohkursen — hätte sein eigenes W verworfen

Naheliegender nächster Schritt: verlangen, dass jeder Schenkel sauber
durchläuft, gemessen am größten Rückschlag.

**Problem:** Laurins erstes Beispiel steigt von 29290 auf 29330, fällt auf
29300 zurück, läuft seitwärts und geht erst dann auf 29360. Roh gerechnet ist
das ein Rückschlag von **75 % des Aufschenkels**. Jeder strenge Formtest auf
Rohkursen hätte sein W abgelehnt.

---

## 3. Laurins eigene Definition

> „Es heißt W, weil wenn man eine Durchschnittslinie durchlegen würde, es
> aussieht wie ein W."

Das ist der Schlüssel: **der Formtest gehört auf die geglättete Linie, nicht
auf die Rohkurse.** Geglättet verschwindet das Gezappel und der Anstieg bleibt
sauber.

---

## 4. Seine beiden Beispiele, nachgemessen

| | W 1 (01.09.) | W 2 (02.09., 09:38–09:56 NY) |
|---|---:|---:|
| Tief 1 | ~29290 | 29.036,75 |
| Hoch | ~29360 | 29.119,00 |
| Tief 2 | ~29290 | 29.017,25 |
| Höhe | ~70 Pkt | **101,75 Pkt** |
| Dauer | ~105 Kerzen | **18 Kerzen** |
| Tiefs auseinander | ~0 | **19,50 Pkt = 19 % der Höhe** |
| zweites Tief | gleich | **TIEFER als das erste** |
| Schenkelverhältnis | 2,15 | 2,60 |

W 2 ist exakt vermessen (Livedaten aus der NinjaTrader-Anbindung), W 1 aus dem
Screenshot abgeschätzt.

**Drei Konsequenzen:**

1. **Das erste Tief darf abgeräumt werden.** Beide Vorgänger brachen ab, sobald
   der Kurs unter das erste Tief fiel — sie hätten W 2 verworfen. Dabei ist
   genau das die starke Variante: erst die Stops holen, dann drehen.
2. **Die Dauer reicht von ~15 bis ~200 Kerzen.** Eine feste Swing-Stärke kann
   das nicht abdecken; gefiltert wird über die **Höhe**, nicht über die Stärke.
3. **Die Schenkel dürfen deutlich ungleich sein** — bei beiden Beispielen ist
   einer mehr als doppelt so lang wie der andere.

---

## 5. Der aktuelle Stand: `common/muster_w.py` + `common/w_schablone.py`

**Nicht freigegeben. Nichts darauf gemessen.** Stand 03.09.2026.

### 5.1 Die Form ist jetzt EINE Kennzahl

Bis zum 02.09. prüften drei getrennte Regeln die Form: höchstens 25 % Rückschlag
je Schenkel, Gipfel zwischen 10 % und 90 % der Dauer, kein Schenkel mehr als
dreimal so lang wie der andere. Drei Schwellen, die sich gegenseitig ins Gehege
kommen — eine Form kann jede einzeln bestehen und trotzdem nicht wie ein W
aussehen.

Sie sind ersetzt durch den **Formfehler** (`common/w_schablone.py`), nach
Laurins eigenem Kriterium: *„am einfachsten ist, wenn man ein W drüberlegt und
das ca. passt."*

1. Segment von Tief 1 bis Tief 2 glätten (Fenster = 12 % der Dauer)
2. Zeit und Preis je auf [0,1] strecken (Min-Max)
3. eine ideale W-Schablone aus fünf Ankerpunkten darüberlegen —
   `(0,0) · (p/2, ½) · (p, 1) · ((1+p)/2, ½) · (1,0)`
4. die Gipfellage `p` von 0,10 bis 0,90 durchschieben
5. die kleinste RMS-Abweichung ist der Formfehler, das zugehörige `p` die
   Gipfellage

Zur Einordnung: perfektes W ≈ 0, Plateau 0,35, Rauschen 0,42, Laurins W 0,085.

**Die Plateau-Frage aus 6.2 löst sich damit von selbst.** Zehn flache Kerzen in
einem 15-Kerzen-Fenster können sich der Schablone nicht anschmiegen, egal wo
deren Gipfel liegt — die Schablone steigt und fällt durchgehend, ein Plateau tut
weder das eine noch das andere. Es braucht keine Plateau-Regel.

### 5.2 Das zweite Tief wird nicht mehr beim ersten Treffer genommen

Die Vorgängerfassung brach bei der ersten Kerze ab, die ins Tiefband
zurückkehrte (6.1). Jetzt läuft die Schleife weiter, bis die Umkehr
**bestätigt** ist: der Schlusskurs steigt um `bestaetigung_anteil` der
Musterhöhe über das laufende Minimum. Als zweites Tief gilt das **Minimum**
dieses Abschnitts.

Und es wird nicht mehr abgebrochen: macht der Kurs danach ein tieferes Minimum
und dreht wieder, entsteht ein **zweiter Kandidat** zum selben ersten Tief.
Welcher gilt, entscheidet nicht die Reihenfolge, sondern die Form.

Bei Laurins W entstehen so zwei Kandidaten — der zu frühe von 13:50 und der
richtige von 13:56. Der Bestätigungszeitpunkt ist der früheste zulässige
Einstieg; er liegt jetzt bei 13:57 statt 13:51.

Begrenzt wird das durch den **Bruch der Nackenlinie**: schließt der Kurs über
dem Hoch, das zu Beginn des Rücklaufs stand, ist die Formation abgeschlossen
und zu diesem ersten Tief entsteht nichts mehr. Diese Prüfung war bis zum
03.09.2026 toter Code — sie verglich gegen das *laufende* Hoch, und ein
Schlusskurs liegt nie über dem eigenen Hoch.

### 5.3 Die Schwellen

| Prüfung | Regel | Herkunft |
|---|---|---|
| Form | Formfehler gegen die W-Schablone | Laurins Definition |
| Zweites Tief | bis 15 % der Höhe **tiefer**, bis 15 % **höher** | Laurin, 03.09. — **siehe Konflikt unten** |
| Bestätigung | Schluss ≥ 15 % der Höhe über dem laufenden Minimum | bewusst klein: erzeugt mehr Kandidaten |
| Mindestdauer | ≥ 10 Kerzen zwischen den Tiefs | Laurin, 03.09. |
| Mindesthöhe | ≥ 2 ATR | schließt Rauschen aus |
| Linker Arm | Abverkauf vor dem ersten Tief ≥ 0,5 Musterhöhen | Umkehrmuster braucht etwas zum Umkehren |

Alle Toleranzen sind **Anteile der Musterhöhe**. Sie stehen in `config.yaml`
unter `patterns.doppelboden`, nicht mehr im Code.

**Eine Schwelle fehlt bewusst:** die Schranke für den Formfehler. Sie kommt aus
der Kalibrierung gegen den Referenzsatz, nicht aus einer Schätzung. Solange sie
fehlt, gibt der Erkenner den Wert nur aus und filtert nicht.

---

## 6. Was nicht stimmt — Stand 03.09.2026

Alle drei Punkte stehen ausführlich in `docs/OFFENE_FRAGEN.md` und warten auf
Laurins Entscheidung.

### 6.1 `max_unter = 0,15` verwirft Laurins eigenes W

Sein zweites Tief liegt 19,50 Punkte unter dem ersten — **23,7 %** der zu dem
Zeitpunkt bekannten Spanne. Mit der Schwelle von 15 % bricht der Erkenner ab,
bevor der Kandidat entsteht. Festgehalten in
`tests/test_muster_w.py::test_konflikt_max_unter_verwirft_laurins_w2`.

### 6.2 Der Formfehler benachteiligt kurze Muster

Ein **perfektes** W bekommt 0,082 bei 8 Stützstellen und 0,001 bei 400 — allein,
weil die Min-Max-Normierung eine zwischen zwei Kerzen liegende Spitze
abschneidet und die Linie dadurch überall verzieht. Laurins echtes W liegt bei
0,085. Bei kurzen Formationen ist der Rauschboden also so groß wie das Signal.

### 6.3 Der Formfehler wählt bei Laurins W den falschen Kandidaten

| zweites Tief | Höhe | Formfehler |
|---|---:|---:|
| 13:50 (zu früh, abgeschnitten) | 82,25 | **0,040** |
| 13:56 (Laurins) | 101,75 | 0,085 |

Der Erkenner findet beide — das war das Ziel und ist erreicht. Aber die Form
bevorzugt den abgeschnittenen, und zwar aus dem Grund in 6.2. Die Gegenprobe
aus AP2b ist damit **nicht bestanden**. Die Schablone wurde bewusst *nicht*
angepasst.

---

## 7. Der Referenzsatz — damit das Fragen aufhört

`werkzeuge/w_referenz.py` und `werkzeuge/w_referenz_server.py`.

Bisher war jede Schwelle aus **zwei** Beispielen kalibriert, und jede Prüfung
hieß: Laurin fragen. Vier Anläufe sind so gescheitert.

Stattdessen jetzt: 150 Kandidaten aus der ganzen Historie (gleichmäßig über die
Monate, nicht über die Gesamtmenge — sonst dominierten die volatilen Jahre) und
100 Zufallsfenster mit **derselben Längenverteilung**, die keine Kandidaten
sind. Ohne diese Negativbeispiele wäre die Frage „wie viel Rauschen lässt diese
Schwelle durch" gar nicht stellbar.

Alle Fenster werden identisch gerendert und **gemischt** gezeigt:

- **kein Nachlauf** — sonst würden Gewinner beschriftet statt Ws
- **kein Datum, kein Kursniveau** — sonst ließe sich der Chart nachschlagen
- **die drei Marker nach derselben rein geometrischen Regel für beide Klassen**
  (höchstes Hoch, tiefstes Tief davor, tiefstes Tief danach) — nicht aus den
  Feldern des Erkenners, sonst wären die Klassen am Bild unterscheidbar. Bei
  86 % der Kandidaten liefert diese Regel exakt dieselben drei Punkte.
- Vorlauf **80 % der Formationsdauer** (15 bis 60 Kerzen) statt fest 40: bei
  einer 10-Kerzen-Formation hätten feste 40 Kerzen vier Fünftel des Bildes
  gefüllt

Die Urteile landen in `data/w_referenz.sqlite3`, Tabelle `urteile`, mit dem
Spalten `musterart` von Anfang an — dasselbe Werkzeug gilt später für
M-Formation, Keil und Flagge.

Die Tabelle `urteile` kennt die **Klasse nicht**; sie hängt am Zeitfenster.
Auch die Seite bekommt `art` nicht ausgeliefert.

---

## 8. Die Reihenfolge, die gilt

1. Erkenner findet Kandidaten ✔
2. **Laurin beurteilt den Referenzsatz** ← hier stehen wir
3. Schwellen gegen die Urteile kalibrieren, Konfliktfälle einzeln vorlegen
4. **Erst wenn Laurin die Definition freigibt, wird gemessen**

Die Messmaschine selbst ist fertig und geprüft: erste Berührung statt Zeit zum
Extremum, Prozent der Musterhöhe statt Punkte, gespiegelte Kontrollreihe
(Volatilität erhalten, Richtung gewürfelt), und die Geometrielinie
`P(Ziel zuerst) = Risiko ÷ (Risiko + Lohn)` als Lügendetektor.

Siehe `docs/MUSTERBEFUND_2026-09-02.md` und `docs/W_MESSUNG_2026-09-02.md`.
