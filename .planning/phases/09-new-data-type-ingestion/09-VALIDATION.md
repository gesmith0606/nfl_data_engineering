---
phase: 9
slug: new-data-type-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, 134 tests collected) |
| **Config file** | pytest runs from project root |
| **Quick run command** | `python -m pytest tests/test_advanced_ingestion.py tests/test_pbp_ingestion.py tests/test_bronze_validation.py -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_advanced_ingestion.py tests/test_pbp_ingestion.py tests/test_bronze_validation.py -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | INGEST-01 | unit | `pytest tests/test_advanced_ingestion.py -x -k "teams"` | Partial | ⬜ pending |
| 09-01-02 | 01 | 1 | INGEST-02 | unit | `pytest tests/test_advanced_ingestion.py -x -k "draft"` | ✅ | ⬜ pending |
| 09-01-03 | 01 | 1 | INGEST-03 | unit | `pytest tests/test_advanced_ingestion.py -x -k "combine"` | ✅ | ⬜ pending |
| 09-01-04 | 01 | 1 | INGEST-04 | unit | `pytest tests/test_advanced_ingestion.py -x -k "depth"` | ✅ | ⬜ pending |
| 09-02-01 | 02 | 1 | INGEST-05 | unit | `pytest tests/test_advanced_ingestion.py -x -k "qbr"` | Partial | ⬜ pending |
| 09-02-02 | 02 | 1 | INGEST-06 | unit | `pytest tests/test_advanced_ingestion.py -x -k "ngs"` | Partial | ⬜ pending |
| 09-02-03 | 02 | 1 | INGEST-07 | unit | `pytest tests/test_advanced_ingestion.py -x -k "pfr_weekly"` | Partial | ⬜ pending |
| 09-02-04 | 02 | 1 | INGEST-08 | unit | `pytest tests/test_advanced_ingestion.py -x -k "pfr_seasonal"` | Partial | ⬜ pending |
| 09-03-01 | 03 | 2 | INGEST-09 | unit | `pytest tests/test_pbp_ingestion.py -v -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Tests for "all variants by default" CLI behavior (NGS, PFR weekly, PFR seasonal, QBR)
- [ ] Tests for schema diff logging output
- [ ] Tests for ingestion summary output (ingested/skipped counts)
- [ ] Test for teams no-season path handling

*Existing infrastructure covers most requirements; Wave 0 fills gaps for new CLI behaviors.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PBP memory usage stays within bounds | INGEST-09 | Memory profiling not automatable in CI | Run `bronze_ingestion_simple.py --data-type pbp --season 2016` and monitor RSS via `top` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
