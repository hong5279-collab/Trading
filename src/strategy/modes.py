from typing import Any, List

from src.models import TradeDecision
from src.strategy.elliott import elliott_decision
from src.strategy.trend_momentum import trend_momentum_decision


MANUAL_STRATEGY_MODES = ("ELLIOTT", "TREND_MOMENTUM")
SUPPORTED_STRATEGY_MODES = MANUAL_STRATEGY_MODES + ("AUTO",)
AUTO_TIEBREAKER_MODE = "TREND_MOMENTUM"


def run_strategy_mode(
    settings: Any,
    highs: List[float],
    lows: List[float],
    closes: List[float],
    strategy_mode: str,
) -> TradeDecision:
    mode = strategy_mode.strip().upper()
    if mode == "ELLIOTT":
        return elliott_decision(settings, highs, lows, closes)
    if mode == "TREND_MOMENTUM":
        return trend_momentum_decision(settings, highs, lows, closes)
    raise ValueError(f"Unsupported strategy mode: {mode}")
