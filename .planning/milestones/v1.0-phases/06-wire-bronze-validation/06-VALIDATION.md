---
phase: 6
slug: wire-bronze-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | tests/ directory, no pytest.ini (uses defaults) |
| **Quick run command** | `python -m pytest tests/test_bronze_validation.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_bronze_validation.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | VAL-01-wire | unit | `python -m pytest tests/test_bronze_validation.py::TestAdapterValidation -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 0 | VAL-01-call | unit | `python -m pytest tests/test_bronze_validation.py::TestIngestionValidation -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 0 | VAL-01-output-pass | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_pass_output -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 0 | VAL-01-output-warn | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_warn_output -x` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 0 | VAL-01-no-block | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_save_after_warning -x` | ❌ W0 | ⬜ pending |
| 06-01-06 | 01 | 0 | VAL-01-silent | unit | `python -m pytest tests/test_bronze_validation.py::TestValidationOutput::test_silent_skip -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_bronze_validation.py` — stubs for all VAL-01 behaviors (6 tests)
- No framework install needed — pytest already present and configured

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
