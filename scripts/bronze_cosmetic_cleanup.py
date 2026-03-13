#!/usr/bin/env python3
"""One-time Bronze filesystem cleanup script.

Handles two cosmetic issues from backfill phases:
1. player_weekly 2016-2019: move files from week=0/ subdirs to season level
2. draft_picks 2000-2025: deduplicate append artifacts (keep newest per season)

Default mode is dry-run. Use --execute to perform actual changes.
"""

import argparse
import shutil
from pathlib import Path


BRONZE_ROOT = Path("data/bronze")
PLAYER_WEEKLY_DIR = BRONZE_ROOT / "players" / "weekly"
DRAFT_PICKS_DIR = BRONZE_ROOT / "draft_picks"

NORMALIZE_SEASONS = [2016, 2017, 2018, 2019]


def normalize_player_weekly(execute: bool = False) -> dict:
    """Move player_weekly 2016-2019 parquet files from week=0/ to season level.

    Args:
        execute: If True, perform filesystem changes. If False, dry-run only.

    Returns:
        Dict with counts: files_moved, dirs_removed, files_skipped.
    """
    stats = {"files_moved": 0, "dirs_removed": 0, "files_skipped": 0}

    for year in NORMALIZE_SEASONS:
        week0_dir = PLAYER_WEEKLY_DIR / f"season={year}" / "week=0"
        if not week0_dir.exists():
            print(f"  SKIP (not found): {week0_dir}")
            continue

        season_dir = week0_dir.parent
        for parquet_file in sorted(week0_dir.glob("*.parquet")):
            dest = season_dir / parquet_file.name
            if dest.exists():
                print(f"  SKIP (already exists): {dest}")
                stats["files_skipped"] += 1
                continue

            if execute:
                shutil.move(str(parquet_file), str(dest))
                print(f"  MOVED: {parquet_file} -> {dest}")
            else:
                print(f"  WOULD MOVE: {parquet_file} -> {dest}")
            stats["files_moved"] += 1

        # Remove empty week=0/ directory
        if execute:
            remaining = list(week0_dir.iterdir())
            if not remaining:
                week0_dir.rmdir()
                print(f"  REMOVED empty dir: {week0_dir}")
                stats["dirs_removed"] += 1
            else:
                print(f"  KEPT dir (not empty): {week0_dir}")
        else:
            print(f"  WOULD REMOVE dir: {week0_dir}")
            stats["dirs_removed"] += 1

    return stats


def deduplicate_draft_picks(execute: bool = False) -> dict:
    """Keep only the newest draft_picks parquet file per season.

    Args:
        execute: If True, delete duplicate files. If False, dry-run only.

    Returns:
        Dict with counts: files_deleted, files_kept.
    """
    stats = {"files_deleted": 0, "files_kept": 0}

    for season_dir in sorted(DRAFT_PICKS_DIR.glob("season=*")):
        if not season_dir.is_dir():
            continue

        parquet_files = sorted(season_dir.glob("draft_picks_*.parquet"))
        if len(parquet_files) <= 1:
            if parquet_files:
                stats["files_kept"] += 1
            continue

        # Keep the last (newest) file, delete the rest
        to_keep = parquet_files[-1]
        to_delete = parquet_files[:-1]

        for f in to_delete:
            if execute:
                f.unlink()
                print(f"  DELETED: {f}")
            else:
                print(f"  WOULD DELETE: {f}")
            stats["files_deleted"] += 1

        if execute:
            print(f"  KEPT: {to_keep}")
        else:
            print(f"  WOULD KEEP: {to_keep}")
        stats["files_kept"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Bronze filesystem cleanup: normalize paths and deduplicate files"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform changes (default is dry-run)",
    )
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"Bronze Cosmetic Cleanup ({mode})")
    print("=" * 50)

    print("\n1. Normalizing player_weekly 2016-2019 (move from week=0/):")
    pw_stats = normalize_player_weekly(execute=args.execute)

    print("\n2. Deduplicating draft_picks (keep newest per season):")
    dp_stats = deduplicate_draft_picks(execute=args.execute)

    print("\n" + "=" * 50)
    prefix = "" if args.execute else "(would be) "
    print(
        f"Summary: {pw_stats['files_moved']} files {prefix}moved, "
        f"{dp_stats['files_deleted']} files {prefix}deleted, "
        f"{pw_stats['dirs_removed']} dirs {prefix}removed"
    )

    if not args.execute:
        print("\nRe-run with --execute to apply changes.")


if __name__ == "__main__":
    main()
