#!/usr/bin/env python3
"""Score the waiver skill's OWN recommendations against what happened.

    python scripts/backtest_recommendations.py --league mantis
    python scripts/backtest_recommendations.py --league la_liga --top-k 3

Every other audit check tests machinery. This one tests the advice: for each
week whose board was written before kickoff, it takes the players the board
ranks below starter level, picks the top few the way the report would, and
compares what they scored with what the whole tier scored. A shuffled ranking
is scored alongside as the control.

See ``src/recommendation_backtest.py`` for why each of those choices is the
way it is, and for why only 2026 weeks 2-7 are eligible.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, recommendation_backtest as rb  # noqa: E402


def _waiver_wire():
    """waiver_wire.py is a script, not a module; load it for last_week_actuals."""
    spec = importlib.util.spec_from_file_location(
        "waiver_wire", REPO_ROOT / "scripts" / "waiver_wire.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _schedule(season: int) -> pd.DataFrame:
    files = sorted(
        glob.glob(
            str(REPO_ROOT / f"data/bronze/schedules/season={season}/**/*.parquet"),
            recursive=True,
        )
    )
    return pd.read_parquet(files[-1]) if files else pd.DataFrame()


def _bye_teams(sched: pd.DataFrame, week: int) -> List[str]:
    reg = sched[sched["week"] <= 18]
    allt = set(reg["home_team"]) | set(reg["away_team"])
    wk = sched[sched["week"] == week]
    return sorted(allt - (set(wk["home_team"]) | set(wk["away_team"])))


def run(
    season: int, league: str, top_k: int, weeks: Optional[Sequence[int]] = None
) -> Dict[str, Any]:
    preset = config.our_league(league)
    scoring = config.SCORING_CONFIGS[preset["scoring_format"]]
    cutoffs = rb.starter_cutoffs(
        config.ROSTER_CONFIGS[preset["roster"]], int(preset.get("teams") or 12)
    )
    ww = _waiver_wire()
    sched = _schedule(season)
    rows: List[Dict[str, Any]] = []
    nulls: List[float] = []
    naive: List[float] = []
    skipped: List[str] = []

    for week in weeks or range(1, 19):
        kickoff = rb.first_kickoff(sched, week)
        if kickoff is None:
            continue
        path = rb.pre_kickoff_board(season, week, kickoff)
        if path is None:
            skipped.append(f"w{week}: no board written before kickoff")
            continue
        actuals = ww.last_week_actuals(season, week, scoring)
        if actuals.empty:
            skipped.append(f"w{week}: no actuals yet")
            continue
        tier = rb.waiver_tier(pd.read_parquet(path), cutoffs, _bye_teams(sched, week))
        tier = rb.attach_actuals(tier, actuals)
        tier = rb.attach_prior(tier, ww.last_week_actuals(season, week - 1, scoring))
        res = rb.week_lift(tier, top_k)
        if res is None:
            skipped.append(f"w{week}: tier smaller than top-{top_k}")
            continue
        res["week"] = week
        res["board"] = Path(path).name
        rows.append(res)
        nulls.append(rb.null_lift(tier, top_k))
        base = rb.week_lift(tier, top_k, by="prior_points")
        if base:
            naive.append(base["lift"])

    return {
        "rows": rows,
        "nulls": nulls,
        "skipped": skipped,
        "naive": naive,
        "summary": rb.summarise(rows, nulls, naive),
        "cutoffs": cutoffs,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--top-k", type=int, default=5, help="how many the board picks")
    ap.add_argument("--weeks", type=int, nargs="*")
    args = ap.parse_args(argv)

    out = run(args.season, args.league, args.top_k, args.weeks)
    s = out["summary"]

    print(
        f"=== recommendation backtest — {args.league} {args.season}, "
        f"top-{args.top_k} of the waiver tier ==="
    )
    print(
        "  tier = board rank below starter level, scored WITHIN position "
        f"({', '.join(f'{p}>{n}' for p, n in sorted(out['cutoffs'].items()))}); "
        "a player with no actuals row did not play and scores 0"
    )
    print()
    if not out["rows"]:
        print("  no eligible weeks")
    else:
        print(f"  {'wk':<4}{'tier':>6}{'lift':>8}   per position")
        for r in out["rows"]:
            by = "  ".join(f"{p} {v:+.1f}" for p, v in sorted(r["by_pos"].items()))
            print(f"  {r['week']:<4}{r['n_tier']:>6}{r['lift']:>+8.2f}   {by}")
    for note in out["skipped"]:
        print(f"  skipped {note}")

    print()
    if s.get("n_weeks"):
        print(f"  mean lift      {s['mean_lift']:+.2f} pts over the tier average")
        print(f"  weeks positive {s['weeks_positive']}/{s['n_weeks']}")
        print(
            f"  shuffled null  {s['null_lift']:+.2f}  (must be ~0 or the test is void)"
        )
        print(
            f"  naive baseline {s['naive_lift']:+.2f}"
            "  the same tier ranked by LAST week's points"
        )
        print(f"  edge over it   {s['edge_over_naive']:+.2f}")
        print(f"  MDE at n={s['n_weeks']}      {s['mde']:.2f} — the smallest lift this")
        print("                 sample could tell apart from zero")
    print()
    print(f"  VERDICT: {s['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
