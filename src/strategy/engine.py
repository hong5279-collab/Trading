from typing import Any, List, Optional

from src.models import TradeDecision
from src.strategy.elliott import elliott_decision
from src.strategy.trend_momentum import trend_momentum_decision


def strategy_decision(
    settings: Any,
    highs: List[float],
    lows: List[float],
    closes: List[float],
    strategy_mode: Optional[str] = None,
) -> TradeDecision:
    mode = (strategy_mode or settings.strategy_mode).strip().upper()
    if mode == "ELLIOTT":
        decision = elliott_decision(settings, highs, lows, closes)
    elif mode == "TREND_MOMENTUM":
        decision = trend_momentum_decision(settings, highs, lows, closes)
    else:
        raise ValueError(f"Unsupported strategy mode: {mode}")

    decision.strategy_name = mode.lower()
    return decision
