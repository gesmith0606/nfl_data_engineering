---
phase: 75-tech-debt-cleanup
status: complete
shipped: 2026-04-26
requirements: [TD-01, TD-02, TD-03, TD-04, TD-05, TD-06, TD-07, TD-08]
---

# Phase 75: v7.0 Tech Debt Cleanup — SUMMARY

All 8 tech debt items rolled forward from the v7.0 audit are now closed.

## Items Cleared

| ID | Item | Fix |
|----|------|-----|
| TD-01 | Auto-rollback used `--amend --no-verify` (policy violation) | Single `git revert --no-commit HEAD` + `git commit -m "..."` — no amend, no hook bypass |
| TD-02 | `web/frontend/**/*.json` blocked by root `*.json` gitignore | Added `!web/frontend/**/*.json` allowlist; package.json/tsconfig now ship via git |
| TD-03 | Hardcoded `--season 2026` in daily-sentiment.yml roster refresh | Replaced with `$(date +%Y)` |
| TD-04 | Duplicate `relativeTime()` in news-feed + player-news-panel | Both now delegate to `formatRelativeTime` from `@/lib/format-relative-time` |
| TD-05 | `formatRelativeTime("")` returned "unknown" → "Updated unknown" UI bug | Empty/null/undefined input → 'unknown' (callers null-check before rendering) |
| TD-06 | `VALID_NFL_TEAMS` had duplicate `LA` + `LAR` for Rams | Dropped `LAR`; single `LA` entry per nflverse convention |
| TD-07 | Structural test missing for `--no-verify` absence in auto-rollback | `test_auto_rollback_pushes_non_force` asserts both `--no-verify` AND `--amend` absence |
| TD-08 | CLAUDE.md silent on Bronze rosters + depth_charts being version-controlled | Added explicit note + warning not to re-add to .gitignore |

## Test Results

- `tests/test_deploy_workflow_v2.py`: **20/20 passing** (TD-07 enforcement test green)
- Frontend `tsc --noEmit`: clean

## Files Modified

```
.github/workflows/deploy-web.yml      (TD-01: revert+commit; no amend; no --no-verify)
.github/workflows/daily-sentiment.yml (TD-03: $(date +%Y))
.gitignore                            (TD-02: !web/frontend/**/*.json)
scripts/sanity_check_projections.py   (TD-06: drop LAR)
tests/test_deploy_workflow_v2.py      (TD-07: structural assertions)
CLAUDE.md                             (TD-08: documented committed Bronze paths)
web/frontend/src/lib/format-relative-time.ts          (TD-05: empty/null guard)
web/frontend/src/features/nfl/components/news-feed.tsx          (TD-04: delegate)
web/frontend/src/features/nfl/components/player-news-panel.tsx  (TD-04: delegate)
```

## Self-Check: PASSED

- [x] All 8 TD items implemented
- [x] TD-07 structural test asserts the contract for TD-01
- [x] No regression in existing deploy-web tests
- [x] Frontend tsc clean
