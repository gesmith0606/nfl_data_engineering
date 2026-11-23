"""scripts/snapshot_gameday_inputs.py -- dated copies of what Sleeper said, and the readers."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from scripts import snapshot_gameday_inputs as snap

PROJ = {
    "4046": {"stats": {"pass_yd": 250.0, "pass_td": 1.8, "pts_ppr": 19.1}},
    "9488": {"stats": {"rec": 6.0, "rec_yd": 71.0}},
    "9999": {"stats": {}},  # nothing projected: not worth a row
}
REGISTRY = {
    "4046": {"position": "QB", "team": "SF", "full_name": "Brock Purdy", "injury_status": "Questionable",
             "injury_body_part": "Toe", "practice_participation": "Limited", "news_updated": 1762600000000},
    "9488": {"position": "WR", "team": "HOU", "full_name": "Tank Dell", "injury_status": None},
    "HOU": {"position": "DEF", "team": "HOU", "full_name": None},
    "555": {"position": "LB", "team": "HOU", "full_name": "A Linebacker"},  # not fantasy-relevant
    "777": {"position": "WR", "team": None, "injury_status": None},  # unsigned, untagged
}  # fmt: skip
NOW = dt.datetime(2026, 11, 8, 12, 4, 34)


def _run(tmp_path, monkeypatch, proj=PROJ, registry=REGISTRY, age_h=0.0):
    monkeypatch.setattr(
        snap.sleeper_http, "fetch_sleeper_json", lambda url, *a, **k: proj
    )
    monkeypatch.setattr(snap, "load_sleeper_players", lambda **k: registry)
    monkeypatch.setattr(snap, "_registry_age_hours", lambda: age_h)
    return snap.snapshot(2026, 9, root=tmp_path, now=NOW)


def test_writes_dated_projection_and_status_snapshots(tmp_path, monkeypatch):
    paths = _run(tmp_path, monkeypatch)
    assert sorted(p.name for p in paths) == [
        "sleeper_projections_20261108_120434.parquet",
        "sleeper_status_20261108_120434.parquet",
    ]
    assert all(p.parent == tmp_path / "season=2026" / "week=09" for p in paths)


def test_projection_rows_keep_the_stat_dict_and_drop_empty_ones(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    got = snap.read_projections(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 13, 0))
    assert set(got) == {"4046", "9488"}
    assert got["4046"]["pass_yd"] == 250.0


def test_status_keeps_the_tags_that_the_registry_file_loses(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    got = snap.read_status(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 13, 0))
    assert got["4046"]["injury_status"] == "Questionable"
    assert got["4046"]["practice_participation"] == "Limited"
    assert "injury_status" not in got["9488"]  # healthy: nothing recorded
    df = pd.read_parquet(next(tmp_path.rglob("sleeper_status_*.parquet")))
    assert set(df["sleeper_id"]) == {
        "4046",
        "9488",
        "HOU",
    }  # no LB, no unsigned-untagged


def test_reader_never_returns_a_snapshot_taken_after_the_cutoff(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    assert (
        snap.read_projections(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 12, 0))
        is None
    )
    assert snap.read_status(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 12, 0)) is None
    assert snap.read_projections(tmp_path, 2026, 10, dt.datetime(2026, 12, 1)) is None


def test_reader_takes_the_newest_snapshot_before_the_cutoff(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    monkeypatch.setattr(
        snap.sleeper_http,
        "fetch_sleeper_json",
        lambda *a, **k: {"4046": {"stats": {"pass_yd": 300.0}}},
    )
    snap.snapshot(2026, 9, root=tmp_path, now=dt.datetime(2026, 11, 8, 16, 50, 0))
    early = snap.read_projections(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 13, 0))
    late = snap.read_projections(tmp_path, 2026, 9, dt.datetime(2026, 11, 8, 17, 0))
    assert early["4046"]["pass_yd"] == 250.0 and late["4046"]["pass_yd"] == 300.0


def test_fails_open_and_says_so_when_sleeper_returns_nothing(
    tmp_path, monkeypatch, capsys
):
    assert _run(tmp_path, monkeypatch, proj={}, registry={}) == []
    out = capsys.readouterr().out
    assert "NO SNAPSHOT" in out and not list(tmp_path.rglob("*.parquet"))


def test_a_stale_registry_cache_is_not_filed_under_todays_timestamp(
    tmp_path, monkeypatch, capsys
):
    paths = _run(tmp_path, monkeypatch, age_h=30.0)
    assert [p.name.split("_20")[0] for p in paths] == ["sleeper_projections"]
    assert "30h old" in capsys.readouterr().out


def test_adp_only_rows_are_dropped_but_projected_rows_kept():
    raw = {
        "1": {"stats": {"adp_dd_ppr": 1000.0}},
        "2": {"stats": {"adp_dd_ppr": 50.0, "pts_ppr": 12.0}},
    }
    assert list(snap.projections_frame(raw)["sleeper_player_id"]) == ["2"]


def _main(tmp_path, monkeypatch, proj, registry, resolved, argv=()):
    from scripts import resolve_pipeline_week as rpw

    monkeypatch.setattr(snap.sleeper_http, "fetch_sleeper_json", lambda *a, **k: proj)
    monkeypatch.setattr(snap, "load_sleeper_players", lambda **k: registry)
    monkeypatch.setattr(snap, "_registry_age_hours", lambda: 0.0)
    monkeypatch.setattr(rpw, "resolve_target_week", lambda today: resolved)
    return snap.main(["--root", str(tmp_path), *argv])


def test_main_exits_nonzero_when_nothing_captured(tmp_path, monkeypatch):
    rc = _main(tmp_path, monkeypatch, {}, {}, (2026, 12, "schedule"))
    assert rc == 1 and not list(tmp_path.rglob("*.parquet"))


def test_main_exits_nonzero_when_only_one_file_written(tmp_path, monkeypatch):
    assert _main(tmp_path, monkeypatch, PROJ, {}, (2026, 12, "schedule")) == 1


def test_main_uses_resolved_week_and_padded_layout(tmp_path, monkeypatch):
    assert _main(tmp_path, monkeypatch, PROJ, REGISTRY, (2026, 12, "schedule")) == 0
    assert len(list((tmp_path / "season=2026" / "week=12").glob("*.parquet"))) == 2


def test_main_offseason_skips_cleanly_but_explicit_week_overrides(
    tmp_path, monkeypatch, capsys
):
    final = (2026, 18, "schedule-final")
    assert _main(tmp_path, monkeypatch, PROJ, REGISTRY, final) == 0
    assert "OFFSEASON" in capsys.readouterr().out
    assert not list(tmp_path.rglob("*.parquet"))
    argv = ["--season", "2026", "--week", "5"]
    assert _main(tmp_path, monkeypatch, PROJ, REGISTRY, final, argv) == 0
    assert (tmp_path / "season=2026" / "week=05").is_dir()


def test_main_writes_ci_outputs_and_summary(tmp_path, monkeypatch):
    out, summ = tmp_path / "out.txt", tmp_path / "summ.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    _main(tmp_path, monkeypatch, PROJ, REGISTRY, (2026, 12, "schedule"))
    assert "week=12" in out.read_text() and "offseason=false" in out.read_text()
    assert "rows" in summ.read_text() and "bytes" in summ.read_text()
