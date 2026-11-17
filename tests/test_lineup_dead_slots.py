"""Dead starters, empty slots and the MUST FIX repair (src/lineup_setter.py).

2026 replay of the Mantis league: in carried-over lineups 39 of 105 starters on
bye or ruled out stayed in, and the tool could not see an empty slot at all.
"""

from __future__ import annotations

import datetime as dt

from src.lineup_setter import (
    ET,
    InjuryContext,
    OfficialReport,
    PlayerRow,
    assign_slots,
    build_id_maps,
    build_rows,
    lineup_deltas,
    optimal_starters,
    recommend,
    render,
    repair_lineup,
    resolve_injury_status,
)

POSITIONS = ["QB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN", "BN"]
NOW = dt.datetime(2026, 11, 8, 9, 0, tzinfo=ET)


def _row(pid, pos, ours, sleeper, slot=None, **kw):
    return PlayerRow(
        sleeper_id=pid,
        name=f"P{pid}",
        position=pos,
        team=kw.pop("team", "T"),
        ours=ours,
        sleeper=sleeper,
        slot=slot,
        **kw,
    )


def _starters(**by_slot_index):
    """Starters list for POSITIONS (9 slots), "0" where not given: s0=QB ... s8=DEF."""
    out = ["0"] * 9
    for k, v in by_slot_index.items():
        out[int(k[1:])] = v
    return out


# --- what counts as dead --------------------------------------------------------


def test_dead_reasons_bye_no_team_out_doubtful_but_not_questionable():
    assert _row("1", "WR", 9, 9, bye=True).dead_reason == "BYE"
    assert _row("2", "WR", 9, 9, team="FA").dead_reason == "no NFL team"
    assert _row("3", "WR", 9, 9, status_level="OUT").dead_reason == "OUT"
    assert _row("4", "WR", 9, 9, status_level="DOUBTFUL").dead_reason == "DOUBTFUL"
    assert _row("5", "WR", 9, 9, status_level="QUESTIONABLE").dead_reason is None
    assert not _row("6", "WR", 9, 9).dead


def test_unconfirmed_sleeper_out_tag_is_not_dead():
    """A stale tag is CHECK STATUS territory, never an automatic bench."""
    r = _row("1", "WR", 9, 0.0, status_unconfirmed=True)
    assert not r.dead


def _meta(**kw):
    return {"position": "WR", "team": "BUF", "injury_status": None, **kw}


def _ctx(reports=None, teams=(), played_prev=None):
    return InjuryContext(
        week=3,
        reports=reports or {},
        teams_reported=set(teams),
        played_prev=played_prev,
        gsis_by_sleeper={"1": "g1"},
    )


def test_status_level_from_official_report_and_designations():
    out = resolve_injury_status(
        "1", _meta(), _ctx({"g1": OfficialReport("Out", "Knee", ("DNP",), NOW)}), NOW
    )
    assert out.level == "OUT"
    q = resolve_injury_status(
        "1", _meta(), _ctx({"g1": OfficialReport("Questionable", None, (), NOW)}), NOW
    )
    assert q.level == "QUESTIONABLE"
    ir = resolve_injury_status("2", _meta(injury_status="IR"), _ctx(), NOW)
    assert ir.level == "OUT"  # roster designation: no game this week
    healthy = resolve_injury_status("3", _meta(), _ctx(), NOW)
    assert healthy is None


def test_stale_sleeper_out_gets_no_level_but_a_missed_week_does():
    played = _ctx(played_prev={"g1"})
    stale = resolve_injury_status("1", _meta(injury_status="Out"), played, NOW)
    assert stale.unconfirmed_bench_tag and stale.level is None
    missed = resolve_injury_status(
        "1", _meta(injury_status="Out"), _ctx(played_prev=set()), NOW
    )
    assert not missed.unconfirmed_bench_tag and missed.level == "OUT"


def test_build_rows_marks_bye_only_when_a_schedule_exists():
    reg = {"1": {"position": "QB", "team": "SF", "full_name": "Brock Purdy"}}
    ko = {"BUF": NOW}
    kw = dict(
        player_ids=["1"], starters=[], roster_positions=["QB"], registry=reg,
        ours={}, sleeper_proj={}, scoring_settings={}, now=NOW,
    )  # fmt: skip
    assert build_rows(kickoffs=ko, **kw)[0].bye
    assert not build_rows(kickoffs={}, **kw)[0].bye  # no schedule: no claim


