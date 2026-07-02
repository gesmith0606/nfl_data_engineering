---
phase: 85
plan: 85-02
title: Active-draft resolution + Sleeper player-id mapping
wave: 2
depends_on: [85-01]
requirements: [SLPR-02, SLPR-03]
files_modified:
  - src/sleeper_draft.py
  - src/sleeper_player_map.py
  - tests/test_sleeper_draft.py
  - tests/fixtures/sleeper_draft/
autonomous: true
---

# Plan 85-02: Active-Draft Resolution + Player-ID Mapping

## Objective

Let the layer find a live draft from a Sleeper username alone, and bridge Sleeper
`player_id` onto our projection player keys (`player_id` / `player_name`) with a cached
registry and ≥95% skill-position coverage. Unmatched picks are surfaced, never dropped.

## Context

- Username→user_id→leagues path already exists; reuse it. Inspect
  `web/api/routers/sleeper_user.py` and `src/sleeper_http.py` for the existing user/league
  calls before adding anything (`/v1/user/{username}`, `/v1/user/{user_id}/leagues/nfl/{season}`).
- `GET /v1/players/nfl` is ~5MB — the registry that maps Sleeper player_id →
  name/position/team. MUST be cached on disk; do not refetch per call.
- DraftBoard (Phase 86 consumer) keys players on the projection `player_id` column,
  falling back to `player_name` (see src/draft_optimizer.py:134-167). So the mapping
  output must resolve to whatever id/name our projections use. DST and K are the known
  mismatch sources — handle explicitly.
- Pick objects already carry `metadata.first_name/last_name/position/team`, giving a
  fallback identity even when the registry lookup misses.

## Tasks

<task id="85-02-1" type="execute">
<title>Resolve active/most-recent draft from a Sleeper username</title>
<read_first>
- web/api/routers/sleeper_user.py (existing username→user_id→leagues resolution to reuse)
- src/sleeper_http.py (user/league helpers + the draft helpers from 85-01)
- src/sleeper_draft.py (DraftState + load_draft_state from 85-01)
</read_first>
<action>
Add resolve_active_draft(username: str, season: str, league_id: Optional[str] = None)
-> dict to src/sleeper_draft.py. It: resolves username → user_id (reuse the existing
sleeper_http user helper; if none exists, add get_user(username) following the same
fail-open pattern), lists the user's NFL leagues for the season, and for each league
calls get_drafts_for_league. Selection rule: prefer a draft with status in
{"drafting","paused"}; else the most-recent by start_time/last_picked; if league_id is
provided, restrict to that league. Return a small dict:
{found: bool, draft_id: str, league_id: str, status: str, candidates: list[{draft_id,
league_id, status, name}]}. When zero or multiple active drafts exist, found stays the
best single pick but candidates lists all options for the caller (the skill) to
disambiguate. Never raise — empty resolution returns {found: False, candidates: []}.
</action>
<acceptance_criteria>
- src/sleeper_draft.py contains "def resolve_active_draft(".
- With sleeper_http calls monkeypatched to fixture data (a user with one drafting league),
  resolve_active_draft returns found True and the expected draft_id.
- With monkeypatched empty responses, resolve_active_draft returns
  {"found": False, ...} and does NOT raise.
- A two-league fixture where both have drafts returns the drafting-status one as
  draft_id and lists both under candidates.
</acceptance_criteria>
</task>

<task id="85-02-2" type="execute">
<title>Cached Sleeper player registry + player-id mapping</title>
<read_first>
- src/sleeper_http.py (fetch_sleeper_json for the registry GET)
- src/utils.py (existing cache/IO helpers + path conventions to match)
- src/draft_optimizer.py:40-107 (compute_value_scores — the projection frame whose
  player_id/player_name keys the mapping must target)
- data/adp_latest.csv (player name/position/team keys used elsewhere)
</read_first>
<action>
Create src/sleeper_player_map.py providing:
- load_sleeper_players(force_refresh: bool = False, max_age_days: int = 7) -> dict —
  returns the Sleeper player registry, cached at data/bronze/players/sleeper_players.json.
  On cache miss or staleness, GET https://api.sleeper.app/v1/players/nfl via
  fetch_sleeper_json and write the cache (create parent dir). On fetch failure, fall back
  to an existing cache if present; only return {} when neither is available (fail-open).
