---
phase: 14
slug: bronze-cosmetic-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — uses defaults |
| **Quick run command** | `python -m pytest tests/ -v -x` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -v -x`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | SC-1 (player_weekly paths) | smoke | `test ! -d data/bronze/players/weekly/season=2016/week=0` | N/A (shell) | ⬜ pending |
| 14-01-02 | 01 | 1 | SC-1 (player_weekly files) | smoke | `ls data/bronze/players/weekly/season=2016/*.parquet` | N/A (shell) | ⬜ pending |
| 14-01-03 | 01 | 1 | SC-2 (draft_picks dedup) | smoke | `for d in data/bronze/draft_picks/season=*/; do echo $(ls $d/*.parquet \| wc -l) $d; done` | N/A (shell) | ⬜ pending |
| 14-01-04 | 01 | 1 | SC-3 (GITHUB_TOKEN docs) | manual | grep verification | N/A (manual) | ⬜ pending |
| 14-01-05 | 01 | 1 | regression | regression | `python -m pytest tests/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed — validation is filesystem inspection after script execution plus existing regression suite.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GITHUB_TOKEN docs accurate | SC-3 | Documentation text review | Grep planning docs for "GITHUB_TOKEN" and verify claims match reality (nfl-data-py does NOT use it) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
