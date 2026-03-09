---
phase: 8
slug: pre-backfill-guards
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | none (uses defaults) |
| **Quick run command** | `python -m pytest tests/test_infrastructure.py -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_infrastructure.py -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | SETUP-01 | unit | `python -m pytest tests/test_infrastructure.py::TestDynamicSeasonValidation::test_injury_season_capped_at_2024 -x` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | SETUP-01 | unit | `python -m pytest tests/test_infrastructure.py::TestDynamicSeasonValidation::test_validate_edge_max_year -x` | ✅ (needs update) | ⬜ pending |
| 08-01-03 | 01 | 1 | SETUP-02 | manual-only | Manual: `grep GITHUB_TOKEN .env` | N/A | ⬜ pending |
| 08-01-04 | 01 | 1 | SETUP-03 | manual-only | Manual: `grep -E 'nfl_data_py\|numpy' requirements.txt` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_infrastructure.py::test_injury_season_capped_at_2024` — stub for SETUP-01
- [ ] Update `tests/test_infrastructure.py::test_validate_edge_max_year` — exclude static-cap types to prevent false failure

*Existing infrastructure covers SETUP-02 and SETUP-03 (manual verifications on config files).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GITHUB_TOKEN present in .env | SETUP-02 | Config file, not testable code behavior | `grep GITHUB_TOKEN .env` returns a line |
| Dependency pins have explanatory comments | SETUP-03 | Comment presence in requirements.txt | `grep -A1 'nfl_data_py\|numpy' requirements.txt` shows comments |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
