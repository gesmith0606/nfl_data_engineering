"""Unit tests for src/waiver_verdicts.py — pickups judged against MY roster."""

from __future__ import annotations

from src.waiver_verdicts import (
    BENCH_UP,
    DEPTH,
    NO_HELP,
    STARTS,
    drop_order,
    load_keepers,
    roster_baseline,
    verdict,
)


def _r(sid, name, pos, blend, ir=False):
    return {"sid": sid, "name": name, "pos": pos, "blend": blend, "ir": ir}


# Feetball-like roster (2026 wk4): RB starters strong, keeper TE on the bench.
ROSTER = [
    _r("1", "Jalen Hurts", "QB", 16.3),
    _r("2", "Derrick Henry", "RB", 18.5),
    _r("3", "Christian McCaffrey", "RB", 16.4),
    _r("4", "Ashton Jeanty", "RB", 15.6),
    _r("5", "Jacory Croskey-Merritt", "RB", 10.3),
    _r("6", "Kyle Monangai", "RB", 9.1),
    _r("7", "Garrett Wilson", "WR", 15.9),
    _r("8", "Ladd McConkey", "WR", 10.3),
    _r("9", "Luther Burden III", "WR", 10.3),
    _r("10", "Brian Thomas Jr.", "WR", 5.6),
    _r("11", "Brenton Strange", "TE", 6.9),
    _r("12", "Colston Loveland", "TE", 5.5),
    _r("13", "Jadarian Price", "RB", 3.7, ir=True),
]
KEEPERS = {"luther burden", "colston loveland"}


def _baseline():
    return roster_baseline(ROSTER, roster_format="yahoo_feetball", keepers=KEEPERS)


def test_load_keepers_reads_only_our_starred_lines(tmp_path):
    f = tmp_path / "k.txt"
    f.write_text(
        "# header\n* Luther Burden III   # 9.06\n* Colston Loveland\nChase Brown  # rival\n"
    )
    assert load_keepers(f) == KEEPERS
    assert load_keepers(tmp_path / "missing.txt") == set()


def test_trending_rb_below_my_bench_is_no_help():
    # Braelon Allen 7.9 / Ollie Gordon 6.2 vs bench RBs 10.3 and 9.1.
    b = _baseline()
    assert verdict("RB", 7.9, b) == NO_HELP
    assert verdict("RB", 6.2, b) == NO_HELP


def test_ir_player_is_not_the_bench_bar_or_a_drop():
    b = _baseline()
    assert b["bench_floor"]["RB"] == 9.1  # Price (IR, 3.7) ignored
    assert "13" not in {r["sid"] for r in drop_order(ROSTER, b, KEEPERS)}


def test_keeper_is_never_a_drop_candidate():
    names = [r["name"] for r in drop_order(ROSTER, _baseline(), KEEPERS)]
    assert "Colston Loveland" not in names and "Luther Burden III" not in names
    assert names[0] == "Brian Thomas Jr."


def test_third_te_is_no_help_when_only_bench_te_is_a_keeper():
    # Gesicki 8.5 vs starter Strange 6.9 (+1.6 < margin); bench TE = keeper only.
    assert verdict("TE", 8.5, _baseline()) == NO_HELP


def test_starts_requires_margin_over_a_replaceable_starter():
    b = _baseline()
    assert verdict("QB", 17.9, b) == DEPTH  # +1.6 over Hurts, no bench QB
    assert verdict("QB", 18.5, b) == STARTS  # +2.2
    assert verdict("WR", 12.5, b) == STARTS  # beats WR3 10.3 by 2.2
    assert verdict("WR", 8.0, b) == BENCH_UP  # beats BTJ 5.6 by 2.4


def test_sleeper_roster_positions_shape_flex_slots():
    rows = [_r("a", "A", "RB", 12.0), _r("b", "B", "RB", 11.0), _r("c", "C", "WR", 6.0)]
    b = roster_baseline(rows, roster_positions=["RB", "FLEX", "BN", "BN"])
    assert set(b["starters"]) == {"a", "b"}
    assert verdict("WR", 13.5, b) == STARTS  # FLEX floor 11.0 + 2
    assert verdict("TE", 9.0, b) == DEPTH  # no TE anywhere


def test_out_player_does_not_set_the_bench_bar():
    rows = ROSTER + [{**_r("14", "Hurt WR", "WR", 0.0), "out": True}]
    b = roster_baseline(rows, roster_format="yahoo_feetball", keepers=KEEPERS)
    assert b["bench_floor"]["WR"] == 5.6  # BTJ, not the injured 0.0
