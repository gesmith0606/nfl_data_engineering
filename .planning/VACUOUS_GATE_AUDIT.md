# Vacuous-Gate Audit — 2026-08-09

Prompted by two incidents this weekend where a "gate" passed because ZERO
rows reached it:

1. Phase 61's event-adjustment gate (`scripts/backtest_event_adjustments.py`)
   — "no regression possible" because no Gold sentiment weeks existed, read
   as `verdict=SHIP`.
2. RB_SNAP_COLLAPSE correction — a silent no-op in every backtest because
   snaps Bronze was absent, and nothing checked for it.

Pattern per `.planning/SENTIMENT_ROLE_LEVER.md` and
`knowledge-vault/concepts/gated-experiment-coverage-check.md`: a gate that
evaluates to PASS on an empty population is not a real pass. This audit
inventories every gate/check/validation in the repo that can render a
verdict, classifies each, and fixes every VACUOUS-CAPABLE one found.

Note: `scripts/check_data_completeness.py` and
`.planning/DATA_COMPLETENESS_AUDIT.md` landed in this same repo, same day,
from a concurrent agent working the sibling problem (missing Bronze paths
causing the exact RB_SNAP_COLLAPSE class of silent hole). That script is
inventoried below (already SAFE-by-design) rather than duplicated.

## Classification legend

- **VACUOUS-CAPABLE** — can render a favorable verdict (PASS/SHIP/OK) with
  n=0 or an empty/untouched population reaching the decision point.
- **SAFE** — has an explicit non-empty / minimum-population guard, or fails
  closed (not-PASS) on empty input by construction.
- **N/A** — not a pass/fail gate (informational script, no exit-code
  contract, or dead/unreachable infra).

## Inventory

