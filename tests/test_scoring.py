from __future__ import annotations

import json
from pathlib import Path

from app.config import RulesConfig, VolatilityConfig, MoveVsPremiumConfig, LiquidityConfig, RiskConfig
from app.features.option_metrics import summarize_chain
from app.features.technicals import TechnicalFeatures
from app.models.schemas import DataStatus, Eligibility, InstrumentType, TrendLabel
from app.scoring.engine import score_with_chain


FIXTURE = Path(__file__).parent / "fixtures" / "reliance_chain.json"


def _features(**kwargs) -> TechnicalFeatures:
    base = dict(
        spot=1310.0,
        atr=35.0,
        atr_pct=2.5,
        hv_20=22.0,
        rs_5=1.0,
        rs_20=4.0,
        squeeze=True,
        trend=TrendLabel.UP,
    )
    base.update(kwargs)
    return TechnicalFeatures(**base)


def _rules() -> RulesConfig:
    return RulesConfig(
        liquidity=LiquidityConfig(
            min_option_volume_atm_window=500,
            min_oi_atm_window=2000,
            max_bid_ask_pct_of_mid=0.05,
            atm_strike_window=2,
        ),
        move_vs_premium=MoveVsPremiumConfig(
            min_expected_to_be_ratio=1.5,
            hold_days_assumption=2,
        ),
        volatility=VolatilityConfig(rich_iv_hv_ratio=1.3),
        risk=RiskConfig(max_premium_per_trade_inr=50000),
    )


def test_naked_buy_ok_when_gates_pass():
    chain = json.loads(FIXTURE.read_text(encoding="utf-8"))
    metrics = summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=35.0,
        direction="CALL",
        lot_size=500,
        liquidity=_rules().liquidity,
        move_cfg=_rules().move_vs_premium,
        risk=_rules().risk,
    )
    row = score_with_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=_features(),
        metrics=metrics,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
    )
    assert row.eligibility == Eligibility.NAKED_BUY_OK
    assert row.atm_iv is not None


def test_exclude_on_liquidity_fail():
    chain = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for row in chain["records"]["data"]:
        row["CE"]["totalTradedVolume"] = 1
        row["PE"]["totalTradedVolume"] = 1
        row["CE"]["openInterest"] = 1
        row["PE"]["openInterest"] = 1
    metrics = summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=35.0,
        direction="CALL",
        lot_size=500,
        liquidity=_rules().liquidity,
        move_cfg=_rules().move_vs_premium,
        risk=_rules().risk,
    )
    row = score_with_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=_features(),
        metrics=metrics,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
    )
    assert row.eligibility == Eligibility.EXCLUDE
    assert any(r.startswith("L") for r in row.failed_rules)


def test_spread_only_when_iv_rich():
    chain = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for row in chain["records"]["data"]:
        row["CE"]["impliedVolatility"] = 60.0
        row["PE"]["impliedVolatility"] = 60.0
        # Keep premium high so move ratio is not "superior"
        row["CE"]["lastPrice"] = 40.0
        row["CE"]["bidprice"] = 39.5
        row["CE"]["askPrice"] = 40.4
    metrics = summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=20.0,
        direction="CALL",
        lot_size=500,
        liquidity=_rules().liquidity,
        move_cfg=_rules().move_vs_premium,
        risk=_rules().risk,
    )
    row = score_with_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=_features(atr=20.0, hv_20=20.0),
        metrics=metrics,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
    )
    assert row.eligibility in {Eligibility.SPREAD_ONLY, Eligibility.WATCH}


def test_score_with_chain_accepts_as_of():
    chain = json.loads(FIXTURE.read_text(encoding="utf-8"))
    metrics = summarize_chain(
        chain,
        symbol="RELIANCE",
        atr=35.0,
        direction="CALL",
        lot_size=500,
        liquidity=_rules().liquidity,
        move_cfg=_rules().move_vs_premium,
        risk=_rules().risk,
        as_of_date="2026-08-13",
    )
    row = score_with_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=_features(),
        metrics=metrics,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
        as_of_date="2026-08-13",
    )
    assert row.as_of_date == "2026-08-13"
    assert "EOD" in row.setup_tags


def test_exclude_when_chain_missing():
    row = score_with_chain(
        symbol="RELIANCE",
        instrument_type=InstrumentType.STOCK,
        features=_features(),
        metrics=None,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
    )
    assert row.eligibility == Eligibility.EXCLUDE
    assert "IN12" in row.failed_rules
