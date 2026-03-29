---
phase: 39
slug: player-feature-vector-assembly
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-29
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ (existing) |
| **Quick run command** | `python -m pytest tests/test_player_feature_engineering.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds (new tests), ~120 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_player_feature_engineering.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 39-01-01 | 01 | 1 | FEAT-01 | unit | `python -m pytest tests/test_player_feature_engineering.py::test_assemble_player_features -v` | ❌ W0 | ⬜ pending |
| 39-01-02 | 01 | 1 | FEAT-02 | unit | `python -m pytest tests/test_player_feature_engineering.py::test_temporal_integrity -v` | ❌ W0 | ⬜ pending |
| 39-01-03 | 01 | 1 | FEAT-03 | unit | `python -m pytest tests/test_player_feature_engineering.py::test_matchup_features -v` | ❌ W0 | ⬜ pending |
| 39-01-04 | 01 | 1 | FEAT-04 | unit | `python -m pytest tests/test_player_feature_engineering.py::test_vegas_implied_totals -v` | ❌ W0 | ⬜ pending |
| 39-02-01 | 02 | 1 | FEAT-02 | integration | `python -m pytest tests/test_player_feature_engineering.py::test_leakage_detection -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_player_feature_engineering.py` — stubs for FEAT-01 through FEAT-04
- [ ] Test fixtures for mock Silver data (small DataFrames mimicking usage, advanced, defense schemas)

*Existing pytest infrastructure covers framework setup.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
