# Matchup View — API Contract

**Phase:** 64-matchup-view-completion
**Plan:** 64-01 (Wave 1 — inventory/contract)
**Date:** 2026-04-17
**Implemented by:** 64-02 (rosters + current-week) and 64-03 (defense-metrics). Frontend wiring lands in 64-04.

This document locks down the three new endpoints that replace the placeholders documented in `PLACEHOLDER-INVENTORY.md`. Plans 64-02 and 64-03 MUST implement the schemas below unchanged. Frontend 64-04 MUST call these shapes unchanged.

All endpoints live under the existing `web/api` FastAPI app. New router file: `web/api/routers/teams.py` (not yet created — 64-02 scope). New service module: `web/api/services/team_service.py` (64-02 scope). All parquet reads use `download_latest_parquet()` from `src/utils.py` per project convention (`CLAUDE.md` S3 Read Rule).

---

## Endpoint A — Current-Week Helper

**Implements:** MTCH-04

### Signature

```
GET /api/teams/current-week
```

### Request

No query params.

### Response

```json
{
  "season": 2025,
  "week": 22,
  "source": "fallback"
}
```

### Response schema (Pydantic)

```python
class CurrentWeekResponse(BaseModel):
    season: int              # e.g., 2025
    week: int                # 1..22 (includes postseason)
    source: Literal["schedule", "fallback"]
```

### Logic

1. Determine candidate seasons: today's calendar year (`YYYY`), then `YYYY - 1`.
2. For each candidate, attempt `download_latest_parquet(local_path=f"data/bronze/schedules/season={YYYY}/")`.
3. On the first season file that loads, scan rows for:
   - `today() >= gameday` and `today() <= gameday + 6 days`
   - If matched: return `(season=YYYY, week=row.week, source="schedule")`.
4. If no row matches today's date in either candidate season (offseason case):
   - Load the **max season present** in `data/bronze/schedules/`.
   - Return `(season=max_season, week=max(df.week), source="fallback")`.
5. If no schedule files exist at all: `HTTPException(503, detail="No schedule data available")`.

### Data source

- `data/bronze/schedules/season=YYYY/schedules_*.parquet`
- Columns used: `season, week, gameday`

### Error modes

| Condition | HTTP | Detail |
|---|---|---|
| No schedule parquet for any season | 503 | "No schedule data available" |
| Schedule file unreadable | 500 | pass-through exception |

### Frontend caller

Replaces `useState(2026)` and `useState(1)` in `MatchupView` (matchup-view.tsx:783-784). 64-04 adds:

```typescript
const { data: currentWeek } = useQuery(currentWeekQueryOptions());
const [season, setSeason] = useState(currentWeek?.season ?? 2025);
const [week, setWeek] = useState(currentWeek?.week ?? 1);
```

Frontend additionally displays a banner when `source === "fallback"` reading _"2026 season not yet available — showing latest 2025 data."_

---

## Endpoint B — Team Roster (Offensive Starters + Defensive Starters)

**Implements:** MTCH-02 (defense) and MTCH-01 (OL portion of offense)

### Signature

```
GET /api/teams/{team}/roster?season=YYYY&week=WW&side={offense|defense|all}
```

### Request

| Param | Type | Required | Default | Validation |
|---|---|---|---|---|
| `team` | str (path) | yes | — | Must be one of 32 team codes in `TEAM_NAMES` (`web/api/config.py`). 400 if unknown. |
| `season` | int | yes | — | `>= 2016, <= 2030`. |
| `week` | int | yes | — | `>= 1, <= 22` (includes postseason). |
| `side` | enum str | no | `"all"` | `"offense"` / `"defense"` / `"all"`. |

### Response

