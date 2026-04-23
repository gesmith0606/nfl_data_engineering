---
phase: 68-sanity-check-v2
plan: 03
type: execute
wave: 3
depends_on:
  - 68-01
  - 68-02
files_modified:
  - .github/workflows/deploy-web.yml
  - tests/test_deploy_workflow_v2.py
autonomous: true
requirements:
  - SANITY-08
  - SANITY-09
tags:
  - sanity-check
  - github-actions
  - deploy-gate
  - auto-rollback
must_haves:
  truths:
    - "GitHub Actions deploy-web workflow invokes `--check-live` against the Railway URL as a job that BLOCKS subsequent jobs (not annotation-only)"
    - "post-deploy-smoke job is promoted from informational to blocking — its failure fails the entire workflow"
    - "On post-deploy-smoke failure, a follow-on rollback job runs `git revert --no-edit HEAD && git push` and Railway auto-redeploys the previous green commit"
    - "Rollback only triggers within a 5-minute window of the original deploy commit (not stale runs)"
    - "Rollback commit message follows the format `revert: auto-rollback after sanity-check failure on <sha>` for git log auditability"
    - "The bot token used for revert+push has `contents: write` permission only (not `force-push` to main)"
  artifacts:
    - path: ".github/workflows/deploy-web.yml"
      provides: "Promoted post-deploy-smoke (now blocking + named live-gate-blocking) + new auto-rollback-on-failure job using git revert"
      contains: "name: live-gate-blocking"
    - path: ".github/workflows/deploy-web.yml"
      provides: "permissions: contents: write block at workflow root for rollback push capability"
      contains: "permissions:"
    - path: "tests/test_deploy_workflow_v2.py"
      provides: "YAML structural tests asserting blocking dependency chain + rollback job invariants (revert command, no force-push, 5min window)"
      min_lines: 100
  key_links:
    - from: ".github/workflows/deploy-web.yml::live-gate-blocking job"
      to: "scripts/sanity_check_projections.py --check-live"
      via: "blocking step that exits non-zero on CRITICAL findings, propagated to needs: dependency"
      pattern: "--check-live"
    - from: ".github/workflows/deploy-web.yml::auto-rollback job"
      to: "git revert --no-edit HEAD"
      via: "shell step that runs only if needs.live-gate-blocking.result == 'failure'"
      pattern: "git revert --no-edit"
    - from: ".github/workflows/deploy-web.yml::auto-rollback job"
      to: "GitHub repo main branch"
      via: "git push origin main using GITHUB_TOKEN with contents:write"
      pattern: "git push origin main"
---

<objective>
Promote the v2 sanity gate's `--check-live` invocation from annotation-only to a BLOCKING GitHub Actions step, and add an automatic-rollback job that runs `git revert --no-edit HEAD && git push origin main` when the post-deploy live gate fails within 5 minutes of the deploying commit. This is the structural delivery: even with a perfectly functioning gate (Plans 68-01 + 68-02), regressions still ship if the workflow doesn't block on failure or auto-revert.

Purpose: Close the workflow-level half of the meta-issue. The Phase 60 gate exited 0 partly because `--check-live` was post-deploy and annotation-only. This plan flips both.

Output: Modified `.github/workflows/deploy-web.yml` with promoted blocking job + new rollback job, plus a YAML structural test asserting the dependency chain and rollback invariants.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/68-sanity-check-v2/68-CONTEXT.md
@.planning/phases/68-sanity-check-v2/68-01-live-probes-and-content-validators-PLAN.md
@.planning/phases/68-sanity-check-v2/68-02-roster-drift-apikey-dqal-PLAN.md
@.github/workflows/deploy-web.yml
@.github/workflows/daily-sentiment.yml

<interfaces>
<!-- Current deploy-web.yml structure (Plan 68-03 modifies this file) -->

