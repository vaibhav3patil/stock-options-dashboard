from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests

from app.config import RulesConfig, get_rules
from app.data.cache import DiskCache

logger = logging.getLogger(__name__)

BHAV_URL_PREFIX = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_"
)
IST = timezone(timedelta(hours=5, minutes=30))


def expected_session_date(now: datetime | None = None) -> date:
    """Most recent weekday in IST (weekends roll back to Friday)."""
    if now is None:
        current = datetime.now(IST)
    elif now.tzinfo is None:
        current = now.replace(tzinfo=IST)
    else:
        current = now.astimezone(IST)
    day = current.date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def norm_expiry(value: object) -> str:
    """Normalize an expiry cell to YYYY-MM-DD when parseable."""
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return str(value)
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def filter_fo_options(
    bhav: pd.DataFrame | None,
    symbol: str,
    *,
    option_type: str | None = None,
    strike: float | None = None,
    expiry: str | None = None,
) -> pd.DataFrame:
    """Stock options for one symbol; optional CE/PE, strike, and expiry filters."""
    if bhav is None or bhav.empty or "TckrSymb" not in bhav.columns:
        return pd.DataFrame()
    df = bhav.loc[bhav["TckrSymb"].astype(str).str.upper() == symbol.upper()]
    if "FinInstrmTp" in df.columns:
        df = df[df["FinInstrmTp"].astype(str).str.upper() == "STO"]
    if option_type and "OptnTp" in df.columns:
        df = df[df["OptnTp"].astype(str).str.upper() == option_type.upper()]
    elif "OptnTp" in df.columns:
        df = df[df["OptnTp"].astype(str).str.upper().isin(["CE", "PE"])]
    if strike is not None and "StrkPric" in df.columns:
        df = df[abs(df["StrkPric"].astype(float) - float(strike)) < 0.05]
    if expiry is not None and "XpryDt" in df.columns:
        want = norm_expiry(expiry)
        df = df[df["XpryDt"].map(norm_expiry) == want]
    return df.reset_index(drop=True)


def safe_zip_member(names: list[str]) -> str:
    """Reject zip-slip paths from a downloaded bhav archive."""
    if not names:
        raise ValueError("Empty zip archive")
    name = names[0]
    if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
        raise ValueError(f"Unsafe zip member: {name}")
    return name


class NseBhavcopyProvider:
    """EOD F&O bhavcopy (last market close) — primary source for option selection."""

    def __init__(
        self,
        rules: RulesConfig | None = None,
        cache: DiskCache | None = None,
        *,
        lookback_days: int = 14,
    ) -> None:
        self.rules = rules or get_rules()
        self.cache = cache or DiskCache()
        self.lookback_days = lookback_days
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )

    def _cache_key(self, trade_date: str) -> str:
        return f"fo_bhav_{trade_date}"

    def _download_date(self, day: datetime) -> Optional[pd.DataFrame]:
        ymd = day.strftime("%Y%m%d")
        url = f"{BHAV_URL_PREFIX}{ymd}_F_0000.csv.zip"
        try:
            resp = self._session.get(url, timeout=45)
        except Exception as exc:
            logger.warning("Bhav download error %s: %s", ymd, exc)
            return None
        if resp.status_code != 200 or len(resp.content) < 1000:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                name = safe_zip_member(zf.namelist())
                df = pd.read_csv(zf.open(name))
            if df is None or df.empty:
                return None
            df["_trade_date"] = day.strftime("%Y-%m-%d")
            return df
        except Exception as exc:
            logger.warning("Bhav parse error %s: %s", ymd, exc)
            return None

    def fetch_bhavcopy(self, trade_date: str | None = None) -> pd.DataFrame:
        """
        Fetch F&O bhavcopy for `trade_date` (YYYY-MM-DD or DD-MM-YYYY).
        If None, finds the latest available session within lookback.
        """
        if trade_date:
            for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                try:
                    day = datetime.strptime(trade_date, fmt)
                    break
                except ValueError:
                    day = None
            if day is None:
                raise ValueError(f"Unrecognized trade_date: {trade_date}")
            df = self._download_date(day)
            if df is None or df.empty:
                raise FileNotFoundError(f"No F&O bhavcopy for {trade_date}")
            return df

        # Walk back calendar days until a file exists (skips weekends/holidays)
        today = datetime.now(IST)
        for i in range(self.lookback_days):
            day = today - timedelta(days=i)
            if day.weekday() >= 5:
                continue
            ymd = day.strftime("%Y-%m-%d")
            cache_key = self._cache_key(ymd)
            cached = self.cache.get_df(
                cache_key, ttl_seconds=self.rules.cache_ttl_seconds.ohlc_daily
            )
            if cached is not None and not cached.empty:
                return cached

            df = self._download_date(day)
            if df is not None and not df.empty:
                self.cache.set_df(cache_key, df)
                self.cache.set_json(
                    "fo_bhav_latest_meta",
                    {"trade_date": ymd, "rows": len(df)},
                )
                return df
        raise FileNotFoundError("No F&O bhavcopy found in lookback window")

    def get_session_bhav(self, trade_date: str) -> pd.DataFrame:
        """Bhav for one session. Historical files are cached (they do not change)."""
        key = self._cache_key(trade_date)
        cached = self.cache.get_df(key, ttl_seconds=30 * 86400)
        if cached is not None and not cached.empty:
            return cached
        df = self.fetch_bhavcopy(trade_date)
        if df is not None and not df.empty:
            self.cache.set_df(key, df)
        return df

    def list_recent_sessions(self, count: int, *, calendar_lookback: int = 45) -> list[str]:
        """Newest-first session dates that have a published F&O bhavcopy."""
        found: list[str] = []
        start = expected_session_date()
        for i in range(calendar_lookback):
            day = start - timedelta(days=i)
            if day.weekday() >= 5:
                continue
            ymd = day.isoformat()
            try:
                df = self.get_session_bhav(ymd)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            found.append(ymd)
            if len(found) >= count:
                break
        return found

    def get_latest_bhav(
        self, *, force_refresh: bool = False
    ) -> tuple[pd.DataFrame, str]:
        meta = self.cache.get_json(
            "fo_bhav_latest_meta",
            ttl_seconds=self.rules.cache_ttl_seconds.ohlc_daily,
        )
        cached_date = (
            str(meta.get("trade_date"))
            if not force_refresh and isinstance(meta, dict) and meta.get("trade_date")
            else None
        )
        # A 24h TTL is not enough: Thursday's file stays "fresh" all Saturday
        # and hides Friday's close. Only reuse cache if it is the latest weekday.
        if cached_date and cached_date >= expected_session_date().isoformat():
            cached = self.cache.get_df(
                self._cache_key(cached_date),
                ttl_seconds=self.rules.cache_ttl_seconds.ohlc_daily,
            )
            if cached is not None and not cached.empty:
                return cached, cached_date

        df = self.fetch_bhavcopy(None)
        trade_date = str(df["_trade_date"].iloc[0]) if "_trade_date" in df.columns else ""
        if not trade_date and "TradDt" in df.columns:
            trade_date = str(pd.to_datetime(df["TradDt"].iloc[0]).date())
        return df, trade_date

    def symbol_options(
        self, bhav: pd.DataFrame, symbol: str
    ) -> pd.DataFrame:
        return filter_fo_options(bhav, symbol)

    def get_atm_iv_history(self, symbol: str) -> list[dict[str, Any]]:
        return []
