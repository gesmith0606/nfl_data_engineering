"""The clearing-price model: what it takes to win, from the league's own claims."""

from __future__ import annotations

import pytest

from src import clearing_model as cm


def _obs(tier, tops, week=3):
    """``tops`` = top rival bid per name, 0 = uncontested."""
    return [cm.Obs(week, tier, (t,) if t else ()) for t in tops]


def test_tier_is_position_and_whether_the_board_ranks_him_top_three():
    assert cm.tier_of("RB", 1) == "RB-top"
    assert cm.tier_of("RB", 3) == "RB-top"
    assert cm.tier_of("RB", 4) == "RB-deep"
    assert cm.tier_of("WR", None) == "WR-deep"  # unranked is not a favourite


def test_contest_rate_is_shrunk_toward_the_league_rate():
    obs = _obs("RB-top", [0, 0, 0, 450]) + _obs("RB-deep", [0] * 20)
    m = cm.ClearingModel(obs)
    deep, top, unseen = (m.p_contested(t) for t in ("RB-deep", "RB-top", "TE-top"))
    assert 0 < deep < top  # no tier is ever 0% or 100% off a handful of rows
    assert min(deep, top) < unseen < max(deep, top, 0.5)  # unseen = the league rate
    assert unseen == pytest.approx(m.base_rate)


def test_p_win_is_the_uncontested_share_plus_beating_the_rival():
    m = cm.ClearingModel(_obs("QB-top", [10, 10, 10, 0]))
    q = m.p_contested("QB-top")
    assert m.p_win(1, "QB-top") == pytest.approx(
        1 - q, abs=0.02
    )  # min bid: only if alone
    assert m.p_win(11, "QB-top") > m.p_win(1, "QB-top")
    # a tie loses: bidding exactly the rival's number does not win it
    assert m.p_win(10, "QB-top") < m.p_win(11, "QB-top")
    # never certain: a rival can always show up with more than we planned for
    assert m.p_win(900, "QB-top") < 1.0


def test_p_win_never_decreases_with_the_bid():
    m = cm.ClearingModel(_obs("RB-top", [5, 40, 120, 450, 0, 0]))
    ps = [m.p_win(b, "RB-top") for b in range(1, 600, 7)]
    assert ps == sorted(ps)


def test_price_for_is_the_cheapest_bid_that_reaches_the_probability():
    m = cm.ClearingModel(_obs("QB-top", [20, 20, 20, 0, 0]))
    b = m.price_for(0.5, "QB-top")
    assert m.p_win(b, "QB-top") >= 0.5 > m.p_win(b - 1, "QB-top") if b > 1 else True
    assert m.price_for(0.999, "QB-top") is None  # the tail is never closed


def test_probably_uncontested_means_the_minimum_or_a_few_dollars():
    m = cm.ClearingModel(_obs("WR-deep", [0] * 30) + _obs("RB-top", [300, 250, 0]))
    adv = m.recommend("WR-deep", value=40, budget_left=800)
    assert adv.bid <= 3 and adv.floor == 1
    assert adv.p_win >= 0.75
    assert "rival" in adv.reason


def test_a_name_that_clears_above_his_value_is_a_lottery_ticket_not_a_chase():
    heavy = _obs("RB-top", [380, 312, 250, 400, 450, 300, 350])
    m = cm.ClearingModel(heavy)
    adv = m.recommend("RB-top", value=40, budget_left=1000)
    assert adv.bid < 40
    assert adv.price_for_half is None or adv.price_for_half > 40
    assert "lottery" in adv.reason


def test_a_contested_tier_that_is_cheap_to_clear_gets_a_real_bid():
    m = cm.ClearingModel(_obs("QB-top", [11, 12, 15, 11, 12, 11]))
    cheap = m.recommend("QB-deep", value=40, budget_left=800)
    real = m.recommend("QB-top", value=40, budget_left=800)
    assert real.bid > cheap.bid >= 1
    assert real.p_win > m.p_win(1, "QB-top")


def test_a_bid_is_never_above_the_cap_or_the_value_and_never_below_the_minimum():
    m = cm.ClearingModel(_obs("RB-top", [900] * 8))
    adv = m.recommend("RB-top", value=10_000, budget_left=100)
    assert 1 <= adv.bid <= 25  # a quarter of what is left
    tiny = m.recommend("RB-top", value=0, budget_left=500)
    assert tiny.bid == 1 and "minimum" in tiny.reason


