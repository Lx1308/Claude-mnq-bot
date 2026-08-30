"""Laden und Validieren von config.yaml + .env.

Grundregel: Schwellenwerte und Verhalten kommen aus der YAML, Secrets
ausschliesslich aus Umgebungsvariablen. Nichts davon steht im Code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Any, Mapping

import yaml

try:  # python-dotenv ist optional zur Laufzeit (z.B. in CI ohne .env)
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(RuntimeError):
    """Konfiguration ist unvollstaendig oder widerspruechlich."""


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"Fehlender Konfigurationsschluessel '{key}' unter '{where}'.")
    return mapping[key]


def _parse_hhmm(value: str, where: str) -> dtime:
    try:
        hour_str, minute_str = value.split(":")
        return dtime(int(hour_str), int(minute_str))
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"'{where}' muss im Format HH:MM stehen, war: {value!r}") from exc


def _lies_setup_parameter(werte: Any) -> "IdeenSetupParameter":
    """Liest die Schwellenwerte einer Setup-Familie aus der YAML."""
    daten = dict(werte or {})
    vorgabe = IdeenSetupParameter()
    return IdeenSetupParameter(
        aktiv=bool(daten.get("aktiv", vorgabe.aktiv)),
        stop_atr=float(daten.get("stop_atr", vorgabe.stop_atr)),
        ziel_atr=float(daten.get("ziel_atr", vorgabe.ziel_atr)),
        puffer_punkte=float(daten.get("puffer_punkte", vorgabe.puffer_punkte)),
        abweichung_atr=float(daten.get("abweichung_atr", vorgabe.abweichung_atr)),
        session_start=str(daten.get("session_start", vorgabe.session_start)),
        session_end=str(daten.get("session_end", vorgabe.session_end)),
    )


# ---------------------------------------------------------------------------
# Secrets (.env)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Secrets:
    """Zugangsdaten aus der .env.

    Seit der Entfernung des Legacy-Pfads (22.08.2026) bleibt hier genau
    ein Eintrag: der FRED-Schluessel fuer die Ist-Werte im
    Wirtschaftskalender. Tradovate-, Anthropic- und Telegram-Schluessel
    sind ersatzlos entfallen - das Zielsystem ruft keinen davon auf.

    Es gibt bewusst KEINE Pflichtpruefung mehr: ohne FRED_API_KEY laeuft
    alles weiter, nur die Actual-Werte fehlen. Das wird im Snapshot
    ausgewiesen statt geschaetzt.
    """

    fred_api_key: str | None = None

    @staticmethod
    def load(dotenv_path: str | os.PathLike[str] | None = ".env") -> "Secrets":
        if dotenv_path is not None and Path(dotenv_path).exists():
            load_dotenv(dotenv_path, override=False)

        wert = os.environ.get("FRED_API_KEY", "").strip()
        return Secrets(fred_api_key=wert or None)


# ---------------------------------------------------------------------------
# Konfigurations-Sektionen
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionConfig:
    timezone: str = "America/New_York"
    start_time: dtime = dtime(18, 0)
    end_time: dtime = dtime(17, 0)


@dataclass(frozen=True)
class MarketConfig:
    product: str = "NQ"
    contract_override: str | None = None
    candle_interval_minutes: int = 1
    candle_buffer_size: int = 500
    warmup_bars: int = 300
    tick_size: float = 0.25
    point_value: float = 20.0
    session: SessionConfig = field(default_factory=SessionConfig)

    # CME-Globex laeuft 18:00 ET bis 17:00 ET mit einer Stunde Pause = 23h.
    SESSION_MINUTES = 23 * 60

    @property
    def bars_per_session(self) -> int:
        """Wie viele Kerzen eine volle Handelssession umfasst."""
        return max(1, self.SESSION_MINUTES // self.candle_interval_minutes)

    @property
    def bars_for_previous_session(self) -> int:
        """Puffergroesse, ab der Vortageshoch/-tief zuverlaessig vorliegen.

        Es braucht die KOMPLETTE Vorsession plus die laufende Session - erst
        dann kennt ``previous_session_levels`` beide Handelstage. Ist der
        Puffer kleiner, bleiben die Vortagesmarken NaN und die zugehoerigen
        Alarme koennen niemals ausloesen. Genau so ein stiller Ausfall soll
        beim Start auffallen, nicht nach Wochen ohne Alarm.
        """
        return 2 * self.bars_per_session


@dataclass(frozen=True)
class FlagConfig:
    impulse_lookback: int = 20
    impulse_min_atr: float = 2.5
    consolidation_lookback: int = 10
    # Vorlaeufiger, aus Daten abgeleiteter Startwert - siehe config.yaml.
    # 1.2 konnte auf keiner Zeitebene ausloesen (schmalste beobachtete
    # Konsolidierung: Range/ATR = 1.37 auf 5m).
    consolidation_max_atr: float = 2.40
    breakout_buffer_atr: float = 0.1


@dataclass(frozen=True)
class IndicatorConfig:
    rsi_period: int = 14
    sma_fast: int = 20
    sma_slow: int = 50
    atr_period: int = 14
    flag: FlagConfig = field(default_factory=FlagConfig)

    @property
    def min_bars_required(self) -> int:
        """Wie viele Kerzen mindestens im Puffer sein muessen."""
        return max(
            self.rsi_period + 1,
            self.sma_slow,
            self.atr_period + 1,
            self.flag.impulse_lookback + self.flag.consolidation_lookback + 1,
        )


@dataclass(frozen=True)
class NtBridgeConfig:
    """Empfaenger fuer Kerzen aus NinjaTrader 8."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8787
    database: str = "data/ntbridge.sqlite3"
    # Juengster Bar aelter als factor * Bar-Laenge -> Snapshot markiert veraltet.
    stale_factor: float = 2.0
    # NinjaTrader-Name -> internes Root, falls der Broker abweichend benennt.
    symbol_map: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IdeenSetupParameter:
    """Schwellenwerte EINER Setup-Familie (Etappe C).

    Bewusst ein gemeinsamer Satz Felder statt einer Klasse je Familie: die
    Familien unterscheiden sich in der Regel-Komposition, nicht in der Art
    ihrer Parameter. Welche Felder eine Familie tatsaechlich auswertet,
    legt ihre ``baue``-Funktion in ``ideas/setups.py`` fest.
    """

    # Familie ganz abschalten, ohne sie aus der Bibliothek zu entfernen.
    aktiv: bool = True

    # Stop- und Zielabstand in ATR-Vielfachen, gemessen ab dem Einstieg -
    # dieselbe Bedeutung wie ``stop_loss_atr``/``take_profit_atr`` in der
    # Backtest-Engine, damit Protokoll und Backtest dasselbe rechnen.
    stop_atr: float = 1.5
    ziel_atr: float = 3.0

    # Bruch-Setups: wie weit der Schluss ueber die Marke hinaus muss.
    # In Punkten, weil die bestehenden Kreuzungsregeln einen Punktpuffer
    # erwarten; bei nur einem protokollierten Instrument (MNQ) ist das
    # eindeutig. Kommt MGC dazu, gehoert hier ein ATR-Vielfaches hin.
    puffer_punkte: float = 1.0

    # VWAP-Reversion: so weit war der Kurs vom VWAP entfernt.
    abweichung_atr: float = 1.5

    # Handelsfenster in Boersenzeit des Instruments.
    session_start: str = "09:30"
    session_end: str = "15:45"


