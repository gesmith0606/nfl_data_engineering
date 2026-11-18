#!/usr/bin/env python3
"""Waiver scorecard: did the claims pay off, and did we pay the price it took?

    python scripts/waiver_scorecard.py --league mantis --weeks 2-7 9
    python scripts/waiver_scorecard.py --league mantis --weeks 2-7 9 \\
        --extra-root "<other checkout with newer boards/bronze>"

Judges the advice by what happened, never by agreement with Sleeper (see
``src/waiver_scorecard.py``). Sleeper leagues only: the transaction log of an
ESPN/Yahoo league needs the owner's login, which a scorecard must not depend
on.

Inputs, all reproducible from disk once fetched:

* Sleeper's public API, cached under ``data/cache/sleeper/<league_id>/`` (league,
  rosters, every transaction leg, per-week stat lines and projections, the
  player registry). ``--refresh`` re-fetches. The projections are *as served
  today*, which includes later revisions, so they flatter Sleeper against our
  board; say so whenever the two are compared.
* Our weekly boards under ``data/gold/projections``: for each week the latest
  board written **before the week's first kickoff** (the board the Tuesday
  report could have used). The week-9 board only exists in a local checkout,
  hence ``--extra-root``.
* A week's pool is rebuilt the way the report builds it: every skill player
  nobody rostered on Tuesday evening, scored by both sources under the league's
  scoring, ranked within position by their mean (the BLEND column).

Writes ``data/waivers/scorecard/<league>_<season>.{json,md}``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import waiver_scorecard as sc  # noqa: E402
from src.lineup_setter import SKILL_POSITIONS  # noqa: E402
from src.waiver_replay import board_for, load_replay  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "waivers" / "scorecard"
#: Weeks the plan's acceptance test splits on: fit on early, hold out late.
EARLY_LAST_WEEK = 6

#: How each listing method orders a position's free agents (best first).
METHODS = {
    "tool_blend": lambda r: -r["blend"],
    "sleeper_only": lambda r: -(r["slpr"] or 0.0),
    "ours_only": lambda r: -(r["ours"] if r["ours"] is not None else -1.0),
    "last_week_points": lambda r: -(r["last"] or 0.0),
    "hindsight_best": lambda r: -r["p4"],
}


# ------------------------------------------------------------------ the card


def _method_block(pool: Mapping[int, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, key in METHODS.items():
        out[name] = {
            "weeks_2_6": sc.score_listed(pool, key, 6, range(2, EARLY_LAST_WEEK + 1)),
            "weeks_7_plus": sc.score_listed(
                pool, key, 6, range(EARLY_LAST_WEEK + 1, 19)
            ),
            "all": sc.score_listed(pool, key, 6),
        }
    out["tier_top30"] = {
        "weeks_2_6": sc.score_listed(
            pool, METHODS["tool_blend"], 30, range(2, EARLY_LAST_WEEK + 1)
        ),
        "weeks_7_plus": sc.score_listed(
            pool, METHODS["tool_blend"], 30, range(EARLY_LAST_WEEK + 1, 19)
        ),
        "all": sc.score_listed(pool, METHODS["tool_blend"], 30),
    }
    return out


def build_card(args: argparse.Namespace) -> Dict[str, Any]:
    rp = load_replay(
        args.league,
        args.season,
        args.extra_root,
        args.last_week,
        args.cache,
        args.refresh,
    )
    data, last_week, w1, me, pts = rp.data, rp.last_week, rp.week1_start, rp.me, rp.pts
    pool: Dict[int, List[Dict[str, Any]]] = {}
    boards: Dict[str, Optional[str]] = {}
    for week in args.weeks:
        path = board_for(week, args.season, rp.sched, rp.roots)
        boards[str(week)] = Path(path).name if path else None
        if path is None or week > last_week:
            continue
        pool[week] = rp.pool(week)

    name, pos_of = rp.name, rp.pos_of

    claims = [
        {**c, "pos": pos_of(c["add"])}
        for c in sc.filed_adds(data["txs"], me, w1)
        if c["week"] <= last_week and pos_of(c["add"]) in SKILL_POSITIONS
    ]
    scored = sc.score_claims(claims, pool, pts, last_week)
    for row in scored["rows"]:
        row["add"], row["drop"] = name(row["add"]), (
            name(row["drop"]) if row["drop"] else None
        )
    mine = sc.score_bids(data["txs"], me, w1)
    room = sc.score_bids(data["txs"], None, w1)
    for r in mine["rows"]:
        r["add"] = name(r["add"])
    lost = sc.lost_bids(data["txs"], me, w1)
    for r in lost:
        r["add"] = name(r["add"])
    room_clear = [r["clearing"] for r in room["rows"]]
    room_paid = [r["paid"] for r in room["rows"]]
    return {
        "league": args.league,
        "season": args.season,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "last_complete_week": last_week,
        "weeks_requested": list(args.weeks),
        "boards_used": boards,
        "notes": [
            "Actual points = Sleeper's stat lines under the league's scoring.",
            "Sleeper projections are as served on the generated_at date, which includes "
            "later revisions: they flatter Sleeper against our pre-kickoff board.",
            "A window is clipped at the last complete week; claims made late have shorter windows.",
        ],
        "claims": scored,
        "bids": {
            "mine": mine,
            "lost": lost,
            "room": {
                "n": room["n"],
                "uncontested": room["uncontested"],
                "median_paid": statistics.median(room_paid) if room_paid else None,
                "median_clearing": (
                    statistics.median(room_clear) if room_clear else None
                ),
                "paid": room["paid"],
                "clearing": room["clearing"],
            },
        },
        "listed": {
            "methods": _method_block(pool),
            "rows": sc.listing_rows(pool, METHODS["tool_blend"], 6),
            "pool_sizes": {str(w): len(rows) for w, rows in pool.items()},
        },
    }


# ---------------------------------------------------------------------- output


def _f(v: Sequence[float], places: int = 0) -> str:
    return " / ".join(f"{x:.{places}f}" for x in v)


def render_md(card: Mapping[str, Any]) -> str:
    c, b, m = card["claims"], card["bids"], card["listed"]["methods"]
    t = c["totals"]
    out = [
        f"# Waiver scorecard — {card['league']} {card['season']}",
        "",
        f"Generated {card['generated_at']}; last complete week {card['last_complete_week']}; "
        f"weeks scored {card['weeks_requested']}.",
        "",
        *[f"- {n}" for n in card["notes"]],
        "",
        "## Filed adds — points over the next 1 / 2 / 4 weeks",
        "",
        f"n = {c['n']} adds. Totals: **added {_f(t['add'], 1)}** · dropped {_f(t['drop'], 1)} · "
        f"board's #1 at the position {_f(t['board_top'], 1)} · best free agent at the position "
        f"(hindsight) {_f(t['best_at_pos'], 1)}.",
        "",
        "| wk | add | bid | dropped | add +1/+2/+4 | drop +1/+2/+4 | board #1 "
        "| board #1 pts | best-at-pos pts |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in c["rows"]:
        out.append(
            f"| {r['week']} | {r['add']} ({r['pos']}) | ${r['bid']} | {r['drop'] or '—'} | "
            f"{_f(r['add_pts'])} | {_f(r['drop_pts'])} | {r['board_top']} | "
            f"{_f(r['board_top_pts'])} | {_f(r['best_at_pos_pts'])} |"
        )
    mine, room = b["mine"], b["room"]
    out += [
        "",
        "## Bids — price paid vs clearing price (runner-up bid + 1, minimum $1)",
        "",
        f"Our {mine['n']} waiver wins this season: **paid ${mine['paid']}, "
        f"${mine['clearing']} would have won every one** (overpaid ${mine['overpaid']}; "
        f"{mine['uncontested']} of {mine['n']} had no rival claim).",
        "",
        "| wk | player | paid | clearing | rival claims | rival bids |",
        "|---|---|---|---|---|---|",
    ]
    for r in mine["rows"]:
        out.append(
            f"| {r['week']} | {r['add']} | ${r['paid']} | ${r['clearing']} | "
            f"{r['rivals']} | {', '.join('$' + str(x) for x in r['rival_bids']) or '—'} |"
        )
    out += ["", "Claims we lost (our bid vs the winner's):", ""]
    for r in b["lost"]:
        out.append(
            f"- wk{r['week']} {r['add']}: bid ${r['bid']}, winner ${r['winner_bid']}"
        )
    out += [
        "",
        f"Whole room: {room['n']} waiver wins, {room['uncontested']} "
        f"({100 * room['uncontested'] / max(1, room['n']):.0f}%) uncontested; "
        f"median paid ${room['median_paid']}, median clearing ${room['median_clearing']}; "
        f"${room['paid']} paid vs ${room['clearing']} needed.",
        "",
        "## Listed names — mean points over the next 1 / 2 / 4 weeks",
        "",
        "Top 6 per position (n = names), by method. 'hindsight_best' is the ceiling; "
        "'tier_top30' is the average of the top 30 per position (the tier a claim is drawn from).",
        "",
        "| method | weeks 2-6 n | +1 | +2 | +4 | weeks 7+ n | +1 | +2 | +4 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, d in m.items():
        e, late = d["weeks_2_6"], d["weeks_7_plus"]
        out.append(
            f"| {name} | {e['n']} | {e['p1']:.1f} | {e['p2']:.1f} | {e['p4']:.1f} | "
            f"{late['n']} | {late['p1']:.1f} | {late['p2']:.1f} | {late['p4']:.1f} |"
        )
    return "\n".join(out) + "\n"


def parse_weeks(tokens: Sequence[str]) -> List[int]:
    out: List[int] = []
    for tok in tokens:
        if "-" in tok:
            a, b = tok.split("-")
            out += range(int(a), int(b) + 1)
        else:
            out.append(int(tok))
    return sorted(set(out))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--weeks", nargs="+", default=["2-7", "9"], help="e.g. 2-7 9")
    ap.add_argument(
        "--last-week", type=int, help="last complete week (default: from the schedule)"
    )
    ap.add_argument(
        "--extra-root",
        action="append",
        default=[],
        help="another checkout whose data/ holds newer boards/bronze (repeatable)",
    )
    ap.add_argument(
        "--cache",
        help="Sleeper JSON cache dir (default data/cache/sleeper/<league id>)",
    )
    ap.add_argument(
        "--refresh", action="store_true", help="re-fetch Sleeper instead of the cache"
    )
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    args.weeks = parse_weeks(args.weeks)

    card = build_card(args)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{args.league}_{args.season}"
    stem.with_suffix(".json").write_text(
        json.dumps(card, indent=1) + "\n", encoding="utf-8"
    )
    md = render_md(card)
    stem.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {stem}.json / .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
