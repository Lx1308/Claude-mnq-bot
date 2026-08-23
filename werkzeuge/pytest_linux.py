"""Testlauf in einer Linux-Umgebung ohne eigenes pytest.

Wozu das gut ist
----------------
Die verbindliche Gegenprobe ist und bleibt der Windows-Lauf::

    .venv\\Scripts\\python.exe -m pytest

Unbeaufsichtigte Laeufe (geplante Aufgaben, Cowork-Sitzungen) arbeiten aber in
einer Linux-Sandbox, in der ``pip install`` am Paketproxy scheitert. Bis zum
23.08.2026 galt deshalb "die Testsuite laeuft dort nicht" -- und Aenderungen
blieben ungeprueft liegen, obwohl "Tests bleiben gruen" eine feste Regel des
Projekts ist.

Sie laeuft dort sehr wohl. Fast alle Testabhaengigkeiten sind reines Python und
liegen bereits im Windows-venv des Projekts; nur die kompilierten Pakete
(pandas, numpy) muessen aus der Linux-Umgebung selbst kommen. Dieses Skript
sammelt die reinen Python-Pakete in ein Scratch-Verzeichnis, ergaenzt einen
Minimalersatz fuer ``exceptiongroup`` (Python 3.10 bringt BaseExceptionGroup
noch nicht mit) und startet pytest darueber.

Aufruf::

    python3 werkzeuge/pytest_linux.py            # ganze Suite
    python3 werkzeuge/pytest_linux.py -k lookahead -v

Grenzen -- bitte nicht ueberdehnen
---------------------------------
Der Lauf findet unter Python 3.10 mit den *Linux*-Versionen von pandas und
numpy statt, nicht unter dem Python des Projekt-venv. Ein gruener Lauf hier
belegt, dass die Testlogik traegt; er ersetzt den Windows-Lauf **nicht** und
darf in der Dokumentation nicht als solcher ausgegeben werden (Invariante 10:
eine Naeherung darf nicht aussehen wie eine Messung).

Das Skript schreibt ausschliesslich nach ``/tmp`` und aendert nichts im
Projekt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJEKTWURZEL = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJEKTWURZEL / ".venv" / "Lib" / "site-packages"
SCRATCH = Path("/tmp/pytest_linux_pakete")

# Reine Python-Pakete aus dem Windows-venv. pandas und numpy stehen bewusst
# nicht dabei: die tragen kompilierte Endungen (.pyd) und sind unter Linux
# unbrauchbar; dort kommen sie aus der Umgebung selbst.
ZU_KOPIEREN = (
    "pytest",
    "_pytest",
    "pluggy",
    "iniconfig",
    "packaging",
    "py.py",
    "httpx",
    "httpcore",
    "h11",
    "certifi",
    "idna",
    "sniffio",
    "anyio",
    "yaml",
    "_yaml",
    "dotenv",
    "tabulate",
    "typing_extensions.py",
    "annotated_types",
    "six.py",
    "dateutil",
)

# Minimalersatz fuer das Paket exceptiongroup. Python 3.11+ hat
# BaseExceptionGroup eingebaut, 3.10 nicht, und das Backport ist in der
# gesperrten Umgebung nicht installierbar. pytest braucht davon nur
# isinstance-Pruefungen und das Buendeln mehrerer Fehler.
EXCEPTIONGROUP_ERSATZ = '''\
"""Minimalersatz fuer ``exceptiongroup`` unter Python 3.10 (siehe
werkzeuge/pytest_linux.py). Nur fuer Testlaeufe, nicht Teil des Projekts."""


class _Subscriptable(type):
    """RaisesGroup schreibt ``BaseExceptionGroup[T]`` auf Modulebene."""

    def __getitem__(cls, item):
        return cls


class BaseExceptionGroup(BaseException, metaclass=_Subscriptable):
    def __init__(self, message, exceptions):
        super().__init__(message, list(exceptions))
        self.message = message
        self.exceptions = tuple(exceptions)

    def __str__(self):
        return "%s (%d sub-exception%s)" % (
            self.message,
            len(self.exceptions),
            "" if len(self.exceptions) == 1 else "s",
        )

    def subgroup(self, cond):
        treffer = [e for e in self.exceptions if _passt(e, cond)]
        return type(self)(self.message, treffer) if treffer else None

    def split(self, cond):
        ja = [e for e in self.exceptions if _passt(e, cond)]
        nein = [e for e in self.exceptions if not _passt(e, cond)]
        return (
            type(self)(self.message, ja) if ja else None,
            type(self)(self.message, nein) if nein else None,
        )

    def derive(self, exceptions):
        return type(self)(self.message, exceptions)


class ExceptionGroup(BaseExceptionGroup, Exception):
    pass


def _passt(exc, cond):
    if isinstance(cond, (type, tuple)):
        return isinstance(exc, cond)
    return bool(cond(exc))


def format_exception(*args, **kwargs):
    import traceback

    return traceback.format_exception(*args, **kwargs)
'''


def vorbereiten() -> Path:
    """Scratch-Verzeichnis mit den reinen Python-Paketen aufbauen."""
    if not SITE_PACKAGES.is_dir():
        raise SystemExit(
            "site-packages des Projekt-venv nicht gefunden: %s\n"
            "Ohne das venv laesst sich pytest hier nicht zusammensuchen." % SITE_PACKAGES
        )

    if SCRATCH.exists():
        shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    fehlend = []
    for name in ZU_KOPIEREN:
        quelle = SITE_PACKAGES / name
        if not quelle.exists():
            fehlend.append(name)
            continue
        ziel = SCRATCH / name
        if quelle.is_dir():
            shutil.copytree(quelle, ziel)
        else:
            shutil.copy2(quelle, ziel)

    if fehlend:
        # Kein Abbruch: welche Pakete gebraucht werden, haengt an den Tests.
        # Ein fehlendes meldet sich beim Sammeln mit einem klaren ImportError.
        print("Hinweis: nicht im venv gefunden: %s" % ", ".join(fehlend), file=sys.stderr)

    # Der Mount setzt teils restriktive Rechte; kopierte Ordner sonst unlesbar.
    for pfad in SCRATCH.rglob("*"):
        try:
            pfad.chmod(pfad.stat().st_mode | 0o700)
        except OSError:
            pass

    # Vorkompilierte .pyc aus dem Windows-Python stiften nur Verwirrung.
    for cache in SCRATCH.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    (SCRATCH / "exceptiongroup.py").write_text(EXCEPTIONGROUP_ERSATZ, encoding="ascii")
    return SCRATCH


def main(argv: list[str]) -> int:
    scratch = vorbereiten()

    umgebung = dict(os.environ)
    umgebung["PYTHONPATH"] = os.pathsep.join([str(scratch), str(PROJEKTWURZEL)])

    befehl = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *argv]
    print("Testlauf (Linux-Ersatzumgebung, ersetzt den Windows-Lauf nicht)")
    ergebnis = subprocess.run(befehl, cwd=str(PROJEKTWURZEL), env=umgebung)
    return ergebnis.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
