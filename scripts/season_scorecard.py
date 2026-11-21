#!/usr/bin/env python3
"""Season scorecard: published board vs consensus vs trailing-3 vs actuals.

One table per (week, position) for the PUBLISHED Gold board, Sleeper (the
consensus the repo benchmarks against) and a trailing-3-game average, all on
the same matched player-weeks, plus how many eligible players had no row on
the board at all, floor/ceiling band coverage and our spread relative to
Sleeper's.

Eligible player-week = played (has a Bronze weekly row), skill position,
consensus (Sleeper half-PPR) >= ``--min-consensus`` (default 5, the repo's
cons>=5 population). Matched = eligible AND on our board. An explicit 0.0 row
(an Out player) is a row; only an absent row is "missing".

Usage::

    python scripts/season_scorecard.py --season 2026
    python scripts/season_scorecard.py --season 2026 --weeks 1-9
    python scripts/season_scorecard.py --board-subdir projections_shadow/regen

Writes ``output/grading/season=YYYY/scorecard.{csv,md}`` and
``scorecard_missing.csv`` (the eligible player-weeks with no board row). Unlike
the old grading reports, ``output/grading/`` is tracked, so a scorecard
survives past the CI run that produced it.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
for _p in (os.path.join(_ROOT, "src"), _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from consensus_metrics import CONSENSUS_MIN_PTS, CONSENSUS_POSITIONS  # noqa: E402
from scoring_calculator import calculate_fantasy_points_df  # noqa: E402

logger = logging.getLogger(__name__)

MIN_GROUP_FOR_SPEARMAN = 10  # same floor as consensus_metrics.compute_spearman_rank_corr
POS_ORDER = CONSENSUS_POSITIONS + ["ALL"]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def load_board(data_root: str, season: int, week: int, scoring: str, subdir: str = "projections") -> pd.DataFrame:
    """Latest published (non-``derived``) board for a week; empty if none."""
    pat = os.path.join(data_root, "gold", *subdir.split("/"), f"season={season}", f"week={week}", f"*{scoring}*.parquet")
    files = sorted(f for f in glob.glob(pat) if "derived" not in os.path.basename(f))
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])
    df["week"] = week
    return df


def load_consensus(data_root: str, season: int, week: int, scoring: str, source: str = "sleeper") -> pd.DataFrame:
    """Latest Silver consensus snapshot for a week -> player_id, consensus."""
    f = _latest(os.path.join(data_root, "silver", "external_projections", f"season={season}", f"week={week:02d}", "*.parquet"))
    if f is None:
        return pd.DataFrame(columns=["player_id", "week", "consensus"])
    df = pd.read_parquet(f)
    if "source" in df.columns:
        df = df[df["source"] == source]
    if "scoring_format" in df.columns:
        df = df[df["scoring_format"] == scoring]
    df = df.dropna(subset=["player_id"]).rename(columns={"projected_points": "consensus"})
    df = df.sort_values("consensus", ascending=False).drop_duplicates("player_id")
    df["week"] = week
    return df[["player_id", "week", "consensus"]]


def load_actuals(data_root: str, season: int, scoring: str) -> pd.DataFrame:
    """Per player-week actual points for ``season`` and ``season-1`` (for trailing-3)."""
    parts = []
    for s in (season - 1, season):
        f = _latest(os.path.join(data_root, "bronze", "players", "weekly", f"season={s}", "*.parquet"))
        if f is None:
            continue
        w = pd.read_parquet(f)
        if "season_type" in w.columns:
            w = w[w["season_type"] == "REG"]
        if "air_yards" not in w.columns and "receiving_air_yards" in w.columns:
            w["air_yards"] = w["receiving_air_yards"].fillna(0)
        parts.append(w)
    if not parts:
        return pd.DataFrame()
    wk = pd.concat(parts, ignore_index=True)
    wk = calculate_fantasy_points_df(wk, scoring_format=scoring, output_col="actual_points")
    wk = wk.sort_values("actual_points", ascending=False).drop_duplicates(["player_id", "season", "week"])
    return add_trailing3(wk)


def add_trailing3(actuals: pd.DataFrame) -> pd.DataFrame:
    """Mean of the player's previous (up to) 3 games, never including the current one."""
    out = actuals.sort_values(["player_id", "season", "week"]).copy()
    out["t3"] = out.groupby("player_id")["actual_points"].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build_player_weeks(
    board: pd.DataFrame,
    consensus: pd.DataFrame,
    actuals: pd.DataFrame,
    min_consensus: float = CONSENSUS_MIN_PTS,
) -> pd.DataFrame:
    """Eligible player-weeks with our number (NaN when off the board).

    Args:
        board: published projections with ``player_id``, ``week``,
            ``projected_points`` and optionally floor/ceiling/``projection_source``.
        consensus: ``player_id``, ``week``, ``consensus``.
        actuals: ``player_id``, ``week``, ``position``, ``actual_points``, ``t3``
            (rows for the weeks being scored only).
        min_consensus: consensus floor defining eligibility.

    Returns:
        One row per eligible player-week; ``on_board`` is False for the holes.
    """
    a = actuals[actuals["position"].isin(CONSENSUS_POSITIONS)]
    pw = a.merge(consensus, on=["player_id", "week"], how="inner")
    pw = pw[pw["consensus"] >= min_consensus].copy()
    keep = ["player_id", "week", "projected_points"]
    for c in ("projected_floor", "projected_ceiling", "projection_source"):
        if c in board.columns:
            keep.append(c)
    b = board[keep].drop_duplicates(["player_id", "week"]).rename(
        columns={"projected_points": "ours", "projected_floor": "floor", "projected_ceiling": "ceiling"}
    )
    pw = pw.merge(b, on=["player_id", "week"], how="left")
    pw["on_board"] = pw["ours"].notna()
    if "projection_source" not in pw.columns:
        pw["projection_source"] = np.nan
    # Fallback rows carry Sleeper's own number, so they flatter every gap to Sleeper.
    pw["is_fallback"] = pw["projection_source"].eq("consensus_fallback")
    for c in ("floor", "ceiling"):
        if c not in pw.columns:
            pw[c] = np.nan
    if "player_name" not in pw.columns:
        pw["player_name"] = pw.get("player_display_name", pw["player_id"])
    return pw


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _group_stats(g: pd.DataFrame) -> dict:
    m = g[g["on_board"]]
    out = {
        "n_eligible": len(g),
        "n_missing": int((~g["on_board"]).sum()),
        "n_matched": len(m),
        "n_fallback": int(g["is_fallback"].sum()) if "is_fallback" in g else 0,
    }
    if m.empty:
        return out
    a = m["actual_points"]
    out.update(
        mae_ours=(m["ours"] - a).abs().mean(),
        mae_sleeper=(m["consensus"] - a).abs().mean(),
        mae_t3=(m["t3"] - a).abs().mean(),
        bias_ours=(m["ours"] - a).mean(),
        bias_sleeper=(m["consensus"] - a).mean(),
        n_t3=int(m["t3"].notna().sum()),
    )
    out["gap"] = out["mae_ours"] - out["mae_sleeper"]
    # Same gap with consensus_fallback rows removed from BOTH sides: those rows are
    # Sleeper's own number, so leaving them in pulls the gap toward zero.
    real = m[~m["is_fallback"]] if "is_fallback" in m else m
    if len(real):
        out["gap_no_fallback"] = (real["ours"] - real["actual_points"]).abs().mean() - (
            real["consensus"] - real["actual_points"]
        ).abs().mean()
    # Holes scored as zero (what a user who opens the board sees for that player).
    filled = g["ours"].fillna(0.0)
    out["mae_ours_filled"] = (filled - g["actual_points"]).abs().mean()
    out["gap_filled"] = out["mae_ours_filled"] - (g["consensus"] - g["actual_points"]).abs().mean()
    inband = m.dropna(subset=["floor", "ceiling"])
    out["band_coverage"] = (
        float(((inband["actual_points"] >= inband["floor"]) & (inband["actual_points"] <= inband["ceiling"])).mean())
        if len(inband)
        else np.nan
    )
    sd_s = m["consensus"].std(ddof=0)
    out["sd_ratio"] = m["ours"].std(ddof=0) / sd_s if sd_s > 0 else np.nan
    return out


