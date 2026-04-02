#!/usr/bin/env python3
"""Ingest Bronze data into Neo4j graph database.

Creates :Player, :Team, and :Game nodes plus temporal edges from Bronze
rosters, schedules, and snap counts. All writes use MERGE for idempotent
re-runs.

Usage::

    python scripts/graph_ingestion.py --seasons 2020 2021 2022 2023 2024

Requires a running Neo4j instance (see docker-compose.yml).
"""

import argparse
import glob
import logging
import os
import sys
from typing import List

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_db import GraphDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")

# Batch size for UNWIND operations
BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Data readers
# ---------------------------------------------------------------------------


def _read_bronze(subdir: str, season: int) -> pd.DataFrame:
    """Read latest Bronze parquet for a subdirectory and season.

    Args:
        subdir: Path under data/bronze/ (e.g. 'players/rosters').
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if no files exist.
    """
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        # Also check for week-level partitioning
        pattern_w = os.path.join(
            BRONZE_DIR, subdir, f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            dfs = [pd.read_parquet(f) for f in files_w]
            return pd.concat(dfs, ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# Node ingestion
# ---------------------------------------------------------------------------


def ingest_teams(gdb: GraphDB, seasons: List[int]) -> int:
    """Create (:Team) nodes from Bronze schedules.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of seasons to process.

    Returns:
        Number of teams created/merged.
    """
    teams = set()
    for season in seasons:
        sched = _read_bronze("schedules", season)
        if sched.empty:
            continue
        if "home_team" in sched.columns:
            teams.update(sched["home_team"].dropna().unique())
        if "away_team" in sched.columns:
            teams.update(sched["away_team"].dropna().unique())

    if not teams:
        logger.warning("No team data found")
        return 0

    team_list = [{"abbr": t} for t in sorted(teams)]
    gdb.run_write(
        "UNWIND $teams AS t " "MERGE (team:Team {abbr: t.abbr})",
        {"teams": team_list},
    )
    logger.info("Merged %d Team nodes", len(team_list))
    return len(team_list)


def ingest_players(gdb: GraphDB, seasons: List[int]) -> int:
    """Create (:Player) nodes from Bronze rosters.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of seasons to process.

    Returns:
        Number of players created/merged.
    """
    all_players = {}  # gsis_id -> player info (latest wins)
    for season in seasons:
        rosters = _read_bronze("players/rosters", season)
        if rosters.empty:
            continue

        # Use player_id as gsis_id
        id_col = "player_id" if "player_id" in rosters.columns else "gsis_id"
        for _, row in rosters.iterrows():
            gsis_id = str(row.get(id_col, ""))
            if not gsis_id or gsis_id == "nan":
                continue
            all_players[gsis_id] = {
                "gsis_id": gsis_id,
                "name": str(row.get("player_name", "")),
                "position": str(row.get("position", "")),
                "height": str(row.get("height", "")),
                "weight": int(row["weight"]) if pd.notna(row.get("weight")) else 0,
            }

    if not all_players:
        logger.warning("No player data found")
        return 0

    # Batch ingest
    player_list = list(all_players.values())
    for i in range(0, len(player_list), BATCH_SIZE):
        batch = player_list[i : i + BATCH_SIZE]
        gdb.run_write(
            "UNWIND $players AS p "
            "MERGE (player:Player {gsis_id: p.gsis_id}) "
            "SET player.name = p.name, "
            "    player.position = p.position, "
            "    player.height = p.height, "
            "    player.weight = p.weight",
            {"players": batch},
        )

    logger.info("Merged %d Player nodes", len(player_list))
    return len(player_list)


def ingest_games(gdb: GraphDB, seasons: List[int]) -> int:
    """Create (:Game) nodes from Bronze schedules.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of seasons to process.

    Returns:
        Number of games created/merged.
    """
    all_games = []
    for season in seasons:
        sched = _read_bronze("schedules", season)
        if sched.empty:
            continue

        for _, row in sched.iterrows():
            game_id = str(row.get("game_id", ""))
            if not game_id or game_id == "nan":
                continue
            all_games.append(
                {
                    "game_id": game_id,
                    "season": int(row.get("season", season)),
                    "week": int(row.get("week", 0)),
                    "home_team": str(row.get("home_team", "")),
                    "away_team": str(row.get("away_team", "")),
                    "game_type": str(row.get("game_type", "REG")),
                }
            )

    if not all_games:
        logger.warning("No game data found")
        return 0

    for i in range(0, len(all_games), BATCH_SIZE):
        batch = all_games[i : i + BATCH_SIZE]
        gdb.run_write(
            "UNWIND $games AS g "
            "MERGE (game:Game {game_id: g.game_id}) "
            "SET game.season = g.season, "
            "    game.week = g.week, "
            "    game.home_team = g.home_team, "
            "    game.away_team = g.away_team, "
            "    game.game_type = g.game_type",
            {"games": batch},
        )

    logger.info("Merged %d Game nodes", len(all_games))
    return len(all_games)


# ---------------------------------------------------------------------------
# Edge ingestion
# ---------------------------------------------------------------------------


def ingest_plays_for_edges(gdb: GraphDB, seasons: List[int]) -> int:
    """Create (:Player)-[:PLAYS_FOR]->(:Team) edges from rosters.

    Temporal properties: season, week_start, week_end.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of seasons to process.

    Returns:
        Number of edges created/merged.
    """
    edges = []
    for season in seasons:
        rosters = _read_bronze("players/rosters", season)
        if rosters.empty:
            continue

        id_col = "player_id" if "player_id" in rosters.columns else "gsis_id"

        # Group by player and team to get week ranges
        if "week" in rosters.columns:
            grouped = (
                rosters.groupby([id_col, "team"])
                .agg(week_start=("week", "min"), week_end=("week", "max"))
                .reset_index()
            )
        else:
            # Seasonal roster — assume full season
            grouped = rosters[[id_col, "team"]].drop_duplicates()
            grouped["week_start"] = 1
            grouped["week_end"] = 18

        for _, row in grouped.iterrows():
            gsis_id = str(row[id_col])
            if not gsis_id or gsis_id == "nan":
                continue
            edges.append(
                {
                    "gsis_id": gsis_id,
                    "team_abbr": str(row["team"]),
                    "season": int(season),
                    "week_start": int(row["week_start"]),
                    "week_end": int(row["week_end"]),
                }
            )

    if not edges:
        return 0

    for i in range(0, len(edges), BATCH_SIZE):
        batch = edges[i : i + BATCH_SIZE]
        gdb.run_write(
            "UNWIND $edges AS e "
            "MATCH (p:Player {gsis_id: e.gsis_id}) "
            "MATCH (t:Team {abbr: e.team_abbr}) "
            "MERGE (p)-[r:PLAYS_FOR {season: e.season}]->(t) "
            "SET r.week_start = e.week_start, "
            "    r.week_end = e.week_end",
            {"edges": batch},
        )

    logger.info("Merged %d PLAYS_FOR edges", len(edges))
    return len(edges)


def ingest_played_in_edges(gdb: GraphDB, seasons: List[int]) -> int:
    """Create (:Player)-[:PLAYED_IN]->(:Game) edges from snap counts.

    Args:
        gdb: Connected GraphDB instance.
        seasons: List of seasons to process.

    Returns:
        Number of edges created/merged.
    """
    edges = []
    for season in seasons:
        snaps = _read_bronze("players/snaps", season)
        if snaps.empty:
            continue

        # snap_counts uses 'player' (name, not ID) and 'pfr_player_id'
        # Link via game_id and team
        for _, row in snaps.iterrows():
            game_id = str(row.get("game_id", ""))
            pfr_id = str(row.get("pfr_player_id", ""))
            if not game_id or game_id == "nan":
                continue

            edges.append(
                {
                    "game_id": game_id,
                    "pfr_player_id": pfr_id,
                    "player_name": str(row.get("player", "")),
                    "team": str(row.get("team", "")),
                    "offense_snaps": int(row.get("offense_snaps", 0)),
                    "offense_pct": float(row.get("offense_pct", 0.0)),
                }
            )

    if not edges:
        return 0

    # Since snap_counts uses pfr_player_id (not gsis_id), we match by name+team
    for i in range(0, len(edges), BATCH_SIZE):
        batch = edges[i : i + BATCH_SIZE]
        gdb.run_write(
            "UNWIND $edges AS e "
            "MATCH (g:Game {game_id: e.game_id}) "
            "MATCH (p:Player) WHERE p.name = e.player_name "
            "MERGE (p)-[r:PLAYED_IN]->(g) "
            "SET r.offense_snaps = e.offense_snaps, "
            "    r.offense_pct = e.offense_pct",
            {"edges": batch},
        )

    logger.info("Merged %d PLAYED_IN edges", len(edges))
    return len(edges)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for graph ingestion."""
    parser = argparse.ArgumentParser(description="Ingest NFL data into Neo4j")
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        required=True,
        help="Season years to ingest (e.g., 2020 2021 2022)",
    )
    args = parser.parse_args()

    with GraphDB() as gdb:
        if not gdb.is_connected:
            logger.error(
                "Cannot connect to Neo4j. " "Start it with: docker compose up -d"
            )
            sys.exit(1)

        gdb.ensure_schema()

        logger.info("Ingesting seasons: %s", args.seasons)

        # Nodes first, then edges
        n_teams = ingest_teams(gdb, args.seasons)
        n_players = ingest_players(gdb, args.seasons)
        n_games = ingest_games(gdb, args.seasons)
        n_plays_for = ingest_plays_for_edges(gdb, args.seasons)
        n_played_in = ingest_played_in_edges(gdb, args.seasons)

        logger.info(
            "Ingestion complete: %d teams, %d players, %d games, "
            "%d PLAYS_FOR edges, %d PLAYED_IN edges",
            n_teams,
            n_players,
            n_games,
            n_plays_for,
            n_played_in,
        )


if __name__ == "__main__":
    main()
