"""Volatility helpers (IV Rank/Percentile) — Phase 3 stubs."""

from __future__ import annotations

from typing import Optional


def iv_rank(current_iv: float, history: list[float]) -> Optional[float]:
    if not history:
        return None
    lo, hi = min(history), max(history)
    if hi <= lo:
        return 50.0
    return (current_iv - lo) / (hi - lo) * 100.0


def iv_percentile(current_iv: float, history: list[float]) -> Optional[float]:
    if not history:
        return None
    below = sum(1 for v in history if v < current_iv)
    return below / len(history) * 100.0
