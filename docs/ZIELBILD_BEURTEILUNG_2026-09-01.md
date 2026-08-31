# Beurteilung der Zieldefinition vom 01.09.2026

Laurins Zieldefinition (21 Punkte) gegen den tatsächlichen Projektstand. Er
hat ausdrücklich verlangt, ihm zu widersprechen, wo er falsch liegt
(Punkt 17). Das passiert in Abschnitt 3.

---

## 1. Was bereits trägt

| | Zustand |
|---|---|
| **Lookahead-Schutz** | strukturell, nicht nur sorgfältig. Vier Phasen je Ereignis, `verfuegbar_idx` als einzige zulässige Quelle, jeder Erkenner mit Abschneide-Test. Das ist die Grundlage, ohne die alles andere wertlos wäre — und sie steht. |
| **Ereignisdatenbank** | 2,59 Mio erkannte Zustände mit Kontext (Regime, Session, Trendlage, Abstand zu Marken), reproduzierbar, mit Herkunftseintrag. |
| **Eine Rechenlogik** | Live-Bot und Backtest rufen dieselben Funktionen. Kein Auseinanderlaufen möglich. |
| **Statistik-Disziplin** | Nulllinie je Richtung, überschneidungsfreie Stichproben, Wilson-Intervalle, Bonferroni, Cluster-Zählung. **Der Beweis, dass sie funktioniert:** der erste Grundratenbericht meldete neun signifikante Muster — die Disziplin hat den Fehler gefangen, bevor er zu einer Handelsentscheidung wurde. |
| **Split** | Training / Validation / OOS mit festen Grenzen, im Ladeweg erzwungen. |

Das entspricht Punkt 19 (Präzision zuerst) und ist der eigentliche Wert des
bisherigen Aufbaus.

## 2. Was fehlt — geordnet nach Wichtigkeit für dein Ziel

### 2.1 Die handelsrelevante Zahl wird gar nicht gemessen

`outcomes.py` misst MFE, MAE und Endergebnis je Horizont. Das beantwortet
„wie weit lief es". Es beantwortet **nicht** die Frage, aus der Profitabilität
folgt:

> **Wird Ziel +x erreicht, *bevor* Stop −y erreicht wird?**

Das ist eine andere Größe als MFE und MAE einzeln. Ein Ereignis mit MFE = 3R
und MAE = 2R kann bedeuten: erst 3R hoch, dann 2R runter (Gewinn) — oder erst
2R runter, dann 3R hoch (ausgestoppt, Verlust). Aus MFE/MAE allein lässt sich
das nicht rekonstruieren.

Diese Barrier-Messung ist die Voraussetzung für deine Punkte 4 und 5
(Entscheidungspunkt, Stop/Target aus den Daten). Ohne sie ist beides nicht
bewertbar. **Das ist die größte Lücke.**

### 2.2 Pfad-Zustände (dein Punkt 2 und 4)

Wir messen: „Ereignis erkannt → was passiert in den nächsten N Kerzen".

Du willst: „Ereignis → Zwischenzustand → Zwischenzustand → …", und für **jeden
Knoten** die Verteilung.

Das ist ein echter Unterschied und fehlt vollständig. Die unbedingte
Verteilung nach einem Sweep kann flach sein, während „Sweep + Reclaim +
Folgekerze schließt über der Marke" eine schiefe Verteilung hat. Genau das ist
die interessante Frage.

### 2.3 Konditionierung ist gebaut, aber nie ausgewertet

Die Regime-Achsen stehen in der Datenbank (98,7 % gefüllt). Die Auswertung
danach (`--nach regime`, `--nach session`) ist noch nie gelaufen. Das ist
billig nachzuholen und könnte den einzigen Effekt zeigen, den der
Gesamtschnitt verdeckt.

### 2.4 Multi-Timeframe