```json
{
  "team": "KC",
  "season": 2025,
  "week": 22,
  "side": "all",
  "fallback": false,
  "fallback_season": null,
  "roster": [
    {
      "player_id": "00-0033873",
      "player_name": "Patrick Mahomes",
      "team": "KC",
      "position": "QB",
      "depth_chart_position": "QB",
      "jersey_number": 15,
      "status": "ACT",
      "snap_pct_offense": 1.0,
      "snap_pct_defense": 0.0,
      "injury_status": null,
      "slot_hint": "QB1"
    }
  ]
}
```

### Response schema (Pydantic)

```python
from typing import Literal, Optional

class RosterPlayer(BaseModel):
    player_id: str                              # gsis_id from roster parquet
    player_name: str
    team: str                                   # 3-letter team code
    position: str                               # roster.position (coarse: QB/RB/WR/TE/OL/DB/DL/LB)
    depth_chart_position: Optional[str]         # granular: LT? no, but T/G/C/OLB/ILB/CB/FS/SS/DE/DT/NT
    jersey_number: Optional[int]
    status: str                                 # ACT/RES/CUT/...
    snap_pct_offense: Optional[float]           # 0..1 from bronze/players/snaps, joined on player_name
    snap_pct_defense: Optional[float]           # 0..1
    injury_status: Optional[str]                # Active/Questionable/Doubtful/Out/IR/PUP
    slot_hint: Optional[str]                    # QB1/RB1/WR1/LT/RT/DE1/CB1/... assigned by starter-selection logic

class TeamRosterResponse(BaseModel):
    team: str
    season: int
    week: int
    side: Literal["offense", "defense", "all"]
    fallback: bool                              # True if requested season/week not present; response uses latest available
    fallback_season: Optional[int]              # populated when fallback=True
    roster: list[RosterPlayer]
```

### Logic

1. Load latest `data/bronze/players/rosters/season={season}/rosters_*.parquet` via `download_latest_parquet`.
2. If file missing: find max season present in `data/bronze/players/rosters/`, load its latest snapshot, set `fallback=True`, `fallback_season=<max_season>`.
3. Filter to `team == {team}` and `status in ('ACT', 'RES')`.
4. Load snap counts: `data/bronze/players/snaps/season={season}/week={week}/snaps_*.parquet`. Left-join to roster on `player_name` (fallback key — no clean `player_id` overlap between the two tables). Populate `snap_pct_offense = offense_pct`, `snap_pct_defense = defense_pct`.
   - If the requested `(season, week)` snap file is missing, search `week=W-1, W-2, ...` until a file is found within the same season; if none, leave snap fields `null`.
5. `side == "offense"`:
   - Keep rows where `position in ('QB','RB','WR','TE','FB','OL') OR depth_chart_position in ('QB','RB','WR','TE','FB','T','G','C')`.
   - Assign `slot_hint`:
     - QB: top `snap_pct_offense` → `QB1`, 2nd → `QB2`.
     - RB: top two → `RB1`, `RB2`.
     - WR: top three → `WR1`, `WR2`, `WR3`.
     - TE: top one → `TE1`.
     - OL — assign from `depth_chart_position`:
       - Single `C` with highest `snap_pct_offense` → `C`.
       - Top two `G` rows by snap → `LG`, `RG` (LG = first in sorted order).
       - Top two `T` rows by snap → `LT`, `RT` (LT = first in sorted order).
     - Remaining offensive players have `slot_hint = null`.
6. `side == "defense"`:
   - Keep rows where `position in ('DE','DT','LB','CB','S','DB','DL') OR depth_chart_position in ('DE','DT','NT','OLB','ILB','MLB','LB','CB','FS','SS','DB')`.
   - Assign `slot_hint`:
     - `DE`/`OLB` pooled → top two by `snap_pct_defense` → `DE1`, `DE2`.
     - `DT`/`NT` pooled → top two → `DT1`, `DT2`.
     - `ILB`/`MLB`/`LB` pooled → top three → `LB1`, `LB2`, `LB3`.
     - `CB` → top two → `CB1`, `CB2`.
     - `FS` → top one → `FS`. `SS` → top one → `SS`. If only generic `DB` rows present, first → `SS`, second → `FS`.
     - Remaining defensive players have `slot_hint = null`.
