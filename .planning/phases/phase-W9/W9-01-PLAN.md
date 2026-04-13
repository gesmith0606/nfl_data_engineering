---
phase: W9-draft-tool
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - web/api/routers/draft.py
  - web/api/models/schemas.py
  - web/api/main.py
autonomous: true
requirements:
  - DRAFT-API-01
  - DRAFT-API-02
  - DRAFT-API-03
  - DRAFT-API-04
  - DRAFT-API-05
  - DRAFT-API-06

must_haves:
  truths:
    - "GET /api/draft/board returns all players with ADP, VORP, model_rank, value_tier"
    - "POST /api/draft/pick records a pick and returns updated board state"
    - "GET /api/draft/recommendations returns ranked suggestions with reasoning"
    - "POST /api/draft/mock/start initializes a mock draft simulation"
    - "POST /api/draft/mock/pick advances one pick in mock draft"
    - "GET /api/draft/adp returns latest ADP data"
  artifacts:
    - path: "web/api/routers/draft.py"
      provides: "All 6 draft API endpoints"
      exports: ["router"]
    - path: "web/api/models/schemas.py"
      provides: "Draft Pydantic response models"
      contains: "DraftBoardResponse"
  key_links:
    - from: "web/api/routers/draft.py"
      to: "src/draft_optimizer.py"
      via: "direct import of DraftBoard, DraftAdvisor, MockDraftSimulator, compute_value_scores"
      pattern: "from draft_optimizer import"
    - from: "web/api/main.py"
      to: "web/api/routers/draft.py"
      via: "app.include_router"
      pattern: "include_router.*draft"
---

<objective>
Build the FastAPI backend endpoints that wrap the existing `draft_optimizer.py` engine for the web draft tool.

Purpose: The entire draft engine (DraftBoard, DraftAdvisor, MockDraftSimulator, AuctionDraftBoard) already exists in `src/draft_optimizer.py`. This plan wraps it in FastAPI endpoints with session-based state management so the Next.js frontend can drive drafts via HTTP.

Output: 6 new API endpoints under `/api/draft/`, Pydantic response models, router registered in main.py.
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@src/draft_optimizer.py
@web/api/main.py
@web/api/routers/lineups.py
@web/api/models/schemas.py
@scripts/draft_assistant.py

<interfaces>
<!-- Key types from src/draft_optimizer.py that endpoints will wrap -->

From src/draft_optimizer.py:
```python
def compute_value_scores(projections: pd.DataFrame, adp_df: Optional[pd.DataFrame] = None) -> pd.DataFrame
    # Returns DataFrame with: model_rank, adp_rank, adp_diff, value_tier, vorp

class DraftBoard:
    def __init__(self, players: pd.DataFrame, roster_format: str = "standard", n_teams: int = 12)
    def draft_player(self, player_id: str, by_me: bool = False) -> Dict
    def draft_by_name(self, name: str, by_me: bool = False) -> Dict
    def roster_summary(self) -> Dict[str, List[str]]
    def remaining_needs(self) -> Dict[str, int]
    def picks_taken(self) -> int
    def my_pick_count(self) -> int

class DraftAdvisor:
    def __init__(self, board: DraftBoard, scoring_format: str = "half_ppr")
    def best_available(self, positions: Optional[List[str]] = None, top_n: int = 10) -> pd.DataFrame
    def recommend(self, top_n: int = 5, enforce_needs: bool = True) -> Tuple[pd.DataFrame, str]
    def undervalued_players(self, top_n: int = 10) -> pd.DataFrame
    def position_breakdown(self) -> pd.DataFrame

class MockDraftSimulator:
    def __init__(self, board: DraftBoard, user_pick: int, n_teams: int, randomness: int = 3)
    def run_full_simulation(self, advisor: DraftAdvisor) -> Dict
        # Returns: picks, my_roster, total_pts, total_vorp, expected_vorp, draft_grade
    def simulate_opponent_pick(self, pick_number: int) -> Optional[str]

class AuctionDraftBoard(DraftBoard):
    def __init__(self, players, roster_format, n_teams, budget_per_team=200)
    def win_bid(self, name: str, cost: int, by_me: bool = True) -> Dict
    def budget_summary(self) -> Dict
```

From src/config.py:
```python
ROSTER_CONFIGS: Dict[str, Dict[str, int]] = {
    "standard": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1, "BN": 6},
    "superflex": {...},
    "2qb": {...},
}
SCORING_CONFIGS: Dict[str, Dict[str, float]] = {"ppr": {...}, "half_ppr": {...}, "standard": {...}}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add draft Pydantic models and create draft router with all 6 endpoints</name>
  <files>web/api/models/schemas.py, web/api/routers/draft.py, web/api/main.py</files>
  <action>
**Step 1 — Add Pydantic models to `web/api/models/schemas.py`:**

Append these models (do NOT modify existing models):

```python
class DraftPlayer(BaseModel):
    """A player on the draft board."""
    player_id: str
    player_name: str
    position: str
    team: Optional[str] = None
    projected_points: float
    model_rank: int
    adp_rank: Optional[float] = None
    adp_diff: Optional[float] = None
    value_tier: str = "fair_value"
    vorp: float = 0.0

