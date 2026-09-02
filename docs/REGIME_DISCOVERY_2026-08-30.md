# Regime-Discovery auf echten MNQ-Daten — 30.08.2026

**Anlass:** Die erste Doppelboden-Messung ließ eine Frage offen — dieselbe
Strategie war in-sample negativ und out-of-sample positiv. Regime oder Zufall?

> **Ergebnis vorweg: nach strengem Maßstab wurde nichts gefunden.** 51
> Hypothesen geprüft, keine unterschreitet die Bonferroni-Schwelle. Das ist
> kein Fehlschlag des Laufs, sondern sein Zweck.

---

## 1. Aufbau

| | |
|---|---|
| Daten | echte MNQ-Historie, 519.084 Kerzen à 5 Minuten |
| **Nur Trainingsteil** | 06.05.2019 – 20.06.2024 (363.358 Kerzen) |
| Out-of-Sample | **nicht angerührt** (`pruefe_nur_training` hätte abgebrochen) |
| Kostenprofil | `private_ninjatrader` |
| Strategien | `doppelboden_bestaetigt`, `doppelboden_nackenbruch`, `vwap_trend` |
| Faktoren | 3 Regime-Achsen + Tageszeit + Wochentag |

Reproduzierbar mit `werkzeuge/regime_discovery.py`.

## 2. Die Regime-Achsen

Drei Achsen, Grenzen **aus der Verteilung** (Terzile eines rollenden
60-Sessions-Fensters), nicht aus einem Lehrbuch:

| Achse | Größe | Ausprägungen |
|---|---|---|
| `vola_regime` | ATR-Rang | niedrig / mittel / hoch |
| `struktur_regime` | ADX-Rang | range / uebergang / trend |
| `liquiditaet_regime` | relatives Volumen zur **selben Tageszeit** | duenn / normal / rege |

**Rückwärtsgerichtet.** Der Rang kommt aus einem rollenden, zurückliegenden
Fenster — nie aus der Gesamthistorie. Sonst hinge das Regime einer Kerze von
2019 davon ab, wie volatil 2026 war; im Backtest sähe das ausgezeichnet aus,
und live gäbe es diese Information nicht. Ein Test hält das fest.

Wo das Fenster noch nicht gefüllt ist, steht **kein Regime** statt des
nächstbesten.

### Verteilung

Alle **27 Schubladen belegt**, von 1,7 % bis 8,1 %. Je Achse sauber gedrittelt
(per Konstruktion).

Die Achsen sind aber **nicht unabhängig**: `niedrig|range|duenn` (8,1 %) und
`hoch|trend|rege` (7,1 %) sind die größten Kombinationen — ruhige Nächte und
aktive Trendtage bündeln sich. Für die Hypothesenzählung ist das günstig
(weniger effektiv unabhängige Tests), heißt aber: die drei Achsen tragen
teilweise dieselbe Information.

## 3. Was die Zerlegung zeigt

### `doppelboden_bestaetigt` (2.252 Trades im Training)

| Achse | Ausprägung | Trades | Treffer | brutto Pkt/Trade |
|---|---|---:|---:|---:|
| Struktur | **uebergang** | 796 | 38,6 % | **+3,40** |
| Struktur | trend | 562 | 33,8 % | −1,63 |
| Struktur | range | 864 | 32,1 % | −3,02 |
| Liquidität | **rege** | 647 | 38,6 % | **+2,50** |
| Liquidität | normal | 862 | 34,0 % | −1,11 |
| Liquidität | duenn | 690 | 32,5 % | −2,09 |
| Vola | niedrig | 78 | 38,5 % | +1,27 |
| Vola | hoch | 1.714 | 35,3 % | −0,25 |

Spannweite auf der Strukturachse: **6,42 Punkte**. Der größte Effekt des
ganzen Laufs.

### `doppelboden_nackenbruch` (1.911 Trades)

| Achse | Ausprägung | Trades | brutto Pkt/Trade |
|---|---|---:|---:|
| Struktur | **trend** | 385 | **+4,00** |
| Struktur | uebergang | 709 | −0,65 |
| Liquidität | **rege** | 728 | +2,66 |
| Liquidität | duenn | 400 | −2,91 |

