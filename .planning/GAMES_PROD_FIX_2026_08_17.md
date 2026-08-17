# Games Prod Fix — 2026-08-17

Investigates the reported prod bug: `GET .../api/games/results?season=2025&week=1`
→ `{"detail":"Game results not found in season=2025 week=1"}`, despite the
committed Bronze schedules parquet holding all 16 week-1 2025 games with real
scores, and the frontend scores page allegedly rendering almost nothing (one
stray ARI@NO card).

**Bottom line: the DATABASE_URL/Postgres theory is false, and the real
`/api/games` endpoint the frontend calls was not actually broken.** The
reported URL is not a route this API has ever exposed. Root cause of the
*literal* symptom is a FastAPI route-ordering footgun (documented below,
harmless in practice since nothing calls that URL). Independently, a real
latent bug (mtime-based "latest parquet" sort, the exact class of bug that
already bit `projection_service.py` on 2026-06-12) was found and fixed in
`src/game_archive.py`, and `game_service.list_games` was brought onto the
same DB-first/Parquet-fallback convention the rest of the API uses, both as
defensive hardening per the task brief.

## 1. Root cause

### 1a. DATABASE_URL theory: falsified

Three independent pieces of evidence:

1. **Live `/api/health` right now**: `{"status":"ok","version":"0.1.0","db_status":"parquet_fallback","llm_enrichment_ready":true}`
   — the HF Space is not running against Postgres.
2. `deploy/huggingface/README.md`: *"Runs in **Parquet-fallback mode**: the
   API reads committed Parquet from the cloned source repo (no live
   database)."* This is the bridge backend's whole design, not an accident.
3. **There is no `games` table anywhere in this codebase.**
   `scripts/sync_gold_to_db.py` only defines `CREATE TABLE IF NOT EXISTS
   projections` and `CREATE TABLE IF NOT EXISTS predictions` — never
   `games`. `web/api/services/game_service.py` (before this fix) had zero
   `web.api.db` imports; it was Parquet-only. `projection_service.py` even
   says so explicitly in its own comment (line ~926-929): *"there is no
   Postgres actuals table, matching game_archive's Parquet-only design."*
   So even in a hypothetical world where DATABASE_URL were set, there was no
   `games` table to serve stale/missing 2025 rows from — the DB branch
   literally did not exist for this endpoint.

### 1b. The literal reported URL never was a route

`git log --oneline --all -- web/api/routers/games.py` shows exactly one
commit ever touched this router (`86a531fb`) — a `/results` sub-route never
existed. `web/frontend/src/lib/nfl/api.ts::fetchGames()` (and its full git
history) has only ever called `` `/api/games?${params}` `` — no `/results`
suffix, confirmed unchanged since introduction.

`web/api/routers/games.py` registers, in order:
```
GET /games/seasons
GET /games/leaders
GET /games/player-log/{player_id}
GET /games/{game_id}      <-- catch-all, registered before the list route
GET /games                 <-- the actual "list games" endpoint
```
FastAPI matches routes in declaration order. A request to
`/api/games/results?season=2025&week=1` doesn't match any literal segment
above `/{game_id}`, so it falls into `GET /games/{game_id}` with
`game_id="results"`. That calls `game_service.game_detail(2025, 1,
"results", ...)` → `src/game_archive.py::get_game_detail()` →
`games[games["game_id"] == "results"]` is empty →
`raise ValueError(f"Game {game_id} not found in season={season} week={week}")`
→ the router's `except ValueError` turns it into `HTTPException(404, ...)`.
That produces **exactly** the observed string: `"Game results not found in
season=2025 week=1"` (`"Game " + "results" + " not found in season=2025
week=1"`). This is not a data problem at all — it's what happens when any
non-game-id path segment is requested under `/games/`.

**Live verification** (2026-08-16, this session):
```
curl .../api/games?season=2025&week=1       -> 200, 16 games, incl.
    {"game_id":"2025_01_ARI_NO","home_team":"NO","away_team":"ARI",
     "home_score":13,"away_score":20, ...}   (the real, correct endpoint)
curl .../api/games/results?season=2025&week=1 -> 404 "Game results not found..."
    (the URL from the bug report, not a real route)
curl .../api/health -> db_status: "parquet_fallback"
```
The endpoint the frontend actually calls works correctly right now and
returns the full, correctly-scored 16-game slate.

### 1c. The "stray ARI@NO card"

`src/game_archive.py::get_game_results()` sorts by `["week", "game_id"]`,
and `game_id` is `f"{season}_{week:02d}_{away_team}_{home_team}"`. Among the
16 week-1 2025 away-team codes (ARI, BAL, CAR, CIN, DAL, DET, HOU, KC, LV,
MIA, MIN, NYG, PIT, SF, TB, TEN), `ARI` sorts alphabetically first, so
`2025_01_ARI_NO` is literally the **first row of the correct, working
response** — not data "from some other source." If the frontend really did
render only one card, the most likely explanation is a frontend-side bug
that only surfaces/renders the first array element (stale React Query cache
from an earlier failed request, a broken `.map()`, etc.) — not a backend gap,
since the full 16-row payload including that exact game is what `/api/games`
serves. This is outside the file scope for this fix (frontend files were not
touched); flagging it here as the diagnostic finding requested.

