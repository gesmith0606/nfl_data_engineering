---
phase: 23
slug: cross-source-features-and-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-18
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_cross_source.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_cross_source.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | CROSS-01 | unit | `python -m pytest tests/test_cross_source.py::test_referee_normalization -v` | ❌ W0 | ⬜ pending |
| 23-01-02 | 01 | 1 | CROSS-01 | unit | `python -m pytest tests/test_cross_source.py::test_referee_penalty_rates -v` | ❌ W0 | ⬜ pending |
| 23-01-03 | 01 | 1 | CROSS-02 | unit | `python -m pytest tests/test_cross_source.py::test_standings_computation -v` | ❌ W0 | ⬜ pending |
| 23-01-04 | 01 | 1 | CROSS-02 | unit | `python -m pytest tests/test_cross_source.py::test_division_rank -v` | ❌ W0 | ⬜ pending |
| 23-02-01 | 02 | 2 | INTEG-01 | integration | `python -m pytest tests/test_cross_source.py::test_pipeline_health -v` | ❌ W0 | ⬜ pending |
| 23-02-02 | 02 | 2 | INTEG-01 | integration | `python -m pytest tests/test_cross_source.py::test_feature_vector_assembly -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_cross_source.py` — stubs for CROSS-01, CROSS-02, INTEG-01
- Existing infrastructure covers framework and fixtures

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Standings spot-check vs published | CROSS-02 | Requires external reference data | Compare 2023 and 2024 division standings against pro-football-reference |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
