from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

from app.config import RulesConfig, get_rules
from app.data.providers.event_calendar import EventCalendarProvider
from app.data.providers.nse_ban import NseBanListProvider
from app.data.providers.nse_bhavcopy import NseBhavcopyProvider
from app.data.providers.yfinance_ohlc import YFinanceOHLCProvider
from app.features.iv_history import IvHistoryStore
from app.features.option_metrics import OptionMetrics, summarize_eod_bhav
from app.features.selection_overlays import EventInfo, rebase_event
from app.features.technicals import TechnicalFeatures, compute_technicals
from app.models.schemas import DataStatus, Eligibility, SymbolMeta, SymbolRow
from app.scoring.engine import direction_from_trend, score_with_chain
from app.universe import filter_liquid_subset, load_universe

logger = logging.getLogger(__name__)

MAX_SCAN_WORKERS = 4
UNIVERSE_SORT_FALLBACK = 10_000


class ScannerService:
    """Daily stock selection using last market close OHLC + EOD F&O bhav."""

    def __init__(
        self,
        rules: RulesConfig | None = None,
        ohlc_provider: YFinanceOHLCProvider | None = None,
        bhav_provider: NseBhavcopyProvider | None = None,
    ) -> None:
        self.rules = rules or get_rules()
        self.ohlc = ohlc_provider or YFinanceOHLCProvider(self.rules)
        self.bhav = bhav_provider or NseBhavcopyProvider(self.rules)
        self.ban = NseBanListProvider(self.rules)
        self.events = EventCalendarProvider()
        self.iv_store = IvHistoryStore()

    def load_symbols(self, *, use_subset: bool) -> list[SymbolMeta]:
        universe = load_universe(self.rules)
        return filter_liquid_subset(universe, self.rules, use_subset=use_subset)

    def _fetch_nifty(self, force_refresh: bool) -> pd.DataFrame | None:
        try:
            return self.ohlc.get_nifty_ohlc(
                period_days=self.rules.scan.ohlc_history_days,
                force_refresh=force_refresh,
            )
        except Exception as exc:
            logger.warning("Nifty OHLC failed: %s", exc)
            return None

    def _technicals(
        self,
        meta: SymbolMeta,
        nifty_ohlc: pd.DataFrame | None,
        as_of_date: str | None,
        *,
        force_refresh: bool,
        ohlc: pd.DataFrame | None,
    ) -> tuple[TechnicalFeatures | None, DataStatus, str | None]:
        try:
            if ohlc is None:
                ohlc = self.ohlc.get_ohlc(
                    meta.symbol,
                    period_days=self.rules.scan.ohlc_history_days,
                    force_refresh=force_refresh,
                )
            if as_of_date:
                ohlc = slice_ohlc_as_of(ohlc, as_of_date)
                nifty_ohlc = slice_ohlc_as_of(nifty_ohlc, as_of_date)
            features = compute_technicals(
                ohlc,
                nifty_ohlc,
                move_cfg=self.rules.move_vs_premium,
                vol_cfg=self.rules.volatility,
                direction_cfg=self.rules.direction,
            )
            return features, DataStatus.OK, None
        except Exception as exc:
            logger.warning("OHLC failed for %s: %s", meta.symbol, exc)
            return None, DataStatus.DATA_STALE, str(exc)

    def _eod_metrics(
        self,
        meta: SymbolMeta,
        features: TechnicalFeatures | None,
        bhav: pd.DataFrame | None,
        as_of_date: str | None,
    ) -> OptionMetrics | None:
        if bhav is None:
            return OptionMetrics(
                status="DATA_UNAVAILABLE",
                message="EOD F&O bhav not loaded",
            )
        if features is None or features.spot is None:
            return None
        bias = direction_from_trend(features.trend, features.rs_20)
        try:
            sym_df = self.bhav.symbol_options(bhav, meta.symbol)
            metrics = summarize_eod_bhav(
                sym_df,
                symbol=meta.symbol,
                as_of_date=as_of_date,
                spot_fallback=features.spot,
                atr=features.atr,
                direction=bias.value,
                liquidity=self.rules.liquidity,
                move_cfg=self.rules.move_vs_premium,
                risk=self.rules.risk,
                lot_size=_lot_from_bhav(sym_df),
            )
            return metrics
        except Exception as exc:
            logger.warning("EOD options failed for %s: %s", meta.symbol, exc)
            return OptionMetrics(status="DATA_UNAVAILABLE", message=str(exc))

    def _iv_overlay(
        self,
        meta: SymbolMeta,
        metrics: OptionMetrics | None,
        as_of_date: str | None,
        *,
        record_iv: bool,
    ) -> tuple[float | None, float | None, int]:
        if metrics is None or metrics.atm_iv is None:
            return None, None, 0
        if record_iv:
            self.iv_store.record(meta.symbol, as_of_date, metrics.atm_iv)
        return self.iv_store.rank(meta.symbol, metrics.atm_iv)

    def _map_symbols(
        self,
        metas: list[SymbolMeta],
        fn: Callable[[SymbolMeta], SymbolRow],
    ) -> list[SymbolRow]:
        workers = max(1, min(self.rules.scan.max_workers, MAX_SCAN_WORKERS))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures: dict[Future[SymbolRow], SymbolMeta] = {
                pool.submit(fn, meta): meta for meta in metas
            }
            return _sort_like_universe(_gather_symbol_rows(futures), metas)

    def scan_symbol(
        self,
        meta: SymbolMeta,
        nifty_ohlc: pd.DataFrame | None,
        bhav: pd.DataFrame | None,
        as_of_date: str | None,
        ban_list: list[str] | None,
        *,
        force_refresh: bool = False,
        ohlc: pd.DataFrame | None = None,
        event: EventInfo | None = None,
        record_iv: bool = True,
    ) -> SymbolRow:
        features, ohlc_status, ohlc_error = self._technicals(
            meta,
            nifty_ohlc,
            as_of_date,
            force_refresh=force_refresh,
            ohlc=ohlc,
        )
        metrics = self._eod_metrics(meta, features, bhav, as_of_date)
        if event is None:
            event = rebase_event(
                self.events.get_event(meta.symbol, force_refresh=force_refresh),
                as_of_date,
            )
        iv_rank, iv_pct, iv_n = self._iv_overlay(
            meta, metrics, as_of_date, record_iv=record_iv
        )
        row = score_with_chain(
            symbol=meta.symbol,
            instrument_type=meta.instrument_type,
            features=features,
            metrics=metrics,
            ohlc_status=ohlc_status,
            rules=self.rules,
            ohlc_error=ohlc_error,
            as_of_date=as_of_date,
            ban_list=ban_list,
            event=event,
            iv_rank=iv_rank,
            iv_percentile=iv_pct,
            iv_history_n=iv_n,
        )
        row.updated_at = datetime.now(timezone.utc)
        return row

    def scan_many(
        self,
        symbols: Iterable[SymbolMeta],
        *,
        force_refresh: bool = False,
    ) -> list[SymbolRow]:
        metas = list(symbols)
        nifty = self._fetch_nifty(force_refresh)

        bhav: pd.DataFrame | None = None
        as_of_date: str | None = None
        try:
            bhav, as_of_date = self.bhav.get_latest_bhav(force_refresh=force_refresh)
            logger.info("Loaded EOD F&O bhav as-of %s (%s rows)", as_of_date, len(bhav))
        except Exception as exc:
            logger.warning("EOD F&O bhav load failed: %s", exc)

        if as_of_date:
            nifty = slice_ohlc_as_of(nifty, as_of_date)

        ban_list: list[str] = []
        try:
            ban_list = self.ban.get_ban_list(as_of_date, force_refresh=force_refresh)
        except Exception as exc:
            logger.warning("F&O ban list failed: %s", exc)

        def _one(meta: SymbolMeta) -> SymbolRow:
            return self.scan_symbol(
                meta,
                nifty,
                bhav,
                as_of_date,
                ban_list,
                force_refresh=force_refresh,
            )

        return self._map_symbols(metas, _one)

    def scan_as_of(
        self,
        symbols: Iterable[SymbolMeta],
        *,
        as_of_date: str,
        bhav: pd.DataFrame,
        nifty_ohlc: pd.DataFrame | None = None,
    ) -> list[SymbolRow]:
        """Score the universe as if only data through `as_of_date` existed."""
        metas = list(symbols)
        nifty = slice_ohlc_as_of(
            nifty_ohlc if nifty_ohlc is not None else self._fetch_nifty(False),
            as_of_date,
        )

        def _one(meta: SymbolMeta) -> SymbolRow:
            try:
                raw = self.ohlc.get_ohlc(
                    meta.symbol,
                    period_days=self.rules.scan.ohlc_history_days,
                )
            except Exception:
                raw = None
            sliced = slice_ohlc_as_of(raw, as_of_date)
            return self.scan_symbol(
                meta,
                nifty,
                bhav,
                as_of_date,
                [],
                ohlc=sliced,
                record_iv=False,
            )

        return self._map_symbols(metas, _one)


