#!/usr/bin/env python3
"""Did our waiver claims actually help? Points gained per claim, us vs the room.

    python scripts/backtest_claim_outcomes.py --league mantis
    python scripts/backtest_claim_outcomes.py --league mantis --through-week 7 --min-weeks 2

Everything else about this pipeline is validated against a PROXY: the bid model
against what the room paid, the RENTAL tag against snap share. Neither asks the
only question that finally matters -- whether the player we added outscored the
player we dropped. This does, for every claim in the league, so our process can
be compared against our leaguemates' rather than only against itself.

The measure is deliberately conservative. For each add-with-drop it scores both
players under the league's own scoring over the weeks AFTER the move, and
reports the difference. It does not credit us for a player we added and never
started, and it does not compare against the best alternative still on waivers
-- the historical free-agent pool is not recoverable, so that number would be
invented. Add-minus-drop is the honest floor.
"""

from __future__ import annotations

import argparse
import glob
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.lineup_setter import ours_by_sleeper_id, roster_gsis_map  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402
from scripts import set_lineups  # noqa: E402
import scripts.waiver_wire as waiver_wire  # noqa: E402
from scripts.waiver_wire import last_week_actuals, scoring_for  # noqa: E402


def weekly_points(
    season: int,
    weeks: Sequence[int],
    scoring: Dict[str, float],
    registry: Mapping[str, Any],
    gsis_map: Mapping[str, str],
) -> Dict[Tuple[str, int], float]:
    """``(sleeper_id, week) -> fantasy points`` under this league's scoring.

    Goes through ``ours_by_sleeper_id`` rather than inverting ``gsis_id``
    directly: that is the crosswalk the rest of the pipeline uses, and the only
    path that resolves rookies, who have neither a Bronze ``sleeper_id`` nor a
    registry ``gsis_id``. Half the claims in a season are rookies.
    """
    out: Dict[Tuple[str, int], float] = {}
    for wk in weeks:
        df = last_week_actuals(season, wk, scoring)
        if df.empty:
            continue
        names = dict(zip(df["player_id"].astype(str), df["player_name"]))
        for sid, pts in ours_by_sleeper_id(
            df, dict(registry), gsis_map=dict(gsis_map), full_names=names
        ).items():
            out[(sid, wk)] = pts
    return out


def bronze_rosters() -> "pd.DataFrame":
    """Every committed Bronze roster snapshot, for the gsis crosswalk."""
    files = glob.glob(
        str(
            REPO_ROOT
            / "data"
            / "bronze"
            / "players"
            / "rosters"
            / "season=*"
            / "**"
            / "*.parquet"
        ),
        recursive=True,
    )
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def claim_rows(
    txns: Sequence[Mapping[str, Any]], through_week: int
) -> List[Dict[str, Any]]:
    """Every add-with-drop in the league, oldest first."""
    rows = []
    for t in txns:
        if t.get("status") != "complete" or not t.get("adds") or not t.get("drops"):
            continue
        leg = int(t.get("leg") or 0)
        if not 1 <= leg <= through_week:
            continue
        for add_sid, rid in (t["adds"] or {}).items():
            drop_sid = next(
                (d for d, dr in (t["drops"] or {}).items() if dr == rid), None
            )
            if drop_sid is None:
                continue
            rows.append(
                {
                    "leg": leg,
                    "roster_id": str(rid),
                    "add": str(add_sid),
                    "drop": str(drop_sid),
                    "bid": int(((t.get("settings") or {}).get("waiver_bid")) or 0),
                    "kind": t.get("type"),
                }
            )
    return sorted(rows, key=lambda r: r["leg"])


