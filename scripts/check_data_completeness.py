#!/usr/bin/env python3
"""
Data completeness invariant check — makes the "silent-hole" bug class
unrepeatable (see .planning/DATA_COMPLETENESS_AUDIT.md, 2026-08-09).

Every silent-hole found in that audit reduced to the same shape: "reader X
requires data/{bronze,silver,gold}/... for seasons Y, the path is
absent/partial, and nothing signals it — no crash, no CI failure, just a
quietly-empty DataFrame in production." This script is a declarative
manifest of every path that must exist (REQUIREMENTS below), checked
directly against the filesystem, so a future regression of the exact same
shape fails loudly instead of silently.

Two modes:
    --local   Full check — every manifest entry, as a dev machine should
              have it (used by the weekly pipeline post-ingest).
    --ci      Only entries marked committed=True — what a fresh `git clone`
              gets, which is exactly what the HF Space prod deploy sees
              (`deploy/huggingface/Dockerfile` clones the repo at build
              time). Uncommitted/local-only paths are skipped so CI never
              fails on data that was never supposed to ship.

Exit code 0 = every FAIL-tier requirement satisfied (WARN-tier misses are
reported but never block). Exit code 1 = at least one FAIL-tier miss.

Usage:
    python scripts/check_data_completeness.py --local
    python scripts/check_data_completeness.py --ci
"""

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

# ---------------------------------------------------------------------------
# Project root on sys.path so we can import src/config.py
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import config  # noqa: E402 — must come after sys.path insertion

# ---------------------------------------------------------------------------
# Paths — module globals so tests can monkeypatch DATA_ROOT to a tmp dir
# (same pattern as scripts/check_ml_output.py's GOLD_DIR/PROJECT_ROOT).
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data"

# Seasons with committed player training data (2016-2025). Single source of
# truth per src/config.py — never hardcode a season range here.
PLAYER_SEASONS = tuple(config.PLAYER_DATA_SEASONS)

# The season currently "live" (rosters/depth-charts/schedules/preseason
# projections/sentiment for the in-progress or upcoming season). Computed
# the same way config.DEFAULT_SEASON is: current calendar year from March
# onward, else the previous year.
CURRENT_SEASON = config.DEFAULT_SEASON

# depth_charts / rosters / schedules need both the full historical training
# range AND the current season (TD-08/09: PlayerNameResolver + current-week
# resolution need live data; backtests/game logs need the historical range).
_HISTORICAL_PLUS_CURRENT = tuple(sorted(set(PLAYER_SEASONS) | {CURRENT_SEASON}))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Requirement:
    """One data-existence invariant.

    Attributes:
        id: Short stable identifier (used in output and issue dedup).
        description: Why this path matters — cites the audit finding / TD.
        tier: "FAIL" (blocks CI / prod correctness) or "WARN" (nice-to-have,
            degrades gracefully per the audit — never blocks).
        committed: Whether this path is `.gitignore`-allowlisted and thus
            present in a fresh clone (== what the HF Space prod deploy
            sees). --ci mode only checks committed=True entries.
        path_template: Path relative to data/, with an optional "{season}"
            placeholder.
        seasons: Seasons to substitute into path_template, one check per
            season. None means path_template is a single static path.
        glob: Glob pattern (relative to the resolved directory) that must
            match at least `min_files` files.
        min_files: Minimum matching-file count for a PASS.
        min_rows: Optional row-count floor, summed across matched parquet
            files for that season/path. Catches a written-but-empty file —
            the exact "path exists, data doesn't" variant of the silent
            no-op. None skips the row check (cheap default; only set for
            the paths where an empty file previously caused a real
            production bug).
    """

    id: str
    description: str
    tier: str
    committed: bool
    path_template: str
    seasons: Optional[Sequence[int]] = None
    glob: str = "**/*.parquet"
    min_files: int = 1
    min_rows: Optional[int] = None


