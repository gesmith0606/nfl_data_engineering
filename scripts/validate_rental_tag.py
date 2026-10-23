"""Does the RENTAL/ENDING tag predict anything? Measure it.

The tag claims a specific thing: a player filling in for a better
same-position team-mate holds a *borrowed* role, and it reverts when that
team-mate comes back. That claim was shipped on reasoning, not evidence. This
script tests it against the season's own record.

    python scripts/validate_rental_tag.py
    python scripts/validate_rental_tag.py --season 2026 --through-week 6

Method: reconstruct every RENTAL situation from the official injury report —
a skill-position player Out in week W, and a lower-ranked team-mate at the
same position who actually played that week. Split by whether the blocker was
still Out in W+1, then compare what happened to the fill-in.

Read the snap-share result, not the points one. Points conflate usage with
touchdown luck, game script and opponent; snap share is the mechanism the tag
actually asserts.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from lineup_setter import roster_gsis_map  # noqa: E402
from sleeper_player_map import load_sleeper_players  # noqa: E402

SKILL = ("QB", "RB", "WR", "TE")
#: A fill-in needs a real role in week W before "he loses it" means anything.
MIN_SNAP_PCT = 20.0
UNRANKED = 10**6


def weekly_stats(season: int, through: int) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for w in range(1, through + 2):
        url = f"https://api.sleeper.app/v1/stats/nfl/regular/{season}/{w}"
        try:
            out[w] = json.load(urllib.request.urlopen(url))
        except Exception:  # noqa: BLE001 — a missing week just shortens the sample
            out[w] = {}
    return out


def snap_pct(stats: Dict[int, dict], sid: str, week: int) -> Optional[float]:
    s = stats.get(week, {}).get(str(sid)) or {}
    played, team = s.get("off_snp"), s.get("tm_off_snp")
    return 100.0 * played / team if played and team else None


def points(stats: Dict[int, dict], sid: str, week: int) -> float:
    return float((stats.get(week, {}).get(str(sid)) or {}).get("pts_ppr") or 0.0)


def out_by_week(season: int, gsis_to_sleeper: Dict[str, str]) -> Dict[int, Set[str]]:
    """``week -> sleeper ids ruled Out`` from the official report."""
    files = sorted(
        glob.glob(
            str(
                REPO_ROOT
                / "data/bronze/players/injuries"
                / f"season={season}"
                / "*.parquet"
            )
        )
    )
    if not files:
        return {}
    inj = pd.read_parquet(files[-1])
    inj = inj[inj.position.isin(SKILL) & (inj.report_status == "Out")]
    return {
        int(w): {
            gsis_to_sleeper[str(g)] for g in grp.gsis_id if gsis_to_sleeper.get(str(g))
        }
        for w, grp in inj.groupby("week")
    }


def describe(label: str, deltas: Sequence[float], unit: str) -> str:
    if not deltas:
        return f"  {label:22} n=  0"
    return (
        f"  {label:22} n={len(deltas):3}  median {statistics.median(deltas):+6.1f}{unit}"
        f"  mean {statistics.mean(deltas):+6.1f}{unit}"
    )


def run(season: int, through: int) -> int:
    registry = load_sleeper_players(max_age_days=7)
    rosters = pd.concat(
        [
            pd.read_parquet(f)
            for f in glob.glob(
                str(REPO_ROOT / "data/bronze/players/rosters/season=*/**/*.parquet"),
                recursive=True,
            )
        ],
        ignore_index=True,
    )
    g2s = roster_gsis_map(rosters)
    stats = weekly_stats(season, through)
    outs = out_by_week(season, g2s)
    if not outs:
        sys.exit("No official Out rows found — cannot reconstruct RENTAL situations")

    def rank(sid: str) -> int:
        r = (registry.get(str(sid)) or {}).get("search_rank")
        return int(r) if isinstance(r, (int, float)) else UNRANKED

    by_team_pos: Dict[Tuple[str, str], List[str]] = {}
    for sid, meta in registry.items():
        if not isinstance(meta, dict) or not meta.get("team"):
            continue
        if meta.get("position") in SKILL:
            by_team_pos.setdefault((meta["team"], meta["position"]), []).append(sid)

    snap_ret: List[float] = []
    snap_stay: List[float] = []
    pts_ret: List[float] = []
    pts_stay: List[float] = []

    for week in range(1, through + 1):
        blockers = outs.get(week, set())
        still_out = outs.get(week + 1, set())
        for blocker in blockers:
            meta = registry.get(str(blocker)) or {}
            key = (meta.get("team"), meta.get("position"))
            if None in key:
                continue
            blocker_rank = rank(blocker)
            for sid in by_team_pos.get(key, []):
                if sid == blocker or sid in blockers or rank(sid) <= blocker_rank:
                    continue
                before = snap_pct(stats, sid, week)
                after = snap_pct(stats, sid, week + 1)
                if before is None or after is None or before < MIN_SNAP_PCT:
                    continue
                returned = blocker not in still_out
                (snap_ret if returned else snap_stay).append(after - before)
                (pts_ret if returned else pts_stay).append(
                    points(stats, sid, week + 1) - points(stats, sid, week)
                )

    print(f"=== RENTAL tag vs outcomes — {season}, weeks 1-{through} ===\n")
    print("Snap share (the mechanism the tag asserts):")
    print(describe("blocker RETURNED", snap_ret, "pp"))
    print(describe("blocker STAYED OUT", snap_stay, "pp"))
    if snap_ret and snap_stay:
        gap = statistics.median(snap_ret) - statistics.median(snap_stay)
        lost_ret = 100 * sum(1 for d in snap_ret if d <= -10) / len(snap_ret)
        lost_stay = 100 * sum(1 for d in snap_stay if d <= -10) / len(snap_stay)
        print(f"\n  difference in medians: {gap:+.1f} percentage points")
        print(
            f"  lost >=10pp of snaps: {lost_ret:.0f}% when he returned"
            f" vs {lost_stay:.0f}% when he did not"
        )
    print("\nFantasy points (noisier — usage is only part of scoring):")
    print(describe("blocker RETURNED", pts_ret, "pt"))
    print(describe("blocker STAYED OUT", pts_stay, "pt"))

    if not (snap_ret and snap_stay):
        print("\n  INCONCLUSIVE: not enough paired observations")
        return 1
    verdict = statistics.median(snap_ret) < statistics.median(snap_stay) - 2.0
    print(
        f"\n  RESULT: {'VALIDATED' if verdict else 'NOT VALIDATED'} — a returning"
        " blocker costs the fill-in materially more snap share"
    )
    return 0 if verdict else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--through-week", type=int, default=6)
    args = ap.parse_args(argv)
    return run(args.season, args.through_week)


if __name__ == "__main__":
    raise SystemExit(main())