- build_player_index(registry: dict) -> dict — normalize each Sleeper entry to a lookup
  keyed by sleeper_player_id → {full_name, position, team, normalized_name}. Use a
  normalize_name() helper (lowercase, strip punctuation/suffixes Jr/Sr/III) shared with
  matching.
- map_picks_to_projections(picks, projections_df) -> tuple[list[dict], list[PickEvent]]
  — for each PickEvent, resolve to a projection row by (normalized_name + position) with
  team as a tiebreaker; return (matched rows incl. our player_id/player_name, list of
  unmatched PickEvents). DST/K that have no projection row are returned in unmatched, not
  silently dropped. Log a single summary WARNING with the match rate and the count of
  unmatched by position.
Provide mapping_coverage(matched, unmatched, positions=("QB","RB","WR","TE")) -> float
helper returning the skill-position match rate for the test gate.
</action>
<acceptance_criteria>
- src/sleeper_player_map.py contains "def load_sleeper_players(",
  "def build_player_index(", "def map_picks_to_projections(", and "def normalize_name(".
- load_sleeper_players writes/reads data/bronze/players/sleeper_players.json (asserted via
  a tmp-path monkeypatch in test; no real 5MB fetch in tests).
- map_picks_to_projections returns unmatched picks as a non-dropped list (a DST fixture
  pick with no projection row appears in the unmatched return).
- On the recorded fixture draft + a representative projection frame, mapping_coverage(...)
  for QB/RB/WR/TE is ≥ 0.95 (asserted in test).
</acceptance_criteria>
</task>

<task id="85-02-3" type="tdd">
<title>Tests for resolution + mapping (offline, fixture-driven)</title>
<read_first>
- tests/test_sleeper_draft.py (extend the 85-01 test module)
- src/sleeper_draft.py and src/sleeper_player_map.py (units under test)
- tests/fixtures/sleeper_draft/ (existing fixtures from 85-01)
</read_first>
<action>
Add fixtures: a small sleeper_players_sample.json (a few dozen entries covering the
fixture draft's picked players across QB/RB/WR/TE/K/DST) and a projections_sample.csv/json
matching the projection schema (player_id, player_name, position, team). Extend
tests/test_sleeper_draft.py with @pytest.mark.unit tests that: monkeypatch the sleeper_http
user/league/draft calls to fixtures and assert resolve_active_draft selection logic
(active-preferred, candidate listing, empty→found False); monkeypatch load_sleeper_players
to the sample registry (tmp cache path) and assert build_player_index shape; assert
map_picks_to_projections returns ≥95% skill-position coverage on the fixture and returns
DST/K with no projection in the unmatched list; assert normalize_name strips a "Jr"/"III"
suffix. No real network in any test.
</action>
<acceptance_criteria>
- tests/fixtures/sleeper_draft/sleeper_players_sample.json and a projections sample
  fixture both exist and are valid (json/csv loads without error).
- tests/test_sleeper_draft.py contains tests referencing resolve_active_draft and
  map_picks_to_projections.
- `python -m pytest tests/test_sleeper_draft.py -q` exits 0.
- A coverage assertion `assert ... >= 0.95` for skill positions is present and passes.
- grep of tests/test_sleeper_draft.py shows no real api.sleeper.app fetch outside
  monkeypatch setup.
</acceptance_criteria>
</task>

## Verification

- `source venv/bin/activate && python -m pytest tests/test_sleeper_draft.py -q` → exits 0.
- `python -m pytest tests/ -q` → no regressions across the suite.
- `python -m black --check src/sleeper_draft.py src/sleeper_player_map.py tests/test_sleeper_draft.py`
  → clean (or format).
- Manual smoke (operator-run, network, NOT in CI): `python -c "from src.sleeper_draft import resolve_active_draft; print(resolve_active_draft('<your_username>', '2026'))"`
  resolves a real draft when one exists.

## must_haves

1. `resolve_active_draft(username, season)` returns a usable draft_id (+ candidates) with
   no manual ID lookup, and fails open to {found: False}. (SLPR-02)
2. A cached Sleeper player registry maps sleeper_player_id → our projection player keys,
   achieving ≥95% skill-position coverage on the fixture. (SLPR-03)
3. Unmatched picks (DST/K/obscure) are surfaced in a returned list and logged, never
   silently dropped. (SLPR-03)
