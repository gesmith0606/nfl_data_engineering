#!/usr/bin/env python3
"""
Run the pre-registered props-blend backtest gate on the archive-backfilled data.

Gate is quoted VERBATIM from .planning/PROP_IMPLIED_DECISION.md ("Backtest
plan", written 2026-06-12, never previously executed):

    Window: 2023 w5-18 + 2024 w1-18 (props history starts May 2023; 2025
    stays sealed).
    Step 1 (benchmark): MAE + within-position-week Spearman of
    prop_implied_points alone vs our heuristic vs Sleeper consensus on
    matched player-weeks.
    Step 2 (blend): proj' = (1-lambda)*proj + lambda*prop_implied_points,
    lambda swept per position in the heuristic lab. Players without props
    (deep bench) keep lambda=0.
    Step 3 (gate): consensus-matched eval. SHIP if WR/RB MAE gap improves
    >=0.05 OR Spearman gap narrows >=0.02 at either position, no QB/TE
    regression.
    KILL if the blend moves <0.02 at every position.

This script does NOT reimplement any metric or blend math — it imports
``apply_props_blend`` / ``compute_prop_implied_points`` from
``src/prop_implied.py`` (the exact machinery ``--props-blend`` on
``generate_projections.py`` uses in production) and ``compute_mae_gap`` /
``compute_spearman_rank_corr`` / ``apply_consensus_filter`` from
``src/consensus_metrics.py`` (the single source of truth every other
backtest/grading report in this repo uses). It only adds the per-week loop
needed because ``backtest_projections.py`` has no ``--props-blend`` wiring
(the flag only exists on ``generate_projections.py``, which reads a single
*latest* forward-capture snapshot — not shaped for a multi-week historical
archive).

BASELINE = the frozen 2022-2024 matched population already on disk
(``output/backtest/pooled_2022_2024_{sleeper,espn}_matched.csv``), produced
by ``backtest_projections.py`` in the same repo state as what's live now
(reused verbatim, same precedent ``OPPORTUNITY_SCAN_2026_08_16.md`` §Method
note used — "reused, did not regenerate, the exact matched population").
TREATED = the same rows, same session, with ``apply_props_blend`` applied
per-week using the archive-backfilled props
(``scripts/ingest_props_archive.py`` output). Untouched/unmatched slices are
byte-identical between the two by construction (only ``projected_points``
for players with in-window prop coverage changes).
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prop_implied import (  # noqa: E402
    CORE_MARKETS_BY_POS,
    PROPS_BLEND_LAMBDAS,
    apply_props_blend,
    compute_prop_implied_points,
)
from src.utils import normalize_player_name  # noqa: E402
from consensus_metrics import (  # noqa: E402
    CONSENSUS_MIN_PTS,
    apply_consensus_filter,
    build_position_table,
    compute_mae_gap,
    compute_spearman_rank_corr,
)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
POOLED_DIR = os.path.join(PROJECT_ROOT, "output", "backtest")
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze", "odds_api", "props")

# Gate window, quoted verbatim from PROP_IMPLIED_DECISION.md.
WINDOW = [(2023, w) for w in range(5, 19)] + [(2024, w) for w in range(1, 19)]

SOURCES = ["sleeper", "espn"]


def build_id_to_full_name() -> pd.Series:
    """player_id -> full display name, from Bronze player_weekly.

    NECESSARY BRIDGE: ``output/backtest/pooled_*_matched.csv`` (produced by
    ``backtest_projections.py``) stores ``player_name`` in the backtester's
    own abbreviated convention ("C.McCaffrey"), but the archive (and the
    live props pipeline) carries full names ("Christian McCaffrey") as
    scraped from FanDuel. ``normalize_player_name`` cannot bridge that gap
    (it strips punctuation, not abbreviation) — everything would silently
    0%-match without this. Joins on the reliable ``player_id`` (nflverse
    gsis_id) both frames already share.
    """
    frames = []
    for season in (2023, 2024):
        pattern = os.path.join(
            PROJECT_ROOT, "data", "bronze", "players", "weekly", f"season={season}", "*.parquet"
        )
        files = sorted(__import__("glob").glob(pattern))
        if files:
            frames.append(pd.read_parquet(files[-1])[["player_id", "player_display_name"]])
    if not frames:
        return pd.Series(dtype=object)
    combined = pd.concat(frames, ignore_index=True).drop_duplicates("player_id")
    return combined.set_index("player_id")["player_display_name"]


def load_pooled(source: str, id_to_name: pd.Series) -> pd.DataFrame:
    path = os.path.join(POOLED_DIR, f"pooled_2022_2024_{source}_matched.csv")
    df = pd.read_csv(path)
    window_df = df[df.set_index(["season", "week"]).index.isin(WINDOW)].copy()
    window_df["player_name_abbrev"] = window_df["player_name"]
    mapped = window_df["player_id"].map(id_to_name)
    unmapped = mapped.isna().sum()
    if unmapped:
        print(
            f"  [{source}] {unmapped}/{len(window_df)} player-weeks have no "
            "player_id -> full-name mapping (e.g. traded/retired edge cases) "
            "— they keep the abbreviated name and will never match the "
            "archive (undercounts coverage by this amount, not a false SHIP)."
        )
    window_df["player_name"] = mapped.fillna(window_df["player_name_abbrev"])
    return window_df


def load_archive() -> pd.DataFrame:
    frames = []
    for season in (2023, 2024):
        path = os.path.join(ARCHIVE_DIR, f"season={season}", f"props_archive_{season}.parquet")
        frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True)


def coverage_mask(proj: pd.DataFrame, implied_df: pd.DataFrame) -> pd.Series:
    """True where a player-week has the position's CORE market(s) covered.

    Mirrors the exact coverage check inside ``apply_props_blend`` (not a new
    metric — extracted so it can be measured for QB/TE too, whose lambda=0
    skips this check internally and never surfaces it).
    """
    if implied_df is None or implied_df.empty:
        return pd.Series(False, index=proj.index)
    lookup = implied_df.drop_duplicates("name_key").set_index("name_key")
    keys = proj["player_name"].map(normalize_player_name)
    markets = keys.map(lookup["prop_markets"]) if "prop_markets" in lookup else pd.Series(index=proj.index)
    out = pd.Series(False, index=proj.index)
    for pos, core in CORE_MARKETS_BY_POS.items():
        pos_mask = proj["position"] == pos
        ok = markets.map(lambda m: isinstance(m, set) and core.issubset(m))
        out |= pos_mask & ok.fillna(False)
    return out


def run_blend_for_source(pooled: pd.DataFrame, archive: pd.DataFrame) -> pd.DataFrame:
    """Apply the props blend week-by-week; return the treated frame (same
    rows/order as ``pooled``, only ``projected_points`` changes for covered
    player-weeks)."""
    treated_frames = []
    for season, week in WINDOW:
        week_matched = pooled[(pooled["season"] == season) & (pooled["week"] == week)].copy()
        if week_matched.empty:
            continue
        week_props = archive[(archive["season"] == season) & (archive["week"] == week)]
        if week_props.empty:
            week_matched["prop_implied_points"] = float("nan")
            week_matched["prop_anchor_gap"] = float("nan")
            week_matched["_covered"] = False
            treated_frames.append(week_matched)
            continue
        implied = compute_prop_implied_points(week_props, scoring_format="half_ppr")
        week_matched["_covered"] = coverage_mask(week_matched, implied)
        blended = apply_props_blend(week_matched, implied, lambdas=PROPS_BLEND_LAMBDAS)
        blended["_covered"] = week_matched["_covered"].values
        treated_frames.append(blended)
    return pd.concat(treated_frames, ignore_index=True)


def gap_table(df: pd.DataFrame) -> dict:
    filtered = apply_consensus_filter(df, weeks=None)  # window already applied
    return compute_mae_gap(filtered)


def spearman_table(df: pd.DataFrame) -> dict:
    filtered = apply_consensus_filter(df, weeks=None)
    out = {}
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = filtered[filtered["position"] == pos]
        our = compute_spearman_rank_corr(sub, "projected_points", "actual_points", pos)
        con = compute_spearman_rank_corr(sub, "consensus_proj", "actual_points", pos)
        out[pos] = {"our": our, "con": con, "gap": our - con if pd.notna(our) and pd.notna(con) else float("nan")}
    return out


def firing_rate_table(treated: pd.DataFrame) -> pd.DataFrame:
    filtered = apply_consensus_filter(treated, weeks=None)
    rows = []
    for (season, pos), grp in filtered.groupby(["season", "position"]):
        rows.append(
            {
                "season": season,
                "position": pos,
                "n_matched": len(grp),
                "n_covered": int(grp["_covered"].sum()),
                "firing_rate": round(grp["_covered"].mean(), 3),
            }
        )
    return pd.DataFrame(rows).sort_values(["position", "season"])


def step1_benchmark(treated: pd.DataFrame, source: str) -> pd.DataFrame:
    """Step 1: prop_implied_points ALONE vs our projection vs consensus,
    restricted to covered, consensus-matched player-weeks."""
    filtered = apply_consensus_filter(treated, weeks=None)
    covered = filtered[filtered["_covered"] & filtered["prop_implied_points"].notna()]
    rows = []
    for pos in ["QB", "RB", "WR", "TE"]:
        sub = covered[covered["position"] == pos]
        if sub.empty:
            continue
        market_mae = (sub["prop_implied_points"] - sub["actual_points"]).abs().mean()
        our_mae = (sub["projected_points"] - sub["actual_points"]).abs().mean()
        con_mae = (sub["consensus_proj"] - sub["actual_points"]).abs().mean()
        rows.append(
            {
                "source": source,
                "position": pos,
                "n": len(sub),
                "market_mae": round(market_mae, 3),
                "our_mae": round(our_mae, 3),
                "consensus_mae": round(con_mae, 3),
                "market_vs_consensus": round(market_mae - con_mae, 3),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    archive = load_archive()
    print(f"Archive loaded: {len(archive)} rows, seasons {sorted(archive['season'].unique())}")
    id_to_name = build_id_to_full_name()
    print(f"player_id -> full name lookup: {len(id_to_name)} players")

    out_dir = os.path.join(POOLED_DIR, "props_blend_archive")
    os.makedirs(out_dir, exist_ok=True)

    all_step1 = []
    for source in SOURCES:
        pooled = load_pooled(source, id_to_name)
        print(f"\n{'=' * 70}\nSOURCE: {source}  (window rows: {len(pooled)})\n{'=' * 70}")

        treated = run_blend_for_source(pooled, archive)

        baseline_gap = gap_table(pooled)
        treated_gap = gap_table(treated)
        baseline_sp = spearman_table(pooled)
        treated_sp = spearman_table(treated)

        print("\n-- MAE gap (ours - consensus; negative = we beat consensus) --")
        print(f"{'pos':6}{'baseline':>12}{'treated':>12}{'delta':>12}")
        for pos in ["QB", "RB", "WR", "TE", "OVERALL"]:
            b, t = baseline_gap.get(pos, float("nan")), treated_gap.get(pos, float("nan"))
            print(f"{pos:6}{b:12.4f}{t:12.4f}{(t - b):12.4f}")

        print("\n-- Spearman gap (ours - consensus; positive = we rank better) --")
        print(f"{'pos':6}{'baseline':>12}{'treated':>12}{'delta':>12}")
        for pos in ["QB", "RB", "WR", "TE"]:
            b = baseline_sp[pos]["gap"]
            t = treated_sp[pos]["gap"]
            delta = t - b if pd.notna(b) and pd.notna(t) else float("nan")
            print(f"{pos:6}{b:12.4f}{t:12.4f}{delta:12.4f}")

        firing = firing_rate_table(treated)
        print("\n-- Firing rate (matched player-weeks with core-market prop coverage) --")
        print(firing.to_string(index=False))

        step1 = step1_benchmark(treated, source)
        if not step1.empty:
            print("\n-- Step 1 benchmark: prop_implied_points alone vs ours vs consensus (covered only) --")
            print(step1.to_string(index=False))
            all_step1.append(step1)

        treated.to_csv(os.path.join(out_dir, f"treated_{source}.csv"), index=False)
        firing.to_csv(os.path.join(out_dir, f"firing_rate_{source}.csv"), index=False)
        pd.DataFrame(
            [{"position": p, "baseline_mae_gap": baseline_gap.get(p), "treated_mae_gap": treated_gap.get(p),
              "delta_mae_gap": treated_gap.get(p) - baseline_gap.get(p),
              "baseline_spearman_gap": baseline_sp.get(p, {}).get("gap"),
              "treated_spearman_gap": treated_sp.get(p, {}).get("gap")}
             for p in ["QB", "RB", "WR", "TE", "OVERALL"]]
        ).to_csv(os.path.join(out_dir, f"gate_table_{source}.csv"), index=False)

    if all_step1:
        pd.concat(all_step1, ignore_index=True).to_csv(
            os.path.join(out_dir, "step1_benchmark.csv"), index=False
        )

    print(
        f"\nAll outputs written to {out_dir}/ (*.csv is globally gitignored in "
        "this repo — output/backtest/ was never committed; these derived "
        "CSVs embed third-party-sourced prop_implied_points values per "
        "player, so leave them local regardless)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
