"""Persist daily ATM IV estimates and compute IV Rank / Percentile."""

from __future__ import annotations

from typing import Optional

from app.data.cache import DiskCache
from app.features.volatility import iv_percentile, iv_rank


class IvHistoryStore:
    def __init__(self, cache: DiskCache | None = None) -> None:
        self.cache = cache or DiskCache()

    def _key(self, symbol: str) -> str:
        return f"iv_hist_{symbol.upper()}"

    def record(self, symbol: str, as_of: str | None, iv: Optional[float]) -> list[float]:
        if iv is None or iv <= 0:
            return self.history(symbol)
        key = self._key(symbol)
        payload = self.cache.get_json(key, ttl_seconds=10 * 365 * 86400) or {"points": []}
        points = list(payload.get("points") or [])
        if as_of:
            points = [p for p in points if p.get("date") != as_of]
            points.append({"date": as_of, "iv": float(iv)})
        else:
            points.append({"date": None, "iv": float(iv)})
        points = points[-260:]
        self.cache.set_json(key, {"points": points})
        return [float(p["iv"]) for p in points if p.get("iv") is not None]

    def history(self, symbol: str) -> list[float]:
        payload = self.cache.get_json(self._key(symbol), ttl_seconds=10 * 365 * 86400) or {}
        return [float(p["iv"]) for p in payload.get("points") or [] if p.get("iv") is not None]

    def rank(self, symbol: str, current_iv: Optional[float]) -> tuple[Optional[float], Optional[float], int]:
        hist = self.history(symbol)
        if current_iv is None:
            return None, None, len(hist)
        if current_iv not in hist and current_iv > 0:
            hist = hist + [float(current_iv)]
        n = len(hist)
        if n < 5:
            return None, None, n
        return iv_rank(float(current_iv), hist), iv_percentile(float(current_iv), hist), n
