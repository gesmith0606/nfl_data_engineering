#!/usr/bin/env python3
"""Resolve the (season, week) the weekly pipeline should target.

The Tuesday cron runs after Monday Night Football, so the week it should
INGEST actuals for has just finished and the week it should PROJECT is the
*upcoming* one.  ``target week`` therefore means "the earliest regular-season
week that still has a game on or after today", read from the committed
schedule parquet (``data/bronze/schedules/season=YYYY/``).

Why not a calendar rule: the previous inline logic anchored Week 1 to "the
Thursday on or after Sep 5".  On 2026-09-08 (the Tuesday before kickoff) that
resolved to season 2025 week 18, so no 2026 Week 1 projections were ever
produced, and every later Tuesday would have projected the week that had just
been played.  The calendar rule survives only as a fallback for when no
schedule parquet exists at all.

Priority order (unchanged from the workflow):
  1. ``INPUT_SEASON`` + ``INPUT_WEEK`` (workflow_dispatch inputs)
  2. ``PIPELINE_WEEK_OVERRIDE`` repository variable, e.g. ``2024:10``
  3. Schedule-driven upcoming week
  4. Calendar fallback

Prints ``season=`` / ``week=`` lines and appends them to ``$GITHUB_OUTPUT``
when set.
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEDULES_ROOT = REPO_ROOT / "data" / "bronze" / "schedules"
MAX_WEEK = 18


def load_schedule(season: int, root: Path = SCHEDULES_ROOT) -> Optional[pd.DataFrame]:
    """Return the latest schedule parquet for *season*, or None if absent."""
    files = sorted(glob.glob(str(root / f"season={season}" / "schedules_*.parquet")))
    if not files:
        return None
    return pd.read_parquet(files[-1])


def upcoming_week(schedule: pd.DataFrame, today: dt.date) -> Optional[int]:
    """Earliest REG week with a game on/after *today*; None if the season is over.

    A week stays "upcoming" until its last game has been played, so a Tuesday
    run lands on the week whose games start Thursday.
    """
    df = schedule
    if "game_type" in df.columns:
        df = df[df["game_type"] == "REG"]
    if df.empty:
        return None
    gameday = pd.to_datetime(df["gameday"], errors="coerce").dt.date
    week_end = (
        df.assign(_gd=gameday).dropna(subset=["_gd"]).groupby("week")["_gd"].max()
    )
    pending = week_end[week_end >= today]
    if pending.empty:
        return None
    return int(pending.index.min())


def calendar_fallback(today: dt.date) -> Tuple[int, int]:
    """Legacy rule: Week 1 anchored to the Thursday on/after Sep 5. Fallback only."""

    def week1_thursday(yr: int) -> dt.date:
        sep5 = dt.date(yr, 9, 5)
        return sep5 + dt.timedelta(days=(3 - sep5.weekday()) % 7)

    season = today.year
    anchor = week1_thursday(season)
    if today < anchor:
        season -= 1
        anchor = week1_thursday(season)
    week = (today - anchor).days // 7 + 1
    return season, max(1, min(week, MAX_WEEK))


def resolve_target_week(
    today: Optional[dt.date] = None, root: Path = SCHEDULES_ROOT
) -> Tuple[int, int, str]:
    """Return ``(season, week, source)`` for the pipeline to target.

    Tries this year's schedule, then last year's.  A season whose games are
    all played resolves to its final regular-season week only when no later
    season's schedule exists yet (the off-season).
    """
    today = today or dt.date.today()
    finished: Optional[Tuple[int, int]] = None
    for season in (today.year, today.year - 1):
        sched = load_schedule(season, root)
        if sched is None or sched.empty:
            continue
        week = upcoming_week(sched, today)
        if week is not None:
            return season, min(week, MAX_WEEK), "schedule"
        if finished is None:
            reg = (
                sched[sched["game_type"] == "REG"]
                if "game_type" in sched.columns
                else sched
            )
            finished = (season, min(int(reg["week"].max()), MAX_WEEK))
    if finished is not None:
        return finished[0], finished[1], "schedule-final"
    season, week = calendar_fallback(today)
    return season, week, "calendar"


def main() -> int:
    input_season = os.environ.get("INPUT_SEASON", "").strip()
    input_week = os.environ.get("INPUT_WEEK", "").strip()
    override = os.environ.get("PIPELINE_WEEK_OVERRIDE", "").strip()

    if input_season and input_week:
        season, week = int(input_season), int(input_week)
        print(f"Using workflow_dispatch inputs: season={season} week={week}")
    elif override and ":" in override:
        s, w = override.split(":", 1)
        season, week = int(s.strip()), int(w.strip())
        print(f"Using PIPELINE_WEEK_OVERRIDE: season={season} week={week}")
    else:
        today = dt.date.today()
        season, week, source = resolve_target_week(today)
        print(f"Auto-computed ({source}): today={today} season={season} week={week}")
        if source == "calendar":
            print(
                "::warning::no schedule parquet found — fell back to the calendar rule"
            )

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"season={season}\nweek={week}\n")
    print(f"season={season}")
    print(f"week={week}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
