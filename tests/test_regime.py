"""Marktregime auf drei Achsen.

Zwei Dinge werden hier abgesichert:

1. **Kein Lookahead.** Die Perzentile ueber die Gesamthistorie zu rechnen
   waere bequem und falsch - das Regime einer Kerze von 2019 haenge dann
   davon ab, wie volatil 2026 war. Im Backtest saehe das ausgezeichnet aus,
   und live gaebe es diese Information nicht.
2. **Der dritte Ausgang.** Wo das Fenster noch nicht gefuellt ist, steht
   ``None`` - unbestimmt - und nicht das naechstbeste Regime. Dieselbe
   Haltung wie bei den Filtern der Ideen-Protokollierung.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from common.indicators import compute_indicators
from common.regime import (
    ACHSEN,
    REGIME_SPALTEN,
    fenster_kerzen,
    regime_spalten,
    relatives_volumen,
    verteilung,
)


def _markt(n: int = 6000, *, seed: int = 20260830) -> pd.DataFrame:
    """Kursverlauf mit wechselnder Volatilitaet und Volumen-Tagesform.

    Nicht als Marktmodell - nur damit die Achsen etwas zu trennen haben.
    """
    rng = np.random.default_rng(seed)
    # Volatilitaet in Bloecken wechseln lassen.
    sigma = np.repeat(rng.choice([2.0, 6.0, 14.0], size=n // 300 + 1), 300)[:n]
    preise = 20000.0 + np.cumsum(rng.normal(0.0, 1.0, n) * sigma)

    index = pd.date_range("2024-01-02 00:00", periods=n, freq="5min", tz="UTC")
    # Volumen mit Tagesform: mittags viel, nachts wenig.
    stunde = index.hour.to_numpy()
    tagesform = 300 + 2500 * np.exp(-((stunde - 15) ** 2) / 18.0)
    volumen = tagesform * rng.uniform(0.5, 1.8, n)

    spanne = np.abs(rng.normal(1.0, 0.4, n)) * sigma + 1.0
    return pd.DataFrame(
        {
            "open": preise,
            "high": preise + spanne,
            "low": preise - spanne,
            "close": preise + rng.normal(0.0, 0.5, n),
            "volume": volumen,
        },
        index=index,
    )


@pytest.fixture
def vorbereitet(indicator_cfg, session_cfg) -> pd.DataFrame:
    return compute_indicators(_markt(), indicator_cfg, session_cfg)


# -- Form -------------------------------------------------------------------

def test_alle_spalten_entstehen(vorbereitet, indicator_cfg, session_cfg):
    regime = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    assert list(regime.columns) == list(REGIME_SPALTEN)
    assert len(regime) == len(vorbereitet)


def test_jede_achse_nutzt_alle_drei_auspraegungen(vorbereitet, indicator_cfg, session_cfg):
    """Eine Achse, die nur eine Auspraegung vergibt, trennt nichts."""
    regime = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    for achse, namen in ACHSEN.items():
        vorhanden = set(regime[achse].dropna().unique())
        assert vorhanden == set(namen), f"{achse} vergibt nur {vorhanden}"


def test_ohne_atr_bricht_es_ab_statt_zu_raten():
    df = _markt(400)
    with pytest.raises(ValueError, match="ATR"):
        regime_spalten(df, None, None)  # type: ignore[arg-type]


# -- Der dritte Ausgang -----------------------------------------------------

def test_vor_dem_fenstervorlauf_ist_das_regime_unbestimmt(
    vorbereitet, indicator_cfg, session_cfg
):
    """Nicht das naechstbeste Regime, sondern None."""
    regime = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    assert regime["regime"].iloc[0] is None
    assert regime["regime"].isna().sum() > 0


def test_eine_unbestimmte_achse_macht_die_schublade_unbestimmt(
    vorbereitet, indicator_cfg, session_cfg
):
    """Eine halb bestimmte Schublade waere schlimmer als gar keine."""
    regime = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    achsen_unbestimmt = regime[list(ACHSEN)].isna().any(axis=1)
    assert regime.loc[achsen_unbestimmt, "regime"].isna().all()


# -- Kein Lookahead ---------------------------------------------------------

def test_spaetere_kerzen_aendern_ein_frueheres_regime_nicht(
    vorbereitet, indicator_cfg, session_cfg
):
    """DER Test dieses Moduls.

    Perzentile ueber die Gesamthistorie zu rechnen waere bequem und falsch:
    das Regime einer Kerze von 2019 haenge dann davon ab, wie volatil 2026
    war. Hier wird die Reihe abgeschnitten und geprueft, dass die
    Regime-Zuordnung der verbleibenden Kerzen identisch bleibt.
    """
    kurz_ende = 4000
    voll = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    kurz = regime_spalten(
        vorbereitet.iloc[:kurz_ende],
        indicator_cfg,
        session_cfg,
        kerzen_minuten=5,
        sessions=6,
    )

    for spalte in ACHSEN:
        a = voll[spalte].iloc[:kurz_ende]
        b = kurz[spalte]
        unterschiede = int((a.fillna("-") != b.fillna("-")).sum())
        assert unterschiede == 0, (
            f"{spalte}: {unterschiede} von {kurz_ende} Kerzen aendern ihr "
            "Regime, wenn spaetere Daten dazukommen - das ist Lookahead."
        )


def test_auch_die_raenge_sind_rueckwaertsgerichtet(
    vorbereitet, indicator_cfg, session_cfg
):
    """Nicht nur die Auspraegung, auch die Zahl dahinter."""
    kurz_ende = 4000
    voll = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    kurz = regime_spalten(
        vorbereitet.iloc[:kurz_ende], indicator_cfg, session_cfg,
        kerzen_minuten=5, sessions=6,
    )
    for spalte in ("vola_rang", "struktur_rang", "liquiditaet_rang"):
        pd.testing.assert_series_equal(
            voll[spalte].iloc[:kurz_ende], kurz[spalte], check_names=False
        )


# -- Relatives Volumen ------------------------------------------------------

def test_relatives_volumen_bezieht_sich_auf_dieselbe_tageszeit():
    """Ein roher Volumenrang wuerde die Eroeffnung immer als 'rege' und die
    Nacht immer als 'duenn' einstufen - eine Aussage, die schon in der
    Session-Angabe steckt und nichts hinzufuegt."""
    df = _markt(4000)
    relativ = relatives_volumen(df, sessions=6)

    gueltig = relativ.dropna()
    assert len(gueltig) > 1000
    # Um 1 herum verteilt, weil auf den eigenen Tageszeit-Median bezogen.
    assert 0.8 < float(gueltig.median()) < 1.25

    # Und: die Tagesform darf sich NICHT mehr im Mittelwert je Stunde zeigen.
    je_stunde = gueltig.groupby(gueltig.index.hour).median()
    assert float(je_stunde.max() - je_stunde.min()) < 0.5, (
        "Das relative Volumen traegt noch die Tagesform - dann misst die "
        "Liquiditaetsachse die Uhrzeit statt der Aktivitaet."
    )


def test_nullvolumen_erzeugt_keine_unendlichkeit():
    df = _markt(2000)
    df["volume"] = 0.0
    relativ = relatives_volumen(df, sessions=6)
    assert not np.isinf(relativ.to_numpy(dtype=float)).any()


# -- Fenstergroesse ---------------------------------------------------------

def test_fenster_skaliert_mit_der_kerzenlaenge():
    """60 Sessions sind auf 1m sehr viel mehr Kerzen als auf 1h."""
    assert fenster_kerzen(1) > fenster_kerzen(5) > fenster_kerzen(60)


def test_unbekannte_kerzenlaenge_bricht_ab():
    with pytest.raises(ValueError, match="7"):
        fenster_kerzen(7)


# -- Bericht ----------------------------------------------------------------

def test_verteilung_zaehlt_die_schubladen(vorbereitet, indicator_cfg, session_cfg):
    regime = regime_spalten(
        vorbereitet, indicator_cfg, session_cfg, kerzen_minuten=5, sessions=6
    )
    v = verteilung(regime)

    assert v.gesamt == len(regime)
    assert v.unbestimmt == int(regime["regime"].isna().sum())
    assert v.kombiniert.sum() == v.gesamt - v.unbestimmt
    assert "Kerzen" in v.bericht()
