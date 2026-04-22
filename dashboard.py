import socket
from datetime import datetime, timedelta

import moomoo as ft
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from src.config import Settings
from src.strategy.elliott import elliott_decision, swing_points


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


def _render_level(fig: go.Figure, value: float, label: str, color: str):
    fig.add_hline(
        y=value,
        line_dash="dot",
        line_color=color,
        annotation_text=f"{label}: {value:.4f}",
        annotation_position="top left",
    )


def _subtype_for_ktype(ktype: ft.KLType):
    mapping = {
        getattr(ft.KLType, "K_1M", None): getattr(ft.SubType, "K_1M", None),
        getattr(ft.KLType, "K_5M", None): getattr(ft.SubType, "K_5M", None),
        getattr(ft.KLType, "K_15M", None): getattr(ft.SubType, "K_15M", None),
        getattr(ft.KLType, "K_30M", None): getattr(ft.SubType, "K_30M", None),
        getattr(ft.KLType, "K_60M", None): getattr(ft.SubType, "K_60M", None),
        getattr(ft.KLType, "K_DAY", None): getattr(ft.SubType, "K_DAY", None),
    }
    return mapping.get(ktype)


def _normalize_candles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["time_key_raw"] = out["time_key"]
    out["time_key"] = pd.to_datetime(out["time_key"], errors="coerce")
    out = out.dropna(subset=["time_key"])
    out = out.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")
    out["open"] = out["open"].astype(float)
    out["high"] = out["high"].astype(float)
    out["low"] = out["low"].astype(float)
    out["close"] = out["close"].astype(float)
    now_utc = datetime.utcnow()
    future_cutoff = now_utc + timedelta(days=1)
    out = out[out["time_key"] <= future_cutoff]
    return out


def _fetch_best_candles(quote_ctx: ft.OpenQuoteContext, symbol: str, ktype: ft.KLType, need: int):
    history_df = _check_ret(
        "request_history_kline",
        *quote_ctx.request_history_kline(symbol, ktype=ktype, max_count=need),
    )
    history_df = _normalize_candles(history_df)
    if history_df.empty:
        raise RuntimeError("No valid history candles returned by OpenD.")

    history_last = history_df["time_key"].max()
    now_utc = datetime.utcnow().date()
    stale_days = (now_utc - history_last.date()).days

    if stale_days <= 7:
        return history_df, "history", stale_days

    try:
        sub_type = _subtype_for_ktype(ktype)
        if sub_type is not None:
            _check_ret(
                "subscribe",
                *quote_ctx.subscribe([symbol], [sub_type], subscribe_push=False),
            )
        realtime_df = _check_ret("get_cur_kline", *quote_ctx.get_cur_kline(symbol, need, ktype=ktype))
        realtime_df = _normalize_candles(realtime_df)
        if not realtime_df.empty:
            rt_last = realtime_df["time_key"].max()
            if rt_last > history_last:
                rt_stale_days = (now_utc - rt_last.date()).days
                return realtime_df, "realtime", rt_stale_days
    except Exception:
        pass

    return history_df, "history-stale", stale_days


