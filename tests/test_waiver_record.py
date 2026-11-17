"""The waiver report leaves a machine-readable record, so past advice can be re-scored."""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pytest

from src import waiver_record as wr


def _row(**kw):
    base = {
        "sid": "1",
        "name": "A B",
        "pos": "WR",
        "team": "KC",
        "ours": 8.0,
        "slpr": 10.0,
        "blend": 9.0,
        "last": 4.0,
        "adds": 12000,
        "dyn": 0,
        "age": 24,
        "snap": (61, 12),
        "inj": "",
        "news": "",
        "verdict": "STARTS",
        "bid": (3, "no rival is both thin here and able to spend"),
        "demand": "unclaimed",
        "blocked_by": [],
        "blocked_returning": False,
    }
    return {**base, **kw}


def test_candidate_row_flattens_bid_and_snap_and_names_the_basis():
    c = wr.candidate_row("WR", 2, _row())
    assert c["list"] == "WR" and c["rank"] == 2
    assert c["bid"] == 3 and "rival" in c["bid_reason"]
    assert (c["snap_pct"], c["snap_delta"]) == (61, 12)
    assert c["blend_basis"] == "both"


def test_blend_basis_says_when_one_source_is_missing():
    # a missing projection of ours silently leaves Sleeper alone -- the record
    # has to say so, or the scorecard cannot tell a consensus row from a guess
    assert wr.candidate_row("WR", 1, _row(ours=None))["blend_basis"] == "sleeper_only"
    assert wr.candidate_row("WR", 1, _row(slpr=None))["blend_basis"] == "ours_only"
    zero = wr.candidate_row("WR", 1, _row(slpr=0.0, ours=7.0))
    assert zero["blend_basis"] == "both" and zero["sleeper_zero"] is True


def test_no_bid_is_none_not_zero():
    c = wr.candidate_row("QB", 1, _row(bid=None))
    assert c["bid"] is None and c["bid_reason"] is None


def test_record_is_json_safe_with_numpy_and_nan():
    rec = wr.build_record(
        league="mantis",
        platform="sleeper",
        season=2026,
        week=11,
        title="t",
        generated_at="2026-11-17T00:00:00+00:00",
        inputs={
            "board": {
                "kind": "weekly",
                "file": "x.parquet",
                "age_hours": np.float64(3.2),
            }
        },
        candidates=[
            wr.candidate_row(
                "WR", 1, _row(blend=np.float64("nan"), ours=np.float32(8.5))
            )
        ],
        fallbacks=["pool guessed from ADP"],
    )
    text = json.dumps(rec)  # must not raise
    back = json.loads(text)
    assert back["candidates"][0]["blend"] is None
    assert back["candidates"][0]["ours"] == 8.5
    assert back["schema"] == wr.SCHEMA and back["fallbacks"] == [
        "pool guessed from ADP"
    ]
    assert not any(
        isinstance(v, float) and math.isnan(v) for v in back["candidates"][0].values()
    )


def test_write_record_is_partitioned_and_never_overwrites(tmp_path: Path):
    rec = wr.build_record(
        league="mantis",
        platform="sleeper",
        season=2026,
        week=11,
        title="t",
        generated_at="2026-11-17T01:02:03+00:00",
        inputs={},
        candidates=[],
        fallbacks=[],
    )
    p1 = wr.write_record(rec, tmp_path)
    assert p1.parent == tmp_path / "mantis" / "season=2026" / "week=11"
    assert p1.name == "report_20261117_010203.json"
    p2 = wr.write_record({**rec, "generated_at": "2026-11-17T01:02:04+00:00"}, tmp_path)
    assert p1 != p2 and p1.exists() and p2.exists()
    assert json.loads(p1.read_text())["league"] == "mantis"


def test_latest_record_picks_the_newest_for_the_week(tmp_path: Path):
    mk = lambda ts, wk=11: wr.write_record(  # noqa: E731
        wr.build_record(
            league="mantis",
            platform="sleeper",
            season=2026,
            week=wk,
            title="t",
            generated_at=ts,
            inputs={},
            candidates=[],
            fallbacks=[],
        ),
        tmp_path,
    )
    mk("2026-11-17T01:00:00+00:00")
    newest = mk("2026-11-18T01:00:00+00:00")
    mk("2026-11-30T01:00:00+00:00", wk=12)
    assert wr.latest_record("mantis", 2026, 11, tmp_path) == newest
    assert wr.latest_record("mantis", 2026, 5, tmp_path) is None


def test_file_freshness_reports_age_or_absence(tmp_path: Path):
    f = tmp_path / "projections_half_ppr_20261110_203619.parquet"
    f.write_bytes(b"x")
    three_hours_later = dt.datetime(2026, 11, 10, 23, 36, 19, tzinfo=dt.timezone.utc)
    got = wr.file_freshness(f, now=three_hours_later.timestamp())
    assert got["stamp"] == "20261110_203619" and got["age_hours"] == 3.0
    # no stamp in the name: fall back to the file's own mtime
    plain = tmp_path / "sleeper_players.json"
    plain.write_text("{}")
    assert wr.file_freshness(plain)["stamp"] is None
    assert wr.file_freshness(plain)["age_hours"] < 1
    assert wr.file_freshness(tmp_path / "nope.parquet") == {
        "file": None,
        "stamp": None,
        "age_hours": None,
    }


def _clean_kwargs(**kw):
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


def test_fallback_notes_are_empty_when_every_input_was_read():
    assert wr.fallback_notes(**_clean_kwargs()) == []


def test_fallback_notes_name_each_silent_substitution():
    notes = wr.fallback_notes(
        **_clean_kwargs(
            weekly_board=False,
            ours_label="preseason pace p.parquet (season/17)",
            guessed_pool=True,
            dynasty_missing=True,
            news_flags=0,
            official_reports=0,
            snap_players=0,
            have_history=False,
            bronze_max_week=8,
            recorded=[
                {"sleeper_zero": True, "blend_basis": "both"},
                {"sleeper_zero": False, "blend_basis": "sleeper_only"},
            ],
        )
    )
    joined = "\n".join(notes)
    for needle in (
        "preseason pace",
        "guessed from ADP",
        "DYN is 0",
        "no sentiment",
        "Sleeper tags only",
        "SNAP column empty",
        "no bids computed",
        "stops at week 8",
        "of 0 (blend halved)",
        "single projection source",
    ):
        assert needle in joined, needle


def test_candidate_row_carries_the_clearing_models_reading_of_the_bid():
    from src import clearing_model as cm

    m = cm.ClearingModel([cm.Obs(3, "WR-top", (40,)), cm.Obs(3, "WR-top", ())])
    adv = m.recommend("WR-top", value=50, budget_left=800)
    c = wr.candidate_row(
        "targets", 1, _row(advice=adv, tier="WR-top", rank=2, price80=17)
    )
    assert c["tier"] == "WR-top" and c["pos_rank"] == 2 and c["bid_price80"] == 17
    assert c["bid_p_win"] == pytest.approx(round(adv.p_win, 3))
    assert c["bid_ceiling"] == 50 and 0 < c["p_contested"] < 1
    # a row the clearing model never priced (ESPN/Yahoo) simply has none
    assert wr.candidate_row("WR", 1, _row())["bid_p_win"] is None