@dataclass(frozen=True)
class IdeenFilterConfig:
    """Filter, die eine erkannte Idee als nicht handelbar markieren."""

    # Fortsetzungs-Setups brauchen Trend, Reversion braucht Range.
    adx_aktiv: bool = True
    adx_trend_min: float = 20.0
    adx_range_max: float = 25.0

    # Nur in liquiden Phasen protokollieren.
    liquiditaet_aktiv: bool = True
    # Duenne Mittagszone blockiert.
    duennzone_aktiv: bool = True

    # Blackout um Wirtschaftstermine. Ist der Kalender nicht erreichbar,
    # wird die Idee NICHT stillschweigend durchgewinkt, sondern mit dem
    # Grund "blackout_nicht_pruefbar" markiert - ein Ausfall darf nie wie
    # Entwarnung aussehen.
    blackout_aktiv: bool = True

    # Wie weit zurueck der Wirtschaftskalender ueberhaupt Auskunft geben
    # kann. Forex Factory liefert im Wesentlichen die laufende Woche; fragt
    # man aeltere Zeitpunkte ab, findet sich dort kein Termin und die
    # Antwort waere "kein Blackout" - eine Entwarnung aus einer Wissens-
    # luecke heraus. Jenseits dieser Grenze bleibt die Frage deshalb offen.
    blackout_max_alter_tage: float = 7.0


