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
from typing import Dict, List, Optional, Sequence, Tuple
from collections import Counter
import logging
import random

from config import ROSTER_CONFIGS

try:  # importable both as ``src.draft_optimizer`` and bare ``draft_optimizer``
    from src.draft_availability import expected_best_vorp_at_pick
except ImportError:  # pragma: no cover — scripts put src/ itself on sys.path
    from draft_availability import expected_best_vorp_at_pick

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLEX_ELIGIBLE = {"RB", "WR", "TE"}
SFLEX_ELIGIBLE = {"QB", "RB", "WR", "TE"}

# ADP value threshold: flag as "undervalued" when model rank beats ADP by >= N spots
UNDERVALUED_THRESHOLD = 15
OVERVALUED_THRESHOLD = 15

_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name) -> str:
    """Suffix/punctuation/nickname-blind join key: ``"James Cook III"`` ==
    ``"James Cook"``, ``"Hollywood Brown"`` == ``"Marquise Brown"``.

    ADP feeds carry generational suffixes and stage names our projections
    drop; a raw-name join left Cook/Walker/Etienne with NaN ADP (2026-08-23
    ESPN mock) and lost Hollywood Brown from every 2022-24 replay board.
    Nickname canonicalization reuses the shared alias table.
    """
    import re

    cleaned = re.sub(r"[^a-z0-9\s]", "", str(name or "").lower())
    tokens = [t for t in cleaned.split() if t not in _NAME_SUFFIXES]
    if tokens:
        tokens[0] = _first_name_aliases().get(tokens[0], tokens[0])
    return " ".join(tokens)


def _first_name_aliases() -> Dict[str, str]:
    """Shared nickname table from sleeper_player_map (empty on import trouble)."""
    global _ALIASES_CACHE
    if _ALIASES_CACHE is None:
        try:
            from src.sleeper_player_map import _FIRST_NAME_ALIASES as aliases
        except ImportError:
            try:
                from sleeper_player_map import _FIRST_NAME_ALIASES as aliases
            except ImportError:  # pragma: no cover
                aliases = {}
        _ALIASES_CACHE = dict(aliases)
    return _ALIASES_CACHE


_ALIASES_CACHE: Optional[Dict[str, str]] = None


