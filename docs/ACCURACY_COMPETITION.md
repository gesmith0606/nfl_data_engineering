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

1. **Export script** `scripts/export_rankings_submission.py` — weekly Gold →
   the CSV layout FantasyPros specifies at onboarding (exact columns TBD by
   their partner docs; typically rank, player name, team, position).
2. **Cron hook** — append to the existing Thursday/weekly pipeline so the
   submission file is produced automatically; manual upload until they grant
   API/feed access.
3. **Application email** — cite the accuracy page + ledger URLs:
   - https://frontend-jet-seven-33.vercel.app/dashboard/accuracy
   - https://frontend-jet-seven-33.vercel.app/dashboard/predictions
4. **Branding decision (user)** — expert display name ("GIQ" vs personal
   name); FantasyPros lists a person or brand, and this is a public identity
   choice only George can make.

## Status

- 2026-08-08: playbook written (deferred-items sprint). Entry itself is an
  external action requiring the user's application + FantasyPros onboarding;
  no submission has been made yet. The export script is intentionally NOT
  built until their partner spec is in hand (ponytail: don't guess a CSV
  format a partner doc will define).
