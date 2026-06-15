---
phase: 85
plan: 85-01
title: Sleeper draft endpoints + normalized draft-state models
wave: 1
depends_on: []
requirements: [SLPR-01, SLPR-04]
files_modified:
  - src/sleeper_http.py
  - src/sleeper_draft.py
  - tests/fixtures/sleeper_draft/
  - tests/test_sleeper_draft.py
autonomous: true
---

# Plan 85-01: Sleeper Draft Endpoints + Normalized Models

## Objective

Add the four Sleeper draft read endpoints to the existing fail-open HTTP wrapper, and
define typed `DraftState` / `PickEvent` models in a new `src/sleeper_draft.py` data
module. Record a real completed-draft fixture and prove parsing + model construction
offline. This is the read/normalize foundation; no live loop, no mapping, no advice.

## Context

- All Sleeper HTTP goes through `src/sleeper_http.py::fetch_sleeper_json()` (D-01 LOCKED).
  It is stdlib-only (`urllib`), fail-open: returns `{}`/`[]` on any error, never raises.
- Sleeper draft REST surface (no auth):
  - `GET /v1/league/{league_id}/drafts` → list of drafts
  - `GET /v1/draft/{draft_id}` → status, type, settings, draft_order, slot_to_roster_id
  - `GET /v1/draft/{draft_id}/picks` → list of pick objects
  - `GET /v1/draft/{draft_id}/traded_picks` → list of traded picks
- Pick object fields: `pick_no`, `round`, `draft_slot`, `roster_id`, `picked_by`,
  `player_id`, `is_keeper`, `metadata{first_name,last_name,position,team,status}`.
- Models live in a NEW `src/sleeper_draft.py` to keep `sleeper_http.py` a thin transport
  wrapper. Phase 86's engine imports from `sleeper_draft.py`.

## Tasks

<task id="85-01-1" type="execute">
<title>Add four draft-read helpers to sleeper_http.py</title>
<read_first>
- src/sleeper_http.py (the full fail-open pattern + module docstring to extend)
</read_first>
<action>
Add four module-level functions to src/sleeper_http.py, each building the Sleeper v1
URL and delegating to fetch_sleeper_json (do NOT add a new transport path):
- get_drafts_for_league(league_id: str, timeout: int = 15) -> list — GETs
  https://api.sleeper.app/v1/league/{league_id}/drafts ; if fetch_sleeper_json returns
  a non-list (the {} fail-open default), return [] so callers can iterate safely.
- get_draft(draft_id: str, timeout: int = 15) -> dict — GETs
  https://api.sleeper.app/v1/draft/{draft_id} ; return {} on non-dict.
- get_draft_picks(draft_id: str, timeout: int = 15) -> list — GETs
  https://api.sleeper.app/v1/draft/{draft_id}/picks ; return [] on non-list.
- get_traded_picks(draft_id: str, timeout: int = 15) -> list — GETs
  https://api.sleeper.app/v1/draft/{draft_id}/traded_picks ; return [] on non-list.
Each guards empty id (return [] / {} with a logger.warning, mirroring the empty-URL
guard already in fetch_sleeper_json). Add Google-style docstrings and full type hints.
Extend the module "Public API" docstring section to list the four new helpers.
</action>
<acceptance_criteria>
- src/sleeper_http.py contains "def get_drafts_for_league(", "def get_draft(",
  "def get_draft_picks(", and "def get_traded_picks(".
- Each new function's body references "api.sleeper.app/v1" and calls fetch_sleeper_json.
- get_draft_picks / get_drafts_for_league / get_traded_picks normalize a non-list
  fail-open return to [] (assert in test: monkeypatched fetch_sleeper_json returning {}
  yields [] from these three; get_draft yields {}).
- `python -c "import src.sleeper_http as s; print(s.get_draft_picks(''))"` prints `[]`.
</acceptance_criteria>
</task>

<task id="85-01-2" type="execute">
<title>Define PickEvent and DraftState models in src/sleeper_draft.py</title>
<read_first>
- src/sleeper_http.py (after task 1 — the helpers these models will be built from)
- src/draft_optimizer.py:109-170 (DraftBoard keys on a "player_id" column, falling back
  to "player_name" — DraftState must carry both so Phase 86 can drive the board)
- src/config.py:44 and src/config.py:232 (SCORING_CONFIGS / ROSTER_CONFIGS keys that
  league settings normalize onto)
- .claude/rules/coding-style.md (frozen dataclasses preferred for DTOs)
</read_first>
<action>
Create src/sleeper_draft.py with two frozen dataclasses and constructor helpers:
- PickEvent(pick_no:int, round:int, draft_slot:int, roster_id:Optional[int],
  picked_by:str, sleeper_player_id:str, first_name:str, last_name:str, position:str,
  team:str, is_keeper:bool). Add classmethod from_sleeper_pick(raw: dict) that reads
  the pick object + nested metadata defensively (missing keys → "" / 0 / False, never
  KeyError). full_name property returns "first_name last_name".stripped.
