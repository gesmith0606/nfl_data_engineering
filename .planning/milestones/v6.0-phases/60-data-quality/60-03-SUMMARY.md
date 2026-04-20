---
phase: 60-data-quality
plan: 03
subsystem: ci-cd
tags: [github-actions, ci-gate, sanity-check, deploy-workflow, data-quality]

# Dependency graph
requires:
  - phase: 60-02
    provides: "scripts/sanity_check_projections.py with exit-code-zero contract (0 = no CRITICAL, 1 = CRITICAL present)"
  - phase: existing
    provides: "deploy-web.yml with Vercel frontend + ECR/SAM backend deploy jobs"
provides:
  - "Data Quality Gate job in .github/workflows/deploy-web.yml that runs sanity check on every web/src/data/workflow push"
  - "needs: quality-gate dependency on both deploy-frontend and deploy-backend"
  - "data/** path trigger so data-only changes also validate before deploy"
affects:
  - "Every future push to main touching web/, src/, data/, or this workflow goes through the sanity gate before reaching production"
  - "Backup QB in top 5, negative projections, and other CRITICAL structural absurdities now block deploys (D-06, D-07)"
  - "Closes phase 60-data-quality — all 3 plans executed, DQAL-01..04 requirements satisfied"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GitHub Actions job dependency graph: quality-gate -> deploy-frontend and quality-gate -> deploy-backend via `needs:`"
    - "CI gate keys exclusively on process exit code (no stdout grep); warnings-only runs exit 0 and allow deploy"
    - "Python 3.11 + pip cache pattern reused from daily-sentiment.yml for consistency across workflows"

key-files:
  created: []
  modified:
    - ".github/workflows/deploy-web.yml"

key-decisions:
  - "Gate keys on exit code only, never on grep — preserves the contract codified in 60-02 where warnings do not block deploy"
  - "Added data/** to paths trigger so parquet refreshes (daily sentiment cron commits, manual regens) route through the sanity gate"
  - "Preserved deploy-frontend commit-message `if:` condition verbatim; `needs: quality-gate` layers on top without altering deploy selectivity"

patterns-established:
  - "Quality-gate-before-deploy pattern: a dedicated pre-deploy job that runs data/code validation and blocks downstream deploys via `needs:`. Transplantable to any future deploy workflow."

requirements-completed: [DQAL-03]

# Metrics
duration: 4min
completed: 2026-04-17
---

# Phase 60 Plan 03: Wire Sanity Check as CI Gate in deploy-web.yml Summary

**Added a `quality-gate` job to `.github/workflows/deploy-web.yml` that runs `scripts/sanity_check_projections.py` before any deploy; CRITICAL issues (exit 1) now block both the Vercel frontend and the ECR/SAM backend deploy. Closes phase 60-data-quality.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-17T18:15:00Z (approx)
- **Completed:** 2026-04-17T18:19:00Z (approx)
- **Tasks:** 1
- **Files modified:** 1 (existing; no new files)

## Accomplishments

- Added `quality-gate` job to `.github/workflows/deploy-web.yml`:
  - Runs on `ubuntu-latest`
  - Checks out repo, sets up Python 3.11 with pip cache on `requirements.txt`, installs deps
  - Executes `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026`
  - Exit code 1 (CRITICAL issues present) causes the job to fail, which in turn blocks downstream deploys
- Added `needs: quality-gate` to `deploy-frontend` and `deploy-backend` so the quality gate is a hard precondition for both deploys
- Added `data/**` to the `paths` trigger so data-only changes (e.g., daily roster/sentiment commits) also run the gate before any subsequent deploy
- Preserved the existing `deploy-frontend` `if:` commit-message condition verbatim — `needs:` layers on top without changing conditional deploy behavior
- Documented the exit-code contract (0 = deploy, 1 = block) in a comment block above the new job so future maintainers see it inline

## Task Commits

1. **Task 1: Wire sanity check as CI gate** — `0473fe9` (ci)

## Files Created/Modified

- `.github/workflows/deploy-web.yml` (modified, +33/-0) — Added `data/**` to paths trigger, added `quality-gate` job with Python 3.11 + requirements.txt pip cache + sanity check invocation, added `needs: quality-gate` to both deploy jobs.

## Decisions Made

