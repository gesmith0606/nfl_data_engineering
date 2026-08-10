"""
Tests for Finding 2 (silent-failure sweep): five Silver transformation
scripts' main() always `return 0` regardless of per-season failures.

Contract under test (per-script):
- If ALL requested seasons produced zero output rows -> main() returns 1
  and prints an ::error:: line.
- If SOME (but not all) seasons failed -> main() still returns 0 (existing
  multi-season fail-open design is preserved) but prints an unmissable
  ::warning:: summary naming the failed seasons.
- If none failed -> main() returns 0, no ::error::/::warning:: about failures.

Each script exposes a season-processing entry point that main() drives:
- silver_player_transformation.run_silver_transform() -> list[int] failed
- silver_team_transformation.run_silver_team_transform() -> list[int] failed
- silver_game_context_transformation.run_game_context_transform() -> list[int] failed
- silver_player_quality_transformation.transform_season(season) -> DataFrame | None
- silver_advanced_transformation.process_season(season) -> DataFrame | None

Tests patch at that seam so the exit-code *wiring* in main() is verified
independently of the underlying fetch/transform logic (which finding 2
explicitly says must not change).
"""
import os
import sys
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSilverPlayerTransformation:
    @patch("scripts.silver_player_transformation.run_silver_transform")
    def test_all_seasons_failed_returns_1(self, mock_run, capsys):
        from scripts.silver_player_transformation import main

        mock_run.return_value = [2016, 2017]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 1
        assert "::error::" in capsys.readouterr().out

    @patch("scripts.silver_player_transformation.run_silver_transform")
    def test_partial_failure_returns_0_with_warning(self, mock_run, capsys):
        from scripts.silver_player_transformation import main

        mock_run.return_value = [2016]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        assert "::warning::" in capsys.readouterr().out

    @patch("scripts.silver_player_transformation.run_silver_transform")
    def test_no_failures_returns_0_clean(self, mock_run, capsys):
        from scripts.silver_player_transformation import main

        mock_run.return_value = []
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "::error::" not in captured
        assert "::warning::" not in captured


class TestSilverTeamTransformation:
    @patch("scripts.silver_team_transformation.run_silver_team_transform")
    def test_all_seasons_failed_returns_1(self, mock_run, capsys):
        from scripts.silver_team_transformation import main

        mock_run.return_value = [2016, 2017]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 1
        assert "::error::" in capsys.readouterr().out

    @patch("scripts.silver_team_transformation.run_silver_team_transform")
    def test_partial_failure_returns_0_with_warning(self, mock_run, capsys):
        from scripts.silver_team_transformation import main

        mock_run.return_value = [2016]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        assert "::warning::" in capsys.readouterr().out


class TestSilverGameContextTransformation:
    @patch("scripts.silver_game_context_transformation.run_game_context_transform")
    def test_all_seasons_failed_returns_1(self, mock_run, capsys):
        from scripts.silver_game_context_transformation import main

        mock_run.return_value = [2016, 2017]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 1
        assert "::error::" in capsys.readouterr().out

    @patch("scripts.silver_game_context_transformation.run_game_context_transform")
    def test_partial_failure_returns_0_with_warning(self, mock_run, capsys):
        from scripts.silver_game_context_transformation import main

        mock_run.return_value = [2016]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        assert "::warning::" in capsys.readouterr().out


class TestSilverPlayerQualityTransformation:
    @patch("scripts.silver_player_quality_transformation._save_local_silver")
    @patch("scripts.silver_player_quality_transformation.transform_season")
    def test_all_seasons_failed_returns_1(self, mock_transform, mock_save, capsys):
        from scripts.silver_player_quality_transformation import main

        mock_transform.return_value = None
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017"]):
            exit_code = main()

        assert exit_code == 1
        mock_save.assert_not_called()
        assert "::error::" in capsys.readouterr().out

    @patch("scripts.silver_player_quality_transformation._save_local_silver")
    @patch("scripts.silver_player_quality_transformation.transform_season")
    def test_partial_failure_returns_0_with_warning(self, mock_transform, mock_save, capsys):
        from scripts.silver_player_quality_transformation import main

        ok_df = pd.DataFrame({"team": ["KC"], "season": [2017], "week": [1]})
        mock_transform.side_effect = [None, ok_df]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017"]):
            exit_code = main()

        assert exit_code == 0
        assert "::warning::" in capsys.readouterr().out

    @patch("scripts.silver_player_quality_transformation._save_local_silver")
    @patch("scripts.silver_player_quality_transformation.transform_season")
    def test_empty_dataframe_result_counts_as_failure(self, mock_transform, mock_save, capsys):
        """A non-None but zero-row result must also count as a failed season."""
        from scripts.silver_player_quality_transformation import main

        mock_transform.return_value = pd.DataFrame(columns=["team", "season", "week"])
        with patch("sys.argv", ["prog", "--season", "2016"]):
            exit_code = main()

        assert exit_code == 1


class TestSilverAdvancedTransformation:
    @patch("scripts.silver_advanced_transformation._save_local_silver")
    @patch("scripts.silver_advanced_transformation.process_season")
    def test_all_seasons_failed_returns_1(self, mock_process, mock_save, capsys):
        from scripts.silver_advanced_transformation import main

        mock_process.return_value = None
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 1
        mock_save.assert_not_called()
        assert "::error::" in capsys.readouterr().out

    @patch("scripts.silver_advanced_transformation._save_local_silver")
    @patch("scripts.silver_advanced_transformation.process_season")
    def test_partial_failure_returns_0_with_warning(self, mock_process, mock_save, capsys):
        from scripts.silver_advanced_transformation import main

        ok_df = pd.DataFrame({"player_gsis_id": ["00-1"], "season": [2017], "week": [1]})
        mock_process.side_effect = [None, ok_df]
        with patch("sys.argv", ["prog", "--seasons", "2016", "2017", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        assert "::warning::" in capsys.readouterr().out

    @patch("scripts.silver_advanced_transformation._save_local_silver")
    @patch("scripts.silver_advanced_transformation.process_season")
    def test_nan_filled_columns_is_success_not_failure(self, mock_process, mock_save, capsys):
        """NGS/QBR-absent seasons return rows with NaN advanced columns --
        that is SUCCESS, not a failed season (see SILVER_REGEN_REPORT.md)."""
        from scripts.silver_advanced_transformation import main

        nan_filled_df = pd.DataFrame({
            "player_gsis_id": ["00-1", "00-2"],
            "season": [2016, 2016],
            "week": [1, 1],
            "ngs_avg_separation": [None, None],
            "qbr_total": [None, None],
        })
        mock_process.return_value = nan_filled_df
        with patch("sys.argv", ["prog", "--seasons", "2016", "--no-s3"]):
            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "::error::" not in captured
        assert "::warning::" not in captured
