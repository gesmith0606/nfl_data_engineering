"""
Sync Gold Parquet data to PostgreSQL for production API use.

Reads the latest Parquet files from data/gold/projections/ and
data/gold/predictions/ and upserts into the projections and predictions
tables.

Usage:
    python scripts/sync_gold_to_db.py                    # Sync all available data
    python scripts/sync_gold_to_db.py --dry-run          # Print what would be synced
    python scripts/sync_gold_to_db.py --seasons 2024     # Specific season
    python scripts/sync_gold_to_db.py --type projections # Only projections

Requires:
    DATABASE_URL environment variable (postgresql://user:pass@host:port/dbname)

If DATABASE_URL is not set the script exits gracefully without error,
making it safe to include in pipelines that may run locally.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("sync_gold_to_db")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLD_PROJECTIONS_DIR = _PROJECT_ROOT / "data" / "gold" / "projections"
GOLD_PREDICTIONS_DIR = _PROJECT_ROOT / "data" / "gold" / "predictions"

# ---------------------------------------------------------------------------
# Schema DDL (idempotent — uses CREATE TABLE IF NOT EXISTS)
# ---------------------------------------------------------------------------
DDL_PROJECTIONS = """
CREATE TABLE IF NOT EXISTS projections (
    id                SERIAL PRIMARY KEY,
    player_id         VARCHAR(20)  NOT NULL,
    player_name       VARCHAR(100) NOT NULL,
    position          VARCHAR(5)   NOT NULL,
    team              VARCHAR(5)   NOT NULL,
    season            INT          NOT NULL,
    week              INT          NOT NULL,
    scoring_format    VARCHAR(20)  NOT NULL,
    projected_points  DECIMAL(6,2),
    projected_floor   DECIMAL(6,2),
    projected_ceiling DECIMAL(6,2),
    is_bye_week       BOOLEAN DEFAULT FALSE,
    is_rookie         BOOLEAN DEFAULT FALSE,
    proj_pass_yards   DECIMAL(7,2),
    proj_pass_tds     DECIMAL(5,2),
    proj_rush_yards   DECIMAL(7,2),
    proj_rush_tds     DECIMAL(5,2),
    proj_rec          DECIMAL(5,2),
    proj_rec_yards    DECIMAL(7,2),
    proj_rec_tds      DECIMAL(5,2),
    proj_fg_makes     DECIMAL(5,2),
    proj_xp_makes     DECIMAL(5,2),
    position_rank     INT,
    injury_status     VARCHAR(30),
    projected_stats   JSONB,
    created_at        TIMESTAMP DEFAULT NOW(),
    UNIQUE (player_id, season, week, scoring_format)
)
"""

DDL_PREDICTIONS = """
CREATE TABLE IF NOT EXISTS predictions (
    id                   SERIAL PRIMARY KEY,
    game_id              VARCHAR(30)  NOT NULL,
    season               INT          NOT NULL,
    week                 INT          NOT NULL,
    home_team            VARCHAR(5)   NOT NULL,
    away_team            VARCHAR(5)   NOT NULL,
    predicted_spread     DECIMAL(5,2),
    predicted_total      DECIMAL(5,2),
    vegas_spread         DECIMAL(5,2),
    vegas_total          DECIMAL(5,2),
    spread_edge          DECIMAL(5,2),
    total_edge           DECIMAL(5,2),
    confidence_tier      VARCHAR(10),
    ats_pick             VARCHAR(10),
    ou_pick              VARCHAR(10),
    model_version        VARCHAR(30),
    created_at           TIMESTAMP DEFAULT NOW(),
    UNIQUE (game_id, model_version)
)
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most recently modified Parquet file in *directory*."""
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _safe_float(val) -> Optional[float]:
    """Convert to float or None for NaN/missing values."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (ValueError, TypeError):
        return None


def _safe_bool(val) -> bool:
    """Convert to bool, defaulting to False."""
    if val is None:
        return False
    try:
        return bool(val)
    except (ValueError, TypeError):
        return False


def _build_projected_stats_json(row: pd.Series) -> Optional[str]:
    """Build a JSONB-compatible stats dict from projection row columns."""
    stat_cols = {
        "passing_yards": "proj_passing_yards",
        "passing_tds": "proj_passing_tds",
        "interceptions": "proj_interceptions",
        "rushing_yards": "proj_rushing_yards",
        "rushing_tds": "proj_rushing_tds",
        "carries": "proj_carries",
        "receptions": "proj_receptions",
        "receiving_yards": "proj_receiving_yards",
        "receiving_tds": "proj_receiving_tds",
        "targets": "proj_targets",
    }
    stats = {}
    for stat_name, col in stat_cols.items():
        if col in row.index:
            v = _safe_float(row[col])
            if v is not None:
                stats[stat_name] = v
    return json.dumps(stats) if stats else None


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


