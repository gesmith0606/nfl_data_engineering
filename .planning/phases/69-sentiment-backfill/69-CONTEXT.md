# Phase 69: Sentiment Backfill - Context

**Gathered:** 2026-04-23
**Status:** Ready for planning
**Mode:** Operational (run existing extractor with concrete parameters)

<domain>
## Phase Boundary

Run the Phase 61 news extractor against accumulated Bronze records so `event_flags`, `sentiment`, `player_id`, and `summary` populate on `/api/news/team-events` and `/api/news/feed`. The extractor code already exists and is deployed on Railway. This phase is fundamentally an **operational run + verification** — it does not add new extraction logic.

Scope: 2025 weeks 17 + 18 (current + most-recent). Full-season backfill deferred as diminishing returns (pre-season Bronze content has low relevance to current projections).

Out of scope: extractor code changes, website UI changes (that's Phase 70), Bronze ingestion changes.

</domain>

<decisions>
## Implementation Decisions

### Run Location (SENT-01)
- Backfill runs **on Railway** via `gh workflow run daily-sentiment.yml` (workflow_dispatch with `-f season=2025 -f week=N`)
- Uses Railway's `ANTHROPIC_API_KEY` (set 2026-04-22 by user)
- No local secret setup required; no local API cost
- Each workflow run processes one week; loop over weeks 17 and 18

### Backfill Scope (SENT-01, SENT-02)
- **2025 W17 + W18 only** (not full season)
- Rationale: focuses on what users see on the website NOW; ~18 source Bronze files total; ~$0.50 Haiku cost
- Meets SENT-02 (≥20 of 32 teams with `total_articles > 0`) because current-week news has broader team coverage than pre-season

### Verification Approach (SENT-02, SENT-03, SENT-05)
- Post-backfill: `curl` Railway `/api/news/team-events` and `/api/news/feed` — assert content populated
- Re-run `scripts/audit_advisor_tools.py` against Railway — assert `getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, `getSentimentSummary` flip from WARN → PASS
- Re-run `scripts/sanity_check_projections.py --check-live <railway-url>` — Phase 68 gate asserts team-events content and extractor freshness; if it passes, SENT-01/02 are live-verified

### Idempotency
- `process_sentiment.py` uses `data/silver/sentiment/processed_ids.json` to skip already-extracted Bronze docs
- Re-running the workflow against already-processed weeks is safe; it will be a no-op for records already in Silver

### Claude's Discretion
- Whether to open a throwaway PR or commit Silver/Gold parquet directly is at Claude's discretion — Railway picks up via Parquet fallback regardless
- Timing of canary verification (sleep after workflow_dispatch) — choose reasonable bound (~5 min workflow wall time plus Railway cache)
- If SENT-02 threshold (≥20 of 32 teams) is missed after W17+W18 extraction, follow-up is out of scope for this phase — document as gap

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/process_sentiment.py` — CLI (already deployed): `--season --week [--dry-run --skip-extraction --skip-team --verbose]`
- `.github/workflows/daily-sentiment.yml` — `workflow_dispatch` accepts `-f season=Y -f week=W`; Phase 67 hardened this (no silent `|| echo`)
- `scripts/audit_advisor_tools.py` — probes 12 AI advisor tools against Railway; Phase 63 reported 4 news tools as WARN due to empty extraction
- `data/bronze/sentiment/{pft,reddit,rotowire,rss,sleeper}/season=2025/` — accumulated Bronze awaiting extraction
- `src/sentiment/processing/extractor.py` — Claude Haiku extraction; guarded for API key absence
- `src/sentiment/processing/pipeline.py` — Bronze → Silver orchestration
- `src/sentiment/aggregation/weekly.py` — Silver → Gold weekly aggregation

### Established Patterns
- Workflow triggers via `gh` CLI — auth already configured in the repo
- Post-workflow wait: `gh run watch $(gh run list --workflow=daily-sentiment.yml --limit 1 --json databaseId --jq '.[0].databaseId')` blocks until complete
- Railway Parquet fallback reads from committed `data/silver/sentiment/` and `data/gold/sentiment/` — no database needed
- Phase 68 `scripts/sanity_check_projections.py --check-live` is the authoritative post-backfill validator

### Integration Points
- Phase 68 gate consumes extraction freshness + team-events content (this phase produces both)
- Website news page (Phase 61 UI) reads `/api/news/team-events` and `/api/news/feed` (depends on this phase's output)
- AI advisor's 4 news tools (Phase 63) should flip WARN → PASS once extraction completes

</code_context>

<specifics>
## Specific Ideas

- The Phase 68 live gate (`--check-live`) is the definitive pass/fail signal for this phase's SENT-02 and SENT-04 criteria — if it passes against Railway post-backfill, phase is effectively verified for those criteria
- `scripts/audit_advisor_tools.py` is the canonical SENT-05 gate — it already exists and was the reason this was reported as a regression on 2026-04-20

</specifics>

<deferred>
## Deferred Ideas

- Full 2025 season backfill (weeks 1-16) — diminishing returns; deferred to v7.1 if needed
- Automated retry-on-failure for extraction runs — current workflow is fail-loud (Phase 67); manual re-trigger is acceptable for operational phase
- Sentiment quality audit (spot-check a sample of extracted `event_flags` for Claude Haiku accuracy) — deferred to a future observability phase

</deferred>
