"""Gate a waiver report before anyone acts on it.

Gold projections have been gated since v7.0 (``sanity_check_projections.py``);
waiver advice never was, so every bad recommendation this season was caught by
the user reading the report rather than by the pipeline.

    python scripts/sanity_check_waivers.py --league mantis
    python scripts/sanity_check_waivers.py --league mantis --week 7

Runs the report, then asserts the invariants in :mod:`src.waiver_sanity` —
nothing on a bye is recommended, no real money goes to a role the news says is
ending, no bid exceeds a quarter of the budget or the room's own record, every
bid has demand history behind it, the board is fresh, and roster mechanics are
present. Exits 1 on any CRITICAL so a cron or a pre-claim check can stop.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import io
import sys
from pathlib import Path
from typing import List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402

from src.waiver_sanity import check_report, summarise  # noqa: E402


def bye_teams(season: int, week: int) -> List[str]:
    """Teams with no game in ``week``; empty when the schedule is unavailable."""
    files = sorted(
        glob.glob(
            str(REPO_ROOT / "data" / "bronze" / "schedules" / f"season={season}" / "**")
            + "/*.parquet",
            recursive=True,
        )
    )
    if not files:
        return []
    sched = pd.read_parquet(files[-1])
    playing = set(sched[sched.week == week].home_team) | set(
        sched[sched.week == week].away_team
    )
    everyone = set(sched.home_team) | set(sched.away_team)
    return sorted(everyone - playing)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key")
    ap.add_argument("--week", type=int)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument(
        "--max-board-age-hours",
        type=int,
        default=36,
        help="warn when the Gold board is older than this",
    )
    args = ap.parse_args(argv)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "waiver_wire", REPO_ROOT / "scripts" / "waiver_wire.py"
    )
    waiver_wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(waiver_wire)

    argv_report = ["--league", args.league]
    if args.week:
        argv_report += ["--week", str(args.week)]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        waiver_wire.main(argv_report)
    text = buf.getvalue()
    print(text)

    week = args.week or 1
    findings = check_report(
        text,
        bye_teams=bye_teams(args.season, week),
        max_board_age_h=args.max_board_age_hours,
    )
    summary = summarise(findings)

    print("=" * 66)
    print(f"  WAIVER SANITY — {args.league} week {week}")
    print("=" * 66)
    for f in findings:
        print(f"  [{f.level}] {f.check}: {f.detail}")
    if not findings:
        print("  no findings")
    print(
        f"\n  RESULT: {'PASS' if summary['passed'] else 'FAIL'} "
        f"({summary['critical']} critical, {summary['warnings']} warnings)"
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