def _ensure_schema(conn) -> None:
    """Create tables if they don't exist."""
    with conn.cursor() as cur:
        cur.execute(DDL_PROJECTIONS)
        cur.execute(DDL_PREDICTIONS)
    conn.commit()
    logger.info("Schema verified / created")


# ---------------------------------------------------------------------------
# Projection sync
# ---------------------------------------------------------------------------


def _collect_projection_files(
    seasons: Optional[list[int]] = None,
) -> list[tuple[int, int, str, Path]]:
    """
    Scan GOLD_PROJECTIONS_DIR and collect (season, week, filename) tuples.

    Parquet files use the naming pattern:
        projections_<scoring_format>_<timestamp>.parquet

    Returns list of (season, week, scoring_format, path).
    """
    entries = []
    if not GOLD_PROJECTIONS_DIR.exists():
        logger.warning("Projections directory does not exist: %s", GOLD_PROJECTIONS_DIR)
        return entries

    for season_dir in sorted(GOLD_PROJECTIONS_DIR.glob("season=*")):
        try:
            season = int(season_dir.name.split("=")[1])
        except (IndexError, ValueError):
            continue
        if seasons and season not in seasons:
            continue

        for week_dir in sorted(season_dir.glob("week=*")):
            try:
                week = int(week_dir.name.split("=")[1])
            except (IndexError, ValueError):
                continue

            # Group files by scoring format and pick the latest per format.
            # Known formats: ppr, half_ppr, standard
            # Filename pattern: projections_<scoring>_<YYYYMMDD>_<HHMMSS>.parquet
            _KNOWN_FORMATS = {"ppr", "half_ppr", "standard"}
            format_files: dict[str, Path] = {}
            for pf in week_dir.glob("projections_*.parquet"):
                stem = pf.stem  # e.g. projections_half_ppr_20260307_101855
                # Strip leading "projections_" then find which known format matches
                remainder = stem[len("projections_"):]  # e.g. half_ppr_20260307_101855
                matched_fmt = None
                for fmt in _KNOWN_FORMATS:
                    if remainder.startswith(fmt + "_") or remainder == fmt:
                        matched_fmt = fmt
                        break
                if matched_fmt is None:
                    logger.debug("Unrecognised scoring format in filename: %s", pf.name)
                    continue
                existing = format_files.get(matched_fmt)
                if existing is None or pf.stat().st_mtime > existing.stat().st_mtime:
                    format_files[matched_fmt] = pf

            for scoring, path in format_files.items():
                entries.append((season, week, scoring, path))

    return entries


