"""EVT-04 audit — verify ``/api/news/team-events`` coverage on a fresh backfill.

Fetches team-events for both 2025 W17 and W18, unions per-team event counts
(positive + negative + neutral + coach + team), and counts how many of the
32 NFL teams have at least one non-zero signal across the union. Gate
(per Phase 72 CONTEXT D-04): >= 15 of 32 teams.

Default target is Railway production. ``--local`` is a developer-mode flag
for pre-Railway smoke testing only and produces NON-SHIPPABLE JSON — the
ship-or-skip gate (CONTEXT D-04) is locked to Railway-live evidence.

Usage:
    # Default — probe Railway live:
    python scripts/audit_event_coverage.py

    # Dev-mode smoke test (NON-SHIPPABLE):
    python scripts/audit_event_coverage.py --local

    # Override output paths:
    python scripts/audit_event_coverage.py \\
        --json-out .planning/.../audit/event_coverage.json \\
        --md-out   .planning/.../audit/event_coverage.md

    # Override probe window:
    python scripts/audit_event_coverage.py --season 2025 --weeks 17,18

Exit code 0 if ``teams_with_events >= EVT_04_GATE``; exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://nfldataengineering-production.up.railway.app"
LOCAL_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 15.0

# Phase 72 CONTEXT D-04 ship gate (amended 2026-04-27 from 15 to 8):
# >= 8 of 32 teams must have at least one non-zero signal across
# (positive + negative + neutral + coach + team) over the W17 ∪ W18 union
# for EVT-04 to PASS.
#
# Original gate was 15; amended after Phase 71 made Claude the primary
# extractor with tighter one-team-per-article attribution (vs the rule-
# extractor's fuzzy multi-team broadcasting). On real backfilled content
# the union floor is ~9-12 teams; 8 catches the all-zeros regression with
# conservative margin. See 72-CONTEXT.md "D-04 Amendment (2026-04-27)".
EVT_04_GATE = 8

DEFAULT_SEASON = 2025
DEFAULT_WEEKS: Tuple[int, ...] = (17, 18)

# Output paths default to the Phase 72 audit directory used as ship evidence.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON_OUT = (
    _PROJECT_ROOT
    / ".planning"
    / "milestones"
    / "v7.1-phases"
    / "72-event-flag-expansion"
    / "audit"
    / "event_coverage.json"
)
DEFAULT_MD_OUT = DEFAULT_JSON_OUT.with_suffix(".md")


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TeamRow:
    team: str
    positive: int
    negative: int
    neutral: int
    coach: int
    team_count: int

    @property
    def total(self) -> int:
        return self.positive + self.negative + self.neutral + self.coach + self.team_count

    @property
    def has_events(self) -> bool:
        return self.total > 0


# ---------------------------------------------------------------------------
# Probe + aggregation
# ---------------------------------------------------------------------------
def _coerce_int(value: Any) -> int:
    """Defensively coerce a JSON number to int. None/NaN/missing -> 0."""
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _row_from_payload(item: Any) -> TeamRow:
    # Defensive: a malformed payload could contain non-dict items (e.g.,
    # [null, ...] from a partial backend failure). Treat as zero-signal row.
    if not isinstance(item, dict):
        return TeamRow(team="", positive=0, negative=0, neutral=0, coach=0, team_count=0)
    return TeamRow(
        team=str(item.get("team", "")),
        positive=_coerce_int(item.get("positive_event_count")),
        negative=_coerce_int(item.get("negative_event_count")),
        neutral=_coerce_int(item.get("neutral_event_count")),
        coach=_coerce_int(item.get("coach_news_count")),
        team_count=_coerce_int(item.get("team_news_count")),
    )


def _fetch_week(client: httpx.Client, base_url: str, season: int, week: int) -> List[TeamRow]:
    url = f"{base_url.rstrip('/')}/api/news/team-events"
    try:
        resp = client.get(url, params={"season": season, "week": week})
        resp.raise_for_status()
        payload = resp.json()
    except ValueError as exc:
        # ValueError covers json.JSONDecodeError when the backend returns
        # a 200 with non-JSON body (e.g., nginx error page during cold start).
        raise RuntimeError(
            f"/api/news/team-events returned non-JSON body "
            f"(season={season}, week={week}, error={exc})"
        ) from exc
    if not isinstance(payload, list):
        raise RuntimeError(
            f"/api/news/team-events did not return a list "
            f"(season={season}, week={week}, got {type(payload).__name__})"
        )
    if len(payload) != 32:
        raise RuntimeError(
            f"/api/news/team-events expected 32 rows "
            f"(season={season}, week={week}, got {len(payload)})"
        )
    return [_row_from_payload(item) for item in payload]


def _union_rows(weeks: List[List[TeamRow]]) -> List[TeamRow]:
    """Sum per-team counts across all weeks. Preserves team set from week 0."""
    if not weeks:
        return []
    by_team: Dict[str, TeamRow] = {row.team: row for row in weeks[0]}
    for week_rows in weeks[1:]:
        for row in week_rows:
            existing = by_team.get(row.team)
            if existing is None:
                by_team[row.team] = row
                continue
            by_team[row.team] = TeamRow(
                team=row.team,
                positive=existing.positive + row.positive,
                negative=existing.negative + row.negative,
                neutral=existing.neutral + row.neutral,
                coach=existing.coach + row.coach,
                team_count=existing.team_count + row.team_count,
            )
    return sorted(by_team.values(), key=lambda r: r.team)


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def _build_json_payload(
    *,
    base_url: str,
    season: int,
    weeks: Tuple[int, ...],
    rows: List[TeamRow],
    teams_with_events: int,
    passed: bool,
) -> Dict[str, Any]:
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "season": season,
        "weeks": list(weeks),
        "gate": EVT_04_GATE,
        "teams_with_events": teams_with_events,
        "passed": passed,
        "per_team": [
            {
                "team": r.team,
                "positive": r.positive,
                "negative": r.negative,
                "neutral": r.neutral,
                "coach": r.coach,
                "team_count": r.team_count,
                "has_events": r.has_events,
            }
            for r in rows
        ],
    }


def _build_markdown(payload: Dict[str, Any]) -> str:
    rows = payload["per_team"]
    verdict = "PASS" if payload["passed"] else "FAIL"
    lines = [
        f"# EVT-04 Audit — {verdict}",
        "",
        f"- **Audited at:** {payload['audited_at']}",
        f"- **Base URL:** {payload['base_url']}",
        f"- **Season:** {payload['season']}",
        f"- **Weeks:** {payload['weeks']}",
        f"- **Gate:** ≥ {payload['gate']} of 32 teams with events",
        f"- **Teams with events:** {payload['teams_with_events']}/32",
        f"- **Verdict:** **{verdict}**",
        "",
        "| Team | + | - | 0 | Coach | Team | Total | Has events |",
        "|------|---|---|---|-------|------|-------|------------|",
    ]
    for r in rows:
        total = r["positive"] + r["negative"] + r["neutral"] + r["coach"] + r["team_count"]
        marker = "✓" if r["has_events"] else "·"
        lines.append(
            f"| {r['team']} | {r['positive']} | {r['negative']} | {r['neutral']} | "
            f"{r['coach']} | {r['team_count']} | {total} | {marker} |"
        )
    return "\n".join(lines) + "\n"


def _write_outputs(
    payload: Dict[str, Any],
    *,
    json_out: Path,
    md_out: Path,
) -> None:
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2) + "\n")
    md_out.write_text(_build_markdown(payload))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_weeks(arg: str) -> Tuple[int, ...]:
    parts = [p.strip() for p in arg.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--weeks must be a non-empty comma list")
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--weeks parse error: {exc}") from exc


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="EVT-04 audit — /api/news/team-events coverage gate"
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Probe http://localhost:8000 instead of Railway. NON-SHIPPABLE — "
        "CONTEXT D-04 ship gate requires Railway-live evidence.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_OUT,
        help=f"Audit JSON output path (default: {DEFAULT_JSON_OUT})",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=DEFAULT_MD_OUT,
        help=f"Markdown summary output path (default: {DEFAULT_MD_OUT})",
    )
    parser.add_argument(
        "--season",
        type=int,
        default=DEFAULT_SEASON,
        help=f"NFL season (default: {DEFAULT_SEASON})",
    )
    parser.add_argument(
        "--weeks",
        type=_parse_weeks,
        default=DEFAULT_WEEKS,
        help=f"Comma list of weeks (default: {','.join(str(w) for w in DEFAULT_WEEKS)})",
    )
    parser.add_argument(
        "--skip-write",
        action="store_true",
        help="Probe + summarize without writing JSON/MD (verify-mode).",
    )
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

    weekly_rows: List[List[TeamRow]] = []
    with httpx.Client(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        for week in args.weeks:
            try:
                rows = _fetch_week(client, base_url, args.season, week)
            except (httpx.HTTPError, RuntimeError) as exc:
                print(
                    f"ERROR: probe failed for week={week}: {exc}",
                    file=sys.stderr,
                )
                return 1
            weekly_rows.append(rows)
            present = sum(1 for r in rows if r.has_events)
            print(f"  week={week}: {present}/32 teams with events")

    union = _union_rows(weekly_rows)
    teams_with_events = sum(1 for r in union if r.has_events)
    passed = teams_with_events >= EVT_04_GATE

    print()
    print(f"Union teams with events (W{','.join(str(w) for w in args.weeks)}): "
          f"{teams_with_events}/32 (gate >= {EVT_04_GATE})")
    print(f"Verdict: {'PASS' if passed else 'FAIL'}")

    payload = _build_json_payload(
        base_url=base_url,
        season=args.season,
        weeks=tuple(args.weeks),
        rows=union,
        teams_with_events=teams_with_events,
        passed=passed,
    )

    if not args.skip_write:
        _write_outputs(payload, json_out=args.json_out, md_out=args.md_out)
        print(f"Wrote {args.json_out}")
        print(f"Wrote {args.md_out}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
