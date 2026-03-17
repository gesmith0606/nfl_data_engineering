---
phase: 22
slug: schedule-derived-context
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pytest runs from project root |
| **Quick run command** | `python -m pytest tests/test_game_context.py -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_game_context.py -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | SCHED-01 | unit | `python -m pytest tests/test_game_context.py::test_weather_features -x` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | SCHED-01 | unit | `python -m pytest tests/test_game_context.py::test_weather_nan_handling -x` | ❌ W0 | ⬜ pending |
| 22-01-03 | 01 | 1 | SCHED-02 | unit | `python -m pytest tests/test_game_context.py::test_rest_features -x` | ❌ W0 | ⬜ pending |
| 22-01-04 | 01 | 1 | SCHED-03 | unit | `python -m pytest tests/test_game_context.py::test_travel_distance -x` | ❌ W0 | ⬜ pending |
| 22-01-05 | 01 | 1 | SCHED-04 | unit | `python -m pytest tests/test_game_context.py::test_timezone_diff -x` | ❌ W0 | ⬜ pending |
| 22-01-06 | 01 | 1 | SCHED-05 | unit | `python -m pytest tests/test_game_context.py::test_coaching_features -x` | ❌ W0 | ⬜ pending |
| 22-01-07 | 01 | 1 | ALL | unit | `python -m pytest tests/test_game_context.py::test_unpivot -x` | ❌ W0 | ⬜ pending |
| 22-02-01 | 02 | 2 | ALL | integration | `python -m pytest tests/test_game_context.py::test_game_context_e2e -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_game_context.py` — stubs for SCHED-01 through SCHED-05
- [ ] No framework install needed (pytest already configured)

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
