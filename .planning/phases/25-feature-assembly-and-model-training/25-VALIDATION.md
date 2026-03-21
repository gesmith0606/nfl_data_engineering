---
phase: 25
slug: feature-assembly-and-model-training
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-20
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` directory (existing) |
| **Quick run command** | `python -m pytest tests/test_feature_engineering.py tests/test_model_training.py tests/test_train_cli.py -v --tb=short` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_feature_engineering.py tests/test_model_training.py tests/test_train_cli.py -v --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 25-01-01 | 01 | 1 | FEAT-01 | unit | `python -m pytest tests/test_feature_engineering.py::test_silver_to_game_join -v` | ❌ W0 | ⬜ pending |
| 25-01-02 | 01 | 1 | FEAT-02 | unit | `python -m pytest tests/test_feature_engineering.py::test_differential_features -v` | ❌ W0 | ⬜ pending |
| 25-01-03 | 01 | 1 | FEAT-02 | unit | `python -m pytest tests/test_feature_engineering.py::test_temporal_lag -v` | ❌ W0 | ⬜ pending |
| 25-01-04 | 01 | 1 | FEAT-04 | unit | `python -m pytest tests/test_feature_engineering.py::test_early_season_nan -v` | ❌ W0 | ⬜ pending |
| 25-02-01 | 02 | 2 | MODL-01 | unit | `python -m pytest tests/test_model_training.py::test_walk_forward_cv -v` | ❌ W0 | ⬜ pending |
| 25-02-02 | 02 | 2 | MODL-02 | unit | `python -m pytest tests/test_model_training.py::test_xgboost_spread_model -v` | ❌ W0 | ⬜ pending |
| 25-02-03 | 02 | 2 | MODL-03 | unit | `python -m pytest tests/test_model_training.py::test_xgboost_total_model -v` | ❌ W0 | ⬜ pending |
| 25-02-04 | 02 | 2 | MODL-05 | unit | `python -m pytest tests/test_model_training.py::test_conservative_defaults -v` | ❌ W0 | ⬜ pending |
| 25-02-05 | 02 | 2 | MODL-02 | unit | `python -m pytest tests/test_model_training.py::test_model_persistence -v` | ❌ W0 | ⬜ pending |
| 25-03-01 | 03 | 3 | MODL-04 | unit | `python -m pytest tests/test_train_cli.py::test_optuna_tuning -v` | ❌ W0 | ⬜ pending |
| 25-03-02 | 03 | 3 | FEAT-03 | unit | `python -m pytest tests/test_train_cli.py::test_feature_importance -v` | ❌ W0 | ⬜ pending |
| 25-03-03 | 03 | 3 | MODL-04 | integration | `python -m pytest tests/test_train_cli.py::test_cli_no_tune -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_feature_engineering.py` — stubs for FEAT-01, FEAT-02, FEAT-04
- [ ] `tests/test_model_training.py` — stubs for MODL-01 through MODL-03, MODL-05
- [ ] `tests/test_train_cli.py` — stubs for MODL-04, FEAT-03
- [ ] `tests/conftest.py` — shared fixtures (game data, Silver feature mocks)
- [ ] `xgboost>=2.1.4,<3.0` in requirements.txt — Python 3.9 compatible

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Feature importance report readability | FEAT-03 | Visual inspection of top-20 feature ranking output | Run `python scripts/train_prediction_model.py --target spread --no-tune`, verify console shows ranked features with scores |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
