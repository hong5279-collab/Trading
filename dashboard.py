import socket
import re
import ssl
from datetime import datetime, timedelta
from html import unescape
from typing import Optional
from urllib.request import Request, urlopen

import moomoo as ft
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from src.config import Settings
from src.strategy.backtest import backtest_strategy
from src.strategy.engine import strategy_decision
from src.strategy.elliott import swing_points
from src.strategy.trend_momentum import _atr, _sma


TRENDING_STOCKS_URL = "https://stockanalysis.com/trending/"


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


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", unescape(value)).strip()


@st.cache_data(ttl=600)
def _fetch_stockanalysis_trending(limit: int = 20):
    request = Request(
        TRENDING_STOCKS_URL,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    context = ssl._create_unverified_context()
    raw_html = urlopen(request, timeout=12, context=context).read().decode("utf-8", "replace")

    updated = "Unknown"
    updated_match = re.search(r"Updated:\s*(.*?)</div>", raw_html, flags=re.S)
    if updated_match:
        updated = _clean_html_text(updated_match.group(1))

    body_match = re.search(r"<tbody>(.*?)</tbody>", raw_html, flags=re.S)
    if not body_match:
        return [], updated

    rows = []
    for row_html in re.findall(r"<tr[^>]*>(.*?)</tr>", body_match.group(1), flags=re.S):
        cells = [_clean_html_text(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.S)]
        if len(cells) < 7:
            continue
        rows.append(
            {
                "rank": int(cells[0]) if cells[0].isdigit() else len(rows) + 1,
                "symbol": cells[1],
                "moomoo_symbol": f"US.{cells[1]}",
                "company": cells[2],
                "views": cells[3],
                "market_cap": cells[4],
                "change_pct": cells[5],
                "volume": cells[6],
            }
        )
        if len(rows) >= limit:
            break

    return rows, updated


def _score_trending_symbol(settings: Settings, quote_ctx: ft.OpenQuoteContext, row: dict):
    symbol = row["moomoo_symbol"]
    need = settings.ew_lookback + 5
    k_df, feed_source, _ = _fetch_best_candles(quote_ctx, symbol, settings.ktype, need)
    if len(k_df) < 60:
        raise RuntimeError(f"not enough candles for {symbol}")

    highs = [float(x) for x in k_df["high"].tolist()]
    lows = [float(x) for x in k_df["low"].tolist()]
    closes = [float(x) for x in k_df["close"].tolist()]
    last_close = closes[-1]
    breakout = max(highs[-settings.trend_breakout_lookback - 1 : -1])
    recent_low = min(lows[-settings.trend_breakout_lookback :])
    momentum_pct = (last_close / closes[-settings.trend_momentum_lookback - 1] - 1) * 100
    distance_to_breakout_pct = (breakout / max(last_close, 1e-9) - 1) * 100
    fast_ma = _sma(closes, settings.trend_fast_ma)
    slow_ma = _sma(closes, settings.trend_slow_ma)
    atr = _atr(highs, lows, closes, settings.trend_atr_window)
    atr_pct = atr / max(last_close, 1e-9) * 100
    trend_decision = strategy_decision(settings, highs, lows, closes, strategy_mode="TREND_MOMENTUM")
    ew_decision = strategy_decision(settings, highs, lows, closes, strategy_mode="ELLIOTT")

    score = 0.0
    if trend_decision.signal == "BUY":
        score += 100.0
    elif 0 <= distance_to_breakout_pct <= 3:
        score += 35.0 - (distance_to_breakout_pct * 5.0)
    elif 3 < distance_to_breakout_pct <= 6:
        score += 10.0
    elif distance_to_breakout_pct < 0:
        score += 20.0

    if fast_ma > slow_ma:
        score += 20.0
    else:
        score -= 20.0
    if momentum_pct >= settings.trend_min_momentum_pct * 100:
        score += 20.0
    if atr_pct >= settings.trend_min_atr_pct * 100:
        score += 10.0
    if ew_decision.signal == "BUY":
        score += 10.0
    if "setup expired" in ew_decision.reason:
        score -= 5.0

    if trend_decision.signal == "BUY":
        action = "BUY signal"
    elif 0 <= distance_to_breakout_pct <= 3 and fast_ma > slow_ma and momentum_pct >= settings.trend_min_momentum_pct * 100:
        action = "Watch breakout"
    elif 0 <= distance_to_breakout_pct <= 6 and fast_ma > slow_ma:
        action = "Near breakout"
    else:
        action = "Skip now"

    return {
        "symbol": symbol,
        "company": row["company"],
        "action": action,
        "score": round(score, 1),
        "price": round(last_close, 4),
        "breakout": round(breakout, 4),
        "distance_to_breakout_pct": round(distance_to_breakout_pct, 2),
        "momentum_pct": round(momentum_pct, 2),
        "atr_pct": round(atr_pct, 2),
        "recent_low": round(recent_low, 4),
        "trend_signal": trend_decision.signal,
        "ew_signal": ew_decision.signal,
        "source_rank": row["rank"],
        "source_views": row["views"],
        "source_change_pct": row["change_pct"],
        "feed_source": feed_source,
        "reason": trend_decision.reason,
    }


def _render_trending_ideas(settings: Settings, quote_ctx: Optional[ft.OpenQuoteContext], scan_limit: int):
    st.subheader("Trending Stock Ideas")
    try:
        trending_rows, updated = _fetch_stockanalysis_trending(limit=max(scan_limit, 20))
    except Exception as exc:
        st.error(f"Could not load trending stocks: {exc}")
        return

    if not trending_rows:
        st.warning("No trending stocks were returned by the source.")
        return

    st.caption(
        f"Source: StockAnalysis trending stocks. Updated: {updated}. "
        "Sorted by pageviews; use as an idea feed only."
    )
    source_df = pd.DataFrame(trending_rows[:scan_limit])
    st.dataframe(
        source_df[["rank", "moomoo_symbol", "company", "views", "change_pct", "volume"]],
        use_container_width=True,
        hide_index=True,
    )

    if quote_ctx is None:
        st.info("Start moomoo OpenD to score trending names with EW and Momentum rules.")
        return

    scored_rows = []
    for row in trending_rows[:scan_limit]:
        try:
            scored_rows.append(_score_trending_symbol(settings, quote_ctx, row))
        except Exception as exc:
            scored_rows.append(
                {
                    "symbol": row["moomoo_symbol"],
                    "company": row["company"],
                    "action": "Unavailable",
                    "score": -999.0,
                    "reason": str(exc),
                    "source_rank": row["rank"],
                    "source_views": row["views"],
                    "source_change_pct": row["change_pct"],
                }
            )

    scored_df = pd.DataFrame(scored_rows).sort_values(
        by=["score", "source_rank"],
        ascending=[False, True],
    )
    available_df = scored_df[scored_df["score"] > -999.0]
    if available_df.empty:
        st.warning("Trending symbols loaded, but none had enough OpenD candle history to score.")
    else:
        best = available_df.iloc[0]
        st.markdown(
            f"**Top scored idea:** {best['symbol']} - {best['action']} "
            f"(score {best['score']}, breakout {best.get('breakout', 'N/A')})"
        )
    st.dataframe(scored_df, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="Trading Strategy Chart", layout="wide")
    st.title("Trading Strategy Visualizer")
    st.caption("Compare the current Elliott model against a trend-momentum breakout model on the latest candles.")

    settings = Settings.from_env()

    with st.sidebar:
        st.subheader("Inputs")
        symbol = st.text_input("Symbol", value=settings.symbol).strip() or settings.symbol
        strategy_mode = st.selectbox(
            "Strategy",
            options=["ELLIOTT", "TREND_MOMENTUM"],
            index=0 if settings.strategy_mode == "ELLIOTT" else 1,
        )
        ew_lookback = st.slider("Candles (lookback)", min_value=60, max_value=1000, value=settings.ew_lookback, step=10)
        swing_window = st.slider("Swing window", min_value=1, max_value=15, value=settings.swing_window, step=1)
        trend_ma = st.slider("Trend MA", min_value=5, max_value=200, value=settings.trend_ma, step=1)
        ew_max_setup_age_bars = st.slider(
            "EW max setup age",
            min_value=5,
            max_value=120,
            value=settings.ew_max_setup_age_bars,
            step=1,
        )
        ew_max_entry_risk_multiple = st.slider(
            "EW max late entry R",
            min_value=0.0,
            max_value=3.0,
            value=settings.ew_max_entry_risk_multiple,
            step=0.05,
        )
        refresh = st.button("Refresh")
        st.divider()
        st.subheader("Trending")
        trending_scan_limit = st.slider("Trending scan count", min_value=5, max_value=20, value=10, step=1)
        load_trending = st.button("Load Trending Ideas")
        st.caption(f"Host: {settings.host}:{settings.port}")

    settings.symbol = symbol
    settings.strategy_mode = strategy_mode
    settings.ew_lookback = ew_lookback
    settings.swing_window = swing_window
    settings.trend_ma = trend_ma
    settings.ew_max_setup_age_bars = ew_max_setup_age_bars
    settings.ew_max_entry_risk_multiple = ew_max_entry_risk_multiple

    if not refresh and not load_trending:
        st.info("Click `Refresh` to fetch latest candles and re-evaluate strategy, or load trending ideas.")
        return

    opend_available = _can_connect_tcp(settings.host, settings.port)
    if refresh and not opend_available:
        st.error(f"Cannot connect to OpenD at {settings.host}:{settings.port}. Start OpenD and check `.env` host/port.")
        return

    quote_ctx = None
    try:
        if opend_available:
            quote_ctx = ft.OpenQuoteContext(host=settings.host, port=settings.port)
        if load_trending:
            _render_trending_ideas(settings, quote_ctx, trending_scan_limit)
            if not refresh:
                return

        if quote_ctx is None:
            st.error(f"Cannot connect to OpenD at {settings.host}:{settings.port}. Start OpenD and check `.env` host/port.")
            return

        need = settings.ew_lookback + 5
        k_df, feed_source, stale_days = _fetch_best_candles(quote_ctx, settings.symbol, settings.ktype, need)
        if len(k_df) < 30:
            st.error(f"Not enough candles for {settings.symbol}. Need at least 30, got {len(k_df)}.")
            return

        k_df["trend_ma"] = k_df["close"].rolling(window=settings.trend_ma, min_periods=1).mean()

        highs = k_df["high"].tolist()
        lows = k_df["low"].tolist()
        closes = k_df["close"].tolist()
        decision = strategy_decision(settings, highs, lows, closes)
        pivots = swing_points(highs, lows, settings.swing_window)
        comparison_rows = [
            backtest_strategy(settings, highs, lows, closes, "ELLIOTT"),
            backtest_strategy(settings, highs, lows, closes, "TREND_MOMENTUM"),
        ]

        col1, col2, col3, col4, col5 = st.columns([1, 1.4, 2.2, 1, 1])
        col1.metric("Signal", decision.signal)
        col2.metric("Strategy", settings.strategy_mode)
        col3.markdown("**Reason**")
        col3.write(decision.reason)
        col4.metric("Bias", decision.bias)
        col5.metric("Confidence", decision.confidence)

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

        st.subheader("Recent Strategy Comparison")
        comparison_df = pd.DataFrame(comparison_rows).sort_values(
            by=["total_return_pct", "win_rate_pct", "trades"],
            ascending=[False, False, False],
        )
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)
        winner = comparison_df.iloc[0]
        if int(winner["trades"]) > 0:
            st.caption(
                f"Recent sample leader: {winner['strategy']} "
                f"(return {winner['total_return_pct']}%, win rate {winner['win_rate_pct']}%, trades {winner['trades']}). "
                "Use this only as a quick local check, not as proof of future edge."
            )
        else:
            st.caption("No completed trades were found in the current candle sample for either strategy.")

        last_candle = k_df["time_key"].max()
        st.caption(
            f"Loaded {len(k_df)} candles. K-type: {settings.ktype}. "
            f"Symbol: {settings.symbol}. Last candle: {last_candle}. "
            f"Selected strategy: {settings.strategy_mode}. Source: {feed_source}."
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