Existing jobs (in dependency order):
1. `quality-gate` — runs `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` (NO --check-live)
2. `deploy-frontend` — needs: quality-gate. Vercel deploy.
3. `deploy-backend` — needs: quality-gate. Docker → ECR → SAM → Lambda.
4. `post-deploy-smoke` — needs: [deploy-frontend, deploy-backend]. Currently runs `--check-live` AFTER deploy. Failure surfaces in workflow summary but DOES NOT trigger any remediation.

Plan 68-03 changes:
- Rename `post-deploy-smoke` → `live-gate-blocking` (clearer intent).
- Keep its `needs: [deploy-frontend, deploy-backend]` and `if: always() && (...)` trigger.
- Add explicit failure propagation — the workflow-level result must be FAILURE on this job's failure (default GHA behavior already; verify no `continue-on-error` set).
- Add NEW job `auto-rollback` with `needs: live-gate-blocking` and `if: needs.live-gate-blocking.result == 'failure'`.

Auto-rollback job constraints (from CONTEXT.md "Rollback Mechanism"):
- Trigger: `live-gate-blocking` exits non-zero
- Window: only run if commit is within 5 min of deploy (sanity bound — prevents stale workflow re-runs from reverting innocent commits)
- Action: `git revert --no-edit HEAD && git push origin main`
- Commit format: `revert: auto-rollback after sanity-check failure on <sha>` (CONTEXT)
- Auth: GITHUB_TOKEN with `contents: write` permission (NOT a PAT, NOT force-push)

GitHub Actions YAML reference points:
- Workflow-level `permissions:` block at root level (top of file, after `env:`)
- `permissions: contents: write` is what GITHUB_TOKEN needs to push the revert
- `permissions: contents: read` is the default — explicit upgrade required

Phase 67 daily-sentiment.yml already uses `git config user.name "github-actions[bot]"` + `git push` pattern (lines 128-147). Reuse that pattern for consistency.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Promote --check-live to blocking job + add explicit workflow-level permissions</name>
  <files>.github/workflows/deploy-web.yml</files>
  <read_first>
    - .github/workflows/deploy-web.yml entire file (current 179 lines)
    - .github/workflows/daily-sentiment.yml lines 127-147 (the git config + commit + push pattern to reuse)
  </read_first>
  <action>
Modify `.github/workflows/deploy-web.yml`:

**Change 1 — Add workflow-level permissions block.** After line 13-14 (the `env:` block), insert:

```yaml
# ----------------------------------------------------------------
# Permissions: contents: write enables auto-rollback (Plan 68-03 SANITY-09)
# to git revert + push from the rollback job. NEVER use force-push to main.
# ----------------------------------------------------------------
permissions:
  contents: write
  actions: read
```

**Change 2 — Rename and harden the post-deploy smoke job.** Replace the entire `post-deploy-smoke` job (lines 144-179) with:

```yaml
  # ------------------------------------------------------------------
  # Live gate (BLOCKING per Plan 68-03 SANITY-08, SANITY-09):
  # Probes the LIVE backend + frontend AFTER deploy with the v2 gate
  # (predictions, lineups, sampled rosters, news content, extractor
  # freshness, roster drift, DQAL-03 carry-overs). Non-zero exit fails
  # this job, fails the workflow, and triggers the auto-rollback job
  # via its `needs: live-gate-blocking` + result==failure trigger.
  #
  # NO `continue-on-error` — failure here is intentional and gates
  # everything downstream including the rollback decision.
  # ------------------------------------------------------------------
  live-gate-blocking:
    name: Live Site Gate (Blocking)
    runs-on: ubuntu-latest
    needs: [deploy-frontend, deploy-backend]
    if: always() && (needs.deploy-frontend.result == 'success' || needs.deploy-backend.result == 'success')
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: requirements.txt

      - name: Install Python dependencies
        run: pip install -r requirements.txt

      # Give Railway/Vercel a moment to serve the new image on the edge.
      # Railway cold-start + router drain can exceed 45s under load.
      - name: Wait for deployments to stabilise
        run: sleep 60

      - name: Run v2 sanity gate against live deployment
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          ENABLE_LLM_ENRICHMENT: ${{ vars.ENABLE_LLM_ENRICHMENT || 'false' }}
        run: |
          python scripts/sanity_check_projections.py \
            --check-live \
            --scoring half_ppr \
            --season 2026
        # Exit code != 0 fails the job, fails the workflow, triggers rollback.
```

