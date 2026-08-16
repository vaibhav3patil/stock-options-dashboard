"""Buy / sell / stop-loss / profit-margin plan for a long option."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.features.market_context import MarketContext, get_market_context
from app.models.schemas import SymbolRow


@dataclass
class TradePlan:
    action: str
    regime: str
    # Option (what you actually trade)
    option_buy: float
    option_sell: float
    option_stop: float
    profit_per_share: float
    risk_per_share: float
    profit_margin_pct: float
    reward_risk: float
    profit_per_lot: Optional[float]
    risk_per_lot: Optional[float]
    # Underlying reference levels
    spot: Optional[float]
    stock_stop: Optional[float]
    stock_target: Optional[float]
    note: str

    def to_row(self) -> dict[str, Any]:
        return {
            "Buy": round(self.option_buy, 2),
            "Sell": round(self.option_sell, 2),
            "Stop": round(self.option_stop, 2),
            "Margin %": round(self.profit_margin_pct, 1),
            "R:R": round(self.reward_risk, 2),
            "P&L / lot": None
            if self.profit_per_lot is None
            else round(self.profit_per_lot, 0),
            "Risk / lot": None
            if self.risk_per_lot is None
            else round(self.risk_per_lot, 0),
            "Stock SL": None if self.stock_stop is None else round(self.stock_stop, 2),
            "Stock tgt": None if self.stock_target is None else round(self.stock_target, 2),
        }


def build_trade_plan(
    row: SymbolRow,
    context: MarketContext | None = None,
) -> Optional[TradePlan]:
    """
    Long-option plan from last-close premium.

    Buy = EOD premium.
    Stop = premium × (1 − regime sl_frac), floored so risk is defined.
    Sell = buy + risk × regime reward multiple (book in a cautious tape).
    If 1-ATR expiry P&L is smaller than that target, cap sell at buy + that P&L
    so we do not invent a target the stock's typical range cannot fund.
    """
    context = context or get_market_context()
    action = getattr(row, "suggestion_action", None) or "NONE"
    premium = getattr(row, "suggestion_premium", None)
    if action not in {"BUY_CALL", "BUY_PUT"} or premium is None or premium <= 0:
        return None

    buy = float(premium)
    risk = buy * context.sl_frac
    stop = max(0.05, buy - risk)
    raw_target = buy + risk * context.reward_multiple
    aligned = (
        getattr(row, "suggestion_pnl_plus_1atr", None)
        if action == "BUY_CALL"
        else getattr(row, "suggestion_pnl_minus_1atr", None)
    )
    if aligned is not None and 0 < float(aligned):
        atr_target = buy + float(aligned)
        # Book 1.5R when the typical day can fund it; otherwise cap at 1-ATR P&L.
        sell = raw_target if atr_target >= raw_target else atr_target
    else:
        sell = raw_target

    profit = sell - buy
    if profit <= 0:
        # Still publish a defined-risk plan; margin may be small/negative
        sell = buy + risk * max(1.0, context.reward_multiple * 0.8)
        profit = sell - buy

    margin_pct = (profit / buy) * 100.0
    rr = profit / risk if risk > 0 else 0.0
    lot = getattr(row, "suggestion_premium_per_lot", None)
    lots_mult = None
    if lot is not None and buy > 0:
        qty = lot / buy
        lots_mult = qty

    spot = row.spot
    atr = row.atr
    be = getattr(row, "suggestion_breakeven", None)
    exp = getattr(row, "suggestion_expected_move_pts", None)
    stock_stop = stock_target = None
    if spot is not None and atr is not None and atr > 0:
        sl_pts = atr * context.underlying_atr_stop
        if action == "BUY_CALL":
            stock_stop = spot - sl_pts
            stock_target = max(be or spot, spot + (exp or atr))
        else:
            stock_stop = spot + sl_pts
            stock_target = min(be or spot, spot - (exp or atr))

    return TradePlan(
        action=action,
        regime=context.regime,
        option_buy=buy,
        option_sell=sell,
        option_stop=stop,
        profit_per_share=profit,
        risk_per_share=risk,
        profit_margin_pct=margin_pct,
        reward_risk=rr,
        profit_per_lot=None if lots_mult is None else profit * lots_mult,
        risk_per_lot=None if lots_mult is None else risk * lots_mult,
        spot=spot,
        stock_stop=stock_stop,
        stock_target=stock_target,
        note=context.note,
    )
