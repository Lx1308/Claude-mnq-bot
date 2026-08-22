"""Setup-Bibliothek der Ideen-Protokollierung.

EINE FAMILIE JE SCHLUESSEL, RICHTUNG ALS EIGENE SPALTE
-----------------------------------------------------
``pdh_pdl_bruch`` ist EIN Setup, das long und short ausloesen kann - nicht
zwei Setups ``pdh_bruch`` und ``pdl_bruch``. Der Grund ist die spaetere
Auswertung: die Frage lautet "traegt der Vortagesmarken-Bruch", und erst
danach "und gibt es einen Unterschied zwischen long und short". Steckt die
Richtung im Schluessel, laesst sich die erste Frage nur noch durch
Zusammenaddieren zweier Kategorien beantworten.

KEINE ZWEITE SIGNAL-IMPLEMENTIERUNG
-----------------------------------
Jede Familie verweist auf eine :class:`RuleStrategy` aus
``backtest/strategies/library.py``. Die Ideen-Protokollierung wertet exakt
dieselben Regel-Objekte aus wie der Backtest. Eine eigene Erkenner-Fassung
hier haette bedeutet, dass der Backtest eine andere Strategie prueft als die,
die protokolliert wird - genau der Fehler, den die zentrale Invariante des
Projekts ausschliesst.

Ein frueherer Zwischenstand (``ideas/detectors.py``, Commit 739cd1c) hatte
genau diese zweite Fassung und wurde deshalb ersetzt.

ABWEICHUNG VON DER SPEZIFIKATION - FESTGESTELLT, NICHT STILL AUFGELOEST
----------------------------------------------------------------------
``ETAPPE_C_SPEZIFIKATION.md`` Abschnitt 2.1 nennt fuer die vier Familien die
bestehenden Strategien ``prev_day_breakout``, ``rsi_mean_reversion``,
``flag_breakout`` und ``vwap_trend``. Zwei davon passen nicht:

* ``rsi_mean_reversion`` ist eine RSI-Mittelwertrueckkehr und hat mit der
  Initial Balance nichts zu tun.
* ``vwap_trend`` ist Trendfolge (Einstieg MIT der VWAP-Kreuzung), waehrend
  ``vwap_reversion`` die Gegenbewegung zurueck zum Anker meint.

Statt die falsche Zuordnung zu uebernehmen, wurden ``ib_breakout`` und
``vwap_reversion`` als Fabriken in derselben Bibliothek ergaenzt - also im
bestehenden Regel-Framework, nicht als Sonderweg fuer ``ideas/``. Damit sind
beide auch im Backtest rechenbar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from backtest.strategies.base import RuleStrategy
from backtest.strategies.library import build_strategy
from common.config import IdeenSetupParameter

if TYPE_CHECKING:
    from common.config import IdeasConfig

# Art des Setups. Der ADX-Filter entscheidet danach, ob Trend oder Range
# gefordert wird: ein Bruch in der flachen Range ist meistens ein
# Fehlausbruch, eine Reversion im starken Trend laeuft dem Zug hinterher.
ART_FORTSETZUNG = "fortsetzung"
ART_REVERSION = "reversion"

# Spalten, die ``compute_indicators`` ohnehin liefert. Wer eine Familie
# ergaenzt, die darueber hinausgeht, traegt die Zusatzspalte in
# ``benoetigte_spalten`` ein - sonst liefe die Regel still ins Leere.
_BASIS_SPALTEN: tuple[str, ...] = ("open", "high", "low", "close", "atr", "vwap")


@dataclass(frozen=True)
class SetupDefinition:
    """Eine Setup-Familie und ihre Abbildung auf eine Backtest-Strategie."""

    schluessel: str
    beschreibung: str
    art: str
    #: Zusaetzlich zu ``_BASIS_SPALTEN`` benoetigte Spalten.
    zusatzspalten: tuple[str, ...]
    #: Baut die Strategie aus den konfigurierten Schwellenwerten.
    baue: Callable[[IdeenSetupParameter], RuleStrategy]

    @property
    def benoetigte_spalten(self) -> tuple[str, ...]:
        return _BASIS_SPALTEN + self.zusatzspalten


def _pdh_pdl_bruch(p: IdeenSetupParameter) -> RuleStrategy:
    return build_strategy(
        "prev_day_breakout",
        buffer_points=p.puffer_punkte,
        stop_loss_atr=p.stop_atr,
        take_profit_atr=p.ziel_atr,
        session_start=p.session_start,
        session_end=p.session_end,
    )


def _ib_bruch(p: IdeenSetupParameter) -> RuleStrategy:
    return build_strategy(
        "ib_breakout",
        buffer_points=p.puffer_punkte,
        stop_loss_atr=p.stop_atr,
        take_profit_atr=p.ziel_atr,
        session_start=p.session_start,
        session_end=p.session_end,
    )


def _vwap_reversion(p: IdeenSetupParameter) -> RuleStrategy:
    return build_strategy(
        "vwap_reversion",
        deviation_atr=p.abweichung_atr,
        stop_loss_atr=p.stop_atr,
        take_profit_atr=p.ziel_atr,
        session_start=p.session_start,
        session_end=p.session_end,
    )


def _flaggen_ausbruch(p: IdeenSetupParameter) -> RuleStrategy:
    return build_strategy(
        "flag_breakout",
        stop_loss_atr=p.stop_atr,
        take_profit_atr=p.ziel_atr,
        session_start=p.session_start,
        session_end=p.session_end,
    )


SETUP_PDH_PDL_BRUCH = "pdh_pdl_bruch"
SETUP_IB_BRUCH = "ib_bruch"
SETUP_VWAP_REVERSION = "vwap_reversion"
SETUP_FLAGGEN_AUSBRUCH = "flaggen_ausbruch"


SETUP_BIBLIOTHEK: dict[str, SetupDefinition] = {
    SETUP_PDH_PDL_BRUCH: SetupDefinition(
        schluessel=SETUP_PDH_PDL_BRUCH,
        beschreibung="Bruch des Vortageshochs bzw. -tiefs",
        art=ART_FORTSETZUNG,
        zusatzspalten=("prev_session_high", "prev_session_low", "rsi"),
        baue=_pdh_pdl_bruch,
    ),
    SETUP_IB_BRUCH: SetupDefinition(
        schluessel=SETUP_IB_BRUCH,
        beschreibung="Bruch der Initial Balance der ersten RTH-Stunde",
        art=ART_FORTSETZUNG,
        # ib_high/ib_low kommen NICHT aus compute_indicators, sondern aus
        # common.levels.initial_balance_per_session. Fehlen sie, wuerde die
        # Regel dauerhaft stumm bleiben - deshalb stehen sie hier.
        zusatzspalten=("ib_high", "ib_low"),
        baue=_ib_bruch,
    ),
    SETUP_VWAP_REVERSION: SetupDefinition(
        schluessel=SETUP_VWAP_REVERSION,
        beschreibung="Rueckkehr zum VWAP nach weiter Abweichung",
        art=ART_REVERSION,
        zusatzspalten=(),
        baue=_vwap_reversion,
    ),
    SETUP_FLAGGEN_AUSBRUCH: SetupDefinition(
        schluessel=SETUP_FLAGGEN_AUSBRUCH,
        beschreibung="Ausbruch aus der Konsolidierung nach einem Impuls",
        art=ART_FORTSETZUNG,
        zusatzspalten=(
            "flag_breakout_up",
            "flag_breakout_down",
            "sma_fast",
            "sma_slow",
        ),
        baue=_flaggen_ausbruch,
    ),
}

ALLE_SETUPS: tuple[str, ...] = tuple(SETUP_BIBLIOTHEK)


class UnbekanntesSetup(KeyError):
    """Der Schluessel steht nicht in der Setup-Bibliothek."""


def hole_setup(schluessel: str) -> SetupDefinition:
    definition = SETUP_BIBLIOTHEK.get(schluessel)
    if definition is None:
        raise UnbekanntesSetup(
            f"Unbekanntes Setup {schluessel!r}. Verfuegbar: "
            + ", ".join(sorted(SETUP_BIBLIOTHEK))
        )
    return definition


def pruefe_konfiguration(cfg: "IdeasConfig") -> None:
    """Startpruefung der Ideen-Konfiguration gegen die Setup-Bibliothek.

    Steht hier und nicht in ``Config.validate``, weil ``common`` die
    Basisschicht ist und nichts aus ``ideas`` importieren soll - sonst
    haenge auch die Importhuelle des MCP-Servers mit daran.

    Bricht ab statt zu warnen: ein Schluessel, den die Bibliothek nicht
    kennt, sieht in der ``config.yaml`` aus wie eine konfigurierte Familie,
    loest aber nie aus. Das waere genau die Art stiller Ausfall, die dieses
    Projekt wiederholt teuer bezahlt hat.
    """
    from common.config import ConfigError

    unbekannt = sorted(set(cfg.setups) - set(SETUP_BIBLIOTHEK))
    if unbekannt:
        raise ConfigError(
            f"ideas.setups enthaelt unbekannte Schluessel: {', '.join(unbekannt)}. "
            f"Verfuegbar: {', '.join(sorted(SETUP_BIBLIOTHEK))}. "
            "Ein unbekannter Schluessel wirkt wie eine konfigurierte Familie, "
            "loest aber nie aus."
        )

    if not any(
        cfg.setup_parameter(schluessel).aktiv for schluessel in SETUP_BIBLIOTHEK
    ):
        raise ConfigError(
            "Keine einzige Setup-Familie ist aktiv. Die Protokollierung liefe "
            "dann dauerhaft ohne Ergebnis."
        )


__all__ = [
    "ALLE_SETUPS",
    "ART_FORTSETZUNG",
    "ART_REVERSION",
    "SETUP_BIBLIOTHEK",
    "SETUP_FLAGGEN_AUSBRUCH",
    "SETUP_IB_BRUCH",
    "SETUP_PDH_PDL_BRUCH",
    "SETUP_VWAP_REVERSION",
    "SetupDefinition",
    "UnbekanntesSetup",
    "hole_setup",
    "pruefe_konfiguration",
]
