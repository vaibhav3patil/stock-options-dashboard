"""Earnings and corporate-action dates (yfinance + optional local CSV)."""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timezone
import pandas as pd

from app import PROJECT_ROOT
from app.config import get_rules
from app.data.cache import DiskCache
from app.features.selection_overlays import EventInfo

logger = logging.getLogger(__name__)


def _parse_day(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


class EventCalendarProvider:
    def __init__(self, cache: DiskCache | None = None) -> None:
        self.cache = cache or DiskCache()
        self.local_path = PROJECT_ROOT / "data" / "events.csv"

    def get_event(self, symbol: str, *, force_refresh: bool = False) -> EventInfo:
        local = self._from_local_csv(symbol)
        if local.days_ahead is not None:
            return local
        return self._from_yfinance(symbol, force_refresh=force_refresh)

    def _from_local_csv(self, symbol: str) -> EventInfo:
        if not self.local_path.exists():
            return EventInfo(source="none")
        today = date.today()
        best: EventInfo | None = None
        try:
            with self.local_path.open(encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if (row.get("symbol") or "").strip().upper() != symbol.upper():
                        continue
                    day = _parse_day(row.get("date"))
                    if day is None:
                        continue
                    days = (day - today).days
                    if days < -1:
                        continue
                    kind = (row.get("type") or "OTHER").strip().upper()
                    info = EventInfo(kind=kind, date=day.isoformat(), days_ahead=days, source="csv")
                    if best is None or (info.days_ahead or 99) < (best.days_ahead or 99):
                        best = info
        except Exception as exc:
            logger.warning("Local events.csv failed: %s", exc)
        return best or EventInfo(source="none")

    def _from_yfinance(self, symbol: str, *, force_refresh: bool) -> EventInfo:
        key = f"events_{symbol.upper()}"
        ttl = get_rules().cache_ttl_seconds.ohlc_daily
        if not force_refresh:
            cached = self.cache.get_json(key, ttl_seconds=ttl)
            if isinstance(cached, dict):
                return EventInfo(
                    kind=cached.get("kind"),
                    date=cached.get("date"),
                    days_ahead=cached.get("days_ahead"),
                    source=cached.get("source") or "yfinance",
                )

        info = self._fetch_yfinance(symbol)
        self.cache.set_json(
            key,
            {
                "kind": info.kind,
                "date": info.date,
                "days_ahead": info.days_ahead,
                "source": info.source,
            },
        )
        return info

    def _fetch_yfinance(self, symbol: str) -> EventInfo:
        try:
            import yfinance as yf
        except Exception:
            return EventInfo(source="none")

        ticker = yf.Ticker(f"{symbol.upper()}.NS")
        today = date.today()
        candidates: list[EventInfo] = []

        try:
            cal = ticker.get_earnings_dates(limit=8)
            if cal is not None and not cal.empty:
                idx = cal.index
                for stamp in idx:
                    day = _parse_day(stamp)
                    if day is None:
                        continue
                    days = (day - today).days
                    if -1 <= days <= 45:
                        candidates.append(
                            EventInfo(
                                kind="EARNINGS",
                                date=day.isoformat(),
                                days_ahead=days,
                                source="yfinance",
                            )
                        )
        except Exception as exc:
            logger.debug("Earnings dates failed for %s: %s", symbol, exc)

        try:
            div = ticker.dividends
            if div is not None and not div.empty:
                last = _parse_day(div.index[-1])
                if last is not None:
                    days = (last - today).days
                    if 0 <= days <= 10 or -5 <= days <= 0:
                        candidates.append(
                            EventInfo(
                                kind="DIVIDEND",
                                date=last.isoformat(),
                                days_ahead=max(days, 0),
                                source="yfinance",
                            )
                        )
        except Exception:
            pass

        try:
            splits = ticker.splits
            if splits is not None and not splits.empty:
                last = _parse_day(splits.index[-1])
                if last is not None and abs((last - today).days) <= 5:
                    candidates.append(
                        EventInfo(
                            kind="SPLIT",
                            date=last.isoformat(),
                            days_ahead=max((last - today).days, 0),
                            source="yfinance",
                        )
                    )
        except Exception:
            pass

        if not candidates:
            return EventInfo(source="yfinance")
        candidates.sort(key=lambda e: e.days_ahead if e.days_ahead is not None else 99)
        return candidates[0]