def main():
    st.set_page_config(page_title="Elliott Strategy Chart", layout="wide")
    st.title("Elliott Strategy Visualizer")
    st.caption("See how the current strategy logic applies to a stock on the latest candles.")

    settings = Settings.from_env()

    with st.sidebar:
        st.subheader("Inputs")
        symbol = st.text_input("Symbol", value=settings.symbol).strip() or settings.symbol
        ew_lookback = st.slider("Candles (lookback)", min_value=60, max_value=1000, value=settings.ew_lookback, step=10)
        swing_window = st.slider("Swing window", min_value=1, max_value=15, value=settings.swing_window, step=1)
        trend_ma = st.slider("Trend MA", min_value=5, max_value=200, value=settings.trend_ma, step=1)
        refresh = st.button("Refresh")
        st.caption(f"Host: {settings.host}:{settings.port}")

    settings.symbol = symbol
    settings.ew_lookback = ew_lookback
    settings.swing_window = swing_window
    settings.trend_ma = trend_ma

    if not refresh:
        st.info("Click `Refresh` to fetch latest candles and re-evaluate strategy.")
        return

    if not _can_connect_tcp(settings.host, settings.port):
        st.error(f"Cannot connect to OpenD at {settings.host}:{settings.port}. Start OpenD and check `.env` host/port.")
        return

    quote_ctx = None
    try:
        quote_ctx = ft.OpenQuoteContext(host=settings.host, port=settings.port)
        need = settings.ew_lookback + 5
        k_df, feed_source, stale_days = _fetch_best_candles(quote_ctx, settings.symbol, settings.ktype, need)
        if len(k_df) < 30:
            st.error(f"Not enough candles for {settings.symbol}. Need at least 30, got {len(k_df)}.")
            return

        k_df["trend_ma"] = k_df["close"].rolling(window=settings.trend_ma, min_periods=1).mean()

        highs = k_df["high"].tolist()
        lows = k_df["low"].tolist()
        closes = k_df["close"].tolist()
        decision = elliott_decision(settings, highs, lows, closes)
        pivots = swing_points(highs, lows, settings.swing_window)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Signal", decision.signal)
        col2.metric("Reason", decision.reason)
        col3.metric("Bias", decision.bias)
        col4.metric("Confidence", decision.confidence)

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=k_df["time_key"],
                    open=k_df["open"],
                    high=k_df["high"],
                    low=k_df["low"],
                    close=k_df["close"],
                    name="OHLC",
                )
            ]
        )
        fig.add_trace(
            go.Scatter(
                x=k_df["time_key"],
                y=k_df["trend_ma"],
                mode="lines",
                name=f"MA({settings.trend_ma})",
                line={"color": "#1f77b4", "width": 1.5},
            )
        )

        if pivots:
            pivot_idx = [p[0] for p in pivots]
            pivot_prices = [p[1] for p in pivots]
            pivot_types = [p[2] for p in pivots]
            pivot_times = [k_df.iloc[i]["time_key"] for i in pivot_idx]
            pivot_colors = ["#d62728" if t == "H" else "#2ca02c" for t in pivot_types]
            fig.add_trace(
                go.Scatter(
                    x=pivot_times,
                    y=pivot_prices,
                    mode="markers+text",
                    marker={"size": 8, "color": pivot_colors},
                    text=pivot_types,
                    textposition="top center",
                    name="Swing Points",
                )
            )

        if decision.entry_price is not None:
            _render_level(fig, decision.entry_price, "Entry", "#0066cc")
        if decision.stop_loss is not None:
            _render_level(fig, decision.stop_loss, "Stop Loss", "#cc0000")
        if decision.take_profit_1 is not None:
            _render_level(fig, decision.take_profit_1, "TP1", "#0f9d58")
        if decision.take_profit_2 is not None:
            _render_level(fig, decision.take_profit_2, "TP2", "#0b8043")
        if decision.invalidation_price is not None:
            _render_level(fig, decision.invalidation_price, "Invalidation", "#f57c00")

        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False,
            height=700,
            margin={"l": 10, "r": 10, "t": 20, "b": 10},
            legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        )
        st.plotly_chart(fig, use_container_width=True)

        last_candle = k_df["time_key"].max()
        st.caption(
            f"Loaded {len(k_df)} candles. K-type: {settings.ktype}. "
            f"Symbol: {settings.symbol}. Last candle: {last_candle}. Source: {feed_source}."
        )
        try:
            snap = _check_ret("get_market_snapshot", *quote_ctx.get_market_snapshot([settings.symbol]))
            if not snap.empty:
                snap_last = float(snap.iloc[0]["last_price"]) if "last_price" in snap.columns else None
                snap_time = str(snap.iloc[0]["update_time"]) if "update_time" in snap.columns else "N/A"
                st.caption(f"Snapshot last_price={snap_last} update_time={snap_time}")
        except Exception:
            pass

        if isinstance(last_candle, pd.Timestamp):
            if stale_days > 7:
                st.warning(
                    f"OpenD kline data looks stale ({stale_days} days old). "
                    "If snapshot time is current but kline is stale, your kline permission/feed is the likely issue."
                )
    except Exception as exc:
        st.error(str(exc))
    finally:
        if quote_ctx is not None:
            quote_ctx.close()


if __name__ == "__main__":
    main()