class DraftBoardResponse(BaseModel):
    """Full draft board state."""
    session_id: str
    players: List[DraftPlayer]
    my_roster: List[DraftPlayer]
    picks_taken: int
    my_pick_count: int
    remaining_needs: dict
    scoring_format: str
    roster_format: str
    n_teams: int

class DraftPickRequest(BaseModel):
    """Request to record a draft pick."""
    session_id: str
    player_id: str
    by_me: bool = True

class DraftPickResponse(BaseModel):
    """Response after a pick is recorded."""
    success: bool
    player: Optional[DraftPlayer] = None
    message: str = ""

class DraftRecommendation(BaseModel):
    """A recommended draft pick."""
    player_id: str
    player_name: str
    position: str
    team: Optional[str] = None
    projected_points: float
    model_rank: int
    vorp: float
    recommendation_score: float

class DraftRecommendationsResponse(BaseModel):
    """Recommendations for current draft position."""
    recommendations: List[DraftRecommendation]
    reasoning: str
    remaining_needs: dict

class MockDraftStartRequest(BaseModel):
    """Request to start a mock draft."""
    scoring: str = "half_ppr"
    roster_format: str = "standard"
    n_teams: int = 12
    user_pick: int = 1
    season: int = 2026

class MockDraftStartResponse(BaseModel):
    """Response after starting a mock draft."""
    session_id: str
    message: str

class MockDraftPickRequest(BaseModel):
    """Request to advance one pick in mock draft."""
    session_id: str

class MockDraftPickResponse(BaseModel):
    """Response after advancing a mock draft pick."""
    pick_number: int
    round_number: int
    is_user_turn: bool
    player_name: Optional[str] = None
    position: Optional[str] = None
    team: Optional[str] = None
    is_complete: bool = False
    draft_grade: Optional[str] = None
    total_pts: Optional[float] = None
    total_vorp: Optional[float] = None

class AdpPlayer(BaseModel):
    """A player's ADP entry."""
    player_name: str
    position: str
    team: Optional[str] = None
    adp_rank: float

class AdpResponse(BaseModel):
    """Latest ADP data."""
    players: List[AdpPlayer]
    source: str
    updated_at: Optional[str] = None
```

**Step 2 — Create `web/api/routers/draft.py`:**

Use in-memory dict for session management (keyed by UUID session_id). Each session stores a DraftBoard + DraftAdvisor + optional MockDraftSimulator. Follow the pattern in `web/api/routers/lineups.py` for sys.path setup.

Key implementation details:

- `_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent` then `sys.path.insert(0, str(_PROJECT_ROOT / "src"))` — same pattern as lineups.py
- Import `DraftBoard, DraftAdvisor, MockDraftSimulator, compute_value_scores` from `draft_optimizer`
- Import `generate_preseason_projections` from `projection_engine` and `ROSTER_CONFIGS, SCORING_CONFIGS` from `config`
- Use `uuid.uuid4().hex` for session IDs
- Store sessions in a module-level dict: `_sessions: Dict[str, Dict] = {}` with keys `board`, `advisor`, `simulator`, `created_at`
- Add a helper `_load_draft_data(scoring, season)` that calls `generate_preseason_projections(season, scoring)`, reads ADP from `data/adp_latest.csv` if it exists (using pandas), and calls `compute_value_scores(projections, adp_df)`
- `_df_row_to_draft_player(row)` converts a DataFrame row to DraftPlayer schema

**Endpoints:**

1. `GET /api/draft/board` — Query params: `scoring` (default "half_ppr"), `roster_format` (default "standard"), `n_teams` (default 12), `season` (default 2026), `session_id` (optional — reuse existing session). If no session_id, create new session. Returns DraftBoardResponse with available players, my_roster, needs.

2. `POST /api/draft/pick` — Body: DraftPickRequest. Looks up session, calls `board.draft_player(player_id, by_me)`. Returns DraftPickResponse.

3. `GET /api/draft/recommendations` — Query params: `session_id`, `top_n` (default 5), `position` (optional filter). Calls `advisor.recommend()` or `advisor.best_available(positions)` if position filter provided. Returns DraftRecommendationsResponse.

4. `POST /api/draft/mock/start` — Body: MockDraftStartRequest. Creates a fresh session with DraftBoard + DraftAdvisor + MockDraftSimulator. Returns MockDraftStartResponse with session_id.

5. `POST /api/draft/mock/pick` — Body: MockDraftPickRequest. Advances one pick in the mock draft. If it is the user's turn, uses advisor.recommend(top_n=1) to auto-pick. If opponent's turn, calls simulator.simulate_opponent_pick(). Track pick_number in the session dict. Returns MockDraftPickResponse. When all picks complete, set is_complete=True and include draft_grade/total_pts/total_vorp.

6. `GET /api/draft/adp` — No params. Reads `data/adp_latest.csv`, returns AdpResponse. Handle missing file with 404.

Use `router = APIRouter(prefix="/draft", tags=["draft"])`.

**Step 3 — Register router in `web/api/main.py`:**

Add `from .routers import draft` to the imports (alongside existing imports). Add `app.include_router(draft.router, prefix="/api")` after the existing router registrations.

**Error handling:** Return 404 HTTPException for invalid session_id, 400 for invalid player_id. Use try/except around draft_optimizer calls.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -c "from web.api.routers.draft import router; print(f'Router loaded with {len(router.routes)} routes')" && python -c "from web.api.models.schemas import DraftBoardResponse, DraftPickRequest, MockDraftStartRequest; print('All draft schemas imported OK')"</automated>
  </verify>
  <done>
    - All 6 endpoints defined in draft.py router
    - DraftBoardResponse and related Pydantic models added to schemas.py
    - Router registered in main.py
    - Imports resolve without errors
    - Sessions created with UUID, board/advisor/simulator stored per session
  </done>
</task>

<task type="auto">
  <name>Task 2: Add draft API tests</name>
  <files>tests/test_draft_api.py</files>
  <action>
Create `tests/test_draft_api.py` with pytest tests for the draft API endpoints using FastAPI TestClient.

```python
from fastapi.testclient import TestClient
from web.api.main import app

