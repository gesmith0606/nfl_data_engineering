# ELITE_MODELS_PLAN.md — Path from Honest Grades to A+

*Planned 2026-06; post-v4.2. Governing principle: the binding constraint is INFORMATION (new data, external benchmarks), not architecture. Any proposal that is "fancier model, same features" is rejected by default.*

## Executive Summary (one page)

**Where we are.** Fantasy heuristic B+ (4.71 MAE, sealed-2025 confirmed, TE hybrid shipped at 3.36) — but ungraded against any external consensus. Spread C+ (52.9% OOF ATS, statistically indistinguishable from break-even at n=1557; binomial 95% CI ≈ ±2.5pts). Totals D (no edge). Graph C (surviving features are lagged aggregates; the distinctive matchup features were leaks). Eval infra A− (the only reason we know all of the above).

**The reframe.** "A+" cannot mean "lower MAE in our own backtest" — that grade is self-referential. A+ means: (1) Fantasy: **beat the free consensus** (Sleeper/ESPN) head-to-head on matched player-weeks; (2) Spread: **positive closing-line value** sustained over a live season, not ATS% on historical OOF; (3) Totals: an honest kill unless a falsifiable edge hypothesis survives a 1-week diagnosis; (4) Graph: lagged matchup features that move the consensus-gap metric, built on the participation data we already have locally (verified dense 2020–2025).

**The unlock discovered during planning:** Sleeper's projections endpoint serves *historical* weeks (verified live for 2023 w5). The external benchmark — the single biggest blind spot — can be stood up against 2022–2025 in days, using the already-built Phase 73 ingesters. Every subsequent fantasy decision then optimizes `MAE_ours − MAE_consensus` instead of raw MAE.

**Sequencing in one line:** Week 1: consensus harness + totals verdict + holdout re-seal. Weeks 2–5: opponent-adjusted allowances + participation-derived route rates + lagged WR/TE matchup rebuild + The Odds API capture starting before the 2026 season. Month 2+: live 2026 graded season (consensus gap + true CLV), then and only then the PFF buy decision and Neo4j activation, each gated on demonstrated need.

**Honest expectations:** Fantasy: closing a 0.1–0.3 MAE gap to consensus is plausible; beating it outright is uncertain — knowing the gap is the deliverable. Spread: most likely outcome is "no sustainable edge at closing lines; possible edge at openers" — the 2026 capture infrastructure decides this with data. Totals: expect kill. Graph: one or two real lagged matchup features is success; ten is fantasy.

---

## Current State Reference (validated during planning)

| Asset | Location | State |
|---|---|---|
| Fantasy heuristic + eval | `src/unified_evaluation.py`, `scripts/backtest_projections.py`, `scripts/production_eval.py`, `scripts/experiment_heuristic_lab.py` (cached sweeps) | 4.71 MAE 2022-24 w3-18 half-PPR |
| External projections pipeline | `scripts/ingest_external_projections_{espn,sleeper,yahoo}.py`, `src/external_projections.py`, `scripts/silver_external_projections_transformation.py`, `.github/workflows/weekly-external-projections.yml` | Built (Phase 73), forward-only, no historical data committed |
| Sleeper historical projections | `https://api.sleeper.app/v1/projections/nfl/regular/{season}/{week}` | **Verified live for past weeks (2023 w5)** |
| Game ensemble | `src/ensemble_training.py` (spread + total targets), `src/prediction_backtester.py` | 52.9% OOF ATS; `evaluate_clv` is model-vs-close, not true CLV |
| Odds | `scripts/bronze_odds_ingestion.py` (FinnedAI 2016–21, dead), nflverse `spread_line`/`total_line` (closing only) | No openers, no live capture |
| Participation | `data/bronze/pbp_participation/season=2020..2025` (`game_id, play_id, offense_players, defense_players`) | 100% non-null 2023–25, 92.8% 2021 |
| Graph features | `scripts/compute_graph_features.py`, `src/graph_{wr,te}_matchup.py` (excluded as same-game leaks), survivors in `src/graph_{qb_wr_chemistry,red_zone,game_script,injury_cascade}.py` | TE hybrid shipped on survivors |
| Leak detector | `detect_leakage` via `scripts/assemble_player_features.py --validate` | Working; every new feature must pass |

