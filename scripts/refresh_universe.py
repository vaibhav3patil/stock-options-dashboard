#!/usr/bin/env python3
"""Refresh F&O universe CSV from Zerodha Kite instruments (no auth)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.data.providers.kite_instruments import fetch_nfo_stock_names


def main() -> None:
    out = _PROJECT_ROOT / "fno_only_stocks.csv"
    names = fetch_nfo_stock_names()
    pd.Series(names, name="Stock_Name").to_csv(out, index=False, header=["Stock_Name"])
    print(f"Saved {len(names)} underlyings to {out}")


if __name__ == "__main__":
    main()
