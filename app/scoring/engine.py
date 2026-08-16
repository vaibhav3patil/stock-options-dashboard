from __future__ import annotations

from typing import Any

from app.config import MoveVsPremiumConfig, RulesConfig, VolatilityConfig
from app.features.option_metrics import OptionMetrics
from app.features.selection_overlays import EventInfo, OverlayInput, apply_selection_overlays
from app.features.technicals import TechnicalFeatures, provisional_technical_score
from app.features.trade_suggestions import TradeSuggestion, build_trade_suggestion
from app.models.schemas import (
    DataStatus,
    DirectionBias,
    Eligibility,
    InstrumentType,
    SymbolRow,
    TrendLabel,
)


def direction_from_trend(trend: TrendLabel, rs_20: float | None) -> DirectionBias:
    if trend == TrendLabel.UP:
        return DirectionBias.CALL
    if trend == TrendLabel.DOWN:
        return DirectionBias.PUT
    if rs_20 is not None and rs_20 > 2:
        return DirectionBias.CALL
    if rs_20 is not None and rs_20 < -2:
        return DirectionBias.PUT
    return DirectionBias.NEUTRAL


def has_directional_setup(features: TechnicalFeatures) -> bool:
    if features.trend in {TrendLabel.UP, TrendLabel.DOWN}:
        return True
    if features.squeeze:
        return True
    if features.rs_20 is not None and abs(features.rs_20) >= 3:
        return True
    return False


def iv_rich_vs_hv(
    atm_iv: float | None,
    hv_20: float | None,
    *,
    rich_ratio: float = 1.3,
) -> bool:
    if atm_iv is None or hv_20 is None or hv_20 <= 0:
        return False
    return atm_iv >= rich_ratio * hv_20


def composite_score(
    features: TechnicalFeatures,
    metrics: OptionMetrics,
    *,
    move_ok: bool,
    liq_ok: bool,
) -> float | None:
    base = provisional_technical_score(features)
    if base is None:
        return None
    score = base
    if liq_ok:
        score += 10
    if move_ok:
        score += 10
    if metrics.atm_iv is not None and features.hv_20 is not None:
        if metrics.atm_iv <= features.hv_20:
            score += 8
        elif metrics.atm_iv <= 1.2 * features.hv_20:
            score += 3
        else:
            score -= 8
    if metrics.bid_ask_pct is not None:
        if metrics.bid_ask_pct <= 0.02:
            score += 5
        elif metrics.bid_ask_pct > 0.05:
            score -= 5
    return float(max(0.0, min(100.0, score)))


def _row_from_features(
    *,
    symbol: str,
    instrument_type: InstrumentType,
    features: TechnicalFeatures | None,
    **overrides: Any,
) -> SymbolRow:
    data: dict[str, Any] = {
        "symbol": symbol,
        "instrument_type": instrument_type,
    }
    if features is not None:
        data.update(
            spot=features.spot,
            atr=features.atr,
            atr_pct=features.atr_pct,
            hv_20=features.hv_20,
            rs_5=features.rs_5,
            rs_20=features.rs_20,
            squeeze=features.squeeze,
            trend=features.trend,
        )
    data.update(overrides)
    return SymbolRow.model_validate(data)


def _setup_tags(features: TechnicalFeatures, *, prefix: str) -> list[str]:
    tags = [prefix]
    if features.squeeze:
        tags.append("SQUEEZE")
    if features.trend == TrendLabel.UP:
        tags.append("TREND_UP")
    elif features.trend == TrendLabel.DOWN:
        tags.append("TREND_DOWN")
    return tags


def score_pre_chain(
    *,
    symbol: str,
    instrument_type: InstrumentType,
    features: TechnicalFeatures | None,
    data_status: DataStatus,
    error: str | None = None,
) -> SymbolRow:
    """OHLC-only fallback (kept for Phase 1 compatibility)."""
    if data_status == DataStatus.DATA_STALE or features is None or features.spot is None:
        return _row_from_features(
            symbol=symbol,
            instrument_type=instrument_type,
            features=None,
            eligibility=Eligibility.EXCLUDE,
            data_status=DataStatus.DATA_STALE,
            failed_rules=["IN12"],
            warnings=[error or "OHLC fetch failed or stale"],
            why="IN12 stale/unavailable OHLC — exclude until data refreshes.",
            score=None,
        )

    return _row_from_features(
        symbol=symbol,
        instrument_type=instrument_type,
        features=features,
        score=provisional_technical_score(features),
        eligibility=Eligibility.WATCH,
        direction_bias=direction_from_trend(features.trend, features.rs_20),
        setup_tags=_setup_tags(features, prefix="PRE_CHAIN"),
        warnings=["EOD option metrics not applied."],
        data_status=DataStatus.OK,
        why="Pre-chain technical scan only.",
    )


