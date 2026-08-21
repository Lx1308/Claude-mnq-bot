"""Aufloesung des Frontmonat-Kontrakts (z.B. NQ -> NQZ5).

Vorgehen: ``/contract/suggest`` liefert Kontraktnamen zum Produkt-Root.
Aus dem Namen wird per CME-Monatscode das Verfallsdatum abgeleitet
(3. Freitag des Verfallsmonats fuer Index-Futures) und der naechste
Kontrakt gewaehlt, der noch nicht in der Rollphase ist.

Warum nicht ueber ``/contractMaturity``? Das waere ein zusaetzlicher
API-Roundtrip pro Kandidat, ohne dass sich das Ergebnis fuer NQ/ES
unterscheiden wuerde. Wer einen anderen Kontrakt will, setzt
``market.contract_override`` in der config.yaml - dann wird hier gar
nichts geraten.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

from common.instruments import (
    MONTH_NUMBER_BY_CODE,
    Instrument,
    UnknownInstrument,
    get_instrument,
)
from common.instruments import third_friday as _third_friday
from common.logging_setup import log_event
from live_bot.tradovate.rest import TradovateApiError, TradovateRestClient

log = logging.getLogger(__name__)

# CME-Monatscodes (Weiterleitung aus dem Instrument-Register, damit es nur
# eine Quelle dafuer gibt).
MONTH_CODES = MONTH_NUMBER_BY_CODE

# Tage vor Verfall, ab denen auf den naechsten Kontrakt gerollt wird.
# Instrumentspezifische Werte kommen aus dem Register.
DEFAULT_ROLL_BUFFER_DAYS = 3


# Contract liegt in common/, damit nicht jeder Nutzer eines aufgeloesten
# Kontrakts den Tradovate-Stack mitzieht. Hier nur die Weiterleitung.
from common.contracts import Contract  # noqa: E402,F401


# Rueckwaertskompatible Weiterleitung - die Regel lebt im Instrument-Register.
third_friday = _third_friday


def _lookup_instrument(product: str) -> Instrument | None:
    try:
        return get_instrument(product)
    except UnknownInstrument:
        return None


def parse_contract_name(
    name: str,
    product: str,
    today: date,
    *,
    instrument: Instrument | None = None,
) -> date | None:
    """Leitet aus 'MNQZ5' bzw. 'MGCG26' das Verfallsdatum ab.

    Die Verfallsregel kommt aus dem Instrument-Register, nicht aus einer
    festen Annahme. Das ist keine Kosmetik: MNQ verfaellt am 3. Freitag,
    MGC am drittletzten Geschaeftstag des Liefermonats - wer eine Regel auf
    beide anwendet, rollt rund zwei Wochen daneben.

    Ist das Produkt nicht registriert, wird auf die Index-Futures-Regel
    zurueckgefallen (bisheriges Verhalten).
    """
    pattern = rf"^{re.escape(product.upper())}([FGHJKMNQUVXZ])(\d{{1,2}})$"
    match = re.match(pattern, name.upper())
    if not match:
        return None

    month_code = match.group(1)
    instrument = instrument or _lookup_instrument(product)

    # Monatscodes, die es fuer dieses Produkt gar nicht gibt, sind kein
    # gueltiger Kontrakt (z.B. "MGCH6" - Maerz ist bei Micro Gold nicht gelistet).
    if instrument is not None and month_code not in instrument.contract_months:
        return None

    month = MONTH_CODES[month_code]
    digits = match.group(2)

    if len(digits) == 2:
        year = 2000 + int(digits)
    else:
        # Einstellige Jahresangabe: naechstes Jahr mit passender Endziffer.
        digit = int(digits)
        year = today.year - (today.year % 10) + digit
        if year < today.year:
            year += 10

    if instrument is not None:
        return instrument.expiry_for(year, month)
    return _third_friday(year, month)


async def resolve_front_month(
    client: TradovateRestClient,
    product: str,
    *,
    today: date | None = None,
    roll_buffer_days: int = DEFAULT_ROLL_BUFFER_DAYS,
    max_suggestions: int = 20,
) -> Contract:
    """Ermittelt den aktuellen Frontmonat-Kontrakt fuer einen Produkt-Root."""
    today = today or date.today()
    product = product.upper()
    instrument = _lookup_instrument(product)
    if instrument is not None:
        roll_buffer_days = instrument.roll_buffer_days

    suggestions = await client.get(
        "/contract/suggest", params={"t": product, "l": max_suggestions}
    )
    if not suggestions:
        raise TradovateApiError(f"Keine Kontrakte fuer Produkt {product!r} gefunden.")

    candidates: list[Contract] = []
    for item in suggestions:
        name = str(item.get("name", ""))
        expiry = parse_contract_name(name, product, today, instrument=instrument)
        if expiry is None:
            continue  # Spreads, fremde Roots oder nicht gelistete Monate
        candidates.append(Contract(id=int(item["id"]), name=name, expiry=expiry))

    if not candidates:
        raise TradovateApiError(
            f"Konnte aus den Vorschlaegen fuer {product!r} keinen Standardkontrakt ableiten. "
            f"Bitte market.contract_override in der config.yaml setzen. "
            f"Vorschlaege waren: {[item.get('name') for item in suggestions]}"
        )

    cutoff = today + timedelta(days=roll_buffer_days)
    active = sorted(
        (contract for contract in candidates if contract.expiry and contract.expiry >= cutoff),
        key=lambda contract: contract.expiry,  # type: ignore[return-value,arg-type]
    )
    if not active:
        # Alle Kandidaten laufen (fast) ab - nimm den spaetesten als Notnagel.
        active = sorted(candidates, key=lambda contract: contract.expiry or date.max)

    chosen = active[0]
    log_event(
        log,
        "tradovate.contract.resolved",
        f"Frontmonat-Kontrakt fuer {product}: {chosen.name}",
        product=product,
        contract=chosen.name,
        contract_id=chosen.id,
        expiry=chosen.expiry.isoformat() if chosen.expiry else None,
    )
    return chosen


async def resolve_contract(
    client: TradovateRestClient,
    product: str,
    override: str | None = None,
    *,
    today: date | None = None,
) -> Contract:
    """Nutzt ``override``, falls gesetzt, sonst den Frontmonat."""
    if override:
        found = await client.get("/contract/find", params={"name": override.upper()})
        if not found or "id" not in found:
            raise TradovateApiError(f"Kontrakt {override!r} nicht gefunden.")
        contract = Contract(
            id=int(found["id"]),
            name=str(found.get("name", override.upper())),
            expiry=parse_contract_name(str(found.get("name", "")), product, today or date.today()),
        )
        log_event(
            log,
            "tradovate.contract.override",
            f"Verwende explizit konfigurierten Kontrakt {contract.name}",
            contract=contract.name,
            contract_id=contract.id,
        )
        return contract
    return await resolve_front_month(client, product, today=today)