**Change 3 — Confirm the existing `quality-gate` step output.** After the existing `quality-gate` job (around lines 24-45), append a new step that captures the deploying commit SHA + timestamp into a downstream artifact for the rollback job's 5-min window check:

Add this step at the END of `quality-gate` job (after the existing "Run sanity check" step):

```yaml
      - name: Record deploy metadata for rollback window
        run: |
          echo "DEPLOY_SHA=${{ github.sha }}" >> deploy_metadata.env
          echo "DEPLOY_TIMESTAMP=$(date -u +%s)" >> deploy_metadata.env

      - name: Upload deploy metadata
        uses: actions/upload-artifact@v4
        with:
          name: deploy-metadata
          path: deploy_metadata.env
          retention-days: 1
```

DO NOT change `quality-gate`'s pass/fail behavior. DO NOT change `deploy-frontend` or `deploy-backend` definitions. DO NOT remove the `quality-gate` job or its sanity check invocation — pre-deploy gating still runs.
  </action>
  <verify>
    <automated>python -c "import yaml; data = yaml.safe_load(open('.github/workflows/deploy-web.yml')); jobs = data['jobs']; assert 'live-gate-blocking' in jobs, f'live-gate-blocking job missing; jobs={list(jobs.keys())}'; assert 'post-deploy-smoke' not in jobs, 'old post-deploy-smoke still present'; assert data.get('permissions', {}).get('contents') == 'write', 'workflow-level contents:write permission missing'; assert jobs['live-gate-blocking'].get('needs') == ['deploy-frontend', 'deploy-backend'], 'live-gate-blocking needs wrong'; assert 'continue-on-error' not in str(jobs['live-gate-blocking']), 'live-gate-blocking must not continue-on-error'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "^permissions:" .github/workflows/deploy-web.yml` returns a match at workflow root (not nested under a job)
    - `grep -A 2 "^permissions:" .github/workflows/deploy-web.yml` contains both `contents: write` and `actions: read`
    - `grep -n "live-gate-blocking:" .github/workflows/deploy-web.yml` returns exactly 1 line (job exists)
    - `grep -n "post-deploy-smoke:" .github/workflows/deploy-web.yml` returns 0 lines (old job removed)
    - `grep -n "continue-on-error" .github/workflows/deploy-web.yml` returns 0 lines inside the live-gate-blocking job (verifiable via python yaml parser — covered above)
    - `grep -n "python scripts/sanity_check_projections.py" .github/workflows/deploy-web.yml` returns at least 2 lines (quality-gate pre-deploy + live-gate-blocking post-deploy)
    - `grep -n "\-\-check-live" .github/workflows/deploy-web.yml` returns exactly 1 line (live-gate-blocking only — not in quality-gate)
    - `grep -n "actions/upload-artifact@v4" .github/workflows/deploy-web.yml` returns at least 1 line (deploy-metadata artifact added in quality-gate)
    - `grep -n "DEPLOY_SHA\|DEPLOY_TIMESTAMP" .github/workflows/deploy-web.yml` returns at least 2 lines (metadata captured for rollback window check)
    - Python YAML parse succeeds — no syntax errors introduced (covered via `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-web.yml'))"`)
  </acceptance_criteria>
  <done>Workflow `contents: write` permission is explicit, post-deploy smoke is renamed to `live-gate-blocking` with no `continue-on-error`, deploy metadata is captured for the rollback window, and the `--check-live` invocation blocks all downstream jobs on non-zero exit.</done>
</task>

