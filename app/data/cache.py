from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.config import get_cache_dir


def safe_cache_key(key: str) -> str:
    """Keep cache filenames inside the cache directory (no path traversal)."""
    cleaned = []
    for ch in key:
        if ch.isalnum() or ch in "-_.":
            cleaned.append(ch)
        else:
            cleaned.append("_")
    safe = "".join(cleaned).replace("..", "_")
    return safe or "cache_key"


class DiskCache:
    """Simple TTL disk cache for DataFrames (parquet/csv) and JSON blobs."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_cache_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_key(key: str) -> str:
        return safe_cache_key(key)

    def _meta_path(self, key: str) -> Path:
        return self.root / f"{self._safe_key(key)}.meta.json"

    def _parquet_path(self, key: str) -> Path:
        return self.root / f"{self._safe_key(key)}.parquet"

    def _csv_path(self, key: str) -> Path:
        return self.root / f"{self._safe_key(key)}.csv"

    def _json_path(self, key: str) -> Path:
        return self.root / f"{self._safe_key(key)}.json"

    def get_df(self, key: str, ttl_seconds: int) -> Optional[pd.DataFrame]:
        meta_path = self._meta_path(key)
        if not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            saved_at = float(meta.get("saved_at", 0))
            if time.time() - saved_at > ttl_seconds:
                return None
            fmt = meta.get("format", "parquet")
            if fmt == "csv":
                csv_path = self._csv_path(key)
                if not csv_path.exists():
                    return None
                return pd.read_csv(csv_path, index_col=0, parse_dates=True)
            data_path = self._parquet_path(key)
            if not data_path.exists():
                return None
            return pd.read_parquet(data_path)
        except Exception:
            return None

    def set_df(self, key: str, df: pd.DataFrame) -> None:
        meta_path = self._meta_path(key)
        try:
            data_path = self._parquet_path(key)
            df.to_parquet(data_path)
            meta_path.write_text(
                json.dumps(
                    {"saved_at": time.time(), "rows": len(df), "format": "parquet"}
                ),
                encoding="utf-8",
            )
        except Exception:
            csv_path = self._csv_path(key)
            df.to_csv(csv_path)
            meta_path.write_text(
                json.dumps(
                    {"saved_at": time.time(), "rows": len(df), "format": "csv"}
                ),
                encoding="utf-8",
            )

    def get_json(self, key: str, ttl_seconds: int) -> Optional[Any]:
        meta_path = self._meta_path(key)
        data_path = self._json_path(key)
        if not meta_path.exists() or not data_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            saved_at = float(meta.get("saved_at", 0))
            if time.time() - saved_at > ttl_seconds:
                return None
            return json.loads(data_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def set_json(self, key: str, payload: Any) -> None:
        data_path = self._json_path(key)
        meta_path = self._meta_path(key)
        data_path.write_text(json.dumps(payload), encoding="utf-8")
        meta_path.write_text(
            json.dumps({"saved_at": time.time()}),
            encoding="utf-8",
        )
