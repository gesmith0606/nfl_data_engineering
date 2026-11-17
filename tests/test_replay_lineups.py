"""The replay is the test bench: it must reproduce the measured 2026 table.

Fixture: ``tests/fixtures/lineup_replay/mantis_2026_w1_9.json.gz`` -- the Mantis
league, weeks 1-9, every roster. Frozen inputs only (our board as of Sunday
13:00 ET, Sleeper's projections as served on 2026-11-15, the official injury
report as of Sunday 09:00 ET, the schedule, actual points), so no network.

The baseline columns (set, sleeper_only, ours_only, hindsight, the v1 rule) do
not depend on the code under test, which is why they are pinned: a drift there
means the bench changed, not the tool.
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
import pytest

from scripts import replay_lineups as rl


@pytest.fixture(scope="module")
def data():
    return rl.load_fixture()


@pytest.fixture(scope="module")
def recs(data):
    return rl.replay(data)


def _mine(recs, rid=6):
    return [r for r in recs if r["rid"] == rid]


def test_reproduces_the_measured_table_for_george_weeks_1_to_9(recs):
    mine = _mine(recs)
    assert len(mine) == 9
    t = rl.totals(mine, rl._COLS + rl._CARRY)
    assert t["set"] == pytest.approx(1543.2, abs=0.1)
    assert t["v1_rule"] == pytest.approx(1543.2, abs=0.1)  # it recommended zero swaps
    assert t["v1_blend"] == pytest.approx(1519.9, abs=0.1)
    assert t["sleeper_only"] == pytest.approx(1540.3, abs=0.1)
    assert t["ours_only"] == pytest.approx(1506.5, abs=0.1)
    assert t["hindsight"] == pytest.approx(1762.2, abs=0.1)
    assert t["hindsight"] - t["set"] == pytest.approx(219.0, abs=0.1)


def test_reproduces_the_league_wide_totals(recs):
    assert len(recs) == 90
    t = rl.totals(recs, rl._COLS + ["carry_raw", "carry_v1"])
    assert t["set"] == pytest.approx(14993.2, abs=0.1)
    assert t["v1_blend"] == pytest.approx(14989.3, abs=0.1)
    assert t["sleeper_only"] == pytest.approx(15061.9, abs=0.1)
    assert t["ours_only"] == pytest.approx(14149.0, abs=0.1)
    assert t["hindsight"] == pytest.approx(17119.1, abs=0.1)
    assert t["carry_raw"] == pytest.approx(11451.3, abs=0.1)  # 80 roster-weeks
    assert t["carry_v1"] == pytest.approx(12607.2, abs=0.1)


def test_v1_rule_verdict_counts_league_wide(recs):
    """2 SWAPs (1 right), 26 COIN FLIPs (62% right), 57 SPLITs (33% right)."""
    v = rl.verdict_stats(recs, "v1_deltas")
    assert v.loc["SWAP", "n"] == 2 and v.loc["SWAP", "hit"] == 0.5
    assert v.loc["COIN FLIP", "n"] == 26 and v.loc["COIN FLIP", "hit"] == 0.62
    assert v.loc["SPLIT", "n"] == 57 and v.loc["SPLIT", "hit"] == 0.33


def test_the_tool_never_recommends_a_dead_starter(recs):
    """Acceptance: set lineups AND carried-over lineups, league-wide, n=170."""
    assert all(r["dead_tool"] == 0 for r in recs)
    carry = [r for r in recs if "carry_raw" in r]
    assert len(carry) == 80
    assert (
        sum(r["dead_carry"] for r in carry) > 50
    )  # the carried lineups really are full of them
    assert all(r["dead_carry_tool"] == 0 for r in carry)


def test_repairing_dead_slots_recovers_points_on_carried_lineups(recs):
    carry = [r for r in recs if "carry_raw" in r]
    raw = sum(r["carry_raw"] for r in carry)
    v1 = sum(r["carry_v1"] for r in carry)
    tool = sum(r["carry_tool"] for r in carry)
    assert tool > v1 > raw
    assert (
        tool - raw > 1000
    )  # ~1,560 points over 80 roster-weeks at the time of writing
    # starters who scored exactly 0 fall by roughly three quarters
    assert sum(r["zero_carry_tool"] for r in carry) < 0.3 * sum(
        r["zero_carry"] for r in carry
    )


def test_the_tool_does_not_hurt_lineups_people_already_set(recs):
    assert sum(r["tool"] for r in recs) >= sum(r["set"] for r in recs) - 1.0


def test_week_8_board_is_preseason_pace_and_the_tool_does_not_use_it(data):
    wk = data["weeks"]["8"]
    assert wk["ours_kind"] == "preseason_pace"
    assert all(
        data["weeks"][str(w)]["ours_kind"] == "weekly" for w in (1, 2, 3, 4, 5, 6, 7, 9)
    )


def test_hindsight_is_the_ceiling_on_every_variant(recs):
    for r in recs:
        for c in ("set", "v1_rule", "v1_blend", "sleeper_only", "ours_only", "tool"):
            assert r[c] <= r["hindsight"] + 0.05, (r["week"], r["rid"], c)


def test_summary_renders_the_table_and_counts(recs):
    out = rl.render_summary(recs, roster=6)
    assert (
        "90 roster-weeks" in out
        and "n=80 roster-weeks" in out
        and "Roster 6, n=9" in out
    )
    assert "1543.2" in out


# --- the pieces of the collector that carry a rule -----------------------------------


def test_pick_board_goes_by_filename_time_not_mtime(tmp_path):
    older = tmp_path / "projections_half_ppr_20261018_165001.parquet"
    newer = tmp_path / "projections_half_ppr_20261025_165121.parquet"
    derived = tmp_path / "projections_derived_20261026_100000.parquet"
    for p in (older, newer, derived):
        p.write_bytes(b"x")
    # make the OLDER board the most recently modified file
    os.utime(newer, (1, 1))
    os.utime(older, (10**9, 10**9))
    files = [str(older), str(newer), str(derived)]
    assert rl.pick_board(files, dt.datetime(2026, 10, 30)) == str(newer)
    # a board stamped after the cutoff does not exist yet
    assert rl.pick_board(files, dt.datetime(2026, 10, 20)) == str(older)
    assert rl.pick_board(files, dt.datetime(2026, 10, 1)) is None


def test_sunday_of_a_week_with_thursday_and_monday_games():
    sched = pd.DataFrame(
        {
            "week": [9, 9, 9, 9],
            "gameday": ["2026-11-05", "2026-11-08", "2026-11-08", "2026-11-09"],
        }
    )
    assert rl.sunday_of(sched, 9) == dt.date(2026, 11, 8)


def test_fixture_registry_carries_no_injury_tags(data):
    for meta in data["registry"].values():
        assert not {"injury_status", "practice_participation", "news_updated"} & set(
            meta
        )


# --- replay mechanics on a three-player league (no big fixture) --------------------------


def _mini(status=None):
    """QB on bye, WR set, WR on the bench; one week, one roster."""
    return {
        "meta": {},
        "league": {"roster_positions": ["QB", "WR", "BN"], "scoring_settings": {"rec": 1.0, "rec_yd": 0.1, "pass_yd": 0.04}},
        "registry": {
            "q": {"position": "QB", "team": "SF", "full_name": "Q Back"},
            "w1": {"position": "WR", "team": "BUF", "full_name": "W One"},
            "w2": {"position": "WR", "team": "BUF", "full_name": "W Two"},
        },
        "taxi": {},
        "weeks": {
            "3": {
                "ours_kind": "weekly", "ours_label": "mini",
                "ours_stats": {"q": {"position": "QB", "passing_yards": 250.0}, "w1": {"position": "WR", "receptions": 4.0, "receiving_yards": 40.0},
                               "w2": {"position": "WR", "receptions": 7.0, "receiving_yards": 90.0}},
                "sleeper_stats": {"q": {"pass_yd": 250.0}, "w1": {"rec": 4.0, "rec_yd": 40.0}, "w2": {"rec": 7.0, "rec_yd": 90.0}},
                "kickoffs": {"BUF": "2026-09-27T13:00:00-04:00"},  # SF is on bye
                "now_sun": "2026-09-27T09:00:00-04:00", "now_pre": "2026-09-27T12:00:00-04:00",
                "injury": {"reports": {}, "teams_reported": [], "played_prev": None, "sids": ["q", "w1", "w2"]},
                "status": status,
                "matchups": [{"roster_id": 1, "players": ["q", "w1", "w2"], "starters": ["q", "w1"],
                              "players_points": {"q": 0.0, "w1": 8.0, "w2": 16.0}}],
            }
        },
    }  # fmt: skip


def test_mini_replay_scores_every_variant_in_actual_points():
    (r,) = rl.replay(_mini())
    assert r["set"] == 8.0  # QB on bye scored nothing
    assert (
        r["tool"] == 16.0
    )  # no QB to bring in; the WR swap (w2 over w1, +8 on both) is the only move
    assert r["dead_set"] == 1 and r["dead_tool"] == 0
    assert r["hindsight"] == 16.0  # best lineup: w2 in the WR slot (no other QB)
    assert r["tool_fixes"] == 0  # nobody eligible to replace the QB


def test_a_saved_sleeper_out_tag_is_replayed_when_a_status_snapshot_exists():
    base = rl.replay(_mini())[0]
    tagged = _mini(status={"w1": {"injury_status": "IR"}})
    (r,) = rl.replay(tagged)
    assert (
        base["dead_set"] == 1 and r["dead_set"] == 2
    )  # w1 on IR is now a dead starter too
    assert r["tool"] == 16.0 and r["dead_tool"] == 0  # w2 replaces him
