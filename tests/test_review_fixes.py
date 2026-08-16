from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.config import get_rules
from app.data.cache import safe_cache_key
from app.data.providers.nse_bhavcopy import (
    NseBhavcopyProvider,
    safe_zip_member,
)
from app.features.selection_overlays import EventInfo
from app.models.schemas import Eligibility, SymbolMeta, SymbolRow
from app.scanner import ScannerService, _gather_symbol_rows, slice_ohlc_as_of


def test_safe_cache_key_strips_traversal():
    key = safe_cache_key("../../etc/passwd")
    assert ".." not in key
    assert "/" not in key
    assert "\\" not in key


def test_safe_zip_member_rejects_parent_paths():
    with pytest.raises(ValueError, match="Unsafe"):
        safe_zip_member(["../secret.csv"])
    with pytest.raises(ValueError, match="Unsafe"):
        safe_zip_member(["/tmp/abs.csv"])
    assert safe_zip_member(["BhavCopy.csv"]) == "BhavCopy.csv"


def test_list_recent_sessions_skips_weekends(monkeypatch):
    called: list[str] = []
    provider = NseBhavcopyProvider()

    def fake_session(ymd: str) -> pd.DataFrame:
        called.append(ymd)
        return pd.DataFrame({"a": [1]})

    monkeypatch.setattr(
        "app.data.providers.nse_bhavcopy.expected_session_date",
        lambda now=None: date(2026, 8, 14),
    )
    monkeypatch.setattr(provider, "get_session_bhav", fake_session)
    found = provider.list_recent_sessions(3, calendar_lookback=10)
    assert found == ["2026-08-14", "2026-08-13", "2026-08-12"]
    assert all(date.fromisoformat(d).weekday() < 5 for d in called)


def test_slice_ohlc_as_of_drops_later_bars():
    idx = pd.date_range("2026-08-03", periods=8, freq="B")
    df = pd.DataFrame({"Close": range(8)}, index=idx)
    sliced = slice_ohlc_as_of(df, "2026-08-06")
    assert sliced is not None
    assert sliced.index.max() <= pd.Timestamp("2026-08-06")


def test_scan_symbol_slices_live_ohlc_to_as_of():
    idx = pd.date_range("2026-01-01", periods=80, freq="B")
    close = np.linspace(100.0, 180.0, 80)
    close[-5:] = 999.0
    ohlc = pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": np.full(80, 1000),
        },
        index=idx,
    )
    as_of = idx[-6].date().isoformat()
    row = ScannerService().scan_symbol(
        SymbolMeta(symbol="TESTCO"),
        ohlc,
        None,
        as_of,
        [],
        ohlc=ohlc,
        event=EventInfo(source="none"),
        record_iv=False,
    )
    assert row.spot is not None
    assert row.spot < 200


def test_worker_exception_does_not_abort_scan():
    def work(meta: SymbolMeta) -> SymbolRow:
        if meta.symbol == "BAD":
            raise RuntimeError("boom")
        return SymbolRow(symbol=meta.symbol)

    metas = [SymbolMeta(symbol="OK"), SymbolMeta(symbol="BAD")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(work, meta): meta for meta in metas}
        rows = _gather_symbol_rows(futures)
    by_symbol = {row.symbol: row for row in rows}
    assert set(by_symbol) == {"OK", "BAD"}
    assert by_symbol["BAD"].eligibility == Eligibility.EXCLUDE
    assert "IN12" in by_symbol["BAD"].failed_rules


def test_get_rules_reloads_when_file_changes(tmp_path, monkeypatch):
    path = tmp_path / "rules.yaml"
    path.write_text("scan:\n  max_workers: 1\n", encoding="utf-8")
    monkeypatch.setenv("OPTION_DASHBOARD_RULES_PATH", str(path))
    import app.config as cfg

    cfg._rules_cache = None
    assert get_rules().scan.max_workers == 1
    path.write_text("scan:\n  max_workers: 3\n", encoding="utf-8")
    assert get_rules().scan.max_workers == 3
