---
phase: 67
milestone: v7.0
status: human_needed
verified_at: "2026-04-21"
---

# Phase 67: Roster Refresh v2 — Verification

## Status

**human_needed** — code changes are complete and committed; final acceptance requires a daily-cron run to complete on GitHub Actions and its output to deploy to Railway.

---

## Commits in this phase

| Plan | Commit  | Summary |
|------|---------|---------|
| 67-01 | `5fd1b65` | `refresh_rosters.py` handles FA / traded / reclassified; writes Bronze `rosters_live/` |
| 67-02 | `bfd30c1` | `team_roster_service.py` applies live corrections over immutable Bronze; `live_source` flag |
| 67-03 | `f09f57f` | `daily-sentiment.yml` fails hard on refresh errors; uploads audit log + live Bronze as artifact (retention 30d) |
| 67-04 | (this commit) | 11 new tests in `tests/test_refresh_rosters_v2.py`; 67-PLAN.md + 67-VERIFICATION.md |

Test results: **11 new + 44 web = all green**.

---

## Automated Verification (already passing)

- `tests/test_refresh_rosters_v2.py::test_released_player_kept_as_fa_not_skipped` — locks root-cause fix
- `tests/test_refresh_rosters_v2.py::test_released_emits_released_change_type` — RELEASED classifier
- `tests/test_refresh_rosters_v2.py::test_traded_emits_traded_change_type` — TRADED classifier
- `tests/test_refresh_rosters_v2.py::test_team_and_position_changed_emits_combined_type` — combined type
- `tests/test_refresh_rosters_v2.py::test_bronze_live_write_creates_timestamped_parquet` — live-roster parquet
- `tests/web/test_graceful_defaulting.py` × 12 — all still pass after service extension
- `tests/web/test_api_teams_roster.py` — all still pass after live-first read

---

## Human Verification Checklist

### Step 1 — Run the daily cron (manual trigger)

After pushing Phase 67 commits, trigger the daily cron manually to exercise the end-to-end path:

```bash
# Option A: via gh CLI
gh workflow run daily-sentiment.yml -f season=2026

# Option B: via GitHub UI
# Actions → Daily Sentiment Pipeline → Run workflow → season=2026
```

Wait for the run to complete. The "Refresh rosters from Sleeper" step must exit 0 (no more `|| echo` — a failure here fails the workflow and opens a GitHub issue via `notify-failure`).

### Step 2 — Verify the audit log artifact

Download the run's `sentiment-data-<run_id>` artifact and inspect:

```bash
# Expect at least one section like:
# --- Roster Refresh: 2026-04-21 12:00:15 ---
#   RELEASED: Kyler Murray (QB): ARI -> FA
#   TRADED: Davante Adams (WR): NYJ -> LAR
#   RECLASSIFIED: Taysom Hill: QB -> TE
cat roster_changes.log | tail -50
```

Confirm at least one `TRADED`, `RELEASED`, or `RECLASSIFIED` entry is present. An all-noop run is also valid (means Sleeper agrees with the current Gold snapshot), but in that case the `rosters_live/` parquet must still be written.

### Step 3 — Verify Bronze `rosters_live/` lands on Railway

The daily cron commits `data/bronze/players/rosters_live/` to the repo; Railway auto-deploys on push. After the commit lands:

```bash
curl -s https://nfldataengineering-production.up.railway.app/api/teams/ARI/roster?season=2026&week=1 | jq '{team, live_source, count: (.roster | length)}'
# Expected: live_source=true (means the live Bronze overlay applied at least one correction)
```

### Step 4 — Kyler Murray acceptance canary

This is the milestone test for Phase 67 — the original user report.

```bash
# Look up Murray's Sleeper truth first:
curl -s "https://api.sleeper.app/v1/players/nfl" | jq '[.[] | select(.full_name == "Kyler Murray")][0] | {full_name, team, status}'
# Expected (whatever Sleeper currently reports — could be a team, null/FA, or 'Released')
```

Then query our API:

```bash
# If Sleeper says Murray is on team X, X's roster should include him:
curl -s "https://nfldataengineering-production.up.railway.app/api/teams/<SLEEPER_TEAM>/roster" | jq '.roster[] | select(.player_name | ascii_downcase == "kyler murray")'

# If Sleeper says team=null (FA), ARI's roster should NOT include him:
curl -s "https://nfldataengineering-production.up.railway.app/api/teams/ARI/roster" | jq '.roster[] | select(.player_name | ascii_downcase == "kyler murray")'
# Expected output: empty (no match)
```

---

## Acceptance

Phase 67 is **passed** when:

1. Daily cron completes with exit 0 and `Refresh rosters` step shows non-zero roster changes OR a valid "No changes detected" (both are acceptable).
2. Artifact contains `roster_changes.log` with the expected typed prefixes and `rosters_live/season=2026/sleeper_rosters_*.parquet`.
3. `/api/teams/<team>/roster` returns `live_source: true` on at least one team.
4. Kyler Murray's team field on `/api/teams/ARI/roster` matches his Sleeper truth (present if Sleeper says ARI, absent if Sleeper says any other team or FA).

Reply with `approved` once these land. If any step fails, paste the failing output — the most likely issue is that `data/bronze/players/rosters_live/` wasn't committed (check step 6 of `daily-sentiment.yml` includes the path).

---

## Dependencies

Independent of Phase 68 (sanity-check v2). Phase 68 will eventually cross-reference `rosters_live/` against Sleeper canonical as one of its sanity assertions (`SANITY-05`).
