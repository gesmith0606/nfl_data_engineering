---
phase: 32
slug: bronze-odds-ingestion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-27
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | none (default discovery) |
| **Quick run command** | `python -m pytest tests/test_bronze_odds.py -x -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_bronze_odds.py -x -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 32-01-01 | 01 | 1 | ODDS-01 | unit | `python -m pytest tests/test_bronze_odds.py::test_parse_finnedai -x` | Wave 0 | pending |
| 32-01-02 | 01 | 1 | ODDS-01 | unit | `python -m pytest tests/test_bronze_odds.py::test_download_idempotent -x` | Wave 0 | pending |
| 32-01-03 | 01 | 1 | ODDS-01 | unit | `python -m pytest tests/test_bronze_odds.py::test_sign_convention -x` | Wave 0 | pending |
| 32-01-04 | 01 | 1 | ODDS-01 | integration | `python -m pytest tests/test_bronze_odds.py::test_cross_validation_gate -x` | Wave 0 | pending |
| 32-01-05 | 01 | 1 | ODDS-01 | unit | `python -m pytest tests/test_bronze_odds.py::test_output_schema -x` | Wave 0 | pending |
| 32-02-01 | 01 | 1 | ODDS-02 | unit | `python -m pytest tests/test_bronze_odds.py::test_team_mapping_complete -x` | Wave 0 | pending |
| 32-02-02 | 01 | 1 | ODDS-02 | unit | `python -m pytest tests/test_bronze_odds.py::test_newyork_disambiguation -x` | Wave 0 | pending |
| 32-02-03 | 01 | 1 | ODDS-02 | unit | `python -m pytest tests/test_bronze_odds.py::test_corrupt_entries_dropped -x` | Wave 0 | pending |
| 32-02-04 | 01 | 1 | ODDS-02 | integration | `python -m pytest tests/test_bronze_odds.py::test_zero_orphans -x` | Wave 0 | pending |
| 32-03-01 | 02 | 1 | ODDS-03 | unit | `python -m pytest tests/test_bronze_odds.py::test_config_registration -x` | Wave 0 | pending |
| 32-03-02 | 02 | 1 | ODDS-03 | unit | `python -m pytest tests/test_bronze_odds.py::test_schema_validation -x` | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_bronze_odds.py` — covers ODDS-01, ODDS-02, ODDS-03
- [ ] Test fixtures: mock FinnedAI JSON subset (5-10 entries) and mock nflverse schedule DataFrame

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| FinnedAI repo accessible | ODDS-01 | Network availability | `curl -sI https://raw.githubusercontent.com/FinnedAI/sportsbookreview-scraper/main/data/nfl_archive_10Y.json` returns 200 |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
