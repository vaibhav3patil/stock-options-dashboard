"""Buy-side trade suggestions: CALL/PUT + ATM / ITM-1 / OTM-1 strike ranker."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import MoveVsPremiumConfig, RiskConfig
from app.features.option_metrics import OptionMetrics, compute_move_vs_premium
from app.models.schemas import DirectionBias, Eligibility


@dataclass
class StrikeCandidate:
    strike: float
    option_type: str  # CE | PE
    moneyness: str  # ATM | ITM | OTM
    label: str  # ATM | ITM-1 | OTM-1
    premium: float
    oi: float
    volume: float
    intrinsic: float
    move_vs_premium_ratio: Optional[float]
    premium_per_lot: Optional[float]
    rank_score: float = 0.0
    breakeven: Optional[float] = None
    required_move_pts: Optional[float] = None
    required_move_pct: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "strike": self.strike,
            "option_type": self.option_type,
            "moneyness": self.moneyness,
            "label": self.label,
            "premium": round(self.premium, 2),
            "oi": self.oi,
            "volume": self.volume,
            "intrinsic": round(self.intrinsic, 2),
            "breakeven": None if self.breakeven is None else round(self.breakeven, 2),
            "required_move_pts": None
            if self.required_move_pts is None
            else round(self.required_move_pts, 2),
            "required_move_pct": None
            if self.required_move_pct is None
            else round(self.required_move_pct, 2),
            "move_vs_premium_ratio": None
            if self.move_vs_premium_ratio is None
            else round(self.move_vs_premium_ratio, 2),
            "premium_per_lot": None
            if self.premium_per_lot is None
            else round(self.premium_per_lot, 0),
            "rank_score": round(self.rank_score, 1),
        }


@dataclass
class TradeSuggestion:
    action: str = "NONE"  # BUY_CALL | BUY_PUT | NONE
    objective: str = "SPECULATION_BUY"
    symbol: str = ""
    expiry: Optional[str] = None
    dte: Optional[int] = None
    spot: Optional[float] = None
    atr: Optional[float] = None
    primary: Optional[StrikeCandidate] = None
    alternates: list[StrikeCandidate] = field(default_factory=list)
    rationale: str = ""
    max_lots: Optional[int] = None
    # Zerodha-style economics for primary strike
    breakeven: Optional[float] = None
    required_move_pts: Optional[float] = None
    required_move_pct: Optional[float] = None
    expected_move_pts: Optional[float] = None
    move_cover_ratio: Optional[float] = None  # expected / required
    pnl_at_plus_1atr: Optional[float] = None  # per share, to-expiry ideal
    pnl_at_minus_1atr: Optional[float] = None
    pnl_scenarios: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "objective": self.objective,
            "symbol": self.symbol,
            "expiry": self.expiry,
            "dte": self.dte,
            "spot": self.spot,
            "atr": self.atr,
            "primary": None if self.primary is None else self.primary.to_dict(),
            "alternates": [a.to_dict() for a in self.alternates],
            "rationale": self.rationale,
            "max_lots": self.max_lots,
            "breakeven": self.breakeven,
            "required_move_pts": self.required_move_pts,
            "required_move_pct": self.required_move_pct,
            "expected_move_pts": self.expected_move_pts,
            "move_cover_ratio": self.move_cover_ratio,
            "pnl_at_plus_1atr": self.pnl_at_plus_1atr,
            "pnl_at_minus_1atr": self.pnl_at_minus_1atr,
            "pnl_scenarios": self.pnl_scenarios,
        }

    @property
    def summary(self) -> str:
        if self.action == "NONE" or self.primary is None:
            return "No buy suggestion"
        p = self.primary
        be = f" · BE {self.breakeven:.2f}" if self.breakeven is not None else ""
        req = (
            f" · need {self.required_move_pts:.1f} pts ({self.required_move_pct:.2f}%)"
            if self.required_move_pts is not None and self.required_move_pct is not None
            else ""
        )
        return (
            f"{self.action.replace('_', ' ')} {self.symbol} "
            f"{p.strike:.0f} {p.option_type} ({p.label}) · "
            f"Exp {self.expiry or '—'} · Prem ₹{p.premium:.2f} · "
            f"Lot ₹{(p.premium_per_lot or 0):.0f}{be}{req}"
        )


def call_breakeven(strike: float, premium: float) -> float:
    """Zerodha: Call BE = Strike + Premium."""
    return strike + premium


def put_breakeven(strike: float, premium: float) -> float:
    """Zerodha: Put BE = Strike − Premium."""
    return strike - premium


def call_pnl_to_expiry(spot: float, strike: float, premium: float) -> float:
    """P&L = max(0, Spot − Strike) − Premium."""
    return max(0.0, spot - strike) - premium


def put_pnl_to_expiry(spot: float, strike: float, premium: float) -> float:
    """P&L = max(0, Strike − Spot) − Premium."""
    return max(0.0, strike - spot) - premium


def breakeven_economics(
    *,
    option_type: str,
    spot: float,
    strike: float,
    premium: float,
    atr: Optional[float] = None,
    hold_days: int = 2,
) -> dict[str, Any]:
    """
    Breakeven + required move + ideal to-expiry P&L at ±1 ATR.
    Formulas from Zerodha Varsity (call/put buying chapters).
    """
    if option_type == "CE":
        be = call_breakeven(strike, premium)
        required_pts = be - spot
        pnl_fn = call_pnl_to_expiry
    else:
        be = put_breakeven(strike, premium)
        required_pts = spot - be
        pnl_fn = put_pnl_to_expiry

    required_pct = (required_pts / spot) * 100.0 if spot else None
    expected = None
    cover = None
    if atr is not None and atr > 0:
        expected = atr * math.sqrt(max(hold_days, 1))
        if required_pts > 0:
            cover = expected / required_pts

    scenarios: list[dict[str, Any]] = []
    pnl_plus = pnl_minus = None
    if atr is not None and atr > 0:
        for label, s in (
            ("spot", spot),
            ("+1 ATR", spot + atr),
            ("-1 ATR", spot - atr),
            ("breakeven", be),
        ):
            pnl = pnl_fn(s, strike, premium)
            scenarios.append(
                {
                    "scenario": label,
                    "spot": round(s, 2),
                    "pnl_per_share": round(pnl, 2),
                }
            )
        pnl_plus = pnl_fn(spot + atr, strike, premium)
        pnl_minus = pnl_fn(spot - atr, strike, premium)

    return {
        "breakeven": be,
        "required_move_pts": required_pts,
        "required_move_pct": required_pct,
        "expected_move_pts": expected,
        "move_cover_ratio": cover,
        "pnl_at_plus_1atr": pnl_plus,
        "pnl_at_minus_1atr": pnl_minus,
        "pnl_scenarios": scenarios,
    }


def _moneyness(spot: float, strike: float, option_type: str) -> tuple[str, float]:
    if option_type == "CE":
        intrinsic = max(0.0, spot - strike)
        if abs(strike - spot) / spot < 0.0025:
            return "ATM", intrinsic
        if strike < spot:
            return "ITM", intrinsic
        return "OTM", intrinsic
    intrinsic = max(0.0, strike - spot)
    if abs(strike - spot) / spot < 0.0025:
        return "ATM", intrinsic
    if strike > spot:
        return "ITM", intrinsic
    return "OTM", intrinsic


def _side_cols(option_type: str) -> tuple[str, str, str]:
    if option_type == "CE":
        return "ce_ltp", "ce_oi", "ce_volume"
    return "pe_ltp", "pe_oi", "pe_volume"


def _candidate_strikes(
    ordered: list[float],
    atm: float,
    *,
    option_type: str,
) -> list[tuple[str, float]]:
    """Return labeled strikes: ATM, ITM-1, OTM-1 when available."""
    if atm not in ordered:
        atm = min(ordered, key=lambda s: abs(s - atm))
    idx = ordered.index(atm)
    out: list[tuple[str, float]] = [("ATM", atm)]
    if option_type == "CE":
        if idx - 1 >= 0:
            out.append(("ITM-1", ordered[idx - 1]))
        if idx + 1 < len(ordered):
            out.append(("OTM-1", ordered[idx + 1]))
    else:
        if idx + 1 < len(ordered):
            out.append(("ITM-1", ordered[idx + 1]))
        if idx - 1 >= 0:
            out.append(("OTM-1", ordered[idx - 1]))
    # de-dupe preserving order
    seen: set[float] = set()
    unique: list[tuple[str, float]] = []
    for label, strike in out:
        if strike in seen:
            continue
        seen.add(strike)
        unique.append((label, strike))
    return unique


def _rank_score(
    *,
    label: str,
    move_ratio: Optional[float],
    oi: float,
    volume: float,
    moneyness: str,
    min_ratio: float,
) -> float:
    score = 40.0
    # Prefer ATM, then ITM, penalize OTM lottery
    if label == "ATM":
        score += 20
    elif label == "ITM-1":
        score += 15
    elif label == "OTM-1":
        score += 5
    if moneyness == "OTM":
        score -= 8
    if move_ratio is not None:
        if move_ratio >= min_ratio:
            score += min(25.0, move_ratio * 8.0)
        else:
            score -= 15.0
    # Liquidity soft boost (log-ish via capped add)
    score += min(10.0, (oi / 1_000_000.0) * 2.0)
    score += min(10.0, (volume / 5_000.0) * 2.0)
    return max(0.0, min(100.0, score))


def build_trade_suggestion(
    *,
    symbol: str,
    bias: DirectionBias,
    eligibility: Eligibility,
    metrics: OptionMetrics,
    atr: Optional[float],
    move_cfg: MoveVsPremiumConfig | None = None,
    risk: RiskConfig | None = None,
) -> TradeSuggestion:
    """
    Speculative long-option suggestion only (BUY CALL / BUY PUT).
    No sell/write recommendations.
    """
    move_cfg = move_cfg or MoveVsPremiumConfig()
    risk = risk or RiskConfig()

    empty = TradeSuggestion(
        action="NONE",
        symbol=symbol,
        expiry=metrics.expiry,
        dte=metrics.dte,
        rationale="No directional buy suggestion.",
    )

    if bias == DirectionBias.NEUTRAL:
        empty.rationale = "Neutral bias — no CALL/PUT buy suggestion."
        return empty
    if eligibility == Eligibility.EXCLUDE:
        empty.rationale = "Excluded — no buy suggestion."
        return empty
    if metrics.status != "OK" or not metrics.chain_rows:
        empty.rationale = "Missing EOD strike window — cannot pick strike."
        return empty

    spot = metrics.underlying
    if spot is None:
        empty.rationale = "Missing spot — cannot pick strike."
        return empty

    option_type = "CE" if bias == DirectionBias.CALL else "PE"
    action = "BUY_CALL" if bias == DirectionBias.CALL else "BUY_PUT"
    ltp_col, oi_col, vol_col = _side_cols(option_type)

    rows = metrics.chain_rows
    ordered = sorted({float(r["strike"]) for r in rows if r.get("strike") is not None})
    if not ordered:
        empty.rationale = "No strikes in ATM window."
        return empty

    atm = metrics.atm_strike or min(ordered, key=lambda s: abs(s - spot))
    by_strike = {float(r["strike"]): r for r in rows if r.get("strike") is not None}

    candidates: list[StrikeCandidate] = []
    for label, strike in _candidate_strikes(ordered, atm, option_type=option_type):
        row = by_strike.get(strike)
        if not row:
            continue
        premium = row.get(ltp_col)
        if premium is None or float(premium) <= 0:
            continue
        premium_f = float(premium)
        oi = float(row.get(oi_col) or 0.0)
        volume = float(row.get(vol_col) or 0.0)
        moneyness, intrinsic = _moneyness(spot, strike, option_type)
        _, _, ratio = compute_move_vs_premium(
            atr=atr,
            premium=premium_f,
            spread_pct=None,
            move_cfg=move_cfg,
        )
        # Anti-lottery: skip OTM if move/premium badly fails and intrinsic is 0
        if (
            moneyness == "OTM"
            and ratio is not None
            and ratio < move_cfg.min_expected_to_be_ratio * 0.75
        ):
            continue

        lot = metrics.lot_size
        prem_lot = float(lot) * premium_f if lot else None

        econ = breakeven_economics(
            option_type=option_type,
            spot=spot,
            strike=strike,
            premium=premium_f,
            atr=atr,
            hold_days=move_cfg.hold_days_assumption,
        )

        rank = _rank_score(
            label=label,
            move_ratio=ratio,
            oi=oi,
            volume=volume,
            moneyness=moneyness,
            min_ratio=move_cfg.min_expected_to_be_ratio,
        )
        if prem_lot is not None and prem_lot > risk.max_premium_per_trade_inr:
            rank -= 20
        # Prefer strikes where expected move covers required move to BE
        cover = econ.get("move_cover_ratio")
        if cover is not None:
            if cover >= move_cfg.min_expected_to_be_ratio:
                rank += 8
            elif cover < 1.0:
                rank -= 12

        candidates.append(
            StrikeCandidate(
                strike=strike,
                option_type=option_type,
                moneyness=moneyness,
                label=label,
                premium=premium_f,
                oi=oi,
                volume=volume,
                intrinsic=intrinsic,
                move_vs_premium_ratio=ratio,
                premium_per_lot=prem_lot,
                rank_score=rank,
                breakeven=econ["breakeven"],
                required_move_pts=econ["required_move_pts"],
                required_move_pct=econ["required_move_pct"],
            )
        )

    if not candidates:
        empty.rationale = f"{action} bias but no liquid ATM/ITM-1/OTM-1 strike passed filters."
        return empty

    candidates.sort(key=lambda c: c.rank_score, reverse=True)
    primary = candidates[0]
    alternates = candidates[1:3]

    max_lots = None
    if primary.premium_per_lot and primary.premium_per_lot > 0:
        max_lots = max(1, int(risk.max_premium_per_trade_inr // primary.premium_per_lot))

    primary_econ = breakeven_economics(
        option_type=primary.option_type,
        spot=spot,
        strike=primary.strike,
        premium=primary.premium,
        atr=atr,
        hold_days=move_cfg.hold_days_assumption,
    )

    note = ""
    if eligibility == Eligibility.SPREAD_ONLY:
        note = " IV rich → prefer a debit spread around this strike rather than naked buy."
    elif eligibility == Eligibility.WATCH:
        note = " Setup/move incomplete — suggestion is tentative."

    cover = primary_econ.get("move_cover_ratio")
    cover_txt = f"{cover:.2f}×" if cover is not None else "n/a"
    rationale = (
        f"{action.replace('_', ' ')} for speculative directional buy. "
        f"Primary {primary.label} {primary.strike:.0f} {primary.option_type} "
        f"({primary.moneyness}). Breakeven {primary_econ['breakeven']:.2f} "
        f"(need {primary_econ['required_move_pts']:.1f} pts / "
        f"{primary_econ['required_move_pct']:.2f}%); "
        f"expected/required≈{cover_txt}."
        f"{note}"
    )

    return TradeSuggestion(
        action=action,
        objective="SPECULATION_BUY",
        symbol=symbol,
        expiry=metrics.expiry,
        dte=metrics.dte,
        spot=spot,
        atr=atr,
        primary=primary,
        alternates=alternates,
        rationale=rationale.strip(),
        max_lots=max_lots,
        breakeven=primary_econ["breakeven"],
        required_move_pts=primary_econ["required_move_pts"],
        required_move_pct=primary_econ["required_move_pct"],
        expected_move_pts=primary_econ["expected_move_pts"],
        move_cover_ratio=primary_econ["move_cover_ratio"],
        pnl_at_plus_1atr=primary_econ["pnl_at_plus_1atr"],
        pnl_at_minus_1atr=primary_econ["pnl_at_minus_1atr"],
        pnl_scenarios=primary_econ["pnl_scenarios"],
    )
