from __future__ import annotations

from app.config import LiquidityConfig, MoveVsPremiumConfig, RulesConfig, VolatilityConfig
from app.features.selection_overlays import EventInfo, OverlayInput, apply_selection_overlays
from app.models.schemas import Eligibility, InstrumentType
from app.scoring.engine import score_with_chain
from app.models.schemas import DataStatus


def _rules() -> RulesConfig:
    return RulesConfig(
        liquidity=LiquidityConfig(max_bid_ask_pct_of_mid=0.03, require_bid_ask=False),
        move_vs_premium=MoveVsPremiumConfig(min_expected_to_be_ratio=1.5, hold_days_assumption=2),
        volatility=VolatilityConfig(max_iv_rank_naked=50, rich_iv_rank=70),
    )


def test_ban_forces_exclude():
    out = apply_selection_overlays(
        Eligibility.NAKED_BUY_OK,
        OverlayInput(symbol="ABC", ban_list=["ABC"], move_ratio=2.0),
        _rules(),
    )
    assert out.eligibility == Eligibility.EXCLUDE
    assert "IN1" in out.failed


def test_earnings_inside_hold_is_spread_only():
    out = apply_selection_overlays(
        Eligibility.NAKED_BUY_OK,
        OverlayInput(
            symbol="AAA",
            event=EventInfo(kind="EARNINGS", date="2026-08-16", days_ahead=1),
            move_ratio=2.0,
        ),
        _rules(),
    )
    assert out.eligibility == Eligibility.SPREAD_ONLY
    assert "C1" in out.failed


def test_dividend_excludes():
    out = apply_selection_overlays(
        Eligibility.NAKED_BUY_OK,
        OverlayInput(
            symbol="AAA",
            event=EventInfo(kind="DIVIDEND", days_ahead=2),
            move_ratio=2.0,
        ),
        _rules(),
    )
    assert out.eligibility == Eligibility.EXCLUDE
    assert "C3" in out.failed


def test_rich_iv_rank_is_spread_only():
    out = apply_selection_overlays(
        Eligibility.NAKED_BUY_OK,
        OverlayInput(symbol="AAA", iv_rank=80, iv_history_n=40, move_ratio=1.6),
        _rules(),
    )
    assert out.eligibility == Eligibility.SPREAD_ONLY
    assert "V3" in out.failed


def test_wide_spread_excludes():
    out = apply_selection_overlays(
        Eligibility.NAKED_BUY_OK,
        OverlayInput(symbol="AAA", bid_ask_pct=0.08, move_ratio=2.0),
        _rules(),
    )
    assert out.eligibility == Eligibility.EXCLUDE
    assert "L3" in out.failed


def test_engine_ban_skips_suggestion():
    row = score_with_chain(
        symbol="XYZ",
        instrument_type=InstrumentType.STOCK,
        features=None,
        metrics=None,
        ohlc_status=DataStatus.OK,
        rules=_rules(),
        ban_list=["XYZ"],
    )
    assert row.eligibility == Eligibility.EXCLUDE
    assert row.in_fno_ban
    assert row.suggestion_action in {None, "NONE"}
