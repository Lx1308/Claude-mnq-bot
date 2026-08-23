"""Regel-Objekte und Strategie-Definition.

Eine Strategie ist hier kein Skript, sondern eine Komposition kleiner,
einzeln testbarer Regeln:

    entry = CrossesAbove("close", "prev_session_high") & ColumnBelow("rsi", 70)
    exit_ = CrossesBelow("close", "vwap")

Vorteile gegenueber frei geschriebenem Code:
  * jede Regel ist fuer sich testbar und wiederverwendbar,
  * die Beschreibung einer Strategie laesst sich automatisch erzeugen
    (landet so im Vergleichsreport),
  * Parametervarianten sind reine Daten, kein Copy-Paste von Logik.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import time as dtime
from typing import Any
from zoneinfo import ZoneInfo

import math
import pandas as pd


@dataclass(frozen=True)
class BarContext:
    """Alles, was eine Regel ueber die aktuelle Kerze wissen darf.

    Bewusst nur die aktuelle und die vorherige Zeile - damit ist es
    strukturell unmoeglich, versehentlich in die Zukunft zu schauen.
    """

    row: pd.Series
    previous: pd.Series | None
    timestamp: pd.Timestamp
    position: int  # +1 long, -1 short, 0 flach
    bars_in_trade: int = 0

    def value(self, key: str | float | int) -> float:
        """Loest einen Spaltennamen oder eine Konstante zu einer Zahl auf."""
        if isinstance(key, (int, float)):
            return float(key)
        raw = self.row.get(key)
        return float("nan") if raw is None else float(raw)

    def previous_value(self, key: str | float | int) -> float:
        if isinstance(key, (int, float)):
            return float(key)
        if self.previous is None:
            return float("nan")
        raw = self.previous.get(key)
        return float("nan") if raw is None else float(raw)


class Rule(ABC):
    """Basisklasse aller Regeln."""

    @abstractmethod
    def evaluate(self, ctx: BarContext) -> bool:
        """True, wenn die Regel auf dieser Kerze zutrifft."""

    @abstractmethod
    def describe(self) -> str:
        """Kurze, lesbare Beschreibung (landet im Report)."""

    def benoetigte_spalten(self) -> set[str]:
        """Spalten, ohne die diese Regel nicht arbeiten kann.

        WARUM ES DAS GIBT
        -----------------
        :meth:`BarContext.value` loest einen unbekannten Spaltennamen zu NaN
        auf, und :func:`_valid` verwirft NaN. Eine Regel auf einer Spalte, die
        es gar nicht gibt, feuert deshalb **nie** - ohne Fehlermeldung, ohne
        Warnung, ohne dass am Ergebnis etwas verdaechtig aussieht. Sie liefert
        schlicht null Trades, und null Trades liest sich wie "die Idee hat in
        diesem Zeitraum nicht gegriffen".

        Genau so ist ``ib_breakout`` am 23.08.2026 aufgefallen: die Strategie
        verlangt ``ib_high``/``ib_low``, ``common.indicators.compute_indicators``
        erzeugt diese Spalten aber nicht, und ueber zehn Jahre Kursverlauf kam
        exakt ein Trade zustande - keiner.

        Der Rueckgabewert ist bewusst eine Menge von Spaltennamen und keine
        Pruefung: pruefen tut :meth:`backtest.engine.Backtester.run`, einmal
        vor der Hauptschleife.
        """
        return set()

    def __and__(self, other: "Rule") -> "AllOf":
        return AllOf(self, other)

    def __or__(self, other: "Rule") -> "AnyOf":
        return AnyOf(self, other)

    def __invert__(self) -> "Not":
        return Not(self)

    def __repr__(self) -> str:  # pragma: no cover - Debugging-Komfort
        return f"<{type(self).__name__}: {self.describe()}>"


# ---------------------------------------------------------------------------
# Kombinatoren
# ---------------------------------------------------------------------------

class AllOf(Rule):
    """UND-Verknuepfung."""

    def __init__(self, *rules: Rule) -> None:
        self._rules = rules

    def evaluate(self, ctx: BarContext) -> bool:
        return all(rule.evaluate(ctx) for rule in self._rules)

    def benoetigte_spalten(self) -> set[str]:
        return set().union(*(rule.benoetigte_spalten() for rule in self._rules)) if self._rules else set()

    def describe(self) -> str:
        return " UND ".join(f"({rule.describe()})" for rule in self._rules)


class AnyOf(Rule):
    """ODER-Verknuepfung."""

    def __init__(self, *rules: Rule) -> None:
        self._rules = rules

    def evaluate(self, ctx: BarContext) -> bool:
        return any(rule.evaluate(ctx) for rule in self._rules)

    def benoetigte_spalten(self) -> set[str]:
        return set().union(*(rule.benoetigte_spalten() for rule in self._rules)) if self._rules else set()

    def describe(self) -> str:
        return " ODER ".join(f"({rule.describe()})" for rule in self._rules)


class Not(Rule):
    def __init__(self, rule: Rule) -> None:
        self._rule = rule

    def evaluate(self, ctx: BarContext) -> bool:
        return not self._rule.evaluate(ctx)

    def benoetigte_spalten(self) -> set[str]:
        return self._rule.benoetigte_spalten()

    def describe(self) -> str:
        return f"NICHT ({self._rule.describe()})"


class Always(Rule):
    def __init__(self, value: bool = True) -> None:
        self._value = value

    def evaluate(self, ctx: BarContext) -> bool:
        return self._value

    def describe(self) -> str:
        return "immer" if self._value else "nie"


# ---------------------------------------------------------------------------
# Vergleichsregeln
# ---------------------------------------------------------------------------

def _valid(*values: float) -> bool:
    """False, sobald ein Wert NaN ist - NaN darf nie ein Signal ausloesen."""
    return not any(math.isnan(value) for value in values)


def _spaltennamen(*bezuege: str | float | int) -> set[str]:
    """Filtert aus Spalte-oder-Konstante-Argumenten die Spaltennamen heraus."""
    return {bezug for bezug in bezuege if isinstance(bezug, str)}


class ColumnAbove(Rule):
    """Spalte liegt ueber Referenz (Konstante oder andere Spalte)."""

    def __init__(self, column: str, reference: str | float, offset: float = 0.0) -> None:
        self._column = column
        self._reference = reference
        self._offset = offset

    def evaluate(self, ctx: BarContext) -> bool:
        left, right = ctx.value(self._column), ctx.value(self._reference)
        return _valid(left, right) and left > right + self._offset

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference)

    def describe(self) -> str:
        suffix = f" + {self._offset}" if self._offset else ""
        return f"{self._column} > {self._reference}{suffix}"


class ColumnBelow(Rule):
    def __init__(self, column: str, reference: str | float, offset: float = 0.0) -> None:
        self._column = column
        self._reference = reference
        self._offset = offset

    def evaluate(self, ctx: BarContext) -> bool:
        left, right = ctx.value(self._column), ctx.value(self._reference)
        return _valid(left, right) and left < right - self._offset

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference)

    def describe(self) -> str:
        suffix = f" - {self._offset}" if self._offset else ""
        return f"{self._column} < {self._reference}{suffix}"


class CrossesAbove(Rule):
    """Flanke: war zuvor <= Referenz, ist jetzt > Referenz (+ Puffer)."""

    def __init__(self, column: str, reference: str | float, buffer: float = 0.0) -> None:
        self._column = column
        self._reference = reference
        self._buffer = buffer

    def evaluate(self, ctx: BarContext) -> bool:
        now, now_ref = ctx.value(self._column), ctx.value(self._reference)
        before, before_ref = ctx.previous_value(self._column), ctx.previous_value(self._reference)
        if not _valid(now, now_ref, before, before_ref):
            return False
        return before <= before_ref and now > now_ref + self._buffer

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference)

    def describe(self) -> str:
        suffix = f" (Puffer {self._buffer})" if self._buffer else ""
        return f"{self._column} kreuzt {self._reference} von unten{suffix}"


class CrossesBelow(Rule):
    def __init__(self, column: str, reference: str | float, buffer: float = 0.0) -> None:
        self._column = column
        self._reference = reference
        self._buffer = buffer

    def evaluate(self, ctx: BarContext) -> bool:
        now, now_ref = ctx.value(self._column), ctx.value(self._reference)
        before, before_ref = ctx.previous_value(self._column), ctx.previous_value(self._reference)
        if not _valid(now, now_ref, before, before_ref):
            return False
        return before >= before_ref and now < now_ref - self._buffer

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference)

    def describe(self) -> str:
        suffix = f" (Puffer {self._buffer})" if self._buffer else ""
        return f"{self._column} kreuzt {self._reference} von oben{suffix}"


class FlagBreakout(Rule):
    """Ausbruch aus der Konsolidierung (Spalten aus common.indicators)."""

    def __init__(self, direction: str = "up") -> None:
        if direction not in {"up", "down"}:
            raise ValueError("direction muss 'up' oder 'down' sein.")
        self._direction = direction
        self._column = "flag_breakout_up" if direction == "up" else "flag_breakout_down"

    def evaluate(self, ctx: BarContext) -> bool:
        return bool(ctx.row.get(self._column, False))

    def benoetigte_spalten(self) -> set[str]:
        return {self._column}

    def describe(self) -> str:
        return f"Flaggen-Ausbruch nach {'oben' if self._direction == 'up' else 'unten'}"


class Rising(Rule):
    """Spalte steigt gegenueber der Vorkerze."""

    def __init__(self, column: str) -> None:
        self._column = column

    def evaluate(self, ctx: BarContext) -> bool:
        now, before = ctx.value(self._column), ctx.previous_value(self._column)
        return _valid(now, before) and now > before

    def benoetigte_spalten(self) -> set[str]:
        return {self._column}

    def describe(self) -> str:
        return f"{self._column} steigt"


class Falling(Rule):
    """Spalte faellt gegenueber der Vorkerze."""

    def __init__(self, column: str) -> None:
        self._column = column

    def evaluate(self, ctx: BarContext) -> bool:
        now, before = ctx.value(self._column), ctx.previous_value(self._column)
        return _valid(now, before) and now < before

    def benoetigte_spalten(self) -> set[str]:
        return {self._column}

    def describe(self) -> str:
        return f"{self._column} faellt"


class PreviousDeviationExceeds(Rule):
    """Die VORKERZE lag mindestens N x ATR von einer Referenz entfernt.

    Bewusst auf der Vorkerze und mit deren ATR: die Abweichung ist die
    Voraussetzung, die Umkehr auf der aktuellen Kerze das Signal. Wuerde man
    beides auf derselben Kerze messen, waere die Bedingung entweder nie
    oder immer erfuellt.

    Abstaende in ATR statt in Punkten, weil derselbe Punktwert bei MNQ ein
    Nichts und bei MGC eine Weltreise waere.
    """

    def __init__(
        self,
        column: str,
        reference: str,
        atr_multiple: float,
        side: str,
        atr_column: str = "atr",
    ) -> None:
        if side not in {"above", "below"}:
            raise ValueError("side muss 'above' oder 'below' sein.")
        self._column = column
        self._reference = reference
        self._multiple = atr_multiple
        self._side = side
        self._atr_column = atr_column

    def evaluate(self, ctx: BarContext) -> bool:
        value = ctx.previous_value(self._column)
        reference = ctx.previous_value(self._reference)
        atr_value = ctx.previous_value(self._atr_column)
        if not _valid(value, reference, atr_value) or atr_value <= 0:
            return False
        deviation = value - reference
        threshold = self._multiple * atr_value
        if self._side == "above":
            return deviation >= threshold
        return deviation <= -threshold

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference, self._atr_column)

    def describe(self) -> str:
        richtung = "ueber" if self._side == "above" else "unter"
        return (
            f"Vorkerze {self._multiple} x ATR {richtung} {self._reference} "
            f"({self._column})"
        )


class DeviationReentry(Rule):
    """Flanke: Kurs war weiter als N x ATR von der Referenz weg und ist zurueck.

    WARUM DAS EINE EIGENE REGEL IST UND NICHT AUS DREI ZUSAMMENGESETZT
    -----------------------------------------------------------------
    Die naheliegende Komposition - "Vorkerze war weit weg UND Kurs steigt
    UND VWAP noch nicht erreicht" - ist **keine Flanke**. Sie bleibt waehrend
    der ganzen Rueckkehrbewegung wahr und feuert auf jeder steigenden Kerze
    erneut.

    An echten MNQ-5m-Daten gemessen und am 22.08.2026 nachgerechnet -
    822 Kerzen vom 18.08. bis 21.08.2026, Handelsfenster 09:30-15:45 ET,
    ``deviation_atr`` 1.5, Long-Seite, Signale mit hoechstens drei Kerzen
    Abstand als eine Bewegung gezaehlt: **47 Signale in 10 Bewegungen**,
    die groesste davon mit 11 Signalen. Dieselbe Strecke mit dieser Regel:
    11 Signale. (Die Messgrundlage steht hier mit, weil "47 Signale" ohne
    Seite, Zeitraum und Buendelungsregel spaeter nicht nachpruefbar waere.)

    In der spaeteren Erwartungswert-Rechnung haette eine einzige Bewegung
    elffach gezaehlt - das Ergebnis waere nicht schwach, sondern falsch.

    Diese Regel prueft stattdessen den **Uebertritt**: die Vorkerze lag
    ausserhalb des Bandes, die aktuelle liegt darin. Das kann je Ausflug
    genau einmal zutreffen und braucht dafuer nur zwei Zeilen, bleibt also
    im Lookahead-sicheren Rahmen von :class:`BarContext`.
    """

    def __init__(
        self,
        column: str,
        reference: str,
        atr_multiple: float,
        side: str,
        atr_column: str = "atr",
    ) -> None:
        if side not in {"above", "below"}:
            raise ValueError("side muss 'above' oder 'below' sein.")
        self._column = column
        self._reference = reference
        self._multiple = atr_multiple
        self._side = side
        self._atr_column = atr_column

    def evaluate(self, ctx: BarContext) -> bool:
        vorher = ctx.previous_value(self._column)
        vorher_ref = ctx.previous_value(self._reference)
        vorher_atr = ctx.previous_value(self._atr_column)
        jetzt = ctx.value(self._column)
        jetzt_ref = ctx.value(self._reference)
        jetzt_atr = ctx.value(self._atr_column)

        if not _valid(vorher, vorher_ref, vorher_atr, jetzt, jetzt_ref, jetzt_atr):
            return False
        if vorher_atr <= 0 or jetzt_atr <= 0:
            return False

        vorher_abstand = vorher - vorher_ref
        jetzt_abstand = jetzt - jetzt_ref

        if self._side == "below":
            war_draussen = vorher_abstand <= -self._multiple * vorher_atr
            ist_drinnen = jetzt_abstand > -self._multiple * jetzt_atr
            # Noch nicht ueber die Referenz hinaus - sonst waere die
            # Rueckkehr bereits gelaufen und es gaebe nichts mehr zu holen.
            noch_nicht_durch = jetzt_abstand < 0
        else:
            war_draussen = vorher_abstand >= self._multiple * vorher_atr
            ist_drinnen = jetzt_abstand < self._multiple * jetzt_atr
            noch_nicht_durch = jetzt_abstand > 0

        return war_draussen and ist_drinnen and noch_nicht_durch

    def benoetigte_spalten(self) -> set[str]:
        return _spaltennamen(self._column, self._reference, self._atr_column)

    def describe(self) -> str:
        richtung = "unterhalb" if self._side == "below" else "oberhalb"
        return (
            f"{self._column} kehrt aus {self._multiple} x ATR {richtung} "
            f"{self._reference} zurueck"
        )


class SessionTimeWindow(Rule):
    """Nur innerhalb eines Zeitfensters der Boersenzeit handeln.

    Nuetzlich, um z.B. die duenne Overnight-Phase auszuschliessen.
    """

    def __init__(
        self,
        start: dtime,
        end: dtime,
        timezone: str = "America/New_York",
    ) -> None:
        self._start = start
        self._end = end
        self._tz = ZoneInfo(timezone)
        self._tz_name = timezone

    def evaluate(self, ctx: BarContext) -> bool:
        local = ctx.timestamp.tz_convert(self._tz).time()
        if self._start <= self._end:
            return self._start <= local <= self._end
        # Fenster ueber Mitternacht
        return local >= self._start or local <= self._end

    def describe(self) -> str:
        return f"Uhrzeit {self._start:%H:%M}-{self._end:%H:%M} ({self._tz_name})"


class MinBarsInTrade(Rule):
    """Verhindert Ausstiege in den ersten N Kerzen nach dem Einstieg."""

    def __init__(self, minimum: int) -> None:
        self._minimum = minimum

    def evaluate(self, ctx: BarContext) -> bool:
        return ctx.bars_in_trade >= self._minimum

    def describe(self) -> str:
        return f"mindestens {self._minimum} Kerzen im Trade"


# ---------------------------------------------------------------------------
# Strategie
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleStrategy:
    """Eine vollstaendige Strategie aus Ein-/Ausstiegsregeln plus Risikoparametern.

    Alle Regeln werden auf dem SCHLUSS einer Kerze ausgewertet; ausgefuehrt
    wird zur EROEFFNUNG der Folgekerze (siehe :mod:`backtest.engine`).
    """

    name: str
    long_entry: Rule | None = None
    long_exit: Rule | None = None
    short_entry: Rule | None = None
    short_exit: Rule | None = None

    #: Stop-Loss in ATR-Vielfachen (None = kein Stop)
    stop_loss_atr: float | None = None
    #: Take-Profit in ATR-Vielfachen (None = kein Ziel)
    take_profit_atr: float | None = None
    #: Zwangsausstieg nach N Kerzen (None = kein Zeitstop)
    max_bars_in_trade: int | None = None
    #: Alle offenen Positionen am Sessionende schliessen
    close_at_session_end: bool = True

    #: Frei waehlbare Metadaten (Parameterwerte fuer den Report)
    params: dict[str, Any] = field(default_factory=dict)

    def benoetigte_spalten(self) -> set[str]:
        """Alle Spalten, die diese Strategie zum Arbeiten braucht.

        Wird von :meth:`backtest.engine.Backtester.run` einmal vor der
        Hauptschleife gegen den vorbereiteten Datensatz geprueft. Fehlt eine
        Spalte, bricht der Lauf ab, statt stumm null Trades zu liefern -
        siehe :meth:`Rule.benoetigte_spalten`.
        """
        spalten: set[str] = set()
        for regel in (self.long_entry, self.long_exit, self.short_entry, self.short_exit):
            if regel is not None:
                spalten |= regel.benoetigte_spalten()
        return spalten

    def describe(self) -> str:
        parts = [f"Strategie: {self.name}"]
        if self.long_entry:
            parts.append(f"  Long-Einstieg : {self.long_entry.describe()}")
        if self.long_exit:
            parts.append(f"  Long-Ausstieg : {self.long_exit.describe()}")
        if self.short_entry:
            parts.append(f"  Short-Einstieg: {self.short_entry.describe()}")
        if self.short_exit:
            parts.append(f"  Short-Ausstieg: {self.short_exit.describe()}")
        if self.stop_loss_atr:
            parts.append(f"  Stop-Loss     : {self.stop_loss_atr} x ATR")
        if self.take_profit_atr:
            parts.append(f"  Take-Profit   : {self.take_profit_atr} x ATR")
        if self.max_bars_in_trade:
            parts.append(f"  Zeitstop      : {self.max_bars_in_trade} Kerzen")
        if self.params:
            rendered = ", ".join(f"{key}={value}" for key, value in sorted(self.params.items()))
            parts.append(f"  Parameter     : {rendered}")
        return "\n".join(parts)

    @property
    def trades_long(self) -> bool:
        return self.long_entry is not None

    @property
    def trades_short(self) -> bool:
        return self.short_entry is not None
