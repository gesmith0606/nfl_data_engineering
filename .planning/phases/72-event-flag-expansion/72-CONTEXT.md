# Phase 72: Event Flag Expansion + Non-Player Attribution - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend the sentiment event-flag vocabulary beyond injury/trade/usage/weather to cover the draft-season domain (rookie buzz, trade rumors, coaching changes, cap cuts, holdouts, drafted, rumored destinations). Decide how to attribute non-player subjects (coaches, reporters, teams) that Phase 71's Claude-primary extractor surfaces with `player_name: null` and a `team_abbr` hint. Plumb the expanded flags through the aggregator → API → frontend → advisor surface and prove coverage on a 2025 W17/W18 backfill.

</domain>

<decisions>
## Implementation Decisions

### New Event Flag Schema

- 7 new flags added to `PlayerSignal` (additive on existing dataclass — same pattern as the 12 existing flags): `is_drafted`, `is_rumored_destination`, `is_coaching_change`, `is_trade_buzz`, `is_holdout`, `is_cap_cut`, `is_rookie_buzz`. Each is `bool = False` default.
- `PlayerSignal.to_dict()` `events` sub-dict gets the 7 new keys.
- `EXTRACTION_PROMPT` in `src/sentiment/processing/extractor.py` extended to enumerate the new flags with brief one-liner definitions; the Claude system prefix is updated so the cached portion stays compact.
- VCR fixtures (`tests/fixtures/claude_responses/offseason_batch_w{17,18}.json`) re-recorded so signals include the new flags where applicable. The fixture `prompt_sha` updates because the prompt text changed.
- `RuleExtractor` gains minimal keyword patterns for the 7 new flags (e.g., regex `r"\bdrafted\s+(?:by|to)\s+the\s+\w+"` → `is_drafted`; `r"\b(?:trade rumor|rumored to be (?:traded|dealt|moved))"` → `is_trade_buzz`). Patterns target high-precision, low-recall — this path is the zero-cost dev fallback, not the primary producer.
- Frontend: extend `EventBadgeMap` (or equivalent) in `web/frontend/components/event-badges.tsx` (or wherever the 12 existing badges live) with 7 new entries — label + color + short description. No new pages, no new components.

### Non-Player Subject Attribution (EVT-02)

