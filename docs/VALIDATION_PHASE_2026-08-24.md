# Validation-Phase: alle sechs Discovery-Kandidaten, gleich geprüft

**24.08.2026 (fünfte Sitzung des Tages).** Formale Validation-Phase nach
Masterplan G (Discovery → Validation → Confirmation → Monitoring), im
Auftrag: alle sechs Kandidaten aus dem Discovery-Lauf ohne Vorauswahl auf
einem Block prüfen, den Discovery nie gesehen hat, mit Walk-Forward-
Konsistenzprüfung und vollständiger Multiple-Testing-Transparenz.

**Reproduzierbar mit:** `werkzeuge/validation_discovery_kandidaten.py`.

**Näherung, keine Messung.** Wie jeder Lauf auf `data/DUKA_5m.csv`:
Index-CFD statt MNQ-Futures, rein informativ (Invariante 10/11).

**Ersetzt für die formale Validation-Phase:**
[`docs/VALIDATION_RSI_TERZIL_2026-08-24.md`](VALIDATION_RSI_TERZIL_2026-08-24.md)
aus der vorherigen Sitzung. Jener Lauf prüfte nur einen von sechs
Kandidaten (`vwap_trend`/RSI-Terzil) auf einem Block, der teilweise mit dem
Discovery-Pool überlappte — eine Einschränkung, die dort offen ausgewiesen
war. Dieser Lauf behebt beides: alle sechs Kandidaten, ein Block, der
nachweislich nie berührt wurde. Der frühere Bericht bleibt stehen (siehe
Hinweis dort), seine Ergebnisse sind durch die hier gemessenen präzisiert,
nicht widerlegt — Richtung und Größenordnung stimmen überein.

---

## Methodik

### Die neue Dreiteilung

Bisher gab es nur einen Zweiwege-Schnitt (70 % Training / 30 % Out-of-Sample).
Der Discovery-Lauf hat den kompletten 70-%-Trainingsteil gepoolt ausgewertet
— es blieb also kein Block übrig, den Discovery nie gesehen hat, außer dem
einmaligen Out-of-Sample-Teil selbst.

Neu in `backtest/splits.py`: `split_data_three_way` teilt den bisherigen
Out-of-Sample-Rest ein zweites Mal (`config.yaml`,
`backtest.split.validation_fraction`, Vorgabe 0,5):

```
0 % ------------- 70 % --------- 85 % ------------------- 100 %
TRAINING            | VALIDATION  |      OUT-OF-SAMPLE
(Discovery, bereits  | (dieser     |      (weiterhin unberührt,
 verbraucht, gepoolt)| Lauf)       |       einmalig für Confirmation)
```

Gemessen (`data/DUKA_5m.csv`):

| Block | Zeitraum | Kerzen |
|---|---|---:|
| Training | 2016-08-22 bis 2023-10-24 | 445 991 |
| **Validation** | **2023-10-24 bis 2025-03-25** | **95 569** |
| Out-of-Sample | 2025-03-25 bis 2026-08-21 | 95 570 |

Die 70-%-Grenze ist **unverändert** dieselbe wie im Discovery-Lauf (Test
`test_dreiwege_split_traingrenze_ist_dieselbe_wie_beim_zweiwege_split`
sichert das ab) — sie wird durch die Dreiteilung nicht verschoben. Der
Out-of-Sample-Rest (85–100 %) bleibt vollständig unberührt und einmalig für
die Confirmation-Phase reserviert; `assert_validation_only` bricht ab, sobald
Daten daraus in einen Validation-Lauf geraten würden.

### Keine Vorauswahl, keine privilegierten Hypothesen

Alle sechs Discovery-Treffer gehen in dieselbe Prüfung — unabhängig davon,
ob eine Hypothese in der vorherigen Sitzung als "vermutlich zirkulär"
eingeordnet wurde oder nicht (siehe Abschnitt "Der Zirkularitätsbefund
relativiert sich" unten). Faktordefinition, Terzilgrenzen (RSI: 45,902 /
56,596; Stochastik-K: 35,858 / 71,374) und Strategie sind exakt aus dem
Discovery-Lauf übernommen, nichts wird auf dem Validation-Block neu
angepasst.

