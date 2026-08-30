"""Event-getriebene Backtest-Engine fuer Futures.

Ausfuehrungsmodell (bewusst konservativ)
---------------------------------------
* Regeln werden auf dem **Schluss** einer Kerze ausgewertet.
* Ausgefuehrt wird zur **Eroeffnung der Folgekerze**. Damit ist Look-ahead
  strukturell ausgeschlossen - der haeufigste Grund fuer Backtests, die
  live nicht funktionieren.
* Stop und Ziel werden **innerhalb** der Kerze anhand von High/Low geprueft.
  Werden beide in derselben Kerze beruehrt, wird der **Stop** angenommen
  (pessimistisch, weil aus OHLC nicht rekonstruierbar ist, was zuerst kam).
* Es ist immer hoechstens **eine** Position offen.
* Kosten: Kommission je Seite plus Slippage je Seite in Ticks, jeweils
  gegen die eigene Position gerichtet.

Warum eine eigene Engine und nicht backtesting.py oder vectorbt?
Siehe ``docs/BACKTESTING_ENTSCHEIDUNG.md`` - kurz: Punktwert und Ticksize
von CME-Kontrakten, eine Position zu jedem Zeitpunkt, intrabar-Stops und
eine erzwungene In-Sample/Out-of-Sample-Trennung liessen sich mit beiden
Bibliotheken nur ueber Umwege abbilden.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from backtest.kosten import Kostenprofil
from backtest.strategies.base import BarContext, RuleStrategy
from common.config import IndicatorConfig, MarketConfig, SessionConfig
from common.ereignisse.opening_range import opening_range_spalten
from common.indicators import compute_indicators
from common.instruments import get_instrument
from common.levels import initial_balance_per_session
from common.muster_serie import doppelmuster_spalten
from common.sessions import session_dates
from common.strukturniveaus import strukturniveau_spalten

log = logging.getLogger(__name__)

LONG = 1
SHORT = -1
FLAT = 0


class ExitReason:
    SIGNAL = "signal"
    STOP = "stop"
    TARGET = "target"
    TIME = "zeitstop"
    SESSION_END = "sessionende"
    END_OF_DATA = "datenende"


@dataclass(frozen=True)
class Trade:
    direction: int
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    bars_held: int
    exit_reason: str
    gross_points: float
    commission: float
    pnl: float           # netto in USD

    @property
    def is_win(self) -> bool:
        return self.pnl > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "richtung": "long" if self.direction == LONG else "short",
            "einstieg": self.entry_time.isoformat(),
            "einstiegskurs": round(self.entry_price, 4),
            "ausstieg": self.exit_time.isoformat(),
            "ausstiegskurs": round(self.exit_price, 4),
            "kerzen": self.bars_held,
            "grund": self.exit_reason,
            "punkte_brutto": round(self.gross_points, 4),
            "kommission": round(self.commission, 2),
            "pnl_usd": round(self.pnl, 2),
        }


@dataclass
class BacktestResult:
    strategy_name: str
    strategy_description: str
    trades: list[Trade] = field(default_factory=list)
    equity: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    bars: int = 0
    period_start: datetime | None = None
    period_end: datetime | None = None
    label: str = ""   # z.B. "in-sample" / "out-of-sample"

    #: Womit gerechnet wurde. Pflicht, seit es mehrere Kostenprofile gibt:
    #: dieselbe Strategie ist unter 0,50 und unter 2,50 USD je Seite ein
    #: voellig anderes Geschaeft, und ein Ergebnis ohne diese Angabe laesst
    #: sich nicht einordnen.
    kosten: dict[str, Any] = field(default_factory=dict)

    #: Wie oft der Stop tatsaechlich auf einem Strukturniveau sass und wie
    #: oft auf das ATR-Vielfache zurueckgefallen wurde.
    #:
    #: WARUM DAS IM ERGEBNIS STEHT: ohne diese Zahl liesse sich eine
    #: Stop-Variante nicht beurteilen. Griff das Niveau nur bei einem Zehntel
    #: der Trades, misst man ueberwiegend den Rueckfall und nennt es "Stop am
    #: letzten Tief".
    strukturstops: int = 0
    stop_rueckfaelle: int = 0

    @property
    def strukturstop_anteil(self) -> float | None:
        """Anteil der Trades mit echtem Strukturstop. ``None`` ohne Trades."""
        gesamt = self.strukturstops + self.stop_rueckfaelle
        return self.strukturstops / gesamt if gesamt else None

    def trades_dataframe(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(
                columns=[
                    "richtung", "einstieg", "einstiegskurs", "ausstieg",
                    "ausstiegskurs", "kerzen", "grund", "punkte_brutto",
                    "kommission", "pnl_usd",
                ]
            )
        return pd.DataFrame([trade.to_dict() for trade in self.trades])


@dataclass(frozen=True)
class CostModel:
    """Handelskosten eines Laufs.

    Traegt seit dem 23.08.2026 ein benanntes :class:`Kostenprofil` statt einer
    Pauschale. Der Grund steht in ``backtest/kosten.py``: Broker-Kommission,
    nicht verhandelbare Boersengebuehren und Slippage verhalten sich
    unterschiedlich und gehoeren getrennt.

    ``commission_per_side`` bleibt als Feld erhalten, damit bestehende Aufrufe
    weiterlaufen. Ist ein ``profil`` gesetzt, hat **es** Vorrang - so laesst
    sich dasselbe Setup unter mehreren Profilen rechnen, ohne die Strategie
    anzufassen.
    """

    commission_per_side: float = 2.50
    slippage_ticks_per_side: float = 1.0
    tick_size: float = 0.25
    point_value: float = 20.0
    contracts: int = 1
    profil: "Kostenprofil | None" = None

    @classmethod
    def aus_profil(
        cls,
        profil: "Kostenprofil",
        *,
        tick_size: float,
        point_value: float,
        contracts: int = 1,
    ) -> "CostModel":
        """Der bevorzugte Weg, ein Kostenmodell zu bauen."""
        return cls(
            commission_per_side=profil.summe_je_seite,
            slippage_ticks_per_side=profil.slippage_ticks_je_seite,
            tick_size=tick_size,
            point_value=point_value,
            contracts=contracts,
            profil=profil,
        )

    @property
    def _je_seite(self) -> float:
        return (
            self.profil.summe_je_seite
            if self.profil is not None
            else self.commission_per_side
        )

    @property
    def slippage_points(self) -> float:
        ticks = (
            self.profil.slippage_ticks_je_seite
            if self.profil is not None
            else self.slippage_ticks_per_side
        )
        return ticks * self.tick_size

    @property
    def round_turn_commission(self) -> float:
        return 2.0 * self._je_seite * self.contracts

    def herkunft(self) -> dict[str, Any]:
        """Womit gerechnet wurde - gehoert in jeden Bericht.

        Ohne diese Angabe laesst sich ein Ergebnis nicht einordnen: dieselbe
        Strategie ist unter 0,50 und unter 2,50 USD je Seite ein voellig
        anderes Geschaeft.
        """
        if self.profil is not None:
            return self.profil.to_dict()
        return {
            "name": "unbenannt",
            "beschreibung": "Direkt gesetzte Werte ohne Profil.",
            "je_seite_usd": round(self.commission_per_side, 4),
            "round_turn_usd": round(2.0 * self.commission_per_side, 4),
            "slippage_ticks_je_seite": self.slippage_ticks_per_side,
            "ist_annahme": True,
            "quelle": "im Aufruf gesetzt, keine Herkunft hinterlegt",
            "aufschluesselung": None,
            "aufschluesselung_hinweis": "Kein Kostenprofil verwendet.",
        }


class Backtester:
    """Fuehrt eine :class:`RuleStrategy` auf einem OHLCV-DataFrame aus."""

    def __init__(
        self,
        market_cfg: MarketConfig,
        indicator_cfg: IndicatorConfig,
        costs: CostModel | None = None,
    ) -> None:
        self._market = market_cfg
        self._indicators = indicator_cfg
        self._costs = costs or CostModel(
            tick_size=market_cfg.tick_size, point_value=market_cfg.point_value
        )

    # -- Vorbereitung ------------------------------------------------------

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """Berechnet alle Indikatorspalten - identisch zum Live-Bot.

        Initial-Balance-Grenzen (``ib_high``/``ib_low``) kommen aus
        ``common.levels.initial_balance_per_session`` - derselben Funktion,
        die auch ``ideas.pipeline.vorbereiten`` und der MCP-Snapshot nutzen.
        Keine zweite Berechnung: ohne diesen Aufruf bricht ``ib_breakout``
        beim Backtest ab, weil die Strategie die Spalten braucht, die
        ``compute_indicators`` allein nicht liefert.
        """
        enriched = compute_indicators(df, self._indicators, self._market.session)
        enriched["session_date"] = session_dates(enriched.index, self._market.session).values
        instrument = get_instrument(self._market.product)
        ib = initial_balance_per_session(enriched, instrument, self._market.session)
        for spalte in ib.columns:
            enriched[spalte] = ib[spalte]

        # Opening Range (5/15/30 Minuten) - dieselbe Bauart wie die Initial
        # Balance, nur kuerzere Fenster. Sie sind Niveauquellen fuer die
        # Ereignis-Erkenner, kein eigenes Muster.
        opening = opening_range_spalten(enriched, instrument, self._market.session)
        for spalte in opening.columns:
            enriched[spalte] = opening[spalte]

        # Chartmuster als Serie (Doppelboden/Doppeltop). Aus
        # common/muster_serie.py, das dieselben Schwellen benutzt wie der
        # punktuelle Erkenner in common/patterns.py - ein Test haelt fest,
        # dass beide zum selben Urteil kommen.
        #
        # Die Spalten stehen auf dem Verfuegbarkeitszeitpunkt, nicht auf dem
        # Extrem: ein Swing-Tief ist an seiner eigenen Kerze nicht erkennbar.
        muster = doppelmuster_spalten(enriched, atr=enriched.get("atr"))
        for spalte in muster.columns:
            enriched[spalte] = muster[spalte]

        # Strukturniveaus - wohin ein Stop chartlich gehoert. Auch hier auf
        # dem Verfuegbarkeitszeitpunkt: ein Stop auf einem Tief, das beim
        # Einstieg noch nicht bestaetigt war, ist Wissen aus der Zukunft.
        niveaus = strukturniveau_spalten(enriched)
        for spalte in niveaus.columns:
            enriched[spalte] = niveaus[spalte]
        return enriched

    # -- Hauptschleife -----------------------------------------------------

    def run(
        self,
        df: pd.DataFrame,
        strategy: RuleStrategy,
        *,
        label: str = "",
        already_prepared: bool = False,
    ) -> BacktestResult:
        data = df if already_prepared else self.prepare(df)
        if len(data) < 2:
            raise ValueError("Fuer einen Backtest werden mindestens zwei Kerzen benoetigt.")

        fehlend = sorted(strategy.benoetigte_spalten() - set(data.columns))
        if fehlend:
            # Abbrechen statt stumm null Trades zu liefern: eine Regel auf einer
            # nicht vorhandenen Spalte liest NaN und feuert nie. Das Ergebnis
            # saehe aus wie "hat nicht gegriffen" statt wie ein Defekt.
            raise ValueError(
                "Strategie '%s' braucht Spalten, die der vorbereitete Datensatz "
                "nicht enthaelt: %s.\nVorhanden sind: %s.\nEntweder erzeugt "
                "common.indicators.compute_indicators diese Spalten nicht, oder "
                "der Datensatz wurde nicht ueber Backtester.prepare geschickt."
                % (strategy.name, ", ".join(fehlend), ", ".join(sorted(data.columns)))
            )

        opens = data["open"].to_numpy(dtype=float)
        highs = data["high"].to_numpy(dtype=float)
        lows = data["low"].to_numpy(dtype=float)
        closes = data["close"].to_numpy(dtype=float)
        atrs = data["atr"].to_numpy(dtype=float)
        sessions = data["session_date"].to_numpy()
        timestamps = data.index

        # Nur die Spalten als Arrays vorhalten, die diese Strategie
        # tatsaechlich liest.
        #
        # WARUM: die Schleife baute je Kerze zwei pandas-Series ueber
        # data.iloc[i]. Bei einem vorbereiteten Rahmen mit ueber vierzig
        # Spalten ist das der Engpass des ganzen Laufs - und er waechst mit
        # jeder Spalte, die irgendwo dazukommt, auch wenn die Strategie sie
        # gar nicht braucht. Ueber sieben Jahre 5m-Daten (519.000 Kerzen)
        # macht das Minuten aus.
        #
        # BarContext.value greift ueber .get() zu; ein Dict genuegt dafuer.
        gebraucht = sorted(strategy.benoetigte_spalten() & set(data.columns))
        spaltenwerte = {
            name: data[name].to_numpy() for name in gebraucht
        }

        def zeile(index: int) -> dict[str, Any]:
            return {name: werte[index] for name, werte in spaltenwerte.items()}

        # Strukturelle Stops und Ziele lesen ihr Niveau aus einer Spalte.
        tick_size = self._costs.tick_size
        strukturstops = 0
        stop_rueckfaelle = 0

        def _strukturniveau(
            spalte: str | None, index: int, richtung: int, *, puffer: float
        ) -> float | None:
            """Das Niveau der Entscheidungskerze, um ``puffer`` verschoben.

            ``puffer`` ist bereits vorzeichenbehaftet gedacht: negativ heisst
            "jenseits des Niveaus in Positionsrichtung" (Stop), positiv
            heisst "diesseits" (Ziel). Multipliziert wird mit der Richtung,
            damit dieselbe Angabe fuer Long und Short passt.
            """
            if not spalte or index < 0:
                return None
            werte = spaltenwerte.get(spalte)
            if werte is None:
                return None
            roh = werte[index]
            try:
                niveau = float(roh)
            except (TypeError, ValueError):
                return None
            if np.isnan(niveau):
                return None
            return niveau + richtung * puffer

        trades: list[Trade] = []
        equity_values = np.zeros(len(data), dtype=float)

        realized = 0.0
        position = FLAT
        entry_price = 0.0
        entry_index = 0
        stop_price: float | None = None
        target_price: float | None = None
        pending: str | None = None   # "long" | "short" | "exit"

        slippage = self._costs.slippage_points
        multiplier = self._costs.point_value * self._costs.contracts

        def close_position(index: int, price: float, reason: str) -> None:
            nonlocal realized, position, stop_price, target_price
            gross_points = (price - entry_price) * position
            commission = self._costs.round_turn_commission
            pnl = gross_points * multiplier - commission
            realized += pnl
            trades.append(
                Trade(
                    direction=position,
                    entry_time=timestamps[entry_index].to_pydatetime(),
                    entry_price=entry_price,
                    exit_time=timestamps[index].to_pydatetime(),
                    exit_price=price,
                    bars_held=index - entry_index,
                    exit_reason=reason,
                    gross_points=gross_points,
                    commission=commission,
                    pnl=pnl,
                )
            )
            position = FLAT
            stop_price = None
            target_price = None

        for i in range(len(data)):
            is_last_bar = i == len(data) - 1
            last_bar_of_session = (
                is_last_bar or sessions[i] != sessions[i + 1]
            )

            # --- 1. Auftrag aus dem Signal der Vorkerze ausfuehren ---------
            if pending is not None:
                if pending == "exit" and position != FLAT:
                    fill = opens[i] - slippage * position
                    close_position(i, fill, ExitReason.SIGNAL)
                elif pending in ("long", "short") and position == FLAT:
                    direction = LONG if pending == "long" else SHORT
                    fill = opens[i] + slippage * direction
                    position = direction
                    entry_price = fill
                    entry_index = i
                    reference_atr = atrs[i - 1] if i > 0 else atrs[i]

                    # Strukturelles Niveau VOR ATR: der Stop gehoert hinter
                    # den Halt, der die Bewegung getragen hat, nicht auf ein
                    # Vielfaches der Schwankungsbreite.
                    #
                    # Gelesen wird das Niveau der ENTSCHEIDUNGSKERZE (i-1),
                    # nicht der Ausfuehrungskerze. Das Niveau bei i kennt der
                    # Handelnde beim Setzen des Auftrags noch nicht.
                    stop_spalte = (
                        strategy.stop_loss_spalte
                        if direction == LONG
                        else strategy.stop_loss_spalte_short
                    )
                    stop_price = _strukturniveau(
                        stop_spalte, i - 1, direction,
                        puffer=-strategy.stop_loss_puffer_ticks * tick_size,
                    )
                    if stop_price is None and (
                        stop_spalte is None or strategy.stop_rueckfall_auf_atr
                    ):
                        if strategy.stop_loss_atr and not np.isnan(reference_atr):
                            stop_price = (
                                fill - direction * strategy.stop_loss_atr * reference_atr
                            )
                            if stop_spalte is not None:
                                stop_rueckfaelle += 1
                    elif stop_price is not None:
                        strukturstops += 1

                    # Ein Stop auf der falschen Seite des Einstiegs waere kein
                    # Stop. Das passiert, wenn das Niveau beim Einstieg schon
                    # ueberschritten war - dann greift der Rueckfall.
                    if stop_price is not None and (fill - stop_price) * direction <= 0:
                        stop_price = None
                        if strategy.stop_loss_atr and not np.isnan(reference_atr):
                            stop_price = (
                                fill - direction * strategy.stop_loss_atr * reference_atr
                            )
                            stop_rueckfaelle += 1
                            strukturstops -= 1

                    target_price = _strukturniveau(
                        strategy.take_profit_spalte, i - 1, direction,
                        puffer=strategy.take_profit_puffer_ticks * tick_size,
                    )
                    if target_price is None and strategy.take_profit_atr:
                        if not np.isnan(reference_atr):
                            target_price = (
                                fill + direction * strategy.take_profit_atr * reference_atr
                            )
                    if target_price is not None and (target_price - fill) * direction <= 0:
                        target_price = None
                pending = None

            # --- 2. Stop / Ziel innerhalb der Kerze -----------------------
            if position != FLAT:
                stop_hit = stop_price is not None and (
                    (position == LONG and lows[i] <= stop_price)
                    or (position == SHORT and highs[i] >= stop_price)
                )
                target_hit = target_price is not None and (
                    (position == LONG and highs[i] >= target_price)
                    or (position == SHORT and lows[i] <= target_price)
                )

                if stop_hit:
                    # Pessimistisch: Stop vor Ziel, plus Slippage im Stop.
                    close_position(i, stop_price - slippage * position, ExitReason.STOP)
                elif target_hit:
                    close_position(i, float(target_price), ExitReason.TARGET)

            # --- 3. Zwangsausstiege ---------------------------------------
            if position != FLAT and strategy.max_bars_in_trade is not None:
                if (i - entry_index) >= strategy.max_bars_in_trade:
                    close_position(i, closes[i] - slippage * position, ExitReason.TIME)

            if position != FLAT and last_bar_of_session and strategy.close_at_session_end:
                reason = ExitReason.END_OF_DATA if is_last_bar else ExitReason.SESSION_END
                close_position(i, closes[i] - slippage * position, reason)
            elif position != FLAT and is_last_bar:
                close_position(i, closes[i] - slippage * position, ExitReason.END_OF_DATA)

            # --- 4. Signale auf Schlusskurs auswerten ---------------------
            if not is_last_bar and not last_bar_of_session:
                ctx = BarContext(
                    row=zeile(i),
                    previous=zeile(i - 1) if i > 0 else None,
                    timestamp=timestamps[i],
                    position=position,
                    bars_in_trade=(i - entry_index) if position != FLAT else 0,
                )
                pending = self._next_order(strategy, ctx, position)

            # --- 5. Equity inkl. offener Position -------------------------
            open_pnl = 0.0
            if position != FLAT:
                open_pnl = (closes[i] - entry_price) * position * multiplier
            equity_values[i] = realized + open_pnl

        result = BacktestResult(
            strategy_name=strategy.name,
            strategy_description=strategy.describe(),
            trades=trades,
            equity=pd.Series(equity_values, index=timestamps, name="equity"),
            bars=len(data),
            period_start=timestamps[0].to_pydatetime(),
            period_end=timestamps[-1].to_pydatetime(),
            label=label,
            kosten=self._costs.herkunft(),
            strukturstops=strukturstops,
            stop_rueckfaelle=stop_rueckfaelle,
        )
        log.info(
            "Backtest '%s'%s: %d Trades, Netto %.2f USD%s",
            strategy.name,
            f" ({label})" if label else "",
            len(trades),
            realized,
            (
                f" (Strukturstop bei {result.strukturstop_anteil:.0%} der Trades)"
                if result.strukturstop_anteil is not None
                else ""
            ),
        )
        return result

    @staticmethod
    def _next_order(
        strategy: RuleStrategy, ctx: BarContext, position: int
    ) -> str | None:
        """Entscheidet, welcher Auftrag zur naechsten Eroeffnung ausgefuehrt wird."""
        if position == LONG:
            if strategy.long_exit is not None and strategy.long_exit.evaluate(ctx):
                return "exit"
            return None
        if position == SHORT:
            if strategy.short_exit is not None and strategy.short_exit.evaluate(ctx):
                return "exit"
            return None

        # Flach: Einstiege pruefen. Long hat Vorrang, wenn beides zutrifft -
        # in dem Fall widersprechen sich die Regeln ohnehin.
        if strategy.long_entry is not None and strategy.long_entry.evaluate(ctx):
            return "long"
        if strategy.short_entry is not None and strategy.short_entry.evaluate(ctx):
            return "short"
        return None
