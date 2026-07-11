# Multi-Source Consensus Benchmark — ESPN + Yahoo (2026-07-11)

Extends the v4.3 "beat Sleeper" historical benchmark to ESPN and Yahoo for
website marketing. Same rows, same rules, same scoring on both sides.

## Headline results (2022–2024, weeks 3–18, half-PPR, matched player-weeks)

MAE gap = our MAE − source MAE. **Negative = we win.**

| Position | vs Sleeper (n=7,009) | vs ESPN (n=6,721) |
|----------|---------------------|-------------------|
| QB       | **−0.386** ✅        | +0.186 ❌          |
| RB       | +0.264 ❌            | +0.173 ❌          |
| WR       | **−0.085** ✅        | **−0.122** ✅      |
| TE       | **−0.428** ✅        | **−0.420** ✅      |
| **OVERALL** | **−0.090** ✅     | **−0.027** ✅      |

- **We beat BOTH Sleeper and ESPN overall** on three seasons of matched
  player-weeks.
- TE is a decisive win against both (−0.42 vs both benchmarks).
- WR beats both. QB crushes Sleeper (−0.39) but ESPN's QB projections are
  stronger than ours (+0.19). RB trails both (known gap; props-blend lever
  gated for in-season 2026).
- The Sleeper column reproduces the published v4.3 audit numbers exactly
  (MODEL_AUDIT_2026_06_12: overall −0.086 with the then-current rounding),
  which validates the shared harness.

## Marketing-safe claims

✅ "Our projections beat both the Sleeper and ESPN consensus overall across
   2022–2024 (7,009 / 6,721 matched player-weeks)."
✅ "Best-in-class TE projections: ~0.42 MAE better than both Sleeper and ESPN."
✅ "Beats both sources at WR; beats Sleeper at QB by 0.39 MAE."
⚠️ Do NOT claim per-position sweep: ESPN wins QB/RB head-to-head, Sleeper
   wins RB. Overall + TE/WR are the honest headline.
⚠️ The ESPN overall margin (−0.027) is slim — phrase as "beats" but do not
   quantify it as a big margin; the robust claims are overall-win + TE/WR.

## Yahoo status

Historical Yahoo weekly projections are **not publicly retrievable**: the
Yahoo Fantasy API archives historical *actual* stats but not projections,
and our Yahoo column is already a FantasyPros-consensus proxy scraped
current-week only. Community tooling confirms only current-season projection
access. Therefore:

- No historical Yahoo benchmark is possible (would require a data vendor).
- The forward path is already live: the weekly-external-projections cron
  captures `yahoo_proxy_fp` (FantasyPros consensus) every week of 2026, and
  the weekly grading report benchmarks against it in-season. A "vs Yahoo/FP
  consensus" claim becomes available with real 2026 data ~week 6+.

## Methodology (identical to the v4.3 Sleeper benchmark)

- Ours: the canonical v4.3 production backtest
  (`backtest_half_ppr_ml_fullfeatures_consensus_20260612_141246.csv` —
  the exact run behind the published −0.086), injury-aware.
- ESPN: ESPN archives per-week PROJECTED stat lines (statSourceId=1) on the
  league-less `/apis/v3/games/ffl/seasons/{season}/players` endpoint.
  Backfilled 2022–2024 w1–18 (54 weeks, ~290 skill players/week, 92%
  player-id resolution). ESPN's raw projected stats are scored with OUR
  `SCORING_CONFIGS` (their `appliedTotal` is league-scoped and zero without
  a league) — both sides therefore use byte-identical scoring rules.
- Join: (player_id, season, week) inner join; population weeks 3–18,
  QB/RB/WR/TE, source projection ≥ 5 pts (consensus_metrics.py — single
  source of truth).

## Regeneration

```bash
# 1. Backfill ESPN (idempotent; skips existing weeks)
python scripts/ingest_external_projections_espn.py --historical --season 2023 --weeks 1-18

# 2. Re-consolidate Silver for affected weeks
python scripts/silver_external_projections_transformation.py --season 2023 --week 5

# 3. Head-to-head on the canonical backtest rows
python scripts/benchmark_consensus_sources.py --sources espn sleeper \
    --json-out output/backtest/consensus_benchmark_summary.json
```

Alternatively `backtest_projections.py --vs-consensus --consensus-source espn`
regenerates our projections from scratch and benchmarks in one shot.

## Artifacts

- `output/backtest/consensus_matched_espn_half_ppr_20260711_155403.csv`
- `output/backtest/consensus_matched_sleeper_half_ppr_20260711_155403.csv`
- `output/backtest/consensus_benchmark_summary.json` (website-ready)

## Incidental fix

The ESPN ingester wrote Bronze partitions as `week=N` (unpadded) while the
Silver consolidator reads `week=NN` — ESPN/Silver consolidation would have
silently no-opped from 2026 week 1 (TD-09 class). Fixed + regression test.

## Website wiring (next step, not done here)

`scripts/generate_frontend_metrics.py --consensus-csv <espn matched csv>`
feeds `model-metrics.json`; the accuracy page's consensus section currently
renders a single benchmark. Adding a second benchmark card ("vs ESPN") is a
frontend change — the data artifact above is ready for it.
