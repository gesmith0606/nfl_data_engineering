---
phase: 73-external-projections-comparison
plan: 03
type: execute
wave: 3
depends_on: [73-02]
files_modified:
  - web/api/models/schemas.py
  - web/api/services/projection_service.py
  - web/api/routers/projections.py
  - tests/web/test_projections_comparison.py
  - tests/fixtures/silver_external_projections/
autonomous: true
requirements: [EXTP-03]
must_haves:
  truths:
    - "GET /api/projections/comparison?season=Y&week=W&scoring=F returns HTTP 200 with a JSON envelope containing a list of ProjectionComparisonRow"
    - "Each row carries player_id, player_name, position, team, plus 4 nullable source columns (ours, espn, sleeper, yahoo) AND a delta_vs_ours float computed at API layer"
    - "Missing sources surface as null per source column (D-06 fail-open) — the response never 500s because one source's Bronze partition is empty"
    - "Pydantic v2 schema (ProjectionComparison + ProjectionComparisonRow) lives in web/api/models/schemas.py — additive, no breaking changes to existing models"
    - "Position filter + limit query params behave identically to the existing /api/projections endpoint (reuses VALID_POSITIONS validation)"
  artifacts:
    - path: "web/api/models/schemas.py"
      provides: "ProjectionComparison + ProjectionComparisonRow Pydantic v2 models"
      contains: "class ProjectionComparison"
    - path: "web/api/services/projection_service.py"
      provides: "get_comparison() service function reading Silver + pivoting"
      contains: "def get_comparison"
    - path: "web/api/routers/projections.py"
      provides: "GET /api/projections/comparison route handler"
      contains: "@router.get(\"/comparison\""
    - path: "tests/web/test_projections_comparison.py"
      provides: "FastAPI TestClient coverage for the new endpoint"
  key_links:
    - from: "web/api/routers/projections.py"
      to: "web/api/services/projection_service.get_comparison"
      via: "function call from route handler"
      pattern: "get_comparison|projection_service\\.get_comparison"
    - from: "web/api/services/projection_service.get_comparison"
      to: "data/silver/external_projections/season=YYYY/week=WW/"
      via: "_latest_parquet read + pivot"
      pattern: "data/silver/external_projections|silver_external_projections"
    - from: "GET /api/projections/comparison"
      to: "web/api/models/schemas.ProjectionComparison"
      via: "response_model declaration"
      pattern: "response_model=ProjectionComparison"
---

<objective>
Wire the Silver consolidation output (from Wave 2) into a new FastAPI endpoint that the frontend (Wave 4) consumes. The endpoint reads the latest Silver Parquet for a given (season, week, scoring), pivots from long to wide format, computes `delta_vs_ours`, and returns a JSON envelope.

Purpose: Provide a stable, documented API contract that the frontend can render. The pivot + delta math lives in the service layer — the router is a thin adapter.
Output: 2 new Pydantic models, 1 new service function, 1 new route, 1 test file with ≥6 tests + fixtures.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/73-external-projections-comparison/73-CONTEXT.md
@.planning/phases/73-external-projections-comparison/73-02-silver-consolidation-PLAN.md
@CLAUDE.md
@web/api/models/schemas.py
@web/api/services/projection_service.py
@web/api/routers/projections.py
@web/api/config.py

<interfaces>
<!-- Existing patterns the new endpoint must follow -->

From web/api/routers/projections.py — existing route shape:
```python
@router.get("", response_model=ProjectionResponse)
def list_projections(
    season: int = Query(..., ge=1999, le=2030, description="NFL season"),
    week: int = Query(..., ge=1, le=18, description="Week number"),
    scoring: str = Query("half_ppr", description="ppr / half_ppr / standard"),
    position: Optional[str] = Query(None, description="QB / RB / WR / TE / K"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(200, ge=1, le=1000, description="Max results"),
) -> ProjectionResponse:
    if scoring not in VALID_SCORING_FORMATS:
        raise HTTPException(status_code=400, detail=...)
    if position and position.upper() not in VALID_POSITIONS:
        raise HTTPException(status_code=400, detail=...)
    ...
```

