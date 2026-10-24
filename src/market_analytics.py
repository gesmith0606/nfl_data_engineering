#!/usr/bin/env python3
"""
Market Analytics Module

Computes line movement features from Bronze odds data and reshapes game-level
rows into per-team-per-week Silver rows for integration into the prediction
feature vector.

Exports:
    compute_movement_features(odds_df) -> DataFrame with computed market features
    reshape_to_per_team(odds_with_features) -> per-team-per-week DataFrame
"""

import glob
import os

import pandas as pd
import numpy as np
from typing import List, Optional

_ODDS_SNAPSHOT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "bronze", "odds_api", "snapshots",
)


def fill_lines_from_odds_snapshot(
    sched: pd.DataFrame, season: int, snapshot_dir: Optional[str] = None
) -> pd.DataFrame:
    """Fill NaN ``spread_line``/``total_line`` of unplayed games from the
    latest live odds snapshot.

    nflverse posts a week's lines days after the books do, so in-season the
    week being predicted has no schedule lines — leaving the model's market
    feature (opening spread) and the Vegas edge empty. The committed Odds API
    snapshots carry them; this takes the median across books per game. Lines
    already on the schedule, and games already played, are never touched.

    Sign: snapshot ``home_spread`` is negative when home is favored; nflverse
    ``spread_line`` is positive when home is favored, so ``spread_line =
    -median(home_spread)``.

    Args:
        sched: Schedule rows with home_team, away_team, spread_line, total_line
            (and ``result`` when available, to skip played games).
        season: Season whose snapshots to read.
        snapshot_dir: Override for the snapshot root (tests).

    Returns:
        Copy of *sched* with missing lines filled where a snapshot has them.
    """
    if sched.empty or not {"spread_line", "total_line"} <= set(sched.columns):
        return sched
    if not sched[["spread_line", "total_line"]].isna().any().any():
        return sched
    root = snapshot_dir or _ODDS_SNAPSHOT_DIR
    files = sorted(glob.glob(os.path.join(root, f"season={season}", "odds_*.parquet")))
    if not files:
        return sched
    # Recent snapshots (several per day), so a game-day snapshot holding only
    # in-progress games doesn't hide the pre-game lines captured earlier.
    odds = pd.concat([pd.read_parquet(f) for f in files[-30:]], ignore_index=True)
    need = {
        "home_team_nfl", "away_team_nfl", "market", "home_spread",
        "total_points", "snapshot_ts", "commence_time",
    }
    if odds.empty or not need <= set(odds.columns):
        return sched
    snap = pd.to_datetime(odds["snapshot_ts"], utc=True)
    kick = pd.to_datetime(odds["commence_time"], utc=True)
    odds = odds.assign(_snap=snap, _date=kick.dt.tz_convert("America/New_York").dt.date)
    odds = odds[snap < kick]  # pre-game prices only, never live in-game lines
    if odds.empty:
        return sched
    keys = ["home_team_nfl", "away_team_nfl", "_date"]
    odds = odds[odds["_snap"] == odds.groupby(keys)["_snap"].transform("max")]
    spreads = (
        odds[odds["market"] == "spreads"].groupby(keys)["home_spread"].median().mul(-1)
    )
    totals = odds[odds["market"] == "totals"].groupby(keys)["total_points"].median()
    lines = pd.DataFrame({"_spread": spreads, "_total": totals}).reset_index()
    lines = lines.rename(
        columns={"home_team_nfl": "home_team", "away_team_nfl": "away_team"}
    )
    on = ["home_team", "away_team"]
    left = sched
    if "gameday" in sched.columns:
        # Match the game date too, so a home/away pair can never fill the
        # rivals' other meeting (e.g. a neutral-site game listed flipped).
        left = sched.assign(_date=pd.to_datetime(sched["gameday"]).dt.date)
        on.append("_date")
    else:
        lines = lines.drop(columns="_date").drop_duplicates(on, keep="last")
    out = left.merge(lines, on=on, how="left").drop(columns="_date", errors="ignore")
    out.index = sched.index
    unplayed = out["result"].isna() if "result" in out.columns else True
    for col, src in (("spread_line", "_spread"), ("total_line", "_total")):
        fill = out[col].isna() & unplayed & out[src].notna()
        out.loc[fill, col] = out.loc[fill, src]
    return out.drop(columns=["_spread", "_total"])

