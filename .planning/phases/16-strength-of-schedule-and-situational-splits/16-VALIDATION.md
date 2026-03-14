---
phase: 16
slug: strength-of-schedule-and-situational-splits
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | `tests/` directory convention (no pytest.ini) |
| **Quick run command** | `python -m pytest tests/test_team_analytics.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_team_analytics.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 0 | SOS-01 | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_week1_adj_equals_raw -x` | ❌ W0 | ⬜ pending |
| 16-01-02 | 01 | 0 | SOS-01 | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_lagged_opponent_adjustment -x` | ❌ W0 | ⬜ pending |
| 16-01-03 | 01 | 0 | SOS-02 | unit | `python -m pytest tests/test_team_analytics.py::TestSOS::test_sos_ranking -x` | ❌ W0 | ⬜ pending |
| 16-01-04 | 01 | 0 | SIT-01 | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_home_away_split -x` | ❌ W0 | ⬜ pending |
| 16-01-05 | 01 | 0 | SIT-02 | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_divisional_tagging -x` | ❌ W0 | ⬜ pending |
| 16-01-06 | 01 | 0 | SIT-03 | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_game_script_split -x` | ❌ W0 | ⬜ pending |
| 16-01-07 | 01 | 0 | ALL | unit | `python -m pytest tests/test_team_analytics.py::TestSituational::test_rolling_on_splits -x` | ❌ W0 | ⬜ pending |
| 16-01-08 | 01 | 0 | ALL | unit | `python -m pytest tests/test_team_analytics.py::TestIdempotency -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_team_analytics.py` — add TestSOS, TestSituational, TestIdempotency classes
- [ ] Test fixture: multi-team multi-week PBP with home/away, divisional opponents, and varied score differentials

*Existing infrastructure covers framework and conftest needs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
