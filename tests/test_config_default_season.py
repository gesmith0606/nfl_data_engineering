"""
Regression test for the dynamic DEFAULT_SEASON rule in src/config.py.

DEFAULT_SEASON used to be a hardcoded literal (2024) that went stale every
year. It is now computed by _compute_default_season(): the season is the
current calendar year from March onward, and the previous calendar year
in January/February (while that season's playoffs are still wrapping up).
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import _compute_default_season, DEFAULT_SEASON


def test_march_onward_uses_current_year():
    assert _compute_default_season(datetime.date(2026, 3, 1)) == 2026
    assert _compute_default_season(datetime.date(2026, 9, 6)) == 2026
    assert _compute_default_season(datetime.date(2026, 12, 31)) == 2026


def test_january_february_uses_prior_year():
    assert _compute_default_season(datetime.date(2026, 1, 1)) == 2025
    assert _compute_default_season(datetime.date(2026, 2, 28)) == 2025


def test_boundary_february_to_march():
    assert _compute_default_season(datetime.date(2027, 2, 28)) == 2026
    assert _compute_default_season(datetime.date(2027, 3, 1)) == 2027


def test_default_season_module_constant_matches_today():
    """DEFAULT_SEASON (computed at import time) must match the rule for today."""
    assert DEFAULT_SEASON == _compute_default_season(datetime.date.today())
