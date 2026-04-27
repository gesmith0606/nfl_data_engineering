# Roadmap: NFL Data Engineering Platform

## Milestones

- ✅ **v1.0 Bronze Expansion** — Phases 1-7 (shipped 2026-03-08)
- ✅ **v1.1 Bronze Backfill** — Phases 8-14 (shipped 2026-03-13)
- ✅ **v1.2 Silver Expansion** — Phases 15-19 (shipped 2026-03-15)
- ✅ **v1.3 Prediction Data Foundation** — Phases 20-23 (shipped 2026-03-19)
- ✅ **v1.4 ML Game Prediction** — Phases 24-27 (shipped 2026-03-22)
- ✅ **v2.0 Prediction Model Improvement** — Phases 28-31 (shipped 2026-03-27)
- ✅ **v2.1 Market Data** — Phases 32-34 (shipped 2026-03-28)
- ✅ **v2.2 Full Odds + Holdout Reset** — Phases 35-38 (shipped 2026-03-29)
- ✅ **v3.0 Player Fantasy Prediction System** — Phases 39-48 (shipped 2026-04-01)
- ✅ **v3.1 Graph-Enhanced Fantasy Projections** — Phases 49-53 (shipped 2026-04-03)
- ✅ **v3.2 Model Perfection** — Phases 54-57 (shipped 2026-04-09)
- *v4.0 Production Launch* — Phases W7-W12 (parallel, see `.planning/v4.0-web/`)
- *v5.0 Sentiment v2* — Phases SV2-01 through SV2-04 (complete)
- ✅ **v6.0 Website Production Ready + Agent Ecosystem** — Phases 60-65 (shipped 2026-04-20)
- ✅ **v7.0 Production Stabilization** — Phases 66-70 (shipped 2026-04-24; 4 human_needed + 1 passed — see `.planning/milestones/v7.0-ROADMAP.md`)
- ✅ **v7.1 Draft Season Readiness** — Phases 71-75 (shipped 2026-04-26; LLM-primary extraction, external projections comparison, Sleeper league integration, tech debt cleanup — see `.planning/milestones/v7.1-ROADMAP.md`)
- 📋 **v7.2 Marketing & Content** — planned

## Phases

<details>
<summary>✅ v6.0 Website Production Ready + Agent Ecosystem (Phases 60-65) — SHIPPED 2026-04-20</summary>

- [x] Phase 60: Data Quality (3/3 plans) — completed 2026-04-17
- [x] Phase 61: News & Sentiment Live (6/6 plans) — completed 2026-04-19
- [x] Phase 62: Design & UX Polish (6/6 plans) — completed 2026-04-20
- [x] Phase 63: AI Advisor Hardening (6/6 plans) — completed 2026-04-20
- [x] Phase 64: Matchup View Completion (4/4 plans) — completed 2026-04-20
- [x] Phase 65: Agent Ecosystem Optimization (4/4 plans) — completed 2026-04-20

Full details: `.planning/milestones/v6.0-ROADMAP.md` | Requirements: `.planning/milestones/v6.0-REQUIREMENTS.md`

</details>

<details>
<summary>✅ v7.0 Production Stabilization (Phases 66-70) — SHIPPED 2026-04-24</summary>

- [x] Phase 66: P0 Deployment Hotfixes (6 reqs) — human_needed, code shipped 2026-04-21
- [x] Phase 67: Roster Refresh v2 (6 reqs) — human_needed, code shipped 2026-04-22
- [x] Phase 68: Sanity-Check v2 (10 reqs, 57 tests) — 5/6 passed + 1 human_needed (live rollback proof)
- [o] Phase 69: Sentiment Backfill (5 reqs) — human_needed, blocked on GH Secret + Variable setup
- [x] Phase 70: Frontend Empty/Error States (5 reqs, 10 tests) — passed 2026-04-24

Full details: `.planning/milestones/v7.0-ROADMAP.md` | Requirements: `.planning/milestones/v7.0-REQUIREMENTS.md` | Audit: `.planning/v7.0-MILESTONE-AUDIT.md`

</details>

<details>
<summary>✅ v7.1 Draft Season Readiness (Phases 71-75) — SHIPPED 2026-04-26</summary>

- [x] Phase 71: LLM-Primary Extraction (5/5 plans) — passed; 5.57× signal lift; $1.57/wk cost
- [x] Phase 72: Event Flag Expansion + Non-Player Attribution (5/5 plans) — passed 2026-04-27; EVT-04 9/32 + EVT-05 32+9 against Railway live; CONTEXT D-04 amended (15→8) post-Phase-71 attribution narrowing
- [x] Phase 73: External Projections Comparison (5/5 plans) — code-complete; EXTP-05 first cron pending
- [x] Phase 74: Sleeper League Integration — passed; getUserRoster advisor tool wired
- [x] Phase 75: v7.0 Tech Debt Cleanup (8/8 TD items) — passed

Full details: `.planning/milestones/v7.1-ROADMAP.md` | Requirements: `.planning/milestones/v7.1-REQUIREMENTS.md` | Audit: `.planning/v7.1-MILESTONE-AUDIT.md`

</details>

### 📋 v7.2 Marketing & Content (Planned)

Preliminary scope — not yet broken into phases.
- Remotion video generation from projection data (MKT-01)
- YouTube/Instagram/TikTok automated distribution (MKT-02)
- NotebookLM podcast generation pipeline (MKT-03)

## Progress

**Execution Order:**
v7.0 phases execute as: 66 → (67 ∥ 68 ∥ 69) → 70
- 66 is blocking for 69 (API key + Docker image) and 70 (backend stops 422-ing)
- 67 and 68 can run in parallel with 69 (no data dependencies between them)
- 70 comes last because it benefits from all upstream data being correct

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 60. Data Quality | v6.0 | 3/3 | Complete | 2026-04-17 |
| 61. News & Sentiment Live | v6.0 | 6/6 | Complete | 2026-04-19 |
| 62. Design & UX Polish | v6.0 | 6/6 | Complete | 2026-04-20 |
| 63. AI Advisor Hardening | v6.0 | 6/6 | Complete | 2026-04-20 |
| 64. Matchup View Completion | v6.0 | 4/4 | Complete | 2026-04-20 |
| 65. Agent Ecosystem Optimization | v6.0 | 4/4 | Complete | 2026-04-20 |
| 66. P0 Deployment Hotfixes | v7.0 | 0/TBD | Not started | - |
| 67. Roster Refresh v2 | v7.0 | 0/TBD | Not started | - |
| 68. Sanity-Check v2 | v7.0 | 0/TBD | Not started | - |
| 69. Sentiment Backfill | v7.0 | 0/TBD | Not started | - |
| 70. Frontend Empty/Error States | v7.0 | 0/TBD | Not started | - |
| 71. LLM-Primary Extraction | v7.1 | 6/5 | Complete    | 2026-04-24 |
| 72. Event Flag Expansion | v7.1 | 5/5 | Complete    | 2026-04-27 |
| 73. External Projections Comparison | v7.1 | 2/5 | Complete    | 2026-04-26 |
| 74. Sleeper League Integration | v7.1 | 1/0 | Complete    | 2026-04-26 |
| 75. v7.0 Tech Debt Cleanup | v7.1 | 1/0 | Complete    | 2026-04-26 |
