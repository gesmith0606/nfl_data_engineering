"""Scorecard for the waiver advice: points after the claim, price vs what it took.

Recorded fixtures only -- no network. Every number the Mantis backfill printed
on 2026-11-15 (157 / 42 / 282 / 431 points, $475 paid vs $19 needed) is pinned
by ``tests/test_waiver_scorecard_backfill.py`` against the committed artifact;
here the arithmetic is pinned on a league small enough to check by hand.
"""

from __future__ import annotations

import pytest

from src import waiver_scorecard as sc

DAY = 86_400_000
W1 = 1_788_840_000_000  # an arbitrary "week 1 starts" instant (ms)


def at(week: int, days: float = 1.0) -> int:
    """A timestamp ``days`` into NFL ``week``."""
    return int(W1 + (week - 1) * 7 * DAY + days * DAY)


SCORING = {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "bonus_rec_te": 0.5, "junk": 9.0}


# --------------------------------------------------------------------- points


def test_league_points_dots_only_known_numeric_keys():
    stats = {"rec": 5, "rec_yd": 50, "rec_td": 1, "unknown": 99, "name": "x"}
    assert sc.league_points(stats, SCORING) == pytest.approx(5 + 5 + 6)


def test_league_points_te_premium_arrives_as_its_own_stat_key():
    # Sleeper's stats feed carries bonus_rec_te per reception already.
    assert sc.league_points({"rec": 4, "bonus_rec_te": 4}, SCORING) == pytest.approx(6)


def test_window_is_clipped_at_the_last_complete_week():
    pts = {("a", 5): 10.0, ("a", 6): 20.0, ("a", 7): 30.0}
    get = lambda pid, wk: pts.get((pid, wk), 0.0)  # noqa: E731
    assert sc.window(get, "a", 5, 2, last_week=9) == (30.0, 2)
    # a claim in the last complete week only has that week to be judged on
    assert sc.window(get, "a", 7, 4, last_week=7) == (30.0, 1)
    # nothing played yet: zero weeks, not a zero score
    assert sc.window(get, "a", 8, 4, last_week=7) == (0.0, 0)


# ------------------------------------------------------------------ time / pool


def test_nfl_week_and_cutoff_line_up():
    assert sc.nfl_week(at(3, 2.5), W1) == 3
    assert sc.nfl_week(W1 - 5 * DAY, W1) == 1  # preseason moves belong to week 1
    assert at(3, 0) <= sc.week_cutoff(3, W1) < at(4, 0)
    assert sc.week_cutoff(3, W1) > at(3, 0.5)  # Tuesday evening, after the week turns


def _tx(kind, rid, adds, drops, week, bid=None, status="complete", days=2.0):
    return {
        "type": kind,
        "status": status,
        "roster_ids": [rid],
        "adds": {p: rid for p in adds} or None,
        "drops": {p: rid for p in drops} or None,
        "settings": {"waiver_bid": bid} if bid is not None else None,
        "status_updated": at(week, days),
        "_leg": week,
    }


def test_rostered_at_undoes_later_moves():
    now = {1: {"keep", "late_add"}, 2: {"x"}}
    txs = [
        _tx("waiver", 1, ["late_add"], ["gone"], week=4),
        _tx("waiver", 2, ["x"], [], week=2),
    ]
    assert sc.rostered_at(now, txs, at(3)) == {"keep", "gone", "x"}
    assert sc.rostered_at(now, txs, at(5)) == {"keep", "late_add", "x"}
    # a failed claim moved nothing
    txs.append(_tx("waiver", 2, ["nope"], [], week=4, status="failed", bid=9))
    assert "nope" not in sc.rostered_at(now, txs, at(5))


# ----------------------------------------------------------------- the ledger


def test_filed_adds_keeps_my_in_season_completed_adds_with_their_drop():
    txs = [
        _tx("waiver", 6, ["a"], ["d"], week=3, bid=100),
        _tx("waiver", 7, ["b"], [], week=3, bid=5),  # someone else's
        _tx("free_agent", 6, ["c"], [], week=2),  # a free add: no bid
        _tx("waiver", 6, ["z"], [], week=3, bid=40, status="failed"),
        _tx("trade", 6, ["t"], [], week=3),
        _tx("waiver", 6, ["pre"], [], week=1, bid=50, days=-20),  # preseason
    ]
    rows = sc.filed_adds(txs, roster_id=6, week1_start=W1)
    assert [(r["add"], r["drop"], r["bid"], r["week"]) for r in rows] == [
        ("c", None, 0, 2),
        ("a", "d", 100, 3),
    ]


def _contest(rival_bids, my_bid=100, me=6):
    win = _tx("waiver", me, ["p"], [], week=3, bid=my_bid)
    rivals = [
        _tx("waiver", 10 + i, ["p"], [], week=3, bid=b, status="failed")
        for i, b in enumerate(rival_bids)
    ]
    other = _tx("waiver", 99, ["someone_else"], [], week=3, bid=999, status="failed")
    stale = _tx("waiver", 98, ["p"], [], week=5, bid=777, status="failed")
    return win, [win, *rivals, other, stale]


