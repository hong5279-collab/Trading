from typing import Any, List, Optional, Tuple

from src.models import ElliottDecision


def _sma(values: List[float], window: int) -> float:
    if len(values) < window:
        return float(values[-1])
    return float(sum(values[-window:]) / window)


def swing_points(highs: List[float], lows: List[float], window: int):
    pivots = []
    for i in range(window, len(highs) - window):
        hi = highs[i]
        lo = lows[i]
        is_high = hi >= max(highs[i - window : i + window + 1])
        is_low = lo <= min(lows[i - window : i + window + 1])
        if is_high and is_low:
            continue
        if is_high:
            pivots.append((i, hi, "H"))
        elif is_low:
            pivots.append((i, lo, "L"))

    if not pivots:
        return pivots

    compressed = [pivots[0]]
    for p in pivots[1:]:
        _, price, ptype = p
        last_i, last_price, last_type = compressed[-1]
        if ptype != last_type:
            compressed.append(p)
            continue
        if (ptype == "H" and price > last_price) or (ptype == "L" and price < last_price):
            compressed[-1] = p
        else:
            compressed[-1] = (last_i, last_price, last_type)
    return compressed


def _bullish_decision_from_prices(settings: Any, prices: List[float], last_close: float, trend: float) -> Optional[ElliottDecision]:
    l1, h1, l2, h3, l4 = prices
    wave1 = h1 - l1
    wave2 = h1 - l2
    wave3 = h3 - l2
    wave4 = h3 - l4
    wave1_pct = wave1 / max(l1, 1e-9)
    wave2_retrace = wave2 / max(wave1, 1e-9)
    wave4_retrace = wave4 / max(wave3, 1e-9)

    # Core Elliott-like impulse constraints for long setups.
    if not (
        l1 < l2 < l4
        and h1 < h3
        and wave1 > 0
        and wave3 > 0
        and wave1_pct >= settings.min_wave_pct
        and settings.wave2_min_retrace <= wave2_retrace <= settings.wave2_max_retrace
        and settings.wave4_min_retrace <= wave4_retrace <= settings.wave4_max_retrace
        and wave3 >= wave1
        and l4 > h1
        and last_close > trend
    ):
        return None

    buffered_stop = l4 * (1 - settings.ew_sl_buffer_pct)
    return ElliottDecision(
        signal="BUY",
        reason="bullish Elliott setup (wave 4 pullback complete)",
        confidence="high",
        bias="bullish",
        entry_price=h3,
        invalidation_price=l4,
        stop_loss=buffered_stop,
        take_profit_1=l4 + (settings.ew_tp1_wave_mult * wave1),
        take_profit_2=l4 + (settings.ew_tp2_wave_mult * wave1),
    )


def _bearish_decision_from_prices(settings: Any, prices: List[float], last_close: float, trend: float) -> Optional[ElliottDecision]:
    h1, l1, h2, l3, h4 = prices
    down1 = h1 - l1
    up2 = h2 - l1
    down3 = h2 - l3
    up4 = h4 - l3
    down1_pct = down1 / max(h1, 1e-9)
    up2_retrace = up2 / max(down1, 1e-9)
    up4_retrace = up4 / max(down3, 1e-9)

    if not (
        h1 > h2 > h4
        and l1 > l3
        and down1 > 0
        and down3 > 0
        and down1_pct >= settings.min_wave_pct
        and settings.wave2_min_retrace <= up2_retrace <= settings.wave2_max_retrace
        and settings.wave4_min_retrace <= up4_retrace <= settings.wave4_max_retrace
        and down3 >= down1
        and h4 < l1
        and last_close < trend
    ):
        return None

    return ElliottDecision(
        signal="SELL",
        reason="bearish Elliott setup",
        confidence="high",
        bias="bearish",
        entry_price=l3,
        invalidation_price=h4,
        stop_loss=h4,
        take_profit_1=h4 - down1,
        take_profit_2=h4 - (1.618 * down1),
    )


def elliott_decision(settings: Any, highs: List[float], lows: List[float], closes: List[float]) -> ElliottDecision:
    pivots = swing_points(highs, lows, settings.swing_window)
    if len(pivots) < 5:
        return ElliottDecision(signal="HOLD", reason="not enough swing points")

    trend = _sma(closes, settings.trend_ma)
    last_close = closes[-1]
    # Scan all recent 5-pivot windows (newest first), not just the very last one.
    for start in range(len(pivots) - 5, -1, -1):
        window = pivots[start : start + 5]
        pattern = "".join(p[2] for p in window)
        prices = [p[1] for p in window]

        if pattern == "LHLHL":
            decision = _bullish_decision_from_prices(settings, prices, last_close, trend)
            if decision is not None:
                return decision

        if pattern == "HLHLH":
            decision = _bearish_decision_from_prices(settings, prices, last_close, trend)
            if decision is not None:
                return decision

    last5_pattern = "".join(p[2] for p in pivots[-5:])
    return ElliottDecision(signal="HOLD", reason=f"no valid Elliott setup (last pattern={last5_pattern})")
