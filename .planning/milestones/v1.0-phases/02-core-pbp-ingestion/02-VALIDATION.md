---
phase: 02
slug: core-pbp-ingestion
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-08
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing — no install needed) |
| **Config file** | none — uses defaults |
| **Quick run command** | `python -m pytest tests/test_pbp_ingestion.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_pbp_ingestion.py tests/test_infrastructure.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PBP-01 | unit | `python -m pytest tests/test_pbp_ingestion.py::test_pbp_columns_has_key_metrics -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PBP-02 | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_single_season_processing -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | PBP-03 | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_column_subsetting -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | PBP-04 | unit (mock) | `python -m pytest tests/test_pbp_ingestion.py::test_pbp_output_path -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pbp_ingestion.py` — stubs for PBP-01 through PBP-04 (new file)
- [ ] No framework install needed — pytest already available

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 16 seasons ingest end-to-end | PBP-04 | Requires nfl-data-py API calls (~15 min) | Run `for s in $(seq 2010 2025); do python scripts/bronze_ingestion_simple.py --data-type pbp --season $s; done` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
