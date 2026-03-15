"""
Historical player profiles: combine measurables + draft capital dimension table.

Pure compute functions for building the combine/draft Silver dimension table.
No I/O or file operations -- all data passed in as DataFrames.
"""

import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def parse_height_to_inches(ht_str: str) -> Optional[float]:
    """Convert height string like '5-11' to inches (71.0).

    Args:
        ht_str: Height string in "feet-inches" format (e.g., "5-11").

    Returns:
        Height in inches as float, or None if input is NaN or unparseable.
    """
    if pd.isna(ht_str):
        return None
    try:
        feet, inches = ht_str.split("-")
        return float(int(feet) * 12 + int(inches))
    except (ValueError, AttributeError):
        return None


def compute_speed_score(wt: pd.Series, forty: pd.Series) -> pd.Series:
    """Compute Bill Barnwell speed score: (weight * 200) / (forty ^ 4).

    NaN propagates naturally when forty or weight is NaN.

    Args:
        wt: Player weight in pounds.
        forty: 40-yard dash time in seconds.

    Returns:
        Speed score series. Average NFL RB ~100; elite > 110.
    """
    return (wt * 200) / (forty ** 4)


def compute_composite_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add composite measurable columns to a combine/draft DataFrame.

    Computes: height_inches, speed_score, bmi, burst_score, catch_radius.
    NaN propagates naturally for missing raw measurables -- no imputation.

    Args:
        df: DataFrame with columns: ht, wt, forty, vertical, broad_jump.

    Returns:
        DataFrame with added composite score columns.
    """
    result = df.copy()

    # Height in inches from string format
    result["height_inches"] = result["ht"].apply(parse_height_to_inches)

    # Speed score (Bill Barnwell formula)
    result["speed_score"] = compute_speed_score(result["wt"], result["forty"])

    # BMI: weight / height_inches^2
    result["bmi"] = result["wt"] / (result["height_inches"] ** 2)

    # Burst score: vertical + broad_jump
    result["burst_score"] = result["vertical"] + result["broad_jump"]

    # Catch radius proxy: height in inches
    result["catch_radius"] = result["height_inches"]

    return result


def compute_position_percentiles(
    df: pd.DataFrame, score_cols: List[str]
) -> pd.DataFrame:
    """Add position-percentile columns ranked within position group.

    For each column in score_cols, adds a "{col}_pos_pctl" column using
    rank(pct=True) within each position group. NaN values are excluded
    from ranking automatically by pandas.

    Args:
        df: DataFrame with a 'pos' column and the specified score columns.
        score_cols: List of column names to compute percentiles for.

    Returns:
        DataFrame with added _pos_pctl suffix columns.
    """
    result = df.copy()
    for col in score_cols:
        pctl_col = f"{col}_pos_pctl"
        result[pctl_col] = result.groupby("pos")[col].rank(pct=True)
    return result


def build_jimmy_johnson_chart() -> Dict[int, float]:
    """Return the Jimmy Johnson draft trade value chart for picks 1-262.

    Picks 1-224 use the standard chart values. Picks 225-262 are extended
    via linear extrapolation from the round 7 decay rate, with a minimum
    value of 0.4 for pick 262.

    Returns:
        Dict mapping pick number (int) to trade value (float).
    """
    chart = {
        # Round 1
        1: 3000, 2: 2600, 3: 2200, 4: 1800, 5: 1700,
        6: 1600, 7: 1500, 8: 1400, 9: 1350, 10: 1300,
        11: 1250, 12: 1200, 13: 1150, 14: 1100, 15: 1050,
        16: 1000, 17: 950, 18: 900, 19: 875, 20: 850,
        21: 800, 22: 780, 23: 760, 24: 740, 25: 720,
        26: 700, 27: 680, 28: 660, 29: 640, 30: 620,
        31: 600, 32: 590,
        # Round 2
        33: 580, 34: 560, 35: 550, 36: 540, 37: 530,
        38: 520, 39: 510, 40: 500, 41: 490, 42: 480,
        43: 470, 44: 460, 45: 450, 46: 440, 47: 430,
        48: 420, 49: 410, 50: 400, 51: 390, 52: 380,
        53: 370, 54: 360, 55: 350, 56: 340, 57: 330,
        58: 320, 59: 310, 60: 300, 61: 292, 62: 284,
        63: 276, 64: 270,
        # Round 3
        65: 265, 66: 260, 67: 255, 68: 250, 69: 245,
        70: 240, 71: 235, 72: 230, 73: 225, 74: 220,
        75: 215, 76: 210, 77: 205, 78: 200, 79: 195,
        80: 190, 81: 185, 82: 180, 83: 175, 84: 170,
        85: 165, 86: 160, 87: 155, 88: 150, 89: 145,
        90: 140, 91: 136, 92: 132, 93: 128, 94: 124,
        95: 120, 96: 116,
        # Round 4
        97: 112, 98: 108, 99: 104, 100: 100, 101: 96,
        102: 92, 103: 88, 104: 86, 105: 84, 106: 82,
        107: 80, 108: 78, 109: 76, 110: 74, 111: 72,
        112: 70, 113: 68, 114: 66, 115: 64, 116: 62,
        117: 60, 118: 58, 119: 56, 120: 54, 121: 52,
        122: 50, 123: 49, 124: 48, 125: 47, 126: 46,
        127: 45, 128: 44,
        # Round 5
        129: 43, 130: 42, 131: 41, 132: 40, 133: 39.5,
        134: 39, 135: 38.5, 136: 38, 137: 37.5, 138: 37,
        139: 36.5, 140: 36, 141: 35.5, 142: 35, 143: 34.5,
        144: 34, 145: 33.5, 146: 33, 147: 32.6, 148: 32.2,
        149: 31.8, 150: 31.4, 151: 31, 152: 30.6, 153: 30.2,
        154: 29.8, 155: 29.4, 156: 29, 157: 28.6, 158: 28.2,
        159: 27.8, 160: 27.4,
        # Round 6
        161: 27, 162: 26.6, 163: 26.2, 164: 25.8, 165: 25.4,
        166: 25, 167: 24.6, 168: 24.2, 169: 23.8, 170: 23.4,
        171: 23, 172: 22.6, 173: 22.2, 174: 21.8, 175: 21.4,
        176: 21, 177: 20.6, 178: 20.2, 179: 19.8, 180: 19.4,
        181: 19, 182: 18.6, 183: 18.2, 184: 17.8, 185: 17.4,
        186: 17, 187: 16.6, 188: 16.2, 189: 15.8, 190: 15.4,
        191: 15, 192: 14.6,
        # Round 7
        193: 14.2, 194: 13.8, 195: 13.4, 196: 13, 197: 12.6,
        198: 12.2, 199: 11.8, 200: 11.4, 201: 11, 202: 10.6,
        203: 10.2, 204: 9.8, 205: 9.4, 206: 9, 207: 8.6,
        208: 8.2, 209: 7.8, 210: 7.4, 211: 7, 212: 6.6,
        213: 6.2, 214: 5.8, 215: 5.4, 216: 5, 217: 4.6,
        218: 4.2, 219: 3.8, 220: 3.4, 221: 3, 222: 2.6,
        223: 2.3, 224: 2,
    }
    # Compensatory picks (225-262): linear extrapolation, min 0.4
    for p in range(225, 263):
        chart[p] = max(0.4, round(2.0 - (p - 224) * 0.042, 2))

    return chart


def dedup_combine(combine_df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicate pfr_ids from combine data, keeping best match.

    For non-null pfr_ids that appear multiple times, prefers the row where
    season == draft_year (best match quality), then falls back to latest
    season. Rows with null pfr_id are all preserved.

    Args:
        combine_df: Raw combine DataFrame with pfr_id column.

    Returns:
        Deduplicated combine DataFrame.
    """
    # Separate null pfr_ids (keep all)
    null_mask = combine_df["pfr_id"].isna()
    nulls = combine_df[null_mask]
    non_nulls = combine_df[~null_mask].copy()

    if non_nulls.empty:
        return combine_df.copy()

    # Mark rows where season matches draft_year (best match)
    if "draft_year" in non_nulls.columns:
        non_nulls["_match_quality"] = (
            non_nulls["season"] == non_nulls["draft_year"]
        ).astype(int)
    else:
        non_nulls["_match_quality"] = 0

    # Sort: group by pfr_id, best match quality first, then latest season
    non_nulls = non_nulls.sort_values(
        ["pfr_id", "_match_quality", "season"],
        ascending=[True, False, False],
    )
    deduped = non_nulls.drop_duplicates(subset="pfr_id", keep="first")
    deduped = deduped.drop(columns=["_match_quality"])

    return pd.concat([deduped, nulls], ignore_index=True)


