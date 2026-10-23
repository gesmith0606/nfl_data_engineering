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
from typing import Any, Dict, List, Mapping, Sequence, Tuple

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


def espn_actuals(
    league_key: str, preset: Mapping[str, Any], season: int, through_week: int
) -> Tuple[List[Tuple[int, str, int]], Dict[str, List[Dict[str, Any]]], int]:
    """ESPN's winning bids and per-player history, through the claims profile.

    The model was only ever measured against Mantis -- one room, 51 bids, one
    set of spending habits. A price model validated in a single market is a
    price model with an unknown generalisation, so this adds the second room
    we can actually read.
    """
    registry = waiver_wire.load_sleeper_players(max_age_days=7)
    # moves_from_tx matches ESPN's own player NAMES onto Sleeper ids, so the
    # name map is not optional -- passing {} silently yields no history at all.
    _by_gsis, by_name = waiver_wire.build_id_maps(registry)
    moves, _faab, _payload, _tx = waiver_wire.espn_player_moves(
        str(preset["league_id"]),
        season,
        int(preset.get("my_team_id") or 1),
        through_week,
        registry,
        by_name,
    )
    actual: List[Tuple[int, str, int]] = []
    for sid, history in moves.items():
        for m in history:
            if m.get("kind") == "add" and m.get("bid"):
                actual.append((int(m["leg"]), str(sid), int(m["bid"])))
    paid = sorted(b for _l, _p, b in actual)
    room_median = paid[len(paid) // 2] if paid else 0
    return sorted(actual), moves, room_median


def run(
    league_key: str,
    through_week: int,
    max_median_error: int = 0,
    season: int = 2026,
) -> int:
    preset = LEAGUE_PRESETS[league_key]
    platform = preset.get("platform")
    if platform not in ("sleeper", "espn"):
        sys.exit(
            f"{league_key} is on {platform}: Sleeper reads its log over the "
            "public API and ESPN through the claims profile; Yahoo's needs a "
            "login that is not in place."
        )
    league_id = str(preset["league_id"])
    budget = 1000
    espn_moves: Dict[str, List[Dict[str, Any]]] = {}
    if platform == "espn":
        actual, espn_moves, room_median = espn_actuals(
            league_key, preset, season, through_week
        )
        rows: List[dict] = []
    else:
        rows = waiver_wire.fetch_league_transactions(league_id, through_week)
        stats = waiver_wire.team_bid_stats(rows)
        spread = sorted(b for st in stats.values() for b in [st["median"]] * st["n"])
        room_median = spread[len(spread) // 2] if spread else 0
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
        if platform == "espn":
            # Only what was knowable BEFORE this claim, or the model is
            # scored against the answer it is trying to predict.
            history = [
                m for m in espn_moves.get(pid, []) if int(m["leg"]) < leg
            ] or None
        else:
            prior = [t for t in rows if int(t.get("_leg") or 0) < leg]
            history = waiver_wire.league_player_moves(league_id, leg - 1, prior).get(
                pid
            )
        suggested, _why = waiver_wire.suggest_bid(
            history,
            [],
            room_median,
            budget,
            leg,
            floor_divisor=int(preset.get("bid_floor_divisor") or 5),
        )
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

    # Why the model wins or loses in THIS room. The no-rival floor is
    # room_median // FLOOR_DIVISOR, swept to 5 against 51 Mantis bids where
    # the median winning bid is $50 and the budget $1000. In a $100 room whose
    # median is $8 that floor is $1, so every historyless player is bid at the
    # minimum and lost. One room cannot tune a divisor for all rooms.
    configured = int(preset.get("bid_floor_divisor") or 5)
    print("\n  -- floor divisor sweep (the no-rival branch's only free knob) --")
    best, best_err = None, None
    for div in (1, 2, 3, 5, 8):
        errs = []
        for leg, pid, won in actual:
            if platform == "espn":
                hist = [
                    m for m in espn_moves.get(pid, []) if int(m["leg"]) < leg
                ] or None
            else:
                prior = [t for t in rows if int(t.get("_leg") or 0) < leg]
                hist = waiver_wire.league_player_moves(league_id, leg - 1, prior).get(
                    pid
                )
            bid, _ = waiver_wire.suggest_bid(
                hist, [], room_median, budget, leg, floor_divisor=div
            )
            errs.append(abs(bid - won))
        med = statistics.median(errs)
        flag = " <- configured for this room" if div == configured else ""
        print(f"  // {div:<3} median err ${med:5.0f}{flag}")
        if best_err is None or med < best_err:
            best, best_err = div, med
    if best != configured:
        print(
            f"  -> this room wants // {best} (${best_err:.0f}), not its configured"
            f" // {configured} — set bid_floor_divisor in LEAGUE_PRESETS"
        )

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
    ap.add_argument(
        "--league",
        default="mantis",
        help="LEAGUE_PRESETS key (Sleeper via API, ESPN via the claims profile)",
    )
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--through-week", type=int, default=7)
    ap.add_argument(
        "--max-median-error",
        type=int,
        default=0,
        help="fail when the model's median absolute error exceeds this, so "
        "drift is caught by a check rather than by a bad claim",
    )
    args = ap.parse_args(argv)
    return run(args.league, args.through_week, args.max_median_error, args.season)


if __name__ == "__main__":
    raise SystemExit(main())