def _base_option_fields(metrics: OptionMetrics, as_of_date: str | None) -> dict:
    return {
        "as_of_date": as_of_date,
        "atm_strike": metrics.atm_strike,
        "atm_iv": metrics.atm_iv,
        "bid_ask_pct": metrics.bid_ask_pct,
        "oi_atm": metrics.oi_atm_window,
        "volume_atm": metrics.volume_atm_window,
        "pcr": metrics.pcr_oi,
        "expiry": metrics.expiry,
        "dte": metrics.dte,
        "lot_size": metrics.lot_size,
        "premium_per_lot": metrics.premium_per_lot,
        "move_vs_premium_ratio": metrics.move_vs_premium_ratio,
        "chain_rows": metrics.chain_rows,
    }


def _suggestion_fields(suggestion: TradeSuggestion) -> dict:
    primary = suggestion.primary
    return {
        "suggestion_action": suggestion.action,
        "suggestion_summary": suggestion.summary,
        "suggestion_strike": None if primary is None else primary.strike,
        "suggestion_option_type": None if primary is None else primary.option_type,
        "suggestion_label": None if primary is None else primary.label,
        "suggestion_premium": None if primary is None else primary.premium,
        "suggestion_premium_per_lot": None if primary is None else primary.premium_per_lot,
        "suggestion_max_lots": suggestion.max_lots,
        "suggestion_rationale": suggestion.rationale,
        "suggestion_alternates": [a.to_dict() for a in suggestion.alternates],
        "suggestion_breakeven": suggestion.breakeven,
        "suggestion_required_move_pts": suggestion.required_move_pts,
        "suggestion_required_move_pct": suggestion.required_move_pct,
        "suggestion_expected_move_pts": suggestion.expected_move_pts,
        "suggestion_move_cover_ratio": suggestion.move_cover_ratio,
        "suggestion_pnl_plus_1atr": suggestion.pnl_at_plus_1atr,
        "suggestion_pnl_minus_1atr": suggestion.pnl_at_minus_1atr,
        "suggestion_pnl_scenarios": suggestion.pnl_scenarios,
    }


def _attach_suggestion(
    row: SymbolRow,
    *,
    symbol: str,
    bias: DirectionBias,
    eligibility: Eligibility,
    metrics: OptionMetrics | None,
    atr: float | None,
    rules: RulesConfig,
) -> SymbolRow:
    if metrics is None or metrics.status != "OK":
        return row
    suggestion = build_trade_suggestion(
        symbol=symbol,
        bias=bias,
        eligibility=eligibility,
        metrics=metrics,
        atr=atr,
        move_cfg=rules.move_vs_premium,
        risk=rules.risk,
    )
    data = row.model_dump()
    data.update(_suggestion_fields(suggestion))
    return SymbolRow.model_validate(data)


