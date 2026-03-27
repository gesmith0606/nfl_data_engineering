---
phase: 31
slug: advanced-features-final-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-25
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_advanced_features.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~35 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_advanced_features.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 31-01-01 | 01 | 1 | ADV-01 | unit | `python -m pytest tests/test_advanced_features.py -x -v -k "momentum"` | ❌ W0 | ⬜ pending |
| 31-01-02 | 01 | 1 | ADV-02 | unit | `python -m pytest tests/test_advanced_features.py -x -v -k "ewm"` | ❌ W0 | ⬜ pending |
| 31-02-01 | 02 | 2 | ADV-03 | integration | `python -m pytest tests/test_advanced_features.py -x -v -k "holdout"` | ❌ W0 | ⬜ pending |
| 31-02-02 | 02 | 2 | ADV-03 | integration | `python scripts/backtest_predictions.py --help` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_advanced_features.py` — stubs for ADV-01, ADV-02, ADV-03
- [ ] Synthetic data fixtures for momentum and EWM feature testing

*Existing test infrastructure (pytest, conftest) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Final holdout comparison table readability | ADV-03 | Visual output formatting | Run `python scripts/backtest_predictions.py --holdout --ensemble` and verify table columns align |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 35s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