@dataclass(frozen=True)
class IdeasConfig:
    """Regelbasierte Ideen-Protokollierung (Etappe C)."""

    enabled: bool = True
    # Tatsaechliche Kontoumgebung, in der die Idee entstanden ist. Landet
    # als Feld an JEDER Idee - eine gemeinsame Datenbank, keine getrennten
    # Logs. Reine Herkunftsdokumentation: die Auswertung rechnet spaeter
    # alle Ideen durch beide Regelwerke und benutzt dieses Feld NICHT als
    # Filter (Spezifikation Abschnitt 4).
    #
    # Der Wert heisst "sim_frei" und nicht "demo", weil die Config bis zum
    # 22.08.2026 unter "tradovate:" ein "environment: demo" fuehrte und
    # beides verwechselbar war. Der Tradovate-Abschnitt ist mit dem
    # Legacy-Pfad entfallen, der eigene Wertebereich bleibt trotzdem: er
    # benennt die Kontoumgebung praeziser, als "demo" es je tat.
    profil: str = "sim_frei"
    profile_erlaubt: tuple[str, ...] = ("sim_frei", "lucid_challenge", "lucid_funded")
    datenbank: str = "data/ideas.sqlite3"
    # Bewusst nur MNQ: ein Mehr-Instrument-Stream ist ausdruecklich nicht
    # Bestandteil des Projekts.
    instrumente: tuple[str, ...] = ("MNQ",)
    # Zeitebene, auf der erkannt wird.
    timeframe: str = "5m"
    # Wie viele Kerzen fuer die Erkennung geladen werden.
    bars: int = 1500

    # Faellt das CRV darunter, wird die Idee als "unter Schwelle" markiert -
    # aber trotzdem protokolliert.
    crv_schwelle: float = 1.5
    # Gefilterte Ideen mitspeichern (empfohlen: sonst laesst sich spaeter
    # nicht pruefen, ob ein Filter zu scharf steht).
    speichere_gefilterte: bool = True
    # Unter dieser Zahl gilt eine Kategorie in der Auswertung als
    # "zu wenig Daten" (Etappe D).
    min_ideen_pro_kategorie: int = 20

    # Schwellenwerte je Setup-Familie, Schluessel wie in
    # ``ideas.setups.SETUP_BIBLIOTHEK``. Fehlt eine Familie, gelten die
    # Vorgabewerte aus ``IdeenSetupParameter``.
    setups: dict[str, IdeenSetupParameter] = field(default_factory=dict)
    filter: IdeenFilterConfig = field(default_factory=IdeenFilterConfig)

    def setup_parameter(self, schluessel: str) -> IdeenSetupParameter:
        return self.setups.get(schluessel, IdeenSetupParameter())


@dataclass(frozen=True)
class EventRiskConfig:
    """Wirtschaftskalender (MCP-Tool ``get_event_risk``)."""

    enabled: bool = True
    currencies: tuple[str, ...] = ("USD",)
    impacts: tuple[str, ...] = ("High",)
    blackout_minutes_before: float = 15.0
    blackout_minutes_after: float = 15.0
    schedule_cache_minutes: float = 30.0
    actual_cache_hours: float = 6.0
    upcoming_limit: int = 8
    forex_factory_url: str = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


@dataclass(frozen=True)
class MacroConfig:
    """Makro-Vintages fuer die Research-Engine (FRED/ALFRED), siehe ``macro/``.

    Getrennt von ``EventRiskConfig``: jenes speist den Live-Snapshot in
    Claude Desktop, dieses die persistierte, revisionsfeste Historie fuer
    Backtests. Ein gemeinsamer Abschnitt haette beide Zwecke vermischt.
    """

    enabled: bool = True
    datenbank: str = "data/macro.sqlite3"
    # Reihen-ID -> Anzeigename. Leer bedeutet: die kuratierte Vorgabemenge
    # aus macro/provider.py::STANDARD_SERIEN wird verwendet.
    serien: dict[str, str] = field(default_factory=dict)
    marktkalender: str = "CME_Equity"
    # Reihen-ID -> "High"/"Medium"/"Low". Eigene fachliche Einordnung
    # (CPI/NFP/PCE = High, PPI/Retail Sales/Claims = Medium, ...) - KEINE
    # externe Messung, keine Kalenderquelle. Begruendung: es gibt keine
    # verlaessliche Gratis-Quelle fuer Forecast UND Impact zusammen
    # (Trading Economics kostenpflichtig, ForexFactory-Scraping widerspricht
    # der "kein fragiles Scraping als Kernarchitektur"-Regel), aber die
    # Impact-Stufe selbst ist statisches Fachwissen, das sich nicht aendert -
    # anders als ein Forecast-Wert ist sie nicht "erfunden", wenn wir sie
    # selbst festlegen. Siehe CODE_CHAT_KONTEXT.md Abschnitt 31.10.
    wichtigkeit: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyseConfig:
    """Parameter der Struktur- und Zonenanalyse im Snapshot.

    Hiess bis zum 22.08.2026 ``on_demand`` - benannt nach dem
    /analyse-Kommando des Telegram-Bots, den es nicht mehr gibt. Die
    sieben Felder jener Schleife (Poll-Timeouts, Cooldown, Tageslimit)
    sind mit ihm entfallen; geblieben sind die sechs, die
    ``mcp_server/snapshot.py`` tatsaechlich auswertet.

    Ein Abschnitt, der nach einer geloeschten Funktion heisst, waere
    irrefuehrend - deshalb umbenannt statt nur ausgeduennt.
    """

    swing_strength: int = 3
    swing_lookback: int = 120
    max_zones: int = 3
    zone_merge_atr: float = 0.5
    trend_slope_lookback: int = 10
    trend_flat_threshold_atr: float = 0.02


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    directory: str = "logs"
    text_file: str = "bot.log"
    json_file: str = "events.jsonl"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    console: bool = True


