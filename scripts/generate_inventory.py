#!/usr/bin/env python3
"""
Generate Bronze layer data inventory.

Scans local data/bronze/ directory (or S3) and produces a markdown table
showing file count, size, season range, column count, and last ingestion
date per data type.

Usage:
    python scripts/generate_inventory.py
    python scripts/generate_inventory.py --output docs/BRONZE_LAYER_DATA_INVENTORY.md
    python scripts/generate_inventory.py --base-dir data/bronze
"""

import argparse
import os
import re
import sys
from datetime import datetime
from typing import Dict, Optional

import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Project root on sys.path so we can import src/config.py
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Local scanning
# ---------------------------------------------------------------------------

def scan_local(base_dir: str = "data/bronze") -> Dict[str, dict]:
    """Scan a local directory tree for parquet files and collect metrics.

    Groups files by data type, which is derived from the directory path
    relative to base_dir (excluding season/week partition dirs).

    For example:
        players/weekly/season=2023/file.parquet -> data type "players/weekly"
        games/season=2023/file.parquet          -> data type "games"

    Args:
        base_dir: Root directory to scan. Defaults to "data/bronze".

    Returns:
        Dict mapping data type name to a dict with keys:
            file_count, total_size_mb, season_range, column_count, last_modified
    """
    if not os.path.isdir(base_dir):
        return {}

    # Collect all parquet file info
    file_info: Dict[str, list] = {}  # data_type -> list of file dicts

    for dirpath, _, filenames in os.walk(base_dir):
        for fname in filenames:
            if not fname.endswith(".parquet"):
                continue

            filepath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(dirpath, base_dir)

            # Extract data type: strip partition dirs (season=YYYY, week=WW)
            parts = rel_path.split(os.sep)
            type_parts = [p for p in parts if not re.match(r"^(season|week)=\d+$", p)]
            data_type = "/".join(type_parts) if type_parts else rel_path

            # Extract season from partition path
            seasons = re.findall(r"season=(\d{4})", rel_path)

            # Get file metadata
            stat = os.stat(filepath)
            size_bytes = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")

            # Get column count from schema (first file only, cached per type)
            col_count = None
            try:
                schema = pq.read_schema(filepath)
                col_count = len(schema)
            except Exception:
                col_count = 0

            if data_type not in file_info:
                file_info[data_type] = []

            file_info[data_type].append({
                "size_bytes": size_bytes,
                "mtime": mtime,
                "seasons": [int(s) for s in seasons],
                "column_count": col_count,
            })

    # Aggregate per data type
    results: Dict[str, dict] = {}
    for data_type, files in sorted(file_info.items()):
        all_seasons = []
        for f in files:
            all_seasons.extend(f["seasons"])
        all_seasons = sorted(set(all_seasons))

        if all_seasons:
            if len(all_seasons) == 1:
                season_range = str(all_seasons[0])
            else:
                season_range = f"{all_seasons[0]}-{all_seasons[-1]}"
        else:
            season_range = "N/A"

        total_size = sum(f["size_bytes"] for f in files)
        # Use column count from first file
        col_count = files[0]["column_count"] or 0
        last_mod = max(f["mtime"] for f in files)

        results[data_type] = {
            "file_count": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "season_range": season_range,
            "column_count": col_count,
            "last_modified": last_mod,
        }

    return results


# ---------------------------------------------------------------------------
# S3 scanning (stub)
# ---------------------------------------------------------------------------

def scan_s3(bucket: str = "nfl-raw", prefix: str = "") -> Dict[str, dict]:
    """Scan S3 bucket for parquet files and collect metrics.

    Requires valid AWS credentials. Uses boto3 list_objects_v2 to collect
    object metadata grouped by data type.

    Args:
        bucket: S3 bucket name. Defaults to "nfl-raw".
        prefix: S3 key prefix to scan under.

    Returns:
        Dict mapping data type name to metrics dict.

    Note:
        This is a stub for future implementation. Requires valid AWS credentials.
    """
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        print("boto3 not installed. S3 scanning requires: pip install boto3")
        return {}

    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-2"))
        paginator = s3.get_paginator("list_objects_v2")

        file_info: Dict[str, list] = {}

        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".parquet"):
                    continue

                # Derive data type from key path
                parts = key.split("/")
                type_parts = [p for p in parts[:-1] if not re.match(r"^(season|week)=\d+$", p)]
                data_type = "/".join(type_parts) if type_parts else "unknown"

                seasons = re.findall(r"season=(\d{4})", key)

                if data_type not in file_info:
                    file_info[data_type] = []

                file_info[data_type].append({
                    "size_bytes": obj["Size"],
                    "mtime": obj["LastModified"].strftime("%Y-%m-%d"),
                    "seasons": [int(s) for s in seasons],
                    "column_count": 0,  # Cannot read schema from S3 listing
                })

        # Aggregate
        results: Dict[str, dict] = {}
        for data_type, files in sorted(file_info.items()):
            all_seasons = sorted({s for f in files for s in f["seasons"]})
            if all_seasons:
                season_range = f"{all_seasons[0]}-{all_seasons[-1]}" if len(all_seasons) > 1 else str(all_seasons[0])
            else:
                season_range = "N/A"

            results[data_type] = {
                "file_count": len(files),
                "total_size_mb": round(sum(f["size_bytes"] for f in files) / (1024 * 1024), 2),
                "season_range": season_range,
                "column_count": 0,
                "last_modified": max(f["mtime"] for f in files),
            }

        return results

    except ClientError as exc:
        print(f"AWS error: {exc}")
        return {}
    except Exception as exc:
        print(f"S3 scan failed: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_markdown(results: Dict[str, dict]) -> str:
    """Generate a markdown inventory table from scan results.

    Args:
        results: Dict mapping data type to metrics (from scan_local or scan_s3).

    Returns:
        Markdown string with title, summary, and per-data-type table.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []

    lines.append("# Bronze Layer Data Inventory")
    lines.append("")
    lines.append(f"**Generated:** {now}")

    if not results:
        total_files = 0
        total_size = 0.0
    else:
        total_files = sum(r["file_count"] for r in results.values())
        total_size = sum(r["total_size_mb"] for r in results.values())

    lines.append(f"**Total Files:** {total_files}")
    lines.append(f"**Total Size:** {total_size:.2f} MB")
    lines.append("")

    if not results:
        lines.append("No Bronze parquet files found.")
        lines.append("")
        return "\n".join(lines)

    # Table header
    lines.append("| Data Type | Files | Size (MB) | Seasons | Columns | Last Updated |")
    lines.append("|-----------|-------|-----------|---------|---------|--------------|")

    for data_type in sorted(results.keys()):
        m = results[data_type]
        lines.append(
            f"| {data_type} | {m['file_count']} | {m['total_size_mb']:.2f} | "
            f"{m['season_range']} | {m['column_count']} | {m['last_modified']} |"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for generating Bronze inventory."""
    parser = argparse.ArgumentParser(
        description="Generate Bronze layer data inventory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-dir",
        default="data/bronze",
        help="Local directory to scan (default: data/bronze)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: print to stdout)",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="Scan S3 bucket instead of local directory (requires AWS credentials)",
    )
    parser.add_argument(
        "--bucket",
        default="nfl-raw",
        help="S3 bucket name when using --s3 (default: nfl-raw)",
    )
    args = parser.parse_args()

    if args.s3:
        results = scan_s3(bucket=args.bucket)
    else:
        results = scan_local(base_dir=args.base_dir)

    markdown = format_markdown(results)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(markdown)
        print(f"Inventory written to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
