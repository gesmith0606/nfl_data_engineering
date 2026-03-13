---
phase: 10
slug: existing-type-backfill
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | none (uses default discovery) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | BACKFILL-04 | unit | `python -m pytest tests/test_backfill.py::test_snap_counts_adapter_list -x` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | BACKFILL-04 | unit | `python -m pytest tests/test_backfill.py::test_snap_counts_week_partition -x` | ❌ W0 | ⬜ pending |
| 10-01-03 | 01 | 1 | BACKFILL-05 | unit | `python -m pytest tests/test_infrastructure.py::test_injury_season_cap -x` | ✅ | ⬜ pending |
| 10-01-04 | 01 | 1 | BACKFILL-01..06 | integration | Manual: run CLI then `validate_data()` on output | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_backfill.py` — stubs for snap_counts adapter fix (BACKFILL-04)
- [ ] Verify `tests/test_infrastructure.py` has injury cap test (BACKFILL-05)

*Existing infrastructure covers most phase requirements. Only snap counts adapter needs new test coverage.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| All backfilled files pass validate_data() | BACKFILL-01..06 | Requires actual data files from nfl-data-py | Run CLI for each type, then call `validate_data()` on output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
