#!/usr/bin/env python3
"""Advisor-vs-field sim study, scored by an INDEPENDENT yardstick (ESPN projections).

The advisor drafts every slot (1..teams) x N seeds in a full mock against
ADP+noise bots; every team's STARTING LINEUP is then scored with ESPN's own
projected points (kona ``leaguedefaults`` endpoint, no cookies) — never our
own projections, which would be circular (scored by our numbers the advisor
"wins" 47/48 by construction; see docs/DRAFT_DOCTRINE.md §10).

2026-08-24 baseline: mean rank 4.3/12 (field 6.5), +2.3 pts/wk vs field avg,
top-3 35%, bottom-3 4%. Limitation: opponents follow ADP, not sharp-human logic.

    python scripts/draft_sim_study.py --scoring standard --adp-file data/adp/adp_espn_standard.csv --seeds 4
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import random
import sys
import urllib.request
from typing import List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
    name_key,
)

_KONA = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{yr}"
    "/segments/0/leaguedefaults/3?view=kona_player_info"
)


def fetch_espn_points(year: int, limit: int = 450) -> dict:
    """ESPN projected season points by suffix-blind name key (fail-open {})."""
    flt = json.dumps({"players": {"limit": limit, "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"}}})
    req = urllib.request.Request(_KONA.format(yr=year), headers={"User-Agent": "Mozilla/5.0", "X-Fantasy-Filter": flt})
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: ESPN projections unavailable ({exc}) — cannot run an independent scoring pass")
        return {}
    out = {}
    for e in payload.get("players", []):
        pl = e.get("player") or {}
        st = [s for s in pl.get("stats", []) if s.get("seasonId") == year and s.get("statSourceId") == 1 and s.get("scoringPeriodId") == 0]
        if pl.get("fullName") and st:
            out[name_key(pl["fullName"])] = float(st[0].get("appliedTotal") or 0.0)
    return out


def starters_points(roster: List[dict]) -> float:
    by = collections.defaultdict(list)
    for p in roster:
        by[p["pos"]].append(p["pts"])
    for k in by:
        by[k].sort(reverse=True)
    total = sum(by.get("QB", [0])[:1]) + sum(by.get("RB", [0, 0])[:2]) + sum(by.get("WR", [0, 0])[:2]) + sum(by.get("TE", [0])[:1])
    flex = sorted(by.get("RB", [])[2:] + by.get("WR", [])[2:] + by.get("TE", [])[1:], reverse=True)
    return total + (flex[0] if flex else 0.0)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Advisor-vs-field sim study (independent scoring)")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--scoring", default="standard", choices=["ppr", "half_ppr", "standard"])
    p.add_argument("--roster-format", default="espn_default")
    p.add_argument("--teams", type=int, default=12)
    p.add_argument("--rounds", type=int, default=16)
    p.add_argument("--seeds", type=int, default=4)
    p.add_argument("--adp-file", default=os.path.join("data", "adp", "adp_espn_standard.csv"))
    p.add_argument("--projections-file")
    args = p.parse_args(argv)

    proj_path = args.projections_file or (sorted(glob.glob(os.path.join("output", "projections", f"preseason_{args.season}_{args.scoring}_*.csv"))) or [None])[-1]
    if not proj_path:
        print("ERROR: no projections; run generate_projections.py --preseason first")
        return 1
    proj = pd.read_csv(proj_path)
    adp = pd.read_csv(args.adp_file)
    base = compute_value_scores(proj, adp, roster_format=args.roster_format, n_teams=args.teams)
    epts = fetch_espn_points(args.season)
    if not epts:
        return 1

    import logging

    logging.disable(logging.CRITICAL)
    n = args.teams
    ranks, margins = [], []
    for slot in range(1, n + 1):
        for seed in range(args.seeds):
            random.seed(1000 * slot + seed)
            np.random.seed(1000 * slot + seed)
            board = DraftBoard(base.copy(), roster_format=args.roster_format, n_teams=n)
            adv = DraftAdvisor(board, scoring_format=args.scoring)
            sim = MockDraftSimulator(board, user_pick=slot, n_teams=n, randomness=4)
            res = sim.run_full_simulation(adv, rounds=args.rounds)
            rosters = collections.defaultdict(list)
            for pick in res["picks"]:
                i = (pick["pick"] - 1) % n
                rnd = (pick["pick"] - 1) // n + 1
                s = n - i if rnd % 2 == 0 else i + 1
                rosters[s].append({"pos": pick["position"], "pts": epts.get(name_key(pick["player_name"]), 0.0)})
            scores = {s: starters_points(r) for s, r in rosters.items()}
            my = scores.get(slot, 0.0)
            ranks.append(1 + sum(1 for s, v in scores.items() if s != slot and v > my))
            margins.append(my - float(np.mean([v for s, v in scores.items() if s != slot])))

    print(f"sims={len(ranks)} ({n} slots x {args.seeds} seeds) | scored by ESPN projections, drafted by ours")
    print(f"advisor mean rank {np.mean(ranks):.2f} (field {(n + 1) / 2:.1f}) | median {np.median(ranks):.0f} | top-3 {np.mean([r <= 3 for r in ranks]):.0%} | bottom-3 {np.mean([r >= n - 2 for r in ranks]):.0%}")
    print(f"starters-points margin vs field avg: {np.mean(margins):+.0f}/season ({np.mean(margins) / 17:+.1f}/wk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
