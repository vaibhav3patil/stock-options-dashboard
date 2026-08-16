from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from app.config import DirectionConfig, MoveVsPremiumConfig, VolatilityConfig
from app.models.schemas import TrendLabel


@dataclass
class TechnicalFeatures:
    spot: Optional[float] = None
    atr: Optional[float] = None
    atr_pct: Optional[float] = None
    hv_20: Optional[float] = None
    rs_5: Optional[float] = None
    rs_20: Optional[float] = None
    squeeze: Optional[bool] = None
    trend: TrendLabel = TrendLabel.UNKNOWN


def _true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = _true_range(df)
    return tr.rolling(window=period, min_periods=period).mean()


def compute_atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    atr = compute_atr(df, period)
    return (atr / df["Close"]) * 100.0


def compute_realized_vol(df: pd.DataFrame, period: int = 20) -> pd.Series:
    log_ret = np.log(df["Close"] / df["Close"].shift(1))
    return log_ret.rolling(window=period, min_periods=period).std() * np.sqrt(252) * 100.0


def compute_relative_strength(
    stock: pd.DataFrame,
    benchmark: pd.DataFrame,
    lookback: int,
) -> Optional[float]:
    if stock.empty or benchmark.empty or lookback <= 0:
        return None
    s = stock["Close"].dropna()
    b = benchmark["Close"].dropna()
    aligned = pd.concat([s.rename("stock"), b.rename("bench")], axis=1, join="inner").dropna()
    if len(aligned) <= lookback:
        return None
    stock_ret = aligned["stock"].iloc[-1] / aligned["stock"].iloc[-lookback - 1] - 1.0
    bench_ret = aligned["bench"].iloc[-1] / aligned["bench"].iloc[-lookback - 1] - 1.0
    return float((stock_ret - bench_ret) * 100.0)


def compute_bollinger_bandwidth(
    df: pd.DataFrame,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.Series:
    mid = df["Close"].rolling(window=period, min_periods=period).mean()
    std = df["Close"].rolling(window=period, min_periods=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    bandwidth = (upper - lower) / mid
    return bandwidth


def is_squeeze(
    df: pd.DataFrame,
    *,
    period: int = 20,
    num_std: float = 2.0,
    lookback: int = 120,
    percentile: float = 20.0,
) -> Optional[bool]:
    bw = compute_bollinger_bandwidth(df, period=period, num_std=num_std).dropna()
    if bw.empty:
        return None
    window = bw.iloc[-lookback:] if len(bw) >= lookback else bw
    if window.empty:
        return None
    threshold = np.nanpercentile(window.values, percentile)
    return bool(bw.iloc[-1] <= threshold)


def classify_trend(
    df: pd.DataFrame,
    *,
    sma_fast: int = 20,
    sma_slow: int = 50,
) -> TrendLabel:
    if df.empty or len(df) < sma_slow:
        return TrendLabel.UNKNOWN
    close = df["Close"]
    fast = close.rolling(sma_fast).mean()
    slow = close.rolling(sma_slow).mean()
    if pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]):
        return TrendLabel.UNKNOWN

    # Structure: recent HH/HL vs LH/LL over last 10 bars
    recent = close.iloc[-10:]
    higher_highs = recent.iloc[-1] > recent.iloc[:5].max()
    lower_lows = recent.iloc[-1] < recent.iloc[:5].min()

    if fast.iloc[-1] > slow.iloc[-1] and close.iloc[-1] > fast.iloc[-1]:
        return TrendLabel.UP
    if fast.iloc[-1] < slow.iloc[-1] and close.iloc[-1] < fast.iloc[-1]:
        return TrendLabel.DOWN
    if higher_highs and not lower_lows:
        return TrendLabel.UP
    if lower_lows and not higher_highs:
        return TrendLabel.DOWN
    return TrendLabel.SIDEWAYS


def compute_technicals(
    stock_ohlc: pd.DataFrame,
    nifty_ohlc: pd.DataFrame | None = None,
    *,
    move_cfg: MoveVsPremiumConfig | None = None,
    vol_cfg: VolatilityConfig | None = None,
    direction_cfg: DirectionConfig | None = None,
) -> TechnicalFeatures:
    move_cfg = move_cfg or MoveVsPremiumConfig()
    vol_cfg = vol_cfg or VolatilityConfig()
    direction_cfg = direction_cfg or DirectionConfig()

    if stock_ohlc is None or stock_ohlc.empty:
        return TechnicalFeatures()

    df = stock_ohlc.copy()
    atr_series = compute_atr(df, move_cfg.atr_period)
    atr_pct_series = compute_atr_pct(df, move_cfg.atr_period)
    hv_series = compute_realized_vol(df, vol_cfg.hv_period)

    spot = float(df["Close"].iloc[-1])
    atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else None
    atr_pct = float(atr_pct_series.iloc[-1]) if not pd.isna(atr_pct_series.iloc[-1]) else None
    hv_20 = float(hv_series.iloc[-1]) if not pd.isna(hv_series.iloc[-1]) else None

    rs_5 = rs_20 = None
    if nifty_ohlc is not None and not nifty_ohlc.empty:
        rs_5 = compute_relative_strength(
            df, nifty_ohlc, direction_cfg.rs_short_lookback_days
        )
        rs_20 = compute_relative_strength(
            df, nifty_ohlc, direction_cfg.rs_lookback_days
        )

    squeeze = is_squeeze(
        df,
        period=direction_cfg.bb_period,
        num_std=direction_cfg.bb_std,
        lookback=direction_cfg.squeeze_lookback,
        percentile=direction_cfg.squeeze_percentile,
    )
    trend = classify_trend(
        df,
        sma_fast=direction_cfg.sma_fast,
        sma_slow=direction_cfg.sma_slow,
    )

    return TechnicalFeatures(
        spot=spot,
        atr=atr,
        atr_pct=atr_pct,
        hv_20=hv_20,
        rs_5=rs_5,
        rs_20=rs_20,
        squeeze=squeeze,
        trend=trend,
    )


def provisional_technical_score(features: TechnicalFeatures) -> Optional[float]:
    """Simple pre-chain score 0–100; clearly provisional until option rules land."""
    if features.spot is None:
        return None
    score = 40.0
    if features.atr_pct is not None:
        # Prefer higher ATR% for option buyers (capped contribution)
        score += min(max(features.atr_pct, 0.0) * 4.0, 20.0)
    if features.squeeze:
        score += 10.0
    if features.trend == TrendLabel.UP or features.trend == TrendLabel.DOWN:
        score += 10.0
    if features.rs_20 is not None:
        score += min(abs(features.rs_20), 15.0)
    return float(max(0.0, min(100.0, score)))
