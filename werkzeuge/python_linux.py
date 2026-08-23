"""Beliebige Projektmodule in einer Linux-Umgebung ohne eigenes venv starten.

Wozu das gut ist
----------------
``werkzeuge/pytest_linux.py`` hat gezeigt, dass sich die Testsuite in der
Linux-Sandbox betreiben laesst, indem man die reinen Python-Pakete aus dem
Windows-venv einsammelt und pandas/numpy aus der Linux-Umgebung nimmt. Dasselbe
gilt fuer den Rest des Projekts: die Backtest-CLI, ``pruefe_datenluecken.py``
und die Ideen-Erkennung brauchen keine anderen Pakete als die Tests.

Dieses Skript macht daraus ein allgemeines Werkzeug, statt die Sammellogik ein
zweites Mal hinzuschreiben -- es ruft ``pytest_linux.vorbereiten`` auf und
startet damit ein beliebiges Modul oder Skript.

Aufruf::

    python3 werkzeuge/python_linux.py -m backtest.cli list
    python3 werkzeuge/python_linux.py -m backtest.cli compare --symbol DEMO \\
        --csv data/DEMO_1m.csv
    python3 werkzeuge/python_linux.py eigenes_skript.py

Grenzen -- bitte nicht ueberdehnen
---------------------------------
Wie beim Testlauf gilt: Python 3.10 statt 3.14, Linux-Versionen von pandas und
numpy statt der des venv. Ergebnisse aus dieser Umgebung sind eine
**Gegenprobe**, kein Ersatz fuer den Lauf unter ``.venv\\Scripts\\python.exe``,
und duerfen in der Dokumentation nicht als solcher ausgegeben werden
(Invariante 10).

Geschrieben wird ausschliesslich nach ``/tmp``; am Projekt aendert das Skript
nichts. Was das gestartete Modul selbst schreibt, verantwortet dieses Modul.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pytest_linux import PROJEKTWURZEL, vorbereiten  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2

    scratch = vorbereiten()

    umgebung = dict(os.environ)
    umgebung["PYTHONPATH"] = os.pathsep.join([str(scratch), str(PROJEKTWURZEL)])

    print(
        "Lauf in der Linux-Ersatzumgebung (Python %d.%d) -- ersetzt den "
        "Windows-Lauf nicht." % sys.version_info[:2],
        file=sys.stderr,
    )
    ergebnis = subprocess.run(
        [sys.executable, *argv], cwd=str(PROJEKTWURZEL), env=umgebung
    )
    return ergebnis.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
