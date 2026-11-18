#!/usr/bin/env python3
"""Does a ranking change raise what the listed names go on to score?

    python scripts/backtest_ranking.py --league mantis \\
        --extra-root "<checkout holding the newest boards, bronze, sentiment>"

Every variant lists the top six per position (the shape of today's report, so
the position mix never moves) and is scored by the mean points those names
scored over the following four weeks. Weeks 2-6 are the fit window; weeks 7 and
9 are held out and never used to choose anything. A variant is *kept* only if
it beats the baseline in both. n is printed beside every number: 120 names in
the fit window, 48 held out, so differences under about a point are noise.

Variants:

* ``tool_blend``      today's ranking: mean of our projection and Sleeper's.
* ``sleeper_only``    the consensus alone.
* ``consensus_2x``    consensus as the base; ours averaged in only within 2x.
* ``bye_aware``       weekly points x games played in the window; a name idle
                      this week uses Sleeper's number for next week.
* ``+ snap_jump``     role-change boost: offense-snap share up 15+ points on
                      the week before and at least 30%.
* ``+ usage_boost``   the week's sentiment flag, from the last file written
                      before Tuesday evening.
* ``+ dyn``           dynasty value in points. **Look-ahead**: FantasyCalc is
                      archived only from 2026-W43, so past weeks use TODAY's
                      value, which already contains the weeks that followed.
                      Shown to size the trade-off, never as evidence.

What cannot be tested here, and why: expected points minus actual
(ffopportunity ends in 2025), Sleeper trending adds (only the live endpoint
exists; ``data/waivers/reports`` records them from now on), and "the starter
ahead is Out" (depth charts are archived on a handful of days and the injury
report for a week is not out by Tuesday).
"""

from __future__ import annotations

import argparse
import glob
import os
import statistics
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import league_context  # noqa: E402
from src import waiver_rank as wr  # noqa: E402
from src.lineup_setter import (  # noqa: E402
    SKILL_POSITIONS,
    score_sleeper_stats,
    sleeper_to_gsis,
)  # noqa: E402
from src.sleeper_player_map import normalize_name  # noqa: E402
from src.waiver_replay import Replay, load_replay  # noqa: E402

FIT = [2, 3, 4, 5, 6]
HELD_OUT = [7, 9]
K = 6
ALIAS = {"LA": "LAR", "JAC": "JAX", "WSH": "WAS"}


def _snaps(roots: Sequence[Path], week: int, season: int) -> Dict[str, float]:
    files = sorted(
        f
        for r in roots
        for f in glob.glob(
            str(r / f"data/bronze/players/snaps/season={season}/week={week}/*.parquet")
        )
    )
    if not files:
        return {}
    d = pd.read_parquet(sorted(files, key=os.path.basename)[-1])
    return {
        normalize_name(str(n)): float(v)
        for n, v in zip(d["player"], d["offense_pct"])
        if pd.notna(v)
    }


def _flags(rp: Replay, week: int, season: int) -> Dict[str, Dict[str, bool]]:
    """Sentiment flags from the last file written before Tuesday evening."""
    cutoff = pd.Timestamp(
        rp.week1_start + (week - 1) * 7 * 86_400_000 + 22 * 3_600_000, unit="ms"
    )
    use: Optional[str] = None
    for r in rp.roots:
        for f in sorted(
            glob.glob(
                str(
                    r / f"data/gold/sentiment/season={season}/week={week:02d}/*.parquet"
                )
            )
        ):
            stamp = pd.to_datetime(
                os.path.basename(f).split("_", 2)[2].split(".")[0],
                format="%Y%m%d_%H%M%S",
            )
            if stamp <= cutoff:
                use = f
    if not use:
        return {}
    d = pd.read_parquet(use)
    return {
        str(r.player_id): {
            "boost": bool(r.is_usage_boost),
            "drop": bool(r.is_usage_drop),
        }
        for r in d.itertuples(index=False)
    }


def attach_features(
    rp: Replay, weeks: Sequence[int], dyn: Dict[str, Any]
) -> Dict[int, List[Dict[str, Any]]]:
    reg = rp.data["registry"]
    gsis = sleeper_to_gsis(reg, rp.ctx["gsis_map"])
    plays = {}
    for w in range(1, 19):
        g = rp.sched[rp.sched["week"] == w]
        plays[w] = {ALIAS.get(t, t) for t in set(g["home_team"]) | set(g["away_team"])}
    pools: Dict[int, List[Dict[str, Any]]] = {}
    for w in weeks:
        pool = rp.pool(w)
        if pool is None:
            continue
        season = rp.season
        s1 = _snaps(rp.roots, w - 1, season)
        s2 = _snaps(rp.roots, w - 2, season)
        flags = _flags(rp, w, season)
        for r in pool:
            team = ALIAS.get(
                (reg.get(r["sid"]) or {}).get("team") or "",
                (reg.get(r["sid"]) or {}).get("team"),
            )
            r["team"] = team
            r["games"] = wr.games_in_window(team, w, plays)
            idle = bool(team) and team not in plays.get(w, ())
            nxt = rp.data["proj"].get(w + 1, {}).get(r["sid"]) or {}
            r["weekly"] = (
                (score_sleeper_stats(nxt, rp.scoring, r["pos"]) if nxt else 0.0)
                if idle
                else r["blend"]
            )
            n = normalize_name(r["name"])
            now, prev = s1.get(n), s2.get(n)
            r["snap"] = None if now is None else now * 100
            r["snap_delta"] = (
                None
                if now is None or prev is None
                else (now - (prev if prev is not None else now)) * 100
            )
            r["flags"] = flags.get(gsis.get(r["sid"], ""), {})
            r["dyn"] = (dyn.get(r["sid"]) or {}).get("value", 0)
        pools[w] = pool
    return pools


