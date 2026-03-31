---
phase: 41
slug: accuracy-improvements
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_player_accuracy.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_player_accuracy.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 41-01-01 | 01 | 1 | ACCY-01 | unit | `python -m pytest tests/test_player_accuracy.py -v` | ❌ W0 | ⬜ pending |
| 41-01-02 | 01 | 1 | ACCY-02 | unit | `python -m pytest tests/test_player_accuracy.py -v` | ❌ W0 | ⬜ pending |
| 41-01-03 | 01 | 1 | ACCY-03 | unit | `python -m pytest tests/test_player_accuracy.py -v` | ❌ W0 | ⬜ pending |
| 41-02-01 | 02 | 2 | ACCY-04 | integration | `python -m pytest tests/test_player_ensemble.py -v` | ❌ W0 | ⬜ pending |
| 41-02-02 | 02 | 2 | ACCY-04 | integration | `python scripts/train_player_models.py --dry-run` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_player_accuracy.py` — stubs for ACCY-01, ACCY-02, ACCY-03
- [ ] `tests/test_player_ensemble.py` — stubs for ACCY-04

*Existing test infrastructure (pytest, conftest) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Ship gate verdict improvement | ACCY-01-04 | Requires real data training | Run `python scripts/train_player_models.py --holdout-eval` and verify OOF improvement |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