---

## PHASE 1 — Quick Wins (days; ~1 week total)

### 1.1 Beat-the-Consensus Harness (fantasy) — 2–3 days. HIGHEST PRIORITY.

**What:** Backfill Sleeper historical projections for 2022–2025 w1–18, then extend `scripts/backtest_projections.py` with a `--vs-consensus` mode.

**Steps:**
1. Add `--historical --season S --weeks 1-18` to `scripts/ingest_external_projections_sleeper.py`, hitting the verified endpoint; write Bronze parquet in the existing Phase 73 schema (`data/bronze/external_projections/sleeper/season=YYYY/week=WW/`). Map `sleeper_id → gsis player_id` via `nfl.import_ids()` / `src/player_name_resolver.py` (pattern already in `scripts/refresh_adp.py`).
2. Run `scripts/silver_external_projections_transformation.py` over the backfill.
3. In `scripts/backtest_projections.py` (hook into `run_backtest()` / `print_summary()`): join consensus on `(player_id, season, week)`; restrict to **matched player-weeks** only and compute both systems on the identical set.
4. Optional second source: Wayback Machine snapshots of FantasyPros weekly projection pages (via fetch MCP) — best-effort, do not block on it.

**Metrics (define once, never change):** half-PPR, weeks 3–18, players with consensus projection ≥ 5 pts:
- **Head-to-head MAE** per position and overall (primary).
- **Spearman rank correlation** within position-week (start/sit relevance).
- **Top-N hit rate**: of actual top-12 QB/TE, top-24 RB/WR each week, fraction appearing in each system's projected top-N.

**Validity check (gate 0):** Sleeper's archive must be *pre-game* projections. Verify: players ruled out before kickoff (cross-ref `injuries` Bronze) should show ~0 projections; spot-check 20 player-weeks vs contemporaneous reporting. If archive looks post-hoc revised, fall back to forward-only collection + Wayback.

**Success gate:** harness runs on ≥3 seasons with ≥85% player-week match rate; per-position gap table produced.
**Expected gain:** zero MAE improvement — this *re-grades* everything. Expect to learn we trail consensus by 0.1–0.4 MAE overall with position-level variance (we may already win at TE post-hybrid).
**Kill criterion:** none — this is the new grading scale. Only the validity check can redirect it.

### 1.2 Game Totals: Kill-or-Fix Diagnosis — 2 days

**What:** A one-shot diagnostic script (pattern: `scripts/ablation_market_features.py`) answering three questions on existing OOF predictions:
1. Does `predicted_total` carry any signal beyond `total_line`? Regress `actual_total ~ total_line + predicted_total`; report partial coefficient and t-stat.
2. Residual analysis of `actual_total − total_line` against the only plausible edges: **wind ≥ 15mph, temperature extremes, dome/outdoor** (from `src/game_context.py` weather features), cumulative starter-injury counts, pace interaction (both teams top-quartile lagged pace). Markets are known to be slowest on wind.
3. Calibrator sanity: current near-zero slope means the model is noise around the line.

**Fix path (only if Q2 shows signal):** abandon predicting `actual_total`; predict `actual_total − total_line` (deviation) from weather/injury/pace interactions only — a deliberately tiny model (≤10 features).
**Success gate for "fix":** deviation model ≥ 52.5% O/U on OOF (n ≥ 800) **and** calibration slope ≥ 0.5 **and** wind-game subset ≥ 55%.
**Kill criterion (expected outcome):** anything less → delete totals from the betting surface; keep `predicted_total` as website content labeled "market tracking," freeing maintenance. Killing a D-grade model honestly *is* the A+ move here.

### 1.3 Eval Hygiene: Re-seal + Unblock CI — 1 day