def _failed_symbol_row(meta: SymbolMeta, exc: Exception) -> SymbolRow:
    return SymbolRow(
        symbol=meta.symbol,
        instrument_type=meta.instrument_type,
        eligibility=Eligibility.EXCLUDE,
        data_status=DataStatus.DATA_STALE,
        failed_rules=["IN12"],
        warnings=[str(exc)],
        why=f"IN12 worker error — {exc}",
    )


def _lot_from_bhav(sym_df: pd.DataFrame) -> int | None:
    if sym_df.empty or "NewBrdLotQty" not in sym_df.columns:
        return None
    lot_val = sym_df["NewBrdLotQty"].dropna()
    return int(lot_val.iloc[0]) if not lot_val.empty else None


def _gather_symbol_rows(futures: dict[Future[SymbolRow], SymbolMeta]) -> list[SymbolRow]:
    rows: list[SymbolRow] = []
    for fut in as_completed(futures):
        meta = futures[fut]
        try:
            rows.append(fut.result())
        except Exception as exc:
            logger.exception("Scan failed for %s: %s", meta.symbol, exc)
            rows.append(_failed_symbol_row(meta, exc))
    return rows


def _sort_like_universe(rows: list[SymbolRow], metas: list[SymbolMeta]) -> list[SymbolRow]:
    order = {m.symbol: i for i, m in enumerate(metas)}
    rows.sort(key=lambda r: order.get(r.symbol, UNIVERSE_SORT_FALLBACK))
    return rows


