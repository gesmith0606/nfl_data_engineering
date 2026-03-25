---
phase: 28
slug: infrastructure-player-features
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-24
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_feature_engineering.py tests/test_player_quality.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~25 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_feature_engineering.py tests/test_player_quality.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 25 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 28-01-01 | 01 | 1 | INFRA-01 | regression | `python -m pytest tests/test_feature_engineering.py -v` | ✅ | ⬜ pending |
| 28-01-02 | 01 | 1 | INFRA-02 | import | `python -c "import lightgbm, catboost, shap"` | ❌ W0 | ⬜ pending |
| 28-02-01 | 02 | 1 | PLAYER-01 | unit | `python -m pytest tests/test_player_quality.py -k qb_epa -v` | ❌ W0 | ⬜ pending |
| 28-02-02 | 02 | 1 | PLAYER-02 | unit | `python -m pytest tests/test_player_quality.py -k starter_detection -v` | ❌ W0 | ⬜ pending |
| 28-02-03 | 02 | 1 | PLAYER-03 | unit | `python -m pytest tests/test_player_quality.py -k injury_impact -v` | ❌ W0 | ⬜ pending |
| 28-02-04 | 02 | 1 | PLAYER-04 | unit | `python -m pytest tests/test_player_quality.py -k positional_quality -v` | ❌ W0 | ⬜ pending |
| 28-02-05 | 02 | 1 | PLAYER-05 | unit | `python -m pytest tests/test_player_quality.py -k lag_guard -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_player_quality.py` — stubs for PLAYER-01 through PLAYER-05
- [ ] Fixtures for synthetic player data (weekly stats, depth charts, injuries)

*Existing test infrastructure covers INFRA-01 (feature_engineering tests already exist).*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 25s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
