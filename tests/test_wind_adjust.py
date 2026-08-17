"""Unit tests for the high-wind QB/WR/TE bias-shrink lever (opt-in,
gate verdict HOLD -- see .planning/WIND_LEVER_2026_08_16.md).

Covers: shrink math, the scoping/byte-identical guard (RB, domes, and
non-high-wind teams must be untouched), and the forecast fallback's
fail-open behavior (a request failure skips that game rather than
defaulting to high-wind or crashing).
"""

import os
import sys

import pandas as pd
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from wind_adjust import (  # noqa: E402
    HIGH_WIND_SHRINK,
    PASS_CATCHING_POSITIONS,
    apply_wind_adjust,
    apply_wind_shrink,
    compute_high_wind_teams,
    fetch_forecast_high_wind_teams,
)


def _proj_row(player_id, position, team, points):
    return {
        "player_id": player_id,
        "position": position,
        "recent_team": team,
        "projected_points": points,
    }


def _proj_df():
    return pd.DataFrame(
        [
            _proj_row("qb1", "QB", "BUF", 20.0),
            _proj_row("wr1", "WR", "BUF", 12.0),
            _proj_row("te1", "TE", "BUF", 8.0),
            _proj_row("rb1", "RB", "BUF", 15.0),  # RB, same high-wind team -- must NOT shrink
            _proj_row("wr2", "WR", "MIA", 10.0),  # low-wind team -- must NOT shrink
            _proj_row("qb2", "QB", "MIA", 18.0),
        ]
    )


class TestShrinkMath:
    def test_shrinks_by_exact_multiplicative_factor(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.10)
        qb_row = out[out["player_id"] == "qb1"].iloc[0]
        assert qb_row["projected_points"] == pytest.approx(20.0 * 0.9, abs=1e-9)

    def test_default_fitted_shrink_constant_applied(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, {"BUF"}, shrink=HIGH_WIND_SHRINK)
        wr_row = out[out["player_id"] == "wr1"].iloc[0]
        expected = round(12.0 * (1.0 - HIGH_WIND_SHRINK), 2)
        assert wr_row["projected_points"] == expected

    def test_never_shrinks_below_zero(self):
        proj = pd.DataFrame([_proj_row("qb1", "QB", "BUF", 0.5)])
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.99)
        assert out.iloc[0]["projected_points"] >= 0


class TestScopingByteIdenticalGuard:
    def test_rb_untouched_even_on_high_wind_team(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.10)
        rb_before = proj[proj["player_id"] == "rb1"]["projected_points"].iloc[0]
        rb_after = out[out["player_id"] == "rb1"]["projected_points"].iloc[0]
        assert rb_after == rb_before
        assert bool(out[out["player_id"] == "rb1"]["wind_adjust_flag"].iloc[0]) is False

    def test_low_wind_team_untouched(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.10)
        before = proj[proj["player_id"].isin(["wr2", "qb2"])]["projected_points"].tolist()
        after = out[out["player_id"].isin(["wr2", "qb2"])]["projected_points"].tolist()
        assert before == after
        assert not out[out["player_id"].isin(["wr2", "qb2"])]["wind_adjust_flag"].any()

    def test_empty_high_wind_teams_is_byte_identical(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, set(), shrink=0.10)
        pd.testing.assert_series_equal(
            out["projected_points"], proj["projected_points"], check_names=True
        )
        assert not out["wind_adjust_flag"].any()

    def test_wind_adjust_flag_set_only_on_shrunk_rows(self):
        proj = _proj_df()
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.10)
        flagged = set(out[out["wind_adjust_flag"]]["player_id"])
        assert flagged == {"qb1", "wr1", "te1"}  # QB/WR/TE on BUF only

    def test_empty_dataframe_returns_empty(self):
        proj = pd.DataFrame(columns=["player_id", "position", "recent_team", "projected_points"])
        out = apply_wind_shrink(proj, {"BUF"}, shrink=0.10)
        assert out.empty
        assert "wind_adjust_flag" in out.columns


class TestForecastFailOpen:
    def _schedule_row(self):
        return pd.DataFrame(
            [
                {
                    "game_id": "2026_01_BUF_MIA",
                    "season": 2026,
                    "week": 1,
                    "roof": "outdoors",
                    "stadium_id": "BUF00",
                    "gameday": "2026-09-10",
                    "gametime": "13:00",
                    "home_team": "BUF",
                    "away_team": "MIA",
                }
            ]
        )

    def test_request_exception_skips_game_without_crashing(self, monkeypatch):
        def _raise(*args, **kwargs):
            raise requests.exceptions.ConnectionError("network down")

        monkeypatch.setattr("wind_adjust.requests.get", _raise)
        teams, n_covered, n_eligible = fetch_forecast_high_wind_teams(
            self._schedule_row(), season=2026, week=1
        )
        assert teams == set()
        assert n_covered == 0
        assert n_eligible == 1  # game was eligible, just uncovered

    def test_missing_stadium_coords_skips_gracefully(self):
        sched = self._schedule_row()
        sched["stadium_id"] = "NOT_A_REAL_STADIUM"
        teams, n_covered, n_eligible = fetch_forecast_high_wind_teams(
            sched, season=2026, week=1
        )
        assert teams == set()
        assert n_covered == 0

    def test_empty_schedules_returns_empty(self):
        teams, n_covered, n_eligible = fetch_forecast_high_wind_teams(
            pd.DataFrame(), season=2026, week=1
        )
        assert teams == set() and n_covered == 0 and n_eligible == 0


class TestComputeHighWindTeamsFailOpen:
    def test_no_bronze_no_schedules_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "wind_adjust.compute_weather_features",
            lambda seasons=None: pd.DataFrame(columns=["season", "week", "team", "is_high_wind"]),
        )
        teams, source, n_covered, n_eligible = compute_high_wind_teams(2099, 1, schedules_df=None)
        assert teams == set()
        assert source == "unavailable"

    def test_apply_wind_adjust_is_noop_when_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "wind_adjust.compute_weather_features",
            lambda seasons=None: pd.DataFrame(columns=["season", "week", "team", "is_high_wind"]),
        )
        proj = _proj_df()
        out = apply_wind_adjust(proj, season=2099, week=1, schedules_df=None)
        pd.testing.assert_series_equal(out["projected_points"], proj["projected_points"])
        assert not out["wind_adjust_flag"].any()


def test_pass_catching_positions_is_qb_wr_te_only():
    assert PASS_CATCHING_POSITIONS == {"QB", "WR", "TE"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