Key = Callable[[Dict[str, Any]], float]


def variants() -> Dict[str, Callable[[], Key]]:
    cons = lambda r: wr.consensus(r["ours"], r["slpr"])[0]  # noqa: E731
    snap = (
        lambda r: r["snap_delta"] is not None
        and r["snap_delta"] >= 15
        and (r["snap"] or 0) >= 30
    )  # noqa: E731
    out: Dict[str, Callable[[], Key]] = {
        "tool_blend": lambda: lambda r: -r["blend"],
        "sleeper_only": lambda: lambda r: -(r["slpr"] or 0.0),
        "consensus_2x": lambda: lambda r: -cons(r),
        "bye_aware (blend)": lambda: lambda r: -(r["weekly"] * r["games"]),
        "bye_aware (consensus)": lambda: lambda r: -(cons(r) * r["games"]),
    }
    for b in (2, 4):
        out[f"blend + snap_jump +{b}"] = lambda b=b: lambda r: -(
            r["blend"] + (b if snap(r) else 0)
        )
        out[f"blend + usage_boost +{b}"] = lambda b=b: lambda r: -(
            r["blend"] + (b if r["flags"].get("boost") else 0)
        )
    for kd in (0.004, 0.01):
        out[f"blend + dyn {kd} (LOOK-AHEAD)"] = lambda kd=kd: lambda r: -(
            r["blend"] + kd * r["dyn"]
        )
    return out


def mean_p4(
    pools: Dict[int, List[Dict[str, Any]]], weeks: Sequence[int], key: Key
) -> tuple:
    vals: List[float] = []
    for w in weeks:
        for pos in SKILL_POSITIONS:
            rs = sorted((r for r in pools.get(w, []) if r["pos"] == pos), key=key)[:K]
            vals += [r["p4"] for r in rs]
    return (statistics.mean(vals) if vals else float("nan")), len(vals)


def run(args: argparse.Namespace) -> int:
    rp = load_replay(
        args.league,
        args.season,
        args.extra_root,
        args.last_week,
        args.cache,
        args.refresh,
    )
    dyn = league_context.fetch_dynasty_values(num_qbs=2, num_teams=10, ppr=1.0)
    pools = attach_features(rp, FIT + HELD_OUT, dyn)
    base = variants()["tool_blend"]()
    b_fit, n_fit = mean_p4(pools, FIT, base)
    b_ho, n_ho = mean_p4(pools, HELD_OUT, base)
    print(
        f"=== ranking backtest — {args.league} {args.season}: top {K} per position, "
        "mean points over the next 4 weeks ==="
    )
    print(
        f"fit weeks {FIT} (n={n_fit} names)   held-out weeks {HELD_OUT} "
        f"(n={n_ho} names; windows clipped at week {rp.last_week})\n"
    )
    print(
        f"  {'variant':<34}{'fit':>8}{'vs base':>9}{'held-out':>10}{'vs base':>9}  verdict"
    )
    for name, mk in variants().items():
        key = mk()
        f, _ = mean_p4(pools, FIT, key)
        h, _ = mean_p4(pools, HELD_OUT, key)
        kept = f > b_fit and h > b_ho and "LOOK-AHEAD" not in name
        note = (
            "KEEP"
            if kept and name != "tool_blend"
            else ("look-ahead, not evidence" if "LOOK-AHEAD" in name else "")
        )
        print(
            f"  {name:<34}{f:>8.2f}{f - b_fit:>+9.2f}{h:>10.2f}{h - b_ho:>+9.2f}  {note}"
        )
    hs, _ = mean_p4(pools, FIT, lambda r: -r["p4"])
    hh, _ = mean_p4(pools, HELD_OUT, lambda r: -r["p4"])
    print(
        f"  {'hindsight (ceiling)':<34}{hs:>8.2f}{hs - b_fit:>+9.2f}{hh:>10.2f}{hh - b_ho:>+9.2f}"
    )
    print(
        "\n  role-change flags with usable point-in-time data: snap_jump, usage_boost; "
        "usage flags exist for "
        f"{sum(1 for w in pools for r in pools[w] if r['flags'])} name-weeks in total"
    )
    for name in args.track:
        old, new = {}, {}
        for w, pool in sorted(pools.items()):
            me = next((r for r in pool if r["name"] == name), None)
            if me is None:
                continue
            same = [r for r in pool if r["pos"] == me["pos"]]
            old[w] = 1 + sum(1 for r in same if r["blend"] > me["blend"])
            pts = lambda r: wr.DYN_POINTS_PER_UNIT * r["dyn"]  # noqa: E731
            new[w] = 1 + sum(
                1 for r in same if (pts(r), r["blend"]) > (pts(me), me["blend"])
            )
        print(f"\n  {name} rank among his position by week: ", end="")
        print(
            "old blend",
            old,
            "| dynasty ordering (TODAY's dynasty value, look-ahead)",
            new,
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis")
    ap.add_argument(
        "--track",
        action="append",
        default=["Mason Taylor"],
        help="print this player's position rank each week under the old blend and "
        "under the new dynasty ordering (dynasty value in points, then blend)",
    )
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--last-week", type=int)
    ap.add_argument("--extra-root", action="append", default=[])
    ap.add_argument("--cache")
    ap.add_argument("--refresh", action="store_true")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
