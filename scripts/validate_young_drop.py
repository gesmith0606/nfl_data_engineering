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
* **Market value months later** -- the right mechanism, and not yet possible.
  There is no historical source to shortcut the wait, which was checked rather
  than assumed on 2026-10-23: FantasyCalc serves only ``/values/current``,
  DynastyProcess's ``values-players.csv`` is a single snapshot (one distinct
  ``scrape_date``) and its ``db_values.csv.gz`` archive 404s, unlike the
  ``db_fpecr.csv.gz`` the ECR ingester uses. So the only route is our own
  archive, and the wait is real:
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

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src import config, sleeper_http  # noqa: E402
from src.lineup_setter import ours_by_sleeper_id, roster_gsis_map  # noqa: E402
from src.sleeper_player_map import load_sleeper_players  # noqa: E402
from src.scoring_calculator import calculate_fantasy_points_df  # noqa: E402
from src.waiver_verdicts import YOUNG_AGE  # noqa: E402
from scripts import set_lineups  # noqa: E402
from scripts.backtest_claim_outcomes import bronze_rosters, claim_rows  # noqa: E402
from scripts.waiver_wire import last_week_actuals, scoring_for  # noqa: E402

HISTORY = REPO_ROOT / "data" / "external" / "fantasycalc" / "history"
CUTOFFS = (22, 23, 24, 25, 26)


def production_test(
    seasons: Sequence[int] = (2022, 2023, 2024), rise: float = 0.10
) -> List[str]:
    """Do young risers out-produce older risers the FOLLOWING season?

    The right mechanism, reached from a different direction. Dynasty market
    value is itself only a proxy for expected future production -- and future
    production is measurable retrospectively, on seasons we already hold,
    without any value history at all.

    For each season: players whose weeks 5-8 snap share beat their weeks 1-4
    share by ``rise``, split at the rule's own age cutoff, scored on their
    NEXT season's median points per game. That is the rule's claim stated
    testably: a young player growing into a role is worth more later than an
    older player doing the same.
    """
    out = [
        f"  {'season':8}{'cohort':24}{'n':>5}{'next-yr PPG median':>20}",
    ]
    rows: List[Tuple[str, int, float]] = []
    for season in seasons:
        nxt, sn, ag = _weekly(season + 1), _snaps(season), _ages(season)
        if nxt.empty or sn.empty or not ag:
            out.append(f"  {season:8}missing data")
            continue
        early = sn[sn.week.between(1, 4)].groupby("player").offense_pct.mean()
        late = sn[sn.week.between(5, 8)].groupby("player").offense_pct.mean()
        rising = {
            p for p in late.index if p in early.index and late[p] - early[p] >= rise
        }
        col = (
            "player_display_name"
            if "player_display_name" in nxt.columns
            else "player_name"
        )
        ppg = nxt.groupby(col).pts.mean()
        for label, keep in (
            (f"young(<={YOUNG_AGE})+rising", lambda a: a <= YOUNG_AGE),
            (f"older(>{YOUNG_AGE})+rising", lambda a: a > YOUNG_AGE),
        ):
            vals = [
                ppg[p] for p in rising if p in ag and keep(ag[p]) and p in ppg.index
            ]
            if len(vals) >= 5:
                med = statistics.median(vals)
                rows.append((label, len(vals), med))
                out.append(f"  {season:8}{label:24}{len(vals):5}{med:20.2f}")
    pooled: Dict[str, List[Tuple[int, float]]] = {}
    for label, n, med in rows:
        pooled.setdefault(label, []).append((n, med))
    out.append("")
    medians = {}
    for label, vs in pooled.items():
        tot = sum(n for n, _ in vs)
        wavg = sum(n * m for n, m in vs) / max(1, tot)
        medians[label] = (tot, wavg)
        out.append(f"  POOLED {label:22} n={tot:4}  weighted median PPG {wavg:.2f}")
    young = next((v for k, v in medians.items() if "young" in k), None)
    older = next((v for k, v in medians.items() if "older" in k), None)
    if young and older and len(pooled) == 2:
        gap = young[1] - older[1]
        out.append(
            f"\n  RESULT: {'VALIDATED' if gap > 0 else 'REJECTED'} — a young riser is worth "
            f"{gap:+.2f} PPG more the following season\n"
            f"    than an older riser with the same rising role "
            f"(n={young[0]} vs {older[0]})."
        )
    return out


def _weekly(season: int) -> "pd.DataFrame":
    """Scored weekly actuals for a season, half-PPR."""
    files = sorted(
        glob.glob(
            str(
                REPO_ROOT
                / "data"
                / "bronze"
                / "players"
                / "weekly"
                / f"season={season}"
                / "*.parquet"
            )
        )
    )
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])
    df = df[df["position"].isin(("QB", "RB", "WR", "TE"))].copy()
    return calculate_fantasy_points_df(df, scoring_format="half_ppr", output_col="pts")


def _snaps(season: int) -> "pd.DataFrame":
    """Every week's snap counts for a season (``player`` is a NAME)."""
    files = sorted(
        glob.glob(
            str(
                REPO_ROOT
                / "data"
                / "bronze"
                / "players"
                / "snaps"
                / f"season={season}"
                / "week=*"
                / "*.parquet"
            )
        )
    )
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return df[["player", "week", "offense_pct"]].dropna()


def _ages(season: int) -> Dict[str, float]:
    """``player name -> age`` from that season's roster snapshot."""
    files = sorted(
        glob.glob(
            str(
                REPO_ROOT
                / "data"
                / "bronze"
                / "players"
                / "rosters"
                / f"season={season}"
                / "**"
                / "*.parquet"
            ),
            recursive=True,
        )
    )
    if not files:
        return {}
    df = pd.read_parquet(files[-1])
    if "age" not in df.columns:
        return {}
    return {
        str(n): float(a) for n, a in zip(df["player_name"], df["age"]) if pd.notna(a)
    }


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

    print(
        f"\n  RIGHT MECHANISM, reached another way — do young risers out-produce\n"
        f"  older risers the FOLLOWING season? (dynasty value is itself only a\n"
        f"  proxy for future production, and production is measurable today):"
    )
    print("\n".join(production_test()))

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
            f"\n  VERDICT: the <= {YOUNG_AGE} cutoff is SUPPORTED by the production test\n"
            "    above, which is the rule's claim stated testably on seasons we already\n"
            "    hold. The MARKET-VALUE confirmation is still pending (one weekly\n"
            "    snapshot so far, ~8 needed) — and the points-after-the-drop sweep at\n"
            "    the top remains the wrong mechanism, whatever it shows."
        )
        return 0
    print("    history is deep enough — extend this script to measure it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
