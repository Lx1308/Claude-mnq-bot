import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path('data/risk.sqlite3')

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS risk_state (
                id INTEGER PRIMARY KEY,
                date TEXT,
                realized_pnl REAL,
                peak_pnl REAL,
                drawdown_hit BOOLEAN
            )
        ''')
        # Seed initial state if empty
        if not conn.execute("SELECT 1 FROM risk_state WHERE date = ?", (datetime.date.today().isoformat(),)).fetchone():
            conn.execute("INSERT INTO risk_state (date, realized_pnl, peak_pnl, drawdown_hit) VALUES (?, 0, 0, 0)", 
                         (datetime.date.today().isoformat(),))

def get_state():
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM risk_state ORDER BY id DESC LIMIT 1").fetchone())

def update_pnl(realized_trade_pnl: float):
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        state = get_state()
        new_pnl = state['realized_pnl'] + realized_trade_pnl
        new_peak = max(state['peak_pnl'], new_pnl)
        
        # Max Trailing Drawdown e.g. 
        MAX_DD = 1500.0
        hit = 1 if (new_peak - new_pnl) >= MAX_DD else state['drawdown_hit']
        
        conn.execute("UPDATE risk_state SET realized_pnl = ?, peak_pnl = ?, drawdown_hit = ? WHERE id = ?",
                     (new_pnl, new_peak, hit, state['id']))

def check_order(symbol: str, side: str, qty: int, price: float) -> bool:
    ''' Returns True if order is allowed, False if blocked by risk limits '''
    state = get_state()
    if state['drawdown_hit']:
        print("RISK REJECT: Trailing Drawdown limit hit.")
        return False
    if qty > 2:  # Max 2 contracts
        print("RISK REJECT: Max contract limit (2) exceeded.")
        return False
    return True
