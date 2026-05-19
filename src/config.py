import os
from dataclasses import dataclass

from dotenv import load_dotenv
import moomoo as ft
from src.strategy.modes import SUPPORTED_STRATEGY_MODES


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}

@dataclass
class Settings:
    host: str
    port: int
    market: ft.TrdMarket
    security_firm: ft.SecurityFirm
    symbol: str
    ktype: ft.KLType
    strategy_mode: str
    ew_lookback: int
    swing_window: int
    trend_ma: int
    min_wave_pct: float
    wave2_min_retrace: float
    wave2_max_retrace: float
    wave4_min_retrace: float
    wave4_max_retrace: float
    ew_tp1_wave_mult: float
    ew_tp2_wave_mult: float
    ew_sl_buffer_pct: float
    ew_max_setup_age_bars: int
    ew_max_entry_risk_multiple: float
    trend_fast_ma: int
    trend_slow_ma: int
    trend_breakout_lookback: int
    trend_momentum_lookback: int
    trend_min_momentum_pct: float
    trend_atr_window: int
    trend_atr_stop_mult: float
    trend_min_atr_pct: float
    trend_tp1_r: float
    trend_tp2_r: float
    poll_seconds: int
    trd_env: ft.TrdEnv
    trade_password: str
    buy_amount_usd: float
    take_profit_pct: float
    stop_loss_pct: float
    max_position_qty: int
    max_position_usd: float
    max_daily_trades: int
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        market_map = {
            "HK": ft.TrdMarket.HK,
            "US": ft.TrdMarket.US,
            "SG": ft.TrdMarket.SG,
            "JP": ft.TrdMarket.JP,
            "HKCC": ft.TrdMarket.HKCC,
        }
        firm_map = {}
        for name in [
            "FUTUSECURITIES",
            "FUTUINC",
            "FUTUSG",
            "FUTUAU",
            "FUTUCA",
            "FUTUMY",
            "FUTUJP",
        ]:
            val = getattr(ft.SecurityFirm, name, None)
            if val is not None:
                firm_map[name] = val
        env_map = {
            "SIMULATE": ft.TrdEnv.SIMULATE,
            "REAL": ft.TrdEnv.REAL,
        }
        ktype_map = {
            "K_1M": ft.KLType.K_1M,
            "K_5M": ft.KLType.K_5M,
            "K_15M": ft.KLType.K_15M,
            "K_30M": ft.KLType.K_30M,
            "K_60M": ft.KLType.K_60M,
            "K_DAY": ft.KLType.K_DAY,
        }

        market_key = os.getenv("MOOMOO_MARKET", "US").upper()
        firm_key = os.getenv("MOOMOO_SECURITY_FIRM", "FUTUMY").upper()
        env_key = os.getenv("TRADE_ENV", "SIMULATE").upper()
        ktype_key = os.getenv("KTYPE", "K_1M").upper()

        if market_key not in market_map:
            raise ValueError(f"Unsupported MOOMOO_MARKET: {market_key}")
        if firm_key not in firm_map:
            raise ValueError(f"Unsupported MOOMOO_SECURITY_FIRM: {firm_key}")
        if env_key not in env_map:
            raise ValueError(f"Unsupported TRADE_ENV: {env_key}")
        if ktype_key not in ktype_map:
            raise ValueError(f"Unsupported KTYPE: {ktype_key}")

        strategy_mode = os.getenv("STRATEGY_MODE", "ELLIOTT").strip().upper()
        if strategy_mode not in SUPPORTED_STRATEGY_MODES:
            supported = ", ".join(SUPPORTED_STRATEGY_MODES)
            raise ValueError(f"STRATEGY_MODE must be one of: {supported}")

        ew_lookback = max(30, int(os.getenv("EW_LOOKBACK", os.getenv("EW_LSOOKBACK", "240"))))
        swing_window = max(1, int(os.getenv("SWING_WINDOW", "5")))
        trend_ma = max(5, int(os.getenv("TREND_MA", "50")))
        min_wave_pct = float(os.getenv("EW_MIN_WAVE_PCT", "0.007"))
        wave2_min_retrace = float(os.getenv("EW_WAVE2_MIN_RETRACE", "0.30"))
        wave2_max_retrace = float(os.getenv("EW_WAVE2_MAX_RETRACE", "0.70"))
        wave4_min_retrace = float(os.getenv("EW_WAVE4_MIN_RETRACE", "0.20"))
        wave4_max_retrace = float(os.getenv("EW_WAVE4_MAX_RETRACE", "0.40"))
        ew_tp1_wave_mult = float(os.getenv("EW_TP1_WAVE_MULT", "1.618"))
        ew_tp2_wave_mult = float(os.getenv("EW_TP2_WAVE_MULT", "2.618"))
        ew_sl_buffer_pct = float(os.getenv("EW_SL_BUFFER_PCT", "0.01"))
        ew_max_setup_age_bars = max(1, int(os.getenv("EW_MAX_SETUP_AGE_BARS", "48")))
        ew_max_entry_risk_multiple = float(os.getenv("EW_MAX_ENTRY_RISK_MULTIPLE", "0.75"))
        trend_fast_ma = max(2, int(os.getenv("TREND_FAST_MA", "20")))
        trend_slow_ma = max(3, int(os.getenv("TREND_SLOW_MA", "50")))
        trend_breakout_lookback = max(5, int(os.getenv("TREND_BREAKOUT_LOOKBACK", "20")))
        trend_momentum_lookback = max(5, int(os.getenv("TREND_MOMENTUM_LOOKBACK", "20")))
        trend_min_momentum_pct = float(os.getenv("TREND_MIN_MOMENTUM_PCT", "0.005"))
        trend_atr_window = max(2, int(os.getenv("TREND_ATR_WINDOW", "14")))
        trend_atr_stop_mult = float(os.getenv("TREND_ATR_STOP_MULT", "2.0"))
        trend_min_atr_pct = float(os.getenv("TREND_MIN_ATR_PCT", "0.002"))
        trend_tp1_r = float(os.getenv("TREND_TP1_R", "1.5"))
        trend_tp2_r = float(os.getenv("TREND_TP2_R", "3.0"))
        take_profit_pct = float(os.getenv("TAKE_PROFIT_PCT", "0.03"))
        stop_loss_pct = float(os.getenv("STOP_LOSS_PCT", "0.015"))
        if take_profit_pct <= 0 or stop_loss_pct <= 0:
            raise ValueError("TAKE_PROFIT_PCT and STOP_LOSS_PCT must be > 0")
        if min_wave_pct <= 0:
            raise ValueError("EW_MIN_WAVE_PCT must be > 0")
        if not (0 < wave2_min_retrace < wave2_max_retrace < 1.2):
            raise ValueError("Require 0 < EW_WAVE2_MIN_RETRACE < EW_WAVE2_MAX_RETRACE < 1.2")
        if not (0 < wave4_min_retrace < wave4_max_retrace < 1.0):
            raise ValueError("Require 0 < EW_WAVE4_MIN_RETRACE < EW_WAVE4_MAX_RETRACE < 1.0")
        if not (0 < ew_tp1_wave_mult < ew_tp2_wave_mult):
            raise ValueError("Require 0 < EW_TP1_WAVE_MULT < EW_TP2_WAVE_MULT")
        if not (0 <= ew_sl_buffer_pct < 0.20):
            raise ValueError("Require 0 <= EW_SL_BUFFER_PCT < 0.20")
        if ew_max_entry_risk_multiple < 0:
            raise ValueError("EW_MAX_ENTRY_RISK_MULTIPLE must be >= 0")
        if trend_fast_ma >= trend_slow_ma:
            raise ValueError("TREND_FAST_MA must be smaller than TREND_SLOW_MA")
        if trend_min_momentum_pct < 0:
            raise ValueError("TREND_MIN_MOMENTUM_PCT must be >= 0")
        if trend_atr_stop_mult <= 0:
            raise ValueError("TREND_ATR_STOP_MULT must be > 0")
        if trend_min_atr_pct < 0:
            raise ValueError("TREND_MIN_ATR_PCT must be >= 0")
        if not (0 < trend_tp1_r < trend_tp2_r):
            raise ValueError("Require 0 < TREND_TP1_R < TREND_TP2_R")

        return cls(
            host=os.getenv("MOOMOO_HOST", "127.0.0.1"),
            port=int(os.getenv("MOOMOO_PORT", "11111")),
            market=market_map[market_key],
            security_firm=firm_map[firm_key],
            symbol=os.getenv("SYMBOL", "US.AAPL"),
            ktype=ktype_map[ktype_key],
            strategy_mode=strategy_mode,
            ew_lookback=ew_lookback,
            swing_window=swing_window,
            trend_ma=trend_ma,
            min_wave_pct=min_wave_pct,
            wave2_min_retrace=wave2_min_retrace,
            wave2_max_retrace=wave2_max_retrace,
            wave4_min_retrace=wave4_min_retrace,
            wave4_max_retrace=wave4_max_retrace,
            ew_tp1_wave_mult=ew_tp1_wave_mult,
            ew_tp2_wave_mult=ew_tp2_wave_mult,
            ew_sl_buffer_pct=ew_sl_buffer_pct,
            ew_max_setup_age_bars=ew_max_setup_age_bars,
            ew_max_entry_risk_multiple=ew_max_entry_risk_multiple,
            trend_fast_ma=trend_fast_ma,
            trend_slow_ma=trend_slow_ma,
            trend_breakout_lookback=trend_breakout_lookback,
            trend_momentum_lookback=trend_momentum_lookback,
            trend_min_momentum_pct=trend_min_momentum_pct,
            trend_atr_window=trend_atr_window,
            trend_atr_stop_mult=trend_atr_stop_mult,
            trend_min_atr_pct=trend_min_atr_pct,
            trend_tp1_r=trend_tp1_r,
            trend_tp2_r=trend_tp2_r,
            poll_seconds=max(5, int(os.getenv("POLL_SECONDS", "30"))),
            trd_env=env_map[env_key],
            trade_password=os.getenv("TRADE_PASSWORD", ""),
            buy_amount_usd=max(1.0, float(os.getenv("BUY_AMOUNT_USD", os.getenv("ORDER_USD", "200")))),
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            max_position_qty=max(1, int(os.getenv("MAX_POSITION_QTY", "10"))),
            max_position_usd=max(1.0, float(os.getenv("MAX_POSITION_USD", "2000"))),
            max_daily_trades=max(1, int(os.getenv("MAX_DAILY_TRADES", "5"))),
            dry_run=_env_bool("DRY_RUN", True),
        )