Der Plan sieht Erkennung auf 1m/5m/15m/1h vor. Gebaut ist nur 1m. Dein
Punkt 10 ist damit unbeantwortet — und der Kontext der höheren Ebene ist genau
die Sorte Bedingung, die eine flache Verteilung schief machen könnte.

### 2.5 Das Hypothesenbudget wird nicht durchgesetzt

`backtest/research_register.py` existiert und ist getestet. Die
Ereignis-Auswertung benutzt es **nicht**. Solange das so ist, ist jede
Aussage über Signifikanz nur innerhalb eines einzelnen Berichts korrekt, nicht
über die Summe aller Berichte, die wir je laufen lassen. Für dein Punkt 16
(selbstständige Weiterentwicklung) ist das die kritische Vorbedingung — dazu
unten mehr.

---

## 3. Wo ich dir widerspreche

### 3.1 Deine Zahlenerwartung ist um ein Vielfaches zu hoch

Du schreibst (Punkt 11):

> „Wenn ein Zustand in 10.000 Fällen untersucht wurde und ein bestimmtes
> Outcome in 7.200 Fällen eintritt…"

**72 % wäre kein Fund, sondern ein Alarmsignal.** Bei einem liquiden
Futures-Kontrakt auf Minutenbasis ist eine gerichtete Trefferquote von 72 %
über 10.000 Fälle praktisch ausgeschlossen. Wenn wir das je messen, ist die
erste Frage nicht „wie handeln wir das", sondern „wo ist der Fehler" — genau
wie gestern bei den neun scheinbar signifikanten Mustern.

Realistisch, wenn überhaupt etwas da ist: **52 bis 55 %.** Und das reicht —
aber nur, wenn das Verhältnis von Ziel zu Stop stimmt. Ein System mit 53 %
Trefferquote und 1:1 Ziel/Stop verliert nach Kosten. Ein System mit 45 %
Trefferquote und 1:2,5 gewinnt.

**Deshalb ist deine eigene Formulierung in Punkt 4 richtiger als die in
Punkt 11**: nicht die höchste Prozentzahl, sondern das wirtschaftliche
Verhältnis. Ich sage das so deutlich, weil du sonst auf eine Zahl wartest, die
nie kommt, und alles darunter für Versagen hältst.

### 3.2 Dein Punkt 3 ist wertvoller, als du selbst annimmst — aus einem Grund, den du nicht nennst

Du willst „nicht nur Richtung, sondern die gesamte Verteilung". Du begründest
das mit Vollständigkeit.

Der eigentliche Grund ist ein anderer, und er ist der wichtigste Satz in
diesem Dokument:

> **Richtung ist auf Minutenbasis kaum vorhersagbar. Volatilität und Pfadform
> sind es deutlich besser.**

Das ist ein robuster Befund der Finanzmarktforschung (Volatilitätsclusterung),
und unsere eigene Messung passt dazu: Trefferanteile sitzen alle auf der
Nulllinie, aber die MAE-Verteilungen unterscheiden sich zwischen den Mustern
sichtbar (Median 3,24 bis 3,76 R; p90 8,8 bis 10,7 R).

Das heißt konkret: Ein Zustand, der **keinen Richtungsvorteil** hat, kann
trotzdem handelbar sein, wenn er die *Form* der Verteilung ändert — etwa weil
danach die Gegenbewegung zuverlässig kleiner ausfällt. Dann kippt
`P(Ziel vor Stop)` bei asymmetrischem Ziel/Stop, ohne dass sich die
Trefferquote je Richtung ändert.

**Das ist die aussichtsreichste offene Frage des Projekts**, und wir können sie
mit den vorhandenen Daten beantworten, sobald 2.1 gebaut ist.

### 3.3 Punkt 16 in der jetzigen Form wäre eine Overfitting-Maschine

„Ein System, das sich kontrolliert weiterentwickelt" — das Wort *kontrolliert*
trägt hier die ganze Last, und es ist bisher nicht eingelöst.