From web/api/models/schemas.py — existing patterns to mirror:
```python
class ProjectionMeta(BaseModel):
    season: int
    week: int
    data_as_of: Optional[str] = Field(None, ...)
    source_path: Optional[str] = Field(None, ...)

class ProjectionResponse(BaseModel):
    season: int
    week: int
    scoring_format: str
    projections: List[PlayerProjection]
    generated_at: str
    meta: Optional[ProjectionMeta] = ...
```

Silver Parquet schema (consumed by this plan, produced by 73-02):
```
columns: player_id (str), player_name (str), position (str), team (str),
         source (str — "ours" | "espn" | "sleeper" | "yahoo_proxy_fp"),
         scoring_format (str), projected_points (float),
         projected_at (str), season (int), week (int)
```

Target endpoint contract (from CONTEXT.md):
```
GET /api/projections/comparison?season=2025&week=1&scoring=half_ppr&position=QB&limit=50

Response (ProjectionComparison):
{
  "season": 2025,
  "week": 1,
  "scoring_format": "half_ppr",
  "rows": [
    {
      "player_id": "00-0033873",
      "player_name": "Patrick Mahomes",
      "position": "QB",
      "team": "KC",
      "ours": 24.3,
      "espn": 23.1,
      "sleeper": 24.0,
      "yahoo": null,
      "delta_vs_ours": 0.65,         # mean(others) - ours; null when no others present
      "position_rank_ours": 1
    },
    ...
  ],
  "sources_present": ["ours", "espn", "sleeper"],   # which sources had any data
  "generated_at": "2026-04-25T14:00:00+00:00",
  "meta": { ... ProjectionMeta ... }
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pydantic models + comparison fixtures</name>
  <files>
    web/api/models/schemas.py,
    tests/fixtures/silver_external_projections/season=2025/week=1/external_projections_sample.parquet,
    tests/web/test_projections_comparison.py
  </files>
  <behavior>
    - `ProjectionComparisonRow(BaseModel)`: fields `player_id: str`, `player_name: str`, `position: str`, `team: str`, `ours: Optional[float] = None`, `espn: Optional[float] = None`, `sleeper: Optional[float] = None`, `yahoo: Optional[float] = None`, `delta_vs_ours: Optional[float] = None`, `position_rank_ours: Optional[int] = None`. Pydantic v2 syntax (BaseModel, Field).
    - `ProjectionComparison(BaseModel)`: fields `season: int`, `week: int`, `scoring_format: str`, `rows: List[ProjectionComparisonRow]`, `sources_present: List[str]`, `generated_at: str`, `meta: Optional[ProjectionMeta] = None`.
    - The frontend-facing field is `yahoo` (NOT `yahoo_proxy_fp`) — the proxy provenance is implied by tooltip on the frontend; the API column name is the user-friendly label per CONTEXT.md UI hint. The provenance string still lives in `sources_present` if needed for tooltip text, AND we expose a separate `source_labels` map: `Dict[str, str]` mapping `"yahoo" -> "yahoo_proxy_fp"` so the frontend can render a "(via FantasyPros)" tooltip.
    - Add `source_labels: Dict[str, str] = Field(default_factory=dict, description="Maps the user-facing source name to the canonical provenance label (e.g. 'yahoo' -> 'yahoo_proxy_fp')")` to ProjectionComparison.
    - Fixture: a small Silver Parquet with 4 sources + 8 players (3 with all 4 sources, 2 with only ours+espn, 2 ours-only, 1 espn-only — exercises the missing-source surface).
  </behavior>
  <action>
    1. In `web/api/models/schemas.py`, add the two new classes immediately after `ProjectionResponse` (around line 100). Strictly additive — do NOT modify existing models. Import `Dict` from typing if not already imported.
    2. Build the fixture Parquet via a tiny helper in the test file (parameterized via `tmp_path` builder OR a static commit). Choose static commit for determinism: write a one-shot helper script that emits `tests/fixtures/silver_external_projections/season=2025/week=1/external_projections_sample.parquet` and run it once; commit the resulting Parquet (~3 KB).
       - Players covered: Patrick Mahomes (KC, QB), Josh Allen (BUF, QB), Christian McCaffrey (SF, RB), Saquon Barkley (PHI, RB), Justin Jefferson (MIN, WR), Tyreek Hill (MIA, WR), Travis Kelce (KC, TE), Justin Tucker (BAL, K) — 8 players × variable source coverage.
    3. Create `tests/web/test_projections_comparison.py` with:
       - `test_projection_comparison_row_default_values` — all 4 sources None, delta None, rank None
       - `test_projection_comparison_envelope_shape` — instantiate from dict, validates roundtrip
       - `test_source_labels_default_empty_dict` — empty by default
    4. Run `python -m pytest tests/web/test_projections_comparison.py -v` — 3 tests pass.
  </action>
  <verify>
    <automated>python -m pytest tests/web/test_projections_comparison.py -v</automated>
  </verify>
  <done>
    - 2 new Pydantic models added to schemas.py
    - Existing models unchanged (additive only)
    - Fixture Parquet exists and is reproducible
    - 3 schema tests pass
    - Pydantic v2 syntax (BaseModel + Field), Python 3.9 type hints
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: get_comparison service function with pivot + delta math</name>
  <files>
    web/api/services/projection_service.py,
    tests/web/test_projections_comparison.py
  </files>
  <behavior>
    - Add module-level constant `SILVER_EXTERNAL_PROJECTIONS_DIR = Path("data/silver/external_projections")` near the top of `projection_service.py` (after `_PROJECT_ROOT` definition).
    - Add `def get_comparison(season: int, week: int, scoring_format: str, position: Optional[str] = None, limit: int = 50) -> Tuple[List[Dict[str, Any]], ProjectionMetaInfo, List[str], Dict[str, str]]`:
       1. Resolve the latest Silver Parquet path via `_latest_parquet(SILVER_EXTERNAL_PROJECTIONS_DIR / f"season={season}" / f"week={week}")`. If None → return `([], ProjectionMetaInfo(season, week, None, None), [], {})` (D-06: empty list, not 404).
       2. Load DataFrame. Filter to `scoring_format == scoring_format` (case-insensitive lower).
       3. Pivot wide: `df.pivot_table(index=['player_id','player_name','position','team'], columns='source', values='projected_points', aggfunc='first').reset_index()`. Rename `yahoo_proxy_fp` column → `yahoo` for the user-facing API.
       4. Build the `source_labels` map by scanning the original `source` column unique values: `{"yahoo": "yahoo_proxy_fp"}` if `yahoo_proxy_fp` is present; empty dict otherwise. Other sources (ours, espn, sleeper) are pass-through and not included in source_labels (label == column).
       5. Compute `delta_vs_ours`: for each row, `mean([espn, sleeper, yahoo] dropna) - ours` if `ours` is not None AND at least one other is not None; else None. Use `pd.notna`.
       6. Compute `position_rank_ours`: for rows where `ours` is not None, dense-rank within position by `ours` descending. None for rows where `ours` is missing.
       7. Apply `position` filter (case-insensitive) if provided.
       8. Sort by `ours` desc (NaN last), then by `delta_vs_ours` desc (NaN last). Apply `head(limit)`.
       9. Return `(records, meta_info, sources_present, source_labels)` where `records = result_df.where(pd.notna(result_df), None).to_dict(orient="records")` (NaN → None for JSON safety) and `sources_present = sorted(unique sources from the loaded DataFrame, with yahoo_proxy_fp renamed to yahoo)`.
    - Add tests:
       - `test_get_comparison_pivots_long_to_wide` — fixture in, 8 rows out, columns include ours/espn/sleeper/yahoo
       - `test_get_comparison_renames_yahoo_proxy_fp_to_yahoo` — assert no `yahoo_proxy_fp` column in output, source_labels has the mapping
       - `test_get_comparison_returns_empty_when_silver_missing` — `tmp_path` with no Parquet → returns empty list, no raise
       - `test_get_comparison_delta_is_null_when_ours_missing` — fixture row with only espn → delta_vs_ours is None
       - `test_get_comparison_position_filter_uppercase` — `position="qb"` → only QB rows
       - `test_get_comparison_position_rank_ours_dense` — fixture with 2 QBs ranked 1 and 2 by ours
  </behavior>
  <action>
    1. Add `SILVER_EXTERNAL_PROJECTIONS_DIR` constant + `get_comparison()` function to `web/api/services/projection_service.py`. Keep it parquet-only for v1 (no DB backend); document the future Postgres path in a TODO comment.
    2. Use `from typing import Any, Dict, List, Tuple` for the return type.
    3. NaN → None conversion: `result_df = result_df.where(pd.notna(result_df), None)` before `to_dict`.
    4. Use `pd.DataFrame.pivot_table` (not `pivot`) to handle duplicate (player_id, source) gracefully via `aggfunc='first'`.
    5. Add 6 service-layer tests to `tests/web/test_projections_comparison.py`. Each test uses `monkeypatch.setattr(projection_service, "SILVER_EXTERNAL_PROJECTIONS_DIR", tmp_path)` and copies the fixture Parquet into `tmp_path/season=2025/week=1/`.
    6. Run `python -m pytest tests/web/test_projections_comparison.py -v` — 9 tests pass total (3 schema + 6 service).
  </action>
  <verify>
    <automated>python -m pytest tests/web/test_projections_comparison.py -v</automated>
  </verify>
  <done>
    - `get_comparison()` returns 4-tuple per the contract
    - yahoo_proxy_fp → yahoo rename + source_labels mapping verified
    - 6 service tests pass; 9 total in the file
    - D-06 fail-open: missing Silver → empty result, never raises
    - delta_vs_ours = mean(others) - ours, null when ours missing
    - position_rank_ours computed within position group
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: GET /api/projections/comparison route + integration test</name>
  <files>
    web/api/routers/projections.py,
    tests/web/test_projections_comparison.py
  </files>
  <behavior>
    - New route handler `comparison(season, week, scoring, position, limit) -> ProjectionComparison` registered with `@router.get("/comparison", response_model=ProjectionComparison)`
    - Query params: `season: int = Query(..., ge=1999, le=2030)`, `week: int = Query(..., ge=1, le=18)`, `scoring: str = Query("half_ppr")`, `position: Optional[str] = Query(None)`, `limit: int = Query(50, ge=1, le=500)` — note default 50 per CONTEXT.md
    - Validates `scoring` against `VALID_SCORING_FORMATS` and `position` against `VALID_POSITIONS` — same pattern as existing `list_projections`
    - Calls `projection_service.get_comparison(...)`, builds `ProjectionComparisonRow[]` from the records, wraps in `ProjectionComparison(...)`, populates `meta` from the returned `ProjectionMetaInfo` and `sources_present` + `source_labels` from the service tuple
    - Empty result is HTTP 200 with `rows=[]`, `sources_present=[]`, `source_labels={}` — never 404 (D-06)
    - Integration tests via FastAPI TestClient:
       - `test_comparison_endpoint_returns_200_with_fixture` — happy path
       - `test_comparison_endpoint_returns_empty_when_silver_missing` — empty Silver dir → 200 with empty rows
       - `test_comparison_endpoint_400_on_invalid_scoring` — `?scoring=foo` → 422 (FastAPI Query validation) OR 400 (manual check) — assert one of them
       - `test_comparison_endpoint_400_on_invalid_position` — `?position=ZZ` → 400
  </behavior>
  <action>
    1. Add `comparison` route to `web/api/routers/projections.py`. Place it AFTER `list_projections` and BEFORE `latest_week`. Import `ProjectionComparison`, `ProjectionComparisonRow` from schemas.
    2. Service call returns 4-tuple — destructure: `records, meta_info, sources_present, source_labels = projection_service.get_comparison(...)`.
    3. Build rows: list comprehension `[ProjectionComparisonRow(**r) for r in records]`.
    4. Build response: `ProjectionComparison(season=season, week=week, scoring_format=scoring, rows=rows, sources_present=sources_present, source_labels=source_labels, generated_at=datetime.now(timezone.utc).isoformat(), meta=ProjectionMeta(...))`.
    5. Add 4 integration tests using `from fastapi.testclient import TestClient; from web.api.main import app; client = TestClient(app)`. Use the same monkeypatch trick from Task 2 to point `SILVER_EXTERNAL_PROJECTIONS_DIR` at the fixture dir.
    6. Run `python -m pytest tests/web/test_projections_comparison.py -v` — 13 tests pass total (3 schema + 6 service + 4 integration).
    7. Manual smoke test (optional): `./web/run_dev.sh` then `curl 'http://localhost:8000/api/projections/comparison?season=2025&week=1&scoring=half_ppr&limit=10' | jq .` returns the expected envelope.
    8. Run the full web test suite: `python -m pytest tests/web/ -v` — no regressions.
  </action>
  <verify>
    <automated>python -m pytest tests/web/test_projections_comparison.py tests/web/ -v</automated>
  </verify>
  <done>
    - GET /api/projections/comparison route registered + functional
    - 13 tests pass in `tests/web/test_projections_comparison.py`
    - No regressions in `tests/web/`
    - Empty Silver → HTTP 200 with empty rows (D-06)
    - Invalid scoring/position → 400/422
    - Response envelope matches CONTEXT.md contract exactly
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HTTP query params → API route | Untrusted input crosses here (season, week, scoring, position, limit) |
| Silver Parquet → service | Internal but decoupled; schema may drift |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-73-03-01 | Tampering | Query params (season/week/scoring/position) | mitigate | FastAPI `Query(..., ge=, le=)` validation + explicit `VALID_SCORING_FORMATS` and `VALID_POSITIONS` set membership checks → HTTPException 400 |
| T-73-03-02 | Denial of Service | unbounded `limit` | mitigate | `limit: int = Query(50, ge=1, le=500)` — hard cap at 500 rows |
| T-73-03-03 | Information Disclosure | source_path in meta | accept | source_path is a project-relative path (no PII), already exposed by existing /api/projections endpoint |
| T-73-03-04 | Tampering | NaN propagation in JSON | mitigate | `result_df.where(pd.notna(result_df), None)` before `to_dict` — prevents `Infinity`/`NaN` JSON serialization which clients interpret incorrectly |
| T-73-03-05 | Repudiation | Yahoo proxy provenance hidden | mitigate | `source_labels: {"yahoo": "yahoo_proxy_fp"}` in response — frontend renders tooltip; user knows it's a FantasyPros proxy |
</threat_model>

<verification>
- All 13 comparison tests green: `python -m pytest tests/web/test_projections_comparison.py -v`
- Full web tests still green: `python -m pytest tests/web/ -v`
- Flake8 clean on edited Python files
- No regressions in full suite: `python -m pytest tests/ -q -x`
- Manual curl smoke test (optional, requires API server) returns expected envelope
</verification>

<success_criteria>
- [x] GET /api/projections/comparison endpoint live + documented via response_model
- [x] ProjectionComparison + ProjectionComparisonRow Pydantic v2 models added (additive)
- [x] yahoo_proxy_fp → yahoo column rename with source_labels provenance map
- [x] D-06 fail-open: empty Silver → 200 with empty rows
- [x] delta_vs_ours computed at API layer (always fresh against current ours)
- [x] position_rank_ours computed in-position
- [x] 13 tests pass; no regressions
</success_criteria>

<output>
After completion, create `.planning/phases/73-external-projections-comparison/73-03-SUMMARY.md` summarizing: schema additions, route registered, request/response contract for the frontend (Wave 4) to consume, requirements covered (EXTP-03).
</output>
