#!/usr/bin/env python3
"""
Sanity Check: Compare Our Projections & Predictions Against Consensus

Loads our generated preseason projections and compares them against
external consensus rankings (hardcoded fallback + optional live fetch)
to flag critical discrepancies.  Optionally validates game predictions
(spreads, totals, team validity, duplicates, Vegas divergence).

Usage:
    python scripts/sanity_check_projections.py --scoring half_ppr
    python scripts/sanity_check_projections.py --scoring ppr --season 2026
    python scripts/sanity_check_projections.py --check-predictions --season 2024 --week 10
    python scripts/sanity_check_projections.py --all --season 2024 --week 10
"""

import sys
import os
import argparse
import glob as globmod
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import requests
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")

# Freshness thresholds (D-08). Gold projections should refresh weekly; Silver
# aggregates can go longer between pipeline runs.
GOLD_MAX_AGE_DAYS = 7
# Silver threshold is offseason-aware: during May–August there are no weekly
# games so Silver is intentionally not refreshed. The flat 14-day window fired
# chronic noise (2 warnings every CI run from April through August). Use 90 days
# in the offseason and 14 days during the regular season (Sep–Jan).
_OFFSEASON_MONTHS = {5, 6, 7, 8}  # May, June, July, August


def _silver_max_age_days() -> int:
    """Return the Silver staleness threshold appropriate for the current month."""
    return 90 if datetime.now().month in _OFFSEASON_MONTHS else 14


# Fantasy positions used when filtering Sleeper live consensus.
_FANTASY_POSITIONS = {"QB", "RB", "WR", "TE"}
# Sleeper -> nflverse team abbreviation normalization. Only LAR differs.
_SLEEPER_TO_NFLVERSE_TEAM = {"LAR": "LA", "JAC": "JAX"}


# ---------------------------------------------------------------------------
# Consensus top-50 rankings (2025/2026 Half-PPR, pre-draft)
# Sources: FantasyPros ECR, ESPN, Yahoo, CBS Sports (aggregated April 2025)
# Format: (rank, player_name, position, team)
# ---------------------------------------------------------------------------
CONSENSUS_TOP_50: List[Tuple[int, str, str, str]] = [
    # QBs
    (1, "Josh Allen", "QB", "BUF"),
    (3, "Lamar Jackson", "QB", "BAL"),
    (5, "Jalen Hurts", "QB", "PHI"),
    (8, "Patrick Mahomes", "QB", "KC"),
    (14, "Joe Burrow", "QB", "CIN"),
    (22, "C.J. Stroud", "QB", "HOU"),
    (30, "Jayden Daniels", "QB", "WAS"),
    (38, "Kyler Murray", "QB", "ARI"),
    # RBs
    (2, "Saquon Barkley", "RB", "PHI"),
    (4, "Jahmyr Gibbs", "RB", "DET"),
    (6, "Bijan Robinson", "RB", "ATL"),
    (7, "Derrick Henry", "RB", "BAL"),
    (10, "Breece Hall", "RB", "NYJ"),
    (13, "Josh Jacobs", "RB", "GB"),
    (15, "De'Von Achane", "RB", "MIA"),
    (18, "Jonathan Taylor", "RB", "IND"),
    (21, "Joe Mixon", "RB", "HOU"),
    (25, "James Cook", "RB", "BUF"),
    (28, "Alvin Kamara", "RB", "NO"),
    (33, "Kenneth Walker III", "RB", "SEA"),
    (36, "David Montgomery", "RB", "DET"),
    (40, "Isiah Pacheco", "RB", "KC"),
    (42, "Aaron Jones", "RB", "MIN"),
    (47, "Travis Etienne", "RB", "JAX"),
    # WRs
    (9, "Ja'Marr Chase", "WR", "CIN"),
    (11, "CeeDee Lamb", "WR", "DAL"),
    (12, "Amon-Ra St. Brown", "WR", "DET"),
    (16, "Tyreek Hill", "WR", "MIA"),
    (17, "Justin Jefferson", "WR", "MIN"),
    (19, "Puka Nacua", "WR", "LA"),
    (20, "Malik Nabers", "WR", "NYG"),
    (23, "Nico Collins", "WR", "HOU"),
    (24, "Drake London", "WR", "ATL"),
    (26, "A.J. Brown", "WR", "PHI"),
    (27, "Garrett Wilson", "WR", "NYJ"),
    (29, "Davante Adams", "WR", "LA"),
    (31, "Marvin Harrison Jr.", "WR", "ARI"),
    (34, "DK Metcalf", "WR", "SEA"),
    (37, "Chris Olave", "WR", "NO"),
    (39, "Brian Thomas Jr.", "WR", "JAX"),
    (41, "Tee Higgins", "WR", "CIN"),
    (43, "Terry McLaurin", "WR", "WAS"),
    (45, "DeVonta Smith", "WR", "PHI"),
    (48, "Jaylen Waddle", "WR", "MIA"),
    # TEs
    (32, "Travis Kelce", "TE", "KC"),
    (35, "Brock Bowers", "TE", "LV"),
    (44, "Sam LaPorta", "TE", "DET"),
    (46, "Mark Andrews", "TE", "BAL"),
    (49, "George Kittle", "TE", "SF"),
    (50, "Trey McBride", "TE", "ARI"),
]


# ---------------------------------------------------------------------------
# Name normalization for fuzzy matching
# ---------------------------------------------------------------------------
def _normalize_name(name: str) -> str:
    """Normalize player name for comparison (lowercase, strip suffixes)."""
    n = name.lower().strip()
    for suffix in [" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"]:
        n = n.replace(suffix, "")
    # Common name mappings
    mappings = {
        "amon-ra st. brown": "amon-ra st brown",
        "amon ra st. brown": "amon-ra st brown",
        "amon-ra st brown": "amon-ra st brown",
        "kenneth walker": "kenneth walker",
        "kenneth walker iii": "kenneth walker",
        "breece hall": "breece hall",
        "de'von achane": "devon achane",
        "ceedee lamb": "ceedee lamb",
        "marquise brown": "marquise brown",
        "marvin harrison": "marvin harrison",
        "brian thomas": "brian thomas",
    }
    return mappings.get(n, n)


# ---------------------------------------------------------------------------
# Point reasonableness thresholds (full-season, half-PPR)
# ---------------------------------------------------------------------------
SEASON_POINT_CAPS: Dict[str, float] = {
    "QB": 500.0,
    "RB": 400.0,
    "WR": 350.0,
    "TE": 250.0,
}

# ---------------------------------------------------------------------------
# Valid NFL team abbreviations (32 teams)
# ---------------------------------------------------------------------------
VALID_NFL_TEAMS = {
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LA",
    "LAC",
    # TD-06 (Phase 75): single Rams entry — keep "LA" per nflverse convention.
    # "LAR" was a duplicate that referred to the same franchise.
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
}

# Spread and total reasonableness bounds
SPREAD_MIN, SPREAD_MAX = -20.0, 20.0
TOTAL_MIN, TOTAL_MAX = 30.0, 65.0
VEGAS_SPREAD_DIVERGENCE_THRESHOLD = 7.0

# ---------------------------------------------------------------------------
# Position-rank gap thresholds for rank-gap warnings (section 3 in run_sanity_check)
# ---------------------------------------------------------------------------
# Compare our ``position_rank`` vs ``consensus_position_rank`` (both in units
# of "Nth player at this position") rather than cross-position overall ranks.
#
# Thresholds (position-aware):
#   QB / TE → 8 slots: smaller starter pools make larger gaps meaningful.
#   RB / WR → 12 slots: deeper pools → more variance at the margins.
#
# Calibrated on 2026 preseason data: QB/TE=8 and RB/WR=12 produces ~3 signal
# warnings (Kenneth Walker RB+17, Jayden Daniels QB+11, Caleb Williams QB+10)
# vs the previous ~14 spurious QB warnings from the VORP overall_rank approach.
_POS_RANK_GAP_THRESHOLD: Dict[str, int] = {
    "QB": 8,
    "RB": 12,
    "WR": 12,
    "TE": 8,
}


