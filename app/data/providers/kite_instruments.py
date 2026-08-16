from __future__ import annotations

from typing import Any

import pandas as pd

KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"


def fetch_nfo_stock_names(url: str = KITE_INSTRUMENTS_URL) -> list[str]:
    """Pull unique NFO underlying names (stocks / named indices)."""
    df = pd.read_csv(url)
    stock_options = df[
        (df["exchange"] == "NFO")
        & (df["name"].notna())
        & (df["name"].astype(str).str.strip() != "")
    ]
    names = sorted({str(n).strip().upper() for n in stock_options["name"].tolist()})
    return names


class KiteInstrumentsProvider:
    """Thin wrapper around public Kite instruments CSV (no auth)."""

    def list_fno_underlyings(self) -> list[str]:
        return fetch_nfo_stock_names()

    def get_option_chain(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("Kite Connect paid API not enabled in v1")
