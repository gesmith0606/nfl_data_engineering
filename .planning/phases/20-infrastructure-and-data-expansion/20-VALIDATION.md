---
phase: 20
slug: infrastructure-and-data-expansion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (latest via pip) |
| **Config file** | None (default discovery) |
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
| 20-01-01 | 01 | 1 | INFRA-01 | unit | `python -m pytest tests/test_infrastructure.py -x -k "pbp_columns"` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | INFRA-01 | smoke | `python -c "import pandas as pd; df = pd.read_parquet('data/bronze/pbp/season=2024/'); assert 'penalty_type' in df.columns"` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | INFRA-01 | regression | `python -m pytest tests/ -v` | ✅ (289 tests) | ⬜ pending |
| 20-02-01 | 02 | 1 | INFRA-02 | unit | `python -m pytest tests/test_infrastructure.py -x -k "officials"` | ❌ W0 | ⬜ pending |
| 20-02-02 | 02 | 1 | INFRA-02 | smoke | `python -c "import pandas as pd; df = pd.read_parquet('data/bronze/officials/season=2024/'); assert len(df) > 0"` | ❌ W0 | ⬜ pending |
| 20-03-01 | 02 | 1 | INFRA-03 | unit | `python -m pytest tests/test_infrastructure.py -x -k "stadium"` | ❌ W0 | ⬜ pending |
| 20-03-02 | 02 | 1 | INFRA-03 | unit | `python -m pytest tests/test_infrastructure.py -x -k "haversine"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_infrastructure.py` — stubs for INFRA-01 (PBP column count, column presence), INFRA-02 (officials schema, registry entry), INFRA-03 (stadium coordinates, haversine sanity check)
- [ ] No new fixtures needed — tests import from `src/config.py` directly and read Bronze parquet files

*Existing infrastructure (pytest, 289 tests) covers regression requirement.*

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
