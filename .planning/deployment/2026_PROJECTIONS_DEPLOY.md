# 2026 Preseason Projections Deployment

**Date**: 2026-04-10
**Status**: LIVE

## Summary

Generated 2026 preseason fantasy projections from 2024 historical seasonal data
and deployed to both the Railway backend API and Vercel frontend.

## Scoring Formats Generated

| Format    | Players | Top Player       | Projected Points |
|-----------|---------|------------------|-----------------|
| half_ppr  | 569     | Lamar Jackson    | 483.1           |
| ppr       | 569     | Lamar Jackson    | 483.1           |
| standard  | 569     | Lamar Jackson    | 483.1           |

## Position Breakdown (per format)

| Position | Count |
|----------|-------|
| WR       | 227   |
| RB       | 145   |
| TE       | 119   |
| QB       | 78    |

## Data Source

- Historical data: 2024 season only (2025 returns HTTP 404 from nfl-data-py as of April 2026)
- Position/name/team enriched via `import_seasonal_rosters([2024])`
- Draft capital boost applied to rookies via historical dimension table (9,892 profiles)

## Storage Paths

- Preseason canonical: `data/gold/projections/preseason/season=2026/*.parquet`
- API-compatible: `data/gold/projections/season=2026/week=1/projections_{scoring}_{ts}.parquet`
  - `week=1` used as the preseason season slot
  - Column `projected_season_points` renamed to `projected_points`
  - `proj_season` column removed to avoid rename_map conflict in projection_service.py
  - `projected_floor` / `projected_ceiling` added at ±20%

## Live URLs

- Frontend: https://frontend-jet-seven-33.vercel.app (defaults to season=2026, week=1)
- Backend API: https://nfldataengineering-production.up.railway.app/api/projections?season=2026&week=1&scoring=half_ppr

## Commits

- `b1e40c9` feat(data): generate 2026 preseason projections (PPR/Half-PPR/Standard)
- `ae95b68` feat(frontend): update default season/week to 2026 preseason
- `41a5cca` fix(api): use _safe_int for season/week in projection serializer
- `64dcf10` fix(data): remove proj_season column from 2026/week=1 parquets

## Bugs Fixed During Deployment

1. `generate_projections.py` preseason mode: 2025 season returns 404 from nfl-data-py —
   fixed by iterating per-season with graceful skip
2. `import_seasonal_data` omits position/player_name/team — fixed by joining
   `import_seasonal_rosters` on player_id
3. `add_floor_ceiling` called on preseason output which uses `projected_season_points`
   not `projected_points` — fixed by skipping for `--preseason` mode
4. Bare `int()` on numpy int64 pandas scalars raised TypeError in Python 3.9 —
   fixed by routing season/week through `_safe_int()` in projection router
5. Duplicate `season` column from `proj_season` rename_map conflict — fixed by
   dropping `proj_season` before saving API-compatible parquets

## Fallbacks Used

- Only 2024 data used (not 2024+2025) due to 2025 seasonal data unavailability
- Week=1 used as preseason slot (API requires week 1-18; no dedicated preseason endpoint)
