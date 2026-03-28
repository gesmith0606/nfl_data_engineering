---
phase: 33
slug: silver-line-movement-features
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, 516 tests passing) |
| **Config file** | tests/ directory, pytest standard discovery |
| **Quick run command** | `python -m pytest tests/test_market_analytics.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_market_analytics.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 33-01-01 | 01 | 1 | LINE-01 | unit | `python -m pytest tests/test_market_analytics.py::TestMovementComputation -x` | Wave 0 | pending |
| 33-01-02 | 01 | 1 | LINE-01 | unit | `python -m pytest tests/test_market_analytics.py::TestPerTeamReshape -x` | Wave 0 | pending |
| 33-01-03 | 01 | 1 | LINE-02 | unit | `python -m pytest tests/test_market_analytics.py::TestMagnitudeBuckets -x` | Wave 0 | pending |
| 33-01-04 | 01 | 1 | LINE-03 | unit | `python -m pytest tests/test_market_analytics.py::TestSteamMove -x` | Wave 0 | pending |
| 33-01-05 | 01 | 1 | D-09/D-10 | unit | `python -m pytest tests/test_market_analytics.py::TestKeyNumberCrossing -x` | Wave 0 | pending |
| 33-02-01 | 02 | 2 | LINE-01 | integration | `python -m pytest tests/test_feature_engineering.py -x -v -k market` | Wave 0 | pending |
| 33-02-02 | 02 | 2 | D-06 | integration | `python -m pytest tests/test_feature_engineering.py -x -v -k retrospective` | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_market_analytics.py` — covers LINE-01, LINE-02, LINE-03, D-09, D-10
- [ ] Additional tests in `tests/test_feature_engineering.py` — covers D-05, D-06, D-07 (market feature column filtering)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | — | — | — |

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
