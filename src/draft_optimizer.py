#!/usr/bin/env python3
"""
Fantasy Football Draft Optimizer

Provides:
    - DraftBoard: tracks available vs. drafted players, computes value scores
    - DraftAdvisor: recommends best available picks based on roster needs,
      positional scarcity, and ADP vs. model rank discrepancies
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging

from config import ROSTER_CONFIGS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLEX_ELIGIBLE = {'RB', 'WR', 'TE'}
SFLEX_ELIGIBLE = {'QB', 'RB', 'WR', 'TE'}

# ADP value threshold: flag as "undervalued" when model rank beats ADP by >= N spots
UNDERVALUED_THRESHOLD = 15
OVERVALUED_THRESHOLD = 15


# ---------------------------------------------------------------------------
# ADP comparison utilities
# ---------------------------------------------------------------------------

def compute_value_scores(
    projections: pd.DataFrame,
    adp_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Enrich projection DataFrame with draft value metrics.

    Adds columns:
        model_rank          - overall rank by projected_season_points
        adp_rank            - ADP rank from adp_df (if provided)
        adp_diff            - adp_rank - model_rank (positive = undervalued by ADP)
        value_tier          - 'undervalued', 'fair_value', 'overvalued'
        vorp                - Value Over Replacement Player at position

    Args:
        projections: DataFrame from projection_engine.generate_preseason_projections().
        adp_df:      Optional DataFrame with columns [player_name, adp_rank] or
                     [player_id, adp_rank].

    Returns:
        Enriched DataFrame sorted by model_rank.
    """
    df = projections.copy()

    # Model rank (overall)
    pts_col = 'projected_season_points' if 'projected_season_points' in df.columns else 'projected_points'
    df['model_rank'] = df[pts_col].rank(ascending=False, method='first').astype(int)

    # VORP: projected points minus replacement-level player at that position
    # Replacement level = 13th QB, 25th RB, 30th WR, 13th TE (typical starter counts × 12 teams)
    REPLACEMENT_RANKS = {'QB': 13, 'RB': 25, 'WR': 30, 'TE': 13}
    for pos, rep_rank in REPLACEMENT_RANKS.items():
        pos_mask = df['position'] == pos
        pos_sorted = df[pos_mask][pts_col].sort_values(ascending=False)
        if len(pos_sorted) >= rep_rank:
            replacement_pts = pos_sorted.iloc[rep_rank - 1]
        else:
            replacement_pts = pos_sorted.iloc[-1] if len(pos_sorted) > 0 else 0
        df.loc[pos_mask, 'replacement_level'] = replacement_pts

    df['vorp'] = (df[pts_col] - df['replacement_level']).round(1)
    df.drop(columns=['replacement_level'], inplace=True)

    # Merge ADP if provided
    if adp_df is not None and not adp_df.empty:
        join_col = 'player_id' if 'player_id' in adp_df.columns else 'player_name'
        adp_subset = adp_df[[join_col, 'adp_rank']].copy()
        df = df.merge(adp_subset, on=join_col, how='left')
        df['adp_diff'] = df['adp_rank'] - df['model_rank']
        df['value_tier'] = 'fair_value'
        df.loc[df['adp_diff'] >= UNDERVALUED_THRESHOLD, 'value_tier'] = 'undervalued'
        df.loc[df['adp_diff'] <= -OVERVALUED_THRESHOLD, 'value_tier'] = 'overvalued'
    else:
        df['adp_rank'] = np.nan
        df['adp_diff'] = np.nan
        df['value_tier'] = 'fair_value'

    return df.sort_values('model_rank').reset_index(drop=True)


# ---------------------------------------------------------------------------
# Draft Board
# ---------------------------------------------------------------------------

