#!/usr/bin/env python3
"""
Generate NFL Fantasy Football Projections

Pulls Silver-layer player data from S3, runs the projection engine,
and writes results to the Gold layer.

Usage:
    python scripts/generate_projections.py --week 1 --season 2026 --scoring ppr
    python scripts/generate_projections.py --week 10 --season 2025 --scoring half_ppr
    python scripts/generate_projections.py --preseason --season 2026 --scoring standard
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from typing import Dict, Optional

import boto3
import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import glob as globmod  # noqa: E402

from nfl_data_integration import NFLDataFetcher  # noqa: E402
from projection_engine import (  # noqa: E402
    generate_weekly_projections,
    generate_preseason_projections,
    apply_injury_adjustments,
    apply_sentiment_adjustments,
    apply_event_adjustments,
    load_latest_sentiment,
    add_floor_ceiling,
)
from kicker_analytics import (  # noqa: E402
    compute_kicker_stats,
    compute_team_kicker_features,
    compute_opponent_kicker_features,
)
from kicker_projection import generate_kicker_projections  # noqa: E402
from scoring_calculator import list_scoring_formats  # noqa: E402
from utils import download_latest_parquet  # noqa: E402
import config  # noqa: E402


PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
GOLD_DIR = os.path.join(PROJECT_ROOT, "data", "gold")


def _load_implied_totals(
    schedules_df: pd.DataFrame, week: int
) -> Optional[Dict[str, float]]:
    """Compute per-team implied scoring totals from schedule lines.

    Uses the standard Vegas convention:
        home_implied = (total_line - spread_line) / 2
        away_implied = (total_line + spread_line) / 2

    where ``spread_line`` is from the home team's perspective (negative
    means home is favoured).

    Args:
        schedules_df: Game schedule DataFrame with ``week``,
            ``home_team``, ``away_team``, ``total_line``, and
            ``spread_line`` columns.
        week: NFL week number.

    Returns:
        Dict mapping team abbreviation to implied points, or None if
        required columns are missing or no games match.
    """
    required = {"week", "home_team", "away_team", "total_line", "spread_line"}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        return None

    games = schedules_df[schedules_df["week"] == week].dropna(
        subset=["total_line", "spread_line"]
    )
    if games.empty:
        return None

    implied: Dict[str, float] = {}
    for _, row in games.iterrows():
        total = float(row["total_line"])
        spread = float(row["spread_line"])
        implied[row["home_team"]] = round((total - spread) / 2, 2)
        implied[row["away_team"]] = round((total + spread) / 2, 2)

    return implied


def _read_local_parquet(base_dir: str, key_pattern: str) -> pd.DataFrame:
    """Read latest parquet from a local directory matching a glob pattern."""
    pattern = os.path.join(base_dir, key_pattern)
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------


def _s3_client(creds):
    return boto3.client(
        "s3",
        aws_access_key_id=creds["access_key"],
        aws_secret_access_key=creds["secret_key"],
        region_name=creds["region"],
    )


def upload_df(df, bucket, key, creds) -> str:
    tmp = f"/tmp/{key.replace('/', '_')}.parquet"
    df.to_parquet(tmp, index=False)
    _s3_client(creds).upload_file(tmp, bucket, key)
    os.remove(tmp)
    uri = f"s3://{bucket}/{key}"
    print(f"  Uploaded -> {uri}")
    return uri


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    load_dotenv()

    formats = list_scoring_formats()
    parser = argparse.ArgumentParser(
        description="NFL Fantasy Football Projection Generator"
    )
    parser.add_argument("--season", type=int, default=2026, help="Target season")
    parser.add_argument("--week", type=int, help="Target week (weekly projection mode)")
    parser.add_argument(
        "--preseason", action="store_true", help="Run pre-season projection mode"
    )
    parser.add_argument(
        "--scoring", choices=formats, default="half_ppr", help="Scoring format"
    )
    parser.add_argument(
        "--output",
        choices=["s3", "csv", "both"],
        default="both",
        help="Output destination",
    )
    parser.add_argument(
        "--output-dir",
        default="output/projections",
        help="Local CSV output directory (default: output/projections)",
    )
    parser.add_argument(
        "--ml",
        action="store_true",
        help="Use ML router: QB/RB via XGB, WR/TE via hybrid residual correction",
    )
    parser.add_argument(
        "--constrain",
        action="store_true",
        help="Apply team-level constraints so player totals align with implied team totals",
    )
    parser.add_argument(
        "--include-kickers",
        action="store_true",
        help="Include kicker (K) projections from PBP data",
    )
    parser.add_argument(
        "--use-sentiment",
        action="store_true",
        default=False,
        help=(
            "Apply Gold-layer sentiment multipliers after injury adjustments. "
            "Requires data/gold/sentiment/ output from the sentiment pipeline. "
            "Default: False (opt-in to preserve backward compatibility)."
        ),
    )
    parser.add_argument(
        "--use-events",
        action="store_true",
        default=False,
        help=(
            "Apply structured event adjustments (questionable/returning/"
            "traded/usage_boost/weather_risk/etc.) after injury adjustments. "
            "Per Phase 61 D-03: each flag maps to a deterministic bounded "
            "multiplier (NOT a continuous sentiment_multiplier). Requires "
            "data/gold/sentiment/ output. Default: False — opt-in behind the "
            "Phase 61-03 backtest SHIP gate."
        ),
    )
    args = parser.parse_args()

    if not args.preseason and not args.week:
        parser.error(
            "Specify --week N for weekly projections or --preseason for draft projections"
        )

    creds = {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region": os.getenv("AWS_REGION", "us-east-2"),
    }
    silver_bucket = os.getenv("S3_BUCKET_SILVER", config.S3_BUCKET_SILVER)
    gold_bucket = os.getenv("S3_BUCKET_GOLD", config.S3_BUCKET_GOLD)
    has_aws = all(creds.values())

    fetcher = NFLDataFetcher()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"\nNFL Fantasy Football Projection Generator")
    print(f"Season: {args.season} | Scoring: {args.scoring.upper()}")
    if args.preseason:
        print("Mode: Pre-Season Draft Projections")
        if args.ml:
            print(
                "Note: --ml is a no-op in preseason mode (all positions use heuristic)"
            )
    else:
        print(f"Mode: Weekly Projections (Week {args.week})")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # Pre-season mode: use seasonal aggregates
    # -----------------------------------------------------------------------
    if args.preseason:
        print("\nFetching historical seasonal data...")
        # Use the two most-recent completed seasons as training data.
        # season-1 (e.g. 2025 when targeting 2026) is REQUIRED: it is the
        # only source of truth for players who debuted last year (2025
        # rookies are 2026 sophomores). A missing season-1 means every
        # first-year player silently falls through to the crude unknown-role
        # fallback, which is worse than a loud failure.
        # season-2 (e.g. 2024) is a soft supplement — warn but continue if
        # it cannot be loaded.
        #
        # NFLDataAdapter.fetch_seasonal_data() is used instead of the legacy
        # NFLDataFetcher.fetch_player_seasonal() because the latter calls
        # nfl.import_seasonal_data() which returns HTTP 404 for seasons >=
        # STATS_PLAYER_MIN_SEASON (2025). The adapter routes those seasons
        # through the nflverse stats_player release tag which does have 2025.
        # It also returns position/player_name/recent_team directly, so the
        # roster-enrichment step below is skipped for adapter-sourced rows.
        from nfl_data_adapter import NFLDataAdapter  # noqa: E402

        adapter = NFLDataAdapter()

        most_recent_season = args.season - 1   # e.g. 2025 — REQUIRED
        prior_season = args.season - 2         # e.g. 2024 — best-effort

        # Hoisted out of the conditional below: line 273 references this in a
        # list comprehension unconditionally, so a 2026 run (where the if-block
        # is skipped because 2025 IS in available_seasons) would NameError on
        # any caller that hasn't already loaded `config` transitively.
        from config import STATS_PLAYER_MIN_SEASON

        # Validate season-1 before attempting the fetch.
        if most_recent_season not in fetcher.available_seasons:
            # fetcher.available_seasons uses the legacy nfl-data-py range; the
            # adapter extends coverage via stats_player. Allow it if the adapter
            # can handle it (season >= STATS_PLAYER_MIN_SEASON).
            if most_recent_season < STATS_PLAYER_MIN_SEASON:
                print(
                    f"ERROR: required season {most_recent_season} is not in "
                    f"available_seasons and predates stats_player coverage "
                    f"({STATS_PLAYER_MIN_SEASON}+). Cannot build projections."
                )
                return 1

        past_seasons = [s for s in [prior_season, most_recent_season]
                        if s in fetcher.available_seasons
                        or s >= STATS_PLAYER_MIN_SEASON]

        seasonal_df = adapter.fetch_seasonal_data(past_seasons)

        if seasonal_df.empty:
            print("ERROR: no seasonal data could be fetched")
            return 1

        # Hard failure if season-1 produced no rows — silently continuing on
        # stale data (season-2 only) would degrade all 2025 rookies to the
        # crude unknown-role fallback without any visible warning.
        # Also guard against an upstream schema change that drops the `season`
        # column entirely, which would otherwise raise KeyError instead of
        # producing a clean diagnostic.
        if "season" not in seasonal_df.columns:
            print(
                "ERROR: NFLDataAdapter output is missing the 'season' column. "
                "Cannot identify season-1 rows — aborting. Likely an upstream "
                "schema change in the nflverse stats_player release."
            )
            return 1
        season1_rows = seasonal_df[seasonal_df["season"] == most_recent_season]
        if season1_rows.empty:
            print(
                f"ERROR: NFLDataAdapter returned 0 rows for required season "
                f"{most_recent_season}. Cannot build reliable projections on "
                f"season-2 data alone — aborting. Check network access or "
                f"nflverse stats_player release availability."
            )
            return 1

        seasons_loaded = sorted(seasonal_df["season"].unique().tolist())
        if prior_season not in seasons_loaded:
            print(
                f"  WARNING: optional season {prior_season} could not be loaded "
                f"— projections will use {most_recent_season} data only."
            )

        print(
            f"  Loaded {len(seasonal_df):,} rows via NFLDataAdapter "
            f"(seasons: {seasons_loaded})"
        )

        # The adapter's `player_name` is the abbreviated nflverse form
        # ("C.Ward"); production output and the web UI expect full names
        # ("Cam Ward"). Prefer `player_display_name` wherever it is present,
        # falling back to the abbreviated name only when display is missing.
        if "player_display_name" in seasonal_df.columns:
            seasonal_df["player_name"] = seasonal_df["player_display_name"].where(
                seasonal_df["player_display_name"].notna(),
                seasonal_df.get("player_name"),
            )

        # NFLDataAdapter.fetch_seasonal_data() already includes position,
        # player_name, recent_team, and season — no roster-join enrichment
        # needed. The needs_enrich guard below is retained as a safety net for
        # any edge case where those columns are somehow absent.
        needs_enrich = (
            "position" not in seasonal_df.columns
            or "player_name" not in seasonal_df.columns
            or "recent_team" not in seasonal_df.columns
        )
        if needs_enrich:
            import nfl_data_py as nfl

            roster_seasons = past_seasons
            try:
                rosters = nfl.import_seasonal_rosters(roster_seasons)
                # Take the most-recent roster entry per player_id for stable values
                roster_latest = (
                    rosters.sort_values("season")
                    .drop_duplicates(subset=["player_id"], keep="last")
                )
                roster_lookup = roster_latest.set_index("player_id")[
                    ["position", "player_name", "team"]
                ]
                if "position" not in seasonal_df.columns:
                    seasonal_df["position"] = seasonal_df["player_id"].map(
                        roster_lookup["position"]
                    )
                if "player_name" not in seasonal_df.columns:
                    seasonal_df["player_name"] = seasonal_df["player_id"].map(
                        roster_lookup["player_name"]
                    )
                if "recent_team" not in seasonal_df.columns:
                    seasonal_df["recent_team"] = seasonal_df["player_id"].map(
                        roster_lookup["team"]
                    )
                matched = seasonal_df["position"].notna().sum()
                print(
                    f"  Joined position/name/team from rosters — "
                    f"{matched} of {len(seasonal_df)} rows matched"
                )
            except Exception as e:
                print(f"  WARNING: could not fetch roster data: {e}")

        # Override stale `recent_team` from nflverse seasonal rosters with the
        # latest Sleeper rosters_live snapshot. nflverse's seasonal data lags
        # real-world roster updates by weeks during the offseason — Malik
        # Willis's GB→MIA move is a recent example where seasonal still says
        # GB but Sleeper has him on MIA. Without this override the lineup
        # page either shows "--" (depth-chart mismatch guard) or carries his
        # GB-backup point total under his MIA-starter slot.
        try:
            live_roster = _read_local_parquet(
                BRONZE_DIR, "players/rosters_live/season=*/*.parquet"
            )
        except Exception as e:  # pragma: no cover — defensive
            live_roster = pd.DataFrame()
            print(f"  WARNING: could not read rosters_live: {e}")

        from utils import apply_sleeper_team_overrides

        seasonal_df = apply_sleeper_team_overrides(
            seasonal_df,
            live_roster,
            team_col="recent_team",
            name_col="player_name",
            logger=logging.getLogger(__name__),
        )

        print(f"Loaded {len(seasonal_df):,} seasonal player rows")

        # Load historical dimension table for draft capital boost
        historical_df = _read_local_parquet(SILVER_DIR, "players/historical/*.parquet")
        if not historical_df.empty:
            print(
                f"Loaded {len(historical_df):,} historical player profiles for draft capital boost"
            )

        # Load latest roster bronze + recent weekly bronze to drive the
        # low-sample / silent-drop fix (rookies and journeymen with thin NFL
        # samples that the seasonal aggregation drops).
        roster_df = _read_local_parquet(BRONZE_DIR, "players/rosters/season=*/*.parquet")
        if not roster_df.empty:
            # Keep only the latest snapshot (latest season).
            latest_season = roster_df["season"].max()
            roster_df = roster_df[roster_df["season"] == latest_season].copy()
            print(
                f"Loaded {len(roster_df):,} roster rows (season={latest_season}) for low-sample fix"
            )

        weekly_df = _read_local_parquet(
            BRONZE_DIR, "player_weekly/season=*/week=*/*.parquet"
        )
        if weekly_df.empty:
            # v1.x → v2.x bronze path move
            weekly_df = _read_local_parquet(
                BRONZE_DIR, "players/weekly/season=*/*.parquet"
            )
        if not weekly_df.empty:
            print(
                f"Loaded {len(weekly_df):,} weekly stat rows for rookie per-game rates"
            )

        depth_charts_df = _read_local_parquet(
            BRONZE_DIR, "depth_charts/season=*/*.parquet"
        )
        if not depth_charts_df.empty:
            print(
                f"Loaded {len(depth_charts_df):,} depth chart rows "
                f"(latest dt: {depth_charts_df['dt'].max()}) for canonical role assignment"
            )

        print("Running pre-season projection model...")
        projections = generate_preseason_projections(
            seasonal_df,
            scoring_format=args.scoring,
            target_season=args.season,
            historical_df=historical_df if not historical_df.empty else None,
            roster_df=roster_df if not roster_df.empty else None,
            weekly_df=weekly_df if not weekly_df.empty else None,
            depth_charts_df=depth_charts_df if not depth_charts_df.empty else None,
        )
        s3_key = f"projections/preseason/season={args.season}/season_proj_{ts}.parquet"
        local_name = f"preseason_{args.season}_{args.scoring}_{ts}.csv"

    # -----------------------------------------------------------------------
    # Weekly mode: use Silver-layer rolling stats
    # -----------------------------------------------------------------------
    else:
        print(f"\nFetching Silver-layer data for season {args.season}...")
        silver_df = pd.DataFrame()

        # Try local Silver first
        silver_df = _read_local_parquet(
            SILVER_DIR, f"players/usage/season={args.season}/*.parquet"
        )
        if not silver_df.empty:
            print(f"Loaded {len(silver_df):,} rows from local Silver layer")

        # Try S3 if local is empty
        if silver_df.empty and has_aws:
            try:
                s3 = _s3_client(creds)
                prefix = f"players/usage/season={args.season}/week={args.week}/"
                silver_df = download_latest_parquet(s3, silver_bucket, prefix)
                print(f"Loaded {len(silver_df):,} rows from Silver S3 layer")
            except Exception as e:
                print(f"WARN: Could not load from Silver S3: {e}")

        if silver_df.empty:
            print("Falling back to fetching weekly data directly from nfl-data-py...")
            try:
                silver_df = fetcher.fetch_player_weekly([args.season])
            except Exception as e:
                print(f"ERROR: {e}")
                return 1

        # Load schedules unconditionally — needed for the matchup factor's
        # upcoming-opponent derivation and bye detection (prior season
        # included so the trailing defensive window spans the boundary).
        sched_parts = []
        for s in (args.season - 1, args.season):
            part = _read_local_parquet(BRONZE_DIR, f"schedules/season={s}/*.parquet")
            if part.empty:
                try:
                    part = fetcher.fetch_schedules([s])
                except Exception as e:
                    print(f"WARN: Could not load schedules for {s}: {e}")
                    part = pd.DataFrame()
            if not part.empty:
                if "season" not in part.columns:
                    part["season"] = s
                sched_parts.append(part)
        schedules_df = (
            pd.concat(sched_parts, ignore_index=True)
            if sched_parts
            else pd.DataFrame()
        )

        # Build the defensive strength table for the matchup factor
        # (trailing fantasy points allowed vs position, properly lagged).
        from player_analytics import compute_defensive_strength

        weekly_parts = []
        for s in (args.season - 1, args.season):
            part = _read_local_parquet(
                BRONZE_DIR, f"players/weekly/season={s}/*.parquet"
            )
            if not part.empty:
                weekly_parts.append(part)
        strength_weekly = (
            pd.concat(weekly_parts, ignore_index=True)
            if weekly_parts
            else silver_df
        )
        opp_rankings = pd.DataFrame()
        try:
            opp_rankings = compute_defensive_strength(
                strength_weekly, schedules_df, scoring_format=args.scoring
            )
        except Exception as e:
            print(f"WARN: Could not compute defensive strength: {e}")
        if not opp_rankings.empty:
            print(
                f"Computed defensive strength table: {len(opp_rankings):,} rows"
            )
        else:
            print("WARN: No defensive strength table; matchup factor neutral")

        # Current-season slice for bye detection / implied totals — the
        # two-season frame above is only for the trailing strength window.
        season_sched = (
            schedules_df[schedules_df["season"] == args.season]
            if "season" in schedules_df.columns
            else schedules_df
        )

        # Implied totals (needed for --constrain)
        implied_totals = None
        if args.constrain:
            if not season_sched.empty:
                implied_totals = _load_implied_totals(season_sched, args.week)
                if implied_totals:
                    print(
                        f"Loaded implied totals for {len(implied_totals)} teams (Week {args.week})"
                    )
                else:
                    print(
                        "WARN: No implied totals available; constraints will be skipped"
                    )

        print(f"Running weekly projection model (Week {args.week})...")
        if args.ml:
            from ml_projection_router import generate_ml_projections

            # Build full assembled feature vector for SHIP positions (QB/RB).
            # SHIP models expect 80+ columns including QBR features that are
            # absent from silver_df but present in the assembled feature vector.
            # assemble_player_features() joins Silver advanced data (which
            # contains qbr_* columns from Bronze QBR) on player_id/season/week.
            feature_df = None
            try:
                import sys
                import os as _os
                _src = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "src")
                if _src not in sys.path:
                    sys.path.insert(0, _src)
                from player_feature_engineering import assemble_player_features
                feature_df = assemble_player_features(season=args.season)
                if feature_df.empty:
                    print("WARN: assemble_player_features returned empty; SHIP path will use silver_df")
                else:
                    qbr_cols = [c for c in feature_df.columns if c.startswith("qbr_")]
                    print(
                        f"Assembled feature vector: {len(feature_df):,} rows, "
                        f"{len(feature_df.columns)} cols ({len(qbr_cols)} qbr_* cols)"
                    )
            except Exception as e:
                print(f"WARN: Could not assemble feature vector: {e}; SHIP path will use silver_df")

            projections = generate_ml_projections(
                silver_df,
                opp_rankings,
                season=args.season,
                week=args.week,
                scoring_format=args.scoring,
                schedules_df=season_sched if not season_sched.empty else None,
                implied_totals=implied_totals,
                apply_constraints=args.constrain,
                feature_df=feature_df,
            )
        else:
            projections = generate_weekly_projections(
                silver_df,
                opp_rankings,
                season=args.season,
                week=args.week,
                scoring_format=args.scoring,
                schedules_df=season_sched if not season_sched.empty else None,
                implied_totals=implied_totals,
                apply_constraints=args.constrain,
            )

        # Load injury data and apply adjustments
        injuries_df = _read_local_parquet(
            BRONZE_DIR, f"players/injuries/season={args.season}/*.parquet"
        )
        if not injuries_df.empty:
            print(f"Loaded {len(injuries_df):,} injury rows from local Bronze")
        if injuries_df.empty and has_aws:
            try:
                inj_prefix = f"players/injuries/season={args.season}/week={args.week}/"
                injuries_df = download_latest_parquet(
                    s3, config.S3_BUCKET_BRONZE, inj_prefix
                )
                print(f"Loaded {len(injuries_df):,} injury report rows from S3")
            except Exception as e:
                print(f"WARN: Could not load injury data: {e}")
        if injuries_df.empty:
            try:
                injuries_df = fetcher.fetch_injuries([args.season], week=args.week)
                print(f"Fetched {len(injuries_df):,} injury rows from nfl-data-py")
            except Exception as e:
                print(f"WARN: Could not fetch injuries: {e}")
        if not injuries_df.empty and not projections.empty:
            projections = apply_injury_adjustments(projections, injuries_df)
            injured = (projections["injury_multiplier"] < 1.0).sum()
            print(f"Injury adjustments applied: {injured} players affected")

        # --- Structured event adjustments (opt-in via --use-events) ---
        # Per Phase 61 D-03: deterministic, tightly-bounded multipliers keyed
        # on boolean flags from the rule extractor. Separate from the legacy
        # continuous --use-sentiment path.
        if args.use_events and not projections.empty:
            print(
                f"\nLoading event data for Season {args.season} "
                f"Week {args.week}..."
            )
            events_df = load_latest_sentiment(args.season, args.week)
            if events_df.empty:
                print(
                    "WARN: No event data available; skipping event adjustments"
                )
            else:
                before_total = float(projections["projected_points"].sum())
                projections = apply_event_adjustments(projections, events_df)
                after_total = float(projections["projected_points"].sum())
                affected = int(
                    (projections["event_multiplier"] != 1.0).sum()
                )
                delta = after_total - before_total
                print(
                    f"Event adjustments applied: {affected} players affected; "
                    f"total projected points {before_total:.1f} → "
                    f"{after_total:.1f} ({delta:+.1f})"
                )

        # --- Sentiment adjustments (opt-in via --use-sentiment) ---
        if args.use_sentiment and not projections.empty:
            print(f"\nLoading sentiment data for Season {args.season} Week {args.week}...")
            sentiment_df = load_latest_sentiment(args.season, args.week)
            if sentiment_df.empty:
                print("WARN: No sentiment data available; skipping sentiment adjustments")
            else:
                print(
                    f"Loaded sentiment data: {len(sentiment_df)} players"
                    + (
                        f", computed at {sentiment_df['computed_at'].iloc[0]}"
                        if "computed_at" in sentiment_df.columns
                        else ""
                    )
                )
                projections = apply_sentiment_adjustments(projections, sentiment_df)
                sent_applied = (projections["sentiment_multiplier"] != 1.0).sum()
                print(f"Sentiment adjustments applied: {sent_applied} players affected")

        # --- Kicker projections (opt-in) ---
        if args.include_kickers and not projections.empty:
            print("\nGenerating kicker projections from PBP data...")
            pbp_df = _read_local_parquet(
                BRONZE_DIR, f"pbp/season={args.season}/*.parquet"
            )
            if pbp_df.empty:
                try:
                    pbp_df = fetcher.fetch_pbp([args.season])
                except Exception as e:
                    print(f"WARN: Could not load PBP for kicker projections: {e}")

            if not pbp_df.empty:
                try:
                    k_stats = compute_kicker_stats(pbp_df, args.season)
                    k_team_feats = compute_team_kicker_features(
                        pbp_df, schedules_df, args.season
                    )
                    k_opp_feats = compute_opponent_kicker_features(
                        pbp_df, schedules_df, args.season
                    )
                    sched_for_k = (
                        schedules_df if not schedules_df.empty else pd.DataFrame()
                    )
                    if sched_for_k.empty:
                        sched_for_k = _read_local_parquet(
                            BRONZE_DIR, f"schedules/season={args.season}/*.parquet"
                        )
                    kicker_proj = generate_kicker_projections(
                        k_stats,
                        k_team_feats,
                        k_opp_feats,
                        sched_for_k,
                        args.season,
                        args.week,
                    )
                    if not kicker_proj.empty:
                        print(f"Kicker projections: {len(kicker_proj)} kickers")
                        projections = pd.concat(
                            [projections, kicker_proj], ignore_index=True
                        )
                    else:
                        print("WARN: No kicker projections generated")
                except Exception as e:
                    print(f"WARN: Kicker projection failed: {e}")
            else:
                print("WARN: No PBP data available for kicker projections")

        s3_key = (
            f"projections/season={args.season}/week={args.week}/"
            f"projections_{args.scoring}_{ts}.parquet"
        )
        local_name = f"week{args.week}_{args.season}_{args.scoring}_{ts}.csv"

    if projections.empty:
        print("ERROR: No projections generated. Check that data is available.")
        return 1

    # Add floor/ceiling after all adjustments (ML router handles this internally).
    # Preseason mode uses projected_season_points (full-season totals), not
    # projected_points (weekly), so floor/ceiling is not applicable there.
    if not args.ml and not args.preseason:
        projections = add_floor_ceiling(projections)

    print(f"\nProjections generated: {len(projections):,} players")

    # -----------------------------------------------------------------------
    # Display top 20
    # -----------------------------------------------------------------------
    display_cols = (
        [
            "player_name",
            "position",
            "recent_team",
            "projected_points",
            "position_rank",
            "overall_rank",
        ]
        if "overall_rank" in projections.columns
        else [
            "player_name",
            "position",
            "recent_team",
            "projected_points",
            "position_rank",
        ]
    )
    display_cols = [c for c in display_cols if c in projections.columns]

    print(f"\nTop 20 Players ({args.scoring.upper()}):")
    print(projections[display_cols].head(20).to_string(index=False))

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    if args.output in ("csv", "both"):
        os.makedirs(args.output_dir, exist_ok=True)
        csv_path = os.path.join(args.output_dir, local_name)
        projections.to_csv(csv_path, index=False)
        print(f"\nSaved CSV -> {csv_path}")

    # Always save to local Gold layer
    gold_path = os.path.join(GOLD_DIR, s3_key)
    os.makedirs(os.path.dirname(gold_path), exist_ok=True)
    projections.to_parquet(gold_path, index=False)
    print(f"Saved Gold -> data/gold/{s3_key}")

    if args.output in ("s3", "both") and has_aws:
        try:
            upload_df(projections, gold_bucket, s3_key, creds)
        except Exception as e:
            print(f"WARN: S3 upload failed: {e}")

    print("\nProjection run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
