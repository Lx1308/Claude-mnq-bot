# Alle Muster, vermessen — 02.09.2026

Nach dem Doppelboden (`W_MESSUNG_2026-09-02.md`) dieselbe Messung für die
übrigen Muster der Ereignisdatenbank. Es ist der weitreichendste Befund, den
das Projekt bisher hat.

---

## Die Messung

**14 Mustertypen × 2 Richtungen × 3 Stopweiten × 4 Zielweiten = 264 Zellen.**
Rund 1,9 Millionen Ereignisse, Trainingsdaten 2019–2023.

- Einstieg zur Eröffnung der Kerze nach `verfuegbar_idx`
- Stop und Ziel als ATR-Vielfache (0,5 / 1 / 2 ATR Stop; 0,5 / 1 / 2 / 3 ATR Ziel)
- Horizont 240 Kerzen, erste Berührung, bei Gleichstand zählt der Stop
- Kosten 1,45 Punkte Round Turn
- Mindestrisiko 2,0 Punkte

Als Nulllinie dient die **Geometrie**:

> P(Ziel zuerst) = Risiko ÷ (Risiko + Lohn)

Beim Doppelboden wurde diese Formel gegen zwei gespiegelte Kontrollreihen
geprüft (Volatilität exakt erhalten, Richtung gewürfelt) und traf deren
Trefferquoten ebenso genau wie die echten. Sie ist damit als Nullmodell
belegt.

---

## Das Ergebnis

| | |
|---|---:|
| Zellen mit E[R] > 0 **nach** Kosten | **0 von 264** |
| Zellen mit E[R] > 0 **vor** Kosten | 74 von 264 |
| Abweichung von der Geometrie, Median | **−0,47 %** |
| Abweichung, Maximum über alle 264 Zellen | **+0,75 %** |

Die Bruttowerte der 74 positiven Zellen liegen zwischen **+0,003 und
+0,014 R**. Die Kosten liegen bei 0,17 bis 0,29 R.

### Die Geometrie sagt alles voraus

| Stop / Ziel | Geometrie | gemessen (Bandbreite über alle Muster) |
|---|---:|---|
| 0,5 / 3 ATR | 14,3 % | 15,0 % |
| 1 / 3 ATR | 25,0 % | 25,6 – 25,7 % |
| 1 / 2 ATR | 33,3 % | 33,9 – 34,0 % |
| 2 / 3 ATR | 40,0 % | 40,1 – 40,6 % |
| 2 / 2 ATR | 50,0 % | 49,0 – 50,3 % |
| 2 / 1 ATR | 66,7 % | 66,1 – 67,0 % |
| 2 / 0,5 ATR | 80,0 % | 78,0 – 79,1 % |

Trefferquoten von 15 % bis 80 %, über 14 verschiedene Musterdefinitionen —
und **keine einzige weicht um mehr als 2 Prozentpunkte** von dem ab, was
allein aus den Abständen folgt.

### Je Muster, jeweils die beste Zelle im Raster

| Muster | Richtung | Ereignisse | über Geometrie | E[R] brutto | E[R] netto |
|---|---|---:|---:|---:|---:|
| niveau_test | long | 66.153 | +0,4 % | +0,010 | −0,172 |
| ausbruch_retest | long | 56.007 | +0,3 % | +0,005 | −0,175 |
| fehlausbruch | long | 71.840 | +0,4 % | +0,010 | −0,178 |
| ausbruch | long | 119.755 | +0,3 % | +0,006 | −0,184 |
| liquidity_sweep | long | 110.834 | +0,1 % | +0,003 | −0,186 |
| order_block | long | 62.075 | +0,5 % | +0,013 | −0,186 |
| displacement | long | 62.179 | +0,5 % | +0,014 | −0,186 |
| bos_bullish | long | 29.146 | +0,5 % | +0,012 | −0,191 |
| choch_bullish | long | 28.843 | +0,4 % | +0,009 | −0,201 |
| fair_value_gap | long | 174.692 | +0,4 % | +0,009 | −0,201 |
| equal_lows | long | 26.846 | +0,6 % | +0,014 | −0,263 |
| ausbruch_retest | short | 58.129 | −0,3 % | −0,005 | −0,185 |
| niveau_test | short | 68.250 | −0,3 % | −0,005 | −0,186 |
| ausbruch | short | 124.379 | −0,1 % | −0,002 | −0,194 |
| order_block | short | 64.184 | −0,1 % | −0,001 | −0,197 |
| displacement | short | 64.307 | −0,1 % | −0,001 | −0,197 |
| liquidity_sweep | short | 110.478 | −0,5 % | −0,008 | −0,199 |
| fehlausbruch | short | 67.200 | −0,9 % | −0,011 | −0,200 |
| choch_bearish | short | 27.289 | −0,5 % | −0,008 | −0,215 |
| fair_value_gap | short | 165.410 | −0,5 % | −0,009 | −0,220 |
| bos_bearish | short | 27.711 | −2,0 % | −0,025 | −0,228 |
| equal_highs | short | 28.622 | −1,0 % | −0,021 | −0,294 |

