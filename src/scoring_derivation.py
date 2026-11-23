"""Derive ppr / standard weekly boards from the published half_ppr board.

The three scoring formats differ ONLY in points per reception (1.0 / 0.5 /
0.0; see ``config.SCORING_CONFIGS``). Re-scoring the stat line does not
reproduce the published ``projected_points`` (the consensus anchor, dispersion
shrink and consensus fills move points after the stat line is fixed), so the
other formats are derived as a *delta* on the published number::

    ppr      = half_ppr + 0.5 * projected_receptions
    standard = half_ppr - 0.5 * projected_receptions   (floored at 0)

The same delta is applied to ``projected_floor`` / ``projected_ceiling`` so
``floor <= points <= ceiling`` is preserved, then ranks are rebuilt with the
shared ``ranking_score.assign_ranks`` helper.
"""

import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:  # package import (tests, web) vs. flat ``src`` on sys.path (scripts)
    from config import SCORING_CONFIGS
    from ranking_score import apply_ranking_scores, assign_ranks
except ImportError:  # pragma: no cover
    from src.config import SCORING_CONFIGS
    from src.ranking_score import apply_ranking_scores, assign_ranks

logger = logging.getLogger(__name__)

SOURCE_FORMAT = "half_ppr"
DERIVED_FORMATS: Tuple[str, ...] = ("ppr", "standard")
SKILL_POSITIONS = ("RB", "WR", "TE")
RECEPTIONS_COL = "proj_receptions"
FALLBACK_SOURCE = "consensus_fallback"

_BOARD_RE = re.compile(r"^projections_half_ppr_(\d{8}_\d{6})\.parquet$")


def reception_delta(target: str) -> float:
    """Points per reception of ``target`` minus half_ppr's (+0.5 / 0.0 / -0.5)."""
    return float(
        SCORING_CONFIGS[target]["reception"]
        - SCORING_CONFIGS[SOURCE_FORMAT]["reception"]
    )


def derive_board(
    half_ppr: pd.DataFrame, target: str, derived_from: Optional[str] = None
) -> pd.DataFrame:
    """Return ``half_ppr`` re-expressed in ``target`` scoring.

    Rows whose reception projection is unknown (null on an RB/WR/TE row, or a
    ``consensus_fallback`` skill row that carries points but zeroed stat
    columns) keep their half_ppr number and are marked
    ``scoring_derivation_flag=True``. QB/K/DEF rows have no receptions, so they
    are unchanged and unflagged.

    Args:
        half_ppr: The published half_ppr board.
        target: ``"ppr"`` or ``"standard"``.
        derived_from: File name recorded in the ``derived_from`` column.

    Returns:
        New board with ``scoring_format``, ``derived_from``,
        ``scoring_derivation_flag`` columns, ranks rebuilt and sorted by
        ``overall_rank`` when present.
    """
    if target not in DERIVED_FORMATS:
        raise ValueError(f"target must be one of {DERIVED_FORMATS}, got {target!r}")
    out = half_ppr.copy()
    rec = (
        pd.to_numeric(out[RECEPTIONS_COL], errors="coerce")
        if RECEPTIONS_COL in out.columns
        else pd.Series(float("nan"), index=out.index)
    )
    skill = out["position"].isin(SKILL_POSITIONS)
    fallback = (
        out["projection_source"] == FALLBACK_SOURCE
        if "projection_source" in out.columns
        else pd.Series(False, index=out.index)
    )
    unknown = skill & (rec.isna() | fallback)
    delta = (rec.fillna(0.0) * reception_delta(target)).where(~unknown, 0.0)

    for col in ("projected_points", "projected_floor", "projected_ceiling"):
        if col in out.columns:
            out[col] = (out[col] + delta).clip(lower=0.0).round(2)

    out["scoring_format"] = target
    out["derived_from"] = derived_from or ""
    out["scoring_derivation_flag"] = unknown.astype(bool)

    if "ranking_score" in out.columns:
        season = (
            int(out["season"].iloc[0]) if "season" in out.columns and len(out) else 0
        )
        week = int(out["week"].iloc[0]) if "week" in out.columns and len(out) else 0
        out = apply_ranking_scores(out, None, season, week)
    if "position_rank" in out.columns and len(out):
        out = assign_ranks(out, overall="overall_rank" in out.columns)
        if "overall_rank" in out.columns:
            out = out.sort_values("overall_rank").reset_index(drop=True)
    return out


def _atomic_write(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def derive_week_dir(
    week_dir: Path, formats: Tuple[str, ...] = DERIVED_FORMATS
) -> List[Path]:
    """Write ppr/standard boards next to the newest half_ppr board in ``week_dir``.

    Output names reuse the source's timestamp
    (``projections_ppr_<ts>.parquet``) so provenance is obvious. Re-running is
    idempotent (files are overwritten). Returns the written paths; empty when
    the directory has no half_ppr board.
    """
    sources = sorted(
        p
        for p in week_dir.glob("projections_half_ppr_*.parquet")
        if _BOARD_RE.match(p.name)
    )
    if not sources:
        return []
    src = sources[-1]
    ts = _BOARD_RE.match(src.name).group(1)  # type: ignore[union-attr]
    base = pd.read_parquet(src)
    written: List[Path] = []
    for fmt in formats:
        dest = week_dir / f"projections_{fmt}_{ts}.parquet"
        _atomic_write(derive_board(base, fmt, derived_from=src.name), dest)
        written.append(dest)
        logger.info("Derived %s -> %s", src.name, dest.name)
    return written


def derive_season(
    gold_dir: Path, season: int, week: Optional[int] = None
) -> Dict[int, List[Path]]:
    """Derive for every week dir of ``season`` (or just ``week``)."""
    result: Dict[int, List[Path]] = {}
    season_dir = gold_dir / "projections" / f"season={season}"
    for wd in sorted(season_dir.glob("week=*")):
        try:
            wk = int(wd.name.split("=", 1)[1])
        except (IndexError, ValueError):
            continue
        if week is not None and wk != week:
            continue
        paths = derive_week_dir(wd)
        if paths:
            result[wk] = paths
    return result