def slice_ohlc_as_of(df: pd.DataFrame | None, as_of_date: str) -> pd.DataFrame | None:
    """Drop bars after the signal date so a replay cannot see the future."""
    if df is None or df.empty:
        return df
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    days = pd.DatetimeIndex(idx).normalize()
    cutoff = pd.Timestamp(as_of_date).normalize()
    mask = pd.Series(days <= cutoff, index=df.index)
    sliced = df.loc[mask]
    return sliced if not sliced.empty else df.iloc[0:0]


def filter_scan_rows(
    rows: list[SymbolRow],
    *,
    eligibility_filter: list[str] | None = None,
    only_with_suggestion: bool = False,
    min_score: float = 0,
) -> list[SymbolRow]:
    """Apply the same sidebar filters used by the scanner table and detail picker."""
    filtered = list(rows)
    if eligibility_filter:
        allowed = set(eligibility_filter)
        filtered = [r for r in filtered if r.eligibility.value in allowed]
    if only_with_suggestion:
        filtered = [
            r
            for r in filtered
            if r.has_buy_idea()
        ]
    if min_score > 0:
        filtered = [
            r
            for r in filtered
            if r.score is not None and r.score >= min_score
        ]
    return filtered


def rows_to_dataframe(rows: list[SymbolRow]) -> pd.DataFrame:
    records = []
    for r in rows:
        records.append(
            {
                "Symbol": r.symbol,
                "AsOf": r.as_of_date,
                "Suggestion": r.suggestion_summary or "—",
                "Action": r.suggestion_action or "NONE",
                "Strike": r.suggestion_strike,
                "Opt": r.suggestion_option_type,
                "Breakeven": None
                if r.suggestion_breakeven is None
                else round(r.suggestion_breakeven, 2),
                "Need%": None
                if r.suggestion_required_move_pct is None
                else round(r.suggestion_required_move_pct, 2),
                "Cover×": None
                if r.suggestion_move_cover_ratio is None
                else round(r.suggestion_move_cover_ratio, 2),
                "Spot": r.spot,
                "ATR%": None if r.atr_pct is None else round(r.atr_pct, 3),
                "ATM_IV": None if r.atm_iv is None else round(r.atm_iv, 2),
                "OI": r.oi_atm,
                "Volume": r.volume_atm,
                "PCR": None if r.pcr is None else round(r.pcr, 2),
                "MvPrem": None
                if r.move_vs_premium_ratio is None
                else round(r.move_vs_premium_ratio, 2),
                "DTE": r.dte,
                "Prem/Lot": None
                if r.premium_per_lot is None
                else round(r.premium_per_lot, 0),
                "HV20": None if r.hv_20 is None else round(r.hv_20, 2),
                "RS20": None if r.rs_20 is None else round(r.rs_20, 2),
                "Squeeze": r.squeeze,
                "Trend": r.trend.value,
                "Score": None if r.score is None else round(r.score, 1),
                "Eligibility": r.eligibility.value,
                "Bias": r.direction_bias.value,
                "Tags": ", ".join(r.setup_tags),
                "Status": r.data_status.value,
                "Why": r.why,
            }
        )
    return pd.DataFrame.from_records(records)
