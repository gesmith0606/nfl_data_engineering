# Roadmap: NFL Data Engineering Platform

## Milestones

- v1.0 Bronze Expansion -- Phases 1-7 (shipped 2026-03-08)
- v1.1 Bronze Backfill -- Phases 8-14 (shipped 2026-03-13)
- v1.2 Silver Expansion -- Phases 15-19 (shipped 2026-03-15)
- v1.3 Prediction Data Foundation -- Phases 20-23 (shipped 2026-03-19)
- v1.4 ML Game Prediction -- Phases 24-27 (shipped 2026-03-22)
- v2.0 Prediction Model Improvement -- Phases 28-31 (shipped 2026-03-27)
- v2.1 Market Data -- Phases 32-34 (shipped 2026-03-28)
- v2.2 Full Odds + Holdout Reset -- Phases 35-38 (shipped 2026-03-29)
- v3.0 Player Fantasy Prediction System -- Phases 39-48 (shipped 2026-04-01)
- v3.1 Graph-Enhanced Fantasy Projections -- Phases 49-53 (shipped 2026-04-03)
- v3.2 Model Perfection -- Phases 54-57 (shipped 2026-04-09)
- *v4.0 Production Launch -- Phases W7-W12 (parallel, see .planning/v4.0-web/)*
- *v5.0 Sentiment v2 -- Phases SV2-01 through SV2-04 (complete)*
- **v6.0 Website Production Ready + Agent Ecosystem -- Phases 60-65 (current)**

---

## v6.0 Website Production Ready + Agent Ecosystem

**Goal:** Get the website to production quality with accurate data, polished design, working news feeds, and a capable AI advisor -- while optimizing the agent/skill ecosystem.

All 6 phases are independent and can be worked in any order.

## Phases

- [x] **Phase 60: Data Quality** - Fix stale rosters, position misclassifications, and projection sanity issues
- [ ] **Phase 61: News & Sentiment Live** - Daily automated news ingestion with real articles on the website
- [ ] **Phase 62: Design & UX Polish** - Premium visual design, consistent styling, animations, mobile responsiveness
- [ ] **Phase 63: AI Advisor Hardening** - Verify all 12 advisor tools work end-to-end on the live site
- [ ] **Phase 64: Matchup View Completion** - Real defensive data, proper ratings, schedule-aware opponents
- [ ] **Phase 65: Agent Ecosystem Optimization** - Consolidate skills, activate or archive dormant agents, add NFL rules

## Phase Details

### Phase 60: Data Quality
**Goal**: Users see accurate, current player data across the entire site
**Depends on**: Nothing (independent)
**Requirements**: DQAL-01, DQAL-02, DQAL-03, DQAL-04
**Success Criteria** (what must be TRUE):
  1. Every player on the projections page shows the correct position (QB/RB/WR/TE/K) matching Sleeper API
  2. Rosters reflect 2026 offseason trades and free agency moves (no player on the wrong team)
  3. Running the sanity check script produces fewer than 10 warnings and zero critical issues
  4. The top 10 projected players at each position align structurally with consensus rankings (no obvious absurdities like a backup QB in top 5)
**Plans:** 3/3 plans executed (COMPLETE)
Plans:
- [x] 60-01-PLAN.md -- Extend roster refresh with position update and change logging
- [x] 60-02-PLAN.md -- Enhance sanity check with freshness, live consensus, updated top-50
- [x] 60-03-PLAN.md -- Wire sanity check as CI gate in deploy-web.yml

### Phase 61: News & Sentiment Live
**Goal**: Users can browse real news articles and see sentiment signals on the website
**Depends on**: Nothing (independent)
**Requirements**: NEWS-01, NEWS-02, NEWS-03, NEWS-04
**Success Criteria** (what must be TRUE):
  1. The daily sentiment pipeline runs automatically via cron and processes RSS, Sleeper, and Reddit sources
  2. The news page displays real articles with source attribution, publication date, and tagged player names
  3. The team sentiment dashboard shows all 32 teams in a color-coded grid (green=bullish, red=bearish)
  4. Visiting a player detail page shows bullish/bearish sentiment badges derived from recent news
**Plans**: TBD
**UI hint**: yes

### Phase 62: Design & UX Polish
**Goal**: The website looks and feels like a premium product on any device
**Depends on**: Nothing (independent)
**Requirements**: DSGN-01, DSGN-02, DSGN-03, DSGN-04
**Success Criteria** (what must be TRUE):
  1. A design audit of every page scores above 7/10 using the design-engineer agent evaluation criteria
  2. Typography, color palette, and spacing are consistent across all 11 pages (no visual jarring when navigating)
  3. Key user actions (page transitions, button clicks, data loads) have smooth animations or micro-interactions
  4. Every page renders correctly and is usable on mobile viewport (375px width)
