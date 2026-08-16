from __future__ import annotations

import numpy as np
import pandas as pd

from app.features.technicals import (
    classify_trend,
    compute_atr_pct,
    compute_realized_vol,
    compute_relative_strength,
    compute_technicals,
    is_squeeze,
    provisional_technical_score,
)
from app.models.schemas import DataStatus, Eligibility, InstrumentType, TrendLabel
from app.scoring.engine import score_pre_chain


def _synth_ohlc(n: int = 120, start: float = 100.0, drift: float = 0.002) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    closes = [start]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + drift + float(rng.normal(0, 0.01))))
    close = np.array(closes)
    high = close * 1.01
    low = close * 0.99
    open_ = close * (1 + rng.normal(0, 0.002, size=n))
    volume = rng.integers(1000, 5000, size=n)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_atr_pct_positive():
    df = _synth_ohlc()
    atr_pct = compute_atr_pct(df, 14)
    assert atr_pct.dropna().iloc[-1] > 0


def test_realized_vol_annualized_scale():
    df = _synth_ohlc()
    hv = compute_realized_vol(df, 20)
    assert hv.dropna().iloc[-1] > 0


def test_relative_strength():
    stock = _synth_ohlc(drift=0.005)
    bench = _synth_ohlc(drift=0.001)
    rs = compute_relative_strength(stock, bench, 20)
    assert rs is not None
    assert rs > 0


def test_trend_up_on_uptrend():
    df = _synth_ohlc(n=80, drift=0.01)
    assert classify_trend(df) in {TrendLabel.UP, TrendLabel.SIDEWAYS}


def test_squeeze_returns_bool_or_none():
    df = _synth_ohlc(n=150)
    flag = is_squeeze(df, lookback=60, percentile=50)
    assert flag is None or isinstance(flag, bool)


def test_compute_technicals_bundle():
    stock = _synth_ohlc()
    nifty = _synth_ohlc(drift=0.001)
    feats = compute_technicals(stock, nifty)
    assert feats.spot is not None
    assert feats.atr_pct is not None
    assert feats.hv_20 is not None
    score = provisional_technical_score(feats)
    assert score is not None
    assert 0 <= score <= 100


def test_score_pre_chain_never_naked_buy_ok():
    stock = _synth_ohlc()
    feats = compute_technicals(stock, None)
    row = score_pre_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=feats,
        data_status=DataStatus.OK,
    )
    assert row.eligibility == Eligibility.WATCH
    assert row.eligibility != Eligibility.NAKED_BUY_OK


def test_score_pre_chain_stale_excludes():
    row = score_pre_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=None,
        data_status=DataStatus.DATA_STALE,
        error="timeout",
    )
    assert row.eligibility == Eligibility.EXCLUDE
    assert "IN12" in row.failed_rules