- **Holdout ledger:** add a gate-use ledger to `scripts/production_eval.py` summaries (count of sealed-2025 evaluations; 3 already burned this session). Declare sealed-2025 *amber*: usable for confirmation, no longer for selection.
- **New sealed set:** 2026 season, forward-only, zero-look — automatic via the weekly pipeline. All Phase 2 work selects on 2022–24 CV and confirms on amber-2025 at most once per shipped change.
- **Fix the hanging test:** mark the network-dependent test with `pytest.mark.network`, excluded by default in `/test` (CLAUDE.md command). Restores trustworthy full-suite runs.
- AWS creds (Phase 76) stay a separate workstream; everything here is local-first.

### 1.4 Live Odds Capture Spike (The Odds API) — 1–2 days build, then passive

**What:** `scripts/bronze_odds_api_ingestion.py` modeled on `bronze_odds_ingestion.py`, hitting The Odds API (free tier: 500 credits/mo; `/v4/sports/americanfootball_nfl/odds`, spreads+totals, 2–3 books). Schedule 2×/day via a small GHA cron (pattern: `daily-sentiment.yml`), committing parquet like TD-08/09 paths. First snapshot per game ≈ opener proxy; last before kickoff ≈ close.
**Why now:** True CLV evaluation (2.4) is impossible without openers, and history cannot be backfilled free. Every week not capturing is a week of 2026 evaluation lost. Season starts ~Sept 2026; look-ahead lines appear earlier.
**Success gate:** by 2026 w1, ≥95% of games have ≥2 timestamped snapshots (open-proxy + close).
**Cost:** $0 (free tier sufficient at 2 snapshots/day). Upgrade ($30/mo) only if line-history granularity is later proven valuable.
**Kill criterion:** none for capture (cheap, irreversible to skip); downstream models can die without killing the data.

---

## PHASE 2 — Medium (weeks 2–6)

### 2.1 Fantasy: Opponent-Adjusted Yardage Allowances — ~1 week

**What:** Current matchup multiplier uses lagged defensive strength (v4.2). Sharpen to **position-specific yardage/reception allowances**: trailing opponent-adjusted passing yards allowed to WRs/TEs/RBs (receiving vs rushing split), as multiplier inputs swept in `scripts/experiment_heuristic_lab.py` (extend `build_defense_strength()`; cached-sweep infra already exists). Strictly weeks-(1..t-1) trailing; pass `detect_leakage`.
**Success gate:** ≥0.03 MAE improvement on 2022–24 w3-18 CV **and** consensus gap (1.1 metric) narrows; confirm once on amber-2025.
**Expected gain:** 0.03–0.06 MAE. **Kill:** <0.02 MAE after the standard sweep grid → revert (lab makes this cheap).

### 2.2 Fantasy: Participation-Derived Route Rate + Snap-Share Trends — ~1 week

**What:** Routes-run data is paid (PFF/FTN) — but a **route-participation proxy** is free: from `data/bronze/pbp_participation` (verified dense), compute per player-week *share of team dropbacks on field* (player in `offense_players` on pass plays). This is the standard "route rate" workhorse that consensus projections lean on. Add: trailing 4-week route-rate, week-over-week delta, and snap-share slope (snap_counts Bronze already ingested). New module `src/graph_route_participation.py` following `src/graph_qb_wr_chemistry.py` patterns, registered in `scripts/compute_graph_features.py`; consumed as heuristic multiplier candidates (lab sweep) and as TE-hybrid Ridge features (`src/ml_projection_router.py`).
**Success gate:** same as 2.1 (≥0.03 MAE CV + consensus-gap narrowing). Route-rate proxy must correlate ≥0.8 with snap-share on pass-heavy scripts as a sanity check.
**Expected gain:** 0.03–0.08 MAE for WR/TE — usage trend is the highest-information lagged signal that rolling point averages miss (e.g., role changes after trades/injuries appear in routes a week before in points).
**Kill:** <0.02 MAE and no consensus-gap movement → keep as web-content feature only.

### 2.3 Lagged WR/TE Matchup Rebuild — 1–2 weeks (overlaps 2.2)