def espn_claim_rows(
    tx: "pd.DataFrame", by_name: Mapping[Any, str]
) -> List[Dict[str, Any]]:
    """Add-with-drop pairs from an ESPN transaction frame, keyed to Sleeper ids.

    ESPN labels each row with the team NAME and the players by their own
    names (``espn:<id>`` when it cannot resolve one), so both sides go through
    the same normalised-name map the demand history uses. A pair where either
    side is unresolvable is dropped: scoring it would need points for a player
    we cannot identify.
    """
    from src.sleeper_player_map import normalize_name

    def sid_for(label: Any) -> Optional[str]:
        name = str(label or "").split("(")[0].strip()
        if not name or name.startswith("espn:") or name.startswith("D/ST"):
            return None
        norm = normalize_name(name)
        return next((v for (n, _pos), v in by_name.items() if n == norm), None)

    rows: List[Dict[str, Any]] = []
    for r in tx.itertuples(index=False):
        add, drop = sid_for(getattr(r, "add", None)), sid_for(getattr(r, "drop", None))
        if not add or not drop:
            continue
        bid = getattr(r, "bid", 0)
        rows.append(
            {
                "leg": int(getattr(r, "week", 0) or 0),
                "roster_id": "US" if bool(getattr(r, "is_me", False)) else str(r.team),
                "add": add,
                "drop": drop,
                "bid": 0 if bid is None or pd.isna(bid) else int(bid),
                "kind": str(getattr(r, "type", "")),
            }
        )
    return sorted(rows, key=lambda r: r["leg"])


def score_claims(
    rows: Sequence[Mapping[str, Any]],
    points: Mapping[Tuple[str, int], float],
    through_week: int,
    min_weeks: int,
) -> List[Dict[str, Any]]:
    """Attach points-after-the-move for the added and dropped player.

    A claim is only scored when at least ``min_weeks`` of football have been
    played since it was made -- otherwise a week-7 add looks identical to a
    week-1 add that has had six weeks to prove itself.
    """
    scored = []
    for r in rows:
        after = [w for w in range(r["leg"] + 1, through_week + 1)]
        if len(after) < min_weeks:
            continue
        got = sum(points.get((r["add"], w), 0.0) for w in after)
        lost = sum(points.get((r["drop"], w), 0.0) for w in after)
        scored.append(
            {
                **r,
                "weeks": len(after),
                "add_pts": got,
                "drop_pts": lost,
                "gain": got - lost,
            }
        )
    return scored


def summarise(scored: Sequence[Mapping[str, Any]], label: str) -> List[str]:
    """One block of output: win rate, median gain, and FAAB per point gained."""
    if not scored:
        return [f"  {label:18} no claims old enough to score"]
    gains = [s["gain"] for s in scored]
    wins = [s for s in scored if s["gain"] > 0]
    spent = sum(s["bid"] for s in scored)
    net = sum(gains)
    lines = [
        f"  {label:18} n={len(scored):3}  won {len(wins):3}/{len(scored):<3}"
        f" ({100 * len(wins) / len(scored):4.1f}%)"
        f"  median {statistics.median(gains):+6.1f}pt  mean {statistics.mean(gains):+6.1f}pt"
    ]
    if spent:
        per = f"${spent / net:.1f}/pt" if net > 0 else "no net points"
        lines.append(f"  {'':18} FAAB ${spent} for {net:+.1f}pt net -> {per}")
    return lines


