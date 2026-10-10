#!/usr/bin/env python3
"""One-time (and whenever a session dies) login for the waiver-claim profile.

    python scripts/league_login.py            # open ESPN + Yahoo, log in, press Enter
    python scripts/league_login.py --check    # headless: still logged in?

Opens the dedicated Playwright profile (``$FANTASY_BROWSER_PROFILE``, default
``~/.nfl-fantasy-browser``) in a visible Chrome with our ESPN and Yahoo team
pages. Log in by hand in that window (captchas included) — this script never
sees or types a password. Press Enter here when done; each league is then read
once (read-only) and reported OK / NOT LOGGED IN.

Sleeper (Mantis) is not opened: its claims stay manual (Terms §11.1).
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
from src import waiver_sites as ws  # noqa: E402

#: The leagues whose claims are filed through the profile.
BROWSER_LEAGUES = ("la_liga", "feetball")


def check_logins(browser: fb.FantasyBrowser, season: int) -> int:
    """Read each league once; returns how many are NOT logged in."""
    bad = 0
    for league in BROWSER_LEAGUES:
        preset = config.LEAGUE_PRESETS[league]
        try:
            summary, _ = ws.read_claims(league, preset, season, browser)
            print(f"  OK            {league}: {summary}")
        except (LookupError, RuntimeError, OSError) as exc:
            bad += 1
            print(f"  NOT LOGGED IN {league}: {exc}")
    return bad


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--check", action="store_true", help="headless status check only")
    ap.add_argument("--season", type=int, default=2026)
    fb.add_browser_args(ap)
    args = ap.parse_args(argv)
    if not args.check:
        args.headed = True

    with fb.open_browser(args) as browser:
        if not args.check:
            for league in BROWSER_LEAGUES:
                preset = config.LEAGUE_PRESETS[league]
                browser.page(
                    preset["platform"],
                    str(preset["league_id"]),
                    int(preset["my_team_id"]),
                )
            input(
                f"\nLog into ESPN and Yahoo in the browser window (profile "
                f"{args.profile}), then press Enter here... "
            )
            for page in browser.context.pages:
                page.reload(wait_until="domcontentloaded")
        print("\nLogin check:")
        return 1 if check_logins(browser, args.season) else 0


if __name__ == "__main__":
    sys.exit(main())
