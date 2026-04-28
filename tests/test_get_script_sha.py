"""Unit tests for src.utils.get_script_sha (Phase 79 DQ-01)."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils import get_script_sha


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a git command inside ``repo`` with deterministic identity."""
    env = {
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture()
def temp_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a clean temp git repo, cd into it, return its path."""
    _git(tmp_path, "init", "-q")
    # Older git defaults to "master"; pin to "main" for deterministic tests.
    _git(tmp_path, "checkout", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Behaviour tests
# ---------------------------------------------------------------------------
def test_clean_tracked_file_returns_40_char_sha(temp_repo: Path) -> None:
    target = temp_repo / "tracked.py"
    target.write_text("print('hello')\n")
    _git(temp_repo, "add", "tracked.py")
    _git(temp_repo, "commit", "-q", "-m", "add tracked.py")

    result = get_script_sha("tracked.py")

    assert set(result.keys()) == {"sha", "dirty", "resolved_at"}
    assert len(result["sha"]) == 40, result
    assert all(c in "0123456789abcdef" for c in result["sha"])
    assert result["dirty"] is False


def test_dirty_tracked_file_returns_dirty_true(temp_repo: Path) -> None:
    target = temp_repo / "tracked.py"
    target.write_text("print('v1')\n")
    _git(temp_repo, "add", "tracked.py")
    _git(temp_repo, "commit", "-q", "-m", "add tracked.py")
    # Modify post-commit but do not stage.
    target.write_text("print('v2')\n")

    result = get_script_sha("tracked.py")

    assert len(result["sha"]) == 40
    assert result["dirty"] is True


def test_untracked_file_returns_unknown_sha(temp_repo: Path) -> None:
    target = temp_repo / "untracked.py"
    target.write_text("print('untracked')\n")
    # NEVER staged or committed.

    result = get_script_sha("untracked.py")

    assert result["sha"] == "unknown"
    assert result["dirty"] is False


def test_nonexistent_path_returns_unknown_sha(temp_repo: Path) -> None:
    result = get_script_sha("does_not_exist_xyz123.py")

    assert result["sha"] == "unknown"
    assert result["dirty"] is False


def test_resolved_at_is_iso8601_utc(temp_repo: Path) -> None:
    target = temp_repo / "tracked.py"
    target.write_text("\n")
    _git(temp_repo, "add", "tracked.py")
    _git(temp_repo, "commit", "-q", "-m", "init")

    result = get_script_sha("tracked.py")
    parsed = datetime.fromisoformat(result["resolved_at"])

    assert parsed.tzinfo is not None
    # offset(0) == UTC
    assert parsed.utcoffset().total_seconds() == 0


def test_subprocess_invocations_are_shell_safe() -> None:
    """git is invoked with shell=False and `--` separator in BOTH calls."""
    mock_log = MagicMock(returncode=0, stdout="a" * 40 + "\n")
    mock_diff = MagicMock(returncode=0, stdout="")
    with patch("src.utils.subprocess.run", side_effect=[mock_log, mock_diff]) as mock_run:
        get_script_sha("scripts/audit_event_coverage.py")

    assert mock_run.call_count == 2

    # Both invocations: positional args is a LIST (not a string), shell=False.
    for call in mock_run.call_args_list:
        args, kwargs = call
        assert isinstance(args[0], list), "git invocation must be a list, not a string"
        assert kwargs.get("shell", False) is False
        assert "--" in args[0], "path must be after a `--` separator"
        # The path token comes AFTER the `--` separator.
        sep_idx = args[0].index("--")
        assert args[0][sep_idx + 1] == "scripts/audit_event_coverage.py"
