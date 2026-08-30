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
- [x] **P1** Pine-Export und TradingView-Ergebnisimport
- [x] **P1** Research-Engine neu (Split, Kosten, Register, ehrliches Protokoll)
- [x] **P1** Watchdog mit Sperre, Tageslimit, Notaus und Parallelitätsprüfung
- [x] **P0** Dokumentation: Projektgrenze aufgehoben, in `CLAUDE.md`,
      `MASTERPLAN.md` und `CODE_CHAT_KONTEXT.md` nachgezogen

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

- [ ] **NT8-Historie tatsächlich importieren.** Das Werkzeug steht
      (`werkzeuge/nt8_import.py`), der Export fehlt. NinjaTrader hält
      MNQ-Minutendaten von 30 Kontrakten zurück bis 2019 vor.
      Ablauf: NT8 → Tools → Historical Data → Export, dann
      `nt8_import.py <datei>` (prüft), dann `--schreiben`.
      Danach sind die Backtests auf Jahren statt auf zehn Tagen.

- [ ] **Erst danach: Hypothesen ernsthaft rechnen.** Auf zehn Tagen sind alle
      Urteile „UNENTSCHIEDEN" (unter 30 Trades). Mit Jahreshistorie werden die
      p-Werte erst aussagekräftig — und die Mehrfachtestkorrektur nötig.

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
