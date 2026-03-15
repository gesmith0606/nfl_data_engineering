---
phase: 18
slug: historical-context
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, 71 tests passing) |
| **Config file** | tests/ directory with existing conftest patterns |
| **Quick run command** | `python -m pytest tests/test_historical_profiles.py -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_historical_profiles.py -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 1 | HIST-01 | unit | `pytest tests/test_historical_profiles.py::test_compute_speed_score -x` | ❌ W0 | ⬜ pending |
| 18-01-02 | 01 | 1 | HIST-01 | unit | `pytest tests/test_historical_profiles.py::test_parse_height -x` | ❌ W0 | ⬜ pending |
| 18-01-03 | 01 | 1 | HIST-01 | unit | `pytest tests/test_historical_profiles.py::test_compute_burst_score -x` | ❌ W0 | ⬜ pending |
| 18-01-04 | 01 | 1 | HIST-01 | unit | `pytest tests/test_historical_profiles.py::test_position_percentiles -x` | ❌ W0 | ⬜ pending |
| 18-01-05 | 01 | 1 | HIST-01 | unit | `pytest tests/test_historical_profiles.py::test_dedup_combine -x` | ❌ W0 | ⬜ pending |
| 18-02-01 | 02 | 1 | HIST-02 | unit | `pytest tests/test_historical_profiles.py::test_jimmy_johnson_chart -x` | ❌ W0 | ⬜ pending |
| 18-02-02 | 02 | 1 | HIST-02 | unit | `pytest tests/test_historical_profiles.py::test_join_no_explosion -x` | ❌ W0 | ⬜ pending |
| 18-02-03 | 02 | 1 | HIST-02 | unit | `pytest tests/test_historical_profiles.py::test_draft_value_mapping -x` | ❌ W0 | ⬜ pending |
| 18-E2E | 02 | 2 | HIST-01+02 | integration | `pytest tests/test_historical_profiles.py::test_end_to_end -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_historical_profiles.py` — stubs for HIST-01, HIST-02
- [ ] No new framework install needed (pytest already configured)

*Existing infrastructure covers framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Match rate logging output | HIST-02 | Log inspection | Run pipeline, verify console shows match rate % and unmatched player list |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
