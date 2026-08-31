# Übergabe an Laurin — Nacht vom 30. auf den 31.08.2026

Du hast gesagt: „mache jetzt komplett weiter und sag mir morgen was ich tun
muss dass alles funktioniert." Hier steht beides.

**Alles lokal committet, nichts gepusht.** 810 Tests grün.

---

## TEIL 1 — Was du tun musst

### 1.1 TRADAYRI neu starten (einmalig nötig)

Der schwarze Chart und die Zeitachse auf „1970" sind behoben, aber die
laufende App hat den alten Stand. Also:

1. **TRADAYRI-Fenster schließen** — und auch das schwarze Konsolenfenster
   dahinter (`cmd.exe`), falls es noch offen ist.
2. `start_TRADAYRI` per Doppelklick neu starten.

Danach zeigt der Chart die Historie mit korrekten Datumsangaben, und in der
Kopfzeile steht ein neues Feld: **„Letzte Kerze"**. Das ist die Anzeige, die
dir die Frage von gestern Abend direkt beantwortet.

### 1.2 „Letzte Kerze" lesen

| Farbe | Bedeutung |
|---|---|
| **Grün** („vor 12 s") | Kerzen kommen an, alles läuft |
| **Gelb** („vor 3 Tagen") | Die Börse ist offen, aber **es kommt nichts an** |
| **Grau** | Alter Bestand bei geschlossener Börse — normal, kein Problem |

Steht sie auf **gelb**, fehlt einer der beiden Punkte aus 1.3.

### 1.3 Damit Live-Kerzen ankommen — zwei Dinge, beide nötig

Die neueste Kerze in der Datenbank ist vom **28.08.**, dem Ende deines
NT8-Exports. Seitdem ist nichts nachgekommen, weil der Empfänger nicht läuft.

**Erstens:** den Empfänger starten. Ein eigenes Terminalfenster, das offen
bleiben muss:

```bash
.venv\Scripts\python.exe -m ntbridge
```

**Zweitens:** in NinjaTrader 8 einen **MNQ-Chart öffnen** und dort den
Indikator **`ClaudeBridge`** hinzufügen (Rechtsklick im Chart → Indicators →
ClaudeBridge). Ohne diesen Indikator schickt NinjaTrader nichts.

Beides zusammen — dann springt die Anzeige innerhalb einer Minute auf grün.

> **Warum das nicht automatisch geht:** NinjaTrader schickt Kerzen nur aus
> einem offenen Chart mit dem Indikator heraus. Das ist Absicht: der
> Datenweg läuft über einen **Indikator**, der strukturell keine Orders
> platzieren kann — getrennt vom Orderweg. Diese Trennung ist einer der
> beiden Riegel, an die ich nicht rühre.

### 1.4 Orderausführung testen — das habe ich bewusst NICHT gemacht

Du wolltest testen, ob eine Order bei NinjaTrader ankommt. Das habe ich
liegen lassen, während du geschlafen hast: eine Order abzuschicken ist eine
Handlung nach außen, und die gehört nicht in eine unbeaufsichtigte Nacht.

Wenn du wach bist und NT8 läuft, machen wir das zusammen — es dauert fünf
Minuten. Sag Bescheid.

---

## TEIL 2 — Was ich gebaut habe

### 2.1 Der schwarze Chart: die Ursache

Drei Dinge, alle behoben:

**Zeitstempel in falscher Einheit.** Die neue pandas-Version liefert
Zeitstempel in Mikrosekunden, der Chart erwartet Nanosekunden — Faktor 1000.
Dadurch landete jede Kerze im Januar 1970. Bei Minutenkerzen fielen dann
viele auf dieselbe Sekunde, und die Chart-Bibliothek bricht ab, sobald zwei
Kerzen dieselbe Zeit haben. Das war der schwarze Screen beim Umschalten.

**Der Chart lud nicht nach.** Die Nachlade-Schleife lief nur, wenn der Server
„Handelssitzung läuft" meldete — und dieser Endpunkt war ein Platzhalter, der
immer „läuft nicht" sagte. Jetzt lädt der Chart nach, solange die Börse offen
ist. Ein Chart soll den aktuellen Stand zeigen, ob dabei gehandelt wird oder
nicht.

**„Markt offen" war fest verdrahtet.** Die Kopfzeile hätte auch sonntags
„MARKT OFFEN" gemeldet. Jetzt kommt die Auskunft aus dem Handelskalender —
derselben Quelle, die auch der Backtest benutzt.

**Startproblem:** Die Wartezeit beim Start war 30 Sekunden. Der Server muss
beim ersten Start eine 657-MB-Datenbank öffnen; unter Plattenlast reicht das
nicht, und dann hat der Starter den Server abgeschossen — das war deine
Fehlermeldung von gestern Abend. Jetzt 90 Sekunden.

### 2.2 Der stille Blocker in der Forschung

Ein Rechenschritt in der Mustererkennung war quadratisch statt linear. Über
die volle Historie hätte die Vorbereitung **rund 77 Minuten** gebraucht —
deshalb lief noch nie ein vollständiger Forschungslauf durch. Jetzt:
**90 Sekunden** für alle 2,57 Millionen Kerzen.

Die Musterdefinition ist unverändert; ein Test vergleicht Fund für Fund
gegen die alte Rechnung.

### 2.3 Die Ereignisdatenbank — der eigentliche Fortschritt

Das ist die Untersuchung, die du beauftragt hast. Sieben Erkenner, alle mit
Lookahead-Test, alle über die volle Historie:

| Erkenner | Was er findet |
|---|---|
| **struktur** | Strukturbrüche (BOS) und Charakterwechsel (CHoCH) |
| **fvg** | Fair Value Gaps mit Verfolgung, ob sie wieder angelaufen wurden |
| **displacement** | Impulskerzen mit Körper- und Volumendominanz |
| **orderblocks** | die letzte Gegenkerze vor einem Impuls |
| **eqhl** | Equal Highs/Lows — der Liquiditätspool |
| **sweeps** | **Liquidity Sweeps** — der Stop-Run mit sofortiger Umkehr |
| **niveaus** | Test / n-ter Test / Ausbruch / Fehlausbruch / Retest an PDH, PDL, Vortagesschluss, Initial Balance, Opening Range und Swings |

Der **Sweep** ist der, den du im Kopf hattest: dein erfolgreicher Trade hatte
das Ziel „knapp unter dem letzten Liquiditäts-Spike". Jedes Sweep-Ereignis
trägt jetzt auch das **relative Volumen an der Sweep-Kerze** — der einzige
messbare Ersatz für das fehlende Orderbuch. Ein Sweep mit vierfachem Umsatz
ist strukturell etwas anderes als einer bei dünnem Handel.

Dazu die Datenbank selbst (`data/eventdb.sqlite3`): vier Tabellen, jedes
Ereignis mit seinem **Kontext zum Verfügbarkeitszeitpunkt** — Volatilitäts-,
Struktur- und Liquiditätsregime, Session, Wochentag, Minuten seit
Börseneröffnung, Abstand zu VWAP und Vortagesmarken.

**Der wichtigste Test dabei:** er schneidet die Kursreihe direkt hinter einem
Ereignis ab und prüft, ob der gespeicherte Kontext identisch bleibt. Läse der
Schreibweg auch nur eine Kerze zu weit, wäre die ganze Datenbank wertlos —
und man würde es den Zahlen nicht ansehen.

### 2.3a Die Datenbank ist gefüllt

Der Volllauf ist durchgelaufen, während du geschlafen hast:

**2.592.334 Ereignisse** über 2.573.719 Minutenkerzen, 06.05.2019 bis
28.08.2026. Aufgeteilt in Training (1,67 Mio), Validation (352 k) und
Out-of-Sample (575 k).

Die vollständige Bestandsaufnahme mit allen Tabellen steht in
**`docs/EREIGNISDATENBANK_BESTAND_2026-08-31.md`**. Drei Dinge daraus, die
dich direkt interessieren:

**Der n-te Test eines Niveaus** — deine Frage, jetzt beziffert:

| Test Nr. | Häufigkeit | Anteil vom vorherigen |
|---:|---:|---:|
| 1 | 151.446 | — |
| 2 | 49.035 | 32 % |
| 3 | 14.998 | 31 % |
| 4 | 4.566 | 30 % |
| 5 | 1.429 | 31 % |
| 6 | 472 | 33 % |

Nach jedem Test wird ein Niveau in rund **einem Drittel** der Fälle noch
einmal getestet — und diese Rate ist über sechs Stufen bemerkenswert stabil.
Ob der zweite Test besser *hält* als der erste, sagt das noch nicht. Aber die
Stichproben reichen bis Test 6 für belastbare Aussagen.

**Liquidity Sweeps** — 357.510 Stück. Das Volumen an der Sweep-Kerze liegt
durchgehend beim **rund Doppelten** des Normalwerts, gleichmäßig über alle
Sessions. Das ist die einzige Aussage über „Liquidität", die diese Daten
hergeben — und sie ist gemessen, nicht behauptet. Die Richtungen sind fast
perfekt ausgeglichen: keine Session sweept systematisch mehr nach unten als
nach oben.

**Welche Marke am meisten gehandelt wird:** Swing-Hochs und -Tiefs stellen
59 % aller Niveau-Ereignisse. Das hängt direkt an der Entscheidung in Teil 3.

> Nochmal deutlich: das sind **Häufigkeiten, keine Ergebnisse**. Ob eines
> dieser Muster funktioniert, steht nirgends — dafür fehlt Etappe 4.

### 2.3b Ein Fund, den ich beim Aufräumen gemacht habe

Der erste Schreiblauf brauchte fast **zwei Stunden** für die 2,59 Mio Zeilen.
Statt zu raten habe ich gemessen: 24 von 36 Sekunden gingen für das
Herausgreifen einzelner Zeitstempel drauf — fünf Mal pro Ereignis.

Jetzt einmal vektorisiert für die ganze Reihe: **16.500 statt 3.600 Zeilen
pro Sekunde**. Hochgerechnet 157 Sekunden statt 7.087. Faktor 45.

Das Datenformat ändert sich dabei nicht — ein Test prüft das auf das Zeichen
genau, inklusive beider US-Zeitumstellungen. Die bereits geschriebene
Datenbank bleibt gültig, ich habe es gegengeprüft.

### 2.4 Geminis Kritik — eingearbeitet

Alle fünf Punkte waren berechtigt, alle sind jetzt im Plan und teilweise
schon gebaut. Details stehen in `docs/FORSCHUNGSPLAN_EVENTDATENBANK.md`
Abschnitt 16. Der stärkste Punkt (gleichzeitige Signale blähen die Statistik
auf) ist bereits als `cluster_id` in der Datenbank umgesetzt.

---

### 2.5 Etappe 4 und 8 sind auch gebaut

Ich bin weiter gekommen als geplant. Zwei Dinge sind dazugekommen:

**Die Outcomes** (`common/ereignisse/outcomes.py`). Für jedes der 2,59 Mio
Ereignisse wird jetzt gemessen, was danach passiert — über 1, 3, 5, 10, 20,
30, 60, 120 und 240 Kerzen: wie weit lief es *für* die Position (MFE), wie
weit *dagegen* (MAE), wo stand es am Ende, und wie lange dauerte es bis zum
jeweiligen Extrem.

Die bestehende Funktion dafür hätte bei dieser Menge Milliarden Iterationen
gebraucht. Die neue rechnet über rollende Fenster: **2 Minuten** für alles.
Ein Test vergleicht beide Fassungen Zeile für Zeile — die Definition ist
dieselbe.

**Der Grundratenbericht** (`werkzeuge/grundratenbericht.py`). Das ist die
Tabelle, um die es dir von Anfang an ging. Aufruf:

```bash
.venv\Scripts\python.exe -m werkzeuge.grundratenbericht --horizont 60
```

Darin sind vier Vorkehrungen eingebaut, ohne die so eine Tabelle wertlos ist:

1. **Jede Zahl steht neben ihrer Nulllinie.** „In 62 % der Fälle ging es
   hoch" sagt nichts, wenn es ohne das Muster in 61 % der Fälle hochgeht.
2. **Überschneidungsfreie Statistik.** Zwei Ereignisse fünf Kerzen
   auseinander teilen sich bei Horizont 60 fast das ganze Fenster. Als
   unabhängig gezählt wäre die Signifikanz um Faktor ~8 zu groß.
3. **Klumpen zählen einmal.** Wenn sieben Erkenner um 15:35 dasselbe melden,
   ist das eine Beobachtung, nicht sieben.
4. **Alle Muster stehen in der Tabelle**, auch die langweiligen — und
   darunter steht, ab welchem p-Wert ein Fund bei so vielen Vergleichen noch
   zählt.

### 2.6 Die Datenbank ist gefüllt — mit einem Vorbehalt

Der Volllauf ist durch: **2.592.334 Ereignisse** und **23.330.554
Outcome-Zeilen**. Die Datei ist **5,4 GB** groß.

Und da liegt ein Problem, das ich dir offen sagen muss: **auf deinem Laptop
ist diese Datenbank an der Grenze.** Das Schreiben dauerte fünf Stunden, und
der erste Auswertungsversuch war nach 25 Minuten noch nicht fertig. Beide
Ursachen habe ich gefunden und behoben (Details im nächsten Abschnitt), aber
die Größenordnung bleibt: jede Auswertung liest hier Gigabyte.

Das spricht zusätzlich für Weg 1 aus Teil 3 — und dafür, die Swing-Niveaus
auszudünnen. Weniger, aber aussagekräftigere Ereignisse wären auf dieser
Hardware deutlich angenehmer zu handhaben.

### 2.7 Drei Geschwindigkeitsfunde in einer Nacht

Alle drei nach demselben Muster: gemessen statt geraten, und alle drei waren
woanders, als ich zuerst vermutet hätte.

| Was | Vorher | Nachher | Ursache |
|---|---|---|---|
| Musterserie vorbereiten | 77 min | 90 s | quadratische Suche |
| Ereignisse schreiben | 7.087 s | ~160 s | Zeitstempel je Zeile statt vektorisiert |
| Outcomes schreiben | 18.386 s | offen* | Einfügereihenfolge gegen den Schlüssel |
| Auswertung lesen | >25 min | offen* | Join mit Millionen Einzel-Lookups |

\* behoben, aber noch nicht auf voller Größe nachgemessen — der Index dafür
baut gerade.

Bei zweien davon lag ich mit der ersten Vermutung falsch und habe es gemerkt,
weil ich gemessen habe: Beim Ereignis-Schreiben hielt ich die Indizes für die
Ursache, baute den Umbau — und maß **keinen Unterschied**. Erst das Profiling
zeigte, dass 24 von 36 Sekunden in Zeitstempel-Zugriffen steckten.

## TEIL 3 — Eine Entscheidung, die du treffen musst

### Es sind viel mehr Ereignisse als geplant

Der Forschungsplan rechnete mit **200.000 bis 800.000** Ereignissen.
Gemessen auf der 1-Minuten-Historie: **rund 2,5 Millionen** — und das ist
erst die 1m-Ebene. Der Plan sieht zusätzlich 5m, 15m und 1h vor.

Das ist kein Fehler, sondern eine ehrliche Zahl: Sweeps und Ausbrüche an
Swing-Niveaus sind auf Minutenbasis einfach häufig.

**Das Problem daran:** Etappe 7 des Plans sieht ein volles Stop-Raster vor —
25 Stop-Positionen × 5 Einstiegsvarianten × alle Ereignisse. Bei 2,5 Mio
Ereignissen sind das **über 300 Millionen Zeilen**. Das ist nicht mehr
handhabbar, weder als Datei noch als Rechenzeit.

**Drei Wege, meine Empfehlung zuerst:**

1. **Stop-Analyse nur auf einer Auswahl** (empfohlen). Erst die Grundraten
   über *alle* Ereignisse messen — das ist billig und beantwortet die
   Hauptfrage. Dann das volle Stop-Raster nur für die Mustertypen rechnen,
   die überhaupt einen Effekt zeigen. Das ist **keine** Rosinenpickerei,
   solange die Auswahl im Hypothesenregister gezählt wird.

2. **Swing-Niveaus ausdünnen.** Rund 800.000 der Ereignisse entstehen daran,
   dass jeder einzelne bestätigte Swing als eigenes Niveau zählt. Man könnte
   nur „bedeutende" Swings nehmen. Das ist eine inhaltliche Entscheidung
   darüber, was ein Niveau ist — und die will ich nicht allein treffen.

3. **Volles Raster trotzdem**, in Parquet-Dateien statt SQLite, Laufzeit
   mehrere Nächte. Machbar, aber teuer, bevor wir wissen, ob überhaupt etwas
   dran ist.

Ich empfehle **Weg 1**. Sag mir morgen, was du willst.

---

## TEIL 4 — Wo ich stehengeblieben bin

**Fertig:** Etappe 1 (Erkenner), Etappe 2 (Datenbank), Etappe 3 (der
Erkennungslauf über die Historie).

**Als Nächstes:** Etappe 4 — die Outcomes. Also: was ist nach jedem Ereignis
tatsächlich passiert, über 1, 3, 5, 10, 20, 30, 60, 120, 240 Kerzen und bis
Sessionende. Das ist der Schritt, nach dem man zum ersten Mal Sätze sagen
kann wie „nach einem Sweep des Vortagestiefs lief der Kurs in X % der Fälle
mindestens 1 ATR nach oben".

Das ist **Opus-Arbeit** — dort kommen Intrabar-Ambiguität, die
Doppelklassifikation und die überschneidungsfreie Statistik zusammen.

**Ehrlich gesagt, damit es nicht untergeht:** Ob in diesen Mustern überhaupt
ein Vorteil steckt, ist offen. Die Datenbank kann genauso gut zeigen, dass
nichts zu holen ist. Das wäre ein gültiges Ergebnis, kein Scheitern — und wir
hätten es sauber gemessen statt geraten.

---

## Modellwahl für morgen

| Aufgabe | Modell |
|---|---|
| Orderweg live testen | **Sonnet 5** — Handgriffe, kein Denken |
| Grundratenbericht lesen und deuten | **Opus 5** — hier sitzt die Statistik |
| Weitere Erkenner (Bewegungsmuster) | Sonnet 5 |
| Outcome-Klassifikation (Etappe 5) | Sonnet 5 — Regeln stehen im Plan |
| Stop-Analyse (Etappe 7) | **Opus 5**, nach deiner Entscheidung aus Teil 3 |

Fang mit dem Orderweg auf Sonnet an. Für die Deutung der Grundratentabelle
lohnt Opus — das ist die Stelle, an der man sich am leichtesten selbst
betrügt.

---

## Die kurze Fassung, falls du wenig Zeit hast

1. TRADAYRI schließen und neu starten.
2. `python -m ntbridge` starten, in NT8 einen MNQ-Chart mit `ClaudeBridge`
   öffnen. Dann steht „Letzte Kerze" auf grün.
3. Diesen Befehl laufen lassen und mir sagen, was dasteht:

```bash
.venv\Scripts\python.exe -m werkzeuge.grundratenbericht --horizont 60
```

Das ist der erste echte Blick auf die Frage, die hinter dem ganzen Projekt
steht. Falls er lange läuft: die Datenbank ist 5,4 GB, der erste Durchlauf
muss viel von der Platte holen.

4. Mir sagen, welchen der drei Wege aus Teil 3 du willst.

---

## Was ich in dieser Nacht nicht geschafft habe

Damit du es von mir hörst und nicht selbst suchen musst:

- **Der Grundratenbericht ist noch nicht gelaufen.** Die Mechanik steht und
  ist getestet, aber der erste Volllauf über die 5,4-GB-Datenbank lief in die
  Länge. Ich habe die Ursachen gefunden und behoben; der Index, der es
  schnell macht, baut noch, während ich das schreibe.
- **Die Outcome-Klassifikation (Etappe 5)** fehlt — also die Einteilung in
  „Ausbruch bestätigt", „Fehlausbruch", „Rückkehr zum Test" und so weiter.
  Die Rohzahlen sind da, die Klassen noch nicht.
- **Die Stop-Analyse (Etappe 7)** wartet auf deine Entscheidung aus Teil 3.
- **Bewegungsmuster** (Impuls + Konsolidierung, Umkehr nach Extrembewegung,
  Kompression → Expansion) sind noch nicht als Erkenner gebaut.