def market_believed(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows the market does not believe in: low-sample projections with no
    external consensus rank (the Okwuegbunam 85-rec artifact class). The
    2021-25 draft replay's unfiltered board — retirees and 1-game ghosts —
    ranked 9.94/12 by actual results; filtered it ranked 6.42. Frames without
    the Gold flag columns pass through unchanged.
    """
    if (
        df.empty
        or "is_low_sample_projection" not in df.columns
        or "consensus_pos_rank" not in df.columns
    ):
        return df
    suspect = (
        df["is_low_sample_projection"].fillna(False).astype(bool)
        & df["consensus_pos_rank"].isna()
    )
    return df[~suspect]

# Legacy replacement levels (typical starter counts x 12 teams) — used
# whenever no roster_format is supplied, preserving historical behavior.
DEFAULT_REPLACEMENT_RANKS = {"QB": 13, "RB": 25, "WR": 30, "TE": 13, "K": 13, "DST": 13}

# How a FLEX slot's usage splits across eligible positions in practice
# (WR-heavy, RB next, TE rare). SFLEX credits QBs at 0.8 per slot.
FLEX_SHARE = {"RB": 0.35, "WR": 0.50, "TE": 0.15}


def replacement_ranks_for(
    roster_format: Optional[str] = None, n_teams: int = 12
) -> Dict[str, int]:
    """Derive per-position replacement ranks from a roster shape.

    Replacement level = 1 past the last league-wide starter:
    ``n_teams x (dedicated starters + flex share) + 1``. Positions the
    lineup cannot start at all (e.g. no-kicker Sleeper leagues) are
    omitted, so their replacement level — and VORP — stays NaN rather
    than fabricating value for undraftable positions.

    Args:
        roster_format: A ``config.ROSTER_CONFIGS`` key; None returns the
            legacy ``DEFAULT_REPLACEMENT_RANKS`` unchanged.
        n_teams: League size.

    Returns:
        Position -> replacement rank mapping.
    """
    if roster_format is None:
        return dict(DEFAULT_REPLACEMENT_RANKS)
    roster = ROSTER_CONFIGS[roster_format]
    flex_slots = roster.get("FLEX", 0)
    ranks: Dict[str, int] = {}
    for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
        starters = float(roster.get(pos, 0))
        share = FLEX_SHARE.get(pos, 0.0) * flex_slots
        if pos == "QB":
            share += 0.8 * roster.get("SFLEX", 0)
        if starters + share <= 0:
            continue
        ranks[pos] = int(n_teams * (starters + share) + 0.5) + 1
    return ranks


# ---------------------------------------------------------------------------
# ADP comparison utilities
# ---------------------------------------------------------------------------


def compute_value_scores(
    projections: pd.DataFrame,
    adp_df: Optional[pd.DataFrame] = None,
    roster_format: Optional[str] = None,
    n_teams: int = 12,
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

    # Normalize positions to uppercase so VORP, needs, saturation, and draftable
    # filtering are robust to lowercase input (e.g. a hand-rolled CSV).
    if "position" in df.columns:
        df["position"] = df["position"].astype(str).str.upper()

    # Model rank (overall)
    pts_col = (
        "projected_season_points"
        if "projected_season_points" in df.columns
        else "projected_points"
    )
    raw_rank = df[pts_col].rank(ascending=False, method="first")
    # DST is not projected by our model (see REPLACEMENT_RANKS note below), so
    # its pts_col is NaN and .rank() leaves it NaN too — .astype(int) on that
    # raises. Push unranked (NaN-points) rows to the back of the board rather
    # than crashing; they still surface, just sorted last by model_rank.
    unranked_fill = int(raw_rank.max()) + 1 if raw_rank.notna().any() else 1
    df["model_rank"] = raw_rank.fillna(unranked_fill).astype(int)

    # VORP: projected points minus replacement-level player at that position.
    # With no roster_format the legacy 12-team-standard ranks apply (13th QB,
    # 25th RB, 30th WR, ...); with one, ranks derive from the actual lineup
    # shape and league size — a 3-FLEX 12-teamer pushes WR replacement to
    # ~43rd, a 10-team 3-WR league to ~36th. DST has no projected_points in
    # our model (ADP-only board row) — replacement_level stays NaN for it, so
    # vorp is NaN (never a crash) rather than a fabricated number.
    replacement_ranks = replacement_ranks_for(roster_format, n_teams)
    for pos, rep_rank in replacement_ranks.items():
        pos_mask = df["position"] == pos
        pos_sorted = df[pos_mask][pts_col].dropna().sort_values(ascending=False)
        if len(pos_sorted) >= rep_rank:
            replacement_pts = pos_sorted.iloc[rep_rank - 1]
        elif len(pos_sorted) > 0:
            replacement_pts = pos_sorted.iloc[-1]
        else:
            # No player at this position has a projection at all (e.g. DST) —
            # leave replacement level (and therefore vorp) as NaN.
            replacement_pts = np.nan
        df.loc[pos_mask, "replacement_level"] = replacement_pts

    df["vorp"] = (df[pts_col] - df["replacement_level"]).round(1)
    df.drop(columns=["replacement_level"], inplace=True)

    # Merge ADP if provided
    if adp_df is not None and not adp_df.empty:
        join_col = "player_id" if "player_id" in adp_df.columns else "player_name"
        # Carry real-ADP stdev through as adp_stdev when the source CSV has
        # it (FFC/ESPN via src/adp_sources.py) — availability probability
        # reads it; absent for the legacy sleeper_rank source, and callers
        # fall back to their own sigma.
        has_stdev = "stdev" in adp_df.columns
        merge_cols = [join_col, "adp_rank"] + (["stdev"] if has_stdev else [])
        adp_subset = adp_df[merge_cols].copy()
        if has_stdev:
            adp_subset = adp_subset.rename(columns={"stdev": "adp_stdev"})
        if join_col == "player_name":
            # Join on a suffix-blind key so "James Cook III" (ADP) meets
            # "James Cook" (projections); keep the first ADP row per key.
            adp_subset["_name_key"] = adp_subset["player_name"].map(name_key)
            adp_subset = adp_subset.drop(columns=["player_name"]).drop_duplicates(
                "_name_key"
            )
            df["_name_key"] = df["player_name"].map(name_key)
            df = df.merge(adp_subset, on="_name_key", how="left").drop(
                columns=["_name_key"]
            )
        else:
            df = df.merge(adp_subset, on=join_col, how="left")
        df["adp_diff"] = df["adp_rank"] - df["model_rank"]
        df["value_tier"] = "fair_value"
        df.loc[df["adp_diff"] >= UNDERVALUED_THRESHOLD, "value_tier"] = "undervalued"
        df.loc[df["adp_diff"] <= -OVERVALUED_THRESHOLD, "value_tier"] = "overvalued"
    else:
        df["adp_rank"] = np.nan
        df["adp_diff"] = np.nan
        df["value_tier"] = "fair_value"

    if "adp_stdev" not in df.columns:
        df["adp_stdev"] = np.nan

    return df.sort_values("model_rank").reset_index(drop=True)


# Sleeper roster-slot name -> DraftBoard roster_config key. Flex variants collapse
# to FLEX, superflex to SFLEX, defense to DST; bench/IR/taxi are not starters.
_SLOT_TO_CONFIG_KEY = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "K": "K",
    "DEF": "DST",
    "DST": "DST",
    "FLEX": "FLEX",
    "WRRB_FLEX": "FLEX",
    "REC_FLEX": "FLEX",
    "WRRB_WRT": "FLEX",
    "SUPER_FLEX": "SFLEX",
    "SUPERFLEX": "SFLEX",
}
_NON_STARTER_SLOTS = {"BN", "IR", "TAXI"}


def roster_config_from_positions(
    roster_positions: Optional[List[str]],
) -> Optional[Dict[str, int]]:
    """Build a DraftBoard ``roster_config`` from a Sleeper ``roster_positions`` list.

    Counts each starting slot into the keys ``DraftBoard`` understands
    (QB/RB/WR/TE/K/DST/FLEX/SFLEX), dropping bench/IR/taxi and unknown IDP slots.
    Lets remaining-needs reflect a league's true lineup (e.g. 3×FLEX and no K/DST
    for "12 Mahomo's") instead of the generic ``standard`` preset.

    Returns ``None`` for empty input so callers fall back to ``roster_format``.
    """
    if not roster_positions:
        return None
    counts: Dict[str, int] = {}
    for raw in roster_positions:
        name = str(raw).upper()
        if name in _NON_STARTER_SLOTS:
            continue
        key = _SLOT_TO_CONFIG_KEY.get(name)
        if key is None:  # unknown / IDP slot — not modeled
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts or None


def draftable_positions(roster_config: Optional[Dict[str, int]]) -> set:
    """Positions a league can actually roster — used to filter the player pool.

    A league with no K or DST starting slot should never be advised to draft a
    kicker/defense (their VORP ≈ 0 otherwise out-ranks deep negative-VORP skill
    players late). FLEX contributes RB/WR/TE; SFLEX adds QB. Falls back to the
    full skill set when no config is given.
    """
    default = {"QB", "RB", "WR", "TE", "K", "DST"}
    if not roster_config:
        return default
    elig: set = set()
    for slot in roster_config:
        if slot == "FLEX":
            elig |= FLEX_ELIGIBLE
        elif slot == "SFLEX":
            elig |= SFLEX_ELIGIBLE
        elif slot in ("QB", "RB", "WR", "TE", "K", "DST"):
            elig.add(slot)
    return elig or {"QB", "RB", "WR", "TE"}


# Sleeper draft `settings` slot keys -> roster_config key (mock draftboards expose
# starting slots this way instead of as a roster_positions list).
_SLOT_SETTING_KEY = {
    "slots_qb": "QB",
    "slots_rb": "RB",
    "slots_wr": "WR",
    "slots_te": "TE",
    "slots_k": "K",
    "slots_def": "DST",
    "slots_flex": "FLEX",
    "slots_wrrb_flex": "FLEX",
    "slots_rec_flex": "FLEX",
    "slots_super_flex": "SFLEX",
}


def roster_config_from_slots(settings: Optional[Dict]) -> Optional[Dict[str, int]]:
    """Build a roster_config from a Sleeper draft's ``settings`` slots_* counts.

    Mock draftboards (and league drafts) expose starting slots as ``slots_qb`` /
    ``slots_flex`` / ``slots_super_flex`` integers rather than a ``roster_positions``
    list. Maps them to the same keys :class:`DraftBoard` understands.
    """
    if not settings:
        return None
    rc: Dict[str, int] = {}
    for k, key in _SLOT_SETTING_KEY.items():
        n = int(settings.get(k) or 0)
        if n:
            rc[key] = rc.get(key, 0) + n
    return rc or None


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
        roster_config: Optional[Dict[str, int]] = None,
    ):
        """
        Args:
            players:       Enriched projection DataFrame (from compute_value_scores).
            roster_format: One of the keys in config.ROSTER_CONFIGS.
            n_teams:       Number of teams in the league.
            roster_config: Explicit starting-slot counts (e.g. built from a league's
                           real Sleeper ``roster_positions`` via
                           :func:`roster_config_from_positions`). When given it
                           overrides ``roster_format`` so remaining-needs reflect the
                           actual league lineup (e.g. 3×FLEX, no K/DST).
        """
        self.n_teams = n_teams
        self.roster_config = roster_config or ROSTER_CONFIGS.get(
            roster_format, ROSTER_CONFIGS["standard"]
        )
        self.scoring_format = "half_ppr"  # informational only on the board

        required_ids = (
            players["player_id"] if "player_id" in players.columns else players.index
        )
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
        id_col = "player_id" if "player_id" in self.available.columns else None
        if id_col is None:
            logger.warning("No player_id column on draft board")
            return {}

        mask = self.available[id_col] == player_id
        if not mask.any():
            # Try by name
            if "player_name" in self.available.columns:
                mask = self.available["player_name"].str.lower() == player_id.lower()
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

    def remove_players(self, names_or_ids: Sequence[str]) -> int:
        """Silently remove players from the available pool (no pick recorded).

        For league-rostered players who were never drafted in THIS draft
        (dynasty/keeper leagues): they must leave the pool so availability,
        recommendations, and value-drop alerts reflect reality — but they are
        NOT picks, so ``picks_taken()`` and roster state stay untouched
        (drafting them via :meth:`draft_player` would corrupt snake math).

        Matches by ``player_id`` first, then by normalized full name
        (suffix/nickname tolerant), so players whose id mapping failed are
        still removed.

        Args:
            names_or_ids: Player ids and/or full names to remove.

        Returns:
            Number of players actually removed.
        """
        if self.available.empty or not names_or_ids:
            return 0
        try:
            from src.sleeper_player_map import normalize_name
        except ImportError:  # pragma: no cover
            from sleeper_player_map import normalize_name

        keys = {str(k) for k in names_or_ids if k}
        norm_keys = {normalize_name(k) for k in keys}
        norm_keys.discard("")

        mask = pd.Series(False, index=self.available.index)
        if "player_id" in self.available.columns:
            mask |= self.available["player_id"].astype(str).isin(keys)
        if "player_name" in self.available.columns:
            mask |= (
                self.available["player_name"]
                .astype(str)
                .map(normalize_name)
                .isin(norm_keys)
            )
        removed = int(mask.sum())
        if removed:
            self.available = self.available[~mask].reset_index(drop=True)
        return removed

    def draft_by_name(self, name: str, by_me: bool = False) -> Dict:
        """Draft a player by (partial) name match."""
        if "player_name" not in self.available.columns:
            return {}
        # Exact suffix-blind match first ("Travis Etienne Jr." == "Travis
        # Etienne"), then the legacy partial match as a fallback.
        keys = self.available["player_name"].map(name_key)
        mask = keys == name_key(name)
        if not mask.any():
            mask = (
                self.available["player_name"]
                .str.lower()
                .str.contains(name.lower(), na=False, regex=False)
            )
        if not mask.any():
            logger.warning(f"Player '{name}' not found")
            return {}
        player_id = self.available[mask].iloc[0].get("player_id", name)
        return self.draft_player(player_id, by_me=by_me)

    # -----------------------------------------------------------------------
    # Roster state
    # -----------------------------------------------------------------------

    def roster_summary(self) -> Dict[str, List[str]]:
        """Return current roster grouped by slot."""
        summary: Dict[str, List[str]] = {slot: [] for slot in self.roster_config}
        for player in self.my_roster:
            pos = player.get("position", "UNK")
            summary.setdefault(pos, []).append(player.get("player_name", "Unknown"))
        return summary

    def filled_slots(self) -> Dict[str, int]:
        """Count how many of each starter slot have been filled."""
        counts: Dict[str, int] = {slot: 0 for slot in self.roster_config}
        for player in self.my_roster:
            pos = str(player.get("position", "UNK")).upper()
            if pos in counts:
                counts[pos] += 1
        return counts

    def remaining_needs(self) -> Dict[str, int]:
        """Slots still needed (starter slots only, excludes BN)."""
        filled = self.filled_slots()
        needs = {}
        for slot, required in self.roster_config.items():
            if slot == "BN":
                continue
            filled_count = filled.get(slot, 0)
            if slot == "FLEX":
                # Count eligible players not already in a starter slot
                flex_players = sum(
                    1
                    for p in self.my_roster
                    if p.get("position") in FLEX_ELIGIBLE
                    and p.get("position") not in ["RB", "WR", "TE"]
                    or self._used_as_flex(p)
                )
                needs["FLEX"] = max(0, required - flex_players)
            else:
                needs[slot] = max(0, required - filled_count)
        return needs

    def _used_as_flex(self, player: Dict) -> bool:
        pos = player.get("position")
        if pos not in FLEX_ELIGIBLE:
            return False
        pos_in_roster = [p for p in self.my_roster if p.get("position") == pos]
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
            avail = avail[avail["position"].isin(positions)]
        return avail.sort_values("model_rank").head(top_n).reset_index(drop=True)

    def recommend(
        self,
        top_n: int = 5,
        enforce_needs: bool = True,
        next_pick_no: Optional[int] = None,
        my_picks_remaining: Optional[int] = None,
    ) -> Tuple[pd.DataFrame, str]:
        """
        Recommend the best available picks accounting for roster construction.

        Args:
            top_n:         Number of recommendations to return.
            enforce_needs: Weight recommendations toward unfilled roster needs and
                           apply the starters-first hard rule.
            next_pick_no:  The user's NEXT overall pick after this one. When given,
                           candidates are scored by opportunity cost (value now
                           minus the best value their position is expected to
                           still offer at that pick) instead of raw VORP.
            my_picks_remaining: Picks the user still has including this one;
                           gates K/DST to the final rounds when known.

        Returns:
            (DataFrame of recommended players, reasoning string)
        """
        avail = self.board.available.copy()
        if avail.empty:
            return pd.DataFrame(), "Draft board is empty."

        # Never recommend a position the roster shape can't start at all (e.g.
        # K/DST in a no-kicker Sleeper league) -- those players carry NaN VORP
        # by design (see replacement_ranks_for) and would otherwise poison
        # total_vorp the moment one gets drafted.
        elig = draftable_positions(self.board.roster_config)
        if "position" in avail.columns:
            avail = avail[avail["position"].astype(str).str.upper().isin(elig)]
        if avail.empty:
            return pd.DataFrame(), "No draftable players remain."

        needs = self.board.remaining_needs()
        my_picks = self.board.my_pick_count()
        picks_taken = self.board.picks_taken()

        reasoning_parts = []
        avail_all = avail  # unfiltered pool — scarcity alerts read the real board

        # Starters-first hard rule (2026-08-23 ESPN mock: the soft need-boost let
        # the advisor draft 2 QB / 3 TE / a K in R9 before its first WR in R10).
        # While any QB/RB/WR/TE/FLEX starter is open, a position whose starter
        # (+FLEX for RB/WR) slots are already full is off the board entirely, and
        # K/DST wait until every skill starter is filled — and, when the number
        # of remaining picks is known, until the final rounds.
        if enforce_needs:
            rc0 = self.board.roster_config
            have0 = Counter(
                str(p.get("position", "")).upper() for p in self.board.my_roster
            )
            open_skill = sum(
                int(needs.get(p, 0)) for p in ("QB", "RB", "WR", "TE", "FLEX", "SFLEX")
            )
            blocked = set()
            if open_skill > 0:
                flex_n = int(rc0.get("FLEX", 0))
                sflex_n = int(rc0.get("SFLEX", 0))
                cap = {
                    "QB": int(rc0.get("QB", 0)) + sflex_n,
                    "TE": int(rc0.get("TE", 0)) + sflex_n,
                    "RB": int(rc0.get("RB", 0)) + flex_n + sflex_n,
                    "WR": int(rc0.get("WR", 0)) + flex_n + sflex_n,
                }
                blocked = {p for p, c in cap.items() if have0.get(p, 0) >= c}
                blocked |= {"K", "DST"}
            # House rule (user, 2026-08-23): never roster a 2nd QB in a 1-QB
            # league — a backup QB never starts; that bench slot is RB/WR depth.
            if int(rc0.get("SFLEX", 0)) == 0 and have0.get("QB", 0) >= int(
                rc0.get("QB", 0)
            ) > 0:
                blocked.add("QB")
            kd_open = int(needs.get("K", 0)) + int(needs.get("DST", 0))
            force_kd = False
            if my_picks_remaining is not None and kd_open > 0:
                if my_picks_remaining > kd_open + 1:
                    blocked |= {"K", "DST"}
                elif my_picks_remaining <= kd_open:
                    # Only the K/DST picks are left — fill them now, whatever
                    # VORP says about one more bench RB.
                    force_kd = True
            filtered = avail[~avail["position"].isin(blocked)]
            if not filtered.empty:
                avail = filtered
                if blocked & {"QB", "RB", "WR", "TE"}:
                    reasoning_parts.append(
                        "starters first: holding "
                        + "/".join(sorted(blocked & {"QB", "RB", "WR", "TE"}))
                    )

        # Positional scarcity alerts
        scarcity = self._scarcity_alerts(avail_all)
        reasoning_parts.extend(scarcity)

        # Score each available player by VORP — value over replacement, not raw
        # points. Raw points over-value QBs in PPR (a QB's 350 pts dwarf a WR's
        # 300, yet the QB's marginal value over a streamer is tiny). VORP already
        # encodes positional scarcity, so it is the correct draft-day signal.
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in avail.columns
            else "projected_points"
        )
        score_col = "vorp" if "vorp" in avail.columns else pts_col
        avail["recommendation_score"] = avail[score_col].fillna(0).astype(float)

        # Opportunity cost (2026-08-23 lesson): score = value now minus the best
        # value this position is expected to still offer at my NEXT pick, via
        # the ADP-survival walk in draft_availability. Raw VORP told us to take
        # a WR whose tier was still 8-deep at the next turn over a QB tier about
        # to vanish. With no next pick (queue building, manual) this degrades to
        # plain VORP.
        avail["expected_next_vorp"] = np.nan
        avail["opportunity_cost"] = np.nan
        if (
            next_pick_no is not None
            and score_col == "vorp"
            and "adp_rank" in avail.columns
        ):
            expected = expected_best_vorp_at_pick(avail, float(next_pick_no))
            if expected:
                avail["expected_next_vorp"] = (
                    avail["position"].map(expected).astype(float).round(1)
                )
                avail["opportunity_cost"] = (
                    avail["vorp"].fillna(0).astype(float)
                    - avail["expected_next_vorp"].fillna(0.0)
                ).round(1)
                avail["recommendation_score"] = avail["opportunity_cost"]
                reasoning_parts.append(f"scored by cost of waiting to pick {next_pick_no}")

        # Nudge toward unfilled STARTING slots so the board builds a legal lineup
        # rather than pure best-available. Modest vs VORP's spread (~200) — a
        # tiebreaker that gets you your QB/TE on time, never an override.
        # An open STARTER slot must outweigh the +/-6 ADP value-tier nudge and
        # the ~0 opportunity costs of a replacement-level pool — at pick 62 of
        # the 2026-08-23 mock a bench RB ("undervalued" by ADP) outranked the
        # WR2 the lineup still needed.
        for pos, count_needed in needs.items():
            if count_needed > 0 and pos in ("QB", "RB", "WR", "TE"):
                boost = min(count_needed * 20, 40)
                avail.loc[avail["position"] == pos, "recommendation_score"] += boost

        if enforce_needs and force_kd:
            open_kd = {p for p in ("K", "DST") if int(needs.get(p, 0)) > 0}
            avail.loc[avail["position"].isin(open_kd), "recommendation_score"] += 1000
            reasoning_parts.append("final picks: fill " + "/".join(sorted(open_kd)))

        # FLEX slots still open → gently favor flex-eligible (RB/WR/TE).
        flex_need = needs.get("FLEX", 0)
        if flex_need > 0:
            avail.loc[
                avail["position"].isin(FLEX_ELIGIBLE), "recommendation_score"
            ] += min(flex_need * 3, 9)

        # ADP value tiers: reward fallers, fade reaches.
        if "value_tier" in avail.columns:
            avail.loc[avail["value_tier"] == "undervalued", "recommendation_score"] += 6
            avail.loc[avail["value_tier"] == "overvalued", "recommendation_score"] -= 6

        # Positional saturation: VORP alone hoards a deep position (e.g. 6 TEs) — it
        # has no roster sense. Past a sane per-position roster cap, extra depth is
        # unstartable, so escalate a penalty. QB/TE depth (you start one) is devalued
        # hardest; RB/WR carry flex + bye/injury depth. Soft, not a wall — a massive
        # faller can still overcome it.
        rc = self.board.roster_config
        base = {p: int(rc.get(p, 0)) for p in ("QB", "RB", "WR", "TE")}
        flex_total = int(rc.get("FLEX", 0))
        sflex_total = int(rc.get("SFLEX", 0))
        pos_cap = {
            "QB": base["QB"] + sflex_total + 1,
            "TE": base["TE"] + 1,
            "RB": base["RB"] + flex_total + 2,
            "WR": base["WR"] + flex_total + 2,
            # K/DST have no bench value in practice -- cap at exactly the
            # roster's slot count (0 when the league has none, e.g. K in
            # sleeper_gentlemen/sleeper_mahomos; the elig filter above already
            # keeps those off the board, so this is belt-and-suspenders).
            "K": int(rc.get("K", 0)),
            "DST": int(rc.get("DST", 0)),
        }
        have = Counter(str(p.get("position", "")).upper() for p in self.board.my_roster)
        # A backup QB/TE (starter already rostered, no superflex) is a bye-week
        # luxury — bench RB/WR depth starts games. Mild, so a true faller still wins.
        if sflex_total == 0:
            for pos in ("QB", "TE"):
                if have.get(pos, 0) >= base[pos] > 0:
                    avail.loc[avail["position"] == pos, "recommendation_score"] -= 20
        for pos in ("QB", "RB", "WR", "TE", "K", "DST"):
            over = have.get(pos, 0) - pos_cap[pos]
            if over >= 0:
                # K/DST carry ~zero bench value (unlike a backup QB/TE), so
                # once the roster's single slot is filled the penalty must
                # dominate any remaining VORP spread rather than just taper
                # it -- otherwise a still-decent kicker keeps outscoring a
                # deeply-negative-VORP skill player late in the draft.
                if pos in ("K", "DST"):
                    unit = 1000
                elif pos in ("QB", "TE"):
                    # A 3rd QB/TE (1-QB/1-TE leagues) is never startable; in a
                    # depleted late pool every RB/WR carries deeply negative VORP
                    # too, so a mild taper still lost to a TE3 (v8.3 sim). Make
                    # it decisive — bench depth belongs to RB/WR (byes/injuries).
                    unit = 400
                else:
                    unit = 25
                avail.loc[avail["position"] == pos, "recommendation_score"] -= unit * (
                    over + 1
                )

        recs = avail.sort_values("recommendation_score", ascending=False).head(top_n)

        # Build reasoning string
        needs_str = (
            ", ".join(f"{p}×{n}" for p, n in needs.items() if n > 0) or "roster full"
        )
        reasoning_parts.insert(0, f"Remaining needs: {needs_str}")
        reasoning = " | ".join(reasoning_parts)

        return recs.reset_index(drop=True), reasoning

    def build_queue(self, depth: int = 12, **turn) -> List[Dict]:
        """Need-aware ranked draft queue via simulate-and-fill.

        Repeatedly takes the top recommendation and *tentatively* rosters it so
        roster needs + positional saturation update between entries — yielding an
        ordered queue that fills the starting lineup in priority order rather than
        a flat best-available list (which would stack one position). The board is
        restored before returning, so this is side-effect free and safe to call on
        every poll of a live draft.

        Returns a list of ``{player_name, position, team, projected_season_points,
        vorp}`` dicts, highest priority first. Paste into a Sleeper queue so the
        platform auto-drafts the best *available* entry on the user's clock.
        """
        board = self.board
        saved_roster = list(board.my_roster)
        saved_available = board.available.copy()
        queue: List[Dict] = []
        try:
            for _ in range(max(0, depth)):
                # ``turn`` (next_pick_no / my_picks_remaining) makes the queue
                # follow cost-of-waiting, exactly like the on-clock recs.
                recs, _ = self.recommend(top_n=1, **turn)
                if recs.empty:
                    break
                row = recs.iloc[0]
                queue.append(
                    {
                        "player_name": row.get("player_name"),
                        "position": row.get("position"),
                        "team": row.get("team", row.get("recent_team")),
                        "projected_season_points": row.get("projected_season_points"),
                        "vorp": row.get("vorp"),
                    }
                )
                key = row.get("player_id") or row.get("player_name")
                board.draft_player(str(key), by_me=True)
        finally:
            board.my_roster = saved_roster
            board.available = saved_available
        return queue

    def _scarcity_alerts(self, avail: pd.DataFrame) -> List[str]:
        """Detect positions with low remaining top-tier talent."""
        alerts = []
        SCARCITY_THRESHOLDS = {"QB": 5, "RB": 10, "WR": 12, "TE": 5}
        for pos, threshold in SCARCITY_THRESHOLDS.items():
            pos_avail = avail[avail["position"] == pos]
            if len(pos_avail) <= threshold:
                alerts.append(f"SCARCITY: Only {len(pos_avail)} {pos}s left!")
        return alerts

    def undervalued_players(self, top_n: int = 10) -> pd.DataFrame:
        """Return available players where model rank significantly beats ADP."""
        avail = self.board.available.copy()
        if "value_tier" not in avail.columns:
            return pd.DataFrame()
        return (
            avail[avail["value_tier"] == "undervalued"]
            .sort_values("adp_diff", ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )

    def overvalued_players(self, top_n: int = 10) -> pd.DataFrame:
        """Return available players where ADP is well above model rank."""
        avail = self.board.available.copy()
        if "value_tier" not in avail.columns:
            return pd.DataFrame()
        return (
            avail[avail["value_tier"] == "overvalued"]
            .sort_values("adp_diff")
            .head(top_n)
            .reset_index(drop=True)
        )

    def position_breakdown(self) -> pd.DataFrame:
        """Summary of remaining available players by position."""
        avail = self.board.available
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in avail.columns
            else "projected_points"
        )
        return (
            avail.groupby("position")
            .agg(
                count=("position", "count"),
                avg_pts=(pts_col, "mean"),
                top_pts=(pts_col, "max"),
            )
            .round(1)
            .reset_index()
            .sort_values("avg_pts", ascending=False)
        )

    def waiver_recommendations(
        self,
        rostered_players: Optional[List[str]] = None,
        position: Optional[str] = None,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """
        Return top unrostered players by projected points for waiver wire consideration.

        Players currently on the draft board's available list are treated as unrostered
        unless their name or player_id appears in ``rostered_players``.

        Args:
            rostered_players: List of player names or player_ids already on a roster.
                              When provided, these players are excluded from results.
            position:         Optional position filter (e.g. 'WR'). Pass None for all.
            top_n:            Number of players to return (default 10).

        Returns:
            DataFrame of top waiver-wire targets sorted by projected points descending.

        Example:
            >>> recs = advisor.waiver_recommendations(position='WR', top_n=5)
        """
        avail = self.board.available.copy()

        if rostered_players:
            # Normalise to lowercase for case-insensitive matching
            rostered_lower = {r.lower() for r in rostered_players}
            name_mask = pd.Series(False, index=avail.index)
            id_mask = pd.Series(False, index=avail.index)

            if "player_name" in avail.columns:
                name_mask = avail["player_name"].str.lower().isin(rostered_lower)
            if "player_id" in avail.columns:
                id_mask = avail["player_id"].str.lower().isin(rostered_lower)

            avail = avail[~(name_mask | id_mask)]

        if position:
            avail = avail[avail["position"] == position.upper()]

        pts_col = (
            "projected_season_points"
            if "projected_season_points" in avail.columns
            else "projected_points"
        )
        return (
            avail.sort_values(pts_col, ascending=False)
            .head(top_n)
            .reset_index(drop=True)
        )


# ---------------------------------------------------------------------------
# Auction Draft Board
# ---------------------------------------------------------------------------


class AuctionDraftBoard(DraftBoard):
    """
    Extends DraftBoard to support auction-style fantasy drafts.

    Each player is won by bidding rather than picking by round/position.
    Tracks per-player costs, the user's remaining budget, and provides
    value-per-dollar analysis.
    """

    def __init__(
        self,
        players: pd.DataFrame,
        roster_format: str = "standard",
        n_teams: int = 12,
        budget_per_team: int = 200,
    ):
        """
        Args:
            players:         Enriched projection DataFrame (from compute_value_scores).
            roster_format:   One of the keys in config.ROSTER_CONFIGS.
            n_teams:         Number of teams in the league.
            budget_per_team: Starting budget for each team (default 200).
        """
        super().__init__(players, roster_format=roster_format, n_teams=n_teams)
        self.budget_per_team: int = budget_per_team
        self.my_budget_remaining: int = budget_per_team
        self.player_costs: Dict[str, int] = {}  # player_name -> cost paid by user

        # Pre-compute league-average projected pts/dollar for value threshold
        pts_col = (
            "projected_season_points"
            if "projected_season_points" in players.columns
            else "projected_points"
        )
        total_pts = players[pts_col].fillna(0).sum()
        total_budget = budget_per_team * n_teams
        self._league_avg_pts_per_dollar: float = (
            total_pts / total_budget if total_budget > 0 else 1.0
        )

    # -----------------------------------------------------------------------
    # Nomination & bidding
    # -----------------------------------------------------------------------

    def nominate_player(self, name: str) -> Optional[pd.Series]:
        """
        Find and return player info for a nominated player.

        Args:
            name: Full or partial player name to search for.

        Returns:
            Player row as a pd.Series, or None if not found.
        """
        if "player_name" not in self.available.columns:
            logger.warning("No player_name column on auction board")
            return None

        mask = (
            self.available["player_name"]
            .str.lower()
            .str.contains(name.lower(), na=False)
        )
        if not mask.any():
            logger.warning(f"Player '{name}' not found for nomination")
            return None

        return self.available[mask].iloc[0]

    def win_bid(self, name: str, cost: int, by_me: bool = True) -> Dict:
        """
        Record that a player was won at auction.

        Args:
            name:  Full or partial player name.
            cost:  Dollar amount paid.
            by_me: True if the user won this player; False if an opponent won them.

        Returns:
            Player row as dict, or {} if not found.
        """
        if cost < 1:
            logger.warning(f"Auction cost must be >= $1, got {cost}")
            cost = 1

        player = self.draft_by_name(name, by_me=by_me)
        if not player:
            return {}

        player_name = player.get("player_name", name)

        if by_me:
            if cost > self.my_budget_remaining:
                logger.warning(
                    f"Bid ${cost} exceeds remaining budget ${self.my_budget_remaining}"
                )
            self.my_budget_remaining = max(0, self.my_budget_remaining - cost)
            self.player_costs[player_name] = cost
            logger.info(
                f"You won {player_name} for ${cost}. Budget remaining: ${self.my_budget_remaining}"
            )
        else:
            logger.info(f"Opponent won {player_name} for ${cost}")

        return player

    def value_vs_cost(self, name: str, cost: int) -> Dict:
        """
        Analyse whether a player represents good value at a given price.

        Args:
            name: Full or partial player name.
            cost: Hypothetical or actual cost to evaluate.

        Returns:
            Dict with keys:
                player_name     - resolved player name
                projected_pts   - model projected season points
                cost            - the cost passed in
                pts_per_dollar  - projected_pts / cost
                fair_value_cost - estimated fair cost based on league avg $/pt
                is_overpay      - True if cost exceeds fair_value_cost by >20%
                overpay_pct     - percentage over/under fair value (positive = overpay)
        """
        player_row = self.nominate_player(name)
        if player_row is None:
            return {}

        pts_col = (
            "projected_season_points"
            if "projected_season_points" in player_row.index
            else "projected_points"
        )
        projected_pts = float(player_row.get(pts_col, 0) or 0)
        pts_per_dollar = projected_pts / max(cost, 1)
        fair_value_cost = (
            projected_pts / self._league_avg_pts_per_dollar
            if self._league_avg_pts_per_dollar > 0
            else 0
        )
        overpay_pct = (
            ((cost - fair_value_cost) / fair_value_cost * 100)
            if fair_value_cost > 0
            else 0.0
        )
        is_overpay = overpay_pct > 20.0

        return {
            "player_name": player_row.get("player_name", name),
            "projected_pts": round(projected_pts, 1),
            "cost": cost,
            "pts_per_dollar": round(pts_per_dollar, 2),
            "fair_value_cost": round(fair_value_cost, 1),
            "is_overpay": is_overpay,
            "overpay_pct": round(overpay_pct, 1),
        }

    def budget_summary(self) -> Dict:
        """
        Return current budget health and spending pace metrics.

        Returns:
            Dict with keys:
                budget_total         - starting budget
                budget_remaining     - dollars left
                budget_spent         - dollars spent so far
                roster_spots_filled  - number of players on user's roster
                roster_spots_total   - total roster slots (from roster config)
                spots_remaining      - unfilled roster spots
                implied_per_spot     - budget_remaining / spots_remaining (or 0 if full)
        """
        roster_spots_total = sum(self.roster_config.values())
        roster_spots_filled = len(self.my_roster)
        spots_remaining = max(0, roster_spots_total - roster_spots_filled)
        implied_per_spot = (
            self.my_budget_remaining / spots_remaining if spots_remaining > 0 else 0
        )
        return {
            "budget_total": self.budget_per_team,
            "budget_remaining": self.my_budget_remaining,
            "budget_spent": self.budget_per_team - self.my_budget_remaining,
            "roster_spots_filled": roster_spots_filled,
            "roster_spots_total": roster_spots_total,
            "spots_remaining": spots_remaining,
            "implied_per_spot": round(implied_per_spot, 2),
        }


# ---------------------------------------------------------------------------
# Mock Draft Simulator
# ---------------------------------------------------------------------------

# Draft grade breakpoints: VORP vs. expected VORP for pick position
_GRADE_THRESHOLDS = [
    (0.15, "A"),  # >15% above expected
    (-0.05, "B"),  # within 5% below expected
    (-0.20, "C"),  # 6-20% below expected
]


def _pick_grade(actual_vorp: float, expected_vorp: float) -> str:
    """
    Assign a letter grade comparing actual total VORP to the expected baseline.

    Args:
        actual_vorp:   Total VORP summed across the user's drafted roster.
        expected_vorp: Baseline VORP for perfectly ADP-optimal picks in those slots.

    Returns:
        Grade string: 'A', 'B', 'C', or 'D'.
    """
    if expected_vorp <= 0:
        return "B"
    ratio = (actual_vorp - expected_vorp) / abs(expected_vorp)
    for threshold, grade in _GRADE_THRESHOLDS:
        if ratio >= threshold:
            return grade
    return "D"


class MockDraftSimulator:
    """
    Simulates a full snake draft without user interaction.

    Opponents pick the best available player by ADP rank, with a configurable
    amount of randomness to mimic realistic draft variance. On the user's turns,
    the DraftAdvisor's top recommendation is used.
    """

    # A bot never drafts a 3rd QB (starters + sflex + 1 bench stash) before
    # this round -- streaming a late-round QB2 is realistic, hoarding QBs in
    # round 4 is not.
    _QB_DEPTH_ROUND = 10

    def __init__(
        self,
        board: DraftBoard,
        user_pick: int,
        n_teams: int,
        randomness: int = 3,
        draft_type: str = "snake",
        behavior: Optional[Dict] = None,
    ):
        """
        Args:
            board:      A fresh DraftBoard instance (will be mutated in-place).
            user_pick:  The user's draft position (1-based).
            n_teams:    Total number of teams in the league.
            randomness: Widens the pool of candidates a bot draws from near the
                        top of the ADP/model-rank-sorted board (``2*randomness+1``
                        candidates, floor 8). The actual pick within that pool is
                        an ADP-noise weighted draw (see ``behavior``), not a flat
                        random offset -- kept as a tuning knob for backward
                        compatibility with existing callers.
            draft_type: ``"snake"`` (serpentine, default) or ``"linear"`` (same
                        slot order every round, as Sleeper dynasty/rookie drafts
                        use). Controls which overall picks belong to the user.
            behavior:   Optional tuning dict for opponent pick realism:
                        ``run_factor`` (default 1.5) -- weight multiplier applied
                        to a position when >=2 of the last 4 picks (any team)
                        shared it, simulating a positional run feeding on itself.
                        ``temperature`` (default 3.0) -- softmax-style temperature
                        for the ADP-noise draw; lower = closer to strict ADP,
                        higher = more reaches/slides.
        """
        if user_pick < 1 or user_pick > n_teams:
            raise ValueError(
                f"user_pick must be between 1 and {n_teams}, got {user_pick}"
            )

        self.board = board
        self.user_pick = user_pick
        self.n_teams = n_teams
        self.randomness = max(0, randomness)
        self.draft_type = "linear" if str(draft_type).lower() == "linear" else "snake"

        self.behavior: Dict[str, float] = {"run_factor": 1.5, "temperature": 3.0}
        if behavior:
            self.behavior.update(behavior)

        # Per-opponent-slot roster tracking (position strings only -- enough
        # to enforce depth caps) and a chronological log of recent pick
        # positions (any team) for positional-run detection.
        self._opp_rosters: Dict[int, List[str]] = {}
        self._recent_positions: List[str] = []
        self._total_rounds: int = max(1, sum(self.board.roster_config.values()))

        pts_col = (
            "projected_season_points"
            if "projected_season_points" in board.available.columns
            else "projected_points"
        )
        self._pts_col = pts_col

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _next_user_pick(self, pick_number: int, total_picks: int) -> Optional[int]:
        """The user's next overall pick strictly after ``pick_number`` (None if done)."""
        for p in range(pick_number + 1, total_picks + 1):
            if self._is_user_turn(p):
                return p
        return None

    def _user_picks_remaining(self, pick_number: int, total_picks: int) -> int:
        """User picks from ``pick_number`` (inclusive) to the end of the draft."""
        return sum(
            1 for p in range(pick_number, total_picks + 1) if self._is_user_turn(p)
        )

    def _is_user_turn(self, pick_number: int) -> bool:
        """Return True when ``pick_number`` is the user's slot for this draft type.

        Linear: the user's slot picks at the same position every round. Snake:
        the order reverses on even rounds (serpentine).
        """
        pick_in_round = (pick_number - 1) % self.n_teams + 1
        if self.draft_type == "linear":
            return pick_in_round == self.user_pick
        round_number = (pick_number - 1) // self.n_teams + 1
        if round_number % 2 == 1:
            return pick_in_round == self.user_pick
        return (self.n_teams - pick_in_round + 1) == self.user_pick

    def _slot_for_pick(self, pick_number: int) -> int:
        """1-based team slot on the clock for ``pick_number`` (any team, not just
        the user) -- same snake/linear math as :meth:`_is_user_turn`."""
        pick_in_round = (pick_number - 1) % self.n_teams + 1
        if self.draft_type == "linear":
            return pick_in_round
        round_number = (pick_number - 1) // self.n_teams + 1
        if round_number % 2 == 1:
            return pick_in_round
        return self.n_teams - pick_in_round + 1

    def _bot_max_for_position(self, position: str, round_number: int) -> int:
        """Roster depth cap a bot will draft to at ``position`` this round.

        Mirrors :meth:`DraftAdvisor.recommend`'s own positional-saturation
        cap so opponents behave like a plausible human roster builder:
        starters + a modest bench, K/DST capped at one apiece, and a 3rd QB
        withheld until the streaming rounds (see ``_QB_DEPTH_ROUND``).
        """
        rc = self.board.roster_config
        base = {p: int(rc.get(p, 0)) for p in ("QB", "RB", "WR", "TE")}
        flex = int(rc.get("FLEX", 0))
        sflex = int(rc.get("SFLEX", 0))
        if position == "QB":
            cap = base["QB"] + sflex + 1
            return cap + 1 if round_number > self._QB_DEPTH_ROUND else cap
        if position == "TE":
            return base["TE"] + 2
        if position == "RB":
            return base["RB"] + flex + 3
        if position == "WR":
            return base["WR"] + flex + 3
        if position == "K":
            return int(rc.get("K", 0))
        if position == "DST":
            return int(rc.get("DST", 0))
        return 99

    def _run_position(self) -> Optional[str]:
        """Position driving a positional run: >=2 of the last 4 picks (any
        team) sharing a position, returned uppercase, or ``None``."""
        recent = self._recent_positions[-4:]
        if len(recent) < 2:
            return None
        pos, count = Counter(recent).most_common(1)[0]
        return pos if count >= 2 else None

    def record_pick(self, position: Optional[str]) -> None:
        """Record a drafted player's position for positional-run tracking.

        Opponent picks record themselves inside :meth:`simulate_opponent_pick`.
        Callers that draft the user's pick directly (:meth:`run_full_simulation`,
        the ``/draft/mock/pick`` endpoint) should call this too so runs are
        detected across the whole draft, not just bot picks.
        """
        if position:
            self._recent_positions.append(str(position).upper())

    # -----------------------------------------------------------------------
    # Simulation actions
    # -----------------------------------------------------------------------

    def simulate_opponent_pick(self, pick_number: int) -> Optional[str]:
        """
        Select an opponent's pick: roster-need aware, run-amplified, ADP-noise
        weighted.

        Replaces naive "closest-to-ADP-rank +/- randomness" selection with a
        behavior model closer to a real draft room:

        - Roster limits: a bot never exceeds a sane depth cap per position
          (:meth:`_bot_max_for_position`) and is nudged to fill K/DST in the
          closing rounds instead of hoarding skill-position depth forever.
        - Positional runs: if 2+ of the last 4 picks (any team) shared a
          position, that position's weight is multiplied by
          ``behavior["run_factor"]`` for this pick -- runs feed on themselves.
        - ADP noise: rather than a hard rank offset, the pick is drawn from
          the top of the ADP/model-rank-sorted board with probability
          ``exp(-rank_gap / behavior["temperature"])`` -- most picks track
          ADP closely, with occasional reaches/slides.

        Args:
            pick_number: Current overall pick number (1-based).

        Returns:
            Player name string if a pick was made, or None if the board is empty.
        """
        avail = self.board.available
        if avail.empty:
            return None

        # Never let an opponent draft a position the roster shape can't
        # start at all (e.g. K/DST in a no-kicker Sleeper league) -- keeps
        # the "every position capped out" stall fallback below from ever
        # reintroducing an undraftable position into the candidate pool.
        elig = draftable_positions(self.board.roster_config)
        if "position" in avail.columns:
            avail = avail[avail["position"].astype(str).str.upper().isin(elig)]
        if avail.empty:
            return None

        # Sort by adp_rank if present, else fall back to model_rank
        sort_col = (
            "adp_rank"
            if ("adp_rank" in avail.columns and avail["adp_rank"].notna().any())
            else "model_rank"
        )
        pool = avail.sort_values(sort_col, na_position="last").reset_index(drop=True)

        slot = self._slot_for_pick(pick_number)
        round_number = (pick_number - 1) // self.n_teams + 1
        roster = self._opp_rosters.setdefault(slot, [])
        pos_counts = Counter(roster)

        positions_upper = pool["position"].astype(str).str.upper()
        legal = positions_upper.map(
            lambda pos: pos_counts.get(pos, 0)
            < self._bot_max_for_position(pos, round_number)
        )
        candidates = pool[legal.to_numpy()]
        if candidates.empty:
            candidates = pool  # every position capped out -- don't stall the draft

        # Nudge K/DST onto the board in the closing rounds if still unfilled,
        # like a real human finally grabbing their kicker/defense.
        rc = self.board.roster_config
        rounds_left = self._total_rounds - round_number
        forced_pos: Optional[str] = None
        if rc.get("K", 0) > 0 and pos_counts.get("K", 0) == 0 and rounds_left <= 1:
            forced_pos = "K"
        elif (
            rc.get("DST", 0) > 0 and pos_counts.get("DST", 0) == 0 and rounds_left <= 2
        ):
            forced_pos = "DST"
        if forced_pos:
            forced = candidates[
                candidates["position"].astype(str).str.upper() == forced_pos
            ]
            if not forced.empty:
                candidates = forced

        top_k = min(len(candidates), max(self.randomness * 2 + 1, 8))
        top_candidates = candidates.head(top_k).reset_index(drop=True)
        if top_candidates.empty:
            return None

        temperature = max(float(self.behavior.get("temperature", 3.0)), 0.1)
        weights = [float(np.exp(-i / temperature)) for i in range(len(top_candidates))]

        run_pos = self._run_position()
        if run_pos:
            run_factor = float(self.behavior.get("run_factor", 1.5))
            weights = [
                w * run_factor if str(p).upper() == run_pos else w
                for w, p in zip(weights, top_candidates["position"])
            ]

        idx = random.choices(range(len(top_candidates)), weights=weights, k=1)[0]
        player_row = top_candidates.iloc[idx]

        player_id = player_row.get("player_id", player_row.get("player_name", ""))
        self.board.draft_player(str(player_id), by_me=False)

        pos = str(player_row.get("position", "")).upper()
        roster.append(pos)
        self._recent_positions.append(pos)

        return str(player_row.get("player_name", player_id))

    def run_full_simulation(
        self, advisor: DraftAdvisor, rounds: Optional[int] = None
    ) -> Dict:
        """
        Run all rounds of the draft to completion.

        On the user's turns, the top recommendation from ``advisor.recommend()``
        is drafted automatically and the reasoning + runner-up alternatives are
        captured on the pick log. Opponents use ADP-based selection with
        configurable randomness.

        Args:
            advisor: A DraftAdvisor wrapping the same DraftBoard as this simulator.
            rounds:  Number of rounds to run. Defaults to the full roster size
                     (``sum(roster_config.values())``); pass e.g. 4 for a Sleeper
                     dynasty rookie draft.

        Returns:
            Summary dict with keys:
                picks          - list of dicts per pick: round, pick, team, player_name, position, adp, pts
                my_roster      - list of player dicts on the user's final roster
                total_pts      - sum of projected season points on user's roster
                total_vorp     - sum of VORP on user's roster
                expected_vorp  - baseline VORP for the same pick slots (ADP-optimal)
                draft_grade    - letter grade 'A'-'D'
        """
        pts_col = self._pts_col
        rounds = (
            rounds if rounds is not None else sum(self.board.roster_config.values())
        )
        # Keep the bots' late-round K/DST nudge in sync with the actual
        # length of this run (may differ from the __init__-time estimate,
        # e.g. a 4-round rookie draft).
        self._total_rounds = max(1, rounds)
        total_picks = self.n_teams * rounds
        picks_log: List[Dict] = []

        # Snapshot expected VORP: what an ADP-optimal drafter would accumulate
        # in the user's exact pick slots across all rounds.
        expected_vorp = self._estimate_expected_vorp(total_picks)

        pick_number = 0

        while pick_number < total_picks and not self.board.available.empty:
            pick_number += 1
            round_number = (pick_number - 1) // self.n_teams + 1

            if self._is_user_turn(pick_number):
                recs, reasoning = advisor.recommend(
                    top_n=5,
                    next_pick_no=self._next_user_pick(pick_number, total_picks),
                    my_picks_remaining=self._user_picks_remaining(
                        pick_number, total_picks
                    ),
                )
                if recs.empty:
                    logger.warning(
                        f"Advisor returned no recommendations at pick {pick_number}"
                    )
                    continue

                # Runner-up alternatives the co-pilot considered (for the report).
                alternatives = [
                    {
                        "player_name": r.get("player_name"),
                        "position": r.get("position"),
                        "vorp": r.get("vorp"),
                    }
                    for _, r in recs.iloc[1:].iterrows()
                ]
                top_pick = recs.iloc[0]
                player_id = top_pick.get("player_id", top_pick.get("player_name", ""))
                player_result = self.board.draft_player(str(player_id), by_me=True)
                if not player_result:
                    continue

                player_name = player_result.get("player_name", str(player_id))
                self.record_pick(player_result.get("position"))
                picks_log.append(
                    {
                        "round": round_number,
                        "pick": pick_number,
                        "team": "YOU",
                        "player_name": player_name,
                        "position": player_result.get("position", "?"),
                        "adp": player_result.get("adp_rank", "N/A"),
                        "pts": round(float(player_result.get(pts_col, 0) or 0), 1),
                        "vorp": player_result.get("vorp", "N/A"),
                        "reasoning": reasoning,
                        "alternatives": alternatives,
                    }
                )
            else:
                player_name = self.simulate_opponent_pick(pick_number)
                if player_name is None:
                    continue

                # Retrieve position from all_players for the log
                pos = "?"
                adp_val: object = "N/A"
                if "player_name" in self.board.all_players.columns:
                    match = self.board.all_players[
                        self.board.all_players["player_name"] == player_name
                    ]
                    if not match.empty:
                        pos = match.iloc[0].get("position", "?")
                        adp_val = match.iloc[0].get("adp_rank", "N/A")

                picks_log.append(
                    {
                        "round": round_number,
                        "pick": pick_number,
                        "team": "OPP",
                        "player_name": player_name,
                        "position": pos,
                        "adp": adp_val,
                        "pts": None,
                    }
                )

        my_roster = self.board.my_roster
        total_pts = sum(float(p.get(pts_col, 0) or 0) for p in my_roster)
        total_vorp = sum(float(p.get("vorp", 0) or 0) for p in my_roster)
        draft_grade = _pick_grade(total_vorp, expected_vorp)

        return {
            "picks": picks_log,
            "my_roster": my_roster,
            "total_pts": round(total_pts, 1),
            "total_vorp": round(total_vorp, 1),
            "expected_vorp": round(expected_vorp, 1),
            "draft_grade": draft_grade,
        }

    def _estimate_expected_vorp(self, total_picks: int) -> float:
        """
        Estimate the VORP a perfectly ADP-optimal user would accumulate
        across their draft slots.

        This uses a snapshot of the current (pre-draft) board sorted by ADP/model rank
        and assumes ADP-optimal picks at every user slot, then sums their VORP values.

        Args:
            total_picks: Total picks in the draft.

        Returns:
            Sum of VORP for ADP-best players at user's pick slots.
        """
        if "vorp" not in self.board.available.columns:
            return 0.0

        # An ADP-optimal drafter would never take a position the roster shape
        # can't start at all (e.g. K in a no-kicker Sleeper league) -- those
        # rows carry NaN vorp by design (replacement_ranks_for), and one
        # landing on a user pick slot here would NaN out the whole baseline,
        # producing a bogus 'D' grade downstream (nan <= 0 is False, so
        # _pick_grade falls through every threshold to "D").
        pool = self.board.available
        elig = draftable_positions(self.board.roster_config)
        if "position" in pool.columns:
            pool = pool[pool["position"].astype(str).str.upper().isin(elig)]

        sort_col = (
            "adp_rank"
            if ("adp_rank" in pool.columns and pool["adp_rank"].notna().any())
            else "model_rank"
        )
        sorted_pool = pool.sort_values(sort_col, na_position="last").reset_index(
            drop=True
        )

        # Simulate which overall pick numbers belong to the user
        user_pick_numbers = []
        for pick_num in range(1, total_picks + 1):
            if self._is_user_turn(pick_num):
                user_pick_numbers.append(pick_num)

        # The user gets picks at 0-based indices: pick_number - 1 into the sorted pool
        expected = 0.0
        for pick_num in user_pick_numbers:
            idx = pick_num - 1
            if idx < len(sorted_pool):
                expected += float(sorted_pool.iloc[idx].get("vorp", 0) or 0)

        return expected
