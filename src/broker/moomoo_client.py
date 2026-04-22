import socket
from typing import Optional, Tuple

import moomoo as ft

from src.config import Settings


def _check_ret(op_name: str, *result):
    if len(result) < 2:
        raise RuntimeError(f"{op_name} failed: unexpected return shape={result}")
    ret = result[0]
    data = result[1]
    if ret != ft.RET_OK:
        raise RuntimeError(f"{op_name} failed: {data}")
    return data


def _can_connect_tcp(host: str, port: int, timeout_sec: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def _opend_troubleshoot_message(host: str, port: int) -> str:
    return (
        f"Cannot connect to moomoo OpenD at {host}:{port} (ECONNREFUSED).\n"
        "Fix checklist:\n"
        "1) Open moomoo/Futu OpenD and log in.\n"
        "2) In OpenD settings, enable API and confirm the listening port.\n"
        "3) Update .env MOOMOO_HOST/MOOMOO_PORT to match OpenD.\n"
        "4) If OpenD runs on another machine, use that machine's LAN IP, not 127.0.0.1.\n"
        "5) Allow OpenD through firewall."
    )


class MoomooGateway:
    def __init__(self, settings: Settings):
        self.s = settings
        self.quote_ctx: Optional[ft.OpenQuoteContext] = None
        self.trd_ctx: Optional[ft.OpenSecTradeContext] = None
        self.acc_id: Optional[int] = None

    def connect(self):
        print(f"[INFO] Connecting to OpenD at {self.s.host}:{self.s.port} ...")
        if not _can_connect_tcp(self.s.host, self.s.port):
            raise RuntimeError(_opend_troubleshoot_message(self.s.host, self.s.port))

        try:
            self.quote_ctx = ft.OpenQuoteContext(host=self.s.host, port=self.s.port)
            self.trd_ctx = ft.OpenSecTradeContext(
                filter_trdmarket=self.s.market,
                host=self.s.host,
                port=self.s.port,
                security_firm=self.s.security_firm,
            )
        except Exception as exc:
            msg = str(exc)
            if "ECONNREFUSED" in msg or "Connect fail" in msg:
                raise RuntimeError(_opend_troubleshoot_message(self.s.host, self.s.port)) from exc
            raise

        acc_df = _check_ret("get_acc_list", *self.trd_ctx.get_acc_list())
        candidates = acc_df[acc_df["trd_env"] == self.s.trd_env]
        if candidates.empty:
            raise RuntimeError(f"No account found for env={self.s.trd_env}")

        if self.s.trd_env == ft.TrdEnv.SIMULATE and "sim_acc_type" in candidates.columns:
            stock_sim = candidates[candidates["sim_acc_type"].astype(str) == "STOCK"]
            if not stock_sim.empty:
                candidates = stock_sim

        self.acc_id = int(candidates.iloc[0]["acc_id"])
        print(f"[INFO] Using account acc_id={self.acc_id}, env={self.s.trd_env}")

        if self.s.trd_env == ft.TrdEnv.REAL:
            if not self.s.trade_password:
                raise RuntimeError("TRADE_PASSWORD is required in REAL mode")
            _check_ret("unlock_trade", *self.trd_ctx.unlock_trade(self.s.trade_password))
            print("[INFO] Trade unlocked for REAL environment")

    def close(self):
        if self.trd_ctx:
            self.trd_ctx.close()
            self.trd_ctx = None
        if self.quote_ctx:
            self.quote_ctx.close()
            self.quote_ctx = None

    def get_recent_ohlc(self):
        need = self.s.ew_lookback + 5
        k_df = _check_ret(
            "request_history_kline",
            *self.quote_ctx.request_history_kline(
                self.s.symbol,
                ktype=self.s.ktype,
                max_count=need,
            ),
        )
        if len(k_df) < need:
            raise RuntimeError(f"Not enough candles: need={need}, got={len(k_df)}")
        highs = [float(x) for x in k_df["high"].tolist()]
        lows = [float(x) for x in k_df["low"].tolist()]
        closes = [float(x) for x in k_df["close"].tolist()]
        return highs, lows, closes

    def latest_price(self) -> float:
        snap = _check_ret("get_market_snapshot", *self.quote_ctx.get_market_snapshot([self.s.symbol]))
        if snap.empty:
            raise RuntimeError(f"No market snapshot for {self.s.symbol}")
        return float(snap.iloc[0]["last_price"])

    def current_position(self) -> Tuple[float, Optional[float]]:
        pos = _check_ret(
            "position_list_query",
            *self.trd_ctx.position_list_query(
                code=self.s.symbol,
                trd_env=self.s.trd_env,
                acc_id=self.acc_id,
            ),
        )
        if pos.empty:
            return 0.0, None
        qty = float(pos["qty"].sum())
        avg_price = None
        for col in ["cost_price", "nominal_price"]:
            if col in pos.columns:
                try:
                    val = float(pos.iloc[0][col])
                    if val > 0:
                        avg_price = val
                        break
                except Exception:
                    pass
        return qty, avg_price

    def active_orders_summary(self) -> Tuple[bool, str]:
        orders = _check_ret(
            "order_list_query",
            *self.trd_ctx.order_list_query(
                code=self.s.symbol,
                trd_env=self.s.trd_env,
                acc_id=self.acc_id,
            ),
        )
        if orders.empty:
            return False, "none"
        if "order_status" not in orders.columns:
            return not orders.empty, "unknown-status-column"

        inactive_keywords = ("filled", "cancel", "failed", "disable", "deleted", "invalid")
        active_mask = []
        for val in orders["order_status"].astype(str).tolist():
            s = val.strip().lower()
            is_inactive = any(k in s for k in inactive_keywords)
            active_mask.append(not is_inactive)

        active_orders = orders[active_mask]
        if active_orders.empty:
            return False, "no-active-orders"
        statuses = ",".join(sorted(set(active_orders["order_status"].astype(str).tolist())))
        return True, statuses

    def place_limit_order(self, side: str, qty: int, price: float):
        side_enum = ft.TrdSide.BUY if side == "BUY" else ft.TrdSide.SELL
        if self.s.dry_run:
            print(f"[DRY_RUN] {side} {qty} {self.s.symbol} @ {price:.4f}")
            return

        order_df = _check_ret(
            "place_order",
            *self.trd_ctx.place_order(
                price=price,
                qty=qty,
                code=self.s.symbol,
                trd_side=side_enum,
                order_type=ft.OrderType.NORMAL,
                trd_env=self.s.trd_env,
                acc_id=self.acc_id,
                remark="auto-elliott-bot",
                time_in_force=ft.TimeInForce.DAY,
            ),
        )
        order_id = order_df.iloc[0]["order_id"] if not order_df.empty else "N/A"
        print(f"[ORDER] side={side} qty={qty} price={price:.4f} order_id={order_id}")
