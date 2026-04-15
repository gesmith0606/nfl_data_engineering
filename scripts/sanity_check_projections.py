#!/usr/bin/env python3
"""
Sanity Check: Compare Our Projections Against Consensus Rankings

Loads our generated preseason projections and compares them against
external consensus rankings (hardcoded fallback + optional live fetch)
to flag critical discrepancies.

Usage:
    python scripts/sanity_check_projections.py --scoring half_ppr
    python scripts/sanity_check_projections.py --scoring ppr --season 2026
"""

import sys
import os
import argparse
import glob as globmod
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")


# ---------------------------------------------------------------------------
# Consensus top-50 rankings (2025/2026 Half-PPR, pre-draft)
# Sources: FantasyPros ECR, ESPN, Yahoo, CBS Sports (aggregated April 2025)
# Format: (rank, player_name, position, team)
# ---------------------------------------------------------------------------
CONSENSUS_TOP_50: List[Tuple[int, str, str, str]] = [
    # QBs
    (1, "Josh Allen", "QB", "BUF"),
    (3, "Lamar Jackson", "QB", "BAL"),
    (5, "Jalen Hurts", "QB", "PHI"),
    (8, "Patrick Mahomes", "QB", "KC"),
    (14, "Joe Burrow", "QB", "CIN"),
    (22, "C.J. Stroud", "QB", "HOU"),
    (30, "Jayden Daniels", "QB", "WAS"),
    (38, "Kyler Murray", "QB", "ARI"),
    # RBs
    (2, "Saquon Barkley", "RB", "PHI"),
    (4, "Jahmyr Gibbs", "RB", "DET"),
    (6, "Bijan Robinson", "RB", "ATL"),
    (7, "Derrick Henry", "RB", "BAL"),
    (10, "Breece Hall", "RB", "NYJ"),
    (13, "Josh Jacobs", "RB", "GB"),
    (15, "De'Von Achane", "RB", "MIA"),
    (18, "Jonathan Taylor", "RB", "IND"),
    (21, "Joe Mixon", "RB", "HOU"),
    (25, "James Cook", "RB", "BUF"),
    (28, "Alvin Kamara", "RB", "NO"),
    (33, "Kenneth Walker III", "RB", "SEA"),
    (36, "David Montgomery", "RB", "DET"),
    (40, "Isiah Pacheco", "RB", "KC"),
    (42, "Aaron Jones", "RB", "MIN"),
    (47, "Travis Etienne", "RB", "JAX"),
    # WRs
    (9, "Ja'Marr Chase", "WR", "CIN"),
    (11, "CeeDee Lamb", "WR", "DAL"),
    (12, "Amon-Ra St. Brown", "WR", "DET"),
    (16, "Tyreek Hill", "WR", "MIA"),
    (17, "Justin Jefferson", "WR", "MIN"),
    (19, "Puka Nacua", "WR", "LAR"),
    (20, "Malik Nabers", "WR", "NYG"),
    (23, "Nico Collins", "WR", "HOU"),
    (24, "Drake London", "WR", "ATL"),
    (26, "A.J. Brown", "WR", "PHI"),
    (27, "Garrett Wilson", "WR", "NYJ"),
    (29, "Davante Adams", "WR", "NYJ"),
    (31, "Marvin Harrison Jr.", "WR", "ARI"),
    (34, "DK Metcalf", "WR", "SEA"),
    (37, "Chris Olave", "WR", "NO"),
    (39, "Brian Thomas Jr.", "WR", "JAX"),
    (41, "Tee Higgins", "WR", "CIN"),
    (43, "Terry McLaurin", "WR", "WAS"),
    (45, "DeVonta Smith", "WR", "PHI"),
    (48, "Jaylen Waddle", "WR", "MIA"),
    # TEs
    (32, "Travis Kelce", "TE", "KC"),
    (35, "Brock Bowers", "TE", "LV"),
    (44, "Sam LaPorta", "TE", "DET"),
    (46, "Mark Andrews", "TE", "BAL"),
    (49, "George Kittle", "TE", "SF"),
    (50, "Trey McBride", "TE", "ARI"),
]


