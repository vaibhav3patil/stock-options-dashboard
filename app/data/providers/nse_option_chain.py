"""Live NSE option-chain client.

Not used for desk selection or scoring. The scanner uses EOD F&O bhavcopy.
Kept for tests that exercise `_normalize_chain_payload` and possible future
display-only tools. Do not wire this into `score_with_chain`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import pandas as pd
import requests

from app.config import RulesConfig, get_rules
from app.data.cache import DiskCache
from app.data.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"
EQUITY_CHAIN_URL = "https://www.nseindia.com/api/option-chain-equities"
INDEX_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices"
INDEX_SYMBOLS = {
    "NIFTY",
    "BANKNIFTY",
    "FINNIFTY",
    "MIDCPNIFTY",
    "NIFTYNXT50",
}


def _normalize_chain_payload(raw: Any, symbol: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        return {
            "symbol": symbol.upper(),
            "status": "DATA_UNAVAILABLE",
            "message": "Empty option-chain response",
            "records": {"data": [], "expiryDates": [], "underlyingValue": None},
            "source": None,
        }
    records = raw.get("records") or {}
    data = records.get("data") or []
    if not data:
        return {
            "symbol": symbol.upper(),
            "status": "DATA_UNAVAILABLE",
            "message": "Option chain has no strike rows",
            "records": records if isinstance(records, dict) else {"data": []},
            "filtered": raw.get("filtered"),
            "source": raw.get("_source"),
        }
    return {
        "symbol": symbol.upper(),
        "status": "OK",
        "message": "ok",
        "records": records,
        "filtered": raw.get("filtered"),
        "source": raw.get("_source"),
    }


def _fetch_via_nsepython(symbol: str) -> Optional[dict[str, Any]]:
    try:
        from nsepython import nse_optionchain_scrapper
    except Exception as exc:
        logger.debug("nsepython unavailable: %s", exc)
        return None
    try:
        raw = nse_optionchain_scrapper(symbol.upper())
        if isinstance(raw, dict):
            raw = dict(raw)
            raw["_source"] = "nsepython"
            return raw
    except Exception as exc:
        logger.warning("nsepython chain failed for %s: %s", symbol, exc)
    return None


def _fetch_via_nselib(symbol: str) -> Optional[dict[str, Any]]:
    try:
        from nselib import derivatives
    except Exception as exc:
        logger.debug("nselib unavailable: %s", exc)
        return None
    try:
        df = derivatives.nse_live_option_chain(symbol.upper())
        if df is None or (hasattr(df, "empty") and df.empty):
            return None
        # nselib returns flattened DF; convert back to NSE-like records when possible
        # Prefer re-fetch via its internal path by calling quote API ourselves.
        return None
    except Exception as exc:
        logger.warning("nselib chain failed for %s: %s", symbol, exc)
    return None


def _build_nse_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
        }
    )
    session.get(f"{NSE_HOME}/option-chain", timeout=20)
    time.sleep(0.4)
    session.headers.update(
        {
            "Accept": "application/json,text/plain,*/*",
            "Referer": f"{NSE_HOME}/option-chain",
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    return session


def _fetch_via_nse_http(symbol: str) -> Optional[dict[str, Any]]:
    sym = symbol.upper()
    path = INDEX_CHAIN_URL if sym in INDEX_SYMBOLS else EQUITY_CHAIN_URL
    try:
        session = _build_nse_session()
        resp = session.get(path, params={"symbol": sym}, timeout=25)
        if resp.status_code != 200 or not resp.content or resp.content.strip() in (b"", b"{}"):
            return None
        raw = resp.json()
        if isinstance(raw, dict):
            raw["_source"] = "nse_http"
            return raw
    except Exception as exc:
        logger.warning("NSE HTTP chain failed for %s: %s", symbol, exc)
    return None


class NseOptionChainProvider(MarketDataProvider):
    """NSE equity option chain with cache + multi-source fallback."""

    def __init__(
        self,
        rules: RulesConfig | None = None,
        cache: DiskCache | None = None,
        *,
        fetcher: Callable[[str], Optional[dict[str, Any]]] | None = None,
        pause_seconds: float = 0.35,
    ) -> None:
        self.rules = rules or get_rules()
        self.cache = cache or DiskCache()
        self._fetcher = fetcher
        self.pause_seconds = pause_seconds
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.pause_seconds:
            time.sleep(self.pause_seconds - elapsed)
        self._last_request_ts = time.time()

    def _fetch_live(self, symbol: str) -> dict[str, Any]:
        if self._fetcher is not None:
            raw = self._fetcher(symbol)
            return _normalize_chain_payload(raw, symbol)

        self._throttle()
        for name, fn in (
            ("nsepython", _fetch_via_nsepython),
            ("nse_http", _fetch_via_nse_http),
            ("nselib", _fetch_via_nselib),
        ):
            raw = fn(symbol)
            payload = _normalize_chain_payload(raw, symbol)
            if payload.get("status") == "OK":
                payload["source"] = payload.get("source") or name
                return payload
            logger.info("Option chain source %s unavailable for %s", name, symbol)
        return _normalize_chain_payload(None, symbol)

    def get_option_chain(
        self,
        symbol: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        cache_key = f"chain_{sym}"
        ttl = self.rules.cache_ttl_seconds.option_chain

        if not force_refresh:
            cached = self.cache.get_json(cache_key, ttl)
            if isinstance(cached, dict) and cached.get("status") == "OK":
                return cached

        payload = self._fetch_live(sym)
        if payload.get("status") == "OK":
            self.cache.set_json(cache_key, payload)
        return payload

    def get_ohlc(
        self,
        symbol: str,
        *,
        period_days: int = 400,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        raise NotImplementedError("Use YFinanceOHLCProvider for OHLC")

    def get_events(self, symbol: str) -> list[dict[str, Any]]:
        return []

    def get_ban_list(self) -> list[str]:
        return []
