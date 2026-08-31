# Grundratenbericht Horizont 60, Training — 31.08.2026

Der erste echte Blick auf die Frage hinter dem ganzen Projekt: **hat eines
dieser Muster einen Vorteil?**

> **Kurzfassung: Nein — und der erste Bericht, der „ja" sagte, war ein
> Artefakt.** Details unten. Das ist kein Fehlschlag, sondern das erwartete
> Ergebnis (Mesfin 2026, Zweiwochenprobe) — sauber gemessen statt geraten.

---

## 1. Was der erste Bericht anzeigte

Roh gerechnet, gruppiert nach Mustertyp, Horizont 60 Kerzen, Trainingsblock:

```
9 Zeilen unter der Bonferroni-Schwelle:
  order_block [long]      kante_R 0.30   p 0.00000
  displacement [long]     kante_R 0.30   p 0.00000
  choch_bullish [long]    kante_R 0.28   p 0.00000
  bos_bullish [long]      kante_R 0.27   p 0.00000
  fair_value_gap [long]   kante_R 0.26   p 0.00008
  fehlausbruch [long]     kante_R 0.25   p 0.00000
  ausbruch [long]         kante_R 0.24   p 0.00000
  ausbruch_retest [long]  kante_R 0.23   p 0.00000
  liquidity_sweep [long]  kante_R 0.22   p 0.00000
```

Neun von zehn Long-Mustern mit „statistisch hochsignifikantem" Vorteil.

## 2. Warum das nicht stimmt

**Erster Verdacht: Wenn *jedes* Long-Muster denselben Vorteil zeigt, ist das
keine Entdeckung, sondern ein Fehler im Aufbau.**

Der Blick auf `niveau_test [long]` bestätigt es:

| | E[R] | **Median R** | Anteil positiv |
|---|---:|---:|---:|
| niveau_test [long] | **−3,03** | **+0,22** | 0,517 |
| alle anderen Long-Muster | +0,02 bis +0,09 | +0,14 bis +0,26 | 0,51–0,52 |

Ein Mittelwert von **−3,03** bei einem Median von **+0,22** — das heißt: der
Mittelwert wird von einzelnen Extremwerten zertrümmert.

**Die Ursache**, direkt aus den Rohdaten (69.126 Ereignisse):

```
end_r  Mittel -3,03   Median +0,22   min -9439,5   max +904,4
atr_referenz  min 0,0026   Median 4,85
atr_referenz < 1,5:  6.273 Ereignisse (9 %),  deren end_r-Mittel: -33,8

Die 5 extremsten:
  end_r        end_pkt   atr_referenz
  -9439,5      -156,0    0,0165
  -9378,3      -179,8    0,0192
  -8367,5      -186,0    0,0222
```

`end_r` ist `end_pkt / atr_referenz`. Bei einer ATR-Referenz von **0,017
Punkten** ergibt eine ganz normale Bewegung von −156 Punkten ein „R" von
**−9.400**. Diese ATR-Werte stammen aus **eingefrorenen Kursen** in der
dünnen Frühhistorie (2019–2021, MNQ bei 7.500, tote Nachtstunden) — kein
Marktzustand, den man hätte handeln können.

**Und dann kommt der zweite Effekt:** `niveau_test [long]` sind 8 % aller
Long-Ereignisse. Ihr Mittelwert von −3,03 zieht die **Nulllinie aller Longs**
auf −0,20. Dadurch sieht jedes andere Long-Muster mit E[R] ≈ +0,05 wie „+0,25
Vorteil" aus — reiner Vergleich gegen eine vergiftete Nulllinie.

Trimmt man die extremsten 1 % weg: `niveau_test [long]` E[R] = **+0,055**. In
einer Reihe mit allem anderen.

## 3. Der robuste Blick

Der **Trefferanteil** — wie oft war der Kurs nach 60 Kerzen über dem Einstieg
— benutzt die ATR gar nicht und ist gegen diesen Fehler immun:

| Richtung | Muster (alle) | Nulllinie | Differenz |
|---|---:|---:|---:|
| Long | 0,509 – 0,520 | 0,516 | −0,7 bis +0,4 Prozentpunkte |
| Short | 0,462 – 0,476 | 0,473 | −1,1 bis +0,3 Prozentpunkte |

**Jedes Muster sitzt auf seiner Nulllinie.** Die Wilson-Konfidenzintervalle
überlappen die Nulllinie durchweg. Der einzige Ausreißer nach unten ist
`bos_bearish [short]` mit 0,462 (Nulllinie 0,473) — also *schlechter* als
Zufall, nicht besser.

Die Long/Short-Asymmetrie selbst (Longs ~51,5 %, Shorts ~47,3 %) ist der
**Aufwärtsdrift von MNQ** über 2019–2023 — die per-Richtung-Nulllinie
korrigiert genau das heraus.

## 4. Was daraus folgt

**Für die Auswertungslogik** (erledigt, `common/ereignisse/grundraten.py`):

- Ereignisse mit `atr_referenz < 1,0` Punkt werden verworfen — Artefakt, kein
  Marktzustand.
- Verbleibende R-Werte werden bei ±25 gekappt (Winsorisierung).
- **Maßgeblich ist der Zwei-Anteile-Test** auf den Trefferanteil, gegen die
  Nulllinie *ohne die eigene Gruppe*, überschneidungsfrei gerechnet. E[R] und
  Median stehen daneben, mit Hinweis wenn sie auseinanderlaufen.
- 27 Tests, u.a. einer, der die vergiftete Nulllinie exakt nachstellt.

**Für die Forschung:**

Nach der Härtung zeigt der Bericht **kein Muster mit belastbarem Vorteil** im
Trainingsblock. Das ist die erwartete Antwort:

- Mesfin (2026) hat 14 Signalfamilien auf MNQ 5m falsifiziert.
- Die Zweiwochenprobe zeigte MFE ≈ MAE, E[R] ≈ 0 über alle Horizonte —
  Zufallspfad.
- `vwap_trend` misst auf den echten Daten −0,08 bis −1,72 USD je Trade.

Ein reiner OHLCV-Mustervorteil auf 1-Minuten-MNQ ist, wenn überhaupt, sehr
klein — und die Grundratentabelle findet ihn nicht.

## 5. Was noch aussteht

- **Der bestätigende Vollrun der gehärteten Auswertung** über die ganze
  Datenbank. Er braucht den erweiterten deckenden Index (Neuaufbau, ~1 h auf
  diesem Rechner) — oder die Entscheidung, die Datenbank kleiner neu zu bauen
  (`docs/UEBERGABE_2026-08-31.md` Teil 3).
- Andere Horizonte (die kürzeren 5–20 Kerzen, die längeren 120–240).
- Gruppierung nach Regime und Session — vielleicht gibt es einen Vorteil, der
  nur in einem bestimmten Regime auftritt und im Gesamtschnitt untergeht.
  Das ist der nächste sinnvolle Schritt, *bevor* man das Projekt für
  gescheitert erklärt.

## 6. Die Lehre

Der erste Bericht meldete einen Fund. Er war falsch. Erkannt wurde das, weil
das Ergebnis *zu* gut und *zu* gleichförmig aussah — neun Muster mit demselben
Vorteil — und weil Mittelwert und Median weit auseinanderlagen.

Genau diese Sorte Fehler — eine Zahl, die aussieht wie ein Befund, es aber
nicht ist — ist in diesem Projekt der teuerste. Diesmal vor der Meldung
gefangen.
