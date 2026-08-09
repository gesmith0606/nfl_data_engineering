#!/usr/bin/env python3
"""Diagnose WHY our WR weekly rank ORDER loses to Sleeper (~+0.35 FantasyPros-
style Accuracy Gap, worst position) while our WR point MAE beats both Sleeper
and ESPN (see docs/ACCURACY_COMPETITION.md / CONSENSUS_ERROR_DECOMPOSITION.md).

Reuses `scripts/simulate_fp_accuracy.py` end to end for the rank/baseline/gap
machinery (load_ours, load_consensus, attach_actuals, score_all) — this
script does not recompute ranks or the baseline lookup table itself, it only
slices the row-level output `score_all()` now returns (`full`, added here)
five different ways.

Because Accuracy Gap = |baseline(rank) - actual_points| and actual_points is
identical across sources for a given player-week, the *entire* difference
between our_gap and sleeper_gap for that player-week is attributable to the
difference in RANK (i.e. ordering), not to point magnitude. That identity is
what makes `full["accuracy_gap"]` usable as a direct "ordering damage" signal
per player-week (Analysis 3) and per rank-tier (Analysis 1).

Analyses:
  1. Rank-curve position — WR accuracy-gap-vs-Sleeper by ACTUAL-finish tier
     (top-12 / 13-30 / 31-50 / 51+ overranked), since the baseline table is
     keyed off actual-rank slots and this isolates where in the true-outcome
     curve our ordering breaks down.
  2. Swap analysis — WR pairs (A, B) in the same week where our projections
     order A > B, Sleeper orders B > A, and Sleeper's order matched the
     actual outcome. Characterizes those pairs by our own projection gap
     (near-tie vs real misorder), Sleeper's gap, actual-outcome spread
     (boom/bust variance), and same-team share.
  3. Magnitude-vs-order — top-20 players by cumulative ordering damage
     (sum of our_gap - sleeper_gap across their weeks), with mean our-rank
     vs Sleeper-rank vs actual-rank, to see if the loss is a few systematic
     misranks or diffuse noise.
  4. Compression hypothesis — mean adjacent-rank projection gap (rank k vs
     k+1) per week, ours vs Sleeper, as a proxy for how compressed/flat each
     source's WR projection curve is (less separation -> easier to flip
     order on noise).
  5. Slice overlap — week-band (3-6 / 7-12 / 13-18) and season breakdown of
     the WR ordering gap, cross-referenced against
     .planning/CONSENSUS_ERROR_DECOMPOSITION.md finding #1 (early-season
     weakness).

Usage:
    py -3 scripts/diagnose_wr_ordering.py
    py -3 scripts/diagnose_wr_ordering.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import simulate_fp_accuracy as fp  # noqa: E402

POSITION = "WR"
_MIN_N_RELIABLE = 50


# ---------------------------------------------------------------------------
# Data assembly (thin wrapper around simulate_fp_accuracy — no rank/baseline
# logic duplicated here)
# ---------------------------------------------------------------------------


def load_all(output_dir: Path, silver_root: Path):
    """Reuse simulate_fp_accuracy's loaders + score_all -> (gaps, baseline, full, ours_path)."""
    ours, ours_path = fp.load_ours(output_dir)
    sleeper = fp.attach_actuals(fp.load_consensus("sleeper", silver_root), ours)
    espn = fp.attach_actuals(fp.load_consensus("espn", silver_root), ours)
    gaps, baseline, full = fp.score_all(ours, sleeper, espn)
    return gaps, baseline, full, ours_path


def attach_team(full: pd.DataFrame, ours_path: str) -> pd.DataFrame:
    """Bring recent_team onto the 'ours' rows from the raw backtest CSV (not
    carried through load_ours' `keep` column subset)."""
    raw = pd.read_csv(ours_path, usecols=["player_id", "season", "week", "recent_team"])
    raw = raw.drop_duplicates(subset=["player_id", "season", "week"])
    raw["player_id"] = raw["player_id"].astype(str)
    full = full.copy()
    full["player_id"] = full["player_id"].astype(str)
    return full.merge(raw, on=["player_id", "season", "week"], how="left")


def wr_pool(full: pd.DataFrame) -> pd.DataFrame:
    """WR rows, scored weeks (3-17), in the FP pool, ours+sleeper only."""
    return full[
        (full["position"] == POSITION)
        & full["week"].isin(fp.SCORE_WEEKS)
        & full["in_pool"]
        & full["source"].isin(["ours", "sleeper"])
    ].copy()


