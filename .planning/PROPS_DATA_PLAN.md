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

## Phase 2 built (2026-08-16)

**`scripts/bronze_weekly_props_ingestion.py`** (new) — DIY DK+FanDuel weekly
player-props scraper, no API key, mirroring
`bronze_season_props_ingestion.py`'s curl_cffi/Chrome-impersonation pattern.
Targets the six markets in the task brief: pass yds, pass TDs, rush yds, rec
yds, receptions, anytime TD.

### Endpoints used

- **DraftKings**: `sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/88808`
  (same base as the season script) plus `/categories/{id}` for per-category
  markets. Unlike season futures, weekly per-game player-prop category ids
  are **not stable/hardcoded** — they don't exist in DK's system until the
  book posts that market family. `discover_dk_weekly_category_ids` instead
  walks whatever categories the live league doc reports and treats any id
  outside a known season/futures/specials exclude-set (`DK_NON_WEEKLY_CATEGORY_IDS`,
  19 ids) as a per-game candidate, then matches **subcategory names** (not
  ids) to the target markets — self-healing once DK posts the yardage
  markets, no id to guess or re-hardcode later. Confirmed live 2026-08-16:
  the old `sites/US-SB/api/v5/eventgroups` API (used by several public DK
  scrapers) is now Akamai-blocked (403); the `eventIds` query param on the
  new nash API is silently ignored (a category call always returns
  everything currently posted league-wide, filtering happens client-side
  post-hoc against the event's `commence_time`).
- **FanDuel**: reuses the season script's `content-managed-page`
  (`customPageId=nfl`) for the game catalog (event ids + kickoff times),
  then `sbapi.nj.sportsbook.fanduel.com/api/event-page?eventId=...` per
  game for market data. FanDuel's live market-blurb catalog for a real Week
  1 2026 event confirms an `ANY_TIME_TOUCHDOWN_SCORER` market type exists in
  their system (rule text present) even though no event currently has it as
  a live, selectable market this far from kickoff.

### Schema mapping

Output columns are the exact `PROPS_SCHEMA_COLS` from
`scripts/bronze_props_ingestion.py` (re-imported, not redefined): snapshot_ts /
event_id / commence_time / home_team / away_team / home_team_nfl /
away_team_nfl / bookmaker / market / player_name / line / price_over /
price_under / season. Market keys reuse the Odds-API vocabulary
(`player_pass_yds`, `player_pass_tds`, `player_rush_yds`,
`player_reception_yds`, `player_receptions`, `player_anytime_td`) so
`src/prop_implied.py` consumes either source unmodified — verified directly:
a real captured DK file round-tripped through
`compute_prop_implied_points()` without error and produced sane per-player
implied points. Prices are American odds throughout (DK: parsed from its
unicode-minus display string via the same `parse_american_odds` pattern as
the season script; FanDuel: `winRunnerOdds.americanDisplayOdds.americanOdds`,
already an int) — the archive's decimal-odds trap
(`PROPS_BLEND_BACKTEST_2026_08_16.md`) does not apply to either book's live
JSON API.

**Output path is deliberately NOT the same file-naming convention as the
Odds API's own weekly capture.** The Odds API writes flat into
`data/bronze/odds_api/props/season=YYYY/props_<timestamp>.parquet`, and
`generate_projections.py --props-blend` globs exactly that
(`props/season={season}/props_*.parquet`, non-recursive) and reads only the
single lexicographically-latest file. A numeric-timestamp filename
(`props_2026...`) always sorts before a letter-prefixed one
(`props_dk_...`) in ASCII, so writing DK/FD into that same flat directory
under any `props_*` name would make a DK/FD snapshot silently and
permanently win the "latest file" selection over a newer, more complete
Odds API capture (which alone has multi-market game coverage today),
regardless of actual timestamp. This script instead writes to
`data/bronze/odds_api/props/season=YYYY/week=WW/props_dk_<ts>.parquet` and
`.../props_fd_<ts>.parquet` — a `week=WW` subdirectory the existing glob
does not recurse into, so today's `--props-blend` behavior is completely
unaffected. **Wiring DK/FD into the actual `--props-blend` multi-book read
path (e.g. cross-book median across Odds API + DK + FD) is a follow-up, not
done here** — this phase only builds and lands the capture.
`git check-ignore` confirms the new path is NOT ignored (the existing
`!data/bronze/odds_api/**/*.parquet` allowlist covers the nested `week=WW/`
dir; the archive re-ignore rule is scoped to the flat `season=X/` archive
filename only and does not match `props_dk_*`/`props_fd_*`).

### Smoke-test reality — live capture vs machinery-only (do not conflate)

- **`player_anytime_td` on DraftKings: REAL LIVE CAPTURE**, not a fixture.
  Ran the finished script against the live DK API on 2026-08-16 (`--days-ahead
  30 --skip-fanduel`, non-dry-run): DraftKings had genuine "Anytime TD
  Scorer" markets already posted for several real Week 1 2026 games (kickoff
  2026-09-10/11), 25 days out. Captured **78 real rows** (e.g. Jaxon
  Smith-Njigba −105, Christian McCaffrey, Kyren Williams, Kenneth Walker
  III), wrote a real Parquet file to
  `data/bronze/odds_api/props/season=2026/week=1/`, and confirmed it
  round-trips through `compute_prop_implied_points()`. One real bug found
  and fixed by this live test: DK's Rams `shortName` is `"LAR"`, nflverse
  uses `"LA"` — 22/78 rows silently failed week resolution until
  `DK_TEAM_ABBR_FIXUPS = {"LAR": "LA"}` was added; all other team
  abbreviations DK reports already match nflverse directly.
