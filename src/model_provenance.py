"""Model provenance helper (MODEL_REVIEW_2026_08_15.md finding #2).

"No data-vintage/provenance pinning on any model artifact — metas record
timestamps + season lists, never a data hash/row-counts/code SHA. The June
artifacts cannot be traced to their training data." This module closes that
gap with one small, embeddable helper: given the Bronze/Silver directories a
training run read, produce a provenance dict (per-source row counts + latest
partition timestamp + git SHA) ready to drop into a model's meta.json.

It does not read or hash any raw data -- row counts come from Parquet footer
metadata only (same cheap technique as
``scripts/check_data_completeness.py::_sum_parquet_rows``), so this is safe
and fast to call at save time even for large Silver directories.

Usage -- each train_*.py script adds this at save time, right before the
``json.dump(meta, ...)`` call:

    from model_provenance import build_provenance

    meta["provenance"] = build_provenance({
        "silver_players_usage": "silver/players/usage",
        "silver_players_advanced": "silver/players/advanced",
        "bronze_players_snaps": "bronze/players/snaps",
    })
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"


def _scan_parquet_source(base: Path) -> Tuple[int, int, Optional[str]]:
    """Row count, file count, and latest mtime (ISO8601 UTC) for a source dir.

    Recurses under ``base`` (season=/week= partitions included). Row counts
    come from Parquet footer metadata -- no data is actually read. A missing
    directory or an unreadable file degrades to a 0/None entry rather than
    raising, matching the warn-never-block convention used elsewhere for
    Bronze/Silver reads.
    """
    import pyarrow.parquet as pq

    if not base.is_dir():
        return 0, 0, None

    files = sorted(base.rglob("*.parquet"))
    total_rows = 0
    latest_mtime: Optional[float] = None
    for f in files:
        try:
            total_rows += pq.ParquetFile(str(f)).metadata.num_rows
        except Exception:
            continue
        mt = f.stat().st_mtime
        if latest_mtime is None or mt > latest_mtime:
            latest_mtime = mt

    latest_iso = (
        datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
        if latest_mtime is not None
        else None
    )
    return total_rows, len(files), latest_iso


def git_sha(cwd: Optional[Path] = None) -> Optional[str]:
    """Current git commit SHA (full hex), or None if unavailable.

    None covers: not a git repo, git not installed, or a shallow clone with
    a detached/unresolvable HEAD -- never raises.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def build_provenance(
    source_dirs: Mapping[str, str],
    data_root: Optional[Path] = None,
    project_root: Optional[Path] = None,
) -> Dict:
    """Build a provenance dict for the Bronze/Silver sources a training run read.

    Args:
        source_dirs: Mapping of a short source label (e.g.
            ``"silver_players_usage"``) to its path relative to ``data/``
            (e.g. ``"silver/players/usage"``). Every ``*.parquet`` file
            under that path, recursively (covers season=/week=
            partitioning), is counted.
        data_root: Override for the ``data/`` root (tests only; production
            callers should omit this).
        project_root: Override for the repo root used to resolve the git
            SHA (tests only).

    Returns:
        A dict shaped for direct embedding as ``meta["provenance"]``::

            {
                "generated_at": "2026-08-15T12:00:00+00:00",
                "git_sha": "abc123..." | None,
                "sources": {
                    "silver_players_usage": {
                        "path": "silver/players/usage",
                        "row_count": 123456,
                        "n_files": 10,
                        "latest_partition_at": "2026-08-10T09:00:00+00:00" | None,
                    },
                    ...
                },
            }
    """
    root = Path(data_root) if data_root is not None else DATA_ROOT
    sources = {}
    for label, rel_path in source_dirs.items():
        row_count, n_files, latest_partition_at = _scan_parquet_source(root / rel_path)
        sources[label] = {
            "path": rel_path,
            "row_count": row_count,
            "n_files": n_files,
            "latest_partition_at": latest_partition_at,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(project_root),
        "sources": sources,
    }
