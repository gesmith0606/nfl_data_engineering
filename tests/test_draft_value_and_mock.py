"""Tests for the v8.2 draft-advice improvements (VORP ranking, positional
saturation, league-aware slots, linear drafts, autonomous mock).

These lock in the draft-day-readiness fixes:
* recommendations rank by VORP, not raw points (no QB-stacking in PPR),
* positional saturation caps unstartable depth (no 6-TE rosters),
* league roster_positions drive needs + the draftable pool (no kickers when
  there is no K slot),
* MockDraftSimulator honors linear order + a rounds cap,
* draft_live.load_projections falls back to the committed preseason parquet.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_optimizer import (  # noqa: E402
    DraftAdvisor,
    DraftBoard,
    MockDraftSimulator,
    compute_value_scores,
    draftable_positions,
    roster_config_from_positions,
    roster_config_from_slots,
)
import config  # noqa: E402

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Load scripts/draft_live.py as a module (scripts/ is not a package).
_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "draft_live.py")
_spec = importlib.util.spec_from_file_location("draft_live", _SCRIPT)
draft_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draft_live)

_MAHOMO_SLOTS = [
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "FLEX",
    "FLEX",
    "BN",
    "BN",
    "BN",
    "BN",
    "BN",
    "BN",
    "BN",
    "BN",
    "BN",
]


def _enriched(rows):
    """Build a board-ready enriched frame with explicit vorp/value_tier."""
    df = pd.DataFrame(rows)
    if "value_tier" not in df.columns:
        df["value_tier"] = "fair_value"
    if "model_rank" not in df.columns:
        df["model_rank"] = (
            df["projected_season_points"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
    if "adp_rank" not in df.columns:
        df["adp_rank"] = df["model_rank"]
    return df


def _board(rows, roster_config):
    return DraftBoard(_enriched(rows), n_teams=12, roster_config=roster_config)


_CFG = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 3}


# ---------------------------------------------------------------------------
# League-rule helpers
# ---------------------------------------------------------------------------


def test_roster_config_from_positions_maps_mahomo_slots():
    cfg = roster_config_from_positions(_MAHOMO_SLOTS)
    assert cfg == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 3}
    assert "BN" not in cfg and "K" not in cfg and "DST" not in cfg


def test_roster_config_collapses_flex_and_superflex():
    cfg = roster_config_from_positions(
        ["QB", "SUPER_FLEX", "WRRB_FLEX", "REC_FLEX", "DEF", "K", "BN"]
    )
    assert cfg["SFLEX"] == 1
    assert cfg["FLEX"] == 2  # WRRB_FLEX + REC_FLEX
    assert cfg["DST"] == 1 and cfg["K"] == 1


def test_roster_config_from_positions_empty_is_none():
    assert roster_config_from_positions(None) is None
    assert roster_config_from_positions([]) is None


def test_draftable_positions_excludes_kicker_when_no_slot():
    elig = draftable_positions(_CFG)
    assert elig == {"QB", "RB", "WR", "TE"}  # FLEX -> RB/WR/TE; no K/DST slot


def test_draftable_positions_includes_kdst_and_superflex():
    elig = draftable_positions({"QB": 1, "K": 1, "DST": 1, "SFLEX": 1})
    assert {"K", "DST"} <= elig
    assert "QB" in elig  # SFLEX keeps QB draftable


def test_draftable_positions_default_when_no_config():
    assert draftable_positions(None) == {"QB", "RB", "WR", "TE", "K", "DST"}


# ---------------------------------------------------------------------------
# DraftBoard honors the real league slots
# ---------------------------------------------------------------------------


def test_board_roster_config_override_drives_needs():
    board = _board(
        [
            {
                "player_id": "p1",
                "player_name": "A",
                "position": "QB",
                "projected_season_points": 300,
                "vorp": 30,
            }
        ],
        _CFG,
    )
    needs = board.remaining_needs()
    assert needs["RB"] == 2 and needs["WR"] == 2 and needs["FLEX"] == 3
    assert "K" not in needs and "DST" not in needs


# ---------------------------------------------------------------------------
# recommend(): VORP ranking + saturation
# ---------------------------------------------------------------------------


def test_recommend_ranks_by_vorp_not_raw_points():
    # QB has the most raw points but a small VORP; the WR/RB should win.
    rows = [
        {
            "player_id": "qb",
            "player_name": "Big QB",
            "position": "QB",
            "projected_season_points": 400,
            "vorp": 30,
        },
        {
            "player_id": "wr",
            "player_name": "Elite WR",
            "position": "WR",
            "projected_season_points": 350,
            "vorp": 150,
        },
        {
            "player_id": "rb",
            "player_name": "Elite RB",
            "position": "RB",
            "projected_season_points": 340,
            "vorp": 140,
        },
        {
            "player_id": "te",
            "player_name": "A TE",
            "position": "TE",
            "projected_season_points": 250,
            "vorp": 40,
        },
    ]
    advisor = DraftAdvisor(_board(rows, _CFG))
    recs, _ = advisor.recommend(top_n=4)
    assert "recommendation_score" in recs.columns  # API contract preserved
    assert recs.iloc[0]["position"] in {"WR", "RB"}
    assert recs.iloc[0]["player_id"] != "qb"


def test_recommend_does_not_stack_quarterbacks():
    rows = [
        {
            "player_id": "qb1",
            "player_name": "QB1",
            "position": "QB",
            "projected_season_points": 400,
            "vorp": 30,
        },
        {
            "player_id": "qb2",
            "player_name": "QB2",
            "position": "QB",
            "projected_season_points": 395,
            "vorp": 28,
        },
        {
            "player_id": "qb3",
            "player_name": "QB3",
            "position": "QB",
            "projected_season_points": 390,
            "vorp": 26,
        },
        {
            "player_id": "wr1",
            "player_name": "WR1",
            "position": "WR",
            "projected_season_points": 300,
            "vorp": 60,
        },
        {
            "player_id": "rb1",
            "player_name": "RB1",
            "position": "RB",
            "projected_season_points": 295,
            "vorp": 58,
        },
        {
            "player_id": "wr2",
            "player_name": "WR2",
            "position": "WR",
            "projected_season_points": 290,
            "vorp": 55,
        },
    ]
    board = _board(rows, _CFG)
    advisor = DraftAdvisor(board)
    board.draft_player("qb1", by_me=True)  # starting QB filled
    top = advisor.recommend(top_n=1)[0].iloc[0]
    assert top["position"] != "QB"  # don't draft a 2nd QB over elite WR/RB
    board.draft_player("qb2", by_me=True)  # now at the QB roster cap (2)
    recs3, _ = advisor.recommend(top_n=3)
    assert "QB" not in set(recs3["position"])  # 3rd QB penalized out of top picks


def test_recommend_saturation_caps_tight_end_depth():
    rows = [
        {
            "player_id": "te1",
            "player_name": "TE1",
            "position": "TE",
            "projected_season_points": 280,
            "vorp": 50,
        },
        {
            "player_id": "te2",
            "player_name": "TE2",
            "position": "TE",
            "projected_season_points": 275,
            "vorp": 48,
        },
        {
            "player_id": "te3",
            "player_name": "TE3",
            "position": "TE",
            "projected_season_points": 270,
            "vorp": 46,
        },
        {
            "player_id": "rb1",
            "player_name": "RB1",
            "position": "RB",
            "projected_season_points": 230,
            "vorp": 20,
        },
        {
            "player_id": "wr1",
            "player_name": "WR1",
            "position": "WR",
            "projected_season_points": 225,
            "vorp": 18,
        },
    ]
    board = _board(rows, _CFG)
    advisor = DraftAdvisor(board)
    board.draft_player("te1", by_me=True)
    board.draft_player("te2", by_me=True)  # 2 TEs = TE roster cap
    top = advisor.recommend(top_n=1)[0].iloc[0]
    # A 3rd TE (vorp 46) is penalized below a needed RB (vorp 20 + need boost).
    assert top["position"] != "TE"


# ---------------------------------------------------------------------------
# MockDraftSimulator: linear vs snake order + rounds cap
# ---------------------------------------------------------------------------


def _big_pool(n_per_pos=20):
    rows = []
    pid = 0
    for pos, base in (("QB", 380), ("RB", 320), ("WR", 330), ("TE", 250)):
        for i in range(n_per_pos):
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "player_name": f"{pos} {i}",
                    "position": pos,
                    "projected_season_points": base - i * 9,
                }
            )
            pid += 1
    enriched = compute_value_scores(pd.DataFrame(rows))
    return enriched


def test_linear_user_turn_is_fixed_slot_each_round():
    sim = MockDraftSimulator(
        DraftBoard(_big_pool(), n_teams=4, roster_config=_CFG),
        user_pick=2,
        n_teams=4,
        draft_type="linear",
    )
    assert [p for p in range(1, 13) if sim._is_user_turn(p)] == [2, 6, 10]


def test_snake_user_turn_reverses_even_rounds():
    sim = MockDraftSimulator(
        DraftBoard(_big_pool(), n_teams=4, roster_config=_CFG),
        user_pick=2,
        n_teams=4,
        draft_type="snake",
    )
    # round 1 -> pick 2; round 2 reverses -> slot 2 is pick 7.
    assert sim._is_user_turn(2) is True
    assert sim._is_user_turn(7) is True
    assert sim._is_user_turn(6) is False


def test_run_full_simulation_respects_rounds_cap():
    board = DraftBoard(_big_pool(), n_teams=4, roster_config=_CFG)
    advisor = DraftAdvisor(board)
    sim = MockDraftSimulator(
        board, user_pick=1, n_teams=4, randomness=0, draft_type="linear"
    )
    result = sim.run_full_simulation(advisor, rounds=3)
    assert len(result["my_roster"]) == 3  # 1 user pick per round, 3 rounds


def test_full_linear_mock_builds_sane_roster_no_qb_spam():
    board = DraftBoard(_big_pool(60), n_teams=12, roster_config=_CFG)
    advisor = DraftAdvisor(board)
    sim = MockDraftSimulator(
        board, user_pick=6, n_teams=12, randomness=0, draft_type="linear"
    )
    result = sim.run_full_simulation(advisor, rounds=15)
    from collections import Counter

    counts = Counter(p.get("position") for p in result["my_roster"])
    assert counts.get("QB", 0) <= 2  # no QB stacking
    assert counts.get("TE", 0) <= 3  # no TE stacking
    assert counts.get("RB", 0) + counts.get("WR", 0) >= 8  # flex filled with RB/WR


# ---------------------------------------------------------------------------
# draft_live: draft-day-robust projection loading + auto mock report
# ---------------------------------------------------------------------------


def test_latest_preseason_parquet_missing_season_is_none():
    cwd = os.getcwd()
    os.chdir(_REPO_ROOT)
    try:
        assert draft_live._latest_preseason_parquet(1999) is None
    finally:
        os.chdir(cwd)


def test_load_projections_prefers_committed_parquet_no_network():
    cwd = os.getcwd()
    os.chdir(_REPO_ROOT)
    try:
        df = draft_live.load_projections(2026, "half_ppr", None)
    finally:
        os.chdir(cwd)
    assert isinstance(df, pd.DataFrame) and not df.empty
    assert "player_name" in df.columns and "position" in df.columns


def test_roster_config_from_slots_maps_mock_settings():
    rc = roster_config_from_slots(
        {
            "slots_qb": 1,
            "slots_rb": 2,
            "slots_wr": 2,
            "slots_te": 1,
            "slots_flex": 2,
            "slots_k": 1,
            "slots_def": 1,
            "teams": 10,
        }
    )
    assert rc == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 2, "K": 1, "DST": 1}
    assert roster_config_from_slots({}) is None
    assert roster_config_from_slots(None) is None


def test_build_queue_is_need_aware_and_restores_board():
    rows = [
        {
            "player_id": "wr1",
            "player_name": "WR1",
            "position": "WR",
            "projected_season_points": 300,
            "vorp": 90,
        },
        {
            "player_id": "rb1",
            "player_name": "RB1",
            "position": "RB",
            "projected_season_points": 295,
            "vorp": 88,
        },
        {
            "player_id": "wr2",
            "player_name": "WR2",
            "position": "WR",
            "projected_season_points": 285,
            "vorp": 70,
        },
        {
            "player_id": "rb2",
            "player_name": "RB2",
            "position": "RB",
            "projected_season_points": 280,
            "vorp": 66,
        },
        {
            "player_id": "te1",
            "player_name": "TE1",
            "position": "TE",
            "projected_season_points": 240,
            "vorp": 50,
        },
        {
            "player_id": "qb1",
            "player_name": "QB1",
            "position": "QB",
            "projected_season_points": 360,
            "vorp": 30,
        },
        {
            "player_id": "qb2",
            "player_name": "QB2",
            "position": "QB",
            "projected_season_points": 350,
            "vorp": 26,
        },
    ]
    board = _board(rows, _CFG)
    advisor = DraftAdvisor(board)
    avail_before, roster_before = len(board.available), len(board.my_roster)

    queue = advisor.build_queue(depth=5)
    assert 1 <= len(queue) <= 5
    # Board is restored (side-effect free) so it can be called every poll.
    assert len(board.available) == avail_before
    assert len(board.my_roster) == roster_before
    # Need-aware: fills multiple positions, never stacks QBs (1-QB league).
    positions = [x["position"] for x in queue]
    assert positions.count("QB") <= 1
    assert len(set(positions)) >= 2


def test_run_auto_mock_report_has_picks_lineup_and_no_kickers():
    pool = _big_pool()
    # Add kickers to confirm they are filtered out of a no-K league.
    kickers = pd.DataFrame(
        [
            {
                "player_id": f"K{i}",
                "player_name": f"K {i}",
                "position": "K",
                "projected_season_points": 150 - i,
                "vorp": 0.0,
                "model_rank": 999,
                "adp_rank": 999,
                "value_tier": "fair_value",
            }
            for i in range(5)
        ]
    )
    proj = pd.concat([pool, kickers], ignore_index=True)
    report = draft_live.run_auto_mock(
        proj,
        adp_df=None,
        n_teams=12,
        my_slot=6,
        draft_type="linear",
        rounds=4,
        roster_format="standard",
        roster_positions=_MAHOMO_SLOTS,
        scoring="ppr",
        league_name="Test League",
        top_n=5,
    )
    assert "AUTONOMOUS MOCK" in report
    assert "OPTIMAL STARTING LINEUP" in report
    assert "Draftable positions: QB, RB, TE, WR" in report
    assert " K " not in report  # no kicker drafted in a no-K league


# ---------------------------------------------------------------------------
# --simulate kicker-loop bug (knowledge-vault:
# nfl-draft-assistant-simulate-kicker-loop-bug.md, 2026-08-18)
#
# scripts/draft_assistant.py --league <preset> --simulate builds a
# DraftBoard/MockDraftSimulator straight from config.ROSTER_CONFIGS without
# the draftable_positions() pre-filter that scripts/draft_live.py already
# applies -- once skill-position VORP drops below a kicker's flat baseline
# late in a draft, the advisor keeps recommending kickers (no saturation cap
# on K/DST) and, for the no-K sleeper_gentlemen/sleeper_mahomos presets, a
# K that has no roster slot at all still gets drafted, leaving vorp NaN for
# that pick (replacement_ranks_for correctly omits K from a no-K shape) and
# poisoning total_vorp -> a bogus 'D' draft grade.
# ---------------------------------------------------------------------------


def _deep_pool_with_kd(n_per_pos: int = 80) -> pd.DataFrame:
    """A player pool deep enough to run a full 12-team, ~20-round simulated
    draft to completion across every startable position, including K/DST."""
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
                    "projected_season_points": base - i * 1.5,
                }
            )
    return pd.DataFrame(rows)


def _run_preset_simulation(preset_key: str, seed: int = 20260818):
    """Reproduce ``draft_assistant.py --league <preset_key> --simulate``:
    build the board/simulator the same way the CLI does (roster_format ->
    config.ROSTER_CONFIGS, no manual pre-filtering by the caller) and run a
    full simulation."""
    import random

    random.seed(seed)
    preset = config.LEAGUE_PRESETS[preset_key]
    roster_format = preset["roster"]
    n_teams = preset["teams"]
    pool = _deep_pool_with_kd()
    enriched = compute_value_scores(pool, roster_format=roster_format, n_teams=n_teams)
    board = DraftBoard(enriched, roster_format=roster_format, n_teams=n_teams)
    advisor = DraftAdvisor(board)
    sim = MockDraftSimulator(
        board, user_pick=1, n_teams=n_teams, randomness=3, draft_type="snake"
    )
    result = sim.run_full_simulation(advisor)
    return result, board


def test_simulate_no_k_roster_never_drafts_a_kicker():
    for preset_key in ("gentlemen", "mahomos"):
        result, board = _run_preset_simulation(preset_key)
        my_positions = Counter(
            str(p.get("position", "")).upper() for p in result["my_roster"]
        )
        assert my_positions.get("K", 0) == 0, (
            f"{preset_key}: user roster drafted a K despite no K slot "
            f"(roster={my_positions})"
        )
        all_positions = Counter(
            str(pick.get("position", "")).upper() for pick in result["picks"]
        )
        assert all_positions.get("K", 0) == 0, (
            f"{preset_key}: some team in the sim drafted a K despite no K "
            f"slot in {config.LEAGUE_PRESETS[preset_key]['roster']}"
        )


def test_simulate_with_k_roster_drafts_at_most_configured_kickers():
    for preset_key in ("la_liga", "feetball"):
        result, board = _run_preset_simulation(preset_key)
        k_slots = config.ROSTER_CONFIGS[config.LEAGUE_PRESETS[preset_key]["roster"]][
            "K"
        ]
        my_positions = Counter(
            str(p.get("position", "")).upper() for p in result["my_roster"]
        )
        assert my_positions.get("K", 0) <= k_slots, (
            f"{preset_key}: user roster drafted {my_positions.get('K', 0)} "
            f"kickers, roster only has {k_slots} K slot(s)"
        )


def test_simulate_total_vorp_finite_for_all_league_presets():
    for preset_key in config.LEAGUE_PRESETS:
        result, _ = _run_preset_simulation(preset_key)
        assert math.isfinite(result["total_vorp"]), (
            f"{preset_key}: total_vorp is not finite ({result['total_vorp']!r})"
        )
        # expected_vorp (the ADP-optimal baseline the grade is measured
        # against) walks the board independently of my_roster -- it must
        # stay finite too, or _pick_grade's `nan <= 0` check silently falls
        # through to a bogus 'D' (see MockDraftSimulator._estimate_expected_vorp).
        assert math.isfinite(result["expected_vorp"]), (
            f"{preset_key}: expected_vorp is not finite ({result['expected_vorp']!r})"
        )
        assert math.isfinite(result["total_pts"]), (
            f"{preset_key}: total_pts is not finite ({result['total_pts']!r})"
        )
        assert result["draft_grade"] in {"A", "B", "C", "D"}


# ---------------------------------------------------------------------------
# v8.3 — 2026-08-23 ESPN mock post-mortem fixes: suffix-blind ADP join,
# starters-first hard rule, opportunity-cost scoring, K/DST last.
# ---------------------------------------------------------------------------


def _pool(per_pos=None):
    """Synthetic projection pool with a monotone points ladder per position."""
    per_pos = per_pos or {"QB": 40, "RB": 90, "WR": 110, "TE": 40, "K": 25}
    base = {"QB": 380, "RB": 300, "WR": 240, "TE": 180, "K": 130}
    step = {"QB": 6, "RB": 4, "WR": 3, "TE": 4, "K": 1}
    rows = []
    for pos, n in per_pos.items():
        for i in range(n):
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "player_name": f"{pos} Player{i}",
                    "position": pos,
                    "team": "XX",
                    "projected_season_points": float(base[pos] - i * step[pos]),
                }
            )
    return pd.DataFrame(rows)


def _pool_adp(df):
    """ADP that follows the model ladder exactly (market agrees with model)."""
    adp = df[["player_name"]].copy()
    adp["adp_rank"] = (
        df["projected_season_points"].rank(ascending=False, method="first").astype(int)
    )
    return adp


def test_compute_value_scores_joins_adp_across_name_suffixes():
    proj = pd.DataFrame(
        {
            "player_id": ["a", "b", "c"],
            "player_name": ["James Cook", "Kenneth Walker III", "Marvin Harrison Jr."],
            "position": ["RB", "RB", "WR"],
            "projected_season_points": [260.0, 210.0, 180.0],
        }
    )
    adp = pd.DataFrame(
        {
            "player_name": ["James Cook III", "Kenneth Walker", "Marvin Harrison"],
            "adp_rank": [12, 22, 40],
        }
    )
    out = compute_value_scores(proj, adp, roster_format="espn_default", n_teams=12)
    got = dict(zip(out["player_name"], out["adp_rank"]))
    assert got == {"James Cook": 12, "Kenneth Walker III": 22, "Marvin Harrison Jr.": 40}


def test_draft_by_name_is_suffix_blind():
    board = DraftBoard(
        compute_value_scores(_pool(), roster_format="espn_default", n_teams=12),
        roster_format="espn_default",
    )
    board.available.loc[0, "player_name"] = "Travis Etienne"
    assert board.draft_by_name("Travis Etienne Jr.")["player_name"] == "Travis Etienne"


def test_recommend_starters_first_never_offers_qb2_before_wr1():
    players = compute_value_scores(_pool(), pd.DataFrame(), roster_format="espn_default")
    board = DraftBoard(players, roster_format="espn_default", n_teams=12)
    for pid in ("QB0", "RB0", "RB1", "TE0"):
        board.draft_player(pid, by_me=True)
    recs, reasoning = DraftAdvisor(board).recommend(top_n=8)
    assert set(recs["position"]) <= {"WR", "RB"}  # WR×2 + FLEX still open
    assert "QB" not in set(recs["position"]) and "TE" not in set(recs["position"])
    assert "starters first" in reasoning


def test_recommend_no_kicker_until_final_rounds():
    players = compute_value_scores(_pool(), pd.DataFrame(), roster_format="espn_default")
    board = DraftBoard(players, roster_format="espn_default", n_teams=12)
    for pid in ("QB0", "RB0", "RB1", "WR0", "WR1", "TE0", "WR2"):
        board.draft_player(pid, by_me=True)  # every skill starter + FLEX filled
    recs, _ = DraftAdvisor(board).recommend(top_n=8, my_picks_remaining=6)
    assert "K" not in set(recs["position"])
    recs, _ = DraftAdvisor(board).recommend(top_n=8, my_picks_remaining=2)
    assert "K" in set(recs["position"])


def test_recommend_opportunity_cost_prefers_the_vanishing_tier():
    """Equal VORP, but QB0's peers are gone by my next pick while RB0's tier
    survives — cost of waiting says QB now, RB later."""
    df = pd.DataFrame(
        {
            "player_id": ["QB0", "QB1", "RB0", "RB1", "RB2"],
            "player_name": ["QB Zero", "QB One", "RB Zero", "RB One", "RB Two"],
            "position": ["QB", "QB", "RB", "RB", "RB"],
            "projected_season_points": [300.0, 200.0, 300.0, 299.0, 298.0],
            # QB1 (the only fallback) goes right after this pick; RB1/RB2 last.
            "adp_rank": [20, 22, 21, 60, 61],
        }
    )
    players = compute_value_scores(
        df.drop(columns=["adp_rank"]), df[["player_name", "adp_rank"]], roster_format="standard"
    )
    board = DraftBoard(players, roster_format="standard", n_teams=12)
    with_cost, reasoning = DraftAdvisor(board).recommend(top_n=5, next_pick_no=40)
    assert with_cost.iloc[0]["player_name"] == "QB Zero"
    assert "cost of waiting" in reasoning
    qb = with_cost.set_index("player_name")
    assert qb.loc["QB Zero", "opportunity_cost"] > qb.loc["RB Zero", "opportunity_cost"]


def test_simulate_espn_default_builds_a_legal_lineup_in_order():
    pool = _pool()
    players = compute_value_scores(pool, _pool_adp(pool), roster_format="espn_default")
    board = DraftBoard(players, roster_format="espn_default", n_teams=12)
    adv = DraftAdvisor(board)
    sim = MockDraftSimulator(board, user_pick=2, n_teams=12, randomness=2)
    res = sim.run_full_simulation(adv, rounds=16)
    mine = [p for p in res["picks"] if p["team"] == "YOU"]
    by_pos = Counter(p["position"] for p in mine)
    first_wr = min(p["round"] for p in mine if p["position"] == "WR")
    assert first_wr <= 5
    assert len(mine) == 16
    # K/DST are gated to the final (open K/DST slots + 1) picks: DST has no
    # projection rows, so the K lands in one of the last three rounds.
    assert by_pos["K"] == 1 and [p for p in mine if p["position"] == "K"][0]["round"] >= 14
    assert by_pos["QB"] <= 2 and by_pos["TE"] <= 2
    # No backup QB/TE before the starting lineup (QB, 2RB, 2WR, TE) is complete.
    lineup_round = min(
        r for r in range(1, 17)
        if Counter(p["position"] for p in mine if p["round"] <= r)
        >= Counter({"QB": 1, "RB": 2, "WR": 2, "TE": 1})
    )
    seen = Counter()
    for p in mine:
        if p["position"] in ("QB", "TE") and seen[p["position"]] >= 1:
            assert p["round"] >= lineup_round
        seen[p["position"]] += 1
