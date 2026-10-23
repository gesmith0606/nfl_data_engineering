#!/usr/bin/env python3
"""Is the young-drop rule supported by evidence, or is it a stated preference?

    python scripts/validate_young_drop.py --league mantis
    python scripts/validate_young_drop.py --league mantis --through-week 6

The skill has said "never drop a young (<=24) player with a role path" since
before the gate existed, and `src/waiver_verdicts.drop_order` now enforces it.
Unlike the bid model (median error $7 against 51 real bids) and the RENTAL tag
(-10.5pp of snap share), that threshold was **chosen, not measured** -- so this
script says plainly what the data can and cannot support.

Two outcomes, and the distinction is the whole point:

* **Points after the drop** -- computable today, and the WRONG mechanism. A
  dynasty rule is about multi-year asset value, not the next three weeks. On
  week-6 2026 Mantis data the sign flipped across adjacent age cutoffs
  (+2.7, -4.9, -3.5, +2.9, +3.4 pts/wk), which is noise at n=34, and a naive
  reading of the <=24 row would have "refuted" a rule it cannot speak to.
* **Market value months later** -- the right mechanism, and not yet possible:
  FantasyCalc serves only ``/values/current``. ``league_context`` now archives
  one compact snapshot per ISO week, so this becomes answerable once a few
  months of history exist. Until then the rule stands on George's instruction,
  which is a legitimate reason -- just not an empirical one.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.lineup_setter import ours_by_sleeper_id, roster_gsis_map  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402
from src.waiver_verdicts import YOUNG_AGE  # noqa: E402
from scripts import set_lineups  # noqa: E402
from scripts.backtest_claim_outcomes import bronze_rosters, claim_rows  # noqa: E402
from scripts.waiver_wire import last_week_actuals, scoring_for  # noqa: E402

HISTORY = REPO_ROOT / "data" / "external" / "fantasycalc" / "history"
CUTOFFS = (22, 23, 24, 25, 26)


def value_history() -> Dict[str, List[Tuple[str, float]]]:
    """``sleeper_id -> [(iso week, value)]`` from the archived snapshots."""
    out: Dict[str, List[Tuple[str, float]]] = {}
    for path in sorted(glob.glob(str(HISTORY / "*.json"))):
        stamp = Path(path).stem.rsplit("_", 1)[-1]
        for row in json.loads(Path(path).read_text(encoding="utf-8")):
            if row.get("value") is not None:
                out.setdefault(str(row["sleeper_id"]), []).append(
                    (stamp, float(row["value"]))
                )
    return out


def sweep_points(
    drops: Sequence[Dict[str, float]], cutoffs: Sequence[int] = CUTOFFS
) -> List[str]:
    """Median points/week after the drop, young vs older, per age cutoff."""
    lines = [
        f"  {'cutoff':10} {'n young':>8} {'young pts/wk':>13}"
        f" {'older pts/wk':>13} {'gap':>7}"
    ]
    gaps = []
    for cut in cutoffs:
        young = [d["per_wk"] for d in drops if d["age"] <= cut]
        older = [d["per_wk"] for d in drops if d["age"] > cut]
        if len(young) < 3 or len(older) < 3:
            lines.append(f"  <= {cut:<7} {len(young):>8}   too few to compare")
            continue
        my, mo = statistics.median(young), statistics.median(older)
        gaps.append(my - mo)
        lines.append(
            f"  <= {cut:<7} {len(young):>8} {my:>13.2f} {mo:>13.2f} {my - mo:>+7.2f}"
        )
    if len(gaps) >= 3 and min(gaps) < 0 < max(gaps):
        lines.append(
            "  -> the sign FLIPS across adjacent cutoffs: noise at this sample "
            "size, and the wrong outcome for a dynasty rule anyway"
        )
    return lines


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--league", default="mantis", help="LEAGUE_PRESETS key (Sleeper)")
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--through-week", type=int, default=0)
    ap.add_argument("--min-weeks", type=int, default=2)
    args = ap.parse_args(argv)

    try:
        preset = config.our_league(args.league)
    except (KeyError, ValueError) as exc:
        sys.exit(exc.args[0])
    lid = str(preset["league_id"])
    league = sleeper_http.get_league(lid)
    if not league:
        sys.exit(f"Sleeper league {lid} unavailable")
    _season, live_week = set_lineups._default_week(args.season)
    through = args.through_week or max(1, live_week - 1)

    scoring = scoring_for(preset, league)
    registry = load_sleeper_players(max_age_days=7)
    gsis_map = roster_gsis_map(bronze_rosters())

    points: Dict[Tuple[str, int], float] = {}
    for wk in range(1, through + 1):
        df = last_week_actuals(args.season, wk, scoring)
        if df.empty:
            continue
        names = dict(zip(df["player_id"].astype(str), df["player_name"]))
        for sid, pts in ours_by_sleeper_id(
            df, dict(registry), gsis_map=dict(gsis_map), full_names=names
        ).items():
            points[(sid, wk)] = pts

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
    drops = []
    for r in claim_rows(txns, through):
        after = list(range(r["leg"] + 1, through + 1))
        if len(after) < args.min_weeks:
            continue
        meta = registry.get(r["drop"]) or {}
        if meta.get("age") is None:
            continue
        got = sum(points.get((r["drop"], w), 0.0) for w in after)
        drops.append({"age": float(meta["age"]), "per_wk": got / len(after)})

    print(f"\n=== young-drop (<= {YOUNG_AGE}) — evidence review, week {through} ===")
    print(f"\n  WRONG MECHANISM (points after the drop), n={len(drops)}:")
    print("\n".join(sweep_points(drops)))

    hist = value_history()
    weeks = sorted({w for vs in hist.values() for w, _ in vs})
    print(
        f"\n  RIGHT MECHANISM (dynasty value change): {len(weeks)} weekly snapshot(s)"
    )
    if len(weeks) < 8:
        print(
            f"    need ~8 to say anything ({', '.join(weeks) or 'none yet'}).\n"
            "    league_context archives one per ISO week from 2026-10-23 on."
        )
        print(
            f"\n  VERDICT: UNVALIDATED BY DESIGN — the <= {YOUNG_AGE} cutoff stands on\n"
            "    George's instruction, not on evidence. That is a legitimate reason;\n"
            "    it is not an empirical one, and the points sweep above cannot settle\n"
            "    it. Re-run once the value history is deep enough."
        )
        return 0
    print("    history is deep enough — extend this script to measure it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