class DraftBoard:
    """
    Tracks the state of an active fantasy draft.

    Maintains a pool of available players and the user's current roster.
    """

    def __init__(
        self,
        players: pd.DataFrame,
        roster_format: str = "standard",
        n_teams: int = 12,
    ):
        """
        Args:
            players:       Enriched projection DataFrame (from compute_value_scores).
            roster_format: One of the keys in config.ROSTER_CONFIGS.
            n_teams:       Number of teams in the league.
        """
        self.n_teams = n_teams
        self.roster_config = ROSTER_CONFIGS.get(roster_format, ROSTER_CONFIGS['standard'])
        self.scoring_format = 'half_ppr'  # informational only on the board

        required_ids = players['player_id'] if 'player_id' in players.columns else players.index
        self.all_players = players.copy()
        self.available = players.copy()
        self.my_roster: List[Dict] = []
        self.drafted_by_others: List[str] = []  # player_ids

    # -----------------------------------------------------------------------
    # Drafting actions
    # -----------------------------------------------------------------------

    def draft_player(self, player_id: str, by_me: bool = False) -> Dict:
        """
        Mark a player as drafted.

        Args:
            player_id: The player's ID.
            by_me:     True if the user drafted this player; False if another team did.

        Returns:
            Player row as dict, or {} if not found.
        """
        id_col = 'player_id' if 'player_id' in self.available.columns else None
        if id_col is None:
            logger.warning("No player_id column on draft board")
            return {}

        mask = self.available[id_col] == player_id
        if not mask.any():
            # Try by name
            if 'player_name' in self.available.columns:
                mask = self.available['player_name'].str.lower() == player_id.lower()
            if not mask.any():
                logger.warning(f"Player '{player_id}' not found in available pool")
                return {}

        player_row = self.available[mask].iloc[0].to_dict()
        self.available = self.available[~mask].reset_index(drop=True)

        if by_me:
            self.my_roster.append(player_row)
            logger.info(f"You drafted: {player_row.get('player_name', player_id)}")
        else:
            self.drafted_by_others.append(player_id)

        return player_row

    def draft_by_name(self, name: str, by_me: bool = False) -> Dict:
        """Draft a player by (partial) name match."""
        if 'player_name' not in self.available.columns:
            return {}
        mask = self.available['player_name'].str.lower().str.contains(name.lower(), na=False)
        if not mask.any():
            logger.warning(f"Player '{name}' not found")
            return {}
        player_id = self.available[mask].iloc[0].get('player_id', name)
        return self.draft_player(player_id, by_me=by_me)

    # -----------------------------------------------------------------------
    # Roster state
    # -----------------------------------------------------------------------

    def roster_summary(self) -> Dict[str, List[str]]:
        """Return current roster grouped by slot."""
        summary: Dict[str, List[str]] = {slot: [] for slot in self.roster_config}
        for player in self.my_roster:
            pos = player.get('position', 'UNK')
            summary.setdefault(pos, []).append(player.get('player_name', 'Unknown'))
        return summary

    def filled_slots(self) -> Dict[str, int]:
        """Count how many of each starter slot have been filled."""
        counts: Dict[str, int] = {slot: 0 for slot in self.roster_config}
        for player in self.my_roster:
            pos = player.get('position', 'UNK')
            if pos in counts:
                counts[pos] += 1
        return counts

    def remaining_needs(self) -> Dict[str, int]:
        """Slots still needed (starter slots only, excludes BN)."""
        filled = self.filled_slots()
        needs = {}
        for slot, required in self.roster_config.items():
            if slot == 'BN':
                continue
            filled_count = filled.get(slot, 0)
            if slot == 'FLEX':
                # Count eligible players not already in a starter slot
                flex_players = sum(1 for p in self.my_roster if p.get('position') in FLEX_ELIGIBLE
                                   and p.get('position') not in ['RB', 'WR', 'TE']
                                   or self._used_as_flex(p))
                needs['FLEX'] = max(0, required - flex_players)
            else:
                needs[slot] = max(0, required - filled_count)
        return needs

    def _used_as_flex(self, player: Dict) -> bool:
        pos = player.get('position')
        if pos not in FLEX_ELIGIBLE:
            return False
        pos_in_roster = [p for p in self.my_roster if p.get('position') == pos]
        pos_required = self.roster_config.get(pos, 0)
        idx = pos_in_roster.index(player) if player in pos_in_roster else -1
        return idx >= pos_required

    def picks_taken(self) -> int:
        return len(self.my_roster) + len(self.drafted_by_others)

    def my_pick_count(self) -> int:
        return len(self.my_roster)


# ---------------------------------------------------------------------------
# Draft Advisor
# ---------------------------------------------------------------------------

