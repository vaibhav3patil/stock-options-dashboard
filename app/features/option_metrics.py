"""Option metrics: ATM window liquidity, IV, PCR, spreads, move-vs-premium."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.config import LiquidityConfig, MoveVsPremiumConfig, RiskConfig
from app.data.providers.lot_sizes import get_lot_size


@dataclass
class OptionMetrics:
    status: str = "DATA_UNAVAILABLE"
    message: str = ""
    underlying: Optional[float] = None
    expiry: Optional[str] = None
    dte: Optional[int] = None
    atm_strike: Optional[float] = None
    atm_iv: Optional[float] = None
    atm_ce_ltp: Optional[float] = None
    atm_pe_ltp: Optional[float] = None
    atm_ce_bid: Optional[float] = None
    atm_ce_ask: Optional[float] = None
    atm_pe_bid: Optional[float] = None
    atm_pe_ask: Optional[float] = None
    bid_ask_pct: Optional[float] = None
    volume_atm_window: Optional[float] = None
    oi_atm_window: Optional[float] = None
    pcr_oi: Optional[float] = None
    pcr_volume: Optional[float] = None
    strike_continuum_ok: Optional[bool] = None
    lot_size: Optional[int] = None
    premium_per_lot: Optional[float] = None
    expected_move: Optional[float] = None
    breakeven_move: Optional[float] = None
    move_vs_premium_ratio: Optional[float] = None
    liquidity_pass: bool = False
    failed_liquidity_rules: list[str] = field(default_factory=list)
    chain_rows: list[dict[str, Any]] = field(default_factory=list)
    source: Optional[str] = None


def bid_ask_pct(bid: float | None, ask: float | None) -> Optional[float]:
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return None
    return (ask - bid) / mid


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        out = float(value)
        if np.isnan(out):
            return None
        return out
    except (TypeError, ValueError):
        return None


def _parse_expiry(expiry: str | None) -> Optional[datetime]:
    if not expiry:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(expiry, fmt)
        except ValueError:
            continue
    return None


def _nearest_expiry(expiry_dates: list[str]) -> Optional[str]:
    if not expiry_dates:
        return None
    parsed = []
    now = datetime.utcnow()
    for e in expiry_dates:
        dt = _parse_expiry(e)
        if dt is not None and dt.date() >= now.date():
            parsed.append((dt, e))
    if not parsed:
        return expiry_dates[0]
    parsed.sort(key=lambda x: x[0])
    return parsed[0][1]


def _side_fields(side: dict[str, Any] | None) -> dict[str, Optional[float]]:
    side = side or {}
    return {
        "oi": _safe_float(side.get("openInterest")),
        "oi_chg": _safe_float(side.get("changeinOpenInterest")),
        "volume": _safe_float(side.get("totalTradedVolume")),
        "iv": _safe_float(side.get("impliedVolatility")),
        "ltp": _safe_float(side.get("lastPrice")),
        "bid": _safe_float(side.get("bidprice") if "bidprice" in side else side.get("bidPrice")),
        "ask": _safe_float(side.get("askPrice")),
    }


def flatten_chain_rows(chain: dict[str, Any], expiry: str | None = None) -> pd.DataFrame:
    records = (chain or {}).get("records") or {}
    rows = records.get("data") or []
    out = []
    for row in rows:
        if expiry and row.get("expiryDate") and row.get("expiryDate") != expiry:
            # NSE sometimes nests CE/PE with expiry; keep matching strikes
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            if ce.get("expiryDate") not in (None, expiry) and pe.get("expiryDate") not in (
                None,
                expiry,
            ):
                continue
        strike = _safe_float(row.get("strikePrice"))
        if strike is None:
            continue
        ce = _side_fields(row.get("CE"))
        pe = _side_fields(row.get("PE"))
        out.append(
            {
                "strike": strike,
                "expiry": row.get("expiryDate")
                or (row.get("CE") or {}).get("expiryDate")
                or (row.get("PE") or {}).get("expiryDate"),
                "ce_oi": ce["oi"] or 0.0,
                "pe_oi": pe["oi"] or 0.0,
                "ce_volume": ce["volume"] or 0.0,
                "pe_volume": pe["volume"] or 0.0,
                "ce_iv": ce["iv"],
                "pe_iv": pe["iv"],
                "ce_ltp": ce["ltp"],
                "pe_ltp": pe["ltp"],
                "ce_bid": ce["bid"],
                "ce_ask": ce["ask"],
                "pe_bid": pe["bid"],
                "pe_ask": pe["ask"],
                "ce_oi_chg": ce["oi_chg"],
                "pe_oi_chg": pe["oi_chg"],
            }
        )
    return pd.DataFrame(out)


def pick_atm_strike(strikes: list[float], spot: float) -> Optional[float]:
    if not strikes:
        return None
    return float(min(strikes, key=lambda s: abs(s - spot)))


def evaluate_liquidity(
    window: pd.DataFrame,
    *,
    liquidity: LiquidityConfig,
    bid_ask: Optional[float],
) -> tuple[bool, list[str]]:
    failed: list[str] = []
    volume = float(window["ce_volume"].sum() + window["pe_volume"].sum()) if not window.empty else 0.0
    oi = float(window["ce_oi"].sum() + window["pe_oi"].sum()) if not window.empty else 0.0

    if volume < liquidity.min_option_volume_atm_window:
        failed.append("L1")
    if oi < liquidity.min_oi_atm_window:
        failed.append("L2")
    # EOD mode: bid/ask absent — only hard-fail L3 when explicitly required
    if liquidity.require_bid_ask:
        if bid_ask is None or bid_ask > liquidity.max_bid_ask_pct_of_mid:
            failed.append("L3")
    elif bid_ask is not None and bid_ask > liquidity.max_bid_ask_pct_of_mid:
        failed.append("L3")

    # L5 strike continuum: contiguous unique strikes covering window
    if window.empty or window["strike"].nunique() < (2 * liquidity.atm_strike_window + 1):
        failed.append("L5")
    else:
        ordered = sorted(window["strike"].unique())
        # Allow mild gaps; require mostly contiguous steps
        diffs = np.diff(ordered)
        if len(diffs) and np.median(diffs) > 0:
            gap_ratio = float(np.max(diffs) / np.median(diffs))
            if gap_ratio > 2.5:
                failed.append("L5")

    return (len(failed) == 0), failed


def compute_move_vs_premium(
    *,
    atr: Optional[float],
    premium: Optional[float],
    spread_pct: Optional[float],
    move_cfg: MoveVsPremiumConfig,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (expected_move, breakeven_move, ratio)."""
    if atr is None or atr <= 0 or premium is None or premium <= 0:
        return None, None, None
    expected = atr * float(np.sqrt(max(move_cfg.hold_days_assumption, 1)))
    half_spread = 0.0
    if spread_pct is not None:
        half_spread = premium * spread_pct / 2.0
    breakeven = premium + half_spread
    if breakeven <= 0:
        return expected, breakeven, None
    return expected, breakeven, expected / breakeven


