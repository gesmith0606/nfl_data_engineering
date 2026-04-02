---
phase: 44
slug: neo4j-phase1-injury-cascade
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-01
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_graph_features.py -v` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_graph_features.py -v`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 44-01-01 | 01 | 1 | NEO4J-01 | unit | `python -m pytest tests/test_graph_features.py::TestGraphDB -v` | Yes | passed |
| 44-01-02 | 01 | 1 | NEO4J-02, NEO4J-03 | unit | `python -m pytest tests/test_graph_features.py::TestInjuryCascade -v` | Yes | passed |
| 44-01-03 | 01 | 1 | NEO4J-04, NEO4J-05 | unit | `python -m pytest tests/test_graph_features.py::TestFeatureExtraction -v` | Yes | passed |
| 44-01-04 | 01 | 1 | NEO4J-06 | integration | `python scripts/graph_ingestion.py --help` | Yes | passed |
| 44-01-05 | 01 | 1 | NEO4J-04 | unit | `python -m pytest tests/test_graph_features.py::TestIntegration -v` | Yes | passed |

*Status: passed*

---

## Outstanding Validation Gap

### Fantasy Backtest with Graph Features

**Status:** NOT YET PERFORMED

Neo4j graph features (injury_cascade_target_boost, injury_cascade_carry_boost, teammate_injured_starter, historical_absorption_rate) have been integrated into the player feature pipeline but have **not been backtested against fantasy MAE**. The backtest is planned for after Phase 2 (PBP participation ingestion) when more graph features are available, to evaluate the full graph feature set together rather than piecemeal.

**Planned evaluation:**
- Run `python scripts/backtest_projections.py --seasons 2022,2023,2024 --scoring half_ppr` with graph features enabled vs disabled
- Compare MAE, RMSE, bias, and per-position accuracy
- Ship-gate decision: if graph features improve MAE, enable by default; if not, keep as opt-in or remove

**Rationale for deferral:** 4 features alone may not move the needle meaningfully on a 4.91 MAE baseline. PBP participation (Phase 2) will add route-running, coverage, and snap-level features that compound with injury cascade. Evaluating the full graph feature set together gives a cleaner signal on whether the Neo4j investment pays off.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Neo4j container starts and accepts connections | NEO4J-01 | Requires Docker daemon | Run `docker compose up -d` then `python -c "from src.graph_db import GraphDB; g = GraphDB(); print(g.is_available())"` |
| Graph ingestion loads real Bronze data into Neo4j | NEO4J-06 | Requires Docker + Bronze data | Run `python scripts/graph_ingestion.py --season 2024` and verify nodes in Neo4j browser (localhost:7474) |
| Full pipeline with graph features produces valid projections | NEO4J-04 | Requires trained models + Silver data + optional Neo4j | Run `python scripts/generate_projections.py --week 10 --season 2024 --ml --scoring half_ppr` and verify graph feature columns in output |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** passed (code validated; fantasy backtest deferred to post-Phase 2)
