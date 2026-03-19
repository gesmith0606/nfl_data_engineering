---
phase: 23
slug: cross-source-features-and-integration
status: draft
nyquist_compliant: true
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
| **Quick run command** | `python -m pytest tests/test_game_context.py tests/test_feature_vector.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_game_context.py tests/test_feature_vector.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | CROSS-01, CROSS-02 | unit | `python -m pytest tests/test_game_context.py --co -q 2>&1 \| grep -E "test_referee\|test_playoff\|test_unpivot_carries"` | Plan 01 Task 1 creates | pending |
| 23-01-02 | 01 | 1 | CROSS-01, CROSS-02 | unit | `python -m pytest tests/test_game_context.py -v -x` | Plan 01 Task 1 creates | pending |
| 23-02-01 | 02 | 2 | INTEG-01 | integration | `python -c "import glob; assert len(glob.glob('data/silver/teams/referee_tendencies/season=*/*.parquet')) >= 8"` | N/A (data gen) | pending |
| 23-02-02 | 02 | 2 | CROSS-01, CROSS-02, INTEG-01 | integration | `python -m pytest tests/test_feature_vector.py -v -x` | Plan 02 Task 2 creates | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_game_context.py` — add 8 new tests for referee tendencies and playoff context (Plan 01 Task 1)
- [ ] `tests/test_feature_vector.py` — NEW file for integration test (Plan 02 Task 2)
- [ ] Re-run `silver_team_transformation.py` to populate local pbp_derived parquet files (Plan 02 Task 1 prerequisite)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Standings spot-check vs published | CROSS-02 | Requires external reference data | Compare 2023 and 2024 division standings against pro-football-reference |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
