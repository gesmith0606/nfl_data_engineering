"""Tests for the UC1 sleeper board (scripts/sleeper_board.py)."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import sleeper_board


@pytest.fixture
def fake_features():
    return pd.DataFrame(
        [
            # Big absorber, not in consensus -> true sleeper
            dict(
                player_id="RB_DEEP",
                team="CAR",
                position="RB",
                season=2026,
                vacated_target_share_abs=0.10,
                vacated_carry_share_abs=0.50,
                rz_vacancy_share=0.1,
                net_target_vacancy=0.06,
                net_carry_vacancy=0.48,
                vacancy_competition_n=4,
                arrival_displacement=0.0,
                vacancy_absorbed_share=0.20,
            ),
            # Big absorber but consensus ranks him -> excluded by default
            dict(
                player_id="RB_STAR",
                team="CAR",
                position="RB",
                season=2026,
                vacated_target_share_abs=0.10,
                vacated_carry_share_abs=0.50,
                rz_vacancy_share=0.1,
                net_target_vacancy=0.06,
                net_carry_vacancy=0.48,
                vacancy_competition_n=4,
                arrival_displacement=0.0,
                vacancy_absorbed_share=0.30,
            ),
            # Trace absorption -> filtered by MIN_ABSORBED_SHARE
            dict(
                player_id="RB_NOISE",
                team="ATL",
                position="RB",
                season=2026,
                vacated_target_share_abs=0.02,
                vacated_carry_share_abs=0.02,
                rz_vacancy_share=0.0,
                net_target_vacancy=0.01,
                net_carry_vacancy=0.01,
                vacancy_competition_n=2,
                arrival_displacement=0.0,
                vacancy_absorbed_share=0.005,
            ),
            # WR absorber for position filtering
            dict(
                player_id="WR_DEEP",
                team="NYJ",
                position="WR",
                season=2026,
                vacated_target_share_abs=0.20,
                vacated_carry_share_abs=0.0,
                rz_vacancy_share=0.05,
                net_target_vacancy=0.18,
                net_carry_vacancy=0.0,
                vacancy_competition_n=3,
                arrival_displacement=0.0,
                vacancy_absorbed_share=0.09,
            ),
        ]
    )


@pytest.fixture
def fake_names():
    return pd.DataFrame(
        [
            dict(player_id="RB_DEEP", player_name="Deep Sleeper"),
            dict(player_id="RB_STAR", player_name="Known Starter"),
            dict(player_id="RB_NOISE", player_name="Camp Body"),
            dict(player_id="WR_DEEP", player_name="Slot Riser"),
        ]
    )


@pytest.fixture
def fake_consensus():
    return pd.DataFrame(
        [dict(name_key="known starter", position="RB", consensus_pos_rank=22.0)]
    )


@pytest.fixture(autouse=True)
def _patch_io(monkeypatch, fake_features, fake_names, fake_consensus):
    monkeypatch.setattr(
        sleeper_board, "build_vacated_opportunity_data", lambda s: fake_features
    )
    monkeypatch.setattr(sleeper_board, "_load_player_names", lambda s: fake_names)
    monkeypatch.setattr(sleeper_board, "_load_consensus", lambda: fake_consensus)


class TestSleeperBoard:
    def test_default_view_excludes_consensus_ranked(self):
        board = sleeper_board.build_sleeper_board(2026)
        names = set(board["player_name"])
        assert "Deep Sleeper" in names
        assert "Known Starter" not in names  # consensus ranks him

    def test_include_ranked_shows_everyone(self):
        board = sleeper_board.build_sleeper_board(2026, include_ranked=True)
        names = set(board["player_name"])
        assert {"Deep Sleeper", "Known Starter"} <= names
        star = board[board["player_name"] == "Known Starter"].iloc[0]
        assert star["consensus_pos_rank"] == 22.0

    def test_noise_threshold_filters_trace_absorption(self):
        board = sleeper_board.build_sleeper_board(2026, include_ranked=True)
        assert "Camp Body" not in set(board["player_name"])

    def test_position_filter(self):
        board = sleeper_board.build_sleeper_board(2026, position="WR")
        assert set(board["position"]) == {"WR"}
        assert "Slot Riser" in set(board["player_name"])

    def test_sorted_by_absorption_desc(self):
        board = sleeper_board.build_sleeper_board(2026, include_ranked=True)
        vals = board["vacancy_absorbed_share"].tolist()
        assert vals == sorted(vals, reverse=True)

    def test_empty_features_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            sleeper_board, "build_vacated_opportunity_data", lambda s: pd.DataFrame()
        )
        assert sleeper_board.build_sleeper_board(2026).empty

    def test_name_key_suffix_handling(self):
        assert sleeper_board._name_key("Kenneth Walker III") == "kenneth walker"
        assert sleeper_board._name_key("Ja'Marr Chase") == "jamarr chase"
