---
phase: 26
slug: backtesting-and-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_backtest_predictions.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~65 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_backtest_predictions.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 65 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 26-01-01 | 01 | 1 | BACK-01 | unit+integration | `python -m pytest tests/test_backtest_predictions.py -v` | ❌ W0 | ⬜ pending |
| 26-02-01 | 02 | 2 | BACK-02, BACK-03 | unit+integration | `python -m pytest tests/test_backtest_predictions.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backtest_predictions.py` — stubs for BACK-01, BACK-02, BACK-03
- [ ] Shared fixtures for synthetic game data with spread_line/total_line

*Existing infrastructure (pytest, synthetic data patterns from test_model_training.py) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Console report readability | BACK-01 | Visual formatting | Run `python scripts/backtest_predictions.py` and confirm table alignment |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 65s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
