"""NSE F&O securities in ban period (EOD archive)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from app.config import RulesConfig, get_rules
from app.data.cache import DiskCache

logger = logging.getLogger(__name__)


class NseBanListProvider:
    def __init__(self, rules: RulesConfig | None = None, cache: DiskCache | None = None) -> None:
        self.rules = rules or get_rules()
        self.cache = cache or DiskCache()

    def get_ban_list(self, as_of: str | None = None, *, force_refresh: bool = False) -> list[str]:
        key = f"fno_ban_{as_of or 'latest'}"
        ttl = self.rules.cache_ttl_seconds.ban_list
        if not force_refresh:
            cached = self.cache.get_json(key, ttl_seconds=ttl)
            if isinstance(cached, list):
                return [str(s).upper() for s in cached]

        symbols = self._fetch(as_of)
        self.cache.set_json(key, symbols)
        return symbols

    def _fetch(self, as_of: str | None) -> list[str]:
        try:
            from nselib.derivatives import fno_security_in_ban_period
        except Exception as exc:
            logger.warning("nselib ban helper unavailable: %s", exc)
            return []

        start = date.today()
        if as_of:
            try:
                start = datetime.strptime(as_of, "%Y-%m-%d").date()
            except ValueError:
                pass

        for delta in range(0, 8):
            day = start - timedelta(days=delta)
            stamp = day.strftime("%d-%m-%Y")
            try:
                raw = fno_security_in_ban_period(trade_date=stamp)
            except Exception as exc:
                logger.debug("Ban list miss %s: %s", stamp, exc)
                continue
            out: list[str] = []
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.strip() and item.strip().lower() != "symbol":
                        out.append(item.strip().upper())
            if out:
                logger.info("F&O ban list as-of %s: %s names", stamp, len(out))
                return out
        logger.warning("F&O ban list unavailable — IN1 will be soft")
        return []
