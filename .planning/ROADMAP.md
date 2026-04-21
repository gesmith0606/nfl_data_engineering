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
- 🚧 **v7.0 Production Stabilization** — Phases 66-70 (in progress)
- 📋 **v7.1 External Projections + Sleeper League** — planned
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

### 🚧 v7.0 Production Stabilization (In Progress)

**Milestone Goal:** Fix 6 production regressions found during 2026-04-20 user audit, close the sanity-check blindspots that let them ship, and restore reliable deploys before any marketing/integration work.

**Phase Numbering:**
- Integer phases (66, 67, 68, 69, 70): Planned milestone work
- Decimal phases (66.1, etc.): Urgent insertions (if needed; marked INSERTED)

**Summary checklist:**

- [ ] **Phase 66: P0 Deployment Hotfixes** — Restore 4 broken dashboard routes (predictions, lineups, matchups, news) via API key + Docker image + query-param fixes
- [ ] **Phase 67: Roster Refresh v2** — Rewrite `refresh_rosters.py` to handle released/traded players, write to Bronze, surface audit log (fixes Kyler Murray)
- [ ] **Phase 68: Sanity-Check v2** — Structural fix: live endpoint probes + payload-content validators + roster drift vs Sleeper + blocking post-deploy smoke (absorbs DQAL-03)
- [ ] **Phase 69: Sentiment Backfill** — Run extractor against accumulated news once API key lands; populate `event_flags` + `sentiment` + `summary` across 32 teams; advisor news tools flip WARN→PASS
- [ ] **Phase 70: Frontend Empty/Error States** — Defensive UX: predictions/lineups/matchups/news render empty states + `data_as_of` metadata instead of crashing on partial data

## Phase Details

### Phase 66: P0 Deployment Hotfixes
**Goal**: Restore all 4 partially/fully-broken dashboard routes in production within a day by fixing environment config, Docker image contents, and frontend query-string hygiene.
**Depends on**: Nothing (first phase of v7.0; unblocks Phase 69 and Phase 70)
**Requirements**: HOTFIX-01, HOTFIX-02, HOTFIX-03, HOTFIX-04, HOTFIX-05, HOTFIX-06
**Success Criteria** (what must be TRUE):
  1. `curl https://nfldataengineering-production.up.railway.app/api/predictions?season=2025&week=18` returns 200 with a non-empty predictions list in the payload
  2. `curl https://nfldataengineering-production.up.railway.app/api/lineups?season=2025&week=18` returns 200 with a well-shaped payload
  3. `curl https://nfldataengineering-production.up.railway.app/api/teams/ARI/roster` returns 200 (not 503) with a populated roster list
  4. All three endpoints above also return 200 with well-shaped payloads when hit with **no query string** (graceful server-side defaulting)
  5. `ANTHROPIC_API_KEY` is set in Railway environment and readable by the news extractor process (verifiable via `/api/health` or a dedicated probe)
  6. Predictions page and lineups page in the browser render data (not blank / not a stuck spinner / not a console 422)
**Plans**: TBD
**UI hint**: yes

### Phase 67: Roster Refresh v2
**Goal**: Rewrite the daily Sleeper-driven roster refresh so released, free-agent, and traded players are handled correctly, corrections land in Bronze (not just Gold preseason), and a surfaced audit log makes changes inspectable — with Kyler Murray as the acceptance canary.
**Depends on**: Nothing (can run parallel with Phase 68 and Phase 69)
**Requirements**: ROSTER-01, ROSTER-02, ROSTER-03, ROSTER-04, ROSTER-05, ROSTER-06
**Success Criteria** (what must be TRUE):
  1. Running `refresh_rosters.py --dry-run` against a Sleeper snapshot where a player has `team=null` or `status='Released'` reports that player as FA in stdout and in the audit log (not silently skipped)
  2. Running `refresh_rosters.py --dry-run` against a snapshot where `new_team != current_team` produces a timestamped "traded" entry in `roster_changes.log`
  3. Kyler Murray's team field on `/api/teams/ARI/roster` no longer lists him; if Sleeper reports him on a new team, that team's roster endpoint includes him; if Sleeper reports him as FA, no team lists him
  4. `data/bronze/players/rosters/` on Railway reflects the post-refresh truth (not just Gold preseason parquet) — verifiable by reading the most-recent Bronze file and confirming released-player corrections are present
  5. `roster_changes.log` from the daily cron is surfaced as a GitHub Actions artifact (or committed to repo) for at least the last run
  6. Daily `daily-sentiment.yml` cron invokes the rewritten script and fails loudly on unexpected errors (no `|| echo` swallowing)
**Plans**: TBD

