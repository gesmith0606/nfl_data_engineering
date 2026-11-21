"""Tests for scripts/resolve_pipeline_week.py — the weekly cron's target week.

Regression anchor: on 2026-09-08 the calendar rule resolved to 2025 week 18
and the pipeline published a stale partition instead of 2026 Week 1.
"""

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "resolve_pipeline_week",
    Path(__file__).resolve().parent.parent / "scripts" / "resolve_pipeline_week.py",
)
rpw = importlib.util.module_from_spec(_SPEC)
sys.modules["resolve_pipeline_week"] = rpw
_SPEC.loader.exec_module(rpw)


def _schedule_2026() -> pd.DataFrame:
    """Real 2026 REG shape: wk1 Sep 9-14 (Wed opener), wk2 Sep 17-21, wk18 Jan 10."""
    rows = [
        (1, "2026-09-09"),
        (1, "2026-09-10"),
        (1, "2026-09-13"),
        (1, "2026-09-14"),
        (2, "2026-09-17"),
        (2, "2026-09-20"),
        (2, "2026-09-21"),
        (3, "2026-09-24"),
        (3, "2026-09-27"),
        (3, "2026-09-28"),
        (18, "2027-01-10"),
    ]
    return pd.DataFrame(
        {
            "season": 2026,
            "game_type": "REG",
            "week": [w for w, _ in rows],
            "gameday": [g for _, g in rows],
        }
    )


def _write(root: Path, season: int, df: pd.DataFrame) -> None:
    d = root / f"season={season}"
    d.mkdir(parents=True)
    df.to_parquet(d / "schedules_20260825_081502.parquet", index=False)


@pytest.fixture
def sched_root(tmp_path: Path) -> Path:
    _write(tmp_path, 2026, _schedule_2026())
    return tmp_path


@pytest.mark.parametrize(
    "today, expected",
    [
        (dt.date(2026, 9, 8), 1),  # Tuesday before kickoff -> Week 1 (the bug)
        (dt.date(2026, 9, 13), 1),  # Sunday of Week 1 -> still Week 1
        (dt.date(2026, 9, 14), 1),  # MNF Monday -> still Week 1
        (dt.date(2026, 9, 15), 2),  # Tuesday after MNF -> Week 2
        (dt.date(2026, 9, 22), 3),  # next Tuesday -> Week 3
        (dt.date(2026, 7, 1), 1),  # preseason -> Week 1 of the new season
    ],
)
def test_upcoming_week_from_schedule(
    sched_root: Path, today: dt.date, expected: int
) -> None:
    season, week, source = rpw.resolve_target_week(today, root=sched_root)
    assert (season, week, source) == (2026, expected, "schedule")


def test_season_over_resolves_to_final_week(sched_root: Path) -> None:
    season, week, source = rpw.resolve_target_week(
        dt.date(2027, 1, 12), root=sched_root
    )
    assert (season, week, source) == (2026, 18, "schedule-final")


def test_prior_season_used_when_current_year_missing(tmp_path: Path) -> None:
    # Only a 2025 schedule exists; a Jan 2026 date is still that season's playoffs.
    df = pd.DataFrame(
        {
            "season": 2025,
            "game_type": "REG",
            "week": [17, 18],
            "gameday": ["2025-12-28", "2026-01-04"],
        }
    )
    _write(tmp_path, 2025, df)
    assert rpw.resolve_target_week(dt.date(2026, 1, 3), root=tmp_path) == (
        2025,
        18,
        "schedule",
    )
    assert rpw.resolve_target_week(dt.date(2026, 1, 12), root=tmp_path) == (
        2025,
        18,
        "schedule-final",
    )


def test_playoff_rows_ignored(tmp_path: Path) -> None:
    df = _schedule_2026()
    df = pd.concat(
        [
            df,
            pd.DataFrame(
                {
                    "season": 2026,
                    "game_type": "POST",
                    "week": [19],
                    "gameday": ["2027-01-17"],
                }
            ),
        ]
    )
    _write(tmp_path, 2026, df)
    assert rpw.resolve_target_week(dt.date(2027, 1, 12), root=tmp_path) == (
        2026,
        18,
        "schedule-final",
    )


