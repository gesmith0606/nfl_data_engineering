# Click-Through Fixes — 2026-08-16

Four prod findings from a browser click-through, fixed. Reference:
`.planning/HYBRID_SHIP_2026_08_15.md`, `.planning/WR_GAP_FIX_2026_08_16.md`,
`.planning/BENCHMARK_REFRESH_2026_08_15.md`.

## 1. Stale accuracy artifact (accuracy page + home hub claim strip)

**Root cause (two independent bugs, both traced by browser click-through +
live DOM inspection of the deployed site):**

1. **Stale artifact.** `web/frontend/src/features/nfl/config/model-metrics.json`
   was last regenerated 2026-06-12
   (`consensus_matched_half_ppr_20260612_141246.csv`), before the
   2026-08-15/16 ships (`HYBRID_SHIP_2026_08_15.md`: QB/RB promoted to hybrid
   ML, correction clamp; `WR_GAP_FIX_2026_08_16.md`: WR secondary-model
   blend). Every component that reads this JSON
   (`accuracy-dashboard.tsx`, `home-modules.tsx`'s `ProofStrip`,
   `mae-chart.tsx`, `accuracy-chart.tsx`, `stat-cards.tsx`) was showing June
   numbers: overall gap −0.009, RB +0.261 (loss, graded D/TRAILING), "3 of 4
   positions" (WR was the one loss).
2. **Methodology drift in the generator.** `scripts/generate_frontend_metrics.py`
   `build_consensus_section()` never applied the `consensus_proj >= 5`
   floor that the rest of the repo's "matched-pairs" methodology uses
   everywhere else (`backtest_projections.py --vs-consensus`'s own printed
   report, every `.planning` benchmark doc) — it just filtered to
   QB/RB/WR/TE and used every row in the saved `consensus_matched_*.csv`,
   including rows where the consensus projected under 5 points (noise-level
   bench players). This inflated the population from n=7,009/6,721 (the
   documented, gate-tested population) to n=10,417/9,574, silently
   diverging the site's numbers from every planning-doc headline table.
   Fixed by adding the same `>= 5` filter (`scripts/generate_frontend_metrics.py`,
   `build_consensus_section`).

**Regeneration:** Ran the production backtest path foreground against the
*current* shipped configuration (post HYBRID_SHIP + WR_GAP_FIX):

```
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 \
  --scoring half_ppr --ml --full-features --vs-consensus --consensus-source sleeper \
  --output-dir output/backtest/clickthrough_fix_20260816
python scripts/backtest_projections.py --seasons 2022,2023,2024 --weeks 1-18 \
  --scoring half_ppr --ml --full-features --vs-consensus --consensus-source espn \
  --output-dir output/backtest/clickthrough_fix_20260816
python scripts/generate_frontend_metrics.py \
  --csv output/backtest/clickthrough_fix_20260816/backtest_half_ppr_ml_fullfeatures_consensus_20260816_112121.csv \
  --consensus-csv output/backtest/clickthrough_fix_20260816/consensus_matched_half_ppr_20260816_112121.csv \
  --tests 3749
```

Matched populations reproduce exactly: n=7,009 vs Sleeper / n=6,721 vs ESPN
— the documented gate populations.

### Old vs new artifact numbers (vs Sleeper, the JSON's benchmark)

| Position | Old (June, stale) | New (2026-08-16, current config) | Verdict |
|---|---:|---:|---|
| QB | −0.325 (win) | **−0.862** (win) | win widens |
| RB | +0.261 (**loss**) | **−0.310** (win) | **FLIPS to a win** (QB/RB hybrid ship) |
| WR | −0.006 (thin win) | **−0.067** (win) | win widens (WR_GAP_FIX blend) |
| TE | −0.195 (win) | **−0.454** (win) | win widens (TE retrain) |
| **OVERALL** | **−0.009** (win) | **−0.325** (win) | **4 of 4 positions now win**, was 3 of 4 |

