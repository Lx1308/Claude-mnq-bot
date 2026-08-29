import time
import subprocess
import sqlite3
import urllib.request
import json
import datetime
import os
import sys

def get_latest_idea():
    try:
        conn = sqlite3.connect('data/ideas.sqlite3')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM ideen ORDER BY erstellt_utc DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def get_latest_price():
    try:
        conn = sqlite3.connect('data/ntbridge.sqlite3')
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT close FROM bars WHERE instrument = 'MNQ' ORDER BY ts_utc DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return row['close'] if row else None
    except Exception:
        return None

def determine_order_kind(richtung, entry, current_price):
    if richtung == 'long':
        if current_price < entry:
            return "STOP", 0.0, entry
        else:
            return "LIMIT", entry, 0.0
    else:
        if current_price > entry:
            return "STOP", 0.0, entry
        else:
            return "LIMIT", entry, 0.0

def main():
    print("Starte autonomen Live-Bot fuer NinjaTrader...")
    last_processed = None
    
    latest = get_latest_idea()
    if latest:
        last_processed = latest['erstellt_utc']
        print(f"Letzte bekannte Idee vom: {last_processed}")

    while True:
        print(f"[{datetime.datetime.now().isoformat()}] Fuehre Analyse (python -m ideas) aus...")
        subprocess.run([sys.executable, "-m", "ideas", "--symbol", "MNQ"], capture_output=True)
        
        latest = get_latest_idea()
        if latest and latest['erstellt_utc'] != last_processed:
            print(f"NEUE IDEE GEFUNDEN: {latest['setup']} - {latest['richtung']}")
            last_processed = latest['erstellt_utc']
            
            curr_price = get_latest_price()
            if not curr_price:
                print("Fehler: Konnte aktuellen Preis nicht ermitteln.")
                continue

            kind, limit_p, stop_p = determine_order_kind(latest['richtung'], latest['entry'], curr_price)
            print(f"Erstelle Order: {kind} an {latest['entry']} (Aktuell: {curr_price})")

            order_payload = {
                "symbol": latest['instrument'],
                "side": "BUY" if latest['richtung'] == 'long' else "SELL",
                "qty": 1,
                "price": limit_p,
                "stop_price": stop_p,
                "stop_loss": latest['stop'],
                "take_profit": latest['ziel'],
                "kind": kind
            }
            try:
                data = json.dumps(order_payload).encode('utf-8')
                req = urllib.request.Request("http://127.0.0.1:8790/api/order/submit", data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                    resp_text = response.read().decode('utf-8')
                    print(f"Order an NinjaTrader gesendet: {response.getcode()} - {resp_text}")
            except Exception as e:
                print(f"Fehler beim Senden der Order: {e}")
                
        now = datetime.datetime.now()
        seconds_to_next_minute = 60 - now.second
        time.sleep(seconds_to_next_minute + 2)

if __name__ == '__main__':
    main()
