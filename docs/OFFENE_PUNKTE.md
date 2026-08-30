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
      Offen ist außerdem, ob es eine 300k-Stufe gibt; in keiner der beiden
      Quellen taucht sie auf.

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

- [ ] **MAE/MFE der Live-Trades nachrechnen.** `execution/store.py` lässt sie
      leer, weil sie den Kursverlauf während des Trades brauchen.
      `backtest/excursions.py` kann das — ein Nachlauf, der die Kerzen des
      Trade-Zeitraums holt und die Felder füllt.

## P2 — Aufräumen und Härten

- [ ] **`ib_breakout` ist weiterhin nicht Pine-exportierbar** und
      `flag_breakout` auch nicht. Beide hängen an selbst gerechneten Spalten.
      Entweder in Pine nachbauen (dann muss die Übereinstimmung bewiesen
      werden) oder dabei belassen und dokumentieren.

- [ ] **`test_empfaenger_lehnt_falschen_pfad_ab` ist flaky.** Fiel am
      30.08.2026 einmal mit `ConnectionAbortedError [WinError 10053]` aus und
      lief beim nächsten Versuch durch. Ein echter Socket in einem Test; die
      Ursache ist ein Zeitproblem beim Verbindungsabbau unter Windows.

- [ ] **`requirements.txt` stimmt nicht mehr.** `fastapi`, `uvicorn`,
      `pywebview` und `starlette` fehlen, obwohl die App sie braucht — ein
      frisches Aufsetzen scheitert. `anthropic` und `websockets` stehen drin,
      werden aber nirgends benutzt (der Anthropic-Import ist repo-weit
      verboten und getestet).

- [ ] **`ui/frontend/fix_app*.py` und `ui/terminal/`** sind Reste aus der
      Antigravity-Phase: acht Wegwerf-Skripte, die einmal eine Textersetzung
      im Frontend gemacht haben, und ein zweites, ungenutztes React-Gerüst.

- [ ] **`feature_store/`** enthält nur noch ein `__pycache__` — das Modul
      selbst ist weg. Entweder wiederherstellen oder den Ordner entfernen.

- [ ] **Leere `ntbridge.sqlite3` im Projektstamm** (0 Byte, 29.08.). Entstand,
      weil etwas mit einem relativen Pfad aus dem falschen Arbeitsverzeichnis
      geöffnet wurde. Die echte Datei liegt unter `data/`.

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

- **Lucid-Zahlen** (siehe P0) — und ob es eine 300k-Stufe gibt.
- **Handelt der Bot ab Montag mit einem Lucid-Profil oder mit `frei`?**
  Vorgabe steht auf `frei` mit selbst gesetzten Grenzen (1.800 USD gesamt,
  600 USD je Tag, 150 USD je Trade), weil ein Lucid-25k mit den aktuellen
  5m-Setups rechnerisch nicht funktioniert — ein einzelner Micro-Kontrakt
  riskiert dort 11,9 % des Puffers. Details in `CODE_CHAT_KONTEXT.md` 34.4.
- **Push nach GitHub:** Die lokalen Commits seit `fd29411` sind nicht gepusht.
  Freigabe erteilen, wenn der Stand als „laufende Version" gelten soll.
