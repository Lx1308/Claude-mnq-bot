import logging
from dataclasses import dataclass
from typing import Optional, Dict

logger = logging.getLogger(__name__)

@dataclass
class Position:
    symbol: str
    qty: int
    entry_price: float
    side: str  # 'LONG' or 'SHORT'
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class RiskEngine:
    def __init__(self):
        self.max_daily_loss = 500.0  # Lucid 25k Pro
        self.current_daily_loss = 0.0
        self.max_position_size = 2  # Max 2 MNQ contracts
        self.active_positions: Dict[str, Position] = {}

    def check_order(self, symbol: str, side: str, qty: int, price: float) -> bool:
        if self.current_daily_loss <= -self.max_daily_loss:
            logger.warning(f"Order abgelehnt: Max Daily Loss ({self.max_daily_loss}) erreicht.")
            return False
            
        current_qty = self.active_positions.get(symbol, Position(symbol, 0, 0, 'LONG')).qty
        if current_qty + qty > self.max_position_size:
            logger.warning(f"Order abgelehnt: Max Position Size ({self.max_position_size}) überschritten.")
            return False
            
        return True

    def register_position(self, symbol: str, side: str, qty: int, price: float, stop_loss: Optional[float], take_profit: Optional[float]):
        self.active_positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            side=side,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        logger.info(f"Position registriert: {side} {qty} {symbol} @ {price}")

    def update_trailing_stop(self, symbol: str, new_stop: float) -> bool:
        if symbol in self.active_positions:
            pos = self.active_positions[symbol]
            pos.stop_loss = new_stop
            logger.info(f"Trailing Stop für {symbol} auf {new_stop} aktualisiert.")
            return True
        return False
        
    def close_position(self, symbol: str, exit_price: float) -> float:
        if symbol in self.active_positions:
            pos = self.active_positions.pop(symbol)
            multiplier = 2 # MNQ
            if pos.side == 'LONG':
                pnl = (exit_price - pos.entry_price) * pos.qty * multiplier
            else:
                pnl = (pos.entry_price - exit_price) * pos.qty * multiplier
                
            if pnl < 0:
                self.current_daily_loss += pnl
                
            logger.info(f"Position {symbol} geschlossen. PnL: {pnl}")
            return pnl
        return 0.0
