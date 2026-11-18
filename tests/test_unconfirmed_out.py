"""A Sleeper "Out" tag the week's official report has not confirmed is not a zero.

On a Tuesday there is no official game status for the coming week, so the board
falls back to Sleeper's live designation, which is the LAST game's ruling. The
2026 week-11 board zeroed Brock Bowers (consensus TE2, 12.1) that way and the
deploy gate rejected it ("TE#71").

Validation behind the rule (2026 weeks 2-10, consensus >= 5, n=86 player-weeks of
skill players officially Out the week before or zeroed on a Tuesday board): 38%
played (95% CI 29-49%), mean actual 4.2 pts vs consensus 10.9. Keeping the full
projection is wrong by +6.8 pts a player, zero by -4.1, 0.4x by +0.2.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from projection_engine import (  # noqa: E402
    EARLY_WEEK_MAX_OFFICIAL,
    UNCONFIRMED_MIN_CONSENSUS,
    UNCONFIRMED_OUT_MULTIPLIER,
    UNCONFIRMED_OUT_STATUS,
    apply_injury_adjustments,
    apply_unconfirmed_out_discount,
    live_injury_report,
    merge_injury_sources,
    soften_unconfirmed_outs,
)

STALE = "00-0000001"  # live Out tag, consensus 12
LOW = "00-0000002"  # live Out tag, consensus 2
NOROW = "00-0000003"  # live Out tag, no consensus row
OFFICIAL = "00-0000004"  # official Out, consensus 12
IR = "00-0000005"  # live IR, consensus 12
DOUBT = "00-0000006"  # live Doubtful, consensus 12
QUEST = "00-0000007"  # live Questionable, consensus 12
HEALTHY = "00-0000008"


def _live():
    return pd.DataFrame(
        [
            {"gsis_id": STALE, "report_status": "Out", "roster_designation": False},
            {"gsis_id": LOW, "report_status": "Out", "roster_designation": False},
            {"gsis_id": NOROW, "report_status": "Out", "roster_designation": False},
            {"gsis_id": OFFICIAL, "report_status": "Out", "roster_designation": False},
            {"gsis_id": IR, "report_status": "Out", "roster_designation": True},
            {
                "gsis_id": DOUBT,
                "report_status": "Doubtful",
                "roster_designation": False,
            },
            {
                "gsis_id": QUEST,
                "report_status": "Questionable",
                "roster_designation": False,
            },
        ]
    )


def _official(n_graded: int = 1):
    rows = [{"gsis_id": OFFICIAL, "report_status": "Out", "week": 11}]
    rows += [
        {"gsis_id": f"00-9{i:06d}", "report_status": "Questionable", "week": 11}
        for i in range(n_graded - 1)
    ]
    return pd.DataFrame(rows)


def _consensus():
    ids = {STALE: 12.0, LOW: 2.0, OFFICIAL: 12.0, IR: 12.0, DOUBT: 12.0, QUEST: 12.0}
    return pd.DataFrame(
        {
            "player_id": list(ids),
            "position": "WR",
            "projected_points": list(ids.values()),
        }
    )


def _board():
    ids = [STALE, LOW, NOROW, OFFICIAL, IR, DOUBT, QUEST, HEALTHY]
    return pd.DataFrame(
        {
            "player_id": ids,
            "player_name": [f"P{i}" for i in range(len(ids))],
            "position": "WR",
            "projected_points": [10.0] * len(ids),
            "proj_receiving_yards": [100.0] * len(ids),
            "projected_floor": [6.0] * len(ids),
            "projected_ceiling": [20.0] * len(ids),
        }
    )


def _run(official, live=None, consensus=None):
    merged, n_official, _ = merge_injury_sources(
        official, _live() if live is None else live
    )
    merged, ids = soften_unconfirmed_outs(
        merged, _consensus() if consensus is None else consensus, n_official
    )
    board = apply_injury_adjustments(_board(), merged)
    board = apply_unconfirmed_out_discount(board, ids)
    return board.set_index("player_id"), ids


def test_stale_out_with_consensus_keeps_a_discounted_projection():
    board, ids = _run(_official())
    row = board.loc[STALE]
    assert row.injury_status == UNCONFIRMED_OUT_STATUS
    assert row.injury_multiplier == UNCONFIRMED_OUT_MULTIPLIER
    assert row.projected_points == pytest.approx(10.0 * UNCONFIRMED_OUT_MULTIPLIER)
    assert row.proj_receiving_yards == pytest.approx(100.0 * UNCONFIRMED_OUT_MULTIPLIER)
    assert bool(row.injury_unconfirmed) is True
    assert ids == [STALE]


def test_the_band_describes_the_either_or_not_a_scaled_point():
    row = _run(_official())[0].loc[STALE]
    assert row.projected_floor == 0.0  # he may not play
    assert row.projected_ceiling == 20.0  # if he does, he is a starter


def test_released_players_run_the_pipeline_as_healthy():
    """The discount is priced on the finished board, so the Sleeper anchor and
    every other blend see the player as the consensus does."""
    merged, n_official, _ = merge_injury_sources(_official(), _live())
    merged, ids = soften_unconfirmed_outs(merged, _consensus(), n_official)
    board = apply_injury_adjustments(_board(), merged).set_index("player_id")
    assert ids == [STALE]
    assert board.loc[STALE].injury_status == "Active"
    assert board.loc[STALE].injury_multiplier == 1.0
    assert board.loc[STALE].projected_points == 10.0


def test_stale_out_with_low_or_missing_consensus_is_still_zero():
    board, _ = _run(_official())
    for pid in (LOW, NOROW):
        assert board.loc[pid].projected_points == 0.0
        assert board.loc[pid].injury_status == "Out"
        assert bool(board.loc[pid].injury_unconfirmed) is False


def test_consensus_exactly_at_the_floor_is_released_and_just_below_is_not():
    cons = pd.DataFrame(
        {
            "player_id": [STALE, LOW],
            "position": "WR",
            "projected_points": [
                UNCONFIRMED_MIN_CONSENSUS,
                UNCONFIRMED_MIN_CONSENSUS - 0.01,
            ],
        }
    )
    board, ids = _run(_official(), consensus=cons)
    assert board.loc[STALE].injury_multiplier == UNCONFIRMED_OUT_MULTIPLIER
    assert board.loc[LOW].injury_multiplier == 0.0
    assert ids == [STALE]


def test_an_official_out_is_still_zero_whatever_the_consensus_says():
    board, _ = _run(_official())
    row = board.loc[OFFICIAL]
    assert row.projected_points == 0.0
    assert row.injury_status == "Out"
    assert bool(row.injury_unconfirmed) is False


def test_roster_designations_are_still_zero():
    board, _ = _run(_official())
    assert board.loc[IR].projected_points == 0.0
    assert board.loc[IR].injury_status == "Out"


def test_once_the_official_report_has_game_statuses_a_live_out_is_zero_again():
    """Friday's report posts ~120+ graded rows; the tag is then current."""
    board, ids = _run(_official(n_graded=EARLY_WEEK_MAX_OFFICIAL))
    assert board.loc[STALE].projected_points == 0.0
    assert board.loc[STALE].injury_status == "Out"
    assert ids == []