**What:** Rebuild the excluded `wr_matchup_*`/`te_matchup_*` features (`src/graph_wr_matchup.py`, `src/graph_te_matchup.py`) as **trailing** versions: opponent's prior-weeks-only per-coverage-unit stats (yards/target allowed to outside WRs vs slot, TE yards allowed per route defended), with defender identity from `defense_players` × rosters/depth_charts (both committed Bronze paths, TD-08). Same `(season, week)` API as survivors so `scripts/compute_graph_features.py` and the leak detector slot in unchanged.
**NOTE (2026-06-10):** simple per-player trailing means of the old same-game aggregates (`_trail8`) were already tried — SHAP selected zero of them; receiver-efficiency form is noise. The rebuild must be **opponent/coverage-unit-centric** (defense-side trailing allowances), not player-form-centric.
**Success gate:** passes `assemble_player_features.py --validate` (prev-week corr > same-week corr pattern, no flag); improves TE hybrid sealed-amber MAE (≤3.32 from 3.36) or enables a WR hybrid that beats WR heuristic by ≥0.05 CV MAE.
**Expected gain:** modest — TE 0.03–0.05; WR residual revival is a coin flip (residual signal was thin for real reasons).
**Kill:** if leak-cleaned versions show CV |effect| <0.02 MAE → archive the modules and write the negative result into `.planning/`; this also feeds the PFF ROI decision (3.2) — "we tried the free version of matchup data; here's exactly where it ran out."

### 2.4 Spread: QB/Injury-Status Features + True-CLV Plumbing — ~1 week

**What:** Two parts.
1. **Features:** starting-QB-out indicator and weighted starter-injury counts (injuries + depth_charts Bronze, both available historically) joined into `src/feature_engineering.py`'s game vector. Honest framing: closing lines fully price QB news; the hypothesis is only that *early-week* lines lag — testable solely after 1.4 capture exists. On closing-line OOF expect ≈0 ATS gain; ship the features anyway because they're required for the open-line experiment.
2. **True CLV:** extend `src/prediction_backtester.py` — keep `evaluate_clv` (model-vs-close) but add `evaluate_line_capture(open_line, close_line, pick_side)`: did our pick's number beat the close? Wire `scripts/backtest_predictions.py --clv-true` to the 1.4 Bronze snapshots. **Declare CLV the primary spread metric in CLAUDE.md**; ATS% demoted to secondary.

**Success gate (deferred to 2026 season):** mean signed line capture > +0.3 pts on picks made at open-proxy, n ≥ 100 picks, by 2026 w10.
**Kill:** capture ≤ 0 at n ≥ 150 → declare no betting edge; spread model survives as a calibrated-probability content feature (already shipped), and we stop spending model effort on it.

### 2.5 Quantile Floor/Ceiling Recalibration — 3–4 days

**What:** Retrain `src/quantile_models.py` (p10/p50/p90) on the **post-leak-audit clean feature set** plus 2.1/2.2 survivors; v4.2's leak fixes mean current quantiles were trained on partially leaky inputs.
**Success gate:** empirical coverage of the 10–90 band ∈ [78%, 82%] on 2022–24 CV (currently unverified); pinball loss not worse than current.
**Expected gain:** trustworthy floor/ceiling for the website/advisor — a product win more than an MAE win.
**Kill:** if coverage can't be calibrated within ±4pts, ship conformal-adjusted bands (simple offset on residual quantiles) instead — never ship known-miscalibrated intervals.

### 2.6 Vegas Priors in Backtest Path — 2 days (audit, likely no-op)

`scripts/backtest_projections.py:_compute_week_implied_totals` already injects implied totals; **audit** that backtest and production (`src/projection_engine.py` Vegas multiplier) use identically-timed lines (nflverse closing lines in backtest vs live lines in production = acceptable, but document it; flag if backtest uses any post-game-revised line). Success gate: written parity note + test in `tests/`. This closes a silent eval-validity hole rather than adding signal.

---

## PHASE 3 — Strategic (month+; mostly gated on 2026 season data)

### 3.1 The 2026 Graded Live Season (Sept 2026 →) — the real exam

Weekly automation (extend `weekly-pipeline.yml`): consensus-gap dashboard (1.1 metrics, ours vs Sleeper vs ESPN, cumulative), spread line-capture report (2.4), totals content. All forward-only = un-erodible sealed evaluation.
**A+ definitions, set now:**
- **Fantasy A+:** cumulative matched-MAE ≤ Sleeper consensus over 2026 w3–18, and rank-corr within 0.01 of consensus. (A = within 0.1 MAE of consensus; we may already be there.)
- **Spread A+:** mean line capture > +0.3 pts, n≥150, with calibrated probabilities (Brier ≤ market-implied baseline).
- **Totals A+:** honest kill executed, or the 1.2 wind-model surviving its live gate.

