#!/usr/bin/env python3
"""Our waiver claims per league as the sites show them right now (read-only).

    python scripts/check_pending_claims.py --league all
    python scripts/check_pending_claims.py --league la_liga --headed

* La Liga (ESPN): pending claims, plus this period's outcomes (EXECUTED,
  FAILED_INVALIDPLAYERSOURCE = outbid or the drop was already used, CANCELED).
* Feetball (Yahoo): the team page's Transactions box (pending claims + trades).
* Mantis (Sleeper): pending claims are private on Sleeper, so only processed
  claims (COMPLETE / FAILED) are shown — check pending ones in the app.

ESPN and Yahoo are read in the dedicated Playwright profile (logged in once with
``python scripts/league_login.py``). Nothing is clicked or submitted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config  # noqa: E402
from src import fantasy_browser as fb  # noqa: E402
from src import waiver_claims as wc  # noqa: E402
from src import waiver_sites as ws  # noqa: E402

#: George's leagues.
MY_LEAGUES = ("mantis", "la_liga", "feetball")


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="all", choices=("all",) + MY_LEAGUES)
    ap.add_argument("--season", type=int, default=2026)
    fb.add_browser_args(ap)
    args = ap.parse_args(argv)
    with fb.open_browser(args) as browser:
        return _run(args, browser)


def _run(args: argparse.Namespace, browser: fb.FantasyBrowser) -> int:
    failed = 0
    for league in MY_LEAGUES if args.league == "all" else (args.league,):
        preset = config.LEAGUE_PRESETS[league]
        try:
            summary, records = ws.read_claims(league, preset, args.season, browser)
        except (LookupError, RuntimeError, OSError) as exc:
            failed += 1
            print(f"\n== {league} ({preset['platform']}) - UNAVAILABLE: {exc}")
            continue
        pending = sum(r.status == "PENDING" for r in records)
        print(f"\n== {league} - {summary} - {pending} pending")
        print(wc.render_records(records))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
