# Ereignisdatenbank — Bestandsaufnahme, 31.08.2026

Erster Volllauf über die gesamte MNQ-Minutenhistorie.

> **Das hier sind Häufigkeiten, keine Ergebnisse.** Es steht nirgends, ob
> eines dieser Muster funktioniert — dafür fehlen die Outcomes (Etappe 4).
> Wer aus diesen Zahlen auf Profitabilität schließt, tut genau das, wogegen
> der ganze Aufbau gebaut ist.

## Der Lauf

| | |
|---|---|
| Kerzen | 2.573.719 (1 Minute) |
| Zeitraum | 06.05.2019 – 28.08.2026 |
| Erkenner | struktur, fvg, displacement, orderblocks, eqhl, sweeps, niveaus |
| **Ereignisse** | **2.592.334** |
| Datei | `data/eventdb.sqlite3` |
| Lauf-Kennung | `L20260830-233449` |

Alle Lookahead-Prüfungen bestanden. Regime-Kontext für 98,7 % der Kerzen
vorhanden (die ersten 60 Handelstage bleiben ohne — das rollende Fenster
braucht Vorlauf).

## Ereignisse je Mustertyp und Datensatzblock

| Mustertyp | Training | Validation | OOS | Gesamt |
|---|---:|---:|---:|---:|
| `fair_value_gap` | 355.135 | 71.145 | 115.358 | **541.638** |
| `ausbruch` | 249.684 | 52.735 | 86.161 | **388.580** |
| `liquidity_sweep` | 225.862 | 49.976 | 81.672 | **357.510** |
| `niveau_test` | 139.991 | 30.983 | 52.288 | **223.262** |
| `fehlausbruch` | 142.034 | 30.321 | 49.003 | **221.358** |
| `displacement` | 130.182 | 27.587 | 45.892 | **203.661** |
| `order_block` | 129.885 | 27.528 | 45.815 | **203.228** |
| `ausbruch_retest` | 116.060 | 25.854 | 43.545 | **185.459** |
| `bos_bullish` | 29.864 | 6.532 | 10.433 | 46.829 |
| `choch_bullish` | 29.782 | 6.184 | 10.110 | 46.076 |
| `equal_highs` | 31.018 | 6.159 | 7.658 | 44.835 |
| `bos_bearish` | 28.606 | 5.828 | 9.906 | 44.340 |
| `choch_bearish` | 28.057 | 5.865 | 9.747 | 43.669 |
| `equal_lows` | 29.286 | 5.478 | 7.125 | 41.889 |

Über die Jahre gleichmäßig verteilt (~350.000 je Jahr, 2019 und 2026 sind
Teiljahre). Kein Artefakt eines einzelnen Zeitraums.

## Welche Marke wird am häufigsten gehandelt?

Niveau-Ereignisse nach der getesteten Marke:

| Marke | Ausbruch | Retest | Fehlausbruch | Sweep | Test | Gesamt |
|---|---:|---:|---:|---:|---:|---:|
| **Swing-Hoch** | 138.180 | 63.845 | 73.304 | 113.116 | 69.611 | **458.056** |
| **Swing-Tief** | 131.114 | 58.703 | 69.328 | 109.637 | 62.700 | **431.482** |
| Vortagesschluss | 20.137 | 11.002 | 14.268 | 24.418 | 16.214 | 86.039 |
| Opening Range 5 (Tief) | 11.869 | 6.334 | 7.790 | 13.328 | 8.697 | 48.018 |
| Opening Range 5 (Hoch) | 11.715 | 6.236 | 7.697 | 13.138 | 8.908 | 47.694 |
| Opening Range 15 (Tief) | 10.872 | 5.701 | 7.071 | 12.017 | 8.132 | 43.793 |
| Opening Range 15 (Hoch) | 10.707 | 5.644 | 6.897 | 11.754 | 8.315 | 43.317 |
| **Vortageshoch** | 9.909 | 5.286 | 6.639 | 11.616 | 7.607 | 41.057 |
| Opening Range 30 (Hoch) | 9.964 | 5.243 | 6.328 | 11.020 | 7.766 | 40.321 |
| Opening Range 30 (Tief) | 9.655 | 4.948 | 6.202 | 10.555 | 7.213 | 38.573 |
| Initial Balance (Hoch) | 8.749 | 4.436 | 5.579 | 9.579 | 6.638 | 34.981 |
| Initial Balance (Tief) | 8.197 | 4.020 | 5.173 | 8.763 | 5.799 | 31.952 |
| **Vortagestief** | 7.512 | 4.061 | 5.082 | 8.569 | 5.662 | 30.886 |

