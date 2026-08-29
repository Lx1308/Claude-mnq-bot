import socket
import json
import threading
import time
import urllib.request
import datetime
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('TcpProxy')

NT8_HOST = '127.0.0.1'
NT8_PORT = 39473
BARS_URL = 'http://127.0.0.1:8787/bars'
ORDERS_URL = 'http://127.0.0.1:8790/api/orders/pending'
FILLS_URL = 'http://127.0.0.1:8790/api/orders/fill'
MODIFIES_URL = 'http://127.0.0.1:8790/api/orders/modify_pending'

def send_to_nt8(sock, msg_dict):
    try:
        data = json.dumps(msg_dict) + '\n'
        sock.sendall(data.encode('utf-8'))
    except Exception as e:
        log.error(f'Failed to send to NT8: {e}')

def post_to_server(url, payload):
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            pass
    except Exception as e:
        log.error(f'POST {url} failed: {e}')

def fetch_json(url):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception:
        return []

def order_polling_thread(sock):
    log.info('Started order polling thread')
    while True:
        orders = fetch_json(ORDERS_URL)
        for o in orders:
            kind_str = 'MARKET'
            ot = str(o.get('order_type', '')).upper()
            if 'LIMIT' in ot: kind_str = 'LIMIT'
            if 'STOP' in ot: kind_str = 'STOP'

            msg = {
                'type': 'order_submit',
                'order_key': str(o.get('order_id')),
                'account': o.get('account_name', 'Sim101'),
                'symbol': 'MNQ',
                'side': 'LONG' if 'LONG' in str(o.get('direction')).upper() else 'SELL',
                'quantity': int(o.get('quantity', 1)),
                'kind': kind_str,
                'limit_price': float(o.get('limit_price') or 0),
                'stop_price': float(o.get('stop_price') or 0),
                'stop_loss': float(o.get('stop_loss_price') or 0),
                'take_profit': float(o.get('take_profit_price') or 0)
            }
            log.info(f'Sending order to NT8: {msg}')
            send_to_nt8(sock, msg)
            
        modifies = fetch_json(MODIFIES_URL)
        for m in modifies:
            msg = {
                'type': 'order_modify',
                'order_key': str(m.get('order_id')),
                'limit_price': float(m.get('limit_price') or 0),
                'stop_price': float(m.get('stop_price') or 0)
            }
            log.info(f'Sending modify to NT8: {msg}')
            send_to_nt8(sock, msg)
            
        time.sleep(0.5)

current_bar = None
last_post_time = 0

def handle_tick(msg):
    global current_bar, last_post_time
    try:
        ts_ns = int(msg['ts'])
        minute_ts = (ts_ns // 60_000_000_000) * 60_000_000_000
        price = float(msg['price'])
        vol = int(msg.get('volume', msg.get('size', 0)))
        
        if current_bar is None or current_bar['ts_ns'] != minute_ts:
            current_bar = {
                'ts_ns': minute_ts,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': vol
            }
        else:
            current_bar['high'] = max(current_bar['high'], price)
            current_bar['low'] = min(current_bar['low'], price)
            current_bar['close'] = price
            current_bar['volume'] += vol
            
        now = time.time()
        if now - last_post_time >= 1.0:
            utc_str = datetime.datetime.fromtimestamp(minute_ts / 1e9, tz=datetime.timezone.utc).isoformat()
            bar_payload = {
                'bars': [{
                    'time': int(minute_ts / 1e9),
                    'timestampUtc': utc_str,
                    'open': current_bar['open'],
                    'high': current_bar['high'],
                    'low': current_bar['low'],
                    'close': current_bar['close'],
                    'volume': current_bar['volume'],
                    'vwap': None,
                    'timeframe': '1m',
                    'instrument': 'MNQ',
                    'closed': False
                }]
            }
            post_to_server(BARS_URL, bar_payload)
            last_post_time = now
            
    except Exception as e:
        log.error(f"Error handling tick: {e}")

def main():
    while True:
        try:
            log.info(f'Connecting to NT8 at {NT8_HOST}:{NT8_PORT}')
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((NT8_HOST, NT8_PORT))
                log.info('Connected.')
                
                threading.Thread(target=order_polling_thread, args=(sock,), daemon=True).start()

                send_to_nt8(sock, {'type': 'subscribe', 'symbol': 'MNQ', 'timeframe': '1m'})
                
                buffer = ''
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode('utf-8')
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line)
                            msg_type = msg.get('type')
                            
                            if msg_type == 'tick':
                                handle_tick(msg)
                            elif msg_type == 'bar':
                                pass
                            elif msg_type == 'execution':
                                post_to_server(FILLS_URL, msg)
                        except Exception as e:
                            log.error(f"Error parsing message: {e}")
                            
        except ConnectionRefusedError:
            log.warning('Connection refused, retrying in 5s...')
            time.sleep(5)
        except Exception as e:
            log.error(f'Socket error: {e}')
            time.sleep(5)

if __name__ == '__main__':
    main()
