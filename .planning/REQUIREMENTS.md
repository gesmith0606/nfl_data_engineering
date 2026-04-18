# Requirements: NFL Data Engineering Platform

**Defined:** 2026-04-17
**Core Value:** A rich NFL data lake powering both fantasy football projections and game prediction models

## v6.0 Requirements

### Data Quality

- [x] **DQAL-01**: All player positions match Sleeper API with zero misclassifications
- [x] **DQAL-02**: Rosters reflect 2026 trades/FA via daily Sleeper refresh
- [~] **DQAL-03**: Sanity check passes with 0 critical issues and is now a CI gate in deploy-web.yml (exit-code contract complete, gate wired to block both Vercel and ECR/SAM deploys; warning count >10 remains due to out-of-scope data issues -- negative projections, rookie absence, stale Silver)
- [x] **DQAL-04**: Preseason projections pass eye test (top 10 matches consensus structure -- Davante Adams LA, Puka Nacua LA, consensus reflects 2026 offseason)

### News & Sentiment

- [~] **NEWS-01**: Daily sentiment pipeline runs automatically (RSS + Sleeper + Reddit) — sources expanded in 61-01 (added RotoWire, PFT, DynastyFF); daily cron wiring pending in 61-04
- [~] **NEWS-02**: News page shows real articles with source, date, and player tags — Bronze ingestion for 3 new sources shipped in 61-01; UI wiring pending in 61-05
- [ ] **NEWS-03**: Team sentiment dashboard shows 32-team color-coded grid
- [ ] **NEWS-04**: Player sentiment signals (bullish/bearish) visible on player pages

### Design & UX

- [ ] **DSGN-01**: Design audit scores >7/10 on all pages (using design-engineer agent)
- [ ] **DSGN-02**: Consistent typography, color, and spacing across all 11 pages
- [ ] **DSGN-03**: Animations and micro-interactions on key user actions
- [ ] **DSGN-04**: Mobile-responsive layout on all pages

### AI Advisor

- [ ] **ADVR-01**: All 12 advisor tools return valid data on the live site _(baseline measured in 63-01: 4 PASS / 3 WARN / 5 FAIL — pending wave-2 fixes)_
- [ ] **ADVR-02**: Advisor can answer "who are the top 10 RBs" with real data
- [ ] **ADVR-03**: External rankings comparison works (Sleeper/FantasyPros/ESPN)
- [ ] **ADVR-04**: Floating chat widget renders and persists on all dashboard pages

### Matchup View

- [ ] **MTCH-01**: Offensive roster shows real player projections and ratings
- [ ] **MTCH-02**: Defensive roster uses actual NFL data (not placeholder hashes)
- [ ] **MTCH-03**: Matchup advantages calculated from real data
- [ ] **MTCH-04**: Schedule-aware — shows correct weekly opponent

### Agent Ecosystem

- [ ] **AGNT-01**: Consolidate 5 overlapping design skills into targeted invocations
- [x] **AGNT-02**: Activate dormant agents or archive them with reasoning — AGENT-INVENTORY.md produced (42 agents triaged; 0 dormant)
- [ ] **AGNT-03**: Add NFL-specific rules to .claude/rules/
- [ ] **AGNT-04**: Skill optimizer runs and produces passing audit (<3 items scoring below 6)

## v7.0 Requirements (Deferred)

### Marketing & Content
- **MKTG-01**: Remotion video generation from projection data
- **MKTG-02**: YouTube/Instagram/TikTok automated distribution
- **MKTG-03**: NotebookLM podcast generation pipeline

### Sleeper League Integration
- **SLP-01**: User enters Sleeper username and sees their leagues
- **SLP-02**: Roster display with projected points and start/sit badges
- **SLP-03**: AI advisor accesses user roster for personalized advice

## Out of Scope

| Feature | Reason |
|---------|--------|
| Remotion video generation | Deferred to v7.0 — website must be production-ready first |
| Sleeper OAuth integration | Deferred to v7.1 — public API sufficient for now |
| PFF paid data | Deferred to v8.0 — $300-500/season, evaluate ROI after launch |
| Multi-platform (ESPN/Yahoo) | Deferred to v9.0 — Sleeper-first strategy |
| Neural networks | Gradient boosting dominates tabular sports prediction at this scale |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DQAL-01 | Phase 60 | Complete |
| DQAL-02 | Phase 60 | Complete |
| DQAL-03 | Phase 60 | Partial (CI gate wired in deploy-web.yml via exit-code contract; warning count gated on out-of-scope data fixes: negative projections, rookie absence, stale Silver) |
| DQAL-04 | Phase 60 | Complete |
| NEWS-01 | Phase 61 | Partial (61-01 added RotoWire + PFT + DynastyFF ingestion; cron wiring pending in 61-04) |
| NEWS-02 | Phase 61 | Partial (61-01 Bronze layer shipped for 3 new sources; UI wiring pending in 61-05) |
| NEWS-03 | Phase 61 | Pending |
| NEWS-04 | Phase 61 | Pending |
| DSGN-01 | Phase 62 | Pending |
| DSGN-02 | Phase 62 | Pending |
| DSGN-03 | Phase 62 | Pending |
| DSGN-04 | Phase 62 | Pending |
| ADVR-01 | Phase 63 | In progress (baseline 63-01: 4P/3W/5F) |
| ADVR-02 | Phase 63 | Pending |
| ADVR-03 | Phase 63 | Pending |
| ADVR-04 | Phase 63 | Pending |
| MTCH-01 | Phase 64 | Pending |
| MTCH-02 | Phase 64 | Pending |
| MTCH-03 | Phase 64 | Pending |
| MTCH-04 | Phase 64 | Pending |
| AGNT-01 | Phase 65 | Pending |
| AGNT-02 | Phase 65 | Complete (65-01: 42-agent inventory, 0 dormant — see AGENT-INVENTORY.md) |
| AGNT-03 | Phase 65 | Pending |
| AGNT-04 | Phase 65 | Pending |

**Coverage:**
- v6.0 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-04-17*
*Last updated: 2026-04-17 after milestone v6.0 initialization*
