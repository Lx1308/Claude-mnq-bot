"""Der Rueckprall-Vergleich - vor allem die Swingtief-Suche.

Der Vergleich "traegt das W etwas ueber ein gehaltenes Tief hinaus" steht und
faellt damit, dass beide Gruppen dieselbe Art Objekt sind und die Indizes
stimmen. Beim Bauen ging genau das schief: ``find_swing_points`` liefert die
Funde ABSTEIGEND nach Index, und eine Monotonie-Annahme in der Blockschleife
warf alles bis auf den letzten weg - 1 statt 4.645 Tiefs, ohne Fehlermeldung.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from werkzeuge import rueckprall as R


def _rausch(n: int = 30_000, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20_000.0 + np.cumsum(rng.normal(0, 3, n))
    s = np.abs(rng.normal(2.5, 1.0, n)) + 0.5
    idx = pd.date_range("2022-01-03 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s,
         "close": p + rng.normal(0, 1.5, n), "volume": 500.0}, index=idx
    ).assign(
        high=lambda d: d[["high", "open", "close"]].max(axis=1),
        low=lambda d: d[["low", "open", "close"]].min(axis=1),
    )


# -- Die Swingtief-Suche ---------------------------------------------------

def test_jedes_gefundene_tief_ist_das_minimum_seines_fensters():
    df = _rausch()
    tiefs = R.swingtiefs(df)
    l = df["low"].to_numpy()
    innen = tiefs[(tiefs > R.STAERKE) & (tiefs < len(df) - R.STAERKE)]
    assert len(innen) > 500, "zu wenige Tiefs, der Test traegt nicht"
    for i in innen:
        fenster = l[i - R.STAERKE:i + R.STAERKE + 1]
        assert l[i] == fenster.min(), f"Index {i} ist nicht das Minimum"


def test_bloecke_verlieren_nichts_an_den_naehten(monkeypatch):
    """Die Blockschleife muss dasselbe liefern wie ein Durchlauf am Stueck.

    Der Fehler beim Bauen lag genau hier: pro Block wurde nur ein einziges
    Tief uebernommen, weil die Funde absteigend kommen.
    """
    df = _rausch(20_000)
    am_stueck = R.swingtiefs(df)
    monkeypatch.setattr(R, "BLOCK_KERZEN", 3_000)
    in_bloecken = R.swingtiefs(df)
    assert len(am_stueck) > 300
    # An den Naehten kann ein Block ein Tief sehen, das der andere nicht
    # sieht - deshalb Teilmenge statt Gleichheit in dieser Richtung.
    fehlend = set(am_stueck) - set(in_bloecken)
    assert len(fehlend) / len(am_stueck) < 0.02, (
        f"{len(fehlend)} von {len(am_stueck)} Tiefs gehen an den Naehten "
        "verloren"
    )


def test_die_suche_liefert_aufsteigende_eindeutige_indizes():
    df = _rausch(15_000)
    tiefs = R.swingtiefs(df)
    assert (np.diff(tiefs) > 0).all(), "Indizes muessen aufsteigend sein"
    assert len(set(tiefs.tolist())) == len(tiefs)


# -- Die Aufteilung --------------------------------------------------------

def test_w_tiefs_werden_mit_toleranz_erkannt():
    tiefs = np.array([100, 200, 300, 400])
    w_zweit = np.array([102, 399])          # zwei Treffer, jeweils in Naehe
    maske, _ = R.teile_auf(tiefs, w_zweit)
    assert maske.tolist() == [True, False, False, True]


def test_ohne_w_ist_alles_generisch():
    tiefs = np.array([100, 200, 300])
    maske, verwendbar = R.teile_auf(tiefs, np.array([], dtype=np.int64))
    assert not maske.any() and verwendbar.all()


def test_zu_weit_entfernt_zaehlt_nicht():
    tiefs = np.array([100])
    assert not R.teile_auf(tiefs, np.array([100 + R.NAEHE + 1]))[0].any()
    assert R.teile_auf(tiefs, np.array([100 + R.NAEHE]))[0].all()


def test_spaet_bestaetigte_w_fliegen_raus():
    """Ein W, das erst NACH der Swing-Bestaetigung feststeht, waere ein Leck.

    Die Leiter startet bei tief_idx + STAERKE. Ist das W erst danach
    bekannt, haette das Etikett Zukunftswissen getragen.
    """
    tiefs = np.array([100, 200])
    w_zweit = np.array([100, 200])
    # Das erste W ist nach 2 Kerzen bestaetigt, das zweite erst nach 50.
    w_best = np.array([102, 250])
    ist_w, verwendbar = R.teile_auf(tiefs, w_zweit, w_best)
    assert ist_w.tolist() == [True, True]
    assert verwendbar.tolist() == [True, False]


# -- Die Leiter ------------------------------------------------------------

def test_leiter_startet_erst_nach_der_bestaetigung():
    """Ein Swingtief ist erst STAERKE Kerzen spaeter bekannt.

    Der Kurs steigt hier SOFORT nach dem Tief steil an. Wer den Anstieg
    mitnaehme, haette das Tief benutzt, bevor es bestaetigt war.
    """
    kerzen = [(100, 101, 99, 100)] * 20
    kerzen += [(100, 100, 90, 91)]                  # Index 20: das Tief
    kerzen += [(91, 200, 90.5, 199)]                # sofort steil hoch
    kerzen += [(199, 200, 198, 199)] * 300
    idx = pd.date_range("2022-01-03 09:00", periods=len(kerzen), freq="1min",
                        tz="UTC")
    df = pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": 500.0}, index=idx)

    tief_idx = np.array([20])
    tief_kurs = np.array([90.0])
    a = np.array([2.0])
    stufen = R.leiter(df, tief_idx, tief_kurs, a, horizont=100)
    # Die Sprosse liegt bei 90 + 0.5*2 = 91. Erreicht wird sie erst ab
    # Index 26 (20 + STAERKE), nicht schon in Kerze 21.
    assert stufen[0.5][0] >= 20 + R.STAERKE


def test_bruch_unter_das_tief_macht_die_sprossen_ungueltig():
    kerzen = [(100, 101, 99, 100)] * 20
    kerzen += [(100, 100, 90, 91)]                  # Tief bei 90
    kerzen += [(91, 92, 90.5, 91)] * 6              # Bestaetigungsfenster
    kerzen += [(91, 92, 85, 86)]                    # Bruch
    kerzen += [(86, 200, 85, 199)]                  # danach steil hoch
    kerzen += [(199, 200, 198, 199)] * 300
    idx = pd.date_range("2022-01-03 09:00", periods=len(kerzen), freq="1min",
                        tz="UTC")
    df = pd.DataFrame(
        {"open": [k[0] for k in kerzen], "high": [k[1] for k in kerzen],
         "low": [k[2] for k in kerzen], "close": [k[3] for k in kerzen],
         "volume": 500.0}, index=idx)
    stufen = R.leiter(df, np.array([20]), np.array([90.0]), np.array([2.0]),
                      horizont=100)
    assert stufen[3.0][0] == -1, (
        "die 3-ATR-Sprosse wird erst NACH dem Bruch erreicht und darf "
        "nicht zaehlen"
    )


def test_hoehere_sprossen_werden_seltener_erreicht():
    df = _rausch(30_000, seed=9)
    tiefs = R.swingtiefs(df)
    tiefs = tiefs[(tiefs > 300) & (tiefs + 300 < len(df))]
    kurse = df["low"].to_numpy()[tiefs]
    a = np.full(len(tiefs), 4.0)
    stufen = R.leiter(df, tiefs, kurse, a, horizont=240)
    quoten = [(stufen[r] >= 0).mean() for r in R.SPROSSEN]
    assert all(x >= y for x, y in zip(quoten, quoten[1:])), (
        f"Quoten muessen fallen, sind aber {quoten}"
    )