- **`player_pass_yds`, `player_pass_tds`, `player_rush_yds`,
  `player_reception_yds`, `player_receptions` on DraftKings: NEEDS
  WEEK-1-VERIFICATION.** Confirmed live (2026-08-16) that DK has posted
  ZERO markets in these five families for any Week 1 2026 game — the
  category-discovery scan found exactly one non-excluded category with live
  markets (1003, "TD Scorers"); a manual scan of DK's known adjacent
  category ids (528/530/992-1030 range) found nothing else live. This is
  the expected, documented off-season caveat from the task brief, not a
  scraper bug — DK typically doesn't post detailed yardage props until
  much closer to kickoff. The parser (`normalize_dk_category`'s
  over/under path) is unit-tested against a **constructed fixture** modeled
  on DK's own confirmed-live selection shape for a different market family
  (the "Total" game market, which already uses a `points` field +
  `outcomeType: "Over"/"Under"`) — a reasonable, defensible guess, but
  unverified against a real weekly player-level payload. **Must be
  re-checked once DK posts Week 1 yardage props** (historically within
  1-2 weeks of kickoff, i.e. by ~2026-09-01).
- **All six markets on FanDuel: NEEDS WEEK-1-VERIFICATION, no live markets
  at all right now.** FanDuel does not book NFL preseason games (confirmed:
  its NFL page's event catalog jumps straight from futures placeholders to
  Week 1 games, no exhibition games), so there was no near-term FanDuel game
  to test parsing against at any market family. The one positive signal:
  the `ANY_TIME_TOUCHDOWN_SCORER` market **type** is confirmed present in
  FanDuel's own live market-blurb rules catalog for a real Week 1 event
  (proof the market family exists in their system), but zero events
  currently expose it as a live, purchasable market. All FanDuel parsing
  (`normalize_fanduel_event_markets`) is unit-tested against constructed
  fixtures modeled on FanDuel's confirmed-live "Total Match Points" selection
  shape (`handicap` field + `Over`/`Under` runnerName) — same caveat as DK's
  yardage markets, un-fired against real data.
- **Explicitly not fabricated**: no test claims a live capture for anything
  except the one DK anytime-TD path that was actually run against the live
  API and produced real rows.

### Wiring

`.github/workflows/odds-capture.yml` — added a new step, "Fetch NFL weekly
player-props snapshot (DraftKings + FanDuel)", inside the existing
`capture-props` job (already gated to the Thu 22:00 UTC + Sun 14:00 UTC
triggers, same job the Odds API weekly capture runs in). Runs
`bronze_weekly_props_ingestion.py --days-ahead 8`. Uses
`continue-on-error: true` — the script's honest exit-1-on-zero-rows contract
(both books blocked, or, expected for most of the 2026 preseason, nothing
posted yet) must not fail the job or trigger `notify-failure`'s GitHub-issue
page; the step still renders red in the Actions UI for visibility. No
change needed to the commit step's `git add data/bronze/odds_api/props/` —
it's already recursive and picks up the new `week=WW/` files for free.

### Tests

`tests/test_bronze_weekly_props_ingestion.py` — 45 tests: American-odds/line
parsing, DK category discovery (exclude-set), DK anytime-TD + O/U
normalization (including the LAR→LA fixup and sibling-market skip), FanDuel
game-event discovery (placeholder exclusion, window filter) + market
normalization, `resolve_week` (single match, home/away swap, no match,
divisional-rematch disambiguation by nearest kickoff date), `finish_rows`
(schema-conformance: output columns == `PROPS_SCHEMA_COLS`, window filter,
unresolvable-week rows dropped not mis-partitioned), Parquet write
(season/week partition path, book-tagged filename never starts with a digit
or matches `props_archive_*`), and the zero-rows-exit-1 / fail-open-per-book
exit-code contract.

### Manifest

`scripts/check_data_completeness.py` — added `bronze_weekly_props`
(WARN-tier, `committed=True`, current-season-only,
`glob="week=*/props_*.parquet"`). Confirmed locally: after the real DK
capture above, `--local` reports `[PASS] bronze_weekly_props[2026] 1
file(s)`. WARN-tier because a miss is expected and correct off-season/most
of preseason — never blocks.

### What Week 1 must confirm

1. **DK yardage/reception markets**: once DK posts `player_pass_yds` /
   `player_pass_tds` / `player_rush_yds` / `player_reception_yds` /
   `player_receptions` for a real game, re-run the script and check whether
   `normalize_dk_category`'s O/U path parses real rows correctly (the
   `points`-field assumption) or needs adjustment — watch the GHA Actions
   log for the per-category row-count summary; a category appearing with 0
   parsed rows despite the category having live markets is the signal
   something changed.
2. **FanDuel, all markets**: same check once FanDuel posts anything —
   confirm `marketName` actually follows the assumed `"<player> <stat>"`
   pattern (vs., e.g., an `"Alt "` prefix or different word order) and that
   `ANY_TIME_TOUCHDOWN_SCORER` fires as expected.
3. **Cross-book wiring**: decide whether/how to merge DK/FD data into the
   `--props-blend` read path (currently untouched — see schema-mapping
   section above) once real multi-market coverage exists to make a
   cross-book median meaningful.
4. **DK team-abbreviation fixups**: the live test only surfaced the Rams
   (`LAR`→`LA`); watch for other DK/nflverse abbreviation mismatches as more
   teams' markets get exercised (e.g. Washington, Las Vegas) — extend
   `DK_TEAM_ABBR_FIXUPS` if the weekly warning log ("N/M rows dropped —
   could not resolve NFL week") fires for a resolvable-looking team pair.
