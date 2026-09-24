#!/usr/bin/env python3
"""Grade a SHADOW Gold board vs production vs Sleeper vs actuals.

Companion to the weekly cron's shadow step (``generate_projections.py
--shadow-tag <tag>``), which writes an unpublished board to
``data/gold/projections_shadow/<tag>/season=YYYY/week=W/``. For each graded
week this loads, on one matched population:

- production: ``data/gold/projections/season=YYYY/week=W/`` (latest)
- shadow:     ``data/gold/projections_shadow/<tag>/season=YYYY/week=W/``
- sleeper:    Silver external projections (source=sleeper), when present
- actuals:    Bronze weekly stats scored in ``--scoring``

and reports MAE, bias (mean projected - actual) and Spearman by position,
per week and pooled across all requested weeks, plus the shadow-vs-production
MAE delta and a verdict against the promotion bar recorded in
``.planning/EARLY_SEASON_PRIOR_GATE.md`` ("Shadow run (2026 weeks 3-6)").

Population ("relevant"): QB/RB/WR/TE players present in production, shadow
and actuals where any available source projected >= 5 points; when Sleeper
exists for a week, rows without a Sleeper projection are dropped so all
three sources are graded on the identical matched set (Sleeper's MAE then
cancels out of the shadow-vs-production gap delta).

Fail-open: a week missing any input is listed under ``missing_weeks`` and
skipped; the script exits 0 unless the arguments are invalid.

Usage::

    python scripts/grade_shadow.py --season 2026 --weeks 3 4 5 6
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
for _p in (_PROJECT_ROOT, os.path.join(_PROJECT_ROOT, "src"), _SCRIPT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from consensus_metrics import (  # noqa: E402
    CONSENSUS_MIN_PTS,
    CONSENSUS_POSITIONS,
    compute_spearman_rank_corr,
)
from weekly_grading_report import (  # noqa: E402
    _json_safe,
    _load_actuals,
    _load_consensus,
    _load_gold_projections,
)

logger = logging.getLogger(__name__)

SOURCES = ("production", "shadow", "sleeper")

#: Promotion bar (pre-registered in EARLY_SEASON_PRIOR_GATE.md, mirrors the
#: original gate's primary + per-position guard on a matched population).
PROMOTION_MAE_IMPROVEMENT = 0.10  # pooled overall: shadow MAE <= prod MAE - 0.10
POSITION_WORSEN_TOLERANCE = 0.05  # no position's pooled MAE worse by > 0.05
REQUIRED_WEEKS = (3, 4, 5, 6)


def build_grading_frame(
    prod_df: pd.DataFrame,
    shadow_df: pd.DataFrame,
    sleeper_df: pd.DataFrame,
    actuals_df: pd.DataFrame,
    season: int,
    week: int,
    min_pts: float = CONSENSUS_MIN_PTS,
) -> pd.DataFrame:
    """Join the three projection sources to actuals for one (season, week).

    Args:
        prod_df: Production Gold board (``player_id``, ``position``,
            ``projected_points``).
        shadow_df: Shadow Gold board (same schema).
        sleeper_df: Silver Sleeper consensus (``player_id``,
            ``consensus_proj``); may be empty.
        actuals_df: Actual points (``player_id``, ``actual_points``).
        season: NFL season.
        week: NFL week.
        min_pts: Relevance threshold on the max available projection.

    Returns:
        One row per relevant player with ``player_id, player_name, position,
        season, week, production, shadow, sleeper, actual``. ``sleeper`` is
        all-NaN when no Sleeper data exists for the week. Empty when any of
        production / shadow / actuals is empty.
    """
    need = {"player_id", "projected_points"}
    if (
        prod_df.empty
        or shadow_df.empty
        or actuals_df.empty
        or not need <= set(prod_df.columns)
        or not need <= set(shadow_df.columns)
        or "actual_points" not in actuals_df.columns
    ):
        return pd.DataFrame()

    def _ids(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["player_id"] = out["player_id"].astype(str).str.strip()
        return out.drop_duplicates("player_id", keep="first")

    prod = _ids(prod_df)
    keep = [c for c in ("player_id", "player_name", "position") if c in prod.columns]
    frame = prod[keep + ["projected_points"]].rename(
        columns={"projected_points": "production"}
    )
    frame = frame.merge(
        _ids(shadow_df)[["player_id", "projected_points"]].rename(
            columns={"projected_points": "shadow"}
        ),
        on="player_id",
        how="inner",
    )
    acts = actuals_df.copy()
    acts["player_id"] = acts["player_id"].astype(str).str.strip()
    acts = acts.sort_values("actual_points", ascending=False).drop_duplicates(
        "player_id"
    )
    frame = frame.merge(
        acts[["player_id", "actual_points"]].rename(
            columns={"actual_points": "actual"}
        ),
        on="player_id",
        how="inner",
    )
    if (
        not sleeper_df.empty
        and {"player_id", "consensus_proj"} <= set(sleeper_df.columns)
        and sleeper_df["consensus_proj"].notna().any()
    ):
        slp = _ids(sleeper_df)[["player_id", "consensus_proj"]].rename(
            columns={"consensus_proj": "sleeper"}
        )
        frame = frame.merge(slp, on="player_id", how="inner")
    else:
        frame["sleeper"] = np.nan

    if "position" not in frame.columns:
        return pd.DataFrame()
    frame = frame[frame["position"].isin(CONSENSUS_POSITIONS)]
    frame = frame.dropna(subset=["production", "shadow", "actual"])
    best = frame[["production", "shadow", "sleeper"]].max(axis=1, skipna=True)
    frame = frame[best >= min_pts].copy()
    frame["season"] = int(season)
    frame["week"] = int(week)
    return frame.reset_index(drop=True)


def grade_frame(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """MAE / bias / Spearman per source, by position plus an ``ALL`` row.

    Spearman is the mean within-week rank correlation
    (``consensus_metrics.compute_spearman_rank_corr``, >= 10 players/week).

    Args:
        frame: Output of :func:`build_grading_frame` (one or many weeks).

    Returns:
        List of dicts: ``position, n, <src>_mae, <src>_bias, <src>_spearman``
        for each available source, plus ``shadow_minus_prod_mae``.
    """
    if frame.empty:
        return []
    sources = [s for s in SOURCES if s in frame and frame[s].notna().any()]
    rows: List[Dict[str, Any]] = []
    groups = [(pos, frame[frame["position"] == pos]) for pos in CONSENSUS_POSITIONS]
    groups.append(("ALL", frame))
    for pos, grp in groups:
        if grp.empty:
            continue
        row: Dict[str, Any] = {"position": pos, "n": int(len(grp))}
        for src in sources:
            err = grp[src] - grp["actual"]
            row[f"{src}_mae"] = float(err.abs().mean())
            row[f"{src}_bias"] = float(err.mean())
            row[f"{src}_spearman"] = compute_spearman_rank_corr(
                grp, src, "actual", position=pos
            )
        row["shadow_minus_prod_mae"] = row["shadow_mae"] - row["production_mae"]
        rows.append(row)
    return rows


def promotion_verdict(
    pooled: List[Dict[str, Any]], weeks_graded: Sequence[int]
) -> Dict[str, Any]:
    """Score the pooled table against the promotion bar.

    Args:
        pooled: :func:`grade_frame` output over all graded weeks.
        weeks_graded: Weeks that actually had all inputs.

    Returns:
        Dict with ``verdict`` (``SHIP`` / ``HOLD`` / ``INTERIM`` /
        ``NO DATA``), the measured overall delta and any failing positions.
    """
    overall = next((r for r in pooled if r["position"] == "ALL"), None)
    if overall is None:
        return {"verdict": "NO DATA", "reason": "no graded weeks"}
    delta = overall["shadow_minus_prod_mae"]
    worse = [
        r["position"]
        for r in pooled
        if r["position"] != "ALL"
        and r["shadow_minus_prod_mae"] > POSITION_WORSEN_TOLERANCE
    ]
    passes = delta <= -PROMOTION_MAE_IMPROVEMENT and not worse
    missing = [w for w in REQUIRED_WEEKS if w not in set(weeks_graded)]
    if missing:
        verdict = "INTERIM"
    else:
        verdict = "SHIP" if passes else "HOLD"
    return {
        "verdict": verdict,
        "overall_shadow_minus_prod_mae": delta,
        "required_improvement": PROMOTION_MAE_IMPROVEMENT,
        "positions_worse_than_tolerance": worse,
        "would_pass_on_current_data": bool(passes),
        "weeks_still_missing": missing,
    }


def grade_weeks(
    season: int,
    weeks: Sequence[int],
    scoring: str = "half_ppr",
    shadow_tag: str = "early_season_prior",
    data_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Load, grade and pool the shadow board for each requested week.

    Args:
        season: NFL season.
        weeks: Weeks to grade.
        scoring: Scoring format.
        shadow_tag: Shadow board tag (``projections_shadow/<tag>/``).
        data_root: Data root (default ``<project>/data``).

    Returns:
        Report dict: ``per_week`` tables, ``pooled`` table,
        ``missing_weeks`` (week -> reason) and ``promotion`` verdict.
    """
    data_root = data_root or os.path.join(_PROJECT_ROOT, "data")
    frames, per_week, missing = [], {}, {}
    for week in weeks:
        try:
            prod = _load_gold_projections(data_root, season, week, scoring)
            shadow = _load_gold_projections(
                data_root,
                season,
                week,
                scoring,
                subdir=f"projections_shadow/{shadow_tag}",
            )
            actuals = _load_actuals(data_root, season, week, scoring)
            sleeper = _load_consensus(data_root, season, week, scoring, "sleeper")
        except Exception as exc:  # fail-open: one bad week never kills the report
            logger.warning("week %s load failed: %s", week, exc)
            missing[week] = f"load error: {exc}"
            continue
        for label, df in (
            ("production board", prod),
            ("shadow board", shadow),
            ("actuals", actuals),
        ):
            if df.empty:
                missing[week] = f"no {label}"
                break
        if week in missing:
            continue
        frame = build_grading_frame(prod, shadow, sleeper, actuals, season, week)
        if frame.empty:
            missing[week] = "no matched relevant players"
            continue
        frames.append(frame)
        per_week[week] = grade_frame(frame)

    pooled_frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    pooled = grade_frame(pooled_frame)
    return {
        "season": season,
        "weeks_requested": list(weeks),
        "weeks_graded": sorted(per_week),
        "shadow_tag": shadow_tag,
        "scoring": scoring,
        "per_week": per_week,
        "pooled": pooled,
        "missing_weeks": missing,
        "promotion": promotion_verdict(pooled, sorted(per_week)),
    }