def verdict(
    ours: Sequence[Mapping[str, Any]], theirs: Sequence[Mapping[str, Any]]
) -> List[str]:
    """Are we better than our leaguemates at this, or not?

    Compares MEDIANS, not means: one Jacoby Brissett at +84pt drags a mean
    anywhere you like, and the question is whether a typical claim of ours
    beats a typical claim of theirs.
    """
    if len(ours) < 3 or len(theirs) < 3:
        return ["  VERDICT: too few scored claims to compare (need 3 each)"]
    mine = statistics.median(s["gain"] for s in ours)
    room = statistics.median(s["gain"] for s in theirs)
    gap = mine - room
    spent_each = [
        sum(g["bid"] for g in grp) / max(1e-9, sum(g["gain"] for g in grp))
        for grp in (ours, theirs)
    ]
    verdicts = {
        True: "BEATING THE ROOM",
        False: "BEHIND THE ROOM — the process is not yet earning its FAAB",
    }
    lines = [
        f"  VERDICT: {verdicts[gap >= 0]}",
        f"    median gain per claim: us {mine:+.1f}pt vs room {room:+.1f}pt ({gap:+.1f})",
        f"    FAAB per net point:    us ${spent_each[0]:.1f} vs room ${spent_each[1]:.1f}",
    ]
    if len(ours) < 10:
        lines.append(
            f"    n={len(ours)} of ours — directional only; re-run at season end"
        )
    worst = min(ours, key=lambda s: s["gain"] / max(1, s["bid"]))
    lines.append(
        f"    worst value: wk{worst['leg']} ${worst['bid']} for {worst['gain']:+.1f}pt"
    )
    return lines


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key (Sleeper)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--through-week", type=int, default=0, help="default: NFL week - 1")
    ap.add_argument(
        "--min-weeks",
        type=int,
        default=2,
        help="weeks of football a claim needs before it is scored (default 2)",
    )
    args = ap.parse_args(argv)

    try:
        preset = config.our_league(args.league)
    except (KeyError, ValueError) as exc:
        sys.exit(exc.args[0])
    platform = preset.get("platform")
    if platform not in ("sleeper", "espn"):
        sys.exit(
            f"{args.league} is on {platform}: Sleeper reads every team's log "
            "over the public API and ESPN through the claims profile, which is "
            "what makes the room comparison possible. Yahoo's needs a login "
            "that is not in place."
        )

    lid = str(preset["league_id"])
    league = sleeper_http.get_league(lid) if platform == "sleeper" else {}
    if platform == "sleeper" and not league:
        sys.exit(f"Sleeper league {lid} unavailable")
    _season, live_week = set_lineups._default_week(args.season)
    through = args.through_week or max(1, live_week - 1)

    scoring = scoring_for(preset, league or None)
    registry = load_sleeper_players(max_age_days=7)
    gsis_map = roster_gsis_map(bronze_rosters())

    if platform == "espn":
        _g, by_name = waiver_wire.build_id_maps(registry)
        _m, _f, _p, tx = waiver_wire.espn_player_moves(
            lid,
            args.season,
            int(preset.get("my_team_id") or 1),
            through,
            registry,
            by_name,
        )
        rows = [r for r in espn_claim_rows(tx, by_name) if r["leg"] <= through]
        title = f"{args.league} (espn)"
        mine = "US"
    else:
        txns = [
            t
            for w in range(0, through + 1)
            for t in (
                sleeper_http.fetch_sleeper_json(
                    f"https://api.sleeper.app/v1/league/{lid}/transactions/{w}"
                )
                or []
            )
        ]
        rows = claim_rows(txns, through)
        title = str(league.get("name"))
    points = weekly_points(
        args.season, range(1, through + 1), scoring, registry, gsis_map
    )
    scored = score_claims(rows, points, through, args.min_weeks)

    if platform == "espn":
        users: Dict[str, Any] = {}
    else:
        users = {
            u["user_id"]: u.get("display_name")
            for u in sleeper_http.get_league_users(lid)
        }
        mine = next(
            (
                str(r.get("roster_id"))
                for r in sleeper_http.get_league_rosters(lid)
                if users.get(r.get("owner_id")) == preset.get("my_user")
            ),
            None,
        )

    print(f"\n=== {title} — claim outcomes through week {through} ===")
    print(
        f"Add minus drop, {args.min_weeks}+ weeks of football after the move, "
        f"scored under this league's own settings.\n"
    )
    ours_scored = [s for s in scored if s["roster_id"] == mine]
    theirs = [s for s in scored if s["roster_id"] != mine]
    out = summarise(ours_scored, "US")
    out += summarise(theirs, "the room")
    out += summarise(scored, "everyone")
    print("\n".join(out))
    print("\n" + "\n".join(verdict(ours_scored, theirs)))

    ours = sorted(
        (s for s in scored if s["roster_id"] == mine), key=lambda s: -s["gain"]
    )
    if ours:
        name = lambda sid: (registry.get(sid) or {}).get("full_name", sid)  # noqa: E731
        print("\n  -- our claims, best first --")
        for s in ours:
            print(
                f"  wk{s['leg']:<2} +{name(s['add'])[:22]:22} -{name(s['drop'])[:22]:22}"
                f" ${s['bid']:<3} {s['gain']:+6.1f}pt over {s['weeks']}wk"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
