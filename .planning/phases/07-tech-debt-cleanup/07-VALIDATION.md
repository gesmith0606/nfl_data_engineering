---
phase: 7
slug: tech-debt-cleanup
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-08
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.1 |
| **Config file** | none (pytest implicit) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | PBP-01–04 | manual-only | Visual inspection of SUMMARY frontmatter | N/A (already present) | ⬜ pending |
| 07-01-02 | 01 | 1 | INFRA-02 | unit | `python -m pytest tests/ -x -q -k max_season` | ✅ | ⬜ pending |
| 07-01-03 | 01 | 1 | VAL-01 | unit | `python -m pytest tests/ -x -q -k format_validation` | ✅ | ⬜ pending |
| 07-01-04 | 01 | 1 | INFRA-03 | unit | `python -m pytest tests/test_generate_inventory.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. No new test files needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SUMMARY frontmatter has requirements-completed field | PBP-01–04 | Doc metadata, not runtime behavior | Inspect `.planning/phases/02-core-pbp-ingestion/02-01-SUMMARY.md` frontmatter YAML |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
