#!/usr/bin/env python3
"""How many points did we leave on the bench, and does the room do better?

    python scripts/backtest_lineups.py --league mantis
    python scripts/backtest_lineups.py --league mantis --through-week 6

George, 2026-10-23: *"we also need a lineup optimizer that we should start
running ... our current ones have not been good."* Before building a fourth
lineup path alongside `lineup_setter`, `roster_optimizer` and `lineup_builder`,
measure the ones that exist -- the approach that reversed the waiver verdict
once its sample was pooled properly.

The measure is the only one that cannot be argued with: for each week, the
points the optimal hindsight lineup would have scored minus the points the
lineup actually set did score. That is regret, in points, and it is computed
from the league's OWN scoring because Sleeper reports per-player points for
every roster. Every team in the room is measured the same way, so "we are bad
at this" and "this is hard" are distinguishable.

Hindsight is not a fair target on its own -- nobody achieves it -- which is
exactly why the room's regret is the comparison that matters.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402

MATCHUPS = "https://api.sleeper.app/v1/league/{lid}/matchups/{week}"
#: Slots that take a specific position only; FLEX/SFLEX are handled separately.
FLEX_SLOTS = {"FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX", "IDP_FLEX"}


def slot_eligibility(slot: str) -> Tuple[str, ...]:
    """Which positions may fill this roster slot."""
    return {
        "QB": ("QB",),
        "RB": ("RB",),
        "WR": ("WR",),
        "TE": ("TE",),
        "K": ("K",),
        "DEF": ("DEF",),
        "FLEX": ("RB", "WR", "TE"),
        "WRRB_FLEX": ("RB", "WR"),
        "REC_FLEX": ("WR", "TE"),
        "SUPER_FLEX": ("QB", "RB", "WR", "TE"),
    }.get(slot, ())


def optimal_points(
    slots: Sequence[str],
    players: Sequence[str],
    points: Mapping[str, float],
    positions: Mapping[str, str],
) -> float:
    """The best score these players could have produced in these slots.

    Solved exactly, as a maximum-weight assignment of players to slots. A
    greedy fill looks sufficient and is not: with two *crossing* flex slots --
    say ``WRRB_FLEX`` (RB/WR) and ``REC_FLEX`` (WR/TE) -- the answer depends on
    which you fill first. WR 20, RB 5, TE 4 scores 24 one way and 25 the other.
    Mantis's slots happen to be nested (FLEX is a subset of SUPER_FLEX) so
    greedy would be right there today, but a regret metric whose own optimum is
    order-dependent is not worth measuring against, and league shapes change.

    Returns 0.0 when nothing is startable.
    """
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    fillable = [s for s in slots if slot_eligibility(s)]
    pool = [p for p in players if p in points]
    if not fillable or not pool:
        return 0.0
    # Rows are slots, columns players; -points because the solver minimises,
    # and an ineligible pairing costs 0 so it is never worth choosing.
    cost = np.zeros((len(fillable), len(pool)))
    for i, slot in enumerate(fillable):
        eligible = slot_eligibility(slot)
        for j, player in enumerate(pool):
            if positions.get(player) in eligible:
                cost[i, j] = -float(points.get(player, 0.0))
    rows, cols = linear_sum_assignment(cost)
    return float(-cost[rows, cols].sum())


def week_regret(
    roster: Mapping[str, Any],
    slots: Sequence[str],
    positions: Mapping[str, str],
) -> Optional[Tuple[float, float]]:
    """``(actual, optimal)`` for one roster-week, or None when unplayable.

    A week with no points at all is a bye or a pre-kickoff read, not a lineup
    mistake, and must not be averaged in as a perfect score.
    """
    points = {
        str(k): float(v or 0.0) for k, v in (roster.get("players_points") or {}).items()
    }
    if not points or not any(points.values()):
        return None
    actual = sum(points.get(str(p), 0.0) for p in (roster.get("starters") or []) if p)
    best = optimal_points(
        slots, [str(p) for p in (roster.get("players") or [])], points, positions
    )
    return actual, best


def summarise(regrets: Sequence[float], label: str) -> List[str]:
    """Points left on the bench, per week."""
    if not regrets:
        return [f"  {label:12} no scorable weeks"]
    perfect = sum(1 for r in regrets if r < 0.05)
    return [
        f"  {label:12} n={len(regrets):3}  median {statistics.median(regrets):6.1f}pt"
        f"  mean {statistics.mean(regrets):6.1f}pt  worst {max(regrets):6.1f}pt"
        f"  perfect {perfect}/{len(regrets)}"
    ]


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key (Sleeper)")
    ap.add_argument("--through-week", type=int, default=0)
    args = ap.parse_args(argv)

    try:
        preset = config.our_league(args.league)
    except (KeyError, ValueError) as exc:
        sys.exit(exc.args[0])
    if preset.get("platform") != "sleeper":
        sys.exit(
            f"{args.league} is on {preset.get('platform')}: only Sleeper reports "
            "per-player points for EVERY roster, which is what makes the room "
            "comparison possible."
        )

    lid = str(preset["league_id"])
    league = sleeper_http.get_league(lid)
    if not league:
        sys.exit(f"Sleeper league {lid} unavailable")
    slots = [s for s in (league.get("roster_positions") or []) if s != "BN"]
    registry = load_sleeper_players(max_age_days=7)
    positions = {
        sid: str((meta or {}).get("position") or "") for sid, meta in registry.items()
    }

    users = {
        u["user_id"]: u.get("display_name") for u in sleeper_http.get_league_users(lid)
    }
    mine = next(
        (
            str(r.get("roster_id"))
            for r in sleeper_http.get_league_rosters(lid)
            if users.get(r.get("owner_id")) == preset.get("my_user")
        ),
        None,
    )

    through = args.through_week or 18
    ours: List[float] = []
    theirs: List[float] = []
    per_week: List[Tuple[int, float, float]] = []
    for week in range(1, through + 1):
        rosters = sleeper_http.fetch_sleeper_json(MATCHUPS.format(lid=lid, week=week))
        if not rosters:
            continue
        for roster in rosters:
            got = week_regret(roster, slots, positions)
            if got is None:
                continue
            actual, best = got
            regret = max(0.0, best - actual)
            if str(roster.get("roster_id")) == mine:
                ours.append(regret)
                per_week.append((week, actual, best))
            else:
                theirs.append(regret)

    print(f"\n=== {league.get('name')} — points left on the bench ===")
    print(
        "Optimal hindsight lineup minus the lineup actually set, under this\n"
        "league's own scoring. Nobody achieves hindsight, which is why the\n"
        "room's regret is the comparison that matters.\n"
    )
    print("\n".join(summarise(ours, "US")))
    print("\n".join(summarise(theirs, "the room")))

    if len(ours) >= 3 and len(theirs) >= 3:
        us, room = statistics.median(ours), statistics.median(theirs)
        verdict = "BETTER THAN THE ROOM" if us <= room else "WORSE THAN THE ROOM"
        print(f"\n  VERDICT: {verdict} at setting lineups")
        print(
            f"    median points left on bench: us {us:.1f} vs room {room:.1f} ({us - room:+.1f})"
        )
        if len(ours) < 10:
            print(f"    n={len(ours)} weeks of ours — directional")
    else:
        print("\n  VERDICT: too few scorable weeks to compare (need 3 each)")

    if per_week:
        print("\n  -- our weeks, worst first --")
        for week, actual, best in sorted(per_week, key=lambda t: -(t[2] - t[1]))[:6]:
            print(
                f"  wk{week:<3} set {actual:6.1f}  best {best:6.1f}"
                f"  left {best - actual:6.1f}pt on the bench"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
