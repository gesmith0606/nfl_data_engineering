---
phase: 03
slug: advanced-stats-context-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed) |
| **Config file** | None (default pytest discovery) |
| **Quick run command** | `python -m pytest tests/test_advanced_ingestion.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_advanced_ingestion.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | ADV-01 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestNGSIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-02 | 01 | 1 | ADV-02 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestPFRWeeklyIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-03 | 01 | 1 | ADV-03 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestPFRSeasonalIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-04 | 01 | 1 | ADV-04 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestQBRIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-05 | 01 | 1 | ADV-05 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestDepthChartsIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-06 | 01 | 1 | CTX-01 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestDraftPicksIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-07 | 01 | 1 | CTX-02 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestCombineIngestion -x` | No -- Wave 0 | ⬜ pending |
| 03-01-08 | 01 | 1 | VAL-01 | unit | `python -m pytest tests/test_advanced_ingestion.py::TestValidation -x` | No -- Wave 0 | ⬜ pending |
| 03-01-09 | 01 | 1 | VAL-02 | unit | Covered by existing `tests/test_infrastructure.py` | Yes | ⬜ pending |
| 03-01-10 | 01 | 1 | VAL-03 | unit | `python -m pytest tests/test_advanced_ingestion.py -v` | No -- Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_advanced_ingestion.py` -- stubs for ADV-01 through ADV-05, CTX-01, CTX-02, VAL-01, VAL-03
- No framework install needed -- pytest already available
- No conftest needed -- tests are self-contained with unittest.mock

*Existing infrastructure covers VAL-02 (adapter error handling).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
