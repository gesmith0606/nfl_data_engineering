"""Drafted while PR 1's suite was running; becomes tests/test_lineup_probability.py in PR 2."""

from __future__ import annotations

import math

import pytest

from src import lineup_setter as ls
from src.lineup_setter import (
    PlayerRow,
    lineup_deltas,
    p_bench_outscores,
    recommend,
)


def _row(pid, pos, ours, sleeper, slot=None, **kw):
    return PlayerRow(
        sleeper_id=pid, name=f"P{pid}", position=pos, team=kw.pop("team", "T"),
        ours=ours, sleeper=sleeper, slot=slot, **kw,
    )  # fmt: skip


def test_two_twelve_point_receivers_match_the_published_examples():
    """A 1 point gap ~54%, 3 points ~61%, 5 points ~69% (orchestrator brief)."""
    for gap, want in ((1, 0.54), (3, 0.61), (5, 0.69)):
        p = p_bench_outscores(
            _row("b", "WR", None, 12 + gap), _row("s", "WR", None, 12)
        )
        assert p == pytest.approx(want, abs=0.04), (gap, p)


def test_equal_players_are_a_coin_flip_and_the_better_one_is_favoured_both_ways():
    a, b = _row("a", "WR", None, 12), _row("b", "WR", None, 12)
    assert p_bench_outscores(a, b) == pytest.approx(0.5)
    hi, lo = _row("h", "RB", None, 15), _row("l", "RB", None, 9)
    assert p_bench_outscores(hi, lo) + p_bench_outscores(lo, hi) == pytest.approx(1.0)
    assert p_bench_outscores(hi, lo) > 0.5 > p_bench_outscores(lo, hi)


def test_higher_projection_means_wider_spread():
    assert _row("a", "WR", None, 20).variance > _row("b", "WR", None, 8).variance


# --- one estimate ---------------------------------------------------------------------


def test_projection_is_the_consensus_when_ours_has_no_weight(monkeypatch):
    monkeypatch.setattr(ls, "OURS_WEIGHT", 0.0)
    assert _row("a", "WR", 20.0, 10.0).projection == 10.0
    assert _row("a", "WR", None, 10.0).projection == 10.0
    assert _row("a", "WR", 7.0, None).projection == 7.0  # no consensus: ours fills in
    assert _row("a", "WR", None, None).projection is None


def test_projection_blends_ours_at_the_fitted_weight(monkeypatch):
    monkeypatch.setattr(ls, "OURS_WEIGHT", 0.25)
    assert _row("a", "WR", 20.0, 10.0).projection == pytest.approx(12.5)


# --- injuries ------------------------------------------------------------------------------


def test_questionable_players_are_discounted_by_play_probability_and_position():
    wr = _row("w", "WR", None, 20.0, status_level="QUESTIONABLE")
    assert wr.p_plays == pytest.approx(0.71)
    assert wr.expected == pytest.approx(20.0 * 0.71 * (1 - 0.22))
    qb = _row("q", "QB", None, 20.0, status_level="QUESTIONABLE")
    assert qb.expected == pytest.approx(20.0 * 0.71 * (1 - 0.08))
    assert _row(
        "r", "RB", None, 20.0, status_level="QUESTIONABLE"
    ).expected == pytest.approx(20 * 0.71 * 0.84)
    assert _row(
        "t", "TE", None, 20.0, status_level="QUESTIONABLE"
    ).expected == pytest.approx(20 * 0.71 * 0.82)
    assert _row("h", "WR", None, 20.0).expected == 20.0


def test_doubtful_is_a_sliver_and_out_or_bye_is_zero():
    assert _row(
        "d", "WR", None, 20.0, status_level="DOUBTFUL"
    ).expected == pytest.approx(20 * 0.065 * 0.78)
    assert _row("o", "WR", None, 20.0, status_level="OUT").expected == 0.0
    assert _row("b", "WR", None, 20.0, bye=True).expected == 0.0


