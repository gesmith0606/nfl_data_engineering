# Phase 69-01 Summary — Sentiment Backfill (Operational)

**Date:** 2026-04-24
**Status:** Code delivered; extraction blocked on external GitHub setup

## What landed

### Infrastructure fixes (2 commits)

| Commit | What | Why |
|--------|------|-----|
| `480b206` | Hardcode `--season 2026` for `refresh_rosters.py` in `daily-sentiment.yml` | Historical sentiment backfill (season=2025) was crashing refresh step: "No parquet files found in data/gold/projections/preseason/season=2025" |
| `f025d8c` | Add workflow-level `permissions: contents: write, issues: write` | Default GITHUB_TOKEN (read-only) blocked the commit-and-push step: "Permission to gesmith0606/nfl_data_engineering.git denied to github-actions[bot]" |

### Workflow runs triggered

- W17: 3 attempts (first 2 failed on the issues above, third succeeded: run 24870092995, 1m16s)
- W18: 1 attempt, succeeded (run 24870132439, 1m16s)

### Data produced

- Bronze: +9 new JSON files (pft, rotowire, rss, sleeper) committed to repo by GHA runner
- Silver signals (W17): 1 file, **2 signals** (thin — extraction fell back to RuleExtractor)
- Silver signals (W18): **0 files** — no player names matched + 1051 docs skipped as already-processed
- Gold aggregation: **no new files** — aggregator warning "No Silver signal files found for season=2025 week=18"

## Why extraction was thin

From W18 workflow logs:

```
03:08:57 [INFO] Daily Sentiment Pipeline | season=2025 week=18 | dry_run=False
03:09:06 [INFO] LLM enrichment: false
03:09:06 [INFO] Extraction complete: 1 processed, 1051 skipped, 0 failed, 0 signals [extractor=RuleExtractor]
03:09:06 [WARNING] PlayerNameResolver: no parquet files found under data/bronze
03:09:06 [WARNING] No Silver signal files found for season=2025 week=18
```

Three root causes (all external setup, not code):

1. **`secrets.ANTHROPIC_API_KEY` not set at repo level.** Workflow line 96 reads `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` — GitHub secrets are DISTINCT from Railway environment variables. Setting the key on Railway (2026-04-22) does NOT make it available to the GHA runner.
2. **`vars.ENABLE_LLM_ENRICHMENT` not set.** Workflow line 97 defaults to `'false'`, so the pipeline used `RuleExtractor` (keyword-based, thin) instead of `ClaudeExtractor`.
3. **Player Bronze parquet is gitignored.** The runner checks out the repo but `data/bronze/players/rosters/` etc. are in `.gitignore`. `PlayerNameResolver` can't match player names → even if Claude extraction ran, player_id resolution would fail.

## Remaining work (human_needed external setup)

The code side is done. To unblock actual extraction:

### Required
1. **Set GitHub Secret `ANTHROPIC_API_KEY`** at https://github.com/gesmith0606/nfl_data_engineering/settings/secrets/actions
   - Use the same `sk-ant-...` key that's on Railway (or generate a new one scoped to CI)
2. **Set GitHub Variable `ENABLE_LLM_ENRICHMENT=true`** at https://github.com/gesmith0606/nfl_data_engineering/settings/variables/actions
3. **Re-trigger** `gh workflow run daily-sentiment.yml -f season=2025 -f week=17` and W18

### Recommended (for real extraction quality)
4. **Decide on Bronze player parquet availability.** Options:
   - Commit Bronze player parquet to the repo (breaks `.gitignore` convention but makes CI self-sufficient)
   - Have the runner download from S3 before extraction (requires AWS creds as GHA secrets)
   - Accept thin extraction (only player names appearing in CFBD/Sleeper canonical payloads resolve)

## Phase 69 disposition

Routing to `human_needed` per Phase 68 VERIFICATION pattern:
- **Code delivery:** complete (2 workflow hotfixes committed, CONTEXT + PLAN artifacts preserved)
- **Extraction output:** blocked on GitHub UI setup (ANTHROPIC_API_KEY secret + ENABLE_LLM_ENRICHMENT variable)
- **Downstream impact:** Phase 70 (frontend empty states) is INDEPENDENT and can proceed in parallel. Once external setup lands + re-trigger runs, verify 69 by checking /api/news/team-events for ≥20/32 populated teams (SENT-02) and running `scripts/audit_advisor_tools.py --live` (SENT-05).

## Files modified (Phase 69)

- `.github/workflows/daily-sentiment.yml` — +15 lines (5 for season hardcode + fix comment, 10 for permissions block)
- `.planning/phases/69-sentiment-backfill/69-CONTEXT.md` — new
- `.planning/phases/69-sentiment-backfill/69-01-backfill-and-verify-PLAN.md` — new
- `.planning/phases/69-sentiment-backfill/69-01-SUMMARY.md` — this file
- `.planning/phases/69-sentiment-backfill/69-VERIFICATION.md` — next
