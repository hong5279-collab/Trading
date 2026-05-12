from typing import Any, List

from src.models import TradeDecision


def _sma(values: List[float], window: int) -> float:
    if len(values) < window:
        return float(values[-1])
    return float(sum(values[-window:]) / window)


def _atr(highs: List[float], lows: List[float], closes: List[float], window: int) -> float:
    if len(highs) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(highs)):
        prev_close = closes[i - 1]
        high = highs[i]
        low = lows[i]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))

    if not true_ranges:
        return 0.0
    if len(true_ranges) < window:
        return float(sum(true_ranges) / len(true_ranges))
    return float(sum(true_ranges[-window:]) / window)


def trend_momentum_decision(settings: Any, highs: List[float], lows: List[float], closes: List[float]) -> TradeDecision:
    lookback_need = max(
        settings.trend_slow_ma,
        settings.trend_breakout_lookback + 1,
        settings.trend_momentum_lookback + 1,
        settings.trend_atr_window + 1,
    )
    if len(closes) < lookback_need:
        return TradeDecision(
            signal="HOLD",
            reason=f"not enough candles for trend strategy (need {lookback_need}, got {len(closes)})",
            strategy_name="trend_momentum",
        )

    last_close = float(closes[-1])
    fast_ma = _sma(closes, settings.trend_fast_ma)
    slow_ma = _sma(closes, settings.trend_slow_ma)
    breakout_level = float(max(highs[-settings.trend_breakout_lookback - 1 : -1]))
    momentum_base = float(closes[-settings.trend_momentum_lookback - 1])
    momentum = (last_close / max(momentum_base, 1e-9)) - 1.0
    atr = _atr(highs, lows, closes, settings.trend_atr_window)
    atr_pct = atr / max(last_close, 1e-9)
    recent_low = float(min(lows[-settings.trend_breakout_lookback :]))

    failures = []
    if fast_ma <= slow_ma:
        failures.append("fast MA is not above slow MA")
    if last_close <= slow_ma:
        failures.append("price is below slow MA trend filter")
    if momentum < settings.trend_min_momentum_pct:
        failures.append("momentum is below minimum threshold")
    if atr_pct < settings.trend_min_atr_pct:
        failures.append("volatility is too low")
    if last_close < breakout_level:
        failures.append("breakout level not cleared")

    if failures:
        bias = "bearish" if last_close < slow_ma and fast_ma < slow_ma else "neutral"
        return TradeDecision(
            signal="HOLD",
            reason="trend setup not ready: " + ", ".join(failures),
            confidence="low",
            bias=bias,
            strategy_name="trend_momentum",
        )

    risk_per_share = max(settings.trend_atr_stop_mult * atr, last_close - recent_low)
    if risk_per_share <= 0:
        return TradeDecision(
            signal="HOLD",
            reason="trend setup invalid: non-positive risk distance",
            strategy_name="trend_momentum",
        )

    stop_loss = last_close - risk_per_share
    tp1 = last_close + (settings.trend_tp1_r * risk_per_share)
    tp2 = last_close + (settings.trend_tp2_r * risk_per_share)
    confidence = "high" if momentum >= max(settings.trend_min_momentum_pct * 2.0, 0.01) else "medium"

    return TradeDecision(
        signal="BUY",
        reason="trend breakout with momentum confirmation",
        confidence=confidence,
        bias="bullish",
        strategy_name="trend_momentum",
        entry_price=breakout_level,
        invalidation_price=recent_low,
        stop_loss=stop_loss,
        take_profit_1=tp1,
        take_profit_2=tp2,
        risk_reward_1=settings.trend_tp1_r,
        risk_reward_2=settings.trend_tp2_r,
    )