def test_a_healthy_bench_player_is_favoured_over_a_questionable_starter_of_equal_projection():
    s = _row("s", "WR", None, 14.0, slot="WR", status_level="QUESTIONABLE")
    b = _row("b", "WR", None, 14.0)
    assert p_bench_outscores(b, s) > 0.6


def test_a_questionable_player_is_more_variable_than_a_healthy_one_of_the_same_mean():
    q = _row("q", "WR", None, 20.0, status_level="QUESTIONABLE")
    # same expected points via a lower projection, but he can score 0
    h = _row("h", "WR", None, q.expected)
    assert q.variance > h.variance


# --- the rule ----------------------------------------------------------------------------------


def test_swap_lean_and_hold_by_probability():
    rows = [
        _row("s1", "WR", None, 12.0, slot="WR"),
        _row("s2", "RB", None, 12.0, slot="RB"),
        _row("s3", "TE", None, 12.0, slot="TE"),
        _row("b1", "WR", None, 20.0),  # big gap -> SWAP
        _row("b2", "RB", None, 12.0 + 3.2),  # ~0.6 -> between lean and swap or swap
        _row("b3", "TE", None, 12.5),  # tiny gap -> hold
    ]
    verdicts = {
        d.in_player.sleeper_id: d for d in lineup_deltas(rows, swap_p=0.60, lean_p=0.55)
    }
    assert verdicts["b1"].verdict == "SWAP" and verdicts["b1"].p > 0.7
    assert "b3" not in verdicts
    assert verdicts["b2"].verdict in ("SWAP", "LEAN") and 0.55 <= verdicts["b2"].p


def test_lean_band_sits_between_the_two_thresholds():
    rows = [_row("s", "WR", None, 12.0, slot="WR"), _row("b", "WR", None, 14.5)]
    p = p_bench_outscores(rows[1], rows[0])
    d = lineup_deltas(rows, swap_p=p + 0.05, lean_p=p - 0.05)
    assert [x.verdict for x in d] == ["LEAN"]
    d = lineup_deltas(rows, swap_p=p - 0.01, lean_p=p - 0.05)
    assert [x.verdict for x in d] == ["SWAP"]
    assert lineup_deltas(rows, swap_p=p + 0.1, lean_p=p + 0.05) == []


def test_each_player_appears_once_and_the_most_probable_swap_wins():
    rows = [
        _row("s1", "WR", None, 6.0, slot="WR"),
        _row("s2", "WR", None, 10.0, slot="WR"),
        _row("b", "WR", None, 18.0),
    ]
    d = lineup_deltas(rows, swap_p=0.55, lean_p=0.52)
    assert len(d) == 1 and d[0].out_player.sleeper_id == "s1"


def test_the_legacy_two_vote_rule_is_still_available_for_the_baseline():
    rows = [_row("s", "WR", 8.0, 9.0, slot="WR"), _row("b", "WR", 12.0, 13.0)]
    assert [x.verdict for x in lineup_deltas(rows, threshold=3.0, legacy=True)] == [
        "SWAP"
    ]


def test_swap_on_an_unconfirmed_out_tag_is_check_status_not_a_swap():
    rows = [
        _row("s", "WR", None, 0.0, slot="WR", status_unconfirmed=True),
        _row("b", "WR", None, 12.0),
    ]
    assert [x.verdict for x in lineup_deltas(rows)] == ["CHECK STATUS"]


def test_recommend_applies_swaps_only_not_lean():
    rows = [
        _row("s1", "WR", None, 6.0, slot="WR"),
        _row("s2", "RB", None, 12.0, slot="RB"),
        _row("b1", "WR", None, 20.0),
        _row("b2", "RB", None, 14.0),
    ]
    rec = recommend(rows, ["WR", "RB", "BN"], ["s1", "s2"], swap_p=0.80, lean_p=0.55)
    assert rec.starters[0] == "b1"  # clear
    assert rec.starters[1] == "s2"  # only a lean: not applied
    assert {d.verdict for d in rec.deltas} == {"SWAP", "LEAN"}