- **Hybrid routing.** The Claude extractor in Phase 71 already captures items with `player_name: null` and a `team_abbr` field into `data/silver/sentiment/non_player_pending/season=YYYY/week=WW/`. Phase 72 adds the routing pass:
  - **Coach OR team subjects** (Claude's response `subject_type: "coach"` or `"team"`) → roll up to `team_events` row using `team_abbr`. Counts surface as new `coach_news_count` and `team_news_count` on the team row.
  - **Reporter subjects** (`subject_type: "reporter"`) → emit to a new `data/silver/sentiment/non_player_news/season=YYYY/week=WW/` Silver path. Reporter byline + team-they-cover preserved.
- Claude prompt extended: each item gets an optional `subject_type: "player" | "coach" | "team" | "reporter"` field. Default `"player"` when absent (back-compat).
- Aggregator (`src/sentiment/aggregation/weekly.py`) no longer silent-drops `player_id: null` records:
  - Increments `null_player_count` on `PipelineResult` (already added in Phase 71).
  - Routes per the hybrid logic above.
- `PlayerNameResolver` is unchanged in Phase 72. Team-aware fuzzy resolution stays deferred to v7.2/v7.3.

### Backfill + Coverage Gates

- Backfill runs only 2025 W17 + W18 — same fixture/data window as the Phase 71 benchmark. Future weeks come naturally via daily cron.
- New script `scripts/audit_event_coverage.py` (mirrors `scripts/audit_advisor_tools.py` pattern) hits `/api/news/team-events` against a target host (default Railway), counts teams with at least one non-zero flag from the 19-flag union (12 existing + 7 new), and emits JSON. EVT-04 gate: ≥ 15 of 32 teams.
- `scripts/audit_advisor_tools.py` extended (or sibling new script) asserts `getPlayerNews` and `getTeamSentiment` return non-empty content for ≥ 20 teams against Railway live. EVT-05 gate.
- Ship-or-skip gate: phase merges only when the audit JSON files are committed showing both gates passed against Railway live. The `ENABLE_LLM_ENRICHMENT=true` GitHub Variable is the operator-controlled rollout switch (already set in Phase 71).

### API + Frontend Integration

- Pydantic models (`web/api/models/schemas.py`):
  - `NewsItem.event_flags` dict gets 7 new keys (Pydantic `Field` with default `False`).
  - `NewsItem` gains optional `subject_type: Optional[Literal["player", "coach", "team", "reporter"]] = "player"` and `team_abbr: Optional[str] = None`.
  - `TeamEvents` gains optional `coach_news_count: int = 0`, `team_news_count: int = 0`, `staff_news_count: int = 0`.
- `web/api/services/news_service.py` reads expanded flags from Silver and projects them into the response shape.
- `web/api/routers/news.py` endpoints stay structurally identical — additive fields only, no breaking changes.
- Advisor tools (`getPlayerNews`, `getTeamSentiment`) return expanded payload transparently. Tool descriptions in the advisor prompt updated to enumerate the new flags so the model knows what to surface to the user.
- Daily cron (`.github/workflows/daily-sentiment.yml`) is untouched. The new flags ride the existing daily extraction; no schedule or env changes.

### Claude's Discretion

- Exact regex patterns and confidence-cap values for `RuleExtractor` keyword paths.
- Specific UI badge color hex values — pick from existing design tokens; if a new hue is needed, reuse the closest match in `web/frontend/lib/design-tokens.ts`.
- Internal helper function names (e.g., `_route_non_player_item`, `_compute_team_rollup`) — pick what reads naturally.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/sentiment/processing/extractor.py` — `PlayerSignal` dataclass (Phase 71 extended with `summary`, `source_excerpt`, `team_abbr`, `extractor`); `EXTRACTION_PROMPT` template; `_VALID_CATEGORIES`, `_EVENT_FLAG_KEYS`. New flags slot into the existing structure.
- `src/sentiment/processing/rule_extractor.py` — keyword-pattern fallback path; new patterns added alongside existing 12 flag patterns.
- `src/sentiment/processing/pipeline.py` — `SentimentPipeline._run_claude_primary_loop` (Phase 71) writes `non_player_pending/` Silver sink; Phase 72 adds the routing pass that consumes it.
- `src/sentiment/aggregation/weekly.py` — `WeeklyAggregator.aggregate(season, week)` reads Silver signals; extend to handle non-player records.
- `src/sentiment/aggregation/team_weekly.py` — likely the home for team-level rollup logic; extend rather than create new.
- `web/api/models/schemas.py` — Pydantic schemas for NewsItem, TeamEvents, etc. Additive field changes.
- `web/api/services/news_service.py` — Silver/Gold readers; extend to project new flags.
- `web/frontend/components/` — find existing badge component, extend EventBadgeMap.
- `tests/fixtures/claude_responses/` — re-record fixtures with new flags via Claude (or hand-author one signal per new flag for completeness).

### Established Patterns
- Additive Silver schema (extractor field, then 7 new event flags) — never rename or drop.
- Bronze immutability — no writes to `data/bronze/` from this phase.
- Pydantic models default-False / default-empty for new fields to keep frontend back-compat.
- Audit scripts emit JSON; one row per gate; commit to phase SUMMARY.
- D-06 fail-open: every ingestor / aggregator handles missing data gracefully.

### Integration Points
- `_run_claude_primary_loop` → reads `non_player_pending/`, calls new `_route_non_player_items` helper.
- `WeeklyAggregator` → calls `_route_non_player_items` and emits to `team_events` rows + new `non_player_news/` Silver path.
- `news_service.get_team_events()` → returns team rows with new count fields.
- `news_service.get_player_news()` → news items now include `subject_type` and `team_abbr` fields when applicable.
- Frontend `news-feed.tsx` + `player-news-panel.tsx` → render expanded badge map.
- Advisor system prompt → updated tool descriptions enumerate new flags.

</code_context>

<specifics>
## Specific Ideas

- The `subject_type` enum stays small (4 values) to keep prompt token cost minimal. Adding a 5th value (e.g., "agent" for player-agent quotes) is a v7.2+ decision.
- Reporter subjects often have multiple team affiliations (e.g., Schefter covers all teams). The `non_player_news` channel records `subject_team` (team they cover for THIS article) rather than a fixed affiliation, so a single reporter can route to different teams across docs.
- Team rollup `coach_news_count` includes all `subject_type ∈ {coach, team}` items. `staff_news_count` is a separate count for any future GM/exec items not modeled yet — populated as 0 for Phase 72 (placeholder).
- The audit scripts hit Railway by default; pass `--local` to run against `localhost:8000` for local validation.

</specifics>

<deferred>
## Deferred Ideas

- Player-agent attribution channel — defer to v7.2 once we see how often agents drive stories.
- Team-aware PlayerNameResolver (resolve "Mahomes" to KC's Mahomes vs other Mahomes) — defer to v7.2/v7.3.
- New `getDraftBuzz` advisor tool — premature; validate the flags first via existing `getPlayerNews` / `getTeamSentiment`.
- Reporter byline disambiguation across multiple syndicated outlets — defer.
- Historical backfill beyond W17/W18 — defer until daily cron has accumulated enough offseason content to make a 4-week+ window meaningful.

</deferred>