| # | Gate | Location | Classification | Notes / Fix |
|---|------|----------|-----------------|-------------|
| 1 | `_overall_verdict` (event-adjustment backtest) | `scripts/backtest_event_adjustments.py` | **VACUOUS-CAPABLE → FIXED** | The literal Phase 61 incident. `events_weeks==0` → treatment byte-identical to baseline → delta=0 everywhere → `verdict=SHIP` printed and written to the markdown report as a real pass. Fixed: added `events_weeks` param; forces `verdict="NO_DATA"` (distinct from SHIP/SKIP) when 0 firing weeks, plus a `Lever firing rate: N/M weeks` print before the verdict line, per the coverage-check doc's mandatory ordering rule. |
| 2 | `print_consensus_report` verdict block | `scripts/backtest_projections.py` | **VACUOUS-CAPABLE → FIXED** | `overall_df = pos_data_all` can be empty even when the pre-filtered `matched_df`/`df` are non-empty (e.g., matched rows all fall outside QB/RB/WR/TE). `NaN < -0.01` and `NaN > 0.01` are both `False`, so the un-guarded branch structure fell through to `"Ours matches consensus"` — a fabricated verdict on 0 rows. Fixed: explicit `if overall_df.empty:` guard prints `"NO DATA"` and returns before computing MAE. Assertion-only; no scoring/backtest logic touched (respects the file-edit constraint on this file). |
| 3 | Snap-count / route-participation coverage notices | `scripts/backtest_projections.py::run_backtest` | **VACUOUS-CAPABLE → FIXED** | This is the actual RB_SNAP_COLLAPSE incident site: when local `players/snaps` (or Silver route-participation) Bronze is absent, the RB snap-collapse / WR route-slope-collapse corrections silently no-op for the entire backtest — previously surfaced only as a bare `print()` easy to lose in output, with no gate reading it. Upgraded both to `logger.warning(...)` with a greppable `GATE COVERAGE:` prefix stating explicitly that the correction "will be a SILENT NO-OP for this entire run." No computation changed — same condition, louder signal. |
| 4 | `compute_ship_or_skip` call site | `scripts/ablation_market_features.py` | **VACUOUS-CAPABLE → FIXED** | `evaluate_baseline`/`evaluate_ablation_model` both return `ats_accuracy=0.0, n_games=0` on an empty holdout. `0.0 > 0.0` is `False`, so this currently ties to SKIP — but only by accident of both zeros comparing equal, not by an explicit floor. Fixed: extracted `compute_ship_or_skip_gated(baseline, ablation)` which checks `n_games` explicitly on both arms and forces `SKIP` with a logged `VACUOUS GATE:` error when either is 0, before ever consulting the (meaningless) accuracy numbers. `compute_ship_or_skip` itself is untouched (still pure/tested). |
| 5 | RB/others gate | `scripts/backtest_vacated_opportunity.py::main` | **VACUOUS-CAPABLE → FIXED** | `others_ok = (others["spearman_delta"] >= -0.005).all()` — pandas `.all()` on an all-NaN-comparison array is `False` today (NaN comparisons are False), so this happens to fail closed, but only incidentally; a fully-empty `others` frame (not just NaN-filled via `reindex`) would vacuously return `True`. Also `rb_improves` reads `rb["spearman_delta"]` with no floor. Fixed: explicit `rb_n = combined.loc[position=="RB", "n"].sum()`; if `rb_n == 0` or the RB spearman delta is NaN, print `HOLD (no data)` and return before reaching the real comparison. |
| 6 | `sanity_check_projections.py` — `run_sanity_check` main gate | `scripts/sanity_check_projections.py` | SAFE | `our_df = _load_our_projections(...)`; `if our_df.empty: return 1` guards the entire downstream check battery before any loop runs. Already audited in `.planning/SANITY_CHECKER_AUDIT.md` (2026-06-10) and hardened further in Phase 68 (DQAL-03/M1-M5). No fix needed. |
| 7 | `_check_consensus_cross_check`, `_check_projection_distribution`, `_check_roster_drift_top50`, `_check_dqal_negative_projection`, `_check_dqal_rookie_ingestion`, `_check_dqal_rank_gap`, `_check_projection_incorporates_recent_season` | `scripts/sanity_check_projections.py` | SAFE | Each has its own explicit `df.empty` / `len(...) < N` guard that emits a `SKIPPED`/`WARN` (not a fabricated PASS) and returns before any comparison. These check *optional secondary* infra (external consensus, rankings) — by design (per M3's own docstring) their absence is a WARN, not a CRITICAL; the primary population (Gold projections) is already gated by #6 above. |
| 8 | `check_ml_output.py::run_checks` | `scripts/check_ml_output.py` | SAFE | `_MIN_ROWS = 50` floor on CHECK2 (`if len(skill_df) < _MIN_ROWS: failures.append(...)`), file-existence CHECK1, all-zero-position CHECK4. Verified n=0 (empty parquet) explicitly fails CHECK2 (added as a regression test, see below) — this script was already correctly designed against the vacuous-pass pattern. |
| 9 | `check_pipeline_health.py` | `scripts/check_pipeline_health.py` | SAFE (but effectively dead) | `check_partition_exists`/`check_layer_freshness` return `ERROR` (not OK) on 0 matching S3 objects — fails closed by design. However this script only reads S3, and AWS credentials have been dead since March 2026 (`_make_s3_client` raises immediately, `run_health_checks` returns 1 before any layer check runs). Not vacuous — it hard-fails — but it can no longer validate anything about the local-first `data/` tree the rest of the pipeline actually reads. Flagged as a related (not vacuous-gate) finding below; not fixed here (would require a local-Bronze fallback rewrite, out of "assertion-only, minimal diff" scope, and `scripts/check_data_completeness.py` — see #16 — already covers the local-first case). |
| 10 | `validate_project.py` | `scripts/validate_project.py` | N/A | Manual diagnostic script; every `validate_*` function only prints `✅`/`❌`, never raises or returns a code, `__main__` has no `sys.exit`. Not a gate — no exit-code contract for anything to vacuously pass. |
| 11 | `NFLDataFetcher.validate_data` / `NFLDataAdapter.validate_data` | `src/nfl_data_integration.py`, `src/nfl_data_adapter.py` | SAFE | `if len(df) == 0: is_valid=False; issues.append("DataFrame is empty"); return`. Explicit, first check in the function. Adapter delegates to the same implementation. Covered by a new regression test (below) so a future refactor can't silently regress it. |
| 12 | `run_prediction_check` (game predictions) | `scripts/sanity_check_projections.py` | SAFE | `if df.empty: return (["No prediction data found"], [])` — empty predictions is a CRITICAL, not a pass. |
| 13 | `print_line_capture_report` gate (`mean_capture > +0.3, n>=100`) | `scripts/backtest_predictions.py` | SAFE | `if n == 0: print("No valid line-capture data..."); return` up front; separately, the PASS/FAIL verdict itself is only computed `if n >= 100`, else prints `"not yet evaluable"`. Matches CLAUDE.md's documented in-season gate (`mean >+0.3, n>=150` for the line-capture ship decision) — the n-floor is already baked in. |
| 14 | `q3_verdict` (totals-edge KILL/FIX gate) | `scripts/diagnose_totals_edge.py` | SAFE | Requires `abs(t) > T_THRESHOLD and n >= MIN_N_SUBGROUP and hr >= MIN_OU_ACC` per subgroup; `np.isnan` guards make any NaN subgroup ineligible; defaults to `"KILL"` (not a ship) when nothing passes. Fails closed. |
| 15 | `eval_matchup_candidate.py` gate | `scripts/eval_matchup_candidate.py` | SAFE | Per-position rows are only appended to `results_rows` after `if eval_df.empty: continue`, so a 0-row position never produces a row; `te_gate_pass`/`wr_gate_pass` default to `False` when `te_row`/`wr_row` is `None`, so `overall = te_gate_pass or wr_gate_pass` correctly defaults to `False` → `"KILL"` rather than a vacuous `"SHIP"`. |
| 16 | `check_data_completeness.py` (concurrent addition) | `scripts/check_data_completeness.py` | SAFE (by design) | New this session from a parallel agent's `DATA_COMPLETENESS_AUDIT.md` work (same repo, same root cause — RB_SNAP_COLLAPSE-class silent Bronze holes). `check_requirement` fails when `len(files) < req.min_files` (default 1) and separately checks `min_rows` via Parquet footer metadata to catch a written-but-empty file. Absence → FAIL, never a silent PASS. Ran against real local data: 88/88 PASS (see Test Results). Directly implements that audit's recommendation #4 ("add a loud non-silent check"), complementary to this audit's fixes #1-#5. |
| 17 | `audit_event_coverage.py` (EVT-04), `audit_advisor_tools_evt05.py` (EVT-05) | `scripts/` | SAFE | Both use explicit `count >= GATE` thresholds (`teams_with_events >= 8`, `non_empty_teams >= 20/8`); 0 always evaluates `False` → FAIL, never PASS. |
| 18 | `audit_advisor_tools.py` per-tool verdict | `scripts/audit_advisor_tools.py` | SAFE (deliberate) | Empty-payload responses map to `WARN` only when the specific probe opts in via `warn_on_empty`; otherwise `FAIL`. Per-tool judgment call already made explicitly in the probe config, not an unnoticed default. |
| 19 | pytest — frame-driven `.iterrows()`/parametrized tests | `tests/*.py` | N/A (scope-bounded) | 18 files use `.iterrows()` inside test bodies and 3 use frame-driven parametrization, but all build synthetic fixed-size fixtures inline (never load "real" accumulated data from `data/`) — an empty fixture would be an authoring bug caught immediately by `assert` on a known-fixed count, not a silent no-op against live data. 16 files read real Parquet from `data/`, but these are ingestion/bronze round-trip tests operating on data the test itself just wrote, not on the shared warehouse. This matches the existing `pytest.ini` `testpaths` exclusion of live-AWS/production-data probes (v8.2 changelog). No CI-critical "assert over an empty real-data frame" test found. |

## Fixes applied (summary)

| File | Change |
|------|--------|
| `scripts/backtest_event_adjustments.py` | `_overall_verdict()` takes `events_weeks`; returns `"NO_DATA"` (not `"SHIP"`) when 0 firing weeks. `main()` computes/prints the firing rate before the verdict. Markdown report text updated to describe `NO_DATA` explicitly instead of silently equating "no regression possible" with SHIP. |
| `scripts/backtest_projections.py` | `print_consensus_report`: guard + explicit "NO DATA" print when the post-filter population is 0 rows, before the MAE/verdict computation. Snap-count and route-participation "not found" notices upgraded from `print()` to `logger.warning("GATE COVERAGE: ...")` — same condition, louder signal (assertion-only; no backtest logic changed). |
| `scripts/ablation_market_features.py` | New `compute_ship_or_skip_gated(baseline, ablation)` — explicit `n_games` floor on both arms, forces `SKIP` with a logged error on 0 games. Call site in `run_ablation()`/`main()` now uses the gated wrapper. `compute_ship_or_skip()` itself untouched. |
| `scripts/backtest_vacated_opportunity.py` | `main()`: explicit `rb_n` / NaN check before the RB/others gate comparison; prints `HOLD (no data)` and returns on 0 RB rows instead of reaching the `.all()`-on-empty comparison. |
| `tests/test_gate_nonvacuity.py` | New. 8 tests feeding empty/n=0 populations to the 5 fixed gates plus `check_ml_output.run_checks` (0-row parquet) and `NFLDataFetcher.validate_data` (baseline contract), asserting none of them report a fabricated pass. |

## Test results

```
./venv/Scripts/python.exe -m pytest tests/test_gate_nonvacuity.py -v
8 passed, 4 warnings in 1.47s

./venv/Scripts/python.exe -m pytest tests/test_check_ml_output.py tests/test_ablation.py \
    tests/test_consensus_benchmark.py tests/test_sanity_check_v2_canary.py \
    tests/test_sanity_check_v2_drift.py tests/test_sanity_check_v2_probes.py \
    tests/test_sanity_check_weekly.py -q
99 passed, 3 warnings in 2.56s

./venv/Scripts/python.exe -m pytest tests/test_prediction_backtester.py tests/test_graph_vacated_opportunity.py -q
76 passed in 3.58s

./venv/Scripts/python.exe -m pytest tests/ -q --collect-only
3586 tests collected in 2.54s   (no collection errors — new test file imports cleanly)
```

Compile-check: `python -m py_compile` on all 4 edited scripts + the new test
file — clean.

### Modified check scripts run against real local data

- **`check_ml_output.py --season 2024 --week 1 --scoring half_ppr`** → PASS
  (RB=5/TE=3/WR=9 hybrid rows, all positions non-zero). Unmodified by this
  audit; confirms baseline behavior.
- **`backtest_event_adjustments.py --seasons 2024 --positions qb`** → ran to
  completion in ~15s. **Live finding (flag loudly): 0/16 weeks had Gold
  event data for 2024, exactly as `.planning/SENTIMENT_ROLE_LEVER.md`
  documented.** Before this fix, this exact real run printed
  `verdict=SHIP`. After the fix it correctly prints
  `verdict=NO_DATA` with `Lever firing rate: 0/16 weeks had event data`
  ahead of it. This is not a regression — it is the fix working as intended
  on the real, still-sparse sentiment data; `--use-events` remains
  correctly opt-in/off in `generate_projections.py` per the existing
  Phase 61 decision.
- **`backtest_projections.py --seasons 2024 --weeks 3-5 --vs-consensus`** →
  ran to completion, real 488-row matched population, real verdict
  ("Consensus BEATS ours by 0.29 MAE pts" for that narrow 3-week slice) —
  confirms the new empty-population guard does not fire on populated data.
- **`check_data_completeness.py --local`** → 88/88 PASS against real local
  `data/`, confirming the concurrent agent's Bronze backfill (weekly, snaps,
  injuries, draft_picks, combine 2016-2025) actually closed the holes it
  targeted.
- **`ablation_market_features.py --dry-run`** → could not complete in this
  environment: `models/ensemble/*.txt` (LightGBM) artifacts are corrupted
  ("Model format error, expect a tree here") and the run crashes during
  model loading, before ever reaching the code path this audit touched.
  Pre-existing environment issue, unrelated to the vacuous-gate fix — not
  addressed here (out of scope; flagged for a separate model-artifact
  investigation). The fix itself (`compute_ship_or_skip_gated`) was
  validated directly via unit tests and a manual REPL check (SKIP on
  n_games=0/0, SHIP on a populated real-improvement case).
- **`backtest_vacated_opportunity.py --seasons 2024`** → exits cleanly via
  the pre-existing `"no seasonal data ... skipping"` → `"No transitions
  evaluated."` early-out (no local Bronze seasonal data for 2022-2023 in
  this environment); the new RB-gate guard was not reached on this run
  (never got past `run_transition`) but was validated directly via the
  regression test using a synthetic `combined` frame shaped exactly like
  the real one.

## Related finding (not a vacuous-gate fix, flagged for follow-up)

`scripts/check_pipeline_health.py` (#9 above) only checks S3, and AWS
credentials have been dead since March 2026 per `CLAUDE.md`'s Configuration
section — it currently hard-fails on every invocation before checking
anything, rather than validating the local-first `data/` tree the rest of
the pipeline actually reads. Not vacuous (it fails, doesn't pass), so out of
this audit's fix scope, but it means this particular "pipeline health" gate
has been non-functional for validating local reality for months.
`scripts/check_data_completeness.py` (new this session, #16) already covers
the local-first case for the specific paths in its manifest, which
substantially closes this gap in practice.

## Counts

19 gates/checks inventoried.

- VACUOUS-CAPABLE found and fixed: **5** (#1-#5)
- SAFE (verified, no fix needed): **12** (#6, #7, #8, #9, #11, #12, #13,
  #14, #15, #16, #17, #18)
- N/A (not a pass/fail gate, or scope-bounded): **2** (#10, #19)
