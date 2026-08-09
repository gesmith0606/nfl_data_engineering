#!/usr/bin/env python3
"""Error decomposition of our fantasy projections vs consensus sources.

Loads the matched-pairs backtest CSVs produced by
``benchmark_consensus_sources.py`` / ``backtest_projections.py --vs-consensus``
(one row per matched player-week: our projection, source projection, actual
points) and slices the MAE gap (ours - source; negative = we win) to find
WHERE we lose, so the gaps translate into concrete model levers.

Reuses ``src/consensus_metrics.py`` (the single source of truth for the
cons>=5, weeks 3-18, QB/RB/WR/TE evaluation population) rather than
re-deriving the filter.

Usage::

    python scripts/decompose_consensus_errors.py
    python scripts/decompose_consensus_errors.py \\
        --sleeper-csv output/backtest/consensus_matched_sleeper_half_ppr_20260711_155403.csv \\
        --espn-csv output/backtest/consensus_matched_espn_half_ppr_20260711_155403.csv \\
        --positions QB RB
"""

from __future__ import annotations

import argparse
import glob as globmod
import os
import sys
from typing import List, Optional

import numpy as np
import pandas as pd

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.join(_SCRIPTS_DIR, "..")
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from consensus_metrics import (  # noqa: E402
    CONSENSUS_POSITIONS,
    apply_consensus_filter,
    compute_mae_gap,
)

_BRONZE_WEEKLY = os.path.join(_PROJECT_ROOT, "data", "bronze", "players", "weekly")

# Below this many matched rows, treat a slice's gap as noise, not signal.
_MIN_N_RELIABLE = 50


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _latest(pattern: str) -> Optional[str]:
    files = sorted(globmod.glob(pattern))
    return files[-1] if files else None


def load_matched(csv_path: Optional[str], source: str, output_dir: str) -> pd.DataFrame:
    """Load a matched CSV, defaulting to the newest file for ``source``."""
    path = csv_path or _latest(
        os.path.join(output_dir, f"consensus_matched_{source}_half_ppr_*.csv")
    )
    if path is None:
        raise FileNotFoundError(
            f"No consensus_matched_{source}_*.csv in {output_dir}. Run "
            "benchmark_consensus_sources.py or backtest_projections.py "
            "--vs-consensus first."
        )
    df = pd.read_csv(path)
    df["_source"] = source
    df["_csv_path"] = path
    return df


# ---------------------------------------------------------------------------
# Archetype (approximated from actual bronze weekly stat mix — no Silver
# usage-share join; see module docstring / report for the caveat).
# ---------------------------------------------------------------------------


