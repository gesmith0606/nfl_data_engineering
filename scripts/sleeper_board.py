#!/usr/bin/env python3
"""UC1 sleeper board — deep players stepping into vacated opportunity.

The anchor-ON trial (.planning/GRAPH_USECASES_2026_07.md) showed the
vacated-opportunity signal's production value is OUTSIDE consensus
coverage: deep-bench players absorbing departed target/carry share whom
external rankings don't rank at all. This board surfaces exactly those —
late-round fliers and waiver-wire names for draft prep.

Ranks rostered fantasy players by ``vacancy_absorbed_share`` (UC1), flags
whether consensus ranks them, and shows the vacancy context (net team
vacancy, competition count). Default view: unranked-by-consensus players
only ("true sleepers").

Usage:
    python scripts/sleeper_board.py --season 2026
    python scripts/sleeper_board.py --season 2026 --position RB --top 25
    python scripts/sleeper_board.py --season 2026 --include-ranked
"""

import argparse
import logging
import os
import re
import sys
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_vacated_opportunity import (
    _read_bronze_parquet,
    build_vacated_opportunity_data,
    normalize_depth_chart,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ignore trace absorption — a 1% share is noise, not a sleeper story.
MIN_ABSORBED_SHARE = 0.02

# Depth-chart rank at/behind which a shot is a contingency stash, not a
# draftable sleeper (the 2026-08-29 board's top two shots were both RB4s).
DEPTH_CONTINGENCY_RANK = 3


def _name_key(name: str) -> str:
    """Normalize a player name for consensus matching (suffix-safe)."""
    n = re.sub(r"[^a-z ]", "", str(name).lower())
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", n).strip()


def _load_consensus() -> pd.DataFrame:
    """Consensus positional ranks from the external rankings caches."""
    try:
        from pathlib import Path

        from consensus_anchor import load_consensus_ranks

        return load_consensus_ranks(Path(BASE_DIR) / "data" / "external")
    except Exception as exc:
        logger.warning("Consensus ranks unavailable (%s) — all players shown", exc)
        return pd.DataFrame(columns=["name_key", "position", "consensus_pos_rank"])


def _load_player_names(season: int) -> pd.DataFrame:
    """player_id -> player_name from the latest roster parquet."""
    import glob

    pattern = os.path.join(
        BASE_DIR,
        "data",
        "bronze",
        "players",
        "rosters",
        f"season={season}",
        "*.parquet",
    )
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame(columns=["player_id", "player_name"])
    df = pd.read_parquet(files[-1])
    return df.drop_duplicates(subset=["player_id"])[["player_id", "player_name"]]


def _load_depth_ranks(season: int) -> pd.DataFrame:
    """player_id -> current depth-chart pos_rank from the LATEST snapshot.

    ``normalize_depth_chart`` keeps the earliest snapshot (the preseason
    baseline the vacancy features need); the board wants today's depth, so
    the frame is pre-filtered to the latest ``dt`` first. Fail-soft: any
    failure returns an empty frame and nobody gets demoted.

    Args:
        season: Target season.

    Returns:
        DataFrame with columns player_id, depth_pos_rank (may be empty).
    """
    empty = pd.DataFrame(columns=["player_id", "depth_pos_rank"])
    try:
        dc = _read_bronze_parquet("depth_charts", season)
        if dc.empty:
            return empty
        if "dt" in dc.columns:
            dc = dc.copy()
            dc["dt"] = pd.to_datetime(dc["dt"], errors="coerce")
            dc = dc[dc["dt"] == dc["dt"].max()]
        norm = normalize_depth_chart(dc)
        if norm.empty:
            return empty
        norm = norm.sort_values("pos_rank").drop_duplicates(subset=["player_id"])
        return norm.rename(columns={"pos_rank": "depth_pos_rank"})[
            ["player_id", "depth_pos_rank"]
        ]
    except Exception as exc:
        logger.warning("Depth charts unavailable (%s) — no depth demotion", exc)
        return empty


def build_sleeper_board(
    season: int,
    position: Optional[str] = None,
    include_ranked: bool = False,
    top: int = 30,
) -> pd.DataFrame:
    """Rank players by vacated-opportunity absorption (UC1).

    Args:
        season: Target season.
        position: Optional position filter (QB/RB/WR/TE).
        include_ranked: Include players consensus already ranks (default:
            unranked-only, the true-sleeper view).
        top: Number of rows to return.

    Returns:
        DataFrame with player, team, position, absorption/vacancy features,
        consensus_pos_rank (NaN = unranked by consensus), depth_pos_rank
        (NaN = not on a depth chart), and depth_note ("RB4 — contingency
        only" for players at depth rank >= DEPTH_CONTINGENCY_RANK, who sort
        below all startable players regardless of absorption).
    """
    feats = build_vacated_opportunity_data(season)
    if feats.empty:
        return pd.DataFrame()

    board = feats[feats["vacancy_absorbed_share"] >= MIN_ABSORBED_SHARE].copy()
    if position:
        board = board[board["position"] == position.upper()]

    names = _load_player_names(season)
    board = board.merge(names, on="player_id", how="left")
    board["player_name"] = board["player_name"].fillna(board["player_id"])
    board["name_key"] = board["player_name"].map(_name_key)

    cons = _load_consensus()
    if not cons.empty:
        board = board.merge(
            cons[["name_key", "position", "consensus_pos_rank"]],
            on=["name_key", "position"],
            how="left",
        )
    else:
        board["consensus_pos_rank"] = pd.NA

    if not include_ranked:
        board = board[board["consensus_pos_rank"].isna()]

    depth = _load_depth_ranks(season)
    if not depth.empty:
        board = board.merge(depth, on="player_id", how="left")
    else:
        board["depth_pos_rank"] = pd.NA

    # An RB4 absorbing vacated share is a handcuff stash, not a draftable
    # shot — sort contingency-depth players below every startable one no
    # matter their absorption. Missing depth data demotes nobody.
    depth_rank = pd.to_numeric(board["depth_pos_rank"], errors="coerce")
    contingency = (depth_rank >= DEPTH_CONTINGENCY_RANK).fillna(False)
    board["depth_note"] = ""
    board.loc[contingency, "depth_note"] = (
        board.loc[contingency, "position"].astype(str)
        + depth_rank[contingency].astype(int).astype(str)
        + " — contingency only"
    )
    board["_contingency"] = contingency
    board = board.sort_values(
        ["_contingency", "vacancy_absorbed_share"], ascending=[True, False]
    ).head(top)
    return board[
        [
            "player_name",
            "team",
            "position",
            "vacancy_absorbed_share",
            "net_target_vacancy",
            "net_carry_vacancy",
            "vacancy_competition_n",
            "consensus_pos_rank",
            "depth_pos_rank",
            "depth_note",
        ]
    ].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UC1 sleeper board — vacated-opportunity absorbers"
    )
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--position", choices=["QB", "RB", "WR", "TE"], default=None)
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument(
        "--include-ranked",
        action="store_true",
        help="Also show players consensus already ranks (default: sleepers only)",
    )
    args = parser.parse_args()

    board = build_sleeper_board(
        season=args.season,
        position=args.position,
        include_ranked=args.include_ranked,
        top=args.top,
    )
    if board.empty:
        print(f"No sleeper-board data for season {args.season}.")
        sys.exit(1)

    scope = args.position or "all positions"
    view = "all players" if args.include_ranked else "consensus-unranked only"
    print(
        f"\nUC1 SLEEPER BOARD — {args.season} ({scope}, {view})\n"
        f"{'player':<26}{'team':<5}{'pos':<4}{'absorbed':>9}"
        f"{'tgt_vac':>9}{'car_vac':>9}{'rivals':>7}{'cons_rank':>10}{'depth':>7}"
    )
    print("-" * 86)
    for _, r in board.iterrows():
        cons = (
            f"{int(r['consensus_pos_rank'])}"
            if pd.notna(r["consensus_pos_rank"])
            else "-"
        )
        depth = (
            f"{r['position']}{int(r['depth_pos_rank'])}"
            if pd.notna(r["depth_pos_rank"])
            else "-"
        )
        note = "  [contingency only]" if r["depth_note"] else ""
        print(
            f"{str(r['player_name'])[:25]:<26}{r['team']:<5}{r['position']:<4}"
            f"{r['vacancy_absorbed_share']:>9.3f}{r['net_target_vacancy']:>9.3f}"
            f"{r['net_carry_vacancy']:>9.3f}{r['vacancy_competition_n']:>7d}"
            f"{cons:>10}{depth:>7}{note}"
        )


if __name__ == "__main__":
    main()
