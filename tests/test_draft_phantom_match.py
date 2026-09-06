"""Regressions from the 2026-08-31 La Liga (ESPN) live draft.

1. Phantom-drafted players: a live pick that maps to no projection row must
   never take an unrelated player off the board. The engine's fallback is now
   :meth:`DraftBoard.draft_by_identity` — exact suffix-blind full name, gated
   on position, team as tiebreak; no match = no removal.
2. Launch cwd: ``draft_live.py`` must resolve default data paths against the
   repo root and user-supplied paths against the launch cwd.
"""

from __future__ import annotations

import importlib.util
import os

import pandas as pd
import pytest

# Load scripts/draft_live.py as a module first — it puts src/ on sys.path,
# which src.draft_optimizer's bare ``from config import ...`` needs.
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live_phantom", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)

from src.draft_models import DraftState, PickEvent  # noqa: E402
from src.draft_optimizer import DraftBoard, compute_value_scores  # noqa: E402
from src.live_draft_engine import LiveDraftEngine  # noqa: E402
from src.sleeper_player_map import map_picks_to_projections  # noqa: E402


def _projections() -> pd.DataFrame:
    rows = [
        ("q1", "Patrick Mahomes", "QB", "KC", 360.0),
        ("r1", "Christian McCaffrey", "RB", "SF", 320.0),
        ("r2", "Bijan Robinson", "RB", "ATL", 300.0),
        ("w1", "Mike Evans", "WR", "TB", 220.0),
        ("w2", "Brian Thomas Jr.", "WR", "JAX", 210.0),
        ("w3", "Chris Godwin Jr.", "WR", "TB", 180.0),
        ("w4", "Ja'Marr Chase", "WR", "CIN", 300.0),
        ("t1", "Michael Thomas", "TE", "NO", 60.0),  # same name, other position
        ("t2", "Travis Kelce", "TE", "KC", 200.0),
    ]
    return pd.DataFrame(
        rows,
        columns=["player_id", "player_name", "position", "team", "projected_points"],
    )


class _EspnLikeAdapter:
    """ESPN adapter's mapping: normalized name + position, no registry."""

    platform = "espn"

    def map_picks(self, picks, projections_df):
        return map_picks_to_projections(picks, projections_df, player_index={})


def _pick(pick_no, first, last, position, team="") -> PickEvent:
    return PickEvent(
        pick_no=pick_no,
        round=1,
        draft_slot=pick_no,
        roster_id=pick_no,
        picked_by=f"owner{pick_no}",
        sleeper_player_id="",
        first_name=first,
        last_name=last,
        position=position,
        team=team,
        is_keeper=False,
    )


def _state(picks) -> DraftState:
    return DraftState(
        draft_id="espn",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=12,
        rounds=16,
        scoring_format="standard",
        roster_format="espn_default",
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(picks),
    )


def _engine(adp_df=None) -> LiveDraftEngine:
    return LiveDraftEngine(_EspnLikeAdapter(), _projections(), adp_df, my_slot=10)


def _names(engine) -> set:
    return set(engine.board.available["player_name"])


# --------------------------------------------------------------------------
# Bug 1 — phantom-drafted players
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_unmatched_name_fragment_does_not_remove_mike_evans():
    engine = _engine()
    picks = [_pick(1, "Chris", "Evans", "WR", "TB"), _pick(2, "Evans", "", "WR")]
    poll = engine.update(_state(picks))

    assert "Mike Evans" in _names(engine)
    assert [p.full_name for p in poll.unmatched] == ["Chris Evans", "Evans"]
    # Still recorded against the drafting slots, just not removed from the board.
    assert engine.rosters[1][0]["player_name"] == "Chris Evans"
    assert engine.rosters[2][0]["player_name"] == "Evans"
    assert len(engine.board.available) == len(engine.enriched)


@pytest.mark.unit
def test_dst_pick_without_projection_row_removes_nothing(caplog):
    engine = _engine()
    with caplog.at_level("WARNING", logger="src.draft_optimizer"):
        poll = engine.update(_state([_pick(1, "Buccaneers", "D/ST", "DST", "TB")]))

    assert len(poll.unmatched) == 1
    assert len(engine.board.available) == len(engine.enriched)
    assert "Buccaneers D/ST" in caplog.text and "nothing removed" in caplog.text


@pytest.mark.unit
def test_suffix_blind_pick_matches_jr_projection_row():
    engine = _engine()
    poll = engine.update(_state([_pick(1, "Brian", "Thomas", "WR", "JAX")]))

    assert poll.unmatched == []
    assert "Brian Thomas Jr." not in _names(engine)
    assert engine.rosters[1][0]["player_name"] == "Brian Thomas Jr."


@pytest.mark.unit
def test_same_name_other_position_is_not_removed():
    engine = _engine()
    poll = engine.update(_state([_pick(1, "Michael", "Thomas", "WR", "NO")]))

    assert [p.full_name for p in poll.unmatched] == ["Michael Thomas"]
    assert "Michael Thomas" in _names(engine)  # the TE row survives a WR pick