<task type="auto">
  <name>Task 2: Add auto-rollback job with 5-minute window + git revert + push</name>
  <files>.github/workflows/deploy-web.yml</files>
  <read_first>
    - .github/workflows/deploy-web.yml (after Task 1 changes — confirm live-gate-blocking + permissions present)
    - .github/workflows/daily-sentiment.yml lines 127-147 (git config user.name + user.email pattern for reuse)
  </read_first>
  <action>
Append a NEW `auto-rollback` job to `.github/workflows/deploy-web.yml` AFTER the `live-gate-blocking` job. The job runs only when `live-gate-blocking` fails AND the failing commit is within 5 minutes of the workflow start — this prevents stale reruns from reverting innocent commits.

Add this block at the END of the `jobs:` section:

```yaml
  # ------------------------------------------------------------------
  # Auto-rollback (Plan 68-03 SANITY-09):
  # Triggers ONLY when live-gate-blocking fails AND the failing commit
  # is within 5 minutes of workflow start. Reverts HEAD with
  # `git revert --no-edit` and pushes to main. Railway auto-redeploys
  # the previous green commit on push. Revert commit message is:
  #   `revert: auto-rollback after sanity-check failure on <sha>`
  # so git log --oneline makes rollbacks auditable.
  #
  # NEVER force-push. NEVER bypass branch protection. The bot token
  # has contents:write only (configured at workflow root).
  # ------------------------------------------------------------------
  auto-rollback:
    name: Auto-Rollback on Live Gate Failure
    runs-on: ubuntu-latest
    needs: live-gate-blocking
    if: always() && needs.live-gate-blocking.result == 'failure'
    steps:
      - name: Checkout main
        uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 2
          # Use GITHUB_TOKEN (contents:write at workflow root)
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Download deploy metadata
        uses: actions/download-artifact@v4
        with:
          name: deploy-metadata

      - name: Verify 5-minute rollback window
        id: window_check
        run: |
          source deploy_metadata.env
          NOW=$(date -u +%s)
          ELAPSED=$(( NOW - DEPLOY_TIMESTAMP ))
          echo "DEPLOY_SHA=$DEPLOY_SHA"
          echo "Elapsed since deploy: ${ELAPSED}s"
          if [ "$ELAPSED" -gt 300 ]; then
            echo "ROLLBACK_SKIPPED=true" >> $GITHUB_OUTPUT
            echo "::warning::Rollback skipped — ${ELAPSED}s since deploy exceeds 5-minute window. Manual review required."
            exit 0
          fi
          echo "ROLLBACK_SKIPPED=false" >> $GITHUB_OUTPUT
          echo "deploy_sha=$DEPLOY_SHA" >> $GITHUB_OUTPUT

      - name: Configure git bot identity
        if: steps.window_check.outputs.ROLLBACK_SKIPPED != 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Revert failing deploy commit
        if: steps.window_check.outputs.ROLLBACK_SKIPPED != 'true'
        run: |
          SHA="${{ steps.window_check.outputs.deploy_sha }}"
          # HEAD on main should equal SHA since we just deployed it. Guard anyway.
          CURRENT_HEAD=$(git rev-parse HEAD)
          if [ "$CURRENT_HEAD" != "$SHA" ]; then
            echo "::error::HEAD ($CURRENT_HEAD) no longer matches deploy SHA ($SHA). Skipping rollback — someone else pushed. Manual review required."
            exit 1
          fi
          git revert --no-edit HEAD
          # Rewrite commit message to the audit format.
          git commit --amend -m "revert: auto-rollback after sanity-check failure on ${SHA}" --no-verify

      - name: Push rollback to main
        if: steps.window_check.outputs.ROLLBACK_SKIPPED != 'true'
        run: |
          # Non-force push. Branch protection rules still apply.
          # If push is rejected (e.g., new commit raced us), surface as failure.
          git push origin main

      - name: Record rollback outcome
        if: always() && steps.window_check.outputs.ROLLBACK_SKIPPED != 'true'
        run: |
          echo "## Auto-Rollback Executed" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "Reverted commit: ${{ steps.window_check.outputs.deploy_sha }}" >> $GITHUB_STEP_SUMMARY
          echo "Railway will auto-redeploy the previous green commit." >> $GITHUB_STEP_SUMMARY
          echo "Review the live-gate-blocking failure before re-deploying." >> $GITHUB_STEP_SUMMARY
```