REQUIREMENTS: tuple = (
    # -- Bronze player data: the RB_SNAP_COLLAPSE / injuries silent no-op
    # (audit finding #1, FIXED 2026-08-09). generate_projections.py and
    # rb_role_signals.py glob these paths and continue on empty — a missing
    # season here is invisible without this check. min_rows guards against
    # a written-but-empty file, not just an absent directory.
    Requirement(
        id="bronze_players_weekly",
        description="Player weekly actuals — RB_SNAP_COLLAPSE dependency (audit #1, TD-10)",
        tier="FAIL",
        committed=True,
        path_template="bronze/players/weekly/season={season}",
        seasons=PLAYER_SEASONS,
        min_rows=100,
    ),
    Requirement(
        id="bronze_players_snaps",
        description="Snap counts — RB_SNAP_COLLAPSE correction input (audit #1)",
        tier="FAIL",
        committed=True,
        path_template="bronze/players/snaps/season={season}",
        seasons=PLAYER_SEASONS,
        min_rows=100,
    ),
    Requirement(
        id="bronze_players_injuries",
        description="Injuries — rb_role_signals.py / RB_SNAP_COLLAPSE input (audit #1)",
        tier="FAIL",
        committed=True,
        path_template="bronze/players/injuries/season={season}",
        seasons=PLAYER_SEASONS,
        min_rows=100,
    ),
    # -- Bronze reference data required by TD-08/09 for the shipped deploy.
    Requirement(
        id="bronze_depth_charts",
        description="Depth charts — PlayerNameResolver needs these for sentiment ingestion (TD-08)",
        tier="FAIL",
        committed=True,
        path_template="bronze/depth_charts/season={season}",
        seasons=_HISTORICAL_PLUS_CURRENT,
    ),
    Requirement(
        id="bronze_players_rosters",
        description="Rosters — PlayerNameResolver + roster/lineup endpoints (TD-08)",
        tier="FAIL",
        committed=True,
        path_template="bronze/players/rosters/season={season}",
        seasons=_HISTORICAL_PLUS_CURRENT,
    ),
    Requirement(
        id="bronze_schedules",
        description="Schedules — web/Dockerfile COPY, current-week resolution (TD-09)",
        tier="FAIL",
        committed=True,
        path_template="bronze/schedules/season={season}",
        seasons=_HISTORICAL_PLUS_CURRENT,
    ),
    Requirement(
        id="bronze_draft_picks",
        description="Draft picks — college-network graph features, was 100% absent (audit #5)",
        tier="FAIL",
        committed=True,
        path_template="bronze/draft_picks/season={season}",
        seasons=PLAYER_SEASONS,
    ),
    Requirement(
        id="bronze_combine",
        description="Combine — college-network graph features, was 100% absent (audit #5)",
        tier="FAIL",
        committed=True,
        path_template="bronze/combine/season={season}",
        seasons=PLAYER_SEASONS,
    ),
    # -- Gold: prod-serving output.
    Requirement(
        id="gold_projections_preseason",
        description="Preseason projections, current season vintage",
        tier="FAIL",
        committed=True,
        path_template="gold/projections/preseason/season={season}",
        seasons=(CURRENT_SEASON,),
    ),
    # gold_projections_weekly (current vintage) is a dynamic check — see
    # check_latest_weekly_gold() below. There's no fixed "current week" to
    # template here; the most recent committed partition IS the definition
    # of current vintage, so it can't be a static REQUIREMENTS entry.
    # -- WARN-tier: graceful-fallback paths per the audit (never silent-null,
    # just degrade to a less-specific source).
    Requirement(
        id="adp",
        description="Per-source ADP CSVs (ffc/espn/sleeper) — draft.py get_adp fallback (audit #7)",
        tier="WARN",
        committed=True,
        path_template="adp",
        glob="*.csv",
        min_files=3,
    ),
    Requirement(
        id="external_rankings",
        description="External rankings cache (Sleeper/FantasyPros/ESPN/DraftSharks)",
        tier="WARN",
        committed=True,
        path_template="external",
        glob="*.json",
        min_files=3,
    ),
    Requirement(
        id="gold_sentiment",
        description="Sentiment aggregation Gold, current season (warn-tier per task spec)",
        tier="WARN",
        committed=True,
        path_template="gold/sentiment/season={season}",
        seasons=(CURRENT_SEASON,),
    ),
)


# ---------------------------------------------------------------------------
# Check execution
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    id: str
    tier: str       # "FAIL" or "WARN" — configured criticality
    passed: bool
    message: str


def _count_files(base: Path, glob_pattern: str) -> list:
    if not base.is_dir():
        return []
    return sorted(base.glob(glob_pattern))


def _sum_parquet_rows(files: list) -> int:
    """Row count via Parquet footer metadata only — no data read."""
    import pyarrow.parquet as pq

    total = 0
    for f in files:
        try:
            total += pq.ParquetFile(str(f)).metadata.num_rows
        except Exception:
            pass  # unreadable/corrupt file — file-count check already flags it
    return total


