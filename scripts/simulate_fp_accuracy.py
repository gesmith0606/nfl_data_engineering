#!/usr/bin/env python3
"""Simulate FantasyPros Expert Accuracy Competition scoring on our historical
weekly rankings, 2022-2024 — QB/RB/WR/TE, half-PPR.

Why: FantasyPros (docs/ACCURACY_COMPETITION.md) grades weekly POSITIONAL
RANKINGS (ordinal order only — magnitude of your own point projections is
thrown away), not point MAE. We've only ever measured MAE. This script
replays that scoring on our historical rankings so we know roughly where
we'd land before applying.

Methodology (from FantasyPros' published FAQs — see .planning/
FP_ACCURACY_SIMULATION.md for citations + full assumption list):

  1. Each ranker's ordinal rank at a position is converted to a "baseline
     point value" via a historical average-production-by-rank-slot lookup
     ("the projected point value is based on the average fantasy production
     for that particular rank slot" — FantasyPros in-season FAQ). We build
     this table from the actual 2022-2024 sample itself (pooled across all
     three seasons) since FantasyPros' internal multi-year baseline isn't
     published.
  2. Accuracy Gap for one player-week = |baseline_points(rank) - actual_points|.
     Lower is better; 0 is a perfect call.
  3. Weekly evaluation pool per position = union(top-N by the ranker's own
     rank, top-N by actual finish), N = {QB: 20, RB: 40, WR: 50, TE: 15}
     (FantasyPros' published thresholds). A player the ranker never ranked
     at all is penalized with rank = (that ranker's max rank that week) + 1.
  4. A ranker's weekly positional score = mean Accuracy Gap over the pool.
     Season score = mean weekly score, weeks 3-17 (week 1-2 excluded because
     our own heuristic has no in-season history yet at week 1/2 — repo
     convention, see backtest_projections.py; week 18 excluded to match
     FantasyPros' own "Weeks 1-17" convention).

We score three rankers on IDENTICAL pools/baseline table so the comparison
is apples-to-apples:
  - ours    : our weekly heuristic backtest ranking (== what
              export_rankings_submission.py would have submitted)
  - sleeper : Sleeper consensus (Silver external_projections)
  - espn    : ESPN consensus (Silver external_projections)

Inputs:
  - output/backtest/backtest_half_ppr_consensus_*.csv (latest) — produced by
    `python scripts/backtest_projections.py --seasons 2022,2023,2024
    --weeks 1-18 --scoring half_ppr --vs-consensus --consensus-source sleeper`
    Has our projected_points + actual_points (half-PPR, via
    calculate_fantasy_points_df) for every backtested player-week.
  - data/silver/external_projections/season=S/week=WW/*.parquet — sleeper +
    espn consensus projections (already committed 2022-2024).

Usage:
    py -3 scripts/simulate_fp_accuracy.py
    py -3 scripts/simulate_fp_accuracy.py --selftest
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

POSITIONS = ("QB", "RB", "WR", "TE")
POOL_N = {"QB": 20, "RB": 40, "WR": 50, "TE": 15}
SCORE_WEEKS = list(range(3, 18))  # weeks 3-17
SEASONS = (2022, 2023, 2024)
SCORING = "half_ppr"
SOURCES = ("ours", "sleeper", "espn")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_ours(output_dir: Path) -> pd.DataFrame:
    """Latest `backtest_half_ppr_consensus_*.csv` -> our rankings + actuals."""
    pattern = str(output_dir / f"backtest_{SCORING}_consensus_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No backtest CSV at {pattern} — run:\n"
            f"  python scripts/backtest_projections.py --seasons "
            f"{','.join(str(s) for s in SEASONS)} --weeks 1-18 --scoring "
            f"{SCORING} --vs-consensus --consensus-source sleeper "
            f"--output-dir {output_dir}"
        )
    path = files[-1]
    df = pd.read_csv(path)
    df = df[df["position"].isin(POSITIONS)].copy()
    df["source"] = "ours"
    keep = [
        "player_id",
        "player_name",
        "position",
        "season",
        "week",
        "projected_points",
        "actual_points",
        "source",
    ]
    return df[keep].rename(columns={"projected_points": "proj_points"}), path


def load_consensus(source: str, silver_root: Path) -> pd.DataFrame:
    """Sleeper/ESPN weekly consensus projections from Silver, 2022-2024."""
    rows = []
    for season in SEASONS:
        season_dir = silver_root / f"season={season}"
        if not season_dir.is_dir():
            continue
        for week_dir in sorted(season_dir.glob("week=*")):
            files = sorted(week_dir.glob("*.parquet"))
            if not files:
                continue
            df = pd.read_parquet(files[-1])
            if "source" in df.columns:
                df = df[df["source"] == source]
            if "scoring_format" in df.columns:
                df = df[df["scoring_format"] == SCORING]
            df = df[df["position"].isin(POSITIONS)]
            if df.empty:
                continue
            df = df.copy()
            df["season"] = season
            df["week"] = int(week_dir.name.split("=")[1])
            rows.append(
                df[["player_id", "player_name", "position", "season", "week", "projected_points"]]
            )
    if not rows:
        return pd.DataFrame(
            columns=["player_id", "player_name", "position", "season", "week", "proj_points", "source"]
        )
    out = pd.concat(rows, ignore_index=True).rename(columns={"projected_points": "proj_points"})
    out["source"] = source
    return out


def attach_actuals(consensus_df: pd.DataFrame, actuals: pd.DataFrame) -> pd.DataFrame:
    """Join actual_points onto a consensus frame (player_id, else name, fallback)."""
    if consensus_df.empty:
        return consensus_df
    a = actuals[["player_id", "player_name", "season", "week", "actual_points"]].drop_duplicates()
    a_id = a.dropna(subset=["player_id"]).copy()
    a_id["player_id"] = a_id["player_id"].astype(str)
    c = consensus_df.copy()
    c["player_id"] = c["player_id"].astype(str)
    merged = c.merge(
        a_id[["player_id", "season", "week", "actual_points"]],
        on=["player_id", "season", "week"],
        how="left",
    )

    missing = merged["actual_points"].isna()
    if missing.any():
        a_name = a.copy()
        a_name["_n"] = a_name["player_name"].str.strip().str.lower()
        c_name = merged.loc[missing, ["player_id", "player_name", "position", "season", "week", "proj_points", "source"]].copy()
        c_name["_n"] = c_name["player_name"].str.strip().str.lower()
        fallback = c_name.merge(
            a_name[["_n", "season", "week", "actual_points"]],
            on=["_n", "season", "week"],
            how="left",
        )
        merged.loc[missing, "actual_points"] = fallback["actual_points"].values

    return merged


# ---------------------------------------------------------------------------
# FantasyPros-style scoring
# ---------------------------------------------------------------------------


def add_rank(df: pd.DataFrame, value_col: str, rank_col: str) -> pd.DataFrame:
    """1-based rank within (source, season, week, position), desc by value_col."""
    df = df.copy()
    df[rank_col] = (
        df.groupby(["source", "season", "week", "position"])[value_col]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return df


def build_baseline_table(actual_ranked: pd.DataFrame) -> dict:
    """position -> Series indexed by actual-finish rank -> mean actual_points.

    Pooled across all seasons/weeks in the sample (2022-2024) — our stand-in
    for FantasyPros' internal historical average-production-by-rank-slot.
    """
    tbl = {}
    for pos, g in actual_ranked.groupby("position"):
        tbl[pos] = g.groupby("actual_rank")["actual_points"].mean().sort_index()
    return tbl


def baseline_value(table: dict, position: str, rank: "pd.Series") -> "pd.Series":
    """Look up baseline points for arbitrary ranks, clamping beyond the table."""
    s = table[position]
    max_rank = s.index.max()
    clamped = rank.clip(upper=max_rank)
    return clamped.map(s)


def compute_accuracy_gaps(long_df: pd.DataFrame, baseline: dict) -> pd.DataFrame:
    """Long df (all sources stacked) -> per-row Accuracy Gap, pool-filtered.

    long_df must have: source, season, week, position, player_id, rank,
    actual_rank (the TRUE finish rank that week, same for every source),
    actual_points.
    """
    rows = []
    for (season, week, position), g in long_df.groupby(["season", "week", "position"]):
        n = POOL_N[position]
        for source, sg in g.groupby("source"):
            in_pool = sg[(sg["rank"] <= n) | (sg["actual_rank"] <= n)]
            if in_pool.empty:
                continue
            gap = (baseline_value(baseline, position, in_pool["rank"]) - in_pool["actual_points"]).abs()
            rows.append(
                pd.DataFrame(
                    {
                        "season": season,
                        "week": week,
                        "position": position,
                        "source": source,
                        "accuracy_gap": gap.values,
                    }
                )
            )
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def score_all(ours: pd.DataFrame, sleeper: pd.DataFrame, espn: pd.DataFrame) -> tuple:
    """Full pipeline -> (gaps_df, baseline_table, pool_penalty_note)."""
    stacked = pd.concat([ours, sleeper, espn], ignore_index=True)
    stacked = stacked.dropna(subset=["actual_points"])
    stacked = add_rank(stacked, "proj_points", "rank")

    # Penalize players a source never ranked but who ARE in another source's
    # frame for that (season, week, position) — assign rank = max+1 for that
    # source/week/position so they still enter the pool via actual_rank.
    full_index = stacked[["season", "week", "position", "player_id", "player_name", "actual_points"]].drop_duplicates(
        subset=["season", "week", "position", "player_id"]
    )
    complete = []
    for source in SOURCES:
        src = stacked[stacked["source"] == source]
        merged = full_index.merge(
            src[["season", "week", "position", "player_id", "proj_points", "rank"]],
            on=["season", "week", "position", "player_id"],
            how="left",
        )
        merged["source"] = source
        max_rank = (
            merged.groupby(["season", "week", "position"])["rank"].transform("max").fillna(0)
        )
        merged["rank"] = merged["rank"].fillna(max_rank + 1).astype(int)
        complete.append(merged)
    full = pd.concat(complete, ignore_index=True)

    # Ground-truth actual finish rank — identical across sources.
    truth = full[full["source"] == "ours"][["season", "week", "position", "player_id", "actual_points"]].drop_duplicates()
    truth = truth.copy()
    truth["actual_rank"] = (
        truth.groupby(["season", "week", "position"])["actual_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    full = full.merge(
        truth[["season", "week", "position", "player_id", "actual_rank"]],
        on=["season", "week", "position", "player_id"],
        how="left",
    )

    baseline = build_baseline_table(truth)
    gaps = compute_accuracy_gaps(full, baseline)

    # Row-level detail (rank, actual_rank, per-row Accuracy Gap, pool flag) —
    # `gaps` above only keeps the aggregated (season, week, position, source)
    # scalar, which is enough for the summary table but not for row-level
    # diagnosis (e.g. per-player ordering damage). Expose it so downstream
    # scripts can reuse this same rank/baseline machinery instead of
    # recomputing it.
    full["accuracy_gap"] = np.nan
    for pos in full["position"].unique():
        mask = full["position"] == pos
        full.loc[mask, "accuracy_gap"] = (
            baseline_value(baseline, pos, full.loc[mask, "rank"]) - full.loc[mask, "actual_points"]
        ).abs()
    n_col = full["position"].map(POOL_N)
    full["in_pool"] = (full["rank"] <= n_col) | (full["actual_rank"] <= n_col)

    return gaps, baseline, full


def summarize(gaps: pd.DataFrame) -> pd.DataFrame:
    """season score (mean weekly Accuracy Gap, weeks 3-17) per source x position x season,
    plus a 2022-2024 combined row per source x position."""
    scored_weeks = gaps[gaps["week"].isin(SCORE_WEEKS)]
    weekly = scored_weeks.groupby(["source", "season", "week", "position"])["accuracy_gap"].mean().reset_index()

    by_season = (
        weekly.groupby(["position", "season", "source"])["accuracy_gap"]
        .mean()
        .unstack("source")
        .reindex(columns=list(SOURCES))
    )
    combined = (
        weekly.groupby(["position", "source"])["accuracy_gap"]
        .mean()
        .unstack("source")
        .reindex(columns=list(SOURCES))
    )
    combined["season"] = "2022-2024"
    combined = combined.reset_index().set_index(["position", "season"])
    by_season = by_season.reset_index().set_index(["position", "season"])
    return pd.concat([by_season, combined]).sort_index()


# ---------------------------------------------------------------------------
# Self-test (runnable check; deliverable requirement)
# ---------------------------------------------------------------------------


def _selftest() -> None:
    """Assertable sanity checks on a tiny synthetic slate. No I/O."""
    truth = pd.DataFrame(
        {
            "season": [2022] * 4,
            "week": [3] * 4,
            "position": ["QB"] * 4,
            "player_id": ["a", "b", "c", "d"],
            "actual_points": [30.0, 20.0, 10.0, 0.0],
        }
    )
    truth["actual_rank"] = truth["actual_points"].rank(ascending=False, method="first").astype(int)
    baseline = build_baseline_table(truth)
    assert list(baseline["QB"].index) == [1, 2, 3, 4]
    # Baseline is monotonically non-increasing by rank.
    vals = baseline["QB"].values
    assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)), "baseline must be non-increasing by rank"

    # A ranker who nails the exact order gets Accuracy Gap 0 for every player.
    perfect = truth.rename(columns={"actual_points": "proj_points"})[["player_id", "proj_points"]]
    perfect["rank"] = perfect["proj_points"].rank(ascending=False, method="first").astype(int)
    gap = (baseline_value(baseline, "QB", perfect["rank"]) - truth.set_index("player_id").loc[perfect["player_id"], "actual_points"].values).abs()
    assert np.allclose(gap.values, 0.0), f"perfect ranker should score 0 Accuracy Gap, got {gap.values}"

    # Rank beyond the table clamps to the worst known baseline instead of KeyError/NaN.
    clamped = baseline_value(baseline, "QB", pd.Series([1, 2, 3, 4, 99]))
    assert clamped.iloc[-1] == baseline["QB"].iloc[-1], "out-of-range rank must clamp, not NaN"
    assert not clamped.isna().any()

    print("selftest OK — baseline table, perfect-ranker zero-gap, and rank clamping all pass.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", default=str(_PROJECT_ROOT / "output" / "backtest"))
    parser.add_argument("--selftest", action="store_true", help="Run assertions on a synthetic slate and exit")
    args = parser.parse_args()

    if args.selftest:
        _selftest()
        return 0

    output_dir = Path(args.output_dir)
    silver_root = _PROJECT_ROOT / "data" / "silver" / "external_projections"

    print("Loading our backtest rankings...")
    ours, ours_path = load_ours(output_dir)
    print(f"  {ours_path} -> {len(ours):,} rows")

    print("Loading Sleeper + ESPN consensus...")
    sleeper = attach_actuals(load_consensus("sleeper", silver_root), ours)
    espn = attach_actuals(load_consensus("espn", silver_root), ours)
    print(f"  sleeper: {len(sleeper):,} rows | espn: {len(espn):,} rows")

    gaps, baseline, _full = score_all(ours, sleeper, espn)
    summary = summarize(gaps)

    pd.set_option("display.width", 140)
    pd.set_option("display.float_format", lambda v: f"{v:6.2f}")
    print("\nFantasyPros-style Accuracy Gap (lower = better) — half-PPR, weeks 3-17")
    print(summary.to_string())

    out_csv = output_dir / "fp_accuracy_simulation_summary.csv"
    summary.to_csv(out_csv)
    print(f"\nSaved summary to {out_csv}")

    gaps_csv = output_dir / "fp_accuracy_simulation_gaps.csv"
    gaps.to_csv(gaps_csv, index=False)
    print(f"Saved per-player-week gaps to {gaps_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
