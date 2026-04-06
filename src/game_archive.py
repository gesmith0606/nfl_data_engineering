"""
Historical Game Archive

Provides functions for querying game results, player fantasy stats per game,
season leaders, and player game logs from Bronze data.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

# Project root (src/ is one level down)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"

# Bronze data paths
_SCHEDULES_DIR = _DATA_DIR / "bronze" / "schedules"
_GAMES_DIR = _DATA_DIR / "bronze" / "games"
_PLAYER_WEEKLY_DIR = _DATA_DIR / "bronze" / "players" / "weekly"

# Earliest season with player weekly data
_PLAYER_STATS_MIN_SEASON = 2016


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most-recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _load_schedules(season: int) -> pd.DataFrame:
    """Load schedule/game data for a season from Bronze.

    Tries ``schedules/`` first, then falls back to ``games/``.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with schedule rows for the season.

    Raises:
        FileNotFoundError: If no data exists for the season.
    """
    for base_dir in (_SCHEDULES_DIR, _GAMES_DIR):
        season_dir = base_dir / f"season={season}"
        if season_dir.exists():
            pq = _latest_parquet(season_dir)
            if pq is not None:
                df = pd.read_parquet(pq)
                # Filter to regular season games only
                if "game_type" in df.columns:
                    df = df[df["game_type"] == "REG"]
                return df

    raise FileNotFoundError(
        f"No schedule data found for season={season}. "
        f"Checked {_SCHEDULES_DIR} and {_GAMES_DIR}."
    )


def _load_player_weekly(season: int) -> pd.DataFrame:
    """Load player weekly stats for a season from Bronze.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with player weekly stats.

    Raises:
        FileNotFoundError: If no data exists for the season.
    """
    season_dir = _PLAYER_WEEKLY_DIR / f"season={season}"
    if not season_dir.exists():
        raise FileNotFoundError(
            f"No player weekly data for season={season}. "
            f"Player stats are available from {_PLAYER_STATS_MIN_SEASON} onward."
        )

    pq = _latest_parquet(season_dir)
    if pq is None:
        raise FileNotFoundError(f"No parquet files in {season_dir}")

    return pd.read_parquet(pq)


def _build_game_id(row: pd.Series) -> str:
    """Build a game_id from season, week, away_team, home_team if missing."""
    return f"{row['season']}_{row['week']:02d}_{row['away_team']}_{row['home_team']}"


def _compute_fumbles_lost(df: pd.DataFrame) -> pd.DataFrame:
    """Compute total fumbles_lost from component columns."""
    df = df.copy()
    fumble_cols = [
        "sack_fumbles_lost",
        "rushing_fumbles_lost",
        "receiving_fumbles_lost",
    ]
    existing = [c for c in fumble_cols if c in df.columns]
    if existing:
        df["fumbles_lost"] = df[existing].fillna(0).sum(axis=1)
    elif "fumbles_lost" not in df.columns:
        df["fumbles_lost"] = 0
    return df


def _compute_two_pt(df: pd.DataFrame) -> pd.DataFrame:
    """Compute total two_pt_conversions from component columns."""
    df = df.copy()
    two_pt_cols = [
        "passing_2pt_conversions",
        "rushing_2pt_conversions",
        "receiving_2pt_conversions",
    ]
    existing = [c for c in two_pt_cols if c in df.columns]
    if existing:
        df["two_pt_conversions"] = df[existing].fillna(0).sum(axis=1)
    elif "two_pt_conversions" not in df.columns:
        df["two_pt_conversions"] = 0
    return df


def get_game_results(season: int, week: Optional[int] = None) -> pd.DataFrame:
    """Get all game results for a season (or specific week).

    Loads from Bronze schedules/games data.

    Args:
        season: NFL season year (1999-2026).
        week: Optional week filter (1-18).

    Returns:
        DataFrame with columns: game_id, season, week, home_team, away_team,
        home_score, away_score, winner, point_spread_result, total_points,
        game_date, game_time.
    """
    df = _load_schedules(season)

    if week is not None:
        df = df[df["week"] == week]

    if df.empty:
        return pd.DataFrame(
            columns=[
                "game_id",
                "season",
                "week",
                "home_team",
                "away_team",
                "home_score",
                "away_score",
                "winner",
                "point_spread_result",
                "total_points",
                "game_date",
                "game_time",
            ]
        )

    # Ensure game_id exists
    if "game_id" not in df.columns:
        df["game_id"] = df.apply(_build_game_id, axis=1)

    # Compute derived columns
    df["home_score"] = (
        pd.to_numeric(df.get("home_score"), errors="coerce").fillna(0).astype(int)
    )
    df["away_score"] = (
        pd.to_numeric(df.get("away_score"), errors="coerce").fillna(0).astype(int)
    )
    df["total_points"] = df["home_score"] + df["away_score"]
    df["point_spread_result"] = df["home_score"] - df["away_score"]

    def _winner(row: pd.Series) -> str:
        if row["home_score"] > row["away_score"]:
            return row["home_team"]
        elif row["away_score"] > row["home_score"]:
            return row["away_team"]
        return "TIE"

    df["winner"] = df.apply(_winner, axis=1)
    df["game_date"] = df.get("gameday", pd.Series(dtype="object"))
    df["game_time"] = df.get("gametime", pd.Series(dtype="object"))

    result_cols = [
        "game_id",
        "season",
        "week",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "winner",
        "point_spread_result",
        "total_points",
        "game_date",
        "game_time",
    ]
    out = df[[c for c in result_cols if c in df.columns]].copy()
    out = out.sort_values(["week", "game_id"]).reset_index(drop=True)
    return out


def get_game_player_stats(
    season: int,
    week: int,
    game_id: Optional[str] = None,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Get every player's fantasy points for games in a given week.

    Loads from Bronze player_weekly, computes fantasy points via the
    scoring calculator.

    Args:
        season: NFL season year.
        week: Week number (1-18).
        game_id: Optional game_id to filter to a single game.
        scoring_format: One of 'ppr', 'half_ppr', 'standard'.

    Returns:
        DataFrame with columns: game_id, player_id, player_name, team,
        position, fantasy_points, passing_yards, passing_tds, rushing_yards,
        rushing_tds, receptions, receiving_yards, receiving_tds, targets,
        carries. Sorted by fantasy_points descending within each game.

    Raises:
        FileNotFoundError: If player weekly data is not available.
    """
    if season < _PLAYER_STATS_MIN_SEASON:
        raise FileNotFoundError(
            f"Player stats not available before {_PLAYER_STATS_MIN_SEASON}."
        )

    pw = _load_player_weekly(season)
    pw = pw[pw["week"] == week].copy()

    if pw.empty:
        return pd.DataFrame()

    # Compute fumbles_lost and two_pt_conversions
    pw = _compute_fumbles_lost(pw)
    pw = _compute_two_pt(pw)

    # Calculate fantasy points
    pw = calculate_fantasy_points_df(pw, scoring_format, output_col="fantasy_points")

    # Build game_id by joining with schedule data
    try:
        sched = _load_schedules(season)
        sched = sched[sched["week"] == week]
        if "game_id" not in sched.columns:
            sched["game_id"] = sched.apply(_build_game_id, axis=1)

        # Create team -> game_id mapping for both home and away
        home_map = sched.set_index("home_team")["game_id"].to_dict()
        away_map = sched.set_index("away_team")["game_id"].to_dict()

        team_col = "recent_team" if "recent_team" in pw.columns else "team"
        pw["game_id"] = pw[team_col].map(
            lambda t: home_map.get(t, away_map.get(t, "UNKNOWN"))
        )
    except FileNotFoundError:
        pw["game_id"] = "UNKNOWN"

    if game_id is not None:
        pw = pw[pw["game_id"] == game_id]

    # Rename recent_team -> team if needed
    if "recent_team" in pw.columns and "team" not in pw.columns:
        pw = pw.rename(columns={"recent_team": "team"})
    elif "recent_team" in pw.columns:
        pw["team"] = pw["recent_team"]

    # Select and order output columns
    out_cols = [
        "game_id",
        "player_id",
        "player_name",
        "team",
        "position",
        "fantasy_points",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "targets",
        "carries",
    ]
    for c in out_cols:
        if c not in pw.columns:
            pw[c] = np.nan

    result = pw[out_cols].copy()
    result = result.sort_values(
        ["game_id", "fantasy_points"], ascending=[True, False]
    ).reset_index(drop=True)

    return result


