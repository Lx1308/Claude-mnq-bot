"""Watchdog: nimmt die Arbeit wieder auf, wenn das Kontingent zurueck ist.

Was hier tatsaechlich moeglich ist - nachgesehen, nicht angenommen
------------------------------------------------------------------
Auf diesem Rechner liegt ``claude.exe`` (2.1.220) unter
``%USERPROFILE%\\.local\\bin\\``. Damit gibt es alles, was ein echter
Fortsetzungsmechanismus braucht:

* ``claude -p "..." --output-format json`` laeuft nicht-interaktiv und liefert
  ein auswertbares Ergebnis.
* ``claude -r <session-id>`` nimmt eine bestimmte Unterhaltung wieder auf.
* Die Sitzungen liegen als ``.jsonl`` unter
  ``%USERPROFILE%\\.claude\\projects\\<projekt>\\``; daraus laesst sich die
  zuletzt benutzte Sitzung bestimmen.

Es muss also nichts erfunden werden. Was NICHT geht: von aussen in eine
laufende interaktive Sitzung hineinschreiben - ein neuer Lauf ist immer ein
neuer Prozess, der eine bestehende Unterhaltung fortsetzt.

Die Sicherungen und warum jede einzelne noetig ist
--------------------------------------------------
Ein Watchdog, der Code aendern darf, ist ein Werkzeug mit scharfer Kante.

* **Sperre mit PID-Pruefung.** Zwei gleichzeitige Laeufe wuerden dieselbe
  Arbeit doppelt machen und sich gegenseitig die Dateien umschreiben. Die
  Sperre traegt die PID; ist der Prozess tot, gilt sie als verwaist und wird
  uebernommen - sonst blockierte ein Absturz den Watchdog fuer immer.
* **Tageslimit.** Eine Obergrenze an Laeufen je Tag. Ohne sie koennte ein
  Fehler in der Abbruchbedingung eine Endlosschleife erzeugen.
* **Notaus.** Existiert ``watchdog.stop``, laeuft nichts. Eine Datei, die
  Laurin von Hand anlegen kann, ohne irgendetwas zu bedienen.
* **Kein Push.** Der Watchdog committet lokal, aber schiebt nie nach GitHub -
  Laurins ausdrueckliche Ansage vom 29.08.2026.
* **Zustand auf der Platte.** ``data/watchdog.json`` haelt fest, was zuletzt
  lief und wie es ausging. Nach einem Neustart weiss der Watchdog, wo er war.

Aufruf
------
    python werkzeuge/watchdog.py status
    python werkzeuge/watchdog.py pruefen      # nur nachsehen, nichts starten
    python werkzeuge/watchdog.py lauf         # einen Durchgang
    python werkzeuge/watchdog.py einrichten   # Windows-Aufgabe anlegen
    python werkzeuge/watchdog.py entfernen    # Windows-Aufgabe loeschen
    python werkzeuge/watchdog.py stopp        # Notaus setzen
    python werkzeuge/watchdog.py weiter       # Notaus loesen
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZUSTAND = PROJECT_ROOT / "data" / "watchdog.json"
SPERRE = PROJECT_ROOT / "data" / "watchdog.lock"
NOTAUS = PROJECT_ROOT / "watchdog.stop"
PROTOKOLL = PROJECT_ROOT / "logs" / "watchdog.log"
AUFTRAG = PROJECT_ROOT / "WATCHDOG_AUFTRAG.md"

AUFGABENNAME = "ClaudeChartBot-Watchdog"

#: Hoechstens so viele Laeufe je Kalendertag. Nicht als Kostenbremse gedacht,
#: sondern als Riegel gegen eine kaputte Abbruchbedingung.
MAX_LAEUFE_JE_TAG = 12

#: Wie lange ein einzelner Lauf hoechstens dauern darf. Danach wird er
#: abgebrochen - ein haengender Prozess wuerde die Sperre halten und jeden
#: weiteren Lauf verhindern.
ZEITGRENZE_SEKUNDEN = 4 * 60 * 60

CLAUDE = Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "claude.exe"


# ---------------------------------------------------------------------------
# Zustand
# ---------------------------------------------------------------------------

def lies_zustand() -> dict[str, Any]:
    if not ZUSTAND.exists():
        return {"laeufe": {}, "letzter_lauf": None, "letztes_ergebnis": None}
    try:
        return json.loads(ZUSTAND.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Ein kaputter Zustand darf den Watchdog nicht dauerhaft lahmlegen -
        # aber er soll auffallen.
        protokolliere("WARNUNG: Zustandsdatei unlesbar, beginne von vorn.")
        return {"laeufe": {}, "letzter_lauf": None, "letztes_ergebnis": None}


def schreibe_zustand(zustand: dict[str, Any]) -> None:
    ZUSTAND.parent.mkdir(parents=True, exist_ok=True)
    # Erst daneben schreiben, dann umbenennen: ein Absturz mitten im Schreiben
    # hinterlaesst sonst eine halbe Datei.
    vorlaeufig = ZUSTAND.with_suffix(".json.tmp")
    vorlaeufig.write_text(json.dumps(zustand, indent=2), encoding="utf-8")
    vorlaeufig.replace(ZUSTAND)


def protokolliere(text: str) -> None:
    PROTOKOLL.parent.mkdir(parents=True, exist_ok=True)
    zeile = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {text}"
    with PROTOKOLL.open("a", encoding="utf-8") as datei:
        datei.write(zeile + "\n")
    print(zeile)


# ---------------------------------------------------------------------------
# Sperre
# ---------------------------------------------------------------------------

def _prozess_laeuft(pid: int) -> bool:
    """Laeuft dieser Prozess noch?

    Ohne diese Pruefung wuerde eine verwaiste Sperre - etwa nach einem
    Stromausfall - den Watchdog dauerhaft blockieren.
    """
    try:
        ergebnis = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
        )
        return str(pid) in ergebnis.stdout
    except Exception:  # noqa: BLE001
        # Im Zweifel als laufend behandeln: lieber ein Lauf zu wenig als zwei
        # gleichzeitig.
        return True


def sperre_nehmen() -> bool:
    SPERRE.parent.mkdir(parents=True, exist_ok=True)
    if SPERRE.exists():
        try:
            alt = json.loads(SPERRE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            alt = {}
        pid = int(alt.get("pid", 0))
        if pid and _prozess_laeuft(pid):
            protokolliere(f"Sperre gehalten von PID {pid} - dieser Lauf entfaellt.")
            return False
        protokolliere(f"Verwaiste Sperre von PID {pid} uebernommen.")

    SPERRE.write_text(
        json.dumps({
            "pid": os.getpid(),
            "seit_utc": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )
    return True


def sperre_freigeben() -> None:
    try:
        SPERRE.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Kontingent
# ---------------------------------------------------------------------------

def claude_laeuft_bereits() -> tuple[bool, str]:
    """Laeuft schon eine Claude-Code-Sitzung?

    Der wichtigste Riegel ueberhaupt. Die Sperre oben verhindert zwei
    WATCHDOG-Laeufe; sie weiss aber nichts von einer Sitzung, die Laurin
    selbst offen hat oder die noch von vorhin laeuft. Wuerde der Watchdog
    dort hineinstarten, arbeiteten zwei Instanzen gleichzeitig an denselben
    Dateien - und die spaetere ueberschriebe die Aenderungen der frueheren,
    ohne dass es jemand merkt.

    Deshalb: laeuft irgendein claude.exe, tut der Watchdog nichts.
    """
    try:
        ergebnis = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq claude.exe", "/NH"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as fehler:  # noqa: BLE001
        # Im Zweifel nicht starten. Ein ausgefallener Lauf kostet eine Stunde,
        # zwei gleichzeitige koennen einen Arbeitstag kosten.
        return True, f"Prozesspruefung fehlgeschlagen ({fehler}) - kein Start"

    zeilen = [z for z in ergebnis.stdout.splitlines() if "claude.exe" in z.lower()]
    if zeilen:
        return True, f"{len(zeilen)} Claude-Code-Sitzung(en) laufen bereits"
    return False, "keine laufende Sitzung"


def kontingent_verfuegbar() -> tuple[bool, str]:
    """Antwortet Claude gerade, oder ist das Kontingent aufgebraucht?

    Geprueft wird mit dem kleinstmoeglichen echten Aufruf. Es gibt keinen
    Endpunkt, der das Kontingent ohne Verbrauch meldet - also wird ein Lauf
    gemacht, der so wenig wie moeglich kostet.
    """
    if not CLAUDE.exists():
        return False, f"claude.exe nicht gefunden unter {CLAUDE}"

    try:
        ergebnis = subprocess.run(
            [str(CLAUDE), "-p", "ok", "--output-format", "json"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "Zeitueberschreitung bei der Probe"
    except Exception as fehler:  # noqa: BLE001
        return False, f"Probe fehlgeschlagen: {fehler}"

    ausgabe = (ergebnis.stdout or "") + (ergebnis.stderr or "")
    unten = ausgabe.lower()
    for hinweis in ("usage limit", "rate limit", "limit reached",
                    "quota", "kontingent"):
        if hinweis in unten:
            return False, f"Kontingent erschoepft ({hinweis})"

    if ergebnis.returncode != 0:
        return False, f"Rueckgabewert {ergebnis.returncode}: {ausgabe[:200]}"
    return True, "Kontingent verfuegbar"


# ---------------------------------------------------------------------------
# Arbeit
# ---------------------------------------------------------------------------

def letzte_sitzung() -> str | None:
    """Die zuletzt benutzte Sitzungskennung dieses Projekts."""
    ordner = (
        Path(os.environ.get("USERPROFILE", "")) / ".claude" / "projects"
        / "C--Users-lm130-Desktop-Claude-chart-bot"
    )
    if not ordner.exists():
        return None
    sitzungen = sorted(
        ordner.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return sitzungen[0].stem if sitzungen else None


def auftrag_lesen() -> str:
    """Was der Watchdog fortsetzen soll.

    Steht in einer Datei und nicht im Code: so kann Laurin den Auftrag
    aendern, ohne etwas zu programmieren, und im Protokoll ist nachlesbar,
    womit ein Lauf gestartet wurde.
    """
    if AUFTRAG.exists():
        return AUFTRAG.read_text(encoding="utf-8").strip()
    return (
        "Setze die Arbeit am Projekt fort. Lies zuerst CODE_CHAT_KONTEXT.md "
        "Abschnitt 34 und den Abschnitt 'Noch offen' darin. Arbeite den "
        "naechsten offenen Punkt ab, fuehre die Tests aus und committe lokal. "
        "PUSHE NICHTS nach GitHub."
    )


def lauf_ausfuehren(trocken: bool = False) -> dict[str, Any]:
    """Ein Durchgang: pruefen, ob etwas zu tun ist, und Claude starten."""
    heute = date.today().isoformat()
    zustand = lies_zustand()
    heutige = int(zustand.get("laeufe", {}).get(heute, 0))

    if NOTAUS.exists():
        return {"getan": False, "grund": f"Notaus gesetzt ({NOTAUS.name})"}

    if heutige >= MAX_LAEUFE_JE_TAG:
        return {
            "getan": False,
            "grund": f"Tageslimit erreicht ({heutige}/{MAX_LAEUFE_JE_TAG})",
        }

    laeuft, wer = claude_laeuft_bereits()
    if laeuft:
        return {"getan": False, "grund": wer}

    verfuegbar, grund = kontingent_verfuegbar()
    if not verfuegbar:
        zustand["letztes_ergebnis"] = grund
        zustand["letzte_pruefung_utc"] = datetime.now(timezone.utc).isoformat()
        schreibe_zustand(zustand)
        return {"getan": False, "grund": grund}

    if trocken:
        return {"getan": False, "grund": "Probelauf - " + grund}

    sitzung = letzte_sitzung()
    befehl = [str(CLAUDE)]
    if sitzung:
        befehl += ["-r", sitzung]
    befehl += [
        "-p", auftrag_lesen(),
        "--permission-mode", "bypassPermissions",
        "--output-format", "json",
    ]

    protokolliere(
        f"Starte Lauf {heutige + 1}/{MAX_LAEUFE_JE_TAG}"
        + (f" (setzt Sitzung {sitzung} fort)" if sitzung else " (neue Sitzung)")
    )

    begonnen = datetime.now(timezone.utc)
    try:
        ergebnis = subprocess.run(
            befehl, cwd=PROJECT_ROOT, capture_output=True, text=True,
            timeout=ZEITGRENZE_SEKUNDEN,
        )
        ausgang = f"Rueckgabewert {ergebnis.returncode}"
        auszug = (ergebnis.stdout or ergebnis.stderr or "")[-2000:]
    except subprocess.TimeoutExpired:
        ausgang = f"Abgebrochen nach {ZEITGRENZE_SEKUNDEN}s"
        auszug = ""

    dauer = (datetime.now(timezone.utc) - begonnen).total_seconds()
    zustand.setdefault("laeufe", {})[heute] = heutige + 1
    zustand["letzter_lauf"] = begonnen.isoformat()
    zustand["letztes_ergebnis"] = ausgang
    zustand["letzte_sitzung"] = sitzung
    zustand["letzte_dauer_sekunden"] = dauer
    schreibe_zustand(zustand)

    protokolliere(f"Lauf beendet nach {dauer:.0f}s: {ausgang}")
    if auszug:
        protokolliere("  Auszug: " + auszug.replace("\n", " ")[:400])
    return {"getan": True, "grund": ausgang, "dauer_sekunden": dauer}


# ---------------------------------------------------------------------------
# Windows-Aufgabe
# ---------------------------------------------------------------------------

def aufgabe_einrichten(stunden: int = 1) -> int:
    """Legt die geplante Aufgabe an, die stuendlich nachsieht."""
    python = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not python.exists():
        python = Path(sys.executable)

    befehl = f'"{python}" "{PROJECT_ROOT / "werkzeuge" / "watchdog.py"}" lauf'
    ergebnis = subprocess.run(
        [
            "schtasks", "/Create", "/TN", AUFGABENNAME, "/TR", befehl,
            "/SC", "HOURLY", "/MO", str(stunden), "/F",
        ],
        capture_output=True, text=True,
    )
    print(ergebnis.stdout or ergebnis.stderr)
    if ergebnis.returncode == 0:
        protokolliere(f"Aufgabe {AUFGABENNAME} eingerichtet (alle {stunden} h).")
        print(
            "\nZum Anhalten ohne die Aufgabe zu loeschen:\n"
            f"  python werkzeuge/watchdog.py stopp\n"
            "Zum vollstaendigen Entfernen:\n"
            "  python werkzeuge/watchdog.py entfernen"
        )
    return ergebnis.returncode


def aufgabe_entfernen() -> int:
    ergebnis = subprocess.run(
        ["schtasks", "/Delete", "/TN", AUFGABENNAME, "/F"],
        capture_output=True, text=True,
    )
    print(ergebnis.stdout or ergebnis.stderr)
    return ergebnis.returncode


def status_zeigen() -> None:
    zustand = lies_zustand()
    heute = date.today().isoformat()

    print("Watchdog")
    print(f"  claude.exe        : {CLAUDE} {'(da)' if CLAUDE.exists() else '(FEHLT)'}")
    print(f"  Notaus            : {'GESETZT' if NOTAUS.exists() else 'nicht gesetzt'}")
    print(f"  Sperre            : {'gehalten' if SPERRE.exists() else 'frei'}")
    laeuft, wer = claude_laeuft_bereits()
    print(f"  Laufende Sitzung  : {wer}")
    print(f"  Laeufe heute      : {zustand.get('laeufe', {}).get(heute, 0)}"
          f" / {MAX_LAEUFE_JE_TAG}")
    print(f"  Letzter Lauf      : {zustand.get('letzter_lauf') or '-'}")
    print(f"  Letztes Ergebnis  : {zustand.get('letztes_ergebnis') or '-'}")
    print(f"  Letzte Sitzung    : {zustand.get('letzte_sitzung') or '-'}")
    print(f"  Auftragsdatei     : {AUFTRAG.name}"
          f" {'(da)' if AUFTRAG.exists() else '(Vorgabetext)'}")

    ergebnis = subprocess.run(
        ["schtasks", "/Query", "/TN", AUFGABENNAME],
        capture_output=True, text=True,
    )
    print(f"  Windows-Aufgabe   : "
          f"{'eingerichtet' if ergebnis.returncode == 0 else 'nicht eingerichtet'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="watchdog")
    parser.add_argument(
        "befehl",
        choices=["status", "pruefen", "lauf", "einrichten", "entfernen",
                 "stopp", "weiter"],
    )
    parser.add_argument("--stunden", type=int, default=1)
    args = parser.parse_args(argv)

    if args.befehl == "status":
        status_zeigen()
        return 0
    if args.befehl == "einrichten":
        return aufgabe_einrichten(args.stunden)
    if args.befehl == "entfernen":
        return aufgabe_entfernen()
    if args.befehl == "stopp":
        NOTAUS.write_text(
            f"Angehalten am {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.\n"
            "Diese Datei loeschen oder 'watchdog.py weiter' aufrufen.\n",
            encoding="utf-8",
        )
        protokolliere("Notaus gesetzt.")
        return 0
    if args.befehl == "weiter":
        NOTAUS.unlink(missing_ok=True)
        protokolliere("Notaus geloest.")
        return 0

    if not sperre_nehmen():
        return 1
    try:
        ergebnis = lauf_ausfuehren(trocken=(args.befehl == "pruefen"))
        print(("Gestartet: " if ergebnis["getan"] else "Nichts getan: ")
              + ergebnis["grund"])
        return 0
    finally:
        sperre_freigeben()


if __name__ == "__main__":
    raise SystemExit(main())
