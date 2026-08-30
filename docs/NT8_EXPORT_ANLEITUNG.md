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

Laurin will alles ab Juni 2019 (30.08.2026). Das sind alle 30 Kontrakte, die
NinjaTrader lokal vorhaelt — MNQ wurde im Mai 2019 eingefuehrt, frueher gibt
es nichts.

**Die Startdaten sind nicht gerechnet, sondern aus NinjaTraders eigenem
Bestand abgelesen** (siehe `rollplan_aus_nt8`). Sie entsprechen genau dem Tag,
ab dem NinjaTrader den jeweiligen Kontrakt als Frontmonat fuehrt.

| Kontrakt | Startdatum | Enddatum | Handelstage |
|---|---|---|---|
| MNQ JUN19 | 06.05.2019 | 21.06.2019 | 28 |
| MNQ SEP19 | 13.06.2019 | 20.09.2019 | 65 |
| MNQ DEC19 | 12.09.2019 | 20.12.2019 | 66 |
| MNQ MAR20 | 12.12.2019 | 20.03.2020 | 64 |
| MNQ JUN20 | 11.03.2020 | 19.06.2020 | 67 |
| MNQ SEP20 | 11.06.2020 | 18.09.2020 | 66 |
| MNQ DEC20 | 10.09.2020 | 18.12.2020 | 69 |
| MNQ MAR21 | 10.12.2020 | 19.03.2021 | 63 |
| MNQ JUN21 | 11.03.2021 | 18.06.2021 | 67 |
| MNQ SEP21 | 10.06.2021 | 17.09.2021 | 65 |
| MNQ DEC21 | 09.09.2021 | 17.12.2021 | 66 |
| MNQ MAR22 | 09.12.2021 | 18.03.2022 | 66 |
| MNQ JUN22 | 10.03.2022 | 17.06.2022 | 67 |
| MNQ SEP22 | 09.06.2022 | 16.09.2022 | 70 |
| MNQ DEC22 | 08.09.2022 | 16.12.2022 | 71 |
| MNQ MAR23 | 12.12.2022 | 17.03.2023 | 65 |
| MNQ JUN23 | 12.03.2023 | 16.06.2023 | 67 |
| MNQ SEP23 | 12.06.2023 | 15.09.2023 | 66 |
| MNQ DEC23 | 11.09.2023 | 15.12.2023 | 68 |
| MNQ MAR24 | 11.12.2023 | 15.03.2024 | 63 |
| MNQ JUN24 | 10.03.2024 | 21.06.2024 | 72 |
| MNQ SEP24 | 17.06.2024 | 20.09.2024 | 65 |
| MNQ DEC24 | 16.09.2024 | 20.12.2024 | 69 |
| MNQ MAR25 | 16.12.2024 | 21.03.2025 | 67 |
| MNQ JUN25 | 16.03.2025 | 20.06.2025 | 71 |
| MNQ SEP25 | 16.06.2025 | 19.09.2025 | 67 |
| MNQ DEC25 | 15.09.2025 | 19.12.2025 | 66 |
| MNQ MAR26 | 15.12.2025 | 20.03.2026 | 66 |
| MNQ JUN26 | 15.03.2026 | 19.06.2026 | 66 |
| MNQ SEP26 | 12.06.2026 | 18.09.2026 | 56 |

**30 Kontrakte, 1954 Handelstage** — Juni 2019 bis heute, lueckenlos.

Der Import schneidet ohnehin auf das Rollfenster zu — ein etwas
grosszuegigerer Zeitraum im Export schadet also nicht. **Leer lassen darfst du
das Startdatum trotzdem nie**, siehe oben.

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
