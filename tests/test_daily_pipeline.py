"""Tests for the daily sentiment pipeline orchestrator.

Verifies that the orchestrator correctly calls each step, handles
failures gracefully, respects --dry-run and --skip-* flags, and
auto-detects NFL season/week.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from scripts.daily_sentiment_pipeline import (
    PipelineResult,
    StepResult,
    detect_nfl_week,
    main,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# detect_nfl_week
# ---------------------------------------------------------------------------


def _write_schedule(root: Path, season: int, rows: list) -> None:
    d = root / f"season={season}"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "season": season,
            "game_type": "REG",
            "week": [w for w, _ in rows],
            "gameday": [g for _, g in rows],
        }
    ).to_parquet(d / "schedules_20260915_080833.parquet", index=False)


@pytest.fixture
def sched_2026(tmp_path: Path) -> Path:
    """Real 2026 REG shape: wk1 Sep 9-14 (Wed opener), wk2 Sep 17-21, wk18 Jan 10."""
    _write_schedule(
        tmp_path,
        2026,
        [
            (1, "2026-09-09"),
            (1, "2026-09-13"),
            (1, "2026-09-14"),
            (2, "2026-09-17"),
            (2, "2026-09-20"),
            (2, "2026-09-21"),
            (3, "2026-09-24"),
            (18, "2027-01-10"),
        ],
    )
    return tmp_path


class TestDetectNflWeek:
    """Sentiment partitions must match the weekly pipeline's target week.

    Regression anchor: on Tue 2026-09-15 the old calendar rule (7-day windows
    from the Week 1 Thursday) wrote ``season=2026/week=01`` while the weekly
    pipeline had already published ``week=02`` projections.
    """

    @pytest.mark.parametrize(
        "today, expected_week",
        [
            (datetime.date(2026, 9, 15), 2),  # Tuesday after Week 1 (the bug)
            (datetime.date(2026, 9, 16), 2),  # Wednesday -- calendar still said 1
            (datetime.date(2026, 9, 14), 1),  # MNF Monday -> still Week 1
            (datetime.date(2026, 9, 8), 1),  # Tuesday before kickoff -> Week 1
            (datetime.date(2026, 7, 1), 1),  # preseason -> Week 1 of new season
        ],
    )
    def test_matches_weekly_pipeline_target_week(
        self, sched_2026: Path, today: datetime.date, expected_week: int
    ) -> None:
        with patch("scripts.resolve_pipeline_week.SCHEDULES_ROOT", sched_2026):
            assert detect_nfl_week(today) == (2026, expected_week)

    def test_tuesday_after_week1_agrees_with_resolver(self, sched_2026: Path) -> None:
        """Byte-for-byte the same (season, week) the weekly cron resolves."""
        from scripts.resolve_pipeline_week import resolve_target_week

        today = datetime.date(2026, 9, 15)
        with patch("scripts.resolve_pipeline_week.SCHEDULES_ROOT", sched_2026):
            season, week, source = resolve_target_week(today)
            assert source == "schedule"
            assert detect_nfl_week(today) == (season, week) == (2026, 2)

    def test_season_over_clamps_to_week_18(self, sched_2026: Path) -> None:
        with patch("scripts.resolve_pipeline_week.SCHEDULES_ROOT", sched_2026):
            assert detect_nfl_week(datetime.date(2027, 1, 25)) == (2026, 18)

    def test_calendar_fallback_without_schedule(self, tmp_path: Path, caplog) -> None:
        """No schedule parquet at all -> legacy calendar rule, with a warning."""
        with patch("scripts.resolve_pipeline_week.SCHEDULES_ROOT", tmp_path):
            season, week = detect_nfl_week(datetime.date(2025, 10, 15))
        assert season == 2025
        assert 1 <= week <= 18
        assert "calendar" in caplog.text


# ---------------------------------------------------------------------------
# StepResult / PipelineResult
# ---------------------------------------------------------------------------


class TestPipelineResult:
    """Tests for the PipelineResult data class."""

    def test_all_success_true(self) -> None:
        result = PipelineResult(
            steps=[StepResult("a", success=True), StepResult("b", success=True)]
        )
        assert result.all_success is True
        assert result.any_success is True

    def test_all_success_false_with_failure(self) -> None:
        result = PipelineResult(
            steps=[StepResult("a", success=True), StepResult("b", success=False)]
        )
        assert result.all_success is False
        assert result.any_success is True

    def test_no_success(self) -> None:
        result = PipelineResult(
            steps=[StepResult("a", success=False), StepResult("b", success=False)]
        )
        assert result.all_success is False
        assert result.any_success is False


# ---------------------------------------------------------------------------
# run_pipeline — skip flags
# ---------------------------------------------------------------------------


class TestSkipFlags:
    """Tests that --skip-* flags prevent the corresponding steps."""

    @patch("scripts.daily_sentiment_pipeline._run_llm_enrichment")
    @patch("scripts.daily_sentiment_pipeline._run_pft_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rotowire_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_reddit(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg, rotowire, pft, llm
    ) -> None:
        """--skip-reddit should not call Reddit ingestion."""
        for mock_fn in [
            rss,
            reddit,
            sleeper,
            extraction,
            player_agg,
            team_agg,
            rotowire,
            pft,
            llm,
        ]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        run_pipeline(season=2025, week=1, skip_reddit=True)

        rss.assert_called_once()
        reddit.assert_not_called()
        sleeper.assert_called_once()

    @patch("scripts.daily_sentiment_pipeline._run_llm_enrichment")
    @patch("scripts.daily_sentiment_pipeline._run_pft_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rotowire_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_rss(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg, rotowire, pft, llm
    ) -> None:
        """--skip-rss should not call RSS ingestion."""
        for mock_fn in [
            rss,
            reddit,
            sleeper,
            extraction,
            player_agg,
            team_agg,
            rotowire,
            pft,
            llm,
        ]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        run_pipeline(season=2025, week=1, skip_rss=True)

        rss.assert_not_called()
        reddit.assert_called_once()
        sleeper.assert_called_once()

    @patch("scripts.daily_sentiment_pipeline._run_llm_enrichment")
    @patch("scripts.daily_sentiment_pipeline._run_pft_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rotowire_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_ingest(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg, rotowire, pft, llm
    ) -> None:
        """--skip-ingest should skip all ingestion steps."""
        for mock_fn in [
            rss,
            reddit,
            sleeper,
            extraction,
            player_agg,
            team_agg,
            rotowire,
            pft,
            llm,
        ]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        run_pipeline(season=2025, week=1, skip_ingest=True)

        rss.assert_not_called()
        reddit.assert_not_called()
        sleeper.assert_not_called()
        extraction.assert_called_once()
        player_agg.assert_called_once()
        team_agg.assert_called_once()


# ---------------------------------------------------------------------------
# Failure isolation — one source failing does not abort others
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    """Tests that failures in one step do not abort subsequent steps."""

    @patch("scripts.daily_sentiment_pipeline._run_llm_enrichment")
    @patch("scripts.daily_sentiment_pipeline._run_pft_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rotowire_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_rss_failure_continues(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg, rotowire, pft, llm
    ) -> None:
        """If RSS fails, Reddit/Sleeper/extraction should still run."""
        rss.return_value = StepResult(name="RSS", success=False, error="timeout")
        for mock_fn in [
            reddit,
            sleeper,
            extraction,
            player_agg,
            team_agg,
            rotowire,
            pft,
            llm,
        ]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        result = run_pipeline(season=2025, week=1)

        # All steps should still be called
        reddit.assert_called_once()
        sleeper.assert_called_once()
        extraction.assert_called_once()
        player_agg.assert_called_once()
        team_agg.assert_called_once()

        # Pipeline should report partial success
        assert result.any_success is True
        assert result.all_success is False

    @patch("scripts.daily_sentiment_pipeline._run_llm_enrichment")
    @patch("scripts.daily_sentiment_pipeline._run_pft_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rotowire_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_all_fail_returns_exit_code_1(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg, rotowire, pft, llm
    ) -> None:
        """If all steps fail, main() should return exit code 1."""
        for mock_fn in [
            rss,
            reddit,
            sleeper,
            extraction,
            player_agg,
            team_agg,
            rotowire,
            pft,
            llm,
        ]:
            mock_fn.return_value = StepResult(name="mock", success=False)

        result = run_pipeline(season=2025, week=1)
        assert result.any_success is False


# ---------------------------------------------------------------------------
# CLI main() entry point
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the CLI main() entry point."""

    @patch("scripts.daily_sentiment_pipeline.run_pipeline")
    def test_main_dry_run_passes_flag(self, mock_run) -> None:
        """--dry-run flag should be passed to run_pipeline."""
        mock_run.return_value = PipelineResult(
            steps=[StepResult("ok", success=True)], dry_run=True
        )
        rc = main(["--season", "2025", "--week", "1", "--dry-run"])
        assert rc == 0
        _, kwargs = mock_run.call_args
        assert kwargs["dry_run"] is True

    @patch("scripts.daily_sentiment_pipeline.run_pipeline")
    def test_main_auto_detects_season_week(self, mock_run) -> None:
        """When no --season/--week provided, auto-detection kicks in."""
        mock_run.return_value = PipelineResult(steps=[StepResult("ok", success=True)])
        rc = main(["--dry-run"])
        assert rc == 0
        _, kwargs = mock_run.call_args
        assert isinstance(kwargs["season"], int)
        assert isinstance(kwargs["week"], int)


