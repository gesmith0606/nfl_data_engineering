"""EVT-05 audit — verify advisor news tools return non-empty per-team coverage.

Probes the two advisor tools that surface news content to the chat agent:
- ``getPlayerNews`` -> ``/api/news/feed`` (broad cross-week feed, limit=200)
- ``getTeamSentiment`` -> ``/api/news/team-events`` for the 2025 W17+W18 union

For each, counts unique team abbreviations. EVT-05 PASS requires:
- ``non_empty_teams_player_news >= EVT_05_PLAYER_GATE`` (default 20)
- ``non_empty_teams_team_sentiment >= EVT_05_TEAM_GATE`` (default 8 — see
  CONTEXT D-04 Amendment 2026-04-27, mirrors the EVT-04 rebaseline)

Default target is Railway production. ``--local`` is a dev-mode flag
that produces NON-SHIPPABLE JSON.

Sibling to ``scripts/audit_advisor_tools.py`` (per Plan 72-05 Task 2:
"extended OR sibling new script"). Kept small to avoid destabilising
the 700-line ``audit_advisor_tools.py`` during the v7.1 close-out.

Usage:
    # Default — probe Railway live:
    python scripts/audit_advisor_tools_evt05.py

    # Dev-mode (NON-SHIPPABLE):
    python scripts/audit_advisor_tools_evt05.py --local

    # Override JSON output:
    python scripts/audit_advisor_tools_evt05.py \\
        --json-out .planning/.../audit/advisor_tools_72.json

Exit 0 if both gates pass; exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://nfldataengineering-production.up.railway.app"
LOCAL_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 15.0

# Plan 72-05 EVT-05 gates. The team-sentiment gate was rebaselined 2026-04-27
# from 20 to 8 alongside EVT-04 — Phase 71's tighter Claude attribution
# (one team per article vs the rule-extractor's fuzzy multi-team broadcast)
# narrows team-sentiment coverage on the locked W17+W18 window. The
# player-news gate stays at 20 since /api/news/feed surfaces a broader
# cross-week feed and reliably produces 32 unique teams.
EVT_05_PLAYER_GATE = 20
EVT_05_TEAM_GATE = 8

DEFAULT_SEASON = 2025
DEFAULT_WEEKS = (17, 18)
DEFAULT_FEED_LIMIT = 200

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON_OUT = (
    _PROJECT_ROOT
    / ".planning"
    / "milestones"
    / "v7.1-phases"
    / "72-event-flag-expansion"
    / "audit"
    / "advisor_tools_72.json"
)


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------
def _probe_player_news(
    client: httpx.Client, base_url: str, season: int, limit: int
) -> Set[str]:
    """getPlayerNews -> /api/news/feed. Returns set of unique team abbreviations."""
    url = f"{base_url.rstrip('/')}/api/news/feed"
    try:
        resp = client.get(url, params={"season": season, "limit": limit})
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(f"/api/news/feed probe failed: {exc}") from exc
    if not isinstance(body, list):
        raise RuntimeError(
            f"/api/news/feed expected list (got {type(body).__name__})"
        )
    teams: Set[str] = set()
    for item in body:
        if not isinstance(item, dict):
            continue
        team = item.get("team") or item.get("team_abbr")
        if team:
            teams.add(str(team))
    return teams


def _probe_team_sentiment(
    client: httpx.Client, base_url: str, season: int, weeks: tuple
) -> Set[str]:
    """getTeamSentiment -> /api/news/team-events. Returns union of teams with
    any non-zero signal across the weeks specified."""
    url = f"{base_url.rstrip('/')}/api/news/team-events"
    union: Set[str] = set()
    for week in weeks:
        try:
            resp = client.get(url, params={"season": season, "week": week})
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(
                f"/api/news/team-events probe failed (week={week}): {exc}"
            ) from exc
        if not isinstance(body, list):
            raise RuntimeError(
                f"/api/news/team-events expected list "
                f"(week={week}, got {type(body).__name__})"
            )
        for item in body:
            if not isinstance(item, dict):
                continue
            total = (
                int(item.get("positive_event_count") or 0)
                + int(item.get("negative_event_count") or 0)
                + int(item.get("neutral_event_count") or 0)
                + int(item.get("coach_news_count") or 0)
                + int(item.get("team_news_count") or 0)
            )
            if total > 0:
                team = item.get("team")
                if team:
                    union.add(str(team))
    return union


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def _build_payload(
    *,
    base_url: str,
    season: int,
    weeks: tuple,
    feed_limit: int,
    player_teams: Set[str],
    team_teams: Set[str],
) -> Dict[str, Any]:
    player_pass = len(player_teams) >= EVT_05_PLAYER_GATE
    team_pass = len(team_teams) >= EVT_05_TEAM_GATE
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "season": season,
        "weeks": list(weeks),
        "feed_limit": feed_limit,
        "evt_05_gate_player_news": EVT_05_PLAYER_GATE,
        "evt_05_gate_team_sentiment": EVT_05_TEAM_GATE,
        "non_empty_teams_player_news": len(player_teams),
        "non_empty_teams_team_sentiment": len(team_teams),
        "evt_05_passed": player_pass and team_pass,
        "tool_results": {
            "getPlayerNews": {
                "endpoint": "/api/news/feed",
                "params": {"season": season, "limit": feed_limit},
                "unique_teams": sorted(player_teams),
                "team_count": len(player_teams),
                "gate": EVT_05_PLAYER_GATE,
                "passed": player_pass,
            },
            "getTeamSentiment": {
                "endpoint": "/api/news/team-events",
                "params": {"season": season, "weeks": list(weeks)},
                "unique_teams": sorted(team_teams),
                "team_count": len(team_teams),
                "gate": EVT_05_TEAM_GATE,
                "passed": team_pass,
            },
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EVT-05 audit — getPlayerNews + getTeamSentiment coverage gate"
    )
    parser.add_argument("--local", action="store_true",
                        help="Probe localhost (NON-SHIPPABLE — CONTEXT D-04 gate "
                             "requires Railway-live evidence).")
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT,
                        help=f"Output JSON path (default: {DEFAULT_JSON_OUT})")
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--weeks",
                        type=lambda s: tuple(int(p.strip()) for p in s.split(",")),
                        default=DEFAULT_WEEKS,
                        help="Comma list (default: 17,18)")
    parser.add_argument("--feed-limit", type=int, default=DEFAULT_FEED_LIMIT,
                        help=f"/api/news/feed limit (default: {DEFAULT_FEED_LIMIT})")
    parser.add_argument("--skip-write", action="store_true",
                        help="Probe without writing JSON.")
    return parser


def main(argv: List[str]) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.local:
        base_url = LOCAL_BASE_URL
        print(
            "WARNING: --local mode produces non-shippable JSON. "
            "CONTEXT D-04 ship gate requires Railway-live audit.",
            file=sys.stderr,
        )
    else:
        base_url = os.environ.get("RAILWAY_API_URL", DEFAULT_BASE_URL)

    api_key = os.environ.get("RAILWAY_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}

    print(f"Probing {base_url} for season={args.season} weeks={list(args.weeks)}")

    with httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        try:
            player_teams = _probe_player_news(
                client, base_url, args.season, args.feed_limit
            )
            team_teams = _probe_team_sentiment(
                client, base_url, args.season, tuple(args.weeks)
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    payload = _build_payload(
        base_url=base_url,
        season=args.season,
        weeks=tuple(args.weeks),
        feed_limit=args.feed_limit,
        player_teams=player_teams,
        team_teams=team_teams,
    )

    print(f"  getPlayerNews     teams: {len(player_teams)}/32 (gate >= {EVT_05_PLAYER_GATE})")
    print(f"  getTeamSentiment  teams: {len(team_teams)}/32 (gate >= {EVT_05_TEAM_GATE})")
    print(f"Verdict: {'PASS' if payload['evt_05_passed'] else 'FAIL'}")

    if not args.skip_write:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"Wrote {args.json_out}")

    return 0 if payload["evt_05_passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
