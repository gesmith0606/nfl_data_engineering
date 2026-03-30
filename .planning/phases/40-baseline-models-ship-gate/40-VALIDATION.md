---
phase: 40
slug: baseline-models-ship-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 40 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_player_model_training.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_player_model_training.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 40-01-01 | 01 | 1 | MODL-01 | unit | `python -m pytest tests/test_player_model_training.py -v` | ❌ W0 | ⬜ pending |
| 40-01-02 | 01 | 1 | MODL-02 | unit | `python -m pytest tests/test_player_model_training.py -v` | ❌ W0 | ⬜ pending |
| 40-01-03 | 01 | 1 | MODL-03 | unit | `python -m pytest tests/test_player_model_training.py -v` | ❌ W0 | ⬜ pending |
| 40-02-01 | 02 | 2 | MODL-04 | integration | `python -m pytest tests/test_player_ship_gate.py -v` | ❌ W0 | ⬜ pending |
| 40-02-02 | 02 | 2 | PIPE-01 | integration | `python -m pytest tests/test_player_ship_gate.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_player_model_training.py` — stubs for MODL-01, MODL-02, MODL-03
- [ ] `tests/test_player_ship_gate.py` — stubs for MODL-04, PIPE-01

*Existing test infrastructure (pytest, conftest) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Ship gate report readability | MODL-04 | Visual inspection of formatted output | Run `python scripts/train_player_models.py --report` and verify table formatting |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
