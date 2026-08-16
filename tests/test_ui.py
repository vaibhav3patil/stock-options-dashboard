from __future__ import annotations

import pandas as pd

from app.models.schemas import Eligibility, SymbolRow
from app.scanner import rows_to_dataframe
from app.ui import eligibility_label, friendly_scenarios, scanner_display_frame


def test_eligibility_labels():
    assert eligibility_label(Eligibility.NAKED_BUY_OK) == "Ready to buy"
    assert eligibility_label("EXCLUDE") == "Skip"


def test_scanner_display_frame_columns():
    row = SymbolRow(
        symbol="AAA",
        eligibility=Eligibility.NAKED_BUY_OK,
        score=88,
        suggestion_action="BUY_CALL",
        suggestion_breakeven=100.0,
        suggestion_required_move_pct=1.2,
        suggestion_move_cover_ratio=1.5,
        why="trend up",
    )
    display = scanner_display_frame(rows_to_dataframe([row]))
    assert list(display.columns)[:4] == ["Symbol", "Idea", "Strike", "CE/PE"]
    assert display.iloc[0]["Readiness"] == "Ready to buy"
    assert display.iloc[0]["Idea"] == "BUY CALL"


def test_trade_idea_panel_includes_lot_size():
    from app.ui import trade_idea_panel_html

    row = SymbolRow(
        symbol="AAA",
        lot_size=500,
        suggestion_action="BUY_CALL",
        suggestion_strike=1000,
        suggestion_option_type="CE",
        suggestion_label="ATM",
        suggestion_premium=10.0,
        suggestion_premium_per_lot=5000,
        suggestion_max_lots=2,
    )
    html = trade_idea_panel_html(row)
    assert "Lot size" in html
    assert "500" in html


def test_compare_top5_shows_all_names():
    from app.features.priority import BuyPriority
    from app.features.trade_plan import build_trade_plan
    from app.ui import compare_top5_html

    rows = []
    for i, (sym, side, strike, prem) in enumerate(
        [
            ("RELIANCE", "BUY_CALL", 1400, 22.0),
            ("ICICIBANK", "BUY_PUT", 1410, 12.5),
            ("TCS", "BUY_CALL", 3200, 40.0),
        ],
        start=1,
    ):
        row = SymbolRow(
            symbol=sym,
            lot_size=700,
            eligibility=Eligibility.NAKED_BUY_OK,
            suggestion_action=side,
            suggestion_strike=strike,
            suggestion_option_type="CE" if "CALL" in side else "PE",
            suggestion_label="ATM",
            suggestion_premium=prem,
            suggestion_premium_per_lot=700 * prem,
            suggestion_move_cover_ratio=1.2 + i * 0.2,
            suggestion_breakeven=strike + prem if "CALL" in side else strike - prem,
            expiry="2026-08-25",
            dte=11,
            as_of_date="2026-08-14",
        )
        rows.append(
            BuyPriority(
                rank=i,
                band="High",
                potential=80 - i,
                why=f"cover and {side}",
                aligned_pnl=4.0,
                row=row,
            )
        )
    plans = {item.row.symbol: build_trade_plan(item.row) for item in rows}
    html = compare_top5_html(rows, plans)
    assert "RELIANCE" in html
    assert "ICICIBANK" in html
    assert "TCS" in html
    assert "BUY CALL" in html
    assert "BUY PUT" in html
    assert "Cost / lot" in html
    assert "12.50" in html or "12.5" in html
    assert "Expiry 25 Aug" in html
    assert '<th class="metric">Expiry</th>' not in html
    assert '<th class="metric">Session</th>' not in html


def test_friendly_scenarios():
    df = friendly_scenarios(
        [{"scenario": "spot", "spot": 100, "pnl_per_share": -5}]
    )
    assert df.iloc[0]["What if"] == "If stock stays at last close"
