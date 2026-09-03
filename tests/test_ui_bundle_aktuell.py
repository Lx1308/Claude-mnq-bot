"""Der ausgelieferte Bundle muss zum Quelltext passen.

WAS AM 03.09.2026 PASSIERTE
---------------------------
Der Order-Bracket-Fehler vom 02.09.2026 war im Quelltext behoben
(``ui/frontend/src/panels/OrderPanel.tsx`` schickt seither ``stop_loss_points``
statt ``stop_loss``), im laufenden System aber nicht: die Oberflaeche wird aus
``ui/frontend/dist/`` ausgeliefert, und dort lag noch der Bundle vom
31.08.2026. Laurin hat NinjaTrader neu kompiliert und die App neu gestartet -
beides half nichts, weil das Frontend GEBAUT werden muss, nicht kompiliert.

Der Fehler bestand also nach dem "Fix" unveraendert weiter, und nichts hat
darauf hingewiesen. Genau die Sorte stillen Ausfalls, gegen die dieses
Projekt sonst ueberall Startpruefungen hat.

    .venv\\Scripts\\python.exe -m pytest tests/test_ui_bundle_aktuell.py

BEHEBEN
-------
    cd ui\\frontend && npm run build

WARUM UEBER DIE ZEITSTEMPEL
---------------------------
Ein Test auf einzelne Feldnamen wuerde nur diesen einen Fehler abfangen. Der
Vergleich der Aenderungszeiten faengt JEDE Quelltextaenderung, die nie gebaut
wurde - auch die, an die heute niemand denkt.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = WURZEL / "ui" / "frontend" / "src"
BUNDLE = WURZEL / "ui" / "frontend" / "dist"

#: Toleranz in Sekunden. Nach einem frischen ``git clone`` tragen alle Dateien
#: praktisch dieselbe Zeit; ohne Spielraum waere der Test dort zufaellig rot.
TOLERANZ_S = 120


def _neueste(pfad: Path, muster: str = "**/*") -> tuple[float, Path | None]:
    neuste_zeit, neuste_datei = 0.0, None
    for datei in pfad.glob(muster):
        if not datei.is_file():
            continue
        zeit = datei.stat().st_mtime
        if zeit > neuste_zeit:
            neuste_zeit, neuste_datei = zeit, datei
    return neuste_zeit, neuste_datei


def test_bundle_ist_nicht_aelter_als_der_quelltext():
    """Sonst laeuft die Oberflaeche auf einem alten Stand."""
    if not BUNDLE.exists():
        pytest.skip(
            "ui/frontend/dist fehlt - die Oberflaeche wurde noch nie gebaut. "
            "Das ist kein Fehler dieses Tests; ohne Bundle liefert der Server "
            "gar keine Oberflaeche aus und sagt das beim Start."
        )
    quell_zeit, quell_datei = _neueste(QUELLE)
    bundle_zeit, _ = _neueste(BUNDLE)
    assert quell_datei is not None, "keine Quelldateien gefunden"

    assert bundle_zeit + TOLERANZ_S >= quell_zeit, (
        f"Der ausgelieferte Bundle ist aelter als der Quelltext.\n"
        f"  neueste Quelldatei: {quell_datei.relative_to(WURZEL)}\n"
        f"  Unterschied:        {(quell_zeit - bundle_zeit) / 3600:.1f} Stunden\n"
        f"\n"
        f"Die Oberflaeche laeuft damit auf einem alten Stand - Aenderungen an\n"
        f"den .tsx-Dateien wirken erst nach einem Build. Beheben mit:\n"
        f"    cd ui\\frontend && npm run build"
    )


def test_der_bracket_fix_steckt_im_bundle():
    """Der konkrete Fehler vom 02.09.2026, im AUSGELIEFERTEN Stand geprueft.

    Das Panel schickt Abstaende in Punkten. Gehen sie als ``stop_loss`` raus -
    ein Feld, das absolute Kurse meint -, legt NinjaTrader ein Verkaufslimit
    bei Kurs 40 an, das sofort ausfuehrbar ist. Genau so wurde am 02.09. eine
    Position eine Sekunde nach dem Einstieg wieder geschlossen.
    """
    if not BUNDLE.exists():
        pytest.skip("ui/frontend/dist fehlt")
    skripte = list((BUNDLE / "assets").glob("*.js"))
    assert skripte, "kein JavaScript im Bundle"
    text = "\n".join(s.read_text(encoding="utf-8", errors="ignore")
                     for s in skripte)

    assert "stop_loss_points" in text and "take_profit_points" in text, (
        "Der gebaute Bundle schickt keine Abstaende. Bitte neu bauen:\n"
        "    cd ui\\frontend && npm run build"
    )
    # Das Order-Panel darf die Abstandsfelder NICHT unter den Kursnamen
    # schicken. Der Bot tut das weiterhin - der arbeitet aber serverseitig
    # und taucht in diesem Bundle nicht auf.
    assert "stop_loss:" not in text, (
        "Im Bundle steht noch das Kursfeld 'stop_loss:' - das ist der alte "
        "Stand vom 31.08.2026, der die Position sofort wieder schloss."
    )
