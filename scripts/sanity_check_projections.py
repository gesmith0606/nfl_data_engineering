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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import requests
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")

# Freshness thresholds (D-08). Gold projections should refresh weekly; Silver
# aggregates can go longer between pipeline runs.
GOLD_MAX_AGE_DAYS = 7
SILVER_MAX_AGE_DAYS = 14

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
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LA", "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO",
    "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

# Spread and total reasonableness bounds
SPREAD_MIN, SPREAD_MAX = -20.0, 20.0
TOTAL_MIN, TOTAL_MAX = 30.0, 65.0
VEGAS_SPREAD_DIVERGENCE_THRESHOLD = 7.0


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
def check_local_freshness(path: str, max_age_days: int = GOLD_MAX_AGE_DAYS) -> Tuple[str, str]:
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
    age_days = (
        datetime.now() - datetime.fromtimestamp(latest.stat().st_mtime)
    ).days
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
            logger.info("Live Sleeper consensus: %d players", len(df))
            return df
    except Exception as exc:  # noqa: BLE001 -- defensive; we always want a fallback
        logger.warning("Sleeper live consensus failed: %s", exc)

    logger.warning(
        "Using hardcoded CONSENSUS_TOP_50 fallback (live sources unavailable)"
    )
    return _build_consensus_df()


