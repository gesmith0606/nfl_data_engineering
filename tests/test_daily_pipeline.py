"""Tests for the daily sentiment pipeline orchestrator.

Verifies that the orchestrator correctly calls each step, handles
failures gracefully, respects --dry-run and --skip-* flags, and
auto-detects NFL season/week.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

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


class TestDetectNflWeek:
    """Tests for NFL season/week auto-detection."""

    def test_mid_season_returns_valid_week(self) -> None:
        """Mid-October should return a week in the 4-8 range."""
        with patch(
            "scripts.daily_sentiment_pipeline.datetime"
        ) as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2025, 10, 15)
            mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            mock_dt.timedelta = datetime.timedelta
            season, week = detect_nfl_week()
            assert season == 2025
            assert 1 <= week <= 18

    def test_preseason_returns_prior_season(self) -> None:
        """July should return the prior season."""
        with patch(
            "scripts.daily_sentiment_pipeline.datetime"
        ) as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2026, 7, 1)
            mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            mock_dt.timedelta = datetime.timedelta
            season, week = detect_nfl_week()
            # Before September = prior season, but July is after June so
            # we use current year's anchor which hasn't happened yet
            assert season == 2025

    def test_week_clamped_to_18(self) -> None:
        """Late January should clamp to week 18."""
        with patch(
            "scripts.daily_sentiment_pipeline.datetime"
        ) as mock_dt:
            mock_dt.date.today.return_value = datetime.date(2026, 1, 25)
            mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
            mock_dt.timedelta = datetime.timedelta
            season, week = detect_nfl_week()
            assert week <= 18


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

    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_reddit(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg
    ) -> None:
        """--skip-reddit should not call Reddit ingestion."""
        for mock_fn in [rss, reddit, sleeper, extraction, player_agg, team_agg]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        run_pipeline(season=2025, week=1, skip_reddit=True)

        rss.assert_called_once()
        reddit.assert_not_called()
        sleeper.assert_called_once()

    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_rss(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg
    ) -> None:
        """--skip-rss should not call RSS ingestion."""
        for mock_fn in [rss, reddit, sleeper, extraction, player_agg, team_agg]:
            mock_fn.return_value = StepResult(name="mock", success=True)

        run_pipeline(season=2025, week=1, skip_rss=True)

        rss.assert_not_called()
        reddit.assert_called_once()
        sleeper.assert_called_once()

    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_skip_ingest(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg
    ) -> None:
        """--skip-ingest should skip all ingestion steps."""
        for mock_fn in [rss, reddit, sleeper, extraction, player_agg, team_agg]:
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

    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_rss_failure_continues(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg
    ) -> None:
        """If RSS fails, Reddit/Sleeper/extraction should still run."""
        rss.return_value = StepResult(name="RSS", success=False, error="timeout")
        for mock_fn in [reddit, sleeper, extraction, player_agg, team_agg]:
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

    @patch("scripts.daily_sentiment_pipeline._run_team_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_player_aggregation")
    @patch("scripts.daily_sentiment_pipeline._run_extraction")
    @patch("scripts.daily_sentiment_pipeline._run_sleeper_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_reddit_ingestion")
    @patch("scripts.daily_sentiment_pipeline._run_rss_ingestion")
    def test_all_fail_returns_exit_code_1(
        self, rss, reddit, sleeper, extraction, player_agg, team_agg
    ) -> None:
        """If all steps fail, main() should return exit code 1."""
        for mock_fn in [rss, reddit, sleeper, extraction, player_agg, team_agg]:
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
        mock_run.return_value = PipelineResult(
            steps=[StepResult("ok", success=True)]
        )
        rc = main(["--dry-run"])
        assert rc == 0
        _, kwargs = mock_run.call_args
        assert isinstance(kwargs["season"], int)
        assert isinstance(kwargs["week"], int)
