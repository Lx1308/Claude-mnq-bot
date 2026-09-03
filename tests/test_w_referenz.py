"""Der Referenzsatz - vor allem: die beiden Klassen duerfen nicht erkennbar sein.

Ein Referenzsatz, dem man ansieht, was ein Kandidat war, ist wertlos: Laurin
wuerde nicht die Form beurteilen, sondern die Markierung. Diese Tests halten
die drei Stellen fest, an denen das schiefgehen kann.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from werkzeuge import w_referenz as W
from werkzeuge import w_referenz_server as S


@pytest.fixture()
def ablage(tmp_path, monkeypatch):
    """Eine leere Referenzdatenbank an einem Wegwerfort."""
    pfad = tmp_path / "w_referenz.sqlite3"
    monkeypatch.setattr(W, "REFERENZ_DB", pfad)
    monkeypatch.setattr(S, "REFERENZ_DB", pfad)
    monkeypatch.setattr(W, "URTEILE_CSV", tmp_path / "urteile.csv")
    return pfad


def _rahmen(n: int = 400, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20_000.0 + np.cumsum(rng.normal(0, 4, n))
    s = np.abs(rng.normal(3, 1.2, n)) + 0.5
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s,
         "close": p + rng.normal(0, 2, n), "volume": 500.0}, index=idx
    ).assign(
        high=lambda d: d[["high", "open", "close"]].max(axis=1),
        low=lambda d: d[["low", "open", "close"]].min(axis=1),
    )


# -- Kein Leck ueber die Seite ---------------------------------------------

def test_die_seite_erfaehrt_die_klasse_nicht(ablage):
    """``art`` darf nicht im JSON stehen - es waere im Browser sichtbar."""
    con = W.oeffne_db()
    with con:
        for nr, art in enumerate(("kandidat", "zufall"), 1):
            con.execute(
                "INSERT INTO fenster (musterart, art, fenster_start,"
                " fenster_ende, dauer, bild, reihenfolge)"
                " VALUES (?,?,?,?,?,?,?)",
                (W.MUSTERART, art, f"2026-01-0{nr}T09:00:00+00:00",
                 f"2026-01-0{nr}T09:40:00+00:00", 40, f"b{nr}.png", nr),
            )
    con.close()

    stand = S._stand()
    assert stand["gesamt"] == 2
    assert len(stand["offen"]) == 2
    for eintrag in stand["offen"]:
        assert set(eintrag) == {"start", "ende", "bild"}
        assert "kandidat" not in repr(eintrag)
        assert "zufall" not in repr(eintrag)


def test_urteil_wird_gespeichert_und_verschwindet_aus_der_liste(ablage):
    con = W.oeffne_db()
    with con:
        con.execute(
            "INSERT INTO fenster (musterart, art, fenster_start, fenster_ende,"
            " dauer, bild, reihenfolge) VALUES (?,?,?,?,?,?,?)",
            (W.MUSTERART, "kandidat", "2026-01-01T09:00:00+00:00",
             "2026-01-01T09:40:00+00:00", 40, "b1.png", 1),
        )
    con.close()

    S._speichere("2026-01-01T09:00:00+00:00", "2026-01-01T09:40:00+00:00", "ja")
    stand = S._stand()
    assert stand["gesamt"] == 1 and stand["offen"] == []

    con = W.oeffne_db()
    zeile = con.execute("SELECT * FROM urteile").fetchone()
    con.close()
    assert zeile["urteil"] == "ja"
    assert zeile["musterart"] == W.MUSTERART

    # Die Textkopie entsteht bei JEDEM Urteil - die SQLite-Datei ist
    # gitignoriert, das CSV ist die einzige versionierte Spur.
    assert W.URTEILE_CSV.exists()
    assert "ja" in W.URTEILE_CSV.read_text(encoding="utf-8")


def test_urteil_zu_einem_unbekannten_fenster_wird_abgelehnt(ablage):
    """Sonst waechst die Urteilstabelle an der Fenstertabelle vorbei."""
    W.oeffne_db().close()
    with pytest.raises(ValueError, match="unbekanntes Fenster"):
        S._speichere("2026-01-01T09:00:00+00:00",
                     "2026-01-01T09:40:00+00:00", "ja")


def test_nur_die_drei_urteile_sind_erlaubt(ablage):
    con = W.oeffne_db()
    with con:
        con.execute(
            "INSERT INTO fenster (musterart, art, fenster_start, fenster_ende,"
            " dauer, bild, reihenfolge) VALUES (?,?,?,?,?,?,?)",
            (W.MUSTERART, "zufall", "2026-01-01T09:00:00+00:00",
             "2026-01-01T09:40:00+00:00", 40, "b1.png", 1),
        )
    con.close()
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        S._speichere("2026-01-01T09:00:00+00:00",
                     "2026-01-01T09:40:00+00:00", "vielleicht")


# -- Kein Leck ueber das Bild ----------------------------------------------

def test_marker_sind_rein_geometrisch():
    """Dieselbe Regel fuer beide Klassen - sie kennt den Erkenner nicht.

    Waeren die Marker bei Kandidaten aus deren Feldern gesetzt und bei
    Zufallsfenstern geschaetzt, waeren die Klassen am Bild unterscheidbar.
    """
    df = _rahmen(400)
    t1, hi, t2 = W.marker(df, 100, 200)
    h = df["high"].to_numpy()[100:201]
    l = df["low"].to_numpy()[100:201]
    assert hi == 100 + int(np.argmax(h))
    assert t1 == 100 + int(np.argmin(l[:hi - 100 + 1]))
    assert t2 == hi + int(np.argmin(l[hi - 100:]))
    assert t1 <= hi <= t2


def test_marker_liegen_immer_im_fenster():
    df = _rahmen(400)
    for start, ende in ((0, 12), (50, 60), (100, 399)):
        t1, hi, t2 = W.marker(df, start, ende)
        assert start <= t1 <= hi <= t2 <= ende


def test_vorlauf_waechst_mit_der_dauer_und_bleibt_begrenzt():
    """Fest 40 Kerzen wuerden eine 10-Kerzen-Formation im Bild ertraenken."""
    assert W.vorlauf(10) == W.VORLAUF_MIN
    assert W.vorlauf(200) == W.VORLAUF_MAX
    assert W.vorlauf(30) < W.vorlauf(60) < W.vorlauf(200)


# -- Kein Leck ueber die Fensterbreite -------------------------------------

def test_ein_fenster_das_im_wesentlichen_ein_kandidat_ist_faellt_durch():
    erst = np.array([100, 500, 900])
    zweit = np.array([200, 620, 950])
    # deckungsgleich mit dem ersten Kandidaten
    assert W._deckt_sich_mit_kandidat(erst, zweit, 100, 200)
    # 80 der 100 Kerzen liegen im Kandidaten
    assert W._deckt_sich_mit_kandidat(erst, zweit, 120, 220)
    # nur 20 von 100
    assert not W._deckt_sich_mit_kandidat(erst, zweit, 180, 280)
    # gar keine Beruehrung
    assert not W._deckt_sich_mit_kandidat(erst, zweit, 300, 400)


def test_beruehrung_allein_verwirft_nicht():
    """Mit 78 % Abdeckung der Reihe waere sonst kein langes Fenster
    platzierbar - und der Satz haette nur kurze Zufallsfenster."""
    erst = np.array([100])
    zweit = np.array([110])
    assert not W._deckt_sich_mit_kandidat(erst, zweit, 90, 190)


def test_zufallsfenster_haben_dieselbe_laengenverteilung():
    """Die Klassen duerfen sich nicht an der Bildbreite unterscheiden.

    Zwei Anlaeufe sind hier schiefgegangen: erst waren die Zufallsfenster im
    Mittel 22,9 gegen 46,8 Kerzen zu kurz (lange waren zwischen den
    Kandidaten nicht platzierbar), dann mit 66,7 gegen 46,8 zu lang (kurze
    fielen oefter durch die Ueberlappungspruefung). Erst die feste Ziellaenge
    stimmt.
    """
    df = _rahmen(60_000, seed=9)
    rng = np.random.default_rng(1)
    # Kandidaten, die ein Drittel der Reihe abdecken.
    starts = np.sort(rng.integers(500, len(df) - 500, 400))
    dauern = rng.integers(10, 150, 400)
    alle = pd.DataFrame({"erst_idx": starts, "zweit_idx": starts + dauern,
                         "bestaetigt_idx": starts + dauern + 2,
                         "dauer": dauern})
    gezogen = alle.sample(n=60, random_state=3)

    zufall = W.ziehe_zufallsfenster(df, alle, gezogen, 60, rng)
    assert len(zufall) >= 55, "zu viele Laengen waren nicht platzierbar"

    # Die Laenge stammt aus der Kandidatenverteilung plus dem Zuschlag bis
    # zur Bestaetigung - Kandidatenbilder reichen genauso weit.
    zuschlag = int((gezogen["bestaetigt_idx"] - gezogen["zweit_idx"]).iloc[0])
    erlaubt = {d + zuschlag for d in gezogen["dauer"].tolist()}
    assert set(zufall["dauer"].tolist()) <= erlaubt
    # ... und die Verteilung darf nicht wegdriften.
    assert abs(zufall["dauer"].mean() - zuschlag
               - gezogen["dauer"].mean()) < 15
    assert (zufall["zweit_idx"] - zufall["erst_idx"]).equals(zufall["dauer"])


def test_urteile_ueberleben_den_verlust_der_datenbank(ablage):
    """Aus dem CSV muss sich die Urteilstabelle wiederherstellen lassen."""
    con = W.oeffne_db()
    with con:
        for nr in (1, 2):
            con.execute(
                "INSERT INTO fenster (musterart, art, fenster_start,"
                " fenster_ende, dauer, bild, reihenfolge)"
                " VALUES (?,?,?,?,?,?,?)",
                (W.MUSTERART, "kandidat", f"2026-01-0{nr}T09:00:00+00:00",
                 f"2026-01-0{nr}T09:40:00+00:00", 40, f"b{nr}.png", nr))
    con.close()
    S._speichere("2026-01-01T09:00:00+00:00", "2026-01-01T09:40:00+00:00", "ja")
    S._speichere("2026-01-02T09:00:00+00:00", "2026-01-02T09:40:00+00:00", "nein")

    ablage.unlink()                       # Datenbank weg
    assert W.lies_urteile_csv() == 2
    con = W.oeffne_db()
    urteile = {r["fenster_start"]: r["urteil"]
               for r in con.execute("SELECT * FROM urteile")}
    con.close()
    assert urteile == {"2026-01-01T09:00:00+00:00": "ja",
                       "2026-01-02T09:00:00+00:00": "nein"}
