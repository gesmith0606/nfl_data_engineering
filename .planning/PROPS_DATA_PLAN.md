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

## Phase 1 scout results (2026-08-16)

**Verdict: PARTIAL ARCHIVE FOUND.** One free, real, machine-parseable
GitHub-hosted archive clears the coverage bar for 4 of 5 required markets
across 2023-2025 (not 2022, no confirmed anytime-TD data). Recommend using it
to run an early partial backtest (pass yds / rush yds / rec yds / receptions,
2023-2025) rather than waiting the full 6 weeks for Phase 2/3, while treating
anytime-TD and true 2022 coverage as still open.

### Search lanes covered

| Lane | Result |
|---|---|
| Kaggle | No dedicated NFL player-props dataset found (searched directly + via web search; only game-line/team datasets surfaced) |
| GitHub repos (scraper projects w/ committed snapshots) | **Hit** — see candidate #1 below. `gh search code`/`gh search repos` across ~20 other prop-related repos found scraper *code* but no other repo with committed historical CSVs at the required grain |
| Academic / betting-research dumps | Nothing found (Princeton DSS catalog entry just links back to SportsOddsHistory; no downloadable player-prop dataset) |
| Wayback Machine (BettingPros/Covers/OddsShort prop pages) | **Inconclusive** — `web.archive.org` CDX API returned HTTP 429 (rate-limited) on every attempt within the session budget; WebFetch tool cannot reach `web.archive.org` at all in this environment. Did not spend further budget retrying since a working candidate was already found. Treat as unverified, not ruled out — a future session with a clean IP/longer budget could still check capture density. |
| Free-tier odds archives (SportsOddsHistory / Covers / OddsShark) | SportsOddsHistory (covers.com) advertises "season-long props" and closing lines but is a browse-only site (no bulk export); did not confirm it exposes weekly *player* yardage/TD props vs. just game lines and futures — likely the usual game-lines-only gap the task flagged. Not pursued further given the GitHub hit. |
| `playerpropdatabase.com` (surfaced by search snippets as "NFL and NBA Player Prop historical data") | **Dead domain** — NXDOMAIN (`nslookup` confirms non-existent domain). Search-result snippet is stale/misleading; site does not currently exist. |
| The Odds API historical tier | Confirmed paid-only (historical player-props data available from 2023-05-03, but gated behind a paid plan) — matches what the existing plan already knew; not a free source. |

### Candidate table

| # | Source | Coverage | Markets | Format | License/ToS | Access | Verified |
|---|---|---|---|---|---|---|---|
| 1 | **GitHub: `firstandthirty/nfl-tools`** (public repo, `player_props/data/`) | FanDuel, single book. `player_pass_yds` + `player_receptions`: **2023 wk2 → 2025 wk18** continuous (6,901 / 6,902 rows). `player_rush_yds` + `player_reception_yds` (rec yds): **2024 wk1 → wk17** continuous (1,095 / 2,334 rows). No confirmed exported data for `player_anytime_td` (market is requested by their capture script `archive_odds_snapshot.py` but no processed/analysis CSV surfaced it — likely dropped or still raw-only). | pass yds, rush yds, rec yds, receptions (anytime TD: script capability only, no data found) | CSV, one row per player-market-snapshot, columns include `season`/`week`, `line`, `over_price`/`under_price`, `actual_value`/`hit_over` (already graded against actuals) | No `LICENSE` file in repo → default all-rights-reserved on the repo owner's original work; underlying odds data is sourced from The Odds API (a commercial provider) via the owner's own capture scripts (`archive_odds_snapshot.py` for live snapshots, `backfill_closing_props.py` targeting a historical/closing-line pull) — redistribution rights are ambiguous, but reading a public GitHub file for private research is low-risk (same trust model as reading any other public repo's committed data) | `curl https://raw.githubusercontent.com/firstandthirty/nfl-tools/main/player_props/data/processed/<file>.csv` — no auth, no key | **Yes** — fetched and inspected `fanduel_pass_yds_history.csv`, `fanduel_receptions_history.csv`, `rush_yds_market_analysis_rows.csv`, `reception_yds_market_analysis_rows.csv` directly; spot-checked a real row (Najee Harris `player_rush_yds` line 51.5, PIT@BAL 2024-11-17, actual 63.0, `hit_over=True`) against a plausible real game; confirmed recent maintenance (commits May 2026, not abandoned) |
| 2 | GitHub: `jbart12/nfl-ai` (PrizePicks accessor research) | Live/current snapshot only (5,529 props at time of writing, PrizePicks) | All positions, many stat types | JSON via live API call | PrizePicks API ToS unclear, but moot | N/A | Ruled out — no historical depth, single point-in-time capture only, not an archive |
| 3 | SportsOddsHistory / Covers.com | Game lines + season-long futures confirmed; player weekly-props coverage unconfirmed | Unknown for weekly player props | Web tables, no bulk export | Unclear | Manual browse only | Not verified — deprioritized after candidate #1 hit |
| 4 | Wayback Machine captures of BettingPros | Unknown | Unknown | HTML scrape | Wayback ToS generally permissive for research | `web.archive.org` CDX/API | **Not verified** — rate-limited (429) throughout session |

### Recommendation / next step

Candidate #1 (`firstandthirty/nfl-tools`) is real, free, and clears the plan's
acceptance bar (closing/pre-kickoff snapshots, ≥half a season contiguous,
machine-parseable CSV, low-risk for private research) for **pass yds, rush
yds, rec yds, and receptions across 2023-2025** — it does not cover anytime TD
or true 2022 data, and is single-book (FanDuel) with ambiguous redistribution
rights on the underlying Odds API data (fine to read/use privately, not to
republish). Next step: pull the four CSVs (`fanduel_pass_yds_history.csv`,
`fanduel_receptions_history.csv`, `rush_yds_market_analysis_rows.csv`,
`reception_yds_market_analysis_rows.csv`) from the repo, normalize into the
`data/bronze/odds_api/props/` schema (they already carry `season`/`week`/
`market_key`/`line`/prices and, usefully, pre-graded `actual_value`/
`hit_over`), and run the pre-registered props-blend backtest on 2023-2024
before the in-season 2026 gate lands — treating anytime-TD as still gapped
(falls back to the Phase 2/3 in-season plan for that one market). Re-verify
license comfort with the user before any redistribution (not just internal
backtest use) of derived results.
