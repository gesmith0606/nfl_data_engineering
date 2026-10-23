"""Unit tests for scripts/validate_rental_tag.py.

The RENTAL/ENDING tag shipped on reasoning, not evidence. This script tests
its actual claim — that a borrowed role reverts when the better team-mate
returns — against the season's own record, so the tag can be defended or
dropped on numbers.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "validate_rental_tag",
    Path(__file__).resolve().parent.parent / "scripts" / "validate_rental_tag.py",
)
validate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(validate)


def _stats(week, sid, played=None, team=None, pts=None):
    row = {}
    if played is not None:
        row["off_snp"] = played
    if team is not None:
        row["tm_off_snp"] = team
    if pts is not None:
        row["pts_ppr"] = pts
    return {week: {sid: row}}


def test_snap_pct_is_a_share_not_a_count():
    s = _stats(3, "1", played=40, team=80)
    assert validate.snap_pct(s, "1", 3) == 50.0


def test_snap_pct_is_none_without_team_snaps():
    """A missing denominator must not read as zero usage."""
    assert validate.snap_pct(_stats(3, "1", played=40), "1", 3) is None
    assert validate.snap_pct(_stats(3, "1"), "1", 3) is None
    assert validate.snap_pct({}, "1", 3) is None


def test_points_default_to_zero_for_a_player_who_did_not_feature():
    assert validate.points({}, "1", 3) == 0.0
    assert validate.points(_stats(3, "1", pts=12.5), "1", 3) == 12.5


def test_describe_reports_n_median_and_mean():
    line = validate.describe("label", [-10.0, -2.0, 0.0], "pp")
    assert "n=  3" in line
    assert "-2.0pp" in line


def test_describe_handles_an_empty_sample():
    assert "n=  0" in validate.describe("label", [], "pp")


def test_min_snap_threshold_requires_a_real_role():
    """A 5%-snap player 'losing his role' would be noise, not signal."""
    assert validate.MIN_SNAP_PCT >= 20.0


def test_skill_positions_only():
    assert set(validate.SKILL) == {"QB", "RB", "WR", "TE"}