# --- repair ---------------------------------------------------------------------


def test_bye_starter_is_replaced_by_best_eligible_bench_player():
    rows = [
        _row("qb", "QB", 20, 20, slot="QB", bye=True),
        _row("qb2", "QB", 12, 12),
        _row("wr", "WR", 15, 15),
    ]
    starters, fixes = repair_lineup(rows, POSITIONS, _starters(s0="qb"))
    assert starters[0] == "qb2"
    f = next(x for x in fixes if x.out_player and x.out_player.sleeper_id == "qb")
    assert f.reason == "BYE" and f.in_player.sleeper_id == "qb2"


def test_empty_slots_are_filled_including_super_flex():
    """The old allocation looked slots up by display name and left SUPER_FLEX empty."""
    rows = [
        _row("qb", "QB", 20, 20, slot="QB"),
        _row("qb2", "QB", 18, 18),
        _row("rb", "RB", 10, 10),
    ]
    starters, fixes = repair_lineup(rows, POSITIONS, _starters(s0="qb"))
    assert starters[6] == "qb2"  # SUPER_FLEX
    assert starters[1] == "rb"  # RB slot was empty too
    assert {f.slot for f in fixes} >= {"SUPER_FLEX", "RB"}
    assert all(f.out_player is None for f in fixes if f.slot in ("RB", "SUPER_FLEX"))


def test_no_eligible_replacement_vacates_the_slot_and_says_so():
    rows = [_row("te", "TE", 9, 9, slot="TE", status_level="OUT")]
    starters, fixes = repair_lineup(rows, POSITIONS, _starters(s4="te"))
    assert starters[4] == "0"
    assert fixes[0].in_player is None and "no eligible player" in fixes[0].line()


def test_one_bench_player_cannot_fill_two_slots():
    rows = [
        _row("w1", "WR", 9, 9, slot="WR", bye=True),
        _row("w2", "WR", 9, 9, slot="WR", bye=True),
        _row("b", "WR", 8, 8),
    ]
    starters, _ = repair_lineup(rows, POSITIONS, _starters(s2="w1", s3="w2"))
    assert starters.count("b") == 1


def test_locked_dead_starter_and_locked_bench_are_left_alone():
    rows = [
        _row("w", "WR", 9, 9, slot="WR", status_level="OUT", locked=True),
        _row("b", "WR", 8, 8, locked=True),
    ]
    starters, fixes = repair_lineup(rows, POSITIONS, _starters(s2="w"))
    assert starters[2] == "w"
    assert not [f for f in fixes if f.out_player]


def test_replacement_never_dead_or_unconfirmed():
    rows = [
        _row("w", "WR", 9, 9, slot="WR", bye=True),
        _row("dead", "WR", 30, 30, status_level="OUT"),
        _row("stale", "WR", 30, 0.0, status_unconfirmed=True),
        _row("ok", "WR", 5, 5),
    ]
    starters, _ = repair_lineup(rows, POSITIONS, _starters(s2="w"))
    assert starters[2] == "ok"


def test_a_missing_board_row_uses_the_consensus_and_never_blocks():
    """231 of 1,818 rostered player-weeks had no row on our board (Puka, week 4)."""
    rows = [
        _row("s", "WR", 8.0, 8.0, slot="WR"),
        _row("puka", "WR", None, 14.0),  # no row on our board
    ]
    assert [d.verdict for d in lineup_deltas(rows, 3.0)] == ["SWAP"]
    # the pre-fix behaviour: the missing row blocked the pair
    assert [d.verdict for d in lineup_deltas(rows, 3.0, legacy=True)] == ["SPLIT"]


def test_dead_starter_and_dead_bench_are_not_deltas():
    rows = [
        _row("s", "WR", 30.0, 30.0, slot="WR", bye=True),  # raw projection is huge
        _row("b", "WR", 10.0, 10.0),
        _row("bd", "WR", 40.0, 40.0, status_level="OUT"),
    ]
    assert lineup_deltas(rows, 3.0) == []  # the starter is a MUST FIX, not a delta


