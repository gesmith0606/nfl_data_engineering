"""Unit tests for src/lineup_setter.py — the weekly lineup setter's pure logic."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from src.lineup_setter import (
    ET,
    InjuryContext,
    PlayerRow,
    build_id_maps,
    build_rows,
    current_slots,
    kickoffs_for_week,
    lineup_deltas,
    official_reports,
    ours_by_sleeper_id,
    preseason_to_weekly,
    render,
    resolve_injury_status,
    roster_gsis_map,
    score_ours,
    score_sleeper_stats,
    sleeper_to_gsis,
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


def test_full_name_fallback_joins_rookies_without_any_id_crosswalk():
    # 2026 rookies: abbreviated Gold name, no sleeper_id in Bronze rosters,
    # no gsis_id in the Sleeper registry. Only a gsis -> full-name map
    # (from Bronze weekly actuals) can join them.
    scored = pd.DataFrame(
        {
            "player_id": ["00-0041512"],
            "player_name": ["J.Price"],
            "position": ["RB"],
            "projected_points": [9.8],
        }
    )
    registry = {
        "13000": {"full_name": "Jadarian Price", "position": "RB", "team": "SEA"}
    }
    assert ours_by_sleeper_id(scored, registry) == {}
    assert ours_by_sleeper_id(
        scored, registry, full_names={"00-0041512": "Jadarian Price"}
    ) == {"13000": 9.8}


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


# --- injury status: official report vs stale Sleeper tag ----------------------

NOW = dt.datetime(2026, 9, 24, 18, 0, tzinfo=ET)
MOORE = {
    "full_name": "DJ Moore",
    "position": "WR",
    "team": "BUF",
    "gsis_id": "00-0034827",
    "injury_status": "Out",
    "injury_body_part": "Shoulder",
    # 2026-09-20 10:20 ET -> 4 days before NOW
    "news_updated": int(dt.datetime(2026, 9, 20, 10, 20, tzinfo=ET).timestamp() * 1000),
}
LP = "Limited Participation in Practice"
FP = "Full Participation in Practice"
DNP = "Did Not Participate In Practice"


def _snap(rows, at):
    cols = [
        "week",
        "team",
        "gsis_id",
        "report_primary_injury",
        "report_status",
        "practice_primary_injury",
        "practice_status",
    ]
    return pd.DataFrame(rows, columns=cols).assign(snapshot_at=at)


def test_official_reports_uses_latest_snapshot_and_builds_practice_trail():
    wed = _snap(
        [
            [3, "BUF", "00-0034827", None, None, "Shoulder", DNP],
            [3, "BUF", "00-0000777", None, None, "Knee", DNP],  # off by Friday
            [2, "MIA", "00-0000555", "Ankle", "Out", "Ankle", DNP],
        ],
        dt.datetime(2026, 9, 24, 12, 0),
    )
    thu = _snap(
        [[3, "BUF", "00-0034827", None, None, "Shoulder", LP]],
        dt.datetime(2026, 9, 25, 12, 0),
    )
    fri = _snap(
        [
            [3, "BUF", "00-0034827", "Shoulder", "Questionable", "Shoulder", LP],
            [3, "KC", "00-0000888", None, None, "Hip", FP],
        ],
        dt.datetime(2026, 9, 26, 12, 0),
    )
    reports, teams = official_reports(pd.concat([wed, thu, fri]), week=3)
    assert set(reports) == {"00-0034827", "00-0000888"}  # latest snapshot only
    moore = reports["00-0034827"]
    assert moore.game_status == "Questionable" and moore.injury == "Shoulder"
    assert moore.practice == ("DNP", "LP")  # repeats collapsed
    assert teams == {"BUF", "KC"}
    assert official_reports(pd.DataFrame(), 3) == ({}, set())


def _ctx(reports=None, teams=None, played_prev=None):
    return InjuryContext(
        week=3,
        reports=reports or {},
        teams_reported=teams or set(),
        played_prev=played_prev,
        gsis_by_sleeper={"4983": "00-0034827"},
    )


def test_official_report_preferred_over_sleeper_tag():
    fri = _snap(
        [[3, "BUF", "00-0034827", "Shoulder", "Questionable", "Shoulder", LP]],
        dt.datetime(2026, 9, 26, 12, 0),
    )
    st = resolve_injury_status("4983", MOORE, _ctx(*official_reports(fri, 3)), NOW)
    assert st.text.startswith("wk3 Q (Shoulder)")
    assert "practice LP" in st.text and "report 09-26" in st.text
    assert "Sleeper still says Out" in st.text
    assert st.unconfirmed_bench_tag  # report says Q, Sleeper says Out


def test_official_report_without_game_status_yet():
    wed = _snap(
        [[3, "BUF", "00-0034827", None, None, "Shoulder", DNP]],
        dt.datetime(2026, 9, 24, 12, 0),
    )
    st = resolve_injury_status("4983", MOORE, _ctx(*official_reports(wed, 3)), NOW)
    assert "no game status yet" in st.text and "practice DNP" in st.text
    assert st.unconfirmed_bench_tag


def test_official_out_confirms_the_tag():
    fri = _snap(
        [[3, "BUF", "00-0034827", "Shoulder", "Out", "Shoulder", DNP]],
        dt.datetime(2026, 9, 26, 12, 0),
    )
    st = resolve_injury_status("4983", MOORE, _ctx(*official_reports(fri, 3)), NOW)
    assert st.text.startswith("wk3 Out (Shoulder)") and not st.unconfirmed_bench_tag


def test_stale_sleeper_out_from_last_weeks_game_is_labelled():
    st = resolve_injury_status("4983", MOORE, _ctx(played_prev={"00-0034827"}), NOW)
    assert st.text == (
        "Sleeper: Out (Shoulder), from wk2 game, not a wk3 ruling, news 4d old"
    )
    assert st.unconfirmed_bench_tag


def test_sleeper_out_for_player_who_missed_last_week_is_not_stale():
    st = resolve_injury_status("4983", MOORE, _ctx(played_prev=set()), NOW)
    assert "did not play wk2" in st.text and not st.unconfirmed_bench_tag


def test_team_report_out_but_player_absent_means_tag_is_stale():
    st = resolve_injury_status("4983", MOORE, _ctx(teams={"BUF"}), NOW)
    assert "not on BUF wk3 report" in st.text and st.unconfirmed_bench_tag


def test_roster_designations_and_healthy_players():
    ir = {**MOORE, "injury_status": "IR"}
    st = resolve_injury_status("4983", ir, _ctx(played_prev={"00-0034827"}), NOW)
    assert st.text.startswith("Sleeper: IR") and not st.unconfirmed_bench_tag
    healthy = {**MOORE, "injury_status": None}
    assert resolve_injury_status("4983", healthy, _ctx(), NOW) is None


def test_sleeper_to_gsis_prefers_registry_then_roster_crosswalk():
    reg = {"1": {"gsis_id": "g1"}, "2": {"gsis_id": None}}
    assert sleeper_to_gsis(reg, {"g2": "2", "gx": "1"}) == {"1": "g1", "2": "g2"}


def test_no_swap_on_stale_sleeper_out_tag_check_status_instead():
    rows = [
        _row("moore", "WR", 3.0, 0.0, slot="WR", status_unconfirmed=True),
        _row("b1", "WR", 9.0, 9.0),  # +6 / +9 would be a SWAP
        _row("s2", "RB", 5.0, 5.0, slot="RB"),
        _row("b2", "RB", 10.0, 10.0),  # healthy starter -> still SWAP
    ]
    d = {x.out_player.sleeper_id: x for x in lineup_deltas(rows, 3.0)}
    assert d["moore"].verdict == "CHECK STATUS"
    assert d["s2"].verdict == "SWAP"
    out = render(rows, list(d.values()), "hdr", "x")
    assert "CHECK STATUS" in out and "not this week's official ruling" in out


def test_build_rows_uses_injury_context_and_news_flags():
    rows = build_rows(
        ["4983"],
        ["4983"],
        ["WR", "BN"],
        {"4983": MOORE},
        {},
        {},
        MANTIS,
        {},
        NOW,
        injury_ctx=_ctx(played_prev={"00-0034827"}),
        news={"4983": "questionable"},
    )
    r = rows[0]
    assert r.status_unconfirmed
    assert any("not a wk3 ruling" in n for n in r.notes)
    assert "news: questionable" in r.notes
