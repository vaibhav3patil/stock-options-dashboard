"""Rank buy-side ideas by estimated profit potential (not a return guarantee)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

from app.models.schemas import BUY_ACTIONS, Eligibility, SymbolRow, TrendLabel

__all__ = [
    "BUY_ACTIONS",
    "BuyPriority",
    "profit_potential_score",
    "rank_buy_ideas",
    "rerank",
    "high_priority_ideas",
    "top_buys",
]


@dataclass(frozen=True)
class BuyPriority:
    rank: int
    band: str  # High | Medium | Low
    potential: float  # 0–100
    why: str
    aligned_pnl: Optional[float]  # to-expiry P&L / share if 1 ATR goes the right way
    row: SymbolRow


def _aligned_pnl(row: SymbolRow) -> Optional[float]:
    if row.suggestion_action == "BUY_CALL":
        return row.suggestion_pnl_plus_1atr
    if row.suggestion_action == "BUY_PUT":
        return row.suggestion_pnl_minus_1atr
    return None


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def profit_potential_score(row: SymbolRow) -> tuple[float, str]:
    """
    Higher = more realistic room to profit on the suggested long option.

    Weights last-close signals already on the row:
    cover (can expected move beat BE), 1-ATR directional P&L,
    readiness, composite score, ATR%, strike quality, trend/RS.
    """
    reasons: list[str] = []
    score = 0.0

    elig = row.eligibility
    if elig == Eligibility.NAKED_BUY_OK:
        score += 24
        reasons.append("ready to buy")
    elif elig == Eligibility.SPREAD_ONLY:
        score += 10
        reasons.append("IV rich — spread safer")
    elif elig == Eligibility.WATCH:
        score += 4
        reasons.append("watch only")

    cover = row.suggestion_move_cover_ratio
    if cover is not None:
        if cover >= 2.0:
            score += 26
            reasons.append(f"cover {cover:.2f}× (strong)")
        elif cover >= 1.5:
            score += 20
            reasons.append(f"cover {cover:.2f}×")
        elif cover >= 1.0:
            score += 10
            reasons.append(f"cover {cover:.2f}× (tight)")
        else:
            score -= 12
            reasons.append(f"cover {cover:.2f}× — expected move may miss BE")

    aligned = _aligned_pnl(row)
    premium = row.suggestion_premium
    if aligned is not None and premium and premium > 0:
        edge = aligned / premium
        if aligned > 0:
            score += min(18.0, 6.0 + edge * 10.0)
            reasons.append(f"1-ATR P&L ₹{aligned:.2f}/sh")
        else:
            score -= 8
            reasons.append("1-ATR move still below BE")

    if row.score is not None:
        score += row.score * 0.18

    if row.atr_pct is not None:
        score += min(8.0, max(0.0, row.atr_pct) * 1.6)
        if row.atr_pct >= 2.0:
            reasons.append(f"ATR {row.atr_pct:.1f}%")

    label = row.suggestion_label
    if label == "ATM":
        score += 8
    elif label == "ITM-1":
        score += 5
        reasons.append("slight ITM")
    elif label == "OTM-1":
        score -= 4
        reasons.append("OTM — harder BE")

    if row.squeeze:
        score += 4
        reasons.append("squeeze")

    rs = row.rs_20
    if rs is not None:
        if row.suggestion_action == "BUY_CALL" and rs > 2:
            score += 5
            reasons.append("RS leader")
        elif row.suggestion_action == "BUY_PUT" and rs < -2:
            score += 5
            reasons.append("RS laggard")

    if row.trend == TrendLabel.UP and row.suggestion_action == "BUY_CALL":
        score += 3
    elif row.trend == TrendLabel.DOWN and row.suggestion_action == "BUY_PUT":
        score += 3

    need = row.suggestion_required_move_pct
    if need is not None:
        if need <= 1.0:
            score += 4
        elif need >= 3.0:
            score -= 6
            reasons.append(f"needs {need:.1f}% to BE")

    ivr = row.iv_rank
    if ivr is not None:
        if ivr >= 70:
            score -= 14
            reasons.append(f"IV Rank {ivr:.0f}")
        elif ivr >= 50:
            score -= 6
        elif ivr <= 30:
            score += 6

    days = row.event_days
    if days is not None and days <= 5:
        score -= 12 if days <= 2 else 6
        reasons.append(f"event in {days}d")

    total = _clip(score)
    if not reasons:
        reasons.append("ranked from last-close cover, score, and 1-ATR P&L")
    return total, "; ".join(reasons[:4])


def _band(potential: float) -> str:
    if potential >= 70:
        return "High"
    if potential >= 50:
        return "Medium"
    return "Low"


def rank_buy_ideas(rows: list[SymbolRow]) -> list[BuyPriority]:
    """Return BUY CALL/PUT rows, best profit-potential first."""
    ideas: list[tuple[float, str, SymbolRow]] = []
    for row in rows:
        if not row.has_buy_idea():
            continue
        potential, why = profit_potential_score(row)
        ideas.append((potential, why, row))

    ideas.sort(key=lambda item: (-item[0], -(item[2].score or 0.0), item[2].symbol))
    ranked: list[BuyPriority] = []
    for i, (potential, why, row) in enumerate(ideas, start=1):
        ranked.append(
            BuyPriority(
                rank=i,
                band=_band(potential),
                potential=round(potential, 1),
                why=why,
                aligned_pnl=_aligned_pnl(row),
                row=row,
            )
        )
    return ranked


def rerank(items: list[BuyPriority]) -> list[BuyPriority]:
    """Re-number ranks 1…n without changing sort order."""
    return [replace(item, rank=i) for i, item in enumerate(items, start=1)]


def high_priority_ideas(rows: list[SymbolRow]) -> list[BuyPriority]:
    """High-band buy ideas only, re-ranked 1…n among High."""
    return rerank([item for item in rank_buy_ideas(rows) if item.band == "High"])


def top_buys(ranked: list[BuyPriority], *, limit: int = 5) -> list[BuyPriority]:
    return list(ranked[:limit])
