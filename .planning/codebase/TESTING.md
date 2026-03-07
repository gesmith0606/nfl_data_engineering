# Testing Patterns

**Analysis Date:** 2026-03-07

## Test Framework

**Runner:**
- `unittest` (Python standard library) -- no pytest config file, but pytest is used as the runner
- Config: No `pytest.ini`, `pyproject.toml`, or `setup.cfg` test configuration
- Python 3.9 compatibility maintained throughout

**Assertion Library:**
- `unittest.TestCase` built-in assertions (`assertEqual`, `assertAlmostEqual`, `assertIn`, `assertRaises`, `assertTrue`)

**Run Commands:**
```bash
source venv/bin/activate       # Required before all operations
python -m pytest tests/ -v     # Run all tests (71 tests)
python scripts/validate_project.py  # Project validation script
```

## Test File Organization

**Location:**
- Separate `tests/` directory at project root (not co-located with source)

**Naming:**
- Pattern: `tests/test_<source_module>.py`
- Each test file mirrors one source module

**Structure:**
```
tests/
├── __init__.py
├── test_utils.py                 # 5 tests  -> src/config.py, src/utils.py
├── test_scoring_calculator.py    # 14 tests -> src/scoring_calculator.py
├── test_player_analytics.py      # 7 tests  -> src/player_analytics.py
├── test_draft_optimizer.py       # 13 tests -> src/draft_optimizer.py
└── test_projection_engine.py     # 19 tests -> src/projection_engine.py
```

**Path setup (required in every test file):**
```python
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
```

## Test Structure

**Suite Organization:**
```python
"""
Unit tests for the Fantasy Scoring Calculator.
"""
import unittest
import sys
import os

import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from scoring_calculator import (
    calculate_fantasy_points,
    calculate_fantasy_points_df,
    get_scoring_config,
    list_scoring_formats,
)


class TestCalculateFantasyPoints(unittest.TestCase):
    """Test single-player fantasy point calculation."""

    def test_ppr_reception(self):
        """PPR awards 1.0 per reception."""
        pts = calculate_fantasy_points({'receptions': 5}, scoring_format='ppr')
        self.assertAlmostEqual(pts, 5.0)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            calculate_fantasy_points({'rushing_yards': 50}, scoring_format='nonexistent')


if __name__ == '__main__':
    unittest.main()
```

**Patterns:**
- Group tests by class, one class per public function or logical component
- Class names: `Test<FunctionOrComponent>` (e.g., `TestGetByeTeams`, `TestDraftBoard`, `TestComputeValueScores`)
- Test method names: `test_<behavior_description>` (e.g., `test_bye_teams_identified`, `test_out_player_zeroed`)
- Docstrings on tests that need clarification (e.g., `"""PPR awards 1.0 per reception."""`)
- No `setUp`/`tearDown` methods used -- helper methods used instead

**Setup pattern -- helper methods:**
```python
def _make_schedule(self):
    """Create minimal schedule DataFrame for testing."""
    return pd.DataFrame({
        'week': [1, 1, 1, 2, 2],
        'home_team': ['KC', 'BUF', 'DAL', 'KC', 'DAL'],
        'away_team': ['DET', 'MIA', 'NYG', 'BUF', 'MIA'],
    })
```

**Module-level helper functions** (used in `tests/test_draft_optimizer.py`):
```python
def _make_projections(n=20):
    """Build a small projections DataFrame for testing."""
    positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE'] * 3
    rows = []
    for i in range(n):
        pos = positions[i % len(positions)]
        rows.append({
            'player_id': f'p{i}',
            'player_name': f'Player {i}',
            'position': pos,
            'recent_team': ['KC', 'BUF', 'DAL', 'SF'][i % 4],
            'projected_season_points': 300.0 - i * 10,
        })
    return pd.DataFrame(rows)
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**
```python
from unittest.mock import Mock, patch

class TestUtils(unittest.TestCase):
    @patch('boto3.client')
    def test_validate_s3_path_valid(self, mock_boto_client):
        """Test S3 path validation with valid path"""
        mock_s3 = Mock()
        mock_s3.head_bucket.return_value = {}
        mock_boto_client.return_value = mock_s3

        result = validate_s3_path("s3://valid-bucket/path/")
        self.assertTrue(result)
