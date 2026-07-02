# Phase 85: Sleeper Draft Data Layer - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Source:** Scoping conversation (v8.0 Live Draft Co-Pilot)

<domain>
## Phase Boundary

Deliver the **data layer** for a live Sleeper draft: the Sleeper draft endpoints (behind the existing fail-open HTTP wrapper), resolution of the active draft from a username, a cached Sleeper-player-id → projection-player map, and normalized typed draft-state models. This phase produces NO live loop and NO advice — it is the read/normalize foundation Phase 86 consumes.
</domain>

<decisions>
## Implementation Decisions (locked)

### Platform & transport
- Sleeper only (v1). Public REST API at `https://api.sleeper.app/v1`, no auth.
- ALL Sleeper calls go through `src/sleeper_http.py::fetch_sleeper_json()` (D-01 locked in prior Sleeper work) — preserve the fail-open contract: return `{}`/`[]` on any network/HTTP/parse error, never raise.
- Zero new third-party dependencies — stdlib `urllib` only, matching existing `sleeper_http.py` (Lambda/CI constraint).

### Endpoints to add
- `get_drafts_for_league(league_id)` → `GET /v1/league/{league_id}/drafts`
- `get_draft(draft_id)` → `GET /v1/draft/{draft_id}` (status, settings, draft_order, slot_to_roster_id)
- `get_draft_picks(draft_id)` → `GET /v1/draft/{draft_id}/picks`
- `get_traded_picks(draft_id)` → `GET /v1/draft/{draft_id}/traded_picks`

### Active-draft resolution (SLPR-02)
- Reuse the existing username→user_id→leagues path already in `src/sleeper_http.py` / `web/api/routers/sleeper_user.py`.
- From the league(s), list drafts and select the active (`status in {drafting, paused}`) else most-recent (`status == complete` / pre_draft) draft. If multiple leagues, prefer the one with an active draft; otherwise return the candidate list for the user to disambiguate.
- Return `draft_id` + normalized league scoring (PPR/Half-PPR/Standard) + roster format + draft order.

### Player-ID mapping (SLPR-03) — highest risk
- Source of truth: `GET /v1/players/nfl` (~5MB). MUST cache locally (e.g. `data/bronze/players/sleeper_players.json` or similar) with a freshness check; do not refetch every call.
- Map Sleeper `player_id` → our projection player keyed by name + position + team (the keys our projections/ADP already use).
- Target ≥95% match on skill positions (QB/RB/WR/TE). DST and K are known mismatch sources — handle explicitly. Unmatched picks must be surfaced/logged, never silently dropped.

### Models (SLPR-04)
- `PickEvent`: pick_no, round, draft_slot, roster_id, picked_by (user_id), sleeper_player_id, mapped player (name/pos/team), is_keeper, metadata.
- `DraftState`: draft_id, status, draft_type (snake/linear/auction), settings (teams, rounds, scoring, roster slots), draft_order (slot→roster/user), picks (list[PickEvent]), traded_picks.
- Where these models live: prefer a new `src/sleeper_draft.py` (data layer) to keep `sleeper_http.py` a thin transport wrapper. Phase 86's engine imports from here.

### Testing
- Record a real completed Sleeper draft (picks + draft + players subset) as a fixture under `tests/fixtures/`. Unit-test parsing, mapping coverage, and model construction against it. No live network in tests.

### Claude's Discretion
- Exact module/file names, cache file path + TTL strategy, dataclass vs pydantic for models (match whatever the repo already uses), and fixture-trimming approach.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Sleeper integration (reuse, do not rebuild)
- `src/sleeper_http.py` — `fetch_sleeper_json()` fail-open wrapper + current user/league/roster calls. New draft endpoints extend this pattern.
- `web/api/routers/sleeper_user.py` — username→user_id→leagues→rosters flow; SLPR-02 reuses this resolution path.

### Draft logic the data must feed (Phase 86 consumer, read for shape)
- `src/draft_optimizer.py` — `DraftBoard`, `DraftAdvisor`, `compute_value_scores()`, VORP replacement ranks. DraftState must carry what these need (scoring, roster format, drafted players by name/pos/team).
- `scripts/draft_assistant.py` — existing interactive CLI; reference for how scoring/roster config + projections are currently loaded.

### Projections / ADP keys (mapping target)
- `web/api/routers/projections.py` and `data/gold/projections/preseason/season=YYYY/` — the player keys our projections use (name/pos/team) that SLPR-03 must map Sleeper ids onto.
- `data/adp_latest.csv` + `scripts/refresh_adp.py` — ADP player keys.

### Config
- `src/config.py` — `SCORING_CONFIGS`, `ROSTER_CONFIGS` (map Sleeper league settings onto these).
</canonical_refs>

<specifics>
## Specific Ideas

- Sleeper draft pick objects include `pick_no`, `round`, `draft_slot`, `roster_id`, `picked_by`, `player_id`, `is_keeper`, and a `metadata` block with first_name/last_name/position/team — the metadata gives a fallback for mapping when the registry lookup misses.
- `get_draft(draft_id)` returns `draft_order` (user_id→slot) and `slot_to_roster_id` — both needed by Phase 86 for slot/turn math, so capture them in DraftState now.
- Sleeper soft rate cap ~1000 req/min; the players registry is the only heavy call — cache it.
</specifics>

<deferred>
## Deferred Ideas

- Yahoo (`draft_results` via OAuth) and ESPN (no live API) — later milestone, not this phase.
- The live poll/diff loop, board sync, recommendations, and key-moment detection — Phase 86.
- The `/draft-live` skill and conversational loop — Phase 87.
</deferred>

---

*Phase: 85-sleeper-draft-data-layer*
*Context gathered: 2026-06-14 via scoping conversation*