Die vier zugrundeliegenden (Strategie, Faktor)-Kombinationen liefern
zusammen 12 Terzil-Gruppen; eine davon (`flag_breakout`/RSI-Terzil/mittel)
hat im Validation-Block nur 7 Trades und bleibt unter der 20-Trade-Schwelle
unauswertbar. **11 Hypothesen** gehen in die Bonferroni-Korrektur dieser
Phase ein — skaliert mit der tatsächlichen Zahl der hier testbaren Gruppen,
nicht mit einer Teilmenge der sechs Kandidaten.

### Walk-Forward-Konsistenz

Für jeden Kandidaten mit ≥ 60 Trades im Validation-Block: drei
chronologische, nicht überlappende Unterfenster, eingefrorene Parameter
(kein Fitting je Fenster). Masterplan J verlangt "Plateaus, keine Spitzen" —
ein Effekt, der nur in einem einzelnen Unterfenster steckt, ist ein Fund in
einer Marktphase, keine robuste Kante.

### Keine Makro-/News-Faktoren

Wie der Discovery-Lauf enthält auch dieser Lauf keine Makro- oder
Newsdaten (Begründung: keine Quelle mit Vintage-/`availability_time`-
Modellierung verfügbar, `NORMALER_CHAT_KONTEXT.md` 18.6). Die
Lookahead-Pflicht für `availability_time` betrifft diesen Lauf deshalb
nicht — sie gilt erst, sobald eine Makro-/News-Spalte hinzukommt.

---

## Ergebnis: alle sechs Kandidaten

| Strategie / Faktor / Gruppe | Discovery (Trainingsteil, gepoolt) | Validation-Block | Vorzeichen hält | Bonferroni (Validation-Phase) | Walk-Forward |
|---|---|---|:---:|:---:|---|
| `flag_breakout` / RSI-Terzil / 2 mittel | 35 Trades, −12,773 Pkt, t=−8,97 | 7 Trades — zu wenig Daten | — | — | übersprungen |
| `rsi_mean_reversion` / RSI-Terzil / 2 mittel | 331 Trades, +13,112 Pkt, t=+6,87 | 73 Trades, **+29,267 Pkt**, t=+4,93 | JA | **JA** (p_korr=0,0001) | 3/3 Fenster |
| `rsi_mean_reversion` / RSI-Terzil / 3 hoch | 1705 Trades, −3,812 Pkt, t=−4,81 | 318 Trades, −5,403 Pkt, t=−2,08 | JA | nein (p_korr=0,42) | 2/3 Fenster |
| `vwap_trend` / RSI-Terzil / 2 mittel | 1435 Trades, −3,199 Pkt, t=−4,74 | 300 Trades, −5,450 Pkt, t=−2,47 | JA | nein (p_korr=0,16) | 3/3 Fenster |
| `rsi_mean_reversion` / Stochastik-Terzil / 2 mittel | 694 Trades, +5,407 Pkt, t=+4,42 | 129 Trades, **+13,843 Pkt**, t=+3,31 | JA | **JA** (p_korr=0,013) | 3/3 Fenster |
| `rsi_mean_reversion` / Stochastik-Terzil / 3 hoch | 1462 Trades, −3,841 Pkt, t=−4,30 | 283 Trades, −2,510 Pkt, t=−0,85 | JA | nein (p_korr=1,0) | 2/3 Fenster |

**Fünf von sechs Kandidaten sind auf dem Validation-Block überhaupt
testbar** (`flag_breakout` ist bei diesem Trade-Volumen strukturell zu
selten — dieselbe dünne, extreme Gruppe, die der Discovery-Bericht selbst
schon als Ausreißer-verdächtig markiert hatte). **Alle fünf testbaren
Kandidaten behalten ihr Vorzeichen** — kein einziger dreht auf dem
unabhängigen Block. **Zwei überstehen die für diese Phase korrigierte
Bonferroni-Schwelle**, beide mit durchgehender Walk-Forward-Konsistenz
(3/3 Fenster).

---

## Der Zirkularitätsbefund relativiert sich

Die vorherige Sitzung prüfte, ob der RSI-Terzil-Faktor bei
`rsi_mean_reversion` misst, dass die Strategie nur ihre eigene Einstiegsregel
erfüllt (RSI-Wert der Einstiegskerze statt der Signalkerze), und stufte auf
dieser Grundlage alle vier `rsi_mean_reversion`-Treffer als "entkräftet" ein.

