"""Die W-Form als Schablone, nicht als Sammlung von Einzelregeln.

WARUM
-----
Laurins Kriterium lautet woertlich: *"am einfachsten ist, wenn man ein W
drueberlegt und das ca. passt."* Der Vorgaenger hat das in drei getrennte
Regeln zerlegt - hoechstens 25 % Rueckschlag je Schenkel, Gipfel zwischen
10 % und 90 % der Dauer, kein Schenkel mehr als dreimal so lang wie der
andere. Drei Schwellen, die sich gegenseitig ins Gehege kommen: eine Form
kann jede einzeln bestehen und trotzdem nicht wie ein W aussehen, und
umgekehrt.

Hier steht stattdessen EINE Kennzahl - der Formfehler. Er ist die kleinste
mittlere quadratische Abweichung zwischen der geglaetteten Kurslinie und
einer idealen W-Schablone, deren Gipfellage frei verschoben wird. Null heisst
"deckungsgleich", grosse Werte heissen "sieht nicht so aus".

WAS DAS NEBENBEI LOEST
----------------------
Die Plateau-Frage aus ``docs/W_DEFINITION_OFFEN.md`` 6.2 braucht keine eigene
Regel mehr. Laurins markierte Rauschphase - zehn flache Kerzen in einem
15-Kerzen-Fenster - kann sich der Schablone nicht anschmiegen, egal wo deren
Gipfel liegt: die Schablone steigt und faellt durchgehend, das Plateau tut
weder das eine noch das andere. Der Formfehler wird gross, ohne dass jemand
"Plateau" definieren muesste.

NORMIERUNG
----------
Zeit und Preis werden je auf [0,1] gestreckt - MIN-MAX, nicht z-Normierung.
Die z-Normierung wuerde die Form an der Streuung messen und damit ein flaches
Muster kuenstlich aufblasen. Die absolute Hoehe ist hier bewusst NICHT
Gegenstand der Pruefung; dafuer gibt es ``min_hoehe_atr``.

Der Formfehler ist damit dimensionslos und zwischen einem 20-Punkte-W und
einem 140-Punkte-W direkt vergleichbar.

DIE SCHWELLE STEHT NICHT HIER
-----------------------------
Ab welchem Formfehler eine Form kein W mehr ist, ergibt sich aus Laurins
Urteilen im Referenzsatz (``werkzeuge/w_referenz.py``), nicht aus einer
Schaetzung. Solange ``patterns.doppelboden.max_formfehler`` in der Config
fehlt, wird der Wert nur ausgegeben.
"""

from __future__ import annotations

import numpy as np

#: Gipfellage: von 10 % bis 90 % der Formationsdauer in 2-%-Schritten.
#: Enger als 10 % waere keine Formation mehr, sondern eine Flanke.
GIPFEL_VON = 0.10
GIPFEL_BIS = 0.90
GIPFEL_SCHRITT = 0.02

#: Aufloesung, auf der Linie und Schablone verglichen werden. Fest, damit der
#: Formfehler eines 15-Kerzen-Musters mit dem eines 200-Kerzen-Musters
#: vergleichbar bleibt - sonst haetten lange Formationen mehr Stuetzstellen
#: und allein dadurch einen anderen Fehler.
RASTER = 101


