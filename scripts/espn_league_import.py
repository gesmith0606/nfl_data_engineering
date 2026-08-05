#!/usr/bin/env python3
"""
ESPN league import CLI — full team import via session cookies.

Pulls league settings, teams, rosters, and completed draft results from
ESPN's fantasy v3 API using the ESPN_S2 / ESPN_SWID cookies in ``.env``
(the same mechanism the Fantasy Footballers Chrome extension uses).
Public leagues need no cookies at all.

Usage:
    python scripts/espn_league_import.py --league-id 12345678
    python scripts/espn_league_import.py --league-id 12345678 --season 2026
    python scripts/espn_league_import.py --league-id 12345678 --my-team
    python scripts/espn_league_import.py --league-id 12345678 --draft
    python scripts/espn_league_import.py --league-id 12345678 --out league.json

Cookie setup (once per season — espn_s2 lives ~1 year):
    1. Log in at fantasy.espn.com
    2. DevTools > Application > Cookies > https://fantasy.espn.com
    3. Copy espn_s2 -> ESPN_S2=...  and SWID -> ESPN_SWID={...}  into .env
"""

import argparse
import json
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.espn_league import (  # noqa: E402
    cookies_from_env,
    extract_draft_picks,
    extract_league_info,
    extract_rosters,
    extract_teams,
    fetch_league,
    find_my_team_id,
)

DIVIDER = "=" * 70


def main() -> int:
    """Entry point for the ESPN league import CLI."""
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Import an ESPN fantasy league (teams, rosters, draft)."
    )
    parser.add_argument("--league-id", type=int, required=True, help="ESPN league id")
    parser.add_argument("--season", type=int, default=2026, help="Season year")
    parser.add_argument(
        "--my-team",
        action="store_true",
        help="Show only the roster owned by your ESPN_SWID account",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Show completed draft results (post-draft only)",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        help="Also write the raw league JSON payload to this path",
    )
    args = parser.parse_args()

    cookies = cookies_from_env()
    print(
        f"Fetching ESPN league {args.league_id} (season {args.season}) "
        f"[auth: {'cookies' if cookies else 'none / public'}]..."
    )
    try:
        payload = fetch_league(args.league_id, args.season, cookies=cookies)
    except (PermissionError, LookupError) as exc:
        print(f"ERROR: {exc}")
        return 1

    info = extract_league_info(payload)
    print(DIVIDER)
    print(f"  {info['name']}  ({info['size']} teams, season {info['season']})")
    ppr = info["points_per_reception"]
    print(
        f"  Scoring: {info['scoring_type']}"
        + (f" | {ppr}/reception" if ppr is not None else "")
        + f" | draft {'complete' if info['draft_complete'] else 'NOT held yet'}"
    )
    print(DIVIDER)

    teams = extract_teams(payload)
    rosters = extract_rosters(payload)

    if args.my_team:
        swid = os.environ.get("ESPN_SWID", "")
        team_id = find_my_team_id(payload, swid)
        if team_id is None:
            print(
                "Could not match ESPN_SWID to a team in this league "
                "(is the cookie from the right ESPN account?)."
            )
            return 1
        teams = teams[teams["team_id"] == team_id]
        rosters = rosters[rosters["team_id"] == team_id]

    for _, team in teams.iterrows():
        owner = f" — {team['owner_name']}" if team["owner_name"] else ""
        print(
            f"\n{team['team_name']} ({team['abbrev']}){owner}  "
            f"[{team['wins']}-{team['losses']}]"
        )
        team_roster = rosters[rosters["team_id"] == team["team_id"]]
        if team_roster.empty:
            print("  (empty roster)")
            continue
        for _, p in team_roster.sort_values(
            ["is_starter", "position"], ascending=[False, True]
        ).iterrows():
            status = (
                f"  [{p['injury_status']}]"
                if p["injury_status"] not in ("", "ACTIVE")
                else ""
            )
            print(
                f"  {p['lineup_slot']:>5}  {p['position']:<3} "
                f"{p['player_name']:<28} {p['pro_team']:<4}{status}"
            )

    if args.draft:
        picks = extract_draft_picks(payload)
        print(f"\nDraft results: {len(picks)} picks")
        for pick in picks:
            print(
                f"  {pick.pick_no:>3}. R{pick.round:<2} "
                f"{pick.full_name:<28} {pick.position:<3} {pick.team:<4} "
                f"-> team {pick.roster_id}"
            )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        print(f"\nRaw payload saved -> {args.out}")

    print(
        f"\nImported {rosters['team_id'].nunique() if not rosters.empty else 0}"
        f" roster(s), {len(rosters)} players."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
