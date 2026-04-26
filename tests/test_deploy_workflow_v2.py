"""Structural tests for .github/workflows/deploy-web.yml (Phase 68-03).

These tests do NOT execute the workflow. They parse the YAML and assert
invariants that protect the SANITY-08 (blocking) + SANITY-09 (auto-rollback)
contract. If a future edit weakens the blocking chain or introduces a
force-push, these tests fail loudly.
"""

from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = Path(".github/workflows/deploy-web.yml")


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW_PATH.exists(), f"{WORKFLOW_PATH} missing"
    with WORKFLOW_PATH.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def jobs(workflow: dict) -> dict:
    return workflow["jobs"]


def _dump(obj) -> str:
    """Dump YAML with unbounded width so long lines (e.g. shell commands)
    are not wrapped across newlines — wrapping would break substring asserts.
    """
    return yaml.dump(obj, width=10**9, default_flow_style=False)


# ---------------------------------------------------------------------------
# Permissions: workflow-level contents:write is required for rollback push.
# ---------------------------------------------------------------------------

def test_workflow_permissions_contents_write(workflow: dict) -> None:
    perms = workflow.get("permissions", {})
    assert perms.get("contents") == "write", (
        f"workflow-level permissions.contents must be 'write' for rollback push; got {perms!r}"
    )


def test_workflow_permissions_actions_read(workflow: dict) -> None:
    perms = workflow.get("permissions", {})
    assert perms.get("actions") == "read", (
        f"workflow-level permissions.actions must be 'read' to consume artifacts; got {perms!r}"
    )


# ---------------------------------------------------------------------------
# Old post-deploy-smoke renamed; live-gate-blocking is the new blocking node.
# ---------------------------------------------------------------------------

def test_old_post_deploy_smoke_removed(jobs: dict) -> None:
    assert "post-deploy-smoke" not in jobs, (
        "old post-deploy-smoke job still present — must be renamed to live-gate-blocking"
    )


def test_live_gate_blocking_job_exists(jobs: dict) -> None:
    assert "live-gate-blocking" in jobs, f"live-gate-blocking job missing; jobs={list(jobs)}"


def test_live_gate_blocking_needs_both_deploys(jobs: dict) -> None:
    needs = jobs["live-gate-blocking"].get("needs")
    assert needs == ["deploy-frontend", "deploy-backend"], (
        f"live-gate-blocking must need [deploy-frontend, deploy-backend]; got {needs!r}"
    )


def test_live_gate_blocking_no_continue_on_error(jobs: dict) -> None:
    job = jobs["live-gate-blocking"]
    assert "continue-on-error" not in job, (
        "live-gate-blocking must NOT set continue-on-error — failure must block the workflow"
    )
    for step in job.get("steps", []):
        assert step.get("continue-on-error") is not True, (
            f"step in live-gate-blocking has continue-on-error=true: {step!r}"
        )


def test_live_gate_blocking_runs_check_live(jobs: dict) -> None:
    job = jobs["live-gate-blocking"]
    run_commands = "\n".join(
        step.get("run", "") for step in job.get("steps", []) if isinstance(step.get("run"), str)
    )
    assert "--check-live" in run_commands, (
        "live-gate-blocking must invoke sanity_check_projections.py with --check-live"
    )
    assert "sanity_check_projections.py" in run_commands, (
        "live-gate-blocking must invoke scripts/sanity_check_projections.py"
    )


# ---------------------------------------------------------------------------
# Auto-rollback invariants: fires only on failure, within 5 minutes,
# uses git revert + push (NEVER force-push), commit message is auditable.
# ---------------------------------------------------------------------------

def test_auto_rollback_job_exists(jobs: dict) -> None:
    assert "auto-rollback" in jobs, f"auto-rollback job missing; jobs={list(jobs)}"


def test_auto_rollback_depends_on_live_gate(jobs: dict) -> None:
    needs = jobs["auto-rollback"].get("needs")
    assert needs == "live-gate-blocking" or needs == ["live-gate-blocking"], (
        f"auto-rollback must depend only on live-gate-blocking; got {needs!r}"
    )


def test_auto_rollback_fires_only_on_failure(jobs: dict) -> None:
    if_expr = jobs["auto-rollback"].get("if", "")
    assert "live-gate-blocking.result" in if_expr, f"if missing result check: {if_expr!r}"
    assert "failure" in if_expr, f"if missing 'failure' trigger: {if_expr!r}"