def check_requirement(req: Requirement) -> list:
    """Evaluate one Requirement, one CheckResult per season (or one if static)."""
    results = []
    seasons = req.seasons if req.seasons is not None else [None]

    for season in seasons:
        rel = req.path_template.format(season=season) if season is not None else req.path_template
        check_id = f"{req.id}[{season}]" if season is not None else req.id
        base = DATA_ROOT / rel
        files = _count_files(base, req.glob)

        if len(files) < req.min_files:
            results.append(CheckResult(
                id=check_id, tier=req.tier, passed=False,
                message=f"{len(files)} file(s) at data/{rel} (need >= {req.min_files})",
            ))
            continue

        if req.min_rows is not None:
            rows = _sum_parquet_rows(files)
            if rows < req.min_rows:
                results.append(CheckResult(
                    id=check_id, tier=req.tier, passed=False,
                    message=f"{len(files)} file(s) but only {rows} row(s) at data/{rel} (need >= {req.min_rows})",
                ))
                continue

        results.append(CheckResult(
            id=check_id, tier=req.tier, passed=True,
            message=f"{len(files)} file(s) at data/{rel}",
        ))

    return results


def check_latest_weekly_gold() -> CheckResult:
    """Dynamic check: the most recent committed season/week Gold projection
    partition must have at least one file.

    Deliberately dynamic rather than a fixed season/week REQUIREMENTS entry:
    "current vintage" for the weekly cron output has no fixed value to
    template ahead of time — the most recent partition IS the definition.
    """
    proj_root = DATA_ROOT / "gold" / "projections"
    season_dirs = sorted(
        (d for d in proj_root.glob("season=*") if d.is_dir()),
        key=lambda d: int(d.name.split("=", 1)[1]),
    ) if proj_root.is_dir() else []

    if not season_dirs:
        return CheckResult(
            id="gold_projections_weekly_latest", tier="FAIL", passed=False,
            message="No data/gold/projections/season=*/ directories found",
        )

    latest_season_dir = season_dirs[-1]
    week_dirs = sorted(
        (d for d in latest_season_dir.glob("week=*") if d.is_dir()),
        key=lambda d: int(d.name.split("=", 1)[1]),
    )

    if not week_dirs:
        return CheckResult(
            id="gold_projections_weekly_latest", tier="FAIL", passed=False,
            message=f"No week=*/ partitions under data/{latest_season_dir.relative_to(DATA_ROOT)}",
        )

    latest_week_dir = week_dirs[-1]
    files = _count_files(latest_week_dir, "*.parquet")
    rel = latest_week_dir.relative_to(DATA_ROOT)

    if not files:
        return CheckResult(
            id="gold_projections_weekly_latest", tier="FAIL", passed=False,
            message=f"0 file(s) at data/{rel} (need >= 1)",
        )

    return CheckResult(
        id="gold_projections_weekly_latest", tier="FAIL", passed=True,
        message=f"{len(files)} file(s) at data/{rel} (latest committed partition)",
    )


def run_checks(ci_mode: bool) -> list:
    """Run every applicable requirement and return the full CheckResult list.

    --ci mode skips committed=False entries (none currently exist in the
    manifest, but the flag exists so a future local-only entry — e.g. a
    Silver path that's never shipped — doesn't false-fail CI).
    """
    results: list = []
    for req in REQUIREMENTS:
        if ci_mode and not req.committed:
            continue
        results.extend(check_requirement(req))

    results.append(check_latest_weekly_gold())
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_report(results: list, ci_mode: bool) -> int:
    """Print a table of results and return the process exit code."""
    mode_label = "CI (committed paths only)" if ci_mode else "LOCAL (full manifest)"
    print(f"\nNFL Data Completeness Check — mode={mode_label}")
    print("=" * 88)

    fail_misses = []
    warn_misses = []

    for r in results:
        status = "PASS" if r.passed else r.tier
        print(f"[{status:>4}] {r.id:<40} {r.message}")
        if not r.passed:
            (fail_misses if r.tier == "FAIL" else warn_misses).append(r)

    print("-" * 88)
    print(
        f"Summary: {len(results)} check(s) — "
        f"{len(results) - len(fail_misses) - len(warn_misses)} PASS, "
        f"{len(warn_misses)} WARN-miss, {len(fail_misses)} FAIL-miss"
    )

    if fail_misses:
        print(f"Overall: FAIL — {len(fail_misses)} FAIL-tier requirement(s) not met:")
        for r in fail_misses:
            print(f"  - {r.id}: {r.message}")
    else:
        print("Overall: PASS" + (f" (with {len(warn_misses)} WARN-tier miss(es), non-blocking)" if warn_misses else ""))

    print("=" * 88)
    return 1 if fail_misses else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Data-existence invariant check — see .planning/DATA_COMPLETENESS_AUDIT.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--local", action="store_true",
        help="Full check — every manifest entry (dev machines).",
    )
    mode_group.add_argument(
        "--ci", action="store_true",
        help="Only committed=True entries — what a fresh clone / prod deploy gets.",
    )
    args = parser.parse_args()

    results = run_checks(ci_mode=args.ci)
    return print_report(results, ci_mode=args.ci)


if __name__ == "__main__":
    sys.exit(main())