def score_with_chain(
    *,
    symbol: str,
    instrument_type: InstrumentType,
    features: TechnicalFeatures | None,
    metrics: OptionMetrics | None,
    ohlc_status: DataStatus,
    rules: RulesConfig,
    ohlc_error: str | None = None,
    as_of_date: str | None = None,
    ban_list: list[str] | None = None,
    event: EventInfo | None = None,
    iv_rank: float | None = None,
    iv_percentile: float | None = None,
    iv_history_n: int = 0,
) -> SymbolRow:
    """
    Eligibility from last-close OHLC + EOD F&O bhav metrics.

    IF liquidity fail OR stale EOD data:
      EXCLUDE
    ELIF IV rich vs HV AND no superior move edge:
      SPREAD_ONLY
    ELIF move_vs_premium fail OR no setup:
      WATCH
    ELIF all key gates pass:
      NAKED_BUY_OK
    ELSE:
      WATCH
    """
    move_cfg: MoveVsPremiumConfig = rules.move_vs_premium
    vol_cfg: VolatilityConfig = rules.volatility
    rich_ratio = getattr(vol_cfg, "rich_iv_hv_ratio", 1.3)

    if ban_list and symbol.upper() in {s.upper() for s in ban_list}:
        return _row_from_features(
            symbol=symbol,
            instrument_type=instrument_type,
            features=None,
            as_of_date=as_of_date,
            eligibility=Eligibility.EXCLUDE,
            data_status=ohlc_status if ohlc_status != DataStatus.OK else DataStatus.OK,
            failed_rules=["IN1"],
            setup_tags=["FNO_BAN"],
            in_fno_ban=True,
            event_kind=None if event is None else event.kind,
            event_date=None if event is None else event.date,
            event_days=None if event is None else event.days_ahead,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            why="IN1 F&O ban — skip.",
        )

    if ohlc_status != DataStatus.OK or features is None or features.spot is None:
        return _row_from_features(
            symbol=symbol,
            instrument_type=instrument_type,
            features=None,
            as_of_date=as_of_date,
            eligibility=Eligibility.EXCLUDE,
            data_status=DataStatus.DATA_STALE,
            failed_rules=["IN12"],
            warnings=[ohlc_error or "OHLC unavailable"],
            why="IN12 stale/unavailable OHLC.",
        )

    bias = direction_from_trend(features.trend, features.rs_20)
    tags = _setup_tags(features, prefix="EOD")
    warnings: list[str] = []
    failed: list[str] = []

    if metrics is None or metrics.status != "OK":
        failed.append("IN12")
        return _row_from_features(
            symbol=symbol,
            instrument_type=instrument_type,
            features=features,
            as_of_date=as_of_date,
            score=provisional_technical_score(features),
            eligibility=Eligibility.EXCLUDE,
            direction_bias=bias,
            setup_tags=tags + ["EOD_OPTIONS_UNAVAILABLE"],
            failed_rules=failed,
            warnings=[(metrics.message if metrics else "No EOD options")]
            + ["EOD F&O bhav unavailable — IN12"],
            data_status=DataStatus.DATA_UNAVAILABLE,
            why="IN12 EOD option data unavailable — exclude.",
        )

    failed.extend(metrics.failed_liquidity_rules)
    opt_fields = _base_option_fields(metrics, as_of_date)

    if not metrics.liquidity_pass:
        why = f"Liquidity hard-fail ({', '.join(metrics.failed_liquidity_rules) or 'L*'})."
        return _row_from_features(
            symbol=symbol,
            instrument_type=instrument_type,
            features=features,
            spot=metrics.underlying or features.spot,
            score=composite_score(features, metrics, move_ok=False, liq_ok=False),
            eligibility=Eligibility.EXCLUDE,
            direction_bias=bias,
            setup_tags=tags,
            failed_rules=failed,
            warnings=warnings + ["L3 bid-ask not in EOD bhav (soft unless require_bid_ask)"],
            data_status=DataStatus.OK,
            why=why,
            **opt_fields,
        )

    move_ok = (
        metrics.move_vs_premium_ratio is not None
        and metrics.move_vs_premium_ratio >= move_cfg.min_expected_to_be_ratio
    )
    if not move_ok:
        failed.append("M3")
        warnings.append("Technique C: expected move does not cover premium break-even buffer")

    setup_ok = has_directional_setup(features)
    if not setup_ok:
        failed.append("T1")
        warnings.append("No clear directional/squeeze setup")

    rich = iv_rich_vs_hv(metrics.atm_iv, features.hv_20, rich_ratio=rich_ratio)
    superior_move = (
        metrics.move_vs_premium_ratio is not None
        and metrics.move_vs_premium_ratio >= move_cfg.min_expected_to_be_ratio * 1.25
    )
    if rich:
        tags.append("IV_RICH_VS_HV")
        warnings.append("V5: ATM IV (est. from close) rich vs HV20")

    score = composite_score(features, metrics, move_ok=move_ok, liq_ok=True)

    if rich and not superior_move:
        eligibility = Eligibility.SPREAD_ONLY
        why = "IV rich vs HV without superior move edge → SPREAD_ONLY (debit spread)."
    elif not move_ok or not setup_ok:
        eligibility = Eligibility.WATCH
        why = "Liquidity OK but move-vs-premium or setup incomplete → WATCH."
    elif move_ok and setup_ok and not rich:
        eligibility = Eligibility.NAKED_BUY_OK
        tags.append("TECHNIQUE_C_PASS")
        why = "Last-close liquidity + move-vs-premium + setup pass → NAKED_BUY_OK."
    else:
        eligibility = Eligibility.NAKED_BUY_OK if (move_ok and setup_ok) else Eligibility.WATCH
        if eligibility == Eligibility.NAKED_BUY_OK:
            tags.append("TECHNIQUE_C_PASS")
            warnings.append("IV elevated but move edge large enough")
            why = "Strong move edge outweighs elevated IV → NAKED_BUY_OK with caution."
        else:
            why = "Mixed gates → WATCH."

    overlay = apply_selection_overlays(
        eligibility,
        OverlayInput(
            symbol=symbol,
            ban_list=ban_list,
            event=event,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            iv_history_n=iv_history_n,
            bid_ask_pct=metrics.bid_ask_pct,
            move_ratio=metrics.move_vs_premium_ratio,
        ),
        rules,
    )
    failed.extend(overlay.failed)
    warnings.extend(overlay.warnings)
    tags.extend(overlay.tags)
    if overlay.eligibility is not None:
        eligibility = overlay.eligibility
    if overlay.why_suffix:
        why = overlay.why_suffix

    if metrics.pcr_oi is not None:
        tags.append(f"PCR:{metrics.pcr_oi:.2f}")

    row = _row_from_features(
        symbol=symbol,
        instrument_type=instrument_type,
        features=features,
        spot=metrics.underlying or features.spot,
        score=score,
        eligibility=eligibility,
        direction_bias=bias,
        setup_tags=tags,
        failed_rules=failed,
        warnings=warnings,
        data_status=DataStatus.OK,
        why=why,
        iv_rank=iv_rank,
        iv_percentile=iv_percentile,
        event_kind=None if event is None else event.kind,
        event_date=None if event is None else event.date,
        event_days=None if event is None else event.days_ahead,
        in_fno_ban="IN1" in failed,
        **opt_fields,
    )
    return _attach_suggestion(
        row,
        symbol=symbol,
        bias=bias,
        eligibility=eligibility,
        metrics=metrics,
        atr=features.atr,
        rules=rules,
    )
