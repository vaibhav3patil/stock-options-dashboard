from __future__ import annotations

from app.models.schemas import Eligibility, SymbolRow
from app.scanner import filter_scan_rows


def _row(symbol: str, *, eligibility: Eligibility, score: float | None, action: str) -> SymbolRow:
    return SymbolRow(
        symbol=symbol,
        eligibility=eligibility,
        score=score,
        suggestion_action=action,
    )


def test_filter_matches_table_and_detail():
    rows = [
        _row("AAA", eligibility=Eligibility.NAKED_BUY_OK, score=100, action="BUY_CALL"),
        _row("BBB", eligibility=Eligibility.NAKED_BUY_OK, score=80, action="BUY_PUT"),
        _row("CCC", eligibility=Eligibility.WATCH, score=100, action="BUY_CALL"),
        _row("DDD", eligibility=Eligibility.NAKED_BUY_OK, score=None, action="BUY_CALL"),
    ]
    visible = filter_scan_rows(
        rows,
        eligibility_filter=["NAKED_BUY_OK"],
        min_score=100,
    )
    assert [r.symbol for r in visible] == ["AAA"]


def test_missing_score_does_not_pass_min_score():
    rows = [_row("AAA", eligibility=Eligibility.WATCH, score=None, action="NONE")]
    assert filter_scan_rows(rows, min_score=1) == []
