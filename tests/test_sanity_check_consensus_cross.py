"""Regression tests for SANITY-M3 consensus cross-check (2026-08-30 incident).

The first Silver external_projections file for season=2026 landed on
2026-08-30 and activated a never-exercised path in
``_check_consensus_cross_check``: the preseason Gold board carries
``projected_season_points`` (season totals) while the external frame
carries ``projected_points`` (per-game), so the merge produced no column
collision, pandas applied no suffixes, and ``row["projected_season_points
_ours"]`` raised KeyError — failing every deploy-web run.

These tests fabricate both frames on disk/in-memory and assert:
1. preseason (season-scale) vs weekly external runs clean — no exception,
   no criticals when the boards agree per-game;
2. the check still escalates to CRITICAL on gross divergence;
3. the in-season path (both frames per-game ``projected_points``) works.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


def _ext_frame(names, per_game_points) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_name": names,
            "position": ["QB"] * len(names),
            "projected_points": per_game_points,
            "scoring_format": ["half_ppr"] * len(names),
        }
    )


def _our_season_frame(names, per_game_points) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_name": names,
            "position": ["QB"] * len(names),
            "projected_season_points": [p * 17.0 for p in per_game_points],
        }
    )


def _write_ext(tmp_path: Path, ext_df: pd.DataFrame) -> None:
    week_dir = (
        tmp_path
        / "data"
        / "silver"
        / "external_projections"
        / "season=2026"
        / "week=01"
    )
    week_dir.mkdir(parents=True)
    ext_df.to_parquet(
        week_dir / "ext_test.parquet",
        index=False,
    )


_NAMES = [f"Quarter Back{i}" for i in range(14)]
_PTS = [24.0 - i for i in range(14)]


def test_preseason_board_vs_weekly_external_no_crash(tmp_path):
    """Season-scale board + per-game external: no KeyError, no criticals."""
    _write_ext(tmp_path, _ext_frame(_NAMES, _PTS))
    with patch.object(sanity, "PROJECT_ROOT", str(tmp_path)), patch.object(
        sanity,
        "_load_our_projections",
        return_value=_our_season_frame(_NAMES, _PTS),
    ):
        criticals, warnings = sanity._check_consensus_cross_check(
            "half_ppr",
            2026,
        )
    assert criticals == []
    assert not any("SKIPPED" in w for w in warnings)


def test_gross_divergence_still_escalates(tmp_path):
    """Completely disjoint top-N still trips the CRITICAL threshold."""
    other = [f"Other Player{i}" for i in range(14)]
    _write_ext(tmp_path, _ext_frame(other, _PTS))
    with patch.object(sanity, "PROJECT_ROOT", str(tmp_path)), patch.object(
        sanity,
        "_load_our_projections",
        return_value=_our_season_frame(_NAMES, _PTS),
    ):
        criticals, _ = sanity._check_consensus_cross_check(
            "half_ppr",
            2026,
        )
    assert criticals and "CONSENSUS DIVERGENCE" in criticals[0]


def test_in_season_per_game_board_still_works(tmp_path):
    """Both frames per-game (in-season weekly path) compares raw points."""
    _write_ext(tmp_path, _ext_frame(_NAMES, _PTS))
    our = pd.DataFrame(
        {
            "player_name": _NAMES,
            "position": ["QB"] * len(_NAMES),
            "projected_points": _PTS,
        }
    )
    with patch.object(sanity, "PROJECT_ROOT", str(tmp_path)), patch.object(
        sanity, "_load_our_projections", return_value=our
    ):
        criticals, warnings = sanity._check_consensus_cross_check(
            "half_ppr",
            2026,
        )
    assert criticals == []
    assert not any("SKIPPED" in w for w in warnings)
