"""Tests for scripts/draft_value_report.py ADP source resolution.

The report prices every player against a room's ADP board, so picking the
wrong board silently re-rates the whole draft. FFC/Sleeper publish genuinely
different PPR vs half-PPR boards (mean |delta rank| ~10 on the 2026 files,
61 players a full round apart), so the scoring format must win over file
mtime when an exact match exists.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import draft_value_report  # noqa: E402


def _touch(path: Path, mtime: float) -> None:
    path.write_text("adp_rank,player_name\n1,Someone\n")
    os.utime(path, (mtime, mtime))


@pytest.fixture()
def adp_dir(tmp_path, monkeypatch):
    """Run adp_file() against a throwaway data/adp tree."""
    (tmp_path / "data" / "adp").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path / "data" / "adp"


class TestAdpFileScoringMatch:
    def test_exact_scoring_match_wins_over_newer_other_scoring(self, adp_dir):
        """A half-PPR league must not be priced off a fresher PPR board."""
        _touch(adp_dir / "adp_ffc_half_ppr.csv", 1_000)
        _touch(adp_dir / "adp_ffc_ppr.csv", 9_000)  # newer, wrong scoring

        assert draft_value_report.adp_file("ffc", "half_ppr") == os.path.join(
            "data", "adp", "adp_ffc_half_ppr.csv"
        )

    def test_falls_back_to_newest_when_no_exact_match(self, adp_dir):
        """With no exact match, the freshest available board is still used."""
        _touch(adp_dir / "adp_ffc_ppr.csv", 1_000)
        _touch(adp_dir / "adp_ffc_standard.csv", 9_000)

        assert draft_value_report.adp_file("ffc", "half_ppr") == os.path.join(
            "data", "adp", "adp_ffc_standard.csv"
        )

    def test_dated_snapshots_are_never_selected(self, adp_dir):
        """Dated archives (adp_ffc_ppr_20260827.csv) are history, not the board."""
        _touch(adp_dir / "adp_ffc_half_ppr.csv", 1_000)
        _touch(adp_dir / "adp_ffc_half_ppr_20260827.csv", 9_000)

        assert draft_value_report.adp_file("ffc", "half_ppr") == os.path.join(
            "data", "adp", "adp_ffc_half_ppr.csv"
        )

    def test_ffc_falls_back_to_legacy_adp_latest(self, adp_dir, tmp_path):
        """Legacy pointer still rescues an otherwise empty FFC lookup."""
        (tmp_path / "data" / "adp_latest.csv").write_text("adp_rank,player_name\n")

        assert draft_value_report.adp_file("ffc", "half_ppr") == os.path.join(
            "data", "adp_latest.csv"
        )

    def test_returns_none_when_nothing_available(self, adp_dir):
        assert draft_value_report.adp_file("sleeper", "half_ppr") is None
