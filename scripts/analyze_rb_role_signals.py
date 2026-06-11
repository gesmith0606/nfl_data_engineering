#!/usr/bin/env python3
"""Validate RB role-change signals against the consensus matched CSV.

Steps:
1. Build signal table for RBs 2022-2024 w3-18.
2. Load and dedup consensus matched CSV.
3. Join signals to matched rows.
4. Per signal: fire rate, precision on disagreement rows (|ours - cons| >= 4),
   optimal correction multiplier (grid 0.3-2.0), estimated MAE delta.
5. Named case sanity checks.
6. Print full validation table.

Usage:
    python scripts/analyze_rb_role_signals.py
"""

import logging
import os
import sys

import numpy as np
import pandas as pd

# Allow src/ imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.rb_role_signals import build_rb_role_signals

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

CONSENSUS_CSV = "output/backtest/consensus_matched_half_ppr_20260610_220524.csv"
OUTPUT_CSV = "output/backtest/rb_role_signal_validation.csv"
SEASONS = [2022, 2023, 2024]
DISAGREE_THRESHOLD = 4.0  # |ours - cons| >= 4 → "disagreement" bucket
MULTIPLIER_GRID = np.arange(0.3, 2.05, 0.05)


# ---------------------------------------------------------------------------
# Load and prep consensus data
# ---------------------------------------------------------------------------


def load_consensus(path: str) -> pd.DataFrame:
    """Load consensus CSV, dedup on (player_id, season, week), add consensus MAE."""
    df = pd.read_csv(path)
    before = len(df)
    df = df.sort_values(
        ["player_id", "season", "week", "projected_points"], ascending=[True, True, True, False]
    ).drop_duplicates(subset=["player_id", "season", "week"], keep="first")
    logger.info(
        "Consensus CSV: %d rows → %d after dedup (removed %d dupes)",
        before,
        len(df),
        before - len(df),
    )
    df["cons_error"] = df["actual_points"] - df["consensus_proj"]
    df["cons_abs_error"] = df["cons_error"].abs()
    df["our_error"] = df["actual_points"] - df["projected_points"]
    df["our_abs_error"] = df["our_error"].abs()
    return df


# ---------------------------------------------------------------------------
# Signal validation helpers
# ---------------------------------------------------------------------------


def optimal_multiplier_for_fired_rows(
    fired: pd.DataFrame,
    multiplier_grid: np.ndarray,
) -> tuple:
    """Find the multiplier applied to projected_points that minimises MAE.

    Sweeps a grid of multipliers and returns (best_mult, mae_at_best_mult).

    Args:
        fired: Rows where the signal fired.
        multiplier_grid: Array of candidate multipliers.

    Returns:
        (best_multiplier, mae_at_best_multiplier)
    """
    best_mae = np.inf
    best_mult = 1.0
    for mult in multiplier_grid:
        adjusted = (fired["projected_points"] * mult).clip(lower=0)
        mae = (adjusted - fired["actual_points"]).abs().mean()
        if mae < best_mae:
            best_mae = mae
            best_mult = mult
    return float(best_mult), float(best_mae)


