---
phase: 79-audit-provenance-version-probe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/utils.py
  - tests/test_get_script_sha.py
autonomous: true
requirements: [DQ-01]
must_haves:
  truths:
    - "src.utils exports get_script_sha(script_path) returning {sha, dirty, resolved_at}"
    - "Calling get_script_sha on a clean tracked file returns the file-specific last-commit SHA (40 chars) and dirty=False"
    - "Calling get_script_sha on a file with uncommitted changes returns dirty=True"
    - "Helper handles untracked / non-existent paths without raising — returns sha='unknown', dirty=False"
    - "Helper invokes git via subprocess with shell=False and `--` separator (no shell-injection surface)"
  artifacts:
    - path: "src/utils.py"
      provides: "get_script_sha(script_path: str) -> Dict[str, Any] returning {sha, dirty, resolved_at}"
      contains: "def get_script_sha("
    - path: "tests/test_get_script_sha.py"
      provides: "Pytest unit tests covering clean file, dirty file, untracked path, and shell-safe subprocess invocation"
      contains: "def test_get_script_sha"
  key_links:
    - from: "src/utils.py::get_script_sha"
      to: "git CLI"
      via: "subprocess.run([\"git\", \"log\", \"-1\", \"--format=%H\", \"--\", path], shell=False, capture_output=True, text=True, check=False)"
      pattern: "subprocess\\.run\\(\\[.git."
    - from: "src/utils.py::get_script_sha"
      to: "git CLI"
      via: "subprocess.run([\"git\", \"diff\", \"HEAD\", \"--\", path], shell=False, capture_output=True, text=True, check=False)"
      pattern: "git.*diff.*HEAD"
---

<objective>
Land the `get_script_sha(script_path)` helper in `src/utils.py` with full unit-test coverage. This is the **foundation primitive** for DQ-01: every audit script will import this function and embed its return dict under `script_provenance` in the JSON output (Plan 79-02). Helper must be deterministic, shell-injection-safe, and degrade gracefully for untracked paths so future audit scripts can adopt it with one import line.

Purpose: Phase 84 DEPLOY-04 will read `script_provenance.sha` from audit JSON outputs and reject evidence whose SHA does not match a known-good audit-script commit. The reliability of that gate depends on this helper returning the correct file-specific SHA every time.

Output:
- `src/utils.py` gains `get_script_sha(script_path: str) -> Dict[str, Any]`
- `tests/test_get_script_sha.py` with ≥ 5 unit tests using a temp-dir git repo fixture
</objective>

<execution_context>
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/workflows/execute-plan.md
@/Users/georgesmith/repos/nfl_data_engineering/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md
@src/utils.py

<interfaces>
<!-- Style template: existing src/utils.py helpers -->

From src/utils.py (existing pattern to mirror):
```python
def get_latest_s3_key(
    s3_client,
    bucket: str,
    prefix: str,
    suffix: str = ".parquet",
) -> Optional[str]:
    """Return the S3 key of the most recently written object matching suffix under prefix.
    ...
    """
```

The new helper follows the same shape: top-level function in `src/utils.py`, type-hinted signature, Google-style docstring, returns a dict (not a dataclass — keeps the JSON-serialisable surface trivial).

