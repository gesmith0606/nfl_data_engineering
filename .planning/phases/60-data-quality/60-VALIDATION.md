---
phase: 60
slug: data-quality
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-17
---

# Phase 60 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` directory (existing) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 60-01-01 | 01 | 1 | DQAL-01 | — | N/A | unit | `python -m pytest tests/test_roster_refresh.py -v` | ❌ W0 | ⬜ pending |
| 60-01-02 | 01 | 1 | DQAL-02 | — | N/A | unit | `python -m pytest tests/test_roster_refresh.py -v` | ❌ W0 | ⬜ pending |
| 60-02-01 | 02 | 2 | DQAL-03 | — | N/A | integration | `python scripts/sanity_check_projections.py` | ✅ | ⬜ pending |
| 60-02-02 | 02 | 2 | DQAL-04 | — | N/A | integration | `python scripts/sanity_check_projections.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_roster_refresh.py` — stubs for DQAL-01, DQAL-02
- [ ] `tests/test_sanity_checks.py` — stubs for DQAL-03, DQAL-04

*Existing infrastructure covers test framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Top 10 alignment with consensus | DQAL-04 | Requires subjective expert judgment on "structural alignment" | Run sanity check, review top-10 per position against FantasyPros/Sleeper consensus |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
