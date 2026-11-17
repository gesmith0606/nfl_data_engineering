#!/usr/bin/env python3
"""Replay the clearing-price model against a Sleeper league's own claims.

    python scripts/backtest_clearing_price.py --league mantis \\
        --extra-root "<checkout holding the newest boards>"

The older ``backtest_bid_model.py`` scores a bid by its distance to the price
that WON, which rewards copying overpayment (73% of Mantis' winning bids had no
rival claim). This scores what a bid would have done against what the other
rosters really bid:

* **win** iff the bid is above every rival's bid (a tie loses); you pay your bid;
* **overpay** = bid - clearing price (top rival bid + 1, minimum $1), on wins.

The universe is every name the report would have listed that week (top six per
position by blend) plus whatever we actually claimed, with the rival bids taken
from Sleeper's transaction log (failed claims included). Fit on weeks 2-5,
scored on weeks 6-10; a walk-forward replay (each week fit only on earlier
weeks) is shown beside it, and is the one used for George's own claims, since
those weeks sit inside the fit window.

What it cannot measure, and says so: Sleeper's trending-add counts (only the
live endpoint exists, so they are recorded by ``waiver_wire.py`` from now on
and not in any fit), and dynasty value (``--dyn`` weights are 0 here because
FantasyCalc is only archived from 2026 week 43).
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import clearing_model as cm  # noqa: E402
from src import waiver_scorecard as sc  # noqa: E402
from src.waiver_replay import Replay, load_replay  # noqa: E402

FIT_WEEKS = range(2, 6)
TEST_WEEKS = range(6, 11)
LIST_K = 6
#: Free replacement level: the blend of the rank-N free agent at the position.
REPLACEMENT_RANK = cm.REPLACEMENT_RANK


def _waiver_wire() -> Any:
    spec = importlib.util.spec_from_file_location(
        "waiver_wire", REPO_ROOT / "scripts" / "waiver_wire.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ universe


def _claims_by_player_week(rp: Replay) -> Dict[tuple, List[Dict[str, Any]]]:
    out: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for t in rp.data["txs"]:
        if t.get("type") != "waiver" or not t.get("adds"):
            continue
        if t["status_updated"] < rp.week1_start or t.get("status") not in (
            "complete",
            "failed",
        ):
            continue
        pid = str(next(iter(t["adds"])))
        out[(pid, sc.nfl_week(t["status_updated"], rp.week1_start))].append(
            {
                "roster": (t.get("roster_ids") or [None])[0],
                "bid": int((t.get("settings") or {}).get("waiver_bid") or 0),
                "won": t["status"] == "complete",
            }
        )
    return out


def build_universe(rp: Replay, weeks: Sequence[int]) -> List[Dict[str, Any]]:
    """Every listed-or-claimed name per week with its tier, value and rival bids."""
    claims = _claims_by_player_week(rp)
    rows: List[Dict[str, Any]] = []
    for wk in weeks:
        pool = rp.pool(wk)
        if not pool:
            continue
        ranked: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in pool:
            ranked[r["pos"]].append(r)
        for pos, rs in ranked.items():
            rs.sort(key=lambda r: -r["blend"])
            repl = (
                rs[REPLACEMENT_RANK - 1]["blend"]
                if len(rs) >= REPLACEMENT_RANK
                else 0.0
            )
            for rank, r in enumerate(rs, start=1):
                mine = [
                    c for c in claims.get((r["sid"], wk), []) if c["roster"] == rp.me
                ]
                if rank > LIST_K and not mine:
                    continue
                rivals = tuple(
                    c["bid"]
                    for c in claims.get((r["sid"], wk), [])
                    if c["roster"] != rp.me
                )
                rows.append(
                    {
                        "week": wk,
                        "sid": r["sid"],
                        "name": r["name"],
                        "pos": pos,
                        "rank": rank,
                        "tier": cm.tier_of(pos, rank),
                        "blend": r["blend"],
                        "above_free": max(0.0, r["blend"] - repl),
                        "p4": r["p4"],
                        "rivals": rivals,
                        "mine": mine,
                    }
                )
    # Names we claimed that no board projected (a waiver pickup the model had
    # never heard of) still belong: they are rank-less, worth nothing to the
    # model, and are exactly where an overbid on a name nobody ranks shows up.
    seen = {(r["sid"], r["week"]) for r in rows}
    boards = {r["week"] for r in rows}
    for (pid, wk), cs in claims.items():
        mine = [c for c in cs if c["roster"] == rp.me]
        if not mine or wk not in boards or (pid, wk) in seen:
            continue
        pos = rp.pos_of(pid)
        if pos not in ("QB", "RB", "WR", "TE"):
            continue
        rows.append(
            {
                "week": wk,
                "sid": pid,
                "name": rp.name(pid),
                "pos": pos,
                "rank": None,
                "tier": cm.tier_of(pos, None),
                "blend": 0.0,
                "above_free": 0.0,
                "p4": sc.window(rp.pts, pid, wk, 4, rp.last_week)[0],
                "rivals": tuple(c["bid"] for c in cs if c["roster"] != rp.me),
                "mine": mine,
            }
        )
    return rows


def obs_of(rows: Sequence[Dict[str, Any]]) -> List[cm.Obs]:
    return [cm.Obs(r["week"], r["tier"], r["rivals"]) for r in rows]


def clearing_of(row: Dict[str, Any]) -> int:
    return max(1, (max(row["rivals"]) if row["rivals"] else 0) + 1)


def budget_left(rp: Replay, week: int, budget: int = 1000) -> int:
    """What we had left going into ``week``, from our own completed claims."""
    spent = sum(
        int((t.get("settings") or {}).get("waiver_bid") or 0)
        for t in rp.data["txs"]
        if t.get("status") == "complete"
        and t.get("type") == "waiver"
        and rp.me in (t.get("roster_ids") or [])
        and rp.week1_start <= t["status_updated"]
        and sc.nfl_week(t["status_updated"], rp.week1_start) < week
    )
    return budget - spent


# ------------------------------------------------------------------ policies


def clearing_bid(
    model: cm.ClearingModel, row: Dict[str, Any], left: int, usd_per_point: float
) -> cm.Advice:
    value = cm.value_ceiling(row["above_free"], usd_per_point=usd_per_point)
    return model.recommend(row["tier"], value, left)


def summarise(label: str, picks: Sequence[tuple]) -> str:
    """``picks`` = (row, bid). Wins, spend, overpay and points won."""
    wins = [(r, b) for r, b in picks if cm.replay_bid(b, r["rivals"])[0]]
    spend = sum(b for _r, b in wins)
    over = sum(b - clearing_of(r) for r, b in wins)
    pts = sum(r["p4"] for r, _b in wins if r["week"] <= 9)
    REPORT["policies"][label] = {
        "n": len(picks),
        "wins": len(wins),
        "spend": spend,
        "overpay": over,
        "points_4wk": round(pts, 1),
    }
    return (
        f"  {label:<22}{len(picks):>4}{len(wins):>6}{spend:>8}{over:>9}"
        f"{(spend / len(wins) if wins else 0):>9.1f}{pts:>10.0f}"
    )


#: What the last run printed, as data (``--out``), so a test can pin it.
REPORT: Dict[str, Any] = {"policies": {}, "our_claims": []}

HEAD = f"  {'policy':<22}{'n':>4}{'wins':>6}{'spend':>8}{'overpay':>9}{'$/win':>9}{'4wk pts':>10}"


def run(args: argparse.Namespace) -> int:
    rp = load_replay(
        args.league,
        args.season,
        args.extra_root,
        args.last_week,
        args.cache,
        args.refresh,
    )
    ww = _waiver_wire()
    weeks = list(range(2, rp.last_week + 2))
    rows = build_universe(rp, weeks)
    if args.write_fit:
        args.write_fit.parent.mkdir(parents=True, exist_ok=True)
        args.write_fit.write_text(
            json.dumps(
                {
                    "league": args.league,
                    "season": args.season,
                    "through_week": max(r["week"] for r in rows),
                    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "obs": cm.obs_to_json(obs_of(rows)),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote production fit: {args.write_fit} ({len(rows)} observations)")
    fit_rows = [r for r in rows if r["week"] in FIT_WEEKS]
    test_rows = [r for r in rows if r["week"] in TEST_WEEKS]
    print(f"=== clearing-price backtest — {args.league} {args.season} ===")
    print(
        f"universe: {len(rows)} name-weeks (top {LIST_K} per position + our claims); "
        f"fit weeks 2-5 n={len(fit_rows)}, test weeks 6-10 n={len(test_rows)}"
    )
    print(
        f"contested (any rival claim): fit {sum(1 for r in fit_rows if r['rivals'])}"
        f"/{len(fit_rows)}, test {sum(1 for r in test_rows if r['rivals'])}/{len(test_rows)}"
    )

    fitted = cm.ClearingModel(obs_of(fit_rows), budget=1000, min_bid=1)
    print(
        "\n-- tiers as fitted on weeks 2-5 (contest rate shrunk toward the league's) --"
    )
    for tier in sorted({r["tier"] for r in rows}):
        n = sum(1 for r in fit_rows if r["tier"] == tier)
        print(
            f"  {tier:<9} n={n:<3} P(contested)={fitted.p_contested(tier):.2f} "
            f"$ for 50%: {fitted.price_for(0.5, tier)}  $ for 80%: {fitted.price_for(0.8, tier)}"
        )

    txs_done = [t for t in rp.data["txs"] if t.get("status") == "complete"]

    def median_rule(week: int) -> int:
        paid = [
            int((t.get("settings") or {}).get("waiver_bid") or 0)
            for t in txs_done
            if t.get("type") == "waiver" and t["_leg"] < week
        ]
        return max(1, int(statistics.median(paid))) if paid else 1

    def old_model(row: Dict[str, Any], left: int) -> int:
        prior = [t for t in txs_done if int(t["_leg"]) < row["week"]]
        history = ww.league_player_moves(rp.league_id, row["week"] - 1, prior).get(
            row["sid"]
        )
        paid = sorted(
            int((t.get("settings") or {}).get("waiver_bid") or 0)
            for t in prior
            if t.get("type") == "waiver"
        )
        med = paid[len(paid) // 2] if paid else 0
        return ww.suggest_bid(history, [], med, left, row["week"])[0]

    for usd in args.usd_per_point:
        print(
            f"\n-- TEST weeks 6-10, model fit on weeks 2-5, ${usd:g}/point ceiling --"
        )
        print(HEAD)
        picks = {
            "clearing model": [
                (r, clearing_bid(fitted, r, budget_left(rp, r["week"]), usd).bid)
                for r in test_rows
            ],
            "league minimum ($1)": [(r, 1) for r in test_rows],
            "room median so far": [(r, median_rule(r["week"])) for r in test_rows],
            "old model (no rivals)": [
                (r, old_model(r, budget_left(rp, r["week"]))) for r in test_rows
            ],
        }
        for label, p in picks.items():
            print(summarise(label, p))
        print(
            summarise("hindsight: clearing", [(r, clearing_of(r)) for r in test_rows])
        )

        chase = [
            r
            for r in test_rows
            if r["rivals"]
            and clearing_of(r) <= cm.value_ceiling(r["above_free"], usd_per_point=usd)
        ]
        print(
            f"  contested names whose clearing price was within their ceiling: "
            f"{len(chase)} of {sum(1 for r in test_rows if r['rivals'])} "
            f"(clearing ${sum(clearing_of(r) for r in chase)} for "
            f"{sum(r['p4'] for r in chase if r['week'] <= 9):.0f} four-week points)"
        )
        walk = []
        for r in rows:
            if r["week"] in TEST_WEEKS:
                model = cm.ClearingModel(
                    obs_of([x for x in rows if x["week"] < r["week"]])
                )
                walk.append(
                    (r, clearing_bid(model, r, budget_left(rp, r["week"]), usd).bid)
                )
        print(summarise("clearing, walk-forward", walk))

    # -- our own claims, each priced only from the weeks before it
    usd = args.usd_per_point[0]
    print(
        f"\n-- OUR claims replayed walk-forward (${usd:g}/point; fit on earlier weeks only) --"
    )
    print(
        f"  {'wk':<3}{'player':<20}{'tier':<9}{'paid':>5}{'clearing':>9}{'model':>7}"
        f"{'p(win)':>8}{'ceiling':>9}{'result':>8}{'worth it':>10}   why"
    )
    wins_paid = wins_model = won_n = 0
    for r in rows:
        mine = r["mine"]
        if not mine:
            continue
        model = cm.ClearingModel(obs_of([x for x in rows if x["week"] < r["week"]]))
        adv = clearing_bid(model, r, budget_left(rp, r["week"]), usd)
        # our claim's real clearing price: against everyone else's bids
        ok, paid = cm.replay_bid(adv.bid, r["rivals"])
        mine_won = any(c["won"] for c in mine)
        if mine_won:
            wins_paid += max(c["bid"] for c in mine if c["won"])
            if ok:
                won_n += 1
                wins_model += adv.bid
        REPORT["our_claims"].append(
            {
                "week": r["week"],
                "name": r["name"],
                "tier": r["tier"],
                "paid": max(c["bid"] for c in mine),
                "we_won": mine_won,
                "clearing": clearing_of(r),
                "model_bid": adv.bid,
                "p_win": round(adv.p_win, 3),
                "ceiling": adv.ceiling,
                "model_wins": ok,
                "worth_chasing": clearing_of(r) <= adv.ceiling,
                "reason": adv.reason,
            }
        )
        print(
            f"  {r['week']:<3}{r['name'][:19]:<20}{r['tier']:<9}"
            f"{max(c['bid'] for c in mine):>5}{clearing_of(r):>9}{adv.bid:>7}"
            f"{adv.p_win:>8.0%}{adv.ceiling:>9}{'WIN' if ok else 'lose':>8}"
            f"{'yes' if clearing_of(r) <= adv.ceiling else 'no':>10}   {adv.reason}"
        )
    print(
        f"\n  claims we WON: paid ${wins_paid}; the model would have won {won_n} of them "
        f"for ${wins_model}"
    )
    REPORT["our_wins"] = {
        "paid": wins_paid,
        "model_won": won_n,
        "model_spend": wins_model,
        "claims_won": sum(1 for c in REPORT["our_claims"] if c["we_won"]),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(REPORT, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--last-week", type=int)
    ap.add_argument("--extra-root", action="append", default=[])
    ap.add_argument("--cache")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", type=Path, help="write the replay as JSON")
    ap.add_argument(
        "--write-fit",
        type=Path,
        help="write every observation (weeks 2..) as the production fit that "
        "waiver_wire.py loads for this league",
    )
    ap.add_argument(
        "--usd-per-point",
        type=float,
        nargs="+",
        default=[2.0],
        help="FAAB dollars one point over free replacement is worth "
        "(the first is used for our claims)",
    )
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
