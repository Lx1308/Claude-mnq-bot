import os
import sys
import sqlite3
import pandas as pd
from datetime import datetime
from backtest.engine import Backtester
from backtest.strategies.library import build_strategy
from common.config import MarketConfig, IndicatorConfig

def fetch_ntbridge_data() -> pd.DataFrame:
    db_path = "data/ntbridge.sqlite3"
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database {db_path} not found")
        
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT ts_utc as timestamp_utc, open, high, low, close, volume FROM bars ORDER BY ts_utc",
        conn,
        parse_dates=["timestamp_utc"]
    )
    conn.close()
    
    df = df.set_index("timestamp_utc").sort_index()
    return df

def run_hypothesis(hypothesis_id: str, strategy_name: str, reason: str, params: dict):
    print(f"--- Running Hypothesis {hypothesis_id} ---")
    df = fetch_ntbridge_data()
    print(f"Loaded {len(df)} bars from ntbridge.sqlite3")
    
    market_cfg = MarketConfig(tick_size=0.25, point_value=20.0)
    indicator_cfg = IndicatorConfig()
    
    tester = Backtester(market_cfg, indicator_cfg)
    print("Preparing indicators...")
    df = tester.prepare(df)
    
    strategy = build_strategy(strategy_name, **params)
    print(f"Running strategy: {strategy.name}...")
    result = tester.run(df, strategy)
    trades = result.trades
    
    pnl = sum(t.pnl for t in trades)
    win_rate = (len([t for t in trades if t.pnl > 0]) / len(trades) * 100) if trades else 0.0
    
    # Generate Protocol
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"backtest_results/protocol_{hypothesis_id}_{timestamp}.md"
    os.makedirs("backtest_results", exist_ok=True)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Research Protocol: {hypothesis_id}\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Strategy:** {strategy.name}\n")
        f.write(f"**Hypothesis / Reason:** {reason}\n")
        f.write(f"**Data:** {len(df)} bars (ntbridge.sqlite3)\n\n")
        
        f.write("## Results\n")
        f.write(f"- **Trades:** {len(trades)}\n")
        f.write(f"- **Win Rate:** {win_rate:.1f} %\n")
        f.write(f"- **Net PnL:** \\n\n")
        
        f.write("## Trades Log\n")
        if not trades:
            f.write("No trades executed.\n")
        else:
            f.write("| Entry Time | Exit Time | Direction | Size | Entry Price | Exit Price | PnL | R-Multiple | Reason |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for t in trades[:50]:
                f.write(f"| {t.entry_time} | {t.exit_time} | {'LONG' if t.direction > 0 else 'SHORT'} | {1} | {t.entry_price:.2f} | {t.exit_price:.2f} | \ |  | {t.exit_reason} |\n")
            if len(trades) > 50:
                f.write(f"\n... and {len(trades)-50} more trades.\n")
                
    print(f"Protocol written to {filename}")
    return filename

if __name__ == '__main__':
    if len(sys.argv) > 1:
        run_hypothesis("CLI_TEST", "power_hour_vwap", "Testing Power Hour Hypothesis", {"stop_loss_atr": 1.5})