def test_clearing_price_is_runner_up_plus_one_and_at_least_one():
    win, txs = _contest([30, 11])
    assert sc.clearing_price(win, txs) == 31
    win, txs = _contest([])
    assert sc.clearing_price(win, txs) == 1  # nobody bid: the minimum wins
    win, txs = _contest([0])  # a $0 claim does not raise the price
    assert sc.clearing_price(win, txs) == 1


def test_clearing_price_ignores_my_own_failed_duplicate_claims():
    win, txs = _contest([], my_bid=42)
    txs.append(_tx("waiver", 6, ["p"], [], week=3, bid=40, status="failed"))
    assert sc.clearing_price(win, txs) == 1


def test_score_bids_totals_and_contest_rate():
    w1, t1 = _contest([30])
    w2 = _tx("waiver", 6, ["q"], [], week=4, bid=300)
    rows = sc.score_bids([*t1, w2], roster_id=6, week1_start=W1)
    assert [(r["paid"], r["clearing"], r["rivals"]) for r in rows["rows"]] == [
        (100, 31, 1),
        (300, 1, 0),
    ]
    assert rows["paid"] == 400 and rows["clearing"] == 32
    assert rows["overpaid"] == 368
    assert rows["uncontested"] == 1 and rows["n"] == 2


def test_lost_bids_report_the_winning_price():
    win = _tx("waiver", 7, ["p"], [], week=4, bid=450)
    lost = _tx("waiver", 6, ["p"], [], week=4, bid=160, status="failed")
    other = _tx("waiver", 8, ["p"], [], week=4, bid=250, status="failed")
    rows = sc.lost_bids([win, lost, other], roster_id=6, week1_start=W1)
    assert rows == [{"add": "p", "week": 4, "bid": 160, "winner_bid": 450}]


# ------------------------------------------------------------------ scoring


def _row(sid, pos, blend, p1, p2, p4, **kw):
    return {
        "sid": sid,
        "name": sid.upper(),
        "pos": pos,
        "blend": blend,
        "p1": p1,
        "p2": p2,
        "p4": p4,
        **kw,
    }


def test_score_claims_compares_add_drop_board_top_and_hindsight_best():
    pool = {
        3: [
            _row("a", "WR", 9, 5, 10, 20),  # the add
            _row("top", "WR", 12, 3, 6, 40),  # board's #1 at WR
            _row("best", "WR", 4, 9, 18, 60),  # hindsight best at WR
            _row("te", "TE", 20, 99, 99, 99),  # other position never leaks in
        ]
    }
    claims = [{"add": "a", "drop": "d", "bid": 100, "week": 3, "pos": "WR"}]
    pts = {("d", 3): 1.0, ("d", 4): 2.0, **{("a", w): 5.0 for w in (3, 4, 5, 6)}}
    got = sc.score_claims(claims, pool, lambda pid, wk: pts.get((pid, wk), 0.0), 9)
    t = got["totals"]
    assert t["add"] == [5, 10, 20]
    assert t["drop"] == [1.0, 3.0, 3.0]
    assert t["board_top"] == [3, 6, 40]
    assert t["best_at_pos"] == [9, 18, 60]
    assert got["n"] == 1


def test_score_claims_a_claim_with_no_drop_scores_zero_for_the_drop():
    pool = {2: [_row("a", "TE", 5, 1, 2, 3)]}
    claims = [{"add": "a", "drop": None, "bid": 0, "week": 2, "pos": "TE"}]
    got = sc.score_claims(claims, pool, lambda p, w: 1.0 if p == "a" else 0.0, 9)
    assert got["totals"]["drop"] == [0, 0, 0]
    assert got["totals"]["add"] == [1.0, 2.0, 4.0]


def test_listed_names_are_the_top_k_per_position_by_the_method_asked_for():
    pool = {
        2: [
            _row("w1", "WR", 9, 1, 2, 10, slpr=1, last=0),
            _row("w2", "WR", 8, 1, 2, 20, slpr=2, last=0),
            _row("w3", "WR", 7, 1, 2, 90, slpr=9, last=0),
            _row("r1", "RB", 5, 1, 2, 30, slpr=1, last=0),
        ]
    }
    by_blend = sc.score_listed(pool, key=lambda r: -r["blend"], k=2)
    assert by_blend["n"] == 3  # 2 WR + 1 RB
    assert by_blend["p4"] == pytest.approx((10 + 20 + 30) / 3)
    by_slpr = sc.score_listed(pool, key=lambda r: -r["slpr"], k=2)
    assert by_slpr["p4"] == pytest.approx((90 + 20 + 30) / 3)
    best = sc.score_listed(pool, key=lambda r: -r["p4"], k=2)
    assert best["p4"] == pytest.approx((90 + 20 + 30) / 3)


def test_listed_scores_can_be_cut_by_week():
    pool = {
        2: [_row("a", "WR", 1, 0, 0, 10)],
        7: [_row("b", "WR", 1, 0, 0, 30)],
    }
    both = sc.score_listed(pool, key=lambda r: -r["blend"], k=6)
    early = sc.score_listed(pool, key=lambda r: -r["blend"], k=6, weeks=range(2, 7))
    assert both["p4"] == 20 and early["p4"] == 10 and early["n"] == 1
