from __future__ import annotations

from app.features.priority import profit_potential_score, rank_buy_ideas, rerank
from app.models.schemas import Eligibility, SymbolRow, TrendLabel


def _idea(
    symbol: str,
    *,
    cover: float,
    score: float,
    eligibility: Eligibility = Eligibility.NAKED_BUY_OK,
    pnl: float = 5.0,
    atr_pct: float = 2.5,
    label: str = "ATM",
    action: str = "BUY_CALL",
) -> SymbolRow:
    return SymbolRow(
        symbol=symbol,
        eligibility=eligibility,
        score=score,
        atr_pct=atr_pct,
        trend=TrendLabel.UP,
        rs_20=4.0,
        suggestion_action=action,
        suggestion_strike=1000,
        suggestion_option_type="CE" if action == "BUY_CALL" else "PE",
        suggestion_label=label,
        suggestion_premium=10.0,
        suggestion_move_cover_ratio=cover,
        suggestion_required_move_pct=1.2,
        suggestion_pnl_plus_1atr=pnl if action == "BUY_CALL" else -10.0,
        suggestion_pnl_minus_1atr=pnl if action == "BUY_PUT" else -10.0,
    )


def test_higher_cover_ranks_first():
    weak = _idea("WEAK", cover=0.7, score=70, pnl=-4.0, eligibility=Eligibility.WATCH)
    strong = _idea("STRONG", cover=2.1, score=85, pnl=8.0)
    ranked = rank_buy_ideas([weak, strong])
    assert [item.row.symbol for item in ranked] == ["STRONG", "WEAK"]
    assert ranked[0].band == "High"
    assert ranked[0].rank == 1


def test_ignores_rows_without_buy_idea():
    skip = SymbolRow(symbol="NONE", suggestion_action="NONE")
    ranked = rank_buy_ideas([skip, _idea("AAA", cover=1.6, score=80)])
    assert [item.row.symbol for item in ranked] == ["AAA"]
    assert not skip.has_buy_idea()
    assert _idea("AAA", cover=1.6, score=80).has_buy_idea()


def test_naked_beats_watch_when_cover_similar():
    watch = _idea("WATCH", cover=1.6, score=80, eligibility=Eligibility.WATCH)
    ready = _idea("READY", cover=1.6, score=80, eligibility=Eligibility.NAKED_BUY_OK)
    ranked = rank_buy_ideas([watch, ready])
    assert ranked[0].row.symbol == "READY"


def test_potential_is_bounded():
    score, _ = profit_potential_score(_idea("AAA", cover=5.0, score=100, pnl=40.0))
    assert 0 <= score <= 100


def test_high_priority_excludes_watch_and_reranks():
    from app.features.priority import high_priority_ideas, top_buys

    high_a = _idea("AAA", cover=2.2, score=90, pnl=8.0)
    high_b = _idea("BBB", cover=2.0, score=88, pnl=6.0)
    watch = _idea("CCC", cover=0.6, score=60, pnl=-5.0, eligibility=Eligibility.WATCH)
    high = high_priority_ideas([watch, high_b, high_a])
    assert [item.row.symbol for item in high] == ["AAA", "BBB"]
    assert [item.rank for item in high] == [1, 2]
    assert [item.row.symbol for item in top_buys(high, limit=5)] == ["AAA", "BBB"]
    assert [item.rank for item in rerank(list(reversed(high)))] == [1, 2]
