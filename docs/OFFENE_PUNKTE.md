# Offene Punkte

Stand: 30.08.2026. Gepflegt von jeder Arbeitssitzung und vom Watchdog
(`werkzeuge/watchdog.py`, Auftrag in `WATCHDOG_AUFTRAG.md`).

Diese Datei ist die **Arbeitsliste**, nicht das Gedächtnis. Warum etwas so ist,
steht in `CODE_CHAT_KONTEXT.md`; was gebaut werden soll, steht hier.

Prioritäten: **P0** blockiert den Betrieb · **P1** wichtig für die Vision ·
**P2** Verbesserung · **P3** Kür.

---

## Erledigt am 30.08.2026

- [x] **P0** Kerzenkorruption im `tcp_proxy` (Invariante 9) — Proxy ist reiner
      Order-Kanal
- [x] **P0** Invertierte Orderrichtung — explizite Abbildung, lehnt Unlesbares ab
- [x] **P0** Gefälschte Backtest-Kennzahlen — echter Split, echte Kosten
- [x] **P0** UTF-8-BOM in acht Dateien — zwei Schutztests wieder grün
- [x] **P0** Drei Risikoimplementierungen → eine (`execution/risiko.py`)
- [x] **P0** Füllungen wurden verworfen (422) — Format des AddOns übernommen
- [x] **P0** Order-Abholung löschte Orders — Statuswechsel statt Entnahme
- [x] **P1** Kontoregeln als benannte Profile (Lucid 25k–150k, `frei`)
- [x] **P1** Autonomer Bot neu, im Serverprozess, mit Positionsgrößenrechnung
- [x] **P1** Chart-Overlays echt (FVG, Swings, Pools, Sweeps, Struktur)
- [x] **P1** Asia-/London-Level in `common/levels.py`
- [x] **P1** Strategie-Panel echt (Ideen + Ablehnungsgründe)
- [x] **P1** Historien-Import aus NT8 mit erzwungenem Kreuzvergleich
- [x] **P1** NT8-Historie **tatsächlich importiert** — 2,57 Mio
      MNQ-Minutenkerzen 2019–08/2026, vier Import-Bugs behoben
      (Zeitzone UTC, toter `rollplan_aus_nt8`, numerische Dateinamen,
      zu strenge Kreuzvergleich-/Anschlussprüfung). Details:
      `CODE_CHAT_KONTEXT.md` 34.9
- [x] **P0** TRADAYRI zeigte beim Start nur ein „schwarzes Rechteck" — das war
      die leere Chart-Fläche (keine Instrument-Vorauswahl, Chart nur ~1.500
      Kerzen). Behoben: MNQ wird beim Start geladen, Chart zeigt die volle
      Historie 2019–heute als Tageskerzen. Neu `werkzeuge/aggregiere_kerzen.py`
      (1h/4h/1d aus 1m vorberechnet), `execution/server.py` zieht sie im
      Hintergrund nach. Details: `CODE_CHAT_KONTEXT.md` 35
- [x] **P1** Pine-Export und TradingView-Ergebnisimport
- [x] **P1** Research-Engine neu (Split, Kosten, Register, ehrliches Protokoll)
- [x] **P1** Watchdog mit Sperre, Tageslimit, Notaus und Parallelitätsprüfung
- [x] **P0** Dokumentation: Projektgrenze aufgehoben, in `CLAUDE.md`,
      `MASTERPLAN.md` und `CODE_CHAT_KONTEXT.md` nachgezogen
- [x] **P0** Die Engine kam an die echte Historie nicht heran
      (`create_provider` kannte nur `csv`, MASTERPLAN X.1). Behoben:
      `NtBridgeDataProvider`. Erster Backtest auf echten MNQ-Daten gelaufen.
- [x] **P1** Chartmuster als Serie (`common/muster_serie.py`) — das „W" ist
      messbar, mit Verfügbarkeitszeitpunkt statt Lookahead. Zwei Strategien,
      erste Messung in `docs/W_MESSUNG_2026-08-30.md`.
- [x] **P1** Engine ~20× schneller (nur deklarierte Spalten je Kerze),
      abgesichert durch `tests/test_spaltenvertrag.py`.
- [x] **P1** Regime-Engine (`common/regime.py`) — drei Achsen, Grenzen aus
      der Verteilung, rückwärtsgerichtet mit Lookahead-Test. Erster
      Discovery-Lauf auf echten Daten: 51 Hypothesen, keine übersteht die
      Bonferroni-Korrektur. `docs/REGIME_DISCOVERY_2026-08-30.md`

---

## P0 — vor dem nächsten Handelstag

- [ ] **Ende-zu-Ende-Probe des Orderwegs mit offener Börse.**
      Bisher ist der Weg nur gegen Testdaten geprüft. Sobald die Börse offen
      ist: eine Order über das Panel schicken und nachsehen, ob
      `order_update`, `execution` und der gebuchte Trade ankommen.
      Prüfen mit `GET /api/orders`, `GET /api/session/trades`, `GET /api/risiko`.

