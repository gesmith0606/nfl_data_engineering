# v7.1 Draft Season Readiness — Requirements

**Milestone:** v7.1
**Created:** 2026-04-24
**Goal:** Deliver draft-season-critical features — LLM-primary sentiment extraction (so offseason news produces real signals), external projections comparison (ESPN/Sleeper/Yahoo side-by-side), Sleeper league integration (personalized rosters + advisor), and v7.0 tech debt cleanup — before fantasy draft season opens.

---

## LLM-Primary Extraction (LLM)

Replace the rule-primary / LLM-enrichment architecture from Phase 61 with LLM-primary extraction that produces signals from offseason content (drafts, trades, coaching changes) — not just in-season injury/trade keyword patterns.

- [ ] **LLM-01**: `ClaudeExtractor` class exists in `src/sentiment/processing/extractor.py` as a peer to `RuleExtractor`, producing structured `{player_name, event_type, sentiment_score, summary, event_flags}` signals from raw Bronze docs (not enrichment of pre-existing rule signals)
- [ ] **LLM-02**: Pipeline orchestrator routes to Claude-primary when `ENABLE_LLM_ENRICHMENT=true`; falls back to `RuleExtractor` when false (zero-cost operation preserved for dev + when API is unreachable)
- [x] **LLM-03**: Claude extraction produces ≥ 5× more signals than rule-based on identical Bronze batch for offseason content (W17/W18 2025 as benchmark). Measured delta committed to a summary doc. — Plan 71-03 ratio=5.57x; gate test in tests/sentiment/test_extractor_benchmark.py
- [x] **LLM-04**: Cost management: batch 5-10 docs per Claude call via prompt caching for the player list; target < $5/week at daily-cron cadence (80 docs/day average); tracked via a cost-log file or Anthropic console screenshot in SUMMARY.md — Plan 71-03 CostLog Parquet sink + HAIKU_4_5_RATES + per-call CostRecord shipped (BATCH_SIZE=8 + cache_control=ephemeral on system prefix + ACTIVE PLAYERS roster block)
- [x] **LLM-05**: Existing rule-extraction test coverage preserved; new Claude-extraction tests use recorded fixtures (VCR-style), not live API calls — deterministic CI — Plan 71-02 FakeClaudeClient + Plan 71-03 ClaudeExtractor DI seam consumed by all 14 batched extractor tests + 1 benchmark test; zero live API calls in CI

## Event Flag Expansion + Non-Player Attribution (EVT)

Extend `event_flags` beyond injury/trade/usage to cover draft-season content, and decide how to handle non-player subjects (coaches, reporters, teams) that the Phase 69 backfill run surfaced as `player_id: null` rejects.

- [ ] **EVT-01**: New event flags added — `is_drafted`, `is_rumored_destination`, `is_coaching_change`, `is_trade_buzz`, `is_holdout`, `is_cap_cut`, `is_rookie_buzz`. All have schema definitions in `src/sentiment/models/` and are emitted by ClaudeExtractor.
- [ ] **EVT-02**: Non-player subjects (coaches, reporters, teams) are either (a) attributed to their team, rolling up to `team_events` rows, OR (b) routed to a new `non_player_news` Silver signal channel — decision captured in CONTEXT.md with rationale.
- [ ] **EVT-03**: Weekly aggregator (`src/sentiment/aggregation/weekly.py`) no longer silently drops `player_id: null` records — either attributes them per EVT-02 or increments a tracked `null_player_count` metric for each batch.
- [ ] **EVT-04**: `/api/news/team-events` populates `event_flags` correctly from the expanded set during offseason; ≥ 15 of 32 teams have at least one non-zero event category on a freshly-backfilled W17+W18 run.
- [ ] **EVT-05**: Advisor news tools (`getPlayerNews`, `getTeamSentiment`) return non-empty results for ≥ 20 teams on the expanded event set.

## External Projections Comparison (EXTP)

Show ESPN, Sleeper, and Yahoo projections side-by-side with the project's Gold projections on the projections page — surfaces comparison value and stress-tests user-facing transparency.

