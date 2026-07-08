"""
Utility functions for the NFL Data Engineering Pipeline
"""
# PEP 563: store annotations as strings so the module imports cleanly even
# when optional deps (pyspark, boto3) are missing — the pandas-only
# helpers (canonical_team, apply_sleeper_team_overrides, get_script_sha)
# are imported by `src/lineup_builder.py` on the FastAPI surface, which
# runs without those heavy deps. Without lazy annotations, `SparkSession`
# in `def get_spark_session(...)` evaluates eagerly at module-import time
# and crashes the whole API on Railway.
from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from typing import Optional, Dict, Any

# boto3 is an optional dependency at module-import time. Production
# Railway image runs only the FastAPI surface and doesn't ship boto3 in
# `web/api/serverless/requirements.txt` (S3 is dev-only). Eagerly
# importing it here would crash any caller that imports `utils` for the
# pandas-only helpers (canonical_team, apply_sleeper_team_overrides,
# get_script_sha), which is exactly how the Railway lineups endpoint
# 500s. Defer to a lazy import inside the S3 helpers via _require_boto3().
try:
    import boto3  # noqa: F401
    from botocore.exceptions import ClientError  # noqa: F401
    _BOTO3_AVAILABLE = True
except (ImportError, Exception):
    _BOTO3_AVAILABLE = False

# PySpark is an optional dependency — guard the import so that modules
# using only the pandas/boto3 helpers (get_latest_s3_key, download_latest_parquet,
# validate_s3_path, etc.) can load without a Java runtime installed.
try:
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.functions import *
    from pyspark.sql.types import *
    _PYSPARK_AVAILABLE = True
except (ImportError, Exception):
    _PYSPARK_AVAILABLE = False


def _require_boto3():
    """Raise a clear error when boto3 is needed but not installed.

    The Railway production image deliberately omits boto3 — the FastAPI
    surface reads everything from local Parquet. Anything that calls into
    S3 (dev/CI ingestion) needs boto3; the install hint here makes the
    failure obvious instead of letting Python's `NameError: boto3` mask it.
    """
    if not _BOTO3_AVAILABLE:
        raise ImportError(
            "boto3 is required for S3 operations but is not installed. "
            "Run `pip install boto3 botocore` (already in requirements.txt; "
            "absent from web/api/serverless/requirements.txt by design)."
        )

# Library module: logging configuration belongs to entrypoints, not here.
logger = logging.getLogger(__name__)

def get_spark_session(app_name: str = "NFL-Data-Pipeline") -> SparkSession:
    """
    Create and configure Spark session for NFL data processing
    
    Args:
        app_name: Name of the Spark application
        
    Returns:
        Configured SparkSession
    """
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()

def pandas_to_spark(spark: SparkSession, df: pd.DataFrame, schema: Optional[StructType] = None) -> DataFrame:
    """
    Convert pandas DataFrame to Spark DataFrame with optional schema
    
    Args:
        spark: SparkSession
        df: pandas DataFrame
        schema: Optional Spark schema
        
    Returns:
        Spark DataFrame
    """
    if schema:
        return spark.createDataFrame(df, schema)
    return spark.createDataFrame(df)

def validate_s3_path(s3_path: str) -> bool:
    """
    Validate if S3 path exists and is accessible

    Args:
        s3_path: S3 path to validate

    Returns:
        True if path is valid and accessible
    """
    try:
        # Parse S3 path
        if not s3_path.startswith('s3://'):
            return False

        path_parts = s3_path.replace('s3://', '').split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else ''

        # Check if bucket exists
        _require_boto3()
        s3_client = boto3.client('s3')
        s3_client.head_bucket(Bucket=bucket)
        
        return True
        
    except ClientError as e:
        logger.error(f"S3 path validation failed for {s3_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating S3 path {s3_path}: {e}")
        return False

def add_audit_columns(df: DataFrame) -> DataFrame:
    """
    Add standard audit columns to DataFrame
    
    Args:
        df: Input Spark DataFrame
        
    Returns:
        DataFrame with audit columns added
    """
    return df.withColumn("created_at", current_timestamp()) \
             .withColumn("updated_at", current_timestamp()) \
             .withColumn("data_source", lit("nfl-data-py"))

