from __future__ import annotations

import logging
from functools import lru_cache

import pandas as pd

from app.data.cache import DiskCache
from app.data.providers.kite_instruments import KITE_INSTRUMENTS_URL

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_nfo_lot_map() -> dict[str, int]:
    try:
        df = pd.read_csv(KITE_INSTRUMENTS_URL)
    except Exception as exc:
        logger.warning("Failed to load Kite instruments for lot sizes: %s", exc)
        return {}
    nfo = df[(df["exchange"] == "NFO") & (df["name"].notna())]
    # Prefer option rows for lot size
    opts = nfo[nfo["instrument_type"].isin(["CE", "PE"])]
    lots: dict[str, int] = {}
    for name, group in opts.groupby(opts["name"].astype(str).str.upper()):
        vals = group["lot_size"].dropna().astype(int)
        if not vals.empty:
            lots[str(name)] = int(vals.mode().iloc[0])
    return lots


def get_lot_size(symbol: str, cache: DiskCache | None = None) -> int | None:
    sym = symbol.upper()
    disk = cache or DiskCache()
    cached = disk.get_json("kite_lot_sizes", ttl_seconds=86400)
    if isinstance(cached, dict) and sym in cached:
        return int(cached[sym])

    lots = _load_nfo_lot_map()
    if lots:
        disk.set_json("kite_lot_sizes", lots)
    return lots.get(sym)