- [ ] **EXTP-01**: `scripts/fetch_external_projections.py` pulls weekly projections from ESPN + Sleeper APIs (Yahoo via scraping if no API), stores to `data/bronze/external_projections/{source}/season=YYYY/week=WW/` per the S3 key convention
- [ ] **EXTP-02**: Silver layer at `data/silver/external_projections/` merges all 4 sources (ours + 3 external) per player-week with column schema `{player_id, source, projected_points, scoring_format}`
- [ ] **EXTP-03**: New `/api/projections/comparison?season=Y&week=W&scoring=F` endpoint returns all 4 sources for each player in the same shape
- [ ] **EXTP-04**: Frontend projections page renders comparison table (columns: Ours / ESPN / Sleeper / Yahoo), with delta column and filter by position
- [ ] **EXTP-05**: Cron-refresh (daily or on-deploy) keeps external data current; staleness surfaced via `data_as_of` chip (Phase 70 pattern)

## Sleeper League Integration (SLEEP)

Let users connect their Sleeper account to import rosters and get personalized advice from the AI advisor.

- [ ] **SLEEP-01**: OAuth / username-based authentication flow on the frontend — user enters Sleeper username, backend resolves leagues + rosters via Sleeper API (already MCP-wired)
- [ ] **SLEEP-02**: User rosters cached in session (or persisted per-user if auth sticks) and surfaced on a new `/leagues` route with league selector + roster view
- [ ] **SLEEP-03**: Advisor AI gains new tool `getUserRoster({league_id})` returning the user's current lineup + bench; existing 12 tools work against user-scoped context when applicable
- [ ] **SLEEP-04**: Start/sit recommendations on the advisor use the user's actual roster (not a hypothetical league) when SLEEP authentication is active

## v7.0 Tech Debt Cleanup (TD)

Clear the 8 items rolled forward from v7.0 audit.

- [ ] **TD-01**: Remove `git commit --amend --no-verify` from auto-rollback (replace with single revert commit using desired message via `-m` on initial revert). Update `test_auto_rollback_pushes_non_force` to assert `--no-verify` absence.
- [ ] **TD-02**: Carve `web/frontend/**/*.json` out of the repo-root `*.json` gitignore so `package.json` + `tsconfig.json` + `package-lock.json` + `vitest.config.ts` ship via git. CI + fresh clones get vitest deps.
- [ ] **TD-03**: Replace hardcoded `--season 2026` in `daily-sentiment.yml` roster refresh step with `$(date +%Y)` or equivalent auto-detection.
- [ ] **TD-04**: Consolidate duplicate `relativeTime()` in `news-feed.tsx` + `player-news-panel.tsx` — both import `formatRelativeTime` from `@/lib/format-relative-time`.
- [ ] **TD-05**: Add upstream guard so `formatRelativeTime("")` doesn't produce "Updated unknown" — either trim-before-truthy-check in `EmptyState.tsx` or early-return in the helper.
- [ ] **TD-06**: Remove redundant `LAR` from `VALID_NFL_TEAMS` (keep `LA` per nflverse convention).
- [ ] **TD-07**: Structural test `test_auto_rollback_pushes_non_force` adds `assert "--no-verify" not in steps_yaml` guard (ties to TD-01).
- [ ] **TD-08**: Document in CLAUDE.md that `data/bronze/players/rosters/` and `data/bronze/depth_charts/` are now version-controlled (committed 2026-04-24) — prevents future confusion about ingestion destination.

---

## Traceability Table

| Requirement | Phase | Status |
|-------------|-------|--------|
| LLM-01..05  | 71    | LLM-03 ✓ / LLM-04 ✓ / LLM-05 ✓ ; LLM-01, LLM-02 Pending (Plan 71-04) |
| EVT-01..05  | 72    | Pending |
| EXTP-01..05 | 73    | Pending |
| SLEEP-01..04 | 74   | Pending |
| TD-01..08   | 75    | Pending |

**Coverage:**
- v7.1 requirements: 27 total
- Mapped to phases: 27 (100%)
- Orphans: 0

## Out of Scope (Deferred)

- PFF paid data integration — v8.0
- Neo4j Aura cloud graph setup — v8.0
- Content pipeline (Remotion, NotebookLM podcast, social video) — v7.2
- Heuristic consolidation (3 duplicate projection functions) — v7.3
- Multi-user auth with persistence (beyond session) — v7.2 or v7.3
- Real-time Sleeper WebSocket for live draft — future
