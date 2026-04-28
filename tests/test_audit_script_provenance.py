"""Tests asserting Phase 79 DQ-01 contract — every audit-script JSON payload
embeds a script_provenance block with {sha, dirty, resolved_at} keys.

Also asserts D-08: historical v7.1 audit JSONs are NOT backfilled in place.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PROVENANCE_KEYS = {"sha", "dirty", "resolved_at"}


def _assert_provenance(provenance: dict) -> None:
    assert isinstance(provenance, dict), provenance
    assert set(provenance.keys()) == PROVENANCE_KEYS, provenance
    assert isinstance(provenance["sha"], str)
    assert provenance["sha"] == "unknown" or len(provenance["sha"]) == 40
    assert isinstance(provenance["dirty"], bool)
    assert isinstance(provenance["resolved_at"], str)


# -----------------------------------------------------------------------
# 1. audit_event_coverage._build_json_payload
# -----------------------------------------------------------------------
def test_event_coverage_payload_has_script_provenance() -> None:
    from scripts.audit_event_coverage import _build_json_payload

    payload = _build_json_payload(
        base_url="https://example.test",
        season=2025,
        weeks=(17, 18),
        rows=[],
        teams_with_events=0,
        passed=False,
    )

    assert "script_provenance" in payload, list(payload.keys())
    _assert_provenance(payload["script_provenance"])


# -----------------------------------------------------------------------
# 2. audit_advisor_tools_evt05._build_payload
# -----------------------------------------------------------------------
def test_evt05_payload_has_script_provenance() -> None:
    from scripts.audit_advisor_tools_evt05 import _build_payload

    payload = _build_payload(
        base_url="https://example.test",
        season=2025,
        weeks=(17, 18),
        feed_limit=200,
        player_teams=set(),
        team_teams=set(),
    )

    assert "script_provenance" in payload, list(payload.keys())
    _assert_provenance(payload["script_provenance"])


# -----------------------------------------------------------------------
# 3. audit_advisor_tools.write_audit_json
# -----------------------------------------------------------------------
def test_advisor_tools_json_sidecar_has_script_provenance(tmp_path: Path) -> None:
    from scripts.audit_advisor_tools import write_audit_json

    out = tmp_path / "TOOL-AUDIT.json"
    write_audit_json(
        results=[
            {
                "verdict": "PASS",
                "tool_name": "getX",
                "endpoint": "/api/x",
                "status_code": 200,
                "latency_ms": 12,
                "category": "OK",
                "reason": "ok",
                "sample": "",
                "body_keys": "",
                "error": "",
                "params": {},
            }
        ],
        out_path=out,
        base_url="https://example.test",
        auth_header_present=False,
    )

    data = json.loads(out.read_text())
    assert "script_provenance" in data, list(data.keys())
    _assert_provenance(data["script_provenance"])
    assert data["summary"] == {"pass": 1, "warn": 0, "fail": 0, "total": 1}


# -----------------------------------------------------------------------
# 4. D-08 forward-only — historical v7.1 audit JSONs not backfilled
# -----------------------------------------------------------------------
HISTORICAL_PATHS = [
    Path(".planning/milestones/v7.1-phases/72-event-flag-expansion/audit/event_coverage.json"),
    Path(".planning/milestones/v7.1-phases/72-event-flag-expansion/audit/advisor_tools_72.json"),
]


@pytest.mark.parametrize("rel_path", HISTORICAL_PATHS, ids=lambda p: p.name)
def test_historical_audit_json_not_backfilled(rel_path: Path) -> None:
    """D-08: existing v7.1 evidence is preserved untouched. The Phase 79
    code change must not retroactively stamp these files. We assert that
    if the file exists, it does NOT contain script_provenance — i.e. the
    only re-stamping pathway is a fresh audit run, not an in-place edit.
    """
    if not rel_path.exists():
        pytest.skip(f"Historical evidence file not present locally: {rel_path}")

    data = json.loads(rel_path.read_text())
    assert "script_provenance" not in data, (
        f"D-08 violated: {rel_path} was backfilled in place. "
        "Phase 79 is forward-only — re-stamping happens only on fresh audit runs."
    )
