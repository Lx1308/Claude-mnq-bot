# Basisvermessung der Strategiebibliothek — 23.08.2026

**Arbeitspaket 3 („eigene Einschätzung"), unbeaufsichtigter Lauf.**

## Vorweg: worauf gemessen wurde

Auf der **Dukascopy-Näherungshistorie**, nicht auf MNQ. Die Quelldatei sagt es
selbst, in ihrer Tabelle `herkunft`:

> NÄHERUNG, KEINE MESSUNG. Diese Daten sind ein CFD auf den
> Nasdaq-100-Index, gestellt von der Dukascopy Bank — KEIN MNQ-Futures.
> Andere Preisbildung (ein Market Maker statt CME-Orderbuch), kein echtes
> Handelsvolumen, keine Kontraktabläufe, andere Sessionstruktur.

Alles Folgende ist damit **rein informativ** (Invariante 10). Es beantwortet
die Frage „wie verhält sich das Regelwerk über einen langen Zeitraum
überhaupt", nicht die Frage „was hätte es an der CME verdient". Wer aus
diesen Zahlen eine Strategieentscheidung ableitet, benutzt eine Schätzung wie
eine Messung.

Ebenso ausdrücklich: der Lauf fand in der **Linux-Ersatzumgebung**
(`werkzeuge/python_linux.py`, Python 3.10) statt, nicht unter dem
Projekt-venv.

## Aufbau

| | |
|---|---|
| Datensatz | 3.179.672 Minutenkerzen, 22.08.2016 – 21.08.2026 |
| Verdichtet auf | 637.130 Kerzen à 5 Minuten (schlusszeitbeschriftet, Invariante 9) |
| In-Sample | 22.08.2016 – 24.10.2023, 445.991 Kerzen |
| Out-of-Sample | 24.10.2023 – 21.08.2026, 191.139 Kerzen |
| Kosten | 2,50 USD Kommission je Seite + 1 Tick Slippage je Seite = **6,00 USD je Round Turn** |
| Kontrakt | MNQ-Spezifikation aus `config.yaml` (Tick 0,25 / 2,00 USD je Punkt) |
| Parameter | **unverändert**, wie in `backtest/strategies/library.py` hinterlegt |

Es wurde **nichts optimiert**. Keine Parametersuche, kein Grid, keine
Variantenauswahl — deshalb ist der Out-of-Sample-Zeitraum durch diesen Lauf
auch nicht verbraucht.

## Ergebnis

| Strategie | Zeitraum | Trades | Treffer % | PF | Netto USD | Ø Trade USD |
|---|---|---:|---:|---:|---:|---:|
| prev_day_breakout | in-sample | 1554 | 32,6 | 0,87 | −6.839,64 | −4,40 |
| prev_day_breakout | out-of-sample | 705 | 32,8 | 0,85 | −6.360,45 | −9,02 |
| vwap_trend | in-sample | 3248 | 22,5 | 0,76 | −18.973,92 | −5,84 |
| vwap_trend | out-of-sample | 1196 | 22,7 | 0,85 | −7.630,33 | −6,38 |
| vwap_reversion | in-sample | 4885 | 48,8 | 0,77 | −29.287,56 | −6,00 |
| vwap_reversion | out-of-sample | 1901 | 48,7 | 0,78 | −21.016,76 | −11,06 |
| rsi_mean_reversion | in-sample | 3841 | 47,5 | 0,75 | −30.255,17 | −7,88 |
| rsi_mean_reversion | out-of-sample | 1431 | 49,6 | 0,82 | −15.915,32 | −11,12 |
| flag_breakout | in-sample | 843 | 30,4 | 0,78 | −4.449,95 | −5,28 |
| flag_breakout | out-of-sample | 370 | 33,2 | 0,83 | −2.692,58 | −7,28 |
| ib_breakout | — | **Abbruch** | | | | |

`ib_breakout` konnte nicht laufen — siehe unten, das ist der eigentliche Fund
dieses Laufs.

### Gegenrechnung

Die berichteten Ø-Trades sind aus Trefferquote, Ø-Gewinn und Ø-Verlust
nachgerechnet worden und stimmen auf Rundungsniveau überein. Die
Break-even-Trefferquote (der Punkt, ab dem das Chancen-Risiko-Verhältnis
trägt) liegt in allen zehn Fällen **3 bis 7 Prozentpunkte** über der
tatsächlichen — kein Ausreißer, kein Einzelfall.

## Was daran interessant ist

**Die Kosten sind nicht der Rand, sie sind der Unterschied.** 6,00 USD je
Round Turn gegen Ø-Trades zwischen −4,40 und −11,12 USD. Rechnet man die
Kosten heraus, steht **vor Kosten**:

| Strategie (in-sample) | Ø Trade brutto | Ø Trade netto |
|---|---:|---:|
| prev_day_breakout | **+1,60** | −4,40 |
| flag_breakout | +0,72 | −5,28 |
| vwap_trend | +0,16 | −5,84 |
| vwap_reversion | 0,00 | −6,00 |
| rsi_mean_reversion | −1,88 | −7,88 |

Vier von fünf Regelwerken sind über zehn Jahre brutto ungefähr **null**. Das
ist kein schlechtes, sondern ein erwartbares Ergebnis: es sind ungefilterte
Basisregeln, und ein ungefilterter Ausbruch ist ungefähr ein Münzwurf mit
Gebühren. Die Aussage dieses Laufs ist deshalb nicht „die Ideen taugen nichts",
sondern:

> Der Hebel liegt nicht am Ein- und Ausstieg, sondern an der **Auswahl** —
> weniger Trades, gefiltert. Bei 6,00 USD Reibung je Trade ist jeder
> vermiedene Nullsummen-Trade bares Geld.

Genau das ist die Prämisse von Etappe C (Ideen protokollieren, Filter messen,
Erwartungswert je Setup ausrechnen). Diese Vermessung stützt sie, statt sie
vorwegzunehmen.

Zwei Einschränkungen dazu, damit die Aussage nicht größer wirkt als sie ist:
die Kostenannahme (1 Tick Slippage je Seite) ist selbst eine Annahme und
niemals an Ausführungen gemessen worden; und die Näherungsdaten eines Market
Makers haben eine andere Mikrostruktur als das CME-Orderbuch, gerade an
Ausbrüchen.

## Befund 1 — `ib_breakout` hat noch nie einen Trade gemacht

Beim ersten Probelauf lieferte `ib_breakout` **null Trades**, über jeden
Zeitraum. Kein Fehler, keine Warnung, keine Auffälligkeit im Report — eine
saubere Null, die sich liest wie „hat in diesem Zeitraum nicht gegriffen".

Die Ursache: die Strategie verlangt die Spalten `ib_high`/`ib_low` aus
`common.levels.initial_balance_per_session`. **`compute_indicators` erzeugt
diese Spalten nicht.** `BarContext.value` löst einen unbekannten Spaltennamen
zu NaN auf, `_valid` verwirft NaN, die Regel feuert nie.

Das ist ein stiller Ausfall der schwersten Sorte — er sieht aus wie ein
Ergebnis. Behoben ist seit dem 23.08.2026 der *stille* Teil:

* `Rule.benoetigte_spalten()` (neu) meldet je Regel die gebrauchten Spalten,
  rekursiv über `AllOf`/`AnyOf`/`Not`.
* `RuleStrategy.benoetigte_spalten()` fasst über alle vier Regelplätze zusammen.
* `Backtester.run` prüft das **einmal vor der Hauptschleife** und bricht mit
  Nennung der fehlenden und der vorhandenen Spalten ab.

Seither meldet der Lauf:

```
Strategie 'ib_breakout' braucht Spalten, die der vorbereitete Datensatz
nicht enthaelt: ib_high, ib_low.
```

**Offen und nicht von einem unbeaufsichtigten Lauf zu entscheiden:** ob die
Initial Balance in `compute_indicators` aufgenommen wird. Das berührt
Invariante 1 (eine einzige Indikator-Implementierung, live wie Backtest) und
ist damit eine Architekturentscheidung. `test_jede_strategie_der_bibliothek_findet_ihre_spalten`
führt die Lücke als **bekannt und erwartet** und fällt um, sobald sie
geschlossen wird — dann gehört der Eintrag aus der Liste, nicht der Test
entschärft.

## Befund 2 — die Robustheitskennzahl log

Für `prev_day_breakout` stand im Report:

```
Ø pro Trade (in-sample)     : -4,40 USD
Ø pro Trade (out-of-sample) : -9,02 USD
Robustheit OOS/IS           : 2,05  -> stabil
```

Der Verlust hat sich mehr als verdoppelt, und daneben stand „stabil". Der
Quotient Ø-Trade OOS zu Ø-Trade IS dreht bei negativem Nenner sein Vorzeichen
um und behauptet das Gegenteil dessen, was passiert ist.

Behoben: `StrategyRun.robustness` ist `None`, sobald der Ø-Trade in-sample
nicht positiv ist. An einer Strategie, die schon in-sample verliert, gibt es
auch nichts zu bestätigen — Robustheit ist die Frage, ob ein *gefundener*
Vorteil außerhalb der Suchdaten Bestand hat. Der Report schreibt in dem Fall
ausdrücklich „nicht aussagekräftig (schon in-sample kein positiver Ø-Trade)",
statt die Zeile wegzulassen: eine fehlende Zeile hielte man für einen
Darstellungsfehler statt für eine Aussage.

## Befund 3 — „% vom Hoch" beim Drawdown ist unbrauchbar (nicht behoben)

Der Report nennt Drawdowns wie `8.539,68 USD (78037,8 % vom Hoch)`. Die
Prozentangabe bezieht sich auf den bisherigen Höchststand der Equity-Kurve,
und die Kurve startet bei **null** (reine P&L, kein Startkapital). Steht der
Höchststand bei ein paar Cent, kommen fünfstellige Prozentwerte heraus. Die
Schutzabfrage in `max_drawdown` (`peak_at_worst > 0`) greift zu spät.

Rechnerisch ist der Wert nicht falsch, nur nutzlos. Ihn sinnvoll zu machen
hieße, ein Startkapital ins Modell zu nehmen — eine Modellentscheidung, keine
Fehlerkorrektur. Deshalb hier **nur festgehalten, nicht geändert**. Bis dahin
gilt: nur die USD-Angabe des Drawdowns lesen, die Prozentangabe ignorieren.

## Wie der Lauf zu wiederholen ist

```
python3 werkzeuge/python_linux.py werkzeuge/dukascopy_export.py \
    --minuten 5 --ziel <scratch>/DUKA_5m.csv
python3 werkzeuge/python_linux.py -m backtest.cli compare \
    --symbol DUKA --csv <scratch>/DUKA_5m.csv --interval 5
```

Über einen FUSE- oder Netz-Mount ist der volle Tabellendurchlauf zäh; die
SQLite-Datei vorher lokal kopieren und `--quelle` setzen. Ein voller
`compare`-Lauf über alle Strategien braucht rund zwanzig Minuten, eine
einzelne Strategie rund zweieinhalb.
