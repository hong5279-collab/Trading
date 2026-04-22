import time
from datetime import date
from typing import Optional

from src.broker.moomoo_client import MoomooGateway
from src.config import Settings
from src.models import ElliottDecision
from src.strategy.elliott import elliott_decision
from src.strategy.risk import evaluate_exit, qty_from_usd


class TraderBot:
    def __init__(self, settings: Settings):
        self.s = settings
        self.gateway = MoomooGateway(settings)
        self.trade_day = date.today()
        self.trade_count_today = 0
        self.active_plan: Optional[ElliottDecision] = None

    def connect(self):
        self.gateway.connect()

    def close(self):
        self.gateway.close()

    def _reset_trade_day_if_needed(self):
        today = date.today()
        if today != self.trade_day:
            self.trade_day = today
            self.trade_count_today = 0

    def run_forever(self):
        print("[INFO] bot started")
        print(
            f"[INFO] symbol={self.s.symbol}, env={self.s.trd_env}, "
            f"dry_run={self.s.dry_run}, poll={self.s.poll_seconds}s, "
            f"buy_usd={self.s.buy_amount_usd}, long_only=True, "
            f"tp={self.s.take_profit_pct:.2%}, sl={self.s.stop_loss_pct:.2%}, "
            f"max_pos_usd={self.s.max_position_usd}"
        )

        while True:
            self._reset_trade_day_if_needed()
            try:
                highs, lows, closes = self.gateway.get_recent_ohlc()
                decision = elliott_decision(self.s, highs, lows, closes)
                signal = decision.signal
                signal_reason = decision.reason

                price = self.gateway.latest_price()
                position_qty, position_avg = self.gateway.current_position()
                position_value = position_qty * price
                has_open, open_statuses = self.gateway.active_orders_summary()

                if position_qty <= 0:
                    self.active_plan = None

                exit_signal, exit_reason, tp1_price, tp2_price, sl_price, active_stop = evaluate_exit(
                    price=price,
                    position_qty=position_qty,
                    position_avg=position_avg,
                    active_plan=self.active_plan,
                    take_profit_pct=self.s.take_profit_pct,
                    stop_loss_pct=self.s.stop_loss_pct,
                )
                if exit_signal is not None:
                    signal = exit_signal
                    signal_reason = exit_reason or signal_reason
                elif signal == "SELL":
                    # Long-only mode: ignore bearish short-entry signals from the strategy.
                    signal = "HOLD"
                    signal_reason = "bearish setup ignored (long-only mode)"

                tick_msg = (
                    f"[TICK] signal={signal} price={price:.4f} "
                    f"position={position_qty} open_orders={has_open} "
                    f"position_value={position_value:.2f} trades_today={self.trade_count_today} "
                    f"reason={signal_reason} confidence={decision.confidence} bias={decision.bias}"
                )
                if has_open:
                    tick_msg += f" open_statuses={open_statuses}"
                if decision.entry_price is not None:
                    tick_msg += f" entry={decision.entry_price:.4f}"
                if decision.invalidation_price is not None:
                    tick_msg += f" invalid={decision.invalidation_price:.4f}"
                if tp1_price is not None:
                    tick_msg += f" tp1={tp1_price:.4f}"
                if tp2_price is not None:
                    tick_msg += f" tp2={tp2_price:.4f}"
                if active_stop is not None:
                    tick_msg += f" sl={active_stop:.4f}"
                elif sl_price is not None:
                    tick_msg += f" sl={sl_price:.4f}"
                print(tick_msg)

                if has_open:
                    print("[INFO] Skip new order because active order is still pending")
                    time.sleep(self.s.poll_seconds)
                    continue
                if self.trade_count_today >= self.s.max_daily_trades:
                    print("[RISK] daily trade limit reached")
                    time.sleep(self.s.poll_seconds)
                    continue

                if signal == "BUY":
                    if decision.entry_price is not None and price < decision.entry_price:
                        print("[INFO] BUY setup found but entry trigger not broken yet, waiting")
                        time.sleep(self.s.poll_seconds)
                        continue

                    buy_qty = qty_from_usd(self.s.buy_amount_usd, price)
                    if buy_qty <= 0:
                        print("[RISK] BUY_AMOUNT_USD too small for current price")
                        time.sleep(self.s.poll_seconds)
                        continue
                    if position_qty + buy_qty > self.s.max_position_qty:
                        print("[RISK] max position limit reached, skip BUY")
                    elif (position_value + (buy_qty * price)) > self.s.max_position_usd:
                        print("[RISK] max USD position limit reached, skip BUY")
                    else:
                        self.gateway.place_limit_order("BUY", buy_qty, price)
                        self.active_plan = decision
                        self.trade_count_today += 1

                elif signal == "SELL":
                    if signal_reason in {"take-profit hit", "stop-loss hit"}:
                        sell_qty = int(position_qty)
                    else:
                        print(f"[INFO] Ignore SELL signal in long-only mode: reason={signal_reason}")
                        time.sleep(self.s.poll_seconds)
                        continue
                    if sell_qty <= 0:
                        print("[RISK] no position to sell")
                    else:
                        self.gateway.place_limit_order("SELL", sell_qty, price)
                        if sell_qty >= int(position_qty):
                            self.active_plan = None
                        self.trade_count_today += 1

            except Exception as exc:
                print(f"[ERROR] {exc}")

            time.sleep(self.s.poll_seconds)
