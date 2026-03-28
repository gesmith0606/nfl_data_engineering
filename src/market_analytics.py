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

import pandas as pd
import numpy as np
from typing import List

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