- **Exit-code-only gating.** The gate step runs the sanity check as a normal GHA shell command; a nonzero exit fails the step which fails the job which blocks `needs:` dependents. No grep on stdout, no additional parsing. This respects the exit-code-zero contract codified by Plan 60-02 (warnings allowed, criticals block) and avoids the classic "stdout-parsing-bites-you-in-production" anti-pattern.
- **Python 3.11 + pip cache** matching daily-sentiment.yml. Consistent tooling across workflows simplifies cache reuse and avoids divergent Python versions between CI jobs.
- **`data/**` path trigger added.** The existing workflow only triggered on `web/**` and `src/**`. The sanity check reads Gold parquet from `data/gold/...`, so a data-only commit (e.g., the daily sentiment cron that updates roster files) should also re-run the gate to validate that the refreshed data is still deployable.
- **Did not consolidate deploy-frontend commit-message filter into the gate.** Gate is unconditional by design — any push to main on the trigger paths validates data. Whether to actually ship the frontend remains gated on the commit-message heuristic (existing behavior), unchanged.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Deferred Issues

None new in this plan. Pre-existing items carried from 60-02 (not addressed here; out of scope):
- Negative projection bug in `src/projection_engine.py` for 7 bench players (surfaces as WARNING in the sanity check; does not block CI per the exit-code contract)
- 2025 rookie coverage gap in Gold projections (surfaces as WARNING; does not block CI)
- Rank-gap threshold calibration (18 live-Sleeper-vs-our-model rank gaps fire as warnings)

## Known Stubs

None. The workflow is fully wired and verifiable end-to-end.

## Threat Flags

None. The plan's threat register (T-60-08 workflow_dispatch bypass, T-60-09 Sleeper API DoS, T-60-10 script tampering) covers every new surface introduced. No new trust boundary was added — GitHub Actions runner permissions unchanged, `requirements.txt` unchanged, script unchanged from 60-02's exit-code contract.

## User Setup Required

None. No new secrets, environment variables, or external service configuration. The gate will start running on the next push to main that touches `web/`, `src/`, `data/`, or the workflow file itself.

## Verification Evidence

Plan verification commands (all from `/Users/georgesmith/repos/nfl_data_engineering/`):

- `grep -c "quality-gate" .github/workflows/deploy-web.yml` -> **4** (job name + 2 `needs:` + doc comment)
- `grep -c "needs: quality-gate" .github/workflows/deploy-web.yml` -> **3** (2 deploy jobs + 1 header comment mentioning the dependency)
- `grep -c "sanity_check_projections" .github/workflows/deploy-web.yml` -> **2** (comment + run command)
- `grep -c "data/\*\*" .github/workflows/deploy-web.yml` -> **1** (paths trigger)
- `grep -n "if:" .github/workflows/deploy-web.yml` -> **line 53** (deploy-frontend commit-message condition preserved)
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-web.yml'))"` -> **YAML valid**
- Local sanity check smoke test: `python scripts/sanity_check_projections.py --scoring half_ppr --season 2026` -> **exit 0** (0 CRITICAL, 34 WARNINGS; PASS as expected — CI would allow deploy)

## Next Phase Readiness

- **Phase 60 is COMPLETE.** All 3 plans executed:
  - 60-01 (roster refresh position update + change logging) — shipped
  - 60-02 (sanity check freshness + live consensus + 2026 top-50) — shipped
  - 60-03 (CI gate) — this plan, shipped
- Requirements satisfied: DQAL-01 and DQAL-02 (plan 60-01), DQAL-04 (plan 60-02), DQAL-03 (plan 60-02 for the check itself + plan 60-03 for the CI gate wiring)
- The phase is ready for `/gsd:verify-work 60`. Verifier should confirm:
  - Position updates flow from Sleeper into Gold parquet via `refresh_rosters.py`
  - Sanity check exits 0 with 0 CRITICAL on current Gold data
  - deploy-web.yml blocks on exit 1 (simulate locally with a forced CRITICAL to prove the gate fires)
- Subsequent phases (61 News & Sentiment Live, 62 Design & UX, 63 AI Advisor, 64 Matchup View, 65 Agent Ecosystem) are independent per ROADMAP.md and can start in any order.

## Self-Check: PASSED

- FOUND: .github/workflows/deploy-web.yml (modified, 33 lines added)
- FOUND: commit 0473fe9 (ci - quality-gate CI gate wiring)
- FOUND: .planning/phases/60-data-quality/60-03-SUMMARY.md (this file)

---
*Phase: 60-data-quality*
*Completed: 2026-04-17*