def compute_archetype(seasons: List[int], position: str) -> pd.DataFrame:
    """Season-level archetype share per player, from Bronze player_weekly.

    RB: receiving_share = receiving_yards / (receiving_yards + rushing_yards)
        — pass-catching back vs pure runner.
    QB: rushing_share = rushing_yards / (rushing_yards + passing_yards)
        — mobile QB vs pocket passer.

    Approximation, not a Silver usage-share join: aggregates whichever weeks
    of Bronze player_weekly are present per season (should be the full
    season) rather than reproducing the exact leak-free rolling windows the
    projection engine uses.
    """
    parts = []
    for season in seasons:
        f = _latest(os.path.join(_BRONZE_WEEKLY, f"season={season}", "*.parquet"))
        if f is None:
            continue
        df = pd.read_parquet(f)
        df = df[df["position"] == position]
        if df.empty:
            continue
        agg = df.groupby("player_id", as_index=False).agg(
            rushing_yards=("rushing_yards", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            passing_yards=("passing_yards", "sum"),
        )
        agg["season"] = season
        parts.append(agg)
    if not parts:
        return pd.DataFrame(columns=["player_id", "season", "archetype_share", "archetype_tier"])

    out = pd.concat(parts, ignore_index=True)
    if position == "RB":
        denom = out["receiving_yards"] + out["rushing_yards"]
        out["archetype_share"] = np.where(denom > 0, out["receiving_yards"] / denom, np.nan)
    elif position == "QB":
        denom = out["rushing_yards"] + out["passing_yards"]
        out["archetype_share"] = np.where(denom > 0, out["rushing_yards"] / denom, np.nan)
    else:
        raise ValueError(f"No archetype definition for position={position}")

    out = out.dropna(subset=["archetype_share"])
    try:
        out["archetype_tier"] = pd.qcut(
            out["archetype_share"], 3, labels=["Low", "Mid", "High"], duplicates="drop"
        )
    except ValueError:
        out["archetype_tier"] = "Mid"  # degenerate distribution (too few players)
    return out[["player_id", "season", "archetype_share", "archetype_tier"]]


# ---------------------------------------------------------------------------
# Slicing
# ---------------------------------------------------------------------------


def _gap_row(label: str, group: pd.DataFrame) -> dict:
    our_err = group["projected_points"] - group["actual_points"]
    src_err = group["consensus_proj"] - group["actual_points"]
    n = len(group)
    our_mae = our_err.abs().mean()
    src_mae = src_err.abs().mean()
    return {
        "slice": label,
        "n": n,
        "our_mae": round(our_mae, 3),
        "source_mae": round(src_mae, 3),
        "gap": round(our_mae - src_mae, 3),  # negative = we win
        "our_bias": round(our_err.mean(), 3),  # +over, -under
        "source_bias": round(src_err.mean(), 3),
        "reliable": n >= _MIN_N_RELIABLE,
    }


def slice_table(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = [_gap_row(str(val), grp) for val, grp in df.groupby(group_col, observed=True)]
    return pd.DataFrame(rows).sort_values("gap", ascending=False).reset_index(drop=True)


def magnitude_band(our_proj: pd.Series) -> pd.Series:
    return pd.cut(
        our_proj, bins=[-0.01, 8, 14, 1000], labels=["<8", "8-14", "14+"]
    )


def week_band(week: pd.Series) -> pd.Series:
    return pd.cut(
        week, bins=[2, 6, 12, 18], labels=["3-6", "7-12", "13-18"]
    )


def top_contributors(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """Per-player contribution to the position's aggregate MAE gap.

    contribution = (our_mae - source_mae) * n for that player, so summing
    contribution / total_n across all players reproduces the position's
    overall gap.
    """
    rows = []
    for (pid, name), grp in df.groupby(["player_id", "player_name"]):
        r = _gap_row(name, grp)
        r["player_id"] = pid
        r["player_name"] = name
        r["contribution"] = round((r["our_mae"] - r["source_mae"]) * r["n"], 2)
        rows.append(r)
    out = pd.DataFrame(rows).sort_values("contribution", ascending=False)
    return out.head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sanity check
# ---------------------------------------------------------------------------


def _sanity_check(matched: pd.DataFrame, source: str) -> None:
    """Cross-check this module's gap math against consensus_metrics (the
    canonical implementation) on the same filtered population."""
    filtered = apply_consensus_filter(matched)
    assert not filtered.empty, f"{source}: consensus-filtered population is empty"
    required = {"player_id", "player_name", "position", "season", "week",
                "projected_points", "consensus_proj", "actual_points"}
    missing = required - set(matched.columns)
    assert not missing, f"{source}: matched CSV missing columns {missing}"

    canonical_gap = compute_mae_gap(filtered)
    for pos in CONSENSUS_POSITIONS:
        pos_df = filtered[filtered["position"] == pos]
        if pos_df.empty:
            continue
        our_mae = (pos_df["projected_points"] - pos_df["actual_points"]).abs().mean()
        src_mae = (pos_df["consensus_proj"] - pos_df["actual_points"]).abs().mean()
        local_gap = our_mae - src_mae
        assert abs(local_gap - canonical_gap[pos]) < 1e-6, (
            f"{source}/{pos}: local gap {local_gap:.4f} != canonical "
            f"{canonical_gap[pos]:.4f}"
        )
    print(f"  [sanity OK] {source}: gap math matches consensus_metrics for "
          f"{[p for p in CONSENSUS_POSITIONS if p in filtered['position'].unique()]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def decompose_source(matched: pd.DataFrame, source: str, positions: List[str],
                      output_dir: str) -> None:
    filtered = apply_consensus_filter(matched)
    ts = None

    for pos in positions:
        pos_df = filtered[filtered["position"] == pos].copy()
        if pos_df.empty:
            print(f"\n[{source.upper()} / {pos}] no matched rows — skip")
            continue

        overall = _gap_row("OVERALL", pos_df)
        print(f"\n{'=' * 78}\n{source.upper()} / {pos} "
              f"(n={overall['n']}, gap={overall['gap']:+.3f}, "
              f"our_bias={overall['our_bias']:+.2f}, source_bias={overall['source_bias']:+.2f})\n"
              f"{'=' * 78}")

        pos_df["_magnitude"] = magnitude_band(pos_df["projected_points"])
        pos_df["_week_band"] = week_band(pos_df["week"])

        tables = {
            "magnitude_band": slice_table(pos_df, "_magnitude"),
            "week_band": slice_table(pos_df, "_week_band"),
            "season": slice_table(pos_df, "season"),
        }

        if pos in ("RB", "QB"):
            arche = compute_archetype(sorted(pos_df["season"].unique().tolist()), pos)
            if not arche.empty:
                pos_df["player_id"] = pos_df["player_id"].astype(str)
                arche["player_id"] = arche["player_id"].astype(str)
                pos_df = pos_df.merge(arche, on=["player_id", "season"], how="left")
                arche_label = "receiving_share" if pos == "RB" else "rushing_share"
                tables[f"archetype_{arche_label}"] = slice_table(
                    pos_df.dropna(subset=["archetype_tier"]), "archetype_tier"
                )
            else:
                print(f"  (no Bronze player_weekly found for archetype — skipped)")

        for name, table in tables.items():
            print(f"\n-- {name} --")
            print(table.to_string(index=False))
            out_csv = os.path.join(
                output_dir, f"decompose_{source}_{pos}_{name}.csv"
            )
            table.to_csv(out_csv, index=False)

        contributors = top_contributors(pos_df, top_n=20)
        print(f"\n-- top_20_contributors --")
        cols = ["player_name", "n", "our_mae", "source_mae", "gap", "contribution"]
        print(contributors[cols].to_string(index=False))
        contributors.to_csv(
            os.path.join(output_dir, f"decompose_{source}_{pos}_top_contributors.csv"),
            index=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sleeper-csv", default=None)
    parser.add_argument("--espn-csv", default=None)
    parser.add_argument("--output-dir", default="output/backtest")
    parser.add_argument(
        "--positions", nargs="+", default=["RB", "QB", "WR", "TE"],
        choices=CONSENSUS_POSITIONS,
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    for source, csv_arg in [("sleeper", args.sleeper_csv), ("espn", args.espn_csv)]:
        matched = load_matched(csv_arg, source, args.output_dir)
        print(f"\nLoaded {len(matched):,} matched rows for {source} "
              f"from {matched['_csv_path'].iloc[0]}")
        _sanity_check(matched, source)
        decompose_source(matched, source, args.positions, args.output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
