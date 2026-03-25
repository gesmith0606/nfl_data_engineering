---
phase: 29
slug: feature-selection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 29 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` (existing test infrastructure) |
| **Quick run command** | `python -m pytest tests/test_feature_selector.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_feature_selector.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 29-01-01 | 01 | 1 | FSEL-01 | unit | `python -m pytest tests/test_feature_selector.py::test_feature_selection_result_dataclass -v` | ❌ W0 | ⬜ pending |
| 29-01-02 | 01 | 1 | FSEL-02 | unit | `python -m pytest tests/test_feature_selector.py::test_correlation_filter -v` | ❌ W0 | ⬜ pending |
| 29-01-03 | 01 | 1 | FSEL-03 | unit | `python -m pytest tests/test_feature_selector.py::test_per_fold_selection -v` | ❌ W0 | ⬜ pending |
| 29-01-04 | 01 | 1 | FSEL-04 | unit | `python -m pytest tests/test_feature_selector.py::test_holdout_exclusion -v` | ❌ W0 | ⬜ pending |
| 29-02-01 | 02 | 2 | FSEL-01 | integration | `python -m pytest tests/test_feature_selector.py::test_cv_validated_cutoff -v` | ❌ W0 | ⬜ pending |
| 29-02-02 | 02 | 2 | FSEL-01 | integration | `python -m pytest tests/test_feature_selector.py::test_end_to_end_selection -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_feature_selector.py` — stubs for FSEL-01 through FSEL-04
- [ ] Fixtures for synthetic feature matrices with known correlations and SHAP values

*Existing infrastructure covers pytest, conftest.py, and XGBoost/SHAP dependencies.*

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