def validate_game_data_quality(df: DataFrame) -> Dict[str, Any]:
    """
    Validate data quality for NFL game data
    
    Args:
        df: Spark DataFrame containing game data
        
    Returns:
        Dictionary with validation results
    """
    total_rows = df.count()
    
    validation_results = {
        "total_rows": total_rows,
        "validations": {}
    }
    
    # Check for null values in critical columns
    critical_columns = ["game_id", "home_team", "away_team", "game_date"]
    
    for col in critical_columns:
        if col in df.columns:
            null_count = df.filter(df[col].isNull()).count()
            null_percentage = (null_count / total_rows) * 100 if total_rows > 0 else 0
            
            validation_results["validations"][f"{col}_null_check"] = {
                "null_count": null_count,
                "null_percentage": null_percentage,
                "passed": null_percentage <= 10  # Max 10% nulls allowed
            }
    
    # Check for duplicate games
    if "game_id" in df.columns:
        distinct_games = df.select("game_id").distinct().count()
        duplicate_games = total_rows - distinct_games
        
        validation_results["validations"]["duplicate_check"] = {
            "duplicate_count": duplicate_games,
            "passed": duplicate_games == 0
        }
    
    return validation_results

def write_validation_report(validation_results: Dict[str, Any], output_path: str) -> None:
    """
    Write data quality validation report to S3
    
    Args:
        validation_results: Results from validation
        output_path: S3 path to write report
    """
    try:
        import json

        # Convert to JSON and upload to S3
        report_json = json.dumps(validation_results, indent=2, default=str)

        # Parse S3 path
        path_parts = output_path.replace('s3://', '').split('/', 1)
        bucket = path_parts[0]
        key = path_parts[1] if len(path_parts) > 1 else 'validation_report.json'

        _require_boto3()
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=report_json,
            ContentType='application/json'
        )
        
        logger.info(f"Validation report written to {output_path}")

    except Exception as e:
        logger.error(f"Failed to write validation report: {e}")
        raise


def get_latest_s3_key(
    s3_client,
    bucket: str,
    prefix: str,
    suffix: str = ".parquet",
) -> Optional[str]:
    """Return the S3 key of the most recently written object matching suffix under prefix.

    Args:
        s3_client: Configured boto3 S3 client.
        bucket: S3 bucket name.
        prefix: S3 key prefix to search (e.g. "players/usage/season=2024/week=1/").
        suffix: File extension filter. Defaults to ".parquet".

    Returns:
        S3 key string of the latest object, or None if no matching objects exist.
    """
    _require_boto3()
    candidates = []
    paginator = s3_client.get_paginator('list_objects_v2')
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get('Contents', []):
                if obj['Key'].endswith(suffix):
                    candidates.append((obj['LastModified'], obj['Key']))
    except ClientError as e:
        logger.error(f"Failed to list objects at s3://{bucket}/{prefix}: {e}")
        return None

    if not candidates:
        logger.warning(f"No {suffix} objects found at s3://{bucket}/{prefix}")
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    latest_key = candidates[0][1]
    logger.info(
        f"Resolved latest key: {latest_key} "
        f"(selected 1 of {len(candidates)} candidate(s))"
    )
    return latest_key