DO NOT use `--force` or `--force-with-lease` on the push. DO NOT use a PAT — GITHUB_TOKEN with workflow-level `contents: write` is sufficient. DO NOT change `live-gate-blocking` — it runs first and this job depends on its failure.
  </action>
  <verify>
    <automated>python -c "
import yaml
data = yaml.safe_load(open('.github/workflows/deploy-web.yml'))
jobs = data['jobs']
assert 'auto-rollback' in jobs, 'auto-rollback job missing'
rb = jobs['auto-rollback']
assert rb.get('needs') == 'live-gate-blocking', f'needs wrong: {rb.get(\"needs\")}'
if_expr = rb.get('if', '')
assert 'live-gate-blocking.result' in if_expr and 'failure' in if_expr, f'if wrong: {if_expr}'
steps_yaml = yaml.dump(rb.get('steps', []))
assert 'git revert --no-edit' in steps_yaml, 'git revert command missing'
assert 'git push origin main' in steps_yaml, 'git push missing'
assert '--force' not in steps_yaml, 'force-push detected — rollback MUST NOT force-push'
assert 'ELAPSED' in steps_yaml and '300' in steps_yaml, '5-minute window check missing'
assert 'revert: auto-rollback after sanity-check failure on' in steps_yaml, 'audit commit format missing'
print('OK')
"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "auto-rollback:" .github/workflows/deploy-web.yml` returns exactly 1 line
    - `grep -n "needs: live-gate-blocking" .github/workflows/deploy-web.yml` returns at least 1 line
    - `grep -n "needs.live-gate-blocking.result == 'failure'" .github/workflows/deploy-web.yml` returns exactly 1 line
    - `grep -n "git revert --no-edit" .github/workflows/deploy-web.yml` returns exactly 1 line
    - `grep -n "git push origin main" .github/workflows/deploy-web.yml` returns at least 1 line
    - `grep -n "\-\-force" .github/workflows/deploy-web.yml` returns 0 lines (no force-push anywhere)
    - `grep -n "revert: auto-rollback after sanity-check failure on" .github/workflows/deploy-web.yml` returns exactly 1 line (audit commit format)
    - `grep -n "\-gt 300" .github/workflows/deploy-web.yml` returns exactly 1 line (5-minute window)
    - `grep -n "github-actions\[bot\]" .github/workflows/deploy-web.yml` returns at least 1 line (bot identity)
    - `grep -n "actions/download-artifact@v4" .github/workflows/deploy-web.yml` returns at least 1 line (consumes deploy-metadata)
    - Python YAML parse succeeds end-to-end
  </acceptance_criteria>
  <done>Auto-rollback job is present, runs only on live-gate-blocking failure within 5 minutes, performs `git revert --no-edit` + `git push origin main` (never force-push), writes an audit-formatted commit message, and surfaces outcome in the workflow summary.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: YAML structural tests asserting blocking chain + rollback invariants</name>
  <files>tests/test_deploy_workflow_v2.py</files>
  <read_first>
    - .github/workflows/deploy-web.yml (post Tasks 1+2 — assert its structure)
    - tests/web/test_graceful_defaulting.py (existing test style reference for tests/web; for repo-root tests, any existing tests/test_*.py patterns)
  </read_first>
  <action>
Create `tests/test_deploy_workflow_v2.py` with structural assertions against `.github/workflows/deploy-web.yml`. Tests treat the workflow as data (not executed) so they are fast and run in CI without needing Actions infrastructure.

Write this test module:

```python
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
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "ELAPSED" in steps_yaml, "auto-rollback missing elapsed-time calculation"
    assert "300" in steps_yaml, "auto-rollback missing 5-minute (300s) window guard"


def test_auto_rollback_uses_git_revert(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "git revert --no-edit" in steps_yaml, (
        "auto-rollback must use `git revert --no-edit` (not reset or checkout)"
    )


def test_auto_rollback_pushes_non_force(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "git push origin main" in steps_yaml, "auto-rollback must push to origin main"
    # The critical security invariant:
    assert "--force" not in steps_yaml, (
        "FORBIDDEN: auto-rollback uses --force or --force-with-lease. "
        "Rollback MUST respect branch protection."
    )
    assert "--force-with-lease" not in steps_yaml, "FORBIDDEN: --force-with-lease"


def test_auto_rollback_audit_commit_message(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "revert: auto-rollback after sanity-check failure on" in steps_yaml, (
        "auto-rollback commit message must follow the audit format "
        "`revert: auto-rollback after sanity-check failure on <sha>`"
    )


def test_auto_rollback_uses_github_actions_bot(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "github-actions[bot]" in steps_yaml, (
        "auto-rollback must configure the github-actions[bot] identity for the commit"
    )


def test_auto_rollback_consumes_deploy_metadata(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["auto-rollback"].get("steps", []))
    assert "actions/download-artifact" in steps_yaml, (
        "auto-rollback must download deploy-metadata artifact for window check"
    )
    assert "deploy-metadata" in steps_yaml, "auto-rollback must reference deploy-metadata artifact"


# ---------------------------------------------------------------------------
# Quality-gate still runs pre-deploy + captures metadata for rollback window.
# ---------------------------------------------------------------------------

def test_quality_gate_still_runs_sanity_check(jobs: dict) -> None:
    assert "quality-gate" in jobs, "quality-gate pre-deploy job must remain"
    steps_yaml = yaml.dump(jobs["quality-gate"].get("steps", []))
    assert "sanity_check_projections.py" in steps_yaml, (
        "quality-gate must still invoke pre-deploy sanity check"
    )


def test_quality_gate_records_deploy_metadata(jobs: dict) -> None:
    steps_yaml = yaml.dump(jobs["quality-gate"].get("steps", []))
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
```
  </action>
  <verify>
    <automated>source venv/bin/activate && python -m pytest tests/test_deploy_workflow_v2.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - `test -f tests/test_deploy_workflow_v2.py` succeeds
    - `grep -c "^def test_" tests/test_deploy_workflow_v2.py` returns at least 18 (one per invariant above)
    - `grep -n "test_auto_rollback_pushes_non_force" tests/test_deploy_workflow_v2.py` returns exactly 1 line (the critical force-push guard)
    - `grep -n "test_auto_rollback_audit_commit_message" tests/test_deploy_workflow_v2.py` returns exactly 1 line
    - `grep -n "test_live_gate_blocking_no_continue_on_error" tests/test_deploy_workflow_v2.py` returns exactly 1 line
    - `python -m pytest tests/test_deploy_workflow_v2.py -v` exits 0 with all tests passing
    - No test uses `requests` or other network calls — pure YAML parsing
  </acceptance_criteria>
  <done>18+ structural tests assert the workflow invariants — blocking chain intact, no force-push, audit commit format, 5-minute window, metadata artifact flow, quality-gate preserved. Running the test module exits 0.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner → GitHub repo (git push) | GITHUB_TOKEN with workflow-level `contents: write`, subject to branch protection |
