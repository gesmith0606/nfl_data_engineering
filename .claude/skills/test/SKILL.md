---
name: test
description: Run the NFL data engineering test suite. Use before committing code, after implementing new features, or when debugging failing tests. Runs pytest with coverage and reports results.
argument-hint: "[test-path-or-keyword]"
allowed-tools: Bash, Read, Grep
---

Run the project test suite and report results.

## Arguments
`$ARGUMENTS` — optional test path or keyword filter (e.g., `tests/test_utils.py` or `-k scoring`)

## Current test files
!`cd /Users/georgesmith/repos/nfl_data_engineering && find tests/ -name "*.py" 2>/dev/null | sort`

## Steps

### 1. Activate environment and run tests
If `$ARGUMENTS` is empty, run the full suite:
```bash
source venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1
```

If `$ARGUMENTS` specifies a path or keyword:
```bash
source venv/bin/activate && python -m pytest $ARGUMENTS -v --tb=short 2>&1
```

### 2. Run module-level smoke tests
```bash
source venv/bin/activate && python -c "
import sys
sys.path.insert(0, 'src')
modules = ['config', 'nfl_data_integration', 'player_analytics', 'scoring_calculator', 'projection_engine', 'draft_optimizer']
for m in modules:
    try:
        __import__(m)
        print(f'  OK: {m}')
    except Exception as e:
        print(f'  FAIL: {m} -> {e}')
"
```

### 3. Check for syntax errors in scripts
```bash
source venv/bin/activate && python -m py_compile \
  scripts/bronze_ingestion_simple.py \
  scripts/silver_player_transformation.py \
  scripts/generate_projections.py \
  scripts/draft_assistant.py && echo "All scripts compile OK"
```

### 4. Report
- Total tests: passed / failed / skipped
- Any failures: show the full traceback and suggest fixes
- If a module import fails, check for missing dependencies and run `pip install -r requirements.txt`
- If tests pass, confirm it's safe to commit

## Notes
- Always activate venv before running pytest
- Add `-x` flag to stop at first failure for debugging
- Use `--tb=long` for more detailed tracebacks