def download_latest_parquet(
    s3_client,
    bucket: str,
    prefix: str,
    tmp_dir: str = "/tmp",
) -> pd.DataFrame:
    """Download the single most recently written Parquet file from an S3 prefix.

    Prevents duplicate rows that occur when multiple timestamped files accumulate
    in the same partition directory. Always reads exactly one file -- the latest
    by S3 LastModified timestamp.

    Args:
        s3_client: Configured boto3 S3 client.
        bucket: S3 bucket name.
        prefix: S3 key prefix to search.
        tmp_dir: Local directory for temporary download. Defaults to "/tmp".

    Returns:
        DataFrame containing the latest file's data, or empty DataFrame if none found.
    """
    key = get_latest_s3_key(s3_client, bucket, prefix)
    if key is None:
        return pd.DataFrame()

    safe_name = key.replace('/', '_')
    tmp_path = os.path.join(tmp_dir, safe_name)

    try:
        s3_client.download_file(bucket, key, tmp_path)
        df = pd.read_parquet(tmp_path)
        logger.info(f"Loaded {len(df):,} rows from s3://{bucket}/{key}")
        return df
    except Exception as e:
        logger.error(f"Failed to download or read s3://{bucket}/{key}: {e}")
        return pd.DataFrame()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def get_script_sha(script_path: str) -> Dict[str, Any]:
    """Resolve the git provenance of an audit script.

    Returns a JSON-serialisable dict capturing the file-specific
    last-commit SHA and whether the working tree has uncommitted
    changes against that file. Designed to be embedded under a
    top-level ``script_provenance`` key in audit-script JSON
    outputs (Phase 79 DQ-01 contract).

    Args:
        script_path: Path to the audit script. May be absolute or
            relative to the repository root. Need not exist on disk.

    Returns:
        Dict with keys:
          - ``sha``: 40-char hex SHA of the last commit that touched
            the file, or the literal string ``"unknown"`` when the
            path is untracked, missing, or git is unavailable.
          - ``dirty``: True when ``git diff HEAD -- {path}`` is
            non-empty. False otherwise (including for ``unknown``
            cases).
          - ``resolved_at``: ISO-8601 UTC timestamp recorded at the
            moment the helper ran.

    Phase 84 DEPLOY-04 consumes ``sha`` and ``dirty`` to gate audit
    evidence. ``dirty=True`` is grounds for hard-rejection; an
    unknown ``sha`` means "pre-provenance era — manual review"
    (D-08).

    Subprocess invocations use ``shell=False`` and pass ``script_path``
    after a ``--`` separator so a hostile path (e.g. ``--upload-pack``)
    cannot be misinterpreted as a git option.
    """
    resolved_at = datetime.now(timezone.utc).isoformat()
    path = str(script_path)

    # Resolve last-commit SHA for this exact file.
    try:
        log_proc = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", path],
            shell=False,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        sha_raw = log_proc.stdout.strip()
        sha = sha_raw if (log_proc.returncode == 0 and len(sha_raw) == 40) else "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # FileNotFoundError = git binary missing; TimeoutExpired = hung subprocess.
        sha = "unknown"

    # Probe for uncommitted local edits against this file.
    dirty = False
    if sha != "unknown":
        try:
            diff_proc = subprocess.run(
                ["git", "diff", "HEAD", "--", path],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            dirty = bool(diff_proc.stdout.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            dirty = False

    return {"sha": sha, "dirty": dirty, "resolved_at": resolved_at}


# Map alternate team abbreviations to the canonical nflverse code so a
# depth-chart-vs-projection team comparison doesn't false-positive on
# alias drift (e.g. projection rows tagged "KAN" while the depth chart
# uses "KC"). The Gold projections file mixes abbreviations because
# rookie rows come from CFBD (PFR-style) while veterans come from
# nflverse.
_TEAM_ALIASES: Dict[str, str] = {
    "KAN": "KC",
    "LAR": "LA",
    "LVR": "LV",
    "NOR": "NO",
    "NWE": "NE",
    "SFO": "SF",
    "TAM": "TB",
    "JAC": "JAX",
    "GNB": "GB",
}


def canonical_team(value: object) -> str:
    """Return the canonical nflverse team code, uppercased.

    Maps alternate abbreviations (KAN/LAR/LVR/NOR/NWE/SFO/TAM/JAC/GNB)
    to their nflverse equivalents. Idempotent — passes nflverse codes
    through unchanged. ``None``/empty inputs return ``""``.
    """
    if value is None:
        return ""
    code = str(value).strip().upper()
    return _TEAM_ALIASES.get(code, code)


def apply_sleeper_team_overrides(
    df: pd.DataFrame,
    sleeper_rosters: pd.DataFrame,
    *,
    team_col: str = "team",
    name_col: str = "player_name",
    position_col: Optional[str] = "position",
    logger=None,
) -> pd.DataFrame:
    """Override stale team assignments with the latest Sleeper rosters_live.

    nflverse seasonal rosters lag real-world roster moves by weeks during the
    offseason — e.g. Malik Willis is on MIA per Sleeper but still tagged GB
    in nflverse's seasonal frame. Without this override, projections (and
    everything downstream that joins by player_id) attribute a player's
    stats to his previous team's role.

    Sleeper's rosters_live parquet keys on ``name_key`` (lowercased
    ``player_name``). When both ``df`` and Sleeper carry a ``position``
    column the helper joins on ``(name_key, position)`` so two distinct
    rostered players sharing a name (e.g. two "Mike Williams" at different
    positions) don't silently overwrite each other. When position is
    absent on either side it falls back to ``name_key`` alone.

    Args:
        df: Frame to mutate (returned with team_col updated).
        sleeper_rosters: Bronze ``rosters_live`` DataFrame. Must carry
            ``name_key``, ``team``, and ``is_free_agent`` columns; an empty
            frame is a no-op.
        team_col: Column on ``df`` that carries the team to override.
        name_col: Column on ``df`` that carries the player name to match.
        position_col: Column on ``df`` carrying the player position. When
            both ``df[position_col]`` and ``sleeper_rosters['position']``
            exist the helper joins on ``(name_key, position)``. Pass
            ``None`` to force name-only matching (useful for tests).
        logger: Optional Python logger; when provided, an INFO message
            summarises overrides applied (count + sample).

    Returns:
        The same ``df`` (in-place ``team_col`` mutation) with the Sleeper
        team value applied where it differs from the existing assignment.
    """
    if sleeper_rosters is None or sleeper_rosters.empty:
        return df
    required = {"name_key", "team", "is_free_agent"}
    if not required.issubset(sleeper_rosters.columns):
        return df
    if name_col not in df.columns or team_col not in df.columns:
        return df

    use_position = (
        position_col is not None
        and position_col in df.columns
        and "position" in sleeper_rosters.columns
    )
    dedup_keys = ["name_key", "position"] if use_position else ["name_key"]

    # Suffix-aware name normalization on BOTH sides. Sleeper's name_key is
    # plain lowercase ("kenneth walker") while nflverse names carry
    # generational suffixes ("Kenneth Walker III"); a raw-lowercase join
    # silently misses those players and leaves their team stale (the
    # 2026-07-08 Kenneth Walker SEA→KC sanity-gate failure).
    try:
        from src.consensus_anchor import normalize_player_name
    except ImportError:
        from consensus_anchor import normalize_player_name

    sleeper_rosters = sleeper_rosters.copy()
    sleeper_rosters["name_key"] = (
        sleeper_rosters["name_key"]
        .fillna("")
        .astype(str)
        .map(normalize_player_name)
    )

    sort_col = (
        "refreshed_at" if "refreshed_at" in sleeper_rosters.columns else "season"
    )
    if sort_col in sleeper_rosters.columns:
        latest = sleeper_rosters.sort_values(sort_col).drop_duplicates(
            subset=dedup_keys, keep="last"
        )
    else:
        latest = sleeper_rosters.drop_duplicates(subset=dedup_keys, keep="last")

    rostered = latest[~latest["is_free_agent"].astype(bool)]
    lookup = rostered.set_index(dedup_keys)["team"]

    name_keys = df[name_col].fillna("").astype(str).map(normalize_player_name)
    if use_position:
        # Rows with empty-string position values (e.g. malformed entries or
        # defensive players accidentally in a fantasy frame) intentionally
        # miss the (name_key, "") MultiIndex lookup and yield NaN. Behavior:
        # the original team is preserved — the conservative outcome — at
        # the cost of not overriding what would have been a name-only match
        # under the legacy fallback. This is by design: a bad position is a
        # data-quality signal, not a reason to broaden the join.
        positions = df[position_col].fillna("").astype(str)
        index = pd.MultiIndex.from_arrays(
            [name_keys.values, positions.values], names=dedup_keys
        )
        new_team = pd.Series(lookup.reindex(index).values, index=df.index)
    else:
        new_team = name_keys.map(lookup)

    override_mask = new_team.notna() & (
        df[team_col].astype(str) != new_team.astype(str)
    )

    if override_mask.any():
        if logger is not None:
            sample = (
                df.loc[override_mask, [name_col, team_col]]
                .assign(new_team=new_team[override_mask].values)
                .head(8)
                .to_dict("records")
            )
            logger.info(
                "Overrode %s on %d player(s) from Sleeper rosters_live "
                "(e.g. %s)",
                team_col,
                int(override_mask.sum()),
                sample,
            )
        df.loc[override_mask, team_col] = new_team[override_mask]

    return df