```

**What to Mock:**
- AWS S3 client (`boto3.client`) -- always mock, never hit real AWS in tests
- External API calls (nfl-data-py fetches)

**What NOT to Mock:**
- Pure computation functions (scoring calculator, projection engine math)
- DataFrame operations (usage metrics, rolling averages, value scores)
- Internal helper functions -- test them directly even if private (`_rookie_baseline`, `_vegas_multiplier`)

## Fixtures and Factories

**Test Data:**
- Inline DataFrame construction using `pd.DataFrame({...})` -- no external fixture files
- Helper methods prefixed with `_make_` for reusable test data:
  - `_make_schedule()` -- minimal NFL schedule
  - `_make_weekly()` -- player weekly stats with 2 players on same team
  - `_make_multi_week()` -- 6 weeks of data for rolling average tests
  - `_make_projections(n=20)` -- projections with realistic position distribution
  - `_make_board()` -- DraftBoard with enriched projections
  - `_make_advisor()` -- DraftAdvisor wrapping a DraftBoard

**Data characteristics:**
- Use realistic NFL team abbreviations: 'KC', 'BUF', 'DAL', 'SF', 'DET', 'MIA', 'NYG'
- Use realistic stat ranges (e.g., passing_yards=275, rushing_yards=85, targets=8)
- Player IDs as simple strings: 'p0', 'p1', 'rb1', 'rb2'
- Player names as descriptive strings: 'Player A', 'Alpha', 'Test Player'

**Location:**
- All test data is inline within test files -- no shared fixtures directory
- No `conftest.py` file

## Coverage

**Requirements:** No formal coverage target enforced. No coverage config detected.

**View Coverage:**
```bash
python -m pytest tests/ --cov=src --cov-report=term-missing  # if pytest-cov installed
```

## Test Types

**Unit Tests (71 tests -- all tests are unit tests):**
- Pure function testing with constructed DataFrames
- No database, network, or filesystem dependencies (S3 calls are mocked)
- Test both happy path and edge cases (empty DataFrames, missing columns, invalid inputs)
- Verify numerical accuracy with `assertAlmostEqual`

**Integration Tests:**
- Not present as a formal test suite
- `scripts/validate_project.py` serves as a lightweight integration check
- `test_nfl_data_integration()` function exists in `src/nfl_data_integration.py` but is a manual script, not part of the test suite

**E2E Tests:**
- Not present. Pipeline validation is done via `scripts/check_pipeline_health.py` (manual)

## Common Patterns

**Testing computed values on DataFrames:**
```python
def test_target_share_computed(self):
    df = self._make_weekly()
    result = compute_usage_metrics(df)
    self.assertIn('target_share', result.columns)
    p1 = result[result['player_id'] == 'p1'].iloc[0]
    self.assertAlmostEqual(p1['target_share'], 8 / 12, places=2)
```

**Testing error raising:**
```python
def test_unknown_format_raises(self):
    with self.assertRaises(ValueError):
        calculate_fantasy_points({'rushing_yards': 50}, scoring_format='nonexistent')
```

**Testing empty/None input handling:**
```python
def test_empty_injuries(self):
    proj = self._make_projections()
    result = apply_injury_adjustments(proj, pd.DataFrame())
    self.assertTrue((result['injury_multiplier'] == 1.0).all())

def test_none_injuries(self):
    proj = self._make_projections()
    result = apply_injury_adjustments(proj, None)
    self.assertTrue((result['injury_multiplier'] == 1.0).all())
```

**Testing column existence:**
```python
def test_adds_model_rank(self):
    proj = _make_projections()
    result = compute_value_scores(proj)
    self.assertIn('model_rank', result.columns)
    self.assertEqual(result.iloc[0]['model_rank'], 1)
```

**Testing state mutations (DraftBoard):**
```python
def test_draft_player_removes_from_pool(self):
    board = self._make_board()
    board.draft_player('p0', by_me=True)
    self.assertEqual(len(board.available), 19)
    self.assertEqual(len(board.my_roster), 1)
```

## Test Distribution by Module

| Test File | Tests | What It Covers |
|-----------|-------|----------------|
| `tests/test_scoring_calculator.py` | 14 | PPR/Half/Standard scoring, DataFrame calc, custom scoring, edge cases, helpers |
| `tests/test_projection_engine.py` | 19 | Bye weeks, rookie baselines, usage roles, Vegas multiplier, weighted baseline, injury adjustments |
| `tests/test_draft_optimizer.py` | 13 | Value scores, DraftBoard state, DraftAdvisor recommendations, waiver wire |
| `tests/test_player_analytics.py` | 7 | Usage metrics, rolling averages, implied team totals |
| `tests/test_utils.py` | 5 | S3 path generation, S3 path validation |

## Modules Without Tests

- `src/nfl_data_integration.py` -- `NFLDataFetcher` class has no unit tests (has a manual `test_nfl_data_integration()` function but it hits real APIs)
- Scripts in `scripts/` -- no automated tests for CLI entry points

---

*Testing analysis: 2026-03-07*