def test_just_under_the_early_week_limit_still_releases():
    board, _ = _run(_official(n_graded=EARLY_WEEK_MAX_OFFICIAL - 1))
    assert board.loc[STALE].injury_multiplier == UNCONFIRMED_OUT_MULTIPLIER


def test_no_official_rows_at_all_is_the_tuesday_case():
    empty = pd.DataFrame(columns=["gsis_id", "report_status", "week"])
    board, ids = _run(empty)
    # With no official row for anyone, OFFICIAL's live Out tag is just another
    # unconfirmed tag (consensus 12), so both it and STALE are released.
    assert board.loc[STALE].injury_multiplier == UNCONFIRMED_OUT_MULTIPLIER
    assert board.loc[OFFICIAL].injury_multiplier == UNCONFIRMED_OUT_MULTIPLIER
    assert ids == sorted([STALE, OFFICIAL])
    assert board.loc[IR].projected_points == 0.0


def test_doubtful_and_questionable_keep_their_own_grades():
    board, _ = _run(_official())
    assert board.loc[DOUBT].injury_multiplier == 0.5
    assert board.loc[DOUBT].injury_status == "Doubtful"
    assert board.loc[QUEST].injury_multiplier == 0.85
    assert board.loc[HEALTHY].injury_multiplier == 1.0


def test_no_consensus_frame_changes_nothing():
    for empty in (
        None,
        pd.DataFrame(),
        pd.DataFrame(columns=["player_id", "projected_points"]),
    ):
        merged, n_official, _ = merge_injury_sources(_official(), _live())
        out, ids = soften_unconfirmed_outs(merged, empty, n_official)
        pd.testing.assert_frame_equal(out, merged)
        assert ids == []


def test_live_frame_without_designation_info_is_never_released():
    live = _live().drop(columns="roster_designation")
    board, ids = _run(_official(), live=live)
    assert board.loc[STALE].projected_points == 0.0
    assert ids == []


