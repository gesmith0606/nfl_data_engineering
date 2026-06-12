#!/usr/bin/env python3
"""Signal probe for defense-side trailing WR/TE allowance features (ELITE-2.3).

Computes partial correlation of each trailing defense-unit feature with
next-week half-PPR points, controlling for trailing target share and
trailing points, on matched WR/TE player-weeks 2022-2024 w3-18 (cons>=5
not required here — raw signal probe).

Usage:
    python scripts/probe_matchup_signal.py
"""

import glob
import logging
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

WR_DEF_TRAIL_COLS = [
    "wr_def_trail_yds_per_tgt",
    "wr_def_trail_yds_per_tgt_outside",
    "wr_def_trail_yds_per_tgt_slot",
    "wr_def_trail_comp_rate",
    "wr_def_trail_td_rate",
    "wr_def_trail_cb_count_per_play",
]

TE_DEF_TRAIL_COLS = [
    "te_def_trail_yds_per_tgt",
    "te_def_trail_comp_rate",
    "te_def_trail_td_rate",
    "te_def_trail_lb_coverage_share",
    "te_def_trail_cb_coverage_share",
]

CONTROL_COLS = {
    "WR": ["target_share_roll3", "fantasy_points_ppr_roll3"],
    "TE": ["target_share_roll3", "fantasy_points_ppr_roll3"],
}

PROBE_SEASONS = [2022, 2023, 2024]
PROBE_WEEKS_MIN = 3
PROBE_WEEKS_MAX = 18


def _load_bronze_multi(subdir: str, seasons: list) -> pd.DataFrame:
    dfs = []
    for s in seasons:
        fs = sorted(glob.glob(os.path.join(BRONZE_DIR, subdir, f"season={s}", "*.parquet")))
        if fs:
            dfs.append(pd.read_parquet(fs[-1]))
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _load_trailing_features(seasons: list, prefix: str) -> pd.DataFrame:
    dfs = []
    for s in seasons:
        pattern = os.path.join(
            SILVER_DIR, "graph_features", f"season={s}", f"{prefix}_*.parquet"
        )
        fs = sorted(glob.glob(pattern))
        if not fs:
            logger.warning("No %s parquet for season=%d — skipping", prefix, s)
            continue
        df = pd.read_parquet(fs[-1])
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


def _partial_corr(x: pd.Series, y: pd.Series, controls: pd.DataFrame) -> float:
    """Partial Pearson correlation of x~y after residualizing on controls.

    Returns NaN if insufficient non-null overlap.
    """
    combined = pd.concat([x, y, controls], axis=1).dropna()
    if len(combined) < 50:
        return np.nan

    x_vals = combined.iloc[:, 0].values
    y_vals = combined.iloc[:, 1].values
    ctrl = combined.iloc[:, 2:].values

    from numpy.linalg import lstsq

    def residualize(v, c):
        c_aug = np.column_stack([np.ones(len(c)), c])
        coef, _, _, _ = lstsq(c_aug, v, rcond=None)
        return v - c_aug @ coef

    x_res = residualize(x_vals, ctrl)
    y_res = residualize(y_vals, ctrl)

    r, p = stats.pearsonr(x_res, y_res)
    return r