| Deploy commit → rollback trigger | 5-minute window gate prevents stale reruns from reverting innocent commits |
| `live-gate-blocking` step → rollback job | `needs` + `if: result == 'failure'` is the only path to rollback |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-68-03-01 | Elevation of privilege | Bot force-push bypassing branch protection | mitigate | `--force` and `--force-with-lease` are explicitly forbidden and asserted absent by `test_auto_rollback_pushes_non_force`. Branch protection still applies; a rejected push surfaces as job failure. |
| T-68-03-02 | Tampering | Stale workflow re-run reverting a healthy commit | mitigate | 5-minute window check via DEPLOY_TIMESTAMP artifact. Also: explicit `git rev-parse HEAD` check — if HEAD has moved, rollback aborts with `::error::`. |
| T-68-03-03 | Repudiation | Auto-rollback commit untraceable in git log | mitigate | Audit commit format `revert: auto-rollback after sanity-check failure on <sha>` is asserted by test. Includes original SHA + bot identity (`github-actions[bot]`). |
| T-68-03-04 | Information disclosure | ANTHROPIC_API_KEY leaked in workflow logs | mitigate | Secret injected via `${{ secrets.ANTHROPIC_API_KEY }}` env var; never echoed. `--check-live` asserts presence only (Plan 68-02), not value. |
| T-68-03-05 | Denial of service | Rollback loop (revert commit itself fails gate) | accept | Revert commit re-runs the full workflow; if it also fails the live gate, a SECOND rollback would attempt to revert the revert. The 5-minute window + HEAD-drift check prevents infinite recursion for most cases; worst case one extra rollback. Solo-ops triage acceptable. |
| T-68-03-06 | Tampering | Attacker commits a malicious sanity-check failure to trigger rollback of a legitimate deploy | accept | Attacker already needs repo push access to commit. Branch protection + code review upstream is the real mitigation; this plan adds post-deploy defence, not supply-chain defence. |
</threat_model>

<verification>
```bash
source venv/bin/activate
# Parse workflow and run structural tests
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-web.yml'))"  # YAML validity
python -m pytest tests/test_deploy_workflow_v2.py -v --tb=short
```

Expected: all 18+ tests pass. No network calls, no actual workflow execution. Pure YAML invariant verification.

Additionally, `actionlint` (if installed) should pass on the workflow — optional but recommended:
```bash
actionlint .github/workflows/deploy-web.yml 2>/dev/null || echo "actionlint not installed — skipping"
```
</verification>

<success_criteria>
- Workflow-level `permissions: contents: write, actions: read` set (enables rollback push, blocks privilege escalation)
- `post-deploy-smoke` renamed to `live-gate-blocking` with `needs: [deploy-frontend, deploy-backend]`
- No `continue-on-error` anywhere in `live-gate-blocking` — its failure fails the workflow
- `live-gate-blocking` runs `python scripts/sanity_check_projections.py --check-live --scoring half_ppr --season 2026`
- `quality-gate` still runs pre-deploy sanity check + uploads `deploy-metadata` artifact (DEPLOY_SHA, DEPLOY_TIMESTAMP)
- New `auto-rollback` job gated by `needs: live-gate-blocking` + `if: needs.live-gate-blocking.result == 'failure'`
- 5-minute window check via `DEPLOY_TIMESTAMP` — rollback skipped (with warning annotation) if > 300s
- HEAD drift check — rollback aborts if HEAD moved since deploy
- `git revert --no-edit HEAD` + `git push origin main` (never `--force`, never `--force-with-lease`)
- Commit message format `revert: auto-rollback after sanity-check failure on <sha>` for audit trail
- `github-actions[bot]` identity configured before commit
- 18+ structural tests in `tests/test_deploy_workflow_v2.py` asserting all invariants — all passing
</success_criteria>

<output>
After completion, create `.planning/phases/68-sanity-check-v2/68-03-SUMMARY.md` covering:
- Workflow transformation (jobs added/renamed/modified)
- Security invariants asserted (no force-push, 5-min window, bot identity, audit commit)
- Test count (18+ structural tests on YAML, no network/execution)
- Files modified (`.github/workflows/deploy-web.yml`, `tests/test_deploy_workflow_v2.py`)
- Acceptance: Running the full test suite exits 0; running the workflow on a known-bad deploy state (simulated) triggers the rollback job correctly (integration-level verification deferred to first real failure since it modifies main)
- Phase-level closure: Plan 68-03 completes the v7.0 SANITY-08 + SANITY-09 contract. Combined with 68-01 (live probes) and 68-02 (drift + DQAL + canary), the v2 sanity gate is structurally complete — the 6 regressions from 2026-04-20 would now be caught AND automatically rolled back in production.
</output>