Existing imports already present in src/utils.py: `logging`, `os`, `pandas`, `Optional`, `Dict`, `Any`, `boto3`. New imports needed: `subprocess`, `datetime` (with `timezone`), `pathlib.Path`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Implement get_script_sha() helper in src/utils.py</name>
  <files>src/utils.py</files>
  <read_first>
    - src/utils.py (FULL FILE — see existing helper patterns: get_latest_s3_key at line 184, download_latest_parquet at line 225)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-01, D-02, D-03 spec)
  </read_first>
  <behavior>
    - get_script_sha("scripts/audit_event_coverage.py") on a clean checkout returns {"sha": "<40-char hex>", "dirty": False, "resolved_at": "<ISO-8601 UTC>"}
    - get_script_sha on a path with `git diff HEAD -- {path}` non-empty returns dirty=True
    - get_script_sha on an untracked path (e.g. a brand-new file) returns {"sha": "unknown", "dirty": False, "resolved_at": "<ISO-8601 UTC>"} — does NOT raise
    - get_script_sha on a path that does not exist on disk returns {"sha": "unknown", "dirty": False, "resolved_at": "<ISO-8601 UTC>"} — does NOT raise
    - resolved_at is always present and parseable as ISO-8601 in UTC (use datetime.now(timezone.utc).isoformat())
    - subprocess invocations MUST use shell=False and pass the path after a `--` separator (defence against any future caller passing user-controlled paths)
  </behavior>
  <action>
    Append the following helper to `src/utils.py`. Place it immediately AFTER `download_latest_parquet` (after line 263). Add the new imports (`subprocess`, `datetime`/`timezone`, `pathlib.Path`) to the existing import block at the top of the file alongside the existing imports — do NOT shadow existing names.

    Add to the imports section near the top of `src/utils.py` (after `import os`):
    ```python
    import subprocess
    from datetime import datetime, timezone
    from pathlib import Path
    ```

    Append at the end of the file (after `download_latest_parquet`):
    ```python
    def get_script_sha(script_path: str) -> Dict[str, Any]:
        """Resolve the git provenance of an audit script.

        Returns a JSON-serialisable dict capturing the file-specific
        last-commit SHA and whether the working tree has uncommitted
        changes against that file. Designed to be embedded under a
        top-level ``script_provenance`` key in audit-script JSON
        outputs (Phase 79 DQ-01 contract).

        Args:
            script_path: Path to the audit script. May be absolute or
                relative to the repository root. Need not exist on disk.

        Returns:
            Dict with keys:
              - ``sha``: 40-char hex SHA of the last commit that touched
                the file, or the literal string ``"unknown"`` when the
                path is untracked, missing, or git is unavailable.
              - ``dirty``: True when ``git diff HEAD -- {path}`` is
                non-empty. False otherwise (including for ``unknown``
                cases).
              - ``resolved_at``: ISO-8601 UTC timestamp recorded at the
                moment the helper ran.

        Phase 84 DEPLOY-04 consumes ``sha`` and ``dirty`` to gate audit
        evidence. ``dirty=True`` is grounds for hard-rejection; an
        unknown ``sha`` means "pre-provenance era — manual review"
        (D-08).

        Subprocess invocations use ``shell=False`` and pass ``script_path``
        after a ``--`` separator so a hostile path (e.g. ``--upload-pack``)
        cannot be misinterpreted as a git option.
        """
        resolved_at = datetime.now(timezone.utc).isoformat()
        path = str(script_path)

        # Resolve last-commit SHA for this exact file.
        try:
            log_proc = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", path],
                shell=False,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            sha_raw = log_proc.stdout.strip()
            sha = sha_raw if (log_proc.returncode == 0 and len(sha_raw) == 40) else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            # FileNotFoundError = git binary missing; TimeoutExpired = hung subprocess.
            sha = "unknown"

        # Probe for uncommitted local edits against this file.
        dirty = False
        if sha != "unknown":
            try:
                diff_proc = subprocess.run(
                    ["git", "diff", "HEAD", "--", path],
                    shell=False,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                dirty = bool(diff_proc.stdout.strip())
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                dirty = False

        return {"sha": sha, "dirty": dirty, "resolved_at": resolved_at}
    ```

    Per D-03: future audit scripts adopt this with one import line. Per project conventions: type hints required, Google-style docstring, `from __future__ import annotations` is NOT used in `src/utils.py` so use `Dict[str, Any]` rather than `dict[str, Any]`.
  </action>
  <verify>
    <automated>python -c "from src.utils import get_script_sha; r = get_script_sha('src/utils.py'); assert set(r.keys()) == {'sha', 'dirty', 'resolved_at'}, r; assert len(r['sha']) == 40 or r['sha'] == 'unknown', r; assert isinstance(r['dirty'], bool), r; print('OK', r)"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -n "def get_script_sha(" src/utils.py` returns exactly one match
    - `grep -n "import subprocess" src/utils.py` returns exactly one match
    - `python -c "from src.utils import get_script_sha"` exits 0
    - The helper returns a dict with exactly three keys: `{"sha", "dirty", "resolved_at"}`
    - Calling on `src/utils.py` itself returns either a 40-char SHA or `"unknown"` (and matching dirty bool)
    - `grep -n 'shell=False' src/utils.py` confirms shell=False on every subprocess.run call inside get_script_sha
    - `grep -nE 'subprocess.run.*\\["git"' src/utils.py` shows the `--` separator before `path` in BOTH subprocess invocations
  </acceptance_criteria>
  <done>
    src/utils.py contains get_script_sha() with full type annotation, Google-style docstring, two safe subprocess invocations (`git log -1 --format=%H -- {path}` and `git diff HEAD -- {path}`), and graceful degradation to `sha='unknown'` for any failure mode.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add unit tests for get_script_sha in tests/test_get_script_sha.py</name>
  <files>tests/test_get_script_sha.py</files>
  <read_first>
    - src/utils.py (read the get_script_sha implementation just landed in Task 1)
    - tests/test_utils.py (pattern reference — uses unittest + sys.path.append style; the new test file uses pytest conventions per .claude/rules/testing.md)
    - .planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-CONTEXT.md (D-01, D-02 spec)
  </read_first>
  <behavior>
    - Test 1 (clean tracked file): get_script_sha on src/utils.py returns 40-char sha, dirty=False
    - Test 2 (dirty tracked file): in a temp-dir git repo with a tracked file modified post-commit, get_script_sha returns dirty=True
    - Test 3 (untracked file): get_script_sha on a brand-new file (created but never staged) returns sha='unknown', dirty=False — does NOT raise
    - Test 4 (non-existent path): get_script_sha on '/tmp/does_not_exist_xyz123.py' returns sha='unknown', dirty=False — does NOT raise
    - Test 5 (resolved_at is ISO-8601 UTC): the resolved_at field parses via datetime.fromisoformat() and has tzinfo set
    - Test 6 (shell-injection safety): mock subprocess.run and assert it was called with shell=False and a list (not a string), and that the path was passed after a '--' separator in BOTH the log and diff invocations
  </behavior>
  <action>
    Create `tests/test_get_script_sha.py` with the following content. Tests use pytest + temp_path fixtures + a small `_git` helper for repo setup.

    ```python
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
    ```

    Note: the test file uses `pytest` style (per `.claude/rules/testing.md`). It does NOT use `unittest.TestCase`. Place at `tests/test_get_script_sha.py` (sibling of existing `tests/test_utils.py`).
  </action>
  <verify>
    <automated>python -m pytest tests/test_get_script_sha.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `tests/test_get_script_sha.py` exists
    - `pytest tests/test_get_script_sha.py -x -q` exits 0 with at least 6 tests collected
    - The mock-based shell-safety test verifies BOTH `git log` and `git diff` calls used `shell=False` and a list-form argv with `--` separator
    - No test depends on the host's actual git history — every behavioural test runs inside a `temp_repo` fixture
  </acceptance_criteria>
  <done>
    Six pytest tests pass: clean-file SHA, dirty-file flag, untracked path, missing path, ISO-8601 resolved_at, and shell-injection safety. Test file uses pytest fixtures and `monkeypatch.chdir` to isolate from the host repo.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller → get_script_sha argument | An audit script (or future caller) supplies a `script_path` string. Treated as untrusted-by-default per defence-in-depth. |
| get_script_sha → git binary | Subprocess call into the system `git` binary. Argument list is fully constructed by the helper. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-79-01 | T (Tampering) — argument injection | `get_script_sha` subprocess call | mitigate | Pass argv as a list with `shell=False`; insert literal `"--"` token before `path` so a hostile path like `--upload-pack=...` cannot be reinterpreted as a git option. Both `git log` and `git diff` invocations follow this pattern. |
| T-79-02 | I (Information Disclosure) — leaking git history | Return value | accept | Helper returns only the SHA (public-by-design — already in commit graph), a dirty bool, and a timestamp. No file contents, no diff bodies, no env vars. Audit JSONs are committed to the planning directory which is already public to the project. |
| T-79-03 | D (Denial of Service) — hung git subprocess | `subprocess.run` calls | mitigate | `timeout=10` on every subprocess.run; on `TimeoutExpired` the helper catches and falls through to `sha='unknown'` rather than propagating. |
| T-79-04 | D (Denial of Service) — missing git binary | `subprocess.run` calls | mitigate | `FileNotFoundError` and `OSError` caught; helper degrades to `sha='unknown'` so audit scripts on a git-less environment (rare but possible in some CI containers) still produce a runnable JSON. |
</threat_model>

<verification>
- Helper imports cleanly: `python -c "from src.utils import get_script_sha"` exits 0
- Behaviour matches D-01 (file-specific last-commit SHA) and D-02 (dirty bool from `git diff HEAD --`)
- Shell-injection test passes — argv is always a list, shell=False, `--` separator before path
- Helper degrades gracefully for untracked / missing / hostile paths
- All tests pass: `pytest tests/test_get_script_sha.py -x -q`
- No regression in existing tests: `pytest tests/test_utils.py -x -q`
</verification>

<success_criteria>
- `from src.utils import get_script_sha` works from any Python module in the project
- The helper returns `{"sha": str, "dirty": bool, "resolved_at": str}` with no other keys
- `sha` is either a 40-char hex string or the literal `"unknown"`
- `dirty` is always a Python `bool` (never None / 0 / 1)
- `resolved_at` is ISO-8601 with UTC offset and parseable via `datetime.fromisoformat()`
- All 6 unit tests pass
</success_criteria>

<output>
After completion, create `.planning/milestones/v7.2-phases/79-audit-provenance-version-probe/79-01-SUMMARY.md` capturing:
- Helper signature and return shape
- Test count and pass status
- Any deviations from the action text (with rationale)
</output>