### Phase 68: Sanity-Check v2
**Goal**: Rebuild the Phase 60 quality gate so that the 6 regressions from the 2026-04-20 audit would all have been caught — add live endpoint probes, payload-content validators, roster drift vs Sleeper canonical, extractor-freshness checks, and promote the post-deploy smoke to a blocking gate with rollback. This is the structural fix for the meta-issue.
**Depends on**: Nothing (can run parallel with Phase 67 and Phase 69)
**Requirements**: SANITY-01, SANITY-02, SANITY-03, SANITY-04, SANITY-05, SANITY-06, SANITY-07, SANITY-08, SANITY-09, SANITY-10
**Success Criteria** (what must be TRUE):
  1. Re-running the v2 sanity gate against the **pre-v7.0 production deploy** (snapshot state on 2026-04-20) would exit non-zero with CRITICAL issues identifying at least: Kyler Murray roster drift, empty `event_flags` on team-events, 422 on `/api/predictions`, 422 on `/api/lineups`, 503 on `/api/teams/{team}/roster`, and stalled news extractor
  2. `scripts/sanity_check_projections.py --check-live <railway-url>` probes `/api/predictions`, `/api/lineups`, and `/api/teams/{team}/roster` for a sampled top-N team set and fails on non-200 or empty-payload-when-data-expected
  3. `--check-live` validates `/api/news/team-events` **content** (e.g. `total_articles > 0` for at least N of 32 teams when news has accumulated), not just `len == 32`
  4. Gate asserts `ANTHROPIC_API_KEY` is set whenever `ENABLE_LLM_ENRICHMENT=true`, and asserts the latest Silver sentiment timestamp is within 48h
  5. The GitHub Actions deploy job invokes `--check-live` against Railway as a **blocking** step, and the post-deploy smoke job is promoted to blocking with automatic rollback on failure (not just annotation)
  6. DQAL-03 carry-over items (negative-projection clamp, 2025 rookie ingestion presence, rank-gap threshold) are asserted by the sanity gate and resolve the v6.0 partial status
**Plans**: TBD

### Phase 69: Sentiment Backfill
**Goal**: With the API key landed in Phase 66, run the news extractor against all accumulated Bronze news records so the news page has real content, `event_flags`/`sentiment`/`summary` populate across 32 teams, and the AI advisor's 4 news tools flip from WARN to PASS on the live Railway audit.
**Depends on**: Phase 66 (HOTFIX-01 API key + HOTFIX-02/03 Docker image)
**Requirements**: SENT-01, SENT-02, SENT-03, SENT-04, SENT-05
**Success Criteria** (what must be TRUE):
  1. `/api/news/team-events` returns `total_articles > 0` and non-empty `event_flags` for **at least 20 of 32 teams** (allowing for quiet-team offseason variance)
  2. `/api/news/feed?season=2025&week=18` returns articles where `sentiment`, `event_flags`, `player_id`, and `summary` are all populated (not null) for the majority of items
  3. The news page on https://frontend-jet-seven-33.vercel.app renders actual headline text with sentiment context (not dangling sentiment numbers with no article body)
  4. `scripts/audit_advisor_tools.py` run against Railway reports `getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, and `getSentimentSummary` as PASS (not WARN)
  5. A run of the daily sentiment cron ingests + extracts + aggregates end-to-end without the extractor stage being skipped or failing silently
**Plans**: TBD
**UI hint**: yes

### Phase 70: Frontend Empty/Error States
**Goal**: Defensive UX layer — when upstream data is partial, stale, or legitimately empty (offseason, no-news week, etc.), the frontend renders friendly empty states with freshness metadata instead of crashing or blanking. Matches the `data_as_of` pattern established in Phase 63.
**Depends on**: Phase 66 (backend must stop 422-ing), partially Phase 69 (news page benefits from real content for the non-empty path)
**Requirements**: FE-01, FE-02, FE-03, FE-04, FE-05
**Success Criteria** (what must be TRUE):
  1. Predictions page shows a friendly empty state with `data_as_of` metadata when `/api/predictions` returns `[]` — no blank screen, no unhandled error
  2. Lineups page shows a friendly empty state surfacing current season/week context when `/api/lineups` returns empty
  3. Matchups page handles `/api/teams/current-week` returning 503 with an offseason-appropriate fallback (e.g. "No games this week — showing preseason preview") rather than a blank page
  4. News page consistently shows headline text + sentiment context when data exists, **and** a "no news yet this week" empty state when it doesn't (no dangling sentiment numbers without article bodies)
  5. All four pages (predictions, lineups, matchups, news) surface `data_as_of` from backend `meta` in a visible location, matching the Phase 63 pattern
**Plans**: TBD
**UI hint**: yes

### 📋 v7.1 External Projections + Sleeper League (Planned)

Preliminary scope — not yet broken into phases. See PROJECT.md "Future Milestones":
- External projections comparison: ESPN/Sleeper/Yahoo side-by-side on projections page (EXTPROJ-01..05)
- Sleeper league integration: username → leagues, roster import, personalized advice, OAuth (SLEEP-01..04)

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
