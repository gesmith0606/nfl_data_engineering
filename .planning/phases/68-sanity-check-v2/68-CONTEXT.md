# Phase 68: Sanity-Check v2 - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Rebuild the Phase 60 quality gate (`scripts/sanity_check_projections.py` + `.github/workflows/deploy-web.yml`) so the 6 regressions found in the 2026-04-20 user audit would all have been caught before shipping. This phase delivers a structural fix to the meta-issue: the gate that previously exited 0 must now fail loudly on roster drift, broken endpoints, empty-content payloads, stalled extractors, and missing API keys. Includes promoting `--check-live` and post-deploy smoke to **blocking** GHA steps with automatic rollback. Absorbs the deferred DQAL-03 cleanup items (negative-projection clamp, 2025 rookie ingestion presence, rank-gap threshold) as additional gate assertions.

This phase **does not** change frontend behavior, ingest new data sources, or modify the news extractor itself (Phase 69). It is purely the verification layer.

</domain>

<decisions>
## Implementation Decisions

### Rollback Mechanism (SANITY-09)
- Auto-rollback: **GitHub Actions revert + push**. On blocking `--check-live` failure within 5 min of deploy, GHA step runs `git revert --no-edit HEAD && git push`. Railway auto-redeploys the previous green commit. Auditable via git log.
- Trigger: post-deploy `--check-live` blocking step exits non-zero within 5 min of deploy
- Revert commit message format: `revert: auto-rollback after sanity-check failure on <sha>` for traceability

### Sampling Scope (SANITY-03 + SANITY-05)
- Roster drift (SANITY-05): **Top-50 players by 2025 PPR projected points** (read from latest Gold projections parquet). Fail with CRITICAL severity on team mismatch vs Sleeper canonical.
- Endpoint sampling (SANITY-03): **Top-10 teams by 2025 W18 snap count** (read from Silver team metrics). Probe `/api/teams/{team}/roster` for each.
- Both samples expected to complete within 30 seconds total probe time.

### Gate Severity & Exit Codes
- CRITICAL findings: exit 2 (blocks deploy)
- WARNING findings: exit 1 (annotates but does not block) — reserved for thresholds-near-edge
- Roster drift mismatches always CRITICAL; empty `event_flags` is WARNING if news has not yet accumulated for that team, CRITICAL if accumulated > 24h ago

### Extractor Freshness Window (SANITY-06)
- Latest Silver sentiment timestamp must be within **48 hours** of gate run
- Stale > 48h: CRITICAL
- Stale > 24h but < 48h: WARNING

### News Content Threshold (SANITY-04)
- Pre-existing v1 check: `len(payload) == 32` (passes empty)
- New v2 check: at least **20 of 32 teams** have `total_articles > 0` when news has accumulated for current season ≥ 3 days. Below 20: CRITICAL.
- Rationale: matches Phase 69 SENT-01 success criterion exactly.

### DQAL-03 Carry-Over Assertions (SANITY-10)
- Negative projection clamp: assert no player has `projected_points < 0` in latest Gold projections parquet
- 2025 rookie ingestion: assert at least 50 rookies present in `data/bronze/players/rookies/season=2025/`
- Rank-gap threshold: assert no consecutive ranking gap > 25 positions in latest external rankings (FantasyPros/Sleeper)

### Claude's Discretion
- Test fixtures: use real production parquet snapshots (already present in `data/`) rather than synthetic mocks for end-to-end gate tests
- Code structure: extend existing `scripts/sanity_check_projections.py` (1211 lines) rather than create a new file — preserves existing argument parsing and CI integration
- Logging: use Python `logging` (not print) with WARNING/ERROR/CRITICAL levels mapping to gate severity
- All grey areas not surfaced above are at Claude's discretion

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `scripts/sanity_check_projections.py` (1211 lines) — main gate script; has `run_sanity_check()`, `run_live_site_check()`, `run_prediction_check()`, `_load_our_projections()`, `_match_players()`, `fetch_live_consensus()`, argparse with `--check-live` flag (line 1109)
- `src/utils.py` — `download_latest_parquet()` for S3 / local parquet reads
- `web/api/services/team_roster_service.py` — already has Sleeper API client patterns from Phase 67
- `data/bronze/players/rosters_live/` — daily-cron-written live roster source of truth (Phase 67)
- `data/gold/projections/` — top-N player ranking source by PPR projected points

### Established Patterns
- CLI scripts use `argparse` with `--season`, `--week`, `--scoring` flags
- All script outputs use color-coded stdout (`✓` green, `⚠` yellow, `✗` red) via existing helpers
- GHA workflows in `.github/workflows/` use `python -m pytest` and `python scripts/...` invocations
- Sleeper API access: `requests.get('https://api.sleeper.app/v1/players/nfl')` — cache locally per-day to avoid rate limits

### Integration Points
- `.github/workflows/deploy-web.yml` — currently runs `--check-live` post-deploy as annotation-only; Phase 68 promotes to blocking
- `.github/workflows/daily-sentiment.yml` — Phase 67 hardened this; Phase 68 adds extractor-freshness assertion
- `web/api/main.py` — Phase 66 added `llm_enrichment_ready` flag to `/api/health`; Phase 68 reads this in `--check-live`

</code_context>

<specifics>
## Specific Ideas

- The Kyler Murray case is the canary: if the v2 gate is run against the pre-v7.0 production state, it MUST exit non-zero with a finding mentioning "Kyler Murray" or "ARI roster drift" (whichever name is in the audit log). This is success criterion #1 for the phase.
- Rollback must produce a commit visible in `git log --oneline | head -5` so the user can see "auto-rollback" entries when reviewing history.
- Probe timeouts should be aggressive (5s per endpoint) — slow Railway response is itself a signal worth surfacing.

</specifics>

<deferred>
## Deferred Ideas

- Synthetic uptime monitoring loop (poll every 5 min for 30 min post-deploy) — out of scope; covered adequately by single post-deploy check
- Slack/Discord alerting on rollback — out of scope; GHA UI notifications + git log are sufficient for solo ops
- Automated "next-version" suggestion when rollback occurs — out of scope; user manually triages

</deferred>
