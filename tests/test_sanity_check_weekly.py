"""Unit tests for the SANITY-M6 weekly projection gate.

Covers the 2026-06-12 incident class: a 42-day-old weekly parquet (generated
2026-05-01 by pre-fix code) was baked into the deploy image and served by the
website's weekly view with Christian McCaffrey at RB118, Drake Maye at QB29,
season-scale totals (Lamar Jackson 483.1 "weekly" points), and duplicate
rookie-fallback rows.

Tests are synthetic — no dependency on real Gold/Silver partitions on disk.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import scripts.sanity_check_projections as sanity  # noqa: E402


SEASON = 2026
WEEK = 1


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _inj(
    status: str = "Out",
    mult: float = 0.0,
    unconfirmed: bool = False,
    pts: float = 0.0,
) -> Dict:
    """One star's injury columns and resulting points on the board."""
    return {"status": status, "mult": mult, "unconfirmed": unconfirmed, "pts": pts}


ALL_STARS = [
    "Star QB1",
    "Star QB2",
    "Christian McCaffrey",
    "Star RB2",
    "Star WR1",
    "Star WR2",
    "Star TE1",
    "Star TE2",
]


def _weekly_df(
    points_scale: float = 1.0,
    duplicate_rows: bool = False,
    cmc_rank_buried: bool = False,
    negative_points: bool = False,
    cmc_zeroed: bool = False,
    injured: Optional[Dict[str, Dict]] = None,
) -> pd.DataFrame:
    """Build a synthetic weekly Gold projections DataFrame.

    Default output is healthy: weekly-scale points, unique player_ids, and
    every consensus star near the top of their position.

    ``injured`` maps a star's name to ``_inj(...)``; when given, the board
    also carries the injury columns (Active / 1.0 / False for everyone else),
    as the real board does. Without it the columns are absent, like an old
    board.
    """
    rows = []
    star_points = {
        "QB": [("Star QB1", 24.0), ("Star QB2", 22.0)],
        "RB": [("Christian McCaffrey", 19.0), ("Star RB2", 17.0)],
        "WR": [("Star WR1", 16.0), ("Star WR2", 15.0)],
        "TE": [("Star TE1", 13.0), ("Star TE2", 11.0)],
    }
    pid = 0
    for pos, players in star_points.items():
        for name, pts in players:
            pid += 1
            if cmc_rank_buried and name == "Christian McCaffrey":
                pts = 0.4  # buries him below the 120 filler players
            if cmc_zeroed and name == "Christian McCaffrey":
                pts = 0.0  # Out on this week's report -> engine zeroes him
            rows.append(
                {
                    "player_id": f"00-{pid:04d}",
                    "player_name": name,
                    "position": pos,
                    "projected_points": pts * points_scale,
                }
            )
        # Filler players so each position has a deep rank table.
        for i in range(30):
            pid += 1
            rows.append(
                {
                    "player_id": f"00-{pid:04d}",
                    "player_name": f"Filler {pos}{i}",
                    "position": pos,
                    "projected_points": (10.0 - i * 0.3) * points_scale,
                }
            )

    if injured is not None:
        for row in rows:
            spec = injured.get(row["player_name"])
            row["injury_status"] = spec["status"] if spec else "Active"
            row["injury_multiplier"] = spec["mult"] if spec else 1.0
            row["injury_unconfirmed"] = spec["unconfirmed"] if spec else False
            if spec:
                row["projected_points"] = spec["pts"]
    if duplicate_rows:
        rows.append(dict(rows[0]))
        rows.append(dict(rows[1]))
    if negative_points:
        pid += 1
        rows.append(
            {
                "player_id": f"00-{pid:04d}",
                "player_name": "Negative Guy",
                "position": "WR",
                "projected_points": -1.5,
            }
        )
    return pd.DataFrame(rows)


def _consensus_df() -> pd.DataFrame:
    """Synthetic Silver external_projections with the same stars on top."""
    rows = []
    stars = {
        "QB": ["Star QB1", "Star QB2"],
        "RB": ["Christian McCaffrey", "Star RB2"],
        "WR": ["Star WR1", "Star WR2"],
        "TE": ["Star TE1", "Star TE2"],
    }
    for pos, names in stars.items():
        for rank, name in enumerate(names):
            rows.append(
                {
                    "player_name": name,
                    "position": pos,
                    "projected_points": 25.0 - rank,
                }
            )
    return pd.DataFrame(rows)


