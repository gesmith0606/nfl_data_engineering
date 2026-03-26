---
phase: 30
slug: model-ensemble
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` (existing test infrastructure) |
| **Quick run command** | `python -m pytest tests/test_ensemble_training.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ensemble_training.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 30-01-01 | 01 | 1 | ENS-01 | unit | `python -m pytest tests/test_ensemble_training.py::test_lgb_training -v` | ❌ W0 | ⬜ pending |
| 30-01-02 | 01 | 1 | ENS-02 | unit | `python -m pytest tests/test_ensemble_training.py::test_oof_temporal -v` | ❌ W0 | ⬜ pending |
| 30-01-03 | 01 | 1 | ENS-03 | unit | `python -m pytest tests/test_ensemble_training.py::test_ridge_meta -v` | ❌ W0 | ⬜ pending |
| 30-02-01 | 02 | 2 | ENS-04 | integration | `python -m pytest tests/test_ensemble_training.py::test_backtest_ensemble -v` | ❌ W0 | ⬜ pending |
| 30-02-02 | 02 | 2 | ENS-05 | integration | `python -m pytest tests/test_ensemble_training.py::test_ensemble_artifacts -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ensemble_training.py` — stubs for ENS-01 through ENS-05
- [ ] Fixtures for synthetic feature matrices with known OOF predictions

*Existing infrastructure covers pytest, conftest.py, and XGBoost/LightGBM/CatBoost/sklearn dependencies.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
