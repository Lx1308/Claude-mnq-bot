"""Die Beurteilungsseite fuer den Referenzsatz.

Ein kleiner lokaler Server, weil eine reine HTML-Datei nicht in eine
SQLite-Datei schreiben kann. Er tut genau drei Dinge: Seite ausliefern, Bilder
ausliefern, Urteile speichern. Kein Netzzugang, keine Abhaengigkeiten ausser
der Standardbibliothek.

    .venv\\Scripts\\python.exe -m werkzeuge.w_referenz_server
    -> http://127.0.0.1:8795

Tastatur: 1 = Ja, 2 = Nein, 3 = Unklar, Pfeil links = zurueck.

Jedes Urteil wird sofort geschrieben. Wer die Seite schliesst und spaeter
wiederkommt, macht dort weiter, wo er aufgehoert hat.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from werkzeuge.w_referenz import (
    BILDER,
    MUSTERART,
    REFERENZ_DB,
    URTEILE_CSV,
    oeffne_db,
    schreibe_urteile_csv,
)

SEITE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<title>Ist das ein W?</title>
<style>
 :root { color-scheme: dark; }
 body { margin:0; background:#0e1013; color:#e6e8eb; font:14px/1.5
        system-ui,-apple-system,"Segoe UI",sans-serif; }
 header { padding:14px 20px; border-bottom:1px solid #23272f;
          display:flex; align-items:center; gap:20px; flex-wrap:wrap; }
 h1 { font-size:15px; margin:0; font-weight:600; letter-spacing:.02em; }
 .zaehler { color:#8b93a0; font-variant-numeric:tabular-nums; }
 .balken { flex:1; min-width:160px; height:5px; background:#23272f;
           border-radius:3px; overflow:hidden; }
 .balken i { display:block; height:100%; background:#5aa9e6; width:0;
             transition:width .15s; }
 main { padding:20px; max-width:1180px; margin:0 auto; }
 figure { margin:0; background:#14161a; border:1px solid #23272f;
          border-radius:8px; overflow:hidden; }
 img { display:block; width:100%; height:auto; }
 .knoepfe { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; }
 button { flex:1; min-width:140px; padding:14px 18px; font-size:15px;
          font-weight:600; border:1px solid #2a2f38; border-radius:8px;
          background:#1a1d23; color:#e6e8eb; cursor:pointer; }
 button:hover { border-color:#3a414d; background:#20242b; }
 button b { display:block; font-size:11px; font-weight:500; color:#8b93a0;
            margin-top:3px; }
 #ja:hover  { border-color:#26a96a; }
 #nein:hover{ border-color:#d1465a; }
 .zurueck { flex:0 0 auto; min-width:auto; padding:14px; }
 .hinweis { margin-top:18px; color:#8b93a0; font-size:12.5px;
            border-top:1px solid #23272f; padding-top:14px; }
 .fertig { text-align:center; padding:60px 20px; }
 .fertig h2 { color:#26a96a; }
 code { background:#1a1d23; padding:2px 6px; border-radius:4px;
        font-size:12px; }
</style></head><body>
<header>
  <h1>Ist das ein W?</h1>
  <div class="balken"><i id="fortschritt"></i></div>
  <div class="zaehler" id="zaehler">...</div>
</header>
<main id="inhalt"><p class="zaehler">wird geladen ...</p></main>
<script>
let liste = [], pos = 0, fertig = 0, gesamt = 0;

async function start() {
  const r = await fetch('/stand');
  const d = await r.json();
  liste = d.offen; gesamt = d.gesamt; fertig = d.gesamt - d.offen.length;
  zeichne();
}

function zeichne() {
  const i = document.getElementById('inhalt');
  document.getElementById('zaehler').textContent =
    fertig + ' / ' + gesamt + ' beurteilt';
  document.getElementById('fortschritt').style.width =
    (gesamt ? fertig / gesamt * 100 : 0) + '%';
  if (pos >= liste.length) {
    i.innerHTML = '<div class="fertig"><h2>Fertig.</h2>' +
      '<p>Alle ' + gesamt + ' Fenster sind beurteilt. ' +
      'Die Urteile stehen in <code>data/w_referenz_urteile.csv</code>.</p></div>';
    return;
  }
  const f = liste[pos];
  i.innerHTML =
    '<figure><img src="/bild/' + f.bild + '" alt=""></figure>' +
    '<div class="knoepfe">' +
      '<button class="zurueck" id="zurueck" title="zurueck">&#8592;</button>' +
      '<button id="ja">Ja, ein W<b>Taste 1</b></button>' +
      '<button id="nein">Nein<b>Taste 2</b></button>' +
      '<button id="unklar">Unklar<b>Taste 3</b></button>' +
    '</div>' +
    '<p class="hinweis">Der helle Streifen links ist der Vorlauf, die gelbe ' +
    'Linie die Durchschnittslinie. Die Reihe endet mit der Formation &mdash; ' +
    'wie es weitergeht, ist absichtlich nicht zu sehen. Beurteilt wird die ' +
    'Form, nicht der Ausgang.</p>';
  document.getElementById('ja').onclick = () => werte('ja');
  document.getElementById('nein').onclick = () => werte('nein');
  document.getElementById('unklar').onclick = () => werte('unklar');
  document.getElementById('zurueck').onclick = zurueck;
}

async function werte(urteil) {
  const f = liste[pos];
  await fetch('/urteil', {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({start: f.start, ende: f.ende, urteil: urteil})});
  fertig++; pos++; zeichne();
}

function zurueck() { if (pos > 0) { pos--; fertig--; zeichne(); } }

document.addEventListener('keydown', e => {
  if (pos >= liste.length) return;
  if (e.key === '1') werte('ja');
  else if (e.key === '2') werte('nein');
  else if (e.key === '3') werte('unklar');
  else if (e.key === 'ArrowLeft') zurueck();
});

start();
</script></body></html>
"""