---

## Das einzige Signal in den Daten — und warum es nicht reicht

Die Tabelle ist sortiert, und die Sortierung ist kein Zufall: **alle Long-
Muster stehen über der Geometrielinie, alle Short-Muster darunter.**

Das ist keine Mustereigenschaft. Es ist der **Aufwärtstrend des MNQ** über den
Zeitraum — der Kontrakt lief von rund 7.000 auf über 30.000 Punkte. Diese
Drift schlägt auf jede Long-Position durch, egal welches Muster davor stand.

Größenordnung: **+0,01 R je Trade.** Die Kosten liegen bei **0,19 R.**

Damit ist auch die naheliegende Idee erledigt, einfach nur long zu handeln:
Der Vorteil ist real, aber neunzehnmal kleiner als die Reibung.

---

## Was daraus folgt

**Wiederkehrende Kursformationen auf MNQ-Minutenkerzen enthalten keine
Richtungsinformation, die über die Geometrie der eigenen Stop- und
Zielsetzung hinausgeht.**

Das ist jetzt gemessen, nicht vermutet — an 1,9 Millionen Ereignissen, über
14 unabhängig definierte Mustertypen, gegen eine als Nullmodell belegte
Vergleichslinie.

Was der Befund **nicht** sagt:

- Nichts über höhere Zeitebenen. Auf 1m sind die Kosten 15 bis 20 % des
  Risikos; auf 15m wären dieselben Strukturen ein Vielfaches größer und die
  Reibung entsprechend kleiner. Allerdings lag hier schon der **Brutto**wert
  bei null — höhere Zeitebenen helfen nur, wenn dort ein Effekt existiert,
  der auf 1m im Rauschen untergeht. Das ist eine offene Frage, keine Lösung.
- Nichts über **Volatilität und Pfadform**. Der Grundratenbericht vom
  31.08.2026 zeigte, dass sich die MAE-Verteilungen zwischen Mustern deutlich
  unterscheiden (Median 3,24 bis 3,76 R, p90 8,8 bis 10,7 R), während die
  Trefferquoten alle auf der Nulllinie sitzen. Ein Zustand ohne
  Richtungsvorteil kann handelbar sein, wenn er die *Form* der Verteilung
  ändert.
- Nichts über Information, die **nicht im Chart steht**: Orderfluss,
  Cross-Asset-Lage, Positionierung, Termine.

---

## Empfehlung

1. **Die Suche nach Richtungsvorteil in 1m-Kursformationen einstellen.** Sie
   ist beendet, und zwar mit einem Ergebnis.
2. **Die Kostenrechnung als Filter für alles Weitere nehmen.** Bei 1,45
   Punkten Round Turn und 2-ATR-Stops sind 15 bis 20 % des Risikos weg, bevor
   der Markt sich bewegt. Jede Idee muss diese Hürde vor allem anderen nehmen
   — auf höheren Zeitebenen ist sie deutlich niedriger.
3. **Als Nächstes Volatilität und Pfadform statt Richtung.** Dort hat die
   bisherige Messung als einzige Stelle Unterschiede zwischen Mustern gezeigt.
4. **Der Live-Demo-Durchstich bleibt davon unberührt** und sollte laufen. Er
   testet die technische Kette, nicht die Strategie — dafür reicht eine
   bewusst simple Regel.

---

## Reproduktion

- Skript: `scratchpad/alle_muster.py` (Indexprobe gegen die Ereignisdatenbank
  läuft vor jeder Messung; ohne 100 % Übereinstimmung bricht es ab)
- Daten: `data/eventdb.sqlite3`, Block `train`, `verfuegbar_ts <= 2023-12-31`
- Kerzen: 2.576.079 Minutenkerzen, 2019-05-06 bis 2026-09-01
- Ergebnis: `scratchpad/alle_muster.pkl`
