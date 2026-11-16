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


def _write_ext(tmp_path: Path, ext_df: pd.DataFrame, week: int = 1) -> None:
    week_dir = (
        tmp_path
        / "data"
        / "silver"
        / "external_projections"
        / "season=2026"
        / f"week={week:02d}"
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


# ---------------------------------------------------------------------------
# 2026-11 incident: a season-long board judged against a mid-season week.
#
# The preseason board never moves in-season, but the check compared it with
# the LATEST weekly consensus. A weekly consensus only lists players who play
# that week, so every star on a bye or an injury report counted as a
# disagreement: 31/72 (43%) by week 11 (15 on bye, 6 injured, 10 injury
# replacements), which blocked every deploy from 2026-11-10. A season-long
# board is compared with the opening week instead: no byes, and the closest
# consensus to the horizon the board was built for.
# ---------------------------------------------------------------------------

_BOARD_NAMES = [f"Quarter Back{i}" for i in range(30)]
_BOARD_PTS = [24.0 - 0.5 * i for i in range(30)]


def _write_bye_week(tmp_path: Path, week: int = 11) -> None:
    """A mid-season week where the board's top five do not play."""
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES[5:], _BOARD_PTS[5:]), week=week)


def _run(tmp_path: Path, our: pd.DataFrame, **kwargs):
    with patch.object(sanity, "PROJECT_ROOT", str(tmp_path)), patch.object(
        sanity, "_load_our_projections", return_value=our
    ):
        return sanity._check_consensus_cross_check("half_ppr", 2026, **kwargs)


def test_season_board_ignores_bye_week_absences(tmp_path):
    """Stars missing from a later week's consensus are not a broken board."""
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES, _BOARD_PTS), week=1)
    _write_bye_week(tmp_path)
    criticals, warnings = _run(tmp_path, _our_season_frame(_BOARD_NAMES, _BOARD_PTS))
    assert criticals == []
    assert not any("SKIPPED" in w for w in warnings)


def test_season_board_scrambled_ranks_still_fail(tmp_path):
    """A board whose ranking is garbage fails with later weeks on disk."""
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES, _BOARD_PTS), week=1)
    _write_bye_week(tmp_path)
    scrambled = _our_season_frame(_BOARD_NAMES, list(reversed(_BOARD_PTS)))
    criticals, _ = _run(tmp_path, scrambled)
    assert criticals and "CONSENSUS DIVERGENCE" in criticals[0]


def test_season_board_scale_bug_still_fails(tmp_path):
    """Right order, double the points: the per-game magnitude test trips."""
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES, _BOARD_PTS), week=1)
    _write_bye_week(tmp_path)
    doubled = _our_season_frame(_BOARD_NAMES, [p * 2 for p in _BOARD_PTS])
    criticals, _ = _run(tmp_path, doubled)
    assert criticals and "CONSENSUS DIVERGENCE" in criticals[0]


def test_explicit_week_is_honoured_for_season_board(tmp_path):
    """Passing ``week`` still selects that week, whatever the board type."""
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES, _BOARD_PTS), week=1)
    _write_bye_week(tmp_path)
    criticals, _ = _run(tmp_path, _our_season_frame(_BOARD_NAMES, _BOARD_PTS), week=11)
    assert criticals and "CONSENSUS DIVERGENCE" in criticals[0]


def test_weekly_board_still_uses_latest_week(tmp_path):
    """A per-game board is a weekly quantity: compare it with the latest week."""
    stale = [f"Week One Only{i}" for i in range(30)]
    _write_ext(tmp_path, _ext_frame(stale, _BOARD_PTS), week=1)
    _write_ext(tmp_path, _ext_frame(_BOARD_NAMES, _BOARD_PTS), week=11)
    weekly = pd.DataFrame(
        {
            "player_name": _BOARD_NAMES,
            "position": ["QB"] * len(_BOARD_NAMES),
            "projected_points": _BOARD_PTS,
        }
    )
    criticals, _ = _run(tmp_path, weekly)
    assert criticals == []


def test_failure_names_the_reference_and_the_players(tmp_path, capsys):
    """The CI log must say what was compared and who was flagged."""
    other = [f"Other Player{i}" for i in range(30)]
    _write_ext(tmp_path, _ext_frame(other, _BOARD_PTS), week=1)
    criticals, _ = _run(tmp_path, _our_season_frame(_BOARD_NAMES, _BOARD_PTS))
    out = capsys.readouterr().out
    assert criticals
    assert "week=01" in out
    assert "quarter back0" in out
    assert "other player0" in out
