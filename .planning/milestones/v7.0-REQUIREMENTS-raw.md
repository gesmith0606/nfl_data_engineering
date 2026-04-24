# Requirements: v7.0 Production Stabilization

**Defined:** 2026-04-21
**Core Value:** A rich, well-modeled NFL data lake that serves as the foundation for both fantasy football decision-making and game prediction models — now delivered to end users via a production website that must work reliably.

**Context:** 2026-04-20 user audit of production found 6 regressions across roster data, predictions, lineups, matchups, news, and AI advisor — while the sanity-check quality gate (Phase 60) passed exit 0 through all of them. This milestone fixes the user-facing regressions AND the structural gap that let them ship. Marketing/integration work (v7.1+) is blocked until this stabilizes.

## v7.0 Requirements

Requirements for v7.0 release. Each maps to exactly one roadmap phase.

### Deployment Hotfixes (HOTFIX)

Fast fixes that restore broken surfaces; prerequisite for Phase 69 sentiment backfill.

- [ ] **HOTFIX-01**: `ANTHROPIC_API_KEY` is set in Railway environment and readable by the news extractor process
- [ ] **HOTFIX-02**: Railway Docker image bundles `data/bronze/schedules/` so `/api/teams/current-week` returns 200, not 503
- [ ] **HOTFIX-03**: Railway Docker image bundles `data/bronze/players/rosters/` (or equivalent) so `/api/teams/{team}/roster` returns 200, not 503
- [ ] **HOTFIX-04**: Predictions page frontend sends `season` and `week` query params to `/api/predictions` (or backend defaults them server-side), eliminating the 422
- [ ] **HOTFIX-05**: Lineups page frontend sends required query params to `/api/lineups`, eliminating the 422
- [ ] **HOTFIX-06**: `/api/predictions`, `/api/lineups`, `/api/teams/ARI/roster` all return 200 with well-shaped payloads when hit with no query string (graceful defaulting)

### Roster Refresh v2 (ROSTER)

`refresh_rosters.py` rewrite: the current script is the root cause of Kyler Murray still showing on Cardinals.

- [ ] **ROSTER-01**: Script handles released players (`team is None` or `status == 'Released'`) by marking them as FA instead of skipping (current script silently continues, preserving stale team)
- [ ] **ROSTER-02**: Script handles traded/moved players (`new_team != current_team`) with timestamped change entry in audit log
- [ ] **ROSTER-03**: Script writes corrections to **Bronze** `players/rosters/` (not just Gold preseason parquet), so `/api/teams/{team}/roster` reflects current truth
- [ ] **ROSTER-04**: Audit log (`roster_changes.log` or equivalent) is surfaced via GitHub Actions artifact or commit so changes are inspectable
- [ ] **ROSTER-05**: Kyler Murray correctly reflects his current team in production (`/api/teams/ARI/roster` does not list him; his actual team — if any — does)
- [ ] **ROSTER-06**: Daily cron (`daily-sentiment.yml`) calls the rewritten script and fails loudly on unexpected errors (current `|| echo` swallows failures)

### Sanity-Check v2 (SANITY)

Structural fix for the blindspot that let Phase 60 pass exit 0 through 6 regressions.

- [ ] **SANITY-01**: Quality gate probes `/api/predictions` with valid params and fails if payload shape is wrong or predictions list is empty when data should exist
- [ ] **SANITY-02**: Quality gate probes `/api/lineups` with valid params and fails if payload shape is wrong
- [ ] **SANITY-03**: Quality gate probes `/api/teams/{team}/roster` for a sampled subset (e.g. top-10 teams by snap count) and fails on 503
- [ ] **SANITY-04**: Quality gate validates `/api/news/team-events` payload **content** (e.g. `total_articles > 0` for at least N teams when news has accumulated), not just `len == 32`
- [ ] **SANITY-05**: Quality gate checks roster drift vs Sleeper canonical for top-50 fantasy players (flag team mismatches as CRITICAL — would have caught Kyler Murray)
- [ ] **SANITY-06**: Quality gate checks that news extractor ran recently (e.g. latest Silver sentiment timestamp within 48h) and fails if extractor is stalled
- [ ] **SANITY-07**: Quality gate checks `ANTHROPIC_API_KEY` is set when `ENABLE_LLM_ENRICHMENT=true` (prevents silent no-op)
- [ ] **SANITY-08**: Deploy gate invokes `--check-live` against the Railway URL as a blocking step (previously only post-deploy, annotation-only)
- [ ] **SANITY-09**: Post-deploy smoke job is promoted to a blocking gate with automatic rollback on failure (previously only annotated)
- [ ] **SANITY-10**: DQAL-03 carry-over — negative projection clamp, 2025 rookie ingestion, rank-gap threshold — all become sanity-check assertions (absorbed into v2)

### Sentiment Backfill (SENT)

After HOTFIX-01 sets the API key, run the extractor against accumulated news so the news page has actual content.

- [ ] **SENT-01**: News extractor runs successfully against accumulated Bronze news records (RSS + Sleeper + Reddit + RotoWire + PFT) once the API key is available
- [ ] **SENT-02**: `/api/news/team-events` shows `event_flags` and `total_articles > 0` for ≥20 of 32 teams (accounting for quiet-team variance)
- [ ] **SENT-03**: `/api/news/feed?season=2025&week=18` returns articles with `sentiment`, `event_flags`, `player_id`, and `summary` populated (not null)
- [ ] **SENT-04**: News page on website renders actual headlines with sentiment context (not just sentiment numbers without article text)
- [ ] **SENT-05**: AI advisor probes `getNewsFeed`, `getPlayerNews`, `getTeamSentiment`, `getSentimentSummary` all return PASS (not WARN) on Railway audit

