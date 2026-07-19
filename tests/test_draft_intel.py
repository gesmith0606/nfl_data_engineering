"""Tests for src/draft_intel.py -- Sleeper league draft-tendency intel.

All Sleeper HTTP reads are mocked at the ``draft_intel`` module level (the
names it imported from ``src/sleeper_http.py``), matching the D-06
fail-open contract those helpers already guarantee -- no real network calls.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import draft_intel  # noqa: E402
from draft_intel import (  # noqa: E402
    build_league_draft_intel,
    get_cached_league_draft_intel,
    intel_to_bot_behavior,
)

# ---------------------------------------------------------------------------
# Synthetic 2-season, 2-manager league-history chain
# ---------------------------------------------------------------------------

_LEAGUES = {
    "L2026": {"league_id": "L2026", "season": "2026", "previous_league_id": "L2025"},
    "L2025": {"league_id": "L2025", "season": "2025", "previous_league_id": None},
}

_USERS = [
    {"user_id": "U1", "display_name": "Alice", "metadata": {"team_name": "Alice's Team"}},
    {"user_id": "U2", "display_name": "Bob", "metadata": {}},
]

_DRAFTS = {
    "L2026": [{"draft_id": "D2026", "status": "complete"}],
    "L2025": [{"draft_id": "D2025", "status": "complete"}],
}


def _pick(round_, pick_no, picked_by, position):
    return {
        "round": round_,
        "pick_no": pick_no,
        "picked_by": picked_by,
        "metadata": {"position": position},
    }


_PICKS = {
    "D2026": [
        # U1 opens RB-RB, then WR (round 3) -- no QB this season.
        _pick(1, 1, "U1", "RB"),
        _pick(2, 3, "U1", "RB"),
        _pick(3, 5, "U1", "WR"),
        # U2 takes QB round 1, then WR-WR (wr-heavy early).
        _pick(1, 2, "U2", "QB"),
        _pick(2, 4, "U2", "WR"),
        _pick(3, 6, "U2", "WR"),
    ],
    "D2025": [
        # U1: RB, WR, WR (wr-heavy, not opens-RB-RB).
        _pick(1, 1, "U1", "RB"),
        _pick(2, 3, "U1", "WR"),
        _pick(3, 5, "U1", "WR"),
        # U2: QB, RB, RB (QB by round 4 again, not wr-heavy).
        _pick(1, 2, "U2", "QB"),
        _pick(2, 4, "U2", "RB"),
        _pick(3, 6, "U2", "RB"),
    ],
}


def _fake_get_league(league_id):
    return _LEAGUES.get(league_id, {})


def _fake_get_league_users(league_id):
    return _USERS if league_id in _LEAGUES else []


def _fake_get_drafts_for_league(league_id):
    return _DRAFTS.get(league_id, [])


def _fake_get_draft_picks(draft_id):
    return _PICKS.get(draft_id, [])


@pytest.fixture(autouse=True)
def _patch_sleeper_http(monkeypatch):
    monkeypatch.setattr(draft_intel, "get_league", _fake_get_league)
    monkeypatch.setattr(draft_intel, "get_league_users", _fake_get_league_users)
    monkeypatch.setattr(draft_intel, "get_drafts_for_league", _fake_get_drafts_for_league)
    monkeypatch.setattr(draft_intel, "get_draft_picks", _fake_get_draft_picks)
    draft_intel._intel_cache.clear()
    yield
    draft_intel._intel_cache.clear()


class TestBuildLeagueDraftIntel:
    def test_seasons_analyzed_and_manager_count(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        assert result["league_id"] == "L2026"
        assert result["seasons_analyzed"] == 2
        assert {m["user_id"] for m in result["managers"]} == {"U1", "U2"}

    def test_display_names_and_team_name(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        alice = next(m for m in result["managers"] if m["user_id"] == "U1")
        assert alice["display_name"] == "Alice"
        assert alice["team_name"] == "Alice's Team"
        bob = next(m for m in result["managers"] if m["user_id"] == "U2")
        assert bob["display_name"] == "Bob"
        assert bob["team_name"] is None

    def test_u1_opens_rb_rb_in_2026_only(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        u1 = next(m for m in result["managers"] if m["user_id"] == "U1")
        t = u1["tendencies"]
        assert t["opens_rb_rb_seasons"] == ["2026"]
        assert t["first_round_by_season"] == {"2026": "RB", "2025": "RB"}
        assert t["modal_first_round_position"] == "RB"
        # RB is not a "notable" first-round position -- no round-1 headline.
        assert not any("round 1" in s for s in u1["summary"])

    def test_u1_wr_heavy_in_2025_only(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        u1 = next(m for m in result["managers"] if m["user_id"] == "U1")
        assert u1["tendencies"]["wr_heavy_early_seasons"] == ["2025"]

    def test_u2_modal_qb_and_qb_by_round_4_summary(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        u2 = next(m for m in result["managers"] if m["user_id"] == "U2")
        t = u2["tendencies"]
        assert t["modal_first_round_position"] == "QB"
        assert t["qb_by_round_seasons"] == {"2026": 1, "2025": 1}
        assert any("QB in round 1 in 2 of 2 drafts" in s for s in u2["summary"])
        assert any("QB by round 4 in 2 of 2 drafts" in s for s in u2["summary"])

    def test_u2_wr_heavy_in_2026_only(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        u2 = next(m for m in result["managers"] if m["user_id"] == "U2")
        assert u2["tendencies"]["wr_heavy_early_seasons"] == ["2026"]

    def test_position_counts_and_shares_sum_correctly(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        u1 = next(m for m in result["managers"] if m["user_id"] == "U1")
        counts = u1["tendencies"]["position_counts_rounds_1_3"]
        # 2026: RB,RB,WR ; 2025: RB,WR,WR -> RB=3, WR=3
        assert counts == {"RB": 3, "WR": 3}
        shares = u1["tendencies"]["early_position_shares"]
        assert shares["RB"] == pytest.approx(0.5)
        assert shares["WR"] == pytest.approx(0.5)

    def test_max_seasons_limits_chain_walk(self):
        result = build_league_draft_intel("L2026", max_seasons=1)
        assert result["seasons_analyzed"] == 1
        u1 = next(m for m in result["managers"] if m["user_id"] == "U1")
        assert list(u1["tendencies"]["first_round_by_season"].keys()) == ["2026"]

    def test_tendencies_dict_has_no_leftover_summary_key(self):
        result = build_league_draft_intel("L2026", max_seasons=3)
        for m in result["managers"]:
            assert "summary" not in m["tendencies"]


class TestFailOpen:
    def test_empty_league_id_returns_empty(self):
        result = build_league_draft_intel("", max_seasons=3)
        assert result == {"league_id": "", "seasons_analyzed": 0, "managers": []}

    def test_unknown_league_returns_empty(self):
        result = build_league_draft_intel("does-not-exist", max_seasons=3)
        assert result["seasons_analyzed"] == 0
        assert result["managers"] == []

    def test_league_lookup_raises_fails_open(self, monkeypatch):
        def _boom(league_id):
            raise RuntimeError("network down")

        monkeypatch.setattr(draft_intel, "get_league", _boom)
        result = build_league_draft_intel("L2026", max_seasons=3)
        assert result == {"league_id": "L2026", "seasons_analyzed": 0, "managers": []}

    def test_no_completed_drafts_skips_season(self, monkeypatch):
        monkeypatch.setattr(draft_intel, "get_drafts_for_league", lambda lid: [])
        result = build_league_draft_intel("L2026", max_seasons=3)
        assert result["seasons_analyzed"] == 0
        assert result["managers"] == []

    def test_picks_fetch_exception_skips_that_season_only(self, monkeypatch):
        real_picks = draft_intel.get_draft_picks

        def _flaky(draft_id):
            if draft_id == "D2025":
                raise RuntimeError("timeout")
            return real_picks(draft_id)

        monkeypatch.setattr(draft_intel, "get_draft_picks", _flaky)
        result = build_league_draft_intel("L2026", max_seasons=3)
        assert result["seasons_analyzed"] == 1
        u1 = next(m for m in result["managers"] if m["user_id"] == "U1")
        assert list(u1["tendencies"]["first_round_by_season"].keys()) == ["2026"]


class TestCaching:
    def test_cached_wrapper_returns_same_result_without_refetch(self, monkeypatch):
        calls = {"n": 0}
        real = draft_intel.get_league

        def _counting(league_id):
            calls["n"] += 1
            return real(league_id)

        monkeypatch.setattr(draft_intel, "get_league", _counting)
        first = get_cached_league_draft_intel("L2026", max_seasons=3)
        n_after_first = calls["n"]
        second = get_cached_league_draft_intel("L2026", max_seasons=3)
        assert second == first
        assert calls["n"] == n_after_first  # no additional get_league calls


class TestIntelToBotBehavior:
    def test_none_or_empty_returns_defaults(self):
        assert intel_to_bot_behavior(None) == {"run_factor": 1.5, "temperature": 3.0}
        assert intel_to_bot_behavior({}) == {"run_factor": 1.5, "temperature": 3.0}

    def test_fully_consistent_opener_lowers_temperature(self):
        tendencies = {
            "first_round_by_season": {"2026": "RB", "2025": "RB"},
            "opens_rb_rb_seasons": ["2026", "2025"],
            "wr_heavy_early_seasons": [],
        }
        behavior = intel_to_bot_behavior(tendencies)
        assert behavior["temperature"] == pytest.approx(1.0)
        assert behavior["run_factor"] == pytest.approx(1.5)

    def test_frequent_wr_runs_raise_run_factor(self):
        tendencies = {
            "first_round_by_season": {"2026": "QB", "2025": "QB"},
            "opens_rb_rb_seasons": [],
            "wr_heavy_early_seasons": ["2026", "2025"],
        }
        behavior = intel_to_bot_behavior(tendencies)
        assert behavior["run_factor"] == pytest.approx(2.5)
        assert behavior["temperature"] == pytest.approx(3.0)

    def test_output_is_mock_draft_simulator_behavior_compatible(self):
        """Sanity: the returned dict is exactly the shape
        MockDraftSimulator(behavior=...) expects (run_factor/temperature),
        and it doesn't raise when passed to the real simulator constructor.
        """
        import pandas as pd

        from draft_optimizer import DraftBoard, MockDraftSimulator

        result = build_league_draft_intel("L2026", max_seasons=3)
        u2 = next(m for m in result["managers"] if m["user_id"] == "U2")
        behavior = intel_to_bot_behavior(u2["tendencies"])
        assert set(behavior.keys()) == {"run_factor", "temperature"}

        players = pd.DataFrame(
            [{"player_id": "P1", "player_name": "X", "position": "RB",
              "projected_season_points": 100.0, "adp_rank": 1.0}]
        )
        board = DraftBoard(players, roster_format="standard", n_teams=12)
        sim = MockDraftSimulator(board=board, user_pick=1, n_teams=12, behavior=behavior)
        assert sim.behavior["run_factor"] == behavior["run_factor"]
        assert sim.behavior["temperature"] == behavior["temperature"]
