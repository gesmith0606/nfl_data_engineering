"""CLI argument tests for ``scripts/process_sentiment.py`` (Plan 71-05 Task 1).

These tests verify the new ``--extractor-mode`` / ``--mode`` arguments
that route ``SentimentPipeline(extractor_mode=...)`` from the operator's
shell. Coverage:

* ``--extractor-mode`` parses the four valid modes and rejects nonsense.
* ``--mode`` is an exact alias for ``--extractor-mode`` (single ``dest``).
* Using both simultaneously triggers the argparse mutex error.
* When neither is set, ``main()`` MUST NOT pass ``extractor_mode`` to the
  pipeline kwargs — Plan 71-04's ``EXTRACTOR_MODE`` env precedence then
  takes effect.
* ``--help`` advertises the ``claude_primary`` choice.
* ANTHROPIC_API_KEY-not-set warning fires only for ``claude`` /
  ``claude_primary`` modes (not ``rule`` / ``auto``).

Tests inject spy classes via ``monkeypatch`` so no real ingestion or
Claude calls run. Pipeline construction is observed only.
"""

from __future__ import annotations

import sys
from typing import Any, Dict
from unittest.mock import MagicMock

import pandas as pd
import pytest

# Import the module under test once at the top so monkeypatch can swap
# ``SentimentPipeline``, ``WeeklyAggregator``, and ``TeamWeeklyAggregator``
# on the imported names that ``main()`` resolves at call time.
from scripts import process_sentiment as ps


# ---------------------------------------------------------------------------
# Spies
# ---------------------------------------------------------------------------


class _PipelineSpy:
    """Records the kwargs passed to ``SentimentPipeline(**kwargs)``."""

    last_init_kwargs: Dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).last_init_kwargs = dict(kwargs)
        self.extractor = MagicMock(is_available=True)

    def run(self, season: int, week: int, dry_run: bool = False) -> Any:
        result = MagicMock()
        result.processed_count = 0
        result.skipped_count = 0
        result.failed_count = 0
        result.signal_count = 0
        result.output_files = []
        return result


class _WeeklyAggSpy:
    def aggregate(self, season: int, week: int, dry_run: bool = False) -> pd.DataFrame:
        return pd.DataFrame()


class _TeamAggSpy:
    def aggregate(self, season: int, week: int, dry_run: bool = False) -> pd.DataFrame:
        return pd.DataFrame()


