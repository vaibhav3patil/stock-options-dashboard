from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import pandas as pd


class MarketDataProvider(ABC):
    """Common interface for market data adapters."""

    @abstractmethod
    def get_ohlc(
        self,
        symbol: str,
        *,
        period_days: int = 400,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Return OHLCV DataFrame indexed by date."""

    @abstractmethod
    def get_option_chain(
        self,
        symbol: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Return option chain payload (Phase 2)."""

    @abstractmethod
    def get_events(self, symbol: str) -> list[dict[str, Any]]:
        """Return earnings / corporate-action events (Phase 4)."""

    @abstractmethod
    def get_ban_list(self) -> list[str]:
        """Return F&O ban-period symbols (Phase 4)."""


class ProviderResult:
    """Helper envelope for provider status messaging."""

    def __init__(
        self,
        *,
        ok: bool,
        data: Any = None,
        status: str = "OK",
        error: Optional[str] = None,
    ) -> None:
        self.ok = ok
        self.data = data
        self.status = status
        self.error = error
