---
phase: 79-audit-provenance-version-probe
plan: 01
subsystem: infra
tags: [git, subprocess, audit, provenance, security, python]

# Dependency graph
requires: []
provides:
  - "src.utils.get_script_sha(script_path) returning {sha, dirty, resolved_at}"
  - "Shell-injection-safe subprocess pattern (shell=False + `--` separator) for future git callers"
  - "Foundation primitive for DQ-01 audit-script provenance contract (consumed by 79-02 onward)"
affects:
  - 79-02-audit-script-wiring
  - 79-03-version-endpoint
  - 79-04-version-probe-smoke
  - 84-deploy-hardening (DEPLOY-04 reads script_provenance.sha)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shell-safe subprocess invocation (shell=False, list-form argv, `--` separator before path)"
    - "Graceful degradation to sha='unknown' on FileNotFoundError/TimeoutExpired/OSError"
    - "10s subprocess timeout to bound DoS exposure on hung git"

key-files:
  created:
    - tests/test_get_script_sha.py
  modified:
    - src/utils.py

key-decisions:
  - "Helper returns plain Dict[str, Any] (not a dataclass) to keep audit-JSON serialisation trivial"
  - "Both git invocations use `--` separator before the path token to neutralise hostile path arguments (T-79-01 mitigation)"
  - "Diff probe is skipped when sha='unknown' to avoid spurious dirty=True on untracked paths"

patterns-established:
  - "Project-wide pattern: any subprocess call into `git` MUST use shell=False, list argv, and `--` separator before user-influenced path tokens"
  - "Audit provenance contract: {sha, dirty, resolved_at} is the canonical shape future audit scripts embed under top-level `script_provenance` key"

requirements-completed: [DQ-01]

# Metrics
duration: ~5min
completed: 2026-04-28
---

# Phase 79 Plan 01: Audit Script SHA Helper Summary

**Shell-injection-safe `get_script_sha(script_path)` helper in `src/utils.py` returning `{sha, dirty, resolved_at}` for DQ-01 audit-JSON provenance, with 6-test pytest fixture-based coverage.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-28T02:08:00Z
- **Completed:** 2026-04-28T02:10:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- New `get_script_sha(script_path: str) -> Dict[str, Any]` in `src/utils.py` returning the file-specific last-commit SHA, a `dirty` bool, and an ISO-8601 UTC `resolved_at` timestamp
- Both subprocess invocations (`git log -1 --format=%H -- {path}` and `git diff HEAD -- {path}`) use `shell=False`, list-form argv, 10s timeout, and a literal `--` separator before the path token (T-79-01 mitigation)
- Graceful degradation to `sha='unknown'`, `dirty=False` on `FileNotFoundError` (no git binary), `TimeoutExpired` (hung subprocess), `OSError`, untracked paths, and non-existent paths — helper never raises
- 6 pytest tests using a temp-dir git repo fixture (`monkeypatch.chdir`) cover: clean tracked file (40-char hex SHA + `dirty=False`), dirty tracked file (post-commit edit + `dirty=True`), untracked file (`sha='unknown'`), nonexistent path (`sha='unknown'`), `resolved_at` parses as ISO-8601 UTC via `datetime.fromisoformat`, and shell-injection safety (mock asserts both git invocations use `shell=False`, list argv, and `--` separator before the path)

## Task Commits

Each task was committed atomically (parallel-executor `--no-verify` per orchestrator instruction):

1. **Task 1: Implement get_script_sha() helper in src/utils.py** — `37ac6b2` (feat)
2. **Task 2: Add unit tests for get_script_sha** — `3eff93c` (test)

_Note: Plan was tagged `tdd="true"` on each task, but per the explicit `<action>` text the helper landed first (Task 1) and the formal pytest file landed second (Task 2). The task-1 verification command exercised the same behaviours the formal tests later codified, so behavioural coverage was continuous._

## Files Created/Modified

- `src/utils.py` — Added imports (`subprocess`, `datetime`/`timezone`, `pathlib.Path`) and appended `get_script_sha()` immediately after `download_latest_parquet()`. 74-line addition; no existing helpers touched.
- `tests/test_get_script_sha.py` — New 126-line pytest module with `_git()` helper, `temp_repo` fixture, and 6 test cases.

## Decisions Made

- **Plain Dict over dataclass:** Return shape stays `Dict[str, Any]` so audit scripts can JSON-dump it directly with no `asdict()` indirection — matches D-03 in CONTEXT.md.
- **Diff probe skipped on `sha='unknown'`:** When the helper cannot resolve a tracked SHA, running `git diff HEAD -- {untracked-path}` would still return non-empty output (the new file content). Skipping the diff in that branch keeps the contract `unknown ⇒ dirty=False` clean for Phase 84 DEPLOY-04 to reason about.
- **`--` separator on BOTH calls:** Even though `git log` and `git diff` are read-only, defence-in-depth says any future caller that passes user-controlled paths gets the same protection. The plan's threat-model entry T-79-01 was honoured on every subprocess.run.

## Deviations from Plan

None — plan executed exactly as written. Both task commits matched the action text; both verification commands and acceptance criteria pass; no auto-fixes triggered.

## Issues Encountered

- The worktree at `.claude/worktrees/agent-a6d67770/` has no local `venv/`; running `python` directly fails with `ModuleNotFoundError: No module named 'boto3'`. Resolved by invoking the parent repo's interpreter directly (`/Users/georgesmith/repos/nfl_data_engineering/venv/bin/python`) for the verification step and pytest run. This is a worktree-shape quirk, not a code issue, and does not affect the committed deliverables.

## User Setup Required

None — no external service configuration required. `get_script_sha` is a pure git-CLI consumer; works on any developer machine and CI runner with `git` on `$PATH`.

## Next Phase Readiness

- **Plan 79-02 (audit-script wiring) unblocked:** Imports `from src.utils import get_script_sha` and embeds the dict under `script_provenance` in `event_coverage.json`, `advisor_tools_72.json`, and the parent advisor-tools script.
- **Phase 84 DEPLOY-04 contract locked:** The `{sha, dirty, resolved_at}` shape is now stable. Any future change to the helper must preserve those three keys or open a coordinated change with Phase 84.
- No blockers, no concerns.

## Self-Check: PASSED

- `src/utils.py` exists and contains `def get_script_sha(` — FOUND
- `tests/test_get_script_sha.py` exists with 6 pytest tests — FOUND
- Commit `37ac6b2` (feat) — FOUND in `git log`
- Commit `3eff93c` (test) — FOUND in `git log`
- `pytest tests/test_get_script_sha.py -x -q` → 6 passed in 2.30s
- `pytest tests/test_utils.py -x -q` → 5 passed (no regression)

---
*Phase: 79-audit-provenance-version-probe*
*Plan: 01-script-sha-helper*
*Completed: 2026-04-28*
