from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.config import RulesConfig, resolve_universe_csv
from app.models.schemas import InstrumentType, SymbolMeta


def tag_instrument_type(symbol: str, index_symbols: list[str]) -> InstrumentType:
    normalized = symbol.strip().upper()
    index_set = {s.strip().upper() for s in index_symbols}
    if normalized in index_set:
        return InstrumentType.INDEX
    return InstrumentType.STOCK


def load_universe(
    rules: RulesConfig,
    csv_path: Path | None = None,
) -> list[SymbolMeta]:
    path = csv_path or resolve_universe_csv(rules)
    if not path.exists():
        raise FileNotFoundError(f"Universe CSV not found: {path}")

    df = pd.read_csv(path)
    if "Stock_Name" not in df.columns:
        raise ValueError(f"Expected column 'Stock_Name' in {path}")

    symbols = (
        df["Stock_Name"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .loc[lambda s: s != ""]
        .unique()
        .tolist()
    )

    return [
        SymbolMeta(
            symbol=sym,
            instrument_type=tag_instrument_type(sym, rules.universe.index_symbols),
        )
        for sym in symbols
    ]


def filter_liquid_subset(
    universe: list[SymbolMeta],
    rules: RulesConfig,
    *,
    use_subset: bool,
) -> list[SymbolMeta]:
    if not use_subset:
        return universe
    subset = {s.strip().upper() for s in rules.universe.liquid_subset}
    if not subset:
        return universe[:20]
    filtered = [row for row in universe if row.symbol in subset]
    # Preserve configured order for liquid subset members present in universe
    order = {sym: i for i, sym in enumerate(rules.universe.liquid_subset)}
    filtered.sort(key=lambda r: order.get(r.symbol, 10_000))
    return filtered or universe[:20]
