from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import yfinance as yf

from app.config import RulesConfig, get_rules
from app.data.cache import DiskCache
from app.data.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

NIFTY_YF = "^NSEI"


def to_yfinance_ticker(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym in {"NIFTY", "NIFTY50", "NSEI"}:
        return NIFTY_YF
    if sym.startswith("^"):
        return sym
    return f"{sym}.NS"


class YFinanceOHLCProvider(MarketDataProvider):
    """Equity / index OHLC via yfinance with disk TTL cache."""

    def __init__(
        self,
        rules: RulesConfig | None = None,
        cache: DiskCache | None = None,
    ) -> None:
        self.rules = rules or get_rules()
        self.cache = cache or DiskCache()

    def get_ohlc(
        self,
        symbol: str,
        *,
        period_days: int = 400,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        ticker = to_yfinance_ticker(symbol)
        cache_key = f"ohlc_{ticker}_{period_days}"
        ttl = self.rules.cache_ttl_seconds.ohlc_daily

        if not force_refresh:
            cached = self.cache.get_df(cache_key, ttl)
            if cached is not None and not cached.empty:
                return cached

        # yfinance period strings are coarse; request enough history then trim
        period = "2y" if period_days >= 300 else "1y"
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval="1d",
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:
            logger.warning("yfinance download failed for %s: %s", ticker, exc)
            raise

        if raw is None or raw.empty:
            raise ValueError(f"No OHLC data for {ticker}")

        # Flatten MultiIndex columns if present (yfinance >= 0.2)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]

        df = raw.rename(columns=str.title)
        needed = ["Open", "High", "Low", "Close", "Volume"]
        missing = [c for c in needed if c not in df.columns]
        if missing:
            # Some downloads use lowercase
            lower_map = {c.lower(): c for c in df.columns}
            rename = {}
            for col in needed:
                if col not in df.columns and col.lower() in lower_map:
                    rename[lower_map[col.lower()]] = col
            df = df.rename(columns=rename)

        df = df[[c for c in needed if c in df.columns]].dropna(how="all")
        if len(df) > period_days:
            df = df.iloc[-period_days:]

        self.cache.set_df(cache_key, df)
        return df

    def get_nifty_ohlc(
        self,
        *,
        period_days: int = 400,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        return self.get_ohlc(
            "NIFTY",
            period_days=period_days,
            force_refresh=force_refresh,
        )

    def get_option_chain(
        self,
        symbol: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Option chain not available on YFinanceOHLCProvider; use NseOptionChainProvider"
        )

    def get_events(self, symbol: str) -> list[dict[str, Any]]:
        return []

    def get_ban_list(self) -> list[str]:
        return []
