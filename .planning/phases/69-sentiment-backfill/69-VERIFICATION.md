---
phase: 69
phase_name: Sentiment Backfill
status: human_needed
verified: 2026-04-24
must_haves_total: 5
must_haves_verified: 0
human_verification:
  - criterion: SENT-01
    description: "Set GitHub Secret ANTHROPIC_API_KEY + GitHub Variable ENABLE_LLM_ENRICHMENT=true, then re-trigger daily-sentiment.yml for W17 + W18"
    location: "https://github.com/gesmith0606/nfl_data_engineering/settings/secrets/actions AND .../settings/variables/actions"
  - criterion: SENT-02
    description: "After (1), verify /api/news/team-events returns total_articles > 0 for ≥20 of 32 teams"
    check: "curl https://nfldataengineering-production.up.railway.app/api/news/team-events"
  - criterion: SENT-03
    description: "After (1), verify /api/news/feed returns populated sentiment/event_flags/player_id/summary"
    check: "curl 'https://nfldataengineering-production.up.railway.app/api/news/feed?season=2025&week=18'"
  - criterion: SENT-04
    description: "After (1-3), visit https://frontend-jet-seven-33.vercel.app/news and confirm real headline text renders (not dangling sentiment numbers)"
  - criterion: SENT-05
    description: "After (1), run scripts/audit_advisor_tools.py against Railway — confirm getNewsFeed/getPlayerNews/getTeamSentiment/getSentimentSummary flip WARN → PASS"
commits:
  - 480b206  # hardcode refresh_rosters season=2026
  - f025d8c  # add contents:write + issues:write permissions
---

# Phase 69 Verification — Sentiment Backfill

## Overall Status: `human_needed`

All 5 SENT requirements are **blocked on external GitHub UI setup**, not on code. The Phase 69 CODE delivery is complete (2 workflow hotfixes + plan/context artifacts). Extraction output — and thus the live verification path — requires:

1. GitHub repository Secret: `ANTHROPIC_API_KEY = sk-ant-...` (same key pattern as Railway env var; they are DISTINCT scopes)
2. GitHub repository Variable: `ENABLE_LLM_ENRICHMENT = true`
3. Re-trigger the two workflow runs for W17 + W18
4. Run verification curls + `audit_advisor_tools.py`

Detailed analysis in `69-01-SUMMARY.md`.

## Evidence

- Workflow runs succeeded cleanly: 24870092995 (W17, 1m16s), 24870132439 (W18, 1m16s)
- Infrastructure gaps (refresh_rosters season coupling; workflow permissions) resolved and pushed
- Extraction produced only 2 thin signals for W17 and 0 signals for W18 due to `ENABLE_LLM_ENRICHMENT=false` fallback to RuleExtractor + absent Player Bronze parquet on the runner

## What the gate would say

If `scripts/sanity_check_projections.py --check-live` runs against Railway right now:
- `_check_extractor_freshness`: CRITICAL (latest Silver sentiment is 6+ months stale — pre-2025 data; no W17/W18 Silver parquet produced since aggregator wrote no files)
- `_validate_team_events_content`: CRITICAL (< 17 of 32 teams populated — extraction was thin)

This is the EXPECTED state for `human_needed` — the Phase 68 gate is doing its job by surfacing these as CRITICAL rather than silently passing.

## Closure path

Once the two GitHub UI settings are applied and workflows re-triggered, re-run the Phase 68 live gate. If it passes, flip this VERIFICATION to `passed`.

Phase 70 (frontend empty states) is independent and proceeds while this waits on external setup.
