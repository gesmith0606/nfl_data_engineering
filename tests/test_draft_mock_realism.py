"""Tests for the MockDraftSimulator realism upgrade (Lane 2):

* opponents respect roster-slot limits (no 3rd QB before round 11, no
  unstartable depth hoarding, K/DST filled late like a real human),
* positional runs measurably amplify continuation of that position,
* the public API stays backward compatible with existing callers.
"""

from __future__ import annotations

import os
import random
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
)

_CFG = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DST": 1}


def _full_pool(n_per_pos: int = 100) -> pd.DataFrame:
    """A player pool deep enough to survive a 12-team, 15-round draft
    (180 picks) across every startable position, including K/DST, without
    any single position running dry (which would force a bot to exceed its
    depth cap simply because nothing legal is left on the board)."""
    rows = []
    for pos, base in (
        ("QB", 380),
        ("RB", 320),
        ("WR", 330),
        ("TE", 250),
        ("K", 140),
        ("DST", 130),
    ):
        for i in range(n_per_pos):
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "player_name": f"{pos} {i}",
                    "position": pos,
                    "projected_season_points": base - i * 3,
                }
            )
    return compute_value_scores(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# Roster-need awareness: full seeded draft, no violations
# ---------------------------------------------------------------------------


def test_full_seeded_draft_has_no_roster_rule_violations():
    random.seed(20260718)
    board = DraftBoard(_full_pool(), n_teams=12, roster_config=_CFG)
    advisor = DraftAdvisor(board)
    sim = MockDraftSimulator(
        board, user_pick=4, n_teams=12, randomness=3, draft_type="snake"
    )
    sim.run_full_simulation(advisor, rounds=15)

    assert sim._opp_rosters, "expected opponent picks to be tracked"
    for slot, positions in sim._opp_rosters.items():
        counts: Counter = Counter()
        for round_idx, pos in enumerate(positions, start=1):
            counts[pos] += 1
            if pos == "QB":
                # Never a 3rd QB in the first 10 rounds.
                assert not (counts["QB"] >= 3 and round_idx <= 10), (
                    f"slot {slot} drafted a 3rd QB by round {round_idx}"
                )

        # Never exceed a sane depth cap per position (starters + bench).
        assert counts.get("QB", 0) <= 3
        assert counts.get("TE", 0) <= _CFG["TE"] + 2
        assert counts.get("RB", 0) <= _CFG["RB"] + _CFG["FLEX"] + 3
        assert counts.get("WR", 0) <= _CFG["WR"] + _CFG["FLEX"] + 3
        # K/DST: exactly one starter each, never a 2nd (deep enough pool that
        # every bot should have filled its single required slot by round 15).
        assert counts.get("K", 0) == 1, f"slot {slot} K count = {counts.get('K', 0)}"
        assert counts.get("DST", 0) == 1, f"slot {slot} DST count = {counts.get('DST', 0)}"


def test_kicker_and_dst_are_filled_late_not_early():
    random.seed(4242)
    board = DraftBoard(_full_pool(), n_teams=12, roster_config=_CFG)
    advisor = DraftAdvisor(board)
    sim = MockDraftSimulator(
        board, user_pick=1, n_teams=12, randomness=3, draft_type="snake"
    )
    sim.run_full_simulation(advisor, rounds=15)

    for slot, positions in sim._opp_rosters.items():
        k_round = next(
            (i for i, p in enumerate(positions, start=1) if p == "K"), None
        )
        dst_round = next(
            (i for i, p in enumerate(positions, start=1) if p == "DST"), None
        )
        assert k_round is not None and dst_round is not None
        # Filled in the back half of a 15-round draft, like a real human.
        assert k_round >= 8, f"slot {slot} took a K too early (round {k_round})"
        assert dst_round >= 8, f"slot {slot} took a DST too early (round {dst_round})"


# ---------------------------------------------------------------------------
# Positional-run amplification
# ---------------------------------------------------------------------------


def _run_trial_positions(behavior: dict, n_trials: int, seed: int) -> list:
    """Run ``simulate_opponent_pick`` once per trial from a fixed history
    (2 of the last 4 picks were RB -- a live run) and record what position
    gets drafted each time."""
    random.seed(seed)
    rows = []
    for i, pos in enumerate((["QB", "RB", "WR", "TE"] * 3)):
        rows.append(
            {
                "player_id": f"{pos}{i}",
                "player_name": f"{pos} {i}",
                "position": pos,
                "projected_season_points": 300 - i,
            }
        )
    pool = compute_value_scores(pd.DataFrame(rows))

    picked = []
    for _ in range(n_trials):
        board = DraftBoard(pool.copy(), n_teams=12, roster_config=_CFG)
        sim = MockDraftSimulator(
            board,
            user_pick=1,
            n_teams=12,
            randomness=5,
            draft_type="snake",
            behavior=behavior,
        )
        sim._recent_positions = ["RB", "WR", "RB", "QB"]  # RB run in progress
        name = sim.simulate_opponent_pick(1)
        row = board.all_players[board.all_players["player_name"] == name].iloc[0]
        picked.append(row["position"])
    return picked


def test_positional_run_amplifies_continuation_vs_baseline():
    n_trials = 300
    baseline = _run_trial_positions(
        {"run_factor": 1.0, "temperature": 5.0}, n_trials, seed=1
    )
    amplified = _run_trial_positions(
        {"run_factor": 4.0, "temperature": 5.0}, n_trials, seed=1
    )

    baseline_rate = baseline.count("RB") / n_trials
    amplified_rate = amplified.count("RB") / n_trials

    assert amplified_rate > baseline_rate + 0.05, (
        f"expected run amplification: baseline={baseline_rate:.3f} "
        f"amplified={amplified_rate:.3f}"
    )


def test_run_position_detection():
    board = DraftBoard(_full_pool(4), n_teams=12, roster_config=_CFG)
    sim = MockDraftSimulator(board, user_pick=1, n_teams=12)

    sim._recent_positions = []
    assert sim._run_position() is None

    sim._recent_positions = ["WR"]
    assert sim._run_position() is None  # only 1 pick of history

    sim._recent_positions = ["QB", "RB", "WR", "TE"]
    assert sim._run_position() is None  # no position repeats

    sim._recent_positions = ["RB", "WR", "RB", "QB"]
    assert sim._run_position() == "RB"

    sim._recent_positions = ["WR", "WR", "WR", "WR"]
    assert sim._run_position() == "WR"


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


def test_constructor_without_behavior_kwarg_still_works():
    board = DraftBoard(_full_pool(4), n_teams=12, roster_config=_CFG)
    sim = MockDraftSimulator(board, user_pick=1, n_teams=12, randomness=3)
    assert sim.behavior == {"run_factor": 1.5, "temperature": 3.0}


def test_behavior_dict_overrides_only_given_keys():
    board = DraftBoard(_full_pool(4), n_teams=12, roster_config=_CFG)
    sim = MockDraftSimulator(
        board, user_pick=1, n_teams=12, behavior={"run_factor": 2.0}
    )
    assert sim.behavior["run_factor"] == 2.0
    assert sim.behavior["temperature"] == 3.0  # untouched default


def test_simulate_opponent_pick_still_returns_player_name_and_advances_board():
    random.seed(1)
    board = DraftBoard(_full_pool(4), n_teams=12, roster_config=_CFG)
    sim = MockDraftSimulator(board, user_pick=1, n_teams=12, randomness=3)
    before = len(board.available)
    name = sim.simulate_opponent_pick(2)
    assert isinstance(name, str) and name
    assert len(board.available) == before - 1
    assert len(board.drafted_by_others) == 1


def test_simulate_opponent_pick_on_empty_board_returns_none():
    board = DraftBoard(
        pd.DataFrame(
            columns=["player_id", "player_name", "position", "projected_season_points"]
        ),
        n_teams=12,
        roster_config=_CFG,
    )
    sim = MockDraftSimulator(board, user_pick=1, n_teams=12)
    assert sim.simulate_opponent_pick(1) is None