- [ ] **Lucid-Zahlen bestätigen.** Alle Werte in `common/kontoregeln.py` sind
      Annahmen aus zwei Drittquellen (Lucids Hilfe-Center antwortet
      automatisierten Abrufen mit 403). Laurin liest sie aus seinem Dashboard
      ab, dann in `config.yaml` unter `ausfuehrung.kontoprofile` eintragen —
      mit `quelle` und `ist_annahme: false`. **Solange das offen ist, darf kein
      Bericht behaupten, ein Lauf habe „die Lucid-Regeln" eingehalten.**
      *(Geklärt am 30.08.2026: eine 300k-Stufe gibt es bei Lucid nicht,
      größte ist 150k — das war eine Verwechslung mit FTMO.)*

## P1 — Forschungsgrundlage

- [ ] **Achsen entkoppeln.** Die drei Regime-Achsen korrelieren
      (`niedrig|range|duenn` und `hoch|trend|rege` sind die größten
      Schubladen). Sauberer wäre der Strukturrang *innerhalb* des
      Volatilitätsterzils.

- [ ] **Ungeprüfte Faktoren nachziehen.** Der Discovery-Lauf vom 30.08.2026
      deckte Volatilität, Struktur, Liquidität, Tageszeit und Wochentag ab.
      Offen: Position zu Vortagesmarken, Struktur der übergeordneten
      Zeitebene, Abstand zum VWAP.

- [ ] **`vola_regime = niedrig` hat unter 80 Trades je Strategie.** Die Achse
      ist gegenüber der Handelszeit unausgewogen — die Strategien handeln RTH,
      und RTH ist selten „niedrige Volatilität". Entweder die Achse relativ zur
      Session bilden oder die Ausprägung als nicht auswertbar führen.

- [ ] **Globales Hypothesenbudget im Register.**
      `Discoverylauf.bonferroni_schwelle` zählt nur laufintern. Ein
      Dauerlauf prüft über viele Läufe hinweg tausende Hypothesen, und jeder
      einzelne Lauf sieht für sich sauber aus. Ohne laufübergreifenden
      Zähler ist die Korrektur eine Fassade. **Von Laurin am 30.08.2026 so
      entschieden.**

- [ ] **OOS-Kontingent.** Harte Obergrenze an Confirmations; danach ist der
      Block verbraucht. Der Bot fasst ihn nicht selbständig an.

- [ ] **Doppelboden-Hypothesen ins Register eintragen.** Bis dahin zählen sie
      nicht gegen das Budget und gelten als nicht geprüft.

- [ ] **Hypothesen ernsthaft rechnen — jetzt möglich.** Bis 30.08.2026 waren
      auf zehn Tagen alle Urteile „UNENTSCHIEDEN" (unter 30 Trades). Seit dem
      NT8-Import liegen sieben Jahre Minutenhistorie in
      `data/ntbridge.sqlite3` — die Backtests rechnen auf Jahren, die p-Werte
      werden aussagekräftig, und die Mehrfachtestkorrektur (P3) wird nötig.
      **Achtung Forschungsintegrität:** die frühe Historie 2019–2021 hat mehr
      Dünnmarkt-Lücken (junger Micro-Kontrakt); das ist kein Datenfehler, aber
      bei Ergebnissen aus diesem Zeitraum zu bedenken.

- [ ] **Die vier Hypothesen aus der Antigravity-Phase als Strategien bauen:**
      15-Minuten-Opening-Range-Breakout, ICT Silver Bullet (10–11 ET),
      Asian-Range-Manipulation (London-Sweep), End-of-Day-VWAP-Reversion.
      Die letzte existiert bereits als `power_hour_vwap`. Für die anderen drei
      fehlen Spalten (Opening Range je Session, Asia-Range als Serie) — die
      gehören in `common/indicators.py` bzw. `common/levels.py`, damit sie
      Backtest **und** Ideen-Protokollierung gleichermaßen sehen.

- [ ] **Ausfuehrungsqualitaet aus den echten Fuellungen messen.** NinjaTrader
      meldet den tatsaechlichen Fuellkurs zurueck (Tabelle `fills`). Der
      Abstand zum angenommenen Kurs ist gemessene Slippage — und beantwortet
      die Frage nach Limit-Fills und Slippage ohne eine einzige Tickdatei.
      Sobald genug Live-Trades da sind: auswerten und das Kostenprofil
      `private_ninjatrader` von `ist_annahme` auf belegt umstellen.
      Hintergrund: `CODE_CHAT_KONTEXT.md` 34.7.

- [ ] **MAE/MFE der Live-Trades nachrechnen.** `execution/store.py` lässt sie
      leer, weil sie den Kursverlauf während des Trades brauchen.
      `backtest/excursions.py` kann das — ein Nachlauf, der die Kerzen des
      Trade-Zeitraums holt und die Felder füllt.