@dataclass(frozen=True)
class SplitConfig:
    mode: str = "fraction"
    in_sample_fraction: float = 0.7
    split_date: str | None = None
    # Anteil des NACH in_sample_fraction verbleibenden Rests, der bei einer
    # Dreiweg-Aufteilung (backtest.splits.split_data_three_way) zur Validation
    # wird. Der Rest bleibt Out-of-Sample - weiterhin einmalig fuer die
    # Confirmation-Phase reserviert (Masterplan G).
    validation_fraction: float = 0.5


@dataclass(frozen=True)
class BacktestConfig:
    provider: str = "csv"
    csv_directory: str = "data"
    output_directory: str = "backtest_results"

    # Welches benannte Kostenprofil verwendet wird. Die Profile selbst liegen
    # in ``kostenprofile``; der Grund fuer die Trennung steht in
    # ``backtest/kosten.py``.
    kostenprofil: str = "private_ninjatrader"
    #: Rohdaten der Profile aus der YAML. Zu ``Kostenprofil``-Objekten wird
    #: das erst in ``backtest.kosten`` - ``common`` ist die Basisschicht und
    #: soll nicht auf ``backtest`` zugreifen.
    kostenprofile: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Altfelder. Bis zum 23.08.2026 die einzige Kostenannahme; bleiben
    # erhalten, damit bestehende Aufrufe nicht brechen. Neue Laeufe nehmen
    # das Kostenprofil.
    commission_per_side: float = 2.50
    slippage_ticks_per_side: float = 1.0

    split: SplitConfig = field(default_factory=SplitConfig)


@dataclass(frozen=True)
class AusfuehrungConfig:
    """Ausfuehrung: welches Konto, welche Grenzen, wann darf gehandelt werden.

    Die eigentlichen Kontoregeln stehen als benanntes Profil in
    ``common/kontoregeln.py`` - hier wird nur ausgewaehlt und, wo noetig,
    ueberschrieben. Derselbe Aufbau wie bei den Kostenprofilen und aus
    demselben Grund: dasselbe Handelsverhalten ist unter 25k-Regeln ein
    anderes Geschaeft als unter 150k-Regeln.

    ``enabled`` steuert NUR den autonomen Bot. Die Oberflaeche kann unabhaengig
    davon Orders schicken - sonst waere ein abgeschalteter Bot gleichbedeutend
    mit einer gesperrten Handelsoberflaeche.
    """

    enabled: bool = False
    kontoprofil: str = "frei"
    #: Rohdaten der Ueberschreibungen. Zu ``Kontoregeln`` wird das erst in
    #: ``common.kontoregeln`` - hier bleibt es Daten.
    kontoprofile: dict[str, dict[str, Any]] = field(default_factory=dict)

    startkapital_usd: float | None = None

    #: Eigenes Kontraktlimit, meist strenger als das des Anbieters. Die
    #: Anbietergrenze ist das Maximum des Erlaubten, keine Empfehlung.
    max_kontrakte: int = 2

    #: Was ein einzelner Trade kosten darf. ``None`` heisst: aus
    #: ``risiko_je_trade_anteil`` ableiten.
    risiko_je_trade_usd: float | None = None

    #: Anteil der massgeblichen Bezugsgroesse je Trade. Bezug ist bei einem
    #: Prop-Konto der GESAMTVERLUSTPUFFER, nicht die Kontogroesse: bei einem
    #: 50k-Konto mit 2.000 USD Puffer waeren ein Prozent von 50.000 ein
    #: Viertel des gesamten Spielraums.
    risiko_je_trade_anteil: float = 0.01

    #: Handelsfenster in Boersenzeit. Vorgabe deckt London-Eroeffnung bis
    #: US-Schluss ab; ausserhalb ist der Nasdaq duenn.
    handel_von: dtime = dtime(3, 0)
    handel_bis: dtime = dtime(16, 0)
    handel_zeitzone: str = "America/New_York"
    nur_wochentags: bool = True

    #: NinjaTrader-Konto. Das AddOn laesst ohnehin nur Simulationskonten zu;
    #: der Name steht hier, damit im Protokoll steht, WELCHES gehandelt wurde.
    konto: str = "Sim101"

    #: Wie oft der Bot nach neuen Signalen sieht.
    takt_sekunden: int = 60


