"""Backtest the waiver bid model against a league's own winning bids.

The model in ``scripts/waiver_wire.py`` prices a claim off what the room has
already paid for that player. This script replays every completed waiver add
in a league, prices it from only what was knowable BEFORE that week, and
compares the suggestion to what actually won.

    python scripts/backtest_bid_model.py --league mantis
    python scripts/backtest_bid_model.py --league mantis --through-week 7

Baselines it reports alongside the model:

* ``median``    — bid the room's median winning bid every time. This is the
  rule the runbook used to give, and the one that produced three overbids in
  a single session.
* ``minimum``   — bid $1 every time.

Median absolute error is the number to read. Mean is dominated by a handful
of outliers that no signal in this repo predicts — see "the tail" in
docs/WEEKLY_WAIVER_RUNBOOK.md §4, where three separate hypotheses (dynasty
value, week, budget depletion) were each tested and rejected.

Sleeper leagues only: ESPN and Yahoo transaction logs need a logged-in
browser, which a backtest should not depend on.
"""

from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from src.config import LEAGUE_PRESETS  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "waiver_wire", REPO_ROOT / "scripts" / "waiver_wire.py"
)
waiver_wire = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(waiver_wire)


def winning_adds(rows: Sequence[dict]) -> List[Tuple[int, str, int]]:
    """``(leg, sleeper_player_id, winning_bid)`` for every paid waiver add."""
    out: List[Tuple[int, str, int]] = []
    for t in rows:
        bid = (t.get("settings") or {}).get("waiver_bid")
        if not bid:
            continue
        for pid in (t.get("adds") or {}) or {}:
            out.append((int(t.get("_leg") or 0), str(pid), int(bid)))
    return out


def score(errors: Sequence[float]) -> Dict[str, float]:
    if not errors:
        return {"n": 0, "median": 0.0, "mean": 0.0, "within_5": 0.0}
    return {
        "n": len(errors),
        "median": statistics.median(errors),
        "mean": statistics.mean(errors),
        "within_5": 100.0 * sum(1 for e in errors if e <= 5) / len(errors),
    }


def run(league_key: str, through_week: int) -> int:
    preset = LEAGUE_PRESETS[league_key]
    if preset.get("platform") != "sleeper":
        sys.exit(f"{league_key} is on {preset.get('platform')}: Sleeper leagues only")
    league_id = str(preset["league_id"])
    rows = waiver_wire.fetch_league_transactions(league_id, through_week)
    stats = waiver_wire.team_bid_stats(rows)
    spread = sorted(b for st in stats.values() for b in [st["median"]] * st["n"])
    room_median = spread[len(spread) // 2] if spread else 0
    budget = 1000

    actual = winning_adds(rows)
    if not actual:
        sys.exit(
            f"No paid waiver adds found in {league_key} through week {through_week}"
        )

    model: List[float] = []
    median_rule: List[float] = []
    minimum_rule: List[float] = []
    for leg, pid, won in actual:
        prior = [t for t in rows if int(t.get("_leg") or 0) < leg]
        history = waiver_wire.league_player_moves(league_id, leg - 1, prior).get(pid)
        suggested, _why = waiver_wire.suggest_bid(history, [], room_median, budget, leg)
        model.append(abs(suggested - won))
        median_rule.append(abs(room_median - won))
        minimum_rule.append(abs(1 - won))

    print(
        f"=== {league_key}: {len(actual)} winning bids through week {through_week} ==="
    )
    print(f"room median winning bid: ${room_median}\n")
    print(f"  {'rule':10}{'n':>5}{'median err':>12}{'mean err':>11}{'within $5':>11}")
    for name, errs in (
        ("model", model),
        ("median", median_rule),
        ("minimum", minimum_rule),
    ):
        s = score(errs)
        print(
            f"  {name:10}{s['n']:5d}{s['median']:11.0f}${s['mean']:10.1f}"
            f"{s['within_5']:10.0f}%"
        )
    best = min(score(model)["median"], score(median_rule)["median"])
    return 0 if score(model)["median"] <= best else 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key (Sleeper)")
    ap.add_argument("--through-week", type=int, default=7)
    args = ap.parse_args(argv)
    return run(args.league, args.through_week)


if __name__ == "__main__":
    raise SystemExit(main())
