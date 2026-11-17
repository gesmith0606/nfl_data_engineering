"""Website lineup builder: week, snapshot, availability, confidence, degraded flag.

2026-11 diagnosis of ``src/lineup_builder.py`` (week 10): it ignored the requested week
(the depth chart was one rolling snapshot, ``week`` synthesized as 1), kept the newest ROW
per player across ~289 daily snapshots instead of the newest snapshot, picked files by
mtime, listed ruled-out players and whole bye teams as starters, and gave every starter
confidence 0.70 (no snap data: it read the unplayed week's own counts). All offline.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import lineup_builder as lb  # noqa: E402


# --- fixtures -----------------------------------------------------------------------------------


def _dc(rows, dt_value="2026-11-10T15:00:00Z"):
    """New-schema depth chart rows: (team, name, gsis, pos_abb, pos_rank[, dt])."""
    out = []
    for r in rows:
        team, name, gsis, pos, rank = r[:5]
        out.append(
            {"dt": r[5] if len(r) > 5 else dt_value, "team": team, "player_name": name,
             "gsis_id": gsis, "pos_abb": pos, "pos_rank": rank}
        )  # fmt: skip
    return pd.DataFrame(out)


def _schedule(week, games, gameday="2026-11-15", gametime="13:00"):
    return pd.DataFrame(
        [{"week": week, "home_team": h, "away_team": a, "gameday": gameday, "gametime": gametime} for h, a in games]
    )  # fmt: skip


KC = [
    ("KC", "Pat Mahomes", "g-qb", "QB", 1),
    ("KC", "Backup QB", "g-qb2", "QB", 2),
    ("KC", "Runner One", "g-rb1", "RB", 1),
    ("KC", "Runner Two", "g-rb2", "RB", 2),
    ("KC", "Runner Three", "g-rb3", "RB", 3),
    ("KC", "Wide A", "g-wr1", "WR", 1),
    ("KC", "Wide B", "g-wr2", "WR", 2),
    ("KC", "Wide C", "g-wr3", "WR", 3),
    ("KC", "Wide D", "g-wr4", "WR", 4),
    ("KC", "Tight End", "g-te", "TE", 1),
]


@pytest.fixture()
def disk(tmp_path, monkeypatch):
    """Point the builder at an empty data root; tests drop files in as needed."""
    monkeypatch.setattr(lb, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(lb, "_load_snap_counts", lambda season, week: pd.DataFrame())
    return tmp_path


def _write(path, df):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def _starters(
    week=11, team="KC", availability=None, snaps=None, depth=None, projections=None
):
    """Run get_team_starters with the loaders stubbed."""
    from unittest.mock import patch

    av = availability or lb._Availability(set(), {}, [])
    with patch.object(lb, "_load_depth_charts", return_value=lb._normalize_depth_chart_schema(depth if depth is not None else _dc(KC))), \
         patch.object(lb, "_availability", return_value=av), \
         patch.object(lb, "_trailing_snap_share", return_value=snaps or {}):  # fmt: skip
        return lb.get_team_starters(2026, week, team=team, projections_df=projections)


def _names(df, starters=True):
    return list(df[df["is_starter"] == starters]["player_name"])


# --- files are chosen by the timestamp in their name -------------------------------------------------


def test_latest_file_goes_by_filename_not_mtime(tmp_path):
    old = tmp_path / "depth_charts_20261103_202401.parquet"
    new = tmp_path / "depth_charts_20261110_211940.parquet"
    for p in (old, new):
        p.write_bytes(b"x")
    os.utime(new, (1, 1))  # a checkout rewrote the newer file's mtime
    os.utime(old, (2_000_000_000, 2_000_000_000))
    assert lb._latest_file([old, new]) == new
    assert lb._latest_file([]) is None


def test_the_loaders_use_it_and_projections_skip_derived_boards(disk):
    for name, rows in (
        ("depth_charts_20261103_202401.parquet", ["old"]),
        ("depth_charts_20261110_211940.parquet", ["new"]),
    ):
        d = _dc([("KC", rows[0], "g1", "QB", 1)])
        _write(disk / "bronze" / "depth_charts" / "season=2026" / name, d)
    os.utime(
        disk / "bronze/depth_charts/season=2026/depth_charts_20261110_211940.parquet",
        (1, 1),
    )
    assert list(lb._load_depth_charts(2026)["full_name"]) == ["new"]

    base = disk / "gold" / "projections" / "season=2026" / "week=11"
    _write(
        base / "projections_half_ppr_20261110_100000.parquet",
        pd.DataFrame({"projected_points": [1.0]}),
    )
    _write(
        base / "projections_half_ppr_20261112_100000.parquet",
        pd.DataFrame({"projected_points": [2.0]}),
    )
    _write(
        base / "projections_derived_20261113_100000.parquet",
        pd.DataFrame({"projected_points": [99.0]}),
    )
    assert lb._load_projections(2026, 11)["projected_points"].iloc[0] == 2.0


# --- one snapshot, as of the week --------------------------------------------------------------------


def test_only_the_chosen_snapshot_survives_so_a_cut_player_is_not_a_starter():
    d = _dc([("KC", "Cut Runner", "g-cut", "RB", 1, "2026-10-01T10:00:00Z"),
             ("KC", "Runner One", "g-rb1", "RB", 1, "2026-11-10T10:00:00Z")])  # fmt: skip
    out = lb._normalize_depth_chart_schema(d)
    assert list(out["full_name"]) == [
        "Runner One"
    ]  # the old code kept both (newest row per player)


def test_each_week_reads_the_snapshot_as_of_its_first_kickoff():
    d = _dc([("KC", "Early RB", "g-1", "RB", 1, "2026-10-01T10:00:00Z"),
             ("KC", "Late RB", "g-2", "RB", 1, "2026-11-10T10:00:00Z")])  # fmt: skip
    wk5 = lb._normalize_depth_chart_schema(
        d, as_of=dt.datetime(2026, 10, 8, tzinfo=dt.timezone.utc)
    )
    wk11 = lb._normalize_depth_chart_schema(
        d, as_of=dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc)
    )
    assert list(wk5["full_name"]) == ["Early RB"] and list(wk11["full_name"]) == [
        "Late RB"
    ]
    assert wk5.attrs["snapshot"]["predates_data"] is False


def test_a_week_that_predates_every_snapshot_uses_the_earliest_and_says_so():
    d = _dc([("KC", "Only RB", "g-1", "RB", 1, "2026-10-01T10:00:00Z")])
    out = lb._normalize_depth_chart_schema(
        d, as_of=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc)
    )
    assert (
        list(out["full_name"]) == ["Only RB"]
        and out.attrs["snapshot"]["predates_data"] is True
    )


def test_week_kickoffs_are_utc_instants_of_the_weeks_games():
    s = _schedule(11, [("KC", "BUF")], gameday="2026-11-15", gametime="13:00")
    (ko,) = lb._week_kickoffs(s, 11)
    assert ko == dt.datetime(
        2026, 11, 15, 18, 0, tzinfo=dt.timezone.utc
    )  # 13:00 ET (EST)
    assert lb._week_kickoffs(s, 12) == []


def test_load_depth_charts_applies_the_weeks_cutoff_from_the_schedule(disk):
    d = _dc([("KC", "Early RB", "g-1", "RB", 1, "2026-10-01T10:00:00Z"),
             ("KC", "Late RB", "g-2", "RB", 1, "2026-11-10T10:00:00Z")])  # fmt: skip
    _write(
        disk / "bronze/depth_charts/season=2026/depth_charts_20261110_211940.parquet", d
    )
    _write(
        disk / "bronze/schedules/season=2026/schedules_20260901_000000.parquet",
        _schedule(5, [("KC", "BUF")], "2026-10-11"),
    )
    _write(disk / "bronze/schedules/season=2026/schedules_20260901_000000.parquet", pd.concat([
        _schedule(5, [("KC", "BUF")], "2026-10-11"), _schedule(11, [("KC", "BUF")], "2026-11-15")]))  # fmt: skip
    assert list(lb._load_depth_charts(2026, 5)["full_name"]) == ["Early RB"]
    assert list(lb._load_depth_charts(2026, 11)["full_name"]) == ["Late RB"]


# --- availability: next man up, bye teams -------------------------------------------------------------


def test_a_ruled_out_starter_is_replaced_by_the_next_man_up_and_kept_as_a_non_starter():
    av = lb._Availability(set(), {"g-rb1": "Out", "g-wr2": "Doubtful"}, [])
    out = _starters(availability=av)
    assert (
        "Runner One" not in _names(out)
        and "Runner Two" in _names(out)
        and "Runner Three" in _names(out)
    )
    assert "Wide B" not in _names(out) and "Wide D" in _names(
        out
    )  # three WR slots, next man up
    sidelined = out[~out["is_starter"]].set_index("player_name")
    assert (
        sidelined.loc["Runner One", "injury_status"] == "Out"
        and sidelined.loc["Wide B", "injury_status"] == "Doubtful"
    )
    assert (sidelined["starter_confidence"] == 0.0).all()
    assert out[out["is_starter"]].groupby("position_group").size().to_dict() == {
        "QB": 1,
        "RB": 2,
        "TE": 1,
        "WR": 3,
    }


def test_ir_and_suspended_are_unavailable_too():
    av = lb._Availability(set(), {"g-qb": "IR", "g-te": "Suspended"}, [])
    out = _starters(availability=av)
    assert _names(out)[0] == "Backup QB" and "Tight End" not in _names(out)


def test_a_team_on_bye_has_no_starters_and_its_players_say_bye():
    av = lb._Availability({"KC"}, {}, [])
    out = _starters(availability=av)
    assert _names(out) == [] and not out.empty
    assert (
        set(out["injury_status"]) == {"BYE"}
        and (out["starter_confidence"] == 0.0).all()
    )


def test_is_bye_uses_canonical_codes():
    av = lb._Availability({lb._canonical_team("LA")}, {}, [])
    assert av.is_bye("LAR") and av.is_bye("LA") and not av.is_bye("KC")
    assert not lb._Availability(None, {}, []).is_bye("KC")  # no schedule: no claim


def test_availability_reads_bye_teams_from_the_schedule_and_status_from_both_sources(
    disk,
):
    _write(
        disk / "bronze/schedules/season=2026/schedules_20260901_000000.parquet",
        _schedule(11, [("KC", "BUF"), ("SF", "SEA")]),
    )
    inj = pd.DataFrame(
        {
            "week": [11, 11, 10],
            "gsis_id": ["g-official", "g-q", "g-old"],
            "report_status": ["Out", "Questionable", "Out"],
        }
    )
    _write(
        disk / "bronze/players/injuries/season=2026/injuries_20261113_120000.parquet",
        inj,
    )
    proj = pd.DataFrame(
        {
            "player_id": ["g-proj", "g-official", "g-fine"],
            "injury_status": ["Out", "Active", "Active"],
        }
    )
    av = lb._availability(2026, 11, ["KC", "BUF", "SF", "SEA", "DAL"], proj)
    assert av.bye_teams == {"DAL"}
    assert av.status == {
        "g-proj": "Out",
        "g-official": "Out",
        "g-q": "Questionable",
    }  # week 10's report ignored
    assert av.notes == []


def test_availability_degrades_loudly_when_it_has_nothing(disk):
    av = lb._availability(2026, 11, ["KC"], pd.DataFrame())
    assert av.bye_teams is None
    assert any("no schedule" in n for n in av.notes) and any(
        "no injury report" in n for n in av.notes
    )


# --- confidence is a signal, not a constant ----------------------------------------------------------------


def test_confidence_follows_recent_usage_and_the_chance_he_plays():
    snaps = {
        ("KC", "Runner One"): 0.9,
        ("KC", "Runner Two"): 0.3,
        ("KC", "Wide A"): 0.9,
        ("KC", "Wide B"): 0.9,
    }
    av = lb._Availability(set(), {"g-wr2": "Questionable"}, [])
    out = _starters(availability=av, snaps=snaps).set_index("player_name")
    assert (
        out.loc["Runner One", "starter_confidence"]
        > out.loc["Runner Two", "starter_confidence"]
    )
    assert out.loc["Wide B", "starter_confidence"] == pytest.approx(
        out.loc["Wide A", "starter_confidence"] * 0.71, abs=0.011
    )
    assert (
        out["starter_confidence"].nunique() > 2
    )  # was a constant 0.70 for all 625 rows
    assert out.loc["Wide B", "injury_status"] == "Questionable" and bool(
        out.loc["Wide B", "is_starter"]
    )


def test_confidence_constants_match_the_lineup_setters():
    from src import lineup_setter as ls

    assert (
        lb._P_PLAYS["questionable"] == ls.P_PLAYS_QUESTIONABLE
        and lb._P_PLAYS["doubtful"] == ls.P_PLAYS_DOUBTFUL
    )


def test_trailing_snap_share_uses_only_prior_weeks(monkeypatch):
    calls = []

    def fake(season, week):
        calls.append(week)
        return pd.DataFrame(
            {
                "team": ["KC"],
                "player": ["Runner One"],
                "offense_pct": [float(week * 10)],
            }
        )

    monkeypatch.setattr(lb, "_load_snap_counts", fake)
    share = lb._trailing_snap_share(2026, 11)
    assert calls == [8, 9, 10] and share[("KC", "Runner One")] == pytest.approx(90.0)
    calls.clear()
    assert (
        lb._trailing_snap_share(2026, 1) == {} and calls == []
    )  # week 1 has no prior weeks


# --- the degraded flag -------------------------------------------------------------------------------------------


def test_a_predated_snapshot_and_missing_data_are_listed_as_degraded_reasons():
    from unittest.mock import patch

    dc = lb._normalize_depth_chart_schema(
        _dc([("KC", "Only RB", "g-1", "RB", 1, "2026-10-01T10:00:00Z")]),
        as_of=dt.datetime(2026, 9, 10, tzinfo=dt.timezone.utc),
    )
    av = lb._Availability(
        None, {}, ["no schedule for 2026 week 3: bye weeks not applied"]
    )
    with patch.object(lb, "_load_depth_charts", return_value=dc), patch.object(
        lb, "_availability", return_value=av
    ), patch.object(lb, "_trailing_snap_share", return_value={}):
        out = lb.get_team_starters(2026, 3, team="KC")
    reasons = out.attrs["degraded_reasons"]
    assert any("no snapshot at or before week 3" in r for r in reasons) and any(
        "no schedule" in r for r in reasons
    )


def test_a_stale_snapshot_is_degraded_but_a_fresh_one_is_not():
    from unittest.mock import patch

    def run(snap_dt):
        dc = lb._normalize_depth_chart_schema(
            _dc([("KC", "RB", "g-1", "RB", 1, snap_dt)]),
            as_of=dt.datetime(2026, 11, 12, tzinfo=dt.timezone.utc),
        )
        with patch.object(lb, "_load_depth_charts", return_value=dc), patch.object(
            lb, "_availability", return_value=lb._Availability(set(), {}, [])
        ), patch.object(lb, "_trailing_snap_share", return_value={}):
            return lb.get_team_starters(2026, 11, team="KC").attrs["degraded_reasons"]

    assert run("2026-11-10T10:00:00Z") == []
    assert any("days older than week 11" in r for r in run("2026-10-01T10:00:00Z"))


def test_the_projection_merge_keeps_the_degraded_reasons_and_the_builders_status():
    from unittest.mock import patch

    av = lb._Availability(
        set(),
        {"g-rb1": "Out"},
        [
            "no injury report or projection statuses for week 11: Out/Questionable not applied"
        ],
    )
    proj = pd.DataFrame(
        {
            "player_id": ["g-qb"],
            "recent_team": ["KC"],
            "player_name": ["Pat Mahomes"],
            "projected_points": [21.0],
            "projected_floor": [12.0],
            "projected_ceiling": [30.0],
        }
    )
    with patch.object(
        lb, "_load_depth_charts", return_value=lb._normalize_depth_chart_schema(_dc(KC))
    ), patch.object(lb, "_availability", return_value=av), patch.object(
        lb, "_trailing_snap_share", return_value={}
    ):
        out = lb.get_team_lineup_with_projections(2026, 11, "KC", projections_df=proj)
    assert (
        out.attrs["degraded_reasons"]
        and out.set_index("player_name").loc["Runner One", "injury_status"] == "Out"
    )
    assert out.set_index("player_name").loc["Pat Mahomes", "projected_points"] == 21.0


# --- the router -------------------------------------------------------------------------------------------------------


def _router(monkeypatch, frame):
    """Call the real endpoint function with the builder stubbed to ``frame``."""
    from web.api.routers import lineups as router

    monkeypatch.setattr(lb, "get_team_lineup_with_projections", lambda **kw: frame)
    monkeypatch.setattr(lb, "get_team_starters", lambda **kw: frame)
    monkeypatch.setattr(
        router.projection_service, "get_projections", lambda **kw: pd.DataFrame()
    )
    monkeypatch.setattr(
        "graph_correlation.load_latest_correlations",
        lambda: pd.DataFrame(),
        raising=False,
    )
    return router.get_lineups(season=2026, week=11, team="KC", scoring="half_ppr")


def _frame(degraded):
    df = pd.DataFrame(
        [
            dict(team="KC", position="QB", position_group="QB", depth_position="QB", player_name="Pat Mahomes", player_id="g-qb", depth_rank=1, snap_pct=None, is_starter=True, starter_confidence=0.7, injury_status=None, field_position="qb", side="offense", projected_points=20.0, projected_floor=10.0, projected_ceiling=30.0),
            dict(team="KC", position="RB", position_group="RB", depth_position="RB", player_name="Out Runner", player_id="g-rb", depth_rank=2, snap_pct=None, is_starter=False, starter_confidence=0.0, injury_status="Out", field_position="rb_2", side="offense", projected_points=15.0, projected_floor=5.0, projected_ceiling=25.0),
        ]
    )  # fmt: skip
    df.attrs["degraded_reasons"] = degraded
    return df


def test_the_endpoint_flags_degraded_when_the_builder_fell_back_and_not_otherwise(
    monkeypatch,
):
    assert (
        _router(
            monkeypatch, _frame(["depth chart is 20 days older than week 11"])
        ).degraded
        is True
    )
    assert _router(monkeypatch, _frame([])).degraded is False


def test_the_endpoint_excludes_non_starters_from_the_team_total_and_reports_their_status(
    monkeypatch,
):
    resp = _router(monkeypatch, _frame([]))
    assert resp.lineups[0].team_projected_total == 20.0  # not 35.0
    flat = {p.player_name: p for p in resp.lineup}
    assert (
        flat["Out Runner"].injury_status == "Out"
        and flat["Out Runner"].is_starter is False
    )
    assert flat["Pat Mahomes"].injury_status is None
