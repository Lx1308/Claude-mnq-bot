# NinjaTrader-Historie exportieren und importieren

Für Laurin zum Abarbeiten, und für jede spätere Sitzung zum Nachschlagen.

## Warum überhaupt

Der Indikator schickt beim Chartladen nur mit, was der Chart geladen hat — in
der Praxis Tage bis Wochen. Für Research braucht es Jahre. NinjaTrader hält
MNQ-Minutendaten von 30 Kontrakten zurück bis 2019 lokal vor
(`Documents\NinjaTrader 8\db\minute\`, rund 24 MB).

## Der Fehler, der am 30.08.2026 aufgetreten ist

Laurin hat das **Startdatum leer gelassen**. NinjaTrader fragt dann die
gesamte Historie beim Server an statt nur das lokal Vorhandene zu schreiben.
Das dauert, und im NT8-Log stand zeitgleich:

```
12:59:44  Verbindung zum historischen Datenserver verloren
12:59:56  Verbindung wiederhergestellt
```

Der Export hing, der Ordner blieb leer. **Immer ein Startdatum angeben.**

## Einstellungen im Dialog

`Tools → Historical Data → Export`

| Feld | Wert |
|---|---|
| Instrument | ein Kontrakt, siehe Tabelle |
| Startdatum | **siehe Tabelle — niemals leer lassen** |
| Enddatum | siehe Tabelle |
| Intervall | **Minute** |
| Datentyp | **Letzter Kurs** |

Ein Kontrakt pro Durchgang; einen Sammelexport gibt es nicht. Die Datei landet
in `Documents\NinjaTrader 8\export\`.

**Dateinamen nicht ändern.** Der Import liest daraus den Kontrakt und schneidet
auf den Zeitraum zu, in dem dieser der Frontmonat war. Ohne das würden sich die
Kontrakte gegenseitig überschreiben — die Reihe sähe lückenlos aus und wäre
eine Mischung aus zwei Kontrakten mit verschiedenem Kursniveau.

## Die Daten je Kontrakt

Startdatum großzügig gewählt (ein Monat vor dem Rollfenster), damit nichts
fehlt. Was davon tatsächlich in die Datenbank geht, steht in der letzten
Spalte — den Rest verwirft der Import.

| Kontrakt | Startdatum | Enddatum | behalten wird |
|---|---|---|---|
| MNQ SEP26 | 01.06.2026 | 18.09.2026 | 11.06.–10.09.2026 |
| MNQ JUN26 | 01.03.2026 | 19.06.2026 | 12.03.–11.06.2026 |
| MNQ MAR26 | 01.12.2025 | 20.03.2026 | 11.12.–12.03.2026 |
| MNQ DEC25 | 01.09.2025 | 19.12.2025 | 11.09.–11.12.2025 |
| MNQ SEP25 | 01.06.2025 | 19.09.2025 | 12.06.–11.09.2025 |
| MNQ JUN25 | 01.03.2025 | 20.06.2025 | 13.03.–12.06.2025 |
| MNQ MAR25 | 01.12.2024 | 21.03.2025 | 12.12.–13.03.2025 |
| MNQ DEC24 | 01.09.2024 | 20.12.2024 | 12.09.–12.12.2024 |
| MNQ SEP24 | 01.06.2024 | 20.09.2024 | 13.06.–12.09.2024 |
| MNQ JUN24 | 01.03.2024 | 21.06.2024 | 07.03.–13.06.2024 |
| MNQ MAR24 | 01.12.2023 | 15.03.2024 | 07.12.–07.03.2024 |
| MNQ DEC23 | 01.09.2023 | 15.12.2023 | 07.09.–07.12.2023 |

Diese zwölf ergeben **drei Jahre lückenlos**. Wer weiter zurück will, rechnet
die Daten mit derselben Regel weiter: Verfall ist der dritte Freitag des
Kontraktmonats, gerollt wird acht Tage davor.

## Reihenfolge: SEP26 zuerst

**Der laufende Kontrakt muss als erster importiert werden.** Nur er
überschneidet sich mit den Kerzen, die die Bridge gesammelt hat, und nur an
dieser Überlappung lässt sich prüfen, ob Zeitzone und Beschriftung stimmen.
Besteht diese Prüfung, wird ein Formatnachweis gespeichert
(`data/nt8_import_nachweis.json`), und alle älteren Kontrakte gehen danach
durch — sie überschneiden sich mit nichts von 2026.

Ohne diesen Nachweis lehnt der Import einen alten Kontrakt ab. Das ist Absicht.

## Wie lange dauert das

Ein Kontrakt umfasst rund 90.000 Minutenkerzen. Liegt er lokal vor — und das
tut er, wenn er unter „Geladen!" steht — sind das Sekunden bis wenige Minuten.
Zieht es sich über Minuten ohne Ergebnis, fehlt das Startdatum oder die
Serververbindung hakt.

## Importieren

Erst prüfen, geschrieben wird nichts:

```bash
.venv\Scripts\python.exe werkzeuge\nt8_import.py "C:\Users\lm130\Documents\NinjaTrader 8\export\MNQ SEP26.txt"
```

Sieht das gut aus, dasselbe mit `--schreiben`:

```bash
.venv\Scripts\python.exe werkzeuge\nt8_import.py "...\MNQ SEP26.txt" --schreiben
```

Vorgabe für die Zeitzone ist `America/New_York`. Stimmt sie nicht, schlägt der
Kreuzvergleich fehl und sagt das — dann `--zeitzone` setzen.

## Was der Import prüft

1. **Kreuzvergleich** gegen die vorhandenen Kerzen (nur beim laufenden
   Kontrakt möglich): stimmen die Kurse auf 0,03 Punkte?
2. **Beschriftung**: liegt die Reihe um eine Minute verschoben *besser* auf der
   Referenz, bricht der Import ab. NinjaTrader beschriftet eine Kerze mit dem
   **Ende** ihres Fensters — genau dieser Fehler ist bei den Dukascopy-Daten
   passiert und war an den Kursen nicht zu sehen.
3. **Rollfenster**: alles außerhalb wird verworfen.
4. **Anschluss** (bei alten Kontrakten): der Preissprung zum Nachbarkontrakt
   muss ein Rollsprung sein und keine Größenordnung.
