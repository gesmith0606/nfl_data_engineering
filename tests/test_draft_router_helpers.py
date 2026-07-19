"""Unit tests for the tier / gone_probability wiring helpers added to
``web/api/routers/draft.py`` (Lane 2). Exercises the pure-Python helpers
directly rather than through the full FastAPI session fixture stack, so
these stay fast and independent of the existing mock-projection fixtures in
test_draft_api.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "web"))

import api  # noqa: E402  (bootstraps src/ on sys.path for the router's imports)
from api.routers.draft import (  # noqa: E402
    _safe_tier,
    _user_next_pick_number,
)
from draft_optimizer import DraftBoard, MockDraftSimulator, compute_value_scores  # noqa: E402
from draft_tiers import compute_tiers  # noqa: E402


def _pool():
    rows = []
    for pos, base in (("QB", 380), ("RB", 320), ("WR", 300), ("TE", 240)):
        for i in range(10):
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "player_name": f"{pos} {i}",
                    "position": pos,
                    "projected_season_points": base - i * 8,
                }
            )
    return compute_value_scores(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# _safe_tier
# ---------------------------------------------------------------------------


def test_safe_tier_converts_float_to_int():
    assert _safe_tier(2.0) == 2


def test_safe_tier_none_for_nan():
    assert _safe_tier(float("nan")) is None


def test_safe_tier_none_for_missing():
    assert _safe_tier(None) is None


def test_safe_tier_none_for_non_numeric():
    assert _safe_tier("not-a-number") is None


# ---------------------------------------------------------------------------
# tier column is actually produced end-to-end by compute_tiers on a
# compute_value_scores frame (what _load_draft_data wires together)
# ---------------------------------------------------------------------------


def test_compute_tiers_integrates_with_compute_value_scores_output():
    enriched = _pool()
    enriched["tier"] = compute_tiers(enriched)
    assert enriched["tier"].notna().all()  # no NaN points in this fixture
    assert enriched["tier"].min() == 1
    # Best player at each position should be tier 1.
    for pos in ("QB", "RB", "WR", "TE"):
        sub = enriched[enriched["position"] == pos]
        best = sub.loc[sub["projected_season_points"].idxmax()]
        assert best["tier"] == 1


# ---------------------------------------------------------------------------
# _user_next_pick_number
# ---------------------------------------------------------------------------


def test_user_next_pick_number_none_without_any_slot():
    board = DraftBoard(_pool(), n_teams=12, roster_config={"QB": 1})
    session = {"board": board}
    assert _user_next_pick_number(session, board, None) is None


def test_user_next_pick_number_uses_query_param_for_plain_board_session():
    board = DraftBoard(_pool(), n_teams=4, roster_config={"QB": 1})
    session = {"board": board}
    # No picks made yet -> user at slot 2 is on the clock for pick 2.
    assert _user_next_pick_number(session, board, user_pick=2) == 2


def test_user_next_pick_number_prefers_session_mock_slot_over_param():
    board = DraftBoard(_pool(), n_teams=4, roster_config={"QB": 1})
    session = {"board": board, "user_pick": 3}
    # Session's mock-draft slot (3) wins even if a different param is passed.
    assert _user_next_pick_number(session, board, user_pick=1) == 3


def test_user_next_pick_number_respects_snake_order_after_picks():
    board = DraftBoard(_pool(), n_teams=4, roster_config={"QB": 1})
    simulator = MockDraftSimulator(board, user_pick=1, n_teams=4, draft_type="snake")
    session = {"board": board, "user_pick": 1, "simulator": simulator}

    # Round 1: user_pick=1 is on the clock at pick 1 (nobody has picked yet).
    assert _user_next_pick_number(session, board, None) == 1

    # Simulate 4 picks (a full round) so slot 1's next turn is the snake-
    # reversed pick 8 (round 2, slot order reversed: picks 5,6,7,8 -> slots
    # 4,3,2,1).
    for pid in list(board.available["player_id"])[:4]:
        board.draft_player(pid, by_me=False)
    assert _user_next_pick_number(session, board, None) == 8


def test_user_next_pick_number_linear_draft_type_from_simulator():
    board = DraftBoard(_pool(), n_teams=4, roster_config={"QB": 1})
    simulator = MockDraftSimulator(board, user_pick=2, n_teams=4, draft_type="linear")
    session = {"board": board, "user_pick": 2, "simulator": simulator}
    assert _user_next_pick_number(session, board, None) == 2