def schablone(p: float, x: np.ndarray) -> np.ndarray:
    """Die ideale W-Form zwischen den beiden Tiefs, Gipfel bei ``p``.

    Fuenf Ankerpunkte, dazwischen linear interpoliert:

        (0, 0)  -  (p/2, 0.5)  -  (p, 1)  -  ((1+p)/2, 0.5)  -  (1, 0)

    Die beiden mittleren Anker liegen zurzeit exakt auf den Geraden zwischen
    ihren Nachbarn; die Schablone ist also ein aufsteigender und ein
    absteigender Schenkel. Sie sind trotzdem ausgeschrieben, weil genau an
    diesen Stellen eine gekruemmte Schablone ansetzen wuerde, sollte sich die
    Kalibrierung als zu streng erweisen - dann steht die Aenderung an einer
    Stelle und nicht verstreut in einer Formel.

    Nur der INNERE Teil des W wird beschrieben, von Tief zu Tief. Die beiden
    aeusseren Arme des Buchstabens liegen ausserhalb des Segments; der linke
    wird ueber ``min_linker_arm`` geprueft.
    """
    anker_x = np.array([0.0, p / 2.0, p, (1.0 + p) / 2.0, 1.0])
    anker_y = np.array([0.0, 0.5, 1.0, 0.5, 0.0])
    return np.interp(x, anker_x, anker_y)


def formfehler(linie: np.ndarray) -> tuple[float, float]:
    """Kleinster Abstand zur W-Schablone und die zugehoerige Gipfellage.

    ``linie`` ist die bereits GEGLAETTETE Kurslinie von Tief 1 bis Tief 2.
    Zurueck kommt ``(fehler, gipfellage)``:

    * ``fehler`` - Wurzel der mittleren quadratischen Abweichung in
      normierten Preiseinheiten. 0 = deckungsgleich.
    * ``gipfellage`` - Position des Schablonengipfels, Anteil der Dauer.

    Eine Linie ohne Preisspanne (alle Werte gleich) hat keine Form; sie
    bekommt ``(inf, nan)`` statt eines erfundenen Wertes.
    """
    werte = np.asarray(linie, dtype=float)
    if werte.ndim != 1:
        raise ValueError("linie muss eindimensional sein.")
    if len(werte) < 5:
        raise ValueError(
            f"linie hat nur {len(werte)} Stuetzstellen - unter fuenf laesst "
            "sich eine W-Form nicht von einer Geraden unterscheiden."
        )
    if not np.all(np.isfinite(werte)):
        raise ValueError("linie enthaelt NaN oder inf.")

    spanne = float(werte.max() - werte.min())
    if spanne <= 0.0:
        return float("inf"), float("nan")

    # Auf das feste Raster bringen, dann Preis auf [0,1].
    x = np.linspace(0.0, 1.0, RASTER)
    y = np.interp(x, np.linspace(0.0, 1.0, len(werte)), werte)
    y = (y - werte.min()) / spanne

    bester = float("inf")
    bestes_p = float("nan")
    for p in np.arange(GIPFEL_VON, GIPFEL_BIS + 1e-9, GIPFEL_SCHRITT):
        abweichung = y - schablone(float(p), x)
        fehler = float(np.sqrt(np.mean(abweichung * abweichung)))
        if fehler < bester:
            bester, bestes_p = fehler, float(p)
    return bester, bestes_p


def glaette(werte: np.ndarray, anteil: float) -> np.ndarray:
    """Die Durchschnittslinie ueber ``werte``, Fenster als Anteil der Laenge.

    Gleitender Mittelwert, ``mode="valid"`` - kein Randwert wird aus weniger
    Kerzen gebildet als die anderen. Das kostet Laenge am Rand und ist
    trotzdem richtig: ein aus drei statt zwoelf Kerzen gemittelter Randwert
    zappelt staerker als der Rest und wuerde genau dort einen Formfehler
    erzeugen, wo die Tiefs sitzen.
    """
    werte = np.asarray(werte, dtype=float)
    if not 0.0 < anteil < 1.0:
        raise ValueError("anteil muss zwischen 0 und 1 liegen.")
    fenster = max(3, int(len(werte) * anteil))
    if len(werte) <= fenster:
        raise ValueError(
            f"{len(werte)} Werte bei Fenster {fenster} - zu kurz zum Glaetten."
        )
    return np.convolve(werte, np.ones(fenster) / fenster, mode="valid")


__all__ = ["schablone", "formfehler", "glaette",
           "GIPFEL_VON", "GIPFEL_BIS", "GIPFEL_SCHRITT", "RASTER"]
