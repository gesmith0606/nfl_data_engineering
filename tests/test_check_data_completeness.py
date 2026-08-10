"""Tests for scripts/check_data_completeness.py — data-existence invariant gate.

Covers the exact scenarios from the audit that motivated this script
(.planning/DATA_COMPLETENESS_AUDIT.md): a missing FAIL-tier season must
fail loudly, a missing WARN-tier path must warn without blocking, a
complete manifest must pass cleanly, and --ci mode must not check
uncommitted (local-only) paths.
"""

import os
import sys
from unittest import mock

import pandas as pd
import pytest

# Make scripts/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_data_completeness as cdc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_parquet(path, n_rows=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame({"col": range(n_rows)}).to_parquet(path, index=False)


def _write_text(path, content="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


def _patch_data_root(tmp_path):
    return mock.patch.object(cdc, "DATA_ROOT", tmp_path / "data")


# ---------------------------------------------------------------------------
# check_requirement — generic manifest-entry evaluation
# ---------------------------------------------------------------------------

class TestCheckRequirement:
    def test_missing_season_is_a_miss(self, tmp_path):
        req = cdc.Requirement(
            id="test_req", description="d", tier="FAIL", committed=True,
            path_template="bronze/thing/season={season}", seasons=(2099,),
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].tier == "FAIL"
        assert "test_req[2099]" == results[0].id

    def test_present_season_passes(self, tmp_path):
        _write_parquet(str(tmp_path / "data" / "bronze" / "thing" / "season=2099" / "f.parquet"))
        req = cdc.Requirement(
            id="test_req", description="d", tier="FAIL", committed=True,
            path_template="bronze/thing/season={season}", seasons=(2099,),
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert results[0].passed is True

    def test_min_files_floor(self, tmp_path):
        # Only 1 file present, but min_files=2 required
        _write_text(str(tmp_path / "data" / "adp" / "a.csv"))
        req = cdc.Requirement(
            id="adp_test", description="d", tier="WARN", committed=True,
            path_template="adp", glob="*.csv", min_files=2,
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert results[0].passed is False
        assert results[0].tier == "WARN"

    def test_min_rows_floor_catches_empty_file(self, tmp_path):
        # File exists (passes min_files) but has too few rows — the
        # "path exists, data doesn't" variant of the silent no-op.
        _write_parquet(
            str(tmp_path / "data" / "bronze" / "players" / "weekly" / "season=2020" / "f.parquet"),
            n_rows=3,
        )
        req = cdc.Requirement(
            id="weekly_test", description="d", tier="FAIL", committed=True,
            path_template="bronze/players/weekly/season={season}",
            seasons=(2020,), min_rows=100,
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert results[0].passed is False
        assert "row(s)" in results[0].message

    def test_min_rows_floor_passes_when_sufficient(self, tmp_path):
        _write_parquet(
            str(tmp_path / "data" / "bronze" / "players" / "weekly" / "season=2020" / "f.parquet"),
            n_rows=500,
        )
        req = cdc.Requirement(
            id="weekly_test", description="d", tier="FAIL", committed=True,
            path_template="bronze/players/weekly/season={season}",
            seasons=(2020,), min_rows=100,
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert results[0].passed is True

    def test_static_path_no_season_placeholder(self, tmp_path):
        _write_text(str(tmp_path / "data" / "external" / "a.json"))
        _write_text(str(tmp_path / "data" / "external" / "b.json"))
        _write_text(str(tmp_path / "data" / "external" / "c.json"))
        req = cdc.Requirement(
            id="ext", description="d", tier="WARN", committed=True,
            path_template="external", glob="*.json", min_files=3,
        )
        with _patch_data_root(tmp_path):
            results = cdc.check_requirement(req)
        assert len(results) == 1
        assert results[0].id == "ext"
        assert results[0].passed is True


# ---------------------------------------------------------------------------
# check_latest_weekly_gold — dynamic "current vintage" check
# ---------------------------------------------------------------------------

class TestCheckLatestWeeklyGold:
    def test_no_season_dirs_is_failure(self, tmp_path):
        with _patch_data_root(tmp_path):
            result = cdc.check_latest_weekly_gold()
        assert result.passed is False
        assert result.tier == "FAIL"

    def test_season_dir_with_no_week_dirs_is_failure(self, tmp_path):
        os.makedirs(str(tmp_path / "data" / "gold" / "projections" / "season=2025"))
        with _patch_data_root(tmp_path):
            result = cdc.check_latest_weekly_gold()
        assert result.passed is False

    def test_latest_week_empty_dir_is_failure(self, tmp_path):
        os.makedirs(str(tmp_path / "data" / "gold" / "projections" / "season=2025" / "week=10"))
        with _patch_data_root(tmp_path):
            result = cdc.check_latest_weekly_gold()
        assert result.passed is False

    def test_picks_max_season_and_max_week(self, tmp_path):
        # Older season/week present too — must pick the max of each.
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "season=2024" / "week=17" / "old.parquet"))
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "season=2025" / "week=5" / "mid.parquet"))
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "season=2025" / "week=18" / "new.parquet"))
        with _patch_data_root(tmp_path):
            result = cdc.check_latest_weekly_gold()
        assert result.passed is True
        assert "week=18" in result.message
        assert "season=2025" in result.message

    def test_preseason_dir_does_not_count_as_a_week(self, tmp_path):
        # "preseason" under season=2026 is not a week=* dir and must not
        # be mistaken for the weekly partition.
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "preseason" / "season=2026" / "s.parquet"))
        with _patch_data_root(tmp_path):
            result = cdc.check_latest_weekly_gold()
        # "preseason" sorts as a "season=*" glob miss (no "=" split match),
        # so with only the preseason dir present there are no real season
        # dirs and the check must fail rather than silently passing.
        assert result.passed is False


