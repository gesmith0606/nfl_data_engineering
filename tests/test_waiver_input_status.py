"""Inputs the report did not read are printed as unknown at the top, never guessed."""

from __future__ import annotations

from src import waiver_record as wr


def _kw(**kw):
    base = dict(
        week=11,
        ours_label="weekly Gold x (3h old)",
        weekly_board=True,
        guessed_pool=False,
        draft_size=216,
        dynasty_missing=False,
        news_flags=40,
        official_reports=300,
        snap_players=900,
        have_history=True,
        have_budget=True,
        bronze_max_week=10,
        recorded=[],
    )
    return {**base, **kw}


def test_stale_news_is_named_with_its_age():
    notes = wr.fallback_notes(**_kw(news_age_hours=130.0))
    assert any("news" in n and "130h old" in n for n in notes)
    assert wr.fallback_notes(**_kw(news_age_hours=20.0)) == []
    # no flags at all is a different, louder problem and keeps its own line
    assert any(
        "no sentiment flags" in n for n in wr.fallback_notes(**_kw(news_flags=0))
    )


def test_unknown_dynasty_values_are_counted_not_defaulted_to_zero():
    notes = wr.fallback_notes(**_kw(dyn_unknown=7, dyn_listed=24))
    assert any("unknown for 7 of 24" in n and "points alone" in n for n in notes)
    assert wr.fallback_notes(**_kw(dyn_unknown=0, dyn_listed=24)) == []


def test_status_block_is_always_printed_so_silence_cannot_mean_unchecked():
    clean = wr.status_block([])
    assert clean.startswith("-- Inputs --") and "every input was read" in clean
    bad = wr.status_block(["pool: other rosters unknown", "news: 130h old"])
    assert bad.startswith("-- INPUTS NOT READ")
    assert "  - pool: other rosters unknown" in bad and "guess" in bad.splitlines()[0]


def test_candidate_row_records_the_ranking_components():
    row = {
        "sid": "1",
        "name": "A",
        "pos": "TE",
        "blend": 9.0,
        "gain4": 12.0,
        "dyn_pts": 31.4,
        "score": 43.4,
        "dyn": 786,
        "dyn_known": True,
    }
    c = wr.candidate_row("targets", 3, row)
    assert (c["gain4"], c["dyn_pts"], c["score"], c["dyn_known"]) == (
        12.0,
        31.4,
        43.4,
        True,
    )
    assert c["list"] == "targets" and c["rank"] == 3
