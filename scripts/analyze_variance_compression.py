"""
Variance Compression Analysis — Hypothesis (2) Investigation.

Measures whether PROJECTION_CEILING_SHRINKAGE + POSITION_CEILING_SHRINKAGE flatten
within-band projections into indistinguishability, destroying within-position-week rank
ordering that existed pre-shrinkage.

Steps:
1. Spread analysis: std/IQR of ours vs consensus within position-week bands (top-12, 13-24).
2. Rank-preservation check: is shrinkage rank-preserving within position-week?
3. Tie analysis: how many ours-vs-consensus projections are within 0.5 pts?
4. Headroom: if we broke ties perfectly (within 0.5 pt), what band Spearman would we achieve?

The "pre-shrinkage" projection is reconstructed by inverting the shrinkage factors
applied to each row (monotone step function, so it's exactly reversible per tier).

Usage:
    python scripts/analyze_variance_compression.py

Output:
    output/variance_compression_analysis.txt  (full report)
    Stdout: summary tables
"""

import logging
import sys
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# Project root on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Shrinkage constants (must mirror projection_engine.py exactly) ──────────
PROJECTION_CEILING_SHRINKAGE: Dict[float, float] = {
    12.0: 0.92,
    18.0: 0.87,
    23.0: 0.80,
}

POSITION_CEILING_SHRINKAGE: Dict[str, Dict[float, float]] = {
    "WR": {12.0: 0.88},
    "TE": {12.0: 0.88},
}

# Bias corrections applied AFTER shrinkage (additive)
POSITION_BIAS_CORRECTION: Dict[str, float] = {
    "QB": 2.3,
}

# Low-projection floor boost (threshold, boost)
LOW_PROJECTION_FLOOR_BOOST: Dict[str, Tuple[float, float]] = {
    "QB": (5.0, 1.0),
    "RB": (3.0, 0.5),
    "WR": (3.0, 0.5),
    "TE": (2.5, 0.3),
}

# ── Data paths ────────────────────────────────────────────────────────────────
FINAL_CSV = ROOT / "output/backtest/consensus_matched_half_ppr_20260611_235925.csv"
OUTPUT_PATH = ROOT / "output/variance_compression_analysis.txt"


def reverse_global_shrinkage(pts: pd.Series) -> pd.Series:
    """Invert PROJECTION_CEILING_SHRINKAGE applied sequentially.

    The cascade applies: for each threshold (ascending), if pts >= threshold,
    factor is overwritten with the tier's factor.  So each row ends up with
    the factor of the HIGHEST threshold it crossed.  Invert by dividing by
    the factor that was applied.

    Since we evaluate at POST-shrinkage values, this is a conservative inversion
    (slightly underestimates true pre values in tier boundaries) but preserves
    ordering monotonically.
    """
    factor = pd.Series(1.0, index=pts.index)
    for threshold in sorted(PROJECTION_CEILING_SHRINKAGE.keys()):
        f = PROJECTION_CEILING_SHRINKAGE[threshold]
        factor = factor.where(pts < threshold, f)
    return pts / factor


def reverse_position_shrinkage(pts: pd.Series, position: str) -> pd.Series:
    """Invert POSITION_CEILING_SHRINKAGE for positions that have it."""
    if position not in POSITION_CEILING_SHRINKAGE:
        return pts
    factor = pd.Series(1.0, index=pts.index)
    for threshold, f in sorted(POSITION_CEILING_SHRINKAGE[position].items()):
        factor = factor.where(pts < threshold, f)
    return pts / factor


def compute_pre_shrinkage(row_pts: pd.Series, position: str) -> pd.Series:
    """Best-effort reconstruction of projected_points before shrinkage.

    Forward order of operations: global shrink → position shrink → bias correction
    → floor boost.  We undo in reverse order.

    Note: bias correction + floor boost are additive after shrinkage and do NOT
    affect relative ordering within a position-week UNLESS floor boost fires
    within the band (very unlikely for cons≥5 rows).  We null out floor-boost
    candidates conservatively.
    """
    pts = row_pts.copy()

    # Undo floor boost: rows below (thresh + boost) might have been boosted;
    # null them out since we can't recover exact pre-boost value.
    if position in LOW_PROJECTION_FLOOR_BOOST:
        thresh, boost = LOW_PROJECTION_FLOOR_BOOST[position]
        floor_mask = pts < (thresh + boost + 0.05)
        pts = pts.where(~floor_mask, other=np.nan)

    # Undo bias correction (additive)
    if position in POSITION_BIAS_CORRECTION:
        pts = pts - POSITION_BIAS_CORRECTION[position]

    # Undo position shrinkage
    pts = reverse_position_shrinkage(pts, position)

    # Undo global shrinkage
    pts = reverse_global_shrinkage(pts)

    return pts