**Diese Sitzung zeigt: die eingefrorene, ORIGINALE Faktordefinition (RSI der
Einstiegskerze, exakt wie im Discovery-Lauf) sagt auf einem echten,
unabhängigen Block weiterhin etwas voraus** — bei der RSI-Terzil-Mitte sogar
deutlicher als im Training (brutto +29,267 gegen +13,112 Punkte, t=+4,93
gegen t=+6,87 bei einem Fünftel der Trade-Zahl), bei beiden
Stochastik-Terzil-Gruppen ebenfalls im gleichen Vorzeichen mit 3/3 bzw. 2/3
konsistenten Fenstern.

**Beide Befunde sind nicht widersprüchlich, sondern beantworten
verschiedene Fragen:**

- Die Zirkularitätsprüfung zeigt: der Effekt verschwindet, sobald man den
  RSI-Wert der Signalkerze statt der Einstiegskerze nimmt — der Faktor misst
  also mechanisch etwas, das eng mit der eigenen Einstiegsregel zusammenhängt.
- Diese Validierung zeigt: **genau diese mechanische Nähe ist trotzdem
  reproduzierbar** — Trades, bei denen sich der RSI zwischen Signal- und
  Einstiegskerze in die Terzil-Mitte hinein bzw. weiter heraus bewegt hat,
  unterscheiden sich systematisch und stabil von den übrigen, auf einem
  Block, den weder Discovery noch die Zirkularitätsprüfung gesehen haben.

**Das ist ausdrücklich keine Entscheidung zwischen beiden Lesarten,
sondern eine offene Spannung, die hier festgehalten wird statt
stillschweigend zugunsten der einen oder anderen aufgelöst zu werden**
(CLAUDE.md: Widersprüche feststellen und dokumentieren, nicht auflösen).
**Korrektur einer eigenen Voreinstufung:** Die pauschale Einordnung "vier
Treffer entkräftet" aus der letzten Sitzung war zu schnell — sie sollte
richtiger heißen: "der naive Faktor ist mechanisch erklärbar, hält sich
aber empirisch auf neuen Daten", was etwas anderes ist als "ist Rauschen".
Für Confirmation zählt ohnehin nur, ob die eingefrorene, wie-entdeckte
Definition weiter trägt — und genau das tut sie hier.

---

## Multiple-Testing-Trichter (über alle Phasen)

| Phase | Geprüfte Hypothesen | Bestanden |
|---|---:|---:|
| Discovery (20×5-Lauf, 24.08.2026) | 239 | 6 (Bonferroni-Schwelle 0,000209) |
| **Validation (dieser Lauf)** | **11** (5 der 6 Kandidaten testbar) | **2** (Bonferroni-Schwelle 0,004545) |

Von den ursprünglich sechs Discovery-Kandidaten: einer nicht testbar (zu
wenig Daten), drei halten im Vorzeichen aber nicht signifikant unter der
strengeren Validation-Bonferroni, zwei bestehen auch diese zweite,
unabhängige Prüfung.

---

## Einordnung

**Zwei Hypothesen — `rsi_mean_reversion`/RSI-Terzil-Mitte und
`rsi_mean_reversion`/Stochastik-Terzil-Mitte — haben jetzt zwei
unabhängige, statistisch korrigierte Prüfungen überstanden**, mit
durchgehender Walk-Forward-Konsistenz. Das ist nach Masterplan G immer noch
kein Befund: Discovery → **Validation** (hier) → Confirmation (einmaliger
Out-of-Sample-Block) → Monitoring. Die Näherungsdaten sind ein CFD, kein
MNQ. Und die beiden Hypothesen betreffen dieselbe Strategie
(`rsi_mean_reversion`) mit stark korrelierten Faktoren (RSI und Stochastik
messen auf demselben Kursverlauf verwandte Dinge) — das sind nicht zwei
unabhängige Bestätigungen im strengen Sinn, eher eine mit zwei Meßlatten.

**Rückfragepflichtig, nicht selbst entschieden:** Ob und wann der
einmalige Out-of-Sample-Block (85–100 %) für die Confirmation dieser beiden
Hypothesen verwendet wird. Er wurde in dieser Sitzung an keiner Stelle
angerührt (`assert_validation_only` bricht sonst laut ab).