@pytest.fixture(autouse=True)
def _patch_pipeline_and_aggregators(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap pipeline + aggregators with spies so no real I/O runs."""
    _PipelineSpy.last_init_kwargs = {}
    monkeypatch.setattr(ps, "SentimentPipeline", _PipelineSpy)
    monkeypatch.setattr(ps, "WeeklyAggregator", _WeeklyAggSpy)
    monkeypatch.setattr(ps, "TeamWeeklyAggregator", _TeamAggSpy)


# ---------------------------------------------------------------------------
# Parser-level tests
# ---------------------------------------------------------------------------


class TestParser:
    """Argparse-only behaviour — no ``main()`` invocation."""

    def test_extractor_mode_claude_primary_parses(self) -> None:
        parser = ps._build_parser()
        args = parser.parse_args(
            ["--season", "2025", "--week", "17", "--extractor-mode", "claude_primary"]
        )
        assert args.extractor_mode == "claude_primary"

    def test_mode_alias_claude_primary_parses(self) -> None:
        parser = ps._build_parser()
        args = parser.parse_args(
            ["--season", "2025", "--week", "17", "--mode", "claude_primary"]
        )
        assert args.extractor_mode == "claude_primary"

    @pytest.mark.parametrize("mode", ["auto", "rule", "claude", "claude_primary"])
    def test_extractor_mode_accepts_all_valid_choices(self, mode: str) -> None:
        parser = ps._build_parser()
        args = parser.parse_args(
            ["--season", "2025", "--week", "17", "--extractor-mode", mode]
        )
        assert args.extractor_mode == mode

    def test_extractor_mode_invalid_value_exits_2(self) -> None:
        parser = ps._build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(
                ["--season", "2025", "--week", "17", "--extractor-mode", "nonsense"]
            )
        assert exc_info.value.code == 2

    def test_extractor_mode_and_mode_together_are_mutually_exclusive(self) -> None:
        parser = ps._build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(
                [
                    "--season",
                    "2025",
                    "--week",
                    "17",
                    "--extractor-mode",
                    "claude_primary",
                    "--mode",
                    "rule",
                ]
            )
        assert exc_info.value.code == 2

    def test_default_extractor_mode_is_none(self) -> None:
        """No CLI override → ``args.extractor_mode is None``.

        Critical: a non-None default (e.g. "auto") would always pass the
        kwarg into the pipeline and clobber EXTRACTOR_MODE env precedence.
        """
        parser = ps._build_parser()
        args = parser.parse_args(["--season", "2025", "--week", "17"])
        assert args.extractor_mode is None

    def test_help_mentions_claude_primary(self, capsys: pytest.CaptureFixture[str]) -> None:
        parser = ps._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])
        captured = capsys.readouterr()
        # ``--help`` writes to stdout; choice list must include claude_primary.
        assert "claude_primary" in captured.out
        assert "--extractor-mode" in captured.out
        assert "--mode" in captured.out


# ---------------------------------------------------------------------------
# main() integration tests — verify pipeline kwargs routing
# ---------------------------------------------------------------------------


class TestMainPipelineRouting:
    """``main()`` constructs SentimentPipeline with expected kwargs."""

    def _run_main(
        self, monkeypatch: pytest.MonkeyPatch, *cli_args: str
    ) -> int:
        """Invoke ``main()`` with a synthetic argv."""
        monkeypatch.setattr(sys, "argv", ["process_sentiment.py", *cli_args])
        return ps.main()

    def test_no_mode_arg_omits_extractor_mode_kwarg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When neither --extractor-mode nor --mode is set, kwarg is omitted.

        This preserves the EXTRACTOR_MODE env precedence Plan 71-04 built.
        """
        rc = self._run_main(monkeypatch, "--season", "2025", "--week", "17")
        assert rc == 0
        assert "extractor_mode" not in _PipelineSpy.last_init_kwargs

    def test_extractor_mode_claude_primary_is_passed_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = self._run_main(
            monkeypatch,
            "--season",
            "2025",
            "--week",
            "17",
            "--extractor-mode",
            "claude_primary",
        )
        assert rc == 0
        assert _PipelineSpy.last_init_kwargs.get("extractor_mode") == "claude_primary"

    def test_mode_alias_routes_identically_to_extractor_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rc = self._run_main(
            monkeypatch,
            "--season",
            "2025",
            "--week",
            "17",
            "--mode",
            "claude_primary",
        )
        assert rc == 0
        assert _PipelineSpy.last_init_kwargs.get("extractor_mode") == "claude_primary"

    def test_rule_mode_does_not_warn_about_missing_anthropic_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """rule / auto modes don't need the API key — no missing-key warning."""
        # Make the pipeline report the extractor as unavailable so the
        # legacy code path that emits the warning would fire if the new
        # code didn't gate it on the mode.
        class _PipelineUnavail(_PipelineSpy):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self.extractor = MagicMock(is_available=False)

        monkeypatch.setattr(ps, "SentimentPipeline", _PipelineUnavail)

        with caplog.at_level("WARNING"):
            rc = self._run_main(
                monkeypatch,
                "--season",
                "2025",
                "--week",
                "17",
                "--extractor-mode",
                "rule",
            )
        assert rc == 0
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert not any(
            "ANTHROPIC_API_KEY" in m for m in warnings
        ), f"unexpected key warning in rule mode: {warnings}"

    def test_claude_primary_mode_warns_when_key_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """claude_primary mode warns when extractor reports unavailable."""

        class _PipelineUnavail(_PipelineSpy):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self.extractor = MagicMock(is_available=False)

        monkeypatch.setattr(ps, "SentimentPipeline", _PipelineUnavail)

        with caplog.at_level("WARNING"):
            rc = self._run_main(
                monkeypatch,
                "--season",
                "2025",
                "--week",
                "17",
                "--extractor-mode",
                "claude_primary",
            )
        assert rc == 0
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
        assert any(
            "ANTHROPIC_API_KEY" in m for m in warnings
        ), f"expected key warning in claude_primary mode; got {warnings}"

    def test_logs_precedence_note_when_cli_arg_set(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Setting --extractor-mode logs an INFO line about CLI > env precedence."""
        with caplog.at_level("INFO"):
            rc = self._run_main(
                monkeypatch,
                "--season",
                "2025",
                "--week",
                "17",
                "--extractor-mode",
                "claude_primary",
            )
        assert rc == 0
        infos = [r.message for r in caplog.records if r.levelname == "INFO"]
        assert any(
            "claude_primary" in m and ("EXTRACTOR_MODE" in m or "env" in m)
            for m in infos
        ), f"expected precedence INFO log; got {infos}"
