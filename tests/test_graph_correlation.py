"""Tests for the player correlation network (UC3)."""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_correlation import (
    EDGE_COLUMNS,
    HOLDOUT_SEASONS,
    MIN_GAMES_HOLDOUT,
    MIN_GAMES_TRAIN,
    TRAIN_SEASONS,
    build_pair_observations,
    compute_correlation_edges,
    compute_stack_insights,
    compute_weekly_points,
)


# ---------------------------------------------------------------------------
# Fixture: synthetic multi-season weekly data with known correlations
# ---------------------------------------------------------------------------
#
# KC: QB1 + WR1 strongly positively correlated (shared spike weeks);
#     RB1 + RB2 strongly negatively correlated (zero-sum backfield).
# Signals are consistent across train (2016-2022) and holdout (2023-2025)
# seasons so pair edges survive the stability gate.


def _weekly_rows(season: int, rng: np.random.Generator, flip_qb_wr: bool = False):
    """One season of weekly rows for the synthetic KC roster."""
    rows = []
    for week in range(1, 15):
        shared = rng.normal(0, 6)  # common game-environment shock
        qb_pts = 18 + shared + rng.normal(0, 2)
        wr_sign = -1.0 if flip_qb_wr else 1.0
        wr_pts = 12 + wr_sign * shared + rng.normal(0, 2)
        # Zero-sum backfield: one back's gain is the other's loss.
        split = rng.normal(0, 5)
        rb1_pts = 12 + split + rng.normal(0, 1)
        rb2_pts = 8 - split + rng.normal(0, 1)
        for pid, name, pos, pts in [
            ("QB1", "Quinn Back", "QB", qb_pts),
            ("WR1", "Wide Out", "WR", wr_pts),
            ("RB1", "Run Back", "RB", rb1_pts),
            ("RB2", "Change Pace", "RB", rb2_pts),
        ]:
            rows.append(
                dict(
                    player_id=pid,
                    player_name=name,
                    position=pos,
                    recent_team="KC",
                    opponent_team="DEN",
                    season=season,
                    week=week,
                    receiving_yards=pts * 10,  # single stat -> points*1.0 at 0.1/yd
                )
            )
    return rows


@pytest.fixture
def synthetic_weekly():
    rng = np.random.default_rng(42)
    rows = []
    for season in TRAIN_SEASONS + HOLDOUT_SEASONS:
        rows += _weekly_rows(season, rng)
    return pd.DataFrame(rows)


@pytest.fixture
def points_df(synthetic_weekly):
    return compute_weekly_points(synthetic_weekly, scoring_format="standard")


# ---------------------------------------------------------------------------
# compute_weekly_points
# ---------------------------------------------------------------------------