(vs ESPN, computed but not surfaced on the JSON's single-source consensus
section — same data available in
`output/backtest/clickthrough_fix_20260816/consensus_matched_espn_half_ppr_20260816_112738.csv`:
overall −0.256, QB −0.261, RB −0.381, WR −0.105, TE −0.453 — also 4 of 4.)

Note: these numbers are *better* than `HYBRID_SHIP_2026_08_15.md`'s own
headline table (−0.293/−0.228 overall) because that report predates
`WR_GAP_FIX_2026_08_16.md`'s WR blend, which shipped afterward — this
regeneration reflects the actual current `models/residual/*_meta.json` on
disk (verified: `wr_residual_meta.json` carries
`blend_secondary_dir`/`blend_weight: 0.4` from WR_GAP_FIX). The WR-specific
gap (−0.067/−0.105) is a bit better than WR_GAP_FIX's own reported
−0.0120/−0.0561 at the same blend weight; both agree on the sign (WR now
beats both sources) and the difference is consistent with WR_GAP_FIX's own
caveat that its tuning numbers came from 2-season-chunked swap-based runs
rather than a single combined 3-season pass through the real production
code path (this regeneration used the latter, i.e. it's the more
authoritative end-to-end number).

**"3 OF 4 POSITIONS" badge**: this text was never hardcoded — it's computed
live in `accuracy-dashboard.tsx` (`CONSENSUS_WINS = CONSENSUS.positions.filter(p
=> p.win).length`) from the JSON. Regenerating the JSON alone flips it to
"4 of 4 positions" everywhere it's used (accuracy page leaderboard headline,
`ProofStrip` on the home hub). No hardcoded copy needed fixing there. Grade
thresholds (`lib/nfl/accuracy-grade.ts`) are also purely computed from the
numbers — untouched, correctly reflect the new grades (RB gap −0.310 now
grades as a win, not D).

**Separately found and fixed: hardcoded stale claims on the public marketing
page** (`web/frontend/src/app/page.tsx`, route `/`, not `/dashboard`) — a
`RECEIPTS` array with hand-typed July numbers (−0.090/−0.027 overall,
"RB +0.26 · we're working on it" shown as a loss). Not literally the "home
hub" (`/dashboard`, which reads the JSON dynamically and is fixed by the
regen above) but directly adjacent and now inconsistent with the corrected
accuracy page, so updated to the same 2026-08-16 numbers and flipped RB from
"WIP/loss" to "beats both" (all 4 positions now win both sources, so the
public page's "we beat both overall" framing is fully true position-by-
position for the first time, not just in aggregate).

### Home hub charts rendering with no series — separate CSS bug, not a data issue

Both charts on `/dashboard` (`MAEByPositionChart`, `WeeklyAccuracyChart`) DO
read populated `modelMetrics.positions` / `modelMetrics.weeklyMae` arrays —
this was never a missing-data problem. Verified live on the deployed site
(`https://frontend-jet-seven-33.vercel.app/dashboard`) via DOM inspection:
the recharts `<path>` elements for both charts exist with real computed
geometry and non-transparent colors (`opacity: 1`, real `d` attribute), but
`getBoundingClientRect()` showed both `ResponsiveContainer`s at
**1193×671px**, positioned starting at `x=1308` (or `y=816`, i.e. off to the
side / below the fold) — nearly double the ~590px width a `md:grid-cols-2`
column should give them.

**Root cause: a classic CSS Grid "blowout".** `grid grid-cols-1 ...
md:grid-cols-2` (`web/frontend/src/app/dashboard/page.tsx`) wraps each chart
in a `<FadeIn>` (a `motion.div`, `src/lib/motion-primitives.tsx`) with no
`min-width` set. CSS Grid items default to `min-width: auto`, which lets a
wide-content child (recharts' `aspect-video` `ResponsiveContainer`, whose
intrinsic/measured width can exceed the intended track) force the grid
track to grow to fit content instead of splitting 50/50 — the chart still
renders correctly (axes, bars/lines, real data) but gets pushed almost
entirely off-screen, which reads as "empty axes, no series" in a normal
viewport. Confirmed live by patching `min-width: 0` onto the grid's direct
children via devtools and re-screenshotting — both charts immediately
rendered in-place with full bars/area visible.

