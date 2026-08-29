#!/usr/bin/env python3
"""Generate an honest pre-kickoff Week-1 board from our preseason projections.

The weekly projection engine cannot run before the season starts (no in-season
weekly data exists, and it has no prior-season trailing seed — see
``.claude`` memory ``project_week1_projections_cold_start``). Meanwhile the API
serves the preseason board for a Week-1 request but passes SEASON TOTALS through
as the "weekly" number, which is misleading. This script produces a real
per-week view from our model output:

    wk1_points = (projected_season_points / GAMES) * matchup_tilt

``matchup_tilt`` reuses ``player_analytics.compute_defensive_strength`` on the
prior season (2025) — the same lagged defense-vs-position signal the in-season
engine uses — mapped onto each team's real Week-1 opponent from the schedule.
The overall rank is VORP (points over positional replacement) so the board is
draft-usable rather than QB-stacked; the positional rank is raw Week-1 points.

Output (per scoring format), consumed by ``external_rankings_service`` (the
Week-1 rankings comparison) and downstream tooling:

    data/gold/projections/season=YYYY/week=WW/week1_board_{scoring}_derived.parquet
    data/gold/projections/season=YYYY/week=WW/week1_board_{scoring}_derived.csv

Usage:
    python scripts/generate_week1_board.py --season 2026 --week 1
    python scripts/generate_week1_board.py --season 2026 --week 1 --scoring ppr
"""

import argparse
import glob
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_optimizer import DEFAULT_REPLACEMENT_RANKS  # noqa: E402
from player_analytics import compute_defensive_strength  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("generate_week1_board")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAMES = 17.0
# Matchup sensitivity per position — softer than the in-season engine's
# [0.75, 1.25] because this is a single cross-season point estimate.
SENS = {"QB": 0.35, "RB": 0.55, "WR": 0.50, "TE": 0.45}
MATCHUP_CLIP = (0.88, 1.12)
POSITIONS = ["QB", "RB", "WR", "TE", "K"]


def _latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _week1_opponent_map(season: int) -> Dict[str, str]:
    """team -> its Week-1 opponent, from the real schedule."""
    sched_f = _latest(
        str(PROJECT_ROOT / f"data/bronze/schedules/season={season}/*.parquet")
    )
    if sched_f is None:
        raise FileNotFoundError(f"No schedule for season {season}")
    sched = pd.read_parquet(sched_f)
    w1 = sched[sched["week"] == 1]
    opp: Dict[str, str] = {}
    for _, g in w1.iterrows():
        opp[g["home_team"]] = g["away_team"]
        opp[g["away_team"]] = g["home_team"]
    return opp


def _defensive_strength(
    prior_season: int, scoring: str
) -> Dict[Tuple[str, str], float]:
    """End-of-``prior_season`` trailing D-vs-position ratio per (team, position)."""
    wk_f = _latest(
        str(
            PROJECT_ROOT / f"data/bronze/players/weekly/season={prior_season}/*.parquet"
        )
    )
    sched_f = _latest(
        str(PROJECT_ROOT / f"data/bronze/schedules/season={prior_season}/*.parquet")
    )
    if wk_f is None or sched_f is None:
        logger.warning(
            "No %s weekly/schedule data — matchup tilt will be neutral", prior_season
        )
        return {}
    ds = compute_defensive_strength(
        pd.read_parquet(wk_f), pd.read_parquet(sched_f), scoring_format=scoring
    )
    if ds.empty:
        return {}
    ds = ds.sort_values("week").groupby(["team", "position"], as_index=False).last()
    return ds.set_index(["team", "position"])["ratio"].to_dict()


def build_week1_board(season: int, week: int, scoring: str) -> pd.DataFrame:
    """Derive the Week-1 board for one scoring format."""
    board_f = _latest(
        str(
            PROJECT_ROOT
            / f"data/gold/projections/preseason/season={season}/season_proj_{scoring}_*.parquet"
        )
    )
    if board_f is None:
        raise FileNotFoundError(
            f"No preseason board for season={season} scoring={scoring}. "
            f"Run generate_projections.py --preseason first."
        )
    logger.info("Preseason board: %s", os.path.basename(board_f))
    b = pd.read_parquet(board_f)
    b = b[b["position"].isin(POSITIONS)].copy()

    opp = _week1_opponent_map(season)
    strength = _defensive_strength(season - 1, scoring)

    def matchup(team: str, pos: str) -> Tuple[float, Optional[str]]:
        o = opp.get(team)
        ratio = strength.get((o, pos)) if o is not None else None
        if ratio is None or pd.isna(ratio):
            return 1.0, o
        m = 1.0 + SENS.get(pos, 0.45) * (ratio - 1.0)
        return float(min(max(m, MATCHUP_CLIP[0]), MATCHUP_CLIP[1])), o

    b["base_pg"] = b["projected_season_points"] / GAMES
    res = b.apply(lambda r: matchup(r["recent_team"], r["position"]), axis=1)
    b["matchup_mult"] = [x[0] for x in res]
    b["wk1_opp"] = [x[1] for x in res]
    b["wk1_points"] = (b["base_pg"] * b["matchup_mult"]).round(2)

    b["wk1_pos_rank"] = (
        b.groupby("position")["wk1_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    # VORP overall: points over the replacement-rank player's Week-1 points.
    repl_level: Dict[str, float] = {}
    for pos, rr in DEFAULT_REPLACEMENT_RANKS.items():
        pool = b[b["position"] == pos].sort_values("wk1_points", ascending=False)
        if len(pool) >= rr:
            repl_level[pos] = float(pool.iloc[rr - 1]["wk1_points"])
        elif len(pool):
            repl_level[pos] = float(pool["wk1_points"].min())
        else:
            repl_level[pos] = 0.0
    b["wk1_vorp"] = (b["wk1_points"] - b["position"].map(repl_level).fillna(0.0)).round(
        2
    )

    b = b.sort_values("wk1_vorp", ascending=False).reset_index(drop=True)
    b["wk1_overall_rank"] = b.index + 1
    return b


def write_board(b: pd.DataFrame, season: int, week: int, scoring: str) -> Path:
    outdir = PROJECT_ROOT / f"data/gold/projections/season={season}/week={week}"
    outdir.mkdir(parents=True, exist_ok=True)
    cols = [
        "player_id",
        "player_name",
        "position",
        "recent_team",
        "wk1_opp",
        "wk1_points",
        "wk1_vorp",
        "matchup_mult",
        "base_pg",
        "projected_season_points",
        "wk1_overall_rank",
        "wk1_pos_rank",
        "overall_rank",
    ]
    out = b[[c for c in cols if c in b.columns]]
    pq = outdir / f"week1_board_{scoring}_derived.parquet"
    out.to_parquet(pq, index=False)
    out.to_csv(outdir / f"week1_board_{scoring}_derived.csv", index=False)
    return pq


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--week", type=int, default=1)
    p.add_argument(
        "--scoring",
        default="all",
        help="ppr / half_ppr / standard / all (default: all)",
    )
    args = p.parse_args(argv)

    formats = (
        ["ppr", "half_ppr", "standard"] if args.scoring == "all" else [args.scoring]
    )
    for fmt in formats:
        b = build_week1_board(args.season, args.week, fmt)
        pq = write_board(b, args.season, args.week, fmt)
        covered = b["wk1_opp"].notna().mean()
        top = b.head(3)["player_name"].tolist()
        logger.info(
            "[%s] wrote %d players -> %s (matchup tilt on %.0f%%, top: %s)",
            fmt,
            len(b),
            pq.relative_to(PROJECT_ROOT),
            covered * 100,
            ", ".join(top),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
