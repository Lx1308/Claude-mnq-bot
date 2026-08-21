"""Claude-Aufruf bei ausgeloestem Alarm.

Wichtig fuer die Datensparsamkeit: An die API gehen ausschliesslich die
*berechneten Kennzahlen* aus dem :class:`MarketSnapshot` und die Details der
ausgeloesten Bedingung - keine Rohdaten, keine Tickstroeme, keine Bilder.

Der System-Prompt weist Claude an,
  * die Lage sachlich in Wenn-Dann-Szenarien zu beschreiben,
  * KEINE Kauf-/Verkaufsempfehlung zu geben,
  * am Ende auf "keine Anlageberatung" hinzuweisen.

Fehler (Timeout, Rate-Limit, Ausfall) werden abgefangen: der Bot laeuft
weiter und verschickt den Alarm dann ohne Claude-Kommentar.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from common.config import ClaudeConfig
from common.logging_setup import log_event
from live_bot.alerts.conditions import Alert
from live_bot.market.state import MarketSnapshot

log = logging.getLogger(__name__)

try:
    import anthropic
    from anthropic import AsyncAnthropic
except ImportError:  # pragma: no cover - Paket fehlt nur ohne Installation
    anthropic = None  # type: ignore[assignment]
    AsyncAnthropic = None  # type: ignore[assignment,misc]


DISCLAIMER = "Hinweis: Dies ist keine Anlageberatung."

SYSTEM_PROMPT = """Du bist ein nuechterner Markt-Analyse-Assistent fuer einen \
erfahrenen Futures-Trader (CME-Index-Futures, Intraday).

Du bekommst ausschliesslich berechnete Kennzahlen einer gerade abgeschlossenen \
Kerze sowie die Beschreibung einer ausgeloesten technischen Bedingung. Du hast \
keinen Chart und keine Rohdaten - erfinde also keine Kursverlaeufe, Volumina \
oder Niveaus, die nicht in den Daten stehen.

Aufgabe:
1. Beschreibe die Ausgangslage in hoechstens drei kurzen Saetzen, rein sachlich \
und nur auf Basis der uebergebenen Zahlen.
2. Formuliere danach zwei bis drei Wenn-Dann-Szenarien. Jedes Szenario nennt \
eine konkrete, beobachtbare Bedingung (z.B. ein Preisniveau, ein RSI-Wert, \
eine VWAP-Relation) und was daraus technisch folgen wuerde.
3. Nenne kurz, was gegen die jeweilige Lesart spricht (Gegenargument oder \
Invalidierungspunkt).

Strikte Regeln:
- Gib NIEMALS eine direkte Kauf- oder Verkaufsempfehlung ab. Keine \
Einstiegssignale, keine Positionsgroessen, keine Stop- oder Zielvorgaben als \
Handlungsanweisung. Beschreibe Niveaus nur als technische Marken.
- Verwende keine Formulierungen wie "du solltest", "kaufe", "verkaufe", \
"Einstieg jetzt".
- Keine Prognosen mit Wahrscheinlichkeitsangaben, die die Daten nicht hergeben.
- Antworte auf Deutsch, kompakt, ohne Marketing-Sprache und ohne Emojis.
- Schliesse deine Antwort IMMER mit exakt dieser Zeile ab: \
"Hinweis: Dies ist keine Anlageberatung."
"""


REPORT_DISCLAIMER = (
    "Hinweis: Dies ist keine Anlageberatung. Marktbedingungen koennen sich "
    "schnell aendern - pruefe alle Marken selbst am Chart."
)

REPORT_SYSTEM_PROMPT = """Du bist ein technischer Markt-Analyst fuer einen \
erfahrenen Futures-Trader (CME-Index-Futures, Intraday). Er fordert diesen \
Bericht aktiv an und trifft seine Entscheidungen selbst.

Du bekommst ausschliesslich berechnete Kennzahlen zur zuletzt abgeschlossenen \
Kerze: Indikatoren, Vortagesmarken, Trendlage sowie Unterstuetzungs- und \
Widerstandszonen aus juengsten Swing-Punkten. Du hast keinen Chart und keine \
Rohdaten - erfinde keine Niveaus, Muster oder Volumina, die nicht in den \
Daten stehen. Wenn eine Angabe fehlt (null), sage das, statt sie zu schaetzen.

Gliedere den Bericht in genau diese Abschnitte, jeweils mit der angegebenen \
Ueberschrift und durch eine Leerzeile getrennt:

LAGE
Zwei bis drei Saetze: Trend oder Seitwaerts, Lage zu VWAP, SMA20 und SMA50, \
RSI-Einordnung, Position innerhalb der Tagesspanne.

STRUKTUR
Die naechsten relevanten Zonen mit konkreten Zahlen und ihrem Abstand zum \
aktuellen Kurs. Erwaehne, wie oft eine Zone bereits getestet wurde.

