"""Hard/soft gates: F&O ban, events, IV Rank, known bid–ask."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from app.config import RulesConfig
from app.features.india_specific import is_fno_banned
from app.models.schemas import Eligibility


@dataclass
class EventInfo:
    kind: Optional[str] = None  # EARNINGS | DIVIDEND | SPLIT | BONUS | OTHER
    date: Optional[str] = None
    days_ahead: Optional[int] = None
    source: str = "none"


def rebase_event(event: EventInfo | None, as_of: date | str | None) -> EventInfo:
    """Recount days-to-event from a historical as-of date (no look-ahead)."""
    if event is None:
        return EventInfo(source="none")
    if as_of is None or not event.date:
        return event
    as_day = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of)[:10])
    try:
        event_day = datetime.strptime(str(event.date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return EventInfo(source=event.source or "none")
    days = (event_day - as_day).days
    if days < -1:
        return EventInfo(source=event.source or "none")
    return EventInfo(
        kind=event.kind,
        date=event.date,
        days_ahead=days,
        source=event.source,
    )


@dataclass
class OverlayInput:
    symbol: str
    ban_list: list[str] | None = None
    event: EventInfo | None = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    iv_history_n: int = 0
    bid_ask_pct: Optional[float] = None
    move_ratio: Optional[float] = None


@dataclass
class OverlayResult:
    eligibility: Eligibility | None = None  # None = keep prior
    failed: list[str] = None  # type: ignore[assignment]
    warnings: list[str] = None  # type: ignore[assignment]
    tags: list[str] = None  # type: ignore[assignment]
    why_suffix: str = ""

    def __post_init__(self) -> None:
        self.failed = self.failed or []
        self.warnings = self.warnings or []
        self.tags = self.tags or []


def apply_selection_overlays(
    current: Eligibility,
    overlay: OverlayInput,
    rules: RulesConfig,
) -> OverlayResult:
    """
    Ban / corp-action → EXCLUDE.
    Event inside hold window → cannot stay NAKED_BUY_OK.
    High IV Rank → SPREAD_ONLY unless cover is extra strong.
    Known wide bid–ask → EXCLUDE (L3).
    """
    out = OverlayResult()
    vol = rules.volatility
    liq = rules.liquidity
    hold = rules.move_vs_premium.hold_days_assumption
    min_ratio = rules.move_vs_premium.min_expected_to_be_ratio
    superior = (
        overlay.move_ratio is not None
        and overlay.move_ratio >= min_ratio * 1.25
    )

    if is_fno_banned(overlay.symbol, overlay.ban_list):
        out.eligibility = Eligibility.EXCLUDE
        out.failed.append("IN1")
        out.tags.append("FNO_BAN")
        out.why_suffix = "IN1 F&O ban — skip."
        return out

    event = overlay.event
    if event and event.days_ahead is not None:
        days = event.days_ahead
        kind = (event.kind or "EVENT").upper()
        out.tags.append(f"{kind}:{days}d")
        if kind in {"DIVIDEND", "SPLIT", "BONUS"} and days <= 5:
            out.eligibility = Eligibility.EXCLUDE
            out.failed.append("C3")
            out.why_suffix = f"Corporate action {kind} in {days}d — skip."
            return out
        if days <= hold:
            out.failed.append("C1")
            out.warnings.append(f"C1: {kind} in {days}d (inside hold window) — no naked buy")
            if current == Eligibility.NAKED_BUY_OK or current == Eligibility.SPREAD_ONLY:
                out.eligibility = Eligibility.SPREAD_ONLY
                out.why_suffix = f"C1 event in {days}d → SPREAD_ONLY (crush risk)."
        elif days <= 5 and (
            (overlay.iv_rank is not None and overlay.iv_rank >= vol.max_iv_rank_naked)
            or not superior
        ):
            out.warnings.append(f"C1: {kind} in {days}d — prefer defined risk")
            if current == Eligibility.NAKED_BUY_OK:
                out.eligibility = Eligibility.SPREAD_ONLY
                out.failed.append("C1")
                out.why_suffix = f"C1 event in {days}d with rich/unknown vol → SPREAD_ONLY."

    if overlay.iv_rank is not None:
        out.tags.append(f"IVR:{overlay.iv_rank:.0f}")
        if overlay.iv_rank >= vol.rich_iv_rank and not superior:
            out.warnings.append(f"V3: IV Rank {overlay.iv_rank:.0f} rich")
            if (out.eligibility or current) == Eligibility.NAKED_BUY_OK:
                out.eligibility = Eligibility.SPREAD_ONLY
                out.failed.append("V3")
                out.why_suffix = out.why_suffix or "V3 IV Rank rich → SPREAD_ONLY."
        elif overlay.iv_rank >= vol.max_iv_rank_naked and not superior:
            out.warnings.append(f"V3: IV Rank {overlay.iv_rank:.0f} above naked cap")
            if (out.eligibility or current) == Eligibility.NAKED_BUY_OK:
                out.eligibility = Eligibility.SPREAD_ONLY
                out.failed.append("V3")
                out.why_suffix = out.why_suffix or "V3 IV Rank above naked cap → SPREAD_ONLY."
    elif overlay.iv_history_n < 10:
        out.warnings.append("V3: IV Rank history thin — using IV vs HV only")
        out.tags.append("IVR_PENDING")

    if overlay.bid_ask_pct is not None:
        if overlay.bid_ask_pct > liq.max_bid_ask_pct_of_mid:
            out.failed.append("L3")
            out.eligibility = Eligibility.EXCLUDE
            out.why_suffix = (
                f"L3 bid–ask {overlay.bid_ask_pct:.1%} wider than "
                f"{liq.max_bid_ask_pct_of_mid:.1%} — skip."
            )
            return out
    else:
        out.warnings.append("L3: bid–ask not available on EOD bhav")

    return out
