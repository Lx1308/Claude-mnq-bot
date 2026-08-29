import sqlite3
import pandas as pd
from datetime import datetime

# Helper function
def get_df_for_overlays(symbol, timeframe, limit=300):
    conn = sqlite3.connect('data/ntbridge.sqlite3')
    query = "SELECT ts_utc as timestamp_utc, open, high, low, close, volume FROM bars WHERE instrument=? AND timeframe=? ORDER BY ts_utc DESC LIMIT ?"
    df = pd.read_sql_query(query, conn, params=(symbol, timeframe, limit))
    conn.close()
    if df.empty:
        return None
    df = df.iloc[::-1].reset_index(drop=True)
    df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'])
    df = df.set_index('timestamp_utc')
    return df