- DraftState(draft_id:str, status:str, draft_type:str, season:str, n_teams:int,
  rounds:int, scoring_format:str, roster_format:str, draft_order:dict,
  slot_to_roster_id:dict, picks:tuple[PickEvent, ...], traded_picks:tuple[dict, ...]).
  Add classmethod from_sleeper(draft:dict, picks:list, traded:list) that maps the
  Sleeper draft.settings + metadata onto our SCORING_CONFIGS / ROSTER_CONFIGS keys
  (e.g. ppr rec value 1.0→"ppr", 0.5→"half_ppr", 0.0→"standard"; team count + roster
  positions → "standard"/"superflex"/"2qb" best-effort with "standard" default) and
  builds the PickEvent tuple via PickEvent.from_sleeper_pick. status/draft_type read
  straight from the draft dict; missing → "" defaults. No network calls in this module-
  level constructor — it operates purely on already-fetched dicts.
Add a thin convenience load_draft_state(draft_id) that calls the sleeper_http helpers
and assembles a DraftState (the ONE place that touches the network).
</action>
<acceptance_criteria>
- src/sleeper_draft.py contains "class PickEvent" and "class DraftState" both decorated
  @dataclass(frozen=True).
- src/sleeper_draft.py contains "def from_sleeper_pick(" and "def from_sleeper(" and
  "def load_draft_state(".
- PickEvent.from_sleeper_pick({}) returns a PickEvent with pick_no==0 and is_keeper
  False (no exception) — proves defensive parsing.
- DraftState.from_sleeper maps a settings dict with rec==0.5 to scoring_format
  "half_ppr" (asserted in test).
- `python -c "import src.sleeper_draft"` exits 0.
</acceptance_criteria>
</task>

<task id="85-01-3" type="tdd">
<title>Record a real-draft fixture and unit-test parsing + models offline</title>
<read_first>
- src/sleeper_draft.py (the models + constructors under test)
- tests/test_draft_optimizer.py (existing pytest style/markers in this repo)
- tests/fixtures/ (existing fixture layout conventions)
</read_first>
<action>
Capture one real completed Sleeper draft as a static fixture (a public/mock draft is
fine) under tests/fixtures/sleeper_draft/: save the raw JSON for get_draft (draft.json),
get_draft_picks (picks.json), and get_traded_picks (traded.json). Trim picks.json to a
representative subset if large but keep ≥ one full round plus picks at every position
(QB/RB/WR/TE/K/DST) and at least one is_keeper:true row if present. Write
tests/test_sleeper_draft.py that loads the fixtures from disk (NO network — monkeypatch
or read files directly), asserts: the four sleeper_http helpers normalize fail-open
returns ([] / {}) when fetch_sleeper_json is monkeypatched to return {}; PickEvent
parsing produces correct pick_no/round/position/full_name for known fixture rows;
DraftState.from_sleeper yields the expected n_teams, rounds, draft_type, and
scoring_format; defensive parsing of an empty/garbage pick dict does not raise. Mark
tests @pytest.mark.unit.
</action>
<acceptance_criteria>
- tests/fixtures/sleeper_draft/draft.json, picks.json, traded.json all exist and are
  valid JSON (`python -c "import json,glob; [json.load(open(f)) for f in glob.glob('tests/fixtures/sleeper_draft/*.json')]"` exits 0).
- tests/test_sleeper_draft.py exists and contains at least one test asserting
  scoring_format mapping and one asserting fail-open list normalization.
- `python -m pytest tests/test_sleeper_draft.py -q` exits 0.
- No test in tests/test_sleeper_draft.py performs a real network call (grep shows no
  urlopen / requests / api.sleeper.app literal outside monkeypatch setup).
</acceptance_criteria>
</task>

## Verification

- `source venv/bin/activate && python -m pytest tests/test_sleeper_draft.py -q` → exits 0.
- `python -m pytest tests/ -q -k "sleeper or draft"` → no regressions in existing draft tests.
- `python -m black --check src/sleeper_draft.py src/sleeper_http.py tests/test_sleeper_draft.py` → clean (or run black to format).
- `python -c "import src.sleeper_http as s, src.sleeper_draft as d"` → exits 0.

## must_haves

1. The four draft endpoints exist on `src/sleeper_http.py`, route through
   `fetch_sleeper_json`, and preserve the fail-open ([]/{}) contract. (SLPR-01)
2. `PickEvent` and `DraftState` exist in `src/sleeper_draft.py`, parse Sleeper draft
   JSON defensively, and map league settings onto SCORING_CONFIGS/ROSTER_CONFIGS keys. (SLPR-04)
3. A recorded real-draft fixture + offline unit tests pass and perform no network I/O. (SLPR-04)
