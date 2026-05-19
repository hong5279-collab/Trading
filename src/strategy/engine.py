from typing import Any, Dict, List, Optional, Tuple

from src.models import TradeDecision
from src.strategy.backtest import backtest_strategy
from src.strategy.modes import AUTO_TIEBREAKER_MODE, MANUAL_STRATEGY_MODES, run_strategy_mode


def _auto_rank(summary: Dict[str, float]) -> Tuple[float, float, float, int, int]:
    return (
        float(summary["total_return_pct"]),
        float(summary["win_rate_pct"]),
        float(summary["avg_trade_return_pct"]),
        int(summary["trades"]),
        1 if summary["strategy"] == AUTO_TIEBREAKER_MODE else 0,
    )


def _choose_auto_strategy(
    settings: Any,
    highs: List[float],
    lows: List[float],
    closes: List[float],
) -> Tuple[str, Dict[str, Dict[str, float]]]:
    summaries = {
        mode: backtest_strategy(settings, highs, lows, closes, mode)
        for mode in MANUAL_STRATEGY_MODES
    }
    selected_mode = max(MANUAL_STRATEGY_MODES, key=lambda mode: _auto_rank(summaries[mode]))
    return selected_mode, summaries


def _auto_reason_prefix(
    selected_mode: str,
    summaries: Dict[str, Dict[str, float]],
) -> str:
    alternate_mode = next(mode for mode in MANUAL_STRATEGY_MODES if mode != selected_mode)
    selected = summaries[selected_mode]
    alternate = summaries[alternate_mode]

    same_metrics = all(
        selected[key] == alternate[key]
        for key in ("total_return_pct", "win_rate_pct", "avg_trade_return_pct", "trades")
    )
    if same_metrics:
        if int(selected["trades"]) == 0:
            return (
                f"AUTO picked {selected_mode.lower()} by tiebreak "
                "(both recent backtests had no completed trades)."
            )
        return f"AUTO picked {selected_mode.lower()} by tiebreak (recent backtests were tied)."

    return (
        f"AUTO picked {selected_mode.lower()} "
        f"({float(selected['total_return_pct']):.2f}% total return, "
        f"{float(selected['win_rate_pct']):.2f}% win rate) over "
        f"{alternate_mode.lower()} "
        f"({float(alternate['total_return_pct']):.2f}%, "
        f"{float(alternate['win_rate_pct']):.2f}%)."
    )


def strategy_decision(
    settings: Any,
    highs: List[float],
    lows: List[float],
    closes: List[float],
    strategy_mode: Optional[str] = None,
) -> TradeDecision:
    mode = (strategy_mode or settings.strategy_mode).strip().upper()
    resolved_mode = mode
    auto_summaries: Optional[Dict[str, Dict[str, float]]] = None

    if mode == "AUTO":
        resolved_mode, auto_summaries = _choose_auto_strategy(settings, highs, lows, closes)

    decision = run_strategy_mode(settings, highs, lows, closes, resolved_mode)
    if mode == "AUTO" and auto_summaries is not None:
        decision.reason = f"{_auto_reason_prefix(resolved_mode, auto_summaries)} {decision.reason}"
        decision.strategy_name = f"auto->{resolved_mode.lower()}"
    else:
        decision.strategy_name = resolved_mode.lower()
    return decision