def summarize_chain(
    chain: dict[str, Any],
    *,
    symbol: str,
    spot_fallback: float | None = None,
    atr: float | None = None,
    direction: str = "CALL",
    liquidity: LiquidityConfig | None = None,
    move_cfg: MoveVsPremiumConfig | None = None,
    risk: RiskConfig | None = None,
    lot_size: int | None = None,
    as_of_date: str | None = None,
) -> OptionMetrics:
    liquidity = liquidity or LiquidityConfig()
    move_cfg = move_cfg or MoveVsPremiumConfig()
    risk = risk or RiskConfig()

    status = (chain or {}).get("status", "DATA_UNAVAILABLE")
    if status != "OK":
        return OptionMetrics(
            status=status,
            message=(chain or {}).get("message", "unavailable"),
            source=(chain or {}).get("source"),
        )

    records = chain.get("records") or {}
    underlying = _safe_float(records.get("underlyingValue")) or spot_fallback
    if underlying is None:
        return OptionMetrics(status="DATA_UNAVAILABLE", message="Missing underlying value")

    as_of = _parse_expiry(as_of_date) or datetime.utcnow()
    expiry = _nearest_expiry_as_of(list(records.get("expiryDates") or []), as_of)
    df = flatten_chain_rows(chain, expiry=expiry)
    if df.empty:
        # Some payloads put all expiries in data without top-level filter
        df = flatten_chain_rows(chain, expiry=None)
    if df.empty:
        return OptionMetrics(status="DATA_UNAVAILABLE", message="No strike rows")

    if expiry is None:
        expiry = str(df["expiry"].dropna().iloc[0]) if df["expiry"].notna().any() else None

    # Prefer selected expiry rows when present
    if expiry and df["expiry"].notna().any():
        matched = df[df["expiry"] == expiry]
        if not matched.empty:
            df = matched

    atm = pick_atm_strike(df["strike"].tolist(), underlying)
    if atm is None:
        return OptionMetrics(status="DATA_UNAVAILABLE", message="Cannot resolve ATM")

    window_n = liquidity.atm_strike_window
    # Use nearest N strikes on each side by rank around ATM
    ordered = sorted(df["strike"].unique())
    atm_idx = ordered.index(atm) if atm in ordered else int(np.argmin([abs(s - atm) for s in ordered]))
    lo = max(0, atm_idx - window_n)
    hi = min(len(ordered), atm_idx + window_n + 1)
    window_strikes = set(ordered[lo:hi])
    window = df[df["strike"].isin(window_strikes)].copy()
    atm_row = df[df["strike"] == atm].iloc[0]

    ce_ba = bid_ask_pct(atm_row.get("ce_bid"), atm_row.get("ce_ask"))
    pe_ba = bid_ask_pct(atm_row.get("pe_bid"), atm_row.get("pe_ask"))
    if direction.upper() == "PUT":
        ba = pe_ba if pe_ba is not None else ce_ba
        chosen_ltp = _safe_float(atm_row.get("pe_ltp"))
    else:
        ba = ce_ba if ce_ba is not None else pe_ba
        chosen_ltp = _safe_float(atm_row.get("ce_ltp"))

    ivs = [v for v in [atm_row.get("ce_iv"), atm_row.get("pe_iv")] if v is not None]
    atm_iv = float(np.mean(ivs)) if ivs else None

    volume = float(window["ce_volume"].sum() + window["pe_volume"].sum())
    oi = float(window["ce_oi"].sum() + window["pe_oi"].sum())
    total_ce_oi = float(df["ce_oi"].sum())
    total_pe_oi = float(df["pe_oi"].sum())
    total_ce_vol = float(df["ce_volume"].sum())
    total_pe_vol = float(df["pe_volume"].sum())
    pcr_oi = (total_pe_oi / total_ce_oi) if total_ce_oi > 0 else None
    pcr_vol = (total_pe_vol / total_ce_vol) if total_ce_vol > 0 else None

    liq_ok, failed = evaluate_liquidity(window, liquidity=liquidity, bid_ask=ba)

    lot = lot_size if lot_size is not None else get_lot_size(symbol)
    # Prefer bhav lot if present on chain meta
    if lot is None:
        lot = _safe_float((chain.get("records") or {}).get("lotSize"))
        lot = int(lot) if lot else None

    premium_lot = None
    if lot and chosen_ltp is not None:
        premium_lot = float(lot) * float(chosen_ltp)
        if premium_lot > risk.max_premium_per_trade_inr:
            failed = list(failed) + ["L4"]
            liq_ok = False

    expected, breakeven, ratio = compute_move_vs_premium(
        atr=atr,
        premium=chosen_ltp,
        spread_pct=ba,
        move_cfg=move_cfg,
    )

    exp_dt = _parse_expiry(expiry)
    dte = (exp_dt.date() - as_of.date()).days if exp_dt else None

    # If IV missing (EOD bhav), estimate from close premium via BS
    if atm_iv is None and chosen_ltp is not None and dte is not None and dte > 0:
        opt = "PE" if direction.upper() == "PUT" else "CE"
        est = _implied_vol_pct(
            spot=underlying,
            strike=atm,
            premium=chosen_ltp,
            dte=dte,
            option_type=opt,
        )
        atm_iv = est

    chain_rows = []
    for _, r in window.sort_values("strike").iterrows():
        chain_rows.append(
            {
                "strike": r["strike"],
                "ce_ltp": r.get("ce_ltp"),
                "ce_iv": r.get("ce_iv"),
                "ce_oi": r.get("ce_oi"),
                "ce_oi_chg": r.get("ce_oi_chg"),
                "ce_volume": r.get("ce_volume"),
                "ce_bid": r.get("ce_bid"),
                "ce_ask": r.get("ce_ask"),
                "pe_ltp": r.get("pe_ltp"),
                "pe_iv": r.get("pe_iv"),
                "pe_oi": r.get("pe_oi"),
                "pe_oi_chg": r.get("pe_oi_chg"),
                "pe_volume": r.get("pe_volume"),
                "pe_bid": r.get("pe_bid"),
                "pe_ask": r.get("pe_ask"),
            }
        )

    return OptionMetrics(
        status="OK",
        message="ok",
        underlying=underlying,
        expiry=expiry,
        dte=dte,
        atm_strike=atm,
        atm_iv=atm_iv,
        atm_ce_ltp=_safe_float(atm_row.get("ce_ltp")),
        atm_pe_ltp=_safe_float(atm_row.get("pe_ltp")),
        atm_ce_bid=_safe_float(atm_row.get("ce_bid")),
        atm_ce_ask=_safe_float(atm_row.get("ce_ask")),
        atm_pe_bid=_safe_float(atm_row.get("pe_bid")),
        atm_pe_ask=_safe_float(atm_row.get("pe_ask")),
        bid_ask_pct=ba,
        volume_atm_window=volume,
        oi_atm_window=oi,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_vol,
        strike_continuum_ok="L5" not in failed,
        lot_size=lot,
        premium_per_lot=premium_lot,
        expected_move=expected,
        breakeven_move=breakeven,
        move_vs_premium_ratio=ratio,
        liquidity_pass=liq_ok,
        failed_liquidity_rules=failed,
        chain_rows=chain_rows,
        source=chain.get("source"),
    )