def test_input_frame_is_not_mutated():
    merged, n_official, _ = merge_injury_sources(_official(), _live())
    before = merged.copy()
    soften_unconfirmed_outs(merged, _consensus(), n_official)
    pd.testing.assert_frame_equal(merged, before)


def test_none_and_empty_injuries_pass_through():
    assert soften_unconfirmed_outs(None, _consensus(), 0)[1] == []
    out, ids = soften_unconfirmed_outs(pd.DataFrame(), _consensus(), 0)
    assert out.empty and ids == []


def test_a_row_the_board_has_no_projection_for_is_not_flagged():
    board = _board()
    board.loc[board.player_id == STALE, "projected_points"] = 0.0
    out = apply_unconfirmed_out_discount(
        apply_injury_adjustments(board, pd.DataFrame()), [STALE]
    ).set_index("player_id")
    assert out.loc[STALE].injury_status == "Active"
    assert bool(out.loc[STALE].injury_unconfirmed) is False


def test_discount_joins_on_gsis_id_when_the_board_has_one():
    board = _board().rename(columns={"player_id": "gsis_id"})
    board["player_id"] = [f"sleeper-{i}" for i in range(len(board))]
    out = apply_unconfirmed_out_discount(
        apply_injury_adjustments(board, pd.DataFrame()), [STALE]
    ).set_index("gsis_id")
    assert out.loc[STALE].injury_status == UNCONFIRMED_OUT_STATUS


def test_live_report_flags_roster_designations():
    registry = {
        "1": {"gsis_id": "00-0000010", "injury_status": "Out"},
        "2": {"gsis_id": "00-0000011", "injury_status": "IR"},
        "3": {"gsis_id": "00-0000012", "injury_status": "PUP"},
        "4": {"gsis_id": "00-0000013", "injury_status": "NFI"},
        "5": {"gsis_id": "00-0000014", "injury_status": "Sus"},
        "6": {"gsis_id": "00-0000015", "injury_status": "Doubtful"},
    }
    df = live_injury_report(registry).set_index("gsis_id")["roster_designation"]
    assert not bool(df["00-0000010"])
    assert not bool(df["00-0000015"])
    for g in ("00-0000011", "00-0000012", "00-0000013", "00-0000014"):
        assert bool(df[g])


def test_merge_carries_the_designation_flag_for_live_rows_only():
    merged, _, _ = merge_injury_sources(_official(), _live())
    by = merged.set_index("gsis_id")
    assert pd.isna(by.loc[OFFICIAL, "roster_designation"])  # official, not a tag
    assert by.loc[STALE, "roster_designation"] == False  # noqa: E712
    assert by.loc[IR, "roster_designation"] == True  # noqa: E712


def test_unconfirmed_flag_column_present_without_any_injury_data():
    out = apply_injury_adjustments(_board(), pd.DataFrame())
    assert "injury_unconfirmed" in out.columns and not out.injury_unconfirmed.any()
    out = apply_unconfirmed_out_discount(_board(), [])
    assert "injury_unconfirmed" in out.columns and not out.injury_unconfirmed.any()


def test_sunday_refresh_undo_restores_a_discounted_row():
    """Unlike a zero (which cannot be restored), 0.4x divides back out."""
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    refresh = importlib.import_module("sunday_projection_refresh")
    board, _ = _run(_official())
    board = board.reset_index()
    healthy = pd.DataFrame(columns=["gsis_id", "report_status"])
    refreshed, summary = refresh._undo_and_reapply(board, healthy)
    row = refreshed.set_index("player_id").loc[STALE]
    assert row.projected_points == pytest.approx(10.0, abs=0.01)
    assert row.injury_status == "Active"
    assert bool(row.injury_unconfirmed) is False
    assert summary["asymmetry_limited"] > 0  # the zeroed rows cannot come back


def test_generate_projections_wires_the_rule_in_order():
    text = (
        Path(__file__).resolve().parent.parent / "scripts" / "generate_projections.py"
    ).read_text(encoding="utf-8")
    inj = text.index("merge_injury_sources(")
    soft = text.index("soften_unconfirmed_outs(", inj)
    apply_ = text.index("apply_injury_adjustments(projections", soft)
    assert inj < soft < apply_
    assert "_load_sleeper_week" in text
    # the discount runs on the finished board: after the injury invariant,
    # before the ranks are recomputed from the final points
    invariant = text.index("Injury invariant: re-zeroed")
    disc = text.index("apply_unconfirmed_out_discount(projections", invariant)
    rank = text.index("projections = apply_ranking_scores(", disc)
    assert invariant < disc < rank
    assert "unconfirmed_ids = []" in text
