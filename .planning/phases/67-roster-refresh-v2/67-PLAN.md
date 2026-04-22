# Phase 67: Roster Refresh v2 — Plan

**Created:** 2026-04-21
**Status:** Executing inline (direct implementation)

## Plan 67-01: `refresh_rosters.py` v2 — FA handling + Bronze live write
**Requirements:** ROSTER-01, ROSTER-02, ROSTER-03, ROSTER-04, ROSTER-06 (escape-hatch piece)
**Commit:** `5fd1b65`

- `build_roster_mapping` no longer skips `team=null` — maps to `team='FA'`
- `update_rosters` classifies every change as `TRADED`, `RELEASED`, `RECLASSIFIED`, or `TRADED+RECLASSIFIED`
- `log_changes` prefixes lines with the change type for audit filterability
- New `write_bronze_live_rosters(mapping, season)` → `data/bronze/players/rosters_live/season=YYYY/sleeper_rosters_YYYYMMDD_HHMMSS.parquet`
- `main()` calls the Bronze writer; `--skip-bronze-live` flag + `SLEEPER_API_UNREACHABLE` env escape hatch

## Plan 67-02: `team_roster_service.py` consumes live corrections
**Requirements:** ROSTER-03 (API-side), ROSTER-05 (acceptance surface)
**Commit:** `bfd30c1`

- New `_load_live_roster_corrections(season)` reads the latest `sleeper_rosters_*.parquet`
- New `_apply_live_corrections(roster_df, live_df)` merges on lowercase full_name, overrides team + position, rewrites status to FA for released players (so `_ACTIVE_STATUSES` filter drops them from team views)
- `load_team_roster` wires the corrections layer between `_load_rosters` and the team filter
- `TeamRosterResponse.live_source: bool` signals when corrections took effect

## Plan 67-03: Daily cron harden + artifact upload
**Requirements:** ROSTER-04 (artifact surfacing), ROSTER-06 (fail-hard)
**Commit:** `f09f57f`

- Drop `|| echo` from refresh_rosters.py invocation
- Commit set includes `data/bronze/players/rosters_live/` so corrections ship to Railway
- Artifact step adds `rosters_live/` + `roster_changes.log`; retention 30 days
- `vars.SLEEPER_API_UNREACHABLE` repo variable wired into env as escape hatch

## Plan 67-04: Tests + verification doc
**Requirements:** (test coverage for 01 / 02; verification artifact for acceptance)

- 11 new unit tests in `tests/test_refresh_rosters_v2.py` covering FA handling, change classification, log formatting, Bronze live write
- 67-VERIFICATION.md captures the human-verification checklist including the Kyler Murray canary

## Requirements → Commits Mapping

| REQ | Delivered by |
|-----|--------------|
| ROSTER-01 (FA handling) | 67-01 `build_roster_mapping` + `update_rosters` + `tests/test_refresh_rosters_v2.py::test_released_*` |
| ROSTER-02 (traded audit) | 67-01 change-type classifier + 67-01 log format + test_traded_* / test_team_and_position_changed_* |
| ROSTER-03 (Bronze write) | 67-01 `write_bronze_live_rosters` + 67-02 service live-first read |
| ROSTER-04 (audit log surfaced) | 67-03 GHA artifact upload including `roster_changes.log` |
| ROSTER-05 (Kyler Murray canary) | verification acceptance after next daily-cron run lands on Railway |
| ROSTER-06 (fail loudly) | 67-03 drops `\|\| echo`; 67-01 escape hatch env var |