7. `side == "all"`: union of 5 and 6.
8. Sort output by (`slot_hint not null first`, `depth_chart_position`, `snap_pct_* desc`).

### Error modes

| Condition | HTTP | Detail |
|---|---|---|
| Invalid team code | 400 | `"Unknown team: {team}"` |
| Invalid season/week range | 422 | FastAPI auto-validation |
| No roster data for any season | 503 | `"Roster data unavailable"` |
| Roster present but zero rows for team | 404 | `"No roster entries for team={team}"` |

### Data source

- Primary: `data/bronze/players/rosters/season=YYYY/rosters_*.parquet`
  - **source:** columns `season, team, position, depth_chart_position, jersey_number, status, player_name, player_id, week, football_name, age` (see `src/nfl_data_integration.py::fetch_rosters`)
- Snap-pct join: `data/bronze/players/snaps/season=YYYY/week=WW/snaps_*.parquet`
  - **source:** columns `player, position, team, offense_pct, defense_pct, st_pct` (note: snap column is `player` not `player_name` — join-side rename required)

### Frontend caller

- Replaces `buildDefensiveRoster(team)` at matchup-view.tsx:718-750 — becomes `buildDefensiveRosterFromApi(rosterResponse)` consuming `side=defense` rows and mapping `slot_hint` → display slot.
- Extends `buildOffensiveRoster` at matchup-view.tsx:142-188 OL branch — OL slots hydrated from `side=offense` rows filtered by `slot_hint in ('LT','LG','C','RG','RT')`.

---

## Endpoint C — Team Defensive Metrics

**Implements:** MTCH-03

### Signature

```
GET /api/teams/{team}/defense-metrics?season=YYYY&week=WW
```

### Request

| Param | Type | Required | Default | Validation |
|---|---|---|---|---|
| `team` | str (path) | yes | — | One of 32 team codes. 400 if unknown. |
| `season` | int | yes | — | `>= 2016, <= 2030`. |
| `week` | int | yes | — | `>= 1, <= 22`. |

### Response

```json
{
  "team": "KC",
  "season": 2025,
  "requested_week": 22,
  "source_week": 22,
  "fallback": false,
  "fallback_season": null,
  "overall_def_rating": 78,
  "def_sos_score": 0.043,
  "def_sos_rank": 9,
  "adj_def_epa": -0.08,
  "positional": [
    {"position": "QB", "avg_pts_allowed": 15.2, "rank": 8,  "rating": 89},
    {"position": "RB", "avg_pts_allowed": 14.1, "rank": 15, "rating": 78},
    {"position": "WR", "avg_pts_allowed": 28.9, "rank": 22, "rating": 65},
    {"position": "TE", "avg_pts_allowed":  7.4, "rank":  4, "rating": 95}
  ]
}
```

### Response schema (Pydantic)

```python
from typing import Literal, Optional

class PositionalDefenseRank(BaseModel):
    position: Literal["QB", "RB", "WR", "TE"]
    avg_pts_allowed: float
    rank: int                                   # 1..32 (1 = best defense = fewest pts allowed)
    rating: int                                 # 50..99 (1-to-1 from rank: 101 - round(rank/32 * 49 + 50))

class TeamDefenseMetricsResponse(BaseModel):
    team: str
    season: int
    requested_week: int
    source_week: int                            # actual week whose data was used (may differ if fallback)
    fallback: bool
    fallback_season: Optional[int]
    overall_def_rating: int                     # 50..99, derived from def_sos_rank
    def_sos_score: Optional[float]
    def_sos_rank: Optional[int]
    adj_def_epa: Optional[float]
    positional: list[PositionalDefenseRank]     # always returns all 4 positions; NaN avg_pts_allowed surfaces as None on 404 positions
```

### Logic

1. Load latest `data/silver/defense/positional/season={season}/opp_rankings_*.parquet`.
   - If missing: use `max(seasons_present)`; set `fallback=True`, `fallback_season=<that>`.