### Frontend Empty/Error States (FE)

Defensive handling so partial-data or offseason conditions render gracefully instead of crashing.

- [ ] **FE-01**: Predictions page shows a friendly empty state with data-as-of metadata when `/api/predictions` returns `[]` (not a blank or crashed page)
- [ ] **FE-02**: Lineups page shows a friendly empty state when `/api/lineups` returns empty (and surfaces current week + season context)
- [ ] **FE-03**: Matchups page handles 503 from `/api/teams/current-week` with an offseason-appropriate fallback (not a blank page)
- [ ] **FE-04**: News page consistently shows headline text + sentiment context when data exists, and a "no news yet this week" empty state when it doesn't (not dangling sentiment numbers)
- [ ] **FE-05**: All four pages surface `data_as_of` (from backend `meta`) so users can see data freshness, matching the pattern from Phase 63

## Future Requirements

Deferred to v7.1+ — tracked but not in current roadmap.

### External Projections Comparison (EXTPROJ, v7.1)

- **EXTPROJ-01**: Projections page shows ESPN projection alongside our projection for comparison
- **EXTPROJ-02**: Projections page shows Sleeper projection alongside our projection for comparison
- **EXTPROJ-03**: Projections page shows Yahoo projection alongside our projection for comparison
- **EXTPROJ-04**: User can sort/filter by disagreement between our projection and the consensus (useful for identifying contrarian picks)
- **EXTPROJ-05**: Projections comparison data refreshed on a reasonable cadence (daily during season)

### Sleeper League Integration (SLEEP, v7.1)

- **SLEEP-01**: User enters Sleeper username → app fetches their leagues
- **SLEEP-02**: Roster view shows projected points + start/sit badges per player
- **SLEEP-03**: Advisor accesses user rosters for personalized advice (OAuth if needed)
- **SLEEP-04**: Waiver wire recommendations tailored to league settings

### Marketing & Content (MKT, v7.2)

- **MKT-01**: Remotion video generation pipeline
- **MKT-02**: YouTube/Instagram/TikTok distribution
- **MKT-03**: NotebookLM podcast pipeline

### Heuristic Consolidation (HEUR, v7.3)

- **HEUR-01**: Unify `generate_weekly_projections`, `generate_heuristic_predictions`, `compute_production_heuristic` into a single source of truth
- **HEUR-02**: Close the walk-forward-CV-vs-production divergence caused by the three duplicate functions

## Out of Scope

Explicitly excluded from v7.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| External projections comparison (ESPN/Sleeper/Yahoo) | v7.1 — stabilize first |
| Sleeper league integration | v7.1 — stabilize first |
| Marketing/content distribution | v7.2 — no point marketing a partially-broken site |
| Heuristic consolidation | v7.3 — model work, not stabilization |
| PFF paid data integration | v8.0 — cost gated, research milestone later |
| 61-03 event-adjustment activation | Bronze event data structurally null (0/48 weeks); revisit when accumulation is non-trivial |
| AWS S3 sync / credential refresh | Local-first workflow active; expiration is not blocking |
| Neo4j Aura cloud migration | v8.0+ — requires paid tier, not stabilization-critical |

## Traceability

Populated by roadmapper on 2026-04-21.

| Requirement | Phase | Status |
|-------------|-------|--------|
| HOTFIX-01   | 66    | Pending |
| HOTFIX-02   | 66    | Pending |
| HOTFIX-03   | 66    | Pending |
| HOTFIX-04   | 66    | Pending |
| HOTFIX-05   | 66    | Pending |
| HOTFIX-06   | 66    | Pending |
| ROSTER-01   | 67    | Pending |
| ROSTER-02   | 67    | Pending |
| ROSTER-03   | 67    | Pending |
| ROSTER-04   | 67    | Pending |
| ROSTER-05   | 67    | Pending |
| ROSTER-06   | 67    | Pending |
| SANITY-01   | 68    | Pending |
| SANITY-02   | 68    | Pending |
| SANITY-03   | 68    | Pending |
| SANITY-04   | 68    | Pending |
| SANITY-05   | 68    | Pending |
| SANITY-06   | 68    | Pending |
| SANITY-07   | 68    | Pending |
| SANITY-08   | 68    | Pending |
| SANITY-09   | 68    | Pending |
| SANITY-10   | 68    | Pending |
| SENT-01     | 69    | Pending |
| SENT-02     | 69    | Pending |
| SENT-03     | 69    | Pending |
| SENT-04     | 69    | Pending |
| SENT-05     | 69    | Pending |
| FE-01       | 70    | Pending |
| FE-02       | 70    | Pending |
| FE-03       | 70    | Pending |
| FE-04       | 70    | Pending |
| FE-05       | 70    | Pending |

**Coverage:**
- v7.0 requirements: 32 total
- Mapped to phases: 32 (100%)
- Unmapped: 0

**Phase requirement counts:**
- Phase 66 (P0 Deployment Hotfixes): 6 requirements
- Phase 67 (Roster Refresh v2): 6 requirements
- Phase 68 (Sanity-Check v2): 10 requirements
- Phase 69 (Sentiment Backfill): 5 requirements
- Phase 70 (Frontend Empty/Error States): 5 requirements

---
*Requirements defined: 2026-04-21*
*Last updated: 2026-04-21 — traceability populated by roadmapper*
