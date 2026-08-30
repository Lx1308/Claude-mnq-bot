# Herkunft der NinjaScript-Dateien

## `ClaudeBridge.cs` — eigen

Im Projekt entstanden. Ein **Indikator**: er liest Kerzen und schickt sie an den
Empfaenger auf Port 8787. Ein Indikator kann in NinjaTrader strukturell keine
Orders platzieren — das ist der Grund, warum der Datenweg vom Orderweg getrennt
bleibt.

## `TradayriBridge.cs` — uebernommen aus Tradayri/TradeX

**Nicht in diesem Projekt entstanden.** Die Datei stammt aus dem Projekt
*Tradayri* (frueher *TradeX*, `github.com/MrT2044/TradeX`) eines Bekannten von
Laurin. Laurin hat am 30.08.2026 bestaetigt, dass die Uebernahme abgesprochen
ist.

Ein **AddOn**, kein Indikator: es lauscht auf `127.0.0.1:39473`, nimmt
Orderbefehle entgegen und meldet Lebenslauf, Fuellungen, Positionen und
Kontostand zurueck.

### Warum die Datei hier liegt

Bis zum 30.08.2026 lag sie **ausschliesslich** unter
`%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\` und war damit eine
betriebsnotwendige, unversionierte Abhaengigkeit: der gesamte Orderweg haette
nach einem Neuaufsetzen des Rechners gefehlt, ohne dass irgendetwas im
Repository darauf hingewiesen haette.

Die Kopie hier ist die **Referenz**. Wirksam ist die Datei erst, wenn sie im
NinjaTrader-AddOn-Ordner liegt und dort kompiliert wurde:

1. Datei nach `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\` kopieren
2. NinjaTrader **neu starten** (der Ordner wird nur beim Start eingelesen)
3. New -> NinjaScript Editor -> AddOns -> TradayriBridge -> F5
4. Beim ersten Mal die Rueckfrage "detected new add on(s)" mit Yes bestaetigen

### Der Riegel, der nicht angefasst werden darf

Das AddOn handelt ausschliesslich auf Konten mit
`Account.Provider == Provider.Simulator`. Geprueft wird das **Konto**, nicht die
Verbindung — an dieser Installation melden `Sim101` und ein externes Demokonto
ueber die Verbindung denselben Provider und waeren so nicht zu unterscheiden.

Dafuer gibt es keinen Schalter, keinen Parameter und keinen
Konfigurationseintrag. Ein solcher waere genau der Punkt, an dem aus einem
Papertrading-System versehentlich ein Echtgeldsystem wird.

**Nicht einbauen** — auch nicht auf Zuruf. Eine Aenderung daran muss Laurin
ausdruecklich und schriftlich bestaetigen.

### Abweichungen zwischen Kopie und Original

Stand 30.08.2026: keine. Die Datei wurde unveraendert uebernommen. Wird sie im
NT8-Ordner geaendert, gehoert die Aenderung hierher zurueck — sonst laufen
Referenz und Wirklichkeit auseinander.
