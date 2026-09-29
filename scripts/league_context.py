#!/usr/bin/env python3
"""League context before any fantasy advice: FAAB, bid history, our churn, dynasty values.

    python scripts/league_context.py --league mantis
    python scripts/league_context.py --league la_liga                     # ESPN cookies in .env
    python scripts/league_context.py --league la_liga --espn-json dump.json

Prints every team's FAAB left/spent, the room's winning-bid levels and biggest
bids, every move we made this season, and for dynasty presets (``"dynasty": True``,
e.g. Mantis) each team's total dynasty value, our roster by value/age, and the best
unrostered players by value. Read this BEFORE recommending claims, bids or drops.

Sleeper: fully live (public API). ESPN: lm-api with ESPN_S2/ESPN_SWID from .env, or
``--espn-json`` = the same league JSON saved from a logged-in browser (views mSettings,
mTeam, mRoster, mTransactions2). Yahoo: no API scope — not supported yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, league_context as lc, sleeper_http  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402

TX_URL = "https://api.sleeper.app/v1/league/{lid}/transactions/{week}"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", required=True, help="LEAGUE_PRESETS key")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument(
        "--espn-json", type=Path, help="ESPN: saved league JSON instead of cookies"
    )
    ap.add_argument("--espn-team-id", type=int, default=1, help="ESPN: my teamId")
    ap.add_argument(
        "--top", type=int, default=20, help="unrostered players shown (dynasty)"
    )
    args = ap.parse_args(argv)

    preset = config.LEAGUE_PRESETS.get(args.league)
    if preset is None:
        sys.exit(
            f"Unknown league '{args.league}'. Presets: {sorted(config.LEAGUE_PRESETS)}"
        )
    platform, lid = preset.get("platform"), str(preset["league_id"])
    registry = load_sleeper_players(max_age_days=1)
    my_ids, rostered, tags, team_values = [], set(), {}, None
    budget = None

    if platform == "sleeper":
        league = sleeper_http.get_league(lid)
        if not league:
            sys.exit(f"Sleeper league {lid} unavailable")
        users = sleeper_http.get_league_users(lid)
        rosters = sleeper_http.get_league_rosters(lid)
        txns = {
            w: sleeper_http.fetch_sleeper_json(TX_URL.format(lid=lid, week=w)) or []
            for w in range(0, 19)
        }
        me = preset.get("my_user") or ""
        teams, tx = lc.sleeper_context(league, users, rosters, txns, registry, me)
        budget = (league.get("settings") or {}).get("waiver_budget")
        title = f"{league.get('name')} — {me} — league context"
        owner = {u.get("user_id"): u.get("display_name") for u in users}
        by_team = {}
        for r in rosters:
            ids = [str(p) for p in r.get("players") or []]
            rostered.update(ids)
            by_team[owner.get(r.get("owner_id"))] = ids
            if owner.get(r.get("owner_id")) == me:
                my_ids = ids
                tags.update({str(p): "taxi" for p in r.get("taxi") or []})
                tags.update({str(p): "IR" for p in r.get("reserve") or []})
    elif platform == "espn":
        from src import espn_league

        if args.espn_json:
            payload = json.loads(args.espn_json.read_text(encoding="utf-8"))
        else:
            try:
                payload = espn_league.fetch_league(
                    int(lid), args.season, views=["mSettings", "mTeam", "mRoster"]
                )
                # mTransactions2 without a scoringPeriodId returns only the
                # current period's lineup moves -> gather every week.
                payload["transactions"] = [
                    t
                    for week in range(0, (payload.get("scoringPeriodId") or 18) + 1)
                    for t in espn_league.fetch_league(
                        int(lid),
                        args.season,
                        views=["mTransactions2"],
                        scoring_period=week,
                    ).get("transactions")
                    or []
                ]
            except PermissionError as exc:
                sys.exit(
                    f"{exc}\nOr save the league JSON from a logged-in browser and pass --espn-json."
                )
        teams, tx = lc.espn_context(payload, args.espn_team_id, registry)
        budget = ((payload.get("settings") or {}).get("acquisitionSettings") or {}).get(
            "acquisitionBudget"
        )
        title = f"{(payload.get('settings') or {}).get('name', args.league)} — league context"
    else:
        sys.exit(
            f"{args.league} is on {platform}: no API reader yet (Yahoo has no read scope). "
            "Read the league's transactions page in Chrome instead."
        )

    my_roster = fas = None
    if platform == "sleeper":
        values = lc.dynasty_values_for_preset(preset, config.ROSTER_CONFIGS)
        if values:
            team_values = {
                t: sum((values.get(p) or {}).get("value", 0) for p in ids)
                for t, ids in by_team.items()
            }
            my_roster = lc.dynasty_roster(my_ids, registry, values, tags)
            pool = [
                sid
                for sid in values
                if sid not in rostered
                and (registry.get(sid) or {}).get("position")
                in ("QB", "RB", "WR", "TE")
            ]
            fas = lc.dynasty_roster(pool, registry, values).head(args.top)

    print(
        lc.render(
            title,
            teams,
            tx,
            budget=budget,
            my_roster=my_roster,
            dynasty_fas=fas,
            team_values=pd.Series(team_values) if team_values else None,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
