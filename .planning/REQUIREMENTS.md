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

- [x] **NEWS-01**: Daily sentiment pipeline runs automatically (RSS + Sleeper + Reddit + RotoWire + PFT) — sources expanded in 61-01; daily cron wiring + D-06 resilience shipped in 61-04 (5 sources, 7 regression tests, ENABLE_LLM_ENRICHMENT feature flag at `0 12 * * *` UTC)
- [x] **NEWS-02**: News page shows real articles with source, date, and player tags — 61-01 Bronze ingestion (3 new sources), 61-05 UI wiring + EventBadges component shipped, 61-06 optional LLM enrichment populates NewsItem.summary when ENABLE_LLM_ENRICHMENT=true
- [x] **NEWS-03**: Team sentiment dashboard shows 32-team color-coded grid — 61-05 shipped GET /api/news/team-events (always 32 rows, zero-filled) + TeamEventDensityGrid.tsx with React Query 5-min refetch, bearish/bullish/neutral color coding, keyboard-navigable tiles
- [x] **NEWS-04**: Player sentiment signals (bullish/bearish) visible on player pages — 61-05 shipped GET /api/news/player-badges/{player_id} + EventBadges.tsx (accessible role=list, colored ring from overallLabel) wired into player-detail.tsx header

### Design & UX

- [x] **DSGN-01**: Design audit scores >7/10 on all pages — 62-06 AUDIT-FINAL: 11/11 pages > 7, mean 7.06 → 7.80 (+0.74)
- [x] **DSGN-02**: Consistent typography, color, and spacing across all 11 pages — token foundation in 62-02, consumption in 62-03 (pages 1-5 + shell) and 62-04 (pages 6-11)
- [x] **DSGN-03**: Animations and micro-interactions on key user actions — motion-primitives.tsx (FadeIn, Stagger, HoverLift, PressScale, DataLoadReveal) applied across 11 pages; prediction edge shimmer on |edge| ≥ 3.0
- [x] **DSGN-04**: Mobile-responsive layout on all pages — 62-05 MOBILE-AUDIT: 11/11 pages zero horizontal overflow at 375px, responsive-column-hide on tables, chat widget full-screen on mobile

### AI Advisor

- [x] **ADVR-01**: All 12 advisor tools return valid data on the live site — 63-06 live Railway re-audit: 7 PASS / 5 WARN / **0 FAIL** (baseline 4/3/5). 5 WARNs are documented `warn_on_empty` offseason payloads.
- [x] **ADVR-02**: Advisor can answer "who are the top 10 RBs" with real data — 63-04 ships `meta.data_as_of` on `/api/projections`, new `/api/projections/latest-week` endpoint, and advisor `getPositionRankings` auto-resolves default week; live transcript in 63-06 ADVISOR-E2E.md confirms end-to-end
- [x] **ADVR-03**: External rankings comparison works (Sleeper/FantasyPros/ESPN) — 63-03 cache-first fallback, live Sleeper returns 10 players with rank_diff math; FantasyPros degrades gracefully on upstream block (stale:true, empty list)
- [x] **ADVR-04**: Floating chat widget renders and persists on all dashboard pages — 63-05 usePersistentChat hook + localStorage (key advisor:conversation:v1), verified on all 10 /dashboard/* routes via Playwright UAT

### Matchup View

- [ ] **MTCH-01**: Offensive roster shows real player projections and ratings _(64-02 shipped OL backend; full requirement waits on 64-04 frontend wiring)_
- [x] **MTCH-02**: Defensive roster uses actual NFL data (not placeholder hashes) — 64-02 ships `/api/teams/{team}/roster?side=defense` with real NFL names + slot_hint
- [ ] **MTCH-03**: Matchup advantages calculated from real data
- [x] **MTCH-04**: Schedule-aware — shows correct weekly opponent — 64-02 ships `/api/teams/current-week` with schedule + offseason fallback

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
| NEWS-01 | Phase 61 | Complete (61-01 added RotoWire + PFT + DynastyFF ingestion; 61-04 wired cron + D-06 resilience + ENABLE_LLM_ENRICHMENT feature flag) |
| NEWS-02 | Phase 61 | Complete (61-01 Bronze ingestion, 61-05 UI + event badges, 61-06 optional LLM summary enrichment) |
| NEWS-03 | Phase 61 | Complete (61-05 team-events endpoint + TeamEventDensityGrid.tsx shipped) |
| NEWS-04 | Phase 61 | Complete (61-05 player-badges endpoint + EventBadges.tsx shipped) |
| DSGN-01 | Phase 62 | Complete (62-06 AUDIT-FINAL: 11/11 > 7, mean 7.06 → 7.80) |
| DSGN-02 | Phase 62 | Complete (62-02 tokens, 62-03 pages 1-5, 62-04 pages 6-11) |
| DSGN-03 | Phase 62 | Complete (62-04 motion primitives + 62-06 pages 1-5 retrofit + edge shimmer) |
| DSGN-04 | Phase 62 | Complete (62-05 375px mobile audit: 11/11 PASS, zero overflow) |
| ADVR-01 | Phase 63 | Complete (63-06 live Railway audit: 7P/5W/0F — FAIL count 5→0) |
| ADVR-02 | Phase 63 | Complete (63-04: `meta.data_as_of` + `/api/projections/latest-week` + advisor auto-resolve; 10 contract tests) |
| ADVR-03 | Phase 63 | Complete (63-03 cache-first fallback; live Sleeper PASS, FantasyPros graceful stale) |
| ADVR-04 | Phase 63 | Complete (63-05 usePersistentChat + localStorage; Playwright UAT 10/10 routes) |
| MTCH-01 | Phase 64 | Partial (64-02 ships OL side of roster endpoint; full requirement lands with 64-04 frontend wiring) |
| MTCH-02 | Phase 64 | Complete (64-02: `/api/teams/{team}/roster?side=defense` returns real NFL players with slot_hint + snap_pct) |
| MTCH-03 | Phase 64 | Pending |
| MTCH-04 | Phase 64 | Complete (64-02: `/api/teams/current-week` schedule-aware with offseason fallback) |
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
*Last updated: 2026-04-19 after Phase 61-06 optional LLM enrichment shipped*