def test_delta_line_prints_the_probability():
    rows = [_row("s", "WR", None, 6.0, slot="WR"), _row("b", "WR", None, 20.0)]
    line = lineup_deltas(rows)[0].line()
    assert "SWAP" in line and "%" in line and "Pb" in line and math.isfinite(len(line))


# --- one estimate: the board's published number, adjusted for scoring -----------------------------


def _board(rows):
    import pandas as pd

    return pd.DataFrame(rows)


def test_score_ours_keeps_the_published_number_and_adds_only_the_scoring_difference():
    from src.lineup_setter import score_ours

    league = {
        "rec": 1.0,
        "rec_yd": 0.1,
        "rush_yd": 0.1,
        "rec_td": 6.0,
        "pass_yd": 0.04,
        "pass_td": 6.0,
        "pass_int": -3.0,
    }
    df = _board([
        {"player_id": "a", "position": "WR", "receptions": 6.0, "receiving_yards": 80.0, "receiving_tds": 0.5,
         "published_points": 13.0, "published_format": "half_ppr"},
    ])  # fmt: skip
    rebuilt = score_ours(df, league)["projected_points"].iloc[0]
    adjusted = score_ours(df, league, adjust_published=True)["projected_points"].iloc[0]
    # half-PPR -> full PPR is +0.5 per reception = +3.0 on the published number
    assert adjusted == pytest.approx(13.0 + 3.0, abs=0.11)
    assert rebuilt == pytest.approx(6 + 8 + 3, abs=0.11)  # the rebuild ignores the 13.0


def test_adjusting_a_board_to_its_own_format_returns_the_published_number_exactly():
    from src.lineup_setter import score_ours
    from src.league_scoring import scoring_from_format

    df = _board([{"player_id": "a", "position": "RB", "receptions": 3.0, "receiving_yards": 20.0,
                  "rushing_yards": 70.0, "rushing_tds": 0.4, "published_points": 11.7, "published_format": "half_ppr"}])  # fmt: skip
    out = score_ours(df, scoring_from_format("half_ppr"), adjust_published=True)[
        "projected_points"
    ].iloc[0]
    assert out == pytest.approx(11.7, abs=0.11)


def test_rows_without_a_published_number_fall_back_to_the_rebuild():
    from src.lineup_setter import score_ours

    df = _board([
        {"player_id": "a", "position": "WR", "receptions": 4.0, "receiving_yards": 50.0, "published_points": float("nan"), "published_format": "half_ppr"},
    ])  # fmt: skip
    got = score_ours(df, {"rec": 1.0, "rec_yd": 0.1}, adjust_published=True)[
        "projected_points"
    ].iloc[0]
    assert got == pytest.approx(9.0)


def test_first_downs_are_scored_from_projected_receptions_and_rushing_yards():
    from src.league_scoring import score_with_settings, unmodeled_offense_keys

    league = {"rec_fd": 0.5, "rush_fd": 0.5}
    df = _board([
        {"position": "WR", "receptions": 10.0, "rushing_yards": 0.0, "projected_points": 0.0},
        {"position": "RB", "receptions": 0.0, "rushing_yards": 100.0, "projected_points": 0.0},
    ])  # fmt: skip
    off = score_with_settings(df, league)["projected_points"].tolist()
    on = score_with_settings(df, league, model_first_downs=True)[
        "projected_points"
    ].tolist()
    assert off == [0.0, 0.0]  # default behaviour unchanged for the waiver/draft tools
    assert on[0] == pytest.approx(10 * 0.61 * 0.5, abs=0.06)
    assert on[1] == pytest.approx(100 * 0.052 * 0.5, abs=0.06)
    assert "rec_fd" in unmodeled_offense_keys(
        league
    ) and "rec_fd" not in unmodeled_offense_keys(league, model_first_downs=True)


# --- Questionable starters: who can still replace him once his status is known ---------------------


def _at(hour):
    import datetime as dt

    return dt.datetime(2026, 11, 15, hour, 0, tzinfo=ls.ET)


