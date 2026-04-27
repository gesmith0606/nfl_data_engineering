# Phase 73: External Projections Comparison - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Show ESPN + Sleeper + Yahoo (or FantasyPros consensus proxy) weekly projections side-by-side with our Gold projections on the projections page. Users compare; we show transparency. Adds Bronze ingestion (3 sources), Silver merged schema (4 sources), new `/api/projections/comparison` endpoint, frontend table extension with delta column, and GHA refresh cron.

</domain>

<decisions>
## Implementation Decisions

### Data Sources

- **Sleeper**: existing MCP — `mcp__sleeper__*` tools already wired. Use existing MCP-based fetch path; no new HTTP code.

  **D-01 clarification (post-implementation, 2026-04-26):** D-01 ("no direct `requests` calls") applies ONLY to Sleeper public-API traffic. The `src/sleeper_http.py` chokepoint exists because Sleeper has rate limits + occasional 5xx + future MCP migration considerations specific to that one provider. ESPN and Yahoo (FantasyPros) ingesters use `requests` directly — they have no shared rate-limit ceiling, no centralized retry policy, and no future migration target. Only the Sleeper script is structurally tested for `import requests` absence.
- **ESPN**: public fantasy projections API at `fantasy.espn.com/apis/v3/games/ffl/seasons/{year}/segments/0/leagues/0?view=mPlayer&view=kona_player_info` (no auth needed for league=0 public projections). Implement as new ingester `scripts/ingest_external_projections_espn.py`.
- **Yahoo**: FantasyPros consensus rankings (free, no OAuth) used as proxy for Yahoo's projections. The FantasyPros consensus aggregates ESPN/Yahoo/CBS/RotoWire — provides a reasonable Yahoo signal until the real Yahoo OAuth is implemented (deferred to v8.0). New ingester `scripts/ingest_external_projections_yahoo.py` with module-level constant `_SOURCE_LABEL = "yahoo_proxy_fp"` so users can see provenance.

### Bronze + Silver Storage

- Bronze path: `data/bronze/external_projections/{source}/season=YYYY/week=WW/{source}_YYYYMMDD_HHMMSS.parquet` per S3 key convention.
- Silver merged path: `data/silver/external_projections/season=YYYY/week=WW/external_projections_YYYYMMDD_HHMMSS.parquet`.
- Silver schema (long format): `{player_id, player_name, position, team, source, scoring_format, projected_points, projected_at}` where `source ∈ {"ours", "espn", "sleeper", "yahoo_proxy_fp"}`.
- Long format simplifies aggregation; the comparison API pivots to wide format on read.
- player_id resolution via existing `PlayerNameResolver` for cross-source name matching.

### API + Frontend Integration

- New endpoint: `GET /api/projections/comparison?season=YYYY&week=WW&scoring=half_ppr`
  - Response shape: `List[ComparisonRow]` where each row is `{player_id, player_name, position, team, ours: Optional[float], espn: Optional[float], sleeper: Optional[float], yahoo: Optional[float], delta_vs_ours: Optional[float], position_rank_ours: Optional[int]}`.
  - Query params: `season` (required), `week` (required), `scoring` (default "half_ppr"), `position` (optional filter), `limit` (default 50).
- Pydantic model `ProjectionComparison` lives in `web/api/models/schemas.py`.
- Service function `projection_service.get_comparison()` reads Silver, pivots, computes deltas.
- Frontend: new comparison view extends the existing projections page. Add a tab or toggle "Comparison" alongside "Standard". Reuses existing position filter, sort, and pagination.
- `data_as_of` chip per source (Phase 70 pattern) — shows Sleeper/ESPN/Yahoo freshness independently.

### Refresh + Freshness

- New GHA workflow `.github/workflows/weekly-external-projections.yml` runs Tuesdays at 14:00 UTC (after Monday Night Football) and Sundays at 12:00 UTC (pre-game refresh). Auto-detects current NFL week.
- Sources fetched in parallel with retry logic; failures skip that source for the week (D-06 fail-open) — comparison page shows source as "—" rather than failing the whole response.
- Each source's ingester writes to Bronze, then a Silver consolidation step merges all 4 sources into the canonical Silver Parquet.

### Claude's Discretion

- Exact ESPN API field mapping (theirs uses different stat-name keys than ours).
- FantasyPros HTML scraping selectors — may evolve; keep them in module-level constants for easy update.
- UI: tab vs side-by-side toggle for "Comparison" view — pick what reads best with existing projections-page layout.
- Default scoring format on the comparison endpoint — match `/api/projections/weekly` default (`"half_ppr"`).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/utils.py` — `download_latest_parquet`, `get_latest_s3_key` for Silver reads.
- `src/player_name_resolver.py` — cross-source name → player_id resolution.
- `web/api/services/projection_service.py` — existing weekly projection reader; extend with `get_comparison()`.
- `web/api/routers/projections.py` — existing projections router; add new `/comparison` endpoint.
- `web/api/models/schemas.py` — Pydantic models; add `ProjectionComparison` and `ProjectionComparisonRow`.
- Frontend `web/frontend/src/features/nfl/components/` — existing projections table component; extend or wrap.
- `.github/workflows/weekly-pipeline.yml` — existing cron pattern; mirror for external-projections.yml.
- Sleeper MCP — already wired; check for projection-fetching tool or extend if needed.

### Established Patterns
- Bronze immutable, Silver additive, Gold output.
- Parquet partitioned by `season=YYYY/week=WW` with timestamp suffix.
- D-06 fail-open: every external call has graceful fallback.
- Frontend reads via React Query + useSuspenseQuery.

### Integration Points
- Backend new endpoint at `/api/projections/comparison`.
- Frontend new view rendered as a tab on the existing projections page.
- GHA cron auto-detects current NFL week (existing weekly-pipeline pattern).

</code_context>

<specifics>
## Specific Ideas

- The Silver schema is long-format (one row per (player, source)) so adding a 5th source later is column-free.
- `delta_vs_ours` is computed at API layer (not Silver) so the math is always fresh against our most recent projection.
- Source labels for `yahoo_proxy_fp` make provenance transparent — users see we're using FantasyPros consensus as a Yahoo proxy until real OAuth lands.
- Position filter on the comparison endpoint reuses the existing position validation from `/api/projections/weekly`.

</specifics>

<deferred>
## Deferred Ideas

- Real Yahoo OAuth integration (requires user-specific tokens) — v8.0.
- CBS Sports projections — defer; FantasyPros consensus already aggregates them.
- Player-level confidence intervals across sources (range, std-dev) — future polish, after the basic comparison ships.
- Mobile-optimized comparison table (horizontal scroll vs sticky columns) — defer to v7.2 design polish.
- "Consensus" projection auto-computed from average of all 4 sources — defer; compare-only first, derive averages later.

</deferred>
