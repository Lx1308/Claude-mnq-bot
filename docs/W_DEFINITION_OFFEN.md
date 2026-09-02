# Was ist ein W? — Stand 02.09.2026, ungeklärt

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

## 5. Der aktuelle Stand: `common/muster_w.py`

**Nicht freigegeben. Nichts darauf gemessen.**

| Prüfung | Regel | Herkunft |
|---|---|---|
| Saubere Schenkel | auf der Durchschnittslinie (Fenster = 12 % der Dauer) höchstens 25 % Rückschlag je Schenkel | Laurins Definition |
| Zweites Tief | bis 30 % der Höhe **tiefer**, bis 15 % **höher** | W 2: 19 % tiefer |
| Ausgewogene Schenkel | keiner mehr als 3× so lang wie der andere | W 1: 2,15, W 2: 2,60 |
| Mindestdauer | ≥ 12 Kerzen zwischen den Tiefs | Praxisliteratur: darunter Konsolidierung |
| Mindesthöhe | ≥ 2 ATR | schließt Rauschen aus |
| Linker Arm | Abverkauf vor dem ersten Tief ≥ 0,5 Musterhöhen | Umkehrmuster braucht etwas zum Umkehren |
| Gipfel mittig | Hoch der Durchschnittslinie zwischen 10 % und 90 % der Formation | sonst Flanke, kein W |

Alle Toleranzen sind **Anteile der Musterhöhe**, keine Punktzahlen — damit
gilt dieselbe Regel für ein 20-Punkte-W und ein 140-Punkte-W.

**Findet:** 48 W-Formen in vier Handelstagen (30.08.–02.09.), also rund zwölf
am Tag. Höhen 18–138 Punkte, Dauern 12–94 Kerzen.

---

## 6. Was noch nicht stimmt

### 6.1 Der Einstieg feuert zu früh

Bei Laurins eigenem W nimmt der Erkenner als zweites Tief die Kerze um **09:50
bei 29.041,75** — nicht die 09:56 bei 29.017,25. Er reagiert auf die erste
Rückkehr in die Toleranz; der echte Boden kam sechs Kerzen später und **24
Punkte tiefer**.

Das ist kein Rechenfehler, sondern das Kernproblem jedes Live-Erkenners: *um
09:50 weiß niemand, dass 09:56 tiefer wird.* Dagegen ist die
Grüne-Kerzen-Regel gedacht — mit einer Kerze ist sie zu locker.

**Offene Frage:** zwei oder drei grüne Kerzen? Das entschärft den Fall, kostet
aber Strecke — bei den alten Messungen lag der Einstieg nach drei grünen
Kerzen im Median schon bei 88 % der Formationshöhe.

### 6.2 Seitwärtsrauschen wird vermutlich mitgenommen

Laurin hat am 02.09. eine enge Seitwärtsphase markiert (rund 28 Punkte Spanne,
~40 Kerzen) und dazu gesagt: **„das ist zB nur Rauschen, sowas ist niemals ein
W."**

Ob der aktuelle Erkenner dort feuert, ist **nicht geprüft**. Die Mindesthöhe
von 2 ATR könnte reichen — muss sie aber nicht, wenn die ATR in einer ruhigen
Phase klein ist.

**Kandidaten für das fehlende Kriterium:**

- **Anzahl der Richtungswechsel.** Ein W hat auf der Durchschnittslinie genau
  drei Wendepunkte. Rauschen oszilliert häufiger. Der jetzige Test misst nur
  den Rückschlag je Schenkel, nicht die Zahl der Schwünge — das ist
  vermutlich die wichtigste Lücke.
- **Schenkelhöhe gegen Kerzengröße.** In einer Seitwärtsphase ist eine einzelne
  Kerze fast so groß wie ein ganzer Schenkel. Bei einem echten W ist der
  Schenkel ein Vielfaches davon.
- **Höhe gegen die Spanne davor.** Rauschen ist typischerweise eine
  Kompression *nach* einer Bewegung; das W sollte im Verhältnis zur
  vorherigen Spanne nicht winzig sein.

### 6.3 Zwölf am Tag — vermutlich zu viele

Wenn Laurin davon zwei oder drei handeln würde, ist die Definition noch zu
weit, und es fehlt das Kriterium, das die anderen neun aussortiert.

---

## 7. Die Reihenfolge, die diesmal gilt

1. Erkenner findet Kandidaten
2. **Laurin beurteilt sie: ja oder nein, und bei nein die Begründung**
3. Kriterium nachziehen, zurück zu 1
4. **Erst wenn die Definition steht, wird gemessen**

Die Messmaschine selbst ist fertig und geprüft: erste Berührung statt Zeit zum
Extremum, Prozent der Musterhöhe statt Punkte, gespiegelte Kontrollreihe
(Volatilität erhalten, Richtung gewürfelt), und die Geometrielinie
`P(Ziel zuerst) = Risiko ÷ (Risiko + Ziel)` als Lügendetektor.

Siehe `docs/MUSTERBEFUND_2026-09-02.md` und `docs/W_MESSUNG_2026-09-02.md`.
