---
phase: 25
slug: feature-assembly-and-model-training
status: draft
nyquist_compliant: false
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
| **Quick run command** | `python -m pytest tests/test_feature_assembly.py tests/test_model_training.py -v --tb=short` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_feature_assembly.py tests/test_model_training.py -v --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 25-01-01 | 01 | 1 | FEAT-01 | unit | `python -m pytest tests/test_feature_assembly.py::test_silver_to_game_join -v` | ❌ W0 | ⬜ pending |
| 25-01-02 | 01 | 1 | FEAT-02 | unit | `python -m pytest tests/test_feature_assembly.py::test_differential_features -v` | ❌ W0 | ⬜ pending |
| 25-01-03 | 01 | 1 | FEAT-03 | unit | `python -m pytest tests/test_feature_assembly.py::test_lag_verification -v` | ❌ W0 | ⬜ pending |
| 25-01-04 | 01 | 1 | FEAT-04 | unit | `python -m pytest tests/test_feature_assembly.py::test_early_season_sparsity -v` | ❌ W0 | ⬜ pending |
| 25-02-01 | 02 | 2 | MODL-01 | unit | `python -m pytest tests/test_model_training.py::test_walk_forward_cv -v` | ❌ W0 | ⬜ pending |
| 25-02-02 | 02 | 2 | MODL-02 | unit | `python -m pytest tests/test_model_training.py::test_xgboost_spread_model -v` | ❌ W0 | ⬜ pending |
| 25-02-03 | 02 | 2 | MODL-03 | unit | `python -m pytest tests/test_model_training.py::test_xgboost_total_model -v` | ❌ W0 | ⬜ pending |
| 25-02-04 | 02 | 2 | MODL-04 | unit | `python -m pytest tests/test_model_training.py::test_model_persistence -v` | ❌ W0 | ⬜ pending |
| 25-02-05 | 02 | 2 | MODL-05 | unit | `python -m pytest tests/test_model_training.py::test_feature_importance -v` | ❌ W0 | ⬜ pending |
| 25-03-01 | 03 | 2 | MODL-01 | integration | `python scripts/train_prediction_model.py --target spread --dry-run` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_feature_assembly.py` — stubs for FEAT-01 through FEAT-04
- [ ] `tests/test_model_training.py` — stubs for MODL-01 through MODL-05
- [ ] `tests/conftest.py` — shared fixtures (game data, Silver feature mocks)
- [ ] `xgboost>=2.1.4,<3.0` in requirements.txt — Python 3.9 compatible

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Feature importance report readability | MODL-05 | Visual inspection of top-20 feature ranking output | Run CLI with `--importance` flag, verify report displays ranked features with scores |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