**Plans**: TBD
**UI hint**: yes

### Phase 63: AI Advisor Hardening
**Goal**: Users can ask the AI advisor any fantasy question and get accurate, data-backed answers
**Depends on**: Nothing (independent)
**Requirements**: ADVR-01, ADVR-02, ADVR-03, ADVR-04
**Success Criteria** (what must be TRUE):
  1. All 12 advisor tools return valid, non-error data when invoked on the live production site
  2. Asking "who are the top 10 RBs" returns a ranked list with real projected points from the Gold layer
  3. The advisor can compare player rankings against external sources (Sleeper ADP, FantasyPros, ESPN)
  4. The floating chat widget renders on every dashboard page and conversation persists across page navigation
**Plans**: 6 (63-01 baseline audit [DONE 4P/3W/5F], 63-02 schema fixes, 63-03 missing routes, 63-04 data gaps, 63-05 ship gate, 63-06 chat widget)
**UI hint**: yes

### Phase 64: Matchup View Completion
**Goal**: Users can evaluate weekly matchups using real NFL data instead of placeholders
**Depends on**: Nothing (independent)
**Requirements**: MTCH-01, MTCH-02, MTCH-03, MTCH-04
**Success Criteria** (what must be TRUE):
  1. The offensive roster in matchup view shows real player names with their projected fantasy points and positional ratings
  2. The defensive roster displays actual NFL player names and stats (no placeholder hashes or dummy data)
  3. Matchup advantage indicators are calculated from real team defensive metrics (not hardcoded)
  4. The matchup view shows the correct weekly opponent based on the current NFL schedule
**Plans**: TBD
**UI hint**: yes

### Phase 65: Agent Ecosystem Optimization
**Goal**: The .claude folder is clean, efficient, and tuned for NFL data engineering work
**Depends on**: Nothing (independent)
**Requirements**: AGNT-01, AGNT-02, AGNT-03, AGNT-04
**Success Criteria** (what must be TRUE):
  1. The 5 overlapping design-related skills are consolidated into targeted, non-redundant invocations
  2. Every agent in .claude/agents/ is either actively used (with a clear purpose) or archived with documented reasoning
  3. NFL-specific rules exist in .claude/rules/ covering data conventions, scoring formats, and validation patterns
  4. The skill optimizer audit completes with fewer than 3 items scoring below 6/10
**Plans**: 4 (65-01 inventory [DONE — 42 agents, 29 skills triaged], 65-02 design consolidation, 65-03 NFL rules, 65-04 skill-optimizer audit)

## Requirement Coverage

| REQ-ID | Phase | Description |
|--------|-------|-------------|
| DQAL-01 | 60 | Player positions match Sleeper API |
| DQAL-02 | 60 | Rosters reflect 2026 trades/FA |
| DQAL-03 | 60 | Sanity check <10 warnings, 0 critical |
| DQAL-04 | 60 | Top 10 projections match consensus structure |
| NEWS-01 | 61 | Daily sentiment pipeline automated |
| NEWS-02 | 61 | News page with real articles |
| NEWS-03 | 61 | Team sentiment 32-team grid |
| NEWS-04 | 61 | Player sentiment badges |
| DSGN-01 | 62 | Design audit >7/10 all pages |
| DSGN-02 | 62 | Consistent typography/color/spacing |
| DSGN-03 | 62 | Animations and micro-interactions |
| DSGN-04 | 62 | Mobile-responsive all pages |
| ADVR-01 | 63 | All 12 advisor tools return valid data |
| ADVR-02 | 63 | Top 10 query with real data |
| ADVR-03 | 63 | External rankings comparison |
| ADVR-04 | 63 | Floating chat widget on all pages |
| MTCH-01 | 64 | Offensive roster with real projections |
| MTCH-02 | 64 | Defensive roster with actual NFL data |
| MTCH-03 | 64 | Matchup advantages from real data |
| MTCH-04 | 64 | Schedule-aware weekly opponent |
| AGNT-01 | 65 | Consolidate 5 overlapping design skills |
| AGNT-02 | 65 | Activate or archive dormant agents |
| AGNT-03 | 65 | NFL-specific rules in .claude/rules/ |
| AGNT-04 | 65 | Skill optimizer audit <3 items below 6 |

**Coverage: 24/24 v6.0 requirements mapped (100%)**

## Progress

**Execution Order:** Phases 60-65 are independent and can be worked in any order.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 60. Data Quality | 3/3 | Complete | 2026-04-17 |
| 61. News & Sentiment Live | 0/TBD | Not started | - |
| 62. Design & UX Polish | 0/TBD | Not started | - |
| 63. AI Advisor Hardening | 1/6 | In progress | - |
| 64. Matchup View Completion | 0/TBD | Not started | - |
| 65. Agent Ecosystem Optimization | 1/4 | In progress | - |
