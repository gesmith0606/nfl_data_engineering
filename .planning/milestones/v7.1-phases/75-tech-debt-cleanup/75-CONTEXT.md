# Phase 75: v7.0 Tech Debt Cleanup - Context

**Gathered:** 2026-04-26
**Status:** Ready for execution

8 concrete tech debt items rolled forward from v7.0 audit. Items are atomic — each one ships independently.

| ID | Item |
|----|------|
| TD-01 | Remove `git commit --amend --no-verify` from auto-rollback (single revert with `-m`); add structural test guard for `--no-verify` absence (TD-07) |
| TD-02 | Allow `web/frontend/**/*.json` past root `*.json` gitignore so package.json/tsconfig/vitest.config land via git |
| TD-03 | Replace hardcoded `--season 2026` in `daily-sentiment.yml` roster refresh with `$(date +%Y)` |
| TD-04 | Consolidate duplicate `relativeTime()` in news-feed.tsx + player-news-panel.tsx → import `formatRelativeTime` from `@/lib/format-relative-time` |
| TD-05 | `formatRelativeTime("")` should not produce "Updated unknown" — guard upstream |
| TD-06 | `VALID_NFL_TEAMS` single Rams entry (`LA`, drop `LAR`) |
| TD-07 | Structural test asserts `--no-verify` absence in auto-rollback workflow |
| TD-08 | CLAUDE.md documents Bronze rosters + depth_charts committed since 2026-04-24 |
