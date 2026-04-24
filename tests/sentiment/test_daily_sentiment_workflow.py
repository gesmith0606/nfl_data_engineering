"""YAML-structure tests for ``.github/workflows/daily-sentiment.yml`` (Plan 71-05 Task 2).

Verifies the workflow exposes ``EXTRACTOR_MODE`` to the pipeline step
when ``ENABLE_LLM_ENRICHMENT=true`` (Phase 71 LLM-02 routing), and
preserves all other safety properties:

* Permissions (contents:write + issues:write) intact.
* No literal API key patterns in the YAML.
* Existing notify-failure job + concurrency group untouched.
* Health-summary step logs the effective extractor mode so reviewers
  see at a glance which extraction path was authoritative.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/daily-sentiment.yml")


@pytest.fixture(scope="module")
def workflow_text() -> str:
    """Read the raw workflow YAML once per test module."""
    return WORKFLOW.read_text()


@pytest.fixture(scope="module")
def workflow_doc(workflow_text: str) -> dict:
    """Parse the workflow YAML with PyYAML (safe loader)."""
    return yaml.safe_load(workflow_text)


# ---------------------------------------------------------------------------
# Structural sanity
# ---------------------------------------------------------------------------


def test_workflow_parses_as_yaml(workflow_doc: dict) -> None:
    """The workflow must remain a valid YAML 1.2 document after edits."""
    assert "jobs" in workflow_doc
    assert "sentiment" in workflow_doc["jobs"]
    assert "notify-failure" in workflow_doc["jobs"]


def test_existing_permissions_preserved(workflow_doc: dict) -> None:
    """Plan 71-05 must NOT regress contents:write + issues:write."""
    perms = workflow_doc["permissions"]
    assert perms["contents"] == "write"
    assert perms["issues"] == "write"


def test_concurrency_group_preserved(workflow_doc: dict) -> None:
    """The single-flight concurrency group keeps daily runs serialised."""
    assert workflow_doc["concurrency"]["group"] == "daily-sentiment"
    # cancel-in-progress: false means in-flight runs finish before next starts
    assert workflow_doc["concurrency"]["cancel-in-progress"] is False


# ---------------------------------------------------------------------------
# EXTRACTOR_MODE wiring (Plan 71-05 — Task 2 core)
# ---------------------------------------------------------------------------


def _step_named(workflow_doc: dict, name: str) -> dict:
    """Helper: return the step dict from sentiment job by name."""
    for step in workflow_doc["jobs"]["sentiment"]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(
        f"step {name!r} not found in sentiment.steps; "
        f"available: {[s.get('name') for s in workflow_doc['jobs']['sentiment']['steps']]}"
    )


def test_run_step_sets_extractor_mode_env(workflow_doc: dict) -> None:
    """The 'Run daily sentiment pipeline' step propagates EXTRACTOR_MODE.

    Value is a GHA expression conditional on vars.ENABLE_LLM_ENRICHMENT —
    `claude_primary` when true, empty string when false. PyYAML loads
    the expression as a literal string; we only assert the substrings
    so reviewers can see both the gate AND the destination mode in one
    place.
    """
    run_step = _step_named(workflow_doc, "Run daily sentiment pipeline")
    env = run_step.get("env", {})
    assert "EXTRACTOR_MODE" in env, (
        f"EXTRACTOR_MODE missing from run-step env block; got keys: {list(env.keys())}"
    )
    expr = str(env["EXTRACTOR_MODE"])
    # Both the destination mode AND the gate variable must be in the expr,
    # so reading the YAML reveals the routing logic without checking the run script.
    assert "claude_primary" in expr, expr
    assert "ENABLE_LLM_ENRICHMENT" in expr, expr


def test_run_step_keeps_existing_env_keys(workflow_doc: dict) -> None:
    """Plan 71-05 only ADDS EXTRACTOR_MODE; ANTHROPIC_API_KEY + flag stay."""
    run_step = _step_named(workflow_doc, "Run daily sentiment pipeline")
    env = run_step.get("env", {})
    assert "ANTHROPIC_API_KEY" in env
    assert "ENABLE_LLM_ENRICHMENT" in env


def test_health_step_logs_extractor_mode(
    workflow_text: str, workflow_doc: dict
) -> None:
    """Health-summary step emits an annotation showing the effective mode.

    Operators inspecting an Actions run see at a glance which extraction
    path actually ran (rule vs claude_primary) without diff'ing the
    repo vars.
    """
    health_step = _step_named(workflow_doc, "Log pipeline health summary")
    env = health_step.get("env", {})
    assert "EXTRACTOR_MODE" in env, (
        f"EXTRACTOR_MODE missing from health-step env; got: {list(env.keys())}"
    )
    # The annotation message must include the literal string operators grep for.
    assert "Extractor mode:" in workflow_text, (
        "Health step must echo 'Extractor mode:' so operators can spot it"
    )


def test_no_anthropic_api_key_in_plain_text(workflow_text: str) -> None:
    """Paranoia check: no leaked literal sk-ant-... keys in the YAML.

    The only API-key reference allowed is the ``${{ secrets.ANTHROPIC_API_KEY }}``
    expression — never the literal value.
    """
    assert "secrets.ANTHROPIC_API_KEY" in workflow_text
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", workflow_text), (
        "Literal sk-ant-... key pattern detected — regression"
    )


def test_notify_failure_job_preserved(workflow_doc: dict) -> None:
    """Plan 71-05 must not delete or relocate the failure-notification job."""
    notify = workflow_doc["jobs"]["notify-failure"]
    assert notify["needs"] == "sentiment"
    assert notify["if"] == "failure()"