def _load_our_projections(scoring: str, season: int) -> pd.DataFrame:
    """Load latest preseason projections from Gold layer."""
    pattern = os.path.join(
        GOLD_DIR,
        f"projections/preseason/season={season}/season_proj_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()

    # Load the latest file
    df = pd.read_parquet(files[-1])
    print(f"Loaded projections from: {os.path.basename(files[-1])}")
    print(f"  {len(df)} players, columns: {list(df.columns)[:8]}...")
    return df


def _build_consensus_df() -> pd.DataFrame:
    """Convert hardcoded consensus list to DataFrame."""
    rows = []
    for rank, name, pos, team in CONSENSUS_TOP_50:
        rows.append(
            {
                "consensus_rank": rank,
                "player_name": name,
                "position": pos,
                "team": team,
                "norm_name": _normalize_name(name),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Data freshness validation (per D-08)
# ---------------------------------------------------------------------------
def check_local_freshness(
    path: str, max_age_days: int = GOLD_MAX_AGE_DAYS
) -> Tuple[str, str]:
    """Check parquet file freshness for a given directory.

    Per D-08: Gold >7 days old = WARN; Silver >14 days old = WARN.

    Args:
        path: Directory containing timestamped *.parquet files.
        max_age_days: Age threshold (inclusive). Files older than this emit WARN.

    Returns:
        (level, message) where level is one of:
            'OK'    -- latest parquet is within max_age_days
            'WARN'  -- latest parquet exceeds the threshold
            'ERROR' -- directory missing or contains no parquet files
        `message` is a human-readable string suitable for logging/printing.
    """
    p = Path(path)
    if not p.exists():
        return ("ERROR", f"Directory not found: {path}")
    files = list(p.glob("*.parquet"))
    if not files:
        return ("ERROR", f"No parquet files in {path}")
    latest = max(files, key=lambda f: f.stat().st_mtime)
    age_days = (datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)).days
    if age_days > max_age_days:
        return (
            "WARN",
            f"{path} is {age_days} days old (threshold: {max_age_days})",
        )
    return ("OK", f"{path} is {age_days} days old")


# ---------------------------------------------------------------------------
# Live consensus fetch with hardcoded fallback (per D-09, D-10)
# ---------------------------------------------------------------------------
def fetch_live_consensus(limit: int = 50) -> pd.DataFrame:
    """Fetch live consensus rankings from Sleeper search_rank.

    Per D-09 & research findings: FantasyPros API returns 403 without an auth
    token, so Sleeper's ``search_rank`` is our primary live consensus proxy.
    Per D-10: If the live fetch fails (network error, rate limit, etc.) fall
    back to the hardcoded :data:`CONSENSUS_TOP_50` so the sanity check always
    produces a usable comparison DataFrame.

    Args:
        limit: Maximum number of rows to return. Sleeper responses are
            truncated to the top-ranked players by ``search_rank``.

    Returns:
        DataFrame with columns: ``consensus_rank``, ``player_name``,
        ``position``, ``team``, ``norm_name``.
    """
    try:
        logger.info("Fetching live consensus from Sleeper search_rank...")
        resp = requests.get(
            "https://api.sleeper.app/v1/players/nfl",
            timeout=60,
            headers={"User-Agent": "NFL-Data-Engineering/1.0"},
        )
        resp.raise_for_status()
        players = resp.json()

        rows: List[Dict[str, object]] = []
        for _pid, info in players.items():
            if not isinstance(info, dict):
                continue
            pos = info.get("position")
            if pos not in _FANTASY_POSITIONS:
                continue
            search_rank = info.get("search_rank")
            if search_rank is None or search_rank > 9999:
                continue
            team = info.get("team")
            if not team:
                continue
            full_name = info.get("full_name", "")
            if not full_name:
                continue
            team = _SLEEPER_TO_NFLVERSE_TEAM.get(team, team)
            rows.append(
                {
                    "consensus_rank": search_rank,
                    "player_name": full_name,
                    "position": pos,
                    "team": team,
                }
            )
        if rows:
            df = (
                pd.DataFrame(rows)
                .sort_values("consensus_rank")
                .head(limit)
                .reset_index(drop=True)
            )
            # Re-rank 1..N so ranks are contiguous for downstream comparison.
            df["consensus_rank"] = range(1, len(df) + 1)
            df["norm_name"] = df["player_name"].apply(_normalize_name)
            df = _add_consensus_position_ranks(df)
            logger.info("Live Sleeper consensus: %d players", len(df))
            return df
    except Exception as exc:  # noqa: BLE001 -- defensive; we always want a fallback
        logger.warning("Sleeper live consensus failed: %s", exc)

    logger.warning(
        "Using hardcoded CONSENSUS_TOP_50 fallback (live sources unavailable)"
    )
    return _add_consensus_position_ranks(_build_consensus_df())


def _add_consensus_position_ranks(consensus_df: pd.DataFrame) -> pd.DataFrame:
    """Derive per-position ranks from a consensus DataFrame.

    The consensus ``consensus_rank`` is a cross-position popularity rank (e.g.,
    Sleeper ``search_rank``). To compare apples-to-apples against our
    ``position_rank`` we re-rank each position's players by their consensus
    overall rank, assigning ``consensus_position_rank = 1`` to the player with
    the lowest (best) overall consensus rank in that position.

    Args:
        consensus_df: DataFrame with columns ``consensus_rank`` and
            ``position``.  Must already be sorted by ``consensus_rank``
            ascending before calling, or ranks are re-derived correctly
            regardless of existing sort order.

    Returns:
        A copy of ``consensus_df`` with an added integer column
        ``consensus_position_rank`` (1 = best in position).
    """
    df = consensus_df.copy()
    df["consensus_position_rank"] = (
        df.groupby("position")["consensus_rank"]
        .rank(method="first", ascending=True)
        .astype(int)
    )
    return df


def _match_players(our_df: pd.DataFrame, consensus_df: pd.DataFrame) -> pd.DataFrame:
    """Match consensus players to our projections using fuzzy name matching.

    Args:
        our_df: Gold projection DataFrame; must contain ``player_name``,
            ``position``, ``recent_team``, ``projected_season_points``,
            ``overall_rank``, and ``position_rank``.
        consensus_df: Consensus DataFrame produced by
            :func:`fetch_live_consensus`; should already carry a
            ``consensus_position_rank`` column (added by
            :func:`_add_consensus_position_ranks`).

    Returns:
        Left-merged DataFrame joining consensus rows onto our projections by
        normalised player name.  Unmatched consensus players have NaN in the
        ``_ours`` columns.
    """
    our = our_df.copy()
    our["norm_name"] = our["player_name"].apply(_normalize_name)

    matched = consensus_df.merge(
        our[
            [
                "norm_name",
                "player_name",
                "position",
                "recent_team",
                "projected_season_points",
                "overall_rank",
                "position_rank",
            ]
        ],
        on="norm_name",
        how="left",
        suffixes=("_consensus", "_ours"),
    )
    return matched


def _load_predictions(season: int, week: int) -> pd.DataFrame:
    """Load latest game predictions from Gold layer."""
    pattern = os.path.join(
        GOLD_DIR,
        f"predictions/season={season}/week={week}/predictions_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()

    df = pd.read_parquet(files[-1])
    print(f"Loaded predictions from: {os.path.basename(files[-1])}")
    print(f"  {len(df)} games, columns: {list(df.columns)}")
    return df


def run_prediction_check(season: int, week: int) -> Tuple[List[str], List[str]]:
    """Validate game predictions. Returns (criticals, warnings) lists."""
    print("\n" + "=" * 70)
    print(f"  NFL Game Prediction Sanity Check — Season {season}, Week {week}")
    print("=" * 70)

    df = _load_predictions(season, week)
    if df.empty:
        print("\nERROR: No predictions found.")
        print(f"  Expected: data/gold/predictions/season={season}/week={week}/")
        return (["No prediction data found"], [])

    criticals: List[str] = []
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # 1. CRITICAL: Spread reasonableness (-20 to +20)
    # ------------------------------------------------------------------
    if "predicted_spread" in df.columns:
        bad_spread = df[
            (df["predicted_spread"] < SPREAD_MIN)
            | (df["predicted_spread"] > SPREAD_MAX)
        ]
        for _, row in bad_spread.iterrows():
            criticals.append(
                f"SPREAD OUT OF RANGE: {row.get('away_team', '?')} @ "
                f"{row.get('home_team', '?')} — predicted_spread="
                f"{row['predicted_spread']:.1f} (valid: {SPREAD_MIN} to {SPREAD_MAX})"
            )

    # ------------------------------------------------------------------
    # 2. CRITICAL: Total reasonableness (30 to 65)
    # ------------------------------------------------------------------
    if "predicted_total" in df.columns:
        bad_total = df[
            (df["predicted_total"] < TOTAL_MIN) | (df["predicted_total"] > TOTAL_MAX)
        ]
        for _, row in bad_total.iterrows():
            criticals.append(
                f"TOTAL OUT OF RANGE: {row.get('away_team', '?')} @ "
                f"{row.get('home_team', '?')} — predicted_total="
                f"{row['predicted_total']:.1f} (valid: {TOTAL_MIN} to {TOTAL_MAX})"
            )

    # ------------------------------------------------------------------
    # 3. CRITICAL: No duplicate games in a week
    # ------------------------------------------------------------------
    if "game_id" in df.columns:
        dupes = df[df.duplicated(subset=["game_id"], keep=False)]
        if not dupes.empty:
            dupe_ids = dupes["game_id"].unique().tolist()
            criticals.append(
                f"DUPLICATE GAMES: {len(dupe_ids)} duplicated game_id(s): "
                f"{dupe_ids[:5]}"
            )

    # Also check for duplicate home/away matchups
    if "home_team" in df.columns and "away_team" in df.columns:
        matchup_dupes = df[df.duplicated(subset=["home_team", "away_team"], keep=False)]
        if not matchup_dupes.empty:
            criticals.append(
                f"DUPLICATE MATCHUPS: {len(matchup_dupes)} rows with repeated "
                f"home/away team pairs"
            )

    # ------------------------------------------------------------------
    # 4. WARNING: Game count (expect 14-16 games per regular season week)
    # ------------------------------------------------------------------
    n_games = len(df)
    if n_games < 13:
        warnings.append(
            f"LOW GAME COUNT: Only {n_games} games found (expected 14-16 "
            f"for a regular season week)"
        )
    elif n_games > 16:
        warnings.append(
            f"HIGH GAME COUNT: {n_games} games found (expected 14-16 "
            f"for a regular season week)"
        )
    else:
        print(f"\n  Game count: {n_games} (OK)")

    # ------------------------------------------------------------------
    # 5. CRITICAL: Valid NFL teams
    # ------------------------------------------------------------------
    for col in ["home_team", "away_team"]:
        if col not in df.columns:
            continue
        invalid = df[~df[col].isin(VALID_NFL_TEAMS)]
        for _, row in invalid.iterrows():
            criticals.append(
                f"INVALID TEAM: {col}='{row[col]}' in game "
                f"{row.get('game_id', '?')}"
            )

    # Check that no team appears as both home and away in the same game
    if "home_team" in df.columns and "away_team" in df.columns:
        self_play = df[df["home_team"] == df["away_team"]]
        for _, row in self_play.iterrows():
            criticals.append(
                f"SELF-MATCHUP: {row['home_team']} listed as both home and "
                f"away in {row.get('game_id', '?')}"
            )

    # ------------------------------------------------------------------
    # 5b. Probability sanity: home_cover_prob / over_prob in [0.30, 0.70]
    # ------------------------------------------------------------------
    # Calibrators are intentionally humble (slope ~0.08); values outside
    # this band indicate a corrupted calibrator. NaN is allowed when the
    # calibrator artifact is absent.  Per TOTALS_VERDICT: over_prob is
    # content-only — large total_edge values are expected and must NOT warn.
    for prob_col in ("home_cover_prob", "over_prob"):
        if prob_col not in df.columns:
            continue
        non_null = df[df[prob_col].notna()]
        out_of_band = non_null[
            (non_null[prob_col] < 0.30) | (non_null[prob_col] > 0.70)
        ]
        for _, row in out_of_band.iterrows():
            warnings.append(
                f"PROB OUT OF BAND: {row.get('away_team', '?')} @ "
                f"{row.get('home_team', '?')} — {prob_col}="
                f"{row[prob_col]:.3f} (expected [0.30, 0.70] or NaN)"
            )

    # ------------------------------------------------------------------
    # 6. WARNING: Large divergence from Vegas spread (>7 points)
    # ------------------------------------------------------------------
    if "predicted_spread" in df.columns and "vegas_spread" in df.columns:
        has_vegas = df[df["vegas_spread"].notna()].copy()
        if not has_vegas.empty:
            has_vegas["spread_diff"] = (
                has_vegas["predicted_spread"] - has_vegas["vegas_spread"]
            ).abs()
            big_div = has_vegas[
                has_vegas["spread_diff"] > VEGAS_SPREAD_DIVERGENCE_THRESHOLD
            ]
            for _, row in big_div.iterrows():
                warnings.append(
                    f"VEGAS SPREAD DIVERGENCE: {row.get('away_team', '?')} @ "
                    f"{row.get('home_team', '?')} — ours={row['predicted_spread']:.1f}, "
                    f"Vegas={row['vegas_spread']:.1f}, "
                    f"diff={row['spread_diff']:.1f} "
                    f"(threshold: {VEGAS_SPREAD_DIVERGENCE_THRESHOLD})"
                )

    # ------------------------------------------------------------------
    # Print CRITICAL issues
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  PREDICTION CRITICAL ISSUES")
    print("-" * 70)
    if criticals:
        for c in criticals:
            print(f"  [CRITICAL] {c}")
    else:
        print("  None — all predictions within valid ranges, no duplicates.")

    # ------------------------------------------------------------------
    # Print WARNINGS
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  PREDICTION WARNINGS")
    print("-" * 70)
    if warnings:
        for w in warnings:
            print(f"  [WARNING]  {w}")
    else:
        print("  None — game count and Vegas alignment look good.")

    # ------------------------------------------------------------------
    # Prediction summary table
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  GAME PREDICTIONS SUMMARY")
    print("-" * 70)
    header = (
        f"{'Game ID':<22} {'Away':>5} {'Home':>5} {'Spread':>7} "
        f"{'Total':>6} {'Vegas Sp':>9} {'Vegas Tot':>10} {'Tier':<8}"
    )
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for _, row in df.iterrows():
        game_id = str(row.get("game_id", ""))[:21]
        away = str(row.get("away_team", ""))
        home = str(row.get("home_team", ""))
        spread = row.get("predicted_spread", 0)
        total = row.get("predicted_total", 0)
        v_spread = row.get("vegas_spread")
        v_total = row.get("vegas_total")
        tier = str(row.get("confidence_tier", ""))
        v_sp_str = f"{v_spread:.1f}" if pd.notna(v_spread) else "N/A"
        v_tot_str = f"{v_total:.1f}" if pd.notna(v_total) else "N/A"
        print(
            f"  {game_id:<22} {away:>5} {home:>5} {spread:>7.1f} "
            f"{total:>6.1f} {v_sp_str:>9} {v_tot_str:>10} {tier:<8}"
        )

    # ------------------------------------------------------------------
    # Prediction distribution stats
    # ------------------------------------------------------------------
    if "predicted_spread" in df.columns and "predicted_total" in df.columns:
        print(
            f"\n  Spread range: [{df['predicted_spread'].min():.1f}, "
            f"{df['predicted_spread'].max():.1f}]  "
            f"mean={df['predicted_spread'].mean():.1f}"
        )
        print(
            f"  Total range:  [{df['predicted_total'].min():.1f}, "
            f"{df['predicted_total'].max():.1f}]  "
            f"mean={df['predicted_total'].mean():.1f}"
        )

    if "confidence_tier" in df.columns:
        tier_counts = df["confidence_tier"].value_counts().to_dict()
        print(f"  Confidence tiers: {tier_counts}")

    return criticals, warnings


# ---------------------------------------------------------------------------
# New check M1 — Gold newer than Silver (stale-file incident class)
# ---------------------------------------------------------------------------


def _check_gold_newer_than_silver(season: int) -> Tuple[List[str], List[str]]:
    """SANITY-M1: Gold projection file must be newer than Silver player_usage.

    Catches the incident class from commit e885989 where a stale preseason
    Gold file silently beat a freshly-generated cron output. If Silver was
    refreshed AFTER the Gold file was written, the Gold projection is using
    stale Silver inputs and should be regenerated.

    Args:
        season: Target season year.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    gold_pattern = os.path.join(
        GOLD_DIR, f"projections/preseason/season={season}", "*.parquet"
    )
    gold_files = sorted(globmod.glob(gold_pattern))
    if not gold_files:
        # Gold missing is caught elsewhere; skip this check.
        return criticals, warnings

    gold_mtime = max(os.path.getmtime(f) for f in gold_files)

    # Check against Silver player_usage — the primary Silver input for projections.
    silver_usage_base = os.path.join(PROJECT_ROOT, "data", "silver", "players", "usage")
    silver_files: List[str] = []
    for root, _dirs, files in os.walk(silver_usage_base):
        for fname in files:
            if fname.endswith(".parquet"):
                silver_files.append(os.path.join(root, fname))

    if not silver_files:
        return criticals, warnings  # Silver missing is caught by freshness check.

    silver_mtime = max(os.path.getmtime(f) for f in silver_files)
    silver_age_after_gold_days = (silver_mtime - gold_mtime) / 86400.0

    if silver_age_after_gold_days > 0.5:  # Silver refreshed >12h after Gold was written
        gold_dt = datetime.fromtimestamp(gold_mtime).strftime("%Y-%m-%d %H:%M")
        silver_dt = datetime.fromtimestamp(silver_mtime).strftime("%Y-%m-%d %H:%M")
        warnings.append(
            f"STALE GOLD VS SILVER: Gold projections (written {gold_dt}) predate "
            f"the latest Silver player_usage refresh ({silver_dt}). Gold may be "
            f"using stale Silver inputs. Regenerate Gold projections."
        )
        print(f"  [WARN] Gold vs Silver staleness: Gold={gold_dt}, Silver={silver_dt}")
    else:
        print("  [PASS] Gold projection is current vs Silver inputs")

    return criticals, warnings


# ---------------------------------------------------------------------------
# New check M2 — Ensemble and residual model artifact integrity
# ---------------------------------------------------------------------------

# All 12 expected files in models/ensemble/.
_ENSEMBLE_EXPECTED_ARTIFACTS = [
    "xgb_spread.json",
    "xgb_total.json",
    "lgb_spread.txt",
    "lgb_total.txt",
    "cb_spread.cbm",
    "cb_total.cbm",
    "ridge_spread.pkl",
    "ridge_total.pkl",
    "calibrator_spread.pkl",
    "calibrator_total.pkl",
    "oof_spread.parquet",
    "oof_total.parquet",
    "metadata.json",
]

# Expected residual models for hybrid positions (v4.2+blend shipped in v4.2 cycle).
_RESIDUAL_HYBRID_POSITIONS = ["te", "wr"]
_RESIDUAL_EXPECTED_VERSION = "v4.2+blend"


def _check_ensemble_artifacts() -> Tuple[List[str], List[str]]:
    """SANITY-M2a: models/ensemble must contain all 12 expected artifacts.

    Missing artifacts cause a crash at load time. This catches the incident
    class where models/ensemble was partially populated.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    ensemble_dir = os.path.join(PROJECT_ROOT, "models", "ensemble")
    if not os.path.isdir(ensemble_dir):
        criticals.append(
            "MODEL ARTIFACTS MISSING: models/ensemble/ directory does not exist. "
            "Ensemble cannot load — run train_ensemble.py first."
        )
        print("  [FAIL] Ensemble artifact check (directory missing)")
        return criticals, warnings

    missing = [
        f
        for f in _ENSEMBLE_EXPECTED_ARTIFACTS
        if not os.path.exists(os.path.join(ensemble_dir, f))
    ]
    if missing:
        criticals.append(
            f"MODEL ARTIFACTS MISSING: models/ensemble/ is incomplete. "
            f"Missing {len(missing)}/{len(_ENSEMBLE_EXPECTED_ARTIFACTS)} files: "
            f"{missing[:6]}{'...' if len(missing) > 6 else ''}. "
            f"Ensemble load will crash at predict time."
        )
        print(f"  [FAIL] Ensemble artifacts: {len(missing)} missing")
    else:
        print(
            f"  [PASS] Ensemble artifacts: all {len(_ENSEMBLE_EXPECTED_ARTIFACTS)} present"
        )
    return criticals, warnings


def _check_te_residual_stamp() -> Tuple[List[str], List[str]]:
    """SANITY-M2b: TE/WR residual model must carry heuristic_version == 'v4.2'.

    When TE/WR Gold rows claim projection_source='hybrid', the residual model
    must be the v4.2 version. A stale model produces a version mismatch that
    silently degrades accuracy.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    residual_dir = os.path.join(PROJECT_ROOT, "models", "residual")
    if not os.path.isdir(residual_dir):
        # No residual dir = heuristic-only mode, which is valid. Skip.
        print("  [PASS] Residual model stamp: no residual dir (heuristic-only mode)")
        return criticals, warnings

    for pos in _RESIDUAL_HYBRID_POSITIONS:
        meta_path = os.path.join(residual_dir, f"{pos}_residual_meta.json")
        joblib_path = os.path.join(residual_dir, f"{pos}_residual.joblib")

        if not os.path.exists(joblib_path):
            criticals.append(
                f"RESIDUAL MODEL MISSING: models/residual/{pos}_residual.joblib "
                f"not found. TE/WR hybrid projection will crash at load time."
            )
            print(f"  [FAIL] {pos.upper()} residual model: joblib missing")
            continue

        if not os.path.exists(meta_path):
            warnings.append(
                f"RESIDUAL META MISSING: models/residual/{pos}_residual_meta.json "
                f"not found. Cannot verify heuristic_version stamp."
            )
            print(f"  [WARN] {pos.upper()} residual model: meta missing")
            continue

        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            warnings.append(
                f"RESIDUAL META CORRUPT: {meta_path} could not be parsed: {exc}"
            )
            continue

        version = meta.get("heuristic_version", "")
        if version != _RESIDUAL_EXPECTED_VERSION:
            criticals.append(
                f"RESIDUAL VERSION MISMATCH: {pos.upper()} residual meta has "
                f"heuristic_version='{version}', expected '{_RESIDUAL_EXPECTED_VERSION}'. "
                f"Stale model artifact — retrain with train_residual_models.py."
            )
            print(
                f"  [FAIL] {pos.upper()} residual stamp: {version!r} != {_RESIDUAL_EXPECTED_VERSION!r}"
            )
        else:
            print(f"  [PASS] {pos.upper()} residual stamp: {version}")

    return criticals, warnings


# ---------------------------------------------------------------------------
# New check M3 — Consensus cross-check vs Silver external_projections
# ---------------------------------------------------------------------------

# Per-position top-N cutoffs for the cross-check comparison.
_CONSENSUS_CROSS_TOP_N: Dict[str, int] = {"QB": 12, "RB": 24, "WR": 24, "TE": 12}
# Maximum point divergence (pts) before flagging a matched player pair.
_CONSENSUS_CROSS_PTS_THRESHOLD = 12.0
# Maximum fraction of top-N that may disagree before escalating to CRITICAL.
_CONSENSUS_CROSS_CRITICAL_FRAC = 0.35


def _check_consensus_cross_check(
    scoring: str, season: int, week: Optional[int] = None
) -> Tuple[List[str], List[str]]:
    """SANITY-M3: compare Gold top-N vs Silver external_projections consensus.

    Catches the dead-multiplier class of bug (e.g., all WR projections shifted
    by a constant factor for months). A handful of disagreements is normal edge;
    >35% of top-N disagreeing signals broken inputs and escalates to CRITICAL.

    The check loads the latest Silver external_projections for the most recent
    available week matching the target season. If no Silver external_projections
    exist, the check is skipped with a WARN (not CRITICAL — Silver external
    data is optional infrastructure).

    Args:
        scoring: Scoring format string (e.g., ``"half_ppr"``).
        season: Target projection season.
        week: Optional week override; uses latest available week if None.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # 1. Load Silver external_projections for the target season.
    # ------------------------------------------------------------------
    ext_base = os.path.join(
        PROJECT_ROOT, "data", "silver", "external_projections", f"season={season}"
    )
    if not os.path.isdir(ext_base):
        warnings.append(
            f"CONSENSUS CROSS-CHECK SKIPPED: no Silver external_projections for "
            f"season={season}. Run weekly-external-projections workflow first."
        )
        print(
            f"  [SKIP] Consensus cross-check (no Silver external_projections for {season})"
        )
        return criticals, warnings

    # Find latest available week.
    week_dirs = sorted(globmod.glob(os.path.join(ext_base, "week=*")))
    if not week_dirs:
        warnings.append(
            f"CONSENSUS CROSS-CHECK SKIPPED: Silver external_projections/{season}/ "
            f"exists but contains no week partitions."
        )
        print("  [SKIP] Consensus cross-check (no week partitions in Silver ext)")
        return criticals, warnings

    if week is not None:
        target_week_dir = os.path.join(ext_base, f"week={week:02d}")
        if not os.path.isdir(target_week_dir):
            target_week_dir = week_dirs[-1]
    else:
        target_week_dir = week_dirs[-1]

    ext_files = sorted(globmod.glob(os.path.join(target_week_dir, "*.parquet")))
    if not ext_files:
        warnings.append(
            f"CONSENSUS CROSS-CHECK SKIPPED: no parquet files in {target_week_dir}."
        )
        print("  [SKIP] Consensus cross-check (no parquet in week dir)")
        return criticals, warnings

    try:
        ext_df = pd.read_parquet(ext_files[-1])
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"CONSENSUS CROSS-CHECK SKIPPED: could not read {ext_files[-1]}: {exc}"
        )
        return criticals, warnings

    # ------------------------------------------------------------------
    # 2. Load our Gold projections.
    # ------------------------------------------------------------------
    try:
        our_df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"CONSENSUS CROSS-CHECK SKIPPED: {exc}")
        return criticals, warnings

    if our_df is None or our_df.empty:
        warnings.append("CONSENSUS CROSS-CHECK SKIPPED: Gold projections empty.")
        return criticals, warnings

    points_col = (
        "projected_points"
        if "projected_points" in our_df.columns
        else "projected_season_points"
    )

    # ------------------------------------------------------------------
    # 3. Filter external projections to skill positions + scoring format.
    # ------------------------------------------------------------------
    if "position" in ext_df.columns:
        ext_df = ext_df[ext_df["position"].isin(_FANTASY_POSITIONS)].copy()
    if "scoring_format" in ext_df.columns:
        ext_scoring = ext_df[ext_df["scoring_format"] == scoring]
        if not ext_scoring.empty:
            ext_df = ext_scoring.copy()

    if "projected_points" not in ext_df.columns or ext_df.empty:
        warnings.append(
            "CONSENSUS CROSS-CHECK SKIPPED: Silver external_projections missing "
            "'projected_points' column or empty after filtering."
        )
        return criticals, warnings

    our_df["_norm"] = our_df["player_name"].apply(_normalize_name)
    ext_df["_norm"] = ext_df["player_name"].apply(_normalize_name)

    total_flagged = 0
    total_checked = 0
    warn_lines: List[str] = []

    for pos, top_n in _CONSENSUS_CROSS_TOP_N.items():
        our_pos = our_df[our_df["position"] == pos].nlargest(top_n, points_col)
        ext_pos = ext_df[ext_df["position"] == pos].nlargest(top_n, "projected_points")

        if our_pos.empty or ext_pos.empty:
            continue

        our_names = set(our_pos["_norm"])
        ext_names = set(ext_pos["_norm"])
        total_checked += top_n

        # Players in our top-N absent from consensus top-2x (generous window).
        ext_top_2x = set(
            ext_df[ext_df["position"] == pos].nlargest(top_n * 2, "projected_points")[
                "_norm"
            ]
        )
        absent_from_ext = our_names - ext_top_2x
        # Players in consensus top-N absent from our top-2x.
        our_top_2x = set(
            our_df[our_df["position"] == pos].nlargest(top_n * 2, points_col)["_norm"]
        )
        absent_from_ours = ext_names - our_top_2x

        for nm in absent_from_ext | absent_from_ours:
            total_flagged += 1
            direction = "ours-only" if nm in absent_from_ext else "consensus-only"
            warn_lines.append(f"  {pos} {nm} ({direction})")

        # Point-magnitude check on matched players.
        merged = our_pos.merge(
            ext_pos[["_norm", "projected_points"]],
            on="_norm",
            suffixes=("_ours", "_ext"),
        )
        for _, row in merged.iterrows():
            diff = abs(row[f"{points_col}_ours"] - row["projected_points_ext"])
            if diff > _CONSENSUS_CROSS_PTS_THRESHOLD:
                total_flagged += 1
                warn_lines.append(
                    f"  {pos} {row['_norm']}: ours={row[f'{points_col}_ours']:.1f}, "
                    f"ext={row['projected_points_ext']:.1f}, diff={diff:.1f}"
                )

    if total_checked == 0:
        print("  [SKIP] Consensus cross-check (no position overlap)")
        return criticals, warnings

    frac = total_flagged / total_checked if total_checked > 0 else 0.0
    if frac > _CONSENSUS_CROSS_CRITICAL_FRAC:
        criticals.append(
            f"CONSENSUS DIVERGENCE: {total_flagged}/{total_checked} "
            f"({frac:.0%}) top-N slots disagree with Silver external_projections "
            f"(threshold {_CONSENSUS_CROSS_CRITICAL_FRAC:.0%}). "
            f"Likely cause: broken projection inputs (dead multiplier, missing "
            f"Silver data, wrong season used). Top offenders:\n"
            + "\n".join(warn_lines[:10])
        )
        print(
            f"  [FAIL] Consensus cross-check: {frac:.0%} disagreement > {_CONSENSUS_CROSS_CRITICAL_FRAC:.0%}"
        )
    elif total_flagged > 0:
        for line in warn_lines[:5]:
            warnings.append(f"CONSENSUS GAP:{line.strip()}")
        print(
            f"  [PASS] Consensus cross-check: {total_flagged} gaps "
            f"({frac:.0%} < {_CONSENSUS_CROSS_CRITICAL_FRAC:.0%} threshold)"
        )
    else:
        print("  [PASS] Consensus cross-check: no gaps vs Silver external_projections")

    return criticals, warnings


# ---------------------------------------------------------------------------
# New check M5 — Distributional drift vs historical Gold archives
# ---------------------------------------------------------------------------

# Historical mean top-24 projected points per position, computed from
# 2022-2024 Gold preseason archives. Used as the expected band centre.
# Band is ±25% of the historical mean (generous to absorb year-to-year
# variance while still catching a dead-multiplier that shifts everything).
_HISTORICAL_TOP24_MEANS: Dict[str, float] = {
    "QB": 310.0,  # typical QB1 preseason projection range
    "RB": 230.0,
    "WR": 195.0,
    "TE": 165.0,
}
_DRIFT_BAND_FRACTION = 0.30  # ±30%


def _check_projection_distribution(
    scoring: str, season: int
) -> Tuple[List[str], List[str]]:
    """SANITY-M5: projected-points distribution must be within historical band.

    Catches the dead-multiplier-class bug (Phase 53 incident) where a bad
    matchup factor silently shifted all projections for months. Compares
    the mean projected_season_points of our top-24 per position against
    the historical band from _HISTORICAL_TOP24_MEANS.

    A ±30% band is generous enough to absorb genuine year-to-year variance
    while still catching a multiplier stuck at 0 or 10x.

    Args:
        scoring: Scoring format string.
        season: Target season year.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    try:
        df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"DISTRIBUTION DRIFT CHECK SKIPPED: {exc}")
        return criticals, warnings

    if df is None or df.empty:
        warnings.append("DISTRIBUTION DRIFT CHECK SKIPPED: Gold projections empty.")
        return criticals, warnings

    points_col = (
        "projected_points"
        if "projected_points" in df.columns
        else "projected_season_points"
    )

    # The historical bands are SEASON-TOTAL magnitudes (preseason files).
    # A weekly Gold file uses the same projected_points column at ~1/17 the
    # scale — comparing it to season bands would fire four spurious
    # CRITICALs. Skip (INFO-style warning) when magnitudes are weekly.
    overall_max = float(df[points_col].max()) if len(df) else 0.0
    if overall_max < 60.0:
        warnings.append(
            "DISTRIBUTION DRIFT CHECK SKIPPED: weekly-scale projections "
            f"detected (max {overall_max:.1f} pts); bands are calibrated "
            "for preseason season totals only."
        )
        return criticals, warnings

    for pos, historical_mean in _HISTORICAL_TOP24_MEANS.items():
        pos_df = df[df["position"] == pos]
        top24 = pos_df.nlargest(24, points_col)
        if len(top24) < 12:
            warnings.append(
                f"DISTRIBUTION DRIFT SKIPPED ({pos}): only {len(top24)} players "
                f"(need ≥12 for meaningful distribution check)."
            )
            continue

        our_mean = top24[points_col].mean()
        lo = historical_mean * (1 - _DRIFT_BAND_FRACTION)
        hi = historical_mean * (1 + _DRIFT_BAND_FRACTION)

        if our_mean < lo or our_mean > hi:
            criticals.append(
                f"DISTRIBUTION DRIFT ({pos}): mean top-24 projected pts = "
                f"{our_mean:.1f}, outside historical band "
                f"[{lo:.1f}, {hi:.1f}] (centre {historical_mean:.1f} ±{_DRIFT_BAND_FRACTION:.0%}). "
                f"Dead multiplier or wrong season data likely."
            )
            print(
                f"  [FAIL] Distribution drift {pos}: mean={our_mean:.1f} "
                f"outside [{lo:.1f}, {hi:.1f}]"
            )
        else:
            print(
                f"  [PASS] Distribution drift {pos}: mean={our_mean:.1f} "
                f"in [{lo:.1f}, {hi:.1f}]"
            )

    return criticals, warnings


def run_sanity_check(scoring: str, season: int) -> int:
    """Run the full sanity check and print report. Returns exit code."""
    print("=" * 70)
    print(f"  NFL Projection Sanity Check — {scoring.upper()}, Season {season}")
    print("=" * 70)

    # Warnings are collected across all sections; initialize early so the
    # freshness checks below can append to the same list.
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # 0. Data freshness checks (per D-08)
    # ------------------------------------------------------------------
    #   Gold (preseason projections)  -> 7-day threshold
    #   Silver (player usage, team PBP metrics) -> 14-day threshold
    # Silver paths match the on-disk layout (data/silver/{players,teams}/*),
    # which diverges from the flattened names used in the planning doc.
    print("\n" + "-" * 70)
    print("  DATA FRESHNESS")
    print("-" * 70)
    gold_dir = os.path.join(GOLD_DIR, f"projections/preseason/season={season}")
    gold_level, gold_msg = check_local_freshness(
        gold_dir, max_age_days=GOLD_MAX_AGE_DAYS
    )
    print(f"  Gold projections:   [{gold_level}] {gold_msg}")
    if gold_level == "WARN":
        warnings.append(f"STALE GOLD DATA: {gold_msg}")
    elif gold_level == "ERROR":
        # Missing Gold is surfaced as a warning here; the projection loader
        # below will raise a critical if no files are readable.
        warnings.append(f"GOLD DATA MISSING: {gold_msg}")

    silver_dirs = [
        (
            "player_usage",
            os.path.join(PROJECT_ROOT, "data", "silver", "players", "usage"),
        ),
        (
            "team_pbp_metrics",
            os.path.join(PROJECT_ROOT, "data", "silver", "teams", "pbp_metrics"),
        ),
    ]
    silver_threshold = _silver_max_age_days()
    for label, sd in silver_dirs:
        # Silver dirs commonly partition further by season=YYYY; freshness
        # check works whether files live at the leaf or at the root.
        probe_dir = sd
        if not any(Path(sd).glob("*.parquet")) and Path(sd).exists():
            # Descend into the most-recent season partition, if any.
            season_partitions = sorted(
                [p for p in Path(sd).glob("season=*") if p.is_dir()]
            )
            if season_partitions:
                probe_dir = str(season_partitions[-1])
        s_level, s_msg = check_local_freshness(probe_dir, max_age_days=silver_threshold)
        print(f"  Silver {label}: [{s_level}] {s_msg}")
        if s_level == "WARN":
            warnings.append(f"STALE SILVER DATA ({label}): {s_msg}")

    # Load our projections
    our_df = _load_our_projections(scoring, season)
    if our_df.empty:
        print("\nERROR: No projections found. Run generate_projections.py first.")
        print(f"  Expected: data/gold/projections/preseason/season={season}/")
        return 1

    # Build consensus (live Sleeper primary, hardcoded fallback per D-09/D-10)
    consensus_df = fetch_live_consensus(limit=50)
    # norm_name is required for player matching downstream
    if "norm_name" not in consensus_df.columns:
        consensus_df["norm_name"] = consensus_df["player_name"].apply(_normalize_name)
    # Heuristic: if the returned DataFrame matches the hardcoded ranks/names
    # exactly we know the Sleeper fetch failed and we fell back.
    hardcoded_ranks = [entry[0] for entry in CONSENSUS_TOP_50]
    hardcoded_names = [entry[1] for entry in CONSENSUS_TOP_50]
    is_fallback = (
        len(consensus_df) == len(CONSENSUS_TOP_50)
        and consensus_df["consensus_rank"].tolist() == hardcoded_ranks
        and consensus_df["player_name"].tolist() == hardcoded_names
    )
    source = "hardcoded fallback" if is_fallback else "live Sleeper"
    print(f"\nConsensus rankings: {len(consensus_df)} players ({source})")

    # Match players
    matched = _match_players(our_df, consensus_df)

    # ------------------------------------------------------------------
    # 1. CRITICAL: Position mismatches
    # ------------------------------------------------------------------
    criticals: List[str] = []
    pos_mismatch = matched[
        matched["position_ours"].notna()
        & (matched["position_consensus"] != matched["position_ours"])
    ]
    for _, row in pos_mismatch.iterrows():
        msg = (
            f"POSITION MISMATCH: {row['player_name_consensus']} — "
            f"consensus={row['position_consensus']}, ours={row['position_ours']}"
        )
        criticals.append(msg)

    # ------------------------------------------------------------------
    # 2. WARNING: Missing top players (consensus top-50 not in ours)
    # ------------------------------------------------------------------
    # NOTE: After _match_players the consensus columns carry the _consensus
    # suffix (pandas merge disambiguation). The `team` column has no suffix
    # because it only exists on the consensus side. This is a latent bug
    # that only surfaces when live Sleeper consensus returns players absent
    # from Gold projections; with the static hardcoded list every consensus
    # entry also appeared in our projections so the missing branch was never
    # exercised. Reference the suffixed columns explicitly.
    #
    # Disposition: WARNING rather than CRITICAL. Per D-06, criticals are
    # structural absurdities (missing positions entirely, player on wrong
    # team in top 20, negative projections). Live Sleeper consensus often
    # includes current rookies not yet in our Gold projections -- flagging
    # those as CRITICAL would block deploys on every rookie preseason run.
    # Missing players are persisted here (below) as well: initialized early
    # so the 'missing' DataFrame is still available for downstream summary.
    missing = matched[matched["overall_rank"].isna()]
    for _, row in missing.iterrows():
        msg = (
            f"MISSING PLAYER: {row['player_name_consensus']} "
            f"({row['position_consensus']}, {row['team']}) — "
            f"consensus rank #{int(row['consensus_rank'])}, "
            f"not found in our projections"
        )
        warnings.append(msg)

    # ------------------------------------------------------------------
    # 3. WARNING: Large rank discrepancies — position rank vs position rank
    # ------------------------------------------------------------------
    # NOTE: warnings list was initialized at the top of run_sanity_check()
    # so freshness checks could append; do NOT re-init here or we lose them.
    #
    # The previous approach compared our VORP-based ``overall_rank`` against
    # the consensus cross-position popularity rank (Sleeper ``search_rank``).
    # That is apples-to-oranges: VORP intentionally buries QBs in 1-QB leagues
    # (1 starter slot vs 2 RB/WR), so elite QBs appear at overall #50–#150 even
    # with 300+ projected points.  This produced ~14 spurious QB warnings per CI
    # run (Jayden Daniels +120, Caleb Williams +118, etc.) that drowned out real
    # signal.
    #
    # Fix (2026-06-11): compare ``position_rank`` (ours) vs
    # ``consensus_position_rank`` (derived by re-ranking consensus entries within
    # each position by their cross-position rank).  Both quantities are on the
    # same scale (QB1 = 1, QB2 = 2, …) so the diff is meaningful.
    #
    matched_found = matched[matched["position_rank"].notna()].copy()
    # position_rank / consensus_position_rank are both integers after dtype cast.
    matched_found["pos_rank_diff"] = matched_found["position_rank"].astype(
        int
    ) - matched_found["consensus_position_rank"].astype(int)
    matched_found["abs_pos_rank_diff"] = matched_found["pos_rank_diff"].abs()
    # Keep overall_rank diff available for display tables (sorted by abs diff).
    matched_found["rank_diff"] = (
        matched_found["overall_rank"] - matched_found["consensus_rank"]
    )
    matched_found["abs_rank_diff"] = matched_found["rank_diff"].abs()

    for _, row in matched_found.iterrows():
        pos = str(row["position_consensus"])
        threshold = _POS_RANK_GAP_THRESHOLD.get(pos, 12)
        if row["abs_pos_rank_diff"] <= threshold:
            continue
        direction = "LOWER" if row["pos_rank_diff"] > 0 else "HIGHER"
        warnings.append(
            f"RANK GAP: {row['player_name_consensus']} ({pos}) — "
            f"consensus {pos}#{int(row['consensus_position_rank'])}, "
            f"ours {pos}#{int(row['position_rank'])} "
            f"(diff: {int(row['pos_rank_diff']):+d}, we rank {direction})"
        )

    big_diff = matched_found.sort_values("abs_pos_rank_diff", ascending=False)

    # ------------------------------------------------------------------
    # 4. WARNING: Unreasonable projected points
    # ------------------------------------------------------------------
    for _, row in our_df.iterrows():
        pos = row.get("position", "")
        pts = row.get("projected_season_points", 0)
        cap = SEASON_POINT_CAPS.get(pos)
        if cap and pts > cap:
            warnings.append(
                f"UNREASONABLE PTS: {row['player_name']} ({pos}) — "
                f"{pts:.1f} pts exceeds {cap:.0f} cap"
            )

    # Also flag negative projections
    neg = our_df[our_df["projected_season_points"] < 0]
    for _, row in neg.iterrows():
        warnings.append(
            f"NEGATIVE PTS: {row['player_name']} ({row['position']}) — "
            f"{row['projected_season_points']:.1f} pts"
        )

    # ------------------------------------------------------------------
    # 5. CRITICAL: Position validity audit — every player must have a
    #    valid NFL position, and known star players must not be misclassified
    # ------------------------------------------------------------------
    valid_positions = {"QB", "RB", "WR", "TE", "K", "DEF"}
    invalid_pos = our_df[~our_df["position"].isin(valid_positions)]
    for _, row in invalid_pos.iterrows():
        criticals.append(
            f"INVALID POSITION: {row['player_name']} — "
            f"position='{row['position']}' (expected one of {valid_positions})"
        )

    null_pos = our_df[our_df["position"].isna()]
    for _, row in null_pos.iterrows():
        criticals.append(f"NULL POSITION: {row['player_name']} — position is null/NaN")

    # Known star players with expected positions — catches data pipeline bugs
    # like Saquon Barkley showing up as QB
    KNOWN_STAR_POSITIONS = {
        "Patrick Mahomes": "QB",
        "Josh Allen": "QB",
        "Lamar Jackson": "QB",
        "Joe Burrow": "QB",
        "Jalen Hurts": "QB",
        "C.J. Stroud": "QB",
        "Saquon Barkley": "RB",
        "Derrick Henry": "RB",
        "Jahmyr Gibbs": "RB",
        "Bijan Robinson": "RB",
        "Christian McCaffrey": "RB",
        "Breece Hall": "RB",
        "Jonathan Taylor": "RB",
        "Josh Jacobs": "RB",
        "De'Von Achane": "RB",
        "Ja'Marr Chase": "WR",
        "Justin Jefferson": "WR",
        "Tyreek Hill": "WR",
        "CeeDee Lamb": "WR",
        "Amon-Ra St. Brown": "WR",
        "Puka Nacua": "WR",
        "A.J. Brown": "WR",
        "Davante Adams": "WR",
        "Malik Nabers": "WR",
        "Travis Kelce": "TE",
        "Brock Bowers": "TE",
        "Sam LaPorta": "TE",
        "Mark Andrews": "TE",
        "George Kittle": "TE",
        "Trey McBride": "TE",
    }
    for star_name, expected_pos in KNOWN_STAR_POSITIONS.items():
        # Use normalized full-name matching to avoid false positives
        # (e.g., "Jermar Jefferson" matching "Justin Jefferson")
        norm_star = _normalize_name(star_name)
        star_rows = our_df[our_df["player_name"].apply(_normalize_name) == norm_star]
        for _, row in star_rows.iterrows():
            if row["position"] != expected_pos:
                criticals.append(
                    f"STAR MISCLASSIFIED: {row['player_name']} — "
                    f"expected {expected_pos}, got {row['position']}"
                )

    # ------------------------------------------------------------------
    # 6. WARNING: Missing kickers (position should exist in projections)
    # ------------------------------------------------------------------
    k_count = len(our_df[our_df["position"] == "K"])
    if k_count == 0:
        warnings.append(
            "NO KICKERS: 0 kicker projections found — "
            "run with --include-kickers or check projection pipeline"
        )

    # ------------------------------------------------------------------
    # 7. WARNING: Position distribution sanity
    # ------------------------------------------------------------------
    pos_counts = our_df["position"].value_counts().to_dict()
    if pos_counts.get("QB", 0) > pos_counts.get("WR", 0):
        warnings.append(
            f"QB > WR COUNT: {pos_counts.get('QB', 0)} QBs vs "
            f"{pos_counts.get('WR', 0)} WRs — likely data issue"
        )

    # ------------------------------------------------------------------
    # Print CRITICAL issues
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  CRITICAL ISSUES")
    print("=" * 70)
    if criticals:
        for c in criticals:
            print(f"  [CRITICAL] {c}")
    else:
        print("  None — all consensus players found with correct positions.")

    # ------------------------------------------------------------------
    # Print WARNINGS
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  WARNINGS")
    print("=" * 70)
    if warnings:
        for w in warnings:
            print(f"  [WARNING]  {w}")
    else:
        print("  None — all ranks within 20 spots, all points reasonable.")

    # ------------------------------------------------------------------
    # Top-20 comparison table (position rank vs position rank)
    # ------------------------------------------------------------------
    # Columns show position-scoped ranks (QB1/QB2, RB1/RB2 …) so the
    # diff is directly interpretable without the VORP-scale distortion
    # that inflated QB overall_rank gaps by 80–120 slots.
    print("\n" + "=" * 70)
    print("  TOP-20 COMPARISON TABLE (position ranks)")
    print("=" * 70)
    top20 = matched_found.sort_values("consensus_rank").head(20)
    header = (
        f"{'Player':<25} {'Pos':<4} {'CPos#':>6} {'OPos#':>6} "
        f"{'Diff':>6} {'Our Pts':>8}"
    )
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for _, row in top20.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_pos = int(row["consensus_position_rank"])
        our_pos = int(row["position_rank"])
        diff = int(row["pos_rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_pos:>6} {our_pos:>6} "
            f"{diff_str:>6} {pts:>8.1f}"
        )

    # ------------------------------------------------------------------
    # Biggest rank discrepancies (position rank vs position rank)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  BIGGEST POSITION-RANK DISCREPANCIES (top 10)")
    print("=" * 70)
    worst = matched_found.sort_values("abs_pos_rank_diff", ascending=False).head(10)
    header2 = (
        f"{'Player':<25} {'Pos':<4} {'CPos#':>6} {'OPos#':>6} "
        f"{'Diff':>6} {'Our Pts':>8}"
    )
    print(f"  {header2}")
    print(f"  {'-' * len(header2)}")
    for _, row in worst.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_pos = int(row["consensus_position_rank"])
        our_pos = int(row["position_rank"])
        diff = int(row["pos_rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_pos:>6} {our_pos:>6} "
            f"{diff_str:>6} {pts:>8.1f}"
        )

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  SUMMARY STATISTICS")
    print("=" * 70)

    n_matched = len(matched_found)
    n_missing = len(missing)
    n_total_consensus = len(consensus_df)

    print(f"  Consensus players matched: {n_matched} / {n_total_consensus}")
    print(f"  Missing from our projections: {n_missing}")
    print(f"  Critical issues: {len(criticals)}")
    print(f"  Warnings: {len(warnings)}")

    if n_matched > 1:
        # Spearman rank correlation on position ranks (apples-to-apples)
        from scipy import stats as sp_stats

        corr, p_value = sp_stats.spearmanr(
            matched_found["consensus_position_rank"], matched_found["position_rank"]
        )
        print(f"\n  Spearman position-rank correlation: {corr:.3f} (p={p_value:.4f})")
        if corr > 0.8:
            print("  Interpretation: STRONG agreement with consensus")
        elif corr > 0.6:
            print("  Interpretation: MODERATE agreement with consensus")
        elif corr > 0.4:
            print("  Interpretation: WEAK agreement with consensus")
        else:
            print("  Interpretation: POOR agreement — investigate model")

        # Mean absolute position-rank difference
        mean_diff = matched_found["abs_pos_rank_diff"].mean()
        median_diff = matched_found["abs_pos_rank_diff"].median()
        print(f"  Mean absolute position-rank difference: {mean_diff:.1f}")
        print(f"  Median absolute position-rank difference: {median_diff:.1f}")

        # Per-position breakdown
        print(f"\n  Per-position position-rank correlation:")
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_data = matched_found[matched_found["position_consensus"] == pos]
            if len(pos_data) > 2:
                pos_corr, _ = sp_stats.spearmanr(
                    pos_data["consensus_position_rank"], pos_data["position_rank"]
                )
                pos_mean = pos_data["abs_pos_rank_diff"].mean()
                print(
                    f"    {pos}: r={pos_corr:.3f}, mean pos-rank diff={pos_mean:.1f} "
                    f"({len(pos_data)} players)"
                )

    # ------------------------------------------------------------------
    # Our top-10 players sorted by raw projected points
    # ------------------------------------------------------------------
    # Sorted by projected_season_points (not overall_rank) so the list
    # reads naturally — VORP-based overall_rank buries QBs in 1-QB leagues
    # which made the old display confusing (e.g. Nacua 307 pts above Bijan
    # 326 pts).  Points order is unambiguous and self-explanatory.
    print("\n" + "=" * 70)
    print("  OUR TOP-10 OVERALL (by projected points)")
    print("=" * 70)
    our_top10 = our_df.sort_values("projected_season_points", ascending=False).head(10)
    for rank_idx, (_, row) in enumerate(our_top10.iterrows(), start=1):
        print(
            f"  #{rank_idx:>2}  {row['player_name']:<25} "
            f"{row['position']:<3}  {row['recent_team']:<4}  "
            f"{row['projected_season_points']:.1f} pts"
        )

    # ------------------------------------------------------------------
    # Position distribution comparison
    # ------------------------------------------------------------------
    # Both sides use top-50 by raw projected points so the comparison is
    # apples-to-apples.  The previous implementation selected our top-50
    # via overall_rank (VORP-based), which under-counted QBs significantly
    # vs the popularity-ranked consensus list.
    print("\n" + "=" * 70)
    print("  POSITION DISTRIBUTION IN TOP-50 (by projected points)")
    print("=" * 70)
    our_top50_by_pts = our_df.nlargest(50, "projected_season_points")
    our_pos_counts = our_top50_by_pts["position"].value_counts().to_dict()
    cons_pos_counts = consensus_df["position"].value_counts().to_dict()

    header3 = f"{'Position':<10} {'Consensus':>10} {'Ours':>10} {'Diff':>10}"
    print(f"  {header3}")
    print(f"  {'-' * len(header3)}")
    for pos in ["QB", "RB", "WR", "TE"]:
        c = cons_pos_counts.get(pos, 0)
        o = our_pos_counts.get(pos, 0)
        d = o - c
        print(f"  {pos:<10} {c:>10} {o:>10} {d:>+10}")

    # ------------------------------------------------------------------
    # Phase 68 SANITY-05 + SANITY-07 + SANITY-10 — drift + API key + DQAL.
    # These assertions run for every deploy (not just --check-live) so
    # they gate-block any merge to main regardless of the --check-live flag.
    # Each regression class produces at most one aggregated CRITICAL per
    # offending player (drift) or per-class (negative-clamp, rookie, rank
    # gap) so one class cannot flood the aggregate and mask another.
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  DQAL-03 CARRY-OVER ASSERTIONS")
    print("-" * 70)

    drift_crit, drift_warn = _check_roster_drift_top50(scoring, season)
    criticals.extend(drift_crit)
    warnings.extend(drift_warn)

    key_crit, key_warn = _assert_api_key_when_enrichment_enabled()
    criticals.extend(key_crit)
    warnings.extend(key_warn)

    neg_crit, neg_warn = _check_dqal_negative_projection(scoring, season)
    criticals.extend(neg_crit)
    warnings.extend(neg_warn)

    # season-1: the most-recent completed season relative to the target season.
    # The Bronze rookies path only holds data for completed draft classes; the
    # incoming 2026 draft class won't exist yet when running a 2026 projection,
    # so we check season-1 (2025 for a 2026 run) rather than season itself.
    rookie_crit, rookie_warn = _check_dqal_rookie_ingestion(season=season - 1)
    criticals.extend(rookie_crit)
    warnings.extend(rookie_warn)

    gap_crit, gap_warn = _check_dqal_rank_gap(season=season)
    criticals.extend(gap_crit)
    warnings.extend(gap_warn)

    recent_crit, recent_warn = _check_projection_incorporates_recent_season(
        season, scoring
    )
    criticals.extend(recent_crit)
    warnings.extend(recent_warn)

    # ------------------------------------------------------------------
    # New checks (audit 2026-06-10): M1 Gold/Silver staleness, M2 model
    # artifact integrity, M3 consensus cross-check, M5 distribution drift.
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  NEW CHECKS (M1–M5)")
    print("-" * 70)

    gs_crit, gs_warn = _check_gold_newer_than_silver(season)
    criticals.extend(gs_crit)
    warnings.extend(gs_warn)

    ens_crit, ens_warn = _check_ensemble_artifacts()
    criticals.extend(ens_crit)
    warnings.extend(ens_warn)

    te_crit, te_warn = _check_te_residual_stamp()
    criticals.extend(te_crit)
    warnings.extend(te_warn)

    cross_crit, cross_warn = _check_consensus_cross_check(scoring, season)
    criticals.extend(cross_crit)
    warnings.extend(cross_warn)

    dist_crit, dist_warn = _check_projection_distribution(scoring, season)
    criticals.extend(dist_crit)
    warnings.extend(dist_warn)

    # Return code
    if criticals:
        print(f"\n  RESULT: FAIL — {len(criticals)} critical issues found")
        return 1
    elif len(warnings) > 10:
        print(f"\n  RESULT: WARN — {len(warnings)} warnings (>10 threshold)")
        return 0
    else:
        print(f"\n  RESULT: PASS — projections look reasonable")
        return 0


# HF Spaces bridge — production backend since 2026-05-28, when the Railway
# trial expired (the old nfldataengineering-production.up.railway.app URL
# now returns 404 for every route, which read as a total live-site outage
# in the gate's first CI run on 2026-06-11).
DEFAULT_LIVE_BACKEND = "https://gesmith0606-nfl-data-api.hf.space"
DEFAULT_LIVE_FRONTEND = "https://frontend-jet-seven-33.vercel.app"


# ---------------------------------------------------------------------------
# Phase 68 SANITY-01/02/03 — live probe helpers
# ---------------------------------------------------------------------------
# Top-10 fallback list (used when Silver team_metrics parquet missing).
# Selected from 2024 W18 snap_count leaders to match CONTEXT sampling intent.
_TOP_10_TEAMS_FALLBACK: List[str] = [
    "KC",
    "BUF",
    "PHI",
    "DET",
    "BAL",
    "SF",
    "MIA",
    "CIN",
    "GB",
    "DAL",
]
# 5-second timeout per probe (Phase 68 CONTEXT "specifics"). Slow Railway
# responses are themselves a signal we want surfaced as CRITICAL.
_PROBE_TIMEOUT_SECONDS: int = 5


def _top_n_teams_by_snap_count(
    season: int, n: int = 10
) -> Tuple[List[str], Optional[str]]:
    """Return ``(team_abbrs, warning_msg)``.

    Reads the latest Silver team_metrics parquet for the given season, sums the
    offensive snap column per team, and returns the top-``n`` abbreviations. If
    Silver team_metrics is absent, falls back to Bronze ``players/snaps`` and
    finally to a hardcoded list (2024 W18 snap leaders).

    Args:
        season: Season year for partition lookup (e.g. 2025).
        n: Number of top teams to return.

    Returns:
        Tuple of (team abbreviations, warning message). ``warning_msg`` is
        non-None only when the fallback list was used.
    """
    silver_glob = os.path.join(
        PROJECT_ROOT,
        "data",
        "silver",
        "team_metrics",
        f"season={season}",
        "week=*",
        "*.parquet",
    )
    parquet_files = sorted(globmod.glob(silver_glob))
    if not parquet_files:
        # Try snap_counts Bronze as fallback (also week-partitioned).
        snaps_glob = os.path.join(
            PROJECT_ROOT,
            "data",
            "bronze",
            "players",
            "snaps",
            f"season={season}",
            "week=*",
            "*.parquet",
        )
        snap_files = sorted(globmod.glob(snaps_glob))
        if not snap_files:
            return _TOP_10_TEAMS_FALLBACK[:n], (
                f"SAMPLING FALLBACK: no Silver team_metrics or Bronze snaps "
                f"for season={season}; using hardcoded top-{n} list"
            )
        # Aggregate latest snap file: sum offense_pct per team, take top-n.
        df = pd.read_parquet(snap_files[-1])
        if "team" not in df.columns or "offense_pct" not in df.columns:
            return _TOP_10_TEAMS_FALLBACK[:n], (
                "SAMPLING FALLBACK: snaps schema unexpected"
            )
        ranked = (
            df.groupby("team")["offense_pct"]
            .sum()
            .sort_values(ascending=False)
            .head(n)
            .index.tolist()
        )
        return [str(t) for t in ranked], None
    df = pd.read_parquet(parquet_files[-1])
    if "team" not in df.columns:
        return _TOP_10_TEAMS_FALLBACK[:n], (
            "SAMPLING FALLBACK: team_metrics missing 'team' column"
        )
    snap_col = next(
        (
            c
            for c in ("total_offense_snaps", "offense_snaps", "snap_count")
            if c in df.columns
        ),
        None,
    )
    if snap_col is None:
        return _TOP_10_TEAMS_FALLBACK[:n], (
            "SAMPLING FALLBACK: no snap-count column in team_metrics"
        )
    ranked = (
        df.groupby("team")[snap_col]
        .sum()
        .sort_values(ascending=False)
        .head(n)
        .index.tolist()
    )
    return [str(t) for t in ranked], None


def _probe_predictions_endpoint(
    backend_url: str, season: int, week: int
) -> Tuple[List[str], List[str]]:
    """Probe ``/api/predictions``.

    CRITICAL when the endpoint returns any non-200 (especially HTTP 422 — the
    regression from the 2026-04-20 audit). Empty predictions list is accepted
    (offseason / no Bronze schedules).

    Args:
        backend_url: Base URL of the deployed FastAPI backend.
        season: Season query parameter.
        week: Week query parameter.

    Returns:
        ``(criticals, warnings)`` — both are lists of human-readable strings.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    path = f"/api/predictions?season={season}&week={week}"
    url = backend_url.rstrip("/") + path
    try:
        resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        criticals.append(f"LIVE API TIMEOUT (>{_PROBE_TIMEOUT_SECONDS}s): GET {path}")
        print(f"  [FAIL] {path}  (TIMEOUT)")
        return criticals, warnings
    except requests.RequestException as exc:
        criticals.append(
            f"LIVE API UNREACHABLE: GET {path} raised " f"{type(exc).__name__}: {exc}"
        )
        print(f"  [FAIL] {path}  (request error)")
        return criticals, warnings
    if resp.status_code != 200:
        criticals.append(f"LIVE API NON-200: GET {path} returned {resp.status_code}")
        print(f"  [FAIL] {path}  (HTTP {resp.status_code})")
        return criticals, warnings
    try:
        payload = resp.json()
    except ValueError:
        criticals.append(f"LIVE API INVALID JSON: GET {path}")
        print(f"  [FAIL] {path}  (not JSON)")
        return criticals, warnings
    if not isinstance(payload, dict) or "predictions" not in payload:
        criticals.append(
            f"LIVE API UNEXPECTED SHAPE: GET {path} missing 'predictions' key"
        )
        print(f"  [FAIL] {path}  (missing 'predictions' key)")
        return criticals, warnings
    rows = len(payload.get("predictions", []) or [])
    print(f"  [PASS] {path}  ({rows} rows)")
    return criticals, warnings


def _probe_lineups_endpoint(
    backend_url: str, season: int, week: int
) -> Tuple[List[str], List[str]]:
    """Probe ``/api/lineups``.

    CRITICAL when the endpoint returns any non-200 (especially HTTP 422 — the
    regression from the 2026-04-20 audit). Empty lineups list is accepted
    (offseason / no Bronze schedules).

    Args:
        backend_url: Base URL of the deployed FastAPI backend.
        season: Season query parameter.
        week: Week query parameter.

    Returns:
        ``(criticals, warnings)`` — both are lists of human-readable strings.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    path = f"/api/lineups?season={season}&week={week}&scoring=half_ppr"
    url = backend_url.rstrip("/") + path
    try:
        resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        criticals.append(f"LIVE API TIMEOUT (>{_PROBE_TIMEOUT_SECONDS}s): GET {path}")
        print(f"  [FAIL] {path}  (TIMEOUT)")
        return criticals, warnings
    except requests.RequestException as exc:
        criticals.append(
            f"LIVE API UNREACHABLE: GET {path} raised " f"{type(exc).__name__}: {exc}"
        )
        print(f"  [FAIL] {path}  (request error)")
        return criticals, warnings
    if resp.status_code != 200:
        criticals.append(f"LIVE API NON-200: GET {path} returned {resp.status_code}")
        print(f"  [FAIL] {path}  (HTTP {resp.status_code})")
        return criticals, warnings
    try:
        payload = resp.json()
    except ValueError:
        criticals.append(f"LIVE API INVALID JSON: GET {path}")
        print(f"  [FAIL] {path}  (not JSON)")
        return criticals, warnings
    if not isinstance(payload, dict) or "lineups" not in payload:
        criticals.append(f"LIVE API UNEXPECTED SHAPE: GET {path} missing 'lineups' key")
        print(f"  [FAIL] {path}  (missing 'lineups' key)")
        return criticals, warnings
    teams = len(payload.get("lineups", []) or [])
    print(f"  [PASS] {path}  ({teams} teams)")
    return criticals, warnings


def _probe_team_rosters_sampled(
    backend_url: str, season: int
) -> Tuple[List[str], List[str]]:
    """Probe ``/api/teams/{team}/roster`` for top-10 teams by snap count.

    CRITICAL when any sampled team returns non-200 (503 was the 2026-04-20
    regression when Railway's Docker image was missing ``data/bronze/schedules/``).
    Probes sequentially with a 5s timeout each (max ~50s wall time, mitigates
    T-68-01-02 DoS concern).

    Args:
        backend_url: Base URL of the deployed FastAPI backend.
        season: Season used to pick top-10 teams by snap count.

    Returns:
        ``(criticals, warnings)`` — both are lists of human-readable strings.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    teams, fallback_warning = _top_n_teams_by_snap_count(season, n=10)
    if fallback_warning:
        warnings.append(fallback_warning)
    failed_teams: List[str] = []
    for team in teams:
        path = f"/api/teams/{team}/roster"
        url = backend_url.rstrip("/") + path
        # Per-probe budget: timeout=_PROBE_TIMEOUT_SECONDS (5s). Sequential
        # probes (not threaded) to avoid burst load on Railway (T-68-01-02).
        try:
            resp = requests.get(url, timeout=_PROBE_TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            failed_teams.append(f"{team} TIMEOUT(>{_PROBE_TIMEOUT_SECONDS}s)")
            continue
        except requests.RequestException as exc:
            failed_teams.append(f"{team} {type(exc).__name__}")
            continue
        # Only log the status code — never log response body (T-68-01-01).
        if resp.status_code != 200:
            failed_teams.append(f"{team} {resp.status_code}")
            continue
    if failed_teams:
        criticals.append(
            f"LIVE API ROSTER PROBE FAILED for "
            f"{len(failed_teams)}/{len(teams)} sampled teams: "
            + ", ".join(failed_teams)
        )
        print(
            f"  [FAIL] /api/teams/*/roster  "
            f"({len(failed_teams)}/{len(teams)} failed)"
        )
    else:
        print(f"  [PASS] /api/teams/*/roster  " f"(all {len(teams)} sampled teams 200)")
    return criticals, warnings


# ---------------------------------------------------------------------------
# Phase 68 SANITY-04 / SANITY-06 — news content validator + extractor freshness
# ---------------------------------------------------------------------------
# Thresholds sourced from 68-CONTEXT.md "News Content Threshold" decision,
# rebaselined 2026-04-27 against the current data regime. Phase 71 made Claude
# the primary extractor, which shifted attribution toward subject_type='player'
# (and away from team-tagged), naturally lowering the team-events row count.
# Live floor in offseason: ~11/32 (W1) and ~9/32 (W18). The original 17/20
# bar was unreachable in the post-71 regime; the new bar still catches the
# 2026-04-20 "all-zeros" regression that motivated the gate. Revisit at the
# start of the regular season (W2-W17 should produce ≥20 again — tighten then).
_NEWS_CONTENT_MIN_TEAMS_OK = 10  # ≥10 of 32 with total_articles > 0 = PASS
_NEWS_CONTENT_MIN_TEAMS_WARN = 5  # 5..9 = WARNING; <5 = CRITICAL

# Thresholds from 68-CONTEXT.md "Extractor Freshness Window" decision.
_EXTRACTOR_FRESH_HOURS = 24
_EXTRACTOR_STALE_CRITICAL_HOURS = 48


def _validate_team_events_content(payload) -> Tuple[List[str], List[str]]:
    """Validate ``/api/news/team-events`` content (not just length).

    The v1 gate only checked the payload row count (32 teams), which passed
    on the 2026-04-20 regression where all 32 teams had ``total_articles=0``
    because the extractor never ran (ANTHROPIC_API_KEY unset on Railway).
    This validator fails CRITICAL when fewer than
    ``_NEWS_CONTENT_MIN_TEAMS_WARN`` teams have articles, WARN in the
    ``_NEWS_CONTENT_MIN_TEAMS_WARN``..``_NEWS_CONTENT_MIN_TEAMS_OK - 1``
    band, PASS at ``>= _NEWS_CONTENT_MIN_TEAMS_OK``.

    Args:
        payload: JSON body returned by GET /api/news/team-events — expected
            to be a list of 32 TeamEvents dicts.

    Returns:
        ``(criticals, warnings)`` — both are lists of human-readable strings.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    if not isinstance(payload, list) or len(payload) != 32:
        length = len(payload) if hasattr(payload, "__len__") else "n/a"
        criticals.append(
            f"LIVE NEWS PAYLOAD SHAPE: expected list of 32 teams, got "
            f"{type(payload).__name__} len={length}"
        )
        return criticals, warnings
    teams_with_articles = sum(
        1
        for row in payload
        if isinstance(row, dict) and int(row.get("total_articles", 0) or 0) > 0
    )
    if teams_with_articles >= _NEWS_CONTENT_MIN_TEAMS_OK:
        print(
            f"  [PASS] /api/news/team-events content  "
            f"({teams_with_articles}/32 teams have articles)"
        )
    elif teams_with_articles >= _NEWS_CONTENT_MIN_TEAMS_WARN:
        warnings.append(
            f"NEWS CONTENT MARGINAL: {teams_with_articles}/32 teams have "
            f"total_articles > 0 (below target of "
            f"{_NEWS_CONTENT_MIN_TEAMS_OK}; would have caught extractor "
            f"degradation)"
        )
        print(
            f"  [WARN] /api/news/team-events content  "
            f"({teams_with_articles}/32 teams)"
        )
    else:
        criticals.append(
            f"NEWS CONTENT EMPTY: {teams_with_articles}/32 teams have "
            f"total_articles > 0 (threshold {_NEWS_CONTENT_MIN_TEAMS_OK}). "
            f"Extractor likely stalled — this matches the 2026-04-20 audit "
            f"regression."
        )
        print(
            f"  [FAIL] /api/news/team-events content  "
            f"({teams_with_articles}/32 teams — extractor stalled)"
        )
    return criticals, warnings


def _check_extractor_freshness() -> Tuple[List[str], List[str]]:
    """Assert the latest Silver sentiment parquet was written recently.

    Reads ``data/silver/sentiment/signals/season=*/week=*/*.parquet`` and takes
    the max mtime as the "extractor last ran" timestamp. Fails CRITICAL when
    older than ``_EXTRACTOR_STALE_CRITICAL_HOURS`` (48h); WARN in the 24..48h
    window; PASS under 24h. CRITICAL when no parquet files exist at all.

    Trust boundary note (T-68-01-03): local filesystem is trusted; an attacker
    who can spoof parquet mtimes already owns the runner.

    Returns:
        ``(criticals, warnings)`` — both are lists of human-readable strings.
    """
    import time as _time  # local alias to keep top-level imports minimal

    criticals: List[str] = []
    warnings: List[str] = []
    # Phase 71+ extractor writes JSON envelopes (signals/ + signals_enriched/),
    # not parquet. Glob both .json and .parquet to stay forward-compatible if
    # the sink ever flips back to parquet.
    base = os.path.join(
        PROJECT_ROOT,
        "data",
        "silver",
        "sentiment",
        "signals",
        "season=*",
        "week=*",
    )
    parquet_files = globmod.glob(os.path.join(base, "*.json")) + globmod.glob(
        os.path.join(base, "*.parquet")
    )
    if not parquet_files:
        criticals.append(
            "EXTRACTOR DATA MISSING: no Silver sentiment files found at "
            "data/silver/sentiment/signals/. Extractor has never run or "
            "output path changed."
        )
        print("  [FAIL] Silver sentiment freshness  (no signal files found)")
        return criticals, warnings
    latest_mtime = max(os.path.getmtime(f) for f in parquet_files)
    age_hours = (_time.time() - latest_mtime) / 3600.0
    age_str = f"{age_hours:.1f}h"
    if age_hours <= _EXTRACTOR_FRESH_HOURS:
        print(f"  [PASS] Silver sentiment freshness  (latest write {age_str} ago)")
    elif age_hours <= _EXTRACTOR_STALE_CRITICAL_HOURS:
        warnings.append(
            f"EXTRACTOR STALE: latest Silver sentiment write was {age_str} "
            f"ago (warning at {_EXTRACTOR_FRESH_HOURS}h, critical at "
            f"{_EXTRACTOR_STALE_CRITICAL_HOURS}h)"
        )
        print(f"  [WARN] Silver sentiment freshness  (latest write {age_str} ago)")
    else:
        criticals.append(
            f"EXTRACTOR STALE: latest Silver sentiment write was {age_str} "
            f"ago (threshold {_EXTRACTOR_STALE_CRITICAL_HOURS}h). Daily cron "
            f"has stopped or extractor is failing."
        )
        print(f"  [FAIL] Silver sentiment freshness  (latest write {age_str} ago)")
    return criticals, warnings


# ---------------------------------------------------------------------------
# Phase 68 SANITY-05 — roster drift vs Sleeper canonical (Kyler Murray canary)
# ---------------------------------------------------------------------------
_SLEEPER_PLAYERS_URL = "https://api.sleeper.app/v1/players/nfl"
_SLEEPER_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", ".cache")


def _fetch_sleeper_canonical_cached() -> Tuple[Dict[str, Dict], Optional[str]]:
    """Fetch Sleeper's player universe with a per-day disk cache.

    The Sleeper ``/v1/players/nfl`` response is ~30MB and their docs ask that
    you hit it at most once per day per client. We key the cache on UTC date:
    ``data/.cache/sleeper_players_YYYYMMDD.json``.

    T-68-02-02 mitigation: a network failure returns ``({}, warning)`` rather
    than raising, so an upstream Sleeper outage degrades to a WARNING rather
    than a CRITICAL — we never block our deploy on their availability.

    Returns:
        Tuple of ``(players_dict, warning_msg)``. ``players_dict`` is the
        raw Sleeper payload keyed by ``sleeper_player_id`` (empty dict on
        fetch failure). ``warning_msg`` is ``None`` on success, otherwise a
        human-readable warning string the caller should surface as WARNING.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_path = os.path.join(_SLEEPER_CACHE_DIR, f"sleeper_players_{today}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path) as fh:
                return json.load(fh), None
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Sleeper cache corrupt (%s); re-fetching", exc)
    try:
        resp = requests.get(_SLEEPER_PLAYERS_URL, timeout=30)
        resp.raise_for_status()
        players = resp.json()
    except requests.RequestException as exc:
        return {}, (
            f"SLEEPER API UNREACHABLE ({type(exc).__name__}: {exc}); "
            f"skipping roster drift check — this is a WARNING, not CRITICAL, "
            f"so upstream outages do not block deploy"
        )
    os.makedirs(_SLEEPER_CACHE_DIR, exist_ok=True)
    try:
        with open(cache_path, "w") as fh:
            json.dump(players, fh)
    except OSError as exc:
        logger.warning("Failed to write Sleeper cache to %s: %s", cache_path, exc)
    return players, None


def _check_roster_drift_top50(scoring: str, season: int) -> Tuple[List[str], List[str]]:
    """SANITY-05: top-50 PPR players' teams must match Sleeper canonical.

    For each of the top-50 players in latest Gold projections (by
    ``projected_points`` descending), fetch Sleeper's canonical team
    assignment via :func:`_fetch_sleeper_canonical_cached` and emit one
    CRITICAL per mismatched player. The Kyler Murray ARI→FA case from the
    2026-04-20 audit is the acceptance canary.

    Severity policy (T-68-02-04):
        - Each mismatched player produces exactly one CRITICAL so flooding
          cannot mask other regression classes in the aggregate count.
        - Sleeper-unreachable degrades to a single WARNING (not CRITICAL).
        - Player not found in Sleeper at all → WARNING, not CRITICAL (could
          be a rookie Sleeper has not catalogued yet).

    Args:
        scoring: Scoring format passed to ``_load_our_projections`` (e.g.
            ``"half_ppr"``).
        season: Target season year for Gold projection lookup.

    Returns:
        ``(criticals, warnings)`` — both lists of human-readable messages.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    try:
        our_df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(
            f"ROSTER DRIFT SKIPPED: no Gold projections for season={season} ({exc})"
        )
        return criticals, warnings
    if our_df is None or our_df.empty:
        warnings.append("ROSTER DRIFT SKIPPED: Gold projections empty")
        return criticals, warnings
    # Schema resolution: tests inject ``projected_points`` (plan invariant),
    # production Gold uses ``projected_season_points`` (actual schema).
    points_col = (
        "projected_points"
        if "projected_points" in our_df.columns
        else "projected_season_points"
    )
    if points_col not in our_df.columns:
        warnings.append(
            "ROSTER DRIFT SKIPPED: Gold projections missing projected_points / "
            "projected_season_points column"
        )
        return criticals, warnings
    # Team column: tests use ``team``; production Gold uses ``recent_team``.
    team_col = "team" if "team" in our_df.columns else "recent_team"
    top50 = our_df.sort_values(points_col, ascending=False).head(50).copy()

    sleeper_players, fetch_warning = _fetch_sleeper_canonical_cached()
    if fetch_warning:
        warnings.append(fetch_warning)
        return criticals, warnings

    # Build Sleeper name+position -> team lookup. Two players can share a
    # name (e.g. Lamar Jackson QB BAL vs Lamar Jackson CB FA) — keying on
    # name alone causes the FA to overwrite the QB and produces a spurious
    # CRITICAL. Including position disambiguates.
    # ``None`` team signals FA / released / retired per Sleeper's contract.
    # Apply the Sleeper→nflverse normalization for abbreviation differences.
    sleeper_lookup: Dict[Tuple[str, str], Optional[str]] = {}
    for _pid, player in sleeper_players.items():
        if not isinstance(player, dict):
            continue
        name = player.get("full_name") or player.get("search_full_name") or ""
        if not name:
            continue
        position = (player.get("position") or "").upper()
        team_raw = player.get("team")
        if team_raw:
            team = _SLEEPER_TO_NFLVERSE_TEAM.get(team_raw, team_raw)
        else:
            team = None
        sleeper_lookup[(_normalize_name(name), position)] = team

    # Back-compat name-only lookup for Gold rows whose position doesn't
    # match any Sleeper entry (rare — partial Sleeper data).
    sleeper_name_to_team: Dict[str, Optional[str]] = {}
    for (name_key, _pos), team in sleeper_lookup.items():
        # Prefer entries with a real team over None when collapsing.
        if (
            name_key not in sleeper_name_to_team
            or sleeper_name_to_team[name_key] is None
        ):
            sleeper_name_to_team[name_key] = team

    for _, row in top50.iterrows():
        our_name = str(row.get("player_name", ""))
        our_team = str(row.get(team_col, "")).upper()
        our_pos = str(row.get("position", "")).upper()
        if not our_name or not our_team:
            continue
        norm_key = _normalize_name(our_name)
        # Prefer position-specific lookup so name collisions don't map to
        # the wrong player.
        pos_key = (norm_key, our_pos)
        if pos_key in sleeper_lookup:
            sleeper_team = sleeper_lookup[pos_key]
        elif norm_key in sleeper_name_to_team:
            sleeper_team = sleeper_name_to_team[norm_key]
        else:
            # Not found at all — could be a very new rookie. WARN, don't block.
            warnings.append(
                f"ROSTER DRIFT NOT-FOUND: {our_name} (Gold team={our_team}) "
                f"not present in Sleeper canonical"
            )
            continue
        if sleeper_team is None:
            # Present in Sleeper but team is explicitly null -> free agent.
            # If our Gold also marks them FA we agree (no drift). Only flag
            # when we have an actual team and Sleeper says FA — that's the
            # Kyler Murray ARI→FA acceptance canary the original test pinned.
            if our_team in ("FA", "", "NONE", "N/A"):
                continue
            criticals.append(
                f"ROSTER DRIFT: {our_name} — Gold says {our_team}, "
                f"Sleeper says FA (free agent / released / retired)"
            )
            continue
        if sleeper_team != our_team:
            criticals.append(
                f"ROSTER DRIFT: {our_name} — Gold says {our_team}, "
                f"Sleeper says {sleeper_team}"
            )

    if not criticals:
        print(f"  [PASS] Roster drift vs Sleeper canonical  (top-50 all match)")
    else:
        print(
            f"  [FAIL] Roster drift vs Sleeper canonical  "
            f"({len(criticals)} mismatches)"
        )
    return criticals, warnings


# ---------------------------------------------------------------------------
# Phase 68 SANITY-07 + SANITY-10 — API key + DQAL-03 carry-over assertions
# ---------------------------------------------------------------------------
# Thresholds come verbatim from 68-CONTEXT.md "DQAL-03 Carry-Over Assertions".
_DQAL_MIN_ROOKIES = 50
_DQAL_MAX_RANK_GAP = 25


def _assert_api_key_when_enrichment_enabled() -> Tuple[List[str], List[str]]:
    """SANITY-07: when LLM enrichment is on, ANTHROPIC_API_KEY must be set.

    This catches the 2026-04-20 regression where ``ENABLE_LLM_ENRICHMENT=true``
    was configured but ``ANTHROPIC_API_KEY`` was never set on Railway, causing
    the news extractor to silently no-op.

    T-68-02-01 mitigation: the CRITICAL message names only the env var, never
    echoes the value. We check presence via ``os.environ.get`` and assert
    truthy — the key string itself is never touched, logged, or printed.

    Returns:
        ``(criticals, warnings)`` — criticals is a single-item list when the
        combination is unsafe; empty otherwise.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    enrichment_flag = os.environ.get("ENABLE_LLM_ENRICHMENT", "false").lower()
    if enrichment_flag not in ("true", "1", "yes"):
        print("  [PASS] LLM enrichment disabled — API key check skipped")
        return criticals, warnings
    if not os.environ.get("ANTHROPIC_API_KEY"):
        criticals.append(
            "API KEY MISSING: ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY "
            "is unset. This silently no-ops the news extractor (the 2026-04-20 "
            "audit regression)."
        )
        print("  [FAIL] ANTHROPIC_API_KEY unset while ENABLE_LLM_ENRICHMENT=true")
    else:
        print("  [PASS] ANTHROPIC_API_KEY is set (ENABLE_LLM_ENRICHMENT=true)")
    return criticals, warnings


def _check_dqal_negative_projection(
    scoring: str, season: int
) -> Tuple[List[str], List[str]]:
    """SANITY-10: no player may have ``projected_points < 0`` in Gold.

    The negative-projection clamp is an invariant of
    :mod:`src.scoring_calculator` for all skill positions. A negative value
    in the latest Gold parquet is a DQAL-03 deferred assertion and indicates a
    projection-engine regression that must block deploy.

    Up to five offenders are sampled into a single aggregated CRITICAL to
    keep output bounded (T-68-02-04: one regression class -> one CRITICAL).

    Args:
        scoring: Scoring format for Gold projection lookup.
        season: Target season year.

    Returns:
        ``(criticals, warnings)``.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    try:
        df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"DQAL NEGATIVE-CLAMP SKIPPED: {exc}")
        return criticals, warnings
    if df is None or df.empty:
        warnings.append("DQAL NEGATIVE-CLAMP SKIPPED: Gold projections empty")
        return criticals, warnings
    # Schema resolution: tests inject ``projected_points`` (plan invariant),
    # production Gold uses ``projected_season_points``.
    points_col = (
        "projected_points"
        if "projected_points" in df.columns
        else "projected_season_points"
    )
    if points_col not in df.columns:
        warnings.append(
            "DQAL NEGATIVE-CLAMP SKIPPED: Gold projections missing "
            "projected_points / projected_season_points column"
        )
        return criticals, warnings
    negative = df[df[points_col] < 0]
    if len(negative) > 0:
        sample = ", ".join(
            f"{row.get('player_name', '?')} ({row[points_col]:.2f})"
            for _, row in negative.head(5).iterrows()
        )
        criticals.append(
            f"NEGATIVE PROJECTION: {len(negative)} player(s) have "
            f"{points_col} < 0. First {min(5, len(negative))}: {sample}. "
            f"Clamp invariant violated."
        )
        print(f"  [FAIL] DQAL negative-clamp  ({len(negative)} violations)")
    else:
        print(
            f"  [PASS] DQAL negative-clamp  (all {len(df)} players "
            f"{points_col} >= 0)"
        )
    return criticals, warnings


def _check_dqal_rookie_ingestion(
    season: int = 2025,
) -> Tuple[List[str], List[str]]:
    """SANITY-10: at least ``_DQAL_MIN_ROOKIES`` rookies must exist in Bronze.

    Reads ``data/bronze/players/rookies/season=<season>/*.parquet`` and
    requires at least 50 rows. Missing directory or <50 rows is a CRITICAL.

    Args:
        season: Target season year (default 2025 — the 2026 draft class).

    Returns:
        ``(criticals, warnings)``.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    rookies_dir = os.path.join(
        PROJECT_ROOT, "data", "bronze", "players", "rookies", f"season={season}"
    )
    if not os.path.isdir(rookies_dir):
        criticals.append(
            f"ROOKIE INGESTION MISSING: {rookies_dir} not found. "
            f"2025 rookie ingestion has never run."
        )
        print(f"  [FAIL] DQAL rookie ingestion  (path missing: {rookies_dir})")
        return criticals, warnings
    parquet_files = sorted(globmod.glob(os.path.join(rookies_dir, "*.parquet")))
    if not parquet_files:
        criticals.append(
            f"ROOKIE INGESTION MISSING: no parquet files in {rookies_dir}. "
            f"Ingestion partially completed but produced no output."
        )
        print(f"  [FAIL] DQAL rookie ingestion  (no parquet in dir)")
        return criticals, warnings
    df = pd.read_parquet(parquet_files[-1])
    row_count = len(df)
    if row_count < _DQAL_MIN_ROOKIES:
        criticals.append(
            f"ROOKIE INGESTION THIN: found {row_count} rookies in "
            f"{os.path.basename(parquet_files[-1])}, need >= "
            f"{_DQAL_MIN_ROOKIES}. Partial ingestion detected."
        )
        print(f"  [FAIL] DQAL rookie ingestion  ({row_count} < {_DQAL_MIN_ROOKIES})")
    else:
        print(
            f"  [PASS] DQAL rookie ingestion  ({row_count} rookies in "
            f"season={season})"
        )
    return criticals, warnings


# ---------------------------------------------------------------------------
# Thresholds for _check_projection_incorporates_recent_season (SANITY-11)
# ---------------------------------------------------------------------------
# Minimum season-1 actual fantasy points (PPR) for a player to count as a
# "significant producer" when checking first-season-only players.
_RECENT_SEASON_MIN_ACTUAL_PTS = 100.0
# Maximum fraction of the top-30 season-1 skill producers that may be absent
# from the current projection (zero pts OR flagged is_low_sample_projection).
# Exceeding this fraction indicates the projection ignored season-1 data.
_RECENT_SEASON_MAX_BAD_FRACTION = 0.40
# For the more sensitive first-season-only player check: maximum fraction of
# top-N debut-season players (those with zero prior-season NFL data) that may
# be flagged is_low_sample_projection in the current projection.  Even a
# modest fraction signals the projection engine fell back to its rookie
# baseline instead of incorporating their completed season stats.
_RECENT_SEASON_MAX_DEBUT_BAD_FRACTION = 0.40
# How many debut-season players to include in the targeted check.
_RECENT_SEASON_DEBUT_TOP_N = 15
# Skill positions considered for fantasy relevance.
_SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}


def _check_projection_incorporates_recent_season(
    season: int,
    scoring: str,
) -> Tuple[List[str], List[str]]:
    """SANITY-11: confirm the projection used ``season-1`` completed-season data.

    This check was introduced after a bug where the 2026 preseason projection
    was silently built on 2024 data only because a network 404 from nfl-data-py
    for the 2025 season was swallowed.  The symptom: players who had their
    first significant NFL season in 2025 (Ashton Jeanty, Cam Ward, Tetairoa
    McMillan, etc.) were either missing from the projection or flagged as
    ``is_low_sample_projection=True``, indicating the engine fell back to
    conservative rookie baselines instead of using their actual 2025 stats.

    Two complementary sub-checks are run:

    **Broad coverage check** — For the top-30 skill-position fantasy producers
    from ``season-1`` Bronze seasonal actuals, verify that ≤40% are absent
    (``projected_season_points <= 0``) or flagged ``is_low_sample_projection``
    in the current Gold projection.  Veterans dominate this list so the
    fraction is typically <5%; a value >40% indicates a catastrophic data drop.

    **Debut-season player check** (the more sensitive signal) — Identify
    players whose *first* NFL season was ``season-1`` (no prior-season data in
    Bronze seasonal) and rank them by ``season-1`` actual points.  Among the
    top-``_RECENT_SEASON_DEBUT_TOP_N`` such players who scored above
    ``_RECENT_SEASON_MIN_ACTUAL_PTS``, if >40% are flagged
    ``is_low_sample_projection`` in the current projection, that is strong
    evidence the projection engine never saw their completed season.

    Args:
        season: The target projection season (e.g., 2026).
        scoring: Scoring format string used to locate the Gold projection file.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    prior_season = season - 1

    # ------------------------------------------------------------------
    # 1. Load season-1 Bronze seasonal actuals
    # ------------------------------------------------------------------
    bronze_seasonal_dir = os.path.join(
        PROJECT_ROOT,
        "data",
        "bronze",
        "players",
        "seasonal",
        f"season={prior_season}",
    )
    parquet_files = sorted(globmod.glob(os.path.join(bronze_seasonal_dir, "*.parquet")))
    if not parquet_files:
        warnings.append(
            f"RECENT-SEASON CHECK SKIPPED: no Bronze seasonal parquet found for "
            f"season={prior_season} at {bronze_seasonal_dir}. Cannot verify "
            f"projection incorporates recent data."
        )
        print(
            f"  [SKIP] SANITY-11 recent-season check  "
            f"(no Bronze seasonal data for season={prior_season})"
        )
        return criticals, warnings

    try:
        actuals_df = pd.read_parquet(parquet_files[-1])
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"RECENT-SEASON CHECK SKIPPED: failed to read Bronze seasonal for "
            f"season={prior_season}: {exc}"
        )
        return criticals, warnings

    # Filter to skill positions; require player_display_name and fantasy_points_ppr.
    if "player_display_name" not in actuals_df.columns:
        warnings.append(
            f"RECENT-SEASON CHECK SKIPPED: Bronze seasonal season={prior_season} "
            f"missing player_display_name column."
        )
        return criticals, warnings
    if "fantasy_points_ppr" not in actuals_df.columns:
        warnings.append(
            f"RECENT-SEASON CHECK SKIPPED: Bronze seasonal season={prior_season} "
            f"missing fantasy_points_ppr column."
        )
        return criticals, warnings

    if "position" in actuals_df.columns:
        actuals_df = actuals_df[actuals_df["position"].isin(_SKILL_POSITIONS)]

    top30_prior = actuals_df.nlargest(30, "fantasy_points_ppr")

    # ------------------------------------------------------------------
    # 2. Load current preseason projection
    # ------------------------------------------------------------------
    try:
        proj_df = _load_our_projections(scoring, season)
    except FileNotFoundError as exc:
        warnings.append(f"RECENT-SEASON CHECK SKIPPED: {exc}")
        return criticals, warnings

    if proj_df is None or proj_df.empty:
        warnings.append("RECENT-SEASON CHECK SKIPPED: Gold projections empty.")
        return criticals, warnings

    if "player_name" not in proj_df.columns:
        warnings.append(
            "RECENT-SEASON CHECK SKIPPED: Gold projection missing player_name column."
        )
        return criticals, warnings

    points_col = (
        "projected_points"
        if "projected_points" in proj_df.columns
        else "projected_season_points"
    )
    if points_col not in proj_df.columns:
        warnings.append(
            "RECENT-SEASON CHECK SKIPPED: Gold projection missing "
            "projected_points / projected_season_points column."
        )
        return criticals, warnings

    has_low_sample_col = "is_low_sample_projection" in proj_df.columns

    def _extract_last_name(name: str) -> str:
        """Return lowercase last name, stripping suffixes and handling abbreviations."""
        import re as _re

        n = name.strip().lower()
        for suf in [" jr.", " jr", " iii", " ii", " iv", " sr.", " sr"]:
            n = n.replace(suf, "")
        # Abbreviated form "F.Lastname" → take after the dot
        if _re.match(r"^[a-z]\.", n):
            return n.split(".", 1)[1].strip()
        parts = n.split()
        return parts[-1] if parts else n

    proj_df = proj_df.copy()
    proj_df["_last_name"] = proj_df["player_name"].apply(_extract_last_name)

    def _is_low_sample(val: object) -> bool:
        """Return True for any truthy representation of low_sample flag."""
        return val in (True, "True", "true", 1, "1")

    # ------------------------------------------------------------------
    # 3. Broad coverage check: top-30 season-1 producers
    # ------------------------------------------------------------------
    broad_missing: List[str] = []
    broad_low_sample: List[str] = []

    for _, row in top30_prior.iterrows():
        display = row.get("player_display_name", "")
        if not display:
            continue
        ln = _extract_last_name(display)
        matches = proj_df[proj_df["_last_name"] == ln]
        if matches.empty or matches[points_col].iloc[0] <= 0:
            broad_missing.append(display)
        elif has_low_sample_col and _is_low_sample(
            matches["is_low_sample_projection"].iloc[0]
        ):
            broad_low_sample.append(display)

    n_broad_bad = len(broad_missing) + len(broad_low_sample)
    broad_frac = n_broad_bad / max(len(top30_prior), 1)

    if broad_frac > _RECENT_SEASON_MAX_BAD_FRACTION:
        sample = (broad_missing + broad_low_sample)[:5]
        criticals.append(
            f"PROJECTION IGNORES RECENT SEASON: {n_broad_bad}/{len(top30_prior)} "
            f"({broad_frac:.0%}) of the top-30 season={prior_season} skill producers "
            f"are absent or low-sample in the season={season} projection — "
            f"threshold is {_RECENT_SEASON_MAX_BAD_FRACTION:.0%}. "
            f"First offenders: {', '.join(sample)}. "
            f"Likely cause: season={prior_season} data was dropped during ingestion."
        )
        print(
            f"  [FAIL] SANITY-11 recent-season (broad)  "
            f"({n_broad_bad}/{len(top30_prior)} = {broad_frac:.0%} bad, "
            f"threshold {_RECENT_SEASON_MAX_BAD_FRACTION:.0%})"
        )
    else:
        print(
            f"  [PASS] SANITY-11 recent-season (broad)  "
            f"({n_broad_bad}/{len(top30_prior)} bad, {broad_frac:.0%} ≤ "
            f"{_RECENT_SEASON_MAX_BAD_FRACTION:.0%})"
        )

    # ------------------------------------------------------------------
    # 4. Debut-season player check: players whose first NFL season was season-1
    #
    # A projection built on season-2 (or older) data would flag these players
    # as low_sample because the engine has no completed-season stats for them.
    # This check is the sensitive signal for the "2025 data swallowed" bug class.
    # ------------------------------------------------------------------
    prior_prior_season = prior_season - 1
    prior_prior_dir = os.path.join(
        PROJECT_ROOT,
        "data",
        "bronze",
        "players",
        "seasonal",
        f"season={prior_prior_season}",
    )
    prior_prior_files = sorted(globmod.glob(os.path.join(prior_prior_dir, "*.parquet")))
    if not prior_prior_files:
        # Cannot determine debut-season players without season-2 data; skip sub-check.
        print(
            f"  [SKIP] SANITY-11 recent-season (debut)  "
            f"(no Bronze seasonal data for season={prior_prior_season}; "
            f"cannot identify debut-season players)"
        )
        return criticals, warnings

    try:
        prior_prior_df = pd.read_parquet(prior_prior_files[-1])
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"RECENT-SEASON DEBUT CHECK SKIPPED: could not read season={prior_prior_season} "
            f"Bronze seasonal: {exc}"
        )
        return criticals, warnings

    # player_id column must exist for debut detection
    if (
        "player_id" not in actuals_df.columns
        or "player_id" not in prior_prior_df.columns
    ):
        print(
            f"  [SKIP] SANITY-11 recent-season (debut)  "
            f"(player_id column missing from Bronze seasonal files)"
        )
        return criticals, warnings

    ids_with_prior_data = set(prior_prior_df["player_id"].dropna().tolist())
    debut_players = actuals_df[~actuals_df["player_id"].isin(ids_with_prior_data)]
    top_debut = (
        debut_players.nlargest(_RECENT_SEASON_DEBUT_TOP_N, "fantasy_points_ppr")
        if len(debut_players) >= _RECENT_SEASON_DEBUT_TOP_N
        else debut_players.sort_values("fantasy_points_ppr", ascending=False)
    )
    # Only evaluate players who scored above the significance floor.
    top_debut = top_debut[
        top_debut["fantasy_points_ppr"] >= _RECENT_SEASON_MIN_ACTUAL_PTS
    ]

    if top_debut.empty:
        print(
            f"  [SKIP] SANITY-11 recent-season (debut)  "
            f"(no debut-season players above {_RECENT_SEASON_MIN_ACTUAL_PTS:.0f} pts "
            f"threshold found for season={prior_season})"
        )
        return criticals, warnings

    debut_low_sample: List[str] = []
    debut_missing: List[str] = []

    for _, row in top_debut.iterrows():
        display = row.get("player_display_name", "")
        if not display:
            continue
        ln = _extract_last_name(display)
        actual_pts = row["fantasy_points_ppr"]
        matches = proj_df[proj_df["_last_name"] == ln]
        if matches.empty or matches[points_col].iloc[0] <= 0:
            debut_missing.append(f"{display} (actual={actual_pts:.0f})")
        elif has_low_sample_col and _is_low_sample(
            matches["is_low_sample_projection"].iloc[0]
        ):
            debut_low_sample.append(f"{display} (actual={actual_pts:.0f})")

    n_debut_bad = len(debut_missing) + len(debut_low_sample)
    n_debut_total = len(top_debut)
    debut_frac = n_debut_bad / max(n_debut_total, 1)

    if debut_frac > _RECENT_SEASON_MAX_DEBUT_BAD_FRACTION:
        offenders = (debut_missing + debut_low_sample)[:5]
        criticals.append(
            f"PROJECTION IGNORES RECENT SEASON (debut-class): {n_debut_bad}/{n_debut_total} "
            f"({debut_frac:.0%}) of the top season={prior_season} debut-class players "
            f"are absent or low-sample in the season={season} projection — "
            f"threshold is {_RECENT_SEASON_MAX_DEBUT_BAD_FRACTION:.0%}. "
            f"These players had their first NFL season in {prior_season} and the projection "
            f"should reflect their completed stats, not rookie fallback baselines. "
            f"First offenders: {', '.join(offenders)}. "
            f"Likely cause: season={prior_season} data was dropped during ingestion "
            f"(e.g., nfl-data-py network 404 silently swallowed)."
        )
        print(
            f"  [FAIL] SANITY-11 recent-season (debut)  "
            f"({n_debut_bad}/{n_debut_total} = {debut_frac:.0%} bad, "
            f"threshold {_RECENT_SEASON_MAX_DEBUT_BAD_FRACTION:.0%})"
        )
    else:
        print(
            f"  [PASS] SANITY-11 recent-season (debut)  "
            f"({n_debut_bad}/{n_debut_total} bad, {debut_frac:.0%} ≤ "
            f"{_RECENT_SEASON_MAX_DEBUT_BAD_FRACTION:.0%})"
        )

    return criticals, warnings


def _check_dqal_rank_gap(
    season: int = 2026,
) -> Tuple[List[str], List[str]]:
    """SANITY-10: no consecutive rank gap > ``_DQAL_MAX_RANK_GAP`` in rankings.

    Reads ``data/gold/rankings/season=<season>/*.parquet`` (preferred) and
    falls back to ``data/adp_latest.csv``. Flags the maximum consecutive gap
    between sorted ranks as CRITICAL when it exceeds 25 — this typically
    indicates missing players in the external rankings feed.

    Args:
        season: Target season year.

    Returns:
        ``(criticals, warnings)``.
    """
    criticals: List[str] = []
    warnings: List[str] = []
    rank_glob = os.path.join(
        PROJECT_ROOT, "data", "gold", "rankings", f"season={season}", "*.parquet"
    )
    rank_files = sorted(globmod.glob(rank_glob))
    rank_df: Optional[pd.DataFrame] = None
    if rank_files:
        rank_df = pd.read_parquet(rank_files[-1])
    else:
        adp_csv = os.path.join(PROJECT_ROOT, "data", "adp_latest.csv")
        if os.path.exists(adp_csv):
            rank_df = pd.read_csv(adp_csv)
    if rank_df is None or rank_df.empty:
        warnings.append(
            f"DQAL RANK-GAP SKIPPED: no external rankings file for " f"season={season}"
        )
        return criticals, warnings
    rank_col = next(
        (c for c in ("rank", "overall_rank", "adp", "ecr") if c in rank_df.columns),
        None,
    )
    if rank_col is None:
        warnings.append("DQAL RANK-GAP SKIPPED: no rank column in rankings schema")
        return criticals, warnings
    sorted_ranks = rank_df[rank_col].dropna().sort_values().astype(int).tolist()
    if len(sorted_ranks) < 2:
        warnings.append(
            f"DQAL RANK-GAP SKIPPED: fewer than 2 ranks in schema "
            f"({len(sorted_ranks)})"
        )
        return criticals, warnings
    max_gap = 0
    gap_boundary: Optional[Tuple[int, int]] = None
    for prev, curr in zip(sorted_ranks, sorted_ranks[1:]):
        gap = curr - prev
        if gap > max_gap:
            max_gap = gap
            gap_boundary = (prev, curr)
    if max_gap > _DQAL_MAX_RANK_GAP:
        assert gap_boundary is not None
        criticals.append(
            f"RANK GAP: rank {gap_boundary[0]} → rank {gap_boundary[1]} "
            f"(gap={max_gap}, threshold={_DQAL_MAX_RANK_GAP}). External "
            f"rankings likely have missing players."
        )
        print(f"  [FAIL] DQAL rank-gap  (max gap {max_gap} > {_DQAL_MAX_RANK_GAP})")
    else:
        print(
            f"  [PASS] DQAL rank-gap  (max consecutive gap {max_gap} <= "
            f"{_DQAL_MAX_RANK_GAP})"
        )
    return criticals, warnings


def run_live_site_check(
    backend_url: str,
    frontend_url: str,
    season: int,
) -> Tuple[List[str], List[str]]:
    """Probe the deployed API + frontend to catch deploy-only breakage.

    This guards against the class of bug that doesn't show up in local Parquet
    freshness or eye-test checks: backend starts but ModuleNotFoundError
    crashes requests; frontend HTML renders but client bundle never boots, so
    /dashboard/projections returns 200 with only skeleton placeholders.

    Returns (criticals, warnings). Empty criticals == PASS.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    print("\n" + "-" * 70)
    print("  LIVE SITE CHECK")
    print("-" * 70)

    # ------------------------------------------------------------------
    # Backend endpoints — non-empty JSON payload contracts
    # ------------------------------------------------------------------
    # Phase 68: the /api/news/team-events entry previously used a weak
    # row-count-only contract that passed on fully-empty payloads (the
    # 2026-04-20 regression). Content validation is now handled below by
    # ``_validate_team_events_content`` after a dedicated fetch.
    api_probes = [
        ("/api/health", lambda d: d.get("status") == "ok"),
        (
            f"/api/projections?season={season}&week=1&scoring=half_ppr&limit=10",
            lambda d: isinstance(d.get("projections"), list)
            and len(d["projections"]) > 0,
        ),
        (
            f"/api/projections/latest-week?season={season}",
            lambda d: d.get("season") == season and d.get("week") is not None,
        ),
    ]
    for path, validator in api_probes:
        url = backend_url.rstrip("/") + path
        try:
            resp = requests.get(url, timeout=15)
        except requests.RequestException as exc:
            criticals.append(
                f"LIVE API UNREACHABLE: GET {path} raised {type(exc).__name__}: {exc}"
            )
            print(f"  [FAIL] {path}  (request error)")
            continue
        if resp.status_code != 200:
            criticals.append(
                f"LIVE API NON-200: GET {path} returned {resp.status_code}"
            )
            print(f"  [FAIL] {path}  (HTTP {resp.status_code})")
            continue
        try:
            payload = resp.json()
        except ValueError:
            criticals.append(f"LIVE API INVALID JSON: GET {path}")
            print(f"  [FAIL] {path}  (not JSON)")
            continue
        try:
            passed = bool(validator(payload))
        except (AttributeError, TypeError, KeyError, IndexError) as exc:
            criticals.append(
                f"LIVE API UNEXPECTED SHAPE: GET {path} ({type(exc).__name__}: {exc})"
            )
            print(f"  [FAIL] {path}  (unexpected payload shape)")
            continue
        if not passed:
            criticals.append(f"LIVE API EMPTY/INVALID PAYLOAD: GET {path}")
            print(f"  [FAIL] {path}  (payload failed contract)")
            continue
        print(f"  [PASS] {path}")

    # ------------------------------------------------------------------
    # Phase 68 SANITY-01/02/03 — v2 probes (predictions, lineups, sampled
    # rosters). These cover the HTTP 422/503 regressions the pre-v7.0 gate
    # missed entirely: the v1 loop above never probed these endpoints.
    # ------------------------------------------------------------------
    pred_crit, pred_warn = _probe_predictions_endpoint(backend_url, season, week=1)
    criticals.extend(pred_crit)
    warnings.extend(pred_warn)

    line_crit, line_warn = _probe_lineups_endpoint(backend_url, season, week=1)
    criticals.extend(line_crit)
    warnings.extend(line_warn)

    rost_crit, rost_warn = _probe_team_rosters_sampled(backend_url, season)
    criticals.extend(rost_crit)
    warnings.extend(rost_warn)

    # ------------------------------------------------------------------
    # Phase 68 SANITY-04 — content-aware validation of /api/news/team-events.
    # Replaces the pre-v7.0 row-count-only contract (which passed on fully
    # empty payloads). CRITICAL when fewer than 17 of 32 teams have articles.
    # ------------------------------------------------------------------
    news_path = "/api/news/team-events?season=2025&week=1"
    news_url = backend_url.rstrip("/") + news_path
    try:
        news_resp = requests.get(news_url, timeout=_PROBE_TIMEOUT_SECONDS)
    except requests.exceptions.Timeout:
        criticals.append(
            f"LIVE API TIMEOUT (>{_PROBE_TIMEOUT_SECONDS}s): GET {news_path}"
        )
        print(f"  [FAIL] {news_path}  (TIMEOUT)")
    except requests.RequestException as exc:
        criticals.append(
            f"LIVE API UNREACHABLE: GET {news_path} raised "
            f"{type(exc).__name__}: {exc}"
        )
        print(f"  [FAIL] {news_path}  (request error)")
    else:
        if news_resp.status_code != 200:
            criticals.append(
                f"LIVE API NON-200: GET {news_path} returned "
                f"{news_resp.status_code}"
            )
            print(f"  [FAIL] {news_path}  (HTTP {news_resp.status_code})")
        else:
            try:
                news_payload = news_resp.json()
            except ValueError:
                criticals.append(f"LIVE API INVALID JSON: GET {news_path}")
                print(f"  [FAIL] {news_path}  (not JSON)")
            else:
                news_crit, news_warn = _validate_team_events_content(news_payload)
                criticals.extend(news_crit)
                warnings.extend(news_warn)

    # ------------------------------------------------------------------
    # Phase 68 SANITY-06 — assert the daily-cron Silver sentiment extractor
    # is still running. Local-filesystem check (no URL dependency).
    # ------------------------------------------------------------------
    fresh_crit, fresh_warn = _check_extractor_freshness()
    criticals.extend(fresh_crit)
    warnings.extend(fresh_warn)

    # ------------------------------------------------------------------
    # Frontend — HTML content markers
    # ------------------------------------------------------------------
    # The dashboard is auth-gated by Clerk, so an unauthenticated GET lands on
    # the sign-in page. Both outcomes are acceptable; what we want to catch is
    # an unexpected 5xx or a totally blank body.
    frontend_probes = [
        ("/", ["NFL", "Analytics"]),  # marketing/home should always mention the brand
        (
            "/dashboard/projections",
            ["Projections"],  # title survives the auth redirect via meta tags
        ),
    ]
    for path, required_markers in frontend_probes:
        url = frontend_url.rstrip("/") + path
        try:
            resp = requests.get(url, timeout=20, allow_redirects=True)
        except requests.RequestException as exc:
            warnings.append(
                f"LIVE FRONTEND UNREACHABLE: GET {path} raised {type(exc).__name__}: {exc}"
            )
            print(f"  [WARN] {path}  (request error)")
            continue
        if resp.status_code >= 500:
            criticals.append(
                f"LIVE FRONTEND 5xx: GET {path} returned {resp.status_code}"
            )
            print(f"  [FAIL] {path}  (HTTP {resp.status_code})")
            continue
        body = resp.text or ""
        if len(body) < 500:
            criticals.append(
                f"LIVE FRONTEND EMPTY BODY: GET {path} ({len(body)} bytes)"
            )
            print(f"  [FAIL] {path}  (body too small: {len(body)} bytes)")
            continue
        missing = [m for m in required_markers if m not in body]
        if missing:
            warnings.append(f"LIVE FRONTEND MISSING MARKERS at {path}: {missing}")
            print(f"  [WARN] {path}  (missing: {missing})")
            continue
        print(f"  [PASS] {path}  ({len(body)} bytes)")

    return criticals, warnings


# ---------------------------------------------------------------------------
# Weekly projection sanity check (M6)
# ---------------------------------------------------------------------------
# Single-week projected-points bands (half-PPR). Calibrated against
# 2024–2025 in-season weekly Gold files: QB top typically 15–25,
# absolute lower bound 8 (bye-week-heavy week) and upper bound 45
# (extreme outlier ceiling). Season-scale values (100+) in a weekly
# file are a hard bug.
_WEEKLY_POINTS_BANDS: Dict[str, Tuple[float, float]] = {
    "QB": (8.0, 50.0),
    "RB": (5.0, 40.0),
    "WR": (4.0, 35.0),
    "TE": (3.0, 25.0),
}
# Any position1 value above this is unambiguously season-scale in a weekly file.
_WEEKLY_SEASON_SCALE_THRESHOLD = 60.0

# Freshness threshold for weekly projection files (same as GOLD_MAX_AGE_DAYS
# so a 6-week-old file hard-fails identically to other Gold freshness gates).
_WEEKLY_MAX_AGE_DAYS = GOLD_MAX_AGE_DAYS  # 7 days

# Top-N consensus players at each position to validate rank placement.
# For each position we take the consensus top-5 and verify every one that
# appears in our weekly file ranks within our top-20 at that position.
_WEEKLY_CONSENSUS_TOP_N = 5
_WEEKLY_RANK_WINDOW = 20


def _parse_timestamp_from_filename(fname: str) -> Optional[datetime]:
    """Extract the YYYYMMDD_HHMMSS timestamp embedded in a Gold filename.

    Gold filenames follow the pattern ``projections_<scoring>_YYYYMMDD_HHMMSS.parquet``
    or ``predictions_YYYYMMDD_HHMMSS.parquet``. Returns ``None`` when no
    timestamp is found so callers can fall back to filesystem mtime.

    Args:
        fname: Basename of the file (e.g. ``projections_half_ppr_20260501_024908.parquet``).

    Returns:
        Parsed ``datetime`` or ``None`` if the pattern is absent.
    """
    import re as _re

    m = _re.search(r"(\d{8})_(\d{6})", fname)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _load_weekly_projections(
    scoring: str, season: int, week: int
) -> Tuple[Optional[str], pd.DataFrame]:
    """Load the latest weekly projection parquet for (season, week, scoring).

    Args:
        scoring: Scoring format key (``"half_ppr"``, ``"ppr"``, or ``"standard"``).
        season: Target season year.
        week: Target week number (1–18).

    Returns:
        ``(file_path, df)`` where ``file_path`` is the absolute path to the
        loaded parquet file (or ``None`` when no files exist) and ``df`` is the
        loaded DataFrame (empty when no files exist).
    """
    pattern = os.path.join(
        GOLD_DIR,
        f"projections/season={season}/week={week}",
        f"projections_{scoring}_*.parquet",
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return None, pd.DataFrame()

    latest = files[-1]
    try:
        df = pd.read_parquet(latest)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read weekly projection parquet %s: %s", latest, exc)
        return latest, pd.DataFrame()

    print(f"Loaded weekly projections from: {os.path.basename(latest)}")
    print(f"  {len(df)} players, columns: {list(df.columns)[:8]}...")
    return latest, df


def run_weekly_projection_check(
    season: int, week: int, scoring: str
) -> Tuple[List[str], List[str]]:
    """SANITY-M6: validate weekly Gold projection file before deploy.

    Catches the incident class from the stale-file bug (2026-05-01 file
    served six weeks later with season-scale totals, CMC at RB118, Drake
    Maye at QB29, and duplicate rookie-fallback rows).

    Four sub-checks are run:

    1. **Freshness (CRITICAL)**: filename-embedded timestamp must not be
       older than ``_WEEKLY_MAX_AGE_DAYS`` (7 days).  A six-week-old file
       hard-fails this gate.  A missing partition emits SKIP (the API falls
       back to preseason projections — this is acceptable pre-season or for
       future weeks that have not been run yet).

    2. **No duplicate player_ids (CRITICAL)**: same player_id appearing
       more than once indicates a projection-engine merge bug (the
       Fernando Mendoza / Ty Simpson 260.1-pt row pair in the incident).

    3. **Star-player rank sanity (CRITICAL)**: cross-check against Silver
       external_projections (latest available week for the season; falls
       back gracefully with SKIP when unavailable).  For each position,
       take the consensus top-``_WEEKLY_CONSENSUS_TOP_N`` players by
       projected_points and assert each one that appears in our weekly
       file ranks within our top-``_WEEKLY_RANK_WINDOW`` at that position.
       CMC at RB118 hard-fails this check.

    4. **Scale sanity (CRITICAL)**: weekly projected_points for the top
       player at each skill position must fall within ``_WEEKLY_POINTS_BANDS``.
       Lamar Jackson at 483.1 pts (season-scale) in a weekly file is
       unambiguously wrong.  Any value above ``_WEEKLY_SEASON_SCALE_THRESHOLD``
       triggers CRITICAL regardless of position-band.  Non-negative clamp
       is also verified here.

    Args:
        season: Target season year.
        week: Target week number (1–18).
        scoring: Scoring format string (e.g. ``"half_ppr"``).

    Returns:
        ``(criticals, warnings)`` lists of human-readable messages.
    """
    print("\n" + "=" * 70)
    print(
        f"  NFL Weekly Projection Sanity Check — Season {season}, "
        f"Week {week}, {scoring.upper()}"
    )
    print("=" * 70)

    criticals: List[str] = []
    warnings: List[str] = []

    # ------------------------------------------------------------------
    # Load weekly parquet
    # ------------------------------------------------------------------
    file_path, df = _load_weekly_projections(scoring, season, week)

    if file_path is None:
        # Missing partition is acceptable for future/pre-season weeks.
        print(
            f"\n  [SKIP] No weekly projection file found for season={season} "
            f"week={week} scoring={scoring}. "
            f"API will fall back to preseason projections — this is expected "
            f"for future or pre-season weeks."
        )
        return criticals, warnings

    if df.empty:
        criticals.append(
            f"WEEKLY FILE UNREADABLE: {os.path.basename(file_path)} could not "
            f"be loaded as a valid parquet."
        )
        print(f"  [FAIL] Weekly file unreadable: {os.path.basename(file_path)}")
        return criticals, warnings

    # Resolve projected_points column (schema varies between generator versions).
    pts_col = (
        "projected_points"
        if "projected_points" in df.columns
        else "projected_season_points"
    )

    print("\n" + "-" * 70)
    print("  CHECK 1: FILE FRESHNESS")
    print("-" * 70)

    # ------------------------------------------------------------------
    # 1. CRITICAL: Freshness — parse timestamp from filename.
    # ------------------------------------------------------------------
    fname = os.path.basename(file_path)
    file_ts = _parse_timestamp_from_filename(fname)
    if file_ts is None:
        # Fall back to filesystem mtime when filename has no timestamp.
        file_ts = datetime.fromtimestamp(os.path.getmtime(file_path))

    age_days = (datetime.now() - file_ts).days
    if age_days > _WEEKLY_MAX_AGE_DAYS:
        criticals.append(
            f"STALE WEEKLY FILE: {fname} is {age_days} days old "
            f"(threshold: {_WEEKLY_MAX_AGE_DAYS} days). Weekly projection must "
            f"be regenerated before deploy. This is the incident class from "
            f"the 2026-05-01 file served six weeks later."
        )
        print(
            f"  [FAIL] {fname} is {age_days} days old "
            f"(threshold: {_WEEKLY_MAX_AGE_DAYS})"
        )
    else:
        print(
            f"  [PASS] {fname} is {age_days} days old "
            f"(threshold: {_WEEKLY_MAX_AGE_DAYS})"
        )

    print("\n" + "-" * 70)
    print("  CHECK 2: DUPLICATE player_id")
    print("-" * 70)

    # ------------------------------------------------------------------
    # 2. CRITICAL: No duplicate player_ids.
    # ------------------------------------------------------------------
    if "player_id" in df.columns:
        dupe_mask = df.duplicated(subset=["player_id"], keep=False)
        dupes = df[dupe_mask]
        if not dupes.empty:
            dupe_ids = dupes["player_id"].unique().tolist()
            dupe_sample = dupes[["player_id", "player_name", pts_col]].head(6)
            sample_str = "; ".join(
                f"{r['player_name']} ({r[pts_col]:.1f})"
                for _, r in dupe_sample.iterrows()
            )
            criticals.append(
                f"DUPLICATE player_id: {len(dupe_ids)} duplicated player_id(s) "
                f"({len(dupes)} rows). Sample: {sample_str}. "
                f"This was the Fernando Mendoza/Ty Simpson 260.1-pt incident."
            )
            print(
                f"  [FAIL] {len(dupe_ids)} duplicate player_id(s), "
                f"{len(dupes)} affected rows"
            )
        else:
            print(f"  [PASS] No duplicate player_ids ({len(df)} players)")
    else:
        warnings.append(
            "WEEKLY SCHEMA: 'player_id' column absent — duplicate detection skipped."
        )
        print("  [SKIP] No player_id column — duplicate detection skipped")

    print("\n" + "-" * 70)
    print("  CHECK 3: SCALE SANITY (weekly projected_points bands)")
    print("-" * 70)

    # ------------------------------------------------------------------
    # 3. Scale sanity — weekly-scale vs season-scale detection.
    # Non-negative clamp is checked here too.
    # ------------------------------------------------------------------
    if pts_col in df.columns:
        # Check non-negative (skill positions).
        skill_positions = {"QB", "RB", "WR", "TE"}
        pos_col = "position" if "position" in df.columns else None
        if pos_col:
            neg_skill = df[
                df[pos_col].isin(skill_positions) & (df[pts_col] < 0)
            ]
        else:
            neg_skill = df[df[pts_col] < 0]

        if not neg_skill.empty:
            sample = ", ".join(
                f"{r.get('player_name', '?')} ({r[pts_col]:.2f})"
                for _, r in neg_skill.head(5).iterrows()
            )
            criticals.append(
                f"NEGATIVE WEEKLY PTS: {len(neg_skill)} player(s) have "
                f"{pts_col} < 0 in weekly file. First {min(5, len(neg_skill))}: "
                f"{sample}. Clamp invariant violated."
            )
            print(f"  [FAIL] {len(neg_skill)} player(s) have negative projected_points")
        else:
            print(f"  [PASS] Non-negative clamp: all skill-position players >= 0")

        # Check position-specific bands for top player at each position.
        if pos_col:
            for pos, (lo, hi) in _WEEKLY_POINTS_BANDS.items():
                pos_df = df[df[pos_col] == pos]
                if pos_df.empty:
                    continue
                top_val = float(pos_df[pts_col].max())
                player_name = pos_df.loc[pos_df[pts_col].idxmax()].get(
                    "player_name", "?"
                )
                # Any value above the absolute season-scale threshold is
                # unambiguously wrong regardless of the per-position band.
                if top_val > _WEEKLY_SEASON_SCALE_THRESHOLD:
                    criticals.append(
                        f"SEASON-SCALE IN WEEKLY FILE ({pos}): {player_name} has "
                        f"{top_val:.1f} pts — this is season-scale, not weekly. "
                        f"Weekly Gold files must have weekly-scale values "
                        f"(expected {pos}1 in [{lo:.0f}, {hi:.0f}]). "
                        f"This was the Lamar Jackson 483.1 incident."
                    )
                    print(
                        f"  [FAIL] {pos} top player {player_name} = {top_val:.1f} "
                        f"(season-scale threshold: {_WEEKLY_SEASON_SCALE_THRESHOLD})"
                    )
                elif top_val > hi:
                    criticals.append(
                        f"WEEKLY SCALE HIGH ({pos}): {player_name} has "
                        f"{top_val:.1f} pts — above expected weekly band "
                        f"[{lo:.0f}, {hi:.0f}] for {pos}1."
                    )
                    print(
                        f"  [FAIL] {pos} top player {player_name} = {top_val:.1f} "
                        f"(band [{lo:.0f}, {hi:.0f}])"
                    )
                elif top_val < lo:
                    warnings.append(
                        f"WEEKLY SCALE LOW ({pos}): top player {player_name} has "
                        f"{top_val:.1f} pts — below expected weekly floor "
                        f"{lo:.0f}. May be a bye-week-heavy week or pipeline issue."
                    )
                    print(
                        f"  [WARN] {pos} top player {player_name} = {top_val:.1f} "
                        f"(floor {lo:.0f})"
                    )
                else:
                    print(
                        f"  [PASS] {pos} top player {player_name} = {top_val:.1f} "
                        f"in [{lo:.0f}, {hi:.0f}]"
                    )
    else:
        warnings.append(
            f"WEEKLY SCHEMA: '{pts_col}' column absent — scale check skipped."
        )
        print(f"  [SKIP] No {pts_col} column — scale check skipped")

    print("\n" + "-" * 70)
    print("  CHECK 4: STAR-PLAYER RANK SANITY (vs Silver external_projections)")
    print("-" * 70)

    # ------------------------------------------------------------------
    # 4. Star-player rank sanity against Silver external_projections.
    # Fall back gracefully with SKIP when Silver data is unavailable.
    # ------------------------------------------------------------------
    # Determine the best available season for Silver external_projections.
    # The weekly file's season may not have Silver data yet (future season),
    # so we search for the most recent available season <= the target season.
    ext_crit, ext_warn = _check_weekly_star_rank_sanity(df, pts_col, season, week)
    criticals.extend(ext_crit)
    warnings.extend(ext_warn)

    # ------------------------------------------------------------------
    # Print CRITICAL issues
    # ------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("  WEEKLY PROJECTION CRITICAL ISSUES")
    print("-" * 70)
    if criticals:
        for c in criticals:
            print(f"  [CRITICAL] {c}")
    else:
        print("  None — weekly projection checks passed.")

    print("\n" + "-" * 70)
    print("  WEEKLY PROJECTION WARNINGS")
    print("-" * 70)
    if warnings:
        for w in warnings:
            print(f"  [WARNING]  {w}")
    else:
        print("  None — all weekly checks within expected bounds.")

    return criticals, warnings


def _check_weekly_star_rank_sanity(
    weekly_df: pd.DataFrame,
    pts_col: str,
    season: int,
    week: int,
) -> Tuple[List[str], List[str]]:
    """SANITY-M6c: assert consensus top-N stars rank in our weekly top-20.

    Loads the Silver external_projections for the most recent available
    week of the most recent available season <= ``season``. For each
    position, takes the consensus top-``_WEEKLY_CONSENSUS_TOP_N`` players
    by projected_points and verifies each one that appears in our weekly
    file ranks within our top-``_WEEKLY_RANK_WINDOW`` at that position.

    Falls back gracefully with SKIP when Silver data is unavailable — this
    is optional infrastructure (same pattern as ``_check_consensus_cross_check``).

    CMC at RB118 in our weekly file will hard-fail this check because
    he ranks consensus RB1 in Silver external_projections.

    Args:
        weekly_df: Weekly Gold projection DataFrame.
        pts_col: Name of the projected-points column in ``weekly_df``.
        season: Target season year.
        week: Target week number.

    Returns:
        ``(criticals, warnings)`` lists.
    """
    criticals: List[str] = []
    warnings: List[str] = []

    # Find the best available Silver external_projections season.
    ext_season: Optional[int] = None
    for s in range(season, season - 4, -1):
        ext_base = os.path.join(
            PROJECT_ROOT, "data", "silver", "external_projections", f"season={s}"
        )
        if os.path.isdir(ext_base):
            ext_season = s
            break

    if ext_season is None:
        warnings.append(
            "WEEKLY STAR-RANK SKIPPED: no Silver external_projections found for "
            f"season={season} or prior 3 seasons. Run weekly-external-projections "
            "workflow first."
        )
        print("  [SKIP] Star-rank check (no Silver external_projections found)")
        return criticals, warnings

    ext_base = os.path.join(
        PROJECT_ROOT, "data", "silver", "external_projections", f"season={ext_season}"
    )
    week_dirs = sorted(globmod.glob(os.path.join(ext_base, "week=*")))
    if not week_dirs:
        warnings.append(
            f"WEEKLY STAR-RANK SKIPPED: Silver external_projections/season={ext_season}/ "
            "exists but contains no week partitions."
        )
        print(
            f"  [SKIP] Star-rank check (no week partitions for season={ext_season})"
        )
        return criticals, warnings

    # Pick the requested week's partition when it exists; otherwise use latest.
    target_week_dir = os.path.join(ext_base, f"week={week:02d}")
    if not os.path.isdir(target_week_dir):
        target_week_dir = week_dirs[-1]

    ext_files = sorted(globmod.glob(os.path.join(target_week_dir, "*.parquet")))
    if not ext_files:
        warnings.append(
            f"WEEKLY STAR-RANK SKIPPED: no parquet files in {target_week_dir}."
        )
        print("  [SKIP] Star-rank check (no parquet in external_projections week dir)")
        return criticals, warnings

    try:
        ext_df = pd.read_parquet(ext_files[-1])
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"WEEKLY STAR-RANK SKIPPED: could not read {ext_files[-1]}: {exc}"
        )
        return criticals, warnings

    if "projected_points" not in ext_df.columns or "player_name" not in ext_df.columns:
        warnings.append(
            "WEEKLY STAR-RANK SKIPPED: Silver external_projections missing "
            "'projected_points' or 'player_name' column."
        )
        return criticals, warnings

    if "position" not in ext_df.columns:
        warnings.append(
            "WEEKLY STAR-RANK SKIPPED: Silver external_projections missing "
            "'position' column."
        )
        return criticals, warnings

    # Filter to skill positions.
    ext_df = ext_df[ext_df["position"].isin(_FANTASY_POSITIONS)].copy()

    if "scoring_format" in ext_df.columns:
        ext_scoring = ext_df[ext_df["scoring_format"] == "half_ppr"]
        if not ext_scoring.empty:
            ext_df = ext_scoring.copy()

    # Build normalized name lookup in our weekly file.
    if pts_col not in weekly_df.columns or "position" not in weekly_df.columns:
        warnings.append(
            "WEEKLY STAR-RANK SKIPPED: weekly df missing required columns."
        )
        return criticals, warnings

    weekly = weekly_df.copy()
    weekly["_norm"] = weekly["player_name"].apply(_normalize_name)
    ext_df["_norm"] = ext_df["player_name"].apply(_normalize_name)

    # Compute our position ranks if not already present.
    if "position_rank" not in weekly.columns:
        weekly["position_rank"] = weekly.groupby("position")[pts_col].rank(
            ascending=False, method="first"
        )

    n_checked = 0
    n_failed = 0

    for pos in _FANTASY_POSITIONS:
        our_pos = weekly[weekly["position"] == pos].copy()
        ext_pos = ext_df[ext_df["position"] == pos].copy()

        if our_pos.empty or ext_pos.empty:
            continue

        # Consensus top-N by projected_points.
        top_consensus = ext_pos.nlargest(_WEEKLY_CONSENSUS_TOP_N, "projected_points")
        n_checked += len(top_consensus)

        for _, cons_row in top_consensus.iterrows():
            norm = cons_row["_norm"]
            our_rows = our_pos[our_pos["_norm"] == norm]
            if our_rows.empty:
                # Player not in our weekly file — may be injured or bye week.
                # This is a WARNING not CRITICAL since weekly files
                # legitimately omit bye-week players.
                warnings.append(
                    f"WEEKLY STAR MISSING: consensus {pos} star "
                    f"'{cons_row['player_name']}' (ext {pos}#{int(top_consensus.index.get_loc(cons_row.name) + 1)}) "
                    f"not found in our weekly file."
                )
                continue

            our_rank = int(our_rows["position_rank"].iloc[0])
            if our_rank > _WEEKLY_RANK_WINDOW:
                n_failed += 1
                criticals.append(
                    f"WEEKLY STAR RANK ({pos}): '{cons_row['player_name']}' is "
                    f"consensus {pos} top-{_WEEKLY_CONSENSUS_TOP_N} but ranks "
                    f"{pos}#{our_rank} in our weekly file "
                    f"(window: top-{_WEEKLY_RANK_WINDOW}). "
                    f"CMC-at-RB118 incident class."
                )
                print(
                    f"  [FAIL] {pos} star '{cons_row['player_name']}': "
                    f"our rank {pos}#{our_rank} > top-{_WEEKLY_RANK_WINDOW}"
                )
            else:
                print(
                    f"  [PASS] {pos} star '{cons_row['player_name']}': "
                    f"our rank {pos}#{our_rank} within top-{_WEEKLY_RANK_WINDOW}"
                )

    if n_checked == 0:
        warnings.append(
            "WEEKLY STAR-RANK SKIPPED: no position overlap between weekly file "
            "and Silver external_projections."
        )
        print("  [SKIP] Star-rank check (no position overlap)")
    elif n_failed == 0:
        print(
            f"  [PASS] Star-rank check: all {n_checked} consensus stars "
            f"within our top-{_WEEKLY_RANK_WINDOW} per position"
        )
    else:
        print(
            f"  [FAIL] Star-rank check: {n_failed}/{n_checked} consensus stars "
            f"outside our top-{_WEEKLY_RANK_WINDOW}"
        )

    return criticals, warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sanity check NFL projections and/or game predictions"
    )
    parser.add_argument(
        "--scoring",
        choices=["ppr", "half_ppr", "standard"],
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=2026,
        help="Target season (default: 2026)",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Week number for prediction checks (default: None)",
    )
    parser.add_argument(
        "--check-predictions",
        action="store_true",
        help="Validate game predictions/lines instead of projections",
    )
    parser.add_argument(
        "--check-weekly",
        action="store_true",
        help="Validate the weekly Gold projection partition the website "
        "serves (freshness, duplicates, star-player ranks, weekly-scale "
        "points). Catches the stale-file incident class (CMC at RB118).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="check_all",
        help="Run both projection and prediction checks",
    )
    parser.add_argument(
        "--check-live",
        action="store_true",
        help="Also probe the deployed backend + frontend (Railway + Vercel). "
        "Catches deploy-only breakage: backend startup crashes, frontend "
        "skeleton-forever bugs. Fails the run on CRITICAL backend issues.",
    )
    parser.add_argument(
        "--live-backend-url",
        default=DEFAULT_LIVE_BACKEND,
        help=f"Deployed backend URL (default: {DEFAULT_LIVE_BACKEND})",
    )
    parser.add_argument(
        "--live-frontend-url",
        default=DEFAULT_LIVE_FRONTEND,
        help=f"Deployed frontend URL (default: {DEFAULT_LIVE_FRONTEND})",
    )
    args = parser.parse_args()

    run_projections = (
        not args.check_predictions and not args.check_weekly
    ) or args.check_all
    run_predictions = args.check_predictions or args.check_all
    run_weekly = args.check_weekly or args.check_all

    # Resolve the week for the weekly projection check independently of the
    # prediction auto-detect below: a missing partition is a SKIP (the API
    # falls back to preseason), never a hard CLI error.
    weekly_week = args.week
    if run_weekly and weekly_week is None:
        proj_dir = os.path.join(GOLD_DIR, f"projections/season={args.season}")
        week_dirs = sorted(
            globmod.glob(os.path.join(proj_dir, "week=*")),
            key=lambda p: int(os.path.basename(p).split("=")[1]),
        )
        if week_dirs:
            weekly_week = int(os.path.basename(week_dirs[-1]).split("=")[1])
            print(
                f"No --week specified; auto-detected weekly projection "
                f"week {weekly_week}"
            )
        else:
            weekly_week = 1  # run_weekly_projection_check emits SKIP

    if run_predictions and args.week is None:
        # Try to find any available week for the season
        pred_dir = os.path.join(GOLD_DIR, f"predictions/season={args.season}")
        week_dirs = sorted(globmod.glob(os.path.join(pred_dir, "week=*")))
        if week_dirs:
            # Use the latest week available
            latest_week = int(os.path.basename(week_dirs[-1]).split("=")[1])
            print(f"No --week specified; auto-detected week {latest_week}")
            args.week = latest_week
        else:
            print(
                "ERROR: --check-predictions or --all requires --week, "
                "and no prediction weeks found for "
                f"season={args.season}"
            )
            return 1

    # Track overall results
    all_criticals: List[str] = []
    all_warnings: List[str] = []
    projection_exit = 0
    prediction_exit = 0
    weekly_exit = 0
    live_exit = 0

    # --- Projection checks ---
    if run_projections:
        projection_exit = run_sanity_check(args.scoring, args.season)

    # --- Weekly projection checks (the partition the website serves) ---
    if run_weekly:
        weekly_criticals, weekly_warnings = run_weekly_projection_check(
            args.season, weekly_week, args.scoring
        )
        all_criticals.extend(weekly_criticals)
        all_warnings.extend(weekly_warnings)
        if weekly_criticals:
            weekly_exit = 1

    # --- Prediction checks ---
    if run_predictions:
        pred_criticals, pred_warnings = run_prediction_check(args.season, args.week)
        all_criticals.extend(pred_criticals)
        all_warnings.extend(pred_warnings)
        if pred_criticals:
            prediction_exit = 1

    # --- Live site checks (deploy verification) ---
    if args.check_live:
        live_criticals, live_warnings = run_live_site_check(
            backend_url=args.live_backend_url,
            frontend_url=args.live_frontend_url,
            season=args.season,
        )
        all_criticals.extend(live_criticals)
        all_warnings.extend(live_warnings)
        if live_criticals:
            live_exit = 1

    # --- Combined PASS/FAIL summary ---
    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)

    sections_run = []
    if run_projections:
        status = "FAIL" if projection_exit != 0 else "PASS"
        sections_run.append(("Projections", status))
    if run_predictions:
        status = "FAIL" if prediction_exit != 0 else "PASS"
        sections_run.append(("Predictions", status))
    if run_weekly:
        status = "FAIL" if weekly_exit != 0 else "PASS"
        sections_run.append(("Weekly Projections", status))
    if args.check_live:
        status = "FAIL" if live_exit != 0 else "PASS"
        sections_run.append(("Live Site", status))

    overall_pass = all(s == "PASS" for _, s in sections_run)

    for section, status in sections_run:
        icon = "PASS" if status == "PASS" else "FAIL"
        print(f"  [{icon}] {section}")

    if overall_pass:
        print(f"\n  OVERALL RESULT: PASS")
    else:
        print(f"\n  OVERALL RESULT: FAIL")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
