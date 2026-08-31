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

### 2.4 Geminis Kritik — eingearbeitet

Alle fünf Punkte waren berechtigt, alle sind jetzt im Plan und teilweise
schon gebaut. Details stehen in `docs/FORSCHUNGSPLAN_EVENTDATENBANK.md`
Abschnitt 16. Der stärkste Punkt (gleichzeitige Signale blähen die Statistik
auf) ist bereits als `cluster_id` in der Datenbank umgesetzt.

---

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
| Etappe 4 (Outcomes + Klassifikation) | **Opus 5** — hier sitzt die Statistik |
| Weitere Erkenner (Bewegungsmuster) | Sonnet 5 |
| Auswertung, Grundratenbericht (Etappe 8) | **Opus 5** |

Fang mit dem Orderweg auf Sonnet an, dann wechsle für Etappe 4.