### 3.2 PFF / Paid-Data ROI Decision — decide ~Nov 2026, not before

**Framework:** Buy PFF ($200–500/yr; VISION.md says ~$200 researcher tier — verify current pricing) **only if** 2.3's free participation-derived matchup features showed promise but hit a measurable data ceiling (e.g., coverage-assignment ambiguity demonstrably capping the feature). Evaluate FTN first — `nfl_data_py.import_ftn_data` is free, 2022+, with charting columns we've never used. The consensus-gap metric prices the decision: if the remaining gap to consensus is ≥0.1 MAE and concentrated in matchup-sensitive positions, $300 is cheap; if we already match consensus, it buys nothing.
**Kill:** no purchase without a named feature, a backtest plan, and a predicted MAE/CLV delta written down *in advance*.

### 3.3 Neo4j Aura Activation — default OFF

**Criteria (all three required):** (a) a shipped feature needs multi-hop relational queries pandas can't express cleanly (e.g., injury-cascade across 3+ degrees, coaching-tree transfer); (b) the pandas fallback in `src/graph_db.py` exceeds ~10 min in the weekly pipeline; (c) the feature it serves has already passed its MAE/CLV gate *on the pandas implementation*. Aura is an ops upgrade, never a modeling bet. Expected outcome through 2026: stays off.

### 3.4 Odds Data Depth (conditional on 2.4 surviving)

If line capture > 0 at n≥100: upgrade The Odds API tier for historical line-movement granularity, add steam-move features to `src/market_analytics.py` (the `NaN` steam placeholder becomes real). If 2.4 killed: free tier continues for content only.

---

## Recommended Sequencing

| Order | Item | Effort | Blocking? |
|---|---|---|---|
| 1 | 1.1 Consensus harness + Sleeper backfill | 2–3 d | Blocks honest grading of everything fantasy |
| 2 | 1.3 Re-seal + CI fix | 1 d | Blocks trustworthy gates |
| 3 | 1.4 Odds capture cron | 1–2 d | **Calendar-critical** — cannot backfill |
| 4 | 1.2 Totals verdict | 2 d | Frees effort |
| 5 | 2.2 Route-rate proxy + snap trends | 1 wk | Highest expected fantasy gain |
| 6 | 2.1 Yardage allowances | 1 wk | Parallel w/ 2.2 (same lab) |
| 7 | 2.3 Lagged matchup rebuild | 1–2 wk | Feeds 3.2 PFF decision |
| 8 | 2.4 Spread features + true-CLV plumbing | 1 wk | Must land before 2026 w1 |
| 9 | 2.5 Quantile recalibration, 2.6 Vegas audit | 1 wk | Product polish |
| 10 | 3.1 Live graded season | passive | Sept 2026 → |
| 11 | 3.2 PFF decision, 3.3 Neo4j, 3.4 odds depth | — | Gated on live evidence |

**What this plan deliberately does NOT do:** no new model architectures on existing features (rejected per session lesson), no WR/RB/QB residual retries without new information (2.2/2.3 are the new information; retry only behind them), no Neo4j/PFF spending before a measured need, and no totals "fix" without the diagnosis proving a falsifiable edge first.

---

### Critical Files for Implementation
- `scripts/backtest_projections.py` — consensus harness integration point (`run_backtest`, `print_summary`, `_compute_week_implied_totals`)
- `scripts/ingest_external_projections_sleeper.py` — historical backfill of the verified Sleeper projections endpoint
- `scripts/compute_graph_features.py` — registration point for route-rate proxy and lagged WR/TE matchup rebuilds
- `src/prediction_backtester.py` — replace pseudo-CLV (`evaluate_clv`) with true open-vs-close line capture
- `scripts/experiment_heuristic_lab.py` — cached-sweep lab where all new fantasy multipliers (2.1/2.2) are gated