client = TestClient(app)
```

Test cases:
1. `test_get_draft_board_creates_session` — GET /api/draft/board with scoring=half_ppr, assert 200, assert response has session_id, players list is non-empty, my_roster is empty list, picks_taken is 0.
2. `test_get_draft_board_reuse_session` — Create a session, then GET /api/draft/board with same session_id, verify same session state.
3. `test_draft_pick` — Create session, POST /api/draft/pick with a player_id from the board. Assert success=True, player is returned.
4. `test_draft_pick_invalid_session` — POST /api/draft/pick with fake session_id, assert 404.
5. `test_recommendations` — Create session, GET /api/draft/recommendations with session_id. Assert recommendations list is non-empty, reasoning is a string.
6. `test_mock_draft_start` — POST /api/draft/mock/start. Assert 200, session_id returned.
7. `test_mock_draft_pick_advances` — Start mock, then POST /api/draft/mock/pick. Assert pick_number >= 1.
8. `test_adp_endpoint` — GET /api/draft/adp. If data/adp_latest.csv exists, assert 200 and players list; if not, assert 404.

Use `@pytest.fixture` for session creation. Mark integration tests with `@pytest.mark.integration` since they depend on projection data.

Note: These tests may be slow since they trigger `generate_preseason_projections`. Use `@pytest.mark.slow` and skip if running fast suite. Add a module-level fixture that creates one session to reuse across tests.
  </action>
  <verify>
    <automated>cd /Users/georgesmith/repos/nfl_data_engineering && source venv/bin/activate && python -m pytest tests/test_draft_api.py -v --timeout=120 -x 2>&1 | tail -30</automated>
  </verify>
  <done>
    - Test file exists with 8+ test cases
    - All tests pass (or skip gracefully if projection data unavailable)
    - Tests cover happy path and error cases for all 6 endpoints
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client -> API | Draft pick requests, session IDs from untrusted frontend |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-W9-01 | Spoofing | session_id | mitigate | UUID4 session IDs are unguessable; validate session exists before use |
| T-W9-02 | DoS | /api/draft/board | mitigate | Session creation triggers projection generation (expensive); add session limit (max 100 concurrent sessions, evict oldest) |
| T-W9-03 | Tampering | /api/draft/pick | mitigate | Validate player_id exists in available pool before drafting |
| T-W9-04 | Info Disclosure | session state | accept | In-memory sessions are single-process; no cross-user data leak risk for single-user app |
</threat_model>

<verification>
1. `uvicorn web.api.main:app --reload --port 8000` starts without import errors
2. `curl http://localhost:8000/api/draft/board?scoring=half_ppr` returns JSON with session_id and players
3. POST /api/draft/pick with valid session_id and player_id returns success
4. GET /api/draft/recommendations with valid session_id returns recommendations
5. POST /api/draft/mock/start returns session_id
6. All tests pass
</verification>

<success_criteria>
- 6 FastAPI endpoints operational under /api/draft/
- Session-based draft state management working
- Existing draft_optimizer.py wrapped without modification
- Pydantic models validate all request/response shapes
- Tests cover all endpoints
</success_criteria>

<output>
After completion, create `.planning/phases/phase-W9/W9-01-SUMMARY.md`
</output>
