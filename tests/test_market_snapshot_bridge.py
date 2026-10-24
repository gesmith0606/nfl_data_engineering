"""Tests for the Odds-API-snapshots -> Silver market_data bridge.

``silver_market_transformation.py`` reads ``data/bronze/odds/``, which the
FinnedAI capture stops populating after 2021.  From 2022 the Odds API cron is
the only line source and writes a different layout, which nothing consumed — so
the season had no Silver ``market_data``, the ensemble's ``opening_spread``
feature was absent, and no game could be scored.  ``build_game_lines_from_snapshots``
bridges them.

The sign flip is the part worth guarding: snapshots use the SPORTSBOOK
convention (negative = home favoured) and Silver is nflverse-oriented for the
row's team (positive = that team favoured).  Getting it backwards would not
raise — it would quietly train and score on inverted market features, which is
a bug this repository has shipped before.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from market_analytics import (  # noqa: E402
    build_game_lines_from_snapshots,
    compute_movement_features,
    reshape_to_per_team,
)

SEASON = 2026
COMMENCE = "2026-09-10T20:00:00Z"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _snapshot_rows(rows, snapshot_ts):
    """Build a snapshot DataFrame in the Bronze odds-API shape."""
    out = []
    for r in rows:
        out.append(
            {
                "snapshot_ts": snapshot_ts,
                "game_id_ext": r.get("game_id_ext", "game_001"),
                "commence_time": r.get("commence_time", COMMENCE),
                "home_team": "Home Club",
                "away_team": "Away Club",
                "home_team_nfl": r.get("home_team_nfl", "KC"),
                "away_team_nfl": r.get("away_team_nfl", "BAL"),
                "bookmaker": r.get("bookmaker", "fanduel"),
                "market": r.get("market", "spreads"),
                "home_spread": r.get("home_spread"),
                "total_points": r.get("total_points"),
                "price_home": -110,
                "price_away": -110,
                "season": SEASON,
            }
        )
    return pd.DataFrame(out)


def _write(df, root, filename):
    season_dir = os.path.join(root, f"season={SEASON}")
    os.makedirs(season_dir, exist_ok=True)
    df.to_parquet(os.path.join(season_dir, filename), index=False)


def _snapshot_dir(tmp_path, *, home_spread_open=-3.0, home_spread_close=-6.0,
                  total_open=44.0, total_close=47.0):
    """Write one open and one close snapshot for a single KC-BAL game."""
    root = str(tmp_path / "snapshots")
    _write(
        _snapshot_rows(
            [
                {"home_spread": home_spread_open, "market": "spreads"},
                {"total_points": total_open, "market": "totals"},
            ],
            "2026-09-10T08:00:00Z",
        ),
        root,
        "odds_20260910_080000.parquet",
    )
    _write(
        _snapshot_rows(
            [
                {"home_spread": home_spread_close, "market": "spreads"},
                {"total_points": total_close, "market": "totals"},
            ],
            "2026-09-10T19:00:00Z",
        ),
        root,
        "odds_20260910_190000.parquet",
    )
    return root


def _schedule(home="KC", away="BAL"):
    return pd.DataFrame(
        [
            {
                "game_id": f"2026_01_{away}_{home}",
                "season": SEASON,
                "week": 1,
                "game_type": "REG",
                "home_team": home,
                "away_team": away,
            }
        ]
    )


# ---------------------------------------------------------------------------
# Sign convention
# ---------------------------------------------------------------------------


class TestSignConvention:
    def test_home_favoured_book_spread_becomes_positive(self, tmp_path):
        """Book -3.0 (home favoured) -> Silver +3.0 for the home team."""
        root = _snapshot_dir(tmp_path, home_spread_open=-3.0, home_spread_close=-6.0)
        games = build_game_lines_from_snapshots(SEASON, root, _schedule())

        assert len(games) == 1
        assert games.loc[0, "opening_spread"] == pytest.approx(3.0)
        assert games.loc[0, "closing_spread"] == pytest.approx(6.0)

    def test_home_underdog_book_spread_becomes_negative(self, tmp_path):
        """Book +2.5 (home getting points) -> Silver -2.5 for the home team."""
        root = _snapshot_dir(tmp_path, home_spread_open=2.5, home_spread_close=1.5)
        games = build_game_lines_from_snapshots(SEASON, root, _schedule())

        assert games.loc[0, "opening_spread"] == pytest.approx(-2.5)
        assert games.loc[0, "closing_spread"] == pytest.approx(-1.5)

    def test_totals_pass_through_unflipped(self, tmp_path):
        """Totals have no side, so they must NOT be negated."""
        root = _snapshot_dir(tmp_path, total_open=44.0, total_close=47.0)
        games = build_game_lines_from_snapshots(SEASON, root, _schedule())

        assert games.loc[0, "opening_total"] == pytest.approx(44.0)
        assert games.loc[0, "closing_total"] == pytest.approx(47.0)


# ---------------------------------------------------------------------------
# Schema and downstream compatibility
# ---------------------------------------------------------------------------


class TestDownstreamContract:
    def test_frame_feeds_the_existing_silver_pipeline(self, tmp_path):
        """The bridge's output must satisfy compute_movement_features ->
        reshape_to_per_team without adaptation — that reuse is the point."""
        root = _snapshot_dir(tmp_path, home_spread_open=-3.0, home_spread_close=-6.0)
        games = build_game_lines_from_snapshots(SEASON, root, _schedule())

        per_team = reshape_to_per_team(compute_movement_features(games))

        assert len(per_team) == 2, "one row per team"
        home = per_team[per_team["is_home"]].iloc[0]
        away = per_team[~per_team["is_home"]].iloc[0]
        assert home["team"] == "KC" and away["team"] == "BAL"
        # Directional column mirrored for the away row.
        assert away["opening_spread"] == pytest.approx(-home["opening_spread"])
        # Symmetric column shared.
        assert away["opening_total"] == pytest.approx(home["opening_total"])

    def test_required_columns_present(self, tmp_path):
        root = _snapshot_dir(tmp_path)
        games = build_game_lines_from_snapshots(SEASON, root, _schedule())
        for col in (
            "game_id", "season", "week", "game_type", "home_team", "away_team",
            "opening_spread", "closing_spread", "opening_total", "closing_total",
        ):
            assert col in games.columns, f"missing {col}"


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------


class TestDegenerateInputs:
    def test_no_snapshots_returns_empty(self, tmp_path):
        empty_root = str(tmp_path / "nothing")
        os.makedirs(empty_root, exist_ok=True)
        assert build_game_lines_from_snapshots(SEASON, empty_root, _schedule()).empty

    def test_game_not_on_the_schedule_is_dropped(self, tmp_path):
        """A snapshot fixture with no schedule row must not invent a game."""
        root = _snapshot_dir(tmp_path)
        other = _schedule(home="SF", away="DAL")
        assert build_game_lines_from_snapshots(SEASON, root, other).empty


# ---------------------------------------------------------------------------
# The --clv-true join contract
# ---------------------------------------------------------------------------


class TestLineCaptureJoinKeys:
    """`run_clv_true_backtest` joins snapshot lines onto assembled features.

    It asked the feature frame for the snapshot's own column names
    (home_team_nfl / away_team_nfl), which the assembled frame never had — so
    the path bailed on its first join for every season and had never run. The
    assembled frame names them team_home / team_away, from the per-team
    reshape's suffixes.
    """

    def test_snapshot_columns_renamed_match_feature_frame(self):
        snap = pd.DataFrame(
            [{"home_team_nfl": "KC", "away_team_nfl": "BAL", "season": SEASON,
              "open_spread": -3.0, "close_spread": -6.0}]
        )
        features = pd.DataFrame(
            [{"team_home": "KC", "team_away": "BAL", "season": SEASON,
              "predicted_margin": 7.0, "spread_line": 6.0}]
        )

        renamed = snap.rename(
            columns={"home_team_nfl": "team_home", "away_team_nfl": "team_away"}
        )
        joined = features.merge(renamed, on=["team_home", "team_away", "season"], how="inner")

        assert len(joined) == 1, "the rename is what makes the join land"
        assert {"open_spread", "close_spread"} <= set(joined.columns)

    def test_unrenamed_join_keys_find_nothing(self):
        """Non-vacuity: the original key names really do fail on this frame."""
        features = pd.DataFrame([{"team_home": "KC", "team_away": "BAL", "season": SEASON}])
        assert not {"home_team_nfl", "away_team_nfl"} <= set(features.columns)
