from __future__ import annotations

from app.features.market_context import MarketContext
from app.features.trade_plan import build_trade_plan
from app.models.schemas import SymbolRow


def _ctx(**kwargs) -> MarketContext:
    base = dict(
        as_of="2026-08-14",
        regime="CAUTIOUS",
        headline="t",
        nifty="n",
        global_note="g",
        sl_frac=0.32,
        reward_multiple=1.5,
        underlying_atr_stop=0.8,
        note="n",
    )
    base.update(kwargs)
    return MarketContext(**base)


def test_call_plan_buy_sell_stop_margin():
    row = SymbolRow(
        symbol="AAA",
        spot=1000,
        atr=20,
        suggestion_action="BUY_CALL",
        suggestion_premium=10.0,
        suggestion_premium_per_lot=5000,
        suggestion_breakeven=1010,
        suggestion_expected_move_pts=28,
        suggestion_pnl_plus_1atr=8.0,
    )
    plan = build_trade_plan(row, _ctx())
    assert plan is not None
    assert plan.option_buy == 10.0
    assert abs(plan.option_stop - 6.8) < 1e-9  # 32% stop
    assert abs(plan.option_sell - 14.8) < 1e-9  # 1.5R
    assert abs(plan.profit_margin_pct - 48.0) < 1e-6
    assert abs(plan.reward_risk - 1.5) < 1e-6
    assert plan.stock_stop is not None and plan.stock_stop < 1000
    assert plan.stock_target is not None and plan.stock_target >= 1010


def test_no_plan_without_premium():
    assert build_trade_plan(SymbolRow(symbol="X", suggestion_action="NONE")) is None