def test_value_ceiling_is_points_over_the_drop_plus_dynasty_value():
    assert cm.value_ceiling(5.0, dyn_value=0, weeks=4, usd_per_point=2.0) == 40
    assert (
        cm.value_ceiling(-3.0, dyn_value=1000, usd_per_dyn=0.02) == 20
    )  # no negative points
    assert cm.value_ceiling(0.0) == 0


def test_replay_wins_only_by_beating_every_rival_and_pays_its_own_bid():
    assert cm.replay_bid(12, [11]) == (True, 12)
    assert cm.replay_bid(11, [11]) == (False, 0)  # tie loses
    assert cm.replay_bid(2, []) == (True, 2)
    assert cm.replay_bid(50, [10, 60]) == (False, 0)


def test_observations_round_trip_through_json():
    obs = [cm.Obs(3, "QB-top", (11, 4)), cm.Obs(4, "RB-deep", ())]
    assert cm.obs_from_json(cm.obs_to_json(obs)) == obs


def test_advise_all_ranks_within_position_and_prices_points_over_free_replacement():
    rows = [{"pos": "WR", "blend": 20.0 - i, "dyn": 0} for i in range(14)]
    rows += [{"pos": "TE", "blend": 9.0, "dyn": 1000}]
    m = cm.ClearingModel(_obs("WR-top", [0, 0, 0, 40]) + _obs("WR-deep", [0] * 8))
    cm.advise_all(rows, m, budget_left=800)
    wr = [r for r in rows if r["pos"] == "WR"]
    assert [r["rank"] for r in wr] == list(range(1, 15))
    assert wr[0]["tier"] == "WR-top" and wr[5]["tier"] == "WR-deep"
    # rank 12 (blend 9.0) is free replacement: nobody below it is worth a point
    assert wr[0]["above_free"] == pytest.approx(11.0)
    assert wr[11]["above_free"] == 0.0 and wr[13]["above_free"] == 0.0
    assert wr[0]["advice"].ceiling == round(2.0 * 11.0 * 4)
    assert wr[13]["advice"].ceiling == 0 and wr[13]["advice"].bid == 1
    # too few tight ends to define a replacement level: every point counts, plus dynasty
    te = rows[-1]
    assert (
        te["advice"].ceiling == round(2.0 * 9.0 * 4 + 0.02 * 1000) and te["rank"] == 1
    )


def _adv(bid=9):
    m = cm.ClearingModel(_obs("QB-top", [20, 0, 0, 40]))
    a = m.recommend("QB-top", value=60, budget_left=900)
    return cm.Advice(**{**a.__dict__, "bid": bid})


def test_final_bid_keeps_the_hazard_rules_that_are_not_about_price():
    old_cut = (1, "WE cut him in wk4 — re-buy at the minimum or not at all")
    old_end = (1, "his starter is returning — the role is ending, minimum or skip")
    kw = dict(no_help_redraft=False, depth_cap=None)
    assert cm.final_bid(old_cut, _adv(), role_ending=False, **kw) == old_cut
    assert cm.final_bid(old_end, _adv(), role_ending=True, **kw) == old_end
    assert cm.final_bid((7, "old"), _adv(9), role_ending=False, **kw)[0] == 9


def test_final_bid_refuses_no_help_in_redraft_and_caps_depth():
    assert cm.final_bid(
        (5, "x"), _adv(9), role_ending=False, no_help_redraft=True, depth_cap=None
    ) == (1, "rated no help — minimum or nothing")
    bid, why = cm.final_bid(
        None, _adv(9), role_ending=False, no_help_redraft=False, depth_cap=4
    )
    assert bid == 4 and "depth only" in why
    assert (
        cm.final_bid(
            None, _adv(3), role_ending=False, no_help_redraft=False, depth_cap=4
        )[0]
        == 3
    )


def test_a_bid_above_every_rivals_remaining_budget_cannot_lose():
    m = cm.ClearingModel(_obs("RB-top", [300, 250, 400, 0]))
    assert m.p_win(40, "RB-top") < 0.8
    assert m.p_win(40, "RB-top", rival_cap=30) == 1.0  # nobody left can bid 31+
    assert m.p_win(30, "RB-top", rival_cap=30) == m.p_win(
        30, "RB-top"
    )  # a tie still loses
    adv = m.recommend("RB-top", value=500, budget_left=1000, rival_cap=12)
    assert adv.bid == 13 and adv.p_win == 1.0  # the cheapest certain win