def _fmt(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.3f}"


def render_table(rows: List[Dict[str, Any]]) -> str:
    """Render a :func:`grade_frame` table as Markdown."""
    if not rows:
        return "_no data_\n"
    sources = [s for s in SOURCES if f"{s}_mae" in rows[0]]
    head = ["Pos", "n"]
    for s in sources:
        head += [f"{s} MAE", f"{s} bias", f"{s} rho"]
    head.append("shadow−prod MAE")
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [r["position"], str(r["n"])]
        for s in sources:
            cells += [
                f"{r[f'{s}_mae']:.3f}",
                f"{r[f'{s}_bias']:+.2f}",
                _fmt(r[f"{s}_spearman"]),
            ]
        cells.append(f"{r['shadow_minus_prod_mae']:+.3f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def render_markdown(report: Dict[str, Any]) -> str:
    """Human-readable Markdown for the whole report."""
    p = report["promotion"]
    out = [
        f"# Shadow grading — {report['shadow_tag']} — season {report['season']}",
        "",
        f"Weeks graded: {report['weeks_graded'] or 'none'} "
        f"(requested {report['weeks_requested']}); scoring {report['scoring']}.",
        "",
        f"**Promotion verdict: {p['verdict']}**",
    ]
    if "overall_shadow_minus_prod_mae" in p:
        out.append(
            f"Pooled overall shadow−production MAE: "
            f"{p['overall_shadow_minus_prod_mae']:+.3f} "
            f"(bar: <= −{p['required_improvement']:.2f}; positions worse than "
            f"+{POSITION_WORSEN_TOLERANCE:.2f}: {p['positions_worse_than_tolerance'] or 'none'})"
        )
    out += ["", "## Pooled", "", render_table(report["pooled"])]
    for week, rows in sorted(report["per_week"].items()):
        out += [f"## Week {week}", "", render_table(rows)]
    if report["missing_weeks"]:
        out += ["## Skipped weeks", ""]
        out += [
            f"- week {w}: {why}" for w, why in sorted(report["missing_weeks"].items())
        ]
    return "\n".join(out) + "\n"


def main() -> int:
    """CLI entry point. Returns 0 (fail-open) unless arguments are invalid."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--weeks", type=int, nargs="+", required=True)
    parser.add_argument(
        "--scoring", default="half_ppr", choices=["half_ppr", "ppr", "standard"]
    )
    parser.add_argument("--shadow-tag", default="early_season_prior")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()
    if any(not 1 <= w <= 18 for w in args.weeks):
        print(f"ERROR: weeks must be 1-18, got {args.weeks}", file=sys.stderr)
        return 1

    report = grade_weeks(
        args.season, args.weeks, args.scoring, args.shadow_tag, args.data_root
    )
    md = render_markdown(report)
    print(md)

    output_root = args.output_root or os.path.join(_PROJECT_ROOT, "output", "grading")
    season_dir = os.path.join(output_root, f"season={args.season}")
    os.makedirs(season_dir, exist_ok=True)
    stem = f"shadow_{args.shadow_tag}_weeks_{min(args.weeks)}-{max(args.weeks)}"
    with open(os.path.join(season_dir, f"{stem}.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(os.path.join(season_dir, f"{stem}.json"), "w", encoding="utf-8") as fh:
        json.dump(_json_safe(report), fh, indent=2)
    print(f"Written: {os.path.join(season_dir, stem)}.{{md,json}}")
    if report["missing_weeks"]:
        print(
            f"::warning::grade_shadow skipped weeks {sorted(report['missing_weeks'])}: "
            f"{report['missing_weeks']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
