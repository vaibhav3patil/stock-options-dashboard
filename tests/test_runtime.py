from __future__ import annotations

from app.data.providers.nse_bhavcopy import NseBhavcopyProvider
from app.runtime import app_version, assert_runtime_api, build_scanner, source_revision
from app.scanner import ScannerService


def test_runtime_api_is_complete():
    assert_runtime_api()
    assert callable(ScannerService.scan_as_of)
    assert callable(NseBhavcopyProvider.list_recent_sessions)
    assert callable(NseBhavcopyProvider.get_session_bhav)


def test_build_scanner_is_a_fresh_instance():
    first = build_scanner()
    second = build_scanner()
    assert first is not second
    assert hasattr(first.bhav, "list_recent_sessions")


def test_version_is_non_empty():
    assert source_revision()
    assert app_version()
