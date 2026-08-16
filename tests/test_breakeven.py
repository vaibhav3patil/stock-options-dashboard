from __future__ import annotations

from app.features.trade_suggestions import (
    breakeven_economics,
    call_breakeven,
    call_pnl_to_expiry,
    put_breakeven,
    put_pnl_to_expiry,
)


def test_call_breakeven_zerodha():
    # Varsity example style: strike 2050, premium 6.35 → BE 2056.35
    assert abs(call_breakeven(2050, 6.35) - 2056.35) < 1e-9


def test_put_breakeven_zerodha():
    # Varsity: strike 18400, premium 315 → BE 18085
    assert put_breakeven(18400, 315) == 18085


def test_call_pnl_formula():
    assert call_pnl_to_expiry(2023, 2050, 6.35) == -6.35
    assert abs(call_pnl_to_expiry(2072, 2050, 6.35) - 15.65) < 1e-9
    assert abs(call_pnl_to_expiry(2055, 2050, 6.35) - (-1.35)) < 1e-9


def test_put_pnl_formula():
    assert put_pnl_to_expiry(16510, 18400, 315) == 1575
    assert put_pnl_to_expiry(19660, 18400, 315) == -315
    assert put_pnl_to_expiry(18085, 18400, 315) == 0


def test_breakeven_economics_call():
    econ = breakeven_economics(
        option_type="CE",
        spot=1310,
        strike=1320,
        premium=16.15,
        atr=20,
        hold_days=2,
    )
    assert abs(econ["breakeven"] - 1336.15) < 1e-9
    assert abs(econ["required_move_pts"] - 26.15) < 1e-9
    assert econ["required_move_pct"] is not None and econ["required_move_pct"] > 0
    assert econ["expected_move_pts"] is not None
    assert econ["move_cover_ratio"] is not None
    assert len(econ["pnl_scenarios"]) >= 3