### `vwap_trend` (2.602 Trades)

Auf allen Achsen schwach — größte Spannweite 3,68 Punkte (Vola), und die
niedrige Vola hat nur 63 Trades.

## 4. Die Statistik

```
Geprüfte Hypothesen        : 51
Unkorrigiertes Niveau      : 0,05
Korrigierte Schwelle       : 0,000980  (alpha / 51)

Bester p-Wert              : 0,0071   (vwap_trend / liquidität / normal, t = −2,70)
Bester positiver Effekt    : 0,0502   (doppelboden_bestaetigt / struktur / uebergang, t = +1,96)

KEINE Gruppe unterschreitet die korrigierte Schwelle.
```

**Bei 51 Hypothesen und α = 0,05 sind rund 2,6 „signifikante" Funde der
Erwartungswert, nicht ein Ergebnis.** Genau deshalb wird korrigiert. Die
Gruppe mit p = 0,050 wäre unkorrigiert ein „Fund" gewesen — und hätte mit
hoher Wahrscheinlichkeit nichts bedeutet.

## 5. Was trotzdem bemerkenswert ist

Ein Punkt, der **kein formaler Test** ist und deshalb keine Signifikanz
beansprucht, aber notiert gehört:

**Beide Doppelboden-Varianten zeigen dieselbe Richtung auf der
Liquiditätsachse** — rege > normal > dünn, konsistent, mit unterschiedlichen
Trades und unterschiedlichem Einstieg:

| | rege | normal | duenn |
|---|---:|---:|---:|
| `doppelboden_bestaetigt` | +2,50 | −1,11 | −2,09 |
| `doppelboden_nackenbruch` | +2,66 | +0,04 | −2,91 |

Zwei Strategien, die sich im Einstieg unterscheiden, ordnen die drei
Liquiditätszustände identisch. Das ist eine **Hypothese für die nächste
Runde**, kein Befund — und sie ist billiger zu prüfen als eine neue, weil sie
aus diesem Lauf schon benannt ist.

Auf der Strukturachse dagegen widersprechen sich die beiden: der frühe
Einstieg trägt im *Übergang*, der späte im *Trend*. Das kann eine echte
Eigenschaft der beiden Einstiegszeitpunkte sein — oder Rauschen. Beides ist
mit diesen Daten nicht zu trennen.

## 6. Was daraus folgt

**Der Vorzeichenwechsel zwischen In- und Out-of-Sample ist damit nicht
erklärt.** Die Regime-Achsen trennen zu schwach, um ihn zu tragen.

Drei Möglichkeiten, in der Reihenfolge, in der sie geprüft werden sollten:

1. **Die Achsen sind zu grob.** Terzile eines rollenden Fensters sind eine
   erste Näherung. Feinere Konditionierung ist Laurins eigentliches Zielbild
   (fallbasiertes Schließen) — aber dort verliert die Bonferroni-Zählung ihren
   Halt, weil aus abzählbaren Hypothesen ein Kontinuum wird.
2. **Der Effekt sitzt woanders.** Tageszeit und Wochentag liefen mit und
   waren ebenfalls schwach. Ungeprüft sind: Position zu Vortagesmarken,
   Struktur der übergeordneten Zeitebene, Abstand zum VWAP.
3. **Es gibt keinen Effekt.** Auch das ist ein Ergebnis, und es deckt sich mit
   der Basisvermessung: die Bibliothek hat keine Kante.

## 7. Offen

- **Nichts davon ist im Register.** Die 51 geprüften Hypothesen zählen
  bislang nicht gegen ein laufübergreifendes Budget — das existiert noch
  nicht. **Bis dahin darf aus mehreren Läufen dieses Skripts keine
  Signifikanzaussage zusammengesetzt werden.**
- Die Achsen korrelieren; eine Entkopplung (z.B. Rang der Struktur *innerhalb*
  des Volatilitätsterzils) wäre sauberer.
- `vola_regime = niedrig` hat bei allen drei Strategien unter 80 Trades. Die
  Achse ist gegenüber der Handelszeit unausgewogen: die Strategien handeln
  RTH, und RTH ist selten „niedrige Volatilität".