class TestWeeklyPoints:
    def test_schema_and_scoring(self, synthetic_weekly):
        pts = compute_weekly_points(synthetic_weekly, scoring_format="standard")
        assert {"player_id", "team", "opponent", "season", "week", "points"} <= set(
            pts.columns
        )
        # receiving_yards * 0.1 = intended points
        row = pts[(pts["player_id"] == "QB1")].iloc[0]
        src = synthetic_weekly[
            (synthetic_weekly["player_id"] == "QB1")
            & (synthetic_weekly["season"] == row["season"])
            & (synthetic_weekly["week"] == row["week"])
        ].iloc[0]
        assert row["points"] == pytest.approx(src["receiving_yards"] * 0.1, abs=0.01)

    def test_playoffs_and_non_skill_excluded(self, synthetic_weekly):
        extra = pd.concat(
            [
                synthetic_weekly,
                pd.DataFrame(
                    [
                        dict(
                            player_id="K1",
                            player_name="Kicker",
                            position="K",
                            recent_team="KC",
                            opponent_team="DEN",
                            season=2020,
                            week=1,
                            receiving_yards=0,
                        ),
                        dict(
                            player_id="QB1",
                            player_name="Quinn Back",
                            position="QB",
                            recent_team="KC",
                            opponent_team="DEN",
                            season=2020,
                            week=19,
                            receiving_yards=100,
                        ),
                    ]
                ),
            ],
            ignore_index=True,
        )
        pts = compute_weekly_points(extra)
        assert "K1" not in set(pts["player_id"])
        assert pts["week"].max() <= 18

    def test_empty_input(self):
        assert compute_weekly_points(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_pair_observations
# ---------------------------------------------------------------------------


class TestPairObservations:
    def test_relations_assigned(self, points_df):
        obs = build_pair_observations(points_df)
        relations = set(obs["relation"].unique())
        assert "qb_stack" in relations  # QB1-WR1
        assert "same_backfield" in relations  # RB1-RB2
        # QB1-RB1 pairs carry no structural relation -> excluded
        qb_rb = obs[
            (obs["player_id_a"] == "QB1") & (obs["player_id_b"].str.startswith("RB"))
        ]
        assert qb_rb.empty

    def test_pair_ids_ordered(self, points_df):
        obs = build_pair_observations(points_df)
        assert (obs["player_id_a"] < obs["player_id_b"]).all()

    def test_game_stack_opposing_qbs(self):
        rows = []
        for week in (1, 2, 3):
            rows += [
                dict(
                    player_id="QB_KC",
                    player_name="A",
                    position="QB",
                    recent_team="KC",
                    opponent_team="DEN",
                    season=2024,
                    week=week,
                    receiving_yards=200,
                ),
                dict(
                    player_id="QB_DEN",
                    player_name="B",
                    position="QB",
                    recent_team="DEN",
                    opponent_team="KC",
                    season=2024,
                    week=week,
                    receiving_yards=180,
                ),
            ]
        pts = compute_weekly_points(pd.DataFrame(rows))
        obs = build_pair_observations(pts)
        stacks = obs[obs["relation"] == "game_stack"]
        assert len(stacks) == 3  # one row per meeting, not mirrored

    def test_empty_input(self):
        assert build_pair_observations(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# compute_correlation_edges (stability gate)
# ---------------------------------------------------------------------------


class TestCorrelationEdges:
    def test_stable_pairs_survive_with_correct_signs(self, points_df):
        edges = compute_correlation_edges(build_pair_observations(points_df))
        pairs = edges[edges["level"] == "pair"].set_index(
            ["player_id_a", "player_id_b"]
        )
        qb_wr = pairs.loc[("QB1", "WR1")]
        assert qb_wr["rho"] > 0.5  # engineered positive stack
        rb_rb = pairs.loc[("RB1", "RB2")]
        assert rb_rb["rho"] < -0.5  # engineered zero-sum backfield

    def test_sign_flip_rejected_by_gate(self):
        """A pair whose correlation flips sign between windows is not served."""
        rng = np.random.default_rng(7)
        rows = []
        for season in TRAIN_SEASONS:
            rows += _weekly_rows(season, rng, flip_qb_wr=False)
        for season in HOLDOUT_SEASONS:
            rows += _weekly_rows(season, rng, flip_qb_wr=True)  # sign flips
        pts = compute_weekly_points(pd.DataFrame(rows), scoring_format="standard")
        edges = compute_correlation_edges(build_pair_observations(pts))
        pairs = edges[edges["level"] == "pair"]
        qb_wr = pairs[(pairs["player_id_a"] == "QB1") & (pairs["player_id_b"] == "WR1")]
        assert qb_wr.empty, "sign-flipping edge must be gated out"
        # The stable backfield pair still survives
        rb = pairs[(pairs["player_id_a"] == "RB1") & (pairs["player_id_b"] == "RB2")]
        assert len(rb) == 1

    def test_min_games_enforced(self, points_df):
        # Truncate holdout to fewer than MIN_GAMES_HOLDOUT shared games.
        thin = points_df[
            (points_df["season"].isin(TRAIN_SEASONS))
            | (
                (points_df["season"] == HOLDOUT_SEASONS[0])
                & (points_df["week"] < 1 + MIN_GAMES_HOLDOUT - 1)
            )
        ]
        edges = compute_correlation_edges(build_pair_observations(thin))
        assert edges[edges["level"] == "pair"].empty

    def test_relation_priors_present_and_gated(self, points_df):
        edges = compute_correlation_edges(build_pair_observations(points_df))
        priors = edges[edges["level"] == "relation"].set_index("relation")
        assert priors.loc["qb_stack", "rho"] > 0
        assert priors.loc["same_backfield", "rho"] < 0

    def test_schema(self, points_df):
        edges = compute_correlation_edges(build_pair_observations(points_df))
        assert list(edges.columns) == EDGE_COLUMNS

    def test_empty_input(self):
        edges = compute_correlation_edges(pd.DataFrame())
        assert edges.empty
        assert list(edges.columns) == EDGE_COLUMNS


# ---------------------------------------------------------------------------
# compute_stack_insights
# ---------------------------------------------------------------------------


class TestStackInsights:
    @pytest.fixture
    def edges(self, points_df):
        return compute_correlation_edges(build_pair_observations(points_df))

    def test_lineup_pair_detection(self, edges):
        insights = compute_stack_insights(["QB1", "WR1", "RB1"], edges)
        pairs = {(i["player_id_a"], i["player_id_b"]) for i in insights}
        assert ("QB1", "WR1") in pairs
        assert ("RB1", "RB2") not in pairs  # RB2 not in the lineup

    def test_insight_types(self, edges):
        insights = compute_stack_insights(["QB1", "WR1", "RB1", "RB2"], edges)
        by_pair = {(i["player_id_a"], i["player_id_b"]): i for i in insights}
        assert by_pair[("QB1", "WR1")]["insight"] == "stack_bonus"
        assert by_pair[("RB1", "RB2")]["insight"] == "shared_ceiling_warning"

    def test_sorted_by_abs_rho(self, edges):
        insights = compute_stack_insights(["QB1", "WR1", "RB1", "RB2"], edges)
        rhos = [abs(i["rho"]) for i in insights]
        assert rhos == sorted(rhos, reverse=True)

    def test_empty_inputs(self, edges):
        assert compute_stack_insights([], edges) == []
        assert compute_stack_insights(["QB1"], pd.DataFrame(columns=EDGE_COLUMNS)) == []


# ---------------------------------------------------------------------------
# API endpoint (TestClient with mocked edge data)
# ---------------------------------------------------------------------------


class TestCorrelationsApi:
    @pytest.fixture
    def client(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from fastapi.testclient import TestClient

        from web.api.main import app

        return TestClient(app)

    @pytest.fixture
    def mock_edges(self):
        return pd.DataFrame(
            [
                dict(
                    level="pair",
                    relation="qb_stack",
                    player_id_a="00-QB",
                    player_id_b="00-WR",
                    player_name_a="Quinn Back",
                    player_name_b="Wide Out",
                    rho=0.55,
                    n_games=40,
                    rho_train=0.5,
                    n_train=30,
                    rho_holdout=0.6,
                    n_holdout=10,
                ),
                dict(
                    level="pair",
                    relation="same_backfield",
                    player_id_a="00-QB",
                    player_id_b="00-RB",
                    player_name_a="Quinn Back",
                    player_name_b="Run Back",
                    rho=0.05,
                    n_games=30,
                    rho_train=0.04,
                    n_train=20,
                    rho_holdout=0.06,
                    n_holdout=10,
                ),
                dict(
                    level="relation",
                    relation="qb_stack",
                    player_id_a=None,
                    player_id_b=None,
                    player_name_a=None,
                    player_name_b=None,
                    rho=0.21,
                    n_games=30000,
                    rho_train=0.22,
                    n_train=20000,
                    rho_holdout=0.21,
                    n_holdout=10000,
                ),
            ]
        )

    def test_player_correlations_endpoint(self, client, mock_edges):
        from unittest.mock import patch

        with patch(
            "graph_correlation.load_latest_correlations", return_value=mock_edges
        ):
            resp = client.get("/api/players/00-QB/correlations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["player_id"] == "00-QB"
        # min_rho default 0.1 keeps only the 0.55 edge; relation rows excluded
        assert len(body["correlations"]) == 1
        edge = body["correlations"][0]
        assert edge["other_player_id"] == "00-WR"
        assert edge["other_player_name"] == "Wide Out"
        assert edge["rho"] == pytest.approx(0.55)

    def test_min_rho_filter(self, client, mock_edges):
        from unittest.mock import patch

        with patch(
            "graph_correlation.load_latest_correlations", return_value=mock_edges
        ):
            resp = client.get("/api/players/00-QB/correlations?min_rho=0.01")
        assert len(resp.json()["correlations"]) == 2

    def test_no_data_returns_empty_200(self, client):
        from unittest.mock import patch

        with patch(
            "graph_correlation.load_latest_correlations",
            return_value=pd.DataFrame(columns=EDGE_COLUMNS),
        ):
            resp = client.get("/api/players/00-QB/correlations")
        assert resp.status_code == 200
        assert resp.json()["correlations"] == []

    def test_load_failure_returns_empty_200(self, client):
        """An import/load crash must serve empty, never a 500."""
        from unittest.mock import patch

        with patch(
            "graph_correlation.load_latest_correlations",
            side_effect=RuntimeError("parquet corrupted"),
        ):
            resp = client.get("/api/players/00-QB/correlations")
        assert resp.status_code == 200
        assert resp.json()["correlations"] == []


# ---------------------------------------------------------------------------
# Integration smoke test on real local data
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRealDataSmoke:
    def test_build_real_edges(self):
        from graph_correlation import build_correlation_data

        edges = build_correlation_data()
        if edges.empty:
            pytest.skip("Local Bronze weekly data 2016-2025 not available")

        pairs = edges[edges["level"] == "pair"]
        priors = edges[edges["level"] == "relation"].set_index("relation")

        assert len(pairs) > 50  # enough long-running stable pairs exist
        # Football sanity: QB-stack and game-stack priors are positive and
        # stable (the two real effects). The naive "zero-sum backfield" and
        # WR-teammate negatives are ~0 and sign-UNSTABLE in real data
        # (team quality lifts teammates together, cancelling the split) —
        # the gate must refuse to serve those relation priors.
        assert priors.loc["qb_stack", "rho"] > 0.15
        assert priors.loc["game_stack", "rho"] > 0.15
        assert "same_backfield" not in priors.index
        assert "wr_teammates" not in priors.index
        # Every served pair passed the gate thresholds.
        assert (pairs["n_train"] >= MIN_GAMES_TRAIN).all()
        assert (pairs["n_holdout"] >= MIN_GAMES_HOLDOUT).all()
        assert (np.sign(pairs["rho_train"]) == np.sign(pairs["rho_holdout"])).all()
