# Enhancement: weekly lineup tool (`scripts/set_lineups.py`)

Filed 2026-09-09 after the Week 1 Mantis Toboggan (Sleeper dynasty superflex, TE premium,
6pt pass TD) lineup review recommended benching Christian Watson (GB WR1) for Hunter Henry.
The call was wrong and the user caught it. Root causes, all process:

1. The only Week 1 board on disk was `week1_board_*_derived` (Aug 31) — preseason/17 with a
   matchup multiplier, built on trailing-2025 usage (Watson = half-season post-ACL -> WR53).
   No weekly projection had been generated; the shipped Sleeper WR consensus anchor never
   touched it because the derived board bypasses the weekly path.
2. League scoring (TE premium, 6pt pass TD) was bolted on by hand in an ad-hoc script —
   the exact "hand re-scoring drops the consensus anchor" failure the 2026-08-23 ESPN mock
   post-mortem already recorded.
3. A ~3-pt single-source margin was presented as a confident swap; Sleeper's own Week 1
   projection (scored under league settings) had Watson 17.0 vs Henry 15.0.
4. Nothing wires roster -> fresh projections -> league scoring -> injury/news -> lineup
   diff. `roster_optimizer.optimal_lineup`, `league_scoring.score_with_settings`, the
   Sleeper roster reader and `ingest_external_projections_sleeper.py` all exist separately.

## Spec

- `python scripts/set_lineups.py --league <preset> [--week N]`
  - Pull the roster + `roster_positions` + `scoring_settings` (Sleeper API; ESPN via
    `espn_league.py` cookies; Yahoo = `--roster-file` manual).
  - Projections = our weekly Gold (regenerate if stale for the week) BLENDED with Sleeper's
    Week N player projections (`/projections/nfl/player/{id}`), both re-scored with
    `score_with_settings` (TE premium applies by player position, not slot).
  - Flag `injury_status`, `depth_chart_order` changes, game-day/lock time per player.
  - Output ONLY deltas vs the lineup currently set, each with both sources' numbers.
  - Hard rule: no swap recommended unless both sources agree AND margin >= threshold
    (start 3.0 pts); otherwise print "coin flip".
- Add `mantis` (league 1378522447686402048, user Gforceee, 10-tm, SF, TE premium) to
  `LEAGUE_PRESETS`; add `SUPER_FLEX`/TE-premium-aware roster config.
- Once the season starts, never read `*_derived` boards for weekly decisions.

Estimate: ~1 day. Owner: next free session before Week 2 lineups (Sun 2026-09-20).

## Status (2026-09-12) — BUILT, Sleeper only

- `src/lineup_setter.py` + `scripts/set_lineups.py` + `tests/test_lineup_setter.py` (12 tests);
  `mantis` added to `LEAGUE_PRESETS` (`my_user` = Sleeper display name; roster shape and
  scoring are read live from the league, so no ROSTER_CONFIGS entry is needed).
- Week 1 live run on Mantis: **no changes** — no bench player beats a starter on both
  sources (Watson FLEX 11.3 ours / 15.7 Sleeper vs Henry 13.8 / 15.0 on the bench, and
  Henry was already locked). The earlier Watson-for-Henry call does not survive the rule.
- Real root cause of the Week 1 gap, beyond process: the Tuesday cron computed 2025 wk18
  on Sep 8 (fixed in PR #107), AND the weekly engine cannot build a Week 1 board for a new
  season — `generate_projections.py --week 1 --season 2026` loads only current-season
  usage (135 rows from the two games already played) and emits 47 rookie-baseline rows.
  The backtester includes the prior season for early weeks; production does not. Until
  that is fixed, OURS for Week 1 is preseason pace (season/17), labelled in the output.
- Sleeper-side scoring is a full dot product over `scoring_settings` (first downs, 2-pt,
  fumbles included); OURS cannot model those keys and says so in the footer.

Still open: ESPN (`espn_league.py` cookies) and Yahoo (`--roster-file`) roster readers;
depth-chart *change* detection needs a prior snapshot (only the current order is shown);
the weekly-engine prior-season seed for Weeks 1-2 (separate PR).
