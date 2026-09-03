"""Die W-Schablone - eine Kennzahl statt dreier Einzelregeln.

Der Formfehler ersetzt ``max_rueckschlag``, die Gipfel-Mittigkeit und das
Schenkelverhaeltnis. Diese Tests halten fest, dass er die Formen so ordnet,
wie ein Mensch sie ordnen wuerde: W besser als Plateau besser als Rauschen.
"""

from __future__ import annotations

import numpy as np
import pytest

from common.w_schablone import (
    GIPFEL_BIS,
    GIPFEL_VON,
    RASTER,
    formfehler,
    glaette,
    schablone,
)

RASTER_X = np.linspace(0.0, 1.0, RASTER)


# -- Die Schablone selbst --------------------------------------------------

def test_schablone_trifft_ihre_ankerpunkte():
    p = 0.4
    y = schablone(p, np.array([0.0, p / 2, p, (1 + p) / 2, 1.0]))
    assert y == pytest.approx([0.0, 0.5, 1.0, 0.5, 0.0])


def test_schablone_hat_ihren_gipfel_bei_p():
    for p in (0.15, 0.5, 0.85):
        y = schablone(p, RASTER_X)
        assert RASTER_X[int(np.argmax(y))] == pytest.approx(p, abs=0.01)


# -- Der Formfehler --------------------------------------------------------

def test_perfekte_schablone_hat_fehler_null():
    for p in (0.2, 0.5, 0.78):
        fehler, gipfel = formfehler(schablone(p, RASTER_X))
        assert fehler < 1e-9
        assert gipfel == pytest.approx(p, abs=0.02)


def test_massstab_ist_egal():
    """Ein 20-Punkte-W und ein 140-Punkte-W bekommen denselben Fehler."""
    form = schablone(0.45, RASTER_X)
    klein = 20_000.0 + 20.0 * form
    gross = 20_000.0 + 140.0 * form
    assert formfehler(klein)[0] == pytest.approx(formfehler(gross)[0])


def test_w_ist_besser_als_plateau_ist_besser_als_rauschen():
    """Die Rangfolge, auf die es ankommt.

    Das Plateau ist Laurins Gegenbeispiel vom 02.09.2026: "das ist zb nur
    Rauschen, sowas ist niemals ein W." Es braucht dafuer keine eigene
    Plateau-Regel - die Schablone steigt und faellt durchgehend, ein Plateau
    tut weder das eine noch das andere.
    """
    w = formfehler(schablone(0.5, RASTER_X))[0]
    plateau = formfehler(np.concatenate([
        np.linspace(0, 1, 20), np.full(60, 1.0), np.linspace(1, 0, 21)]))[0]
    rauschen = formfehler(np.sin(np.linspace(0, 6 * np.pi, RASTER)))[0]
    assert w < plateau < rauschen


def test_gerade_ist_kein_w():
    gerade = formfehler(np.linspace(0.0, 1.0, RASTER))[0]
    assert gerade > formfehler(schablone(0.5, RASTER_X))[0] + 0.1


def test_flanke_ist_schlechter_als_ein_mittiges_w():
    """Ein Gipfel ganz am Rand ist eine Flanke, kein W."""
    x = RASTER_X
    flanke = np.concatenate([np.linspace(0, 1, 5), np.linspace(1, 0, RASTER - 5)])
    assert formfehler(flanke)[0] > formfehler(schablone(0.5, x))[0]


def test_gipfellage_bleibt_im_erlaubten_bereich():
    for linie in (np.linspace(0, 1, 40), np.sin(np.linspace(0, 3 * np.pi, 40))):
        _, gipfel = formfehler(linie)
        assert GIPFEL_VON - 1e-9 <= gipfel <= GIPFEL_BIS + 1e-9


def test_flache_linie_bekommt_keinen_erfundenen_wert():
    """Ohne Preisspanne gibt es keine Form - inf statt einer Zahl."""
    fehler, gipfel = formfehler(np.full(50, 20_000.0))
    assert fehler == float("inf")
    assert np.isnan(gipfel)


def test_kurze_muster_tragen_einen_diskretisierungsaufschlag():
    """BEKANNTE SCHWAECHE, hier festgenagelt statt versteckt.

    Ein PERFEKTES W bekommt nicht den Fehler null, wenn seine Spitze
    zwischen zwei Kerzen faellt. Die Min-Max-Normierung setzt das
    beobachtete Maximum auf 1,0 - liegt es unter der wahren Spitze, wird
    die ganze Linie mit hochgezogen und weicht ueberall ab.

    Gemessen an einer perfekten Schablone:

        8 Stuetzstellen  -> 0,082
       12 Stuetzstellen  -> 0,052
       20 Stuetzstellen  -> 0,030
      100 Stuetzstellen  -> 0,006
      400 Stuetzstellen  -> 0,001

    Zum Vergleich: Laurins echtes W vom 02.09.2026 kommt auf 0,085. Bei
    kurzen Formationen liegt der Rauschboden also in derselben Groessen-
    ordnung wie das Signal, und EINE Schranke ueber alle Dauern hinweg
    benachteiligt kurze Muster.

    Nicht stillschweigend behoben: die Normierung ist in AP2b ausdruecklich
    als Min-Max vorgegeben. Der Vorschlag (Schablone per kleinster Quadrate
    affin anpassen statt an zwei Extremwerten aufhaengen) steht in
    docs/OFFENE_FRAGEN.md und ist Laurins Entscheidung.
    """
    aufschlag = {n: formfehler(schablone(0.5, np.linspace(0, 1, n)))[0]
                 for n in (8, 12, 20, 100, 400)}
    assert aufschlag[8] > aufschlag[20] > aufschlag[400]
    assert aufschlag[8] < 0.09, "der Aufschlag ist groesser geworden"
    assert aufschlag[400] < 0.005


# -- Randfaelle ------------------------------------------------------------

def test_zu_kurze_linie_bricht_ab():
    with pytest.raises(ValueError, match="Stuetzstellen"):
        formfehler(np.array([1.0, 2.0, 1.0]))


def test_nan_bricht_ab():
    linie = schablone(0.5, RASTER_X).copy()
    linie[10] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        formfehler(linie)


# -- Die Durchschnittslinie ------------------------------------------------

def test_glaette_nimmt_den_gleitenden_mittelwert():
    werte = np.arange(20, dtype=float)
    linie = glaette(werte, 0.25)          # Fenster 5
    assert len(linie) == 16
    assert linie[0] == pytest.approx(2.0)


def test_glaette_hat_ein_mindestfenster():
    """Unter drei Kerzen ist es keine Durchschnittslinie mehr."""
    assert len(glaette(np.arange(20, dtype=float), 0.01)) == 18


def test_glaette_bricht_bei_zu_kurzer_reihe_ab():
    with pytest.raises(ValueError, match="zu kurz"):
        glaette(np.arange(3, dtype=float), 0.5)


def test_glaette_prueft_den_anteil():
    with pytest.raises(ValueError, match="anteil"):
        glaette(np.arange(50, dtype=float), 1.5)
