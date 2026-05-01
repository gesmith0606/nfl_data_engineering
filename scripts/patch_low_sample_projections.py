"""Patch the latest preseason projections parquet with low-sample additions.

Reads the most recent ``projections_<scoring>_*.parquet`` for the target
season/week, identifies rostered fantasy players missing from it, synthesizes
projections via :func:`src.rookie_projection.project_low_sample_players`,
re-ranks the union, and writes a new timestamped parquet alongside the source.

This is the surgical alternative to a full preseason regen — used when
nfl-data-py's seasonal endpoint is unavailable for the target season (e.g.
during the offseason data-prep gap) and we don't want to regress
high-quality veteran projections by re-running with one season fewer.

Usage::

    python scripts/patch_low_sample_projections.py --season 2026 --scoring half_ppr
    python scripts/patch_low_sample_projections.py --season 2026 --scoring half_ppr --dry-run
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from projection_engine import add_floor_ceiling  # noqa: E402
from rookie_projection import (  # noqa: E402
    find_promoted_veterans,
    project_low_sample_players,
)
from utils import apply_sleeper_team_overrides  # noqa: E402

logger = logging.getLogger(__name__)

VORP_REPLACEMENT = {"QB": 13, "RB": 25, "WR": 30, "TE": 13, "K": 13}


def _latest(pattern: str) -> Optional[Path]:
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    return Path(files[-1]) if files else None


def _read_latest_roster(bronze_dir: Path) -> pd.DataFrame:
    """Latest roster snapshot, restricted to the most recent season.

    Pulls the file with the latest mtime, then filters to that file's
    most-recent season — handles the case where multiple seasons live
    under one file or under different files written at different times.
    """
    files = sorted(
        glob.glob(str(bronze_dir / "players/rosters/season=*/*.parquet")),
        key=os.path.getmtime,
    )
    if not files:
        return pd.DataFrame()
    # Walk back through files until we find one for the latest season number.
    latest_season = max(
        int(f.split("season=")[1].split("/")[0]) for f in files
    )
    for f in reversed(files):
        if f"season={latest_season}" in f:
            df = pd.read_parquet(f)
            if "season" in df.columns:
                df = df[df["season"] == latest_season].copy()
            return df
    return pd.read_parquet(files[-1])


def _augment_roster_with_draft_picks(
    roster: pd.DataFrame,
    draft_picks: pd.DataFrame,
    target_season: int,
) -> pd.DataFrame:
    """Append draft picks not already in the roster as synthetic ACT rows.

    nfl-data-py's seasonal-rosters endpoint lags the draft by weeks-to-months
    in the offseason (mid-2026 the 2026 roster doesn't yet contain the 2026
    rookie class even though the draft completed days earlier). Without this
    augmentation, every freshly-drafted rookie is silently absent from the
    projection output until rosters refresh.

    Each appended row carries:
      - player_id (gsis_id from draft_picks)
      - player_name, position, team (from draft_picks)
      - status="ACT", years_exp=0, rookie_year=target_season
      - draft_number = overall pick (drives the synthesizer's draft-capital
        override and the UDFA cap)

    Players already in the roster (by player_id) are left unchanged.
    """
    if draft_picks is None or draft_picks.empty:
        return roster

    existing_ids = (
        set(roster["player_id"].astype(str)) if "player_id" in roster.columns else set()
    )
    new_rows = []
    for _, dp in draft_picks.iterrows():
        # gsis_id is preferred (matches nflverse player_id) but is missing
        # for ~10% of fresh-draft picks until rosters refresh. Fall back to
        # pfr_player_id with a `pfr_` prefix so the synthesizer still gets a
        # unique identifier — those players just won't join cleanly with
        # downstream weekly stats until nflverse backfills the gsis_id.
        gsis = dp.get("gsis_id")
        gsis_s = str(gsis).strip() if gsis is not None else ""
        if gsis_s and gsis_s.lower() not in ("none", "nan"):
            pid = gsis_s
        else:
            pfr = dp.get("pfr_player_id")
            pfr_s = str(pfr).strip() if pfr is not None else ""
            if not pfr_s or pfr_s.lower() in ("none", "nan"):
                continue
            pid = f"pfr_{pfr_s}"
        if pid in existing_ids:
            continue
        team = str(dp.get("team", ""))
        pos = str(dp.get("position", "")).upper()
        if not team or not pos:
            continue
        name = str(dp.get("pfr_player_name") or dp.get("player_name") or "")
        if not name:
            continue
        try:
            pick = int(dp.get("pick", 0) or 0) or None
        except (TypeError, ValueError):
            pick = None
        new_rows.append(
            {
                "player_id": pid,
                "player_name": name,
                "team": team,
                "position": pos,
                "status": "ACT",
                "years_exp": 0,
                "rookie_year": float(target_season),
                "draft_number": pick,
                "depth_chart_position": pos,
                "jersey_number": 99.0,
                "draft_club": team,
            }
        )
    if not new_rows:
        return roster
    addn = pd.DataFrame(new_rows)
    # Backfill any source columns the synthetic rows don't have.
    for col in roster.columns:
        if col not in addn.columns:
            addn[col] = pd.NA
    augmented = pd.concat([roster, addn[roster.columns.tolist() + [
        c for c in addn.columns if c not in roster.columns
    ]]], ignore_index=True, sort=False)
    logger.info(
        "Augmented roster with %d draft picks not yet in nfl-data-py rosters",
        len(addn),
    )
    return augmented


def _read_latest_draft_picks(bronze_dir: Path, season: int) -> pd.DataFrame:
    """Latest draft_picks bronze for the season."""
    pat = str(bronze_dir / f"draft_picks/season={season}/*.parquet")
    files = sorted(glob.glob(pat), key=os.path.getmtime)
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_latest_prospect_features(silver_dir: Path, season: int, scoring: str) -> pd.DataFrame:
    """Latest CFBD-derived prospect feature parquet for the target season."""
    pat = str(
        silver_dir
        / "college"
        / "prospect_features"
        / f"season={season}"
        / f"{scoring}_*.parquet"
    )
    files = sorted(glob.glob(pat), key=os.path.getmtime)
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_latest_depth_charts(bronze_dir: Path) -> pd.DataFrame:
    """Latest depth_charts snapshot. Returns the entire bronze parquet — the
    synthesizer narrows to fantasy positions and latest dt per (team, pos)."""
    files = sorted(
        glob.glob(str(bronze_dir / "depth_charts/season=*/*.parquet")),
        key=os.path.getmtime,
    )
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_weekly(bronze_dir: Path) -> pd.DataFrame:
    """Concatenate all weekly bronze across seasons (bounded — only stat cols
    we use are loaded). Tries both ``player_weekly/`` and ``players/weekly/``
    to handle the v1.x → v2.x bronze path move."""
    patterns = [
        str(bronze_dir / "player_weekly/season=*/week=*/*.parquet"),
        str(bronze_dir / "player_weekly/season=*/*.parquet"),
        str(bronze_dir / "players/weekly/season=*/*.parquet"),
        str(bronze_dir / "players/weekly/season=*/week=*/*.parquet"),
    ]
    files: list = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    files = sorted(set(files))
    if not files:
        return pd.DataFrame()
    keep_cols = {
        "player_id",
        "season",
        "week",
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "carries",
        "receiving_yards",
        "receiving_tds",
        "receptions",
        "targets",
        "receiving_air_yards",  # alias rename below
    }
    chunks = []
    for f in files:
        df = pd.read_parquet(f)
        cols = [c for c in df.columns if c in keep_cols]
        if not cols:
            continue
        chunks.append(df[cols])
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks, ignore_index=True)
    if "receiving_air_yards" in out.columns and "air_yards" not in out.columns:
        out = out.rename(columns={"receiving_air_yards": "air_yards"})
    return out


def _re_rank(proj: pd.DataFrame, pts_col: str = "projected_season_points") -> pd.DataFrame:
    """Recompute VORP-based ``overall_rank`` and within-position ``position_rank``."""
    proj = proj.copy()
    proj["vorp"] = np.nan
    for pos, rep in VORP_REPLACEMENT.items():
        mask = proj["position"] == pos
        sorted_pts = proj.loc[mask, pts_col].sort_values(ascending=False)
        if len(sorted_pts) >= rep:
            replacement = sorted_pts.iloc[rep - 1]
        elif len(sorted_pts) > 0:
            replacement = sorted_pts.iloc[-1]
        else:
            replacement = 0.0
        proj.loc[mask, "vorp"] = (proj.loc[mask, pts_col] - replacement).round(1)

    proj["overall_rank"] = (
        proj["vorp"].rank(ascending=False, method="first").astype(int)
    )
    proj["position_rank"] = (
        proj.groupby("position")[pts_col]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return proj.sort_values("overall_rank").reset_index(drop=True)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--scoring", choices=["ppr", "half_ppr", "standard"], default="half_ppr")
    p.add_argument("--week", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    gold_dir = PROJECT_ROOT / "data" / "gold"
    bronze_dir = PROJECT_ROOT / "data" / "bronze"

    week_dir = gold_dir / "projections" / f"season={args.season}" / f"week={args.week}"
    pattern = str(week_dir / f"projections_{args.scoring}_*.parquet")
    canonical = _latest(pattern)
    if canonical is None:
        logger.error("No source projections found at %s", pattern)
        return 1

    logger.info("Source: %s", canonical)
    proj = pd.read_parquet(canonical)
    logger.info("Source rows: %d (cols: %s)", len(proj), list(proj.columns))

    pts_col = (
        "projected_season_points"
        if "projected_season_points" in proj.columns
        else "projected_points"
    )
    team_col = "recent_team" if "recent_team" in proj.columns else "team"

    # Apply Sleeper rosters_live override before any team-based dedup logic
    # below — players who moved teams in the offseason (e.g. Malik Willis
    # GB→MIA) need their team corrected so the lineup builder doesn't fall
    # back to the depth-chart-mismatch guard ("--").
    live_pattern = str(
        bronze_dir / "players/rosters_live/season=*/*.parquet"
    )
    live_files = sorted(glob.glob(live_pattern))
    live_roster = (
        pd.read_parquet(live_files[-1]) if live_files else pd.DataFrame()
    )
    # Track whether the Sleeper override actually mutated rows; if so, the
    # bail-early branch below still needs to persist the corrected file.
    pre_override_team = proj[team_col].astype(str).copy()
    proj = apply_sleeper_team_overrides(
        proj,
        live_roster,
        team_col=team_col,
        name_col="player_name",
        logger=logger,
    )
    team_overrides_applied = bool(
        (pre_override_team != proj[team_col].astype(str)).any()
    )

    roster = _read_latest_roster(bronze_dir)
    if roster.empty:
        logger.error("No roster bronze found — cannot identify silent drops")
        return 1
    logger.info("Roster rows: %d (season=%s)", len(roster), roster["season"].max())

    # Augment with the freshly-drafted rookie class. nfl-data-py's seasonal
    # roster lags the draft, so freshly-drafted players (Mendoza, Simpson,
    # Beck in 2026) won't appear in the projection output without this
    # synthetic merge. The draft_picks bronze carries gsis_id, team, pick,
    # and position — everything the synthesizer needs.
    draft_picks = _read_latest_draft_picks(bronze_dir, args.season)
    if not draft_picks.empty:
        logger.info(
            "Draft picks bronze: %d rows for season %d", len(draft_picks), args.season
        )
        roster = _augment_roster_with_draft_picks(roster, draft_picks, args.season)

    weekly = _read_weekly(bronze_dir)
    logger.info("Weekly rows: %d", len(weekly))

    depth_charts = _read_latest_depth_charts(bronze_dir)
    if not depth_charts.empty:
        logger.info(
            "Depth_charts rows: %d (latest dt: %s)",
            len(depth_charts),
            depth_charts["dt"].max() if "dt" in depth_charts.columns else "n/a",
        )

    already = set(proj["player_id"].dropna().astype(str))

    # Compute (team, position) pairs where the upstream pipeline already
    # produced a "viable starter" — defined as a player whose
    # projected_points clears a position-specific floor that backups never
    # exceed. This blocks the synthesizer from minting a second starter at
    # the same team-position when depth_charts has a feed hole (e.g. Tua
    # absent from MIA's 2026-03-14 snapshot).
    starter_floors = {"QB": 200.0, "RB": 100.0, "WR": 100.0, "TE": 80.0, "K": 100.0}
    upstream = proj.copy()
    if "projected_season_points" in upstream.columns and "projected_points" not in upstream.columns:
        upstream = upstream.rename(columns={"projected_season_points": "projected_points"})
    if "recent_team" in upstream.columns and "team" not in upstream.columns:
        upstream = upstream.rename(columns={"recent_team": "team"})

    team_pos_starter_already: set = set()
    for pos, floor in starter_floors.items():
        pos_rows = upstream[
            (upstream["position"] == pos) & (upstream["projected_points"] >= floor)
        ]
        for team in pos_rows["team"].dropna().unique():
            team_pos_starter_already.add((str(team), pos))

    logger.info(
        "Upstream already covers a starter at %d (team, position) pairs",
        len(team_pos_starter_already),
    )

    # ------------------------------------------------------------------
    # Promoted-veteran detection: identify veterans whose depth-chart role
    # outpaces their upstream projection tier. Players like Malik Willis
    # (GB-backup projection 53.8 → MIA QB1 per ESPN's latest depth chart)
    # would otherwise keep their backup-tier number under their new
    # starter slot. The detection helper lives in src/rookie_projection.py
    # so it can be unit-tested in isolation.
    # ------------------------------------------------------------------
    promoted_player_ids = find_promoted_veterans(
        upstream,
        depth_charts,
        starter_floors=starter_floors,
        already_projected_player_ids=already,
    )

    # Cache the stale rows BEFORE dropping them — needed below so a
    # silent failure to re-synthesize doesn't leave the player completely
    # missing from the output.
    stale_promoted_rows = proj[
        proj["player_id"].astype(str).isin(promoted_player_ids)
    ].copy()

    if promoted_player_ids:
        sample = (
            stale_promoted_rows.head(8)[
                ["player_id", "player_name", team_col, pts_col]
            ].to_dict("records")
        )
        logger.info(
            "Promoting %d veteran(s) to starter role for re-projection "
            "(e.g. %s)",
            len(promoted_player_ids),
            sample,
        )
        # Remove stale rows so the synthesizer's new starter projections
        # replace them after the concat.
        proj = proj[
            ~proj["player_id"].astype(str).isin(promoted_player_ids)
        ].copy()
        already = already - promoted_player_ids

    silver_dir = PROJECT_ROOT / "data" / "silver"
    college_features = _read_latest_prospect_features(silver_dir, args.season, args.scoring)
    if not college_features.empty:
        logger.info(
            "Prospect features: %d rows (cohort) — applying college-prior blend",
            len(college_features),
        )

    additions = project_low_sample_players(
        roster_df=roster,
        weekly_df=weekly if not weekly.empty else None,
        already_projected_player_ids=already,
        target_season=args.season,
        scoring_format=args.scoring,
        depth_charts_df=depth_charts if not depth_charts.empty else None,
        team_pos_starter_already_projected=team_pos_starter_already,
        college_features_df=college_features if not college_features.empty else None,
        force_reproject_player_ids=promoted_player_ids,
    )
    logger.info("Synthesized %d low-sample projection rows", len(additions))

    # Synthesizer-internal columns are normally backfilled onto `proj`
    # only when `additions` is non-empty (see backfill block below).
    # Hoist that step here so the restore-stale-row fallback path can't
    # produce a frame that's missing `is_low_sample_projection` /
    # `low_sample_role` / `low_sample_n_games`. Without this, downstream
    # `add_floor_ceiling` would silently skip the widened-variance band
    # for restored rows because the gating column doesn't exist.
    for col in ("is_low_sample_projection", "low_sample_role", "low_sample_n_games"):
        if col not in proj.columns:
            proj[col] = False if col == "is_low_sample_projection" else None

    # Post-synthesis fallback: if a player was flagged for promotion but
    # the synthesizer didn't emit a row for them (e.g. they're missing
    # from the roster bronze, or filtered out by an earlier guard), we
    # would silently drop them from the final output. Restore the stale
    # row so the lineup page at least keeps showing something for that
    # slot rather than a gap.
    if promoted_player_ids and not stale_promoted_rows.empty:
        synthesized_ids = (
            set(additions["player_id"].astype(str))
            if not additions.empty
            else set()
        )
        missing = {p for p in promoted_player_ids if p not in synthesized_ids}
        if missing:
            restore = stale_promoted_rows[
                stale_promoted_rows["player_id"].astype(str).isin(missing)
            ].copy()
            # Stale rows pre-date the synthesizer-internal columns; align
            # them to the post-hoist `proj` schema so the concat is clean.
            for col in (
                "is_low_sample_projection",
                "low_sample_role",
                "low_sample_n_games",
            ):
                if col not in restore.columns:
                    restore[col] = False if col == "is_low_sample_projection" else None
            logger.warning(
                "Promotion fallback: %d veteran(s) flagged for re-projection "
                "but absent from synthesizer output; restoring stale rows so "
                "they don't disappear from the lineup. ids=%s",
                len(missing),
                sorted(missing),
            )
            proj = pd.concat([proj, restore], ignore_index=True, sort=False)

    if additions.empty:
        if not team_overrides_applied:
            logger.info(
                "Nothing to add — every rostered fantasy player is already projected"
            )
            return 0
        logger.info(
            "No rookies to synthesize, but Sleeper team overrides were "
            "applied; writing refreshed parquet so the lineup builder picks "
            "up the corrected team assignments."
        )
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest = week_dir / f"projections_{args.scoring}_{ts}.parquet"
        if args.dry_run:
            logger.info(
                "DRY-RUN — would write %d rows (team-overrides only) → %s",
                len(proj),
                dest,
            )
            return 0
        proj.to_parquet(dest, index=False)
        logger.info(
            "Wrote %d rows (0 added, %d existing, team overrides applied) → %s",
            len(proj),
            len(proj),
            dest,
        )
        return 0

    # The synthesizer's output column is `projected_season_points`; the source
    # parquet may use either `projected_points` or `projected_season_points`.
    # Normalize so the concat aligns on a single points column.
    if pts_col == "projected_points" and "projected_season_points" in additions.columns:
        additions = additions.rename(columns={"projected_season_points": "projected_points"})

    if team_col == "team" and "recent_team" in additions.columns:
        additions = additions.rename(columns={"recent_team": "team"})

    # Backfill any source columns the additions don't have so the schema unions cleanly.
    for col in proj.columns:
        if col not in additions.columns:
            additions[col] = np.nan
    # Synthesizer-internal cols are guaranteed to exist on `proj` by the
    # hoisted backfill above; nothing further to do here.

    merged = pd.concat(
        [proj, additions[proj.columns]], ignore_index=True, sort=False
    )

    # Re-rank including the new rows.
    merged = _re_rank(merged, pts_col=pts_col)

    # Apply floor/ceiling on the union (heuristic fallback path produces 35-45%
    # band by position; for low-sample rows we widen by 10pp so the UI can show
    # the higher uncertainty). Wider band signals "low confidence" without
    # breaking the existing schema.
    if "projected_points" not in merged.columns:
        # add_floor_ceiling expects projected_points; provide alias for the pass.
        merged["projected_points"] = merged[pts_col]
    merged = add_floor_ceiling(merged)
    if "projected_points" in merged.columns and pts_col == "projected_season_points":
        # Drop the alias we added for the floor/ceiling helper.
        merged = merged.drop(columns=["projected_points"])
    if "is_low_sample_projection" in merged.columns:
        low_mask = merged["is_low_sample_projection"].fillna(False).astype(bool)
        merged.loc[low_mask, "projected_floor"] = (
            merged.loc[low_mask, pts_col] * 0.50
        ).clip(lower=0).round(2)
        merged.loc[low_mask, "projected_ceiling"] = (
            merged.loc[low_mask, pts_col] * 1.50
        ).round(2)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = week_dir / f"projections_{args.scoring}_{ts}.parquet"

    if args.dry_run:
        logger.info("DRY-RUN — would write %d rows → %s", len(merged), dest)
        # Show a sample of the new rows
        sample = merged[merged.get("is_low_sample_projection", False) == True].head(10)
        if not sample.empty:
            cols = [c for c in [
                "player_name", "position", team_col, "position_rank", "overall_rank",
                pts_col, "projected_floor", "projected_ceiling", "low_sample_role",
            ] if c in sample.columns]
            print(sample[cols].to_string(index=False))
        return 0

    merged.to_parquet(dest, index=False)
    logger.info("Wrote %d rows (%d added, %d existing) → %s",
                len(merged), len(additions), len(proj), dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
