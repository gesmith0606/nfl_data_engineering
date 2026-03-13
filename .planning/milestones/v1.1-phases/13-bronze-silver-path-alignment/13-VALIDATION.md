---
phase: 13
slug: bronze-silver-path-alignment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | none (pytest runs from root) |
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
| 13-01-01 | 01 | 1 | SC-1 | integration | `python -c "from scripts.silver_player_transformation import _read_local_bronze; df = _read_local_bronze('snap_counts', 2020); print(len(df))"` | No -- manual | ⬜ pending |
| 13-01-02 | 01 | 1 | SC-2 | integration | `python -c "from scripts.silver_player_transformation import _read_local_schedules; df = _read_local_schedules(2020); print(len(df))"` | No -- manual | ⬜ pending |
| 13-01-03 | 01 | 1 | SC-3 | unit | `python -m pytest tests/ -k snap -x` | No -- needs test | ⬜ pending |
| 13-01-04 | 01 | 1 | SC-4 | smoke | `test ! -d data/bronze/players/snap_counts` | No -- shell check | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- Existing infrastructure covers all phase requirements.
- Manual verification via Silver pipeline run is the primary validation: `python scripts/silver_player_transformation.py --season 2020`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Silver pipeline reads snap_counts from correct path | SC-1 | Integration requires running full pipeline | `python scripts/silver_player_transformation.py --season 2020` and verify no fallback to network |
| Silver pipeline reads schedules from correct path | SC-2 | Integration requires running full pipeline | `python scripts/silver_player_transformation.py --season 2020` and verify no fallback to network |
| Old snap_counts dir removed | SC-4 | Filesystem cleanup | `test ! -d data/bronze/players/snap_counts && echo PASS` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
