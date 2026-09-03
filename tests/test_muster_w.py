"""Der W-Erkenner - vor allem das zweite Tief und der fehlende Lookahead.

Die beiden wichtigsten Tests:

* ``test_laurins_w2_liefert_das_tief_um_0956`` - die Gegenprobe an echten
  Kursen. Die Vorgaengerfassung brach beim ERSTEN Ruecklauf ins Tiefband ab
  und lieferte die 09:50 bei 29.041,75 statt der 09:56 bei 29.017,25.
* ``test_kein_lookahead_bei_abgeschnittener_reihe`` - was auf der halben
  Reihe gefunden wird, muss auf der ganzen identisch herauskommen.

Und ein dritter, der kein Verhalten sichert, sondern einen Widerspruch
festhaelt: ``test_konflikt_max_unter_verwirft_laurins_w2``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from common.config import Config, DoppelbodenConfig
from common.indicators import atr as atr_indikator
from common.muster_w import WMuster, bester_je_tief, finde_w

FIXTURE = Path(__file__).parent / "daten" / "laurins_w2_2026-09-02.csv"


# -- Hilfsmittel -----------------------------------------------------------

def _laurins_w2() -> tuple[pd.DataFrame, np.ndarray]:
    """MNQ-Minutenkerzen 12:30-14:10 UTC am 02.09.2026, echte Kurse.

    Enthaelt Laurins W: erstes Tief 13:38 (09:38 ET) bei 29.036,75, Hoch
    13:43 bei 29.119,00, zweites Tief 13:56 bei 29.017,25.
    """
    df = pd.read_csv(FIXTURE)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
    df = df.set_index("ts_utc")
    return df, atr_indikator(df, period=14).to_numpy()


def _rahmen(kerzen: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """OHLC von Hand, damit sich das Ergebnis nachrechnen laesst."""
    index = pd.date_range("2026-01-05 09:00", periods=len(kerzen), freq="1min",
                          tz="UTC")
    return pd.DataFrame(
        {
            "open": [k[0] for k in kerzen],
            "high": [k[1] for k in kerzen],
            "low": [k[2] for k in kerzen],
            "close": [k[3] for k in kerzen],
            "volume": [500.0] * len(kerzen),
        },
        index=index,
    )


def _rausch(n: int = 40_000, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    p = 20_000.0 + np.cumsum(rng.normal(0, 4, n))
    s = np.abs(rng.normal(3, 1.2, n)) + 0.5
    richtung = rng.normal(0, 2, n)
    idx = pd.date_range("2026-01-05 09:00", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": p, "high": p + s, "low": p - s, "close": p + richtung,
         "volume": 500.0},
        index=idx,
    ).assign(
        high=lambda d: d[["high", "open", "close"]].max(axis=1),
        low=lambda d: d[["low", "open", "close"]].min(axis=1),
    )


# -- Die Gegenprobe an Laurins eigenem W -----------------------------------

def test_laurins_w2_liefert_das_tief_um_0956():
    """Der Fehler vom 02.09.2026, an echten Kursen festgenagelt.

    ``max_unter`` steht hier bewusst weit (0,35). Mit dem Wert aus der
    Config (0,15) entsteht dieser Kandidat gar nicht erst - genau das ist
    der Widerspruch, den ``test_konflikt_max_unter_verwirft_laurins_w2``
    festhaelt.
    """
    df, a = _laurins_w2()
    cfg = DoppelbodenConfig(max_dauer=60, max_unter=0.35)
    funde = finde_w(df, a, cfg=cfg)

    erst = df.index.get_loc(pd.Timestamp("2026-09-02T13:38:00Z"))
    zum_tief = [f for f in funde if f.erst_idx == erst]
    assert zum_tief, "Laurins erstes Tief um 13:38 wird gar nicht aufgegriffen"

    tiefe = {df.index[f.zweit_idx].strftime("%H:%M"): f for f in zum_tief}
    assert "13:56" in tiefe, (
        f"das zweite Tief um 13:56 fehlt; gefunden wurden {sorted(tiefe)}"
    )
    treffer = tiefe["13:56"]
    assert treffer.tief2 == pytest.approx(29_017.25)
    assert treffer.tief1 == pytest.approx(29_036.75)
    assert treffer.hoch == pytest.approx(29_119.00)
    assert treffer.hoehe == pytest.approx(101.75)
    assert treffer.zweites_tiefer, "das zweite Tief liegt tiefer als das erste"


def test_laurins_w2_wird_erst_nach_dem_tief_bestaetigt():
    """Der Einstieg darf nicht vor der Umkehr liegen."""
    df, a = _laurins_w2()
    funde = finde_w(df, a, cfg=DoppelbodenConfig(max_dauer=60, max_unter=0.35))
    erst = df.index.get_loc(pd.Timestamp("2026-09-02T13:38:00Z"))
    treffer = next(f for f in funde
                   if f.erst_idx == erst
                   and df.index[f.zweit_idx].strftime("%H:%M") == "13:56")
    assert treffer.bestaetigt_idx > treffer.zweit_idx
    assert treffer.einstieg_idx == treffer.bestaetigt_idx + 1
    assert df.index[treffer.bestaetigt_idx].strftime("%H:%M") == "14:00"


def test_zwei_aufwaertskerzen_entfernen_den_verfruehten_kandidaten():
    """Laurins Regel vom 03.09.2026, an seinem eigenen W nachgerechnet.

    Was die Regel tut - und was sie NICHT tut:

        1 Aufwaertskerze   zwei Kandidaten
                           13:52 zu 29.068,25  (das verfruehte Tief 13:50)
                           13:58 zu 29.051,00  (das richtige Tief 13:56)
        2 Aufwaertskerzen  EIN Kandidat
                           14:01 zu 29.062,00

    Der Gewinn liegt darin, dass der verfruehte Kandidat ganz verschwindet.
    Der Einstieg beim richtigen wird dagegen 11 Punkte TEURER, nicht
    billiger - die strengere Bestaetigung kostet Strecke.

    Ob sich das rechnet, entscheidet die Messung ueber alle Faelle, nicht
    dieses eine Beispiel. Der Test haelt nur fest, was tatsaechlich
    passiert.
    """
    df, a = _laurins_w2()
    erst = df.index.get_loc(pd.Timestamp("2026-09-02T13:38:00Z"))

    def kandidaten(n_auf: int) -> list:
        cfg = DoppelbodenConfig(max_dauer=60, max_unter=0.35,
                                min_aufwaerts_kerzen=n_auf)
        return sorted((f for f in finde_w(df, a, cfg=cfg)
                       if f.erst_idx == erst), key=lambda f: f.zweit_idx)

    locker, streng = kandidaten(1), kandidaten(2)
    opens = df["open"].to_numpy()

    assert [df.index[f.zweit_idx].strftime("%H:%M") for f in locker] == \
        ["13:50", "13:56"]
    assert [df.index[f.zweit_idx].strftime("%H:%M") for f in streng] == \
        ["13:56"], "der verfruehte Kandidat muss verschwinden"

    assert opens[locker[1].einstieg_idx] == pytest.approx(29_051.00)
    assert opens[streng[0].einstieg_idx] == pytest.approx(29_062.00)


def test_mehrere_kandidaten_je_erstem_tief():
    """Kein ``break`` mehr beim ersten Ruecklauf.

    Geprueft mit der lockeren Ein-Kerzen-Regel, weil Laurins Zwei-Kerzen-
    Regel den verfruehten Kandidaten bei seinem W gerade wegfiltert - was
    sie soll. Die Mechanik, dass MEHRERE Kandidaten je erstem Tief entstehen
    koennen, muss davon unabhaengig funktionieren.
    """
    df, a = _laurins_w2()
    cfg = DoppelbodenConfig(max_dauer=60, max_unter=0.35,
                            min_aufwaerts_kerzen=1)
    funde = finde_w(df, a, cfg=cfg)
    erst = df.index.get_loc(pd.Timestamp("2026-09-02T13:38:00Z"))
    zum_tief = sorted((f for f in funde if f.erst_idx == erst),
                      key=lambda f: f.zweit_idx)
    assert len(zum_tief) >= 2, "es entsteht nur ein Kandidat - der break ist zurueck"
    zeiten = [df.index[f.zweit_idx].strftime("%H:%M") for f in zum_tief]
    assert zeiten[:2] == ["13:50", "13:56"]


def test_konflikt_max_unter_verwirft_laurins_w2():
    """KEIN Verhaltenstest - ein festgehaltener Widerspruch.

    Laurin hat am 03.09.2026 ``max_unter: 0.15`` vorgegeben. Sein eigenes W
    vom 02.09. hat ein zweites Tief 19,50 Punkte UNTER dem ersten; gemessen
    an der damals bekannten Spanne (29.119,00 - 29.036,75 = 82,25) sind das
    23,7 %. Die Schwelle verwirft es also.

    Der Test schlaegt fehl, sobald der Widerspruch behoben ist - dann ist er
    zu loeschen. Bis dahin verhindert er, dass er in Vergessenheit geraet.
    Entscheidung steht bei Laurin (docs/OFFENE_FRAGEN.md).
    """
    df, a = _laurins_w2()
    aus_config = Config.load().patterns.doppelboden
    assert aus_config.max_unter == 0.15, "die Config hat sich geaendert"

    cfg = DoppelbodenConfig(max_dauer=60, max_unter=aus_config.max_unter)
    funde = finde_w(df, a, cfg=cfg)
    erst = df.index.get_loc(pd.Timestamp("2026-09-02T13:38:00Z"))
    zweite_tiefs = {df.index[f.zweit_idx].strftime("%H:%M")
                    for f in funde if f.erst_idx == erst}
    assert "13:56" not in zweite_tiefs, (
        "der Widerspruch ist behoben - diesen Test loeschen"
    )

    # 24 % unter dem ersten Tief: das ist die Zahl, um die es geht.
    spanne = 29_119.00 - 29_036.75
    assert (29_036.75 - 29_017.25) / spanne == pytest.approx(0.237, abs=0.001)


# -- Kein Lookahead --------------------------------------------------------

def test_kein_lookahead_bei_abgeschnittener_reihe():
    """Was auf der halben Reihe gefunden wird, muss auf der ganzen identisch
    herauskommen. Sonst ist Zukunftswissen im Spiel."""
    df = _rausch(40_000)
    a = atr_indikator(df, period=14).to_numpy()
    schnitt = len(df) // 2
    kurz = df.iloc[:schnitt]
    a_kurz = atr_indikator(kurz, period=14).to_numpy()

    cfg = DoppelbodenConfig(strength=20, max_dauer=200)
    voll = {(f.erst_idx, f.zweit_idx): f for f in finde_w(df, a, cfg=cfg)}
    teil = finde_w(kurz, a_kurz, cfg=cfg)

    # Wer zu nah am Schnitt liegt, hatte in der kurzen Reihe schlicht weniger
    # Zukunft zum Suchen - das ist kein Lookahead.
    puffer = cfg.max_dauer + cfg.strength + 5

    geprueft = 0
    for f in teil:
        if f.erst_idx > schnitt - puffer:
            continue
        geprueft += 1
        g = voll.get((f.erst_idx, f.zweit_idx))
        assert g is not None, (
            f"Fund bei {f.erst_idx}/{f.zweit_idx} fehlt in der vollen Reihe"
        )
        assert g.bestaetigt_idx == f.bestaetigt_idx
        assert g.einstieg_idx == f.einstieg_idx
        assert g.hoch == pytest.approx(f.hoch)
        assert g.tief2 == pytest.approx(f.tief2)
        assert g.formfehler == pytest.approx(f.formfehler)
    assert geprueft > 30, "zu wenige Faelle geprueft, der Test traegt nicht"


def test_nackenlinie_ist_das_laufende_hoch_nicht_das_spaetere():
    """Ein Hoch NACH dem Ruecklauf darf die obere Linie nicht mehr anheben."""
    kerzen = [(100, 101, 99, 100)] * 60           # Vorlauf fuer den Arm
    kerzen += [(100, 100.5, 90, 91)]              # 60: das erste Tief
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]   # Anstieg
    kerzen += [(103, 104, 102, 103)] * 6          # Hoch bei 104
    kerzen += [(103, 103.5, 91, 92)]              # Ruecklauf ans Tief
    kerzen += [(92, 94, 91.5, 93.5)]              # erste Aufwaertskerze
    kerzen += [(93.5, 96, 93, 95.5)]              # zweite -> Bestaetigung
    kerzen += [(96, 130, 95, 129)]                # viel spaeteres Hoch: 130
    kerzen += [(129, 131, 128, 130)] * 20
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)

    cfg = DoppelbodenConfig(strength=5, max_dauer=60, min_dauer=10,
                            min_hoehe_atr=2.0, min_linker_arm=0.0)
    funde = finde_w(df, a, cfg=cfg)
    assert funde, "das Muster sollte gefunden werden"
    assert all(f.hoch < 110 for f in funde), (
        "die obere Linie enthaelt das spaetere Hoch von 130 - das ist Lookahead"
    )


# -- Die Struktur des Musters ----------------------------------------------

def test_gerissenes_tief_ergibt_kein_muster():
    kerzen = [(100, 101, 99, 100)] * 60
    kerzen += [(100, 100.5, 90, 91)]
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]
    kerzen += [(103, 104, 102, 103)] * 6
    kerzen += [(103, 103.5, 80, 81)]              # weit unter das Tief
    kerzen += [(81, 85, 80.5, 84.5)] * 25
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)
    cfg = DoppelbodenConfig(strength=5, max_dauer=60, min_dauer=10,
                            min_linker_arm=0.0)
    funde = finde_w(df, a, cfg=cfg)
    assert not [f for f in funde if abs(f.tief1 - 90.0) < 1e-9], (
        "das gerissene Tief darf keine untere Linie mehr sein"
    )


def test_flaches_muster_wird_verworfen():
    """Unter der Mindesthoehe in ATR ist es Rauschen, kein Muster."""
    df = _rausch(20_000, seed=3)
    a = atr_indikator(df, period=14).to_numpy()
    viele = finde_w(df, a, cfg=DoppelbodenConfig(strength=20, min_hoehe_atr=0.5))
    wenige = finde_w(df, a, cfg=DoppelbodenConfig(strength=20, min_hoehe_atr=6.0))
    assert len(wenige) < len(viele)


def test_formfehler_schranke_filtert():
    df = _rausch(20_000, seed=3)
    a = atr_indikator(df, period=14).to_numpy()
    offen = finde_w(df, a, cfg=DoppelbodenConfig(strength=20))
    eng = finde_w(df, a, cfg=DoppelbodenConfig(strength=20, max_formfehler=0.05))
    assert len(eng) < len(offen)
    assert all(f.formfehler <= 0.05 for f in eng)


def test_kandidaten_sind_begrenzt():
    df = _rausch(20_000, seed=3)
    a = atr_indikator(df, period=14).to_numpy()
    cfg = DoppelbodenConfig(strength=20, max_kandidaten=2)
    funde = finde_w(df, a, cfg=cfg)
    je_tief: dict[int, int] = {}
    for f in funde:
        je_tief[f.erst_idx] = je_tief.get(f.erst_idx, 0) + 1
    assert je_tief and max(je_tief.values()) <= 2


def test_bester_je_tief_nimmt_den_kleinsten_formfehler():
    def _m(erst: int, zweit: int, fehler: float) -> WMuster:
        return WMuster(erst_idx=erst, hoch_idx=erst + 5, zweit_idx=zweit,
                       bestaetigt_idx=zweit + 1, einstieg_idx=zweit + 2,
                       tief1=100.0, tief2=100.0, hoch=170.0, linker_arm=1.0,
                       formfehler=fehler, gipfellage=0.5, atr=5.0)
    funde = [_m(10, 20, 0.30), _m(10, 30, 0.10), _m(50, 60, 0.20)]
    beste = bester_je_tief(funde)
    assert [f.zweit_idx for f in beste] == [30, 60]


# -- Die Geometrie ---------------------------------------------------------

def _muster() -> WMuster:
    return WMuster(erst_idx=0, hoch_idx=5, zweit_idx=10, bestaetigt_idx=12,
                   einstieg_idx=13, tief1=100.0, tief2=100.5, hoch=170.0,
                   linker_arm=1.0, formfehler=0.05, gipfellage=0.5, atr=5.0)


def test_stop_muss_unter_dem_tief_liegen():
    m = _muster()
    assert m.hoehe == pytest.approx(70.0)
    # Laurins Beispiel: 15 Punkte unter dem Tief sind 21 % der Hoehe.
    assert m.stop(15.0 / 70.0) == pytest.approx(85.0)
    with pytest.raises(ValueError, match="unter das Tief"):
        m.stop(0.0)
    with pytest.raises(ValueError, match="unter das Tief"):
        m.stop(-0.1)


def test_ziel_davor_und_als_messziel():
    m = _muster()
    # 10 Punkte VOR der oberen Linie = 14 % der Hoehe.
    assert m.ziel(10.0 / 70.0) == pytest.approx(160.0)
    # Klassisches Messziel: eine Musterhoehe darueber hinaus.
    assert m.ziel(-1.0) == pytest.approx(240.0)


def test_dauer_und_verzoegerung():
    m = _muster()
    assert m.dauer == 10
    assert m.verzoegerung == 2
    assert m.versatz == pytest.approx(0.5)
    assert not m.zweites_tiefer


# -- Randfaelle ------------------------------------------------------------

def test_atr_laenge_wird_geprueft():
    df = _rausch(2_000)
    with pytest.raises(ValueError, match="atr hat"):
        finde_w(df, np.ones(10))


def test_ungueltige_staerke_bricht_ab():
    df = _rausch(2_000)
    with pytest.raises(ValueError, match="strength"):
        finde_w(df, np.ones(len(df)), cfg=DoppelbodenConfig(strength=0))


def test_nach_dem_nackenlinienbruch_kommt_kein_kandidat_mehr():
    """Ueber die Nackenlinie hinaus ist die Formation abgeschlossen.

    Der Zweig war bis zum 03.09.2026 toter Code: verglichen wurde gegen das
    LAUFENDE Hoch, und ein Schlusskurs liegt nie ueber dem eigenen Hoch.
    """
    kerzen = [(100, 101, 99, 100)] * 60
    kerzen += [(100, 100.5, 90, 91)]              # 60: erstes Tief
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]
    kerzen += [(103, 104, 102, 103)] * 6          # Nackenlinie 104
    kerzen += [(103, 103.5, 91, 92)]              # Ruecklauf ans Tief
    kerzen += [(92, 94, 91.5, 93.5)]              # erste Aufwaertskerze
    kerzen += [(93.5, 97, 93, 96.5)]              # zweite -> Kandidat
    kerzen += [(97, 120, 96, 119)]                # Bruch ueber die Nackenlinie
    kerzen += [(119, 120, 90.5, 91)]              # zurueck ans alte Tief
    kerzen += [(91, 95, 90.5, 94)]                # erste Aufwaertskerze
    kerzen += [(94, 99, 93.5, 98)]                # zweite - wuerde bestaetigen
    kerzen += [(98, 99, 97, 98)] * 20
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)
    cfg = DoppelbodenConfig(strength=5, max_dauer=60, min_dauer=10,
                            min_hoehe_atr=2.0, min_linker_arm=0.0)
    zum_ersten = [f for f in finde_w(df, a, cfg=cfg) if f.erst_idx == 60]
    assert len(zum_ersten) == 1, (
        "nach dem Bruch der Nackenlinie darf zu diesem Tief kein weiterer "
        f"Kandidat entstehen, es sind {len(zum_ersten)}"
    )


def test_eine_einzelne_gruene_kerze_bestaetigt_nicht():
    """Laurins Regel: die untere Linie ist erst nach zwei Aufwaertskerzen
    bestaetigt. Eine allein kann noch zum Abverkauf gehoeren."""
    kerzen = [(100, 101, 99, 100)] * 60
    kerzen += [(100, 100.5, 90, 91)]              # erstes Tief
    kerzen += [(91, 92 + i, 90.5, 91.5 + i) for i in range(12)]
    kerzen += [(103, 104, 102, 103)] * 6          # Nackenlinie
    kerzen += [(103, 103.5, 91, 92)]              # Ruecklauf ans Tief
    kerzen += [(92, 97, 91.5, 96.5)]              # EINE gruene Kerze
    kerzen += [(96.5, 97, 91.5, 92)] * 30         # danach nur noch abwaerts
    df = _rahmen(kerzen)
    a = np.full(len(df), 2.0)
    cfg = DoppelbodenConfig(strength=5, max_dauer=60, min_dauer=10,
                            min_hoehe_atr=2.0, min_linker_arm=0.0)
    mit_zwei = finde_w(df, a, cfg=cfg)
    lockerer = DoppelbodenConfig(strength=5, max_dauer=60, min_dauer=10,
                                 min_hoehe_atr=2.0, min_linker_arm=0.0,
                                 min_aufwaerts_kerzen=1)
    mit_einer = finde_w(df, a, cfg=lockerer)
    assert not mit_zwei, "eine gruene Kerze darf nicht reichen"
    assert mit_einer, "mit der lockeren Regel entstuende hier ein Kandidat"
