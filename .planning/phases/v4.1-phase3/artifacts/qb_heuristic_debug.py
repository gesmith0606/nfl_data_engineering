#!/usr/bin/env python3
"""Debug: why is the QB production heuristic producing ~0 points?

The E1 result showed:
    QB mean_heuristic = 0.03 pts (vs mean_actual = 14.13)
    QB mean_residual = +14.10

This means the production heuristic used for residual training is broken
for QB. This script narrows down exactly where the zeroing happens.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import PLAYER_DATA_SEASONS  # noqa: E402
from player_feature_engineering import assemble_multiyear_player_features  # noqa: E402
from projection_engine import (  # noqa: E402
    POSITION_STAT_PROFILE,
    PROJECTION_CEILING_SHRINKAGE,
    _matchup_factor,
    _usage_multiplier,
    _weighted_baseline,
)
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402
from unified_evaluation import (  # noqa: E402
    build_opp_rankings,
    compute_actual_fantasy_points,
    compute_production_heuristic,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("qb_heur_debug")

SCORING = "half_ppr"

log.info("Loading data…")
ALL = assemble_multiyear_player_features(PLAYER_DATA_SEASONS)
OPP = build_opp_rankings(PLAYER_DATA_SEASONS)
qb = ALL[ALL["position"] == "QB"].copy()
log.info("%d QB rows", len(qb))

# What does the production heuristic return?
heur = compute_production_heuristic(qb, "QB", OPP, SCORING)
log.info("Heuristic stats: mean=%.3f median=%.3f max=%.3f frac_zero=%.3f",
         heur.mean(), heur.median(), heur.max(), (heur == 0).mean())

# Step by step reproduction
stat_cols = POSITION_STAT_PROFILE.get("QB", [])
log.info("QB stat_cols = %s", stat_cols)

# Check which rolling columns exist
for stat in stat_cols:
    for suffix in ("roll3", "roll6", "std"):
        col = f"{stat}_{suffix}"
        present = col in qb.columns
        nan_pct = qb[col].isna().mean() if present else 1.0
        nonzero = (qb[col].fillna(0) > 0).mean() if present else 0.0
        log.info("  %s: present=%s nan_rate=%.3f nonzero_rate=%.3f",
                 col, present, nan_pct, nonzero)

# Compute step by step
work = qb.copy().drop(columns=["opp_rank"], errors="ignore")
usage = _usage_multiplier(work, "QB")
matchup = _matchup_factor(work, OPP, "QB")
log.info("usage_mult mean=%.3f matchup mean=%.3f", usage.mean(), matchup.mean())

proj_cols = {}
for stat in stat_cols:
    baseline = _weighted_baseline(work, stat)
    proj_val = (baseline * usage * matchup).round(2)
    log.info("  proj_%s: mean=%.3f median=%.3f max=%.3f nonzero=%.3f",
             stat, proj_val.mean(), proj_val.median(), proj_val.max(),
             (proj_val > 0).mean())
    proj_cols[f"proj_{stat}"] = proj_val

work = work.assign(**proj_cols)

# Now rename and score
rename_map = {f"proj_{s}": s for s in stat_cols}
orig_cols = [v for v in rename_map.values() if v in work.columns]
log.info("Will drop orig cols %s (these conflict with proj_ rename)", orig_cols)
scoring_input = work.drop(columns=orig_cols, errors="ignore")
scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)

# Inspect what columns went into scoring
for c in stat_cols:
    if c in scoring_input.columns:
        s = scoring_input[c]
        log.info("  scoring_input[%s]: mean=%.3f nonzero=%.3f",
                 c, s.mean(), (s > 0).mean())

# Check scoring calc directly on a few rows BEFORE calculate_fantasy_points
sample = scoring_input[stat_cols].head(10)
log.info("First 10 QB rows going into scoring:\n%s", sample.to_string())

scored = calculate_fantasy_points_df(
    scoring_input, scoring_format=SCORING, output_col="projected_points"
)
log.info("After calculate_fantasy_points_df:")
log.info("  projected_points mean=%.3f nonzero=%.3f",
         scored["projected_points"].mean(),
         (scored["projected_points"] > 0).mean())
log.info("  First 10 rows with inputs+output:")
show_cols = stat_cols + ["projected_points"]
show_cols = [c for c in show_cols if c in scored.columns]
log.info("\n%s", scored[show_cols].head(10).to_string())

# Also check a single known-good QB for comparison: passing yards should be ~200+
pat_idx = qb[qb["player_name"].str.contains("Mahomes", na=False)].index[:5] if "player_name" in qb.columns else []
if len(pat_idx) > 0:
    log.info("\nMahomes rows (raw features):")
    show = ["season", "week", "passing_yards_roll3", "passing_yards_roll6",
            "passing_yards_std", "passing_tds_roll3", "passing_tds_std",
            "passing_yards", "passing_tds"]
    show = [c for c in show if c in qb.columns]
    log.info("\n%s", qb.loc[pat_idx, show].to_string())

# Check whether raw `passing_yards` column exists and compare to rolling
if "passing_yards" in qb.columns:
    log.info("passing_yards raw col: mean=%.3f median=%.3f nonzero=%.3f",
             qb["passing_yards"].mean(), qb["passing_yards"].median(),
             (qb["passing_yards"] > 0).mean())

# Critical check: does calculate_fantasy_points_df maybe need a specific column?
log.info("\nAll columns in scoring_input matching stat names:")
for c in scoring_input.columns:
    if any(k in c for k in ["passing", "rushing", "interception"]):
        log.info("  %s", c)