def _nearest_expiry_as_of(expiry_dates: list[str], as_of: datetime) -> Optional[str]:
    if not expiry_dates:
        return None
    parsed = []
    for e in expiry_dates:
        dt = _parse_expiry(e)
        if dt is not None and dt.date() >= as_of.date():
            parsed.append((dt, e))
    if not parsed:
        return expiry_dates[0]
    parsed.sort(key=lambda x: x[0])
    return parsed[0][1]


def _norm_cdf(x: float) -> float:
    return float(0.5 * (1.0 + math.erf(x / math.sqrt(2.0))))


def _bs_price(
    spot: float,
    strike: float,
    t_years: float,
    rate: float,
    vol: float,
    option_type: str,
) -> float:
    if t_years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return max(0.0, spot - strike) if option_type == "CE" else max(0.0, strike - spot)
    d1 = (math.log(spot / strike) + (rate + 0.5 * vol * vol) * t_years) / (vol * math.sqrt(t_years))
    d2 = d1 - vol * math.sqrt(t_years)
    if option_type == "CE":
        return spot * _norm_cdf(d1) - strike * math.exp(-rate * t_years) * _norm_cdf(d2)
    return strike * math.exp(-rate * t_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _implied_vol_pct(
    *,
    spot: float,
    strike: float,
    premium: float,
    dte: int,
    option_type: str,
    rate: float = 0.065,
) -> Optional[float]:
    """Crude Newton IV (%) from EOD close premium."""
    if premium <= 0 or dte <= 0:
        return None
    t = dte / 365.0
    vol = 0.25
    for _ in range(40):
        price = _bs_price(spot, strike, t, rate, vol, option_type)
        diff = price - premium
        if abs(diff) < 1e-3:
            return vol * 100.0
        bump = 1e-4
        vega = (
            _bs_price(spot, strike, t, rate, vol + bump, option_type)
            - _bs_price(spot, strike, t, rate, vol - bump, option_type)
        ) / (2 * bump)
        if abs(vega) < 1e-8:
            break
        vol = max(1e-4, vol - diff / vega)
    return vol * 100.0 if vol > 0 else None


def bhav_to_chain_payload(
    symbol_df: pd.DataFrame,
    *,
    symbol: str,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    """Convert EOD F&O bhav rows for one symbol into NSE-like chain payload."""
    if symbol_df is None or symbol_df.empty:
        return {
            "symbol": symbol.upper(),
            "status": "DATA_UNAVAILABLE",
            "message": "No EOD option rows for symbol",
            "records": {"data": [], "expiryDates": [], "underlyingValue": None},
            "source": "fo_bhav_eod",
        }

    df = symbol_df.copy()
    expiries = sorted({str(x) for x in df["XpryDt"].dropna().unique()}) if "XpryDt" in df.columns else []
    underlying = None
    if "UndrlygPric" in df.columns and df["UndrlygPric"].notna().any():
        underlying = float(df["UndrlygPric"].dropna().iloc[0])

    lot = None
    if "NewBrdLotQty" in df.columns and df["NewBrdLotQty"].notna().any():
        lot = int(df["NewBrdLotQty"].dropna().iloc[0])

    # Pivot CE/PE by strike+expiry
    data_rows: list[dict[str, Any]] = []
    group_cols = ["XpryDt", "StrkPric"]
    for (expiry, strike), g in df.groupby(group_cols, dropna=False):
        row: dict[str, Any] = {
            "strikePrice": float(strike) if pd.notna(strike) else None,
            "expiryDate": str(expiry) if pd.notna(expiry) else None,
        }
        for opt in ("CE", "PE"):
            side = g[g["OptnTp"].astype(str).str.upper() == opt]
            if side.empty:
                continue
            s = side.iloc[0]
            close = _safe_float(s.get("ClsPric"))
            last = _safe_float(s.get("LastPric"))
            settle = _safe_float(s.get("SttlmPric"))
            # Last traded matches Kite LTP; official close can differ by a few ticks.
            px = last or close or settle
            row[opt] = {
                "strikePrice": float(strike) if pd.notna(strike) else None,
                "expiryDate": str(expiry) if pd.notna(expiry) else None,
                "openInterest": _safe_float(s.get("OpnIntrst")) or 0.0,
                "changeinOpenInterest": _safe_float(s.get("ChngInOpnIntrst")) or 0.0,
                "totalTradedVolume": _safe_float(s.get("TtlTradgVol")) or 0.0,
                "impliedVolatility": None,
                "lastPrice": px,
                "bidprice": None,
                "askPrice": None,
            }
        if "CE" in row or "PE" in row:
            data_rows.append(row)

    return {
        "symbol": symbol.upper(),
        "status": "OK" if data_rows else "DATA_UNAVAILABLE",
        "message": "ok" if data_rows else "No option rows after pivot",
        "source": "fo_bhav_eod",
        "as_of_date": as_of_date,
        "records": {
            "expiryDates": expiries,
            "underlyingValue": underlying,
            "lotSize": lot,
            "data": data_rows,
        },
    }


def summarize_eod_bhav(
    symbol_df: pd.DataFrame,
    *,
    symbol: str,
    as_of_date: str | None = None,
    spot_fallback: float | None = None,
    atr: float | None = None,
    direction: str = "CALL",
    liquidity: LiquidityConfig | None = None,
    move_cfg: MoveVsPremiumConfig | None = None,
    risk: RiskConfig | None = None,
    lot_size: int | None = None,
) -> OptionMetrics:
    chain = bhav_to_chain_payload(symbol_df, symbol=symbol, as_of_date=as_of_date)
    return summarize_chain(
        chain,
        symbol=symbol,
        spot_fallback=spot_fallback,
        atr=atr,
        direction=direction,
        liquidity=liquidity,
        move_cfg=move_cfg,
        risk=risk,
        lot_size=lot_size,
        as_of_date=as_of_date,
    )
