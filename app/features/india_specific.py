"""India-specific gates (ban, ASM, VIX, circuits, corp actions) — Phase 4 stubs."""

from __future__ import annotations

from typing import Optional


def is_fno_banned(symbol: str, ban_list: list[str] | None) -> bool:
    if not ban_list:
        return False
    return symbol.upper() in {s.upper() for s in ban_list}


def vix_regime_warning(india_vix: Optional[float]) -> Optional[str]:
    if india_vix is None:
        return None
    if india_vix >= 20:
        return "IN3: elevated India VIX"
    return None