**Der wichtigste Befund daraus:** Swing-Hochs und -Tiefs stellen 890.000 der
rund 1,5 Mio Niveau-Ereignisse — 59 %. Das liegt daran, dass **jeder** der
rund 250.000 bestätigten Swings als eigenes Niveau zählt. Für die
Stop-Analyse ist das zu fein (siehe `docs/UEBERGABE_2026-08-31.md`,
Abschnitt 3).

## Der n-te Test eines Niveaus

Laurins Frage („mehrere aufeinanderfolgende Tests eines Levels") lässt sich
jetzt beziffern:

| Test Nr. | Häufigkeit | Anteil vom vorherigen |
|---:|---:|---:|
| 1 | 151.446 | — |
| 2 | 49.035 | 32 % |
| 3 | 14.998 | 31 % |
| 4 | 4.566 | 30 % |
| 5 | 1.429 | 31 % |
| 6 | 472 | 33 % |
| 7 | 188 | 40 % |
| 8+ | 231 | |

Bemerkenswert stabil: nach jedem Test wird das Niveau in **rund einem Drittel**
der Fälle noch einmal getestet, bevor etwas anderes passiert. Diese Rate ändert
sich über die ersten sechs Tests kaum.

**Was das nicht sagt:** ob der zweite Test besser hält als der erste. Dafür
braucht es Etappe 4. Aber die Stichprobengrößen reichen bis Test 6 locker für
belastbare Aussagen (n ≥ 200 gefordert, hier n = 472).

## Equal Highs / Equal Lows

| Anzahl gleicher Swings | Equal Highs | Equal Lows |
|---:|---:|---:|
| 2 | 36.917 | 34.570 |
| 3 | 6.212 | 5.726 |
| 4 | 1.282 | 1.145 |
| 5 | 293 | 292 |
| 6 | 90 | 101 |
| 7+ | 41 | 55 |

Auch hier ein stabiler Abfall auf etwa ein Sechstel je Stufe. Ab vier gleichen
Swings wird die Stichprobe für belastbare Aussagen knapp.

## Liquidity Sweeps je Session

Laurins Kerninteresse. `direction +1` = Sell-Side-Sweep (Stops unter einer
Marke geholt, bullisch gedeutet), `-1` = Buy-Side.

| Session | Richtung | Anzahl | Volumen am Extremum |
|---|---:|---:|---:|
| New York | +1 | 75.895 | 2,04× |
| New York | −1 | 73.863 | 1,96× |
| Asien | −1 | 52.661 | 1,85× |
| Asien | +1 | 52.534 | 1,94× |
| London | +1 | 37.440 | 1,98× |
| London | −1 | 37.192 | 1,88× |
| Globex ohne Hauptsession | −1 | 13.831 | 2,05× |
| Globex ohne Hauptsession | +1 | 13.562 | 2,11× |

**Zwei Dinge fallen auf:**

1. **Die Richtungen sind fast perfekt ausgeglichen** — in jeder Session, mit
   Abweichungen unter 3 %. Es gibt keine Session, in der systematisch mehr
   nach unten als nach oben gesweept würde.

2. **Das Volumen an der Sweep-Kerze liegt durchgehend beim rund
   Doppelten** des Normalwerts — und zwar in *allen* Sessions, gleichmäßig.
   Das ist die einzige Aussage über „Liquidität", die diese Daten hergeben:
   ein Sweep geht mit erhöhtem Umsatz einher. Ob ein Sweep mit dreifachem
   Volumen anders weiterläuft als einer mit anderthalbfachem, ist eine
   Outcome-Frage.

## Volatilitätsregime

| Regime | Ereignisse |
|---|---:|
| hoch | 986.393 |
| niedrig | 795.683 |
| mittel | 776.846 |

Die Terzile sind per Konstruktion gleich groß über die *Kerzen* — dass im
hohen Vola-Regime 24 % mehr Ereignisse liegen als im mittleren, heißt: in
bewegten Phasen entstehen mehr Muster je Kerze. Erwartbar, aber es gehört bei
jeder späteren Auswertung berücksichtigt (sonst ist die Regime-Verteilung
allein schon ein Störfaktor).

## Was als Nächstes kommt

Etappe 4: für jedes dieser 2,59 Mio Ereignisse messen, was danach passiert —
über 1, 3, 5, 10, 20, 30, 60, 120, 240 Kerzen und bis Sessionende. Erst
danach lassen sich Sätze bilden wie „nach dem zweiten Test des Vortagestiefs
lief der Kurs in X % der Fälle mindestens 1 ATR nach oben, gegenüber einer
Grundrate von Y %".

Und erst dann steht auch fest, ob überhaupt etwas dran ist.