**Fix:**
- `web/frontend/src/app/dashboard/page.tsx`: added `className='min-w-0'` to
  both `<FadeIn>` wrappers around the two charts (the direct grid-item fix,
  verified live).
- `web/frontend/src/components/ui/chart.tsx` (`ChartContainer`): added
  `min-w-0` to the container's own class list as defensive root-cause
  hardening, so any other page that puts a chart inside a shrinking
  flex/grid container without remembering to add `min-w-0` doesn't hit the
  same bug.

## 2. Projections page — offseason join mismatch

**Root cause (verified against real data, not the assumed one):** the top
weekly table wasn't actually the "blank void" theorized — `get_projections(2026,
1, ...)` correctly serves 1,000 rows via the existing preseason fallback — but
there was no guard for a genuine zero-row 200 response, only an `isError`
`EmptyState`. The real, confirmed bug was in the Multi-Source Comparison's
`get_comparison()` (`web/api/services/projection_service.py`, ~line 825-853):
it resolves the archived `external_projections` Silver slice back to the
latest one with data (`season=2025/week=18`), then pivots that archived
parquet's `source` column into wide columns (`ours`/`sleeper`/`espn`/`yahoo`).
The archived snapshot for that slice
(`data/silver/external_projections/season=2025/week=18/external_projections_20260611_004337.parquet`)
was written 2026-06-11 — before our own Gold weekly projections for that
week existed (earliest `data/gold/projections/season=2025/week=18/` file is
2026-07-02) — so the archived "ours" rows are permanently empty for that
slice, even though live Gold data for `season=2025/week=18` exists today
(354 rows). Not a season/week mismatch (the top table and comparison table
already resolve the same slice) — a stale-ingestion gap in one archived
snapshot.

**Fix:**
- `web/api/services/projection_service.py::get_comparison` — after building
  the wide pivot, overlay the `ours` column with a live call to
  `get_projections(resolved_season, resolved_week, scoring_format)` keyed by
  `player_id`, falling back to the archived value via `combine_first` when
  live data isn't available. Verified: comparison endpoint now returns real
  `ours` values for all 50 rows in the season=2025/week=18 fallback slice
  instead of `null`/dashes.
- `web/frontend/src/features/nfl/components/projections-table/index.tsx`
  (~line 200-222) — added a `projections.length === 0` branch rendering
  `EmptyState` ("No projections yet" / explanatory description), mirroring
  the weekly-report page's honest `mode: 'preseason'` pattern, between the
  existing `isError` and success branches.

**Tests:** `tests/web/test_projections_comparison.py` — new
`test_comparison_endpoint_overlays_live_ours_when_archive_missing_it`
(archived Silver has only `sleeper`, live Gold has `ours`; asserts overlay
wins); file: 8/8 passed. New frontend tests:
`projections-table/__tests__/index.test.tsx` (empty-state + populated-rows,
2/2) and `__tests__/projection-comparison-table.test.tsx` (fallback banner +
populated Ours column, 1/1). Full backend `tests/web/`: 161/161 passed.

## 3. Scores page — CSS grid blowout, not a data/API bug

**Investigated and ruled out first:** data (16 games in
`data/bronze/schedules/season=2025/`), `src/game_archive.py::get_game_results(2025,
1)` (16 rows), the local API, and the live prod backend
(`https://gesmith0606-nfl-data-api.hf.space/api/games?season=2025&week=1`,
`count: 16`) all correctly return the full 16-game slate. The frontend's own
proxy route (`/api/games?season=2025&week=1`) also returns `count: 16` right
now, and all 16 `[data-game-id]` cards exist in the DOM. So this was never a
data or query bug.

