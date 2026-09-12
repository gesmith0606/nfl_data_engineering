"""Unit tests for src/lineup_setter.py — the weekly lineup setter's pure logic."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.lineup_setter import (
    ET,
    PlayerRow,
    build_id_maps,
    build_rows,
    current_slots,
    kickoffs_for_week,
    lineup_deltas,
    ours_by_sleeper_id,
    preseason_to_weekly,
    render,
    roster_gsis_map,
    score_ours,
    score_sleeper_stats,
)

MANTIS = {
    "pass_yd": 0.04,
    "pass_td": 6.0,
    "rec": 1.0,
    "rec_yd": 0.1,
    "bonus_rec_te": 1.0,
    "rec_fd": 0.5,
    "fum_lost": -2.0,
}
POSITIONS = [
    "QB",
    "RB",
    "RB",
    "WR",
    "WR",
    "WR",
    "TE",
    "FLEX",
    "FLEX",
    "SUPER_FLEX",
    "BN",
    "BN",
]


# --- scoring -----------------------------------------------------------------


def test_sleeper_scoring_is_dot_product_with_te_premium_only_for_te():
    stats = {"rec": 5, "rec_yd": 60, "rec_fd": 3, "fum_lost": 0.1, "pts_ppr": 99.0}
    wr = score_sleeper_stats(stats, MANTIS, "WR")
    te = score_sleeper_stats(stats, MANTIS, "TE")
    assert wr == pytest.approx(5 + 6 + 1.5 - 0.2)
    assert te == pytest.approx(wr + 5)  # +1 per reception for TEs only


def test_preseason_to_weekly_divides_by_17_and_scores_under_league_rules():
    pre = pd.DataFrame(
        {
            "player_id": ["g1"],
            "player_name": ["Some TE"],
            "position": ["TE"],
            "recent_team": ["NE"],
            "receptions": [51.0],
            "receiving_yards": [850.0],
            "receiving_tds": [0.0],
            "passing_yards": [0.0],
            "passing_tds": [0.0],
            "interceptions": [0.0],
            "rushing_yards": [0.0],
            "rushing_tds": [0.0],
        }
    )
    weekly = preseason_to_weekly(pre)
    assert weekly["receptions"].iloc[0] == pytest.approx(3.0)
    scored = score_ours(weekly, MANTIS)
    assert scored["projected_points"].iloc[0] == pytest.approx(
        3 + 5 + 3, abs=0.11
    )  # rec + yds + TE bonus


# --- identity ----------------------------------------------------------------


REGISTRY = {
    "1": {
        "full_name": "Christian Watson",
        "position": "WR",
        "team": "GB",
        "gsis_id": "00-0038124",
        "injury_status": None,
        "depth_chart_order": 1,
    },
    "2": {
        "full_name": "Hunter Henry",
        "position": "TE",
        "team": "NE",
        "gsis_id": None,
        "injury_status": "Questionable",
        "depth_chart_order": 1,
    },
    "3": {
        "full_name": "Some QB",
        "position": "QB",
        "team": "BUF",
        "gsis_id": "00-0000003",
    },
    "4": {
        "full_name": "Bye Back",
        "position": "RB",
        "team": "MIA",
        "gsis_id": "00-0000004",
    },
}


def test_id_maps_use_gsis_then_name_position():
    by_gsis, by_name = build_id_maps(REGISTRY)
    assert by_gsis["00-0038124"] == "1"
    assert by_name[("hunter henry", "TE")] == "2"
    scored = pd.DataFrame(
        {
            "player_id": ["00-0038124", "00-9999999"],
            "player_name": ["C. Watson", "Hunter Henry"],
            "position": ["WR", "TE"],
            "projected_points": [12.0, 9.0],
        }
    )
    assert ours_by_sleeper_id(scored, REGISTRY) == {"1": 12.0, "2": 9.0}


def test_roster_crosswalk_maps_abbreviated_weekly_names():
    rosters = pd.DataFrame(
        {
            "season": [2025, 2026, 2026],
            "player_id": ["00-0000003", "00-0000003", "00-0000099"],
            "sleeper_id": [3.0, 3.0, 99.0],
        }
    )
    assert roster_gsis_map(rosters) == {"00-0000003": "3", "00-0000099": "99"}
    scored = pd.DataFrame(
        {
            "player_id": ["00-0000003", "00-0000099"],
            "player_name": ["S.QB", "N.Body"],  # weekly Gold style, no name match
            "position": ["QB", "RB"],
            "projected_points": [20.0, 7.0],
        }
    )
    registry_without_gsis = {
        "3": {"full_name": "Some QB", "position": "QB", "team": "BUF"}
    }
    assert ours_by_sleeper_id(scored, registry_without_gsis) == {}
    assert ours_by_sleeper_id(
        scored, registry_without_gsis, gsis_map=roster_gsis_map(rosters)
    ) == {"3": 20.0, "99": 7.0}


# --- schedule / slots --------------------------------------------------------


SCHED = pd.DataFrame(
    {
        "week": [1, 1, 2],
        "gameday": ["2026-09-10", "2026-09-13", "2026-09-17"],
        "gametime": ["20:15", "13:00", "20:15"],
        "home_team": ["LA", "GB", "BUF"],
        "away_team": ["SF", "NE", "MIA"],
    }
)


def test_kickoffs_and_lock_bye_flags():
    ko = kickoffs_for_week(SCHED, 1)
    assert ko["SF"] == dt.datetime(2026, 9, 10, 20, 15, tzinfo=ET)
    assert "BUF" not in ko
    now = dt.datetime(2026, 9, 12, 12, 0, tzinfo=ET)
    rows = build_rows(
        ["1", "2", "3"],
        ["3", "1"],
        ["QB", "WR", "BN"],
        REGISTRY,
        {},
        {},
        MANTIS,
        ko,
        now,
    )
    by_id = {r.sleeper_id: r for r in rows}
    assert by_id["3"].bye and by_id["3"].slot == "QB"
    assert by_id["1"].slot == "WR" and not by_id["1"].locked and not by_id["1"].bye
    assert by_id["2"].slot is None and "Questionable" in by_id["2"].notes
    # SF played Thursday -> locked; Sleeper's LAR maps onto the schedule's LA
    reg = {
        "9": {"full_name": "X", "position": "RB", "team": "SF"},
        "10": {"full_name": "Y", "position": "WR", "team": "LAR"},
    }
    rows_sf = build_rows(["9", "10"], [], [], reg, {}, {}, MANTIS, ko, now)
    assert rows_sf[0].locked
    assert rows_sf[1].locked and not rows_sf[1].bye


def test_render_orders_starters_by_roster_slot():
    reg = {
        "q": {"full_name": "Q", "position": "QB", "team": "T"},
        "w": {"full_name": "W", "position": "WR", "team": "T"},
    }
    rows = build_rows(
        ["w", "q"],
        ["q", "w"],
        ["QB", "SUPER_FLEX", "BN"],
        reg,
        {},
        {},
        MANTIS,
        {},
        None,
    )
    out = render(rows, [], "h", "x").splitlines()
    body = [ln for ln in out if ln.strip().startswith(("QB", "SFLEX"))]
    assert body[0].strip().startswith("QB") and body[1].strip().startswith("SFLEX")


def test_current_slots_zip_skips_bench_and_pads_empty():
    assert current_slots(["QB", "RB", "BN", "IR"], ["a"]) == [("QB", "a"), ("RB", "0")]


# --- deltas ------------------------------------------------------------------


def _row(pid, pos, ours, sleeper, slot=None, **kw):
    return PlayerRow(
        sleeper_id=pid,
        name=f"P{pid}",
        position=pos,
        team="T",
        ours=ours,
        sleeper=sleeper,
        slot=slot,
        **kw,
    )


def test_swap_only_when_both_sources_clear_threshold():
    rows = [
        _row("s", "WR", 8.0, 9.0, slot="FLEX"),
        _row("b1", "WR", 12.0, 13.0),  # +4 / +4 -> SWAP
    ]
    d = lineup_deltas(rows, threshold=3.0)
    assert [x.verdict for x in d] == ["SWAP"]
    assert d[0].in_player.sleeper_id == "b1" and d[0].slot == "FLEX"


def test_coin_flip_when_agree_but_thin_and_split_when_disagree():
    rows = [
        _row("s1", "WR", 8.0, 9.0, slot="WR"),
        _row("s2", "RB", 10.0, 10.0, slot="RB"),
        _row("b1", "WR", 12.0, 10.0),  # +4 / +1  -> COIN FLIP
        _row("b2", "RB", 14.0, 8.0),  # +4 / -2  -> SPLIT
    ]
    verdicts = {
        (x.slot, x.in_player.sleeper_id): x.verdict for x in lineup_deltas(rows, 3.0)
    }
    assert verdicts[("WR", "b1")] == "COIN FLIP"
    assert verdicts[("RB", "b2")] == "SPLIT"


def test_locked_and_bye_bench_never_proposed_and_locked_starter_untouched():
    rows = [
        _row("s", "WR", 5.0, 5.0, slot="WR"),
        _row("locked_s", "RB", 1.0, 1.0, slot="RB", locked=True),
        _row("b_locked", "WR", 20.0, 20.0, locked=True),
        _row("b_bye", "WR", 20.0, 20.0, bye=True),
        _row("b_rb", "RB", 20.0, 20.0),
    ]
    assert lineup_deltas(rows, 3.0) == []


def test_bench_player_used_once_and_goes_where_margin_is_largest():
    rows = [
        _row("flex", "WR", 9.0, 9.0, slot="FLEX"),
        _row("wr", "WR", 5.0, 5.0, slot="WR"),
        _row("b", "WR", 12.0, 12.0),
    ]
    d = lineup_deltas(rows, 3.0)
    assert len(d) == 1 and d[0].slot == "WR" and d[0].out_player.sleeper_id == "wr"


def test_position_not_eligible_for_slot_is_ignored():
    rows = [_row("qb", "QB", 5.0, 5.0, slot="QB"), _row("wr", "WR", 30.0, 30.0)]
    assert lineup_deltas(rows, 3.0) == []


def test_render_smoke_lists_lineup_bench_and_deltas():
    rows = [
        _row("s", "WR", 8.0, 9.0, slot="WR"),
        _row("b", "WR", 12.0, 13.0, injury_status="Q"),
    ]
    rows[1].notes.append("Q")
    out = render(rows, lineup_deltas(rows, 3.0), "hdr", "preseason pace")
    assert (
        "hdr" in out
        and "SWAP" in out
        and "BN" in out
        and "Starters total: ours 8.0 / Sleeper 9.0" in out
    )