class TestClaudeFailureSentinel:
    """The fail-open design let an exhausted credit balance hide for weeks
    (2026-07-08): claude_primary 400'd on every call, per-doc fallback kept
    runs green. _run_extraction must now shout when ALL Claude calls fail."""

    @staticmethod
    def _result(processed, claude_failed, is_primary=True):
        r = MagicMock()
        r.processed_count = processed
        r.skipped_count = 0
        r.signal_count = 5
        r.claude_failed_count = claude_failed
        r.is_claude_primary = is_primary
        return r

    def _run(self, result, capsys):
        from scripts.daily_sentiment_pipeline import _run_extraction

        fake_pipeline = MagicMock()
        fake_pipeline.run.return_value = result
        with patch(
            "src.sentiment.processing.pipeline.SentimentPipeline",
            return_value=fake_pipeline,
        ):
            step = _run_extraction(season=2026, week=1, dry_run=True, verbose=False)
        return step, capsys.readouterr().out

    def test_all_claude_calls_failed_emits_sentinel(self, capsys):
        step, out = self._run(self._result(processed=10, claude_failed=10), capsys)
        assert step.success  # fail-open behavior preserved
        assert "SENTINEL" in step.detail
        assert "::warning" in out
        assert "credit balance" in out

    def test_partial_failures_do_not_trip_sentinel(self, capsys):
        step, out = self._run(self._result(processed=10, claude_failed=3), capsys)
        assert "SENTINEL" not in step.detail
        assert "::warning" not in out

    def test_rule_extractor_mode_does_not_trip_sentinel(self, capsys):
        step, out = self._run(
            self._result(processed=10, claude_failed=0, is_primary=False), capsys
        )
        assert "SENTINEL" not in step.detail
        assert "::warning" not in out

    def test_zero_docs_does_not_trip_sentinel(self, capsys):
        step, out = self._run(self._result(processed=0, claude_failed=0), capsys)
        assert "SENTINEL" not in step.detail