Ein System, das eigene Hypothesen erzeugt und testet, ohne dass die
**Gesamtzahl aller je gestellten Fragen** mitgezählt wird, findet garantiert
Muster: bei α = 0,05 sind es 5 % aller getesteten Zufallsreihen. Bei einer
Pfad-Zustandsanalyse (2.2) mit 10 Knoten × 20 Bedingungen × 14 Mustern sind
das 2.800 Tests — davon 140 „signifikant" durch reinen Zufall.

Dein Vorsatz („nicht in blindes Data Mining ausarten", Punkt 6) reicht dafür
nicht. Es braucht einen **Zähler, der nicht umgangen werden kann**: jede
gestellte Frage wird registriert, bevor die Antwort gesehen wird, und die
Signifikanzschwelle richtet sich nach dem Gesamtstand. Das Register dafür
existiert — es muss verbindlich werden.

Dasselbe gilt für dein Punkt 20 („historisch gab es N vergleichbare Fälle"):
Bei genügend Merkmalen findet man zu *jeder* Lage ähnliche historische Lagen.
Der Merkmalsvektor muss **vorher** festgelegt sein, nicht gesucht werden.

---

## 4. Was ich für die richtige Reihenfolge halte

**Zuerst — Barrier-Outcomes (2.1).** Ohne sie ist kein Entscheidungspunkt
bewertbar und keine Stop-/Target-Frage beantwortbar. Für jedes Ereignis über
ein Raster von Ziel/Stop-Kombinationen messen: was wurde zuerst erreicht, nach
wie vielen Kerzen, und was folgt daraus nach Kosten. Das ist die Zahl, aus der
Profitabilität folgt.

**Parallel, weil billig — Regime- und Session-Auswertung (2.3).** Läuft mit dem
Vorhandenen und kann den Effekt zeigen, den der Gesamtschnitt verdeckt.

**Dann — Pfad-Zustände (2.2).** Ereignis-Verkettung mit Verteilung je Knoten,
plus die wirtschaftliche Bewertung jedes Knotens (dein Punkt 4). Erst hier
wird deine eigentliche Frage beantwortet.

**Verbindlich davor — das Hypothesenbudget (2.5).** Muss stehen, *bevor* die
Pfad-Analyse läuft, nicht danach. Sonst ist deren Ergebnis nicht bewertbar.

**Danach — Multi-Timeframe (2.4)**, wenn 1m nichts hergibt.

**Live-Demo (dein Punkt 13):** Da stimme ich dir zu, und zwar aus deinem
Grund. Der Orderweg ist gebaut und getestet, aber nie durchgehend live
gelaufen. Das sollte passieren, *bevor* die Forschung fertig ist — nicht um
Geld zu verdienen, sondern weil ein technischer Fehler in der Kette (Fill,
Stop, Buchung, Protokoll) nur im echten Betrieb auffällt. Ein Bot, der auf dem
Simulationskonto mit einer bewusst simplen Regel hundert schlechte Trades
macht, ist mehr wert als weitere Wochen Forschung ohne Durchstich.

---

## 5. Was das für deine Vision bedeutet

Deine Zieldefinition beschreibt ein System, das aus Marktzuständen
Wahrscheinlichkeitsverteilungen ableitet und daraus wirtschaftlich begründete
Entscheidungen trifft. Das ist erreichbar und methodisch richtig gedacht.

**Was du dabei akzeptieren musst:** Das System wird sehr wahrscheinlich zu dem
Ergebnis kommen, dass es die meiste Zeit **keine** Entscheidung gibt, die sich
lohnt. Ein ehrliches System sagt öfter „ich weiß es nicht" als „hier ist ein
Trade". Wenn am Ende drei Zustände übrigbleiben, die zusammen zwanzigmal im
Monat auftreten und einen kleinen positiven Erwartungswert nach Kosten haben,
ist das ein **Erfolg** — kein mageres Ergebnis.

Und es kann sein, dass gar nichts übrigbleibt. Auch das wäre ein Ergebnis:
sauber gemessen, statt teuer im Livebetrieb gelernt.
