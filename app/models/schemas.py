from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class InstrumentType(str, Enum):
    STOCK = "STOCK"
    INDEX = "INDEX"


class Eligibility(str, Enum):
    EXCLUDE = "EXCLUDE"
    WATCH = "WATCH"
    SPREAD_ONLY = "SPREAD_ONLY"
    NAKED_BUY_OK = "NAKED_BUY_OK"


class DirectionBias(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NEUTRAL = "NEUTRAL"


class DataStatus(str, Enum):
    OK = "OK"
    DATA_STALE = "DATA_STALE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    PENDING = "PENDING"


class TrendLabel(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    SIDEWAYS = "SIDEWAYS"
    UNKNOWN = "UNKNOWN"


BUY_ACTIONS = frozenset({"BUY_CALL", "BUY_PUT"})


class SymbolMeta(BaseModel):
    symbol: str
    instrument_type: InstrumentType = InstrumentType.STOCK


class SymbolRow(BaseModel):
    symbol: str
    instrument_type: InstrumentType = InstrumentType.STOCK
    spot: Optional[float] = None
    atr: Optional[float] = None
    atr_pct: Optional[float] = None
    hv_20: Optional[float] = None
    rs_5: Optional[float] = None
    rs_20: Optional[float] = None
    squeeze: Optional[bool] = None
    trend: TrendLabel = TrendLabel.UNKNOWN
    # Last market close (EOD) option metrics
    as_of_date: Optional[str] = None
    atm_strike: Optional[float] = None
    atm_iv: Optional[float] = None
    bid_ask_pct: Optional[float] = None
    oi_atm: Optional[float] = None
    volume_atm: Optional[float] = None
    pcr: Optional[float] = None
    expiry: Optional[str] = None
    dte: Optional[int] = None
    lot_size: Optional[int] = None
    premium_per_lot: Optional[float] = None
    move_vs_premium_ratio: Optional[float] = None
    chain_rows: list[dict[str, Any]] = Field(default_factory=list)
    score: Optional[float] = Field(
        default=None,
        description="Composite score 0–100 from last-close parameters.",
    )
    eligibility: Eligibility = Eligibility.WATCH
    direction_bias: DirectionBias = DirectionBias.NEUTRAL
    setup_tags: list[str] = Field(default_factory=list)
    failed_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    data_status: DataStatus = DataStatus.PENDING
    updated_at: Optional[datetime] = None
    why: str = "Awaiting scan."
    # Buy-side trade suggestion (CALL/PUT + strike)
    suggestion_action: Optional[str] = None  # BUY_CALL | BUY_PUT | NONE
    suggestion_summary: Optional[str] = None
    suggestion_strike: Optional[float] = None
    suggestion_option_type: Optional[str] = None  # CE | PE
    suggestion_label: Optional[str] = None  # ATM | ITM-1 | OTM-1
    suggestion_premium: Optional[float] = None
    suggestion_premium_per_lot: Optional[float] = None
    suggestion_max_lots: Optional[int] = None
    suggestion_rationale: Optional[str] = None
    suggestion_alternates: list[dict[str, Any]] = Field(default_factory=list)
    # Zerodha-style breakeven economics (primary strike)
    suggestion_breakeven: Optional[float] = None
    suggestion_required_move_pts: Optional[float] = None
    suggestion_required_move_pct: Optional[float] = None
    suggestion_expected_move_pts: Optional[float] = None
    suggestion_move_cover_ratio: Optional[float] = None
    suggestion_pnl_plus_1atr: Optional[float] = None
    suggestion_pnl_minus_1atr: Optional[float] = None
    suggestion_pnl_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    # Selection overlays (ban / event / IV Rank)
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    event_kind: Optional[str] = None
    event_date: Optional[str] = None
    event_days: Optional[int] = None
    in_fno_ban: bool = False

    def has_buy_idea(self) -> bool:
        return self.suggestion_action in BUY_ACTIONS and self.suggestion_strike is not None
