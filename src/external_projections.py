"""Silver consolidator for external projections (Phase 73-02).

Reads the 3 external Bronze sources (ESPN, Sleeper, Yahoo/FP proxy) plus our
Gold projections and merges them into a single long-format Silver Parquet.

Long-format schema (per CONTEXT D-04):
    {player_id, player_name, position, team, source, scoring_format,
     projected_points, projected_at, season, week}
where source ∈ {"ours", "espn", "sleeper", "yahoo_proxy_fp"}.

The consolidator follows D-06 fail-open: any single missing or unreadable
source is silently omitted; only the available sources land in Silver.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Canonical Silver columns in declared order.
_SILVER_COLUMNS: List[str] = [
    "player_id",
    "player_name",
    "position",
    "team",
    "source",
    "scoring_format",
    "projected_points",
    "projected_at",
    "season",
    "week",
]

_EXTERNAL_SOURCES = ("espn", "sleeper", "yahoo_proxy_fp")


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most recently modified .parquet in directory or None."""
    if not directory.exists():
        return None
    parquets = list(directory.glob("*.parquet"))
    if not parquets:
        return None
    return max(parquets, key=lambda p: p.stat().st_mtime)


@dataclass(frozen=True)
class SilverConsolidator:
    """Reads all 4 sources for a season/week and emits a long-format DataFrame.

    Attributes:
        season: NFL season year.
        week: NFL week number.
        scoring_format: "ppr" | "half_ppr" | "standard".
        bronze_root: Root path containing per-source Bronze partitions.
        gold_root: Root path containing our Gold projections.
    """

    season: int
    week: int
    scoring_format: str = "half_ppr"
    bronze_root: Path = Path("data/bronze/external_projections")
    gold_root: Path = Path("data/gold/projections")

    def read_bronze_source(self, source: str) -> pd.DataFrame:
        """Read latest Bronze Parquet for one source/season/week.

        Returns empty DataFrame on any error (D-06 fail-open).
        """
        week_dir = (
            self.bronze_root
            / source
            / f"season={self.season}"
            / f"week={self.week:02d}"
        )
        latest = _latest_parquet(week_dir)
        if latest is None:
            return pd.DataFrame(columns=_SILVER_COLUMNS)
        try:
            df = pd.read_parquet(latest)
        except Exception as exc:
            logger.warning("Could not read %s: %s — fail-open empty", latest, exc)
            return pd.DataFrame(columns=_SILVER_COLUMNS)
        # Filter to requested scoring_format if column present.
        if "scoring_format" in df.columns:
            df = df[df["scoring_format"] == self.scoring_format].copy()
        # Ensure all Silver columns present.
        for col in _SILVER_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[_SILVER_COLUMNS].copy()

    def read_ours(self) -> pd.DataFrame:
        """Read our latest Gold projection Parquet, normalize to long format."""
        # Try scoring-format-specific subdirectory first.
        candidates = [
            self.gold_root
            / f"season={self.season}"
            / f"week={self.week:02d}"
            / self.scoring_format,
            self.gold_root
            / f"season={self.season}"
            / f"week={self.week:02d}",
        ]
        latest: Optional[Path] = None
        for cand in candidates:
            latest = _latest_parquet(cand)
            if latest is not None:
                break
        if latest is None:
            return pd.DataFrame(columns=_SILVER_COLUMNS)

        try:
            df = pd.read_parquet(latest)
        except Exception as exc:
            logger.warning(
                "Could not read our Gold %s: %s — fail-open empty", latest, exc
            )
            return pd.DataFrame(columns=_SILVER_COLUMNS)

        # Normalize column names — projection_service uses recent_team for current team.
        if "team" not in df.columns and "recent_team" in df.columns:
            df = df.rename(columns={"recent_team": "team"})

        # The Gold projection schema may use projected_points OR
        # projected_season_points (preseason). Prefer projected_points.
        pts_col = None
        for cand_col in ("projected_points", "projected_season_points"):
            if cand_col in df.columns:
                pts_col = cand_col
                break
        if pts_col is None:
            return pd.DataFrame(columns=_SILVER_COLUMNS)

        out = pd.DataFrame(
            {
                "player_id": df.get("player_id"),
                "player_name": df.get("player_name"),
                "position": df.get("position"),
                "team": df.get("team"),
                "source": "ours",
                "scoring_format": self.scoring_format,
                "projected_points": df[pts_col].astype(float),
                "projected_at": datetime.fromtimestamp(
                    latest.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "season": self.season,
                "week": self.week,
            }
        )
        return out[_SILVER_COLUMNS]

    def _resolve_missing_player_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        """For rows where player_id is null/empty, attempt name→id resolution."""
        if df.empty:
            return df
        try:
            from src.player_name_resolver import PlayerNameResolver
            resolver = PlayerNameResolver()
        except Exception as exc:
            logger.warning("PlayerNameResolver unavailable: %s", exc)
            return df

        def _resolve(row):
            pid = row.get("player_id")
            if pid and isinstance(pid, str) and pid.strip():
                return pid
            name = row.get("player_name")
            if not name:
                return ""
            try:
                resolved = resolver.resolve(
                    name=name,
                    team=row.get("team"),
                    position=row.get("position"),
                )
            except Exception:
                resolved = None
            if resolved and isinstance(resolved, dict):
                return resolved.get("player_id") or ""
            if isinstance(resolved, str):
                return resolved
            return ""

        df = df.copy()
        df["player_id"] = df.apply(_resolve, axis=1)
        return df

    def to_long_format(self, frames: List[pd.DataFrame]) -> pd.DataFrame:
        """Concat all source DataFrames, enforce dtypes."""
        non_empty = [f for f in frames if not f.empty]
        if not non_empty:
            return pd.DataFrame(columns=_SILVER_COLUMNS)
        out = pd.concat(non_empty, ignore_index=True)
        # Enforce dtypes
        out["projected_points"] = out["projected_points"].astype(float)
        out["season"] = out["season"].astype(int)
        out["week"] = out["week"].astype(int)
        # Ensure column order
        return out[_SILVER_COLUMNS].copy()

    def consolidate(self) -> pd.DataFrame:
        """Read all 4 sources, resolve player_ids, return long-format DataFrame."""
        frames = [self.read_ours()]
        for source in _EXTERNAL_SOURCES:
            frames.append(self.read_bronze_source(source))
        merged = self.to_long_format(frames)
        merged = self._resolve_missing_player_ids(merged)
        return merged

    def write_silver(
        self,
        df: pd.DataFrame,
        silver_root: Path = Path("data/silver/external_projections"),
    ) -> Optional[Path]:
        """Write the consolidated DataFrame to Silver Parquet at the canonical path."""
        if df.empty:
            logger.warning("No external projections to write (D-06 fail-open)")
            return None
        week_dir = (
            silver_root / f"season={self.season}" / f"week={self.week:02d}"
        )
        week_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = week_dir / f"external_projections_{ts}.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("Wrote %d rows to %s", len(df), out_path)
        return out_path
