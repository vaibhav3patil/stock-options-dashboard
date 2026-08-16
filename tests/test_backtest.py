from __future__ import annotations

import pandas as pd

from app.features.backtest import (
    STRICT_DESK,
    SessionQuote,
    lookup_option_quote,
    passes_strict_desk,
    simulate_hold,
)
from app.models.schemas import SymbolRow
from app.features.selection_overlays import EventInfo, rebase_event
from app.scanner import slice_ohlc_as_of


def test_simulate_hold_stop_before_target_same_day():
    outcome, px, day = simulate_hold(
        entry=10.0,
        stop=7.0,
        target=15.0,
        path=[SessionQuote("2026-08-14", last=12.0, high=16.0, low=6.5, close=12.0)],
    )
    assert outcome == "STOP"
    assert px == 7.0
    assert day == "2026-08-14"


def test_simulate_hold_hits_target():
    outcome, px, _ = simulate_hold(
        entry=10.0,
        stop=7.0,
        target=15.0,
        path=[SessionQuote("2026-08-14", last=12.0, high=12.5, low=11.0, close=12.0)],
    )
    assert outcome == "TIME"
    outcome, px, _ = simulate_hold(
        entry=10.0,
        stop=7.0,
        target=15.0,
        path=[SessionQuote("2026-08-14", last=16.0, high=16.2, low=11.0, close=16.0)],
    )
    assert outcome == "TARGET"
    assert px == 15.0


def test_lookup_option_quote():
    bhav = pd.DataFrame(
        [
            {
                "TckrSymb": "ICICIBANK",
                "FinInstrmTp": "STO",
                "OptnTp": "PE",
                "StrkPric": 1410.0,
                "XpryDt": "2026-08-25",
                "LastPric": 12.5,
                "ClsPric": 12.05,
                "HghPric": 14.0,
                "LwPric": 11.0,
                "_trade_date": "2026-08-14",
            }
        ]
    )
    q = lookup_option_quote(
        bhav,
        symbol="ICICIBANK",
        strike=1410,
        option_type="PE",
        expiry="2026-08-25",
    )
    assert q is not None
    assert q.last == 12.5
    assert q.low == 11.0


def test_slice_ohlc_drops_future_bars():
    idx = pd.to_datetime(["2026-08-12", "2026-08-13", "2026-08-14"])
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)
    sliced = slice_ohlc_as_of(df, "2026-08-13")
    assert list(sliced["Close"]) == [1.0, 2.0]


def test_close_only_stop_ignores_intraday_low():
    outcome, px, _ = simulate_hold(
        entry=10.0,
        stop=7.0,
        target=15.0,
        path=[SessionQuote("2026-08-14", last=9.0, high=12.0, low=6.0, close=9.0)],
        stop_on="close",
    )
    assert outcome == "TIME"
    assert px == 9.0


def test_strict_desk_rejects_otm_and_thin_cover():
    weak = SymbolRow(
        symbol="AAA",
        suggestion_label="OTM-1",
        suggestion_move_cover_ratio=1.1,
        iv_rank=40,
    )
    strong = SymbolRow(
        symbol="BBB",
        suggestion_label="ATM",
        suggestion_move_cover_ratio=1.8,
        iv_rank=30,
    )
    assert passes_strict_desk(weak, STRICT_DESK) is False
    assert passes_strict_desk(strong, STRICT_DESK) is True


def test_rebase_event_from_signal_date():
    info = EventInfo(kind="EARNINGS", date="2026-08-20", days_ahead=5, source="csv")
    out = rebase_event(info, "2026-08-13")
    assert out.days_ahead == 7
    past = rebase_event(info, "2026-08-25")
    assert past.days_ahead is None
