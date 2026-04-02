"""
Load Gold Parquet data into PostgreSQL.

Reads projection and prediction Parquet files and upserts them into the
database tables defined in schema.sql.  Idempotent via INSERT ... ON CONFLICT.

Usage:
    python web/db/load_data.py --season 2024 --week 17
    python web/db/load_data.py --season 2024 --week 17 --type projections
    python web/db/load_data.py --season 2024 --week 17 --type predictions
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from web.api.config import GOLD_PREDICTIONS_DIR, GOLD_PROJECTIONS_DIR  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------


def _latest_parquet(directory: Path) -> Path:
    """Return the most-recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    if not parquets:
        raise FileNotFoundError(f"No parquet files in {directory}")
    return parquets[-1]


# ---------------------------------------------------------------------------
# Upsert logic
# ---------------------------------------------------------------------------

_PROJECTION_COLS = [
    "player_id",
    "player_name",
    "team",
    "position",
    "season",
    "week",
    "scoring_format",
    "projected_points",
    "projected_floor",
    "projected_ceiling",
    "proj_pass_yards",
    "proj_pass_tds",
    "proj_rush_yards",
    "proj_rush_tds",
    "proj_rec",
    "proj_rec_yards",
    "proj_rec_tds",
    "proj_fg_makes",
    "proj_xp_makes",
    "position_rank",
    "injury_status",
]

_PREDICTION_COLS = [
    "game_id",
    "season",
    "week",
    "home_team",
    "away_team",
    "predicted_spread",
    "predicted_total",
    "vegas_spread",
    "vegas_total",
    "spread_edge",
    "total_edge",
    "confidence_tier",
    "ats_pick",
    "ou_pick",
]


def _upsert_projections(conn, df: pd.DataFrame, scoring_format: str) -> int:
    """Upsert projection rows.  Returns number of rows written."""
    # Normalise column names (match service layer rename logic)
    rename_map = {
        "recent_team": "team",
        "proj_passing_yards": "proj_pass_yards",
        "proj_passing_tds": "proj_pass_tds",
        "proj_rushing_yards": "proj_rush_yards",
        "proj_rushing_tds": "proj_rush_tds",
        "proj_receptions": "proj_rec",
        "proj_receiving_yards": "proj_rec_yards",
        "proj_receiving_tds": "proj_rec_tds",
        "proj_season": "season",
        "proj_week": "week",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["scoring_format"] = scoring_format

    # Ensure required columns exist (fill missing with None)
    for col in _PROJECTION_COLS:
        if col not in df.columns:
            df[col] = None

    cols_str = ", ".join(_PROJECTION_COLS)
    placeholders = ", ".join(["%s"] * len(_PROJECTION_COLS))
    conflict_updates = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in _PROJECTION_COLS
        if c not in ("player_id", "season", "week", "scoring_format")
    )

    sql = (
        f"INSERT INTO projections ({cols_str}) VALUES ({placeholders}) "
        f"ON CONFLICT (player_id, season, week, scoring_format) "
        f"DO UPDATE SET {conflict_updates}"
    )

    count = 0
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            values = [_to_db_val(row.get(c)) for c in _PROJECTION_COLS]
            cur.execute(sql, values)
            count += 1
    conn.commit()
    return count


def _upsert_predictions(conn, df: pd.DataFrame) -> int:
    """Upsert prediction rows.  Returns number of rows written."""
    for col in _PREDICTION_COLS:
        if col not in df.columns:
            df[col] = None

    cols_str = ", ".join(_PREDICTION_COLS)
    placeholders = ", ".join(["%s"] * len(_PREDICTION_COLS))
    conflict_updates = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in _PREDICTION_COLS
        if c not in ("game_id", "season", "week")
    )

    sql = (
        f"INSERT INTO predictions ({cols_str}) VALUES ({placeholders}) "
        f"ON CONFLICT (game_id, season, week) "
        f"DO UPDATE SET {conflict_updates}"
    )

    count = 0
    with conn.cursor() as cur:
        for _, row in df.iterrows():
            values = [_to_db_val(row.get(c)) for c in _PREDICTION_COLS]
            cur.execute(sql, values)
            count += 1
    conn.commit()
    return count


def _to_db_val(val):
    """Convert pandas values to plain Python types suitable for psycopg2."""
    if val is None:
        return None
    if isinstance(val, float) and val != val:  # NaN
        return None
    try:
        # Convert numpy types to Python builtins
        return val.item()
    except (AttributeError, ValueError):
        return val


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Gold Parquet into PostgreSQL")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--type",
        choices=["projections", "predictions", "all"],
        default="all",
        help="Which data type to load (default: all)",
    )
    parser.add_argument(
        "--scoring",
        default="half_ppr",
        help="Scoring format for projections (default: half_ppr)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set")
        sys.exit(1)

    import psycopg2

    conn = psycopg2.connect(database_url)

    try:
        if args.type in ("projections", "all"):
            week_dir = (
                GOLD_PROJECTIONS_DIR / f"season={args.season}" / f"week={args.week}"
            )
            pq = _latest_parquet(week_dir)
            logger.info("Loading projections from %s", pq)
            df = pd.read_parquet(pq)
            n = _upsert_projections(conn, df, args.scoring)
            logger.info("Upserted %d projection rows", n)

        if args.type in ("predictions", "all"):
            week_dir = (
                GOLD_PREDICTIONS_DIR / f"season={args.season}" / f"week={args.week}"
            )
            pq = _latest_parquet(week_dir)
            logger.info("Loading predictions from %s", pq)
            df = pd.read_parquet(pq)
            n = _upsert_predictions(conn, df)
            logger.info("Upserted %d prediction rows", n)
    finally:
        conn.close()

    logger.info("Done")


if __name__ == "__main__":
    main()