SZENARIO A / SZENARIO B
Zwei gegenlaeufige Wenn-Dann-Szenarien, jeweils in dieser Form: eine \
beobachtbare Bedingung (konkretes Niveau), die technische Folge daraus, und \
der Punkt, an dem das Szenario hinfaellig waere. Formuliere als Struktur, \
nicht als Prognose - etwa "Solange X haelt, spricht die Struktur eher fuer Y".

MARKEN
Fuer das aus der Struktur naheliegendere Szenario, als reine Zahlenangabe:
- Einstiegszone (eine Spanne, keine Punktlandung) mit technischer Begruendung
- Stop-Marke, hergeleitet aus dem letzten Swing-Punkt oder aus einem \
ATR-Vielfachen; nenne die Herleitung explizit
- Zielmarke, hergeleitet aus der naechsten Zone
- Risiko und Chance jeweils in Punkten UND in USD je Kontrakt (Punktwert \
steht in den Daten), dazu das Chance-Risiko-Verhaeltnis
Ergibt sich kein Verhaeltnis von mindestens 1:1.5, sage das offen und nenne \
keine erzwungenen Marken.

EINSCHAETZUNG
Ein bis zwei Saetze, welche Richtung die aktuelle Struktur eher stuetzt, \
ausdruecklich als Szenario und mit der Bedingung, unter der es gilt.

