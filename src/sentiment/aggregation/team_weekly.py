"""
Team-level weekly sentiment aggregation — Gold layer.

Reads Gold player-level sentiment data, groups by team, and computes
team-wide sentiment scores and multipliers. Also detects team mentions
in Silver signal excerpts for team-specific sentiment signals.

The output is consumed by ``generate_predictions.py`` as a post-prediction
edge modifier (not a model input).

Public API
----------
>>> aggregator = TeamWeeklyAggregator()
>>> df = aggregator.aggregate(season=2026, week=1)
>>> df[["team", "team_sentiment_multiplier"]].head()
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_GOLD_PLAYER_SENTIMENT_DIR = _PROJECT_ROOT / "data" / "gold" / "sentiment"
_GOLD_TEAM_SENTIMENT_DIR = _PROJECT_ROOT / "data" / "gold" / "sentiment" / "team_sentiment"

# Phase 72 EVT-02: non-player Silver path Phase 71 non_player_pending writes,
# routed by Plan 72-03 _route_non_player_items into per-team coach/team counts.
_SILVER_NON_PLAYER_PENDING_DIR = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_pending"
)

# Team sentiment multiplier range — tighter than player (0.70-1.15)
# because team-level signals are noisier.
_TEAM_MULT_MIN = 0.95
_TEAM_MULT_MAX = 1.05
_TEAM_MULT_NEUTRAL = 1.0

# Aggregation weights
_PLAYER_COMPONENT_WEIGHT = 0.6
_TEAM_MENTION_COMPONENT_WEIGHT = 0.4

# Sentiment edge weight: max adjustment is +/- 0.15 points on spread edge.
# The multiplier diff range is at most 0.10 (1.05 - 0.95), so
# SENTIMENT_EDGE_WEIGHT = 1.5 gives max 0.10 * 1.5 = 0.15.
SENTIMENT_EDGE_WEIGHT = 1.5

# ---------------------------------------------------------------------------
# NFL Team mapping — all 32 teams
# ---------------------------------------------------------------------------

# Canonical 3-letter abbreviations for all 32 NFL teams
_NFL_TEAMS: Dict[str, List[str]] = {
    "ARI": ["Arizona", "Cardinals", "Arizona Cardinals"],
    "ATL": ["Atlanta", "Falcons", "Atlanta Falcons"],
    "BAL": ["Baltimore", "Ravens", "Baltimore Ravens"],
    "BUF": ["Buffalo", "Bills", "Buffalo Bills"],
    "CAR": ["Carolina", "Panthers", "Carolina Panthers"],
    "CHI": ["Chicago", "Bears", "Chicago Bears"],
    "CIN": ["Cincinnati", "Bengals", "Cincinnati Bengals"],
    "CLE": ["Cleveland", "Browns", "Cleveland Browns"],
    "DAL": ["Dallas", "Cowboys", "Dallas Cowboys"],
    "DEN": ["Denver", "Broncos", "Denver Broncos"],
    "DET": ["Detroit", "Lions", "Detroit Lions"],
    "GB": ["Green Bay", "Packers", "Green Bay Packers"],
    "HOU": ["Houston", "Texans", "Houston Texans"],
    "IND": ["Indianapolis", "Colts", "Indianapolis Colts"],
    "JAX": ["Jacksonville", "Jaguars", "Jacksonville Jaguars"],
    "KC": ["Kansas City", "Chiefs", "Kansas City Chiefs"],
    "LAC": ["Los Angeles Chargers", "Chargers", "LA Chargers"],
    "LAR": ["Los Angeles Rams", "Rams", "LA Rams"],
    "LV": ["Las Vegas", "Raiders", "Las Vegas Raiders"],
    "MIA": ["Miami", "Dolphins", "Miami Dolphins"],
    "MIN": ["Minnesota", "Vikings", "Minnesota Vikings"],
    "NE": ["New England", "Patriots", "New England Patriots"],
    "NO": ["New Orleans", "Saints", "New Orleans Saints"],
    "NYG": ["New York Giants", "Giants", "NY Giants"],
    "NYJ": ["New York Jets", "Jets", "NY Jets"],
    "PHI": ["Philadelphia", "Eagles", "Philadelphia Eagles"],
    "PIT": ["Pittsburgh", "Steelers", "Pittsburgh Steelers"],
    "SEA": ["Seattle", "Seahawks", "Seattle Seahawks"],
    "SF": ["San Francisco", "49ers", "San Francisco 49ers"],
    "TB": ["Tampa Bay", "Buccaneers", "Tampa Bay Buccaneers", "Bucs"],
    "TEN": ["Tennessee", "Titans", "Tennessee Titans"],
    "WAS": ["Washington", "Commanders", "Washington Commanders"],
}

# Build the lookup dict: every name/abbreviation → canonical 3-letter code
TEAM_NAME_TO_ABBR: Dict[str, str] = {}
for abbr, aliases in _NFL_TEAMS.items():
    TEAM_NAME_TO_ABBR[abbr] = abbr
    for alias in aliases:
        TEAM_NAME_TO_ABBR[alias] = abbr

# Build regex patterns for team detection — word-boundary matching
# to avoid false positives (e.g., "car" matching "CAR").
# Sort by length descending so longer names match first.
_all_team_names = sorted(TEAM_NAME_TO_ABBR.keys(), key=len, reverse=True)
_TEAM_PATTERNS: List[tuple] = []
for name in _all_team_names:
    # Abbreviations (all-uppercase, <= 3 chars) use case-sensitive matching
    # to avoid false positives (e.g., "car" should NOT match "CAR").
    if name.isupper() and len(name) <= 3:
        _TEAM_PATTERNS.append((re.compile(r"\b" + re.escape(name) + r"\b"), TEAM_NAME_TO_ABBR[name]))
    else:
        _TEAM_PATTERNS.append((re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE), TEAM_NAME_TO_ABBR[name]))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def detect_teams_in_text(text: str) -> Set[str]:
    """Detect NFL team mentions in text using word-boundary regex.

    Args:
        text: Article or post text to scan.

    Returns:
        Set of canonical 3-letter team abbreviations found.
    """
    found: Set[str] = set()
    for pattern, abbr in _TEAM_PATTERNS:
        if pattern.search(text):
            found.add(abbr)
    return found


def team_sentiment_to_multiplier(score: float) -> float:
    """Convert a team sentiment score to a projection multiplier.

    Linear mapping:
      - score = -1.0 -> multiplier = 0.95
      - score =  0.0 -> multiplier = 1.00
      - score = +1.0 -> multiplier = 1.05

    Args:
        score: Team sentiment score, nominally in [-1.0, +1.0].

    Returns:
        Multiplier float clamped to [0.95, 1.05].
    """
    score = max(-1.0, min(1.0, float(score)))
    multiplier = _TEAM_MULT_NEUTRAL + score * (_TEAM_MULT_MAX - _TEAM_MULT_NEUTRAL)
    return round(max(_TEAM_MULT_MIN, min(_TEAM_MULT_MAX, multiplier)), 4)


def apply_team_sentiment_adjustment(
    predictions: pd.DataFrame,
    team_sentiment: pd.DataFrame,
) -> pd.DataFrame:
    """Apply team sentiment as a post-prediction edge adjustment.

    Computes a sentiment-based edge adjustment for each game based on
    the difference between home and away team sentiment multipliers.
    The adjustment is bounded to +/- 0.15 points maximum.

    This does NOT change model predictions — it adjusts the edge
    (which is already a comparison layer vs Vegas).

    Args:
        predictions: DataFrame with columns: home_team, away_team,
            spread_edge, total_edge.
        team_sentiment: DataFrame with columns: team,
            team_sentiment_multiplier.

    Returns:
        Copy of predictions with added columns: home_sentiment,
        away_sentiment, sentiment_adjustment, adjusted_spread_edge.
    """
    result = predictions.copy()

    # Build a lookup dict for team multipliers
    sentiment_lookup: Dict[str, float] = {}
    if not team_sentiment.empty and "team" in team_sentiment.columns:
        sentiment_lookup = dict(
            zip(team_sentiment["team"], team_sentiment["team_sentiment_multiplier"])
        )

    # Look up home and away team sentiment multipliers
    result["home_sentiment"] = result["home_team"].map(
        lambda t: sentiment_lookup.get(t, _TEAM_MULT_NEUTRAL)
    )
    result["away_sentiment"] = result["away_team"].map(
        lambda t: sentiment_lookup.get(t, _TEAM_MULT_NEUTRAL)
    )

    # Compute adjustment: (home_mult - away_mult) * SENTIMENT_EDGE_WEIGHT
    # Max diff is 0.10 (1.05 - 0.95), so max adjustment = 0.10 * 1.5 = 0.15
    raw_adjustment = (result["home_sentiment"] - result["away_sentiment"]) * SENTIMENT_EDGE_WEIGHT

    # Clamp to +/- 0.15 for safety
    result["sentiment_adjustment"] = raw_adjustment.clip(-0.15, 0.15)

    # Apply to spread edge
    result["adjusted_spread_edge"] = result["spread_edge"] + result["sentiment_adjustment"]

    return result


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class TeamWeeklyAggregator:
    """Aggregates player-level Gold sentiment into team-level features.

    Reads Gold player sentiment Parquet files, groups by team, computes
    weighted-average team sentiment, and converts to team multipliers
    in the tight [0.95, 1.05] range.

    Output saved to ``data/gold/sentiment/team_sentiment/season=YYYY/week=WW/``.

    Example:
        >>> agg = TeamWeeklyAggregator()
        >>> df = agg.aggregate(season=2026, week=1)
        >>> df[["team", "team_sentiment_multiplier"]].head()
    """

    def __init__(self, project_root: Optional[Path] = None) -> None:
        """Initialise the team aggregator.

        Args:
            project_root: Override project root for testing. Defaults to
                the auto-detected project root.
        """
        if project_root is not None:
            self._root = Path(project_root)
        else:
            self._root = _PROJECT_ROOT
        self._gold_player_dir = self._root / "data" / "gold" / "sentiment"
        self._gold_team_dir = self._root / "data" / "gold" / "sentiment" / "team_sentiment"
        # Phase 72 EVT-02: source for non-player rollup counts.
        self._silver_non_player_dir = (
            self._root / "data" / "silver" / "sentiment" / "non_player_pending"
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_player_sentiment(self, season: int, week: int) -> pd.DataFrame:
        """Load Gold player-level sentiment Parquet for a season/week.

        Args:
            season: NFL season year.
            week: NFL week number.

        Returns:
            DataFrame of player sentiment data, or empty DataFrame if
            no files found.
        """
        week_dir = self._gold_player_dir / f"season={season}" / f"week={week:02d}"
        if not week_dir.exists():
            logger.warning("No Gold player sentiment dir: %s", week_dir)
            return pd.DataFrame()

        parquet_files = sorted(week_dir.glob("*.parquet"), key=lambda p: p.name, reverse=True)
        if not parquet_files:
            logger.warning("No Parquet files in %s", week_dir)
            return pd.DataFrame()

        # Read the latest file (sorted descending by timestamp in filename)
        latest = parquet_files[0]
        logger.info("Loading player sentiment from %s", latest)
        return pd.read_parquet(latest)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _load_non_player_counts(
        self, season: int, week: int
    ) -> Dict[str, Dict[str, int]]:
        """Load coach + team news counts per team from non_player_pending Silver.

        Phase 72 EVT-02: reads ``data/silver/sentiment/non_player_pending/
        season=YYYY/week=WW/`` and counts items grouped by team_abbr +
        subject_type. Items with ``subject_type == "reporter"`` are NOT counted
        here — those go to the separate ``non_player_news`` Silver channel.

        Args:
            season: NFL season year.
            week: NFL week number.

        Returns:
            Dict mapping team_abbr -> {coach_news_count, team_news_count,
            staff_news_count} (staff is placeholder = 0 for Phase 72).
            Empty dict when no non_player_pending data exists.
        """
        import json

        week_dir = (
            self._silver_non_player_dir
            / f"season={season}"
            / f"week={week:02d}"
        )
        if not week_dir.exists():
            return {}

        counts: Dict[str, Dict[str, int]] = {}
        for path in week_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not read non_player file %s: %s", path, exc)
                continue

            items = data.get("items", []) if isinstance(data, dict) else data
            if not isinstance(items, list):
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                team_abbr = item.get("team_abbr")
                subject_type = item.get("subject_type", "player")
                if not team_abbr or subject_type not in ("coach", "team"):
                    continue
                if team_abbr not in counts:
                    counts[team_abbr] = {
                        "coach_news_count": 0,
                        "team_news_count": 0,
                        "staff_news_count": 0,
                    }
                if subject_type == "coach":
                    counts[team_abbr]["coach_news_count"] += 1
                elif subject_type == "team":
                    counts[team_abbr]["team_news_count"] += 1

        return counts

    def _aggregate_by_team(self, player_df: pd.DataFrame) -> pd.DataFrame:
        """Group player sentiment data by team and compute team scores.

        Args:
            player_df: Gold player sentiment DataFrame with columns
                including 'team' and 'sentiment_score_avg'.

        Returns:
            DataFrame with one row per team.
        """
        if player_df.empty or "team" not in player_df.columns:
            return pd.DataFrame()

        # Ensure sentiment_score_avg exists
        if "sentiment_score_avg" not in player_df.columns:
            logger.warning("No sentiment_score_avg column in player data")
            return pd.DataFrame()

        # Group by team
        grouped = player_df.groupby("team")

        team_rows = []
        for team, group in grouped:
            scores = group["sentiment_score_avg"].dropna()

            if scores.empty:
                team_score = 0.0
            else:
                # Player component: mean of player sentiment scores
                # For now, team-mention component is 0 (no team-specific
                # signal data). The formula supports adding it later.
                player_component = float(scores.mean()) * _PLAYER_COMPONENT_WEIGHT
                team_mention_component = 0.0 * _TEAM_MENTION_COMPONENT_WEIGHT
                team_score = player_component + team_mention_component
                # Clamp to [-1, +1]
                team_score = max(-1.0, min(1.0, team_score))

            positive_count = int((scores > 0).sum()) if not scores.empty else 0
            negative_count = int((scores < 0).sum()) if not scores.empty else 0

            team_rows.append({
                "team": team,
                "team_sentiment_score": round(team_score, 4),
                "team_sentiment_multiplier": team_sentiment_to_multiplier(team_score),
                "player_signal_count": len(group),
                "positive_count": positive_count,
                "negative_count": negative_count,
                "net_sentiment": positive_count - negative_count,
                # Phase 72 EVT-02: non-player rollup counts (filled in
                # aggregate() from _load_non_player_counts).
                "coach_news_count": 0,
                "team_news_count": 0,
                "staff_news_count": 0,
            })

        return pd.DataFrame(team_rows)

    # ------------------------------------------------------------------
    # Gold output
    # ------------------------------------------------------------------

    def _write_gold_parquet(
        self,
        df: pd.DataFrame,
        season: int,
        week: int,
    ) -> Path:
        """Write the team sentiment DataFrame to a Gold Parquet file.

        Args:
            df: Team-level sentiment DataFrame.
            season: NFL season year.
            week: NFL week number.

        Returns:
            Path to the written Parquet file.
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = self._gold_team_dir / f"season={season}" / f"week={week:02d}"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"team_sentiment_{ts}.parquet"
        df.to_parquet(output_path, index=False)
        logger.info(
            "Wrote Gold team sentiment Parquet (%d rows) -> %s", len(df), output_path
        )
        return output_path

    # ------------------------------------------------------------------
    # Public aggregate method
    # ------------------------------------------------------------------

    def aggregate(
        self,
        season: int,
        week: int,
        dry_run: bool = False,
    ) -> pd.DataFrame:
        """Aggregate player-level sentiment into team-level features.

        Args:
            season: NFL season year (e.g. 2026).
            week: NFL week number (1-18).
            dry_run: If True, the Gold Parquet is not written to disk.

        Returns:
            DataFrame with one row per team. Columns include:
            ``team``, ``team_sentiment_score``, ``team_sentiment_multiplier``,
            ``player_signal_count``, ``positive_count``, ``negative_count``,
            ``net_sentiment``. Empty DataFrame if no player sentiment found.
        """
        logger.info(
            "TeamWeeklyAggregator: aggregating season=%d week=%d (dry_run=%s)",
            season, week, dry_run,
        )

        player_df = self._load_player_sentiment(season, week)
        if player_df.empty:
            logger.warning(
                "No player sentiment data for season=%d week=%d", season, week
            )
            return pd.DataFrame()

        df = self._aggregate_by_team(player_df)
        if df.empty:
            logger.warning(
                "No team aggregation results for season=%d week=%d", season, week
            )
            return pd.DataFrame()

        # Phase 72 EVT-02: merge non-player rollup counts onto each team row.
        non_player_counts = self._load_non_player_counts(season, week)
        if non_player_counts:
            for idx, row in df.iterrows():
                team = row["team"]
                if team in non_player_counts:
                    df.at[idx, "coach_news_count"] = non_player_counts[team][
                        "coach_news_count"
                    ]
                    df.at[idx, "team_news_count"] = non_player_counts[team][
                        "team_news_count"
                    ]
                    df.at[idx, "staff_news_count"] = non_player_counts[team][
                        "staff_news_count"
                    ]

        # Add season/week columns
        df["season"] = season
        df["week"] = week
        df["computed_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            "TeamWeeklyAggregator: %d teams, multiplier range [%.4f, %.4f]",
            len(df),
            df["team_sentiment_multiplier"].min(),
            df["team_sentiment_multiplier"].max(),
        )

        if not dry_run:
            self._write_gold_parquet(df, season, week)
        else:
            logger.info("Dry run: Gold team Parquet not written")

        return df
