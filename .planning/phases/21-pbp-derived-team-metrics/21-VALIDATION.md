---
phase: 21
slug: pbp-derived-team-metrics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | tests/ directory |
| **Quick run command** | `python -m pytest tests/test_team_analytics.py -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_team_analytics.py -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | PBP-01 | unit | `pytest tests/test_team_analytics.py::test_compute_penalty_metrics -x` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | PBP-02 | unit | `pytest tests/test_team_analytics.py::test_compute_opp_drawn_penalties -x` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | PBP-03 | unit | `pytest tests/test_team_analytics.py::test_compute_turnover_luck -x` | ❌ W0 | ⬜ pending |
| 21-01-04 | 01 | 1 | PBP-04 | unit | `pytest tests/test_team_analytics.py::test_red_zone_trips -x` | ❌ W0 | ⬜ pending |
| 21-01-05 | 01 | 1 | PBP-05 | unit | `pytest tests/test_team_analytics.py::test_compute_fg_accuracy -x` | ❌ W0 | ⬜ pending |
| 21-01-06 | 01 | 1 | PBP-06 | unit | `pytest tests/test_team_analytics.py::test_compute_return_metrics -x` | ❌ W0 | ⬜ pending |
| 21-01-07 | 01 | 1 | PBP-07 | unit | `pytest tests/test_team_analytics.py::test_compute_third_down_rates -x` | ❌ W0 | ⬜ pending |
| 21-01-08 | 01 | 1 | PBP-08 | unit | `pytest tests/test_team_analytics.py::test_compute_explosive_plays -x` | ❌ W0 | ⬜ pending |
| 21-01-09 | 01 | 1 | PBP-09 | unit | `pytest tests/test_team_analytics.py::test_compute_drive_efficiency -x` | ❌ W0 | ⬜ pending |
| 21-01-10 | 01 | 1 | PBP-10 | unit | `pytest tests/test_team_analytics.py::test_compute_sack_rates -x` | ❌ W0 | ⬜ pending |
| 21-01-11 | 01 | 1 | PBP-11 | unit | `pytest tests/test_team_analytics.py::test_compute_top -x` | ❌ W0 | ⬜ pending |
| 21-02-01 | 02 | 1 | INTEG-02 | unit | `pytest tests/test_team_analytics.py::test_pbp_derived_rolling -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_team_analytics.py` — add 12 new test functions for all PBP-derived metrics
- [ ] Extend `_make_pbp_rows()` fixture with penalty, ST, fumble, drive, sack, and TOP fields

*Existing infrastructure covers framework and config — only test stubs needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