def _upsert_projections(
    conn,
    season: int,
    week: int,
    scoring_format: str,
    path: Path,
    dry_run: bool,
) -> int:
    """Upsert projection rows from *path* into the projections table.

    Returns the number of rows processed.
    """
    logger.info("Reading projections: %s", path)
    df = pd.read_parquet(path)

    # Normalise column names to match DB schema
    rename_map = {
        "recent_team": "team",
        "proj_season": "season",
        "proj_week": "week",
        "proj_passing_yards": "proj_pass_yards",
        "proj_passing_tds": "proj_pass_tds",
        "proj_rushing_yards": "proj_rush_yards",
        "proj_rushing_tds": "proj_rush_tds",
        "proj_receptions": "proj_rec",
        "proj_receiving_yards": "proj_rec_yards",
        "proj_receiving_tds": "proj_rec_tds",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Override season/week from directory structure (more reliable than parquet columns)
    df["season"] = season
    df["week"] = week
    df["scoring_format"] = scoring_format

    upsert_sql = """
        INSERT INTO projections (
            player_id, player_name, position, team, season, week,
            scoring_format, projected_points, projected_floor, projected_ceiling,
            is_bye_week, is_rookie, proj_pass_yards, proj_pass_tds,
            proj_rush_yards, proj_rush_tds, proj_rec, proj_rec_yards,
            proj_rec_tds, proj_fg_makes, proj_xp_makes,
            position_rank, injury_status, projected_stats
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (player_id, season, week, scoring_format)
        DO UPDATE SET
            player_name       = EXCLUDED.player_name,
            position          = EXCLUDED.position,
            team              = EXCLUDED.team,
            projected_points  = EXCLUDED.projected_points,
            projected_floor   = EXCLUDED.projected_floor,
            projected_ceiling = EXCLUDED.projected_ceiling,
            is_bye_week       = EXCLUDED.is_bye_week,
            is_rookie         = EXCLUDED.is_rookie,
            proj_pass_yards   = EXCLUDED.proj_pass_yards,
            proj_pass_tds     = EXCLUDED.proj_pass_tds,
            proj_rush_yards   = EXCLUDED.proj_rush_yards,
            proj_rush_tds     = EXCLUDED.proj_rush_tds,
            proj_rec          = EXCLUDED.proj_rec,
            proj_rec_yards    = EXCLUDED.proj_rec_yards,
            proj_rec_tds      = EXCLUDED.proj_rec_tds,
            proj_fg_makes     = EXCLUDED.proj_fg_makes,
            proj_xp_makes     = EXCLUDED.proj_xp_makes,
            position_rank     = EXCLUDED.position_rank,
            injury_status     = EXCLUDED.injury_status,
            projected_stats   = EXCLUDED.projected_stats
    """

    rows = []
    for _, row in df.iterrows():
        stats_json = _build_projected_stats_json(row)
        rows.append((
            str(row.get("player_id", "")),
            str(row.get("player_name", "")),
            str(row.get("position", "")),
            str(row.get("team", "")),
            int(season),
            int(week),
            scoring_format,
            _safe_float(row.get("projected_points")),
            _safe_float(row.get("projected_floor")),
            _safe_float(row.get("projected_ceiling")),
            _safe_bool(row.get("is_bye_week")),
            _safe_bool(row.get("is_rookie_projection")),
            _safe_float(row.get("proj_pass_yards")),
            _safe_float(row.get("proj_pass_tds")),
            _safe_float(row.get("proj_rush_yards")),
            _safe_float(row.get("proj_rush_tds")),
            _safe_float(row.get("proj_rec")),
            _safe_float(row.get("proj_rec_yards")),
            _safe_float(row.get("proj_rec_tds")),
            _safe_float(row.get("proj_fg_makes")),
            _safe_float(row.get("proj_xp_makes")),
            int(row["position_rank"]) if _safe_float(row.get("position_rank")) is not None else None,
            str(row["injury_status"]) if row.get("injury_status") not in (None, float("nan")) and str(row.get("injury_status", "")).lower() not in ("nan", "none", "") else None,
            stats_json,
        ))

    if dry_run:
        logger.info(
            "[DRY RUN] Would upsert %d projection rows (season=%s week=%s scoring=%s)",
            len(rows),
            season,
            week,
            scoring_format,
        )
        return len(rows)

    with conn.cursor() as cur:
        cur.executemany(upsert_sql, rows)
    conn.commit()
    logger.info(
        "Upserted %d projection rows (season=%s week=%s scoring=%s)",
        len(rows),
        season,
        week,
        scoring_format,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Prediction sync
# ---------------------------------------------------------------------------


def _collect_prediction_files(
    seasons: Optional[list[int]] = None,
) -> list[tuple[int, int, Path]]:
    """Collect (season, week, path) for all prediction Parquet files."""
    entries = []
    if not GOLD_PREDICTIONS_DIR.exists():
        logger.warning("Predictions directory does not exist: %s", GOLD_PREDICTIONS_DIR)
        return entries

    for season_dir in sorted(GOLD_PREDICTIONS_DIR.glob("season=*")):
        try:
            season = int(season_dir.name.split("=")[1])
        except (IndexError, ValueError):
            continue
        if seasons and season not in seasons:
            continue

        for week_dir in sorted(season_dir.glob("week=*")):
            try:
                week = int(week_dir.name.split("=")[1])
            except (IndexError, ValueError):
                continue
            path = _latest_parquet(week_dir)
            if path:
                entries.append((season, week, path))

    return entries


def _upsert_predictions(
    conn,
    season: int,
    week: int,
    path: Path,
    dry_run: bool,
) -> int:
    """Upsert prediction rows from *path* into the predictions table.

    Returns the number of rows processed.
    """
    logger.info("Reading predictions: %s", path)
    df = pd.read_parquet(path)

    # Normalise column names — predictions may use model_spread/model_total
    rename_map = {
        "model_spread": "predicted_spread",
        "model_total": "predicted_total",
        "spread_confidence_tier": "confidence_tier",
        "total_confidence_tier": "confidence_tier",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    df["season"] = season
    df["week"] = week

    # Default model_version if column absent
    if "model_version" not in df.columns:
        df["model_version"] = "P30 Ensemble"

    upsert_sql = """
        INSERT INTO predictions (
            game_id, season, week, home_team, away_team,
            predicted_spread, predicted_total,
            vegas_spread, vegas_total,
            spread_edge, total_edge,
            confidence_tier, ats_pick, ou_pick, model_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (game_id, model_version)
        DO UPDATE SET
            season           = EXCLUDED.season,
            week             = EXCLUDED.week,
            home_team        = EXCLUDED.home_team,
            away_team        = EXCLUDED.away_team,
            predicted_spread = EXCLUDED.predicted_spread,
            predicted_total  = EXCLUDED.predicted_total,
            vegas_spread     = EXCLUDED.vegas_spread,
            vegas_total      = EXCLUDED.vegas_total,
            spread_edge      = EXCLUDED.spread_edge,
            total_edge       = EXCLUDED.total_edge,
            confidence_tier  = EXCLUDED.confidence_tier,
            ats_pick         = EXCLUDED.ats_pick,
            ou_pick          = EXCLUDED.ou_pick
    """

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("game_id", "")),
            int(season),
            int(week),
            str(row.get("home_team", "")),
            str(row.get("away_team", "")),
            _safe_float(row.get("predicted_spread")),
            _safe_float(row.get("predicted_total")),
            _safe_float(row.get("vegas_spread")),
            _safe_float(row.get("vegas_total")),
            _safe_float(row.get("spread_edge")),
            _safe_float(row.get("total_edge")),
            str(row.get("confidence_tier", "low")),
            str(row.get("ats_pick", "")),
            str(row.get("ou_pick", "")),
            str(row.get("model_version", "P30 Ensemble")),
        ))

    if dry_run:
        logger.info(
            "[DRY RUN] Would upsert %d prediction rows (season=%s week=%s)",
            len(rows),
            season,
            week,
        )
        return len(rows)

    with conn.cursor() as cur:
        cur.executemany(upsert_sql, rows)
    conn.commit()
    logger.info(
        "Upserted %d prediction rows (season=%s week=%s)",
        len(rows),
        season,
        week,
    )
    return len(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Gold Parquet data to PostgreSQL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be synced without writing to the database",
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        metavar="YEAR",
        help="Restrict sync to specific season years (e.g. --seasons 2023 2024)",
    )
    parser.add_argument(
        "--type",
        choices=["projections", "predictions", "all"],
        default="all",
        dest="data_type",
        help="Which data type to sync (default: all)",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.info(
            "DATABASE_URL not set — skipping database sync (parquet-only mode)"
        )
        sys.exit(0)

    # Import here so psycopg2 absence never crashes parquet-only runs
    try:
        import psycopg2
    except ImportError:
        logger.error(
            "psycopg2 not installed. Run: pip install psycopg2-binary"
        )
        sys.exit(1)

    # In dry-run mode: discover files and report counts without touching the DB
    if args.dry_run:
        total_rows = 0
        if args.data_type in ("projections", "all"):
            proj_files = _collect_projection_files(seasons=args.seasons)
            if not proj_files:
                logger.warning("No projection Parquet files found to sync")
            for season, week, scoring, path in proj_files:
                df = pd.read_parquet(path)
                logger.info(
                    "[DRY RUN] Would upsert %d projection rows (season=%s week=%s scoring=%s)",
                    len(df),
                    season,
                    week,
                    scoring,
                )
                total_rows += len(df)

        if args.data_type in ("predictions", "all"):
            pred_files = _collect_prediction_files(seasons=args.seasons)
            if not pred_files:
                logger.info(
                    "[DRY RUN] No prediction Parquet files found (none generated yet)"
                )
            for season, week, path in pred_files:
                df = pd.read_parquet(path)
                logger.info(
                    "[DRY RUN] Would upsert %d prediction rows (season=%s week=%s)",
                    len(df),
                    season,
                    week,
                )
                total_rows += len(df)

        logger.info("[DRY RUN] Would sync %d total rows to PostgreSQL", total_rows)
        return

    conn = psycopg2.connect(database_url)
    logger.info("Connected to PostgreSQL")

    try:
        _ensure_schema(conn)

        total_rows = 0

        # ---- Projections ----
        if args.data_type in ("projections", "all"):
            proj_files = _collect_projection_files(seasons=args.seasons)
            if not proj_files:
                logger.warning("No projection Parquet files found to sync")
            for season, week, scoring, path in proj_files:
                total_rows += _upsert_projections(
                    conn, season, week, scoring, path, dry_run=False
                )

        # ---- Predictions ----
        if args.data_type in ("predictions", "all"):
            pred_files = _collect_prediction_files(seasons=args.seasons)
            if not pred_files:
                logger.info("No prediction Parquet files found (expected if no predictions generated yet)")
            for season, week, path in pred_files:
                total_rows += _upsert_predictions(
                    conn, season, week, path, dry_run=False
                )

        logger.info("Synced %d total rows to PostgreSQL", total_rows)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