def _spearman(g: pd.DataFrame, col: str) -> float:
    d = g[g["on_board"]].dropna(subset=[col])
    if len(d) < MIN_GROUP_FOR_SPEARMAN:
        return np.nan
    r, _ = scipy_stats.spearmanr(d[col], d["actual_points"])
    return float(r)


def _mean_rho(pw: pd.DataFrame, col: str) -> float:
    """Mean of within (week, position) Spearman values (consensus_metrics convention)."""
    vals = [_spearman(g, col) for _, g in pw.groupby(["week", "position"])]
    vals = [v for v in vals if not np.isnan(v)]
    return float(np.mean(vals)) if vals else np.nan


def scorecard_rows(pw: pd.DataFrame) -> pd.DataFrame:
    """Per-week x position rows, plus ``ALL`` rows pooled over weeks and/or positions.

    MAE, bias, band coverage and SD ratio pool the matched rows; Spearman is the
    mean of the within (week, position) values, as in ``consensus_metrics``.
    """
    pw = pw.copy()
    pw["week"] = pw["week"].astype(int)
    rows: List[dict] = []
    weeks = sorted(pw["week"].unique())
    for wk in weeks + ["ALL"]:
        sub_w = pw if wk == "ALL" else pw[pw["week"] == wk]
        for pos in POS_ORDER:
            g = sub_w if pos == "ALL" else sub_w[sub_w["position"] == pos]
            if g.empty:
                continue
            r = {"week": str(wk), "position": pos, **_group_stats(g)}
            if wk != "ALL" and pos != "ALL":
                r["rho_ours"], r["rho_sleeper"], r["rho_t3"] = (_spearman(g, c) for c in ("ours", "consensus", "t3"))
            else:
                r["rho_ours"], r["rho_sleeper"], r["rho_t3"] = (_mean_rho(g, c) for c in ("ours", "consensus", "t3"))
            rows.append(r)
    cols = [
        "week", "position", "n_eligible", "n_missing", "n_matched", "n_fallback", "mae_ours", "mae_sleeper", "mae_t3", "gap",
        "gap_no_fallback", "bias_ours", "bias_sleeper", "rho_ours", "rho_sleeper", "rho_t3", "mae_ours_filled", "gap_filled",
        "band_coverage", "sd_ratio", "n_t3",
    ]  # fmt: skip
    return pd.DataFrame(rows).reindex(columns=cols)


