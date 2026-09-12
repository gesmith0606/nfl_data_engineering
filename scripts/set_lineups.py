#!/usr/bin/env python3
"""Weekly lineup setter: roster -> two projection sources -> league scoring -> deltas.

    python scripts/set_lineups.py --league mantis
    python scripts/set_lineups.py --league mantis --week 2 --threshold 2.5

Pulls the Sleeper roster, roster_positions and scoring_settings for a league
preset, scores OUR projections and Sleeper's weekly projections under those exact
settings (TE premium, 6-pt pass TD, first downs on the Sleeper side), and prints
only the deltas vs the lineup currently set. A swap is recommended only when both
sources agree by the threshold (default 3.0 pts); otherwise it is a coin flip.

OURS = the latest weekly Gold parquet for the week. When that board is thin
(< 150 skill rows — e.g. Week 1 of a new season, where the weekly engine has no
current-season usage yet) it falls back to preseason pace (season stats / 17) and
says so. ``*_derived`` boards are never read (see LINEUP_TOOL_ENHANCEMENT.md).

Sleeper only for now; ESPN/Yahoo need a roster reader (tracked in the doc).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.league_scoring import unmodeled_offense_keys  # noqa: E402
from src.lineup_setter import (  # noqa: E402
    ET,
    MIN_WEEKLY_ROWS,
    SKILL_POSITIONS,
    build_rows,
    kickoffs_for_week,
    lineup_deltas,
    ours_by_sleeper_id,
    preseason_to_weekly,
    render,
    score_ours,
    weekly_gold_to_stats,
)
from src.sleeper_player_map import load_sleeper_players  # noqa: E402

GOLD = REPO_ROOT / "data" / "gold" / "projections"
SCHEDULES = REPO_ROOT / "data" / "bronze" / "schedules"


def _latest(pattern: str, exclude: str = "derived") -> Optional[Path]:
    files = [f for f in glob.glob(pattern) if exclude not in os.path.basename(f)]
    return Path(max(files, key=os.path.getmtime)) if files else None


def _default_week(season_hint: Optional[int]) -> Tuple[int, int]:
    spec = importlib.util.spec_from_file_location(
        "resolve_pipeline_week", REPO_ROOT / "scripts" / "resolve_pipeline_week.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    season, week, _ = mod.resolve_target_week(dt.date.today())
    return (season_hint or season), week


def load_ours(season: int, week: int) -> Tuple[pd.DataFrame, str]:
    """Weekly Gold if healthy, else preseason pace. Returns (stat rows, label)."""
    weekly = _latest(
        str(GOLD / f"season={season}" / f"week={week}" / "projections_*.parquet")
    )
    if weekly is not None:
        df = pd.read_parquet(weekly)
        skill = (
            df[df["position"].isin(SKILL_POSITIONS)] if "position" in df.columns else df
        )
        if len(skill) >= MIN_WEEKLY_ROWS:
            age_h = (
                dt.datetime.now() - dt.datetime.fromtimestamp(weekly.stat().st_mtime)
            ).total_seconds() / 3600
            return (
                weekly_gold_to_stats(df),
                f"weekly Gold {weekly.name} ({age_h:.0f}h old)",
            )
        print(
            f"WARN: weekly board {weekly.name} has only {len(skill)} skill rows (< {MIN_WEEKLY_ROWS}); "
            "falling back to preseason pace"
        )
    pre = _latest(
        str(GOLD / "preseason" / f"season={season}" / "season_proj_*.parquet")
    )
    if pre is None:
        sys.exit(
            f"No usable projections for {season} week {week}. Generate one:\n"
            f"  python scripts/generate_projections.py --week {week} --season {season} --scoring ppr"
        )
    return (
        preseason_to_weekly(pd.read_parquet(pre)),
        f"preseason pace {pre.name} (season/17)",
    )


def load_sleeper_projections(season: int, week: int) -> Dict[str, Dict[str, Any]]:
    """Live Sleeper weekly projections keyed by sleeper player id."""
    url = config.SENTIMENT_CONFIG["sleeper_projections_url"].format(
        season=season, week=week
    )
    raw = sleeper_http.fetch_sleeper_json(url)
    if not raw:
        sys.exit(
            f"Sleeper projections unavailable ({url}) — refusing to recommend on one source."
        )
    if isinstance(
        raw, list
    ):  # defensive: some endpoints return a list of {player_id, stats}
        return {str(x.get("player_id")): (x.get("stats") or x) for x in raw}
    return {
        str(k): (v.get("stats") or v) for k, v in raw.items() if isinstance(v, dict)
    }


def find_my_roster(league_id: str, username: str) -> Dict[str, Any]:
    users = sleeper_http.get_league_users(league_id)
    me = next(
        (
            u
            for u in users
            if str(u.get("display_name", "")).lower() == username.lower()
        ),
        None,
    )
    if me is None:
        sys.exit(
            f"User '{username}' not in league {league_id}: {[u.get('display_name') for u in users]}"
        )
    rosters = sleeper_http.get_league_rosters(league_id)
    mine = next((r for r in rosters if r.get("owner_id") == me["user_id"]), None)
    if mine is None:
        sys.exit(f"No roster owned by {username} in league {league_id}")
    return mine


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key (e.g. mantis)")
    ap.add_argument(
        "--week", type=int, help="NFL week (default: upcoming week per schedule)"
    )
    ap.add_argument("--season", type=int, help="Season (default: current)")
    ap.add_argument("--user", help="Sleeper display name (default: preset my_user)")
    ap.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Min margin on BOTH sources for a SWAP",
    )
    args = ap.parse_args(argv)

    preset = config.LEAGUE_PRESETS.get(args.league)
    if preset is None:
        sys.exit(
            f"Unknown league '{args.league}'. Presets: {sorted(config.LEAGUE_PRESETS)}"
        )
    if preset.get("platform") != "sleeper":
        sys.exit(
            f"{args.league} is on {preset.get('platform')}: only Sleeper rosters are supported yet."
        )
    username = args.user or preset.get("my_user")
    if not username:
        sys.exit("Pass --user <Sleeper display name> (preset has no my_user).")

    if args.season and args.week:
        season, week = args.season, args.week
    else:
        season, week = _default_week(args.season)
        week = args.week or week
    league_id = str(preset["league_id"])

    league = sleeper_http.get_league(league_id)
    if not league:
        sys.exit(f"Sleeper league {league_id} unavailable.")
    roster_positions = league.get("roster_positions") or []
    scoring = league.get("scoring_settings") or {}
    mine = find_my_roster(league_id, username)
    registry = load_sleeper_players()

    ours_df, ours_label = load_ours(season, week)
    ours = ours_by_sleeper_id(score_ours(ours_df, scoring), registry)
    sleeper_proj = load_sleeper_projections(season, week)

    sched_file = _latest(
        str(SCHEDULES / f"season={season}" / "*.parquet"), exclude="\0"
    )
    kickoffs = (
        kickoffs_for_week(pd.read_parquet(sched_file), week) if sched_file else {}
    )
    if not kickoffs:
        print(f"WARN: no schedule for {season} week {week}; lock/bye flags disabled")

    rows = build_rows(
        player_ids=[
            p for p in mine.get("players") or [] if p not in (mine.get("taxi") or [])
        ],
        starters=mine.get("starters") or [],
        roster_positions=roster_positions,
        registry=registry,
        ours=ours,
        sleeper_proj=sleeper_proj,
        scoring_settings=scoring,
        kickoffs=kickoffs,
        now=dt.datetime.now(tz=ET),
    )
    deltas = lineup_deltas(rows, threshold=args.threshold)
    header = (
        f"{league.get('name', league_id)} — {username} — {season} week {week} "
        f"(threshold {args.threshold:.1f} on both sources)"
    )
    print(render(rows, deltas, header, ours_label))
    gaps = unmodeled_offense_keys(scoring)
    if gaps:
        print(f"\n  note: OURS cannot model {', '.join(gaps)} (Sleeper side does)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
