---
phase: 73-external-projections-comparison
plan: 05
type: execute
wave: 5
depends_on: [73-04]
files_modified:
  - .github/workflows/weekly-external-projections.yml
  - tests/test_weekly_external_projections_workflow.py
  - .planning/phases/73-external-projections-comparison/73-SUMMARY.md
  - .planning/STATE.md
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
autonomous: true
requirements: [EXTP-05]
must_haves:
  truths:
    - "GitHub Actions workflow .github/workflows/weekly-external-projections.yml exists with scheduled cron triggers (Tuesdays 14:00 UTC + Sundays 12:00 UTC) and workflow_dispatch input overrides"
    - "Workflow auto-detects current NFL season + week (mirrors weekly-pipeline.yml compute-week job)"
    - "Workflow runs all 3 Bronze ingesters in parallel (matrix job) followed by the Silver consolidation step (depends on the 3 Bronze jobs)"
    - "Workflow commits the new Bronze + Silver Parquets back to the repo via a final commit-and-push step (matches the daily-sentiment.yml pattern)"
    - "Per-source ingester failure does NOT cancel the silver-consolidation step (continue-on-error: true on each Bronze matrix item) — D-06 fail-open"
    - "Phase 73 SUMMARY.md, STATE.md, REQUIREMENTS.md, ROADMAP.md updated with EXTP-01..05 marked ✓"
  artifacts:
    - path: ".github/workflows/weekly-external-projections.yml"
      provides: "Twice-weekly cron + workflow_dispatch entry to refresh external projections"
      contains: "weekly-external-projections"
    - path: "tests/test_weekly_external_projections_workflow.py"
      provides: "Structural validation of the workflow YAML (cron schedule, jobs, dependencies)"
    - path: ".planning/phases/73-external-projections-comparison/73-SUMMARY.md"
      provides: "Phase 73 closeout summary"
  key_links:
    - from: ".github/workflows/weekly-external-projections.yml"
      to: "scripts/ingest_external_projections_{espn,sleeper,yahoo}.py"
      via: "matrix job invoking each ingester"
      pattern: "ingest_external_projections_"
    - from: ".github/workflows/weekly-external-projections.yml"
      to: "scripts/silver_external_projections_transformation.py"
      via: "consolidation job (needs: [ingest])"
      pattern: "silver_external_projections_transformation"
---

<objective>
Wire the new Phase 73 pipeline to a recurring schedule and close the phase. The workflow refreshes external projections twice a week (post-MNF and pre-game-day), runs the 3 Bronze ingesters in parallel, consolidates Silver, and commits the results so the API has fresh data without any human in the loop. Then write the phase SUMMARY and sync STATE/REQUIREMENTS/ROADMAP.

Purpose: Close requirement EXTP-05 (cron-refresh + freshness surfacing) and close Phase 73.
Output: 1 GHA workflow file, 1 structural test, 1 phase SUMMARY, planning docs updated.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/73-external-projections-comparison/73-CONTEXT.md
@.planning/phases/73-external-projections-comparison/73-01-bronze-ingesters-PLAN.md
@.planning/phases/73-external-projections-comparison/73-02-silver-consolidation-PLAN.md
@.planning/phases/73-external-projections-comparison/73-03-api-comparison-endpoint-PLAN.md
@.planning/phases/73-external-projections-comparison/73-04-frontend-comparison-view-PLAN.md
@.github/workflows/weekly-pipeline.yml
@CLAUDE.md

<interfaces>
<!-- Workflow patterns to mirror -->

From .github/workflows/weekly-pipeline.yml:
- `compute-week` job: auto-detects (season, week) from today's date with workflow_dispatch input overrides — extract this verbatim into the new workflow (or reuse via reusable workflow if the repo supports `workflow_call`).
- Uses `actions/checkout@v4` + `actions/setup-python@v5` with `cache: pip`
- `concurrency: group: weekly-pipeline / cancel-in-progress: false` to prevent concurrent runs

From .github/workflows/daily-sentiment.yml (referenced in STATE.md context):
- `permissions: contents: write, issues: write` for the commit-back step
- Commit-and-push pattern (look up the actual file when implementing)