def test_auto_rollback_has_five_minute_window(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    assert "ELAPSED" in steps_yaml, "auto-rollback missing elapsed-time calculation"
    assert "300" in steps_yaml, "auto-rollback missing 5-minute (300s) window guard"


def test_auto_rollback_uses_git_revert(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    # TD-01 (Phase 75): replaced --no-edit with --no-commit (revert + custom commit message).
    assert "git revert --no-commit" in steps_yaml or "git revert --no-edit" in steps_yaml, (
        "auto-rollback must use `git revert --no-commit` (not reset or checkout)"
    )


def test_auto_rollback_pushes_non_force(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    assert "git push origin main" in steps_yaml, "auto-rollback must push to origin main"
    # The critical security invariant:
    assert "--force" not in steps_yaml, (
        "FORBIDDEN: auto-rollback uses --force or --force-with-lease. "
        "Rollback MUST respect branch protection."
    )
    assert "--force-with-lease" not in steps_yaml, "FORBIDDEN: --force-with-lease"
    # TD-07 (Phase 75): structural test asserting --no-verify absence.
    assert "--no-verify" not in steps_yaml, (
        "TD-07: auto-rollback must NOT use --no-verify — pre-commit hooks "
        "are part of the safety net for the rollback commit too."
    )
    # TD-01 (Phase 75): no --amend (was a policy violation).
    assert "--amend" not in steps_yaml, (
        "TD-01: auto-rollback must NOT use --amend; commit the rollback "
        "with a single revert + commit -m, not revert then amend."
    )


def test_auto_rollback_audit_commit_message(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    assert "revert: auto-rollback after sanity-check failure on" in steps_yaml, (
        "auto-rollback commit message must follow the audit format "
        "`revert: auto-rollback after sanity-check failure on <sha>`"
    )


def test_auto_rollback_uses_github_actions_bot(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    assert "github-actions[bot]" in steps_yaml, (
        "auto-rollback must configure the github-actions[bot] identity for the commit"
    )


def test_auto_rollback_consumes_deploy_metadata(jobs: dict) -> None:
    steps_yaml = _dump(jobs["auto-rollback"].get("steps", []))
    assert "actions/download-artifact" in steps_yaml, (
        "auto-rollback must download deploy-metadata artifact for window check"
    )
    assert "deploy-metadata" in steps_yaml, "auto-rollback must reference deploy-metadata artifact"


# ---------------------------------------------------------------------------
# Quality-gate still runs pre-deploy + captures metadata for rollback window.
# ---------------------------------------------------------------------------

def test_quality_gate_still_runs_sanity_check(jobs: dict) -> None:
    assert "quality-gate" in jobs, "quality-gate pre-deploy job must remain"
    steps_yaml = _dump(jobs["quality-gate"].get("steps", []))
    assert "sanity_check_projections.py" in steps_yaml, (
        "quality-gate must still invoke pre-deploy sanity check"
    )


def test_quality_gate_records_deploy_metadata(jobs: dict) -> None:
    steps_yaml = _dump(jobs["quality-gate"].get("steps", []))
    assert "DEPLOY_SHA" in steps_yaml, "quality-gate must capture DEPLOY_SHA for rollback window"
    assert "DEPLOY_TIMESTAMP" in steps_yaml, "quality-gate must capture DEPLOY_TIMESTAMP"
    assert "upload-artifact" in steps_yaml, "quality-gate must upload deploy-metadata artifact"


# ---------------------------------------------------------------------------
# Deploy dependency chain — rollback only reachable via live-gate-blocking.
# ---------------------------------------------------------------------------

def test_deploy_frontend_depends_on_quality_gate(jobs: dict) -> None:
    needs = jobs.get("deploy-frontend", {}).get("needs")
    assert needs == "quality-gate" or (isinstance(needs, list) and "quality-gate" in needs), (
        f"deploy-frontend must depend on quality-gate; got {needs!r}"
    )


def test_deploy_backend_depends_on_quality_gate(jobs: dict) -> None:
    needs = jobs.get("deploy-backend", {}).get("needs")
    assert needs == "quality-gate" or (isinstance(needs, list) and "quality-gate" in needs), (
        f"deploy-backend must depend on quality-gate; got {needs!r}"
    )