def assign_consensus_band(cons_rank: pd.Series) -> pd.Series:
    """Map consensus within-position-week rank to band label."""
    bands = pd.Series("25+", index=cons_rank.index)
    bands[cons_rank <= 24] = "13-24"
    bands[cons_rank <= 12] = "top-12"
    return bands


def spearman_within_groups(
    df: pd.DataFrame, pred_col: str, actual_col: str, group_cols: List[str]
) -> float:
    """Mean per-group Spearman between pred_col and actual_col (groups with ≥3 rows)."""
    corrs = []
    for _, grp in df.groupby(group_cols):
        if len(grp) < 3:
            continue
        if grp[pred_col].std() < 1e-9 or grp[actual_col].std() < 1e-9:
            corrs.append(0.0)
            continue
        r, _ = spearmanr(grp[pred_col], grp[actual_col])
        if not np.isnan(r):
            corrs.append(r)
    return float(np.mean(corrs)) if corrs else np.nan


def spread_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Compare std/IQR of ours vs consensus within position-band-week groups."""
    rows = []
    for pos in ["RB", "WR", "TE", "QB"]:
        pos_df = df[df["position"] == pos].copy()
        pos_df["band"] = assign_consensus_band(pos_df["cons_rank_within_week"])
        for band in ["top-12", "13-24", "25+"]:
            band_df = pos_df[pos_df["band"] == band]
            if len(band_df) < 10:
                continue
            # Per-week stats then mean across weeks
            wk_stats = band_df.groupby(["season", "week"]).agg(
                ours_std=("projected_points", "std"),
                ours_iqr=("projected_points", lambda x: x.quantile(0.75) - x.quantile(0.25)),
                cons_std=("consensus_proj", "std"),
                cons_iqr=("consensus_proj", lambda x: x.quantile(0.75) - x.quantile(0.25)),
                n=("projected_points", "count"),
            )
            rows.append({
                "pos": pos,
                "band": band,
                "n_pw": len(band_df),
                "n_wks": len(wk_stats),
                "ours_std": wk_stats["ours_std"].mean(),
                "cons_std": wk_stats["cons_std"].mean(),
                "ours_iqr": wk_stats["ours_iqr"].mean(),
                "cons_iqr": wk_stats["cons_iqr"].mean(),
                "std_ratio": wk_stats["ours_std"].mean() / max(wk_stats["cons_std"].mean(), 0.01),
                "iqr_ratio": wk_stats["ours_iqr"].mean() / max(wk_stats["cons_iqr"].mean(), 0.01),
            })
    return pd.DataFrame(rows)


def count_rank_flips(
    group_df: pd.DataFrame, col_a: str, col_b: str
) -> Tuple[int, int]:
    """Count pairs where rank order differs between col_a and col_b."""
    idxs = list(group_df.index)
    a_vals = group_df[col_a].values
    b_vals = group_df[col_b].values
    flips = 0
    total = 0
    for ii, jj in combinations(range(len(idxs)), 2):
        total += 1
        # i ranks higher than j in col_a?
        a_order = a_vals[ii] > a_vals[jj]
        b_order = b_vals[ii] > b_vals[jj]
        if a_order != b_order:
            flips += 1
    return flips, total


def rank_preservation_analysis(df: pd.DataFrame) -> Dict:
    """Check if shrinkage is rank-preserving within position-weeks."""
    results = {}
    for pos in ["RB", "WR", "TE", "QB"]:
        pos_df = df[df["position"] == pos].copy()

        # Reconstruct pre-shrinkage
        pos_df["pre_shrink_proj"] = compute_pre_shrinkage(
            pos_df["projected_points"], pos
        )
        pos_df = pos_df.dropna(subset=["pre_shrink_proj"])

        pos_df["band"] = assign_consensus_band(pos_df["cons_rank_within_week"])

        pos_results = {}
        for band in ["top-12", "13-24", "25+"]:
            band_df = pos_df[pos_df["band"] == band].copy()
            if len(band_df) < 20:
                pos_results[band] = {
                    "post": np.nan, "pre": np.nan, "delta": np.nan,
                    "n": len(band_df), "rank_flips": 0, "total_pairs": 0,
                    "flip_rate": np.nan,
                }
                continue

            post_spear = spearman_within_groups(
                band_df, "projected_points", "actual_points", ["season", "week"]
            )
            pre_spear = spearman_within_groups(
                band_df, "pre_shrink_proj", "actual_points", ["season", "week"]
            )

            # Count rank-flips introduced by shrinkage
            total_flips = 0
            total_pairs = 0
            for _, grp in band_df.groupby(["season", "week"]):
                if len(grp) < 2:
                    continue
                flips, pairs = count_rank_flips(
                    grp, "pre_shrink_proj", "projected_points"
                )
                total_flips += flips
                total_pairs += pairs

            flip_rate = total_flips / max(total_pairs, 1)

            pos_results[band] = {
                "post": post_spear,
                "pre": pre_spear,
                "delta": pre_spear - post_spear,
                "n": len(band_df),
                "rank_flips": total_flips,
                "total_pairs": total_pairs,
                "flip_rate": flip_rate,
            }
        results[pos] = pos_results
    return results


def tie_analysis(df: pd.DataFrame, tie_threshold: float = 0.5) -> pd.DataFrame:
    """Quantify within-band projection ties and compute oracle headroom."""
    rows = []
    for pos in ["RB", "WR", "TE", "QB"]:
        pos_df = df[df["position"] == pos].copy()
        pos_df["band"] = assign_consensus_band(pos_df["cons_rank_within_week"])

        for band in ["top-12", "13-24"]:
            band_df = pos_df[pos_df["band"] == band].copy()
            if len(band_df) < 10:
                continue

            current_spear = spearman_within_groups(
                band_df, "projected_points", "actual_points", ["season", "week"]
            )
            cons_spear = spearman_within_groups(
                band_df, "consensus_proj", "actual_points", ["season", "week"]
            )

            tied_pairs = 0
            total_pairs = 0
            perfect_break_spears = []

            for _, grp in band_df.groupby(["season", "week"]):
                if len(grp) < 2:
                    continue
                proj = grp["projected_points"].values
                actual = grp["actual_points"].values
                n = len(proj)

                # Count tied pairs
                for ii, jj in combinations(range(n), 2):
                    total_pairs += 1
                    if abs(proj[ii] - proj[jj]) <= tie_threshold:
                        tied_pairs += 1

                # Oracle projection: nudge tied rows by actual
                proj_series = grp["projected_points"].copy()
                tied_mask = pd.Series(False, index=grp.index)
                idxs = list(grp.index)
                for ii, i_idx in enumerate(idxs):
                    for jj, j_idx in enumerate(idxs):
                        if ii >= jj:
                            continue
                        if abs(proj_series[i_idx] - proj_series[j_idx]) <= tie_threshold:
                            tied_mask[i_idx] = True
                            tied_mask[j_idx] = True

                oracle = proj_series.copy()
                oracle[tied_mask] = (
                    proj_series[tied_mask]
                    + 0.001 * grp.loc[tied_mask, "actual_points"]
                )
                if oracle.std() > 1e-9 and grp["actual_points"].std() > 1e-9:
                    r, _ = spearmanr(oracle, grp["actual_points"])
                    if not np.isnan(r):
                        perfect_break_spears.append(r)

            tie_rate = tied_pairs / max(total_pairs, 1)
            oracle_spear = (
                float(np.mean(perfect_break_spears)) if perfect_break_spears else np.nan
            )
            headroom = oracle_spear - current_spear if not np.isnan(oracle_spear) else np.nan

            rows.append({
                "pos": pos,
                "band": band,
                "n_pw": len(band_df),
                "current_spear": current_spear,
                "cons_spear": cons_spear,
                "gap": current_spear - cons_spear,
                "tie_rate_%": tie_rate * 100,
                "tied_pairs": tied_pairs,
                "total_pairs": total_pairs,
                "oracle_spear": oracle_spear,
                "headroom": headroom,
            })
    return pd.DataFrame(rows)


def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    """Load the consensus matched CSV and compute derived columns."""
    df = pd.read_csv(csv_path)

    # Standard filters
    df = df[
        (df["consensus_proj"] >= 5)
        & (df["week"] >= 3)
        & (~df["is_bye_week"])
        & (~df["season"].isin([2025]))
    ].copy()

    logger.info("Loaded %d rows (cons>=5, w3-18, no bye, 2022-24)", len(df))

    # Compute consensus rank within position-week
    df["cons_rank_within_week"] = df.groupby(["position", "season", "week"])[
        "consensus_proj"
    ].rank(ascending=False, method="min")

    return df


def format_table(df: pd.DataFrame, float_cols: List[str], fmt: str = "{:.3f}") -> str:
    """Format a DataFrame for display with controlled float precision."""
    display = df.copy()
    for col in float_cols:
        if col in display.columns:
            display[col] = display[col].apply(
                lambda x: fmt.format(x) if pd.notna(x) else "—"
            )
    return display.to_string(index=False)


def main() -> None:
    logger.info("Starting variance compression analysis")
    logger.info("Reading: %s", FINAL_CSV)

    df = load_and_prepare(FINAL_CSV)

    output_lines: List[str] = []

    # ── 1. Spread Analysis ─────────────────────────────────────────────────────
    logger.info("Running spread analysis...")
    spread_df = spread_analysis(df)

    output_lines.append("=" * 72)
    output_lines.append("1. WITHIN-BAND SPREAD: ours vs consensus (mean std/IQR per position-week)")
    output_lines.append("   std_ratio = ours_std / cons_std  (<1 = we are flatter)")
    output_lines.append("=" * 72)
    output_lines.append(
        format_table(
            spread_df,
            ["ours_std", "cons_std", "ours_iqr", "cons_iqr", "std_ratio", "iqr_ratio"],
            "{:.3f}",
        )
    )
    output_lines.append("")

    # ── 2. Rank-Preservation Check ─────────────────────────────────────────────
    logger.info("Running rank-preservation check (this may take ~30s)...")
    rp_results = rank_preservation_analysis(df)

    output_lines.append("=" * 72)
    output_lines.append("2. RANK-PRESERVATION: band Spearman pre-shrinkage vs post-shrinkage")
    output_lines.append("   delta(pre-post) > 0  => shrinkage hurts ordering")
    output_lines.append("   flip_rate: fraction of within-week pairs reordered by shrinkage")
    output_lines.append("=" * 72)
    rp_rows = []
    for pos, bands in rp_results.items():
        for band, vals in bands.items():
            rp_rows.append(
                {
                    "pos": pos,
                    "band": band,
                    "n": vals.get("n", 0),
                    "post_spear": vals.get("post", np.nan),
                    "pre_spear": vals.get("pre", np.nan),
                    "delta(pre-post)": vals.get("delta", np.nan),
                    "flip_rate": vals.get("flip_rate", np.nan),
                    "flips": vals.get("rank_flips", 0),
                    "pairs": vals.get("total_pairs", 0),
                }
            )
    rp_df = pd.DataFrame(rp_rows)
    output_lines.append(
        format_table(
            rp_df,
            ["post_spear", "pre_spear", "delta(pre-post)", "flip_rate"],
            "{:.4f}",
        )
    )
    output_lines.append("")

    # Verdict
    rp_df_num = rp_df.copy()
    rp_df_num["delta_num"] = pd.to_numeric(
        rp_df_num["delta(pre-post)"], errors="coerce"
    )
    sig_reorder = rp_df_num[
        (rp_df_num["delta_num"] > 0.01)
        & rp_df_num["band"].isin(["top-12", "13-24"])
    ]
    output_lines.append("RANK-PRESERVATION VERDICT:")
    if len(sig_reorder) == 0:
        output_lines.append(
            "  Shrinkage IS effectively rank-preserving in all broken bands (delta < 0.01)."
        )
        output_lines.append(
            "  => Compression hypothesis WRONG for Spearman. Fix requires new signal, not de-compression."
        )
    else:
        bands_affected = sig_reorder[["pos", "band", "delta_num"]].to_string(index=False)
        output_lines.append(
            f"  Shrinkage REORDERS {len(sig_reorder)} band(s) by >0.01 Spearman:\n{bands_affected}"
        )
        output_lines.append(
            "  => Compression contributes to rank-ordering loss. De-compression could help."
        )
    output_lines.append("")

    # ── 3. Tie Analysis & Headroom ─────────────────────────────────────────────
    logger.info("Running tie analysis (this may take ~60s)...")
    tie_df = tie_analysis(df, tie_threshold=0.5)

    output_lines.append("=" * 72)
    output_lines.append("3. TIE ANALYSIS (|proj_i - proj_j| <= 0.5 pts within band-week)")
    output_lines.append("   tie_rate_%: % of within-band pairs within 0.5 pts of each other")
    output_lines.append("   oracle_spear: Spearman if we perfectly break all 0.5pt ties")
    output_lines.append("   headroom: oracle_spear - current_spear (max gain from any tiebreaker)")
    output_lines.append("=" * 72)
    output_lines.append(
        format_table(
            tie_df,
            ["current_spear", "cons_spear", "gap", "tie_rate_%", "oracle_spear", "headroom"],
            "{:.4f}",
        )
    )
    output_lines.append("")

    # ── 4. Raw spread spot-check ───────────────────────────────────────────────
    output_lines.append("=" * 72)
    output_lines.append("4. RAW PROJECTION PERCENTILES (ours vs consensus) — top-12 + 13-24")
    output_lines.append("=" * 72)
    for pos in ["RB", "WR"]:
        pos_df = df[df["position"] == pos].copy()
        pos_df["band"] = assign_consensus_band(pos_df["cons_rank_within_week"])
        for band in ["top-12", "13-24"]:
            band_df = pos_df[pos_df["band"] == band]
            od = band_df["projected_points"].describe(
                percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
            )
            cd = band_df["consensus_proj"].describe(
                percentiles=[0.1, 0.25, 0.5, 0.75, 0.9]
            )
            output_lines.append(f"\n{pos} {band} (n={len(band_df)})")
            output_lines.append(
                f"  Ours:      p10={od['10%']:.1f}  p25={od['25%']:.1f}  "
                f"med={od['50%']:.1f}  p75={od['75%']:.1f}  p90={od['90%']:.1f}  "
                f"std={od['std']:.2f}"
            )
            output_lines.append(
                f"  Consensus: p10={cd['10%']:.1f}  p25={cd['25%']:.1f}  "
                f"med={cd['50%']:.1f}  p75={cd['75%']:.1f}  p90={cd['90%']:.1f}  "
                f"std={cd['std']:.2f}"
            )
    output_lines.append("")

    # ── 5. Summary ────────────────────────────────────────────────────────────
    output_lines.append("=" * 72)
    output_lines.append("5. COMPRESSION HYPOTHESIS SUMMARY")
    output_lines.append("=" * 72)

    def _get(row_df: pd.DataFrame, col: str) -> float:
        if len(row_df) == 0:
            return np.nan
        return float(row_df.iloc[0][col])

    for pos in ["RB", "WR"]:
        for band in ["top-12", "13-24"]:
            row = tie_df[(tie_df["pos"] == pos) & (tie_df["band"] == band)]
            rp_row = rp_df_num[
                (rp_df_num["pos"] == pos) & (rp_df_num["band"] == band)
            ]
            sp_row = spread_df[(spread_df["pos"] == pos) & (spread_df["band"] == band)]
            output_lines.append(
                f"{pos} {band}: "
                f"std_ratio={_get(sp_row,'std_ratio'):.3f}  "
                f"tie_rate={_get(row,'tie_rate_%'):.1f}%  "
                f"flip_rate={_get(rp_row,'flip_rate'):.4f}  "
                f"headroom={_get(row,'headroom'):.4f}  "
                f"gap={_get(row,'gap'):.4f}"
            )
    output_lines.append("")

    report = "\n".join(output_lines)
    print(report)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report)
    logger.info("Full report written to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
