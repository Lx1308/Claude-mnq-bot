# Neulauf der Basisvermessung unter realistischen Kosten — 23.08.2026

**Anlass:** Die Basisvermessung vom selben Tag lief unter der Altpauschale von
2,50 USD je Seite (5,00 USD Round Turn). Laurin hat am 23.08.2026 die
tatsächlichen Konditionen genannt; der Lauf ist damit wiederholt.

**Kostenprofil:** `private_ninjatrader` — 0,95 USD je Seite, **1,90 USD Round
Turn**, Slippage 1 Tick je Seite (separat, keine Gebühr). Quelle: Laurin,
NinjaTrader-Free-Modell. Die Aufteilung in Broker-/Börsen-/Clearing-/NFA-Anteil
ist **nicht belegt** und wird nicht erfunden.

**Daten:** `data/DUKA_5m.csv`, 637 130 Fünfminutenkerzen aus der
Dukascopy-Näherung, 2016-08-22 bis 2026-08-21.
In-Sample bis 2023-10-24, Out-of-Sample danach.

> **Näherung, keine Messung.** Index-CFD statt MNQ-Futures. Ergebnisse sind
> **rein informativ** und keine Grundlage für Strategieentscheidungen.

---

## Ergebnis

| Strategie | Zeitraum | Trades | Treffer % | PF | Netto USD | Ø Trade USD |
|---|---|---:|---:|---:|---:|---:|
| prev_day_breakout | in-sample | 1554 | 33,5 | 0,96 | −2 022,24 | −1,30 |
| prev_day_breakout | out-of-sample | 705 | 33,3 | 0,90 | −4 174,95 | −5,92 |
| flag_breakout | in-sample | 843 | 31,8 | 0,90 | −1 836,65 | −2,18 |
| flag_breakout | out-of-sample | 370 | 34,6 | 0,90 | −1 545,58 | −4,18 |
| vwap_trend | in-sample | 3248 | 22,9 | 0,87 | −8 905,12 | −2,74 |
| vwap_trend | out-of-sample | 1196 | 22,8 | 0,92 | −3 922,73 | −3,28 |
| vwap_reversion | in-sample | 4885 | 50,0 | 0,88 | −14 144,06 | −2,90 |
| vwap_reversion | out-of-sample | 1901 | 48,9 | 0,84 | −15 123,66 | −7,96 |
| rsi_mean_reversion | in-sample | 3841 | 49,0 | 0,84 | −18 348,07 | −4,78 |
| rsi_mean_reversion | out-of-sample | 1431 | 49,6 | 0,86 | −11 479,22 | −8,02 |
| `ib_breakout` | — | **Abbruch** | | | | |

`ib_breakout` bricht weiterhin ab — `Backtester.prepare()` erzeugt `ib_high`
und `ib_low` nicht. Unverändert der Befund aus der ersten Vermessung.

---

## Vergleich mit dem Lauf unter der Altpauschale

| Strategie (in-sample) | alt (5,00 RT) | neu (1,90 RT) | Differenz |
|---|---:|---:|---:|
| prev_day_breakout | −6 839,64 | **−2 022,24** | +4 817,40 |
| flag_breakout | −4 449,95 | **−1 836,65** | +2 613,30 |
| vwap_trend | −18 973,92 | **−8 905,12** | +10 068,80 |
| vwap_reversion | −29 287,56 | **−14 144,06** | +15 143,50 |
| rsi_mean_reversion | −30 255,17 | **−18 348,07** | +11 907,10 |

**Die Differenzen stimmen auf den Cent** mit `Trades × 3,10 USD` überein
(5,00 − 1,90). Beispiel `vwap_reversion`: 4885 × 3,10 = 15 143,50.

**Die Trade-Zahlen sind identisch geblieben** — 1554, 843, 3248, 4885, 3841 in
beiden Läufen. Das ist der Nachweis, dass ein Profilwechsel **nur** die Kosten
ändert und nicht die Strategie.

---

## Was das Ergebnis sagt — und was nicht

**Alle fünf Strategien bleiben negativ, in-sample wie out-of-sample.** Die
realistischeren Kosten verbessern jede Zahl deutlich, drehen aber keine.

**Der Profit-Faktor liegt zwischen 0,84 und 0,96** — also durchgehend unter 1,
aber nicht weit darunter. `prev_day_breakout` in-sample erreicht 0,96: das ist
knapp, aber die falsche Seite von knapp.

**Warum die Kosten trotzdem nicht die Erklärung sind.** Die Bruttorechnung vom
selben Tag ergab bei `prev_day_breakout` −2,00 USD je Trade **vor** allen
Kosten. Die Kante fehlt schon vorher; günstigere Konditionen verkleinern den
Verlust, erzeugen aber keinen Gewinn.

**Was sich geändert hat, ist die Größenordnung.** Unter der Altpauschale sah
`prev_day_breakout` mit −4,40 USD je Trade aus wie ein klarer Verlustbringer.
Unter realistischen Kosten sind es −1,30 — nahe genug an null, dass ein
Regimefilter den Unterschied machen könnte. **Genau das ist die Frage, die die
Einzelfaktor-Research beantworten soll** (Entscheidung 18.3).

**Nicht ableiten:** dass diese Setups auf echtem MNQ genauso abschneiden. Der
CFD hat andere Preisbildung, kein echtes Handelsvolumen und keine
Kontraktabläufe. Es sind vier Tage echte MNQ-Historie vorhanden — zu wenig für
jede Aussage.

---

## Wie der Lauf zu wiederholen ist

```bash
.venv\Scripts\python.exe werkzeuge/dukascopy_export.py --minuten 5 --ziel data\DUKA_5m.csv
.venv\Scripts\python.exe -m backtest.cli compare --symbol DUKA --csv data\DUKA_5m.csv \
    --interval 5 --kostenprofil private_ninjatrader
```

Rund 13 Minuten für fünf Strategien. Mit `--kostenprofil lucid` lässt sich
derselbe Lauf unter den Prop-Firm-Konditionen rechnen (0,50 je Seite) — dort
wäre die Differenz noch einmal 0,90 USD je Trade zugunsten des Ergebnisses.
