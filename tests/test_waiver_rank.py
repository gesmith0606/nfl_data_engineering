"""One ranked list per league: four-week gain to my lineup, byes included."""

from __future__ import annotations

import pytest

from src import waiver_rank as wr

ALL = {"AAA", "BBB", "CCC", "DDD"}


def _playing(**byes):
    """``{week: teams that play}``; ``byes={'AAA': 12}`` = AAA idle in week 12."""
    out = {w: set(ALL) for w in range(10, 18)}
    for team, wk in byes.items():
        out[wk].discard(team)
    return out


def _r(sid, pos, blend, team="AAA", **kw):
    return {"sid": sid, "pos": pos, "blend": blend, "team": team, **kw}


# ------------------------------------------------------------------ consensus


def test_consensus_averages_only_while_the_two_sources_agree_within_2x():
    assert wr.consensus(10.0, 14.0) == (12.0, "both")
    assert wr.consensus(10.0, 20.0) == (15.0, "both")  # exactly 2x still agrees
    assert wr.consensus(10.0, 21.0) == (21.0, "disagree")  # Sleeper's number stands
    assert wr.consensus(21.0, 10.0) == (10.0, "disagree")  # in either direction


def test_a_sleeper_zero_is_not_averaged_into_a_starter():
    # Tyler Huntley wk8: ours 16.8, Sleeper 0.0 -> the old blend said 8.4
    assert wr.consensus(16.8, 0.0) == (0.0, "disagree")


def test_consensus_says_which_source_it_rests_on_when_one_is_missing():
    assert wr.consensus(None, 7.0) == (7.0, "sleeper_only")
    assert wr.consensus(7.0, None) == (7.0, "ours_only")
    assert wr.consensus(None, None) == (0.0, "none")


# --------------------------------------------------------------------- byes


def test_games_in_window_counts_byes_and_trusts_an_unknown_schedule():
    play = _playing(AAA=12)
    assert wr.games_in_window("AAA", 11, play) == 3  # weeks 11-14, idle in 12
    assert wr.games_in_window("BBB", 11, play) == 4
    assert wr.games_in_window("AAA", 11, {}) == 4  # no schedule: do not invent a bye
    assert wr.games_in_window(None, 11, play) == 4
    # a window running past the schedule counts only the weeks we know
    # weeks 16-19: the season ends at 18 (19 is not played), and 18 is not in this
    # schedule so it counts as played: 16 yes, 17 bye, 18 yes
    assert wr.games_in_window("AAA", 16, _playing(AAA=17)) == 2


# ----------------------------------------------------------------- the gain


FORMAT = "standard"  # QB1 RB2 WR2 TE1 FLEX1 (+K/DST, unused here)


def _roster():
    return [
        _r("q", "QB", 20),
        _r("r1", "RB", 14),
        _r("r2", "RB", 12),
        _r("w1", "WR", 13),
        _r("w2", "WR", 11),
        _r("te", "TE", 9),
        _r("flex", "WR", 10),
    ]


def test_a_claim_is_worth_the_gain_to_my_lineup_not_his_own_points():
    play = _playing()
    better_te = _r("n", "TE", 12)  # +3 a week over the starter
    same_te = _r("m", "TE", 8)  # worse than my starter: no gain
    assert wr.window_gain(better_te, _roster(), 11, play, FORMAT) == pytest.approx(12.0)
    assert wr.window_gain(same_te, _roster(), 11, play, FORMAT) == 0.0


def test_a_bye_in_the_window_costs_the_gain_for_that_week():
    play = _playing(BBB=12)
    cand = _r("n", "TE", 12, team="BBB")
    # plays 3 of 4 weeks; in the idle week my own TE keeps his lineup spot
    assert wr.window_gain(cand, _roster(), 11, play, FORMAT) == pytest.approx(9.0)


def test_a_player_on_a_bye_this_week_is_valued_on_the_weeks_he_plays():
    play = _playing(BBB=11)
    # this week's blend is 0 (bye); `weekly` carries his real level
    cand = _r("n", "TE", 0.0, team="BBB", weekly=12.0)
    assert wr.window_gain(cand, _roster(), 11, play, FORMAT) == pytest.approx(9.0)


def test_my_hurt_starter_opens_a_slot_for_the_week_he_is_out_only():
    roster = _roster()
    roster[5] = {**roster[5], "out": True}  # my starting TE is out this week
    cand = _r("n", "TE", 8, team="BBB")
    # week 0: +8 over an empty TE slot; later weeks my TE (9) is back and beats him
    assert wr.window_gain(cand, roster, 11, _playing(), FORMAT) == pytest.approx(8.0)


# ------------------------------------------------------------- the list


def test_redraft_ranks_by_gain_and_dynasty_adds_value_in_points():
    cands = [
        _r("a", "TE", 12, dyn=0),  # gain 12, no dynasty value
        _r("b", "TE", 5, dyn=900),  # no lineup gain, a dynasty asset
    ]
    args = (_roster(), 11, _playing(), FORMAT, None)
    redraft = wr.rank_targets([dict(c) for c in cands], *args, dynasty=False)
    assert [c["sid"] for c in redraft] == ["a", "b"]
    dyn = wr.rank_targets([dict(c) for c in cands], *args, dynasty=True)
    assert dyn[0]["sid"] == "b" and dyn[0]["dyn_pts"] == pytest.approx(36.0)
    assert dyn[0]["score"] == pytest.approx(36.0)


def test_zero_gain_ties_fall_back_to_dynasty_value_then_the_blend():
    cands = [
        _r("a", "TE", 3, dyn=100),
        _r("b", "TE", 3, dyn=500),
        _r("c", "TE", 6, dyn=100),
    ]
    out = wr.rank_targets(cands, _roster(), 11, _playing(), FORMAT, None, dynasty=False)
    assert [c["sid"] for c in out] == ["b", "c", "a"]


def test_every_role_boost_ships_at_zero_until_a_scorecard_moves_it():
    assert set(wr.FLAG_BOOSTS) == {"snap_jump", "starter_out", "xp_gap", "trending"}
    assert all(v == 0.0 for v in wr.FLAG_BOOSTS.values())
    c = _r("a", "TE", 12, flags={"snap_jump": True})
    out = wr.rank_targets([c], _roster(), 11, _playing(), FORMAT, None, dynasty=False)
    assert out[0]["score"] == out[0]["gain4"]


def test_a_window_past_the_end_of_the_season_counts_only_the_weeks_played():
    # week 17 + 4 weeks reaches 20; only 17 and 18 exist
    c = _r("n", "TE", 12, team="BBB")
    assert wr.window_gain(c, _roster(), 17, {}, FORMAT) == pytest.approx(6.0)
