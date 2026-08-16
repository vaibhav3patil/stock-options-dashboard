from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.config import RulesConfig, UniverseConfig, load_rules
from app.models.schemas import InstrumentType
from app.universe import filter_liquid_subset, load_universe, tag_instrument_type


def test_tag_instrument_type_index():
    assert tag_instrument_type("NIFTY", ["NIFTY", "BANKNIFTY"]) == InstrumentType.INDEX
    assert tag_instrument_type("banknifty", ["BANKNIFTY"]) == InstrumentType.INDEX


def test_tag_instrument_type_stock():
    assert tag_instrument_type("RELIANCE", ["NIFTY"]) == InstrumentType.STOCK


def test_load_universe_from_csv(tmp_path: Path):
    csv_path = tmp_path / "uni.csv"
    pd.DataFrame({"Stock_Name": ["RELIANCE", "NIFTY", "TCS"]}).to_csv(
        csv_path, index=False
    )
    rules = RulesConfig(
        universe=UniverseConfig(
            csv_path=str(csv_path),
            index_symbols=["NIFTY", "BANKNIFTY"],
            liquid_subset=["TCS", "RELIANCE"],
        )
    )
    rows = load_universe(rules, csv_path=csv_path)
    by_sym = {r.symbol: r for r in rows}
    assert by_sym["NIFTY"].instrument_type == InstrumentType.INDEX
    assert by_sym["RELIANCE"].instrument_type == InstrumentType.STOCK


def test_filter_liquid_subset_preserves_order():
    rules = RulesConfig(
        universe=UniverseConfig(
            liquid_subset=["INFY", "TCS", "RELIANCE"],
            index_symbols=[],
        )
    )
    from app.models.schemas import SymbolMeta

    universe = [
        SymbolMeta(symbol="RELIANCE"),
        SymbolMeta(symbol="TCS"),
        SymbolMeta(symbol="INFY"),
        SymbolMeta(symbol="WIPRO"),
    ]
    filtered = filter_liquid_subset(universe, rules, use_subset=True)
    assert [r.symbol for r in filtered] == ["INFY", "TCS", "RELIANCE"]


def test_load_rules_defaults():
    # Project rules.yaml should parse
    cfg = load_rules()
    assert cfg.move_vs_premium.atr_period == 14
    assert "NIFTY" in cfg.universe.index_symbols


def test_packaged_universe_csv_resolves():
    from app.config import resolve_universe_csv

    path = resolve_universe_csv(load_rules())
    assert path.exists()
    assert path.name == "fno_only_stocks.csv"