Cron schedules per CONTEXT.md:
- `0 14 * * 2` — Tuesday 14:00 UTC (post-MNF refresh)
- `0 12 * * 0` — Sunday 12:00 UTC (pre-game-day refresh)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Author weekly-external-projections.yml workflow + structural test</name>
  <files>
    .github/workflows/weekly-external-projections.yml,
    tests/test_weekly_external_projections_workflow.py
  </files>
  <behavior>
    - YAML structure:
       1. `name: Weekly External Projections Refresh`
       2. `on:` two cron entries (Tue 14:00 UTC, Sun 12:00 UTC) + `workflow_dispatch` with `season` + `week` + `scoring` (default `half_ppr`) inputs
       3. `concurrency: { group: weekly-external-projections, cancel-in-progress: false }`
       4. `permissions: { contents: write }` (needed for the commit-back step)
       5. `env: PYTHON_VERSION: "3.11"` (matches weekly-pipeline.yml)
       6. Job 1 `compute-week`: copy the auto-detect Python from weekly-pipeline.yml verbatim (priority: workflow_dispatch inputs > PIPELINE_WEEK_OVERRIDE var > auto-compute). Outputs `season`, `week`.
       7. Job 2 `ingest`: matrix `source: [espn, sleeper, yahoo]`, `needs: [compute-week]`, `continue-on-error: true` (D-06: one source failure does NOT block the others or the consolidation), runs `python scripts/ingest_external_projections_${{ matrix.source }}.py --season $SEASON --week $WEEK`
       8. Job 3 `consolidate`: `needs: [compute-week, ingest]` with `if: always()` (so consolidation runs even if some ingesters failed), runs `python scripts/silver_external_projections_transformation.py --season $SEASON --week $WEEK --scoring ${{ inputs.scoring || 'half_ppr' }}`
       9. Job 4 `commit-back`: `needs: [consolidate]`, commits any new files under `data/bronze/external_projections/` and `data/silver/external_projections/` back to the repo. Uses `git add data/bronze/external_projections/ data/silver/external_projections/` (specific paths, NOT `git add .` per .claude rules). Commit message: `data(external-projections): refresh season=$SEASON week=$WEEK [skip ci]`.
       10. Job 5 `notify-failure`: `if: failure() || cancelled()` — opens GitHub issue with run URL (mirror weekly-pipeline.yml's notify-failure job)
    - Structural test `tests/test_weekly_external_projections_workflow.py` parses the YAML with `pyyaml` and asserts:
       - `test_workflow_has_two_cron_schedules` — exactly 2 cron entries, one Tue 14:00 UTC, one Sun 12:00 UTC
       - `test_workflow_has_workflow_dispatch_inputs` — season + week + scoring inputs exist
       - `test_ingest_job_uses_matrix_for_three_sources` — matrix.source contains exactly ["espn", "sleeper", "yahoo"]
       - `test_ingest_continue_on_error_is_true` — D-06 fail-open contract enforced at workflow level
       - `test_consolidate_runs_if_always` — `if: always()` on consolidate so it runs even if some ingesters failed
       - `test_commit_back_uses_specific_paths_not_git_add_all` — git add command targets `data/bronze/external_projections/` and `data/silver/external_projections/` only (TD-pattern: never `git add .`)
       - `test_workflow_does_not_use_no_verify` — TD-01 awareness: assert `--no-verify` not present anywhere in the YAML
       - `test_workflow_does_not_hardcode_season_year` — TD-03 awareness: assert no literal year >= 2024 baked into a script invocation (use $SEASON env)
  </behavior>
  <action>
    1. Read `.github/workflows/weekly-pipeline.yml` to copy the `compute-week` job verbatim.
    2. Read `.github/workflows/daily-sentiment.yml` to confirm the commit-back permission pattern + actor/email setup.
    3. Author `.github/workflows/weekly-external-projections.yml` per the Behavior block. Use 2-space YAML indent.
    4. CRITICAL TD-style guards:
       - DO NOT use `git commit --no-verify` (TD-01)
       - DO NOT use `git add .` — use specific paths (this PR's defensive pattern)
       - DO NOT hardcode season year — use `$SEASON` from compute-week output (TD-03 spirit)
    5. Commit-back step git config:
       ```yaml
       - name: Commit and push refreshed parquets
         run: |
           git config user.name  "github-actions[bot]"
           git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
           git add data/bronze/external_projections/ data/silver/external_projections/
           if git diff --staged --quiet; then
             echo "No changes to commit (sources may have failed silently — D-06)"
             exit 0
           fi
           git commit -m "data(external-projections): refresh season=$SEASON week=$WEEK [skip ci]"
           git push
       ```
    6. Create `tests/test_weekly_external_projections_workflow.py` with 8 assertions per the Behavior block. Use `pyyaml` (already in requirements; if not, add). Pattern: `with open(WORKFLOW_PATH) as f: workflow = yaml.safe_load(f)` then index into the dict.
    7. NB: `on:` is a YAML keyword and pyyaml parses it as `True` boolean key — handle by `workflow.get(True, workflow.get("on"))` OR use `yaml.SafeLoader` with care. Document the workaround in a comment.
    8. Run `python -m pytest tests/test_weekly_external_projections_workflow.py -v` — 8 tests pass.
    9. Validate YAML syntax: `python -c "import yaml; yaml.safe_load(open('.github/workflows/weekly-external-projections.yml'))"` — no exception.
  </action>
  <verify>
    <automated>python -m pytest tests/test_weekly_external_projections_workflow.py -v</automated>
  </verify>
  <done>
    - Workflow YAML exists, parses cleanly
    - 8 structural tests pass
    - D-06 fail-open at workflow level (continue-on-error + if: always)
    - TD-01 / TD-03 patterns honored (no --no-verify, no hardcoded year, no git add .)
    - Commit-back uses specific paths
  </done>
</task>

<task type="auto">
  <name>Task 2: Phase 73 SUMMARY.md + STATE/REQUIREMENTS/ROADMAP sync</name>
  <files>
    .planning/phases/73-external-projections-comparison/73-SUMMARY.md,
    .planning/STATE.md,
    .planning/REQUIREMENTS.md,
    .planning/ROADMAP.md
  </files>
  <action>
    1. Create `.planning/phases/73-external-projections-comparison/73-SUMMARY.md` with sections:
       - Frontmatter: `phase`, `status: complete`, `completed: <today>`, `requirements: [EXTP-01, EXTP-02, EXTP-03, EXTP-04, EXTP-05]`, `plans_complete: 5/5`
       - **Goal Recap** — 1 paragraph from CONTEXT.md
       - **What Shipped** — table mapping each plan (73-01..05) to artifacts and tests count
       - **Requirements Closure** — table with EXTP-01..05 each marked ✓ with evidence (file path or test name)
       - **Source Provenance** — note that Yahoo is "yahoo_proxy_fp" (FantasyPros consensus) until real Yahoo OAuth lands in v8.0
       - **D-06 Fail-Open Verification** — list every fail-open path (each ingester, Silver consolidator, API endpoint, frontend EmptyState, GHA workflow continue-on-error)
       - **Frontend Screenshots** — embed/reference the 2 screenshots from Plan 73-04 Task 4 (desktop + mobile)
       - **Cron Schedule** — Tue 14:00 UTC + Sun 12:00 UTC, manual override via gh workflow run
       - **Tests** — total new test count across the 5 plans
       - **Open Items** — any deferred work (real Yahoo OAuth, CBS, consensus auto-compute) — should match CONTEXT.md "Deferred Ideas"
       - **Handoff** — what enables next: parallel phases (74 Sleeper League, 75 Tech Debt) unblocked
    2. Update `.planning/STATE.md`:
       - Bump `progress.completed_plans` and `progress.percent`
       - Update `stopped_at` and `last_activity` to reflect Phase 73 closure
       - Add Phase 73 closure note to `Accumulated Context > Decisions`
       - Update `Current Position` to next pending phase (74 or 75 depending on user choice)
    3. Update `.planning/REQUIREMENTS.md` — mark EXTP-01..05 as ✓ in the EXTP section AND in the Traceability Table (`EXTP-01..05 | 73 | All shipped`)
    4. Update `.planning/ROADMAP.md`:
       - Mark Phase 73 checkbox as `[x]` in the v7.1 summary checklist
       - Update the Phase 73 Plans subsection: each plan from `[ ]` to `[x]` with completion date
       - Update the Progress table row for Phase 73 to `5/5 | Complete | <today>`
    5. Verify all four files saved correctly:
       - `cat .planning/STATE.md | grep -E "completed_plans|stopped_at" | head -3`
       - `grep -c "EXTP-0" .planning/REQUIREMENTS.md` — at least 5 ✓ markers
       - `grep "Phase 73" .planning/ROADMAP.md` — checkbox is `[x]`
  </action>
  <verify>
    <automated>test -f .planning/phases/73-external-projections-comparison/73-SUMMARY.md && grep -q "EXTP-05" .planning/REQUIREMENTS.md && grep -q "\\[x\\] \\*\\*Phase 73" .planning/ROADMAP.md && python -c "import re; s=open('.planning/STATE.md').read(); assert 'Phase 73' in s or '73-' in s, 'STATE.md not updated'"</automated>
  </verify>
  <done>
    - 73-SUMMARY.md exists with all required sections
    - STATE.md progress + position updated
    - REQUIREMENTS.md EXTP-01..05 marked ✓
    - ROADMAP.md Phase 73 checkbox closed + Plans list closed + Progress table row updated
    - All 4 files saved + verified
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner → repo | The workflow commits back to the repo — needs scoped permissions |
| External APIs → workflow | ESPN/Sleeper/FP HTTP responses cross into the runner |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-73-05-01 | Elevation of Privilege | commit-back step uses GITHUB_TOKEN | mitigate | `permissions: contents: write` (least-privilege scope; no `actions: write` or `secrets: read`) |
| T-73-05-02 | Tampering | git add . could pick up unintended files | mitigate | Specific paths only: `git add data/bronze/external_projections/ data/silver/external_projections/` — verified by structural test |
| T-73-05-03 | Repudiation | --no-verify bypasses pre-commit hooks | mitigate | TD-01 pattern: assert `--no-verify` absent in workflow YAML via `test_workflow_does_not_use_no_verify` |
| T-73-05-04 | Denial of Service | one slow ingester blocks all sources | mitigate | Matrix `continue-on-error: true` + `consolidate` step `if: always()` — D-06 fail-open at the workflow level |
| T-73-05-05 | Information Disclosure | Workflow logs leak API keys | accept | None of the 3 ingesters require API keys (ESPN league=0 public, Sleeper public, FP public scrape). No secrets needed by this workflow. |
</threat_model>

<verification>
- 8 workflow structural tests pass: `python -m pytest tests/test_weekly_external_projections_workflow.py -v`
- YAML lints clean: `python -c "import yaml; yaml.safe_load(open('.github/workflows/weekly-external-projections.yml'))"`
- Phase planning docs synced: SUMMARY exists, STATE bumped, REQUIREMENTS marks ✓, ROADMAP marks `[x]`
- Manual workflow_dispatch run (after merge): `gh workflow run weekly-external-projections.yml -f season=2025 -f week=1 -f scoring=half_ppr` — completes successfully (out of band; not blocking the PR)
- Full test suite green: `python -m pytest tests/ -q -x`
</verification>

<success_criteria>
- [x] weekly-external-projections.yml exists with twice-weekly cron + workflow_dispatch
- [x] Bronze matrix runs all 3 ingesters in parallel with continue-on-error
- [x] Silver consolidation runs `if: always()` so it runs even on partial failure
- [x] Commit-back uses specific paths and DOES NOT use --no-verify (TD-01 + TD-03 alignment)
- [x] Phase 73 SUMMARY written with EXTP-01..05 evidence
- [x] STATE.md progress incremented
- [x] REQUIREMENTS.md EXTP markers all ✓
- [x] ROADMAP.md Phase 73 closed
- [x] 8 workflow tests pass; full suite green
</success_criteria>

<output>
After completion, the phase is closed. Phase 74 (Sleeper League) and Phase 75 (Tech Debt) remain unblocked and parallel-runnable.

The Phase 73 SUMMARY at `.planning/phases/73-external-projections-comparison/73-SUMMARY.md` is the canonical artifact future planners should read for context.
</output>
