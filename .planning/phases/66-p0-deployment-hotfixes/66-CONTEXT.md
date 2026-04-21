# Phase 66: P0 Deployment Hotfixes - Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous)

<domain>
## Phase Boundary

Restore all 4 partially/fully-broken dashboard routes in production within a day by fixing three distinct layers: environment configuration (ANTHROPIC_API_KEY on Railway), Docker image contents (bundle `data/bronze/schedules/` and `data/bronze/players/rosters/`), and request hygiene on both the backend (graceful defaulting for missing query params) and the frontend (resolve latest-played-week instead of hardcoded defaults).

Critical path: this phase unblocks Phase 69 (needs API key + Docker data) and Phase 70 (needs backend to stop 422-ing). Phases 67 and 68 run in parallel.

</domain>

<decisions>
## Implementation Decisions

### Backend Graceful Defaulting
- `/api/predictions` with no params → auto-resolve to latest-played-week (reuse Phase 63 advisor pattern via `/api/projections/latest-week` helper or equivalent service-level lookup)
- `/api/lineups` with no params → latest-week resolution + empty team returns list of available teams in the payload (not 400/422)
- `/api/teams/{team}/roster` with no season/week → latest-week default (extends 64-02 offseason fallback pattern)
- All 3 endpoints add `data_as_of` meta field to response envelope, matching Phase 63 pattern on `/api/projections`

### Frontend Week-Defaulting
- Predictions and lineups pages call `/api/projections/latest-week` on mount to resolve default season/week (replaces hardcoded `season=2024, week=1` in `prediction-cards.tsx` and `season=2026, week=1` in `lineup-view.tsx`)
- URL state bound via **nuqs** (bookmarkable, matches repo convention used on projections page)
- Initial render while latest-week resolves uses existing Suspense skeleton pattern (already wrapping `<PredictionCardGrid />`)
- Lineups team filter defaults to empty with a "Select a team" CTA — preserves user intent rather than picking arbitrarily

### Docker + Deployment
- Bundle `data/bronze/schedules/` and `data/bronze/players/rosters/` into the Railway image — minimum to fix HOTFIX-02/03 503s; no other Bronze data types added (injuries/NGS/snap_counts deferred until needed)
- Cache busting: bump existing `ARG CACHE_BUST=2026-04-19-01` to `2026-04-21-01` (matches existing date-NN convention from line 5 of `web/Dockerfile`)
- Daily image staleness: explicitly deferred to Phase 67 (roster refresh v2) — don't duplicate daily rebuild logic here
- ANTHROPIC_API_KEY verification: add `llm_enrichment_ready: bool` flag to `/api/health` response (returns `bool(os.environ.get('ANTHROPIC_API_KEY'))` — never logs or returns the key itself). User sets env var in Railway dashboard, then `curl /api/health` confirms; manual browser smoke on predictions/lineups/news pages as the final acceptance check

### Claude's Discretion
- Exact location of latest-week resolution helper on backend (could extend existing `/api/projections/latest-week` service, could add a shared `services/default_resolver.py`, could be inline per router — whichever best matches existing code organization)
- Specific nuqs parser shape for season/week on predictions/lineups pages (whichever matches the projections-page precedent)
- Whether to add a one-off post-deploy smoke script in this phase or defer entirely to Phase 68's sanity-check v2 (lean toward defer — 68 is the structural fix)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `/api/projections/latest-week` endpoint (Phase 63-04) — source of truth for current season/week; returns `{season, week}` or `null`
- `resolveDefaultWeek()` helper on frontend side (Phase 63-04 pattern) — already returns `null` distinctly from `{week: null}` so advisor can distinguish "no data" from "backend unreachable"
- `meta.data_as_of` on `ProjectionResponse` — extended from Phase 63; pattern ready to copy to predictions/lineups/roster responses
- `predictionsQueryOptions` / `lineupQueryOptions` in `web/frontend/src/features/nfl/api/queries.ts` — both already retry-aware; swap hardcoded defaults for latest-week resolution
- `team_roster_service.py` (Phase 64-02) — single parquet reader for `teams/*` namespace; can accept a latest-week default

### Established Patterns
- React Query + nuqs for URL params + server state (predictions page already uses Query; need to add nuqs for season/week bindings)
- Suspense skeleton wrapping card grids — already on `<PredictionCardGrid />`
- `data_as_of` meta on Gold responses as the upstream traceability signal (Phase 63-04 decision)
- Docker `CACHE_BUST` ARG pattern — line 5 of `web/Dockerfile`, dated format `YYYY-MM-DD-NN`
- D-06 graceful-failure from Phase 61 — empty envelopes (200 + empty list) preferred over 404/422 when offseason/no-data

### Integration Points
- `web/Dockerfile` lines 24-33 — COPY block for data; add two new lines for schedules and players/rosters
- `web/api/routers/predictions.py` + `lineups.py` + `teams.py` — accept optional season/week, resolve via helper when missing
- `web/api/routers/health.py` (or equivalent) — extend response with `llm_enrichment_ready`
- `web/frontend/src/features/nfl/components/prediction-cards.tsx:170-171` — replace `useState(2024)` and `useState(1)` with nuqs-bound defaults resolved from latest-week
- `web/frontend/src/features/nfl/components/lineup-view.tsx:20-21` — same replacement for `useState(2026)` and `useState(1)`

</code_context>

<specifics>
## Specific Ideas

- Kyler Murray is mentioned in the v7.0 audit but is Phase 67's acceptance canary, not this one — do not touch roster refresh here
- The existing 2026-04-19 CACHE_BUST bump was done for the same reason (force Railway to re-run COPY layers on stale cache); use the same trick with today's date
- Phase 66 must not depend on ANTHROPIC_API_KEY landing to be verifiable — only HOTFIX-01 verification needs it; the Docker/params fixes stand alone

</specifics>

<deferred>
## Deferred Ideas

- Daily image rebuild via GHA — deferred to Phase 67 (roster refresh v2 will handle data-freshness cadence)
- Post-deploy blocking smoke + rollback — structurally Phase 68's scope (sanity-check v2)
- Additional Bronze data types (injuries, NGS, snap_counts) in Docker — re-evaluate after Phase 67's refresh strategy is in place

</deferred>