def render_markdown(rows: pd.DataFrame, weeks_without_board: Iterable[int], season: int, scoring: str, source_counts: Optional[pd.DataFrame] = None) -> str:
    """Human-readable summary: headline, per-position table, per-week table, caveats."""

    def f(v, nd=2, signed=False):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "-"
        return f"{v:+.{nd}f}" if signed else f"{v:.{nd}f}"

    lines = [
        f"# Season scorecard - {season} {scoring}",
        "",
        "Published board vs Sleeper (consensus) vs trailing-3-game average, matched player-weeks "
        "(played, consensus >= 5, on our board). Gap = ours - Sleeper MAE (positive = we are worse).",
        "",
    ]
    nb = sorted(weeks_without_board)
    if nb:
        lines += [f"Week {', '.join(str(w) for w in nb)}: no published board - excluded from every number below.", ""]
    lines += ["## By position (all weeks pooled)", "",
              "| Pos | n elig | missing | fallback | n | MAE ours | MAE Sleeper | MAE t3 | gap | gap (no fallback) | gap (miss=0) | rho ours | rho Sleeper | rho t3 | band cov | SD ratio |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for _, r in rows[rows["week"] == "ALL"].iterrows():
        lines.append(
            f"| {r.position} | {int(r.n_eligible)} | {int(r.n_missing)} | {int(r.n_fallback)} | {int(r.n_matched)} | {f(r.mae_ours)} | {f(r.mae_sleeper)} | "
            f"{f(r.mae_t3)} | {f(r.gap, 3, True)} | {f(r.gap_no_fallback, 3, True)} | {f(r.gap_filled, 3, True)} | {f(r.rho_ours, 3)} | {f(r.rho_sleeper, 3)} | "
            f"{f(r.rho_t3, 3)} | {f(r.band_coverage)} | {f(r.sd_ratio)} |"
        )
    lines += ["", "## By week (all positions)", "",
              "| Week | n elig | missing | fallback rows | MAE ours | MAE Sleeper | MAE t3 | gap | gap (no fallback) | gap (miss=0) |", "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for _, r in rows[(rows["week"] != "ALL") & (rows["position"] == "ALL")].iterrows():
        lines.append(
            f"| {r.week} | {int(r.n_eligible)} | {int(r.n_missing)} | {int(r.n_fallback)} | {f(r.mae_ours)} | {f(r.mae_sleeper)} | {f(r.mae_t3)} | "
            f"{f(r.gap, 3, True)} | {f(r.gap_no_fallback, 3, True)} | {f(r.gap_filled, 3, True)} |"
        )
    lines += ["", "## Week x position", "",
              "| Week | Pos | n | missing | MAE ours | MAE Sleeper | MAE t3 | bias ours | rho ours | rho Sleeper |", "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for _, r in rows[(rows["week"] != "ALL") & (rows["position"] != "ALL")].iterrows():
        lines.append(
            f"| {r.week} | {r.position} | {int(r.n_matched)} | {int(r.n_missing)} | {f(r.mae_ours)} | {f(r.mae_sleeper)} | {f(r.mae_t3)} | "
            f"{f(r.bias_ours, 2, True)} | {f(r.rho_ours, 3)} | {f(r.rho_sleeper, 3)} |"
        )
    if source_counts is not None and not source_counts.empty:
        cols = list(source_counts.columns)
        lines += ["", "## Board rows by projection_source", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in source_counts.itertuples(index=False)]
    lines += [
        "",
        "Definitions: MAE/bias pool matched rows. rho = mean of within (week, position) Spearman, groups of >= 10 "
        "(`src/consensus_metrics.py`). `gap (miss=0)` scores eligible players with no board row as 0. "
        "`consensus_fallback` rows carry Sleeper's own number, so `gap` flatters us by their share; `gap (no fallback)` drops them from both sides. "
        "band cov = share with floor <= actual <= ceiling. SD ratio = SD(ours)/SD(Sleeper) on matched rows. "
        "t3 columns skip players with no prior game (n_t3 in the CSV).",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_weeks(spec: Optional[str]) -> Optional[List[int]]:
    if not spec:
        return None
    if "-" in spec:
        lo, hi = spec.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in spec.split(",")]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--scoring", default="half_ppr")
    ap.add_argument("--weeks", help="e.g. 1-9 or 1,2,5 (default: every week with actuals)")
    ap.add_argument("--min-consensus", type=float, default=CONSENSUS_MIN_PTS)
    ap.add_argument("--data-root", default=os.path.join(_ROOT, "data"))
    ap.add_argument("--board-subdir", default="projections", help="gold sub-path, e.g. projections_shadow/<tag>")
    ap.add_argument("--out-dir", default=None, help="default output/grading/season=YYYY")
    ap.add_argument("--label", default="", help="suffix for the output files, e.g. _regen")
    args = ap.parse_args(argv)

    actuals = load_actuals(args.data_root, args.season, args.scoring)
    if actuals.empty:
        print("No Bronze weekly actuals found.", file=sys.stderr)
        return 2
    cur = actuals[actuals["season"] == args.season]
    weeks = _parse_weeks(args.weeks) or sorted(cur["week"].unique())

    pws, no_board, sources = [], [], []
    for wk in weeks:
        board = load_board(args.data_root, args.season, wk, args.scoring, args.board_subdir)
        cons = load_consensus(args.data_root, args.season, wk, args.scoring)
        if board.empty:
            no_board.append(wk)
            continue
        if "projection_source" in board.columns:
            sources.append(board["projection_source"].value_counts().rename(wk))
        pws.append(build_player_weeks(board, cons, cur[cur["week"] == wk], args.min_consensus))
    if not pws:
        print("No boards found for the requested weeks.", file=sys.stderr)
        return 2
    pw = pd.concat(pws, ignore_index=True)
    rows = scorecard_rows(pw)
    src = pd.DataFrame(sources).fillna(0).astype(int).rename_axis("week").reset_index() if sources else None

    out_dir = args.out_dir or os.path.join(_ROOT, "output", "grading", f"season={args.season}")
    os.makedirs(out_dir, exist_ok=True)
    rows.round(6).to_csv(os.path.join(out_dir, f"scorecard{args.label}.csv"), index=False)
    miss = pw[~pw["on_board"]][["week", "player_id", "player_name", "position", "recent_team", "consensus", "actual_points"]]
    miss.sort_values(["week", "consensus"], ascending=[True, False]).to_csv(
        os.path.join(out_dir, f"scorecard_missing{args.label}.csv"), index=False
    )
    md = render_markdown(rows, no_board, args.season, args.scoring, src)
    with open(os.path.join(out_dir, f"scorecard{args.label}.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    allr = rows[(rows["week"] == "ALL") & (rows["position"] == "ALL")].iloc[0]
    print(
        f"n eligible {int(allr.n_eligible)}, missing {int(allr.n_missing)}, MAE ours {allr.mae_ours:.3f} "
        f"Sleeper {allr.mae_sleeper:.3f} t3 {allr.mae_t3:.3f}; gap {allr.gap:+.3f} (miss=0 {allr.gap_filled:+.3f}); "
        f"weeks without board: {no_board or 'none'}"
    )
    print(
        f"gap excluding consensus_fallback rows: {allr.gap_no_fallback:+.3f}; fallback rows: {int(allr.n_fallback)} "
        f"(by week {({int(r.week): int(r.n_fallback) for r in rows[(rows['position'] == 'ALL') & (rows['week'] != 'ALL')].itertuples()})})"
    )
    print(f"Wrote {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