def merge_wide(wr: pd.DataFrame) -> pd.DataFrame:
    """One row per (season, week, player) with ours_* / sleeper_* columns,
    intersected on rows BOTH sources placed in-pool (see report for caveat)."""
    o = wr[wr["source"] == "ours"][
        ["season", "week", "player_id", "player_name", "recent_team", "rank",
         "proj_points", "accuracy_gap", "actual_points", "actual_rank"]
    ].rename(columns={"rank": "our_rank", "proj_points": "our_proj", "accuracy_gap": "our_gap"})
    s = wr[wr["source"] == "sleeper"][
        ["season", "week", "player_id", "rank", "proj_points", "accuracy_gap"]
    ].rename(columns={"rank": "sleeper_rank", "proj_points": "sleeper_proj", "accuracy_gap": "sleeper_gap"})
    return o.merge(s, on=["season", "week", "player_id"], how="inner")


# ---------------------------------------------------------------------------
# 1. Rank-curve position
# ---------------------------------------------------------------------------


def rank_curve(wide: pd.DataFrame) -> pd.DataFrame:
    tiers = pd.cut(
        wide["actual_rank"], bins=[0, 12, 30, 50, 10_000],
        labels=["WR1-12 (elite)", "WR13-30", "WR31-50", "WR51+ (overranked bust)"],
    )
    rows = []
    for tier, g in wide.groupby(tiers, observed=True):
        rows.append({
            "tier": tier,
            "n": len(g),
            "our_gap": round(g["our_gap"].mean(), 3),
            "sleeper_gap": round(g["sleeper_gap"].mean(), 3),
            "gap_diff": round((g["our_gap"] - g["sleeper_gap"]).mean(), 3),
            "reliable": len(g) >= _MIN_N_RELIABLE,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2. Swap analysis (pairwise, vectorized per week)
# ---------------------------------------------------------------------------


def _week_pairs(g: pd.DataFrame) -> pd.DataFrame:
    """All unordered player pairs within one (season, week) WR pool."""
    g = g.reset_index(drop=True)
    m = len(g)
    if m < 2:
        return pd.DataFrame()
    i, j = np.triu_indices(m, k=1)
    our_diff = g["our_proj"].values[i] - g["our_proj"].values[j]
    sleeper_diff = g["sleeper_proj"].values[i] - g["sleeper_proj"].values[j]
    actual_diff = g["actual_points"].values[i] - g["actual_points"].values[j]
    same_team = g["recent_team"].values[i] == g["recent_team"].values[j]
    return pd.DataFrame({
        "season": g["season"].iloc[0],
        "week": g["week"].iloc[0],
        "player_a": g["player_name"].values[i],
        "player_b": g["player_name"].values[j],
        "our_diff": our_diff,
        "sleeper_diff": sleeper_diff,
        "actual_diff": actual_diff,
        "same_team": same_team,
    })


def swap_analysis(wide: pd.DataFrame) -> tuple:
    """-> (all_pairs, swap_loss_pairs). swap_loss = we got the order wrong,
    Sleeper got it right, and the two sources actually disagreed."""
    parts = [
        _week_pairs(g) for _, g in wide.groupby(["season", "week"])
    ]
    all_pairs = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    all_pairs = all_pairs[(all_pairs["our_diff"] != 0) & (all_pairs["actual_diff"] != 0)]

    we_wrong = np.sign(all_pairs["our_diff"]) != np.sign(all_pairs["actual_diff"])
    sleeper_right = np.sign(all_pairs["sleeper_diff"]) == np.sign(all_pairs["actual_diff"])
    swap_loss = all_pairs[we_wrong & sleeper_right & (all_pairs["sleeper_diff"] != 0)].copy()
    return all_pairs, swap_loss


def summarize_swaps(all_pairs: pd.DataFrame, swap_loss: pd.DataFrame) -> dict:
    return {
        "total_pairs": len(all_pairs),
        "swap_loss_pairs": len(swap_loss),
        "swap_loss_pct": round(100 * len(swap_loss) / len(all_pairs), 2) if len(all_pairs) else 0.0,
        "median_abs_our_diff_all_pairs": round(all_pairs["our_diff"].abs().median(), 3),
        "median_abs_our_diff_swap_loss": round(swap_loss["our_diff"].abs().median(), 3),
        "median_abs_sleeper_diff_swap_loss": round(swap_loss["sleeper_diff"].abs().median(), 3),
        "median_abs_actual_diff_swap_loss": round(swap_loss["actual_diff"].abs().median(), 3),
        "median_abs_actual_diff_all_pairs": round(all_pairs["actual_diff"].abs().median(), 3),
        "pct_same_team_swap_loss": round(100 * swap_loss["same_team"].mean(), 2),
        "pct_same_team_all_pairs": round(100 * all_pairs["same_team"].mean(), 2),
    }


# ---------------------------------------------------------------------------
# 3. Magnitude-vs-order: per-player cumulative ordering damage
# ---------------------------------------------------------------------------


def top_ordering_damage(wide: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    wide = wide.copy()
    wide["gap_diff"] = wide["our_gap"] - wide["sleeper_gap"]
    rows = []
    for (pid, name), g in wide.groupby(["player_id", "player_name"]):
        rows.append({
            "player_id": pid,
            "player_name": name,
            "n": len(g),
            "cumulative_damage": round(g["gap_diff"].sum(), 2),
            "mean_our_rank": round(g["our_rank"].mean(), 1),
            "mean_sleeper_rank": round(g["sleeper_rank"].mean(), 1),
            "mean_actual_rank": round(g["actual_rank"].mean(), 1),
        })
    out = pd.DataFrame(rows).sort_values("cumulative_damage", ascending=False)
    return out.head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. Compression hypothesis
# ---------------------------------------------------------------------------


def adjacent_rank_gap(full: pd.DataFrame) -> pd.DataFrame:
    """Mean |proj(rank k) - proj(rank k+1)| within the top-50 WR curve, per
    (season, week, source), then averaged across weeks per source."""
    wr = full[
        (full["position"] == POSITION)
        & full["week"].isin(fp.SCORE_WEEKS)
        & (full["rank"] <= fp.POOL_N[POSITION])
        & full["source"].isin(["ours", "sleeper"])
    ]
    rows = []
    for (season, week, source), g in wr.groupby(["season", "week", "source"]):
        g = g.sort_values("rank")
        diffs = np.abs(np.diff(g["proj_points"].values))
        if len(diffs) == 0:
            continue
        rows.append({
            "season": season, "week": week, "source": source,
            "mean_adjacent_gap": diffs.mean(),
            "proj_std": g["proj_points"].std(),
            "proj_iqr": g["proj_points"].quantile(0.75) - g["proj_points"].quantile(0.25),
        })
    weekly = pd.DataFrame(rows)
    return weekly.groupby("source")[["mean_adjacent_gap", "proj_std", "proj_iqr"]].mean().round(3)


# ---------------------------------------------------------------------------
# 5. Slice overlap with known findings
# ---------------------------------------------------------------------------


def slice_overlap(wide: pd.DataFrame) -> pd.DataFrame:
    wide = wide.copy()
    wide["gap_diff"] = wide["our_gap"] - wide["sleeper_gap"]
    wide["week_band"] = pd.cut(wide["week"], bins=[2, 6, 12, 18], labels=["3-6", "7-12", "13-18"])
    rows = []
    for (season, band), g in wide.groupby(["season", "week_band"], observed=True):
        rows.append({
            "season": season, "week_band": band, "n": len(g),
            "our_gap": round(g["our_gap"].mean(), 3),
            "sleeper_gap": round(g["sleeper_gap"].mean(), 3),
            "gap_diff": round(g["gap_diff"].mean(), 3),
        })
    return pd.DataFrame(rows).sort_values(["week_band", "season"])


# ---------------------------------------------------------------------------
# Self-test / sanity check
# ---------------------------------------------------------------------------


def _selftest() -> None:
    """Assertable checks on a tiny synthetic slate. No I/O."""
    # --- swap_analysis: hand-built 4-player week where Sleeper corrects one
    # of our two misorders.
    wide = pd.DataFrame({
        "season": [2022] * 4, "week": [3] * 4,
        "player_id": ["a", "b", "c", "d"],
        "player_name": ["A", "B", "C", "D"],
        "recent_team": ["KC", "KC", "SF", "DAL"],
        "our_rank": [1, 2, 3, 4], "our_proj": [20.0, 18.0, 12.0, 10.0],
        "our_gap": [0.0] * 4,
        "sleeper_rank": [2, 1, 3, 4], "sleeper_proj": [17.0, 19.0, 12.0, 10.0],
        "sleeper_gap": [0.0] * 4,
        "actual_points": [15.0, 25.0, 5.0, 30.0],  # A<B (we say A>B: wrong; sleeper says B>A: right)
        "actual_rank": [3, 2, 4, 1],
    })
    all_pairs, swap_loss = swap_analysis(wide)
    # Pair (A, B): we say A>B (wrong, actual B>A), sleeper says B>A (right) -> swap loss.
    ab = swap_loss[(swap_loss["player_a"] == "A") & (swap_loss["player_b"] == "B")]
    assert len(ab) == 1, f"expected the A/B pair to register as a swap loss, got {len(swap_loss)} total rows"
    assert bool(ab["same_team"].iloc[0]) is True, "A/B are both KC — same_team must be True"
    # Pair (C, D): we say C>D (wrong, actual D>C), sleeper ALSO says C>D (wrong) -> NOT a swap loss
    # (sleeper didn't get it right either).
    cd = swap_loss[(swap_loss["player_a"] == "C") & (swap_loss["player_b"] == "D")]
    assert len(cd) == 0, "C/D: sleeper also got it wrong, must not count as a swap loss"

    # --- rank_curve: tiering is exhaustive and buckets sum to n.
    curve = rank_curve(wide)
    assert curve["n"].sum() == len(wide)

    # --- top_ordering_damage: contribution sums to the same total as a
    # direct groupby-free sum (no players dropped/duplicated).
    wide2 = wide.copy()
    wide2["our_gap"] = [1.0, 2.0, 0.5, 0.0]
    wide2["sleeper_gap"] = [0.5, 0.5, 0.5, 0.5]
    damage = top_ordering_damage(wide2, top_n=10)
    assert np.isclose(damage["cumulative_damage"].sum(), (wide2["our_gap"] - wide2["sleeper_gap"]).sum())

    print("selftest OK — swap-loss logic, rank-curve tiering, and ordering-damage "
          "aggregation all pass.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", default=str(_PROJECT_ROOT / "output" / "backtest"))
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        _selftest()
        return 0

    output_dir = Path(args.output_dir)
    silver_root = _PROJECT_ROOT / "data" / "silver" / "external_projections"

    print("Loading data via simulate_fp_accuracy (reused, not duplicated)...")
    gaps, baseline, full, ours_path = load_all(output_dir, silver_root)
    full = attach_team(full, ours_path)

    # --- Self-check: this script's WR/ours-vs-sleeper slice must reproduce
    # the canonical fp.summarize() 2022-2024 number exactly (same rows, same
    # two-level weekly-then-season averaging) -- proves `full`/in_pool here
    # matches what compute_accuracy_gaps already certified.
    canonical = fp.summarize(gaps).loc[(POSITION, "2022-2024")]
    wr_all = wr_pool(full)
    mine = (
        wr_all.groupby(["source", "season", "week"])["accuracy_gap"].mean()
        .groupby("source").mean()
    )
    assert abs(mine["ours"] - canonical["ours"]) < 1e-6, (
        f"ours WR gap mismatch: mine={mine['ours']:.4f} canonical={canonical['ours']:.4f}"
    )
    assert abs(mine["sleeper"] - canonical["sleeper"]) < 1e-6, (
        f"sleeper WR gap mismatch: mine={mine['sleeper']:.4f} canonical={canonical['sleeper']:.4f}"
    )
    print(f"[sanity OK] WR ours={mine['ours']:.3f} sleeper={mine['sleeper']:.3f} "
          f"(matches fp.summarize() canonical numbers exactly)")

    wide = merge_wide(wr_all)
    print(f"Matched WR player-weeks (both sources in-pool): {len(wide):,}")

    print("\n" + "=" * 78 + "\n1. RANK-CURVE POSITION\n" + "=" * 78)
    curve = rank_curve(wide)
    print(curve.to_string(index=False))
    curve.to_csv(output_dir / "diagnose_wr_rank_curve.csv", index=False)

    print("\n" + "=" * 78 + "\n2. SWAP ANALYSIS\n" + "=" * 78)
    all_pairs, swap_loss = swap_analysis(wide)
    swap_summary = summarize_swaps(all_pairs, swap_loss)
    for k, v in swap_summary.items():
        print(f"  {k}: {v}")
    pd.Series(swap_summary).to_csv(output_dir / "diagnose_wr_swap_summary.csv")
    swap_loss.sort_values("actual_diff", key=lambda s: s.abs(), ascending=False).head(200).to_csv(
        output_dir / "diagnose_wr_swap_loss_pairs.csv", index=False
    )

    print("\n" + "=" * 78 + "\n3. TOP-20 CUMULATIVE ORDERING DAMAGE\n" + "=" * 78)
    damage = top_ordering_damage(wide, top_n=20)
    print(damage.to_string(index=False))
    damage.to_csv(output_dir / "diagnose_wr_top_ordering_damage.csv", index=False)

    print("\n" + "=" * 78 + "\n4. COMPRESSION HYPOTHESIS (mean adjacent-rank projection gap, top-50 pool)\n" + "=" * 78)
    compression = adjacent_rank_gap(full)
    print(compression.to_string())
    compression.to_csv(output_dir / "diagnose_wr_compression.csv")

    print("\n" + "=" * 78 + "\n5. SLICE OVERLAP (week-band x season)\n" + "=" * 78)
    overlap = slice_overlap(wide)
    print(overlap.to_string(index=False))
    overlap.to_csv(output_dir / "diagnose_wr_slice_overlap.csv", index=False)

    print(f"\nAll diagnose_wr_*.csv written to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
