---
phase: 12
slug: 2025-player-stats-gap-closure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (pytest runs from project root) |
| **Quick run command** | `python -m pytest tests/test_stats_player.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_stats_player.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 0 | BACKFILL-02 | unit | `python -m pytest tests/test_stats_player.py -x -q` | ❌ W0 | ⬜ pending |
| 12-01-02 | 01 | 1 | BACKFILL-02 | unit | `python -m pytest tests/test_stats_player.py::test_column_mapping -x` | ❌ W0 | ⬜ pending |
| 12-01-03 | 01 | 1 | BACKFILL-02 | unit | `python -m pytest tests/test_stats_player.py::test_conditional_routing -x` | ❌ W0 | ⬜ pending |
| 12-01-04 | 01 | 1 | BACKFILL-02 | unit | `python -m pytest tests/test_stats_player.py::test_weekly_validation -x` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 1 | BACKFILL-03 | unit | `python -m pytest tests/test_stats_player.py::test_seasonal_aggregation -x` | ❌ W0 | ⬜ pending |
| 12-02-02 | 02 | 1 | BACKFILL-03 | unit | `python -m pytest tests/test_stats_player.py::test_seasonal_validation -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_stats_player.py` — stubs for BACKFILL-02, BACKFILL-03 (column mapping, routing, aggregation, validation)
- [ ] Test fixtures: mock DataFrame with stats_player schema (115 columns) for unit tests without network

*Existing infrastructure covers pytest framework — only new test file needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Silver pipeline processes 2025 data | BACKFILL-02/03 | Requires full pipeline run with real data | Run `python scripts/silver_player_transformation.py --seasons 2025` and verify no errors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
