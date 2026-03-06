#!/usr/bin/env python3
"""
Fantasy Scoring Calculator

Converts raw player stat projections into fantasy points for any
configurable scoring format (PPR, Half-PPR, Standard, or custom).
"""

from typing import Dict, Optional
import pandas as pd
import numpy as np
import logging

from config import SCORING_CONFIGS

logger = logging.getLogger(__name__)


def calculate_fantasy_points(
    stats: Dict[str, float],
    scoring_format: str = "half_ppr",
    custom_scoring: Optional[Dict[str, float]] = None,
) -> float:
    """
    Calculate fantasy points for a single player's stat line.

    Args:
        stats:          Dict of stat name -> value (e.g. {'rushing_yards': 75, 'rush_td': 1}).
        scoring_format: One of 'ppr', 'half_ppr', 'standard', or 'custom'.
        custom_scoring: Scoring config dict when scoring_format='custom'.

    Returns:
        Total fantasy points as a float.

    Stat key mapping (input keys -> scoring config keys):
        rushing_yards   -> rush_yd
        rushing_tds     -> rush_td
        receiving_yards -> rec_yd
        receiving_tds   -> rec_td
        receptions      -> reception
        passing_yards   -> pass_yd
        passing_tds     -> pass_td
        interceptions   -> interception
        fumbles_lost    -> fumble_lost
        two_pt_conversions -> 2pt_conversion
    """
    if scoring_format == 'custom':
        if custom_scoring is None:
            raise ValueError("custom_scoring dict required when scoring_format='custom'")
        scoring = custom_scoring
    elif scoring_format in SCORING_CONFIGS:
        scoring = SCORING_CONFIGS[scoring_format]
    else:
        raise ValueError(f"Unknown scoring format: {scoring_format}. "
                         f"Choose from {list(SCORING_CONFIGS.keys())} or 'custom'.")

    # Canonical stat-name to scoring-key mapping
    _MAP = {
        'rushing_yards': 'rush_yd',
        'rushing_tds': 'rush_td',
        'receiving_yards': 'rec_yd',
        'receiving_tds': 'rec_td',
        'receptions': 'reception',
        'passing_yards': 'pass_yd',
        'passing_tds': 'pass_td',
        'interceptions': 'interception',
        'fumbles_lost': 'fumble_lost',
        'two_pt_conversions': '2pt_conversion',
        # Also accept scoring keys directly
        'rush_yd': 'rush_yd',
        'rush_td': 'rush_td',
        'rec_yd': 'rec_yd',
        'rec_td': 'rec_td',
        'reception': 'reception',
        'pass_yd': 'pass_yd',
        'pass_td': 'pass_td',
        'interception': 'interception',
        'fumble_lost': 'fumble_lost',
        '2pt_conversion': '2pt_conversion',
    }

    total = 0.0
    for stat_key, value in stats.items():
        scoring_key = _MAP.get(stat_key)
        if scoring_key and scoring_key in scoring:
            total += value * scoring[scoring_key]

    return round(total, 2)


def calculate_fantasy_points_df(
    df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    custom_scoring: Optional[Dict[str, float]] = None,
    output_col: str = "projected_points",
) -> pd.DataFrame:
    """
    Vectorized fantasy point calculation on a DataFrame of player stats.

    Expected columns (any subset):
        rushing_yards, rushing_tds, carries,
        receiving_yards, receiving_tds, receptions, targets,
        passing_yards, passing_tds, interceptions,
        fumbles_lost, two_pt_conversions

    Args:
        df:             DataFrame with player stat columns.
        scoring_format: Scoring format name.
        custom_scoring: Custom scoring dict (required when scoring_format='custom').
        output_col:     Name of the output fantasy-points column.

    Returns:
        DataFrame with output_col added.
    """
    if scoring_format == 'custom':
        if custom_scoring is None:
            raise ValueError("custom_scoring dict required when scoring_format='custom'")
        scoring = custom_scoring
    else:
        scoring = SCORING_CONFIGS[scoring_format]

    df = df.copy()

    def _get(col: str) -> pd.Series:
        return df[col].fillna(0) if col in df.columns else pd.Series(0, index=df.index)

    pts = (
        _get('rushing_yards') * scoring.get('rush_yd', 0)
        + _get('rushing_tds') * scoring.get('rush_td', 0)
        + _get('receiving_yards') * scoring.get('rec_yd', 0)
        + _get('receiving_tds') * scoring.get('rec_td', 0)
        + _get('receptions') * scoring.get('reception', 0)
        + _get('passing_yards') * scoring.get('pass_yd', 0)
        + _get('passing_tds') * scoring.get('pass_td', 0)
        + _get('interceptions') * scoring.get('interception', 0)
        + _get('fumbles_lost') * scoring.get('fumble_lost', 0)
        + _get('two_pt_conversions') * scoring.get('2pt_conversion', 0)
    )

    df[output_col] = pts.round(2)
    logger.info(f"Fantasy points calculated ({scoring_format}) for {len(df)} rows")
    return df


def get_scoring_config(scoring_format: str) -> Dict[str, float]:
    """Return the scoring config dict for a given format."""
    if scoring_format not in SCORING_CONFIGS:
        raise ValueError(f"Unknown format: {scoring_format}")
    return SCORING_CONFIGS[scoring_format]


def list_scoring_formats() -> list:
    """Return list of supported scoring format names."""
    return list(SCORING_CONFIGS.keys())