def test_a_late_questionable_starter_keeps_a_late_fallback_and_an_early_bench_does_not_count():
    s = _row(
        "s", "WR", None, 14.0, slot="WR", status_level="QUESTIONABLE", kickoff=_at(20)
    )
    late = _row("late", "WR", None, 9.0, kickoff=_at(20))
    early = _row("early", "WR", None, 12.0, kickoff=_at(13))
    notes = ls.questionable_fallbacks([s, late, early])
    assert (
        len(notes) == 1
        and "Fallback still open: Plate" in notes[0]
        and "Pearly" not in notes[0]
    )


def test_no_late_fallback_is_said_out_loud():
    s = _row(
        "s", "WR", None, 14.0, slot="WR", status_level="QUESTIONABLE", kickoff=_at(20)
    )
    notes = ls.questionable_fallbacks(
        [s, _row("early", "WR", None, 12.0, kickoff=_at(13))]
    )
    assert "NO LATE FALLBACK" in notes[0]


def test_healthy_dead_and_locked_starters_get_no_fallback_note():
    healthy = _row("h", "WR", None, 14.0, slot="WR", kickoff=_at(13))
    locked = _row(
        "l",
        "WR",
        None,
        14.0,
        slot="WR",
        status_level="QUESTIONABLE",
        kickoff=_at(13),
        locked=True,
    )
    assert (
        ls.questionable_fallbacks(
            [healthy, locked, _row("b", "WR", None, 9.0, kickoff=_at(20))]
        )
        == []
    )


# --- the ESPN writer asks for more than the report does ---------------------------------------------


def test_the_writer_files_a_swap_only_at_the_write_probability():
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "sl_write_p",
        Path(__file__).resolve().parent.parent / "scripts" / "set_lineups.py",
    )
    sl = importlib.util.module_from_spec(spec)
    sys.modules["sl_write_p"] = sl
    spec.loader.exec_module(sl)
    assert sl.WRITE_P == 0.60 and ls.SWAP_P < sl.WRITE_P

    def entry(pid, name, slot):
        return {
            "playerId": pid,
            "lineupSlotId": slot,
            "playerPoolEntry": {
                "id": pid,
                "player": {"fullName": name, "defaultPositionId": 3},
            },
        }

    payload = {
        "teams": [
            {
                "id": 1,
                "roster": {
                    "entries": [entry(1, "Starter One", 4), entry(2, "Bench Two", 20)]
                },
            }
        ]
    }
    out_p, in_p = _row("1", "WR", None, 8.0, slot="WR"), _row("2", "WR", None, 9.5)
    out_p.name, in_p.name = "Starter One", "Bench Two"
    weak = ls.Delta("SWAP", "WR", out_p, in_p, p=0.55, gap=1.5)
    strong = ls.Delta("SWAP", "WR", out_p, in_p, p=0.70, gap=4.0)
    kw = dict(
        preset={"league_id": "1"},
        espn_live={"team_id": 1, "payload": payload},
        season=2026,
        week=11,
        apply_changes=False,
    )
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        sl.espn_write(deltas=[weak], **kw)
    assert "not filing (SWAP)" in buf.getvalue() and "DRY RUN" not in buf.getvalue()
    buf = io.StringIO()
    with redirect_stdout(buf):
        sl.espn_write(deltas=[strong], **kw)
    assert "DRY RUN" in buf.getvalue()


def test_sleeper_first_downs_can_be_replaced_by_documented_rates():
    stats = {
        "rec": 6.0,
        "rec_yd": 60.0,
        "rec_fd": 8.0,
    }  # Sleeper: 1.33 first downs per catch
    league = {"rec": 1.0, "rec_yd": 0.1, "rec_fd": 0.5}
    asis = ls.score_sleeper_stats(stats, league, "WR")
    rates = ls.score_sleeper_stats(stats, league, "WR", fd_rates=True)
    assert asis == pytest.approx(6 + 6 + 4.0)
    assert rates == pytest.approx(6 + 6 + 6 * 0.61 * 0.5, abs=0.06)
    assert ls.CONSENSUS_FD_FROM_RATES is False  # not adopted: no lineup-points evidence
