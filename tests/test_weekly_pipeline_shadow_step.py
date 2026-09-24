"""YAML-structure tests for the early-season-prior SHADOW run in
``.github/workflows/weekly-pipeline.yml`` (2026 weeks 3-6, user-approved;
protocol in ``.planning/EARLY_SEASON_PRIOR_GATE.md`` "Shadow run").

Invariants protected:
  - the shadow step runs after production Gold, is non-blocking, and is
    gated to weeks 3-6;
  - it mirrors the prod command (+ ``--early-season-prior``) but writes via
    ``--shadow-tag`` so it can never land in ``data/gold/projections/``;
  - the Gold commit step ships ``data/gold/projections_shadow/`` and
    ``.gitignore`` allowlists it (TD-08/09/10 pattern);
  - the shadow grading step is fail-open and gated to graded weeks 3-6.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(".github/workflows/weekly-pipeline.yml")
SHADOW_STEP = "Gold — SHADOW early-season-prior board (weeks 3-6, not published)"
GRADE_STEP = "Shadow grading — early-season prior (previous week)"


@pytest.fixture(scope="module")
def steps() -> list:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = next(j for j in doc["jobs"].values() if "gold_projections" in str(j))
    return job["steps"]


def _step(steps: list, name: str) -> dict:
    return next(s for s in steps if s.get("name") == name)


def _index(steps: list, pred) -> int:
    return next(i for i, s in enumerate(steps) if pred(s))


def test_prod_step_exports_mode(steps: list) -> None:
    prod = next(s for s in steps if s.get("id") == "gold_projections")
    assert 'echo "mode=ml" >> "$GITHUB_OUTPUT"' in prod["run"]
    assert 'echo "mode=heuristic" >> "$GITHUB_OUTPUT"' in prod["run"]


def test_shadow_step_after_prod_and_non_blocking(steps: list) -> None:
    shadow = _step(steps, SHADOW_STEP)
    assert shadow["continue-on-error"] is True
    assert shadow["if"] == "steps.gold_projections.outcome == 'success'"
    assert shadow["env"]["PROD_MODE"] == "${{ steps.gold_projections.outputs.mode }}"
    prod_i = _index(steps, lambda s: s.get("id") == "gold_projections")
    shadow_i = _index(steps, lambda s: s.get("name") == SHADOW_STEP)
    commit_i = _index(steps, lambda s: s.get("id") == "commit_gold")
    assert prod_i < shadow_i < commit_i
    assert "::warning::" in shadow["run"]


def test_shadow_step_command(steps: list) -> None:
    run = _step(steps, SHADOW_STEP)["run"]
    assert '[ "$WEEK" -lt 3 ] || [ "$WEEK" -gt 6 ]' in run
    assert "scripts/generate_projections.py" in run
    assert "--early-season-prior" in run
    assert "--shadow-tag early_season_prior" in run
    assert "--scoring half_ppr" in run
    assert 'if [ "$PROD_MODE" = "ml" ]; then ML_FLAG="--ml"; fi' in run
    # never an explicit write into the prod serving path
    assert "data/gold/projections/" not in run


def test_commit_step_ships_shadow_boards(steps: list) -> None:
    commit = next(s for s in steps if s.get("id") == "commit_gold")
    assert "git add data/gold/projections_shadow/" in commit["run"]
    assert "git add data/gold/projections/ " in commit["run"]


def test_gitignore_allowlists_shadow_path() -> None:
    lines = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    for pattern in (
        "!data/gold/projections_shadow/",
        "!data/gold/projections_shadow/**",
        "!data/gold/projections_shadow/**/*.parquet",
    ):
        assert pattern in lines
    assert lines.index("!data/gold/projections_shadow/") > lines.index("data/gold/*")


def test_shadow_grading_step(steps: list) -> None:
    grade = _step(steps, GRADE_STEP)
    assert grade["continue-on-error"] is True
    run = grade["run"]
    assert '[ "$GRADE_WEEK" -lt 3 ] || [ "$GRADE_WEEK" -gt 6 ]' in run
    assert "scripts/grade_shadow.py" in run
    assert "--shadow-tag early_season_prior" in run
    assert "output/grading" in run
    assert "::warning::" in run
    elite_i = _index(steps, lambda s: s.get("id") == "elite_grading")
    grade_i = _index(steps, lambda s: s.get("name") == GRADE_STEP)
    assert grade_i == elite_i + 1
