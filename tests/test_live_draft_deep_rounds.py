"""Offline tests for the deep-round auto-switch (UC1 vacated-opportunity shots)
and tier-cliff alerts in the live draft co-pilot (2026-08-29 hardening).

TASK 1 — when every recommendation's VORP is <= 0 (deep rounds), the render
augments with a "DEEP ROUNDS — vacated-opportunity shots" section fed by the
UC1 sleeper board, loaded ONCE lazily and filtered by the drafted set per
cycle. Fails soft (one warning, no crash) when the data is unavailable.

TASK 2 — tier-cliff alerts (doctrine §9 "next implementation step"): tiers are
computed ONCE from the initial board (`draft_tiers.compute_tiers`) and filtered
by drafted players per cycle; when <= 2 players remain in the current best
available tier at a position, a `TIER CLIFF:` line renders.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os

import pandas as pd
import pytest

from src import live_draft_engine as lde
from src.draft_models import DraftState, PickEvent
from src.live_draft_engine import LiveDraftEngine

# Load scripts/draft_live.py as a module (scripts/ is not a package).
_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live_deep", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)


class _Adapter:
    """Offline adapter: name-based pick mapping, no network."""

    platform = "test"

    def resolve_draft(self, identifier, season, league_id=None):
        return {"found": False, "candidates": []}

    def load_state(self, draft_id):  # pragma: no cover - unused
        raise NotImplementedError

    def map_picks(self, picks, projections_df):
        from src.sleeper_player_map import map_picks_to_projections

        return map_picks_to_projections(picks, projections_df, player_index={})


def _pick(no: int, name: str, position: str, n_teams: int = 12) -> PickEvent:
    first, _, last = name.partition(" ")
    idx = (no - 1) % n_teams
    rnd = (no - 1) // n_teams + 1
    slot = (n_teams - idx) if rnd % 2 == 0 else idx + 1
    return PickEvent(
        pick_no=no,
        round=rnd,
        draft_slot=slot,
        roster_id=slot,
        picked_by="test",
        sleeper_player_id="",
        first_name=first,
        last_name=last,
        position=position,
        team="",
        is_keeper=False,
    )


def _state(picks=(), n_teams: int = 12) -> DraftState:
    return DraftState(
        draft_id="t1",
        status="drafting",
        draft_type="snake",
        season="2026",
        n_teams=n_teams,
        rounds=15,
        scoring_format="half_ppr",
        roster_format="standard",
        draft_order={},
        slot_to_roster_id={},
        picks=tuple(picks),
    )


@pytest.fixture
def tiered_projections():
    """A pool with a clear RB tier structure.

    RB points [300, 295, 250, 245, 200]: drops [5, 45, 5, 45], std 20,
    threshold max(0.35*20, 0.5)=7 -> tiers [1, 1, 2, 2, 3].
    WR points [200, 198, 196, 194, 150] -> top tier of 4 (no cliff at 2-left).
    """
    rows = [
        ("r1", "RB One", "RB", "AAA", 300.0),
        ("r2", "RB Two", "RB", "BBB", 295.0),
        ("r3", "RB Three", "RB", "CCC", 250.0),
        ("r4", "RB Four", "RB", "DDD", 245.0),
        ("r5", "RB Five", "RB", "EEE", 200.0),
        ("w1", "WR One", "WR", "AAA", 200.0),
        ("w2", "WR Two", "WR", "BBB", 198.0),
        ("w3", "WR Three", "WR", "CCC", 196.0),
        ("w4", "WR Four", "WR", "DDD", 194.0),
        ("w5", "WR Five", "WR", "EEE", 150.0),
        ("q1", "QB One", "QB", "AAA", 350.0),
        ("q2", "QB Two", "QB", "BBB", 300.0),
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "player_id",
            "player_name",
            "position",
            "team",
            "projected_season_points",
        ],
    )


@pytest.fixture
def flat_projections():
    """Every position dead flat -> every VORP is 0 (deep-round condition)."""
    rows = []
    for pos, pts, n in (
        ("RB", 100.0, 6),
        ("WR", 90.0, 6),
        ("QB", 250.0, 6),
        ("TE", 80.0, 6),
    ):
        for i in range(1, n + 1):
            rows.append((f"{pos.lower()}{i}", f"{pos} Guy{i}", pos, "ZZZ", pts))
    return pd.DataFrame(
        rows,
        columns=[
            "player_id",
            "player_name",
            "position",
            "team",
            "projected_season_points",
        ],
    )


@pytest.fixture
def fake_vacated_board():
    # Mirrors the real board's shape (rows pre-sorted by absorbed share):
    # AJ Dillon steps into 48.7% of CAR's vacated carries (2026-08-28 mock).
    return pd.DataFrame(
        [
            ("AJ Dillon", "CAR", "RB", 0.051, 0.065, 0.487, 2, None),
            ("Tyler Allgeier", "ATL", "RB", 0.031, 0.02, 0.30, 3, None),
            ("Quentin Johnston", "LAC", "WR", 0.022, 0.25, 0.00, 1, None),
        ],
        columns=[
            "player_name",
            "team",
            "position",
            "vacancy_absorbed_share",
            "net_target_vacancy",
            "net_carry_vacancy",
            "vacancy_competition_n",
            "consensus_pos_rank",
        ],
    )


# ---------------------------------------------------------------------------
# TASK 1 — deep-round detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_deep_round_true_when_all_vorp_nonpositive(flat_projections):
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    engine.update(_state())
    recs, _ = engine.recommendations(top_n=5)
    assert not recs.empty
    assert engine.is_deep_round(recs) is True


@pytest.mark.unit
def test_is_deep_round_false_with_positive_vorp(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    engine.update(_state())
    recs, _ = engine.recommendations(top_n=5)
    assert engine.is_deep_round(recs) is False


@pytest.mark.unit
def test_is_deep_round_false_on_empty_or_missing_vorp(flat_projections):
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    assert engine.is_deep_round(pd.DataFrame()) is False
    assert engine.is_deep_round(pd.DataFrame({"player_name": ["x"]})) is False
    assert engine.is_deep_round(pd.DataFrame({"vorp": [float("nan")]})) is False


@pytest.mark.unit
def test_is_deep_round_top_rec_nonpositive_wins_over_stray_positives(flat_projections):
    """Primary trigger: TOP rec at/below replacement — even when a K/DST-ish
    positive VORP lingers further down the list (2026-08-28 mock shape)."""
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    recs = pd.DataFrame({"vorp": [-2.0, -5.0, 3.1]})
    assert engine.is_deep_round(recs) is True
    # NaN top row falls back to the all-nonpositive check.
    assert engine.is_deep_round(pd.DataFrame({"vorp": [float("nan"), -1.0]})) is True
    assert engine.is_deep_round(pd.DataFrame({"vorp": [float("nan"), 4.0]})) is False


# ---------------------------------------------------------------------------
# TASK 1 — deep-round shots: cache, drafted filter, fail-soft
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_deep_round_shots_loaded_once_and_sorted(
    monkeypatch, flat_projections, fake_vacated_board
):
    calls = []

    def _fake_loader(season):
        calls.append(season)
        return fake_vacated_board

    monkeypatch.setattr(lde, "_load_vacated_board", _fake_loader)
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    engine.update(_state())

    shots = engine.deep_round_shots(top_n=5)
    assert [s["player_name"] for s in shots] == [
        "AJ Dillon",
        "Tyler Allgeier",
        "Quentin Johnston",
    ]
    # One-line reason: vacated share (dominant channel) + rival count.
    assert "48.7%" in shots[0]["reason"] and "carries" in shots[0]["reason"]
    assert "2 rival" in shots[0]["reason"]
    assert shots[0]["absorbed_share"] == pytest.approx(0.051)
    assert "targets" in shots[2]["reason"]

    # Cached: a second call must NOT reload (no added latency per poll cycle).
    engine.deep_round_shots()
    assert calls == [2026]  # loaded once, with the draft state's season


@pytest.mark.unit
def test_deep_round_shots_exclude_drafted_players(
    monkeypatch, flat_projections, fake_vacated_board
):
    monkeypatch.setattr(lde, "_load_vacated_board", lambda season: fake_vacated_board)
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    engine.update(_state())
    # Someone drafts A.J. Dillon (name-key tolerant: punctuation differs).
    engine.rosters.setdefault(3, []).append(
        {"player_name": "A.J. Dillon", "position": "RB"}
    )
    shots = engine.deep_round_shots()
    assert "AJ Dillon" not in [s["player_name"] for s in shots]
    assert "Tyler Allgeier" in [s["player_name"] for s in shots]


@pytest.mark.unit
def test_deep_round_shots_fail_soft_one_warning(monkeypatch, flat_projections, caplog):
    calls = []

    def _boom(season):
        calls.append(season)
        raise FileNotFoundError("no bronze data on this machine")

    monkeypatch.setattr(lde, "_load_vacated_board", _boom)
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    engine.update(_state())
    with caplog.at_level(logging.WARNING, logger="src.live_draft_engine"):
        assert engine.deep_round_shots() == []
        assert engine.deep_round_shots() == []  # second call: cached, no reload
    assert len(calls) == 1
    assert sum("DEEP ROUNDS" in r.message for r in caplog.records) == 1


# ---------------------------------------------------------------------------
# TASK 2 — tier-cliff alerts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tier_cliff_two_left_before_any_pick(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    engine.update(_state())
    cliffs = {c["position"]: c for c in engine.tier_cliff_alerts()}
    rb = cliffs["RB"]
    assert rb["tier"] == 1 and rb["remaining"] == 2
    assert rb["players"] == ["RB One", "RB Two"]
    assert rb["next_player"] == "RB Three"
    assert rb["drop_pts"] == pytest.approx(45.0)
    # WR top tier has 4 players -> no cliff.
    assert "WR" not in cliffs


@pytest.mark.unit
def test_tier_cliff_last_of_tier_after_pick(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    engine.update(_state([_pick(1, "RB One", "RB")]))
    rb = {c["position"]: c for c in engine.tier_cliff_alerts()}["RB"]
    assert rb["remaining"] == 1 and rb["players"] == ["RB Two"]
    assert rb["next_player"] == "RB Three"
    assert rb["drop_pts"] == pytest.approx(45.0)


@pytest.mark.unit
def test_tier_pool_computed_once(tiered_projections, monkeypatch):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    engine.update(_state())
    engine.tier_cliff_alerts()
    pool_first = engine._tier_pool
    assert pool_first is not None
    # Recompute would produce a NEW object; the cached one must be reused.
    engine.update(_state([_pick(1, "RB One", "RB")]))
    engine.tier_cliff_alerts()
    assert engine._tier_pool is pool_first


@pytest.mark.unit
def test_tier_cliffs_empty_without_board(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    assert engine.tier_cliff_alerts() == []  # board not built yet — no crash


# ---------------------------------------------------------------------------
# Render integration (scripts/draft_live.py)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_deep_rounds_section(monkeypatch, flat_projections, fake_vacated_board):
    monkeypatch.setattr(lde, "_load_vacated_board", lambda season: fake_vacated_board)
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    poll = engine.update(_state())
    text = draft_live.render(engine, poll, top_n=5, as_json=False)
    assert "DEEP ROUNDS — vacated-opportunity shots" in text
    assert "AJ Dillon" in text and "48.7%" in text
    out = json.loads(draft_live.render(engine, poll, top_n=5, as_json=True))
    assert out["deep_round_shots"][0]["player_name"] == "AJ Dillon"


@pytest.mark.unit
def test_render_no_deep_section_when_vorp_positive(
    monkeypatch, tiered_projections, fake_vacated_board
):
    monkeypatch.setattr(lde, "_load_vacated_board", lambda season: fake_vacated_board)
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    poll = engine.update(_state())
    text = draft_live.render(engine, poll, top_n=5, as_json=False)
    assert "DEEP ROUNDS" not in text


@pytest.mark.unit
def test_render_deep_rounds_fail_soft(monkeypatch, flat_projections):
    def _boom(season):
        raise RuntimeError("vacated data missing")

    monkeypatch.setattr(lde, "_load_vacated_board", _boom)
    engine = LiveDraftEngine(_Adapter(), flat_projections, my_slot=1)
    poll = engine.update(_state())
    text = draft_live.render(engine, poll, top_n=5, as_json=False)  # must not raise
    assert "DEEP ROUNDS" not in text


@pytest.mark.unit
def test_render_tier_cliff_line(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    poll = engine.update(_state([_pick(1, "RB One", "RB")]))
    text = draft_live.render(engine, poll, top_n=5, as_json=False)
    assert (
        "TIER CLIFF: last of RB tier 1 — RB Two "
        "(next tier starts at RB Three, -45.0 proj pts)" in text
    )
    out = json.loads(draft_live.render(engine, poll, top_n=5, as_json=True))
    assert any(
        c["position"] == "RB" and c["remaining"] == 1 for c in out["tier_cliffs"]
    )


@pytest.mark.unit
def test_render_two_left_cliff_wording(tiered_projections):
    engine = LiveDraftEngine(_Adapter(), tiered_projections, my_slot=1)
    poll = engine.update(_state())
    text = draft_live.render(engine, poll, top_n=5, as_json=False)
    assert "TIER CLIFF: 2 left in RB tier 1 — RB One, RB Two" in text
