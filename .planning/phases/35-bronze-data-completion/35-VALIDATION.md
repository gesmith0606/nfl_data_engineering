---
phase: 35
slug: bronze-data-completion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` directory |
| **Quick run command** | `python -m pytest tests/test_bronze_odds.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_bronze_odds.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 35-01-T1 | 01 | 1 | BRNZ-02 | unit | `python -m pytest tests/test_bronze_odds.py::TestNflverseBridgeSchema -x` | W0 | pending |
| 35-01-T2 | 01 | 1 | BRNZ-02 | unit | `python -m pytest tests/test_bronze_odds.py::TestNflverseCoverage -x` | W0 | pending |
| 35-01-T3 | 01 | 1 | BRNZ-02 | unit | `python -m pytest tests/test_bronze_odds.py::TestNflversePlayoffCoverage -x` | W0 | pending |
| 35-01-T4 | 01 | 1 | BRNZ-01 | unit | `python -m pytest tests/test_bronze_odds.py::TestLineSourceColumn -x` | W0 | pending |
| 35-01-T5 | 01 | 1 | BRNZ-01 | integration | `python scripts/bronze_odds_ingestion.py --season 2016` | Exists | pending |
| 35-02-T1 | 02 | 1 | BRNZ-03 | smoke | `python -m pytest tests/test_bronze_odds.py -x -v` + ls check | Manual | pending |

---

## Wave 0 Requirements

- [ ] `tests/test_bronze_odds.py::TestNflverseBridgeSchema` — verify nflverse bridge output matches FinnedAI schema
- [ ] `tests/test_bronze_odds.py::TestNflverseCoverage` — verify coverage checks (D-10)
- [ ] `tests/test_bronze_odds.py::TestNflversePlayoffCoverage` — verify playoff coverage (D-11)
- [ ] `tests/test_bronze_odds.py::TestLineSourceColumn` — verify line_source provenance column (D-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 2025 Bronze data completeness | BRNZ-03 | Requires live nfl-data-py API call | Run `ls data/bronze/*/season=2025/` and verify 7 data types present |
| FinnedAI per-season cross-validation | BRNZ-01 | Script prints r-value during execution | Run each season and verify `r > 0.95` in output |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
