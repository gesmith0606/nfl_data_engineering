---
phase: 42
slug: pipeline-integration-and-extensions
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-31
---

# Phase 42 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_ml_projection_router.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_ml_projection_router.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 42-01-01 | 01 | 1 | PIPE-02, PIPE-03 | unit | `python -m pytest tests/test_ml_projection_router.py -v` | ❌ W0 | ⬜ pending |
| 42-01-02 | 01 | 1 | PIPE-04 | unit | `python -m pytest tests/test_ml_projection_router.py -v` | ❌ W0 | ⬜ pending |
| 42-02-01 | 02 | 2 | EXTD-01 | integration | `python scripts/generate_projections.py --help` | ✅ | ⬜ pending |
| 42-02-02 | 02 | 2 | EXTD-02 | unit | `python -m pytest tests/test_ml_projection_router.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ml_projection_router.py` — stubs for PIPE-02, PIPE-03, PIPE-04, EXTD-02

*Existing test infrastructure (pytest, conftest) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end projection with --ml | PIPE-02 | Requires trained models + Silver data | Run `python scripts/generate_projections.py --week 10 --season 2024 --ml --scoring half_ppr` |
| Draft assistant consumes ML projections | PIPE-02 | Interactive CLI | Run draft_assistant.py with --projections-file pointing to ML output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
