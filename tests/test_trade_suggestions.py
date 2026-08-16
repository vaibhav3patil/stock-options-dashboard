from __future__ import annotations

import json
from pathlib import Path

from app.config import LiquidityConfig, MoveVsPremiumConfig, RiskConfig
from app.features.option_metrics import summarize_chain
from app.features.trade_suggestions import build_trade_suggestion
from app.models.schemas import DirectionBias, Eligibility


FIXTURE = Path(__file__).parent / "fixtures" / "reliance_chain.json"


def _metrics():
    chain = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=35.0,
        direction="CALL",
        lot_size=500,
        liquidity=LiquidityConfig(
            min_option_volume_atm_window=500,
            min_oi_atm_window=2000,
            max_bid_ask_pct_of_mid=0.05,
            require_bid_ask=False,
            atm_strike_window=2,
        ),
        move_cfg=MoveVsPremiumConfig(min_expected_to_be_ratio=1.5, hold_days_assumption=2),
        risk=RiskConfig(max_premium_per_trade_inr=50000),
        as_of_date="2026-08-13",
    )


def test_buy_call_primary_strike():
    metrics = _metrics()
    sug = build_trade_suggestion(
        symbol="RELIANCE",
        bias=DirectionBias.CALL,
        eligibility=Eligibility.NAKED_BUY_OK,
        metrics=metrics,
        atr=35.0,
        move_cfg=MoveVsPremiumConfig(min_expected_to_be_ratio=1.5, hold_days_assumption=2),
        risk=RiskConfig(max_premium_per_trade_inr=50000),
    )
    assert sug.action == "BUY_CALL"
    assert sug.primary is not None
    assert sug.primary.option_type == "CE"
    assert sug.primary.label in {"ATM", "ITM-1", "OTM-1"}
    assert sug.primary.premium > 0
    assert "BUY CALL" in sug.summary


def test_buy_put_primary_strike():
    metrics = _metrics()
    sug = build_trade_suggestion(
        symbol="RELIANCE",
        bias=DirectionBias.PUT,
        eligibility=Eligibility.WATCH,
        metrics=metrics,
        atr=35.0,
    )
    assert sug.action == "BUY_PUT"
    assert sug.primary is not None
    assert sug.primary.option_type == "PE"


def test_neutral_no_suggestion():
    metrics = _metrics()
    sug = build_trade_suggestion(
        symbol="RELIANCE",
        bias=DirectionBias.NEUTRAL,
        eligibility=Eligibility.NAKED_BUY_OK,
        metrics=metrics,
        atr=35.0,
    )
    assert sug.action == "NONE"
    assert sug.primary is None


def test_exclude_no_suggestion():
    metrics = _metrics()
    sug = build_trade_suggestion(
        symbol="RELIANCE",
        bias=DirectionBias.CALL,
        eligibility=Eligibility.EXCLUDE,
        metrics=metrics,
        atr=35.0,
    )
    assert sug.action == "NONE"