2. Filter to `team == {team}` and `week == {week}`.
   - If that week has no rows (data lag): walk backward `week-1, week-2, ...` within same season until a row set is found; `source_week = that week`.
   - If no week has data for this team/season: walk to prior season; continue `fallback=True`.
3. Build `positional[]` with exactly 4 entries (QB/RB/WR/TE). If a position is missing from the week's rows (unlikely but defensive), set `avg_pts_allowed = null`, `rank = null`, `rating = 72` (positional median fallback — document in response field description).
4. `rating = 101 - round(rank / 32 * 49 + 50)` clipped to `[50, 99]`. Verified: `rank=1 → 101 - round(1/32*49+50) = 101 - 52 = 49 → clip to 50; rank=32 → 101 - round(99) = 2 → clip to 50`. **Bug check:** the formula in 64-01 plan text (`rating = 101 - round(rank/32 * 49 + 50)`) is backwards for rank=1. Use instead: `rating = round((1 - (rank - 1) / 31) * 49 + 50)` → rank 1 → 99, rank 32 → 50. This is the corrected formula; plans 64-03 MUST implement this version.
5. Load latest `data/silver/teams/sos/season={season}/sos_*.parquet`. Filter to `team == {team}`, `week == source_week`.
   - Extract `def_sos_score`, `def_sos_rank`, `adj_def_epa`.
   - `overall_def_rating = round((1 - (def_sos_rank - 1) / 31) * 49 + 50)` clipped to `[50, 99]`.
   - If `def_sos_rank` is NaN (week 1, no prior aggregate): use fallback `overall_def_rating = 72` (league median) and leave `def_sos_rank = None`.

### Error modes

| Condition | HTTP | Detail |
|---|---|---|
| Unknown team | 400 | `"Unknown team: {team}"` |
| Invalid season/week | 422 | FastAPI auto |
| No silver/defense data at all | 503 | `"Defense metrics unavailable"` |
| Team has no rows across all seasons | 404 | `"No defense metrics for team={team}"` |

### Data source

- Positional ranks: `data/silver/defense/positional/season=YYYY/opp_rankings_*.parquet`
  - **source:** columns `season, week, team, position, avg_pts_allowed, rank`
- Team-level SOS: `data/silver/teams/sos/season=YYYY/sos_*.parquet`
  - **source:** columns `team, season, week, def_sos_score, adj_def_epa, def_sos_rank`

### Frontend caller

- Replaces the hardcoded `defaults` dict in `buildDefensiveRoster` (matchup-view.tsx:722-734). Each defensive slot's rating becomes a function of `positional[]`:
  - DE1/DE2/DT1/DT2: use `overall_def_rating` (no per-DL-position breakdown exists) with ±small perturbation per slot index (deterministic, not `slotHash`) — or simpler: all four DL slots share `overall_def_rating`.
  - LB1/LB2/LB3: average of `positional[RB].rating` and `positional[TE].rating` (LBs cover both).
  - CB1/CB2: `positional[WR].rating`.
  - SS: average of `positional[TE].rating` and `positional[WR].rating`.
  - FS: `positional[WR].rating`.
- Provides tooltip data for `MatchupAdvantages` (matchup-view.tsx:574-645): the diff box shows `positional.rank` and `avg_pts_allowed` inline ("Team ranks 22nd vs WRs, allowing 28.9 pts/g").

---

## Pydantic Schema Block (paste into `web/api/models/schemas.py` as-is)

Plans 64-02 and 64-03 MUST NOT modify the shapes below. If a shape needs changing mid-execution, return a checkpoint and re-confirm the contract.

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- Endpoint A: current-week ----------

class CurrentWeekResponse(BaseModel):
    season: int = Field(..., ge=2016, le=2030)
    week: int = Field(..., ge=1, le=22)
    source: Literal["schedule", "fallback"]


# ---------- Endpoint B: team roster ----------

