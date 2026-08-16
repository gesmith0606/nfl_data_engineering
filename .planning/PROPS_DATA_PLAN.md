# Player-props data plan — scrape-don't-buy (2026-08-16)

Decision context: opportunity-scan move #1 recommended a $29 one-month Odds API
historical tier to run the never-executed props-blend backtest (2022-2024).
User direction: don't buy; plan a self-scraped path instead. This is that plan —
**plan only, nothing built yet.**

## What already exists (verified 2026-08-16)

- **Forward capture is DONE and free**: `.github/workflows/odds-capture.yml`
  captures player props Thu 22:00 UTC (TNF, ~5 credits) + Sun 14:00 UTC
  (post-inactives, ~65-75 credits) on the Odds API FREE tier
  (`ODDS_API_KEY` GHA secret) → `data/bronze/odds_api/props/`. Empty today only
  because the 2026 season hasn't started; data begins flowing week 1 (Sept).
- **DIY sportsbook scraping is proven in this repo**: `scripts/
  bronze_season_props_ingestion.py` pulls DraftKings + FanDuel season-futures
  JSON directly (curl_cffi, no API key) from a GHA cron — the pattern works from
  runner IPs.
- **The props-blend gate was always an in-season gate**: pre-registered to
  evaluate once Sunday snapshots accumulate (~week 6+). The $29 historical
  backtest was an accelerant, not a prerequisite.

## The honest constraint

**Historical (2022-2024) prop lines cannot be scraped** — sportsbooks serve only
live/current lines; the past isn't on any page we can fetch. Self-scraping is a
forward-only strategy. Anything historical must come from an archive someone
else kept.

## Plan

### Phase 1 — free-archive scout (bounded: one agent-session, ~1 hr)
Search for free historical player-prop datasets covering any of 2022-2024:
Kaggle datasets, GitHub repos (sportsbook scraper projects often commit
snapshots), academic/betting-research dumps, Wayback Machine captures of
BettingPros/PropsCash-style pages. Acceptance bar: closing lines (or any
pre-kickoff snapshot) for QB/RB/WR yardage+TD markets, ≥half a season of
coverage, parseable. Outcome A: usable archive found → normalize into
`data/bronze/odds_api/props/` schema, run the pre-registered backtest.
Outcome B (likely): nothing usable → Phase 2 only, historical question waits
for the in-season gate.

### Phase 2 — harden + broaden forward capture (build when season nears, ~Sept 1)
1. **DIY DK+FanDuel weekly-props scraper** mirroring the season-props pattern
   (curl_cffi, no key): weekly player markets (pass/rush/rec yds, TDs, recs)
   both books → same bronze schema, tagged by book. Purpose: (a) redundancy if
   free Odds API credits run dry mid-season, (b) two extra books for cross-book
   medians (already proven valuable in season-props: 139 dual-quoted markets).
2. Wire into `odds-capture.yml` as an additional fail-open step (same Thu/Sun
   cadence), gitignore-allowlist the bronze path (TD-08/09/10 pattern — the
   in-season gate + weekly grading read it).
3. Completeness manifest entry (WARN-tier, in-season-only expectations).

### Phase 3 — evaluation (already scheduled, no new work)
The pre-registered props-blend gate runs on accumulated 2026 snapshots (~week
6+), now with up to 3 books instead of 1. If Phase 1 finds an archive, the
historical backtest runs immediately instead.

## Cost/benefit vs the $29

Buying: instant 2022-24 backtest, one-time cost, but a one-shot dataset.
Scraping: $0, builds a permanent multi-book capture asset, but answers the
props question ~6 weeks later (unless Phase 1 scores). Recommendation embedded
in this plan: run Phase 1 now (free, bounded), build Phase 2 before week 1,
revisit the $29 only if the in-season gate demands more history than 2026
provides.