**Actual root cause (found via live DOM inspection of the deployed
`/dashboard/games?season=2025&week=1`, reproduced the "1 visible card" bug
directly):** the same CSS Grid "blowout" class of bug as Finding 1's charts,
this time inside a shared component. `GameResultsGrid`
(`web/frontend/src/features/nfl/components/game-results/index.tsx`) renders
its 16 `GameCard`s through `<Stagger className='grid grid-cols-1 ...
xl:grid-cols-4'>`. `Stagger` (`web/frontend/src/lib/motion-primitives.tsx`)
wraps *each* child in its own internal `<motion.div variants={itemVariants}>`
with no `className` — that internal wrapper, not the card itself, is the
actual direct grid item, and it had no `min-width: 0`. Grid's default
`min-width: auto` let the wide-content card (long team names, `nowrap` score
row) blow each column out to ~616px, so `gridTemplateColumns` computed to
`616px 616px 616px 616px` (2,512px total) — cards 2-16 got pushed off-screen
to the right/below the fold, leaving only card #1 (ARI@NO) visible, which is
exactly the reported symptom. Confirmed by patching `min-width: 0` onto the
16 grid-item wrappers live via devtools and re-screenshotting: all 16 cards
immediately snapped into a correct 4-column grid.

The "half-faded" look is confirmed correct, unrelated styling — per-team
win/loss dimming (`text-white/50` on the losing team's row) inside each
card, not a broken whole-card fade; it reads fine once the full slate
renders.

**Fix:** `web/frontend/src/lib/motion-primitives.tsx`, `Stagger`'s per-child
wrapper — added `className='min-w-0'`. This is the shared root cause (also
used by `stat-cards.tsx`'s `Stagger`-based grid and any future
`<Stagger className='grid ...'>` usage), so fixing it once here prevents the
same bug recurring elsewhere, matching Finding 1's chart fix in
`components/ui/chart.tsx` / `dashboard/page.tsx`.

A prior investigation pass (background agent, before this bug was traced)
concluded "could not reproduce" after checking data/API/backend and a
single screenshot that happened not to trigger the blowout — it hardened
`game-results/__tests__/index.test.tsx` to mock a 4-game slate instead of 1
(`tests/test_game_archive.py`: 28 passed). That test still doesn't catch
this specific CSS layout bug (jsdom doesn't lay out CSS Grid), so no
regression test was added for the blowout itself — the fix is a one-line
change to a shared, already-tested primitive.

## 4. Verification

- Backend: benchmark regeneration reproduces documented gate populations
  exactly (n=7,009/6,721); numbers cross-checked against
  `HYBRID_SHIP_2026_08_15.md` and `WR_GAP_FIX_2026_08_16.md` (see §1 note on
  the WR figure). `tests/web/`: 161/161 passed. `tests/test_game_archive.py`:
  28/28 passed.
- Frontend: `npm test` (vitest) in `web/frontend/` — **341 passed, 54 test
  files passed, 0 failed** (final run, after all four findings' edits
  landed, including the two new test files added for Finding 2 — no
  dedicated tests existed for most touched components, e.g.
  `accuracy-dashboard.tsx`, `home-modules.tsx`, `mae-chart.tsx`,
  `accuracy-chart.tsx`, `page.tsx`, `dashboard/page.tsx`,
  `components/ui/chart.tsx`, `motion-primitives.tsx` — so the full suite
  was run as a regression check for those; all pass).
- `npx tsc --noEmit`: no type errors in any touched file.
- Both CSS grid-blowout fixes (Finding 1 charts, Finding 3 game cards) were
  verified against the *live deployed site*
  (`https://frontend-jet-seven-33.vercel.app`) by reproducing the bug via
  DOM/network inspection, then confirming the fix (`min-width: 0`) resolves
  it via a live devtools patch + re-screenshot — not just reasoned about
  statically.
