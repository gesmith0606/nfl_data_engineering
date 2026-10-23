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

Read the DECISION view first. Absolute error measures distance to the
winning price, which conflates "we misjudged him" with "we correctly refused
to overpay" — declining a $450 claim is not a $443 error. The decision view
splits the same replay into claims the model would have won (and by how much
it overpaid) and claims it would have lost (and what they went for).

Median absolute error is the better of the two error numbers; the mean is
dominated by outliers no signal in this repo predicts — see "the tail" in
docs/WEEKLY_WAIVER_RUNBOOK.md §4, where four separate hypotheses were each
tested and rejected across two leagues.

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


def run(league_key: str, through_week: int, max_median_error: int = 0) -> int:
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
    overpaid: List[float] = []
    lost_prices: List[float] = []
    median_rule: List[float] = []
    minimum_rule: List[float] = []
    for leg, pid, won in actual:
        prior = [t for t in rows if int(t.get("_leg") or 0) < leg]
        history = waiver_wire.league_player_moves(league_id, leg - 1, prior).get(pid)
        suggested, _why = waiver_wire.suggest_bid(history, [], room_median, budget, leg)
        model.append(abs(suggested - won))
        median_rule.append(abs(room_median - won))
        minimum_rule.append(abs(1 - won))
        if suggested >= won:
            overpaid.append(suggested - won)
        else:
            lost_prices.append(won)

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
    print("\n  -- decision view: what the advice would actually have cost --")
    if overpaid:
        print(
            f"  wins   {len(overpaid):3}  median overpay ${statistics.median(overpaid):.0f}"
            f"  total FAAB wasted ${sum(overpaid):.0f}"
        )
    else:
        print("  wins     0")
    if lost_prices:
        dear = sum(1 for p in lost_prices if p >= 100)
        cheap = sum(1 for p in lost_prices if p <= 20)
        print(
            f"  losses {len(lost_prices):3}  median winning price "
            f"${statistics.median(lost_prices):.0f}  ({dear} went for $100+, "
            f"{cheap} for $20 or less)"
        )
    else:
        print("  losses   0")

    model_median = score(model)["median"]
    rivals = min(score(median_rule)["median"], score(minimum_rule)["median"])
    if model_median > rivals:
        print(
            f"\n  FAIL: model median ${model_median:.0f} is worse than the best "
            f"naive rule (${rivals:.0f})"
        )
        return 1
    if max_median_error and model_median > max_median_error:
        print(
            f"\n  FAIL: model median ${model_median:.0f} exceeds the "
            f"--max-median-error bound of ${max_median_error}"
        )
        return 1
    print(f"\n  PASS: model median ${model_median:.0f} beats both naive rules")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key (Sleeper)")
    ap.add_argument("--through-week", type=int, default=7)
    ap.add_argument(
        "--max-median-error",
        type=int,
        default=0,
        help="fail when the model's median absolute error exceeds this, so "
        "drift is caught by a check rather than by a bad claim",
    )
    args = ap.parse_args(argv)
    return run(args.league, args.through_week, args.max_median_error)


if __name__ == "__main__":
    raise SystemExit(main())
