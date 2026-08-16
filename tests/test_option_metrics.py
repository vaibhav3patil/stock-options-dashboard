from __future__ import annotations

import pandas as pd

from app.config import LiquidityConfig, MoveVsPremiumConfig, RiskConfig
from app.features.option_metrics import (
    bhav_to_chain_payload,
    compute_move_vs_premium,
    summarize_chain,
    summarize_eod_bhav,
)


def _eod_rows() -> pd.DataFrame:
    """Minimal EOD bhav-like rows around ATM 1310."""
    rows = []
    for strike in (1290, 1300, 1310, 1320, 1330):
        for opt, px, oi, vol in (
            ("CE", max(1.0, 22 - (strike - 1310) * 0.7), 200000 + strike, 200),
            ("PE", max(1.0, 21 + (strike - 1310) * 0.7), 180000 + strike, 180),
        ):
            rows.append(
                {
                    "TckrSymb": "RELIANCE",
                    "FinInstrmTp": "STO",
                    "OptnTp": opt,
                    "StrkPric": strike,
                    "XpryDt": "2026-08-25",
                    "ClsPric": px,
                    "LastPric": px,
                    "SttlmPric": px,
                    "UndrlygPric": 1310.0,
                    "OpnIntrst": oi,
                    "ChngInOpnIntrst": 1000,
                    "TtlTradgVol": vol,
                    "NewBrdLotQty": 500,
                }
            )
    return pd.DataFrame(rows)


def test_eod_bhav_summarize():
    metrics = summarize_eod_bhav(
        _eod_rows(),
        symbol="RELIANCE",
        as_of_date="2026-08-13",
        atr=35.0,
        direction="CALL",
        liquidity=LiquidityConfig(
            min_option_volume_atm_window=100,
            min_oi_atm_window=1000,
            require_bid_ask=False,
            atm_strike_window=2,
        ),
        move_cfg=MoveVsPremiumConfig(min_expected_to_be_ratio=1.5, hold_days_assumption=2),
        risk=RiskConfig(max_premium_per_trade_inr=50000),
        lot_size=500,
    )
    assert metrics.status == "OK"
    assert metrics.atm_strike == 1310
    assert metrics.liquidity_pass is True
    assert "L3" not in metrics.failed_liquidity_rules
    assert metrics.premium_per_lot == 500 * 22.0
    assert metrics.move_vs_premium_ratio is not None
    assert metrics.atm_iv is not None  # estimated from close
    assert metrics.source == "fo_bhav_eod"


def test_bhav_prefers_last_traded_over_close():
    rows = _eod_rows()
    rows.loc[
        (rows["StrkPric"] == 1310) & (rows["OptnTp"] == "CE"),
        ["LastPric", "ClsPric"],
    ] = [12.50, 15.30]
    payload = bhav_to_chain_payload(rows, symbol="RELIANCE")
    atm = next(r for r in payload["records"]["data"] if r["strikePrice"] == 1310)
    assert atm["CE"]["lastPrice"] == 12.50


def test_bhav_to_chain_payload_empty():
    payload = bhav_to_chain_payload(pd.DataFrame(), symbol="TCS")
    assert payload["status"] == "DATA_UNAVAILABLE"


def test_liquidity_fail_wide_spread_when_required():
    from pathlib import Path
    import json

    chain = json.loads(
        (Path(__file__).parent / "fixtures" / "reliance_chain.json").read_text()
    )
    for row in chain["records"]["data"]:
        if row["strikePrice"] == 1310:
            row["CE"]["bidprice"] = 10.0
            row["CE"]["askPrice"] = 40.0
    metrics = summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=20.0,
        direction="CALL",
        lot_size=500,
        liquidity=LiquidityConfig(max_bid_ask_pct_of_mid=0.03, require_bid_ask=True),
    )
    assert metrics.liquidity_pass is False
    assert "L3" in metrics.failed_liquidity_rules


def test_move_vs_premium_ratio():
    expected, be, ratio = compute_move_vs_premium(
        atr=30.0,
        premium=10.0,
        spread_pct=0.02,
        move_cfg=MoveVsPremiumConfig(hold_days_assumption=2),
    )
    assert expected is not None and expected > 0
    assert be is not None and be > 10
    assert ratio is not None and ratio > 1.5


def test_expected_session_rolls_weekend_to_friday():
    from datetime import datetime

    from app.data.providers.nse_bhavcopy import IST, expected_session_date

    saturday = datetime(2026, 8, 15, 18, 0, tzinfo=IST)
    friday = datetime(2026, 8, 14, 10, 0, tzinfo=IST)
    assert expected_session_date(saturday).isoformat() == "2026-08-14"
    assert expected_session_date(friday).isoformat() == "2026-08-14"
