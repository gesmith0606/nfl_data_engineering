"""Export Gold rankings as submission CSVs (FantasyPros expert entry).

Turns the existing Gold artifacts into per-position ranked CSV files ready
for accuracy-competition submission (docs/ACCURACY_COMPETITION.md):

    # Weekly in-season rankings (one CSV per position)
    py -3 scripts/export_rankings_submission.py --weekly --season 2026 --week 3

    # Preseason draft rankings (overall + per position)
    py -3 scripts/export_rankings_submission.py --preseason --season 2026

The exact partner spec arrives at FantasyPros onboarding, so the column
layout is a flag, not a rewrite:

    --columns rank,player_name,team,position     (default)

Outputs land in data/exports/rankings/ (gitignored path is fine — these are
generated artifacts).
"""

from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

# Repo root on sys.path so `src.` imports work when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from src.projection_store import load_latest_preseason  # noqa: E402

POSITIONS = ("QB", "RB", "WR", "TE", "K")
DEFAULT_COLUMNS = ["rank", "player_name", "team", "position"]
DEFAULT_OUT_DIR = _PROJECT_ROOT / "data" / "exports" / "rankings"


def _load_weekly(season: int, week: int, scoring: str) -> pd.DataFrame:
    """Latest weekly Gold parquet for (season, week, scoring)."""
    pattern = str(
        _PROJECT_ROOT
        / "data"
        / "gold"
        / "projections"
        / f"season={season}"
        / f"week={week}"
        / f"projections_{scoring}_*.parquet"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No weekly Gold parquet for season={season} week={week} "
            f"scoring={scoring} — run generate_projections.py first."
        )
    df = pd.read_parquet(files[-1])
    if "recent_team" in df.columns and "team" not in df.columns:
        df = df.rename(columns={"recent_team": "team"})
    return df


def _ranked(df: pd.DataFrame, points_col: str, columns: list) -> pd.DataFrame:
    """Sort by points desc, add 1-based rank, project to the export columns."""
    out = df.sort_values(points_col, ascending=False).reset_index(drop=True).copy()
    out["rank"] = out.index + 1
    for col in columns:
        if col not in out.columns:
            out[col] = ""
    return out[columns]


def _write(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"wrote {path} ({len(df)} rows)")


def export_weekly(
    season: int,
    week: int,
    scoring: str = "half_ppr",
    columns: list = None,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> list:
    """Write one ranked CSV per position for a week. Returns written paths."""
    columns = columns or DEFAULT_COLUMNS
    df = _load_weekly(season, week, scoring)
    written = []
    for pos in POSITIONS:
        pos_df = df[df["position"].astype(str).str.upper() == pos]
        if pos_df.empty:
            continue
        path = out_dir / f"{season}_wk{week:02d}_{scoring}_{pos}.csv"
        _write(_ranked(pos_df, "projected_points", columns), path)
        written.append(path)
    return written


def export_preseason(
    season: int,
    columns: list = None,
    out_dir: Path = DEFAULT_OUT_DIR,
) -> list:
    """Write overall + per-position preseason draft ranking CSVs."""
    columns = columns or DEFAULT_COLUMNS
    df = load_latest_preseason(season)
    if df is None or df.empty:
        raise FileNotFoundError(
            f"No preseason parquet for season={season} — run "
            "generate_projections.py --preseason first."
        )
    written = []
    path = out_dir / f"{season}_draft_overall.csv"
    _write(_ranked(df, "projected_season_points", columns), path)
    written.append(path)
    for pos in POSITIONS:
        pos_df = df[df["position"].astype(str).str.upper() == pos]
        if pos_df.empty:
            continue
        pos_path = out_dir / f"{season}_draft_{pos}.csv"
        _write(_ranked(pos_df, "projected_season_points", columns), pos_path)
        written.append(pos_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--weekly", action="store_true")
    mode.add_argument("--preseason", action="store_true")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, help="Required with --weekly")
    parser.add_argument("--scoring", default="half_ppr")
    parser.add_argument(
        "--columns",
        default=",".join(DEFAULT_COLUMNS),
        help="Comma-separated export columns (adjust to the partner spec)",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    columns = [c.strip() for c in args.columns.split(",") if c.strip()]
    out_dir = Path(args.out)
    try:
        if args.weekly:
            if args.week is None:
                parser.error("--weekly requires --week")
            written = export_weekly(
                args.season, args.week, args.scoring, columns, out_dir
            )
        else:
            written = export_preseason(args.season, columns, out_dir)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{len(written)} file(s) exported to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
