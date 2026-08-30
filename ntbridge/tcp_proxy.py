"""Bruecke zum NinjaScript-AddOn ``TradayriBridge`` (TCP, 127.0.0.1:39473).

Was dieser Baustein ist
-----------------------
Ein **Order-Kanal**, kein Datenkanal. Er holt die vom Execution-Server
eingereihten Orders ab, schickt sie zeilenweise als JSON an das AddOn und
meldet dessen Ausfuehrungsmeldungen zurueck.

Warum er KEINE Kerzen mehr schreibt
-----------------------------------
Die erste Fassung baute aus den Ticks des AddOns selbst Minutenkerzen und
schob sie in den Empfaenger (``POST /bars``). Das war aus zwei Gruenden
falsch und ist deshalb entfernt:

1. **Falsche Beschriftung.** Sie rechnete ``ts // 60s * 60s`` - das ist die
   EROEFFNUNGSzeit der Minute. NinjaTrader beschriftet eine Kerze mit ihrem
   ENDE (Ticks 14:00:00-14:00:59 ergeben die Kerze 14:01, Invariante 9 in
   CLAUDE.md). Beide Wege schrieben damit auf denselben Primaerschluessel
   ``(instrument, timeframe, ts_utc)`` zwei VERSCHIEDENE Zeitfenster.

2. **Unfertige Kerzen.** Gesendet wurde jede Sekunde mit ``closed: false``.
   Der Kerzenspeicher kennt kein "vorlaeufig" - er macht ein UPSERT. Die
   laufende, halbfertige Minute haette die fertige Kerze des Indikators
   ueberschrieben.

Zusammen haette das ab der naechsten Boersenoeffnung die 1m-Reihe still um
eine Minute verschoben, waehrend 5m/15m/1h/1d korrekt geblieben waeren -
genau der Fehlertyp, der bei den Dukascopy-Daten erst im Kreuzvergleich
auffiel und an den Kursen selbst nicht zu erkennen war.

Kerzen kommen ausschliesslich aus ``ClaudeBridge.cs`` ueber den
HTTP-Empfaenger. Das bleibt der einzige Schreibweg in den Kerzenspeicher.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.request

log = logging.getLogger("ntbridge.tcp_proxy")

NT8_HOST = "127.0.0.1"
NT8_PORT = 39473

ORDERS_URL = "http://127.0.0.1:8790/api/orders/pending"
FILLS_URL = "http://127.0.0.1:8790/api/orders/fill"
UPDATES_URL = "http://127.0.0.1:8790/api/orders/update"
MODIFIES_URL = "http://127.0.0.1:8790/api/orders/modify_pending"

# Wie das AddOn die Richtung liest: side == "SELL" -> SellShort, sonst Buy.
# Es gibt dort keinen dritten Zweig, deshalb muss hier eindeutig abgebildet
# werden. Die frueher benutzte Kurzform
#     "LONG" wenn "LONG" in richtung, sonst "SELL"
# machte aus jedem "BUY" ein "SELL" - der autonome Bot schickte "BUY"/"SELL"
# und drehte damit jede Long-Idee in einen Short. Die Oberflaeche schickt
# zufaellig "LONG"/"SHORT" und war nicht betroffen; der Fehler war also nur
# auf einem der beiden Wege sichtbar.
_LONG = {"LONG", "BUY", "BUYTOCOVER"}
_SHORT = {"SHORT", "SELL", "SELLSHORT"}


def richtung_fuer_nt8(wert: object) -> str | None:
    """"LONG"/"SELL" fuer das AddOn - oder None, wenn unlesbar.

    Lieber gar keine Order als eine in die falsche Richtung.
    """
    text = str(wert or "").strip().upper()
    if text in _LONG:
        return "LONG"
    if text in _SHORT:
        return "SELL"
    return None


def _sende(sock: socket.socket, nachricht: dict) -> None:
    try:
        sock.sendall((json.dumps(nachricht) + "\n").encode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - der Faden darf nicht sterben
        log.error("Senden an NT8 fehlgeschlagen: %s", exc)


def _hole_json(url: str):
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as antwort:
            return json.loads(antwort.read().decode("utf-8"))
    except Exception:
        return []


def _melde(url: str, nutzlast: dict) -> None:
    try:
        anfrage = urllib.request.Request(
            url,
            data=json.dumps(nutzlast).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(anfrage, timeout=5):
            pass
    except Exception as exc:  # noqa: BLE001
        log.error("POST %s fehlgeschlagen: %s", url, exc)


def _order_schleife(sock: socket.socket, stopp: threading.Event) -> None:
    log.info("Order-Abholung gestartet")
    while not stopp.is_set():
        for order in _hole_json(ORDERS_URL) or []:
            richtung = richtung_fuer_nt8(order.get("direction"))
            if richtung is None:
                # Nicht raten. Die Order verfaellt hier und wird protokolliert.
                log.error(
                    "Order %s ohne lesbare Richtung (%r) - nicht gesendet",
                    order.get("order_id"),
                    order.get("direction"),
                )
                continue

            art = str(order.get("order_type") or "MARKET").upper()
            if "LIMIT" in art:
                art = "LIMIT"
            elif "STOP" in art:
                art = "STOP"
            else:
                art = "MARKET"

            nachricht = {
                "type": "order_submit",
                "order_key": str(order.get("order_id")),
                "account": order.get("account_name", "Sim101"),
                "symbol": order.get("symbol", "MNQ"),
                "side": richtung,
                "quantity": int(order.get("quantity", 1)),
                "kind": art,
                "limit_price": float(order.get("limit_price") or 0),
                "stop_price": float(order.get("stop_price") or 0),
                "stop_loss": float(order.get("stop_loss_price") or 0),
                "take_profit": float(order.get("take_profit_price") or 0),
            }
            log.info("Order an NT8: %s", nachricht)
            _sende(sock, nachricht)

        for aenderung in _hole_json(MODIFIES_URL) or []:
            _sende(
                sock,
                {
                    "type": "order_modify",
                    "order_key": str(aenderung.get("order_id")),
                    "limit_price": float(aenderung.get("limit_price") or 0),
                    "stop_price": float(aenderung.get("stop_price") or 0),
                },
            )

        stopp.wait(0.5)


def main() -> None:
    while True:
        stopp = threading.Event()
        try:
            log.info("Verbinde zu NT8 %s:%s", NT8_HOST, NT8_PORT)
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((NT8_HOST, NT8_PORT))
                log.info("Verbunden.")

                threading.Thread(
                    target=_order_schleife, args=(sock, stopp), daemon=True
                ).start()

                puffer = ""
                while True:
                    rohdaten = sock.recv(4096)
                    if not rohdaten:
                        break
                    puffer += rohdaten.decode("utf-8", errors="replace")
                    while "\n" in puffer:
                        zeile, puffer = puffer.split("\n", 1)
                        if not zeile.strip():
                            continue
                        try:
                            nachricht = json.loads(zeile)
                        except Exception as exc:  # noqa: BLE001
                            log.error("Nachricht unlesbar: %s", exc)
                            continue

                        art_nachricht = nachricht.get("type")
                        if art_nachricht == "execution":
                            _melde(FILLS_URL, nachricht)
                        elif art_nachricht == "order_update":
                            # Der Lebenslauf ist der einzige Weg, eine
                            # Ablehnung ueberhaupt zu bemerken: eine Order,
                            # die die Boerse nicht annimmt, meldet sich sonst
                            # nirgends.
                            _melde(UPDATES_URL, nachricht)
                        # "tick" und "bar" werden bewusst verworfen - siehe
                        # Modul-Docstring.
        except ConnectionRefusedError:
            log.warning("Keine Verbindung (AddOn nicht geladen?) - erneut in 5s")
        except Exception as exc:  # noqa: BLE001
            log.error("Socket-Fehler: %s", exc)
        finally:
            stopp.set()
        time.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