Strikte Regeln:
- Keine Handlungsanweisungen. Niemals "kaufe", "verkaufe", "steig jetzt ein", \
"du solltest". Marken sind technische Niveaus zur eigenen Bewertung, keine \
Auftraege.
- Keine Empfehlung zur Kontraktanzahl oder Positionsgroesse. Risiko nur je \
einzelnem Kontrakt beziffern.
- Keine Wahrscheinlichkeitsangaben in Prozent, die die Daten nicht hergeben.
- Antworte auf Deutsch, in kurzen Absaetzen, ohne Emojis, ohne Markdown-\
Formatierung (kein *, **, #) - der Text geht unveraendert an Telegram.
- Halte den gesamten Bericht unter 2500 Zeichen.
- Schliesse IMMER mit exakt dieser Zeile ab: \
"Hinweis: Dies ist keine Anlageberatung. Marktbedingungen koennen sich \
schnell aendern - pruefe alle Marken selbst am Chart."
"""


@dataclass(frozen=True)
class ClaudeComment:
    """Ergebnis eines Claude-Aufrufs."""

    text: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    succeeded: bool = True
    error: str | None = None
    truncated: bool = False


def build_metrics_payload(snapshot: MarketSnapshot, alert: Alert) -> dict[str, Any]:
    """Baut das an Claude gesendete Kennzahlen-Objekt.

    Bewusst als eigene Funktion, damit im Test und im Log exakt nachvollziehbar
    ist, welche Felder das Haus verlassen.
    """

    def rounded(value: float | None, digits: int = 2) -> float | None:
        return round(value, digits) if value is not None else None

    distance_to_vwap = (
        rounded(snapshot.close - snapshot.vwap) if snapshot.vwap is not None else None
    )

    return {
        "instrument": snapshot.symbol,
        "kerzenintervall_minuten": snapshot.interval_minutes,
        "zeitpunkt_utc": snapshot.timestamp.isoformat(),
        "handelstag": snapshot.session_date.isoformat() if snapshot.session_date else None,
        "kerze": {
            "open": rounded(snapshot.open),
            "high": rounded(snapshot.high),
            "low": rounded(snapshot.low),
            "close": rounded(snapshot.close),
            "volumen": rounded(snapshot.volume, 0),
        },
        "indikatoren": {
            "rsi_14": rounded(snapshot.rsi, 1),
            "sma_20": rounded(snapshot.sma_fast),
            "sma_50": rounded(snapshot.sma_slow),
            "vwap_session": rounded(snapshot.vwap),
            "atr": rounded(snapshot.atr),
            "abstand_close_zu_vwap": distance_to_vwap,
            "close_ueber_sma20": (
                None if snapshot.sma_fast is None else snapshot.close > snapshot.sma_fast
            ),
            "sma20_ueber_sma50": (
                None
                if snapshot.sma_fast is None or snapshot.sma_slow is None
                else snapshot.sma_fast > snapshot.sma_slow
            ),
        },
        "vortagesmarken": {
            "hoch": rounded(snapshot.prev_session_high),
            "tief": rounded(snapshot.prev_session_low),
            "schluss": rounded(snapshot.prev_session_close),
        },
        "konsolidierung": {
            "in_konsolidierung": snapshot.flag_in_consolidation,
            "impulsrichtung": snapshot.flag_direction,
            "range_hoch": rounded(snapshot.flag_range_high),
            "range_tief": rounded(snapshot.flag_range_low),
            "ausbruch_oben": snapshot.flag_breakout_up,
            "ausbruch_unten": snapshot.flag_breakout_down,
        },
        "ausgeloeste_bedingung": {
            "schluessel": alert.condition,
            "beschreibung": alert.headline,
            "richtung": alert.direction,
            "details": alert.details,
        },
    }


class ClaudeCommentator:
    """Duenner Wrapper um die Anthropic Messages API."""

    def __init__(self, config: ClaudeConfig, api_key: str | None) -> None:
        self._config = config
        self._client: Any = None

        if not api_key:
            log_event(
                log,
                "claude.disabled",
                "Kein ANTHROPIC_API_KEY gesetzt - Alarme werden ohne Claude-Kommentar versendet",
                level=logging.WARNING,
            )
            return
        if AsyncAnthropic is None:
            log_event(
                log,
                "claude.disabled",
                "Paket 'anthropic' ist nicht installiert - Alarme ohne Claude-Kommentar",
                level=logging.WARNING,
            )
            return

        # Das SDK wiederholt 408/409/429/5xx selbstaendig mit Backoff.
        self._client = AsyncAnthropic(
            api_key=api_key,
            timeout=config.timeout_seconds,
            max_retries=config.max_retries,
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def comment(self, snapshot: MarketSnapshot, alert: Alert) -> ClaudeComment:
        """Kurzer Kommentar zu einem ausgeloesten Alarm. Wirft nie."""
        payload = build_metrics_payload(snapshot, alert)
        return await self._create(
            system=SYSTEM_PROMPT,
            user_message=(
                "Hier sind die berechneten Kennzahlen zum Zeitpunkt der ausgeloesten "
                "Bedingung. Beschreibe die Lage und die Wenn-Dann-Szenarien.\n\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
            ),
            max_tokens=self._config.max_tokens,
            effort=self._config.effort,
            disclaimer=DISCLAIMER,
            context={"condition": alert.condition, "kind": "alert"},
        )

    async def report(self, payload: dict[str, Any], *, symbol: str) -> ClaudeComment:
        """Ausfuehrlicher On-Demand-Bericht (/analyse). Wirft nie.

        Nutzt denselben Client, dieselben Timeouts und dieselbe
        Fehlerbehandlung wie :meth:`comment` - nur System-Prompt,
        Token-Budget und Effort unterscheiden sich.
        """
        return await self._create(
            system=REPORT_SYSTEM_PROMPT,
            user_message=(
                f"Erstelle den angeforderten Marktbericht fuer {symbol}. "
                "Hier sind die berechneten Kennzahlen zur zuletzt abgeschlossenen "
                "Kerze.\n\n" + json.dumps(payload, ensure_ascii=False, indent=2)
            ),
            max_tokens=self._config.report_max_tokens,
            effort=self._config.report_effort,
            disclaimer=REPORT_DISCLAIMER,
            context={"symbol": symbol, "kind": "on_demand_report"},
        )

    # -- Gemeinsamer Aufrufpfad -------------------------------------------

    async def _create(
        self,
        *,
        system: str,
        user_message: str,
        max_tokens: int,
        effort: str,
        disclaimer: str,
        context: dict[str, Any],
    ) -> ClaudeComment:
        if self._client is None:
            return ClaudeComment(
                text="",
                succeeded=False,
                error="Claude ist nicht konfiguriert.",
            )

        try:
            response = await self._client.messages.create(
                model=self._config.model,
                max_tokens=max_tokens,
                system=system,
                output_config={"effort": effort},
                messages=[{"role": "user", "content": user_message}],
            )
        except Exception as exc:  # noqa: BLE001 - Claude-Fehler darf den Bot nie stoppen
            error_type = type(exc).__name__
            log_event(
                log,
                "claude.error",
                f"Claude-Aufruf fehlgeschlagen ({error_type}): {exc}",
                level=logging.ERROR,
                error_type=error_type,
                error=str(exc),
                **context,
            )
            return ClaudeComment(text="", succeeded=False, error=f"{error_type}: {exc}")

        # Safety-Klassifikatoren koennen einen Request ablehnen - dann ist
        # content leer bzw. unvollstaendig. Immer zuerst stop_reason pruefen.
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            log_event(
                log,
                "claude.refusal",
                "Claude hat die Anfrage abgelehnt",
                level=logging.WARNING,
                category=category,
                **context,
            )
            return ClaudeComment(
                text="",
                model=getattr(response, "model", None),
                succeeded=False,
                error=f"refusal (category={category})",
            )

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()

        truncated = getattr(response, "stop_reason", None) == "max_tokens"
        if truncated:
            log_event(
                log,
                "claude.truncated",
                "Claude-Antwort wurde durch max_tokens abgeschnitten",
                level=logging.WARNING,
                max_tokens=max_tokens,
                **context,
            )

        # Der Disclaimer ist Pflicht - falls das Modell ihn vergisst oder die
        # Antwort abgeschnitten wurde, wird er hier ergaenzt.
        if disclaimer not in text:
            text = f"{text}\n\n{disclaimer}".strip()

        usage = getattr(response, "usage", None)
        comment = ClaudeComment(
            text=text,
            model=getattr(response, "model", None),
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            succeeded=True,
            truncated=truncated,
        )

        log_event(
            log,
            "claude.response",
            "Claude-Antwort erhalten",
            model=comment.model,
            input_tokens=comment.input_tokens,
            output_tokens=comment.output_tokens,
            response_text=comment.text,
            **context,
        )
        return comment