## 2. What was actually fixed

Even though the DB theory didn't hold and the real endpoint wasn't broken,
two concrete latent risks were found and fixed within scope
(`web/api/routers/games.py`, `web/api/services/game_service.py`,
`src/game_archive.py`, tests):

### 2a. `src/game_archive.py::_latest_parquet` — mtime-sort bug

Was: `sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)`.
In the HF Spaces deployment the repo is `git clone`d fresh at container
build time, so **every file gets the same clone-time mtime** — an mtime sort
degenerates to directory-iteration order, i.e. an arbitrary pick whenever a
season directory ever holds more than one parquet. This is the *exact* bug
class that already hit `projection_service.py` in production on 2026-06-12
(documented in that file's comments) — `projection_service.py` was fixed to
sort on the filename-embedded `YYYYMMDD_HHMMSS` timestamp instead, but
`game_archive.py` still had the old, vulnerable version. Currently
`data/bronze/schedules/season=2025/` holds exactly one file, so this wasn't
firing today, but it's a real landmine for the next mid-season schedule
refresh. Fixed by porting the same filename-timestamp sort (`_FILENAME_TS_RE`
/ `_filename_sort_key`) into `game_archive.py`.

### 2b. `game_service.list_games` — DB-first-with-Parquet-fallback added

Brought `list_games` onto the same convention `projection_service.get_projections`
and `prediction_service.get_predictions` already use (`is_db_enabled()` →
try DB → fall back to Parquet on any exception), **plus** an explicit
empty-result fallback that those two precedents don't have — DB reachable
but zero rows now also falls back to Parquet instead of serving a false
miss. This directly hardens against the hypothesis in the bug report (a
`games` table that's wired up but not backfilled for a season) in case one
ever ships. `GameListResponse` gained a `source` field
(`"postgres"` / `"parquet"` / `"parquet_fallback"`) mirroring
`ProjectionMetaInfo.source`'s `"weekly"`/`"preseason_fallback"` labelling
convention, so callers/monitoring can tell which path served a response.

`game_service.list_games()` signature changed from `List[Dict]` to
`Tuple[List[Dict], str]` (records, source) — the only caller
(`web/api/routers/games.py::list_games`) was updated accordingly. No other
call sites exist in the repo.

`src/game_archive.py` remains Parquet-only by design (per the documented
convention referenced in `projection_service.py`) — the new DB code lives
entirely in `web/api/services/game_service.py`, matching where
`projection_service.py`/`prediction_service.py` keep their own `_get_*_db`
helpers.

## 3. Tests

Added to `tests/test_game_archive.py`:

- `TestGameServiceDbFallback`:
  - `test_db_disabled_uses_parquet_unchanged` — DB never queried, `source ==
    "parquet"`, 16 records (**DB-disabled → parquet path unchanged**).
  - `test_db_empty_falls_back_to_parquet` — DB returns `pd.DataFrame()`,
    Parquet is queried and serves all 16 games, `source ==
    "parquet_fallback"` (**DB-empty → parquet fallback serves 16 games**).
  - `test_db_error_falls_back_to_parquet` — DB raises, same fallback.
  - `test_db_success_skips_parquet` — DB returns rows, Parquet never
    touched, `source == "postgres"`.
- `TestGameApiDbFallbackIntegration::test_results_endpoint_falls_back_to_parquet_when_db_empty`
  — router-level: hits `GET /api/games?season=2025&week=1` with DB
  enabled-but-empty mocked, asserts 200/16 games/`source ==
  "parquet_fallback"`/`2025_01_ARI_NO` present.
- Extended the existing `test_list_games` to assert `data["source"] ==
  "parquet"` (DB-disabled is the actual state of every real environment
  today, confirming local/current-prod behavior is unchanged).

Results:
```
tests/test_game_archive.py ................................  33 passed
tests/test_web_api.py + tests/web/                            216 passed (incl. above)
```
Full repo suite (`pytest tests/`) was also run to confirm no regressions
outside the games surface.

## 4. Files touched

- `web/api/routers/games.py` — unpack `(games, source)` from
  `game_service.list_games`, pass `source` into `GameListResponse`.
- `web/api/services/game_service.py` — `_get_game_results_db()`,
  `list_games()` DB-first/Parquet-fallback rewrite (now returns
  `Tuple[List[Dict], str]`).
- `web/api/models/schemas.py` — `GameListResponse.source` field.
- `src/game_archive.py` — `_latest_parquet()` filename-timestamp sort fix
  (mirrors `projection_service.py`'s existing fix).
- `tests/test_game_archive.py` — new DB-fallback test coverage +
  `source` assertion on the existing list-games test.