## P2 — Aufräumen und Härten

- [ ] **Kennzahl „Max. Drawdown in % vom Hoch" ist kaputt.** Bei einem
      Zwischenhoch nahe null liefert sie Werte wie „6317,6 % vom Hoch". Die
      absolute USD-Zahl stimmt; der Prozentwert braucht einen Bezug auf das
      Startkapital statt auf das Equity-Hoch.

- [ ] **`aggregiere_kerzen --voll` liest die 1m-Reihe je Ziel-Timeframe neu.**
      Bei drei Timeframes sind das drei volle Lesevorgänge über ~2,5 Mio
      Zeilen (~20 s jeder). Einmal lesen und im Speicher an alle drei
      Resample-Läufe geben würde reichen. (Inkrementell ist es egal — da wird
      nur der junge Rand gelesen.)

- [ ] **`chart.timeframe.v2` in `App.tsx`** ist ein Migrations-Schlüssel, der
      die gespeicherte Timeframe-Vorliebe einmalig auf `1d` zurücksetzt. Kann
      wieder auf `chart.timeframe` zurück, sobald sicher ist, dass jeder die
      neue Version einmal gestartet hat.

- [ ] **`nt8_import` Kreuzvergleich beim Re-Import des Frontkontrakts.**
      Liegt der Frontkontrakt schon in `ntbridge.sqlite3` und wird er
      erneut importiert, vergleicht der Kreuzvergleich den Export gegen
      seine *eigenen* schon geschriebenen Kerzen — die Prüfung wird trivial,
      und `nt8_import_nachweis.json` bekommt eine nichtssagende
      `gemeinsame_kerzen`-Zahl (nach dem Import-Lauf vom 30.08.2026 stand da
      75423 statt der echten 9310; von Hand korrigiert). Fix: nur gegen
      Referenzkerzen aus einer *anderen* `source` vergleichen
      (`BarStore.load_frame` müsste die Spalte durchreichen).

- [ ] **`ib_breakout` ist weiterhin nicht Pine-exportierbar** und
      `flag_breakout` auch nicht. Beide hängen an selbst gerechneten Spalten.
      Entweder in Pine nachbauen (dann muss die Übereinstimmung bewiesen
      werden) oder dabei belassen und dokumentieren.

- [x] ~~`requirements.txt` stimmt nicht mehr.~~ Erledigt 30.08.2026.
      *(Alter Text: fastapi, uvicorn und pywebview fehlten; anthropic und
      websockets standen drin, ohne benutzt zu werden.)*

- [x] ~~`ui/frontend/fix_app*.py`, `ui/terminal/`, `feature_store/`, leere
      `ntbridge.sqlite3` im Stamm.~~ Entfernt 30.08.2026 (bis auf
      `ui/terminal/`, siehe unten).

- [x] ~~Flackernder Test `test_empfaenger_lehnt_falschen_pfad_ab`.~~ Behoben
      30.08.2026 — und es war kein Testproblem: der Empfänger antwortete mit
      404, **bevor** er den Anfragekörper gelesen hatte. Wer antwortet und die
      Verbindung schließt, während der Client noch sendet, bricht dessen
      Sendevorgang ab (`WinError 10053`). Ein NinjaTrader, der auf einen
      falschen Pfad postet, sah damit einen Verbindungsabbruch statt der
      sauberen 404, die ihm gesagt hätte, was er falsch macht.

- [ ] **`ui/terminal/`** ist ein zweites, ungenutztes React-Gerüst aus der
      Antigravity-Phase. Kann weg, sobald sicher ist, dass nichts daraus
      gebraucht wird.


- [ ] **Order-Änderungen (`/api/orders/modify_pending`)** liefern immer eine
      leere Liste. Für einen nachziehenden Stop müsste das gebaut werden — das
      AddOn kann es bereits (`order_modify`).

## P3 — Später

- [ ] **Cross-Asset-Kontext** (VIX, DXY, Zinsen) über FRED, wie in
      `CODE_CHAT_KONTEXT.md` Abschnitt 31 vorgesehen. Ausdrücklich **nicht**
      über die NT8-Bridge — die bleibt MNQ-only.

- [ ] **Mehrfachtestkorrektur im Register.** `p_value_corrected` und
      `bonferroni_passed` existieren als Felder, werden von der neuen
      Research-Engine aber noch nicht gefüllt.

- [ ] **Replay-Modus** der Oberfläche (`ReplayControls.tsx` ist da, die
      Endpunkte `/api/step` und `/api/reset` sind Attrappen).

---

## Fragen an Laurin

- **Lucid-Zahlen** (siehe P0). *(300k-Frage ist geklärt: gibt es nicht.)*
*(Beantwortet am 30.08.2026: der Bot handelt mit `frei`; die Auswertung
gegen die Prop-Regelwerke passiert im Nachhinein über `auswertung/`. Push nach
GitHub freigegeben und ausgeführt.)*
