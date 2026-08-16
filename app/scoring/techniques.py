"""Named technique modules A–J + IN* — stubs for Phase 2+."""

from __future__ import annotations

TECHNIQUE_IDS = list("ABCDEFHJ")  # G,I deferred per rules doc
INDIA_RULE_IDS = [f"IN{i}" for i in range(1, 13)]


def list_technique_ids() -> list[str]:
    return TECHNIQUE_IDS + INDIA_RULE_IDS
