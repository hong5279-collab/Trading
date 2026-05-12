from dataclasses import dataclass
from typing import Optional


@dataclass
class TradeDecision:
    signal: str
    reason: str
    confidence: str = "low"
    bias: str = "neutral"
    strategy_name: str = "unknown"
    entry_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward_1: Optional[float] = None
    risk_reward_2: Optional[float] = None


ElliottDecision = TradeDecision