def test_calendar_fallback_when_no_schedule(tmp_path: Path) -> None:
    season, week, source = rpw.resolve_target_week(dt.date(2026, 9, 8), root=tmp_path)
    assert source == "calendar"
    assert (season, week) == (2025, 18)  # documents the legacy behaviour we replaced


def test_cli_precedence_inputs_over_schedule(
    sched_root: Path, monkeypatch, capsys, tmp_path
) -> None:
    out = tmp_path / "gh_out"
    monkeypatch.setenv("INPUT_SEASON", "2024")
    monkeypatch.setenv("INPUT_WEEK", "10")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("PIPELINE_WEEK_OVERRIDE", raising=False)
    assert rpw.main() == 0
    assert _core(out) == "season=2024\nweek=10\noffseason=false\n"
    assert "workflow_dispatch" in capsys.readouterr().out


def test_cli_override_variable(monkeypatch, capsys) -> None:
    monkeypatch.delenv("INPUT_SEASON", raising=False)
    monkeypatch.delenv("INPUT_WEEK", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("PIPELINE_WEEK_OVERRIDE", "2023:7")
    assert rpw.main() == 0
    assert "season=2023\nweek=7" in capsys.readouterr().out


def _core(out: Path) -> str:
    """Step-output file minus the refresh_season line (covered separately)."""
    return "".join(
        ln + "\n"
        for ln in out.read_text().splitlines()
        if not ln.startswith("refresh_season=")
    )


def _cli_env(monkeypatch, tmp_path, today: dt.date, root: Path) -> Path:
    out = tmp_path / "gh_out"
    for k in ("INPUT_SEASON", "INPUT_WEEK", "PIPELINE_WEEK_OVERRIDE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    class _D(dt.date):
        @classmethod
        def today(cls):
            return today

    monkeypatch.setattr(rpw.dt, "date", _D)
    monkeypatch.setattr(rpw, "SCHEDULES_ROOT", root)
    monkeypatch.setattr(
        rpw,
        "resolve_target_week",
        lambda t, root=root, _orig=rpw.resolve_target_week: _orig(t, root=root),
    )
    return out


def test_cli_mid_season_not_offseason(sched_root, monkeypatch, capsys, tmp_path):
    out = _cli_env(monkeypatch, tmp_path, dt.date(2026, 9, 22), sched_root)
    assert rpw.main() == 0
    assert _core(out) == "season=2026\nweek=3\noffseason=false\n"
    assert "::warning::" not in capsys.readouterr().out


def test_cli_day_after_final_game_is_offseason(
    sched_root, monkeypatch, capsys, tmp_path
):
    # Final REG game 2027-01-10; the 11th is the first day with nothing left.
    out = _cli_env(monkeypatch, tmp_path, dt.date(2027, 1, 11), sched_root)
    assert rpw.main() == 0
    assert _core(out) == "season=2026\nweek=18\noffseason=true\n"
    assert "::warning::" in capsys.readouterr().out


def test_cli_final_game_day_still_week_18(sched_root, monkeypatch, tmp_path):
    out = _cli_env(monkeypatch, tmp_path, dt.date(2027, 1, 10), sched_root)
    assert rpw.main() == 0
    assert _core(out) == "season=2026\nweek=18\noffseason=false\n"


def test_cli_january_tuesday_offseason_and_never_season_2027(
    sched_root, monkeypatch, tmp_path
):
    # 2027-01-12 (Tuesday cron): must stay season 2026, never roll to 2027 wk1.
    out = _cli_env(monkeypatch, tmp_path, dt.date(2027, 1, 12), sched_root)
    assert rpw.main() == 0
    assert _core(out) == "season=2026\nweek=18\noffseason=true\n"


def test_cli_dispatch_inputs_never_offseason(sched_root, monkeypatch, tmp_path):
    out = _cli_env(monkeypatch, tmp_path, dt.date(2027, 3, 1), sched_root)
    monkeypatch.setenv("INPUT_SEASON", "2026")
    monkeypatch.setenv("INPUT_WEEK", "18")
    assert rpw.main() == 0
    assert _core(out) == "season=2026\nweek=18\noffseason=false\n"


# ---------------------------------------------------------------------------
# "Which week is being PLAYED today" (Sunday refresh) is the same question as
# "earliest week with a game on/after today" evaluated on a game day, so the
# shared resolver serves it without a second function. Pinned below.
# ---------------------------------------------------------------------------


def _season_df(season, rows):
    return pd.DataFrame(
        {
            "season": season,
            "game_type": "REG",
            "week": [w for w, _ in rows],
            "gameday": [g for _, g in rows],
        }
    )


@pytest.fixture
def midseason_root(tmp_path):
    rows = [
        (5, "2026-10-08"),
        (5, "2026-10-11"),
        (5, "2026-10-12"),
        # bye-heavy week: only Thu + Sun, no Monday game
        (6, "2026-10-15"),
        (6, "2026-10-18"),
        (7, "2026-10-22"),
        (7, "2026-10-25"),
        (7, "2026-10-26"),
        (18, "2027-01-09"),
        (18, "2027-01-10"),
    ]
    _write(tmp_path, 2026, _season_df(2026, rows))
    return tmp_path


def test_midseason_sunday_is_the_week_being_played(midseason_root):
    assert rpw.resolve_target_week(dt.date(2026, 10, 25), midseason_root) == (
        2026,
        7,
        "schedule",
    )


def test_thursday_night_game_day_is_that_week(midseason_root):
    # Thursday 10/22: week 6 ended Sunday 10/18, so week 7 is on the field.
    assert rpw.resolve_target_week(dt.date(2026, 10, 22), midseason_root)[:2] == (
        2026,
        7,
    )


def test_sunday_of_week_18_in_january_is_prior_season(midseason_root):
    # 2027 has no schedule; a calendar-year rule would say season 2027.
    assert rpw.resolve_target_week(dt.date(2027, 1, 10), midseason_root) == (
        2026,
        18,
        "schedule",
    )


def test_bye_heavy_week_without_monday_game(midseason_root):
    # Week 6 has no Monday game: Sunday 10/18 is still week 6, Monday 10/19 is not.
    assert rpw.resolve_target_week(dt.date(2026, 10, 18), midseason_root)[:2] == (
        2026,
        6,
    )
    assert rpw.resolve_target_week(dt.date(2026, 10, 19), midseason_root)[:2] == (
        2026,
        7,
    )


@pytest.mark.parametrize(
    "today, expected",
    [
        (dt.date(2026, 10, 25), 2026),  # in season
        (dt.date(2027, 1, 10), 2026),  # January wk 18: NOT 2027
        (dt.date(2027, 1, 20), 2026),  # playoffs / just after the regular season
        (dt.date(2027, 2, 20), 2026),  # Jan-Feb offseason still the old season
        (dt.date(2027, 3, 2), 2027),  # March onward: the new season's board
        (dt.date(2027, 7, 1), 2027),
    ],
)
def test_refresh_season_never_flips_to_new_year_in_january(
    midseason_root, today, expected
):
    assert rpw.refresh_season(today, midseason_root) == expected


def test_cli_writes_refresh_season_jan_week18(sched_root, monkeypatch, tmp_path):
    out = _cli_env(monkeypatch, tmp_path, dt.date(2027, 1, 10), sched_root)
    assert rpw.main() == 0
    assert "refresh_season=2026\n" in out.read_text()


def test_cli_refresh_season_ignores_dispatch_inputs(sched_root, monkeypatch, tmp_path):
    out = _cli_env(monkeypatch, tmp_path, dt.date(2026, 9, 22), sched_root)
    monkeypatch.setenv("INPUT_SEASON", "2024")
    monkeypatch.setenv("INPUT_WEEK", "10")
    assert rpw.main() == 0
    text = out.read_text()
    assert "season=2024\n" in text and "refresh_season=2026\n" in text