class Griff(BaseHTTPRequestHandler):
    """Handler. Alles synchron - es sitzt genau ein Mensch davor."""

    def log_message(self, *_args) -> None:      # keine Zugriffszeilen
        pass

    def _sende(self, status: int, typ: str, koerper: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(koerper)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(koerper)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._sende(200, "text/html; charset=utf-8", SEITE.encode("utf-8"))
        elif self.path == "/stand":
            self._sende(200, "application/json", json.dumps(_stand()).encode())
        elif self.path.startswith("/bild/"):
            self._bild(self.path[len("/bild/"):])
        else:
            self._sende(404, "text/plain; charset=utf-8", b"nicht gefunden")

    def _bild(self, name: str) -> None:
        # Nur Dateinamen aus der Ablage, kein Pfad von aussen.
        pfad = (BILDER / Path(name).name).resolve()
        if pfad.parent != BILDER.resolve() or not pfad.is_file():
            self._sende(404, "text/plain; charset=utf-8", b"kein Bild")
            return
        self._sende(200, "image/png", pfad.read_bytes())

    def do_POST(self) -> None:
        if self.path != "/urteil":
            self._sende(404, "text/plain; charset=utf-8", b"nicht gefunden")
            return
        laenge = int(self.headers.get("Content-Length", 0))
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}")
            urteil = str(daten["urteil"])
            if urteil not in ("ja", "nein", "unklar"):
                raise ValueError(f"unbekanntes Urteil {urteil!r}")
            _speichere(str(daten["start"]), str(daten["ende"]), urteil)
        except (KeyError, ValueError, sqlite3.Error) as fehler:
            self._sende(400, "application/json",
                        json.dumps({"fehler": str(fehler)}).encode())
            return
        self._sende(200, "application/json", b'{"ok":true}')


def _stand() -> dict:
    """Was noch offen ist - ohne die Klasse zu verraten.

    ``art`` wird bewusst NICHT ausgeliefert. Stuende sie im JSON, waere sie
    im Browser sichtbar, und der Referenzsatz waere wertlos.
    """
    con = oeffne_db()
    try:
        gesamt = con.execute(
            "SELECT COUNT(*) FROM fenster WHERE musterart = ?",
            (MUSTERART,)).fetchone()[0]
        zeilen = con.execute(
            "SELECT f.fenster_start, f.fenster_ende, f.bild FROM fenster f "
            "WHERE f.musterart = ? AND NOT EXISTS ("
            "  SELECT 1 FROM urteile u WHERE u.musterart = f.musterart"
            "  AND u.fenster_start = f.fenster_start"
            "  AND u.fenster_ende = f.fenster_ende) "
            "ORDER BY f.reihenfolge", (MUSTERART,)).fetchall()
    finally:
        con.close()
    return {
        "gesamt": gesamt,
        "offen": [{"start": r["fenster_start"], "ende": r["fenster_ende"],
                   "bild": r["bild"]} for r in zeilen],
    }


def _speichere(start: str, ende: str, urteil: str) -> None:
    con = oeffne_db()
    try:
        with con:
            treffer = con.execute(
                "SELECT 1 FROM fenster WHERE musterart = ? AND fenster_start = ?"
                " AND fenster_ende = ?", (MUSTERART, start, ende)).fetchone()
            if treffer is None:
                raise ValueError(f"unbekanntes Fenster {start} .. {ende}")
            con.execute(
                "INSERT OR REPLACE INTO urteile "
                "(musterart, fenster_start, fenster_ende, urteil, ts) "
                "VALUES (?,?,?,?,?)",
                (MUSTERART, start, ende, urteil,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
    finally:
        con.close()
    # Nach JEDEM Urteil, nicht erst am Ende: die SQLite-Datei ist
    # gitignoriert, das CSV ist die einzige versionierte Spur. 250 Zeilen zu
    # schreiben kostet nichts, ein verlorener Nachmittag schon.
    schreibe_urteile_csv()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8795)
    p.add_argument("--kein-browser", action="store_true")
    args = p.parse_args(argv)

    if not REFERENZ_DB.exists():
        print("Es gibt noch keinen Referenzsatz. Zuerst:")
        print(r"  .venv\Scripts\python.exe -m werkzeuge.w_referenz")
        return 1

    stand = _stand()
    adresse = f"http://127.0.0.1:{args.port}"
    print(f"{stand['gesamt']} Fenster, davon {len(stand['offen'])} offen")
    print(f"  {adresse}")
    print("  Tastatur: 1 = Ja, 2 = Nein, 3 = Unklar, Pfeil links = zurueck")
    print("  Beenden mit Strg+C - die Urteile sind schon gespeichert.")
    print(f"  Textkopie: {URTEILE_CSV}")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Griff)
    if not args.kein_browser:
        webbrowser.open(adresse)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbeendet")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
