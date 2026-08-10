"""YAML-structure tests for ``.github/workflows/weekly-external-projections.yml``
(silent-failure sweep, Finding 4).

Prior behavior:
  (a) The per-source ingest step in the ``ingest`` matrix job was
      ``continue-on-error: true`` with no annotation on failure -- a source
      failing produced no visible signal anywhere in the run.
  (b) The ``consolidate`` job (``if: always()``) unconditionally ran the
      Silver consolidation + commit steps even when zero fresh Bronze rows
      arrived this run (e.g. every ingest source failed), silently
      committing a Silver file rederived from stale/pre-existing Bronze data.

This module verifies the workflow still parses as valid YAML and that both
gaps are now covered: a ``::warning::`` signal per failed ingest source, and
a pre-commit freshness gate that skips (never fails) the commit when no new
Bronze files arrived.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/weekly-external-projections.yml")


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text()


@pytest.fixture(scope="module")
def workflow_doc(workflow_text: str) -> dict:
    return yaml.safe_load(workflow_text)


def test_workflow_parses_as_yaml(workflow_doc: dict) -> None:
    """The workflow must remain a valid YAML 1.2 document after edits."""
    assert "jobs" in workflow_doc
    assert "ingest" in workflow_doc["jobs"]
    assert "consolidate" in workflow_doc["jobs"]


def test_ingest_matrix_and_continue_on_error_preserved(workflow_doc: dict) -> None:
    """The fail-open matrix (one source failing must not abort the others)
    must stay intact -- only the visibility of a failure changes."""
    ingest = workflow_doc["jobs"]["ingest"]
    assert set(ingest["strategy"]["matrix"]["source"]) == {"espn", "sleeper", "yahoo"}
    assert ingest["strategy"]["fail-fast"] is False

    ingest_step = next(
        s for s in ingest["steps"] if s.get("name", "").startswith("Ingest")
    )
    assert ingest_step["continue-on-error"] is True


def test_ingest_step_emits_warning_on_failure(workflow_text: str) -> None:
    """Finding 4(a): a failed per-source ingest must emit a ::warning::
    annotation naming the matrix source, not fail silently."""
    ingest_step_text = workflow_text.split("- name: Ingest")[1].split(
        "- name: Upload Bronze artifacts"
    )[0]
    assert "::warning::" in ingest_step_text
    assert "matrix.source" in ingest_step_text


def test_consolidate_job_still_runs_always(workflow_doc: dict) -> None:
    """The consolidate job must keep running even when the ingest job has
    partial/total failures (continue-on-error means it never truly
    'fails' the job, but if: always() is the existing safety net)."""
    assert workflow_doc["jobs"]["consolidate"]["if"] == "always()"


def test_consolidate_job_has_freshness_gate(workflow_doc: dict) -> None:
    """Finding 4(b): Consolidate-to-Silver and Commit-Silver steps must be
    gated on a freshness check so a zero-fresh-rows run doesn't commit
    Silver output rederived from stale Bronze data."""
    steps = workflow_doc["jobs"]["consolidate"]["steps"]
    step_names = [s.get("name") for s in steps]
    assert "Check for fresh Bronze data" in step_names

    consolidate_step = next(s for s in steps if s.get("name") == "Consolidate to Silver")
    commit_step = next(s for s in steps if s.get("name") == "Commit Silver")

    assert consolidate_step.get("if") == "steps.freshness.outputs.skip != 'true'"
    assert commit_step.get("if") == "steps.freshness.outputs.skip != 'true'"


def test_freshness_gate_warns_not_fails(workflow_doc: dict) -> None:
    """The freshness gate must warn (::warning::) on zero fresh files and
    must NOT fail the workflow -- freshness-monitor.yml already watches
    staleness separately."""
    steps = workflow_doc["jobs"]["consolidate"]["steps"]
    freshness_step = next(s for s in steps if s.get("name") == "Check for fresh Bronze data")
    run_text = freshness_step["run"]
    assert "::warning::" in run_text
    assert "exit 1" not in run_text