# ---------------------------------------------------------------------------
# run_checks — --local vs --ci filtering
# ---------------------------------------------------------------------------

class TestRunChecksModeFiltering:
    def test_ci_mode_skips_uncommitted_requirements(self, tmp_path):
        custom_reqs = (
            cdc.Requirement(
                id="shipped", description="d", tier="FAIL", committed=True,
                path_template="bronze/shipped/season={season}", seasons=(2020,),
            ),
            cdc.Requirement(
                id="local_only", description="d", tier="FAIL", committed=False,
                path_template="silver/local_only/season={season}", seasons=(2020,),
            ),
        )
        _write_parquet(str(tmp_path / "data" / "bronze" / "shipped" / "season=2020" / "f.parquet"))
        # local_only path deliberately NOT created — would fail if checked
        with _patch_data_root(tmp_path), mock.patch.object(cdc, "REQUIREMENTS", custom_reqs):
            ci_results = cdc.run_checks(ci_mode=True)
            local_results = cdc.run_checks(ci_mode=False)

        ci_ids = {r.id for r in ci_results}
        local_ids = {r.id for r in local_results}
        assert "local_only[2020]" not in ci_ids
        assert "local_only[2020]" in local_ids
        # local mode's uncommitted-but-missing entry should be a failure
        assert any(r.id == "local_only[2020]" and not r.passed for r in local_results)


# ---------------------------------------------------------------------------
# print_report — exit code aggregation
# ---------------------------------------------------------------------------

class TestPrintReportExitCode:
    def test_fail_tier_miss_exits_1(self, capsys):
        results = [cdc.CheckResult(id="a", tier="FAIL", passed=False, message="missing")]
        code = cdc.print_report(results, ci_mode=False)
        assert code == 1
        assert "FAIL" in capsys.readouterr().out

    def test_warn_tier_miss_exits_0(self, capsys):
        results = [cdc.CheckResult(id="a", tier="WARN", passed=False, message="missing")]
        code = cdc.print_report(results, ci_mode=False)
        assert code == 0
        out = capsys.readouterr().out
        assert "Overall: PASS" in out
        assert "WARN" in out

    def test_all_pass_exits_0(self, capsys):
        results = [
            cdc.CheckResult(id="a", tier="FAIL", passed=True, message="ok"),
            cdc.CheckResult(id="b", tier="WARN", passed=True, message="ok"),
        ]
        code = cdc.print_report(results, ci_mode=False)
        assert code == 0
        assert "Overall: PASS" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main() — end-to-end scenarios requested by the task spec:
# missing season -> FAIL, warn-tier -> exit 0, complete -> pass
# ---------------------------------------------------------------------------

class TestMainEndToEnd:
    def _small_manifest(self):
        return (
            cdc.Requirement(
                id="fail_thing", description="d", tier="FAIL", committed=True,
                path_template="bronze/fail_thing/season={season}", seasons=(2020, 2021),
            ),
            cdc.Requirement(
                id="warn_thing", description="d", tier="WARN", committed=True,
                path_template="gold/warn_thing", glob="*.csv", min_files=1,
            ),
        )

    def test_missing_fail_tier_season_exits_1(self, tmp_path, monkeypatch):
        reqs = self._small_manifest()
        # Only season=2020 present; 2021 is missing -> FAIL-tier miss.
        _write_parquet(str(tmp_path / "data" / "bronze" / "fail_thing" / "season=2020" / "f.parquet"))
        _write_text(str(tmp_path / "data" / "gold" / "warn_thing" / "w.csv"))
        with _patch_data_root(tmp_path), mock.patch.object(cdc, "REQUIREMENTS", reqs):
            with mock.patch("sys.argv", ["check_data_completeness.py", "--local"]):
                result = cdc.main()
        assert result == 1

    def test_missing_warn_tier_only_exits_0(self, tmp_path, monkeypatch):
        reqs = self._small_manifest()
        _write_parquet(str(tmp_path / "data" / "bronze" / "fail_thing" / "season=2020" / "f.parquet"))
        _write_parquet(str(tmp_path / "data" / "bronze" / "fail_thing" / "season=2021" / "f.parquet"))
        # run_checks() always appends the dynamic gold-weekly check too —
        # satisfy it so this test isolates the warn_thing miss.
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "season=2020" / "week=1" / "g.parquet"))
        # warn_thing deliberately absent — WARN-tier miss only.
        with _patch_data_root(tmp_path), mock.patch.object(cdc, "REQUIREMENTS", reqs):
            with mock.patch("sys.argv", ["check_data_completeness.py", "--local"]):
                result = cdc.main()
        assert result == 0

    def test_complete_manifest_passes(self, tmp_path, monkeypatch):
        reqs = self._small_manifest()
        _write_parquet(str(tmp_path / "data" / "bronze" / "fail_thing" / "season=2020" / "f.parquet"))
        _write_parquet(str(tmp_path / "data" / "bronze" / "fail_thing" / "season=2021" / "f.parquet"))
        _write_text(str(tmp_path / "data" / "gold" / "warn_thing" / "w.csv"))
        _write_parquet(str(tmp_path / "data" / "gold" / "projections" / "season=2020" / "week=1" / "g.parquet"))
        with _patch_data_root(tmp_path), mock.patch.object(cdc, "REQUIREMENTS", reqs):
            with mock.patch("sys.argv", ["check_data_completeness.py", "--ci"]):
                result = cdc.main()
        assert result == 0

    def test_local_and_ci_are_mutually_exclusive(self):
        with mock.patch("sys.argv", ["check_data_completeness.py", "--local", "--ci"]):
            with pytest.raises(SystemExit):
                cdc.main()

    def test_requires_a_mode(self):
        with mock.patch("sys.argv", ["check_data_completeness.py"]):
            with pytest.raises(SystemExit):
                cdc.main()


# ---------------------------------------------------------------------------
# Real manifest sanity — the REQUIREMENTS tuple itself must be well-formed
# ---------------------------------------------------------------------------

class TestRealManifestShape:
    def test_all_tiers_valid(self):
        for req in cdc.REQUIREMENTS:
            assert req.tier in ("FAIL", "WARN"), req.id

    def test_all_ids_unique(self):
        ids = [req.id for req in cdc.REQUIREMENTS]
        assert len(ids) == len(set(ids))

    def test_current_season_is_int(self):
        assert isinstance(cdc.CURRENT_SEASON, int)

    def test_player_seasons_nonempty(self):
        assert len(cdc.PLAYER_SEASONS) > 0