def run_probe() -> None:
    """Run signal probes and print results."""
    logger.info("Loading player-weekly for %s", PROBE_SEASONS)
    pw = _load_bronze_multi("players/weekly", PROBE_SEASONS)
    if pw.empty:
        logger.error("No player-weekly data — exiting")
        return

    # Compute actual half-PPR points from the weekly file
    if "fantasy_points" not in pw.columns:
        logger.error("fantasy_points column missing from player_weekly")
        return

    # half-PPR = fantasy_points (standard) + 0.5 * receptions
    # but player_weekly has fantasy_points (standard) and fantasy_points_ppr
    # half-PPR = 0.5*(PPR + standard)
    if "fantasy_points_ppr" in pw.columns:
        pw["actual_half_ppr"] = (pw["fantasy_points"] + pw["fantasy_points_ppr"]) / 2
    else:
        pw["actual_half_ppr"] = pw["fantasy_points"]

    pw = pw[PROBE_SEASONS[0] <= pw["season"]][pw["season"] <= PROBE_SEASONS[-1]].copy()
    pw = pw[(pw["week"] >= PROBE_WEEKS_MIN) & (pw["week"] <= PROBE_WEEKS_MAX)]

    logger.info("Player-weekly rows: %d", len(pw))

    # Load trailing features
    logger.info("Loading WR trailing features...")
    wr_trail = _load_trailing_features(PROBE_SEASONS, "graph_wr_def_trailing")
    logger.info("Loading TE trailing features...")
    te_trail = _load_trailing_features(PROBE_SEASONS, "graph_te_def_trailing")

    if wr_trail.empty:
        logger.warning("No WR trailing features found — check if compute_graph_features ran")
    if te_trail.empty:
        logger.warning("No TE trailing features found — check if compute_graph_features ran")

    # Load Silver player usage for controls (target_share_roll3, fantasy_points_ppr_roll3)
    logger.info("Loading Silver usage data for controls...")
    usage_dfs = []
    for s in PROBE_SEASONS:
        fs = sorted(
            glob.glob(
                os.path.join(SILVER_DIR, "players", "usage", f"season={s}", "*.parquet")
            )
        )
        if fs:
            usage_dfs.append(pd.read_parquet(fs[-1]))
    usage = pd.concat(usage_dfs, ignore_index=True) if usage_dfs else pd.DataFrame()
    logger.info("Silver usage rows: %d", len(usage))

    def probe_position(
        pos: str,
        trail_df: pd.DataFrame,
        trail_cols: list,
    ) -> None:
        """Run probe for a single position."""
        print(f"\n{'='*70}")
        print(f"  Signal Probe: {pos} defense-side trailing features")
        print(f"  Control vars: trailing target_share + trailing fantasy_pts")
        print(f"  Probe set: 2022-24 w3-18 matched player-weeks")
        print(f"{'='*70}")

        if trail_df.empty:
            print(f"  SKIP — no trailing features available")
            return

        # Get position player-weeks
        pos_pw = pw[pw["position"] == pos][
            ["player_id", "season", "week", "actual_half_ppr"]
        ].copy()
        pos_pw["player_id"] = pos_pw["player_id"].astype(str)

        # Merge trailing features
        trail_df["player_id"] = trail_df["player_id"].astype(str)
        merged = pos_pw.merge(
            trail_df[["player_id", "season", "week"] + trail_cols],
            on=["player_id", "season", "week"],
            how="left",
        )
        logger.info("%s: %d pos_pw rows, %d merged rows", pos, len(pos_pw), len(merged))

        # Merge controls from Silver usage
        ctrl_cols = CONTROL_COLS[pos]
        if not usage.empty:
            usage_sub = usage[
                ["player_id", "season", "week"] + [c for c in ctrl_cols if c in usage.columns]
            ].copy()
            usage_sub["player_id"] = usage_sub["player_id"].astype(str)
            merged = merged.merge(usage_sub, on=["player_id", "season", "week"], how="left")

        # Fall back to rolling on pw if silver unavailable
        if "fantasy_points_ppr_roll3" not in merged.columns and "actual_half_ppr" in merged.columns:
            merged = merged.sort_values(["player_id", "season", "week"])
            merged["fantasy_points_ppr_roll3"] = merged.groupby(["player_id", "season"])[
                "actual_half_ppr"
            ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

        if "target_share_roll3" not in merged.columns:
            merged["target_share_roll3"] = np.nan

        available_ctrl = [c for c in ctrl_cols if c in merged.columns and merged[c].notna().sum() > 100]
        ctrl_df = merged[available_ctrl] if available_ctrl else pd.DataFrame(index=merged.index)

        print(
            f"\n  {'Feature':<42} {'partial_r':>9} {'n_obs':>7} {'null%':>6}"
        )
        print(f"  {'-'*65}")

        has_signal = False
        for col in trail_cols:
            if col not in merged.columns:
                print(f"  {col:<42} {'MISSING':>9}")
                continue

            feature = merged[col]
            target = merged["actual_half_ppr"]
            null_rate = 100 * feature.isna().mean()

            if ctrl_df.empty:
                r_val = feature.corr(target)
                n_obs = feature.notna() & target.notna()
                n_obs_count = n_obs.sum()
            else:
                r_val = _partial_corr(feature, target, ctrl_df)
                combined = pd.concat([feature, target, ctrl_df], axis=1).dropna()
                n_obs_count = len(combined)

            flag = " <-- SIGNAL" if abs(r_val) >= 0.03 else ""
            if abs(r_val) >= 0.03:
                has_signal = True
            r_str = f"{r_val:+.4f}" if not np.isnan(r_val) else "   NaN"
            print(f"  {col:<42} {r_str:>9} {n_obs_count:>7} {null_rate:>5.1f}%{flag}")

        print(f"\n  {'SIGNAL FOUND: YES' if has_signal else 'SIGNAL FOUND: NO'} (threshold |r| >= 0.03)")

    probe_position("WR", wr_trail.copy() if not wr_trail.empty else pd.DataFrame(), WR_DEF_TRAIL_COLS)
    probe_position("TE", te_trail.copy() if not te_trail.empty else pd.DataFrame(), TE_DEF_TRAIL_COLS)

    print("\n")


if __name__ == "__main__":
    run_probe()
