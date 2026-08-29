#!/usr/bin/env python3
"""Pre-draft target sheet — which flagged players are reachable at YOUR picks.

    python scripts/draft_targets.py --league la_liga
    python scripts/draft_targets.py --slot 12 --teams 12 --scoring standard
    python scripts/draft_targets.py --league feetball --rounds 16 --per-pick 8

VALUE / BUST / BREAKOUT / SLEEPER come from the doctrine labels in
src.draft_value; MY GUY comes from data/draft/my_guys.txt. The point of the
sheet is reachability: a VALUE tag on an ADP-20 player says nothing useful at
pick 36, and the 2026-08-28 mock ran the whole draft with the labels sitting
in a report nobody could act on.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import LEAGUE_PRESETS  # noqa: E402
from src.draft_optimizer import compute_value_scores  # noqa: E402
from src.draft_targets import (  # noqa: E402
    MY_GUYS_PATH,
    build_target_sheet,
    load_watchlist,
)
from src.draft_value import attach_features, label_board  # noqa: E402


def _latest(pattern: str):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def main() -> int:
    p = argparse.ArgumentParser(description="Pre-draft target sheet by pick slot")
    p.add_argument("--league", choices=sorted(LEAGUE_PRESETS), help="League preset")
    p.add_argument("--slot", type=int, help="Your draft slot (1-indexed)")
    p.add_argument("--teams", type=int, default=12)
    p.add_argument("--rounds", type=int, default=15)
    p.add_argument("--scoring", choices=("ppr", "half_ppr", "standard"))
    p.add_argument("--draft-type", choices=("snake", "linear"), default="snake")
    p.add_argument("--season", type=int, default=date.today().year)
    p.add_argument("--per-pick", type=int, default=6)
    p.add_argument("--window", type=int, default=12, help="ADP reach tolerance")
    p.add_argument("--my-guys", default=MY_GUYS_PATH)
    p.add_argument("--adp-file", help="Override the ADP board")
    args = p.parse_args()

    preset = LEAGUE_PRESETS.get(args.league, {}) if args.league else {}
    scoring = args.scoring or preset.get("scoring_format") or "half_ppr"
    teams = args.teams or preset.get("teams") or 12
    slot = args.slot or preset.get("my_pick")
    roster = preset.get("roster")
    if not slot:
        p.error("need --slot (or a --league preset that sets my_pick)")

    proj_path = _latest(f"output/projections/preseason_{args.season}_{scoring}_*.csv")
    if not proj_path:
        print(
            f"No {scoring} projections for {args.season}. Run generate_projections.py"
        )
        return 1
    source = preset.get("platform") or "espn"
    adp_path = (
        args.adp_file
        or _latest(f"data/adp/adp_{source}_{scoring}.csv")
        or _latest(f"data/adp/adp_{source}_*.csv")
    )
    if not adp_path:
        print(f"No ADP board for source '{source}'. Run refresh_adp.py")
        return 1

    projections = pd.read_csv(proj_path)
    adp = pd.read_csv(adp_path)
    board = (
        compute_value_scores(projections, adp, roster_format=roster, n_teams=teams)
        if roster
        else compute_value_scores(projections, adp, n_teams=teams)
    )
    labeled = label_board(attach_features(board, args.season))

    wl = load_watchlist(args.my_guys)
    my_guys, fades = wl["targets"], wl["fades"]
    sheet = build_target_sheet(
        labeled,
        slot=slot,
        n_teams=teams,
        rounds=args.rounds,
        draft_type=args.draft_type,
        my_guys=my_guys,
        fades=fades,
        window=args.window,
        per_pick=args.per_pick,
    )

    print(
        f"\nTARGET SHEET — slot {slot}/{teams}, {scoring}, {args.draft_type}, "
        f"{args.rounds} rounds"
    )
    print(f"projections: {proj_path}")
    print(f"ADP        : {adp_path}")
    if my_guys or fades:
        print(
            f"my guys    : {len(my_guys)} target(s), {len(fades)} fade(s) "
            f"from {args.my_guys}"
        )
    elif os.path.exists(args.my_guys):
        print(f"my guys    : file present but empty ({args.my_guys})")
    else:
        print(f"my guys    : none — create {args.my_guys} to tag MY GUY")
    print("=" * 92)
    for entry in sheet:
        print(f"\nPICK {entry['pick']}  (round {entry['round']})")
        if not entry["players"]:
            print("   (no flagged player projects to be here — take best available)")
            continue
        for pl in entry["players"]:
            tags = "/".join(pl["tags"])
            reasons = str(pl.get("reasons") or "")[:64]
            print(
                f"   {str(pl['player_name']):<24}{str(pl['position']):<4}"
                f"{str(pl['team']):<5}adp={str(pl['adp_rank']):<6}[{tags}]"
                + (f"  {reasons}" if reasons else "")
            )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
