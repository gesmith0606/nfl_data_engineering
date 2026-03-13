---
phase: 11
slug: orchestration-and-validation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-12
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ (existing) |
| **Quick run command** | `python -m pytest tests/test_batch_ingestion.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_batch_ingestion.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | ORCH-01 | unit | `python -m pytest tests/test_batch_ingestion.py -v -k "test_batch"` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | ORCH-02 | unit | `python -m pytest tests/test_batch_ingestion.py -v -k "test_failure"` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | VALID-01 | integration | `python scripts/validate_bronze.py --dry-run` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 2 | VALID-02 | integration | `python scripts/generate_inventory.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_batch_ingestion.py` — stubs for ORCH-01, ORCH-02

*Existing test infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Inventory markdown readable | VALID-02 | Visual formatting check | Open `docs/BRONZE_LAYER_DATA_INVENTORY.md` and verify 15 data types listed |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-12