def test_recommend_repairs_first_then_swaps_on_the_repaired_lineup():
    rows = [
        _row("qb", "QB", 20, 20, slot="QB", bye=True),
        _row("qb2", "QB", 12, 12),
        _row("wr1", "WR", 6, 6, slot="WR"),
        _row("wr2", "WR", 14, 14),
    ]
    rec = recommend(rows, ["QB", "WR", "BN"], ["qb", "wr1"], threshold=3.0)
    assert [f.reason for f in rec.must_fix if f.out_player] == ["BYE"]
    assert rec.starters == ["qb2", "wr2"]
    assert [d.verdict for d in rec.deltas] == ["SWAP"]
    assert "qb" not in rec.starters and "wr1" not in rec.starters
    # judged on the repaired lineup: the swap is wr2 over wr1, not anything about qb
    assert rec.deltas[0].out_player.sleeper_id == "wr1"


def test_recommended_lineup_has_no_dead_starter_when_anyone_alive_exists():
    rows = [
        _row("a", "RB", 9, 9, slot="RB", bye=True),
        _row("b", "RB", 8, 8, slot="FLEX", status_level="DOUBTFUL"),
        _row("c", "RB", 7, 7),
        _row("d", "WR", 6, 6),
    ]
    rec = recommend(rows, POSITIONS, _starters(s1="a", s5="b"))
    by_id = {r.sleeper_id: r for r in rows}
    assert not [p for p in rec.starters if p != "0" and by_id[p].dead]


# --- assignment and the no-lineup path -----------------------------------------------


def test_assign_slots_is_optimal_with_crossing_flex_slots():
    """Greedy fills W/R first and strands the TE: WR 20, RB 5, TE 4 -> 25, not 24."""
    rows = [_row("wr", "WR", 20, 20), _row("rb", "RB", 5, 5), _row("te", "TE", 4, 4)]
    got = assign_slots(["WRRB_FLEX", "REC_FLEX"], rows)
    assert sorted(r.sleeper_id for r in got if r) == ["rb", "wr"] or sorted(
        r.sleeper_id for r in got if r
    ) == ["te", "wr"]
    total = sum(r.blend for r in got if r)
    assert total == 25.0


def test_optimal_starters_fills_super_flex_k_and_def_and_skips_dead():
    rows = [
        _row("qb", "QB", 20, 20),
        _row("qb2", "QB", 15, 15),
        _row("rb", "RB", 10, 10),
        _row("wr1", "WR", 9, 9),
        _row("wr2", "WR", 8, 8),
        _row("te", "TE", 7, 7),
        _row("k", "K", 8, 8),
        _row("def", "DEF", 6, 6),
        _row("dead_rb", "RB", 50, 50, bye=True),
    ]
    got = optimal_starters(rows, POSITIONS)
    assert len(got) == 9
    assert got[0] == "qb" and got[6] == "qb2"  # SUPER_FLEX holds the second QB
    assert got[7] == "k" and got[8] == "def"
    assert "dead_rb" not in got


# --- K / DEF identity ----------------------------------------------------------------


def test_id_maps_index_kickers_and_defences():
    reg = {
        "11533": {"full_name": "Brandon Aubrey", "position": "K", "active": True},
        "HOU": {
            "full_name": None, "first_name": "Houston", "last_name": "Texans",
            "position": "DEF", "active": True,
        },
    }  # fmt: skip
    _gsis, by_name = build_id_maps(reg)
    assert by_name[("brandon aubrey", "K")] == "11533"
    assert by_name[("houston texans", "DEF")] == "HOU"
    assert by_name[("texans", "DEF")] == "HOU"


# --- the report ----------------------------------------------------------------------


def test_render_prints_must_fix_before_the_lineup_table():
    rows = [_row("qb", "QB", 20, 20, slot="QB", bye=True), _row("qb2", "QB", 12, 12)]
    rec = recommend(rows, ["QB", "BN"], ["qb"])
    out = render(rec.rows, rec.deltas, "hdr", "weekly", must_fix=rec.must_fix)
    assert out.index("MUST FIX") < out.index("SLOT")
    assert "Pqb" in out and "BYE" in out and "Pqb2" in out
    none = render(rows, [], "hdr", "weekly", must_fix=[])
    assert "MUST FIX: none" in none
    assert "MUST FIX" not in render(rows, [], "hdr", "weekly")
