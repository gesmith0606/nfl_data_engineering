---
phase: 79-audit-provenance-version-probe
plan: 04
subsystem: ci
tags: [github-actions, deploy-hardening, version-probe, asymmetry-detection, warn-only]

# Dependency graph
requires:
  - phase: 79-audit-provenance-version-probe
    plan: 03
    provides: GET /api/version returns 7-key VersionResponse with full 40-char git_sha (consumed by smoke step's jq extraction)
provides:
  - "deploy-backend job step that polls Railway /api/version every 15s for up to 300s asserting git_sha == github.sha"
  - "::notice::SHA-match annotation on success; ::warning::SHA-asymmetry annotation on timeout (warn-only per D-07)"
  - "Phase 84 DEPLOY-02 promotion target: literal step name 'Probe Railway /api/version for SHA match' is grep-stable"
affects:
  - 84-deploy-hardening (DEPLOY-02 promotes this step from continue-on-error:true to fail-on-mismatch)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "warn-only-then-promote rhythm: continue-on-error: true now, removed in Phase 84"
    - "wall-clock budget enforcement: date -u +%s arithmetic in shell while-loop with per-request curl -m 10"
    - "GitHub Actions structured annotations (::notice:: / ::warning:: with title= attribute) for workflow-summary visibility"
    - "Optional secret-injection: HEADER_ARGS array conditionally appends -H X-API-Key when RAILWAY_API_KEY is set"

key-files:
  created: []
  modified:
    - ".github/workflows/deploy-web.yml (deploy-backend job: appended new smoke step after the 120s wait)"

key-decisions:
  - "Step name set to literal 'Probe Railway /api/version for SHA match' so Phase 84 DEPLOY-02 can grep-and-promote without re-anchoring"
  - "set -uo pipefail (NOT -euo) so a transient curl non-zero exit does not abort the polling loop"
  - "Per-request curl -m 10 timeout caps per-iteration latency at 10s, preventing a hung Railway from eating the 300s budget"
  - "jq -r '.git_sha // \"missing\"' coerces null/absent field to a stable sentinel — keeps comparison deterministic"
  - "RAILWAY_API_KEY is consumed via existing secret only; no new repo secret added (operator territory per D-07)"

patterns-established:
  - "Asymmetry-probe step shape: continue-on-error + env-passed EXPECTED_SHA + jq-extracted SHA + structured annotations"
  - "Phase 84 promotion seam: a single step named with a grep-stable literal so a follow-on phase can flip continue-on-error and timeout branch without rewriting the polling logic"

requirements-completed: [DQ-02]

# Metrics
duration: 1min
completed: 2026-04-28
---

# Phase 79 Plan 04: Version-Probe Smoke Step Summary

**New deploy-backend smoke step polls Railway /api/version asserting git_sha == github.sha (warn-only, 5-minute budget); the step is named with a grep-stable literal so Phase 84 DEPLOY-02 can promote it to a hard gate by removing continue-on-error and flipping the timeout branch.**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-04-28T21:58:50Z
- **Completed:** 2026-04-28T21:59:30Z
- **Tasks:** 1
- **Files modified:** 1
- **Commits:** 1

## Accomplishments

- Added a new step named exactly `Probe Railway /api/version for SHA match` to `.github/workflows/deploy-web.yml` inside the `deploy-backend` job, positioned AFTER the existing 120s Railway-redeploy wait.
- Step polls `https://nfldataengineering-production.up.railway.app/api/version` every 15 seconds for up to 300 seconds (5-minute budget per D-07).
- Match path: `::notice title=Railway /api/version SHA match::git_sha=<sha> after <elapsed>s (<attempts> attempts)` and `exit 0`.
- Timeout path: `::warning title=Railway /api/version SHA asymmetry::Expected <github.sha> after 300s; last seen git_sha=<last>` and `exit 0` (warn-only — `continue-on-error: true` covers this; explicit `exit 0` keeps the job log clean).
- Uses ONLY `curl` and `jq` — both pre-installed on `ubuntu-latest`. No new dependencies, no new actions.
- `EXPECTED_SHA` env wired from `${{ github.sha }}` (40-char SHA of the just-pushed commit on `main`).
- `RAILWAY_API_KEY` env wired from `secrets.RAILWAY_API_KEY`. Header args array conditionally appends `-H X-API-Key: …` only when the secret is non-empty (no header sent when unset).
- Per-request `curl -m 10` timeout prevents a hung Railway endpoint from eating the whole budget.
- `jq -r '.git_sha // "missing"'` coerces null/absent fields to a stable sentinel; equality comparison stays deterministic.
- The existing `live-gate-blocking` job (Plan 68-03 SANITY-08/09) is unmodified — `Live Site Gate (Blocking)` job name and steps unchanged.
- Workflow YAML loads cleanly via `yaml.safe_load`.

## Task Commits

Single atomic commit with `--no-verify` (worktree-executor protocol; consistent with prior commits in this phase):

1. **Task 1: Probe Railway /api/version for SHA match** — `2c890b3` (ci)

## Files Created/Modified

- `.github/workflows/deploy-web.yml` — Inserted a new step in the `deploy-backend` job (between `Wait for Railway webhook to redeploy` and the `live-gate-blocking` job comment block). +64 lines, no removals.

## Decisions Made

- **Step name fixed to grep-stable literal.** Phase 84 DEPLOY-02 grep-promotes this step by name; any rename would force Phase 84 to re-anchor, so the literal `Probe Railway /api/version for SHA match` is locked exactly as the plan specified.
- **`set -uo pipefail` over `-euo pipefail`.** With `-e`, a transient curl non-zero exit code (e.g., 28 timeout, 7 connect-refused during Railway warm-up) would abort the loop on the first iteration and prevent retries. The `-u` and `-o pipefail` parts still catch unset-var and pipeline failures.
- **`exit 0` on timeout despite `continue-on-error: true`.** Belt-and-suspenders: `continue-on-error` is the warn-only switch, but explicit `exit 0` ensures the step's log output reads as "TIMEOUT (warn-only per Phase 79 D-07)" rather than "command exited non-zero (ignored)". Cleaner workflow-summary semantics.
- **Conditional `-H X-API-Key` via array.** The `_AUTH_EXEMPT_PATHS` list in `web/api/main.py` (line 55) does NOT include `/api/version` — so the endpoint is auth-required when `API_KEY` is set on Railway. Sending the header only when `RAILWAY_API_KEY` is set means the step works in both auth-enforced and auth-disabled deploys.
- **No new repo secret.** Plan explicitly stated this is operator territory. `RAILWAY_API_KEY` is reused if already configured; otherwise the step still runs and a 401 surfaces as the timeout-warning path (which is acceptable warn-only behavior).
- **Smoke step lives only in `deploy-backend`.** Not in `deploy-frontend` (Vercel doesn't expose `/api/version`) or `live-gate-blocking` (which already has its own probes via `sanity_check_projections.py --check-live`).

## Deviations from Plan

None — plan executed exactly as written. The step name, position (after the 120s wait), `continue-on-error: true`, env wiring, polling cadence (15s), budget (300s / 5 min), curl/jq mechanics, annotation format, and warn-only `exit 0` on timeout all match the action text verbatim.

## Verification Run-Through

| Acceptance Item | Result |
|-----------------|--------|
| `grep -n "Probe Railway /api/version for SHA match" .github/workflows/deploy-web.yml` returns exactly one match | PASS (count: 1) |
| `grep -nE "continue-on-error: true" .github/workflows/deploy-web.yml` shows the new smoke step has it | PASS (line 181) |
| `grep -n "BUDGET_SECONDS=300" .github/workflows/deploy-web.yml` returns one match | PASS (line 189) |
| `grep -n 'github\.sha' .github/workflows/deploy-web.yml` shows EXPECTED_SHA env var sourcing from `${{ github.sha }}` | PASS (line 183 EXPECTED_SHA; line 64 pre-existing DEPLOY_SHA) |
| `grep -n "/api/version" .github/workflows/deploy-web.yml` returns at least one match | PASS (3 matches: VERSION_URL definition, warning annotation, notice annotation) |
| YAML parses cleanly: `python -c "import yaml; yaml.safe_load(...)"` exits 0 | PASS (`YAML OK`) |
| Plan's automated python verify (step in deploy-backend, idx > 0, continue-on-error True, EXPECTED_SHA contains github.sha, /api/version in run, BUDGET_SECONDS=300) | PASS — printed `OK ['Wait for Railway webhook to redeploy', 'Probe Railway /api/version for SHA match']` |
| `grep -nE "Live Site Gate \(Blocking\)" .github/workflows/deploy-web.yml` still shows the existing line content (live-gate-blocking unmodified) | PASS (line 250) |
| Smoke step positioned AFTER the existing 120s wait step (idx > 0) | PASS (idx == 1) |
| No untracked files post-commit | PASS (`git status --short` empty) |
| No unintended deletions in the commit | PASS (`git diff --diff-filter=D HEAD~1 HEAD` empty) |

## Confirmation: No New Secrets Added

Per D-07 and the plan's explicit "Do NOT add a new repo secret as part of this plan; that is operator territory" note, this plan introduces ZERO new repository secrets.

- The smoke step references `${{ secrets.RAILWAY_API_KEY }}`, an EXISTING secret already used elsewhere in the codebase (e.g., `audit_event_coverage.py`, live-gate `sanity_check_projections.py --check-live`).
- The `HEADER_ARGS` array conditional ensures the step degrades gracefully if `RAILWAY_API_KEY` is unset on the runner — the curl call still runs, no header is sent, and a 401 from auth-enforced Railway becomes the timeout-warning path (acceptable per warn-only semantics).
- No `${{ secrets.* }}` reference to any name other than the pre-existing `RAILWAY_API_KEY`.

## Phase 84 Promotion Path

Phase 84 DEPLOY-02 inherits this step. Promotion is a TWO-line surgery:

1. **Delete the line `continue-on-error: true`** (line 181 today) → step now fails the job on non-zero exit.
2. **In the timeout branch (lines 211-215):**
   - Change `::warning title=Railway /api/version SHA asymmetry…` to `::error title=Railway /api/version SHA asymmetry…`.
   - Change the trailing `exit 0` to `exit 1`.

The match-path branch and all polling-loop mechanics carry over unchanged. The grep-stable step name `Probe Railway /api/version for SHA match` lets Phase 84 anchor its edit script without ambiguity.

## Issues Encountered

None.

## User Setup Required

None — no operator action needed for this plan to ship. The smoke step runs on the next push that triggers `deploy-web.yml`. The first run will exercise the polling loop against the live Railway `/api/version` endpoint (now returning 7-key shape per Plan 79-03).

If the operator wants to suppress the X-API-Key header path entirely (e.g., during a Railway deployment where API_KEY is unset), no action is required — the conditional header-args array handles it.

## Next Phase Readiness

- **Phase 84 DEPLOY-02** can now promote this step from warn-only to fail-on-mismatch via the two-line edit described above. The step name is grep-stable and the polling logic is production-tested by the time Phase 84 runs.
- **Asymmetry detection capability** is now LIVE in CI (warn-only). Any push that ships code Railway then fails to roll out within 5 minutes will surface a `::warning::Railway /api/version SHA asymmetry::…` annotation on the workflow summary page — visible to humans even before Phase 84 hardens it.
- The v7.1 silent-freeze failure mode (Phase 66 → Phase 75 stuck on stale image) now has a CI-visible canary. Future deploys missing the just-pushed SHA in the live `/api/version` after 5 minutes will be flagged.

## Self-Check: PASSED

- Files modified:
  - `.github/workflows/deploy-web.yml` — FOUND (modified, +64 lines)
- Files created:
  - `.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-04-version-probe-smoke-step-SUMMARY.md` — FOUND (this file)
- Commits exist on `worktree-agent-a52aeee5`:
  - `2c890b3` (Task 1) — FOUND (`ci(79-04): probe Railway /api/version for SHA match in deploy-backend`)

---
*Phase: 79-audit-provenance-version-probe*
*Plan: 04 — version-probe-smoke-step*
*Completed: 2026-04-28*