@pytest.mark.unit
def test_positionless_pick_needs_exact_suffix_blind_name():
    """Manual --add-pick names carry no position: exact name only, no fragments."""
    engine = _engine()
    engine.update(_state([_pick(1, "Brian", "Thomas", ""), _pick(2, "Evans", "", "")]))

    names = _names(engine)
    assert "Brian Thomas Jr." not in names
    assert "Mike Evans" in names


@pytest.mark.unit
def test_draft_by_identity_never_partial_matches():
    board = DraftBoard(
        compute_value_scores(_projections()), roster_format="espn_default"
    )
    assert board.draft_by_identity("Evans", "WR") == {}
    assert board.draft_by_identity("Chris Evans", "WR") == {}
    assert board.draft_by_identity("Michael Thomas", "WR") == {}
    assert len(board.available) == 9
    assert board.draft_by_identity("Chris Godwin", "WR", "TB")["player_name"] == (
        "Chris Godwin Jr."
    )
    assert len(board.available) == 8


@pytest.mark.unit
def test_draft_by_identity_team_breaks_name_position_tie():
    proj = pd.concat(
        [
            _projections(),
            pd.DataFrame(
                [("w9", "Mike Evans", "WR", "SF", 10.0)],
                columns=[
                    "player_id",
                    "player_name",
                    "position",
                    "team",
                    "projected_points",
                ],
            ),
        ],
        ignore_index=True,
    )
    board = DraftBoard(compute_value_scores(proj), roster_format="espn_default")
    assert board.draft_by_identity("Mike Evans", "WR", "SF")["player_id"] == "w9"
    assert (board.available["player_id"] == "w1").any()


@pytest.mark.unit
def test_matched_adp_only_kicker_leaves_the_board():
    """ADP-only K/DST rows have NaN player_ids; str(nan) used to match nothing."""
    adp = pd.DataFrame(
        [
            {
                "player_name": "Cameron Dicker",
                "position": "K",
                "team": "LAC",
                "adp_rank": 150,
            },
            {
                "player_name": "Mike Evans",
                "position": "WR",
                "team": "TB",
                "adp_rank": 20,
            },
        ]
    )
    engine = _engine(adp)
    kicker = engine.enriched[engine.enriched["player_name"] == "Cameron Dicker"]
    if kicker.empty:
        pytest.skip("compute_value_scores did not append an ADP-only kicker row")
    assert kicker["player_id"].isna().all()

    poll = engine.update(_state([_pick(1, "Cameron", "Dicker", "K", "LAC")]))
    assert poll.unmatched == []
    assert "Cameron Dicker" not in _names(engine)


@pytest.mark.unit
def test_keepers_file_removal_still_works():
    """The keepers path (`*` lines via draft_by_name, others via remove_players)."""
    board = DraftBoard(
        compute_value_scores(_projections()), roster_format="espn_default"
    )
    assert (
        board.draft_by_name("Brian Thomas", by_me=True)["player_name"]
        == "Brian Thomas Jr."
    )
    assert board.remove_players(["Chris Godwin", "Mike Evans"]) == 2
    names = set(board.available["player_name"])
    assert {"Brian Thomas Jr.", "Chris Godwin Jr.", "Mike Evans"}.isdisjoint(names)
    assert [p["player_name"] for p in board.my_roster] == ["Brian Thomas Jr."]


# --------------------------------------------------------------------------
# Bug 2 — launch cwd
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("platform", [None, "sleeper", "espn"])
def test_default_adp_path_is_absolute_under_repo_root(monkeypatch, tmp_path, platform):
    monkeypatch.chdir(tmp_path)
    path = draft_live.default_adp_path(platform, "standard")
    assert os.path.isabs(path)
    assert os.path.commonpath([path, str(draft_live.REPO_ROOT)]) == str(
        draft_live.REPO_ROOT
    )


@pytest.mark.unit
def test_relative_adp_file_resolves_against_launch_cwd(monkeypatch, tmp_path, capsys):
    proj_csv = tmp_path / "proj.csv"
    _projections().to_csv(proj_csv, index=False)
    (tmp_path / "relative.csv").write_text("player_name,position,team,adp_rank\n")
    monkeypatch.chdir(tmp_path)

    seen = {}

    def _capture(adp_file, platform=None, scoring=None):
        seen["adp_file"] = adp_file
        return None

    monkeypatch.setattr(draft_live, "load_adp", _capture)
    rc = draft_live.main(
        [
            "--manual",
            "--teams",
            "3",
            "--my-slot",
            "3",
            "--projections-file",
            "proj.csv",
            "--adp-file",
            "relative.csv",
            "--add-pick",
            "Patrick Mahomes",
            "--json",
        ]
    )
    assert rc == 0
    assert seen["adp_file"] == str(tmp_path / "relative.csv")
    assert draft_live.Path.cwd().resolve() == draft_live.REPO_ROOT
    err = capsys.readouterr().err
    assert str(draft_live.REPO_ROOT) in err