def get_game_detail(
    season: int,
    week: int,
    game_id: str,
    scoring_format: str = "half_ppr",
) -> Dict:
    """Get full game detail: score, both team rosters with fantasy points.

    Args:
        season: NFL season year.
        week: Week number.
        game_id: Game identifier (e.g. '2024_01_BAL_KC').
        scoring_format: Scoring format for fantasy points.

    Returns:
        Dict with keys:
        - game_info: dict with home/away team, scores, date
        - home_players: list of player stat dicts, sorted by points
        - away_players: list of player stat dicts, sorted by points
        - top_performers: top 5 scorers across both teams
    """
    # Get game result
    games = get_game_results(season, week)
    game_row = games[games["game_id"] == game_id]
    if game_row.empty:
        raise ValueError(f"Game {game_id} not found in season={season} week={week}")

    game_info = game_row.iloc[0].to_dict()
    home_team = game_info["home_team"]
    away_team = game_info["away_team"]

    # Get player stats (may not be available for older seasons)
    home_players: List[Dict] = []
    away_players: List[Dict] = []
    top_performers: List[Dict] = []

    if season >= _PLAYER_STATS_MIN_SEASON:
        try:
            stats = get_game_player_stats(season, week, game_id, scoring_format)
            if not stats.empty:
                home_df = stats[stats["team"] == home_team].sort_values(
                    "fantasy_points", ascending=False
                )
                away_df = stats[stats["team"] == away_team].sort_values(
                    "fantasy_points", ascending=False
                )
                home_players = home_df.to_dict("records")
                away_players = away_df.to_dict("records")

                # Top 5 across both teams
                all_players = stats.sort_values("fantasy_points", ascending=False).head(
                    5
                )
                top_performers = all_players.to_dict("records")
        except FileNotFoundError:
            logger.warning(
                "Player stats not available for season=%d week=%d", season, week
            )

    return {
        "game_info": game_info,
        "home_players": home_players,
        "away_players": away_players,
        "top_performers": top_performers,
    }