class RosterPlayer(BaseModel):
    player_id: str
    player_name: str
    team: str
    position: str
    depth_chart_position: Optional[str] = None
    jersey_number: Optional[int] = None
    status: str
    snap_pct_offense: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    snap_pct_defense: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    injury_status: Optional[str] = None
    slot_hint: Optional[str] = None  # QB1, RB1, LT, DE1, CB1, etc.


class TeamRosterResponse(BaseModel):
    team: str
    season: int
    week: int
    side: Literal["offense", "defense", "all"]
    fallback: bool = False
    fallback_season: Optional[int] = None
    roster: list[RosterPlayer]


# ---------- Endpoint C: defense metrics ----------

class PositionalDefenseRank(BaseModel):
    position: Literal["QB", "RB", "WR", "TE"]
    avg_pts_allowed: Optional[float] = None  # None if position missing from week's data
    rank: Optional[int] = Field(default=None, ge=1, le=32)
    rating: int = Field(..., ge=50, le=99)


class TeamDefenseMetricsResponse(BaseModel):
    team: str
    season: int
    requested_week: int
    source_week: int
    fallback: bool = False
    fallback_season: Optional[int] = None
    overall_def_rating: int = Field(..., ge=50, le=99)
    def_sos_score: Optional[float] = None
    def_sos_rank: Optional[int] = Field(default=None, ge=1, le=32)
    adj_def_epa: Optional[float] = None
    positional: list[PositionalDefenseRank]  # always 4 entries: QB, RB, WR, TE
```

---

## Fallback Matrix

| Endpoint | Requested condition | Action | Response signal |
|---|---|---|---|
| `/api/teams/current-week` | Today inside a scheduled gameday+6d window | Return matched (season, week) | `source: "schedule"` |
| `/api/teams/current-week` | Today in offseason / no schedule row matches | Return max (season, week) from latest schedule parquet | `source: "fallback"` |
| `/api/teams/current-week` | No schedule parquet for any season exists | HTTP 503 | — |
| `/api/teams/{team}/roster` | Requested season has no roster parquet (e.g., 2026) | Load max-season snapshot instead | `fallback: true, fallback_season: <max>` |
| `/api/teams/{team}/roster` | Requested (season, week) has no snap file | Walk back weeks within same season; leave snap fields `null` if none found | `snap_pct_offense/defense: null` on affected rows |
| `/api/teams/{team}/roster` | Team has zero active rows for the season | HTTP 404 | — |
| `/api/teams/{team}/defense-metrics` | Requested week has no positional data | Walk back within season to latest week with data | `source_week < requested_week` |
| `/api/teams/{team}/defense-metrics` | Requested season missing entirely | Load max-season silver/defense parquet | `fallback: true, fallback_season: <max>` |
| `/api/teams/{team}/defense-metrics` | Week 1 SOS scores are NaN (no prior aggregate yet) | Set `def_sos_score/rank = null`, `overall_def_rating = 72` (league median) | Non-null `positional[]` still returned from opp_rankings |
| `/api/teams/{team}/defense-metrics` | Requested position missing from week's rows | `avg_pts_allowed=null, rank=null, rating=72` | Position entry still present in `positional[]` |

---

## Requirements Coverage

| Requirement | Endpoint | Response field(s) |
|---|---|---|
| MTCH-01 (offensive roster w/ real ratings) | Endpoint B (`side=offense`) | `roster[]` with OL rows where `slot_hint in ('LT','LG','C','RG','RT')` — OL rating comes from Endpoint C `overall_def_rating` proxy applied to opponent side; **this plan's scope is the API shape, not the rating algorithm** |
| MTCH-02 (defensive roster = real NFL data) | Endpoint B (`side=defense`) | `roster[]` with 11 `slot_hint` assignments |
| MTCH-03 (matchup advantages from real data) | Endpoint C | `positional[]`, `overall_def_rating`, `def_sos_rank` |
| MTCH-04 (schedule-aware default week) | Endpoint A | `season`, `week`, `source` |
