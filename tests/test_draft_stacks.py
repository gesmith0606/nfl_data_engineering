"""Tests for src/draft_stacks.py -- correlation-network stack hints."""

from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_stacks import (  # noqa: E402
    SHARED_CEILING_RHO_MAX,
    STACK_BONUS_RHO_MIN,
    get_stack_hints,
)


def _available_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": "P100",
                "player_name": "Available WR",
                "position": "WR",
                "recent_team": "KC",
            },
            {
                "player_id": "P200",
                "player_name": "Available RB",
                "position": "RB",
                "recent_team": "SF",
            },
            {
                "player_id": "P300",
                "player_name": "Neutral TE",
                "position": "TE",
                "recent_team": "DET",
            },
        ]
    )


def _my_roster() -> list:
    return [{"player_id": "P001", "player_name": "My QB", "position": "QB"}]


def _edges_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "level": "pair",
                "relation": "qb_stack",
                "player_id_a": "P001",
                "player_id_b": "P100",
                "player_name_a": "My QB",
                "player_name_b": "Available WR",
                "rho": 0.42,
                "n_games": 30,
            },
            {
                "level": "pair",
                "relation": "same_backfield",
                "player_id_a": "P001",
                "player_id_b": "P200",
                "player_name_a": "My QB",
                "player_name_b": "Available RB",
                "rho": -0.35,
                "n_games": 20,
            },
            {
                # Below both thresholds -- must not surface.
                "level": "pair",
                "relation": "wr_teammates",
                "player_id_a": "P001",
                "player_id_b": "P300",
                "player_name_a": "My QB",
                "player_name_b": "Neutral TE",
                "rho": 0.05,
                "n_games": 15,
            },
            {
                # Relation-level prior row (no player ids) -- must be ignored.
                "level": "relation",
                "relation": "qb_stack",
                "player_id_a": None,
                "player_id_b": None,
                "player_name_a": None,
                "player_name_b": None,
                "rho": 0.30,
                "n_games": 500,
            },
        ]
    )


class TestGetStackHints:
    def test_positive_edge_yields_stack_bonus(self):
        hints = get_stack_hints(_available_df(), _my_roster(), edges_df=_edges_df())
        bonus = [h for h in hints if h["kind"] == "stack_bonus"]
        assert len(bonus) == 1
        h = bonus[0]
        assert h["player_name"] == "Available WR"
        assert h["position"] == "WR"
        assert h["team"] == "KC"
        assert h["rostered_player_name"] == "My QB"
        assert h["rho"] == pytest.approx(0.42)
        assert h["n_games"] == 30

    def test_negative_edge_yields_shared_ceiling_warning(self):
        hints = get_stack_hints(_available_df(), _my_roster(), edges_df=_edges_df())
        warnings = [h for h in hints if h["kind"] == "shared_ceiling_warning"]
        assert len(warnings) == 1
        assert warnings[0]["player_name"] == "Available RB"
        assert warnings[0]["rho"] == pytest.approx(-0.35)

    def test_weak_edge_below_threshold_excluded(self):
        hints = get_stack_hints(_available_df(), _my_roster(), edges_df=_edges_df())
        names = {h["player_name"] for h in hints}
        assert "Neutral TE" not in names

    def test_relation_level_prior_ignored(self):
        hints = get_stack_hints(_available_df(), _my_roster(), edges_df=_edges_df())
        assert all(h["player_name"] != "" for h in hints)
        assert len(hints) == 2  # only the two qualifying pair-level edges

    def test_thresholds_match_module_constants(self):
        assert STACK_BONUS_RHO_MIN == 0.25
        assert SHARED_CEILING_RHO_MAX == -0.20

    def test_empty_roster_returns_empty(self):
        assert get_stack_hints(_available_df(), [], edges_df=_edges_df()) == []

    def test_empty_available_returns_empty(self):
        assert (
            get_stack_hints(pd.DataFrame(), _my_roster(), edges_df=_edges_df()) == []
        )

    def test_none_available_returns_empty(self):
        assert get_stack_hints(None, _my_roster(), edges_df=_edges_df()) == []

    def test_no_edges_dataset_fails_open(self):
        assert get_stack_hints(_available_df(), _my_roster(), edges_df=pd.DataFrame()) == []

    def test_missing_edges_artifact_on_disk_fails_open(self, monkeypatch):
        """No edges_df passed in -- falls back to the on-disk loader, which
        should fail open (empty list) when no artifact exists.
        """
        import draft_stacks

        monkeypatch.setattr(
            draft_stacks, "load_latest_correlations", lambda: pd.DataFrame()
        )
        hints = get_stack_hints(_available_df(), _my_roster())
        assert hints == []

    def test_loader_exception_fails_open(self, monkeypatch):
        import draft_stacks

        def _boom():
            raise RuntimeError("disk error")

        monkeypatch.setattr(draft_stacks, "load_latest_correlations", _boom)
        hints = get_stack_hints(_available_df(), _my_roster())
        assert hints == []

    def test_edge_to_drafted_players_only_not_surfaced(self):
        """An edge between two players NEITHER of which is on the roster
        (or both already drafted) should not surface a hint."""
        edges = pd.DataFrame(
            [
                {
                    "level": "pair",
                    "relation": "wr_teammates",
                    "player_id_a": "P999",
                    "player_id_b": "P998",
                    "player_name_a": "Nobody A",
                    "player_name_b": "Nobody B",
                    "rho": 0.5,
                    "n_games": 10,
                }
            ]
        )
        hints = get_stack_hints(_available_df(), _my_roster(), edges_df=edges)
        assert hints == []