def get_season_leaders(
    season: int,
    scoring_format: str = "half_ppr",
    position: Optional[str] = None,
    limit: int = 50,
) -> pd.DataFrame:
    """Get season-long fantasy point leaders.

    Aggregates weekly stats across all weeks for a season.

    Args:
        season: NFL season year.
        scoring_format: Scoring format for fantasy points.
        position: Optional position filter (QB/RB/WR/TE).
        limit: Maximum number of leaders to return.

    Returns:
        DataFrame with columns: player_id, player_name, team, position,
        total_fantasy_points, games_played, ppg, best_week, worst_week.

    Raises:
        FileNotFoundError: If player stats are not available for the season.
    """
    if season < _PLAYER_STATS_MIN_SEASON:
        raise FileNotFoundError(
            f"Player stats not available before {_PLAYER_STATS_MIN_SEASON}."
        )

    pw = _load_player_weekly(season)
    pw = _compute_fumbles_lost(pw)
    pw = _compute_two_pt(pw)
    pw = calculate_fantasy_points_df(pw, scoring_format, output_col="fantasy_points")

    if "recent_team" in pw.columns:
        pw = pw.rename(columns={"recent_team": "team"})

    if position:
        pw = pw[pw["position"].str.upper() == position.upper()]

    # Aggregate by player
    agg = (
        pw.groupby(["player_id", "player_name", "position"])
        .agg(
            team=("team", "last"),
            total_fantasy_points=("fantasy_points", "sum"),
            games_played=("fantasy_points", "count"),
            best_week=("fantasy_points", "max"),
            worst_week=("fantasy_points", "min"),
        )
        .reset_index()
    )
    agg["ppg"] = (agg["total_fantasy_points"] / agg["games_played"]).round(2)
    agg["total_fantasy_points"] = agg["total_fantasy_points"].round(2)
    agg["best_week"] = agg["best_week"].round(2)
    agg["worst_week"] = agg["worst_week"].round(2)

    agg = agg.sort_values("total_fantasy_points", ascending=False).head(limit)
    agg = agg.reset_index(drop=True)

    return agg[
        [
            "player_id",
            "player_name",
            "team",
            "position",
            "total_fantasy_points",
            "games_played",
            "ppg",
            "best_week",
            "worst_week",
        ]
    ]