def join_combine_draft(
    combine_df: pd.DataFrame, draft_df: pd.DataFrame
) -> pd.DataFrame:
    """Full outer join of combine and draft data on pfr_id.

    Coalesces overlapping columns (season, position) preferring combine
    values. Attaches draft_value from the Jimmy Johnson chart. Adds
    has_pfr_id boolean and gsis_id from draft data.

    Args:
        combine_df: Deduplicated combine DataFrame with pfr_id.
        draft_df: Draft picks DataFrame with pfr_player_id and gsis_id.

    Returns:
        Merged DataFrame with one row per player.
    """
    merged = combine_df.merge(
        draft_df,
        left_on="pfr_id",
        right_on="pfr_player_id",
        how="outer",
        suffixes=("_combine", "_draft"),
    )

    # Coalesce overlapping columns: prefer combine, fall back to draft
    if "season_combine" in merged.columns and "season_draft" in merged.columns:
        merged["season"] = merged["season_combine"].fillna(merged["season_draft"])
        merged = merged.drop(columns=["season_combine", "season_draft"])

    # Coalesce position columns (combine uses 'pos', draft uses 'position')
    if "pos" in merged.columns and "position" in merged.columns:
        merged["pos"] = merged["pos"].fillna(merged["position"])
        merged = merged.drop(columns=["position"])
    elif "position" in merged.columns:
        merged = merged.rename(columns={"position": "pos"})

    # Attach draft value from Jimmy Johnson chart
    chart = build_jimmy_johnson_chart()
    if "pick" in merged.columns:
        merged["draft_value"] = merged["pick"].map(chart)
    else:
        merged["draft_value"] = float("nan")

    # Coalesce pfr_id from both sides
    if "pfr_id" in merged.columns and "pfr_player_id" in merged.columns:
        merged["pfr_id"] = merged["pfr_id"].fillna(merged["pfr_player_id"])

    # Add has_pfr_id flag
    merged["has_pfr_id"] = merged["pfr_id"].notna()

    # Preserve gsis_id from draft data for downstream roster linkage
    if "gsis_id" not in merged.columns:
        merged["gsis_id"] = None

    return merged


