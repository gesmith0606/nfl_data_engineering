"""Build prospect feature parquet for the upcoming season.

Joins:
  - Historical players (Silver `players/historical/*.parquet`)  — has draft
    capital, combine measurables, and per-position college info.
  - Their NFL season-1 fantasy points (from `data/bronze/players/weekly/`
    aggregated per `(player_id, season=draft_year)`).
  - Aggregated college stats (Bronze `college_player_stats/*` flattened to
    one row per player_name with per-game and career totals).

Then runs ``build_prospect_profile()`` for the prospect cohort (defaults to
the rookies whose ``draft_year == target_season - 1`` — they're the year-1
group whose projection most needs a prior). Writes the result to
``data/silver/college/prospect_features/season=<target_season>/<scoring>_<ts>.parquet``.

Usage::

    python scripts/build_prospect_features.py --target-season 2026 --scoring half_ppr
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

from college_prospect_features import build_prospect_profile  # noqa: E402
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402

logger = logging.getLogger(__name__)


def _read_latest(pattern: str) -> Optional[pd.DataFrame]:
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    if not files:
        return None
    return pd.read_parquet(files[-1])


def _read_concat(pattern: str) -> pd.DataFrame:
    """Concatenate all parquets matching the pattern."""
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _compute_season1_pts(
    historical: pd.DataFrame,
    weekly: pd.DataFrame,
    scoring: str,
) -> pd.DataFrame:
    """Add ``nfl_season1_pts`` and ``nfl_season1_starter_games`` to historical.

    - ``nfl_season1_pts`` — fantasy points across all weeks of the player's
      draft_year (so the prior reflects rookie-year output).
    - ``nfl_season1_starter_games`` — count of weeks in draft_year with
      "meaningful volume" by position. Used downstream to filter the comp
      pool to rookies who actually played a starter's role, not backups
      whose low totals reflect lack of opportunity (Jalen Hurts year-1
      sitting behind Wentz, etc.).

    Position-specific volume thresholds:
      QB: pass attempts >= 10 in the week (true start, not garbage relief)
      RB: carries >= 5 OR targets >= 3
      WR/TE: targets >= 3
      K: any week with FG attempts (skill: kickers always play full games when active)
    """
    if historical.empty or weekly.empty:
        historical = historical.copy()
        historical["nfl_season1_pts"] = np.nan
        historical["nfl_season1_starter_games"] = 0
        return historical

    w = calculate_fantasy_points_df(weekly, scoring_format=scoring, output_col="_pts")

    # Total points by (player_id, season)
    grouped = (
        w.groupby(["player_id", "season"], as_index=False)["_pts"].sum()
        .rename(columns={"_pts": "season_pts", "season": "draft_year"})
    )

    # Per-week starter flag based on position-aware volume.
    # We need position from historical to apply position-specific thresholds.
    h = historical.copy()
    if "player_id" not in h.columns and "gsis_id" in h.columns:
        h["player_id"] = h["gsis_id"]

    # Pull position into weekly via roster join (best signal). Fallback: use
    # historical['pos'] for the (player_id, season) match.
    pos_col = "pos" if "pos" in h.columns else ("position" if "position" in h.columns else None)
    pos_lookup: dict = {}
    if pos_col is not None:
        pos_lookup = dict(zip(h["player_id"].astype(str), h[pos_col].astype(str)))

    def _is_starter_row(row) -> bool:
        pid = str(row.get("player_id", ""))
        pos = pos_lookup.get(pid, "")
        if pos == "QB":
            return float(row.get("attempts", 0) or 0) >= 10
        if pos == "RB":
            carries = float(row.get("carries", 0) or 0)
            targets = float(row.get("targets", 0) or 0)
            return carries >= 5 or targets >= 3
        if pos in ("WR", "TE"):
            return float(row.get("targets", 0) or 0) >= 3
        if pos == "K":
            return float(row.get("fg_made", 0) or 0) > 0 or float(row.get("fg_att", 0) or 0) > 0
        return False

    w_for_starter = w.copy()
    # Vectorize the threshold logic for speed.
    w_for_starter["_pos"] = w_for_starter["player_id"].astype(str).map(pos_lookup).fillna("")
    qb_mask = w_for_starter["_pos"].eq("QB") & (w_for_starter.get("attempts", 0).fillna(0) >= 10)
    rb_mask = w_for_starter["_pos"].eq("RB") & (
        (w_for_starter.get("carries", 0).fillna(0) >= 5)
        | (w_for_starter.get("targets", 0).fillna(0) >= 3)
    )
    wr_te_mask = w_for_starter["_pos"].isin(["WR", "TE"]) & (
        w_for_starter.get("targets", 0).fillna(0) >= 3
    )
    fg_made = w_for_starter.get("fg_made", pd.Series(0, index=w_for_starter.index)).fillna(0)
    fg_att = w_for_starter.get("fg_att", pd.Series(0, index=w_for_starter.index)).fillna(0)
    k_mask = w_for_starter["_pos"].eq("K") & ((fg_made > 0) | (fg_att > 0))
    w_for_starter["_starter_week"] = (qb_mask | rb_mask | wr_te_mask | k_mask).astype(int)

    starter_games = (
        w_for_starter.groupby(["player_id", "season"], as_index=False)["_starter_week"]
        .sum()
        .rename(columns={"_starter_week": "starter_games", "season": "draft_year"})
    )

    h["draft_year"] = h["draft_year"].astype("Int64")
    grouped["draft_year"] = grouped["draft_year"].astype("Int64")
    starter_games["draft_year"] = starter_games["draft_year"].astype("Int64")
    merged = h.merge(grouped, on=["player_id", "draft_year"], how="left")
    merged = merged.merge(starter_games, on=["player_id", "draft_year"], how="left")
    merged["nfl_season1_pts"] = merged["season_pts"]
    merged["nfl_season1_starter_games"] = merged["starter_games"].fillna(0).astype(int)
    merged = merged.drop(columns=["season_pts", "starter_games"], errors="ignore")
    return merged


def _aggregate_college_stats(stats_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse multi-season player_stats rows into one row per player.

    Sums across seasons by ``athleteId`` (or by name+team fallback). Adds
    per-game rates if ``games`` is present. The output is what
    ``compute_prospect_similarity`` expects in ``college_stats_df``.
    """
    if stats_df.empty:
        return stats_df

    df = stats_df.copy()

    # Identify name + position-ish columns we need.
    name_col = next((c for c in ("athleteName", "player", "name", "player_name") if c in df.columns), None)
    if name_col is None:
        return pd.DataFrame()
    if name_col != "player_name":
        df = df.rename(columns={name_col: "player_name"})

    if "team" not in df.columns:
        team_col = next((c for c in ("school", "college_team") if c in df.columns), None)
        if team_col:
            df = df.rename(columns={team_col: "team"})

    # Ensure conference column exists.
    if "conference" not in df.columns:
        df["conference"] = ""

    # Numeric columns to sum across seasons (everything that looks like a stat).
    numeric = df.select_dtypes(include="number").columns.tolist()
    # Exclude season/year/id-ish columns from summing.
    drop_from_sum = {"season", "year", "athleteId", "playerId", "id"}
    sum_cols = [c for c in numeric if c not in drop_from_sum]

    # Group by name (best signal we have without a player_id).
    agg = (
        df.groupby("player_name", as_index=False)[sum_cols]
        .sum()
    )
    # Carry latest team/conference per player (most-recent season row).
    if "season" in df.columns:
        latest_meta = (
            df.sort_values("season")
            .drop_duplicates("player_name", keep="last")[
                ["player_name"] + [c for c in ("team", "conference") if c in df.columns]
            ]
        )
        agg = agg.merge(latest_meta, on="player_name", how="left")

    return agg


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--target-season", type=int, required=True,
                   help="Upcoming NFL season being projected (e.g. 2026)")
    p.add_argument("--scoring", choices=["ppr", "half_ppr", "standard"],
                   default="half_ppr")
    p.add_argument("--prospect-draft-years", type=int, nargs="+", default=None,
                   help="Override prospect cohort. Default = target_season - 1 only "
                        "(i.e. the year-1 rookies whose projections need a prior most). "
                        "Pass two values to widen, e.g. --prospect-draft-years 2024 2025")
    p.add_argument("--k-comps", type=int, default=5)
    p.add_argument(
        "--min-starter-games",
        type=int,
        default=10,
        help="Minimum count of starter-volume weeks in draft_year for a "
             "historical player to be in the comp pool. 0 disables the "
             "filter (back-compat). Default 10 — addresses the 'Hurts/Lock "
             "sat behind a vet year-1' suppression bias.",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    historical = _read_latest(str(PROJECT_ROOT / "data/silver/players/historical/*.parquet"))
    if historical is None or historical.empty:
        logger.error("No historical Silver parquet found")
        return 1
    logger.info("Historical rows: %d", len(historical))

    weekly = _read_concat(str(PROJECT_ROOT / "data/bronze/players/weekly/season=*/*.parquet"))
    if weekly.empty:
        weekly = _read_concat(str(PROJECT_ROOT / "data/bronze/player_weekly/season=*/week=*/*.parquet"))
    logger.info("Weekly rows: %d", len(weekly))

    historical = _compute_season1_pts(historical, weekly, scoring=args.scoring)
    n_with_outcome = int(historical["nfl_season1_pts"].notna().sum())
    logger.info("Historical players with nfl_season1_pts: %d / %d", n_with_outcome, len(historical))

    college_stats = _read_concat(
        str(PROJECT_ROOT / "data/bronze/college_player_stats/season=*/*.parquet")
    )
    logger.info("College stats raw rows: %d", len(college_stats))
    college_stats = _aggregate_college_stats(college_stats)
    logger.info("College stats per-player rows: %d", len(college_stats))

    # Determine prospect cohort.
    prospect_years = args.prospect_draft_years or [args.target_season - 1]
    logger.info("Prospect cohort: draft_year in %s", prospect_years)
    prospects = historical[historical["draft_year"].isin(prospect_years)].copy()

    # Filter to fantasy positions.
    fantasy_pos = {"QB", "RB", "WR", "TE", "K"}
    if "pos" in prospects.columns:
        prospects = prospects[prospects["pos"].isin(fantasy_pos)].copy()
    elif "position" in prospects.columns:
        prospects = prospects[prospects["position"].isin(fantasy_pos)].copy()
    logger.info("Fantasy-position prospects: %d", len(prospects))

    # Normalize column names build_prospect_profile expects.
    if "pos" in prospects.columns and "position" not in prospects.columns:
        prospects = prospects.rename(columns={"pos": "position"})
    if "school" in prospects.columns and "college_team" not in prospects.columns:
        prospects["college_team"] = prospects["school"]
    if "team" in prospects.columns and "recent_team" not in prospects.columns:
        prospects = prospects.rename(columns={"team": "recent_team"})

    # Mirror the same renames on the comp-pool for consistent feature vectors.
    hist_pool = historical[~historical["draft_year"].isin(prospect_years)].copy()
    if "pos" in hist_pool.columns and "position" not in hist_pool.columns:
        hist_pool = hist_pool.rename(columns={"pos": "position"})
    if hist_pool.empty:
        logger.error("Empty historical comp pool — cannot build prospect profiles")
        return 1
    if "position" in hist_pool.columns:
        hist_pool = hist_pool[hist_pool["position"].isin(fantasy_pos)].copy()

    # Restrict comp pool to historicals with NFL outcomes so that the k=5
    # nearest neighbors actually carry comp_median signal — without this,
    # comp_rows.dropna() can yield n_comps=0 even when the feature distance
    # is small. The cohort needs an outcome to be useful for similarity.
    pool_before = len(hist_pool)
    hist_pool = hist_pool[hist_pool["nfl_season1_pts"].notna()].copy()
    logger.info(
        "Comp pool: %d (filtered from %d to those with nfl_season1_pts outcomes)",
        len(hist_pool),
        pool_before,
    )

    # Restrict to historicals who actually started as rookies. Filters out
    # backups whose low totals reflect lack of opportunity (e.g. Jalen Hurts
    # year-1 sat behind Wentz with 28 attempts; Drew Lock's small sample).
    # The current rookie cohort being projected is asymmetrically composed
    # of day-1 starters (high-pick QBs / RBs) — comparing them to non-starters
    # under-projects them systemically.
    if args.min_starter_games > 0 and "nfl_season1_starter_games" in hist_pool.columns:
        before_filter = len(hist_pool)
        hist_pool = hist_pool[
            hist_pool["nfl_season1_starter_games"] >= args.min_starter_games
        ].copy()
        logger.info(
            "Starter-games filter (>=%d weeks): comp pool %d → %d",
            args.min_starter_games,
            before_filter,
            len(hist_pool),
        )

    if prospects.empty:
        logger.error("No fantasy-position prospects in cohort %s", prospect_years)
        return 1

    # Reset indexes — compute_prospect_similarity uses positional masks against
    # the feature matrix, which assumes 0..N-1 indexes on both inputs.
    profile = build_prospect_profile(
        prospect_df=prospects.reset_index(drop=True),
        historical_df=hist_pool.reset_index(drop=True),
        college_stats_df=college_stats if not college_stats.empty else None,
        nfl_career_df=hist_pool.reset_index(drop=True),
        k_comps=args.k_comps,
    )
    logger.info("Profile rows: %d (cols added: %s)",
                len(profile),
                [c for c in profile.columns if c.startswith("prospect_") or c == "scheme_familiarity_score"])

    if args.dry_run:
        cols = [c for c in [
            "player_name", "position", "recent_team", "college_team",
            "draft_ovr", "prospect_comp_median",
            "prospect_comp_floor", "prospect_comp_ceiling",
            "scheme_familiarity_score", "n_comps",
        ] if c in profile.columns]
        print(profile[cols].head(20).to_string(index=False))
        return 0

    out_dir = PROJECT_ROOT / "data" / "silver" / "college" / "prospect_features" / f"season={args.target_season}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"{args.scoring}_{ts}.parquet"
    profile.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows → %s", len(profile), out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
