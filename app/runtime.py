"""Process-level versioning so deploys never keep a stale scanner in memory."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.data.providers.nse_bhavcopy import NseBhavcopyProvider
from app.features.backtest import BacktestService
from app.scanner import ScannerService

_APP_DIR = Path(__file__).resolve().parent
_FINGERPRINT_FILES = (
    "scanner.py",
    "runtime.py",
    "streamlit_app.py",
    "data/providers/nse_bhavcopy.py",
    "features/backtest.py",
    "features/priority.py",
    "features/trade_plan.py",
    "ui.py",
)


def app_version() -> str:
    """Release id from the host (git SHA, image tag). Falls back to source hash."""
    env = (os.getenv("APP_VERSION") or os.getenv("GIT_SHA") or "").strip()
    return env or source_revision()


def source_revision() -> str:
    digest = hashlib.sha256()
    for rel in _FINGERPRINT_FILES:
        path = _APP_DIR / rel
        digest.update(rel.encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def assert_runtime_api() -> None:
    """Fail fast if this process loaded an old provider/scanner mix."""
    missing: list[str] = []
    checks = (
        (ScannerService, "scan_as_of"),
        (ScannerService, "scan_many"),
        (NseBhavcopyProvider, "list_recent_sessions"),
        (NseBhavcopyProvider, "get_session_bhav"),
        (BacktestService, "run"),
    )
    for cls, name in checks:
        if not callable(getattr(cls, name, None)):
            missing.append(f"{cls.__name__}.{name}")
    if missing:
        raise RuntimeError(
            "App process is running stale code. Restart the Streamlit/server "
            f"process after deploy. Missing: {', '.join(missing)}"
        )


def build_scanner() -> ScannerService:
    """Always construct a new service. Data stays on disk; do not cache this object."""
    assert_runtime_api()
    return ScannerService()
