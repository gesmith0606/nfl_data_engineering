# Third-Party Accuracy Verification — Entry Playbook

Goal: convert the internal accuracy receipts (Model-vs-Consensus page, graded
prediction ledger) into **third-party-verified proof**, the way 4for4 built its
"most accurate" brand on FantasyPros' scoring of John Paulsen.

## Where to enter

### 1. FantasyPros Expert Accuracy Competition (primary target)
- What it is: FantasyPros scores 150+ analysts' **weekly rankings** and 200+
  analysts' **preseason draft rankings** against actual results, with a public
  methodology and season leaderboards (fantasypros.com/nfl/accuracy/).
- How to enter: apply as a ranking **partner/expert** — FantasyPros onboards
  experts who publish rankings on their own site and syndicate them. Contact:
  partners@fantasypros.com (also reachable via the "Become an Expert" flow).
- What they need from us, weekly (in-season):
  - Positional rankings (QB/RB/WR/TE/K/DST) submitted before Sunday slates —
    our weekly Gold projections sorted by `projected_points` ARE the ranking;
    export = trivial transform of the existing parquet.
  - A stable expert identity (site name, logo, URL).
- What they need preseason: a draft ranking (overall + positional) — the
  preseason Gold artifact sorted by `projected_season_points` / VORP.
- Why it's winnable exposure even mid-pack: every submitted week gets a
  public accuracy score next to ESPN/Yahoo/CBS names — distribution and
  credibility we cannot buy otherwise.

### 2. FantasyNation / other scorers (secondary)
- Smaller equivalents that also grade experts (FantasyNation ranked 4for4's
  Paulsen #2 in 2020-21). Lower reach; enter once FantasyPros is flowing —
  same artifact, another consumer.

## What we already have that maps directly

| Their requirement | Our artifact |
|---|---|
| Weekly positional rankings | `data/gold/projections/season=S/week=W/*.parquet` sorted by `projected_points` |
| Preseason draft rankings | `data/gold/projections/preseason/season=S/*.parquet` (overall_rank, position_rank) |
| Custom-scoring variants (std/half/ppr) | already generated per format |
| Track record to cite in the application | Model-vs-Consensus page: matched-pairs MAE vs Sleeper consensus 2022-24, we beat consensus overall (QB −0.39, WR −0.075, TE −0.43) |

## Work items (when picked up)

1. **Export script** — BUILT (2026-08-08): `scripts/export_rankings_submission.py`
   writes per-position weekly CSVs (`--weekly --season S --week W`) and
   overall+positional preseason draft CSVs (`--preseason --season S`) to
   `data/exports/rankings/`. Column layout is a flag
   (`--columns rank,player_name,team,position` default) so the partner spec
   is a one-flag adjustment, not a rewrite.
2. **Cron hook** — BUILT (2026-08-08): the Tuesday weekly pipeline
   (`.github/workflows/weekly-pipeline.yml`) runs the weekly export right
   after the Gold sanity check (fail-open) and publishes the CSVs as the
   `rankings-submission-<run_id>` workflow artifact (90-day retention);
   manual upload to FantasyPros until they grant API/feed access.
3. **Application email** — cite the accuracy page + ledger URLs:
   - https://frontend-jet-seven-33.vercel.app/dashboard/accuracy
   - https://frontend-jet-seven-33.vercel.app/dashboard/predictions
4. **Branding decision (user)** — expert display name ("GIQ" vs personal
   name); FantasyPros lists a person or brand, and this is a public identity
   choice only George can make.

## Status

- 2026-08-08: playbook written (deferred-items sprint). Entry itself is an
  external action requiring the user's application + FantasyPros onboarding;
  no submission has been made yet.
- 2026-08-08 (later): export script built with a configurable column layout —
  ready to run the moment onboarding specifies the format.
- 2026-08-08 (later still): weekly cron hook wired (work item 2) — every
  Tuesday pipeline run now attaches the submission CSVs as a workflow
  artifact. Preseason draft CSVs regenerated + verified against the latest
  Gold vintage. Remaining steps are user-owned: application email + expert
  identity; flip `--columns` if the partner spec differs from the default.
- **2026-08-10: in-season ordinal tracking wired.** `FP_ACCURACY_SIMULATION.md`
  found we lose the ordinal Accuracy Gap metric (what FantasyPros actually
  scores) at every position on the 2022-2024 simulation, even where our MAE
  beats consensus — so the weekly ELITE grading report now measures the
  *right* metric automatically, in-season, every week:
  - `scripts/weekly_grading_report.py` gained two new sections, computed
    every Tuesday for the previous week alongside the existing MAE-gap
    report: **"FantasyPros-Style Ordinal Accuracy Gap (Week W)"** (ours vs
    sleeper/espn/yahoo_proxy_fp for that week) and **"Ordinal Accuracy Gap —
    Season-to-Date"** (weeks 3..W pooled, so the rank→baseline-points table
    stabilises as the season progresses, mirroring the pooled multi-season
    baseline used in the offline simulation). Output lands in the same
    places as the rest of the grading report: `output/grading/season=YYYY/
    week=WW_report.{md,json}` (JSON keys `ordinal` / `cumulative_ordinal`),
    uploaded as the `grading-report-<run_id>` workflow artifact.
  - The scoring machinery is imported from `scripts/simulate_fp_accuracy.py`
    (refactored to a generic `score_sources()` / `build_ordinal_table()` — no
    metric logic duplicated between the offline simulation and the live
    report). Sources: our Gold projections + whichever of
    sleeper/espn/yahoo_proxy_fp the `weekly-external-projections` cron
    captured that week (`data/silver/external_projections/season=YYYY/
    week=WW/`, already wired since Phase 73 — confirmed end-to-end, no
    pipeline changes needed).
  - Fail-open at two levels: a source missing for a given week (e.g.
    yahoo_proxy_fp isn't captured for any pre-2026 week, since that cron
    started 2026) is recorded in `sources_missing` and the table still
    renders for whatever sources ARE present (minimum: "ours" alone) — never
    a crash, never a blocked pipeline run.
  - Smoke-tested against real 2024 week 10 data (Gold + Sleeper + ESPN
    present locally): Accuracy Gap (lower = better) — QB ours 11.73 vs
    sleeper 7.13 / espn 6.95; RB ours 5.58 vs 4.88 / 4.50; WR ours 6.64 vs
    6.46 / 5.65; TE ours 6.42 vs 4.45 / 4.99 — consistent in direction with
    the 2022-2024 offline simulation (we trail consensus on this metric at
    every position), confirming the live wiring reproduces the same finding
    the offline simulation predicted.
