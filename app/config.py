from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app import PROJECT_ROOT


class UniverseConfig(BaseModel):
    csv_path: str = "fno_only_stocks.csv"
    index_symbols: list[str] = Field(default_factory=list)
    liquid_subset: list[str] = Field(default_factory=list)


class LiquidityConfig(BaseModel):
    min_option_volume_atm_window: int = 500
    min_oi_atm_window: int = 2000
    max_bid_ask_pct_of_mid: float = 0.03
    atm_strike_window: int = 2
    # EOD bhav has no bid/ask — keep L3 soft unless true
    require_bid_ask: bool = False


class VolatilityConfig(BaseModel):
    iv_rank_lookback_days: int = 252
    max_iv_rank_naked: int = 50
    max_iv_percentile_naked: int = 50
    rich_iv_rank: int = 70
    hv_period: int = 20
    # Phase 2 proxy until IV Rank history (Phase 3)
    rich_iv_hv_ratio: float = 1.3


class MoveVsPremiumConfig(BaseModel):
    min_expected_to_be_ratio: float = 1.5
    atr_period: int = 14
    hold_days_assumption: int = 2


class DirectionConfig(BaseModel):
    rs_lookback_days: int = 20
    rs_short_lookback_days: int = 5
    sma_fast: int = 20
    sma_slow: int = 50
    bb_period: int = 20
    bb_std: float = 2.0
    squeeze_lookback: int = 120
    squeeze_percentile: float = 20.0


class RiskConfig(BaseModel):
    max_premium_per_trade_inr: float = 15000
    max_concurrent_naked_buys: int = 3


class CacheTtlConfig(BaseModel):
    option_chain: int = 120
    ohlc_daily: int = 86400
    ban_list: int = 3600


class ScanConfig(BaseModel):
    max_workers: int = 4
    chain_max_workers: int = 2
    ohlc_history_days: int = 400
    chain_request_pause_ms: int = 350


class RulesConfig(BaseModel):
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    liquidity: LiquidityConfig = Field(default_factory=LiquidityConfig)
    volatility: VolatilityConfig = Field(default_factory=VolatilityConfig)
    move_vs_premium: MoveVsPremiumConfig = Field(default_factory=MoveVsPremiumConfig)
    direction: DirectionConfig = Field(default_factory=DirectionConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    cache_ttl_seconds: CacheTtlConfig = Field(default_factory=CacheTtlConfig)
    scan: ScanConfig = Field(default_factory=ScanConfig)


def _default_rules_path() -> Path:
    env = os.getenv("OPTION_DASHBOARD_RULES_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "rules.yaml"


def _default_cache_dir() -> Path:
    env = os.getenv("OPTION_DASHBOARD_CACHE_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_ROOT / "data" / "cache"


def load_rules(path: Path | None = None) -> RulesConfig:
    rules_path = path or _default_rules_path()
    if not rules_path.exists():
        return RulesConfig()
    with rules_path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}
    return RulesConfig.model_validate(raw)


def resolve_universe_csv(rules: RulesConfig) -> Path:
    """Resolve the F&O universe file; try packaged path then the old repo-root copy."""
    env = os.getenv("OPTION_DASHBOARD_UNIVERSE_CSV")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env).expanduser().resolve())
    configured = Path(rules.universe.csv_path)
    if configured.is_absolute():
        candidates.append(configured)
    else:
        candidates.append((PROJECT_ROOT / configured).resolve())
    candidates.append(PROJECT_ROOT / "fno_only_stocks.csv")
    candidates.append(PROJECT_ROOT.parent / "fno_only_stocks.csv")
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path
    return candidates[0]


_rules_cache: tuple[float, str, RulesConfig] | None = None


def get_rules() -> RulesConfig:
    """Load rules.yaml; reload when the file mtime or path changes."""
    global _rules_cache
    path = _default_rules_path()
    mtime = path.stat().st_mtime if path.exists() else 0.0
    resolved = str(path)
    if (
        _rules_cache is not None
        and _rules_cache[0] == mtime
        and _rules_cache[1] == resolved
    ):
        return _rules_cache[2]
    loaded = load_rules(path)
    _rules_cache = (mtime, resolved, loaded)
    return loaded


def get_cache_dir() -> Path:
    path = _default_cache_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