class DraftAdvisor:
    """
    Provides pick recommendations given the current DraftBoard state.
    """

    def __init__(self, board: DraftBoard, scoring_format: str = "half_ppr"):
        self.board = board
        self.scoring_format = scoring_format

    def best_available(
        self,
        positions: Optional[List[str]] = None,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        Return the top-N available players by model rank, optionally filtered by position.

        Args:
            positions: List of positions to include (None = all).
            top_n:     Number of players to return.

        Returns:
            DataFrame of top available players.
        """
        avail = self.board.available.copy()
        if positions:
            avail = avail[avail['position'].isin(positions)]
        return avail.sort_values('model_rank').head(top_n).reset_index(drop=True)

    def recommend(
        self,
        top_n: int = 5,
        enforce_needs: bool = True,
    ) -> Tuple[pd.DataFrame, str]:
        """
        Recommend the best available picks accounting for roster construction.

        Args:
            top_n:         Number of recommendations to return.
            enforce_needs: Weight recommendations toward unfilled roster needs.

        Returns:
            (DataFrame of recommended players, reasoning string)
        """
        avail = self.board.available.copy()
        if avail.empty:
            return pd.DataFrame(), "Draft board is empty."

        needs = self.board.remaining_needs()
        my_picks = self.board.my_pick_count()
        picks_taken = self.board.picks_taken()

        reasoning_parts = []

        # Positional scarcity alerts
        scarcity = self._scarcity_alerts(avail)
        reasoning_parts.extend(scarcity)

        # Score each available player
        pts_col = 'projected_season_points' if 'projected_season_points' in avail.columns else 'projected_points'
        avail['recommendation_score'] = avail[pts_col].fillna(0)

        # Boost score for positions still needed
        for pos, count_needed in needs.items():
            if count_needed > 0 and pos in ['QB', 'RB', 'WR', 'TE']:
                boost = min(count_needed * 15, 40)
                avail.loc[avail['position'] == pos, 'recommendation_score'] += boost

        # Boost undervalued players slightly
        if 'value_tier' in avail.columns:
            avail.loc[avail['value_tier'] == 'undervalued', 'recommendation_score'] += 10

        # Penalize overvalued
        if 'value_tier' in avail.columns:
            avail.loc[avail['value_tier'] == 'overvalued', 'recommendation_score'] -= 8

        recs = avail.sort_values('recommendation_score', ascending=False).head(top_n)

        # Build reasoning string
        needs_str = ", ".join(f"{p}×{n}" for p, n in needs.items() if n > 0) or "roster full"
        reasoning_parts.insert(0, f"Remaining needs: {needs_str}")
        reasoning = " | ".join(reasoning_parts)

        return recs.reset_index(drop=True), reasoning

    def _scarcity_alerts(self, avail: pd.DataFrame) -> List[str]:
        """Detect positions with low remaining top-tier talent."""
        alerts = []
        SCARCITY_THRESHOLDS = {'QB': 5, 'RB': 10, 'WR': 12, 'TE': 5}
        for pos, threshold in SCARCITY_THRESHOLDS.items():
            pos_avail = avail[avail['position'] == pos]
            if len(pos_avail) <= threshold:
                alerts.append(f"SCARCITY: Only {len(pos_avail)} {pos}s left!")
        return alerts

    def undervalued_players(self, top_n: int = 10) -> pd.DataFrame:
        """Return available players where model rank significantly beats ADP."""
        avail = self.board.available.copy()
        if 'value_tier' not in avail.columns:
            return pd.DataFrame()
        return (avail[avail['value_tier'] == 'undervalued']
                .sort_values('adp_diff', ascending=False)
                .head(top_n)
                .reset_index(drop=True))

    def overvalued_players(self, top_n: int = 10) -> pd.DataFrame:
        """Return available players where ADP is well above model rank."""
        avail = self.board.available.copy()
        if 'value_tier' not in avail.columns:
            return pd.DataFrame()
        return (avail[avail['value_tier'] == 'overvalued']
                .sort_values('adp_diff')
                .head(top_n)
                .reset_index(drop=True))

    def position_breakdown(self) -> pd.DataFrame:
        """Summary of remaining available players by position."""
        avail = self.board.available
        pts_col = 'projected_season_points' if 'projected_season_points' in avail.columns else 'projected_points'
        return (avail.groupby('position')
                .agg(
                    count=('position', 'count'),
                    avg_pts=(pts_col, 'mean'),
                    top_pts=(pts_col, 'max'),
                )
                .round(1)
                .reset_index()
                .sort_values('avg_pts', ascending=False))
