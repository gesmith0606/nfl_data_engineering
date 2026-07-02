---
phase: 88
plan: 88-01
title: Yahoo Draft Adapter
milestone: v8.0 Live Draft Co-Pilot
status: complete
requirements:
  - YH-01  # OAuth2 + token store + automatic refresh; secrets from env only; clean re-auth on failure
  - YH-02  # YahooAdapter conforms to DraftAdapter; engine/skill run unmodified; conservative polling + backoff
  - YH-03  # offline fixture tests, >=95% skill mapping, no CI network
must_haves:
  - YahooAdapter is an isinstance() of src.draft_adapter.DraftAdapter
  - All HTTP/OAuth is stdlib-only (urllib + json) — zero new third-party deps
  - Tests are 100% offline (@pytest.mark.unit), no real Yahoo creds, all network monkeypatched
  - Fail-open everywhere (D-06): throttle/blip/missing-creds yield empty data, never crash a draft
  - Reuse generic map_picks_to_projections(picks, df, player_index={}) for Yahoo mapping
  - black + flake8 --max-line-length=100 clean
constraints:
  - CREATE ONLY NEW FILES — no edits to existing files; wiring returned as integration instructions
  - No git commits
---

# Phase 88 — Yahoo Draft Adapter

## Goal
Add Yahoo as a second live-draft platform behind the existing `DraftAdapter`
protocol, so the live engine and `draft-live` skill run unmodified. Sleeper is
the reference implementation (Phase 85-86); Yahoo mirrors its structure.

## Research findings (Yahoo Fantasy Sports API)
- Base: `https://fantasysports.yahooapis.com/fantasy/v2`; append `?format=json`.
- Auth: 3-legged OAuth2. Authorize at `.../oauth2/request_auth`, token exchange
  + refresh at `.../oauth2/get_token`. Access tokens ~3600s; refresh tokens
  **rotate** (a refresh response may omit or replace the refresh token).
- `draft_results` resource (league + team scope) returns picks mid-draft; each
  entry carries `pick`, `round`, `team_key`, `player_key` (+ `cost` for auction).
- Player identity is NOT in `draft_results` — resolve `player_key`
  (`nfl.p.<id>`) via the `players` resource (`name.full`, `display_position`,
  `editorial_team_abbr`).
- Key formats: league `nfl.l.<id>`, team `nfl.l.<id>.t.<n>`, player `nfl.p.<id>`.
- Yahoo wraps collections as numeric-string-keyed objects with a `count` field
  (not arrays), and fragments single records across lists of small dicts.
- Undocumented throttling returns **HTTP 999** — poll conservatively (~5-10s)
  and back off; references: `yfpy`, `yahoo_fantasy_api`.

## Tasks
1. `src/yahoo_oauth.py` — `YahooOAuth` token manager (stdlib): authorization URL,
   `exchange_code`, `refresh_access_token` (rotation + clear-on-fail),
   `get_access_token` (transparent refresh w/ expiry skew), JSON token persist
   under `data/yahoo_tokens.json`. Secrets from env only. (YH-01)
2. `src/yahoo_draft.py` — fetch (`fetch_yahoo_json`, fail-open incl. 999),
   collection flatteners (`_iter_collection`, `_merge_fragments`),
   settings→config mapping (scoring via Rec stat_id 11; roster
   superflex/2qb/standard), `pick_from_yahoo`, `build_players_index`,
   `parse_draft_results`, `state_from_yahoo`, `load_draft_state`,
   `resolve_active_draft`. (YH-02)
3. `src/yahoo_adapter.py` — `YahooAdapter(DraftAdapter)`; `map_picks` reuses
   `sleeper_player_map.map_picks_to_projections(..., player_index={})`. (YH-02)
4. `tests/fixtures/yahoo_draft/` — realistic `league_settings`, `draft_results`,
   `players` (QB/RB/WR/TE/K/DST), `projections_sample`. (YH-03)
5. `tests/test_yahoo_adapter.py` — offline OAuth refresh/rotation, parsing,
   scoring/roster mapping, protocol conformance, >=95% skill coverage,
   fail-open. (YH-03)

## Verification
- `python -m pytest tests/test_yahoo_adapter.py -q` → 22 passed.
- `python -m black` + `python -m flake8 --max-line-length=100` → clean.

## Out of scope / follow-up
- Live-engine wiring (`_ADAPTERS` registration) — returned as integration
  instructions for the orchestrator (no existing files edited this phase).
- Real end-to-end Yahoo OAuth dress rehearsal with live credentials.
- ESPN adapter (Phase 89).