def _fname(age_days: int) -> str:
    ts = (datetime.now() - timedelta(days=age_days)).strftime("%Y%m%d_%H%M%S")
    return f"projections_half_ppr_{ts}.parquet"


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect GOLD_DIR and PROJECT_ROOT into a temp sandbox."""
    gold = tmp_path / "data" / "gold"
    gold.mkdir(parents=True)
    monkeypatch.setattr(sanity, "GOLD_DIR", str(gold))
    monkeypatch.setattr(sanity, "PROJECT_ROOT", str(tmp_path))
    return tmp_path


def _write_weekly(tmp_path: Path, df: pd.DataFrame, age_days: int = 0) -> Path:
    week_dir = (
        tmp_path / "data" / "gold" / "projections" / f"season={SEASON}" / f"week={WEEK}"
    )
    week_dir.mkdir(parents=True, exist_ok=True)
    path = week_dir / _fname(age_days)
    df.to_parquet(path, index=False)
    return path


def _write_consensus(tmp_path: Path, week: int = WEEK, age_hours: float = 0) -> Path:
    ext_dir = (
        tmp_path
        / "data"
        / "silver"
        / "external_projections"
        / f"season={SEASON}"
        / f"week={week:02d}"
    )
    ext_dir.mkdir(parents=True, exist_ok=True)
    ts = (datetime.now() - timedelta(hours=age_hours)).strftime("%Y%m%d_%H%M%S")
    path = ext_dir / f"external_{ts}.parquet"
    _consensus_df().to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMissingPartition:
    def test_missing_partition_is_skip_not_failure(self, sandbox):
        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )
        assert criticals == []
        assert warnings == []


class TestFreshness:
    def test_stale_file_is_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(), age_days=42)
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("STALE WEEKLY FILE" in c for c in criticals)

    def test_fresh_file_passes_freshness(self, sandbox):
        _write_weekly(sandbox, _weekly_df(), age_days=0)
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert not any("STALE WEEKLY FILE" in c for c in criticals)


class TestDuplicates:
    def test_duplicate_player_ids_are_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(duplicate_rows=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("DUPLICATE player_id" in c for c in criticals)


class TestScaleSanity:
    def test_season_scale_points_are_critical(self, sandbox):
        # 20x weekly scale: top QB at 480 pts mimics the incident file.
        _write_weekly(sandbox, _weekly_df(points_scale=20.0))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("season-scale" in c.lower() for c in criticals)

    def test_negative_points_are_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df(negative_points=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("negative" in c.lower() for c in criticals)


class TestStarRank:
    def test_buried_consensus_star_is_critical(self, sandbox):
        # CMC buried below 30 filler RBs — the RB118 incident in miniature.
        _write_weekly(sandbox, _weekly_df(cmc_rank_buried=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("McCaffrey" in c for c in criticals)

    def test_no_consensus_data_is_warning_not_critical(self, sandbox):
        _write_weekly(sandbox, _weekly_df())

        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR-RANK SKIPPED" in w for w in warnings)

    def test_stale_consensus_still_catches_a_buried_healthy_star(self, sandbox):
        # The cron nearly always runs on LAST week's consensus (it lands
        # ~5h later). The CMC-at-RB118 class (0.4 pts) must still fail there.
        _write_weekly(sandbox, _weekly_df(cmc_rank_buried=True))
        _write_consensus(sandbox, week=WEEK - 1)

        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )

        assert any("McCaffrey" in c for c in criticals)
        assert any("STALE consensus" in w for w in warnings)

    def test_stale_consensus_star_we_zeroed_is_a_warning(self, sandbox):
        # 2026-10-27/11-03/11-10: Warren, Lamar, Evans got hurt after last
        # week's consensus was written; the board zeroed them correctly and
        # the gate failed it three weeks running.
        _write_weekly(sandbox, _weekly_df(cmc_zeroed=True))
        _write_consensus(sandbox, week=WEEK - 1)

        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR ZEROED" in w and "McCaffrey" in w for w in warnings)

    def test_current_week_consensus_zeroed_star_is_still_critical(self, sandbox):
        # Same-week consensus says he plays and we zeroed him: a real
        # disagreement worth a look, so the relaxation is stale-only.
        _write_weekly(sandbox, _weekly_df(cmc_zeroed=True))
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("McCaffrey" in c for c in criticals)

    def test_early_same_week_snapshot_is_stale_too(self, sandbox):
        # What actually failed 2026-10-27/11-03/11-10: week=W already existed,
        # holding the Sunday capture taken two days before the Tuesday board
        # and before that weekend's games. No fallback happened, so the
        # missing-partition test above never saw it.
        _write_weekly(sandbox, _weekly_df(cmc_zeroed=True))
        _write_consensus(sandbox, age_hours=45)

        criticals, warnings = sanity.run_weekly_projection_check(
            SEASON, WEEK, "half_ppr"
        )

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STALE consensus" in w for w in warnings)
        assert any("STAR ZEROED" in w and "McCaffrey" in w for w in warnings)

    def test_early_same_week_snapshot_still_catches_a_buried_star(self, sandbox):
        _write_weekly(sandbox, _weekly_df(cmc_rank_buried=True))
        _write_consensus(sandbox, age_hours=45)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("McCaffrey" in c for c in criticals)

    def test_snapshot_from_earlier_the_same_day_is_not_stale(self, sandbox):
        # A few hours' head start is still this week's news: zeroing a star
        # the consensus ranked that morning stays a critical.
        _write_weekly(sandbox, _weekly_df(cmc_zeroed=True))
        _write_consensus(sandbox, age_hours=5)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert any("McCaffrey" in c for c in criticals)


class TestStarRankAvailability:
    """A star the board carries as unavailable is an availability disagreement
    with the consensus, not a model error (2026-11-17: Bowers, Out on the
    Tuesday board while the 14:13 consensus still had him TE2, failed the
    deploy gate; the same shape as weeks 8-10)."""

    def _run(self, sandbox, board, **consensus_kw):
        _write_weekly(sandbox, board)
        _write_consensus(sandbox, **consensus_kw)
        return sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

    def test_out_star_on_a_fresh_consensus_is_a_warning(self, sandbox):
        # What main's week-11 board looks like: Out, multiplier 0.0, 0 points.
        board = _weekly_df(injured={"Christian McCaffrey": _inj()})

        criticals, warnings = self._run(sandbox, board)

        assert not any("McCaffrey" in c for c in criticals)
        msg = next(w for w in warnings if "McCaffrey" in w)
        assert "STAR UNAVAILABLE" in msg
        assert "Out" in msg
        assert "RB#" in msg and "ext RB#1" in msg  # both ranks
        assert "availability" in msg and "not a model error" in msg

    def test_unconfirmed_out_star_is_a_warning(self, sandbox):
        # A #178 board: 0.4x, flagged, still far outside the window.
        board = _weekly_df(
            injured={
                "Christian McCaffrey": _inj("Out (unconfirmed)", 0.4, True, pts=1.0)
            }
        )

        criticals, warnings = self._run(sandbox, board)

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR UNAVAILABLE" in w and "McCaffrey" in w for w in warnings)

    def test_unconfirmed_flag_alone_is_an_explanation(self, sandbox):
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Active", 1.0, True, pts=1.0)}
        )

        criticals, _ = self._run(sandbox, board)

        assert not any("McCaffrey" in c for c in criticals)

    def test_doubtful_star_is_a_warning(self, sandbox):
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Doubtful", 0.5, False, pts=2.0)}
        )

        criticals, warnings = self._run(sandbox, board)

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR UNAVAILABLE" in w and "Doubtful" in w for w in warnings)

    @pytest.mark.parametrize("status", ["IR", "PUP", "Injured Reserve", "Suspension"])
    def test_roster_designations_are_explanations(self, sandbox, status):
        board = _weekly_df(injured={"Christian McCaffrey": _inj(status, 0.0)})

        criticals, _ = self._run(sandbox, board)

        assert not any("McCaffrey" in c for c in criticals)

    def test_questionable_star_is_still_critical(self, sandbox):
        # 0.85x cannot bury a star: the injury does not explain this rank.
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Questionable", 0.85, False, pts=0.4)}
        )

        criticals, _ = self._run(sandbox, board)

        assert any("McCaffrey" in c for c in criticals)

    def test_healthy_buried_star_is_still_critical(self, sandbox):
        # The CMC-at-RB118 class, on a board that carries the injury columns.
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Active", 1.0, False, pts=0.4)}
        )

        criticals, _ = self._run(sandbox, board)

        assert any("McCaffrey" in c and "RB#" in c for c in criticals)

    def test_out_status_without_a_discount_is_not_an_explanation(self, sandbox):
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Out", 1.0, False, pts=0.4)}
        )

        criticals, _ = self._run(sandbox, board)

        assert any("McCaffrey" in c for c in criticals)

    def test_board_without_injury_columns_keeps_the_old_behaviour(self, sandbox):
        criticals, _ = self._run(sandbox, _weekly_df(cmc_zeroed=True))

        assert any("McCaffrey" in c for c in criticals)

    def test_a_star_inside_the_window_is_not_an_exemption(self, sandbox):
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Out (unconfirmed)", 0.4, True, 8.0)}
        )

        criticals, warnings = self._run(sandbox, board)

        assert criticals == []
        assert not any("STAR UNAVAILABLE" in w for w in warnings)

    def test_five_exempted_stars_stay_warnings(self, sandbox):
        board = _weekly_df(injured={n: _inj() for n in ALL_STARS[:5]})

        criticals, warnings = self._run(sandbox, board)

        assert criticals == []
        assert sum("STAR UNAVAILABLE" in w for w in warnings) == 5

    def test_six_exempted_stars_trip_the_cap(self, sandbox):
        board = _weekly_df(injured={n: _inj() for n in ALL_STARS[:6]})

        criticals, _ = self._run(sandbox, board)

        msg = next(c for c in criticals if "STAR EXEMPTIONS" in c)
        assert "6" in msg and "5" in msg

    def test_the_cap_does_not_hide_a_healthy_buried_star(self, sandbox):
        injured = {n: _inj() for n in ALL_STARS[:3]}
        injured["Christian McCaffrey"] = _inj("Active", 1.0, False, pts=0.4)
        injured["Star RB2"] = _inj("Active", 1.0, False, pts=0.4)

        criticals, _ = self._run(sandbox, _weekly_df(injured=injured))

        assert any("McCaffrey" in c and "WEEKLY STAR RANK" in c for c in criticals)
        assert not any("STAR EXEMPTIONS" in c for c in criticals)

    def test_stale_consensus_zeroed_star_keeps_the_old_message(self, sandbox):
        # #168's path is unchanged: it fires first, so the text and the
        # warning are exactly what they were.
        board = _weekly_df(injured={"Christian McCaffrey": _inj()})

        criticals, warnings = self._run(sandbox, board, week=WEEK - 1)

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR ZEROED" in w and "McCaffrey" in w for w in warnings)
        assert not any("STAR UNAVAILABLE" in w for w in warnings)

    def test_stale_consensus_still_catches_a_healthy_buried_star(self, sandbox):
        board = _weekly_df(
            injured={"Christian McCaffrey": _inj("Active", 1.0, False, pts=0.4)}
        )

        criticals, warnings = self._run(sandbox, board, week=WEEK - 1)

        assert any("McCaffrey" in c for c in criticals)
        assert any("STALE consensus" in w for w in warnings)

    def test_unavailable_nonzero_star_on_stale_consensus_is_a_warning(self, sandbox):
        # The #168 exemption needs a zero; an unconfirmed 0.4x row is not zero.
        board = _weekly_df(
            injured={
                "Christian McCaffrey": _inj("Out (unconfirmed)", 0.4, True, pts=1.0)
            }
        )

        criticals, warnings = self._run(sandbox, board, week=WEEK - 1)

        assert not any("McCaffrey" in c for c in criticals)
        assert any("STAR UNAVAILABLE" in w for w in warnings)

    def test_run_passes_when_the_only_outside_star_is_explained(self, sandbox):
        board = _weekly_df(injured={"Star TE2": _inj()})

        criticals, _ = self._run(sandbox, board)

        assert criticals == []


class TestHealthyFile:
    def test_healthy_fresh_file_has_no_criticals(self, sandbox):
        _write_weekly(sandbox, _weekly_df())
        _write_consensus(sandbox)

        criticals, _ = sanity.run_weekly_projection_check(SEASON, WEEK, "half_ppr")

        assert criticals == []
