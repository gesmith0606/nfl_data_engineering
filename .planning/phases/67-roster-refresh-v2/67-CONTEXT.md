# Phase 67: Roster Refresh v2 — Context

**Gathered:** 2026-04-21
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous)

<domain>
## Phase Boundary

Rewrite `scripts/refresh_rosters.py` so released, free-agent, and traded players are handled correctly, corrections land in **Bronze** (not just Gold preseason), and a surfaced audit log makes changes inspectable. Kyler Murray is the acceptance canary — if Sleeper reports him as released/FA/traded, production must reflect that.

Runs in parallel with Phase 68. Both are independent of Phase 66.

</domain>

<decisions>
## Implementation Decisions

### Released + FA handling
- When Sleeper reports `team=null` (released / FA / retired), the script writes `team='FA'` to output rather than skipping (closes the line 80-82 loophole — current behavior is the root cause of the Kyler Murray regression).
- Released players **stay in projections** with `team='FA'` and `is_available=True` (planned column) so the advisor can surface "FA pickup candidate". Do not drop them.
- Position field unchanged when team becomes FA — Sleeper still knows the player's position.

### Traded vs released audit
- Audit log uses distinct entry prefixes so log readers can triage by type:
  - `TRADED: PlayerName (POS): OLD → NEW`
  - `RELEASED: PlayerName (POS): OLD → FA`
  - `RECLASSIFIED: PlayerName: OLD_POS → NEW_POS` (position change only)
- Three-way change (team + pos) emits both a `TRADED` and a `RECLASSIFIED` line for the same player.

### Bronze write strategy
- New dedicated path: `data/bronze/players/rosters_live/season=YYYY/sleeper_rosters_YYYYMMDD_HHMMSS.parquet`
- Original nfl-data-py Bronze at `data/bronze/players/rosters/` stays **immutable** — critical for model training stability (never mutate training data with live-rewritten teams; walk-forward CV would leak).
- Gold projection parquet write from v1 still happens — preserves advisor compatibility.

### Service consumption order
- `team_roster_service.py` gains a `_load_rosters_live(season)` helper that tries `rosters_live/` first, falls back to original `rosters/` if no live file exists. Phase 64-02's `load_team_roster` uses the new helper.
- Fallback semantics in `TeamRosterResponse` extended: add `live_source: bool` alongside existing `fallback` / `fallback_season`.

### Daily cron hardening
- `daily-sentiment.yml` refresh step drops the `|| echo` suffix. Script exit code now blocks the workflow step. Subsequent sentiment steps use `if: always()` where appropriate so a roster-refresh failure doesn't cascade to ingestion (each ingestor is already D-06-isolated per Phase 61).
- New env guard: if `SLEEPER_API_UNREACHABLE` is explicitly set (escape hatch for known upstream incidents), script exits 0 with a warning.

### Audit log surfacing
- `roster_changes.log` uploaded as a GHA workflow artifact on every daily-cron run (`actions/upload-artifact@v4`, retention 30 days).
- Committed-to-repo fallback removed (previous approach — log was .gitignored locally and lost).

### Claude's Discretion
- Exact CLI flag names for the escape hatch (`--allow-sleeper-failure` vs env var)
- Whether to add a `is_available: bool` column now or defer to Phase 70 frontend layer
- Output parquet filename exactly

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_roster_mapping()` in `refresh_rosters.py:106` — already does the single-pass team+position extraction; extend to emit `team=None` instead of skipping
- `update_rosters()` at line 213 — already handles team + pos in combined pass; add FA branch
- `log_changes()` at line 271 — timestamp-delimited append pattern already in place; add entry-type prefixes
- `team_roster_service._load_rosters()` — single reader for Bronze rosters; extend with `_live` variant
- Existing `find_latest_parquet()` pattern at line 166 — reuse for `rosters_live/` discovery

### Established Patterns
- Sleeper-to-nflverse team normalization via `SLEEPER_TO_NFLVERSE_TEAM` dict (line 43)
- Fantasy positions set `{QB, RB, WR, TE, K}` at line 39 — keep scope narrow; don't expand to DST/defensive positions
- Active-player collision handling (line 153) — preserve as-is
- Timestamp format `YYYYMMDD_HHMMSS` for parquet filenames — matches all other Bronze writes

### Integration Points
- `.github/workflows/daily-sentiment.yml` line ~111-115 — remove `|| echo`, add artifact upload
- `web/api/services/team_roster_service.py` — extend `_load_rosters()` to check `rosters_live/` first
- `web/api/models/schemas.py::TeamRosterResponse` — add `live_source: bool = False` field
- Phase 68 sanity-check v2 will cross-reference `rosters_live/` against Sleeper canonical — keep the path/schema stable for that

</code_context>

<specifics>
## Specific Ideas

- **Kyler Murray is the acceptance canary.** Phase 67 is only passed when: (a) script correctly classifies Murray's Sleeper status as of run time, (b) Gold projections reflect it, (c) Bronze `rosters_live/` reflects it, (d) `/api/teams/ARI/roster` on Railway matches Sleeper truth.
- Training-data mutation is the #1 thing to avoid. The original nfl-data-py `data/bronze/players/rosters/` tree is frozen. All "live truth" goes to the new `rosters_live/` tree.
- Position changes (e.g. a WR moved to RB) are informational — don't propagate to training data; Silver/Bronze originals win for historical modeling (carry-over from Phase 60 D-05).

</specifics>

<deferred>
## Deferred Ideas

- Multi-source roster triangulation (ESPN + Yahoo alongside Sleeper) → v7.1 when external projections comparison lands
- Historical roster backfill — reconstructing transaction history from Sleeper snapshots → out of scope (nfl-data-py transactions dataset exists but under-used)
- Real-time push updates from Sleeper (webhook / streaming) → out of scope; daily cadence is sufficient for projections use case

</deferred>
