"""Aus Fuellungen werden Trades.

Warum das ein eigener Baustein ist
----------------------------------
Ein Trade entsteht nicht aus einer Order, sondern aus **zwei Fuellungen**:
einer, die eine Position oeffnet, und einer, die sie schliesst. Dazwischen
liegt alles, was ihn spaeter auswertbar macht - Richtung, Dauer, Kosten,
R-Vielfaches.

Das NinjaScript-AddOn liefert dafuer genau die Information, die man braucht:
jede Fuellung traegt eine **Rolle** (``entry``/``stop``/``target``), weil alle
drei Orders einer Klammer denselben ``order_key`` haben. Ohne die Rolle waere
nicht unterscheidbar, ob eine Fuellung eine Position eroeffnet oder schliesst
- und das ist der Unterschied zwischen einem Gewinn und einem Verlust mit
demselben Vorzeichen.

Was hier NICHT passiert
-----------------------
MAE und MFE bleiben ``None``. Sie brauchen den Kursverlauf **waehrend** des
Trades, und der steht erst fest, wenn die Kerzen dieses Zeitraums vorliegen.
Sie nachtraeglich aus Ein- und Ausstiegskurs zu schaetzen waere eine Zahl,
die aussieht wie eine Messung - genau das, was Invariante 11 verbietet.
``backtest/excursions.py`` rechnet sie spaeter aus den Kerzen nach.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from common.config import SessionConfig
from common.sessions import session_date_for

__all__ = ["EINSTIEG_ROLLEN", "AUSSTIEG_ROLLEN", "session_datum", "baue_trade"]

#: Rollen, die eine Position oeffnen bzw. schliessen. Eine unbekannte Rolle
#: gehoert in keine der beiden Mengen und fuehrt zu keinem Trade - lieber eine
#: fehlende Buchung als eine falsche.
EINSTIEG_ROLLEN = frozenset({"entry", ""})
AUSSTIEG_ROLLEN = frozenset({"stop", "target", "exit", "flatten"})


def session_datum(zeitpunkt: datetime | str) -> str:
    """CME-Handelstag als ISO-Datum (18:00-ET-Rollover).

    Ueber ``common.sessions`` - dieselbe Regel wie bei Session-VWAP und
    Vortagesmarken. Eine zweite Tagesdefinition in der Ausfuehrungsschicht
    liefe frueher oder spaeter auseinander, und niemand wuerde es merken.
    """
    if isinstance(zeitpunkt, str):
        zeitpunkt = datetime.fromisoformat(zeitpunkt)
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=timezone.utc)
    return session_date_for(zeitpunkt, SessionConfig()).isoformat()


def ts_aus_nanosekunden(ts: Any) -> str:
    """NinjaTrader schickt Epoch-Nanosekunden; hier wird ISO-UTC daraus."""
    try:
        return datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(timezone.utc).isoformat()


def baue_trade(
    *,
    order: dict[str, Any],
    einstieg: dict[str, Any],
    ausstieg: dict[str, Any],
    point_value: float,
) -> dict[str, Any]:
    """Ein geschlossener Trade aus Order, Einstiegs- und Ausstiegsfuellung.

    ``point_value`` kommt aus der Konfiguration bzw. dem Instrumentenregister
    und wird hier NICHT geraten. Bei MNQ sind es 2 USD je Indexpunkt; mit dem
    Vorgabewert von ``MarketConfig`` (20, das ist NQ) waere jede USD-Zahl
    zehnmal zu gross - derselbe Fehler, der im Backtest-Endpunkt stand.
    """
    richtung = str(order["richtung"]).lower()
    vorzeichen = 1.0 if richtung == "long" else -1.0

    einstiegskurs = float(einstieg["preis"])
    ausstiegskurs = float(ausstieg["preis"])
    menge = int(ausstieg.get("menge") or order.get("menge") or 1)

    punkte = (ausstiegskurs - einstiegskurs) * vorzeichen
    kommission = float(einstieg.get("kommission") or 0.0) + float(
        ausstieg.get("kommission") or 0.0
    )
    pnl = punkte * point_value * menge - kommission

    # R-Vielfaches nur, wenn ein Stop bekannt war. Ohne Stop gibt es kein R -
    # und ein ersatzweise angenommener Abstand waere eine erfundene Bezugsgroesse.
    #
    # Der Stop kommt in zwei Bedeutungen: der Bot liefert einen ABSOLUTEN
    # KURS aus der Ideen-Tabelle, das Order-Panel einen ABSTAND in Punkten.
    # Beides hier zu verwechseln kostet nicht nur Genauigkeit: am 02.09.2026
    # stand als "stop_loss" die 20 aus dem Panel, und die Rechnung
    # abs(29430,25 - 20) ergab ein Risiko von 29410 Punkten - jedes R war
    # damit um Faktor 1470 zu klein.
    risiko_punkte = 0.0
    abstand = order.get("stop_loss_punkte")
    if abstand:
        risiko_punkte = abs(float(abstand))
    else:
        stop = order.get("stop_loss")
        if stop:
            risiko_punkte = abs(einstiegskurs - float(stop))
    r_vielfaches = punkte / risiko_punkte if risiko_punkte > 0 else None

    return {
        "trade_id": str(uuid.uuid4()),
        "order_id": order["order_id"],
        "instrument": order["instrument"],
        "richtung": richtung,
        "menge": menge,
        "einstieg_utc": einstieg["ts_utc"],
        "einstiegskurs": einstiegskurs,
        "ausstieg_utc": ausstieg["ts_utc"],
        "ausstiegskurs": ausstiegskurs,
        "grund_ausstieg": ausstieg.get("rolle") or "unbekannt",
        "punkte_brutto": punkte,
        "kommission": kommission,
        "pnl_usd": pnl,
        "r_vielfaches": r_vielfaches,
        # Bewusst leer - siehe Modul-Docstring.
        "mae_punkte": None,
        "mfe_punkte": None,
        "session_datum": session_datum(ausstieg["ts_utc"]),
        "idee_id": order.get("idee_id"),
        "hypothese": order.get("hypothese"),
    }


def verbuche(store, order_id: str, point_value: float) -> dict[str, Any] | None:
    """Prueft, ob die Fuellungen einer Order einen geschlossenen Trade ergeben.

    Wird nach jeder eingehenden Fuellung aufgerufen. Liefert den Trade, wenn
    er gerade vollstaendig geworden ist, sonst ``None``.

    Bewusst idempotent gedacht: der Aufrufer schreibt den Trade nur, wenn
    hier einer zurueckkommt, und eine bereits verbuchte Ausstiegsfuellung
    fuehrt zu keiner zweiten Buchung, weil die Fuellungen selbst ueber die
    ``exec_id`` eindeutig sind.
    """
    order = store.order(order_id)
    if order is None:
        return None

    fills = store.fills(order_id)
    einstiege = [f for f in fills if (f["rolle"] or "") in EINSTIEG_ROLLEN]
    ausstiege = [f for f in fills if (f["rolle"] or "") in AUSSTIEG_ROLLEN]
    if not einstiege or not ausstiege:
        return None

    bereits = {t["order_id"]: t for t in store.trades(limit=1000)}
    if order_id in bereits:
        return None

    return baue_trade(
        order=order,
        einstieg=einstiege[0],
        ausstieg=ausstiege[-1],
        point_value=point_value,
    )