def _match_players(
    our_df: pd.DataFrame, consensus_df: pd.DataFrame
) -> pd.DataFrame:
    """Match consensus players to our projections using fuzzy name matching."""
    our = our_df.copy()
    our["norm_name"] = our["player_name"].apply(_normalize_name)

    matched = consensus_df.merge(
        our[["norm_name", "player_name", "position", "recent_team",
             "projected_season_points", "overall_rank", "position_rank"]],
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
            (df["predicted_total"] < TOTAL_MIN)
            | (df["predicted_total"] > TOTAL_MAX)
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
        matchup_dupes = df[
            df.duplicated(subset=["home_team", "away_team"], keep=False)
        ]
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
        print(f"\n  Spread range: [{df['predicted_spread'].min():.1f}, "
              f"{df['predicted_spread'].max():.1f}]  "
              f"mean={df['predicted_spread'].mean():.1f}")
        print(f"  Total range:  [{df['predicted_total'].min():.1f}, "
              f"{df['predicted_total'].max():.1f}]  "
              f"mean={df['predicted_total'].mean():.1f}")

    if "confidence_tier" in df.columns:
        tier_counts = df["confidence_tier"].value_counts().to_dict()
        print(f"  Confidence tiers: {tier_counts}")

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
    gold_dir = os.path.join(
        GOLD_DIR, f"projections/preseason/season={season}"
    )
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
        ("player_usage", os.path.join(PROJECT_ROOT, "data", "silver", "players", "usage")),
        ("team_pbp_metrics", os.path.join(PROJECT_ROOT, "data", "silver", "teams", "pbp_metrics")),
    ]
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
        s_level, s_msg = check_local_freshness(
            probe_dir, max_age_days=SILVER_MAX_AGE_DAYS
        )
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
        consensus_df["norm_name"] = consensus_df["player_name"].apply(
            _normalize_name
        )
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
    # 3. WARNING: Large rank discrepancies (>20 spots)
    # ------------------------------------------------------------------
    # NOTE: warnings list was initialized at the top of run_sanity_check()
    # so freshness checks could append; do NOT re-init here or we lose them.
    matched_found = matched[matched["overall_rank"].notna()].copy()
    matched_found["rank_diff"] = (
        matched_found["overall_rank"] - matched_found["consensus_rank"]
    )
    matched_found["abs_rank_diff"] = matched_found["rank_diff"].abs()

    big_diff = matched_found[matched_found["abs_rank_diff"] > 20].sort_values(
        "abs_rank_diff", ascending=False
    )
    for _, row in big_diff.iterrows():
        direction = "LOWER" if row["rank_diff"] > 0 else "HIGHER"
        warnings.append(
            f"RANK GAP: {row['player_name_consensus']} ({row['position_consensus']}) — "
            f"consensus #{int(row['consensus_rank'])}, ours #{int(row['overall_rank'])} "
            f"(diff: {int(row['rank_diff']):+d}, we rank {direction})"
        )

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
        criticals.append(
            f"NULL POSITION: {row['player_name']} — position is null/NaN"
        )

    # Known star players with expected positions — catches data pipeline bugs
    # like Saquon Barkley showing up as QB
    KNOWN_STAR_POSITIONS = {
        "Patrick Mahomes": "QB", "Josh Allen": "QB", "Lamar Jackson": "QB",
        "Joe Burrow": "QB", "Jalen Hurts": "QB", "C.J. Stroud": "QB",
        "Saquon Barkley": "RB", "Derrick Henry": "RB", "Jahmyr Gibbs": "RB",
        "Bijan Robinson": "RB", "Christian McCaffrey": "RB", "Breece Hall": "RB",
        "Jonathan Taylor": "RB", "Josh Jacobs": "RB", "De'Von Achane": "RB",
        "Ja'Marr Chase": "WR", "Justin Jefferson": "WR", "Tyreek Hill": "WR",
        "CeeDee Lamb": "WR", "Amon-Ra St. Brown": "WR", "Puka Nacua": "WR",
        "A.J. Brown": "WR", "Davante Adams": "WR", "Malik Nabers": "WR",
        "Travis Kelce": "TE", "Brock Bowers": "TE", "Sam LaPorta": "TE",
        "Mark Andrews": "TE", "George Kittle": "TE", "Trey McBride": "TE",
    }
    for star_name, expected_pos in KNOWN_STAR_POSITIONS.items():
        # Use normalized full-name matching to avoid false positives
        # (e.g., "Jermar Jefferson" matching "Justin Jefferson")
        norm_star = _normalize_name(star_name)
        star_rows = our_df[
            our_df["player_name"].apply(_normalize_name) == norm_star
        ]
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
    # Top-20 comparison table
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  TOP-20 COMPARISON TABLE")
    print("=" * 70)
    top20 = (
        matched_found.sort_values("consensus_rank")
        .head(20)
    )
    header = f"{'Player':<25} {'Pos':<4} {'Cons#':>6} {'Ours#':>6} {'Diff':>6} {'Our Pts':>8}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for _, row in top20.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_rank = int(row["consensus_rank"])
        our_rank = int(row["overall_rank"])
        diff = int(row["rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_rank:>6} {our_rank:>6} {diff_str:>6} {pts:>8.1f}"
        )

    # ------------------------------------------------------------------
    # Biggest rank discrepancies
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  BIGGEST RANK DISCREPANCIES (top 10)")
    print("=" * 70)
    worst = matched_found.sort_values("abs_rank_diff", ascending=False).head(10)
    header2 = f"{'Player':<25} {'Pos':<4} {'Cons#':>6} {'Ours#':>6} {'Diff':>6} {'Our Pts':>8}"
    print(f"  {header2}")
    print(f"  {'-' * len(header2)}")
    for _, row in worst.iterrows():
        name = row["player_name_consensus"][:24]
        pos = row["position_consensus"]
        cons_rank = int(row["consensus_rank"])
        our_rank = int(row["overall_rank"])
        diff = int(row["rank_diff"])
        pts = row["projected_season_points"]
        diff_str = f"{diff:+d}"
        print(
            f"  {name:<25} {pos:<4} {cons_rank:>6} {our_rank:>6} {diff_str:>6} {pts:>8.1f}"
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
        # Rank correlation (Spearman)
        from scipy import stats as sp_stats

        corr, p_value = sp_stats.spearmanr(
            matched_found["consensus_rank"], matched_found["overall_rank"]
        )
        print(f"\n  Spearman rank correlation: {corr:.3f} (p={p_value:.4f})")
        if corr > 0.8:
            print("  Interpretation: STRONG agreement with consensus")
        elif corr > 0.6:
            print("  Interpretation: MODERATE agreement with consensus")
        elif corr > 0.4:
            print("  Interpretation: WEAK agreement with consensus")
        else:
            print("  Interpretation: POOR agreement — investigate model")

        # Mean absolute rank difference
        mean_diff = matched_found["abs_rank_diff"].mean()
        median_diff = matched_found["abs_rank_diff"].median()
        print(f"  Mean absolute rank difference: {mean_diff:.1f}")
        print(f"  Median absolute rank difference: {median_diff:.1f}")

        # Per-position breakdown
        print(f"\n  Per-position rank correlation:")
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_data = matched_found[matched_found["position_consensus"] == pos]
            if len(pos_data) > 2:
                pos_corr, _ = sp_stats.spearmanr(
                    pos_data["consensus_rank"], pos_data["overall_rank"]
                )
                pos_mean = pos_data["abs_rank_diff"].mean()
                print(
                    f"    {pos}: r={pos_corr:.3f}, mean rank diff={pos_mean:.1f} "
                    f"({len(pos_data)} players)"
                )

    # ------------------------------------------------------------------
    # Our top-10 players (what we think are the best)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  OUR TOP-10 OVERALL")
    print("=" * 70)
    our_top10 = our_df.sort_values("overall_rank").head(10)
    for _, row in our_top10.iterrows():
        print(
            f"  #{int(row['overall_rank']):>3}  {row['player_name']:<25} "
            f"{row['position']:<3}  {row['recent_team']:<4}  "
            f"{row['projected_season_points']:.1f} pts"
        )

    # ------------------------------------------------------------------
    # Position distribution comparison
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  POSITION DISTRIBUTION IN TOP-50")
    print("=" * 70)
    our_top50 = our_df[our_df["overall_rank"] <= 50]
    our_pos_counts = our_top50["position"].value_counts().to_dict()
    cons_pos_counts = consensus_df["position"].value_counts().to_dict()

    header3 = f"{'Position':<10} {'Consensus':>10} {'Ours':>10} {'Diff':>10}"
    print(f"  {header3}")
    print(f"  {'-' * len(header3)}")
    for pos in ["QB", "RB", "WR", "TE"]:
        c = cons_pos_counts.get(pos, 0)
        o = our_pos_counts.get(pos, 0)
        d = o - c
        print(f"  {pos:<10} {c:>10} {o:>10} {d:>+10}")

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


DEFAULT_LIVE_BACKEND = "https://nfldataengineering-production.up.railway.app"
DEFAULT_LIVE_FRONTEND = "https://frontend-jet-seven-33.vercel.app"


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
        (
            "/api/news/team-events?season=2025&week=1",
            lambda d: isinstance(d, list) and len(d) == 32,
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
            criticals.append(
                f"LIVE API EMPTY/INVALID PAYLOAD: GET {path}"
            )
            print(f"  [FAIL] {path}  (payload failed contract)")
            continue
        print(f"  [PASS] {path}")

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
            warnings.append(
                f"LIVE FRONTEND MISSING MARKERS at {path}: {missing}"
            )
            print(f"  [WARN] {path}  (missing: {missing})")
            continue
        print(f"  [PASS] {path}  ({len(body)} bytes)")

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

    run_projections = not args.check_predictions or args.check_all
    run_predictions = args.check_predictions or args.check_all

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
    live_exit = 0

    # --- Projection checks ---
    if run_projections:
        projection_exit = run_sanity_check(args.scoring, args.season)

    # --- Prediction checks ---
    if run_predictions:
        pred_criticals, pred_warnings = run_prediction_check(
            args.season, args.week
        )
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