def get_player_game_log(
    player_id: str,
    season: int,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """Get a player's full game log for a season.

    Args:
        player_id: NFL player ID (e.g. '00-0034796').
        season: NFL season year.
        scoring_format: Scoring format for fantasy points.

    Returns:
        DataFrame with columns: week, opponent, home_away, fantasy_points,
        game_result, passing_yards, passing_tds, rushing_yards, rushing_tds,
        receptions, receiving_yards, receiving_tds, targets, carries.

    Raises:
        FileNotFoundError: If player stats are not available for the season.
    """
    if season < _PLAYER_STATS_MIN_SEASON:
        raise FileNotFoundError(
            f"Player stats not available before {_PLAYER_STATS_MIN_SEASON}."
        )

    pw = _load_player_weekly(season)
    pw = pw[pw["player_id"] == player_id].copy()

    if pw.empty:
        return pd.DataFrame()

    pw = _compute_fumbles_lost(pw)
    pw = _compute_two_pt(pw)
    pw = calculate_fantasy_points_df(pw, scoring_format, output_col="fantasy_points")

    team_col = "recent_team" if "recent_team" in pw.columns else "team"
    pw["opponent"] = pw.get("opponent_team", pd.Series(dtype="object"))

    # Determine home/away by joining with schedule
    pw["home_away"] = "unknown"
    pw["game_result"] = "unknown"
    try:
        sched = _load_schedules(season)
        for idx, row in pw.iterrows():
            wk = row["week"]
            team = row[team_col]
            wk_sched = sched[sched["week"] == wk]

            home_game = wk_sched[wk_sched["home_team"] == team]
            away_game = wk_sched[wk_sched["away_team"] == team]

            if not home_game.empty:
                g = home_game.iloc[0]
                pw.at[idx, "home_away"] = "home"
                hs = int(g.get("home_score", 0) or 0)
                as_ = int(g.get("away_score", 0) or 0)
                pw.at[idx, "game_result"] = (
                    "W" if hs > as_ else ("L" if as_ > hs else "T")
                )
            elif not away_game.empty:
                g = away_game.iloc[0]
                pw.at[idx, "home_away"] = "away"
                hs = int(g.get("home_score", 0) or 0)
                as_ = int(g.get("away_score", 0) or 0)
                pw.at[idx, "game_result"] = (
                    "W" if as_ > hs else ("L" if hs > as_ else "T")
                )
    except FileNotFoundError:
        logger.warning("Schedule data not available for season=%d", season)

    out_cols = [
        "week",
        "opponent",
        "home_away",
        "fantasy_points",
        "game_result",
        "passing_yards",
        "passing_tds",
        "rushing_yards",
        "rushing_tds",
        "receptions",
        "receiving_yards",
        "receiving_tds",
        "targets",
        "carries",
    ]
    for c in out_cols:
        if c not in pw.columns:
            pw[c] = np.nan

    result = pw[out_cols].sort_values("week").reset_index(drop=True)
    return result


def get_available_seasons() -> List[Dict]:
    """Get list of available seasons with game counts.

    Returns:
        List of dicts with keys: season, game_count, has_player_stats.
    """
    seasons = []

    # Check both schedules and games directories
    for base_dir in (_SCHEDULES_DIR, _GAMES_DIR):
        if not base_dir.exists():
            continue
        for season_dir in sorted(base_dir.iterdir()):
            if not season_dir.name.startswith("season="):
                continue
            try:
                s = int(season_dir.name.split("=")[1])
            except (ValueError, IndexError):
                continue

            # Avoid duplicates
            if any(item["season"] == s for item in seasons):
                continue

            pq = _latest_parquet(season_dir)
            if pq is None:
                continue

            df = pd.read_parquet(pq)
            if "game_type" in df.columns:
                df = df[df["game_type"] == "REG"]

            has_player = (
                _PLAYER_WEEKLY_DIR / f"season={s}"
            ).exists() and s >= _PLAYER_STATS_MIN_SEASON

            seasons.append(
                {
                    "season": s,
                    "game_count": len(df),
                    "has_player_stats": has_player,
                }
            )

    return sorted(seasons, key=lambda x: x["season"], reverse=True)
