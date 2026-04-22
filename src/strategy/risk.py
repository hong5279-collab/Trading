from typing import Optional, Tuple

from src.models import ElliottDecision


def qty_from_usd(usd_amount: float, price: float) -> int:
    if price <= 0:
        return 0
    return int(usd_amount // price)


def evaluate_exit(
    price: float,
    position_qty: float,
    position_avg: Optional[float],
    active_plan: Optional[ElliottDecision],
    take_profit_pct: float,
    stop_loss_pct: float,
) -> Tuple[Optional[str], Optional[str], Optional[float], Optional[float], Optional[float], Optional[float]]:
    tp1_price = None
    tp2_price = None
    sl_price = None
    active_stop = None

    if position_qty > 0:
        if active_plan is not None:
            active_stop = active_plan.stop_loss or active_plan.invalidation_price
            tp1_price = active_plan.take_profit_1
            tp2_price = active_plan.take_profit_2
        elif position_avg:
            sl_price = position_avg * (1 - stop_loss_pct)
            tp1_price = position_avg * (1 + take_profit_pct)

        effective_stop = active_stop if active_stop is not None else sl_price
        effective_tp = tp2_price if tp2_price is not None else tp1_price
        if effective_tp is not None and price >= effective_tp:
            return "SELL", "take-profit hit", tp1_price, tp2_price, sl_price, active_stop
        if effective_stop is not None and price <= effective_stop:
            return "SELL", "stop-loss hit", tp1_price, tp2_price, sl_price, active_stop

    return None, None, tp1_price, tp2_price, sl_price, active_stop