# ---------------------------------------------------------------------------
# Name normalization for fuzzy matching
# ---------------------------------------------------------------------------
def _normalize_name(name: str) -> str:
    """Normalize player name for comparison (lowercase, strip suffixes)."""
    n = name.lower().strip()
    for suffix in [" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"]:
        n = n.replace(suffix, "")
    # Common name mappings
    mappings = {
        "amon-ra st. brown": "amon-ra st brown",
        "amon ra st. brown": "amon-ra st brown",
        "amon-ra st brown": "amon-ra st brown",
        "kenneth walker": "kenneth walker",
        "kenneth walker iii": "kenneth walker",
        "breece hall": "breece hall",
        "de'von achane": "devon achane",
        "ceedee lamb": "ceedee lamb",
        "marquise brown": "marquise brown",
        "marvin harrison": "marvin harrison",
        "brian thomas": "brian thomas",
    }
    return mappings.get(n, n)


# ---------------------------------------------------------------------------
# Point reasonableness thresholds (full-season, half-PPR)
# ---------------------------------------------------------------------------
SEASON_POINT_CAPS: Dict[str, float] = {
    "QB": 500.0,
    "RB": 400.0,
    "WR": 350.0,
    "TE": 250.0,
}


def _load_our_projections(scoring: str, season: int) -> pd.DataFrame:
    """Load latest preseason projections from Gold layer."""
    pattern = os.path.join(
        GOLD_DIR,
        f"projections/preseason/season={season}/season_proj_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()

    # Load the latest file
    df = pd.read_parquet(files[-1])
    print(f"Loaded projections from: {os.path.basename(files[-1])}")
    print(f"  {len(df)} players, columns: {list(df.columns)[:8]}...")
    return df


def _build_consensus_df() -> pd.DataFrame:
    """Convert hardcoded consensus list to DataFrame."""
    rows = []
    for rank, name, pos, team in CONSENSUS_TOP_50:
        rows.append(
            {
                "consensus_rank": rank,
                "player_name": name,
                "position": pos,
                "team": team,
                "norm_name": _normalize_name(name),
            }
        )
    return pd.DataFrame(rows)


def _match_players(
    our_df: pd.DataFrame, consensus_df: pd.DataFrame
) -> pd.DataFrame:
    """Match consensus players to our projections using fuzzy name matching."""
    our = our_df.copy()
    our["norm_name"] = our["player_name"].apply(_normalize_name)

    matched = consensus_df.merge(
        our[["norm_name", "player_name", "position", "recent_team",
             "projected_season_points", "overall_rank", "position_rank"]],
        on="norm_name",
        how="left",
        suffixes=("_consensus", "_ours"),
    )
    return matched


def run_sanity_check(scoring: str, season: int) -> int:
    """Run the full sanity check and print report. Returns exit code."""
    print("=" * 70)
    print(f"  NFL Projection Sanity Check — {scoring.upper()}, Season {season}")
    print("=" * 70)

    # Load our projections
    our_df = _load_our_projections(scoring, season)
    if our_df.empty:
        print("\nERROR: No projections found. Run generate_projections.py first.")
        print(f"  Expected: data/gold/projections/preseason/season={season}/")
        return 1

    # Build consensus
    consensus_df = _build_consensus_df()
    print(f"\nConsensus rankings: {len(consensus_df)} players (hardcoded fallback)")

    # Match players
    matched = _match_players(our_df, consensus_df)

    # ------------------------------------------------------------------
    # 1. CRITICAL: Position mismatches
    # ------------------------------------------------------------------
    criticals: List[str] = []
    pos_mismatch = matched[
        matched["position_ours"].notna()
        & (matched["position_consensus"] != matched["position_ours"])
    ]
    for _, row in pos_mismatch.iterrows():
        msg = (
            f"POSITION MISMATCH: {row['player_name_consensus']} — "
            f"consensus={row['position_consensus']}, ours={row['position_ours']}"
        )
        criticals.append(msg)

    # ------------------------------------------------------------------
    # 2. CRITICAL: Missing top players (consensus top-50 not in ours)
    # ------------------------------------------------------------------
    missing = matched[matched["overall_rank"].isna()]
    for _, row in missing.iterrows():
        msg = (
            f"MISSING PLAYER: {row['player_name']} ({row['position']}, "
            f"{row['team']}) — consensus rank #{row['consensus_rank']}, "
            f"not found in our projections"
        )
        criticals.append(msg)

    # ------------------------------------------------------------------
    # 3. WARNING: Large rank discrepancies (>20 spots)
    # ------------------------------------------------------------------
    warnings: List[str] = []
    matched_found = matched[matched["overall_rank"].notna()].copy()
    matched_found["rank_diff"] = (
        matched_found["overall_rank"] - matched_found["consensus_rank"]
    )
    matched_found["abs_rank_diff"] = matched_found["rank_diff"].abs()

    big_diff = matched_found[matched_found["abs_rank_diff"] > 20].sort_values(
        "abs_rank_diff", ascending=False
    )
    for _, row in big_diff.iterrows():
        direction = "LOWER" if row["rank_diff"] > 0 else "HIGHER"
        warnings.append(
            f"RANK GAP: {row['player_name_consensus']} ({row['position_consensus']}) — "
            f"consensus #{int(row['consensus_rank'])}, ours #{int(row['overall_rank'])} "
            f"(diff: {int(row['rank_diff']):+d}, we rank {direction})"
        )

    # ------------------------------------------------------------------
    # 4. WARNING: Unreasonable projected points
    # ------------------------------------------------------------------
    for _, row in our_df.iterrows():
        pos = row.get("position", "")
        pts = row.get("projected_season_points", 0)
        cap = SEASON_POINT_CAPS.get(pos)
        if cap and pts > cap:
            warnings.append(
                f"UNREASONABLE PTS: {row['player_name']} ({pos}) — "
                f"{pts:.1f} pts exceeds {cap:.0f} cap"
            )

    # Also flag negative projections
    neg = our_df[our_df["projected_season_points"] < 0]
    for _, row in neg.iterrows():
        warnings.append(
            f"NEGATIVE PTS: {row['player_name']} ({row['position']}) — "
            f"{row['projected_season_points']:.1f} pts"
        )

    # ------------------------------------------------------------------
    # Print CRITICAL issues
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  CRITICAL ISSUES")
    print("=" * 70)
    if criticals:
        for c in criticals:
            print(f"  [CRITICAL] {c}")
    else:
        print("  None — all consensus players found with correct positions.")

    # ------------------------------------------------------------------
    # Print WARNINGS
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  WARNINGS")
    print("=" * 70)
    if warnings:
        for w in warnings:
            print(f"  [WARNING]  {w}")
    else:
        print("  None — all ranks within 20 spots, all points reasonable.")

    # ------------------------------------------------------------------
    # Top-20 comparison table
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  TOP-20 COMPARISON TABLE")
    print("=" * 70)
    top20 = (
        matched_found.sort_values("consensus_rank")
        .head(20)
    )
    header = f"{'Player':<25} {'Pos':<4} {'Cons#':>6} {'Ours#':>6} {'Diff':>6} {'Our Pts':>8}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for _, row in top20.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_rank = int(row["consensus_rank"])
        our_rank = int(row["overall_rank"])
        diff = int(row["rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_rank:>6} {our_rank:>6} {diff_str:>6} {pts:>8.1f}"
        )

    # ------------------------------------------------------------------
    # Biggest rank discrepancies
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  BIGGEST RANK DISCREPANCIES (top 10)")
    print("=" * 70)
    worst = matched_found.sort_values("abs_rank_diff", ascending=False).head(10)
    header2 = f"{'Player':<25} {'Pos':<4} {'Cons#':>6} {'Ours#':>6} {'Diff':>6} {'Our Pts':>8}"
    print(f"  {header2}")
    print(f"  {'-' * len(header2)}")
    for _, row in worst.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_rank = int(row["consensus_rank"])
        our_rank = int(row["overall_rank"])
        diff = int(row["rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_rank:>6} {our_rank:>6} {diff_str:>6} {pts:>8.1f}"
        )

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  SUMMARY STATISTICS")
    print("=" * 70)

    n_matched = len(matched_found)
    n_missing = len(missing)
    n_total_consensus = len(consensus_df)

    print(f"  Consensus players matched: {n_matched} / {n_total_consensus}")
    print(f"  Missing from our projections: {n_missing}")
    print(f"  Critical issues: {len(criticals)}")
    print(f"  Warnings: {len(warnings)}")

    if n_matched > 1:
        # Rank correlation (Spearman)
        from scipy import stats as sp_stats

        corr, p_value = sp_stats.spearmanr(
            matched_found["consensus_rank"], matched_found["overall_rank"]
        )
        print(f"\n  Spearman rank correlation: {corr:.3f} (p={p_value:.4f})")
        if corr > 0.8:
            print("  Interpretation: STRONG agreement with consensus")
        elif corr > 0.6:
            print("  Interpretation: MODERATE agreement with consensus")
        elif corr > 0.4:
            print("  Interpretation: WEAK agreement with consensus")
        else:
            print("  Interpretation: POOR agreement — investigate model")

        # Mean absolute rank difference
        mean_diff = matched_found["abs_rank_diff"].mean()
        median_diff = matched_found["abs_rank_diff"].median()
        print(f"  Mean absolute rank difference: {mean_diff:.1f}")
        print(f"  Median absolute rank difference: {median_diff:.1f}")

        # Per-position breakdown
        print(f"\n  Per-position rank correlation:")
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_data = matched_found[matched_found["position_consensus"] == pos]
            if len(pos_data) > 2:
                pos_corr, _ = sp_stats.spearmanr(
                    pos_data["consensus_rank"], pos_data["overall_rank"]
                )
                pos_mean = pos_data["abs_rank_diff"].mean()
                print(
                    f"    {pos}: r={pos_corr:.3f}, mean rank diff={pos_mean:.1f} "
                    f"({len(pos_data)} players)"
                )

    # ------------------------------------------------------------------
    # Our top-10 players (what we think are the best)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  OUR TOP-10 OVERALL")
    print("=" * 70)
    our_top10 = our_df.sort_values("overall_rank").head(10)
    for _, row in our_top10.iterrows():
        print(
            f"  #{int(row['overall_rank']):>3}  {row['player_name']:<25} "
            f"{row['position']:<3}  {row['recent_team']:<4}  "
            f"{row['projected_season_points']:.1f} pts"
        )

    # ------------------------------------------------------------------
    # Position distribution comparison
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  POSITION DISTRIBUTION IN TOP-50")
    print("=" * 70)
    our_top50 = our_df[our_df["overall_rank"] <= 50]
    our_pos_counts = our_top50["position"].value_counts().to_dict()
    cons_pos_counts = consensus_df["position"].value_counts().to_dict()

    header3 = f"{'Position':<10} {'Consensus':>10} {'Ours':>10} {'Diff':>10}"
    print(f"  {header3}")
    print(f"  {'-' * len(header3)}")
    for pos in ["QB", "RB", "WR", "TE"]:
        c = cons_pos_counts.get(pos, 0)
        o = our_pos_counts.get(pos, 0)
        d = o - c
        print(f"  {pos:<10} {c:>10} {o:>10} {d:>+10}")

    # Return code
    if criticals:
        print(f"\n  RESULT: FAIL — {len(criticals)} critical issues found")
        return 1
    elif len(warnings) > 10:
        print(f"\n  RESULT: WARN — {len(warnings)} warnings (>10 threshold)")
        return 0
    else:
        print(f"\n  RESULT: PASS — projections look reasonable")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity check NFL projections against consensus rankings"
    )
    parser.add_argument(
        "--scoring",
        choices=["ppr", "half_ppr", "standard"],
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="Target season (default: 2026)",
    )
    args = parser.parse_args()

    return run_sanity_check(args.scoring, args.season)


if __name__ == "__main__":
    sys.exit(main())