def signal_stats(
    rb: pd.DataFrame,
    signal_col: str,
    fire_value: object = None,
) -> dict:
    """Compute fire rate, disagreement-bucket precision, optimal multiplier.

    Args:
        rb: RB subset of the joined DataFrame.
        signal_col: Column name to check.
        fire_value: If None, signal fires when signal_col is truthy (!= 0 and not NaN).
                    Otherwise, fires when signal_col == fire_value.

    Returns:
        Dict with statistics.
    """
    if signal_col not in rb.columns:
        return {"signal": signal_col, "error": "column missing"}

    if fire_value is None:
        fired_mask = (rb[signal_col] != 0) & rb[signal_col].notna()
    else:
        fired_mask = rb[signal_col] == fire_value

    n_total = len(rb)
    n_fired = int(fired_mask.sum())
    fire_rate = n_fired / n_total if n_total > 0 else 0.0

    fired = rb[fired_mask].copy()
    not_fired = rb[~fired_mask].copy()

    # MAE delta across all RB rows (if we applied optimal multiplier to fired rows)
    if len(fired) == 0:
        return {
            "signal": signal_col,
            "n_total": n_total,
            "n_fired": n_fired,
            "fire_rate": round(fire_rate, 4),
            "our_mae_all": round(rb["our_abs_error"].mean(), 3),
            "cons_mae_all": round(rb["cons_abs_error"].mean(), 3),
            "disagreement_n": 0,
            "disagreement_fired_n": 0,
            "precision_on_disagree": None,
            "our_minus_cons_on_fired": None,
            "optimal_multiplier": 1.0,
            "mae_fired_at_opt_mult": None,
            "mae_fired_baseline": None,
            "est_rb_mae_delta": 0.0,
        }

    # Disagreement rows: |ours - cons| >= DISAGREE_THRESHOLD
    disagree_mask = (rb["our_abs_error"] - rb["cons_abs_error"]).abs() >= DISAGREE_THRESHOLD
    disagree_and_fired = fired_mask & disagree_mask

    # Precision: mean(our_abs_error - cons_abs_error) on signal-firing rows
    # Positive = we are worse than consensus on fired rows (signal correctly identifies gap)
    our_minus_cons_on_fired = float((fired["our_abs_error"] - fired["cons_abs_error"]).mean())

    # Disagreement bucket: fraction of fired rows in the disagree bucket
    n_disagree = int(disagree_mask.sum())
    n_disagree_fired = int(disagree_and_fired.sum())
    precision_on_disagree = (
        float((rb.loc[disagree_and_fired, "our_abs_error"] - rb.loc[disagree_and_fired, "cons_abs_error"]).mean())
        if n_disagree_fired > 0
        else None
    )

    # Optimal multiplier on fired rows
    best_mult, mae_at_opt = optimal_multiplier_for_fired_rows(fired, MULTIPLIER_GRID)
    mae_fired_baseline = float(fired["our_abs_error"].mean())

    # Estimated full RB MAE delta: (mae improvement on fired rows) × (fired / total)
    improvement_on_fired = mae_fired_baseline - mae_at_opt
    est_rb_mae_delta = improvement_on_fired * (n_fired / n_total)

    return {
        "signal": signal_col,
        "n_total": n_total,
        "n_fired": n_fired,
        "fire_rate": round(fire_rate, 4),
        "our_mae_all": round(rb["our_abs_error"].mean(), 3),
        "cons_mae_all": round(rb["cons_abs_error"].mean(), 3),
        "disagreement_n": n_disagree,
        "disagreement_fired_n": n_disagree_fired,
        "precision_on_disagree": (
            round(precision_on_disagree, 3) if precision_on_disagree is not None else None
        ),
        "our_minus_cons_on_fired": round(our_minus_cons_on_fired, 3),
        "optimal_multiplier": round(best_mult, 2),
        "mae_fired_at_opt_mult": round(mae_at_opt, 3),
        "mae_fired_baseline": round(mae_fired_baseline, 3),
        "est_rb_mae_delta": round(est_rb_mae_delta, 3),
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("=== RB Role Signal Validation ===")

    # 1. Build signal table
    logger.info("Building signal table for seasons %s w3-18 ...", SEASONS)
    signals = build_rb_role_signals(SEASONS, weeks=(3, 18))
    logger.info("Signal table: %d rows", len(signals))

    # 2. Load and dedup consensus
    consensus = load_consensus(CONSENSUS_CSV)
    rb = consensus[consensus["position"] == "RB"].copy()
    logger.info(
        "RB rows in consensus (after dedup): %d | our MAE: %.3f | cons MAE: %.3f",
        len(rb),
        rb["our_abs_error"].mean(),
        rb["cons_abs_error"].mean(),
    )

    # 3. Join signals
    # Merge on player_id, season (season in consensus = proj_season), week
    rb = rb.rename(columns={"proj_season": "season_join"})
    # consensus has 'season' and 'proj_season' columns; proj_season is the projection season
    rb["season"] = rb["season_join"].astype(int)
    rb["week"] = rb["week"].astype(int)

    signals["player_id"] = signals["player_id"].astype(str)
    rb["player_id"] = rb["player_id"].astype(str)

    joined = rb.merge(
        signals[
            [
                "player_id",
                "season",
                "week",
                "rb_better_teammate_out",
                "rb_better_teammate_returning",
                "snap_share_slope",
                "snap_share_collapsing",
                "depth_rank_improved",
                "depth_rank_worsened",
                "current_depth_rank",
                "modal_depth_rank_lookback",
                "recent_snap_pct",
                "prior_snap_pct",
            ]
        ],
        on=["player_id", "season", "week"],
        how="left",
    )
    n_matched = joined[["rb_better_teammate_out", "snap_share_slope", "depth_rank_improved"]].notna().any(axis=1).sum()
    logger.info(
        "Joined: %d / %d RB rows matched to signal table (%.1f%%)",
        n_matched,
        len(joined),
        100 * n_matched / len(joined),
    )

    # Fill integer signals with 0 for unmatched rows
    for col in ["rb_better_teammate_out", "rb_better_teammate_returning",
                "snap_share_collapsing", "depth_rank_improved", "depth_rank_worsened"]:
        if col in joined.columns:
            joined[col] = joined[col].fillna(0).astype(int)

    # 4. Per-signal statistics
    signal_cols = [
        "rb_better_teammate_out",
        "rb_better_teammate_returning",
        "snap_share_collapsing",
        "depth_rank_improved",
        "depth_rank_worsened",
    ]

    print("\n" + "=" * 90)
    print("SIGNAL VALIDATION TABLE (RBs, 2022-2024 w3-18, half-PPR)")
    print("=" * 90)
    print(
        f"{'Signal':<35} {'N fired':>8} {'Fire%':>6} "
        f"{'Our-Cons on fired':>18} {'Dis.fired':>10} "
        f"{'Prec on dis':>12} {'Opt mult':>9} {'MAE delta':>10}"
    )
    print("-" * 90)

    results = []
    for col in signal_cols:
        stats = signal_stats(joined, col)
        results.append(stats)
        n_fired = stats.get("n_fired", 0)
        fire_rate_pct = f"{100*stats.get('fire_rate', 0):.1f}%"
        our_minus = (
            f"{stats['our_minus_cons_on_fired']:+.3f}"
            if stats.get("our_minus_cons_on_fired") is not None
            else "  N/A"
        )
        dis_fired = stats.get("disagreement_fired_n", 0)
        prec = (
            f"{stats['precision_on_disagree']:+.3f}"
            if stats.get("precision_on_disagree") is not None
            else "  N/A"
        )
        opt_m = f"{stats.get('optimal_multiplier', 1.0):.2f}x"
        delta = f"{stats.get('est_rb_mae_delta', 0.0):+.3f}"
        print(
            f"{col:<35} {n_fired:>8} {fire_rate_pct:>6} "
            f"{our_minus:>18} {dis_fired:>10} "
            f"{prec:>12} {opt_m:>9} {delta:>10}"
        )
    print("=" * 90)
    print(
        "\nBaseline (no signal): our MAE = "
        f"{joined['our_abs_error'].mean():.3f}, "
        f"cons MAE = {joined['cons_abs_error'].mean():.3f}, "
        f"gap = {joined['our_abs_error'].mean() - joined['cons_abs_error'].mean():+.3f}"
    )
    print(
        "Columns: N fired = rows where signal fires | Fire% = % of all RB rows | "
        "Our-Cons on fired = mean(our_abs_error - cons_abs_error) on fired rows (positive = we're worse) | "
        "Dis.fired = disagreement-bucket rows where signal fires | "
        "Prec on dis = mean(our_abs_error - cons_abs_error) on disagreement+fired rows | "
        "Opt mult = multiplier to apply to projection that minimises MAE on fired rows | "
        "MAE delta = estimated full-RB MAE improvement from applying optimal mult"
    )

    # 5. Disagreement bucket deep dive
    print("\n" + "=" * 70)
    print("DISAGREEMENT BUCKET ANALYSIS (|ours - cons| >= 4 pts)")
    print("=" * 70)
    dis = joined[(joined["our_abs_error"] - joined["cons_abs_error"]).abs() >= DISAGREE_THRESHOLD]
    print(f"Disagreement rows: {len(dis)} / {len(joined)} ({100*len(dis)/len(joined):.1f}%)")
    print(f"our MAE on disagreement: {dis['our_abs_error'].mean():.3f}")
    print(f"cons MAE on disagreement: {dis['cons_abs_error'].mean():.3f}")

    # ours >> cons (we over-project)
    over = joined[joined["projected_points"] - joined["consensus_proj"] >= 4]
    under = joined[joined["consensus_proj"] - joined["projected_points"] >= 4]
    print(f"\nOurs >> cons (+4): n={len(over)}, our_mae={over['our_abs_error'].mean():.2f}, cons_mae={over['cons_abs_error'].mean():.2f}")
    print(f"Ours << cons (-4): n={len(under)}, our_mae={under['our_abs_error'].mean():.2f}, cons_mae={under['cons_abs_error'].mean():.2f}")

    for col in ["rb_better_teammate_returning", "snap_share_collapsing", "depth_rank_worsened"]:
        if col in over.columns:
            n_over_fire = int((over[col] != 0).sum())
            print(
                f"  {col} fires in {n_over_fire}/{len(over)} ours>>cons rows "
                f"({100*n_over_fire/len(over):.1f}%)"
            )
    for col in ["rb_better_teammate_out", "depth_rank_improved"]:
        if col in under.columns:
            n_under_fire = int((under[col] != 0).sum())
            print(
                f"  {col} fires in {n_under_fire}/{len(under)} ours<<cons rows "
                f"({100*n_under_fire/len(under):.1f}%)"
            )

    # 6. Named case sanity checks
    print("\n" + "=" * 70)
    print("NAMED CASE SANITY CHECKS")
    print("=" * 70)
    cases = [
        # (description, player_id, season, week)
        ("Z.Moss 2023 w5 (Taylor returned → rb_better_teammate_returning expected later)", "00-0036251", 2023, 5),
        ("Z.Moss 2023 w9 (snap_share_collapsing expected)", "00-0036251", 2023, 9),
        ("Z.Moss 2023 w10 (snap_share_collapsing expected)", "00-0036251", 2023, 10),
        ("D.Foreman 2022 w8 (depth_rank_improved expected)", "00-0033925", 2022, 8),
        ("Z.Charbonnet 2024 w15 (rb_better_teammate_out expected)", "00-0039165", 2024, 15),
    ]
    signal_check_cols = [
        "projected_points", "consensus_proj", "actual_points",
        "rb_better_teammate_out", "rb_better_teammate_returning",
        "snap_share_collapsing", "snap_share_slope", "recent_snap_pct",
        "depth_rank_improved", "depth_rank_worsened",
        "current_depth_rank", "modal_depth_rank_lookback",
    ]
    for desc, pid, season, week in cases:
        row = joined[
            (joined["player_id"] == pid)
            & (joined["season"] == season)
            & (joined["week"] == week)
        ]
        if len(row) == 0:
            print(f"\n{desc}")
            print("  NOT FOUND in consensus CSV")
            continue
        print(f"\n{desc}")
        r = row.iloc[0]
        for col in signal_check_cols:
            if col in row.columns:
                val = r[col]
                print(f"  {col}: {val}")

    # 7. Also show Z.Moss snap collapse over the full window
    print("\n--- Z.Moss 2023 snap history ---")
    moss_all = joined[
        (joined["player_id"] == "00-0036251")
        & (joined["season"] == 2023)
    ].sort_values("week")
    if len(moss_all) > 0:
        print(
            moss_all[
                ["week", "projected_points", "consensus_proj", "actual_points",
                 "snap_share_collapsing", "snap_share_slope", "recent_snap_pct",
                 "rb_better_teammate_returning", "depth_rank_worsened"]
            ].to_string()
        )

    # 8. Recommendation
    print("\n" + "=" * 70)
    print("RECOMMENDATION (gate: est_rb_mae_delta >= 0.02)")
    print("=" * 70)
    for r in results:
        est = r.get("est_rb_mae_delta", 0.0)
        recommend = "RECOMMEND" if abs(est) >= 0.02 else "below gate"
        direction = "APPLY" if est > 0 else "no net benefit on full RB pop"
        print(
            f"  {r['signal']:<35} est MAE delta = {est:+.3f} → {recommend} ({direction})"
        )

    # Save joined table
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    joined.to_csv(OUTPUT_CSV, index=False)
    logger.info("Saved joined validation table to %s", OUTPUT_CSV)


if __name__ == "__main__":
    main()