@dataclass(frozen=True)
class Config:
    market: MarketConfig
    indicators: IndicatorConfig
    # Alles ab hier hat brauchbare Defaults - so laesst sich ein Config-Objekt
    # in Tests und Skripten aufbauen, ohne jede Sektion auszubuchstabieren.
    analyse: AnalyseConfig = field(default_factory=AnalyseConfig)
    event_risk: EventRiskConfig = field(default_factory=EventRiskConfig)
    macro: MacroConfig = field(default_factory=MacroConfig)
    ntbridge: NtBridgeConfig = field(default_factory=NtBridgeConfig)
    ideas: IdeasConfig = field(default_factory=IdeasConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    ausfuehrung: AusfuehrungConfig = field(default_factory=AusfuehrungConfig)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # -- Laden -------------------------------------------------------------

    @staticmethod
    def load(path: str | os.PathLike[str] = DEFAULT_CONFIG_PATH) -> "Config":
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(f"Konfigurationsdatei nicht gefunden: {config_path.resolve()}")
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ConfigError("config.yaml muss ein Mapping auf oberster Ebene sein.")
        return Config.from_dict(data)

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "Config":
        mk = dict(_require(data, "market", "root"))
        sess = dict(mk.pop("session", {}) or {})
        market = MarketConfig(
            product=str(mk.get("product", "NQ")).upper(),
            contract_override=(mk.get("contract_override") or None),
            candle_interval_minutes=int(mk.get("candle_interval_minutes", 1)),
            candle_buffer_size=int(mk.get("candle_buffer_size", 500)),
            warmup_bars=int(mk.get("warmup_bars", 300)),
            tick_size=float(mk.get("tick_size", 0.25)),
            point_value=float(mk.get("point_value", 20.0)),
            session=SessionConfig(
                timezone=str(sess.get("timezone", "America/New_York")),
                start_time=_parse_hhmm(str(sess.get("start_time", "18:00")), "market.session.start_time"),
                end_time=_parse_hhmm(str(sess.get("end_time", "17:00")), "market.session.end_time"),
            ),
        )

        ind = dict(data.get("indicators", {}) or {})
        flag = dict(ind.pop("flag", {}) or {})
        indicators = IndicatorConfig(
            rsi_period=int(ind.get("rsi_period", 14)),
            sma_fast=int(ind.get("sma_fast", 20)),
            sma_slow=int(ind.get("sma_slow", 50)),
            atr_period=int(ind.get("atr_period", 14)),
            flag=FlagConfig(
                impulse_lookback=int(flag.get("impulse_lookback", 20)),
                impulse_min_atr=float(flag.get("impulse_min_atr", 2.5)),
                consolidation_lookback=int(flag.get("consolidation_lookback", 10)),
                consolidation_max_atr=float(flag.get("consolidation_max_atr", 2.40)),
                breakout_buffer_atr=float(flag.get("breakout_buffer_atr", 0.1)),
            ),
        )

        an = dict(data.get("analyse", {}) or {})
        analyse = AnalyseConfig(
            swing_strength=int(an.get("swing_strength", 3)),
            swing_lookback=int(an.get("swing_lookback", 120)),
            max_zones=int(an.get("max_zones", 3)),
            zone_merge_atr=float(an.get("zone_merge_atr", 0.5)),
            trend_slope_lookback=int(an.get("trend_slope_lookback", 10)),
            trend_flat_threshold_atr=float(an.get("trend_flat_threshold_atr", 0.02)),
        )

        er = dict(data.get("event_risk", {}) or {})
        event_risk = EventRiskConfig(
            enabled=bool(er.get("enabled", True)),
            currencies=tuple(er.get("currencies", ["USD"])),
            impacts=tuple(er.get("impacts", ["High"])),
            blackout_minutes_before=float(er.get("blackout_minutes_before", 15)),
            blackout_minutes_after=float(er.get("blackout_minutes_after", 15)),
            schedule_cache_minutes=float(er.get("schedule_cache_minutes", 30)),
            actual_cache_hours=float(er.get("actual_cache_hours", 6)),
            upcoming_limit=int(er.get("upcoming_limit", 8)),
            forex_factory_url=str(
                er.get(
                    "forex_factory_url",
                    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                )
            ),
        )

        mc = dict(data.get("macro", {}) or {})
        macro = MacroConfig(
            enabled=bool(mc.get("enabled", True)),
            datenbank=str(mc.get("datenbank", "data/macro.sqlite3")),
            serien={
                str(series_id).upper(): str(name)
                for series_id, name in (mc.get("serien", {}) or {}).items()
            },
            marktkalender=str(mc.get("marktkalender", "CME_Equity")),
            wichtigkeit={
                str(series_id).upper(): str(stufe)
                for series_id, stufe in (mc.get("wichtigkeit", {}) or {}).items()
            },
        )

        nb = dict(data.get("ntbridge", {}) or {})
        ntbridge = NtBridgeConfig(
            enabled=bool(nb.get("enabled", True)),
            host=str(nb.get("host", "127.0.0.1")),
            port=int(nb.get("port", 8787)),
            database=str(nb.get("database", "data/ntbridge.sqlite3")),
            stale_factor=float(nb.get("stale_factor", 2.0)),
            symbol_map={
                str(key).upper(): str(value).upper()
                for key, value in (nb.get("symbol_map", {}) or {}).items()
            },
        )

        id_ = dict(data.get("ideas", {}) or {})
        id_setups = dict(id_.get("setups", {}) or {})
        id_filter = dict(id_.get("filter", {}) or {})
        ideas = IdeasConfig(
            enabled=bool(id_.get("enabled", True)),
            profil=str(id_.get("profil", "sim_frei")).lower(),
            profile_erlaubt=tuple(
                str(wert).lower()
                for wert in (
                    id_.get("profile_erlaubt")
                    or ["sim_frei", "lucid_challenge", "lucid_funded"]
                )
            ),
            datenbank=str(id_.get("datenbank", "data/ideas.sqlite3")),
            instrumente=tuple(
                str(symbol).upper() for symbol in (id_.get("instrumente", ["MNQ"]) or ["MNQ"])
            ),
            timeframe=str(id_.get("timeframe", "5m")).lower(),
            bars=int(id_.get("bars", 1500)),
            crv_schwelle=float(id_.get("crv_schwelle", 1.5)),
            speichere_gefilterte=bool(id_.get("speichere_gefilterte", True)),
            min_ideen_pro_kategorie=int(id_.get("min_ideen_pro_kategorie", 20)),
            setups={
                str(schluessel): _lies_setup_parameter(werte)
                for schluessel, werte in id_setups.items()
            },
            filter=IdeenFilterConfig(
                adx_aktiv=bool(id_filter.get("adx_aktiv", True)),
                adx_trend_min=float(id_filter.get("adx_trend_min", 20.0)),
                adx_range_max=float(id_filter.get("adx_range_max", 25.0)),
                liquiditaet_aktiv=bool(id_filter.get("liquiditaet_aktiv", True)),
                duennzone_aktiv=bool(id_filter.get("duennzone_aktiv", True)),
                blackout_aktiv=bool(id_filter.get("blackout_aktiv", True)),
                blackout_max_alter_tage=float(
                    id_filter.get("blackout_max_alter_tage", 7.0)
                ),
            ),
        )

        lg = dict(data.get("logging", {}) or {})
        logging_cfg = LoggingConfig(
            level=str(lg.get("level", "INFO")).upper(),
            directory=str(lg.get("directory", "logs")),
            text_file=str(lg.get("text_file", "bot.log")),
            json_file=str(lg.get("json_file", "events.jsonl")),
            max_bytes=int(lg.get("max_bytes", 10 * 1024 * 1024)),
            backup_count=int(lg.get("backup_count", 5)),
            console=bool(lg.get("console", True)),
        )

        bt = dict(data.get("backtest", {}) or {})
        split = dict(bt.get("split", {}) or {})
        backtest = BacktestConfig(
            provider=str(bt.get("provider", "csv")).lower(),
            csv_directory=str((bt.get("csv", {}) or {}).get("directory", "data")),
            output_directory=str(bt.get("output_directory", "backtest_results")),
            kostenprofil=str(bt.get("kostenprofil", "private_ninjatrader")).lower(),
            kostenprofile={
                str(name).lower(): dict(werte or {})
                for name, werte in (bt.get("kostenprofile", {}) or {}).items()
            },
            commission_per_side=float(bt.get("commission_per_side", 2.50)),
            slippage_ticks_per_side=float(bt.get("slippage_ticks_per_side", 1.0)),
            split=SplitConfig(
                mode=str(split.get("mode", "fraction")).lower(),
                in_sample_fraction=float(split.get("in_sample_fraction", 0.7)),
                split_date=(split.get("split_date") or None),
                validation_fraction=float(split.get("validation_fraction", 0.5)),
            ),
        )

        aus = dict(data.get("ausfuehrung", {}) or {})
        ausfuehrung = AusfuehrungConfig(
            enabled=bool(aus.get("enabled", False)),
            kontoprofil=str(aus.get("kontoprofil", "frei")).lower(),
            kontoprofile={
                str(name).lower(): dict(werte or {})
                for name, werte in (aus.get("kontoprofile", {}) or {}).items()
            },
            startkapital_usd=(
                None if aus.get("startkapital_usd") is None
                else float(aus["startkapital_usd"])
            ),
            max_kontrakte=int(aus.get("max_kontrakte", 2)),
            risiko_je_trade_usd=(
                None if aus.get("risiko_je_trade_usd") is None
                else float(aus["risiko_je_trade_usd"])
            ),
            risiko_je_trade_anteil=float(aus.get("risiko_je_trade_anteil", 0.01)),
            handel_von=_parse_hhmm(str(aus.get("handel_von", "03:00")), "ausfuehrung.handel_von"),
            handel_bis=_parse_hhmm(str(aus.get("handel_bis", "16:00")), "ausfuehrung.handel_bis"),
            handel_zeitzone=str(aus.get("handel_zeitzone", "America/New_York")),
            nur_wochentags=bool(aus.get("nur_wochentags", True)),
            konto=str(aus.get("konto", "Sim101")),
            takt_sekunden=int(aus.get("takt_sekunden", 60)),
        )

        cfg = Config(
            market=market,
            indicators=indicators,
            analyse=analyse,
            event_risk=event_risk,
            macro=macro,
            ntbridge=ntbridge,
            ideas=ideas,
            logging=logging_cfg,
            backtest=backtest,
            ausfuehrung=ausfuehrung,
            raw=dict(data),
        )
        cfg.validate()
        return cfg

    # -- Validierung -------------------------------------------------------

    def validate(self) -> None:
        if self.market.candle_interval_minutes <= 0:
            raise ConfigError("market.candle_interval_minutes muss > 0 sein.")
        if self.market.tick_size <= 0:
            raise ConfigError("market.tick_size muss > 0 sein.")
        if self.market.point_value <= 0:
            raise ConfigError("market.point_value muss > 0 sein.")
        needed = self.indicators.min_bars_required
        if self.market.candle_buffer_size < needed:
            raise ConfigError(
                f"market.candle_buffer_size ({self.market.candle_buffer_size}) ist kleiner als "
                f"der Bedarf der Indikatoren ({needed})."
            )
        # Kontraktspezifikation gegen das Instrument-Register pruefen.
        # Ein "product: MNQ" mit den Punktwerten von NQ wuerde jede
        # USD-Angabe um den Faktor 10 verfaelschen - lautlos.
        from common.instruments import UnknownInstrument, get_instrument

        try:
            instrument = get_instrument(self.market.product)
        except UnknownInstrument:
            instrument = None

        if instrument is not None:
            if abs(self.market.tick_size - instrument.tick_size) > 1e-9:
                raise ConfigError(
                    f"market.tick_size ({self.market.tick_size}) passt nicht zu "
                    f"{instrument.root} im Instrument-Register ({instrument.tick_size})."
                )
            if abs(self.market.point_value - instrument.point_value) > 1e-9:
                raise ConfigError(
                    f"market.point_value ({self.market.point_value}) passt nicht zu "
                    f"{instrument.root} im Instrument-Register ({instrument.point_value}). "
                    f"Ein Tick ist bei {instrument.root} {instrument.tick_value:.2f} USD wert."
                )

        # Ausfuehrung: ein Tippfehler im Kontoprofil wuerde nicht auffallen,
        # sondern den Bot unter den falschen Grenzen handeln lassen - und das
        # merkt man erst, wenn eine Grenze gerissen ist, die es gar nicht gab.
        from common.kontoregeln import KONTOREGELN, bekannte_kontoprofile

        if self.ausfuehrung.kontoprofil not in KONTOREGELN:
            raise ConfigError(
                f"ausfuehrung.kontoprofil ({self.ausfuehrung.kontoprofil!r}) ist "
                f"unbekannt. Bekannt: {', '.join(bekannte_kontoprofile())}"
            )
        if self.ausfuehrung.max_kontrakte <= 0:
            raise ConfigError("ausfuehrung.max_kontrakte muss > 0 sein.")
        if not 0 < self.ausfuehrung.risiko_je_trade_anteil <= 0.25:
            raise ConfigError(
                "ausfuehrung.risiko_je_trade_anteil muss zwischen 0 und 0.25 liegen. "
                "Ein Viertel des Puffers auf einem Trade ist bereits die Grenze zum "
                "Unsinn; darueber ist es kein Risikomass mehr."
            )
        if (
            self.ausfuehrung.risiko_je_trade_usd is not None
            and self.ausfuehrung.risiko_je_trade_usd <= 0
        ):
            raise ConfigError("ausfuehrung.risiko_je_trade_usd muss > 0 sein.")
        if (
            self.ausfuehrung.enabled
            and self.ausfuehrung.risiko_je_trade_usd is None
            and KONTOREGELN[self.ausfuehrung.kontoprofil].max_verlust_usd is None
            and not self.ausfuehrung.startkapital_usd
        ):
            raise ConfigError(
                "ausfuehrung.enabled ist true auf dem Profil 'frei', aber weder "
                "startkapital_usd noch risiko_je_trade_usd sind gesetzt. Das "
                "Risikobudget waere 0 und der Bot wuerde jede Idee ablehnen - "
                "das saehe aus wie ein Defekt, waere aber Absicht."
            )
        if self.ausfuehrung.handel_von >= self.ausfuehrung.handel_bis:
            raise ConfigError(
                f"ausfuehrung.handel_von ({self.ausfuehrung.handel_von:%H:%M}) muss vor "
                f"handel_bis ({self.ausfuehrung.handel_bis:%H:%M}) liegen. Ein Fenster "
                "ueber Mitternacht ist hier nicht vorgesehen - es waere in "
                "Boersenzeit auch keins."
            )
        if self.ausfuehrung.takt_sekunden < 5:
            raise ConfigError(
                "ausfuehrung.takt_sekunden unter 5 Sekunden ist sinnlos: der Bot "
                "arbeitet auf Kerzenschluessen, nicht auf Ticks."
            )
        # Ein Prop-Konto ohne Startkapital laesst jede Verlustgrenze ins Leere
        # laufen - die Grenzen sind absolute Kontostaende, keine Prozente.
        if (
            self.ausfuehrung.kontoprofil != "frei"
            and self.ausfuehrung.startkapital_usd is None
            and KONTOREGELN[self.ausfuehrung.kontoprofil].kontogroesse_usd <= 0
        ):
            raise ConfigError(
                "ausfuehrung.startkapital_usd fehlt und das Profil kennt keine "
                "Kontogroesse - die Verlustgrenzen waeren nicht berechenbar."
            )

        swing_window = 2 * self.analyse.swing_strength + 1
        if self.analyse.swing_lookback < swing_window:
            raise ConfigError(
                f"analyse.swing_lookback ({self.analyse.swing_lookback}) muss mindestens "
                f"2*swing_strength+1 = {swing_window} betragen, sonst kann kein Swing "
                "bestaetigt werden."
            )
        if self.market.candle_buffer_size < self.analyse.swing_lookback:
            raise ConfigError(
                f"market.candle_buffer_size ({self.market.candle_buffer_size}) ist kleiner als "
                f"analyse.swing_lookback ({self.analyse.swing_lookback}) - die Zonen "
                "wuerden auf weniger Kerzen beruhen als konfiguriert."
            )
        # Ideen-Protokollierung: ein Tippfehler im Profil oder ein unbekannter
        # Setup-Schluessel wuerde nicht auffallen, sondern die spaetere
        # Auswertung still in zwei Gruppen zerlegen bzw. eine Familie nie
        # ausloesen lassen. Deshalb hier abbrechen statt akzeptieren.
        if self.ideas.enabled:
            if self.ideas.profil not in self.ideas.profile_erlaubt:
                raise ConfigError(
                    f"ideas.profil ({self.ideas.profil!r}) steht nicht in "
                    f"ideas.profile_erlaubt ({', '.join(self.ideas.profile_erlaubt)}). "
                    "Das Feld dokumentiert die tatsaechliche Kontoumgebung; ein "
                    "Tippfehler wuerde die Auswertung unbemerkt in zwei Gruppen "
                    "zerlegen."
                )
            # Die Pruefung der Setup-SCHLUESSEL steht bewusst nicht hier,
            # sondern in ``ideas.setups.pruefe_konfiguration``. Ein Import
            # von ``ideas`` an dieser Stelle waere eine Schichtumkehr -
            # ``common`` ist die Basis, ``ideas`` liegt darueber - und wuerde
            # ausserdem ``ideas`` samt ``backtest.strategies`` in die
            # Importhuelle des MCP-Servers ziehen, die bewusst schmal ist.
            if self.ideas.setups and not any(
                parameter.aktiv for parameter in self.ideas.setups.values()
            ):
                raise ConfigError(
                    "ideas.enabled ist true, aber keine einzige Setup-Familie ist "
                    "aktiv. Die Protokollierung liefe dann dauerhaft ohne Ergebnis."
                )

            # Vortagesmarken brauchen die komplette Vorsession PLUS die
            # laufende. Reicht ideas.bars nicht, bleiben prev_session_high
            # und -low dauerhaft NaN und pdh_pdl_bruch loest NIE aus - ohne
            # Fehlermeldung.
            #
            # Diese Zusicherung stand bis zum 22.08.2026 an den Alarmen des
            # Legacy-Pfads (candle_buffer_size). Der Pfad ist entfernt, die
            # Gefahr nicht: sie ist mit der Ideen-Protokollierung nur
            # umgezogen.
            minuten = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(
                self.ideas.timeframe
            )
            if minuten is not None:
                noetig = 2 * (23 * 60 // minuten)
                if self.ideas.bars < noetig:
                    raise ConfigError(
                        f"ideas.bars ({self.ideas.bars}) reicht nicht fuer "
                        f"Vortageshoch/-tief: bei {self.ideas.timeframe}-Kerzen "
                        f"werden {noetig} benoetigt (Vorsession + laufende "
                        "Session). Sonst bleiben die Vortagesmarken leer und "
                        "das Setup pdh_pdl_bruch loest nie aus."
                    )

        if not 0.0 < self.backtest.split.in_sample_fraction < 1.0:
            raise ConfigError("backtest.split.in_sample_fraction muss zwischen 0 und 1 liegen.")
        if not 0.0 < self.backtest.split.validation_fraction < 1.0:
            raise ConfigError("backtest.split.validation_fraction muss zwischen 0 und 1 liegen.")
        if self.backtest.split.mode not in {"fraction", "date"}:
            raise ConfigError("backtest.split.mode muss 'fraction' oder 'date' sein.")
        if self.backtest.split.mode == "date" and not self.backtest.split.split_date:
            raise ConfigError("backtest.split.mode='date' erfordert backtest.split.split_date.")

        if not self.macro.datenbank.strip():
            raise ConfigError("macro.datenbank darf nicht leer sein.")
        if not self.macro.marktkalender.strip():
            raise ConfigError("macro.marktkalender darf nicht leer sein.")
        unbekannte_stufen = set(self.macro.wichtigkeit.values()) - {"High", "Medium", "Low"}
        if unbekannte_stufen:
            raise ConfigError(
                f"macro.wichtigkeit enthaelt unbekannte Stufen {sorted(unbekannte_stufen)} - "
                "erlaubt sind nur 'High', 'Medium', 'Low'."
            )

