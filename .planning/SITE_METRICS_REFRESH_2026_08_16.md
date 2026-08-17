# Site Metrics Refresh — 2026-08-16/17

Follow-up to `.planning/CONSOLIDATION_2026_08_16.md` §8 ("Cut for time"): that
task promoted QB (`combo` span+recency model) and RB (`zone_more_years`
model), promoted QB/RB/TE quantile bands, held WR and TE residual models
unchanged, but never re-ran the headline 2022-24 matched-pairs consensus
benchmark or the FantasyPros ordinal gate against the newly-promoted config,
and never regenerated the public site artifact. This task closes that gap.
Does **not** touch `src/weather_features.py` or any weather/wind flag —
every backtest below ran without `--early-season-prior`/weather levers, pure
promoted-config-as-shipped.

## 1. Benchmark recipe

Per-season foreground chunks (each ~2 min), `--ml --full-features
--vs-consensus --consensus-source sleeper`, current shipped models
(`models/residual/{qb,rb,wr,te}_residual*` — QB=combo, RB=zone_more_years,
WR/TE unchanged per consolidation):

```bash
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/backtest_projections.py \
  --seasons 2022 --weeks 1-18 --scoring half_ppr --ml --full-features \
  --vs-consensus --consensus-source sleeper \
  --output-dir output/backtest/site_refresh_2026_08_16
# ... repeated for --seasons 2023, --seasons 2024
```

Pooled the 3 per-season main CSVs into one 11,358-row combined CSV (this is
the artifact `--csv` input and also feeds the ordinal sim). Then ran
`scripts/benchmark_consensus_sources.py --sources espn sleeper` once against
the pooled CSV — it re-joins Silver consensus fresh per source and applies
the single source of truth filter (`src/consensus_metrics.py:
apply_consensus_filter`, cons≥5pts, weeks 3-18, QB/RB/WR/TE), so **one**
backtest engine mode (`--ml --full-features`, the promoted-config production
path) plus a single shared re-join script covers both sources — no need to
re-run the (expensive) full-features ML backtest twice per source, since our
projections don't depend on which consensus source they're compared against.

**Matched populations reproduce exactly**: Sleeper n=**7,009**, ESPN
n=**6,721** — both match the documented gate populations bit-for-bit.

## 2. Headline MAE-gap tables (promoted config, 2022-24, weeks 3-18, cons≥5)

Gap = our MAE − source MAE. Negative = we win.

### vs Sleeper (n=7,009)

| Position | n | Our MAE | Sleeper MAE | Gap | Verdict |
|---|---:|---:|---:|---:|---|
| QB | 1,250 | 4.742 | 6.401 | **−1.659** | win |
| RB | 1,877 | 4.866 | 5.332 | **−0.466** | win |
| WR | 2,965 | 4.977 | 5.042 | **−0.065** | win |
| TE | 917 | 4.001 | 4.455 | **−0.454** | win |
| **OVERALL** | **7,009** | **4.777** | **5.285** | **−0.508** | **win** |

### vs ESPN (n=6,721)

| Position | n | Our MAE | ESPN MAE | Gap | Verdict |
|---|---:|---:|---:|---:|---|
| QB | 1,211 | 4.777 | 5.842 | **−1.064** | win |
| RB | 1,834 | 4.822 | 5.346 | **−0.525** | win |
| WR | 2,752 | 4.961 | 5.065 | **−0.104** | win |
| TE | 924 | 4.012 | 4.465 | **−0.453** | win |
| **OVERALL** | **6,721** | **4.759** | **5.199** | **−0.440** | **win** |

**4 of 4 positions beat both sources**, same as the pre-consolidation
click-through-fix headline — but QB and RB widen substantially further:

| Position | Old (click-through-fix, pre-consolidation) vs Sleeper | New (promoted config) vs Sleeper | Δ |
|---|---:|---:|---:|
| QB | −0.862 | **−1.659** | −0.797 (win nearly doubles) |
| RB | −0.310 | **−0.466** | −0.156 (win widens 50%) |
| WR | −0.067 | −0.065 | +0.002 (HOLD, unchanged as expected) |
| TE | −0.454 | −0.454 | 0.000 (HOLD, unchanged as expected) |
| OVERALL | −0.325 | **−0.508** | −0.183 |

