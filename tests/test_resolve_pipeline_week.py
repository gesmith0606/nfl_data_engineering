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
    assert out.read_text() == "season=2024\nweek=10\n"
    assert "workflow_dispatch" in capsys.readouterr().out


def test_cli_override_variable(monkeypatch, capsys) -> None:
    monkeypatch.delenv("INPUT_SEASON", raising=False)
    monkeypatch.delenv("INPUT_WEEK", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setenv("PIPELINE_WEEK_OVERRIDE", "2023:7")
    assert rpw.main() == 0
    assert "season=2023\nweek=7" in capsys.readouterr().out