def build_combine_draft_profiles(
    combine_df: pd.DataFrame, draft_df: pd.DataFrame
) -> pd.DataFrame:
    """Orchestrate the full combine/draft profile pipeline.

    Steps: dedup_combine -> join_combine_draft -> compute_composite_scores
    -> compute_position_percentiles.

    Args:
        combine_df: Raw combine DataFrame from Bronze layer.
        draft_df: Raw draft picks DataFrame from Bronze layer.

    Returns:
        Final profiles DataFrame with composite scores and percentiles.
    """
    # Step 1: Dedup combine data
    combine_deduped = dedup_combine(combine_df)
    combine_deduped_count = len(combine_deduped)
    draft_count = len(draft_df)

    logger.info(
        "Input: %d combine rows (deduped from %d), %d draft rows",
        combine_deduped_count,
        len(combine_df),
        draft_count,
    )

    # Step 2: Join combine + draft
    merged = join_combine_draft(combine_deduped, draft_df)

    # Step 3: Compute composite scores
    merged = compute_composite_scores(merged)

    # Step 4: Compute position percentiles
    percentile_cols = ["speed_score", "bmi", "burst_score", "catch_radius"]
    merged = compute_position_percentiles(merged, percentile_cols)

    # Log match statistics
    has_combine = merged["ht"].notna() | merged["wt"].notna()
    has_draft = merged["pick"].notna() if "pick" in merged.columns else pd.Series(False, index=merged.index)
    matched = has_combine & has_draft
    combine_only = has_combine & ~has_draft
    draft_only = ~has_combine & has_draft

    logger.info(
        "Output: %d total rows | %d matched | %d combine-only | %d draft-only | %.1f%% match rate",
        len(merged),
        matched.sum(),
        combine_only.sum(),
        draft_only.sum(),
        (matched.sum() / len(merged) * 100) if len(merged) > 0 else 0,
    )

    if combine_only.sum() > 0:
        logger.warning(
            "%d combine-only players (no draft record)", combine_only.sum()
        )
    if draft_only.sum() > 0:
        logger.warning(
            "%d draft-only players (no combine record)", draft_only.sum()
        )

    # Assert no row explosion
    max_expected = combine_deduped_count + draft_count
    assert len(merged) <= max_expected, (
        f"Row explosion detected: {len(merged)} rows > {max_expected} "
        f"(combine_deduped={combine_deduped_count} + draft={draft_count})"
    )

    return merged
