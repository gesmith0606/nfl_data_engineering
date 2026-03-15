---
phase: 17
slug: advanced-player-profiles
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (no pytest.ini; uses defaults) |
| **Quick run command** | `python -m pytest tests/test_player_advanced_analytics.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_player_advanced_analytics.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 0 | PROF-01..06 | unit | `pytest tests/test_player_advanced_analytics.py -x` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 1 | PROF-01 | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_receiving_profile -x` | ❌ W0 | ⬜ pending |
| 17-02-02 | 02 | 1 | PROF-02 | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_passing_profile -x` | ❌ W0 | ⬜ pending |
| 17-02-03 | 02 | 1 | PROF-03 | unit | `pytest tests/test_player_advanced_analytics.py::test_ngs_rushing_profile -x` | ❌ W0 | ⬜ pending |
| 17-03-01 | 03 | 1 | PROF-04 | unit | `pytest tests/test_player_advanced_analytics.py::test_pfr_pressure_rate -x` | ❌ W0 | ⬜ pending |
| 17-03-02 | 03 | 1 | PROF-05 | unit | `pytest tests/test_player_advanced_analytics.py::test_pfr_team_blitz_rate -x` | ❌ W0 | ⬜ pending |
| 17-04-01 | 04 | 1 | PROF-06 | unit | `pytest tests/test_player_advanced_analytics.py::test_qbr_rolling -x` | ❌ W0 | ⬜ pending |
| 17-05-01 | 05 | 2 | SC-4 | unit | `pytest tests/test_player_advanced_analytics.py::test_left_join_no_drops -x` | ❌ W0 | ⬜ pending |
| 17-05-02 | 05 | 2 | SC-5 | unit | `pytest tests/test_player_advanced_analytics.py::test_min_periods -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_player_advanced_analytics.py` — stubs for PROF-01 through PROF-06 + success criteria
- [ ] Test fixtures: synthetic NGS/PFR/QBR DataFrames with known values for rolling verification

*Existing infrastructure covers framework install (pytest already in venv).*

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