def build_game_lines_from_snapshots(
    season: int,
    snapshot_dir: Optional[str] = None,
    schedule: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Game-level open/close lines for a season the FinnedAI Bronze never covered.

    ``silver_market_transformation.py`` reads ``data/bronze/odds/``, which stops
    at 2021. The Odds API cron writes a different layout under
    ``data/bronze/odds_api/snapshots``, and nothing consumed it — so from 2022 on
    there is no Silver ``market_data``, no ``opening_spread`` feature, and the
    ensemble cannot score the season at all. This bridges the two.

    Sign: snapshot spreads are the SPORTSBOOK convention (negative = home
    favoured); Silver ``opening_spread`` is nflverse-oriented for the row's team
    (measured: Silver home rows correlate +0.944 with nflverse ``spread_line``
    on 2020). So the home value is ``-open_spread``, exactly as
    :func:`fill_lines_from_odds_snapshot` already does for ``spread_line``.
    ``reshape_to_per_team`` then negates it for the away row.

    Args:
        season: NFL season year.
        snapshot_dir: Override for the snapshot root (tests).
        schedule: Schedule rows supplying game_id/week/game_type. Read from the
            committed Bronze schedules when None.

    Returns:
        Game-level DataFrame shaped for :func:`compute_movement_features`, or an
        empty DataFrame when the season has no snapshots.
    """
    from odds_snapshot_loader import load_open_close_lines

    spreads = load_open_close_lines(season, "spreads", snapshot_dir)
    totals = load_open_close_lines(season, "totals", snapshot_dir)
    if spreads.empty and totals.empty:
        return pd.DataFrame()

    keys = ["home_team_nfl", "away_team_nfl"]
    cols_s = keys + ["open_spread", "close_spread"]
    cols_t = keys + ["open_total", "close_total"]
    if spreads.empty:
        games = totals[cols_t].copy()
        games["open_spread"] = pd.NA
        games["close_spread"] = pd.NA
    elif totals.empty:
        games = spreads[cols_s].copy()
        games["open_total"] = pd.NA
        games["close_total"] = pd.NA
    else:
        games = spreads[cols_s].merge(totals[cols_t], on=keys, how="outer")

    if schedule is None:
        files = sorted(
            glob.glob(os.path.join("data", "bronze", "schedules", f"season={season}", "*.parquet"))
        )
        if not files:
            return pd.DataFrame()
        schedule = pd.read_parquet(files[-1])

    need = ["game_id", "season", "week", "game_type", "home_team", "away_team"]
    sched = schedule[[c for c in need if c in schedule.columns]].drop_duplicates()
    out = sched.merge(
        games, left_on=["home_team", "away_team"], right_on=keys, how="inner"
    ).drop(columns=keys)

    # Flip to the nflverse orientation the trained model expects.
    out["opening_spread"] = -pd.to_numeric(out.pop("open_spread"), errors="coerce")
    out["closing_spread"] = -pd.to_numeric(out.pop("close_spread"), errors="coerce")
    out["opening_total"] = pd.to_numeric(out.pop("open_total"), errors="coerce")
    out["closing_total"] = pd.to_numeric(out.pop("close_total"), errors="coerce")
    return out.reset_index(drop=True)


# NFL key numbers where point probability spikes
KEY_SPREAD_NUMBERS = [3, 7, 10]
KEY_TOTAL_NUMBERS = [41, 44, 47]


def compute_movement_features(odds_df: pd.DataFrame) -> pd.DataFrame:
    """Compute line movement features from Bronze odds data.

    Adds shift, absolute movement, magnitude buckets, key number crossings,
    and a steam move placeholder to the input DataFrame.

    Feature temporal classification:
    -----------------------------------------------------------------------
    PRE-GAME features (safe for live prediction -- known before kickoff):
        opening_spread, opening_total

    RETROSPECTIVE features (historical analysis / ablation only --
        depend on closing line which is known only at kickoff):
        closing_spread, closing_total, spread_shift, total_shift,
        spread_move_abs, total_move_abs, spread_magnitude, total_magnitude,
        crosses_key_spread, crosses_key_total, is_steam_move

    WARNING: Adding retrospective features to _PRE_GAME_CONTEXT in
    feature_engineering.py would create closing-line leakage.
    -----------------------------------------------------------------------

    Args:
        odds_df: Bronze odds DataFrame with columns: game_id, season, week,
            game_type, home_team, away_team, opening_spread, closing_spread,
            opening_total, closing_total, home_moneyline, away_moneyline,
            nflverse_spread_line, nflverse_total_line.

    Returns:
        DataFrame with all original columns plus 9 computed feature columns.
    """
    df = odds_df.copy()

    # Movement = closing - opening
    df["spread_shift"] = df["closing_spread"] - df["opening_spread"]
    df["total_shift"] = df["closing_total"] - df["opening_total"]

    # Absolute magnitude
    df["spread_move_abs"] = df["spread_shift"].abs()
    df["total_move_abs"] = df["total_shift"].abs()

    # Magnitude buckets (ordinal: 0=none, 1=small, 2=medium, 3=large)
    df["spread_magnitude"] = pd.cut(
        df["spread_move_abs"],
        bins=[-0.001, 0.0, 1.0, 2.0, float("inf")],
        labels=[0, 1, 2, 3],
    ).astype(float)

    df["total_magnitude"] = pd.cut(
        df["total_move_abs"],
        bins=[-0.001, 0.0, 1.0, 2.0, float("inf")],
        labels=[0, 1, 2, 3],
    ).astype(float)

    # Key number crossing -- spread crosses 3, 7, or 10
    open_s = df["opening_spread"].abs()
    close_s = df["closing_spread"].abs()
    df["crosses_key_spread"] = False
    for key_num in KEY_SPREAD_NUMBERS:
        crossed = ((open_s < key_num) & (close_s >= key_num)) | (
            (open_s >= key_num) & (close_s < key_num)
        )
        df["crosses_key_spread"] = df["crosses_key_spread"] | crossed

    # Key number crossing -- total crosses 41, 44, or 47
    df["crosses_key_total"] = False
    for key_num in KEY_TOTAL_NUMBERS:
        crossed = ((df["opening_total"] < key_num) & (df["closing_total"] >= key_num)) | (
            (df["opening_total"] >= key_num) & (df["closing_total"] < key_num)
        )
        df["crosses_key_total"] = df["crosses_key_total"] | crossed

    # Steam move: NaN placeholder (no timestamp data in FinnedAI -- per D-15/D-16)
    df["is_steam_move"] = float("nan")

    return df


def reshape_to_per_team(odds_with_features: pd.DataFrame) -> pd.DataFrame:
    """Reshape game-level odds to per-team-per-week rows.

    Each game produces two rows: one for the home team, one for the away team.

    Sign convention (per D-02):
        Directional columns (opening_spread, closing_spread, spread_shift)
        are negated for the away team row. A home-favored spread of -3.0
        becomes +3.0 from the away team's perspective.

    Symmetric columns (per D-01/D-03/D-11):
        Totals, absolute movement, magnitude buckets, key crossings, and
        steam move are identical for both home and away rows.

    Args:
        odds_with_features: Game-level DataFrame from compute_movement_features().

    Returns:
        Per-team DataFrame sorted by [team, season, week] with is_home flag.
    """
    DIRECTIONAL = ["opening_spread", "closing_spread", "spread_shift"]
    SYMMETRIC = [
        "opening_total", "closing_total", "total_shift",
        "spread_move_abs", "total_move_abs",
        "spread_magnitude", "total_magnitude",
        "crosses_key_spread", "crosses_key_total", "is_steam_move",
    ]
    ID_COLS = ["game_id", "season", "week", "game_type"]

    # Home rows: directional features as-is
    home = odds_with_features[ID_COLS].copy()
    home["team"] = odds_with_features["home_team"].values
    home["opponent"] = odds_with_features["away_team"].values
    home["is_home"] = True
    for col in DIRECTIONAL:
        home[col] = odds_with_features[col].values
    for col in SYMMETRIC:
        home[col] = odds_with_features[col].values

    # Away rows: negate directional features
    away = odds_with_features[ID_COLS].copy()
    away["team"] = odds_with_features["away_team"].values
    away["opponent"] = odds_with_features["home_team"].values
    away["is_home"] = False
    for col in DIRECTIONAL:
        away[col] = -odds_with_features[col].values
    for col in SYMMETRIC:
        away[col] = odds_with_features[col].values

    result = pd.concat([home, away], ignore_index=True)
    return result.sort_values(["team", "season", "week"]).reset_index(drop=True)
