---
phase: 24
slug: documentation-refresh
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (installed in venv) |
| **Config file** | implicit (no pytest.ini, uses defaults) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** `python scripts/generate_inventory.py --output /dev/null` (DOCS-05 smoke test)
- **After every plan wave:** Visual review of all 5 documents against success criteria
- **Before `/gsd:verify-work`:** Full suite must be green + all 5 success criteria manually verified
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 24-01-01 | 01 | 1 | DOCS-01 | manual-only | N/A — documentation content review | N/A | ⬜ pending |
| 24-01-02 | 01 | 1 | DOCS-02 | manual-only | N/A — documentation content review | N/A | ⬜ pending |
| 24-02-01 | 02 | 1 | DOCS-03 | manual-only | N/A — documentation content review | N/A | ⬜ pending |
| 24-02-02 | 02 | 1 | DOCS-04 | manual-only | N/A — documentation content review | N/A | ⬜ pending |
| 24-02-03 | 02 | 1 | DOCS-05 | smoke | `python scripts/generate_inventory.py --output /dev/null` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. This is a documentation-only phase — no test infrastructure needed. The existing `scripts/generate_inventory.py` serves as the only automated verification tool and already exists.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Silver schemas in data dictionary | DOCS-01 | Pure markdown documentation — no behavioral code | Verify `docs/NFL_DATA_DICTIONARY.md` contains schema definitions for all 12 Silver output paths |
| Gold schemas in data dictionary | DOCS-02 | Pure markdown documentation — no behavioral code | Verify `docs/NFL_DATA_DICTIONARY.md` contains Gold layer prediction output schema section |
| CLAUDE.md accuracy | DOCS-03 | Pure markdown documentation — no behavioral code | Verify CLAUDE.md references 15 Bronze types, 12 Silver paths, 360 tests, v1.3 status |
| Implementation guide updated | DOCS-04 | Pure markdown documentation — no behavioral code | Verify `docs/NFL_DATA_MODEL_IMPLEMENTATION_GUIDE.md` shows phases 18-23 complete with status badges |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
