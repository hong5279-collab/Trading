# Moomoo Auto Trading Starter

This is a safe starter app for automated trading with moomoo OpenAPI.

It includes:
- moomoo OpenD connection
- account auto-selection
- selectable strategy engine:
  - Elliott Wave-style swing entry/exit signal
  - trend-momentum breakout with MA, momentum, and ATR risk filters
- dollar-based order sizing for entries (BUY by USD amount)
- automatic take-profit / stop-loss sell rules
- risk guardrails (max position, daily trade cap, dry-run, simulate mode)
- dashboard comparison of recent strategy performance on fetched candles

## 1) Prerequisites

- Python 3.10+
- moomoo desktop app / OpenD installed and running
- OpenD listening on `127.0.0.1:11111` (or update `.env`)
- Logged-in moomoo account in OpenD

## 2) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3) Configure

```bash
cp .env.example .env
```

Edit `.env` (important defaults):
- `TRADE_ENV=SIMULATE`
- `DRY_RUN=true`

Keep these until you are confident.

## 4) Run

```bash
python app.py
```

## 4b) Strategy chart UI

You can visualize how the Elliott strategy applies on a stock chart:

```bash
streamlit run dashboard.py
```

In the sidebar:
- set `Symbol` (example: `US.AAPL` or `US.NVDA`)
- adjust candle lookback / swing window / trend MA
- click `Refresh`

The chart overlays:
- candlesticks + trend MA
- detected swing highs/lows
- current strategy levels (Entry, Invalidation, Stop Loss, TP1, TP2)
- a recent backtest summary for `ELLIOTT` and `TREND_MOMENTUM`

## Project structure

- `app.py`: thin entrypoint
- `src/config.py`: environment and settings loading
- `src/broker/moomoo_client.py`: moomoo/OpenD connectivity and order APIs
- `src/strategy/elliott.py`: Elliott wave signal engine
- `src/strategy/trend_momentum.py`: breakout + momentum strategy engine
- `src/strategy/engine.py`: strategy selection router
- `src/strategy/backtest.py`: recent-candle comparison helper for the dashboard
- `src/strategy/risk.py`: sizing and TP/SL exit helpers
- `src/bot/trader.py`: trading loop orchestration
- `src/models.py`: shared dataclasses

## 5) How it works

- Every `POLL_SECONDS`, it fetches recent candles via `request_history_kline`.
- It evaluates the selected `STRATEGY_MODE`:
  - `ELLIOTT`: swing-pivot impulse / ABC continuation logic
  - `TREND_MOMENTUM`: breakout above recent highs with MA trend, momentum, and ATR filters
- Uses structured Elliott decision fields:
  - `entry_price` trigger (breakout confirmation)
  - `invalidation_price` and `stop_loss`
  - `take_profit_1` and `take_profit_2`
  - long-side TP/SL is widened via configurable wave multipliers and stop buffer:
    - `take_profit_1 = l4 + EW_TP1_WAVE_MULT * wave1`
    - `take_profit_2 = l4 + EW_TP2_WAVE_MULT * wave1`
    - `stop_loss = l4 * (1 - EW_SL_BUFFER_PCT)`
- Signal quality filters are applied to reduce noise:
  - trend filter with `TREND_MA`
  - minimum wave size with `EW_MIN_WAVE_PCT`
  - retracement bounds using `EW_WAVE2_*` and `EW_WAVE4_*`
- The trend strategy adds:
  - `TREND_FAST_MA` / `TREND_SLOW_MA`
  - `TREND_BREAKOUT_LOOKBACK`
  - `TREND_MOMENTUM_LOOKBACK` and `TREND_MIN_MOMENTUM_PCT`
  - `TREND_ATR_WINDOW`, `TREND_ATR_STOP_MULT`, and `TREND_MIN_ATR_PCT`
  - `TREND_TP1_R` / `TREND_TP2_R` risk-reward targets
- Position size is converted from USD to shares at runtime:
  - `BUY_AMOUNT_USD / price` -> buy quantity
- `SELL` orders are used only to exit existing long positions (TP/SL)
- If a position exists and average cost is available:
  - priority: use active Elliott plan TP/SL when available
  - fallback: use percent TP/SL from average cost
- Before any order, it checks:
  - open orders for the symbol
  - current position size
  - `MAX_POSITION_QTY`
  - `MAX_POSITION_USD`
  - `MAX_DAILY_TRADES`
  - `DRY_RUN`

Orders are submitted as limit (`OrderType.NORMAL`) at current snapshot last price.

## 6) Tuning knobs

- `EW_LOOKBACK`: candles inspected for swing detection (higher = slower but cleaner)
- `STRATEGY_MODE`: choose `ELLIOTT` or `TREND_MOMENTUM`
- `SWING_WINDOW`: pivot sensitivity (higher = fewer pivots/signals)
- `TREND_MA`: trend filter moving average window
- `EW_MIN_WAVE_PCT`: minimum wave-1 size as a fraction of price (filters tiny moves)
- `EW_WAVE2_MIN_RETRACE` / `EW_WAVE2_MAX_RETRACE`: acceptable wave-2 retracement band
- `EW_WAVE4_MIN_RETRACE` / `EW_WAVE4_MAX_RETRACE`: acceptable wave-4 retracement band
- `EW_TP1_WAVE_MULT`: first Elliott TP extension multiplier (wider default: `1.618`)
- `EW_TP2_WAVE_MULT`: second Elliott TP extension multiplier (wider default: `2.618`)
- `EW_SL_BUFFER_PCT`: extra stop buffer below invalidation `l4` (default: `0.01`)
- `TREND_FAST_MA` / `TREND_SLOW_MA`: moving average trend filter for the trend strategy
- `TREND_BREAKOUT_LOOKBACK`: breakout channel length
- `TREND_MOMENTUM_LOOKBACK`: return lookback used for momentum confirmation
- `TREND_MIN_MOMENTUM_PCT`: minimum return threshold for a breakout trade
- `TREND_ATR_WINDOW`: ATR volatility window
- `TREND_ATR_STOP_MULT`: ATR-based stop distance multiplier
- `TREND_MIN_ATR_PCT`: minimum ATR/price ratio required before taking a trend trade
- `TREND_TP1_R` / `TREND_TP2_R`: take-profit levels in multiples of initial risk
- `MAX_POSITION_USD`: hard cap on total position market value

There is no universal "best" strategy. In this starter app, `TREND_MOMENTUM` is meant to be the more evidence-backed default candidate to test first, while `ELLIOTT` remains available when you want more structure-based entries.

## 7) Live trading warning

When switching to `TRADE_ENV=REAL`:
- You may need to set `TRADE_PASSWORD` for `unlock_trade`.
- Start with very small size.
- Review logs and order behavior in simulation first.

This project is educational starter code, not financial advice.

## 8) If you see ECONNREFUSED

If you get errors like:
- `Connect fail ... ECONNREFUSED`

Then your app cannot reach OpenD at `MOOMOO_HOST:MOOMOO_PORT`.

Checklist:
- Start moomoo OpenD and log in.
- Confirm OpenD API port (default is often `11111`).
- Ensure `.env` matches host/port.
- If OpenD is on another machine, set `MOOMOO_HOST` to that machine's LAN IP.
- Check firewall rules.
