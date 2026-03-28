---
phase: 34
slug: clv-tracking-ablation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `tests/` directory (existing) |
| **Quick run command** | `python -m pytest tests/test_prediction_backtester.py tests/test_ablation.py -v --tb=short` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~45 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_prediction_backtester.py tests/test_ablation.py -v --tb=short`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 34-01-01 | 01 | 1 | CLV-01 | unit | `python -m pytest tests/test_prediction_backtester.py -k "clv" -v` | ❌ W0 | ⬜ pending |
| 34-01-02 | 01 | 1 | CLV-02 | unit | `python -m pytest tests/test_prediction_backtester.py -k "clv_tier" -v` | ❌ W0 | ⬜ pending |
| 34-01-03 | 01 | 1 | CLV-01 | integration | `python scripts/backtest_predictions.py --ensemble --seasons 2022 --weeks 1-4` | ✅ | ⬜ pending |
| 34-02-01 | 02 | 2 | LINE-04 | unit | `python -m pytest tests/test_ablation.py -v` | ❌ W0 | ⬜ pending |
| 34-02-02 | 02 | 2 | LINE-04 | integration | `python scripts/ablation_market_features.py --dry-run` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Extend `tests/test_prediction_backtester.py` — CLV unit tests for `evaluate_clv()`, CLV by tier, CLV by season (Plan 34-01 Task 1 creates these)
- [ ] Create `tests/test_ablation.py` — unit tests for ablation orchestration logic, ship/skip decision, report format, copy semantics (Plan 34-02 Task 1 creates these)

*Existing test infrastructure covers framework install and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SHAP importance report readability | CLV-03 | Visual inspection of text table format | Run ablation script, check SHAP table in output has feature names + importance values sorted descending |
| Ship-or-skip decision documented | LINE-04 | One-time decision based on holdout results | After ablation completes, verify output report contains explicit "SHIP" or "SKIP" verdict with ATS comparison |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 45s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
