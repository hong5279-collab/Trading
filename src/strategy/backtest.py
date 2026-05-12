from typing import Any, Dict, List, Optional, Union

from src.models import TradeDecision
from src.strategy.engine import strategy_decision


def _max_drawdown(equity_curve: List[float]) -> float:
    peak = 1.0
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return max_dd


def backtest_strategy(
    settings: Any,
    highs: List[float],
    lows: List[float],
    closes: List[float],
    strategy_mode: str,
) -> Dict[str, Union[float, int, str]]:
    if len(closes) < 40:
        return {
            "strategy": strategy_mode,
            "trades": 0,
            "win_rate_pct": 0.0,
            "avg_trade_return_pct": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    equity = 1.0
    equity_curve = [equity]
    trade_returns: List[float] = []
    position: Optional[TradeDecision] = None
    entry_price: Optional[float] = None

    for idx in range(30, len(closes)):
        hi = float(highs[idx])
        lo = float(lows[idx])
        close = float(closes[idx])

        if position is not None and entry_price is not None:
            exit_price = None
            stop_loss = position.stop_loss
            tp1 = position.take_profit_1
            tp2 = position.take_profit_2

            if stop_loss is not None and lo <= stop_loss:
                exit_price = stop_loss
            elif tp2 is not None and hi >= tp2:
                exit_price = tp2
            elif tp1 is not None and hi >= tp1:
                exit_price = tp1

            if exit_price is not None:
                trade_return = (exit_price / entry_price) - 1.0
                trade_returns.append(trade_return)
                equity *= 1.0 + trade_return
                equity_curve.append(equity)
                position = None
                entry_price = None
                continue

        decision = strategy_decision(
            settings,
            highs[: idx + 1],
            lows[: idx + 1],
            closes[: idx + 1],
            strategy_mode=strategy_mode,
        )
        if position is None and decision.signal == "BUY" and decision.entry_price is not None and close >= decision.entry_price:
            position = decision
            entry_price = close

    if position is not None and entry_price is not None:
        final_return = (float(closes[-1]) / entry_price) - 1.0
        trade_returns.append(final_return)
        equity *= 1.0 + final_return
        equity_curve.append(equity)

    wins = sum(1 for value in trade_returns if value > 0)
    trades = len(trade_returns)
    win_rate = (wins / trades) * 100.0 if trades else 0.0
    avg_trade_return = (sum(trade_returns) / trades) * 100.0 if trades else 0.0

    return {
        "strategy": strategy_mode,
        "trades": trades,
        "win_rate_pct": round(win_rate, 2),
        "avg_trade_return_pct": round(avg_trade_return, 2),
        "total_return_pct": round((equity - 1.0) * 100.0, 2),
        "max_drawdown_pct": round(_max_drawdown(equity_curve) * 100.0, 2),
    }
