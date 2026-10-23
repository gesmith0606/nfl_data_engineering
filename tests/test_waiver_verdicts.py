"""Unit tests for src/waiver_verdicts.py — pickups judged against MY roster."""

from __future__ import annotations

from pathlib import Path

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


def test_bye_player_is_neither_the_bench_bar_nor_a_drop():
    rows = ROSTER + [{**_r("15", "Star On Bye", "WR", 0.0), "bye": True}]
    b = roster_baseline(rows, roster_format="yahoo_feetball", keepers=KEEPERS)
    assert b["bench_floor"]["WR"] == 5.6
    assert "Star On Bye" not in [r["name"] for r in drop_order(rows, b, KEEPERS)]


def test_a_young_riser_is_not_offered_as_a_drop_where_players_are_kept():
    """The gate flagged this; the list should not have suggested it.

    Live week-7 Mantis named Adonai Mitchell (24, 61k adds) a drop candidate
    and the `young-drop` invariant failed the report. Correct, but the weaker
    half of "make the right thing the only path, then fail loudly" — so the
    list stops offering him and the gate stays as the backstop.
    """
    rows = [
        {
            "sid": "young",
            "name": "Adonai Mitchell",
            "age": 24,
            "adds": 61000,
            "dyn": 1242,
        },
        {"sid": "old", "name": "Jacoby Brissett", "age": 33, "adds": 0, "dyn": 1566},
        {"sid": "quiet", "name": "Pat Bryant", "age": 23, "adds": 0, "dyn": 1263},
    ]
    baseline = {"starters": set()}

    kept = [
        r["name"] for r in drop_order(rows, baseline, key="dyn", keeps_players=True)
    ]
    assert "Adonai Mitchell" not in kept
    # A young player nobody is adding is still droppable, or this protects
    # every rookie on the bench forever.
    assert kept == ["Pat Bryant", "Jacoby Brissett"]

    # Redraft has no reason to protect him.
    redraft = [r["name"] for r in drop_order(rows, baseline, key="dyn")]
    assert "Adonai Mitchell" in redraft


def test_a_role_the_news_says_is_ending_is_never_priced_up():
    """Live week-7: George Holani was bid $4 behind Charbonnet(returning)."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "ww_bid", root / "scripts" / "waiver_wire.py"
    )
    ww = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ww)

    held = [{"leg": 2, "bid": 40, "kind": "add", "by": "9"}]
    normal, why_normal = ww.suggest_bid(held, [30], 12, 400, 7)
    ending, why_ending = ww.suggest_bid(held, [30], 12, 400, 7, role_ending=True)
    assert normal > 1, "a contested role still prices up"
    assert ending == 1
    assert "role is ending" in why_ending
    assert why_ending != why_normal


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_a_depth_add_is_capped_by_value_not_by_what_it_takes_to_win():
    """The bid model prices CONTEST; it has no idea what a player is worth to us.

    Wiring the ESPN rival model immediately produced $14 — a quarter of our
    FAAB, the hard cap — on 20 players rated `depth`. With no rival model that
    flaw was invisible, because every site bid fell to the floor anyway.
    """
    src = (REPO_ROOT / "scripts" / "waiver_wire.py").read_text(encoding="utf-8")
    assert 'elif r.get("bid") and r["verdict"] == DEPTH:' in src
    assert "depth only — capped at the" in src
    # The cap must be the same floor the no-rival branch uses, not a new number.
    assert "floor = max(1, room_median // 5)" in src


def test_the_no_rival_floor_divisor_is_per_room_and_measured():
    """A price model tuned in one market has an unknown generalisation.

    The // 5 floor was swept against 51 Mantis bids ($1000 budget, $50 median
    winning bid). In La Liga ($100 budget, $8 median) that floor is $1, so
    every historyless player was bid at the minimum and lost: median error $6
    against the median rule's $4, i.e. the model was WORSE than the naive rule
    in the second room we measured. At // 1 it is $4 and passes.
    """
    import importlib.util

    from src import config

    spec = importlib.util.spec_from_file_location(
        "ww_floor", REPO_ROOT / "scripts" / "waiver_wire.py"
    )
    ww = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ww)

    # No history, no rivals -> the floor branch, which the divisor controls.
    assert ww.suggest_bid(None, [], 8, 100, 7, floor_divisor=5)[0] == 1
    assert ww.suggest_bid(None, [], 8, 100, 7, floor_divisor=1)[0] == 8
    # Default stays the Mantis-validated value for any unmeasured room.
    assert ww.suggest_bid(None, [], 50, 1000, 7)[0] == 10

    assert config.LEAGUE_PRESETS["la_liga"]["bid_floor_divisor"] == 1
    assert "bid_floor_divisor" not in config.LEAGUE_PRESETS["mantis"], (
        "Mantis's sweep curve is flat between // 3 and // 5 ($6 vs $7 at "
        "n=51), so it keeps the default rather than chasing noise"
    )


def test_the_young_drop_cutoff_is_now_backed_by_a_production_test():
    """Validated the right way round: value is a proxy for future production.

    Across 2022-24 a <=24 player whose weeks 5-8 snap share rose 10pp over
    weeks 1-4 went on to a median 5.16 PPG the FOLLOWING season, against 4.20
    for an older player with the same rising role — +0.96, consistent in sign
    all three years (n=97 vs 116). The earlier "unvalidated by design" verdict
    was reached by looking only for dynasty market-value history, which does
    not exist; the rule's own claim was testable on seasons already held.
    """
    import importlib.util

    src = (REPO_ROOT / "src" / "waiver_verdicts.py").read_text(encoding="utf-8")
    assert "VALIDATED" in src and "+0.96 PPG" in src
    assert "Unvalidated by design" not in src

    spec = importlib.util.spec_from_file_location(
        "vyd", REPO_ROOT / "scripts" / "validate_young_drop.py"
    )
    vyd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vyd)
    # The script must still print BOTH caveats, or the verdict overstates.
    body = (REPO_ROOT / "scripts" / "validate_young_drop.py").read_text(
        encoding="utf-8"
    )
    assert "WRONG MECHANISM" in body, "the misleading sweep must stay visible"
    assert "MARKET-VALUE confirmation is still pending" in body
    # And it must key off the shipped cutoff, not a hardcoded 24.
    assert "YOUNG_AGE" in body and "<= {YOUNG_AGE}" in body