| Position | Old vs ESPN | New vs ESPN | Δ |
|---|---:|---:|---:|
| QB | −0.261 | **−1.064** | −0.803 |
| RB | −0.381 | **−0.525** | −0.144 |
| WR | −0.105 | −0.104 | +0.001 (HOLD) |
| TE | −0.453 | −0.453 | 0.000 (HOLD) |
| OVERALL | −0.256 | **−0.440** | −0.184 |

WR/TE reproducing to the third decimal is the expected sanity check — both
were explicit consolidation HOLDs (WR blend unchanged, TE regressed on
today's levers so shipped stayed put), and the numbers confirm the pipeline
picked up the correct (unchanged) artifacts for those two positions while
correctly reflecting the new QB/RB models. The QB/RB swings are directionally
consistent with `CONSOLIDATION_2026_08_16.md`'s sealed-2025 confirmation
reads (QB +0.096 MAE, RB +0.071 MAE, both with materially improved bias —
QB bias −1.341→−0.798) but larger in this matched-pairs population than the
single-holdout-year sealed reads predicted; sealed-2025 and 2022-24
matched-pairs are different eval windows/populations by design (walk-forward
CV never touches 2025, sealed touches are one-shot per position), so this
is not a contradiction, just a bigger sample showing a bigger effect.

## 3. FantasyPros ordinal simulation

`scripts/simulate_fp_accuracy.py` requires its own input glob
(`backtest_half_ppr_consensus_*.csv`, no `_ml_fullfeatures_` infix — see
`load_ours()`), so the pooled `--ml --full-features` CSV from §1 was copied
to `output/backtest/site_refresh_2026_08_16/fp_sim/backtest_half_ppr_consensus_combined.csv`
(no re-run of the model — same promoted-config projections, same 11,358
rows, just renamed to satisfy the loader, matching the precedent in
`HYBRID_SHIP_2026_08_15.md` §7's `fp_sim_newconfig` combined-file trick).

```bash
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/simulate_fp_accuracy.py \
  --output-dir output/backtest/site_refresh_2026_08_16/fp_sim
```

Accuracy Gap (lower = better), half-PPR, weeks 3-17, 2022-2024 pooled:

| Position | Old ours (HYBRID_SHIP §7) | New ours (promoted config) | Sleeper | ESPN | Winner |
|---|---:|---:|---:|---:|---|
| QB | 6.59 | **5.44** | 7.19 | 7.18 | **Ours — beats both, gap widens** |
| RB | 5.43 | **5.32** | 5.92 | 5.91 | **Ours — beats both, improved further** |
| WR | 6.51 | 6.49 | 6.29 | 6.47 | Sleeper (still losing both — unchanged, WR HOLD) |
| TE | 5.70 | **5.70** | 6.12 | 6.15 | **Ours — beats both, held** |

**QB/RB/TE ordinal wins held**, and **RB improved further** (5.43 → 5.32),
per the mission's explicit check. QB's ordinal gap improved even more than
RB's (6.59 → 5.44) — the combo model's ordinal ranking quality jumped
noticeably, not just its MAE. TE reproduces to two decimals exactly (5.70 →
5.70), the expected HOLD confirmation. WR stays the one honest loss,
essentially unchanged (6.51 → 6.49), consistent with WR HOLD.

## 4. Site artifact regeneration

```bash
PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe scripts/generate_frontend_metrics.py \
  --csv output/backtest/site_refresh_2026_08_16/backtest_half_ppr_ml_fullfeatures_consensus_pooled_2022_2024.csv \
  --consensus-csv output/backtest/site_refresh_2026_08_16/consensus_matched_sleeper_half_ppr_20260817_001331.csv \
  --tests 3813
```

(`--tests 3813` from `pytest tests/ --collect-only -q`, floor-fix already
live in `generate_frontend_metrics.py::build_consensus_section` since the
click-through-fix task — verified still applying `consensus_proj >= 5` and
QB/RB/WR/TE-only before writing the artifact.)

Wrote `web/frontend/src/features/nfl/config/model-metrics.json`. Verified
every number in the JSON's `consensus` section against the §2 tables above —
**exact match** (QB gap −1.659, RB −0.466, WR −0.065, TE −0.454, overall
−0.508, n=7,009 — all reproduce to 3 decimals). `overall`/`positions`
sections (whole-population MAE/RMSE/bias, weeks 2-18, not consensus-filtered)
also regenerated from the same pooled CSV.

## 5. Old vs new site numbers

### `model-metrics.json` (drives `/dashboard` accuracy page + `ProofStrip`)

| Field | Old (2026-08-16 click-through-fix) | New (this task) |
|---|---:|---:|
| Overall MAE (unfiltered) | not directly comparable (different filter) | 4.13 |
| Consensus gap vs Sleeper, OVERALL | −0.325 | **−0.508** |
| QB gap | −0.862 | **−1.659** |
| RB gap | −0.310 | **−0.466** |
| WR gap | −0.067 | −0.065 |
| TE gap | −0.454 | −0.454 |
| "N of 4 positions" badge | 4 of 4 | 4 of 4 (unchanged — was already a full sweep) |

### `web/frontend/src/app/page.tsx` RECEIPTS (hardcoded marketing copy)

| Chip | Old | New |
|---|---:|---:|
| OVERALL vs Sleeper | −0.32 | **−0.51** |
| OVERALL vs ESPN | −0.26 | **−0.44** |
| TE beats both | −0.45 | −0.45 (unchanged) |
| QB beats both | −0.86 | **−1.66** |
| RB beats both | −0.31 | **−0.47** |

Also updated the file-header doc comment (lines ~12-24) that restated these
numbers in prose and pointed at the stale `HYBRID_SHIP_2026_08_15.md` /
`WR_GAP_FIX_2026_08_16.md` provenance — now points at
`CONSOLIDATION_2026_08_16.md` + this doc.

**Grep swept** for other stale hardcoded claims (old gap values, "3 of 4
positions", old player-week counts) across
`web/frontend/src/app/page.tsx`, `web/frontend/src/features/nfl/components/
{accuracy-chart,accuracy-dashboard,home-modules,mae-chart,stat-cards}.tsx` —
no other hits. The dashboard-side components (`accuracy-dashboard.tsx`,
`home-modules.tsx`'s `ProofStrip`, `mae-chart.tsx`, `accuracy-chart.tsx`,
`stat-cards.tsx`) all read `model-metrics.json` live and needed no edits —
confirmed by grepping them for numeric literals matching the old figures
(none found).

## 6. Verification

- **Population reproduction**: n=7,009 (Sleeper) / n=6,721 (ESPN) — exact,
  matches every other benchmark doc in this repo.
- **Artifact-vs-table cross-check**: every number in the regenerated
  `model-metrics.json` consensus section matches the §2 hand-computed tables
  to 3 decimals.
- **HOLD sanity check**: WR and TE gaps reproduce within 0.002 of their
  pre-consolidation (click-through-fix) values on both sources — confirms
  the pipeline correctly picked up unchanged WR/TE artifacts while reflecting
  the new QB/RB models, i.e. this refresh isn't silently re-deriving
  everything from a different code path.
- Python: `pytest tests/ --collect-only -q` → 3,813 tests collected (used as
  `--tests` for the artifact; full suite not re-run, no Python source
  touched this task — only benchmark scripts were *invoked*, not edited).
- Frontend: `npx vitest run` in `web/frontend/` — **354 passed, 57 test
  files passed, 0 failed** (full suite; no dedicated test exists for
  `page.tsx`'s `RECEIPTS` array, same as the click-through-fix precedent, so
  the full suite serves as the regression check).
- `npx tsc --noEmit` in `web/frontend/`: clean, no errors.

## 7. Artifacts

- `output/backtest/site_refresh_2026_08_16/` — 3 per-season main CSVs, 3
  per-season Sleeper consensus_matched CSVs, pooled main CSV
  (`backtest_half_ppr_ml_fullfeatures_consensus_pooled_2022_2024.csv`),
  fresh per-source matched CSVs + `consensus_benchmark_summary.json` from
  `benchmark_consensus_sources.py`, `fp_sim/` (ordinal sim inputs + outputs:
  `fp_accuracy_simulation_summary.csv`, `fp_accuracy_simulation_gaps.csv`).
- `web/frontend/src/features/nfl/config/model-metrics.json` — regenerated.
- `web/frontend/src/app/page.tsx` — `RECEIPTS` array + header doc-comment
  updated to the new numbers.

## 8. Not done / out of scope

- WR option (ii) (fresh 60/40 blend with an unfiltered-population
  secondary) — still flagged in `CONSOLIDATION_2026_08_16.md` §3 as a
  follow-up, not this task's mission.
- No model retraining or promotion decisions here — this task only measures
  and publishes the already-promoted config's numbers.
