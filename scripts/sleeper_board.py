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

from graph_vacated_opportunity import build_vacated_opportunity_data

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ignore trace absorption — a 1% share is noise, not a sleeper story.
MIN_ABSORBED_SHARE = 0.02


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
        and consensus_pos_rank (NaN = unranked by consensus).
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

    board = board.sort_values("vacancy_absorbed_share", ascending=False).head(top)
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
        f"{'tgt_vac':>9}{'car_vac':>9}{'rivals':>7}{'cons_rank':>10}"
    )
    print("-" * 79)
    for _, r in board.iterrows():
        cons = (
            f"{int(r['consensus_pos_rank'])}"
            if pd.notna(r["consensus_pos_rank"])
            else "-"
        )
        print(
            f"{str(r['player_name'])[:25]:<26}{r['team']:<5}{r['position']:<4}"
            f"{r['vacancy_absorbed_share']:>9.3f}{r['net_target_vacancy']:>9.3f}"
            f"{r['net_carry_vacancy']:>9.3f}{r['vacancy_competition_n']:>7d}{cons:>10}"
        )


if __name__ == "__main__":
    main()
