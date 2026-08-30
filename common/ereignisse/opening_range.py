"""Opening Range je Handelstag - als Niveau-Serie, nicht als eigener Erkenner.

Die ersten Minuten nach der RTH-Eroeffnung spannen eine Range auf, an der sich
der Rest des Tages oft orientiert. Das ist dasselbe Prinzip wie die Initial
Balance (erste Stunde), nur mit kuerzerem Fenster - und **genau deshalb gibt
es hier keinen eigenen Erkenner**: Test, Ausbruch, Fehlausbruch und Sweep an
einer OR-Grenze sind dieselben Muster wie an jeder anderen Marke. Sie kommen
aus ``niveaus.py`` und ``sweeps.py``, sobald die OR-Serien als Niveauquelle
angemeldet sind.

Ein dritter Erkenner mit derselben Logik waere derselbe Fehler wie eine zweite
Indikator-Implementierung (Invariante 1): er wuerde mit der Zeit auseinander-
laufen, und dann untersuchte man an der OR ein anderes Muster als am
Vortageshoch.

FENSTER
-------
Drei Laengen, weil sie unterschiedliche Dinge messen und sich nicht
ineinander umrechnen lassen:

* **5 min**  - die Eroeffnungsauktion selbst
* **15 min** - die uebliche "Opening Range" der Intraday-Literatur
* **30 min** - die halbe Initial Balance

Die 60-Minuten-Variante ist die Initial Balance und steht bereits als
``ib_high``/``ib_low`` zur Verfuegung; sie wird hier nicht wiederholt.

LOOKAHEAD-SCHUTZ
----------------
Wie bei ``initial_balance_per_session``: die Werte bleiben ``NaN``, **solange
das Fenster laeuft**. Eine Kerze um 09:38 kennt das 15-Minuten-Hoch nicht, das
erst um 09:45 feststeht. Wuerde man den Tageswert auf alle Kerzen verteilen,
waere jede darauf gebaute Auswertung wertlos - und nichts an den Kursen
verriete es.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.config import SessionConfig
from common.instruments import Instrument
from common.levels import _minutes_from_rth_open, rth_mask
from common.sessions import session_dates

#: Fensterlaengen in Minuten. 60 fehlt bewusst - das ist die Initial Balance.
OR_FENSTER: tuple[int, ...] = (5, 15, 30)


def opening_range_spalten(
    df: pd.DataFrame,
    instrument: Instrument,
    session_cfg: SessionConfig,
    *,
    fenster: tuple[int, ...] = OR_FENSTER,
) -> pd.DataFrame:
    """Opening-Range-Hoch/-Tief je Handelstag, auf jede Kerze abgebildet.

    Spalten ``or{n}_high`` / ``or{n}_low`` je Fensterlaenge, ``NaN`` bis das
    jeweilige Fenster abgelaufen ist.
    """
    spalten: dict[str, np.ndarray] = {}
    leer = np.full(len(df), np.nan)
    for minuten in fenster:
        spalten[f"or{minuten}_high"] = leer.copy()
        spalten[f"or{minuten}_low"] = leer.copy()
    if df.empty:
        return pd.DataFrame(spalten, index=df.index)

    tage = session_dates(df.index, session_cfg)
    innerhalb_rth = rth_mask(df, instrument)
    verstrichen = _minutes_from_rth_open(df, instrument)

    for minuten in fenster:
        im_fenster = (
            innerhalb_rth & (verstrichen >= 0) & (verstrichen < minuten)
        )
        if not bool(im_fenster.any()):
            continue

        teil = df[im_fenster.values]
        tage_im_fenster = tage[im_fenster.values]
        hoch = teil["high"].groupby(tage_im_fenster.values).max()
        tief = teil["low"].groupby(tage_im_fenster.values).min()

        # ``copy()``: ``Series.to_numpy()`` kann eine schreibgeschuetzte Sicht
        # auf den Blockspeicher liefern (pandas 3), und die Maskierung
        # gleich darunter schreibt hinein.
        h = tage.map(hoch).astype("float64").to_numpy().copy()
        t = tage.map(tief).astype("float64").to_numpy().copy()
        # Erst nach Ablauf des Fensters sichtbar machen.
        noch_nicht = (verstrichen < minuten).to_numpy()
        h[noch_nicht] = np.nan
        t[noch_nicht] = np.nan

        spalten[f"or{minuten}_high"] = h
        spalten[f"or{minuten}_low"] = t

    return pd.DataFrame(spalten, index=df.index)


def or_spaltennamen(fenster: tuple[int, ...] = OR_FENSTER) -> tuple[str, ...]:
    """Die erzeugten Spaltennamen, in fester Reihenfolge."""
    namen: list[str] = []
    for minuten in fenster:
        namen.append(f"or{minuten}_high")
        namen.append(f"or{minuten}_low")
    return tuple(namen)


__all__ = [
    "OR_FENSTER",
    "opening_range_spalten",
    "or_spaltennamen",
]
