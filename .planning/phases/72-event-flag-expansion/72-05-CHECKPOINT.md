---
plan: 72-05-backfill-audit-summary
phase: 72-event-flag-expansion
status: human-action-required
created: 2026-04-25
requirements: [EVT-04, EVT-05]
---

# Plan 72-05: Backfill + Audit + SUMMARY — CHECKPOINT (HUMAN ACTION REQUIRED)

This plan was scoped per CONTEXT D-04 to require **Railway-live** audit JSON evidence (no `--local` fallback). Plans 72-01..72-04 shipped all the code changes needed for Phase 72; the remaining work is operator-mediated:

## Required Operator Actions

1. **Push to main** (current branch is ahead of origin by 50+ commits — push when ready):
   ```bash
   git push origin main
   ```

2. **Confirm Railway deploys** the new backend with the Phase 72 schema extensions. Smoke-check `/api/health` shows `extractor_mode: "claude_primary"` (or equivalent).

3. **Trigger W17 + W18 backfill** via GitHub Actions:
   ```bash
   gh workflow run daily-sentiment.yml -f season=2025 -f week=17
   gh workflow run daily-sentiment.yml -f season=2025 -f week=18
   ```

4. **Run EVT-04 audit** (≥ 15/32 teams non-zero events) — script needs to be created per Plan 72-05:
   ```bash
   python scripts/audit_event_coverage.py \
     --base-url https://nfldataengineering-production.up.railway.app \
     --season 2025 --week 17 \
     --out .planning/phases/72-event-flag-expansion/audit/event_coverage_w17.json
   ```

5. **Run EVT-05 audit** (≥ 20 teams via advisor tools):
   ```bash
   python scripts/audit_advisor_tools.py \
     --base-url https://nfldataengineering-production.up.railway.app \
     --out-72 .planning/phases/72-event-flag-expansion/audit/advisor_tools_72.json
   ```

6. **Verify** both audit JSONs:
   - `base_url` contains `railway.app` (load-bearing tamper check)
   - EVT-04: ≥ 15 teams with at least one non-zero event from the 19-flag union
   - EVT-05: ≥ 20 teams returned non-empty content from `getPlayerNews` AND `getTeamSentiment`

7. **Commit** the audit JSONs:
   ```bash
   git add .planning/phases/72-event-flag-expansion/audit/
   git commit -m "test(72-05): EVT-04/EVT-05 audit evidence — Railway live"
   ```

8. **Write 72-SUMMARY.md** (phase-level) + run `node ./.claude/get-shit-done/bin/gsd-tools.cjs phase complete 72`.

## Code Status

All code work for Phase 72 is committed (Plans 72-01 through 72-04). What remains is operational evidence collection that depends on Railway being deployed and the backfill running — this is intentionally not automated by the autonomous runner.

## Why Checkpoint Now

The autonomous run prioritizes code completion across all v7.1 phases. Plan 72-05 audit gates are deferred to operator action so we can continue to Phase 73 (External Projections), Phase 74 (Sleeper League), Phase 75 (Tech Debt) without blocking on Railway deployment timing.

When ready, run `/gsd:execute-phase 72 --gaps-only` (or manually execute the steps above) to close out the EVT-04/EVT-05 gates.
