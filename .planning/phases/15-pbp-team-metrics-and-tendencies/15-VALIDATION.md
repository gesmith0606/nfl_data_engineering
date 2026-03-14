---
phase: 15
slug: pbp-team-metrics-and-tendencies
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | none — pytest runs from project root |
| **Quick run command** | `python -m pytest tests/test_team_analytics.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_team_analytics.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 0 | PBP-05 | unit | `python -m pytest tests/test_player_analytics.py::TestRollingSeasonFix -v` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 0 | PBP-01 | unit | `python -m pytest tests/test_team_analytics.py::TestEPA -v` | ❌ W0 | ⬜ pending |
| 15-01-03 | 01 | 0 | PBP-02 | unit | `python -m pytest tests/test_team_analytics.py::TestSuccessRate -v` | ❌ W0 | ⬜ pending |
| 15-01-04 | 01 | 0 | PBP-03 | unit | `python -m pytest tests/test_team_analytics.py::TestCPOE -v` | ❌ W0 | ⬜ pending |
| 15-01-05 | 01 | 0 | PBP-04 | unit | `python -m pytest tests/test_team_analytics.py::TestRedZone -v` | ❌ W0 | ⬜ pending |
| 15-01-06 | 01 | 0 | TEND-01 | unit | `python -m pytest tests/test_team_analytics.py::TestPace -v` | ❌ W0 | ⬜ pending |
| 15-01-07 | 01 | 0 | TEND-02 | unit | `python -m pytest tests/test_team_analytics.py::TestPROE -v` | ❌ W0 | ⬜ pending |
| 15-01-08 | 01 | 0 | TEND-03 | unit | `python -m pytest tests/test_team_analytics.py::TestFourthDown -v` | ❌ W0 | ⬜ pending |
| 15-01-09 | 01 | 0 | TEND-04 | unit | `python -m pytest tests/test_team_analytics.py::TestEarlyDownRunRate -v` | ❌ W0 | ⬜ pending |
| 15-01-10 | 01 | 0 | INFRA-01 | unit | `python -m pytest tests/test_team_analytics.py::TestConfig -v` | ❌ W0 | ⬜ pending |
| 15-01-11 | 01 | 0 | INFRA-02 | smoke | `python scripts/silver_team_transformation.py --help` | ❌ W0 | ⬜ pending |
| 15-01-12 | 01 | 0 | INFRA-03 | unit | `python -m pytest tests/test_team_analytics.py::TestOutput -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_team_analytics.py` — stubs for PBP-01 through TEND-04, INFRA-01, INFRA-03
- [ ] Add cross-season rolling test to `tests/test_player_analytics.py` for PBP-05 fix validation

*Existing pytest infrastructure covers framework requirements.*

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
