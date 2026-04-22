from dataclasses import dataclass
from typing import Optional


@dataclass
class ElliottDecision:
    signal: str
    reason: str
    confidence: str = "low"
    bias: str = "neutral"
    entry_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
